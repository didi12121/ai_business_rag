import json
import time
import httpx
from sqlalchemy import text

from app.database import SessionLocal
from app.llm.base import LlmClient

_LLM_CONFIG_CACHE: dict | None = None
_LLM_CONFIG_TS: float = 0
LLM_CONFIG_TTL: float = 30  # seconds, auto-pick up config changes without restart


def _load_model_from_table() -> dict | None:
    """Load the active model from ai_llm_model table. Returns None if table missing or empty."""
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT base_url, api_key, model, timeout "
                "FROM ai_llm_model WHERE is_active = 1 LIMIT 1"
            )
        ).fetchone()
        if not row:
            return None
        return {
            "base_url": row[0], "api_key": row[1],
            "model": row[2], "timeout": str(row[3]),
        }
    except Exception:
        # Table may not exist yet
        return None
    finally:
        db.close()


def _load_llm_config() -> dict:
    """Load LLM config: prefers ai_llm_model table, falls back to sys_config."""
    model_config = _load_model_from_table()
    if model_config:
        return model_config
    # Fallback to sys_config (backward compat)
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT config_key, config_value FROM sys_config "
                "WHERE config_key LIKE 'ai.llm.%'"
            )
        ).fetchall()
        return {row[0].replace("ai.llm.", ""): row[1] for row in rows}
    except Exception:
        return {}
    finally:
        db.close()


def get_llm_config(refresh: bool = False) -> dict:
    global _LLM_CONFIG_CACHE, _LLM_CONFIG_TS
    if _LLM_CONFIG_CACHE is None or refresh or (time.time() - _LLM_CONFIG_TS > LLM_CONFIG_TTL):
        _LLM_CONFIG_CACHE = _load_llm_config()
        _LLM_CONFIG_TS = time.time()
    return _LLM_CONFIG_CACHE


def refresh_llm_config() -> dict:
    """Force immediate reload of LLM config (called on model activate/update/delete)."""
    return get_llm_config(refresh=True)


def _normalize_base_url(url: str) -> str:
    url = url.rstrip("/")
    # Strip /chat/completions suffix if user pasted the full endpoint
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url


class OpenAICompatibleClient(LlmClient):

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120):
        self.base_url = _normalize_base_url(base_url)
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def chat(self, messages: list[dict], temperature: float = 0.1) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"LLM API error: {response.status_code} {response.text[:500]}"
                )
            data = response.json()
            choices = data.get("choices")
            if choices:
                return choices[0]["message"]["content"]
            raise RuntimeError(f"LLM returned empty choices: {data}")

    async def chat_stream(self, messages: list[dict], temperature: float = 0.1):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True,
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"LLM API error: {response.status_code} {body[:500]}"
                    )
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices")
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            c = delta.get("content")
                            if c:
                                yield c
                        except json.JSONDecodeError:
                            continue


def create_llm_client() -> OpenAICompatibleClient:
    config = get_llm_config()
    return OpenAICompatibleClient(
        base_url=config.get("base_url", ""),
        api_key=config.get("api_key", ""),
        model=config.get("model", ""),
        timeout=int(config.get("timeout", 120)),
    )
