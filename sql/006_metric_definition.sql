-- ============================================================
-- 业务指标定义
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_metric_definition (
  id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  metric_code VARCHAR(100) NOT NULL COMMENT '指标编码',
  metric_name VARCHAR(100) NOT NULL COMMENT '指标名称',
  description TEXT COMMENT '指标说明',
  sql_expression TEXT NOT NULL COMMENT '单行SQL表达式',
  aggregate_expression TEXT DEFAULT NULL COMMENT '聚合SQL表达式',
  required_tables VARCHAR(500) DEFAULT NULL COMMENT '需要的表及别名',
  required_fields VARCHAR(1000) DEFAULT NULL COMMENT '需要的字段',
  example_question TEXT DEFAULT NULL COMMENT '示例问题',
  enabled TINYINT DEFAULT 1 COMMENT '是否启用',
  create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_metric_code (metric_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI业务指标定义';

-- ============================================================
-- 1. shipment_amount：出货折算金额
-- ============================================================
-- 公式：出库重量 × 单位换算系数 ÷ 产品单重 × 产品单价
-- is_kg=1（KG单位）时换算系数=1000，否则（斤）换算系数=500

INSERT INTO ai_metric_definition
(metric_code, metric_name, description, sql_expression, aggregate_expression, required_tables, required_fields, example_question, enabled)
VALUES
(
  'shipment_amount',
  '出货折算金额',
  '出货折算金额：按出库重量、单位换算系数、产品单重、产品单价计算。is_kg=1（KG单位）时换算系数=1000，否则（斤）=500。公式：出库重量 × 换算系数 ÷ 产品单重 × 产品单价。',
  'apr.weight * CASE WHEN afi.is_kg = 1 THEN 1000 ELSE 500 END / NULLIF(api.weight, 0) * api.unit_price',
  'SUM(apr.weight * CASE WHEN afi.is_kg = 1 THEN 1000 ELSE 500 END / NULLIF(api.weight, 0) * api.unit_price)',
  'ad_product_record apr, ad_product_info api, ad_factory_info afi',
  'apr.weight, afi.is_kg, api.weight, api.unit_price',
  '上个月哪个产品出货金额最高？产品出货金额排行榜？上个月壮森出货金额是多少？',
  1
)
ON DUPLICATE KEY UPDATE
metric_name = VALUES(metric_name),
description = VALUES(description),
sql_expression = VALUES(sql_expression),
aggregate_expression = VALUES(aggregate_expression),
required_tables = VALUES(required_tables),
required_fields = VALUES(required_fields),
example_question = VALUES(example_question),
enabled = VALUES(enabled),
update_time = NOW();

-- ============================================================
-- 2. record_amount：普通记录金额
-- ============================================================
-- 公式：数量 × 单价
-- 适用于订单金额、明细金额、用户明确要求"数量乘单价"口径的场景。

INSERT INTO ai_metric_definition
(metric_code, metric_name, description, sql_expression, aggregate_expression, required_tables, required_fields, example_question, enabled)
VALUES
(
  'record_amount',
  '普通记录金额',
  '普通记录金额：按数量 × 产品单价计算。适用于订单金额、明细金额或用户明确要求数量乘单价口径的场景。不适用于出货折算金额场景。',
  'apr.kuang_num * api.unit_price',
  'SUM(apr.kuang_num * api.unit_price)',
  'ad_product_record apr, ad_product_info api',
  'apr.kuang_num, api.unit_price',
  '订单金额最高的是哪个？明细金额前10？数量乘单价算出来最高的是哪个？',
  1
)
ON DUPLICATE KEY UPDATE
metric_name = VALUES(metric_name),
description = VALUES(description),
sql_expression = VALUES(sql_expression),
aggregate_expression = VALUES(aggregate_expression),
required_tables = VALUES(required_tables),
required_fields = VALUES(required_fields),
example_question = VALUES(example_question),
enabled = VALUES(enabled),
update_time = NOW();

-- ============================================================
-- 业务规则
-- ============================================================

-- 规则10：出货金额计算规则（修正版）
INSERT INTO ai_business_rule
(id, rule_name, rule_type, rule_content, related_tables, priority, enabled)
VALUES
(10, '出货金额计算规则', 'metric',
'出货折算金额不是直接取记录表金额字段，而是按公式计算：出货折算金额 = 出库重量 × 单位换算系数 ÷ 产品单重 × 产品单价。单位换算系数由厂家 is_kg 决定：ad_factory_info.is_kg=1（KG单位）时系数为1000，否则（斤）为500。SQL单行表达式：apr.weight * CASE WHEN afi.is_kg = 1 THEN 1000 ELSE 500 END / NULLIF(api.weight, 0) * api.unit_price。聚合表达式：SUM(apr.weight * CASE WHEN afi.is_kg = 1 THEN 1000 ELSE 500 END / NULLIF(api.weight, 0) * api.unit_price)',
'ad_product_record,ad_product_info,ad_factory_info',
100, 1)
ON DUPLICATE KEY UPDATE
rule_content = VALUES(rule_content),
related_tables = VALUES(related_tables),
priority = VALUES(priority),
enabled = VALUES(enabled);

-- 规则11：普通记录金额计算规则
INSERT INTO ai_business_rule
(id, rule_name, rule_type, rule_content, related_tables, priority, enabled)
VALUES
(11, '普通记录金额计算规则', 'metric',
'普通记录金额按数量 × 产品单价计算。适用于订单金额、明细金额或用户明确要求数量乘单价口径的场景。不要与出货折算金额混淆。SQL单行表达式：apr.kuang_num * api.unit_price。聚合表达式：SUM(apr.kuang_num * api.unit_price)',
'ad_product_record,ad_product_info',
90, 1)
ON DUPLICATE KEY UPDATE
rule_content = VALUES(rule_content),
related_tables = VALUES(related_tables),
priority = VALUES(priority),
enabled = VALUES(enabled);
