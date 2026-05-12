from datetime import datetime, timedelta
from calendar import monthrange


def resolve_relative_date_params(params: dict, question: str) -> dict:
    now = datetime.now()
    result = dict(params)

    has_this_month = any(w in question for w in ["这个月", "本月"])
    has_last_month = any(w in question for w in ["上个月", "上月"])
    has_today = "今天" in question

    if has_this_month:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        _, last_day = monthrange(now.year, now.month)
        end = (start + timedelta(days=last_day)).replace(hour=0, minute=0, second=0, microsecond=0)
        result["startDate"] = start.strftime("%Y-%m-%d %H:%M:%S")
        result["endDate"] = end.strftime("%Y-%m-%d %H:%M:%S")
        result["monthStr"] = start.strftime("%Y-%m")
    elif has_last_month:
        if now.month == 1:
            start = now.replace(year=now.year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = now.replace(month=now.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result["startDate"] = start.strftime("%Y-%m-%d %H:%M:%S")
        result["endDate"] = end.strftime("%Y-%m-%d %H:%M:%S")
        result["monthStr"] = start.strftime("%Y-%m")
    elif has_today:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        result["startDate"] = start.strftime("%Y-%m-%d %H:%M:%S")
        result["endDate"] = end.strftime("%Y-%m-%d %H:%M:%S")

    return result
