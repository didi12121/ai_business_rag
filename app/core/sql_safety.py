import re
from functools import lru_cache

import sqlparse
from sqlalchemy import text

from app.database import SessionLocal

FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "truncate",
    "create", "replace", "grant", "revoke", "call", "exec",
    "merge", "load", "outfile", "dumpfile",
]


@lru_cache(maxsize=1)
def _load_allowed_tables() -> set[str]:
    ai_tables = {
        "ai_table_schema", "ai_field_schema",
        "ai_business_rule", "ai_query_template",
    }
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT table_name FROM ai_table_schema WHERE enabled = 1")
        ).fetchall()
        return {row[0] for row in rows} | ai_tables
    finally:
        db.close()


def check_sql_safety(sql: str, max_rows: int = 200):
    if not sql or not sql.strip():
        raise ValueError("SQL 不能为空")

    stripped = sql.strip()
    lower = stripped.lower()

    if ";" in stripped.rstrip(";"):
        raise ValueError("不允许多语句 SQL")

    if not (lower.startswith("select") or lower.startswith("with")):
        raise ValueError("只允许 SELECT 查询")

    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", lower):
            raise ValueError(f"SQL 包含危险关键字：{kw}")

    if re.search(r"select\s+\*", lower):
        raise ValueError("不允许使用 SELECT *")

    parsed = sqlparse.parse(sql)
    if len(parsed) != 1:
        raise ValueError("只允许单条 SQL")

    allowed = _load_allowed_tables()
    for match in re.finditer(
        r"\bfrom\s+([a-zA-Z0-9_]+)|\bjoin\s+([a-zA-Z0-9_]+)", lower
    ):
        table = match.group(1) or match.group(2)
        if table and table not in allowed:
            raise ValueError(f"不允许访问表：{table}")

    if "limit" not in lower:
        sql = stripped.rstrip(";") + f" LIMIT {max_rows}"

    return sql
