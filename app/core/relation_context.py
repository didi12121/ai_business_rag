import logging
from sqlalchemy import text
from app.database import SessionLocal

logger = logging.getLogger("ai_business_rag")


def load_table_relations() -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT from_table, from_field, to_table, to_field,
                   relation_type, join_type, description
            FROM ai_table_relation
            WHERE enabled = 1
            ORDER BY id ASC
        """)).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        logger.exception("Failed to load ai_table_relation")
        return []
    finally:
        db.close()


def build_relation_prompt_section() -> str:
    relations = load_table_relations()
    if not relations:
        return ""
    lines = ["=== 可用表关系（必须按此 JOIN，不得自创） ===", ""]
    for r in relations:
        lines.append(
            f"[{r['from_table']}] -- {r['join_type']} --> [{r['to_table']}]"
        )
        lines.append(
            f"  ON {r['from_table']}.{r['from_field']} = {r['to_table']}.{r['to_field']}"
        )
        if r.get("description"):
            lines.append(f"  说明: {r['description']}")
        lines.append("")
    lines.append("规则：生成 SQL 时必须使用上述 JOIN 条件，不要自创。")
    lines.append("")
    return "\n".join(lines)
