"""In-memory conversation context store. Session-scoped, max 5 turns."""
import json
import uuid
from datetime import datetime

_store: dict[str, list[dict]] = {}
MAX_TURNS = 5


def _compact(obs: list[dict]) -> list[dict]:
    """Keep only rowCount + first 3 rows preview per observation."""
    compacted = []
    for o in (obs or []):
        rows = o.get("rows", [])[:3]
        compacted.append({
            "stepId": o.get("stepId"),
            "name": o.get("name"),
            "purpose": o.get("purpose"),
            "rowCount": o.get("rowCount"),
            "rowsPreview": rows,
        })
    return compacted


_ENTITY_FIELDS = [
    "ad_product_info_id", "product_info_id", "ad_product_name",
    "factory_info_id", "ad_factory_info_id", "factory_name",
    "raw_materials_code", "raw_name",
    "order_no", "ad_order_id",
    "part_id", "parts_name",
    "month_str", "quantity",
    "total_amount", "total_weight", "total_kuang_num",
]


def _extract_key_entities(turn: dict) -> dict:
    """Extract IDs, names, dates from observations."""
    entities = {}
    for obs in (turn.get("observations") or []):
        for row in (obs.get("rowsPreview") or obs.get("rows", []))[:3]:
            for k, v in (row or {}).items():
                if k in _ENTITY_FIELDS and v is not None:
                    if k not in entities:
                        entities[k] = []
                    if v not in entities[k]:
                        entities[k].append(v)
    # Extract from plan
    plan = turn.get("plan", {})
    if plan:
        for step in (plan.get("steps") or []):
            tr = step.get("timeRange", {})
            if tr:
                entities["lastTimeRange"] = tr
            if step.get("metric"):
                entities["lastMetric"] = step["metric"]
            if step.get("targetEntity"):
                entities["lastTargetEntity"] = step["targetEntity"]
    return entities


def _make_summary(turn: dict) -> str:
    q = turn.get("question", "")
    a = turn.get("answer", "")
    entities = turn.get("keyEntities", {})
    parts = [f"问题: {q}", f"结论: {a[:200] if a else '(无回答)'}"]
    if entities:
        # Add key entity values
        for k in ["ad_product_name", "factory_name", "raw_materials_code", "order_no"]:
            if k in entities and entities[k]:
                parts.append(f"{k}: {', '.join(str(x) for x in entities[k][:3])}")
    return "\n".join(parts)


def add_turn(session_id: str, turn: dict):
    if session_id not in _store:
        _store[session_id] = []

    if "observations" in turn:
        turn["observations"] = _compact(turn["observations"])
    turn["keyEntities"] = _extract_key_entities(turn)
    turn["summary"] = _make_summary(turn)
    turn["createdAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _store[session_id].append(turn)
    if len(_store[session_id]) > MAX_TURNS:
        _store[session_id] = _store[session_id][-MAX_TURNS:]


def get_context(session_id: str, max_turns: int = 5) -> list[dict]:
    turns = _store.get(session_id, [])
    return turns[-max_turns:] if turns else []


def clear_context(session_id: str):
    _store.pop(session_id, None)


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]
