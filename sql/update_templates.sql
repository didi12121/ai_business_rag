-- ============================================================
-- 根据真实 DDL 修正查询模板和业务规则
-- ============================================================

-- ============================================================
-- 修正 ai_query_template
-- ============================================================

-- 1. factory_product_list（JOIN 条件微调：ad_product_info.del_flag 可能为 '2'）
UPDATE ai_query_template SET
sql_template = 'SELECT
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
 WHERE api.del_flag IN (''0'', ''2'')
   AND afi.del_flag = ''0''
   {% if factoryName %}
   AND afi.factory_name LIKE CONCAT(''%'', :factoryName, ''%'')
   {% endif %}
 ORDER BY api.ad_product_name, api.color
 LIMIT 200'
WHERE intent_code = 'factory_product_list';

-- 2. product_info_query（微调 del_flag 条件）
UPDATE ai_query_template SET
sql_template = 'SELECT
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
 WHERE api.del_flag IN (''0'', ''2'')
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
 LIMIT 200'
WHERE intent_code = 'product_info_query';

-- 3. product_out_summary（字段名修正：product_info_id / kuang_num，移除不存在的 total_price）
UPDATE ai_query_template SET
sql_template = 'SELECT
   afi.factory_name,
   api.ad_product_name,
   api.color,
   api.raw_materials_code,
   COUNT(*) AS record_count,
   COALESCE(SUM(apr.kuang_num), 0) AS total_kuang_num,
   COALESCE(SUM(apr.weight), 0) AS total_weight,
   MIN(apr.record_time) AS first_record_time,
   MAX(apr.record_time) AS last_record_time
 FROM ad_product_record apr
 JOIN ad_product_info api ON apr.product_info_id = api.ad_product_info_id
 LEFT JOIN ad_factory_info afi ON apr.factory_info_id = afi.factory_info_id
 WHERE apr.del_flag = ''0''
   AND api.del_flag IN (''0'', ''2'')
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
 ORDER BY total_weight DESC
 LIMIT 200',
result_description = '按厂家、产品、颜色、原料汇总出货记录数、筐数和重量。'
WHERE intent_code = 'product_out_summary';

-- 4. raw_material_usage（字段名修正：product_info_id）
UPDATE ai_query_template SET
sql_template = 'SELECT
   api.raw_materials_code AS raw_name,
   COUNT(*) AS record_count,
   COALESCE(SUM(apr.weight), 0) AS total_out_weight,
   COALESCE(SUM(apr.weight), 0) * 0.01 AS estimated_loss,
   COALESCE(SUM(apr.weight), 0) * 1.01 AS total_with_loss
 FROM ad_product_record apr
 JOIN ad_product_info api ON apr.product_info_id = api.ad_product_info_id
 LEFT JOIN ad_factory_info afi ON apr.factory_info_id = afi.factory_info_id
 WHERE apr.del_flag = ''0''
   AND api.del_flag IN (''0'', ''2'')
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
 LIMIT 200'
WHERE intent_code = 'raw_material_usage';

-- 5. monthly_inventory_query（完全重写：真实表结构为 raw_materials_code / years / month / quantity）
UPDATE ai_query_template SET
sql_template = 'SELECT
   CONCAT(ami.years, ''-'', ami.month) AS month_str,
   ami.raw_materials_code,
   ami.quantity
 FROM ad_month_inventory ami
 WHERE ami.del_flag = ''0''
   {% if monthStr %}
   AND CONCAT(ami.years, ''-'', ami.month) = :monthStr
   {% endif %}
   {% if rawName %}
   AND ami.raw_materials_code LIKE CONCAT(''%'', :rawName, ''%'')
   {% endif %}
   {% if onlyNegative %}
   AND ami.quantity < 0
   {% endif %}
 ORDER BY ami.quantity ASC
 LIMIT 200',
result_description = '返回月份、原料编码和库存数量。'
WHERE intent_code = 'monthly_inventory_query';


-- ============================================================
-- 补充 ad_product_parts 表说明（如果不存在）
-- ============================================================

INSERT INTO ai_table_schema
(id, table_name, business_name, description, example_question, enabled)
VALUES
(6, 'ad_product_parts', '产品配件信息',
'保存产品配件信息，关联产品。配件有独立的名称、颜色、原料、重量。所有业务查询默认过滤 del_flag = 0。',
'某产品有哪些配件？配件的原料是什么？',
1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
example_question = VALUES(example_question),
enabled = VALUES(enabled);


-- ============================================================
-- 修正业务规则中的字段引用
-- ============================================================

UPDATE ai_business_rule SET
related_tables = 'ad_factory_info,ad_product_info,ad_product_parts,ad_product_record,ad_raw_record,ad_month_inventory'
WHERE id = 1;

UPDATE ai_business_rule SET
related_tables = 'ad_raw_record,ad_product_record,ad_product_info,ad_month_inventory'
WHERE id = 3;
