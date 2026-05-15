import json
import time
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.llm.openai_compatible import create_llm_client
from app.core.sys_config import get_ai_config
from app.core.sql_safety import check_sql_safety, build_display_sql
from app.core.query_router import route_question
from app.core.intent_parser import parse_intent
from app.core.quick_intent import quick_intent_match
from app.core.business_context import (
    load_table_schemas, load_field_schemas,
    load_business_rules, load_query_template,
)
from app.core.date_resolver import resolve_relative_date_params
from app.core.sql_renderer import render_sql_template
from app.core.free_query import generate_free_sql
from app.prompts.answer_prompt import ANSWER_PROMPT
from app.prompts.rule_explain_prompt import RULE_EXPLAIN_PROMPT

router = APIRouter()


async def _send(ws: WebSocket, event: str, data: dict | None = None):
    msg = {"event": event, **(data or {})}
    await ws.send_text(json.dumps(msg, ensure_ascii=False))


def _to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _normalize_value(value):
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, datetime): return value.strftime("%Y-%m-%d %H:%M:%S")
    from datetime import date
    if isinstance(value, date): return value.strftime("%Y-%m-%d")
    return value


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        raw = await ws.receive_text()
        body = json.loads(raw)
        question = body.get("question", "").strip()
        if not question:
            await _send(ws, "error", {"message": "问题不能为空"})
            await ws.close()
            return
    except (WebSocketDisconnect, json.JSONDecodeError):
        return

    t0 = time.time()
    config = get_ai_config()
    show_sql = body.get("showSql", config.get("sql.show_sql_default", True))

    try:
        session_id = body.get("sessionId")
        if not session_id:
            from app.core.conversation_memory import new_session_id
            session_id = new_session_id()
            await _send(ws, "session", {"sessionId": session_id})

        # ── Load context and route ──
        from app.core.conversation_memory import get_context
        ctx = get_context(session_id, max_turns=5)
        route = route_question(question, ctx)
        route_mode = route["mode"]

        await _send(ws, "route_decided", {
            "mode": route_mode,
            "reason": route["reason"],
            "confidence": route.get("confidence", 0),
        })

        # ── reject ──
        if route_mode == "reject":
            await _send(ws, "error", {"message": "当前 AI 模块只支持查询和分析，不支持修改业务数据。"})
            await ws.close()
            return

        # ── agent ──
        if route_mode == "agent":
            if not config.get("agent.enabled", True):
                await _send(ws, "error", {"message": "复杂分析功能未启用"})
                await ws.close()
                return

            from app.core.data_agent import run_data_agent
            agent_done_emitted = False

            async def event_cb_agent(payload: dict):
                nonlocal agent_done_emitted
                if payload.get("event") == "done":
                    agent_done_emitted = True
                try:
                    await _send(ws, payload["event"], payload)
                except Exception:
                    pass

            result = await run_data_agent(
                question=question, session_id=session_id, user_id=None,
                show_sql=show_sql, event_callback=event_cb_agent,
                conversation_context=ctx,
            )

            if result.get("success"):
                if not agent_done_emitted:
                    await _send(ws, "done", result)
            elif result.get("errorCode") == "REJECTED":
                pass
            else:
                await _send(ws, "error", {
                    "message": result.get("answer", "Agent 分析未能完成"),
                    "errorCode": result.get("errorCode"),
                })
            await ws.close()
            return

        # ── rule (explain directly, no SQL) ──
        if route_mode == "rule":
            table_schemas = load_table_schemas()
            field_schemas = load_field_schemas()
            rules = load_business_rules()
            prompt = RULE_EXPLAIN_PROMPT.format(
                current_date=datetime.now().strftime("%Y-%m-%d"),
                question=question,
                table_schemas=_to_json(table_schemas),
                field_schemas=_to_json(field_schemas),
                business_rules=_to_json(rules),
            )
            client = create_llm_client()
            await _send(ws, "answer_start")
            async for token in client.chat_stream([{"role": "system", "content": prompt}]):
                await _send(ws, "answer_chunk", {"text": token})
            duration_ms = int((time.time() - t0) * 1000)
            await _send(ws, "done", {"durationMs": duration_ms, "queryMode": "rule"})
            await ws.close()
            return

        # ── template ──
        if route_mode == "template":
            await _send(ws, "thinking", {"step": "intent", "text": "正在识别查询意图..."})
            intent_result = quick_intent_match(question)
            if not intent_result:
                intent_result = await parse_intent(question)

            intent_code = intent_result.get("intent", "unknown")
            confidence = intent_result.get("confidence", 0)

            await _send(ws, "intent_done", {
                "intent": intent_code, "confidence": confidence,
                "reason": intent_result.get("reason", ""),
                "params": intent_result.get("params", {}),
            })

            if intent_code != "unknown" and confidence >= 0.45:
                template = load_query_template(intent_code)
                if template:
                    params = resolve_relative_date_params(intent_result.get("params", {}), question)
                    sql, bind_params = render_sql_template(template["sql_template"], params)
                    await _send(ws, "sql_ready", {
                        "sql": build_display_sql(sql, bind_params),
                        "template": template["template_name"],
                    })
                    await _send(ws, "thinking", {"step": "safety", "text": "正在安全检查..."})
                    try:
                        from sqlalchemy import text as sa_text
                        sql = check_sql_safety(sql, max_rows=config.get("free_sql.max_rows", 200))
                    except Exception as e:
                        await _send(ws, "error", {"message": f"SQL 安全检查失败: {e}"})
                        await ws.close()
                        return
                    await _send(ws, "thinking", {"step": "query", "text": "正在查询数据库..."})
                    db = SessionLocal()
                    try:
                        db.execute(sa_text("SET SESSION max_execution_time = :t"),
                                   {"t": config.get("sql.timeout_seconds", 10) * 1000})
                        result = db.execute(sa_text(sql), bind_params)
                        rows_raw = result.fetchall()
                        columns = list(result.keys())
                        rows = [dict(zip(columns, r)) for r in rows_raw]
                    except Exception as e:
                        await _send(ws, "error", {"message": f"SQL 执行失败: {e}"})
                        await ws.close()
                        db.close()
                        return
                    finally:
                        db.close()
                    await _send(ws, "query_done", {
                        "rowCount": len(rows),
                        "rows": [{k: _normalize_value(v) for k, v in r.items()} for r in rows],
                    })
                    rules = load_business_rules()
                    prompt = ANSWER_PROMPT.format(
                        current_date=datetime.now().strftime("%Y-%m-%d"),
                        question=question, intent=intent_code,
                        template_description=template.get("description", ""),
                        business_rules=_to_json(rules),
                        sql_result_json=_to_json(rows[:50]),
                        result_description=template.get("result_description", ""),
                    )
                    client = create_llm_client()
                    await _send(ws, "answer_start")
                    async for token in client.chat_stream([{"role": "system", "content": prompt}]):
                        await _send(ws, "answer_chunk", {"text": token})
                    duration_ms = int((time.time() - t0) * 1000)
                    await _send(ws, "done", {"durationMs": duration_ms, "queryMode": "template"})
                    await ws.close()
                    return
            # Template match failed → fall through to free_sql below

        # ── free_sql (also serves as fallback for template) ──
        if not config.get("free_sql.enabled", False):
            await _send(ws, "error", {"message": "当前问题暂时无法识别且自由SQL未启用。"})
            await ws.close()
            return

        await _send(ws, "thinking", {"step": "free_sql", "text": "AI 正在根据表结构生成查询..."})

        free_result = await generate_free_sql(question)
        await _send(ws, "free_sql_reason", {
            "canGenerate": free_result["canGenerate"],
            "reason": free_result["reason"],
            "usedTables": free_result.get("usedTables", []),
            "riskLevel": free_result.get("riskLevel", "high"),
        })

        if not free_result["canGenerate"] or not free_result["sql"]:
            await _send(ws, "error", {"message": f"无法生成有效查询：{free_result['reason']}"})
            await ws.close()
            return

        sql = free_result["sql"]
        bind_params = free_result.get("params")
        if not isinstance(bind_params, dict):
            bind_params = {}
        await _send(ws, "sql_ready", {
            "sql": build_display_sql(sql, bind_params),
            "template": "自由 SQL 查询",
        })

        await _send(ws, "thinking", {"step": "safety", "text": "正在安全检查..."})
        try:
            sql = check_sql_safety(sql, max_rows=config.get("free_sql.max_rows", 200), is_free_sql=True)
        except Exception as e:
            await _send(ws, "error", {"message": f"SQL 安全检查失败: {e}"})
            await ws.close()
            return

        estimated_rows = None
        if config.get("free_sql.explain_before_run", True):
            await _send(ws, "thinking", {"step": "explain", "text": "正在预估查询范围..."})
            db = SessionLocal()
            try:
                from sqlalchemy import text as sa_text
                explain_result = db.execute(sa_text(f"EXPLAIN {sql}"), bind_params).fetchall()
                total = 0
                for r in explain_result:
                    try:
                        total += int(r._mapping.get("rows", 0) or 0)
                    except (ValueError, TypeError):
                        pass
                estimated_rows = total
                max_est = config.get("free_sql.max_estimated_rows", 50000)
                if estimated_rows > max_est:
                    await _send(ws, "error", {"message": f"查询范围过大（预估{estimated_rows}行），请增加条件后再试。"})
                    await ws.close()
                    db.close()
                    return
            except Exception as e:
                await _send(ws, "error", {"message": f"SQL 预检失败: {e}"})
                await ws.close()
                db.close()
                return
            finally:
                db.close()

        await _send(ws, "thinking", {"step": "query", "text": "正在查询数据库..."})
        db = SessionLocal()
        try:
            from sqlalchemy import text as sa_text
            db.execute(sa_text("SET SESSION max_execution_time = :t"),
                       {"t": config.get("sql.timeout_seconds", 10) * 1000})
            result = db.execute(sa_text(sql), bind_params)
            rows_raw = result.fetchall()
            columns = list(result.keys())
            rows = [dict(zip(columns, r)) for r in rows_raw]
        except Exception as e:
            await _send(ws, "error", {"message": f"SQL 执行失败: {e}"})
            await ws.close()
            db.close()
            return
        finally:
            db.close()

        await _send(ws, "query_done", {
            "rowCount": len(rows),
            "rows": [{k: _normalize_value(v) for k, v in r.items()} for r in rows],
            "estimatedRows": estimated_rows,
        })

        rules = load_business_rules()
        prompt = ANSWER_PROMPT.format(
            current_date=datetime.now().strftime("%Y-%m-%d"),
            question=question, intent="free_sql",
            template_description=free_result["reason"],
            business_rules=_to_json(rules),
            sql_result_json=_to_json(rows[:50]),
            result_description="自由 SQL 查询结果",
        )
        client = create_llm_client()
        await _send(ws, "answer_start")
        async for token in client.chat_stream([{"role": "system", "content": prompt}]):
            await _send(ws, "answer_chunk", {"text": token})

        duration_ms = int((time.time() - t0) * 1000)
        await _send(ws, "done", {
            "durationMs": duration_ms, "queryMode": "free_sql",
            "freeSqlReason": free_result["reason"],
            "usedTables": free_result.get("usedTables", []),
            "riskLevel": free_result.get("riskLevel", "low"),
            "estimatedRows": estimated_rows,
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await _send(ws, "error", {"message": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
