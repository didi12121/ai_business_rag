import json
import re
from datetime import datetime

from app.llm.openai_compatible import create_llm_client

REVIEWER_PROMPT = """
你是 SQL 业务语义审查员。你的任务是检查 SQL 是否正确回答用户问题。

**重要：你只做审查，不生成新 SQL，不执行 SQL。输出严格 JSON。**

当前日期：{current_date}

=== 用户问题 ===
{question}

=== Query Plan ===
{plan_json}

=== 当前步骤 ===
{step_json}

=== 待审查 SQL ===
{sql}

=== 使用的表 ===
{used_tables}

=== 业务指标定义 ===
{metric_definitions}

=== 表关系（推荐 JOIN 条件） ===
{relation_context}

=== 表及字段 Schema ===
{schema_context}

=== 业务规则 ===
{business_rules}

=== 审查规则 ===

你需要逐项检查以下 8 个维度，每个维度给出通过/不通过，以及具体问题：

**1. 查询目标是否正确**
- 用户问产品 → SQL 是否按产品查询/分组（GROUP BY 产品相关字段）？
- 用户问厂家 → SQL 是否按厂家查询/分组？
- 用户问原料 → SQL 是否按原料查询/分组？
- 不要把"查询产品列表"当成只查产品 ID，需要返回产品名称等信息。

**2. 时间范围是否正确**
- 用户问上个月/本月 → SQL 是否使用了正确的时间范围？
- SQL 是否使用了闭开区间（>= 开始 AND < 结束）？
- 是否遗漏了时间条件？
- endDate 是否为下个周期第一天 00:00:00？

**3. 表 JOIN 是否正确**
- 用户问题涉及厂家 → SQL 是否 JOIN ad_factory_info？
- 用户问题涉及产品属性/颜色/原料 → SQL 是否 JOIN ad_product_info？
- 用户问题涉及出库/出货 → SQL 是否使用 ad_product_record？
- SQL 是否使用了推荐表关系中的 JOIN 条件？
- 是否遗漏了 step.requiredTables 中要求的表？
- JOIN 条件是否使用了推荐路径，而非自创？

**4. 过滤条件是否正确**
- 厂家名称是否过滤在 factory_name 上（不是 product_name 或其他字段）？
- 产品名称是否过滤在 ad_product_name 上？
- 原料是否过滤在 raw_materials_code / raw_name 上？
- 是否把"哪个产品""哪些产品"误当成产品名来 LIKE 查询？
- 是否把"哪个厂家"误当成厂家名？
- 是否把"出货金额最高"误当成筛选条件（应是排序条件）？
- 是否把原料名误当成产品名过滤？

**5. 指标公式是否正确**
- 如果 step.metric = shipment_amount → SQL 是否使用了出货金额指标公式？
- 出货金额公式是否包含 CASE WHEN afi.is_kg = 1 THEN 1000 ELSE 500 END 逻辑？
- 是否错误使用 total_price、unit_price、total_weight 代替出货金额？
- 用户问"金额最高" → 是否按金额排序，而不是按重量（weight）排序？
- 聚合表达式中的 NULLIF 是否保留？

**6. 排序和 LIMIT 是否正确**
- 用户问最高/最多 → ORDER BY ... DESC？
- 用户问最低/最少 → ORDER BY ... ASC？
- 用户问前10/前N → LIMIT N？
- 用户问"哪个"（单个） → LIMIT 1？
- 用户问"哪些"/"列表" → LIMIT 是否合理（不太小）？

**7. del_flag 是否合理**
- 有 del_flag 的表是否过滤了有效数据（del_flag = '0' 或 del_flag IN ('0','2')）？
- 如果业务规则允许 del_flag IN ('0','2')，不要误判为缺少过滤。

**8. SELECT 字段是否足够回答问题**
- 是否包含了用户需要看的名称（厂家名、产品名、原料名等）？
- 是否包含了数值字段（金额、重量、数量等）？
- 是否只返回了 ID 而没有名称？这会导致无法阅读结果。

=== 输出格式 ===

审查通过：
{{
  "passed": true,
  "riskLevel": "low",
  "issues": [],
  "suggestions": [],
  "reason": "SQL 能够正确回答用户问题"
}}

审查不通过：
{{
  "passed": false,
  "riskLevel": "medium",
  "issues": [
    "具体问题1",
    "具体问题2"
  ],
  "suggestions": [
    "具体修复建议1",
    "具体修复建议2"
  ],
  "reason": "一句话总结为什么不通过"
}}

**注意：**
- riskLevel: low=没有问题, medium=有小问题但方向对, high=SQL 完全不对
- issues 列表要具体，指出哪个字段/哪个条件错了
- suggestions 列表要可操作，告诉 SQL Builder 怎么改
- 如果 SQL 大方向正确但有小瑕疵（如缺少某个显示字段），用 riskLevel=medium 并给出建议
- 不要吹毛求疵：如果 SQL 确实能回答问题，即使不是最优写法，也 passed=true

请返回严格 JSON：
"""


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


async def review_sql(
    question: str,
    plan: dict,
    step: dict,
    sql: str,
    used_tables: list[str] | None = None,
    metric_definitions: str | None = None,
    relation_context: str | None = None,
    schema_context: str | None = None,
    business_rules: str | None = None,
) -> dict:
    """审查 SQL 是否在语义上正确回答了用户问题。

    返回格式：
    {
      "passed": True/False,
      "riskLevel": "low"/"medium"/"high",
      "issues": [...],
      "suggestions": [...],
      "reason": "..."
    }
    """
    current_date = datetime.now().strftime("%Y-%m-%d")

    prompt = REVIEWER_PROMPT.format(
        current_date=current_date,
        question=question,
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2),
        step_json=json.dumps(step, ensure_ascii=False, indent=2),
        sql=sql,
        used_tables=json.dumps(used_tables or [], ensure_ascii=False),
        metric_definitions=metric_definitions or "无",
        relation_context=relation_context or "无",
        schema_context=schema_context or "无",
        business_rules=business_rules or "无",
    )

    client = create_llm_client()
    raw = await client.chat([{"role": "system", "content": prompt}])

    try:
        result = json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        return {
            "passed": False,
            "riskLevel": "high",
            "issues": [f"SQL Reviewer JSON 解析失败"],
            "suggestions": [],
            "reason": f"Reviewer 返回无法解析: {raw[:300]}",
        }

    # Ensure required fields exist
    result.setdefault("passed", False)
    result.setdefault("riskLevel", "high")
    result.setdefault("issues", [])
    result.setdefault("suggestions", [])
    result.setdefault("reason", "")

    return result
