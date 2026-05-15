import json
import re
from datetime import datetime

from app.llm.openai_compatible import create_llm_client
from app.core.business_context import load_table_schemas, load_field_schemas, load_business_rules

PLANNER_PROMPT = """
你是工厂业务数据分析规划器。

你的任务：根据用户问题，判断需要查询哪些数据、按什么顺序查、每一步的目的是什么。
你不需要生成 SQL，只需要规划查询步骤。

当前日期：{current_date}

=== 可查询业务对象 ===

{table_overview}

=== 表关系（决定 JOIN 哪些表） ===

{table_relations}

=== 业务指标定义 ===

{metric_definitions}

=== 业务规则 ===

{business_rules}

=== 规划规则 ===

1. 只能规划查询和分析，不能规划增删改。
2. 如果用户要修改数据 → canAnswer=false, taskType=unsupported。
3. 一次查询能解决的 → steps 只有 1 步。
4. 需要分析、对比、趋势、原因的 → 可以多步。
5. 每一步必须说明 purpose, dataNeeded, queryType, targetEntity, metric, filters, groupBy, sort, limit。
6. "哪个产品""什么产品"不是产品名 → targetEntity=product。
7. "哪个厂家""什么厂家"不是厂家名 → targetEntity=factory。
8. "哪个原料"不是原料名 → targetEntity=raw_material。
9. "最高/最大/排行/前几" → ranking + desc。
10. "最低/最少" → ranking + asc。
11. metric 金额区分规则（重要）：
    a) 用户明确说以下词语 → metric=shipment_amount（出货折算金额）：
       "出货金额"、"出库金额"、"出货折算金额"、"哪个产品出货金额最高"、"出货金额排行榜"
    b) 用户明确说以下词语 → metric=record_amount（普通记录金额）：
       "订单金额"、"明细金额"、"数量乘单价"、"数量×单价"、"普通金额"
    c) 用户只说"金额"但上下文是产品出货/出库统计 → 默认 metric=shipment_amount
    d) 用户只说"金额"但上下文是订单/明细 → 默认 metric=record_amount
    e) 无法判断金额口径 → 默认 shipment_amount，在 plan.reason 中注明"用户未明确金额口径，系统按出货折算金额口径处理"
12. "重量/斤/KG/公斤" → metric=shipment_weight。
13. "数量/框数/筐数/件数" → metric=shipment_quantity。
14. "出货金额/出货量" → 从 ad_product_record 汇总。
15. "最近 X 天" → 从 {current_date} 往前推 X 天。
16. "这个月/本月" → {current_date} 所在月的第一天到下月第一天。
17. "上个月" → {current_date} 上个月第一天到本月第一天。
18. 时间范围必须转成明确 start/end 格式 yyyy-MM-dd HH:mm:ss。
19. 不要把疑问词放进 filters。
20. 返回严格 JSON，不要 Markdown，不要解释。
21. 如果上下文中有类似问题，可以参考其业务对象、指标等。
22. 用户追问"为什么？""那今天呢？"时，沿用上一轮的业务对象和指标，只改变时间范围或增加原因分析步骤。

=== 实体消歧 ===
23. 用户问题中可能同时出现厂家和产品：
    - 带"圈/厂/行/公司/商行/实业/塑胶/塑料/五金"后缀 → 通常是厂家名
    - 带字母数字编码（如 ws-01-abs, TDX-01, M30, 690） → 通常是产品名/型号
    - 纯颜色词（黄/红/蓝/绿/黑/白/灰）且独立出现 → 可能是颜色筛选
    - "妙趣圈的ws-01-abs价格" → 妙趣圈=厂家, ws-01-abs=产品

=== requiredTables 规则 ===
24. 每个 step 必须包含 requiredTables 字段，列出本步骤需要的所有表。
25. 涉及厂家过滤 → 包含 ad_factory_info
26. 涉及产品名/颜色/原料 → 包含 ad_product_info
27. 涉及出库/出货/重量/数量 → 包含 ad_product_record
28. 涉及金额（shipment_amount） → 必须包含 ad_product_record + ad_product_info + ad_factory_info
29. 涉及订单 → 包含 ad_order_info + ad_order_item
30. 涉及配件/胶件 → 包含 ad_product_parts
31. 涉及库存 → 包含 ad_month_inventory
32. 如果查询只需单表（如"有哪些厂家"），requiredTables 只写那张表。
33. 不要包含不存在的表名。

=== 对话上下文 ===

{conversation_context}

=== 用户问题 ===
{question}

=== 返回格式 ===

{{
  "canAnswer": true,
  "taskType": "data_query | business_analysis | explain | unsupported",
  "goal": "一句话概括查询目标",
  "steps": [
    {{
      "stepId": 1,
      "name": "步骤简称",
      "purpose": "这一步要获取什么数据",
      "dataNeeded": "需要什么数据",
      "queryType": "ranking | aggregate | detail | list | compare | trend",
      "targetEntity": "product | factory | raw_material | order | record",
      "metric": "shipment_amount | record_amount | shipment_weight | shipment_quantity | inventory | record_count | unknown",
      "timeRange": {{"start": "yyyy-MM-dd HH:mm:ss", "end": "yyyy-MM-dd HH:mm:ss", "label": "上个月"}},
      "filters": [],
      "groupBy": ["product"],
      "sort": [{{"field": "shipment_amount", "direction": "desc"}}],
      "limit": 10,
      "dependsOn": null,
      "requiredTables": ["ad_product_record", "ad_product_info", "ad_factory_info"]
    }}
  ],
  "finalAnswerRequirement": "回答需要包含什么内容",
  "reason": "规划理由"
}}

无法回答时：
{{
  "canAnswer": false,
  "taskType": "unsupported",
  "goal": "",
  "steps": [],
  "finalAnswerRequirement": "",
  "reason": "原因"
}}

请返回 JSON：
"""


def _build_table_overview() -> str:
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
        lines.append(f"  [{tname}] {bname}: {desc}")
        for f in fields:
            if f["table_name"] != tname:
                continue
            fname = f["field_name"]
            fbiz = f.get("business_name", "")
            fdesc = f.get("description", "")
            vmap = f.get("value_mapping")
            extra = ""
            if vmap:
                try:
                    vm = json.loads(vmap) if isinstance(vmap, str) else vmap
                    extra = " 枚举: " + ", ".join(f"{k}={v}" for k, v in vm.items())
                except (json.JSONDecodeError, TypeError):
                    pass
            lines.append(f"    {fname} ({fbiz}): {fdesc}{extra}")
    return "\n".join(lines)


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


async def generate_query_plan(
    question: str,
    conversation_context: list[dict] | None = None,
) -> dict:
    overview = _build_table_overview()
    business_rules = load_business_rules()
    rules_text = json.dumps(
        [r.get("rule_content", "") for r in business_rules],
        ensure_ascii=False,
    )
    current_date = datetime.now().strftime("%Y-%m-%d")

    # Load metric definitions
    from app.core.metric_context import build_metric_prompt_section
    metric_section = build_metric_prompt_section()
    from app.core.relation_context import build_relation_prompt_section
    relation_section = build_relation_prompt_section()

    # Build context string
    context_text = ""
    if conversation_context:
        turns = []
        for t in conversation_context[-3:]:  # last 3 turns
            turns.append(f"  问: {t.get('question', '')}\n  答: {t.get('summary', t.get('answer', ''))[:300]}")
        if turns:
            context_text = "最近对话上下文：\n" + "\n".join(turns)
            context_text += "\n\n你可以参考上下文理解省略表达和追问。但涉及新时间范围必须重新查询数据库。"

    prompt = PLANNER_PROMPT.format(
        current_date=current_date,
        table_overview=overview,
        table_relations=relation_section or "无",
        metric_definitions=metric_section or "无",
        business_rules=rules_text,
        conversation_context=context_text or "无上下文",
        question=question,
    )

    client = create_llm_client()
    raw = await client.chat([{"role": "system", "content": prompt}])

    try:
        result = json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        return {
            "canAnswer": False,
            "taskType": "unsupported",
            "reason": f"Planner JSON 解析失败: {raw[:300]}",
            "steps": [],
            "goal": "",
            "finalAnswerRequirement": "",
        }

    return result
