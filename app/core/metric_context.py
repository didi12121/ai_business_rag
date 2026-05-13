import logging
from sqlalchemy import text
from app.database import SessionLocal

logger = logging.getLogger("ai_business_rag")


def load_metric_definitions() -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT
                metric_code, metric_name, description,
                sql_expression, aggregate_expression,
                required_tables, required_fields, example_question
            FROM ai_metric_definition
            WHERE enabled = 1
            ORDER BY id ASC
        """)).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        logger.warning("Failed to load ai_metric_definition, metrics unavailable")
        return []
    finally:
        db.close()


def build_metric_prompt_section() -> str:
    """Build the metric definitions section for LLM prompts."""
    metrics = load_metric_definitions()
    if not metrics:
        return ""
    lines = ["=== 可用业务指标定义 ===", ""]
    for m in metrics:
        lines.append(f"指标编码: {m['metric_code']}")
        lines.append(f"指标名称: {m['metric_name']}")
        lines.append(f"说明: {m['description']}")
        lines.append(f"聚合表达式: {m['aggregate_expression']}")
        lines.append(f"需要表: {m['required_tables']}")
        lines.append(f"需要字段: {m['required_fields']}")
        lines.append("")
    lines.append("指标使用规则：")
    lines.append("- 如果当前 step.metric 命中某个 metric_code，必须使用该指标的 aggregate_expression。")
    lines.append("- 不要自行猜测指标计算公式，不要使用 total_price/amount 等不存在字段作为出货金额。")
    lines.append("- shipment_amount 排序用 ORDER BY total_amount DESC（别名为 total_amount）。")
    lines.append("- 涉及 shipment_amount 必须 JOIN ad_product_record+ad_product_info+ad_factory_info。")
    lines.append("- 必须使用 NULLIF(api.weight, 0) 避免除以0。")
    lines.append("")
    return "\n".join(lines)
