import json

from app.llm.openai_compatible import create_llm_client
from app.prompts.intent_validation_prompt import INTENT_VALIDATION_PROMPT


async def validate_intent(
    question: str,
    intent: str,
    params: dict,
) -> dict:
    """Validate and optionally correct a regex-matched intent using LLM.

    Returns:
        {
            "valid": bool,
            "intent": str,     # original or corrected
            "params": dict,    # original or corrected
            "reason": str,
        }
    On any error (network, parse, timeout), returns valid=True (passthrough).
    """
    prompt = INTENT_VALIDATION_PROMPT.format(
        question=question,
        intent=intent,
        params_json=json.dumps(params, ensure_ascii=False),
    )

    try:
        client = create_llm_client()
        raw = await client.chat(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.0,
        )
        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.lstrip("`").lstrip("json").strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        result = json.loads(raw)
        return {
            "valid": bool(result.get("valid", True)),
            "intent": result.get("intent", intent),
            "params": result.get("params", params),
            "reason": result.get("reason", ""),
        }
    except Exception:
        # Degrade gracefully — trust the regex match on any error
        return {"valid": True, "intent": intent, "params": params, "reason": "校验器异常，使用规则匹配结果"}
