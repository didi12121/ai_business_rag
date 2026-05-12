import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import text

logger = logging.getLogger("ai_business_rag")

from app.database import SessionLocal
from app.models.request import AskRequest
from app.core.sys_config import get_ai_config, refresh_ai_config_cache
from app.core.sql_safety import check_sql_safety, build_display_sql, is_modification_request
from app.core.intent_parser import parse_intent
from app.core.quick_intent import quick_intent_match
from app.core.business_context import (
    load_table_schemas, load_field_schemas,
    load_business_rules, load_query_template,
)
from app.core.date_resolver import resolve_relative_date_params
from app.core.sql_renderer import render_sql_template
from app.core.answer_generator import generate_answer, explain_business_rule
from app.core.free_query import generate_free_sql

router = APIRouter(prefix="/api/ai")


# ── helpers ──────────────────────────────────────────────

def _now():
    return int(time.time() * 1000)

def _normalize_value(value):
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, datetime): return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date): return value.strftime("%Y-%m-%d")
    return value

def _normalize_rows(rows): return [{k: _normalize_value(v) for k, v in r.items()} for r in rows]

def _save_chat_log(session_id, user_id, question, intent_code, intent_result,
                   params, sql_text, rows, answer, success, error_msg, duration_ms,
                   query_mode=None, free_sql_reason=None, used_tables=None,
                   risk_level=None, estimated_rows=None):
    db = SessionLocal()
    try:
        db.execute(text(
            "INSERT INTO ai_chat_log "
            "(session_id, user_id, question, intent_code, intent_result, "
            "params_json, sql_text, sql_rows_json, answer, success, error_msg, "
            "model_name, duration_ms, create_time, "
            "query_mode, free_sql_reason, used_tables, risk_level, estimated_rows) "
            "VALUES "
            "(:sid, :uid, :q, :ic, :ir, :pj, :st, :sr, :a, :ok, :em, "
            ":mn, :dur, NOW(), :qm, :fsr, :ut, :rl, :er)"
        ), {
            "sid": session_id, "uid": user_id, "q": question, "ic": intent_code,
            "ir": json.dumps(intent_result, ensure_ascii=False),
            "pj": json.dumps(params, ensure_ascii=False),
            "st": sql_text,
            "sr": json.dumps(rows[:50], ensure_ascii=False) if rows else None,
            "a": answer, "ok": 1 if success else 0, "em": error_msg,
            "mn": "llm",
            "dur": duration_ms,
            "qm": query_mode, "fsr": free_sql_reason,
            "ut": json.dumps(used_tables) if used_tables else None,
            "rl": risk_level, "er": estimated_rows,
        })
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ── query handlers ───────────────────────────────────────

async def run_template_query(question, intent_code, intent_result, show_sql):
    template = load_query_template(intent_code)
    if not template:
        return {"success": False, "question": question,
                "answer": "没有找到对应查询模板", "errorCode": "TEMPLATE_NOT_FOUND",
                "errorMsg": f"intent {intent_code} 对应的模板不存在"}

    params = resolve_relative_date_params(intent_result.get("params", {}), question)

    try:
        sql, bind_params = render_sql_template(template["sql_template"], params)
    except Exception as e:
        return {"success": False, "question": question,
                "answer": "SQL 模板渲染失败", "errorCode": "SQL_RENDER_ERROR",
                "errorMsg": str(e)}

    config = get_ai_config()
    try:
        sql = check_sql_safety(sql, max_rows=config.get("free_sql.max_rows", 200))
    except Exception as e:
        return {"success": False, "question": question,
                "answer": "SQL 安全检查未通过", "errorCode": "SQL_SAFETY_ERROR",
                "errorMsg": str(e)}

    db = SessionLocal()
    try:
        db.execute(text("SET SESSION max_execution_time = :t"),
                   {"t": config.get("sql.timeout_seconds", 10) * 1000})
        result = db.execute(text(sql), bind_params)
        rows_raw = result.fetchall()
        columns = list(result.keys())
        rows = [dict(zip(columns, r)) for r in rows_raw]
    except Exception as e:
        return {"success": False, "question": question,
                "answer": "SQL 执行失败", "errorCode": "SQL_EXECUTE_ERROR",
                "errorMsg": str(e)}
    finally:
        db.close()

    business_rules = load_business_rules()
    try:
        answer = await generate_answer(
            question=question, intent=intent_code,
            template_description=template.get("description", ""),
            business_rules=business_rules, rows=rows,
            result_description=template.get("result_description", ""),
        )
    except Exception as e:
        return {"success": False, "question": question,
                "answer": "AI 回答生成失败", "errorCode": "ANSWER_GENERATE_ERROR",
                "errorMsg": str(e)}

    display_sql = build_display_sql(sql, bind_params) if show_sql else None
    return {
        "success": True, "question": question, "queryMode": "template",
        "intent": intent_code, "confidence": intent_result.get("confidence", 0),
        "params": params, "answer": answer,
        "sql": display_sql, "rows": _normalize_rows(rows), "rowCount": len(rows),
        "templateName": template["template_name"],
    }


async def run_free_sql_query(question, show_sql):
    config = get_ai_config()
    free_result = await generate_free_sql(question)

    if not free_result["canGenerate"]:
        return {
            "success": False, "question": question, "queryMode": "free_sql",
            "answer": f"无法生成有效查询：{free_result['reason']}",
            "errorCode": "FREE_SQL_GENERATE_FAILED",
            "errorMsg": free_result["reason"],
            "freeSqlReason": free_result["reason"],
            "usedTables": free_result.get("usedTables", []),
            "riskLevel": free_result.get("riskLevel", "high"),
        }

    sql = free_result["sql"]
    if not sql:
        return {
            "success": False, "question": question, "queryMode": "free_sql",
            "answer": "LLM 未生成 SQL", "errorCode": "FREE_SQL_GENERATE_FAILED",
            "errorMsg": "LLM 返回空 SQL",
        }
    bind_params = free_result.get("params")
    if not isinstance(bind_params, dict):
        bind_params = {}

    # Safety check
    try:
        sql = check_sql_safety(sql, max_rows=config.get("free_sql.max_rows", 200), is_free_sql=True)
    except Exception as e:
        return {
            "success": False, "question": question, "queryMode": "free_sql",
            "answer": "SQL 安全检查未通过", "errorCode": "SQL_SAFETY_ERROR",
            "errorMsg": str(e), "sql": sql,
            "freeSqlReason": free_result["reason"],
            "usedTables": free_result.get("usedTables", []),
            "riskLevel": free_result.get("riskLevel", "high"),
        }

    # EXPLAIN check
    estimated_rows = None
    if config.get("free_sql.explain_before_run", True):
        db = SessionLocal()
        try:
            explain_result = db.execute(text(f"EXPLAIN {sql}"), bind_params).fetchall()
            total = 0
            for r in explain_result:
                try:
                    total += int(r._mapping.get("rows", 0) or 0)
                except (ValueError, TypeError):
                    pass
            estimated_rows = total
            max_est = config.get("free_sql.max_estimated_rows", 50000)
            if estimated_rows > max_est:
                db.close()
                return {
                    "success": False, "question": question, "queryMode": "free_sql",
                    "answer": "查询范围过大，请增加时间、厂家、产品等条件后再试。",
                    "errorCode": "SQL_TOO_LARGE", "errorMsg": f"预估扫描 {estimated_rows} 行，超过限制 {max_est}",
                    "sql": sql, "estimatedRows": estimated_rows,
                    "freeSqlReason": free_result["reason"],
                    "usedTables": free_result.get("usedTables", []),
                    "riskLevel": free_result.get("riskLevel", "high"),
                }
        except Exception as e:
            db.close()
            return {
                "success": False, "question": question, "queryMode": "free_sql",
                "answer": "SQL 预检失败", "errorCode": "SQL_EXPLAIN_ERROR",
                "errorMsg": str(e), "sql": sql,
            }
        finally:
            try: db.close()
            except: pass

    # Execute
    db = SessionLocal()
    try:
        db.execute(text("SET SESSION max_execution_time = :t"),
                   {"t": config.get("sql.timeout_seconds", 10) * 1000})
        result = db.execute(text(sql), bind_params)
        rows_raw = result.fetchall()
        columns = list(result.keys())
        rows = [dict(zip(columns, r)) for r in rows_raw]
    except Exception as e:
        return {
            "success": False, "question": question, "queryMode": "free_sql",
            "answer": "SQL 执行失败", "errorCode": "SQL_EXECUTE_ERROR",
            "errorMsg": str(e), "sql": sql,
            "estimatedRows": estimated_rows,
            "freeSqlReason": free_result["reason"],
            "usedTables": free_result.get("usedTables", []),
            "riskLevel": free_result.get("riskLevel", "high"),
        }
    finally:
        db.close()

    # Generate answer
    business_rules = load_business_rules()
    try:
        answer = await generate_answer(
            question=question, intent="free_sql",
            template_description=free_result["reason"],
            business_rules=business_rules, rows=rows,
            result_description="自由 SQL 查询结果",
        )
    except Exception as e:
        return {
            "success": False, "question": question, "queryMode": "free_sql",
            "answer": "AI 回答生成失败", "errorCode": "ANSWER_GENERATE_ERROR",
            "errorMsg": str(e),
        }

    display_sql = build_display_sql(sql, bind_params) if show_sql else None
    return {
        "success": True, "question": question, "queryMode": "free_sql",
        "intent": "free_sql", "confidence": 0, "params": {},
        "answer": answer, "sql": display_sql,
        "rows": _normalize_rows(rows), "rowCount": len(rows),
        "templateName": "自由 SQL 查询",
        "freeSqlReason": free_result["reason"],
        "usedTables": free_result.get("usedTables", []),
        "riskLevel": free_result.get("riskLevel", "low"),
        "estimatedRows": estimated_rows,
    }


async def run_rule_explain(question, intent_result):
    table_schemas = load_table_schemas()
    field_schemas = load_field_schemas()
    business_rules = load_business_rules()
    try:
        answer = await explain_business_rule(question, table_schemas, field_schemas, business_rules)
    except Exception as e:
        return {"success": False, "question": question,
                "answer": "AI 回答生成失败", "errorCode": "ANSWER_GENERATE_ERROR",
                "errorMsg": str(e)}
    return {
        "success": True, "question": question, "queryMode": "rule",
        "intent": "business_rule_explain",
        "confidence": intent_result.get("confidence", 0),
        "params": {}, "answer": answer,
        "sql": None, "rows": [], "rowCount": 0,
        "templateName": "业务规则解释",
    }


# ── main endpoint ────────────────────────────────────────

@router.post("/ask")
async def ask(req: AskRequest):
    t0 = _now()
    question = req.question.strip()
    config = get_ai_config()
    show_sql = req.showSql if req.showSql is not None else config.get("sql.show_sql_default", True)

    # Reject modification requests early
    if is_modification_request(question):
        duration_ms = _now() - t0
        _save_chat_log(req.sessionId, req.userId, question, "unknown", {},
                       {}, None, [], "当前 AI 模块只支持查询和分析，不支持修改业务数据。",
                       False, "拒绝修改类请求", duration_ms, query_mode="reject")
        return {"success": False, "question": question,
                "answer": "当前 AI 模块只支持查询和分析，不支持修改业务数据。",
                "errorCode": "UNSUPPORTED_OPERATION", "errorMsg": "拒绝修改类请求"}

    # Agent mode (priority when enabled)
    agent_attempted = False
    if config.get("agent.enabled", True):
        agent_attempted = True
        try:
            from app.core.conversation_memory import get_context
            from app.core.data_agent import run_data_agent
            session_id = req.sessionId or "default"
            ctx = get_context(session_id, max_turns=5)
            result = await run_data_agent(
                question, session_id, req.userId, show_sql,
                conversation_context=ctx,
            )
            result["durationMs"] = _now() - t0
            result["sessionId"] = session_id
            if result.get("success"):
                _save_chat_log(
                    req.sessionId, req.userId, question,
                    "agent", {}, {}, result.get("sql"), result.get("rows", []),
                    result["answer"], True, "", result["durationMs"],
                    query_mode="agent",
                )
                return result
            elif result.get("errorCode") == "REJECTED":
                return result
            # Agent failed non-rejection → fall through to template/free_sql
        except Exception as e:
            logger.exception("Agent failed, fallback to template/free_sql")
            try:
                _save_chat_log(
                    req.sessionId, req.userId, question,
                    "agent", {}, {}, None, [],
                    "", False, str(e),
                    int((time.time() - t0) * 1000),
                    query_mode="agent",
                )
            except Exception:
                pass
            # fall through to template/free_sql

    # 1. Quick intent match
    intent_result = quick_intent_match(question)
    intent_source = "local" if intent_result else None

    # 2. LLM intent if no quick match
    if not intent_result:
        intent_result = await parse_intent(question)
        intent_source = "llm"

    intent_code = intent_result.get("intent", "unknown")
    confidence = intent_result.get("confidence", 0)

    # 3. Rule explain
    if intent_code == "business_rule_explain":
        result = await run_rule_explain(question, intent_result)
        duration_ms = _now() - t0
        result["durationMs"] = duration_ms
        _save_chat_log(req.sessionId, req.userId, question, intent_code, intent_result,
                       {}, None, result.get("rows", []), result["answer"],
                       result["success"], "", duration_ms, query_mode="rule")
        return result

    # 4. Template query
    if intent_code != "unknown" and confidence >= 0.45:
        result = await run_template_query(question, intent_code, intent_result, show_sql)
        duration_ms = _now() - t0
        result["durationMs"] = duration_ms
        _save_chat_log(req.sessionId, req.userId, question, intent_code, intent_result,
                       result.get("params", {}), result.get("sql"),
                       result.get("rows", []), result["answer"],
                       result["success"],
                       result.get("errorMsg", ""),
                       duration_ms, query_mode="template")
        return result

    # 5. Free SQL fallback
    if not config.get("free_sql.enabled", False):
        duration_ms = _now() - t0
        _save_chat_log(req.sessionId, req.userId, question, "unknown", intent_result,
                       {}, None, [],
                       "当前问题暂时无法识别。你可以尝试询问：某厂家有哪些产品、某产品单价、本月出货、本月原料使用、本月库存等问题。",
                       False, "FREE_SQL_DISABLED", duration_ms, query_mode="free_sql")
        return {"success": False, "question": question,
                "answer": "当前问题暂时无法识别。你可以尝试询问：某厂家有哪些产品、某产品单价、本月出货、本月原料使用、本月库存等问题。",
                "errorCode": "UNKNOWN_INTENT", "errorMsg": intent_result.get("reason", "")}

    result = await run_free_sql_query(question, show_sql)
    duration_ms = _now() - t0
    result["durationMs"] = duration_ms
    _save_chat_log(req.sessionId, req.userId, question,
                   intent_code if intent_code != "unknown" else "free_sql",
                   intent_result, result.get("params", {}), result.get("sql"),
                   result.get("rows", []), result["answer"],
                   result["success"],
                   result.get("errorMsg", ""),
                   duration_ms, query_mode="free_sql",
                   free_sql_reason=result.get("freeSqlReason"),
                   used_tables=result.get("usedTables"),
                   risk_level=result.get("riskLevel"),
                   estimated_rows=result.get("estimatedRows"))
    return result


# ── config refresh ───────────────────────────────────────

@router.post("/config/refresh")
def config_refresh():
    config = refresh_ai_config_cache()
    return {"success": True, "message": "AI配置缓存已刷新", "config": config}


