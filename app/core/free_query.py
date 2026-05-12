import json
import re
from datetime import datetime

from app.llm.openai_compatible import create_llm_client
from app.core.business_context import load_table_schemas, load_field_schemas, load_business_rules


FREE_QUERY_PROMPT = """
你是一个 MySQL 查询生成助手。根据用户问题和可用表结构，生成一条只读 SELECT 语句。

【重要】当前真实日期：{current_date}。你训练数据的日期是过时的，必须以这里提供的日期为准。

可用业务表及字段：

{table_schemas_json}

业务规则：
{business_rules_json}

要求：
1. 只生成 SELECT 或 WITH 开头的查询。
2. 所有表默认过滤 del_flag = '0'。
3. 使用 JOIN 关联表时，注意外键关系（通常 xxx_id 字段关联对应表的 id）。
4. "这个月/本月" = {current_date} 所在月的第一天到下月第一天。
   "上个月" = {current_date} 上一个自然月。
   "今天" = {current_date}。
   "昨天" = {current_date} 前一天。
   "明天" = {current_date} 后一天（查询时注意无未来数据）。
5. 如果用户要删除/修改，返回空。
6. 只返回 SQL，不要解释，不要 Markdown 代码块。

用户问题：{question}

请生成 SQL：
"""


def _relative_dates() -> str:
    return datetime.now().strftime("%Y-%m-%d")


async def free_query_sql(question: str) -> str | None:
    table_schemas = load_table_schemas()
    field_schemas = load_field_schemas()
    business_rules = load_business_rules()

    # Build compact schema description
    schema_lines = []
    for t in table_schemas:
        tname = t["table_name"]
        tdesc = t.get("description", "")
        fields = [f for f in field_schemas if f["table_name"] == tname]
        field_lines = []
        for f in fields:
            fname = f["field_name"]
            fdesc = f.get("description", "") or f.get("business_name", "")
            vmap = f.get("value_mapping")
            if isinstance(vmap, str):
                try:
                    vmap = json.loads(vmap)
                except (json.JSONDecodeError, TypeError):
                    vmap = None
            extra = ""
            if vmap and isinstance(vmap, dict):
                extra = " 枚举: " + ", ".join(f"{k}={v}" for k, v in vmap.items())
            field_lines.append(f"    {fname}: {fdesc}{extra}")
        schema_lines.append(f"  [{tname}] {tdesc}\n" + "\n".join(field_lines))

    table_schemas_json = "\n".join(schema_lines)
    business_rules_json = json.dumps(
        [r.get("rule_content", "") for r in business_rules],
        ensure_ascii=False,
    )

    prompt = FREE_QUERY_PROMPT.format(
        current_date=_relative_dates(),
        table_schemas_json=table_schemas_json,
        business_rules_json=business_rules_json,
        question=question,
    )

    client = create_llm_client()
    raw = await client.chat([{"role": "user", "content": prompt}])

    # Extract SQL from response (strip markdown code fences if any)
    sql = raw.strip()
    m = re.search(r"```(?:sql)?\s*(.*?)```", sql, re.DOTALL | re.IGNORECASE)
    if m:
        sql = m.group(1).strip()

    # Basic sanity: must start with SELECT or WITH
    lower = sql.lower()
    if not (lower.startswith("select") or lower.startswith("with")):
        return None

    return sql
