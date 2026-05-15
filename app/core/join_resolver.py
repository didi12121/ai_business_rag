from app.core.relation_context import load_table_relations
from app.core.table_alias import get_table_alias


def resolve_join_paths(required_tables: list[str], base_table: str | None = None) -> dict:
    """Given a list of required tables, find JOIN paths from ai_table_relation.

    If base_table is provided and is in required_tables, use it as the FROM table.
    If base_table is provided but not in required_tables, add it.
    If base_table is None, auto-pick the best base table.
    """
    relations = load_table_relations()
    if not relations or not required_tables:
        return {"canResolve": False, "joins": [], "reason": "无关系数据或未指定表"}

    tables = set(required_tables)
    if base_table:
        tables.add(base_table)
        base = base_table
    else:
        base = _pick_base_table(tables, relations)

    joins = []
    covered = {base}
    used_edges = set()

    # BFS: find paths from covered tables to remaining tables
    for _ in range(len(tables)):
        for r in relations:
            edge_key = (r["from_table"], r["to_table"], r["from_field"], r["to_field"])
            if edge_key in used_edges:
                continue
            ft = r["from_table"]
            tt = r["to_table"]
            if ft in covered and tt not in covered:
                alias_ft = get_table_alias(ft)
                alias_tt = get_table_alias(tt)
                joins.append({
                    "joinType": r["join_type"],
                    "fromTable": ft, "fromField": r["from_field"],
                    "toTable": tt, "toField": r["to_field"],
                    "sql": f"{r['join_type']} {tt} {alias_tt} ON {alias_ft}.{r['from_field']} = {alias_tt}.{r['to_field']}",
                })
                covered.add(tt)
                used_edges.add(edge_key)
            elif tt in covered and ft not in covered:
                alias_ft = get_table_alias(ft)
                alias_tt = get_table_alias(tt)
                joins.append({
                    "joinType": r["join_type"],
                    "fromTable": tt, "fromField": r["to_field"],
                    "toTable": ft, "toField": r["from_field"],
                    "sql": f"{r['join_type']} {ft} {alias_ft} ON {alias_tt}.{r['to_field']} = {alias_ft}.{r['from_field']}",
                })
                covered.add(ft)
                used_edges.add(edge_key)

    missing = tables - covered
    if missing:
        return {
            "canResolve": False,
            "baseTable": base,
            "joins": joins,
            "reason": f"无法找到 JOIN 路径到表: {', '.join(missing)}",
        }

    return {
        "canResolve": True,
        "baseTable": base,
        "joins": joins,
        "reason": "",
    }


def _pick_base_table(tables: set[str], relations: list[dict]) -> str:
    """Pick the best base table — prefer the one with most outgoing relations."""
    scores: dict[str, int] = {}
    for r in relations:
        if r["from_table"] in tables:
            scores[r["from_table"]] = scores.get(r["from_table"], 0) + 1
        if r["to_table"] in tables:
            scores[r["to_table"]] = scores.get(r["to_table"], 0) + 1
    if scores:
        return max(scores, key=scores.get)
    return next(iter(tables))
