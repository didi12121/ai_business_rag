"""Query Router — route user questions to the right processing mode.

Modes:
  reject   — modification requests, unsupported operations
  rule     — business rule / formula explanations
  template — high-confidence template match via quick_intent
  free_sql — single-step queries (one SQL can answer)
  agent    — complex analysis, multi-step, cause analysis
"""

from app.core.sql_safety import is_modification_request
from app.core.quick_intent import quick_intent_match

_RULE_KEYWORDS = [
    "怎么算", "怎么计算", "是什么意思", "什么意思",
    "规则", "公式", "如何计算", "如何算",
]

_SHORT_FOLLOWUP = [
    "为什么", "那今天呢", "展开说说", "明细呢",
    "这个产品明细", "详细说说", "多说点",
    "还有吗", "继续", "然后呢",
]

_COMPLEX_KEYWORDS = [
    "为什么", "原因", "分析", "对比", "趋势",
    "异常", "风险", "建议", "变化", "下降",
    "增长", "连续", "综合", "帮我看看", "是否正常",
    "明细原因", "排查", "诊断",
]


def route_question(
    question: str,
    conversation_context: list[dict] | None = None,
) -> dict:
    """Route a user question to the appropriate processing mode.

    Returns:
      {"mode": "reject|rule|template|free_sql|agent",
       "reason": "...",
       "confidence": 0.0}
    """
    q = question.strip()

    # ── 1. Modification requests → reject ──
    if is_modification_request(q):
        return {
            "mode": "reject",
            "reason": "修改类请求，当前仅支持查询和分析",
            "confidence": 0.99,
        }

    # ── 2. Rule explanation → rule ──
    if any(kw in q for kw in _RULE_KEYWORDS):
        return {
            "mode": "rule",
            "reason": "用户询问业务规则/公式/字段含义",
            "confidence": 0.95,
        }

    # ── 3. Short follow-up → agent (needs context) ──
    is_short = len(q) <= 10 and any(kw in q for kw in _SHORT_FOLLOWUP)
    if is_short:
        if conversation_context:
            return {
                "mode": "agent",
                "reason": "短追问，结合上下文进行多步分析",
                "confidence": 0.90,
            }
        else:
            return {
                "mode": "agent",
                "reason": "缺少上下文，短追问无法独立回答，建议先提供完整问题",
                "confidence": 0.60,
            }

    # ── 4. Template match → template ──
    intent = quick_intent_match(q)
    if intent and intent.get("confidence", 0) >= 0.90:
        # Only route to template if it's not business_rule_explain (handled in step 2)
        if intent.get("intent") != "business_rule_explain":
            return {
                "mode": "template",
                "reason": f"高置信匹配模板: {intent.get('intent')}",
                "confidence": intent.get("confidence", 0.90),
            }

    # ── 5. Complex analysis → agent ──
    if any(kw in q for kw in _COMPLEX_KEYWORDS):
        return {
            "mode": "agent",
            "reason": "问题涉及分析/原因/对比/趋势，需要多步查询",
            "confidence": 0.85,
        }

    # ── 6. Default → free_sql ──
    return {
        "mode": "free_sql",
        "reason": "单步查询，一条 SQL 可解决",
        "confidence": 0.70,
    }
