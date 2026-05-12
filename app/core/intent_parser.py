import json
import re
from datetime import datetime

from app.llm.openai_compatible import create_llm_client
from app.prompts.intent_prompt import INTENT_PROMPT
from app.core.business_context import load_table_schemas, load_field_schemas


def _build_schema_text(table_schemas: list[dict], field_schemas: list[dict]) -> str:
    lines = []
    for t in table_schemas:
        tname = t["table_name"]
        bname = t.get("business_name", "")
        desc = t.get("description", "")
        lines.append(f"  [{tname}] {bname} — {desc}")
        for f in field_schemas:
            if f["table_name"] != tname:
                continue
            fname = f["field_name"]
            fbiz = f.get("business_name", "")
            fdesc = f.get("description", "")
            vmap = f.get("value_mapping")
            extra = ""
            if vmap:
                try:
                    vm = json.loads(vmap) if isinstance(vmap, str) else vmap
                    extra = " 枚举: " + ", ".join(f"{k}={v}" for k, v in vm.items())
                except (json.JSONDecodeError, TypeError):
                    pass
            lines.append(f"    {fname}: {fbiz} — {fdesc}{extra}")
    return "\n".join(lines)


def _build_intent_list() -> str:
    from app.database import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT intent_code, description, example_question FROM ai_query_template WHERE enabled = 1")
        ).fetchall()
        lines = []
        for r in rows:
            lines.append(f"  {r[0]}: {r[1]}（例：{r[2]}）")
        return "\n".join(lines)
    finally:
        db.close()


def _relative_dates() -> tuple[str, str]:
    now = datetime.now()
    return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


async def parse_intent(question: str) -> dict:
    table_schemas = load_table_schemas()
    field_schemas = load_field_schemas()
    schema_text = _build_schema_text(table_schemas, field_schemas)
    intent_list = _build_intent_list()
    current_date, current_month = _relative_dates()

    prompt = INTENT_PROMPT.format(
        table_schemas=schema_text,
        intent_list=intent_list,
        current_date=current_date,
        current_month=current_month,
        question=question,
    )

    client = create_llm_client()
    try:
        raw = await client.chat([{"role": "system", "content": prompt}])
    except Exception as e:
        return _fallback(f"LLM调用失败: {e}")

    try:
        result = json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        return _fallback(f"JSON解析失败: {raw[:200]}")

    return {
        "intent": result.get("intent", "unknown"),
        "confidence": result.get("confidence", 0),
        "params": result.get("params", {}),
        "reason": result.get("reason", ""),
        "raw": raw,
    }


def _fallback(error: str) -> dict:
    return {"intent": "unknown", "confidence": 0, "params": {}, "reason": error, "raw": ""}
