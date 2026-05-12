import re
from datetime import datetime


def _current_dates() -> tuple[str, str, str]:
    now = datetime.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        end = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        start.strftime("%Y-%m-%d %H:%M:%S"),
        end.strftime("%Y-%m-%d %H:%M:%S"),
        start.strftime("%Y-%m"),
    )


def quick_intent_match(question: str) -> dict | None:
    q = question.strip()

    # factory_list
    if re.search(r"(有哪些?|所有|全部).*(厂家|工厂|厂商)", q) or re.search(r"(厂家|工厂|厂商).*(列表|有哪些|多少家)", q):
        return {"intent": "factory_list", "confidence": 0.95, "params": {}, "reason": "本地规则匹配"}

    # factory_product_list: "xxx有哪些产品？" / "xxx的产品"
    m = re.search(r"(.+?)(有哪些?|做什么?|生产什么?|的).*产品", q)
    if m and len(m.group(1)) < 20:
        name = m.group(1).strip().rstrip("的")
        return {"intent": "factory_product_list", "confidence": 0.92, "params": {"factoryName": name}, "reason": "本地规则匹配"}

    # product_parts_query: "xxx有什么胶件/配件"
    m = re.search(r"(.+?)(有什么?|有哪些?|什么).*(胶件|配件|零件|部件)", q)
    if m and len(m.group(1)) < 30:
        name = m.group(1).strip()
        return {"intent": "product_parts_query", "confidence": 0.92, "params": {"productName": name}, "reason": "本地规则匹配"}

    # product_info_query: "xxx单价/多少钱/信息/是什么/什么颜色/什么原料"
    m = re.search(r"(.+?)(单价|多少钱|什么价|信息|详情|规格|是什么|什么颜色|什么原料|重量|多重)", q)
    if m and len(m.group(1)) < 30:
        name = m.group(1).strip()
        params = {"productName": name}
        # also try to extract color
        color_m = re.search(r"(黄|红|蓝|绿|黑|白|灰|紫|橙|粉|透明)", name)
        if color_m:
            params["color"] = color_m.group(1)
        return {"intent": "product_info_query", "confidence": 0.90, "params": params, "reason": "本地规则匹配"}

    # order_list: "出库单" / "订单列表" / "有哪些订单" / "未签单"
    if any(w in q for w in ["出库单", "订单列表", "有哪些订单", "多少订单", "订单情况", "未签单", "已签单", "已作废"]):
        params = {}
        # order_date is varchar yyyy-MM-dd, not datetime
        if any(w in q for w in ["今天", "今日"]):
            params["orderDate"] = datetime.now().strftime("%Y-%m-%d")
        elif any(w in q for w in ["昨天", "昨日"]):
            from datetime import timedelta
            params["orderDate"] = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if "未签单" in q:
            params["signState"] = "N"
        elif "已签单" in q:
            params["signState"] = "Y"
        elif "已作废" in q:
            params["signState"] = "D"
        return {"intent": "order_list", "confidence": 0.92, "params": params, "reason": "本地规则匹配"}

    # order_detail: "订单明细" / "订单里有什么"
    if any(w in q for w in ["订单明细", "订单里有什么", "订单包含"]):
        return {"intent": "order_detail", "confidence": 0.92, "params": {}, "reason": "本地规则匹配"}

    # product_out_summary: "出货流水" (NOT "出库单"/"订单"!)
    has_time = any(w in q for w in ["这个月", "本月", "上个月", "上月", "今天"])
    has_out = any(w in q for w in ["出了多少", "出货", "出库", "出了几", "出了好多"])
    if has_time and has_out:
        params = _fill_dates({}, question)
        # extract product name
        m = re.search(r"这个月|本月|上个月|上月|今天(.+?)(出了多少|出货|出库)", q)
        if not m:
            m = re.search(r"(.+?)(出了多少|出货|出库)", q)
        if m and len(m.group(1)) < 30:
            params["productName"] = m.group(1).strip()
        return {"intent": "product_out_summary", "confidence": 0.90, "params": params, "reason": "本地规则匹配"}

    # raw_material_usage: "这个月xxx用了多少" / "原料消耗"
    has_usage = any(w in q for w in ["用了多少", "原料消耗", "原料用了", "消耗排行", "用了多少原料"])
    if has_time or has_usage:
        m = re.search(r"(.+?)(用了多少|消耗|原料)", q)
        if m and len(m.group(1)) < 20:
            params = _fill_dates({}, question)
            params["rawName"] = m.group(1).strip()
            return {"intent": "raw_material_usage", "confidence": 0.90, "params": params, "reason": "本地规则匹配"}

    # business_rule_explain — check BEFORE inventory to avoid mismatch
    if any(w in q for w in ["怎么算", "怎么计算", "是什么意思", "什么意思", "规则", "公式", "为什么", "如何计算"]):
        return {"intent": "business_rule_explain", "confidence": 0.92, "params": {}, "reason": "本地规则匹配"}

    # monthly_inventory_query: "库存" (but not "怎么算"/"规则")
    has_inv = any(w in q for w in ["库存", "还有多少库存", "库存情况", "库存为负", "库存多少"])
    if has_inv:
        params = _fill_dates({}, question)
        if "负" in q:
            params["onlyNegative"] = True
        # extract raw material name before 库存
        m = re.search(r"^(.+?)(库存|还有多少库存|的库存)", q)
        if not m:
            m = re.search(r"这个月|本月|上个月|上月(.+?)(库存)", q)
        if m and m.group(1) and len(m.group(1)) < 20:
            params["rawName"] = m.group(1).strip()
        return {"intent": "monthly_inventory_query", "confidence": 0.90, "params": params, "reason": "本地规则匹配"}

    return None


def _fill_dates(params: dict, question: str) -> dict:
    start_date, end_date, month_str = _current_dates()
    if any(w in question for w in ["这个月", "本月"]):
        params["startDate"] = start_date
        params["endDate"] = end_date
        params["monthStr"] = month_str
    return params
