-- ============================================================
-- ai_field_schema 初始化数据（从 filed.csv 生成）
-- ============================================================

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(1, 'ad_factory_info', 'factory_info_id', '厂家id', '厂家id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(2, 'ad_factory_info', 'factory_name', '厂家名字', '厂家名字', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(3, 'ad_factory_info', 'print_type', '出库单使用的模板类型', '出库单使用的模板类型', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(4, 'ad_factory_info', 'is_kg', '是否使用kg', '汇总报表是否使用KG作为单位否则使用斤', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(5, 'ad_factory_info', 'use_new_export', '是否使用新模板', '是否使用新模板进行月度汇总', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(6, 'ad_product_info', 'ad_product_info_id', '产品id', '产品id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(7, 'ad_product_info', 'ad_factory_info_id', '产品所属工厂id', '产品所属工厂id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(8, 'ad_product_info', 'ad_product_name', '名称', '产品名称', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(9, 'ad_product_info', 'raw_materials_code', '产品所使用原料', '产品所使用原料', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(10, 'ad_product_info', 'weight', '产品重量', '产品重量', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(11, 'ad_product_info', 'unit_price', '单价', '产品单价', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(12, 'ad_product_info', 'color', '颜色', '', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(13, 'ad_product_parts', 'id', 'id', '胶件对应的id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(14, 'ad_product_parts', 'ad_product_info_id', '对应产品的id', '胶件对应产品的id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(15, 'ad_product_parts', 'parts_name', '名称', '胶件名称', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(16, 'ad_product_parts', 'ad_factory_info_id', '厂家id', '胶件所属厂家id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(17, 'ad_product_parts', 'raw_materials_code', '原料名称', '冗余字段，同产品原料名称', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(18, 'ad_product_parts', 'color', '颜色', '冗余字段，同产品原料颜色', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(19, 'ad_product_parts', 'img_base64', '图片', '胶件图片的base64', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(20, 'ad_product_parts', 'weight', '重量', '胶件的重量', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(21, 'ad_product_record', 'product_record_id', '主键id', '主键id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(22, 'ad_product_record', 'factory_info_id', '厂家id', '厂家id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(23, 'ad_product_record', 'product_info_id', '产品id', '产品id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(24, 'ad_product_record', 'record_time', '记录出库的时间', '记录出库的时间', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(25, 'ad_product_record', 'weight', '出库的重量', '记录出库的重量', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(26, 'ad_product_record', 'kuang_num', '框数', '使用周转筐的数量', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(27, 'ad_product_record', 'remark', '备注', '备注', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(28, 'ad_raw_record', 'id', '主键id', '主键id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(29, 'ad_raw_record', 'factory_info_id', '厂家id', '厂家id', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(30, 'ad_raw_record', 'raw_materials_code', '原料名称', '原料名称', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(31, 'ad_raw_record', 'num', '数量', '数量', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);

INSERT INTO ai_field_schema
(id, table_name, field_name, business_name, description, value_mapping, example_value, enabled)
VALUES
(32, 'ad_raw_record', 'time', '时间', '时间', NULL, NULL, 1)
ON DUPLICATE KEY UPDATE
business_name = VALUES(business_name),
description = VALUES(description),
value_mapping = VALUES(value_mapping),
example_value = VALUES(example_value),
enabled = VALUES(enabled);
