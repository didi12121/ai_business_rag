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

_MODIFICATION_KEYWORDS = [
    "修改", "删除", "新增", "添加", "插入", "更新", "清空",
    "重置", "改成", "设为", "调整价格", "删除记录", "清空库存",
    "改价格", "改单价", "保存", "写入", "导入", "覆盖", "批量修改",
]


def is_modification_request(question: str) -> bool:
    return any(kw in question for kw in _MODIFICATION_KEYWORDS)


AI_META_TABLES = {
    "ai_table_schema", "ai_field_schema",
    "ai_business_rule", "ai_query_template",
}


@lru_cache(maxsize=1)
def _load_allowed_tables(free_sql: bool = False) -> set[str]:
    db = SessionLocal()
    try:
        if free_sql:
            rows = db.execute(
                text(
                    "SELECT table_name FROM ai_table_schema "
                    "WHERE enabled = 1 AND allow_query = 1"
                )
            ).fetchall()
            return {row[0] for row in rows}
        else:
            rows = db.execute(
                text(
                    "SELECT table_name FROM ai_table_schema "
                    "WHERE enabled = 1"
                )
            ).fetchall()
            return {row[0] for row in rows} | AI_META_TABLES
    finally:
        db.close()


def _extract_tables(sql: str) -> set[str]:
    """Extract table names from FROM/JOIN clauses, supporting:
    - plain: ad_product_info
    - backtick: `ad_product_info`
    - db prefix: db.ad_product_info
    - backtick db: `db`.`ad_product_info`
    """
    found = set()
    lower = sql.lower()
    # Match patterns like FROM table, JOIN table
    for m in re.finditer(
        r"(?:from|join)\s+(?:`?(\w+)`?\.)?`?(\w+)`?",
        lower
    ):
        tbl = m.group(2)
        if tbl:
            found.add(tbl)
    return found


def check_sql_safety(sql: str, max_rows: int = 200, is_free_sql: bool = False) -> str:
    if not sql or not sql.strip():
        raise ValueError("SQL 不能为空")

    stripped = sql.strip()
    lower = stripped.lower()

    # No multi-statement
    if ";" in stripped.rstrip(";"):
        raise ValueError("不允许多语句 SQL")

    # Only SELECT or WITH
    if not (lower.startswith("select") or lower.startswith("with")):
        raise ValueError("只允许 SELECT 查询")

    # No dangerous keywords
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", lower):
            raise ValueError(f"SQL 包含危险关键字：{kw}")

    # No SELECT *
    if re.search(r"select\s+\*", lower):
        raise ValueError("不允许使用 SELECT *")

    # Must be exactly one statement
    parsed = sqlparse.parse(sql)
    if len(parsed) != 1:
        raise ValueError("只允许单条 SQL")

    # Table whitelist check
    allowed = _load_allowed_tables(free_sql=is_free_sql)
    used_tables = _extract_tables(sql)
    for tbl in used_tables:
        if tbl not in allowed:
            raise ValueError(f"不允许访问表：{tbl}")

    # LIMIT enforcement
    limit_m = re.search(r"\blimit\s+(\d+)", lower)
    if not limit_m:
        sql = stripped.rstrip(";") + f" LIMIT {max_rows}"
    else:
        existing_limit = int(limit_m.group(1))
        if existing_limit > max_rows:
            sql = re.sub(
                r"\bLIMIT\s+\d+",
                f"LIMIT {max_rows}",
                stripped,
                flags=re.IGNORECASE,
            )

    return sql


def build_display_sql(sql: str, params: dict) -> str:
    """Substitute params into SQL for display only. Not for execution."""
    result = sql
    # Sort by key length descending to avoid partial matches (e.g. :id vs :id2)
    for k in sorted(params.keys(), key=len, reverse=True):
        v = params[k]
        if isinstance(v, str):
            escaped = v.replace("'", "''")
            result = re.sub(rf":{re.escape(k)}\b", f"'{escaped}'", result)
        else:
            result = re.sub(rf":{re.escape(k)}\b", str(v), result)
    return result
