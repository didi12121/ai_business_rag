import json
import re
from datetime import datetime

from app.llm.openai_compatible import create_llm_client
from app.core.business_context import load_table_schemas, load_field_schemas, load_business_rules

SQL_BUILDER_PROMPT = """
你是 MySQL 只读 SQL 生成器。根据 Query Plan 的当前步骤生成一条 SELECT SQL。

当前日期：{current_date}

=== 可查询表及字段 ===

{table_schemas}

=== 业务规则 ===

{business_rules}

=== 用户问题 ===
{question}

=== Query Plan ===
{plan_json}

=== 当前步骤 ===
{step_json}

=== 之前步骤的结果摘要 ===
{previous_summary}

=== 生成规则 ===

1. 只能 SELECT 或 WITH。
2. 禁止 SELECT *，必须显式列出字段。
3. 禁止多语句。
4. 禁止 INSERT/UPDATE/DELETE/DROP/ALTER/CREATE 等危险操作。
5. 只能访问上面可查询表中的表。
6. 不要使用不存在的表或字段。
7. 有 del_flag 的表必须加 del_flag = '0'。
8. 时间范围使用闭开区间：record_time >= 'xxx' AND record_time < 'xxx'。
9. 必须加 LIMIT。
10. ranking 必须按 queryType 要求的 GROUP BY 和 ORDER BY。
11. "哪个产品"不是产品名，不能生成 product_name LIKE '%哪个产品%'。
12. "哪个厂家"不是厂家名，不能生成 factory_name LIKE '%哪个厂家%'。
13. "哪个原料"不是原料名，不能生成 raw_name LIKE '%哪个原料%'。
14. "出货金额最高"表示按金额汇总排序，不是筛选条件。
15. shipment_amount 用 (quantity * unit_price) 或 total_price 或 sum(weight * unit_price)。
16. shipment_weight 用 weight 字段。
17. shipment_quantity 用 kuang_num 或 num 或 quantity 字段。
18. 不要编造不存在的字段，不确定就 canGenerate=false。
19. 返回严格 JSON，不要 Markdown。

=== 返回格式 ===

{{
  "canGenerate": true,
  "sql": "SELECT ... LIMIT 100",
  "params": {{}},
  "reason": "生成理由",
  "usedTables": ["table1"],
  "riskLevel": "low/medium/high"
}}

无法生成：
{{
  "canGenerate": false,
  "sql": null,
  "reason": "原因",
  "usedTables": [],
  "riskLevel": "high"
}}

请返回 JSON：
"""


def _build_schema_text() -> str:
    schemas = load_table_schemas()
    fields = load_field_schemas()
    lines = []
    for t in schemas:
        allow = t.get("allow_query", 0)
        if not allow or int(allow) != 1:
            continue
        tname = t["table_name"]
        bname = t.get("business_name", "")
        desc = t.get("description", "")
        lines.append(f"[{tname}] {bname}: {desc}")
        for f in fields:
            if f["table_name"] != tname:
                continue
            fname = f["field_name"]
            fbiz = f.get("business_name", "")
            fdesc = f.get("description", "")
            lines.append(f"  {fname}: {fbiz} — {fdesc}")
    return "\n".join(lines)


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


async def build_step_sql(
    question: str,
    plan: dict,
    step: dict,
    previous_observations: list[dict],
) -> dict:
    schema_text = _build_schema_text()
    rules = load_business_rules()
    rules_text = json.dumps([r.get("rule_content", "") for r in rules], ensure_ascii=False)
    current_date = datetime.now().strftime("%Y-%m-%d")

    # Summarize previous observations
    prev_summary = "无"
    if previous_observations:
        summaries = []
        for obs in previous_observations:
            row_count = obs.get("rowCount", 0)
            summaries.append(f"  Step {obs.get('stepId', '?')}: {row_count} 行, 目的: {obs.get('purpose', '')}")
        prev_summary = "\n".join(summaries)

    prompt = SQL_BUILDER_PROMPT.format(
        current_date=current_date,
        table_schemas=schema_text,
        business_rules=rules_text,
        question=question,
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2),
        step_json=json.dumps(step, ensure_ascii=False, indent=2),
        previous_summary=prev_summary,
    )

    client = create_llm_client()
    raw = await client.chat([{"role": "system", "content": prompt}])

    try:
        result = json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        return {
            "canGenerate": False,
            "sql": None,
            "params": {},
            "reason": f"SQL Builder JSON 解析失败: {raw[:300]}",
            "usedTables": [],
            "riskLevel": "high",
        }

    return result
