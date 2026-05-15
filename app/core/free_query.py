import json
import re
from datetime import datetime

from app.llm.openai_compatible import create_llm_client
from app.core.sys_config import get_ai_config
from app.core.business_context import load_table_schemas, load_field_schemas, load_business_rules


FREE_SQL_PROMPT = """
你是一个 MySQL SELECT 查询生成助手。根据用户问题和真实表结构生成只读 SQL。

【重要】当前真实日期：{current_date}。你训练数据的日期是过时的，必须以这里提供的日期为准。

当前月份 = {current_date} 所在月第一天到下月第一天
上个月 = {current_date} 上一个自然月

=== 可查询表清单（只列出 allow_query = 1 的表） ===

{table_schemas}

=== 表别名规范 ===

{table_aliases}

=== 表关系（JOIN 必须以此为准） ===

{table_relations}

=== 业务指标定义 ===

{metric_definitions}

=== 业务规则 ===
{business_rules}

=== 严格限制 ===

1. 只能生成 SELECT 或 WITH。
2. 禁止 INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/REPLACE/CALL/EXEC/LOAD DATA/GRANT/REVOKE。
3. 禁止多语句 SQL。
4. 禁止 SELECT *，必须显式列出字段。
5. 只能访问上面可查询表清单中的表。
6. 不要使用不存在的表或字段。
7. 如果表有 del_flag 字段，必须加 del_flag = '0'。
8. 时间范围使用闭开区间：record_time >= 'yyyy-MM-dd 00:00:00' AND record_time < 'yyyy-MM-dd 00:00:00'。
9. 必须加 LIMIT，默认 LIMIT {max_rows}。
10. 如果问题涉及修改/删除，canGenerate = false。
11. 如果缺少必要字段无法生成可靠 SQL，canGenerate = false。
12. "出货金额"必须使用指标定义中的 shipment_amount 公式，禁止用 total_price/amount 等不存在字段。
13. "金额最高"排序必须用 amount 别名，禁止按 total_weight 排序。

=== 实体消歧 ===
- 带"圈/厂/行/公司/商行/实业/塑胶"后缀的是厂家名 → factory_name
- 带字母数字编码的是产品名/型号 → ad_product_name
- 纯颜色词才是 color 字段；"黄ABS"是产品名不是颜色
- 不确定时用 LIKE 模糊匹配所有可能字段，或返回 canGenerate=false

=== 用户问题 ===
{question}

=== 返回格式 ===

严格返回 JSON，不要 Markdown，不要解释文字：

{{
  "canGenerate": true,
  "sql": "SELECT ... LIMIT {max_rows}",
  "params": {{}},
  "reason": "为什么这样查询",
  "usedTables": ["table1"],
  "riskLevel": "low/medium/high"
}}

如果无法生成：

{{
  "canGenerate": false,
  "sql": null,
  "params": {{}},
  "reason": "原因",
  "usedTables": [],
  "riskLevel": "high"
}}

riskLevel 判断：
- low: 简单单表查询
- medium: 多表 JOIN 或聚合
- high: 复杂子查询、大范围扫描

请返回 JSON：
"""


def _build_schema_text() -> str:
    schemas = load_table_schemas()
    fields = load_field_schemas()
    lines = []
    for t in schemas:
        allow = t.get("allow_query")
        if not allow or int(allow) != 1:
            continue
        tname = t["table_name"]
        bname = t.get("business_name", "")
        desc = t.get("description", "")
        lines.append(f"[{tname}] {bname} — {desc}")
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
            lines.append(f"  {fname}: {fbiz} — {fdesc}{extra}")
    return "\n".join(lines)


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


async def generate_free_sql(question: str) -> dict:
    config = get_ai_config()
    schema_text = _build_schema_text()
    business_rules = load_business_rules()
    rules_text = json.dumps(
        [r.get("rule_content", "") for r in business_rules],
        ensure_ascii=False,
    )
    from app.core.metric_context import build_metric_prompt_section
    metric_section = build_metric_prompt_section()
    from app.core.relation_context import build_relation_prompt_section
    relation_section = build_relation_prompt_section()
    from app.core.table_alias import build_alias_prompt_section
    alias_section = build_alias_prompt_section()
    current_date = datetime.now().strftime("%Y-%m-%d")

    prompt = FREE_SQL_PROMPT.format(
        current_date=current_date,
        max_rows=config.get("free_sql.max_rows", 200),
        table_schemas=schema_text,
        table_relations=relation_section or "无",
        table_aliases=alias_section,
        metric_definitions=metric_section or "无",
        business_rules=rules_text,
        question=question,
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
            "reason": f"LLM 返回无法解析: {raw[:300]}",
            "usedTables": [],
            "riskLevel": "high",
        }

    sql = result.get("sql")
    # Enforce del_flag = '0'
    if sql and result.get("canGenerate"):
        from app.core.sql_enhancer import enforce_del_flag
        sql = enforce_del_flag(sql)

    return {
        "canGenerate": result.get("canGenerate", False),
        "sql": sql,
        "params": result.get("params", {}),
        "reason": result.get("reason", ""),
        "usedTables": result.get("usedTables", []),
        "riskLevel": result.get("riskLevel", "high"),
    }
