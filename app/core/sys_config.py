from app.database import SessionLocal

_cache: dict | None = None

_DEFAULTS = {
    "agent.enabled": True,
    "agent.max_steps": 5,
    "agent.default_limit": 100,
    "agent.show_plan": True,
    "agent.show_step_sql": True,
    "agent.allow_followup_steps": True,
    "free_sql.enabled": True,
    "free_sql.require_confirm": False,
    "free_sql.max_rows": 200,
    "free_sql.explain_before_run": True,
    "free_sql.max_estimated_rows": 50000,
    "sql.timeout_seconds": 10,
    "sql.show_sql_default": True,
    "sql_review.enabled": True,
    "sql_review.max_retry": 1,
}

_BOOL_KEYS = {
    "agent.enabled", "agent.show_plan", "agent.show_step_sql",
    "agent.allow_followup_steps",
    "free_sql.enabled", "free_sql.require_confirm",
    "free_sql.explain_before_run", "sql.show_sql_default",
    "sql_review.enabled",
}

_INT_KEYS = {
    "agent.max_steps", "agent.default_limit",
    "free_sql.max_rows", "free_sql.max_estimated_rows",
    "sql.timeout_seconds",
    "sql_review.max_retry",
}


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "y", "on")
    return False


def _parse_int(value, default: int) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _parse_value(key: str, raw: str):
    if key in _BOOL_KEYS:
        return _parse_bool(raw)
    if key in _INT_KEYS:
        return _parse_int(raw, _DEFAULTS.get(key, 0))
    return raw


def load_sys_config(prefix: str = "ai.") -> dict:
    db = SessionLocal()
    try:
        from sqlalchemy import text
        rows = db.execute(
            text(
                "SELECT config_key, config_value FROM sys_config "
                "WHERE config_key LIKE CONCAT(:prefix, '%')"
            ),
            {"prefix": prefix},
        ).fetchall()
        config = {}
        for row in rows:
            key = row[0]
            if key.startswith(prefix):
                short_key = key[len(prefix):]
            else:
                short_key = key
            config[short_key] = _parse_value(short_key, row[1])
        return config
    finally:
        db.close()


def get_ai_config() -> dict:
    global _cache
    if _cache is None:
        _cache = load_sys_config("ai.")
        for k, v in _DEFAULTS.items():
            if k not in _cache:
                _cache[k] = v
    return _cache


def refresh_ai_config_cache() -> dict:
    global _cache
    _cache = load_sys_config("ai.")
    for k, v in _DEFAULTS.items():
        if k not in _cache:
            _cache[k] = v
    return _cache
