"""Query Plan Validator — checks the LLM-generated plan for sanity."""

import re
from datetime import datetime

_BAD_FILTERS = [
    "哪个产品", "哪些产品", "什么产品", "哪个厂家", "哪些厂家",
    "什么厂家", "哪个原料", "哪些原料", "什么原料", "出货金额最高",
    "出货最多", "金额最高", "重量最大", "排行", "top",
]


def validate_and_fix_plan(plan: dict, question: str, max_limit: int = 100) -> dict:
    errors = []

    if not plan.get("canAnswer"):
        return plan  # Nothing to validate

    steps = plan.get("steps", [])
    if not steps:
        errors.append("Query Plan 没有步骤")

    for i, step in enumerate(steps):
        sid = step.get("stepId", i + 1)

        # ranking must have groupBy, metric, sort, limit
        if step.get("queryType") == "ranking":
            if not step.get("groupBy"):
                # auto-fix from targetEntity
                te = step.get("targetEntity", "")
                if te == "product":
                    step["groupBy"] = ["product"]
                elif te == "factory":
                    step["groupBy"] = ["factory"]
                elif te == "raw_material":
                    step["groupBy"] = ["raw_material"]
                else:
                    errors.append(f"Step {sid}: ranking 必须指定 groupBy")

            if not step.get("sort"):
                mc = step.get("metric", "")
                if mc == "shipment_amount":
                    step["sort"] = [{"field": "shipment_amount", "direction": "desc"}]
                elif mc == "shipment_weight":
                    step["sort"] = [{"field": "shipment_weight", "direction": "desc"}]
                elif mc == "shipment_quantity":
                    step["sort"] = [{"field": "shipment_quantity", "direction": "desc"}]

        # Check filters for interrogative garbage
        for f in step.get("filters", []):
            if isinstance(f, str):
                for bad in _BAD_FILTERS:
                    if bad in f:
                        errors.append(f"Step {sid}: filter 包含疑问词 '{bad}' → 已清除")
                        step["filters"].remove(f)
                        break
            elif isinstance(f, dict):
                fv = str(f.get("value", "")).lower()
                for bad in _BAD_FILTERS:
                    if bad in fv:
                        errors.append(f"Step {sid}: filter 包含疑问词 '{bad}' → 已清除")
                        step["filters"].remove(f)
                        break

        # Limit enforcement
        slimit = step.get("limit")
        if not slimit or slimit > max_limit:
            step["limit"] = max_limit

        # Time range fill
        if not step.get("timeRange") or not step["timeRange"].get("start"):
            now = datetime.now()
            if any(w in question for w in ["上个月", "上月"]):
                if now.month == 1:
                    start = now.replace(year=now.year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
                else:
                    start = now.replace(month=now.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0)
                end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                step["timeRange"] = {
                    "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": end.strftime("%Y-%m-%d %H:%M:%S"),
                    "label": "上个月",
                }
            elif any(w in question for w in ["这个月", "本月"]):
                start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if now.month == 12:
                    end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                else:
                    end = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
                step["timeRange"] = {
                    "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": end.strftime("%Y-%m-%d %H:%M:%S"),
                    "label": "本月",
                }
            elif any(w in question for w in ["今天", "今日"]):
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                from datetime import timedelta
                end = start + timedelta(days=1)
                step["timeRange"] = {
                    "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": end.strftime("%Y-%m-%d %H:%M:%S"),
                    "label": "今天",
                }

    # Update plan
    plan["steps"] = steps
    if errors:
        plan["_validationErrors"] = errors

    return plan
