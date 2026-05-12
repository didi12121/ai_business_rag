import json
import httpx
from sqlalchemy import text

from app.database import SessionLocal
from app.llm.base import LlmClient

_LLM_CONFIG_CACHE: dict | None = None


def _load_llm_config() -> dict:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT config_key, config_value FROM sys_config "
                "WHERE config_key LIKE 'ai.llm.%'"
            )
        ).fetchall()
        return {row[0].replace("ai.llm.", ""): row[1] for row in rows}
    finally:
        db.close()


def get_llm_config(refresh: bool = False) -> dict:
    global _LLM_CONFIG_CACHE
    if _LLM_CONFIG_CACHE is None or refresh:
        _LLM_CONFIG_CACHE = _load_llm_config()
    return _LLM_CONFIG_CACHE


class OpenAICompatibleClient(LlmClient):

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
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
            return data["choices"][0]["message"]["content"]

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
                            delta = chunk["choices"][0].get("delta", {})
                            # DeepSeek returns reasoning_content (thinking) separately
                            # Only yield actual content, skip nulls and reasoning
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
