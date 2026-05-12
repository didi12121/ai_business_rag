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
11. "金额/销售额/总价" → metric=shipment_amount。
12. "重量/斤/KG/公斤" → metric=shipment_weight。
13. "数量/框数/筐数/件数" → metric=shipment_quantity。
14. "出货金额/出货量" → 从 ad_product_record 汇总。
15. "最近 X 天" → 从 {current_date} 往前推 X 天。
16. "这个月/本月" → {current_date} 所在月的第一天到下月第一天。
17. "上个月" → {current_date} 上个月第一天到本月第一天。
18. 时间范围必须转成明确 start/end 格式 yyyy-MM-dd HH:mm:ss。
19. 不要把疑问词放进 filters。
20. 返回严格 JSON，不要 Markdown，不要解释。

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
      "metric": "shipment_amount | shipment_weight | shipment_quantity | record_count | inventory | unknown",
      "timeRange": {{"start": "yyyy-MM-dd HH:mm:ss", "end": "yyyy-MM-dd HH:mm:ss", "label": "上个月"}},
      "filters": [],
      "groupBy": ["product"],
      "sort": [{{"field": "shipment_amount", "direction": "desc"}}],
      "limit": 10,
      "dependsOn": null
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


async def generate_query_plan(question: str) -> dict:
    overview = _build_table_overview()
    business_rules = load_business_rules()
    rules_text = json.dumps(
        [r.get("rule_content", "") for r in business_rules],
        ensure_ascii=False,
    )
    current_date = datetime.now().strftime("%Y-%m-%d")

    prompt = PLANNER_PROMPT.format(
        current_date=current_date,
        table_overview=overview,
        business_rules=rules_text,
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
