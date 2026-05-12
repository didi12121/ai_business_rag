import json
from datetime import date, datetime
from decimal import Decimal

from app.llm.openai_compatible import create_llm_client
from app.prompts.answer_prompt import ANSWER_PROMPT
from app.prompts.rule_explain_prompt import RULE_EXPLAIN_PROMPT


class _JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(obj, date):
            return obj.strftime("%Y-%m-%d")
        return super().default(obj)


def _to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, cls=_JsonEncoder)


async def generate_answer(
    question: str,
    intent: str,
    template_description: str,
    business_rules: list[dict],
    rows: list[dict],
    result_description: str,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d")
    client = create_llm_client()
    prompt = ANSWER_PROMPT.format(
        current_date=now,
        question=question,
        intent=intent,
        template_description=template_description,
        business_rules=_to_json(business_rules),
        sql_result_json=_to_json(rows[:50]),
        result_description=result_description,
    )
    return await client.chat([{"role": "system", "content": prompt}])


async def explain_business_rule(
    question: str,
    table_schemas: list[dict],
    field_schemas: list[dict],
    business_rules: list[dict],
) -> str:
    now = datetime.now().strftime("%Y-%m-%d")
    client = create_llm_client()
    prompt = RULE_EXPLAIN_PROMPT.format(
        current_date=now,
        question=question,
        table_schemas=_to_json(table_schemas),
        field_schemas=_to_json(field_schemas),
        business_rules=_to_json(business_rules),
    )
    return await client.chat([{"role": "system", "content": prompt}])
