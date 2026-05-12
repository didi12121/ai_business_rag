-- ============================================================
-- AI 业务问答模块：基础 SQL（DDL + 初始化数据 + 查询模板）
-- ============================================================

-- ============================================================
-- Part 1: AI 元数据表 DDL
-- ============================================================

-- 1.1 表说明表
CREATE TABLE IF NOT EXISTS `ai_table_schema` (
  `id` BIGINT NOT NULL PRIMARY KEY,
  `table_name` VARCHAR(100) NOT NULL COMMENT '数据库表名',
  `business_name` VARCHAR(100) NOT NULL COMMENT '业务名称',
  `description` TEXT COMMENT '表的业务说明',
  `example_question` TEXT COMMENT '这个表可以回答的问题',
  `enabled` TINYINT DEFAULT 1 COMMENT '是否启用：1启用，0停用',
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_table_name` (`table_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI表语义说明';

-- 1.2 字段说明表
CREATE TABLE IF NOT EXISTS `ai_field_schema` (
  `id` BIGINT NOT NULL PRIMARY KEY,
  `table_name` VARCHAR(100) NOT NULL COMMENT '数据库表名',
  `field_name` VARCHAR(100) NOT NULL COMMENT '字段名',
  `business_name` VARCHAR(100) NOT NULL COMMENT '字段中文含义',
  `description` TEXT COMMENT '字段说明',
  `value_mapping` JSON COMMENT '枚举值说明',
  `example_value` VARCHAR(255) COMMENT '示例值',
  `enabled` TINYINT DEFAULT 1 COMMENT '是否启用',
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_table_field` (`table_name`, `field_name`),
  KEY `idx_table_name` (`table_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI字段语义说明';

-- 1.3 业务规则表
CREATE TABLE IF NOT EXISTS `ai_business_rule` (
  `id` BIGINT NOT NULL PRIMARY KEY,
  `rule_name` VARCHAR(100) NOT NULL COMMENT '规则名称',
  `rule_type` VARCHAR(50) COMMENT '规则类型：unit/inventory/month_report/query/filter',
  `rule_content` TEXT NOT NULL COMMENT '规则内容',
  `related_tables` VARCHAR(500) COMMENT '相关表，逗号分隔',
  `priority` INT DEFAULT 0 COMMENT '优先级，越大越重要',
  `enabled` TINYINT DEFAULT 1 COMMENT '是否启用',
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY `idx_rule_type` (`rule_type`),
  KEY `idx_enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI业务规则';

-- 1.4 查询模板表
CREATE TABLE IF NOT EXISTS `ai_query_template` (
  `id` BIGINT NOT NULL PRIMARY KEY,
  `template_name` VARCHAR(100) NOT NULL COMMENT '模板名称',
  `intent_code` VARCHAR(100) NOT NULL COMMENT '意图编码',
  `description` TEXT COMMENT '模板说明',
  `sql_template` TEXT NOT NULL COMMENT 'SQL模板，使用 Jinja2 变量语法',
  `param_schema` JSON COMMENT '参数说明',
  `example_question` TEXT COMMENT '示例问题',
  `result_description` TEXT COMMENT '结果字段说明',
  `enabled` TINYINT DEFAULT 1 COMMENT '是否启用',
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_intent_code` (`intent_code`),
  KEY `idx_enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI查询模板';

-- 1.5 聊天记录表
CREATE TABLE IF NOT EXISTS `ai_chat_log` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `session_id` VARCHAR(100) DEFAULT NULL COMMENT '会话ID',
  `user_id` VARCHAR(100) DEFAULT NULL COMMENT '用户ID，可选',
  `question` TEXT NOT NULL COMMENT '用户问题',
  `intent_code` VARCHAR(100) DEFAULT NULL COMMENT '识别出的意图',
  `intent_result` JSON COMMENT '完整意图识别结果',
  `params_json` JSON COMMENT '参数',
  `sql_text` TEXT COMMENT '实际执行SQL',
  `sql_rows_json` JSON COMMENT 'SQL结果，注意控制长度',
  `answer` LONGTEXT COMMENT 'AI回答',
  `success` TINYINT DEFAULT 1 COMMENT '是否成功',
  `error_msg` TEXT COMMENT '错误信息',
  `model_name` VARCHAR(100) DEFAULT NULL COMMENT '模型名称',
  `duration_ms` INT DEFAULT NULL COMMENT '耗时毫秒',
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_session_id` (`session_id`),
  KEY `idx_intent_code` (`intent_code`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI问答记录';


-- ============================================================
-- Part 2: 初始化业务语义数据 —— ai_table_schema
-- ============================================================

INSERT INTO ai_table_schema
(id, table_name, business_name, description, example_question, enabled)
VALUES
(1, 'ad_factory_info', '厂家基础信息',
'保存厂家基础信息。所有业务查询默认过滤 del_flag = 0。is_kg 字段决定产品重量单位，1 表示 KG，0 表示斤。',
'有哪些厂家？铭泰这个厂家是否存在？某厂家使用什么单位？',
1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
example_question = VALUES(example_question),
enabled = VALUES(enabled);

INSERT INTO ai_table_schema
(id, table_name, business_name, description, example_question, enabled)
VALUES
(2, 'ad_product_info', '产品基础信息',
'保存产品名称、颜色、单重、单价、原料编码、所属厂家等信息。查询产品基础资料、价格、重量、原料时使用。所有业务查询默认过滤 del_flag = 0。',
'某厂家有哪些产品？黄ABS单价是多少？某产品使用什么原料？',
1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
example_question = VALUES(example_question),
enabled = VALUES(enabled);

INSERT INTO ai_table_schema
(id, table_name, business_name, description, example_question, enabled)
VALUES
(3, 'ad_product_record', '产品出货记录',
'保存产品出货或产品记录。通常需要关联 ad_product_info 查询产品名称、颜色、原料、厂家。所有业务查询默认过滤 del_flag = 0。',
'这个月某产品出了多少？某厂家本月出货金额是多少？ABS产品出货量是多少？',
1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
example_question = VALUES(example_question),
enabled = VALUES(enabled);

INSERT INTO ai_table_schema
(id, table_name, business_name, description, example_question, enabled)
VALUES
(4, 'ad_raw_record', '原料记录',
'保存原料进料和上月存料记录。raw_type = 0 表示进料，raw_type = 1 表示上月存料。所有业务查询默认过滤 del_flag = 0。',
'这个月某原料进了多少？上月存料是多少？',
1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
example_question = VALUES(example_question),
enabled = VALUES(enabled);

INSERT INTO ai_table_schema
(id, table_name, business_name, description, example_question, enabled)
VALUES
(5, 'ad_month_inventory', '月度原料库存',
'保存月度原料库存统计结果，包括上月存料、本月进料、本月出料、损耗和本月结余库存。所有业务查询默认过滤 del_flag = 0。',
'这个月某原料还有多少库存？哪些原料库存为负？库存是怎么算的？',
1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
example_question = VALUES(example_question),
enabled = VALUES(enabled);


-- ============================================================
-- Part 3: 初始化业务规则 —— ai_business_rule
-- ============================================================

INSERT INTO ai_business_rule
(id, rule_name, rule_type, rule_content, related_tables, priority, enabled)
VALUES
(1, '有效数据过滤规则', 'filter',
'所有业务表如果存在 del_flag 字段，查询时默认只查询 del_flag = 0 的数据。除非用户明确要求查看已删除数据，否则禁止查询 del_flag != 0 的记录。',
'ad_factory_info,ad_product_info,ad_product_record,ad_raw_record,ad_month_inventory',
100, 1)
ON DUPLICATE KEY UPDATE
rule_content = VALUES(rule_content),
related_tables = VALUES(related_tables),
priority = VALUES(priority),
enabled = VALUES(enabled);

INSERT INTO ai_business_rule
(id, rule_name, rule_type, rule_content, related_tables, priority, enabled)
VALUES
(2, '产品单位规则', 'unit',
'ad_factory_info.is_kg = 1 时，产品重量单位按 KG 处理；ad_factory_info.is_kg = 0 时，产品重量单位按 斤 处理。回答中如果能关联厂家，需要说明单位。',
'ad_factory_info,ad_product_info',
90, 1)
ON DUPLICATE KEY UPDATE
rule_content = VALUES(rule_content),
related_tables = VALUES(related_tables),
priority = VALUES(priority),
enabled = VALUES(enabled);

INSERT INTO ai_business_rule
(id, rule_name, rule_type, rule_content, related_tables, priority, enabled)
VALUES
(3, '原料库存计算规则', 'inventory',
'月末库存 = 上月存料 + 本月进料 - 本月出料 - 损耗。损耗 = 本月出料 * 1%。当本月出料为 0 时，损耗为 0。库存允许出现负数。',
'ad_raw_record,ad_product_record,ad_product_info,ad_month_inventory',
100, 1)
ON DUPLICATE KEY UPDATE
rule_content = VALUES(rule_content),
related_tables = VALUES(related_tables),
priority = VALUES(priority),
enabled = VALUES(enabled);

INSERT INTO ai_business_rule
(id, rule_name, rule_type, rule_content, related_tables, priority, enabled)
VALUES
(4, '时间范围规则', 'query',
'用户说"这个月"时，指当前日期所在自然月的第一天到下个月第一天之前；用户说"上个月"时，指当前日期上一个自然月；用户说"今天"时，指当前日期当天。',
'ad_product_record,ad_raw_record,ad_month_inventory',
80, 1)
ON DUPLICATE KEY UPDATE
rule_content = VALUES(rule_content),
related_tables = VALUES(related_tables),
priority = VALUES(priority),
enabled = VALUES(enabled);


-- ============================================================
-- Part 4: 初始化查询模板 —— ai_query_template
-- ============================================================

-- 5.1 查询厂家产品列表
INSERT INTO ai_query_template
(id, template_name, intent_code, description, sql_template, param_schema, example_question, result_description, enabled)
VALUES
(1,
'查询厂家产品列表',
'factory_product_list',
'根据厂家名称查询该厂家下的产品列表',
'SELECT
   afi.factory_info_id,
   afi.factory_name,
   CASE WHEN afi.is_kg = 1 THEN ''KG'' ELSE ''斤'' END AS weight_unit,
   api.ad_product_info_id,
   api.ad_product_name,
   api.color,
   api.raw_materials_code,
   api.weight,
   api.unit_price
 FROM ad_product_info api
 JOIN ad_factory_info afi ON api.ad_factory_info_id = afi.factory_info_id
 WHERE api.del_flag = ''0''
   AND afi.del_flag = ''0''
   {% if factoryName %}
   AND afi.factory_name LIKE CONCAT(''%'', :factoryName, ''%'')
   {% endif %}
 ORDER BY api.ad_product_name, api.color
 LIMIT 200',
'{"factoryName": {"type": "string", "required": true, "description": "厂家名称，支持模糊匹配"}}',
'铭泰有哪些产品？某某厂有哪些产品？',
'返回厂家名称、产品名称、颜色、原料、单重、单价和重量单位。',
1)
ON DUPLICATE KEY UPDATE
sql_template = VALUES(sql_template),
param_schema = VALUES(param_schema),
example_question = VALUES(example_question),
result_description = VALUES(result_description),
enabled = VALUES(enabled);

-- 5.2 查询产品基础信息
INSERT INTO ai_query_template
(id, template_name, intent_code, description, sql_template, param_schema, example_question, result_description, enabled)
VALUES
(2,
'查询产品基础信息',
'product_info_query',
'根据产品名称、颜色、厂家名称查询产品基础信息',
'SELECT
   api.ad_product_info_id,
   api.ad_product_name,
   api.color,
   api.raw_materials_code,
   api.weight,
   api.unit_price,
   afi.factory_name,
   CASE WHEN afi.is_kg = 1 THEN ''KG'' ELSE ''斤'' END AS weight_unit
 FROM ad_product_info api
 LEFT JOIN ad_factory_info afi ON api.ad_factory_info_id = afi.factory_info_id
 WHERE api.del_flag = ''0''
   AND (afi.factory_info_id IS NULL OR afi.del_flag = ''0'')
   {% if productName %}
   AND api.ad_product_name LIKE CONCAT(''%'', :productName, ''%'')
   {% endif %}
   {% if color %}
   AND api.color LIKE CONCAT(''%'', :color, ''%'')
   {% endif %}
   {% if factoryName %}
   AND afi.factory_name LIKE CONCAT(''%'', :factoryName, ''%'')
   {% endif %}
 ORDER BY afi.factory_name, api.ad_product_name, api.color
 LIMIT 200',
'{"productName": {"type": "string", "required": false, "description": "产品名称"}, "color": {"type": "string", "required": false, "description": "颜色"}, "factoryName": {"type": "string", "required": false, "description": "厂家名称"}}',
'黄ABS单价是多少？红色产品有哪些？铭泰的黄ABS信息？',
'返回产品名称、颜色、原料、单重、单价、厂家和单位。',
1)
ON DUPLICATE KEY UPDATE
sql_template = VALUES(sql_template),
param_schema = VALUES(param_schema),
example_question = VALUES(example_question),
result_description = VALUES(result_description),
enabled = VALUES(enabled);

-- 5.3 查询产品出货汇总
INSERT INTO ai_query_template
(id, template_name, intent_code, description, sql_template, param_schema, example_question, result_description, enabled)
VALUES
(3,
'查询产品出货汇总',
'product_out_summary',
'按时间范围、产品名称、厂家、原料汇总产品出货数量、重量和金额',
'SELECT
   afi.factory_name,
   api.ad_product_name,
   api.color,
   api.raw_materials_code,
   COUNT(*) AS record_count,
   COALESCE(SUM(apr.num), 0) AS total_num,
   COALESCE(SUM(apr.weight), 0) AS total_weight,
   COALESCE(SUM(apr.total_price), 0) AS total_price,
   MIN(apr.record_time) AS first_record_time,
   MAX(apr.record_time) AS last_record_time
 FROM ad_product_record apr
 JOIN ad_product_info api ON apr.ad_product_info_id = api.ad_product_info_id
 LEFT JOIN ad_factory_info afi ON api.ad_factory_info_id = afi.factory_info_id
 WHERE apr.del_flag = ''0''
   AND api.del_flag = ''0''
   AND (afi.factory_info_id IS NULL OR afi.del_flag = ''0'')
   {% if startDate %}
   AND apr.record_time >= :startDate
   {% endif %}
   {% if endDate %}
   AND apr.record_time < :endDate
   {% endif %}
   {% if productName %}
   AND api.ad_product_name LIKE CONCAT(''%'', :productName, ''%'')
   {% endif %}
   {% if factoryName %}
   AND afi.factory_name LIKE CONCAT(''%'', :factoryName, ''%'')
   {% endif %}
   {% if rawName %}
   AND api.raw_materials_code LIKE CONCAT(''%'', :rawName, ''%'')
   {% endif %}
 GROUP BY afi.factory_name, api.ad_product_name, api.color, api.raw_materials_code
 ORDER BY total_price DESC, total_weight DESC
 LIMIT 200',
'{"startDate": {"type": "datetime", "required": false, "description": "开始时间，闭区间"}, "endDate": {"type": "datetime", "required": false, "description": "结束时间，开区间"}, "productName": {"type": "string", "required": false, "description": "产品名称"}, "factoryName": {"type": "string", "required": false, "description": "厂家名称"}, "rawName": {"type": "string", "required": false, "description": "原料名称"}}',
'这个月黄ABS出了多少？铭泰本月出货金额是多少？ABS原料相关产品出了多少？',
'按厂家、产品、颜色、原料汇总出货记录数、数量、重量、金额。',
1)
ON DUPLICATE KEY UPDATE
sql_template = VALUES(sql_template),
param_schema = VALUES(param_schema),
example_question = VALUES(example_question),
result_description = VALUES(result_description),
enabled = VALUES(enabled);

-- 5.4 查询原料使用汇总
INSERT INTO ai_query_template
(id, template_name, intent_code, description, sql_template, param_schema, example_question, result_description, enabled)
VALUES
(4,
'查询原料使用汇总',
'raw_material_usage',
'根据产品出货记录和产品原料字段，汇总某时间范围内原料出料重量',
'SELECT
   api.raw_materials_code AS raw_name,
   COUNT(*) AS record_count,
   COALESCE(SUM(apr.weight), 0) AS total_out_weight,
   COALESCE(SUM(apr.weight), 0) * 0.01 AS estimated_loss,
   COALESCE(SUM(apr.weight), 0) * 1.01 AS total_with_loss
 FROM ad_product_record apr
 JOIN ad_product_info api ON apr.ad_product_info_id = api.ad_product_info_id
 LEFT JOIN ad_factory_info afi ON api.ad_factory_info_id = afi.factory_info_id
 WHERE apr.del_flag = ''0''
   AND api.del_flag = ''0''
   AND (afi.factory_info_id IS NULL OR afi.del_flag = ''0'')
   AND api.raw_materials_code IS NOT NULL
   AND api.raw_materials_code <> ''''
   {% if startDate %}
   AND apr.record_time >= :startDate
   {% endif %}
   {% if endDate %}
   AND apr.record_time < :endDate
   {% endif %}
   {% if rawName %}
   AND api.raw_materials_code LIKE CONCAT(''%'', :rawName, ''%'')
   {% endif %}
   {% if factoryName %}
   AND afi.factory_name LIKE CONCAT(''%'', :factoryName, ''%'')
   {% endif %}
 GROUP BY api.raw_materials_code
 ORDER BY total_out_weight DESC
 LIMIT 200',
'{"startDate": {"type": "datetime", "required": false, "description": "开始时间"}, "endDate": {"type": "datetime", "required": false, "description": "结束时间"}, "rawName": {"type": "string", "required": false, "description": "原料名称"}, "factoryName": {"type": "string", "required": false, "description": "厂家名称"}}',
'这个月ABS用了多少？本月原料消耗排行？铭泰相关产品用了哪些原料？',
'按原料汇总本月出料重量、估算损耗和含损耗总量。',
1)
ON DUPLICATE KEY UPDATE
sql_template = VALUES(sql_template),
param_schema = VALUES(param_schema),
example_question = VALUES(example_question),
result_description = VALUES(result_description),
enabled = VALUES(enabled);

-- 5.5 查询月度库存
INSERT INTO ai_query_template
(id, template_name, intent_code, description, sql_template, param_schema, example_question, result_description, enabled)
VALUES
(5,
'查询月度原料库存',
'monthly_inventory_query',
'根据月份和原料名称查询月度库存数据',
'SELECT
   month_str,
   raw_name,
   last_month_weight,
   this_month_weight_in,
   this_month_weight_out,
   loss,
   this_month_weight
 FROM ad_month_inventory
 WHERE del_flag = ''0''
   {% if monthStr %}
   AND month_str = :monthStr
   {% endif %}
   {% if rawName %}
   AND raw_name LIKE CONCAT(''%'', :rawName, ''%'')
   {% endif %}
   {% if onlyNegative %}
   AND this_month_weight < 0
   {% endif %}
 ORDER BY this_month_weight ASC
 LIMIT 200',
'{"monthStr": {"type": "string", "required": false, "description": "月份，格式 yyyy-MM"}, "rawName": {"type": "string", "required": false, "description": "原料名称"}, "onlyNegative": {"type": "boolean", "required": false, "description": "是否只查询负库存"}}',
'这个月ABS还有多少库存？2026-05哪些原料库存为负？本月库存最少的原料有哪些？',
'返回月份、原料、上月存料、本月进料、本月出料、损耗和本月结余库存。',
1)
ON DUPLICATE KEY UPDATE
sql_template = VALUES(sql_template),
param_schema = VALUES(param_schema),
example_question = VALUES(example_question),
result_description = VALUES(result_description),
enabled = VALUES(enabled);
