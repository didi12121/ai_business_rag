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
    "修改", "删除", "添加", "插入", "更新", "清空",
    "增加", "移除", "去掉",
    "重置", "改成", "设为", "调整价格", "删除记录", "清空库存",
    "改价格", "改单价", "保存", "写入", "导入", "覆盖", "批量修改",
    "新增一个", "新增一条", "帮新增", "新增一下",
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


# System fields that exist on every RuoYi table, don't require ai_field_schema entry
_BUILTIN_FIELDS = {
    "del_flag", "create_time", "create_by", "update_time", "update_by",
    "remark", "order_no", "out_id",
}

# Known SQL functions/operators that can precede a column reference
_SQL_FUNCTIONS = {
    "sum", "avg", "min", "max", "count", "coalesce", "nullif", "ifnull",
    "concat", "group_concat", "cast", "convert", "if", "case", "when", "then",
    "else", "end", "distinct", "as", "on", "and", "or", "in", "not", "is",
    "null", "like", "between", "exists", "asc", "desc", "separator",
}


@lru_cache(maxsize=1)
def _load_field_map() -> dict[str, set[str]]:
    """Return {table_name: {field_name, ...}} from ai_field_schema."""
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT table_name, field_name FROM ai_field_schema WHERE enabled = 1"
        )).fetchall()
        field_map: dict[str, set[str]] = {}
        for r in rows:
            field_map.setdefault(r[0], set()).add(r[1].lower())
        return field_map
    finally:
        db.close()


def _extract_alias_map(sql: str) -> dict[str, str]:
    """Extract alias → table_name mapping."""
    mapping: dict[str, str] = {}
    for m in re.finditer(
        r"(?:from|join)\s+`?(\w+)`?\s+(?:AS\s+)?(\w+)",
        sql, re.IGNORECASE,
    ):
        table = m.group(1).lower()
        alias = m.group(2).lower()
        if alias not in _SQL_FUNCTIONS and alias not in ("where", "group", "order", "limit", "having"):
            mapping[alias] = table
    return mapping


def _validate_fields(sql: str, allowed_tables: set[str]):
    """Check that alias.column references exist in ai_field_schema."""
    field_map = _load_field_map()
    alias_map = _extract_alias_map(sql)

    # Find all alias.column patterns
    col_refs = re.findall(r"(\w+)\.(\w+)", sql.lower())
    for alias, col in col_refs:
        if alias in _SQL_FUNCTIONS:
            continue
        table = alias_map.get(alias, alias)
        if table not in field_map:
            continue  # Skip if table not in field schema (e.g. derived tables)
        valid_fields = field_map[table]
        # Builtin system fields are always allowed
        if col in _BUILTIN_FIELDS:
            continue
        if col not in valid_fields:
            raise ValueError(
                f"字段不存在：{alias}.{col}（表 {table} 中没有此字段，可用字段: {', '.join(sorted(valid_fields)[:20])}...）"
            )


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

    # Field validation: check alias.column references exist in ai_field_schema
    _validate_fields(sql, used_tables)

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
