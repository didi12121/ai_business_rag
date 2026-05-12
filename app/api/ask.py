import json
import time
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.models.request import AskRequest
from app.core.intent_parser import parse_intent
from app.core.quick_intent import quick_intent_match
from app.core.business_context import (
    load_table_schemas,
    load_field_schemas,
    load_business_rules,
    load_query_template,
)
from app.core.date_resolver import resolve_relative_date_params
from app.core.sql_renderer import render_sql_template
from app.core.sql_safety import check_sql_safety
from app.core.answer_generator import generate_answer, explain_business_rule

router = APIRouter(prefix="/api/ai")


def _normalize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _normalize_rows(rows: list[dict]) -> list[dict]:
    return [{k: _normalize_value(v) for k, v in row.items()} for row in rows]


def _save_chat_log(
    session_id: str | None,
    user_id: str | None,
    question: str,
    intent_code: str,
    intent_result: dict,
    params: dict,
    sql_text: str | None,
    rows: list[dict],
    answer: str,
    success: bool,
    error_msg: str,
    duration_ms: int,
):
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO ai_chat_log "
                "(session_id, user_id, question, intent_code, intent_result, "
                "params_json, sql_text, sql_rows_json, answer, success, "
                "error_msg, model_name, duration_ms, create_time) "
                "VALUES "
                "(:sid, :uid, :q, :ic, :ir, :pj, :st, :sr, :a, :ok, "
                ":em, :mn, :dur, NOW())"
            ),
            {
                "sid": session_id,
                "uid": user_id,
                "q": question,
                "ic": intent_code,
                "ir": json.dumps(intent_result, ensure_ascii=False),
                "pj": json.dumps(params, ensure_ascii=False),
                "st": sql_text,
                "sr": json.dumps(rows[:50], ensure_ascii=False) if rows else None,
                "a": answer,
                "ok": 1 if success else 0,
                "em": error_msg,
                "mn": settings.LLM_MODEL,
                "dur": duration_ms,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@router.post("/ask")
async def ask(req: AskRequest):
    t0 = time.time()
    question = req.question.strip()

    # 1. Quick local intent match (skip LLM call for common patterns)
    intent_result = quick_intent_match(question)
    if intent_result:
        intent_code = intent_result["intent"]
        confidence = intent_result["confidence"]
    else:
        # 2. LLM intent recognition
        intent_result = await parse_intent(question)
        intent_code = intent_result["intent"]
        confidence = intent_result["confidence"]

    # 3. Business rule explanation
    if intent_code == "business_rule_explain":
        table_schemas = load_table_schemas()
        field_schemas = load_field_schemas()
        business_rules = load_business_rules()
        answer = await explain_business_rule(
            question, table_schemas, field_schemas, business_rules
        )
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success": True,
            "question": question,
            "intent": intent_code,
            "confidence": confidence,
            "params": {},
            "answer": answer,
            "sql": None,
            "rows": [],
            "rowCount": 0,
            "templateName": "业务规则解释",
            "durationMs": duration_ms,
        }

    # 4. Unknown or low confidence
    if intent_code == "unknown" or confidence < 0.45:
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "question": question,
            "answer": (
                "当前问题暂时无法识别。你可以尝试询问："
                "某厂家有哪些产品、某产品单价、本月出货、本月原料使用、本月库存等问题。"
            ),
            "errorCode": "UNKNOWN_INTENT",
            "errorMsg": intent_result.get("reason", "无法识别意图"),
        }

    # 5. Load query template
    template = load_query_template(intent_code)
    if not template:
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "question": question,
            "answer": "没有找到对应查询模板，请联系管理员。",
            "errorCode": "TEMPLATE_NOT_FOUND",
            "errorMsg": f"intent {intent_code} 对应的模板不存在",
        }

    # 6. Resolve relative dates
    params = resolve_relative_date_params(intent_result.get("params", {}), question)

    # 7. Render SQL
    try:
        sql, bind_params = render_sql_template(template["sql_template"], params)
        # Build display SQL with values substituted
        display_sql = sql
        for k, v in bind_params.items():
            display_sql = display_sql.replace(f":{k}", f"'{v}'" if isinstance(v, str) else str(v))
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "question": question,
            "answer": "SQL 模板渲染失败。",
            "errorCode": "SQL_RENDER_ERROR",
            "errorMsg": str(e),
        }

    # 8. SQL safety check
    try:
        sql = check_sql_safety(sql, max_rows=settings.MAX_QUERY_ROWS)
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "question": question,
            "answer": "SQL 安全检查未通过。",
            "errorCode": "SQL_SAFETY_ERROR",
            "errorMsg": str(e),
        }

    # 9. Execute SQL
    try:
        db = SessionLocal()
        db.execute(
            text("SET SESSION max_execution_time = :t"),
            {"t": settings.SQL_TIMEOUT_SECONDS * 1000},
        )
        result = db.execute(text(sql), bind_params)
        rows_raw = result.fetchall()
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in rows_raw]
        db.close()
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "question": question,
            "answer": "SQL 执行失败。",
            "errorCode": "SQL_EXECUTE_ERROR",
            "errorMsg": str(e),
        }

    # 10. Generate answer
    try:
        business_rules = load_business_rules()
        answer = await generate_answer(
            question=question,
            intent=intent_code,
            template_description=template["description"] or "",
            business_rules=business_rules,
            rows=rows,
            result_description=template.get("result_description") or "",
        )
    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "question": question,
            "answer": "AI 回答生成失败。",
            "errorCode": "ANSWER_GENERATE_ERROR",
            "errorMsg": str(e),
        }

    duration_ms = int((time.time() - t0) * 1000)

    # 11. Save chat log
    _save_chat_log(
        session_id=req.sessionId,
        user_id=req.userId,
        question=question,
        intent_code=intent_code,
        intent_result=intent_result,
        params=params,
        sql_text=sql if req.showSql else None,
        rows=rows,
        answer=answer,
        success=True,
        error_msg="",
        duration_ms=duration_ms,
    )

    normalized_rows = _normalize_rows(rows)

    return {
        "success": True,
        "question": question,
        "intent": intent_code,
        "confidence": confidence,
        "intentReason": intent_result.get("reason", ""),
        "params": params,
        "answer": answer,
        "sql": display_sql if req.showSql else None,
        "rows": normalized_rows,
        "rowCount": len(normalized_rows),
        "templateName": template["template_name"],
        "durationMs": duration_ms,
    }
