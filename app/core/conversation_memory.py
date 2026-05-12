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


def _make_summary(turn: dict) -> str:
    """Generate a short text summary of a turn."""
    q = turn.get("question", "")
    a = turn.get("answer", "")
    short_answer = a[:200] if a else "(无回答)"
    return f"问题: {q}\n结论: {short_answer}"


def add_turn(session_id: str, turn: dict):
    if session_id not in _store:
        _store[session_id] = []

    # Compact observations
    if "observations" in turn:
        turn["observations"] = _compact(turn["observations"])
    if "summary" not in turn:
        turn["summary"] = _make_summary(turn)
    turn["createdAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _store[session_id].append(turn)
    # Trim to max turns
    if len(_store[session_id]) > MAX_TURNS:
        _store[session_id] = _store[session_id][-MAX_TURNS:]


def get_context(session_id: str, max_turns: int = 5) -> list[dict]:
    turns = _store.get(session_id, [])
    return turns[-max_turns:] if turns else []


def clear_context(session_id: str):
    _store.pop(session_id, None)


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]
