-- ============================================================
-- 表关系定义
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_table_relation (
  id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  from_table VARCHAR(100) NOT NULL,
  from_field VARCHAR(100) NOT NULL,
  to_table VARCHAR(100) NOT NULL,
  to_field VARCHAR(100) NOT NULL,
  relation_type VARCHAR(50) DEFAULT 'many_to_one',
  join_type VARCHAR(20) DEFAULT 'LEFT JOIN',
  description TEXT,
  enabled TINYINT DEFAULT 1,
  create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_from_table (from_table),
  KEY idx_to_table (to_table),
  KEY idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 核心关系（以真实字段为准）
INSERT INTO ai_table_relation (from_table, from_field, to_table, to_field, relation_type, join_type, description, enabled) VALUES
('ad_product_record', 'product_info_id',  'ad_product_info',  'ad_product_info_id',  'many_to_one', 'JOIN',      '出库记录关联产品信息', 1),
('ad_product_record', 'factory_info_id',  'ad_factory_info',  'factory_info_id',     'many_to_one', 'LEFT JOIN', '出库记录关联厂家信息', 1),
('ad_product_info',   'ad_factory_info_id','ad_factory_info',  'factory_info_id',     'many_to_one', 'LEFT JOIN', '产品信息关联厂家信息', 1),
('ad_order_item',     'ad_order_id',      'ad_order_info',    'ad_order_id',         'many_to_one', 'JOIN',      '订单明细关联订单', 1),
('ad_order_item',     'ad_product_info_id','ad_product_info',  'ad_product_info_id',  'many_to_one', 'JOIN',      '订单明细关联产品', 1),
('ad_order_info',     'ad_factory_info_id','ad_factory_info',  'factory_info_id',     'many_to_one', 'LEFT JOIN', '订单关联厂家', 1),
('ad_order_item',     'ad_factory_info_id','ad_factory_info',  'factory_info_id',     'many_to_one', 'LEFT JOIN', '订单明细关联厂家', 1),
('ad_product_parts',  'ad_product_info_id','ad_product_info',  'ad_product_info_id',  'many_to_one', 'JOIN',      '配件关联产品', 1),
('ad_product_parts',  'ad_factory_info_id','ad_factory_info',  'factory_info_id',     'many_to_one', 'LEFT JOIN', '配件关联厂家', 1),
('ad_raw_record',     'factory_info_id',  'ad_factory_info',  'factory_info_id',     'many_to_one', 'LEFT JOIN', '原料记录关联厂家', 1),
('ad_month_inventory','ad_factory_info_id','ad_factory_info',  'factory_info_id',     'many_to_one', 'LEFT JOIN', '月库存关联厂家', 1),
('ad_order_item',     'part_id',          'ad_product_parts', 'id',                  'many_to_one', 'LEFT JOIN', '订单明细关联配件', 1),
('ad_product_record', 'part_id',          'ad_product_parts', 'id',                  'many_to_one', 'LEFT JOIN', '出库记录关联配件', 1)
ON DUPLICATE KEY UPDATE from_field=VALUES(from_field), to_field=VALUES(to_field), description=VALUES(description), enabled=VALUES(enabled);
