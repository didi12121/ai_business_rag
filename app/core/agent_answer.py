import json
from datetime import datetime

from app.llm.openai_compatible import create_llm_client

FINAL_ANSWER_PROMPT = """
你是工厂业务数据分析师。根据查询结果生成一份简洁的业务报告。

当前日期：{current_date}

=== 用户问题 ===
{question}

=== 查询计划摘要 ===
{plan_summary}

=== 成功步骤结果 ===
{observations_json}

=== 失败步骤 ===
{failed_steps_json}

=== 部分成功状态 ===
partialSuccess: {partial_success}

=== 输出规范 ===

请严格按照以下结构输出，用自然语言，不要用 Markdown 表格。

【结论】
一句话直接回答用户问题。

【关键数据】
- 用中文标签 + 数值，每条一行。
- 金额保留 2 位小数并带"元"。
- 重量保留 2 位小数。
- 排行榜用编号列表：1. 产品名：金额 元

【简要分析】
- 简短的 1-3 句话分析排名、差距、趋势、异常点等。
- 如果数据不足或无法分析，请说明。

【统计口径】
- 时间范围：根据查询步骤中的时间条件说明。
- 涉及 shipment_amount（出货折算金额）：说明口径为"出货折算金额按业务规则计算：出库重量 × 单位换算系数 ÷ 产品单重 × 产品单价。is_kg=1时系数为1000，否则为500。"
- 涉及 record_amount（普通记录金额）：说明口径为"金额按数量 × 单价计算。"
- 涉及其他指标（重量、数量等）：简要说明计算方式。
- 不要同时出现两种金额口径的说明，只说明实际使用的口径。
- 如果用户没有问计算公式且不是金额相关，可以简化为"按业务规则计算"。

=== 严格规则 ===

1. 不使用 Markdown 表格（| ... | 格式）。
2. 不暴露 SQL、字段名（如 ad_product_info_id、raw_materials_code）、JSON。
3. 不输出"根据 Agent / observations / rows / JSON"。
4. 用"根据当前查询结果"替代。
5. 数据为空时明确说"没有查到相关数据"，并给出可能原因和建议。
6. partialSuccess=true 时说明"部分查询步骤未完成，分析可能不完整"。
7. 排行榜类问题：先给第一名结论，再列前 N 名编号列表。
8. 最高/最多类问题：展示产品名 + 数值 + 对比第二名。
9. 原因分析类：结合上下文和查询结果解释，不编造。
10. 简单问题（如"某产品单价多少"）可以简化结构，不强制四段式。
11. 金额数值后面加"元"。

请生成中文回答：
"""


async def generate_final_answer(
    question: str,
    plan: dict,
    observations: list[dict],
    successful_steps: list[dict] | None = None,
    failed_steps: list[dict] | None = None,
    partial_success: bool = False,
) -> str:
    current_date = datetime.now().strftime("%Y-%m-%d")

    # Compact plan summary with metric info
    plan_summary = ""
    if plan:
        plan_summary = f"目标: {plan.get('goal', '')}, 任务类型: {plan.get('taskType', '')}"
        # Collect metrics used in each step for caliber guidance
        metrics_used = []
        for step in plan.get("steps", []):
            m = step.get("metric", "")
            if m and m not in ("unknown", "record_count") and m not in metrics_used:
                metrics_used.append(m)
        if metrics_used:
            plan_summary += f", 使用的指标: {', '.join(metrics_used)}"

    failed_summary = []
    if failed_steps:
        for f in failed_steps:
            failed_summary.append({
                "stepId": f.get("stepId"),
                "name": f.get("name"),
                "errorCode": f.get("errorCode"),
                "errorMsg": f.get("errorMsg"),
            })

    prompt = FINAL_ANSWER_PROMPT.format(
        current_date=current_date,
        question=question,
        plan_summary=plan_summary,
        observations_json=json.dumps(observations, ensure_ascii=False, indent=2, default=str),
        failed_steps_json=json.dumps(failed_summary, ensure_ascii=False, indent=2),
        partial_success=str(partial_success).lower(),
    )

    client = create_llm_client()
    return await client.chat([{"role": "system", "content": prompt}])
