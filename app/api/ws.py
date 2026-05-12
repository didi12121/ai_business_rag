import json
import time
from decimal import Decimal
from datetime import date, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import SessionLocal
from app.llm.openai_compatible import create_llm_client
from app.core.intent_parser import parse_intent
from app.core.quick_intent import quick_intent_match
from app.core.business_context import (
    load_table_schemas, load_field_schemas,
    load_business_rules, load_query_template,
)
from app.core.date_resolver import resolve_relative_date_params
from app.core.sql_renderer import render_sql_template
from app.core.sql_safety import check_sql_safety
from app.prompts.answer_prompt import ANSWER_PROMPT
from app.prompts.rule_explain_prompt import RULE_EXPLAIN_PROMPT

router = APIRouter()


async def _send(ws: WebSocket, event: str, data: dict | None = None):
    msg = {"event": event}
    if data:
        msg.update(data)
    await ws.send_text(json.dumps(msg, ensure_ascii=False))


def _normalize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


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

    try:
        # Step 1: Intent recognition
        await _send(ws, "thinking", {"step": "intent", "text": "正在识别查询意图..."})

        intent_result = quick_intent_match(question)
        intent_source = "local"
        if intent_result is None:
            intent_result = await parse_intent(question)
            intent_source = "llm"

        intent_code = intent_result["intent"]
        confidence = intent_result["confidence"]

        await _send(ws, "intent_done", {
            "intent": intent_code,
            "confidence": confidence,
            "reason": intent_result.get("reason", ""),
            "params": intent_result.get("params", {}),
            "source": intent_source,
        })

        # Step 2: Business rule explain
        if intent_code == "business_rule_explain":
            table_schemas = load_table_schemas()
            field_schemas = load_field_schemas()
            business_rules = load_business_rules()

            prompt = RULE_EXPLAIN_PROMPT.format(
                current_date=datetime.now().strftime("%Y-%m-%d"),
                question=question,
                table_schemas=_to_json(table_schemas),
                field_schemas=_to_json(field_schemas),
                business_rules=_to_json(business_rules),
            )
            client = create_llm_client()
            await _send(ws, "answer_start")
            async for token in client.chat_stream([{"role": "system", "content": prompt}]):
                await _send(ws, "answer_chunk", {"text": token})

            duration_ms = int((time.time() - t0) * 1000)
            await _send(ws, "done", {"durationMs": duration_ms})
            await ws.close()
            return

        # Step 3: Unknown → try free query as fallback
        if intent_code == "unknown" or confidence < 0.45:
            await _send(ws, "thinking", {"step": "free_query", "text": "未匹配到固定模板，尝试根据表结构生成查询..."})
            try:
                from app.core.free_query import free_query_sql
                sql = await free_query_sql(question)
                if sql is None:
                    await _send(ws, "error", {"message": "无法生成有效查询，请换个问法试试"})
                    await ws.close()
                    return
                bind_params = {}
                template_name = "自由查询"
                params = {}
            except Exception as e:
                await _send(ws, "error", {"message": f"查询生成失败: {e}"})
                await ws.close()
                return
        else:
            # Step 4: Load template
            template = load_query_template(intent_code)
            if not template:
                await _send(ws, "error", {"message": "没有找到对应查询模板"})
                await ws.close()
                return
            template_name = template["template_name"]

            # Step 5: Resolve date params
            params = resolve_relative_date_params(intent_result.get("params", {}), question)

            # Step 6: Render SQL
            sql, bind_params = render_sql_template(template["sql_template"], params)

        if template_name == "自由查询":
            template_description = "根据表结构自动生成的查询"
        else:
            template_description = template.get("description", "")

        # Build display SQL with actual values substituted
        display_sql = sql
        for k, v in bind_params.items():
            if isinstance(v, str):
                display_sql = display_sql.replace(f":{k}", f"'{v}'")
            else:
                display_sql = display_sql.replace(f":{k}", str(v))

        await _send(ws, "sql_ready", {
            "sql": display_sql,
            "params": {k: v for k, v in params.items() if v is not None and v != ""},
            "template": template_name,
        })

        # Step 7: Safety check
        await _send(ws, "thinking", {"step": "safety", "text": "正在安全检查..."})
        try:
            sql = check_sql_safety(sql, max_rows=settings.MAX_QUERY_ROWS)
        except Exception as e:
            await _send(ws, "error", {"message": f"SQL 安全检查失败: {e}"})
            await ws.close()
            return

        # Step 8: Execute
        await _send(ws, "thinking", {"step": "query", "text": "正在查询数据库..."})
        try:
            from sqlalchemy import text as sa_text
            db = SessionLocal()
            db.execute(
                sa_text("SET SESSION max_execution_time = :t"),
                {"t": settings.SQL_TIMEOUT_SECONDS * 1000},
            )
            result = db.execute(sa_text(sql), bind_params)
            rows_raw = result.fetchall()
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in rows_raw]
            db.close()
        except Exception as e:
            await _send(ws, "error", {"message": f"SQL 执行失败: {e}"})
            await ws.close()
            return

        await _send(ws, "query_done", {
            "rowCount": len(rows),
            "rows": [{k: _normalize_value(v) for k, v in row.items()} for row in rows],
        })

        # Step 9: Generate answer (streaming)
        business_rules = load_business_rules()
        prompt = ANSWER_PROMPT.format(
            current_date=datetime.now().strftime("%Y-%m-%d"),
            question=question,
            intent=intent_code,
            template_description=template_description or "",
            business_rules=_to_json(business_rules),
            sql_result_json=_to_json(rows[:50]),
            result_description=template_description or "",
        )

        client = create_llm_client()
        await _send(ws, "answer_start")
        async for token in client.chat_stream([{"role": "system", "content": prompt}]):
            await _send(ws, "answer_chunk", {"text": token})

        # Step 10: Done
        duration_ms = int((time.time() - t0) * 1000)
        await _send(ws, "done", {"durationMs": duration_ms})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await _send(ws, "error", {"message": str(e)})
    finally:
        try:
            await ws.close()
        except Exception:
            pass
