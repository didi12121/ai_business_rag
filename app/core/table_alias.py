"""Standard table aliases for SQL generation."""

ALIAS_MAP = {
    "ad_product_record":   "apr",
    "ad_product_info":     "api",
    "ad_factory_info":     "afi",
    "ad_raw_record":       "arr",
    "ad_month_inventory":  "ami",
    "ad_order_info":       "aoi",
    "ad_order_item":       "aoitem",
    "ad_product_parts":    "app",
}


def get_table_alias(table_name: str) -> str:
    return ALIAS_MAP.get(table_name, table_name[:3])


def build_alias_prompt_section() -> str:
    lines = ["=== 表别名规范（必须使用，不要自创别名）===", ""]
    for table, alias in ALIAS_MAP.items():
        lines.append(f"  {table} → {alias}")
    lines.append("")
    lines.append("例如：FROM ad_product_record apr JOIN ad_product_info api ON apr.product_info_id = api.ad_product_info_id")
    lines.append("")
    return "\n".join(lines)
