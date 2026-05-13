"""Post-process generated SQL to enforce del_flag = '0' on all tables that have it."""
import re

from app.database import SessionLocal


def _get_del_flag_tables() -> set[str]:
    """Return table names that have a del_flag field (from ai_field_schema)."""
    db = SessionLocal()
    try:
        from sqlalchemy import text
        rows = db.execute(text(
            "SELECT DISTINCT table_name FROM ai_field_schema "
            "WHERE field_name = 'del_flag' AND enabled = 1"
        )).fetchall()
        return {r[0] for r in rows}
    except Exception:
        # Fallback: assume all business tables have del_flag
        return set()
    finally:
        db.close()


def enforce_del_flag(sql: str) -> str:
    """Ensure every table with del_flag has del_flag = '0' in WHERE."""
    tables_with_del = _get_del_flag_tables()
    if not tables_with_del:
        return sql

    # Find all table aliases in FROM/JOIN
    aliases = _extract_aliases(sql)
    lower = sql.lower()
    has_where = "where" in lower

    for alias, table_name in aliases.items():
        if table_name not in tables_with_del:
            continue
        # Check if del_flag filter already exists for this alias
        pattern = rf"{re.escape(alias)}\.del_flag\s*=\s*'0'"
        if re.search(pattern, lower):
            continue
        pattern2 = rf"{re.escape(alias)}\.del_flag\s*!=\s*'1'"
        if re.search(pattern2, lower):
            continue

        # Inject the filter
        clause = f"{alias}.del_flag = '0'"
        if has_where:
            sql = re.sub(
                r"(WHERE\s+)",
                rf"\1{clause} AND ",
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            # No WHERE clause — inject after last JOIN/table reference
            m = re.search(r"(FROM\s+.+?)(ORDER\s+BY|GROUP\s+BY|LIMIT|$)", sql, re.IGNORECASE | re.DOTALL)
            if m:
                sql = sql[:m.end(1)] + f" WHERE {clause} " + sql[m.end(1):]

    return sql


def _extract_aliases(sql: str) -> dict[str, str]:
    """Extract table alias → table_name mapping from FROM/JOIN clauses."""
    mapping = {}
    # Match: FROM table_name alias or JOIN table_name alias
    for m in re.finditer(
        r"(?:from|join)\s+`?(\w+)`?\s+(?:AS\s+)?(\w+)",
        sql,
        re.IGNORECASE,
    ):
        table = m.group(1).lower()
        alias = m.group(2).lower()
        if alias not in ("where", "on", "and", "or", "group", "order", "limit", "select", "set"):
            mapping[alias] = table
    # Also handle: FROM table_name (no alias)
    for m in re.finditer(
        r"from\s+`?(\w+)`?\s*(?:where|$|group|order|limit|inner|left|right|join)",
        sql,
        re.IGNORECASE,
    ):
        table = m.group(1).lower()
        if table not in mapping.values():
            mapping[table] = table  # alias = table name
    return mapping
