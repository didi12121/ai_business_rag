-- ============================================================
-- 自由 SQL 查询模式：数据库迁移
-- ============================================================

-- 1. ai_table_schema 增加 allow_query 字段
ALTER TABLE ai_table_schema
ADD COLUMN IF NOT EXISTS allow_query TINYINT DEFAULT 0 COMMENT '是否允许AI自由SQL查询：1允许，0禁止';

-- 2. ai_chat_log 增加自由 SQL 相关字段
ALTER TABLE ai_chat_log
ADD COLUMN IF NOT EXISTS query_mode VARCHAR(50) DEFAULT NULL COMMENT '查询模式：template/free_sql/rule',
ADD COLUMN IF NOT EXISTS free_sql_reason TEXT NULL COMMENT '自由SQL生成理由',
ADD COLUMN IF NOT EXISTS used_tables JSON NULL COMMENT '自由SQL使用的表',
ADD COLUMN IF NOT EXISTS risk_level VARCHAR(50) DEFAULT NULL COMMENT '自由SQL风险等级',
ADD COLUMN IF NOT EXISTS estimated_rows BIGINT DEFAULT NULL COMMENT 'EXPLAIN预估扫描行数';

-- 3. 设置允许自由查询的业务表
UPDATE ai_table_schema SET allow_query = 1 WHERE table_name IN (
    'ad_factory_info',
    'ad_product_info',
    'ad_product_parts',
    'ad_product_record',
    'ad_raw_record',
    'ad_month_inventory',
    'ad_order_info',
    'ad_order_item'
);

-- 4. sys_config 插入自由 SQL 相关配置
INSERT INTO sys_config (config_name, config_key, config_value, config_type, create_by, create_time, remark)
VALUES
('AI自由SQL开关',              'ai.free_sql.enabled',              'true',  'Y', 'admin', NOW(), '是否允许LLM自由生成SQL'),
('AI自由SQL是否需要确认',      'ai.free_sql.require_confirm',      'false', 'Y', 'admin', NOW(), '自由SQL执行前是否需要用户确认'),
('AI自由SQL最大返回行数',      'ai.free_sql.max_rows',             '200',   'Y', 'admin', NOW(), '自由SQL查询最大返回行数'),
('AI自由SQL是否执行EXPLAIN',   'ai.free_sql.explain_before_run',   'true',  'Y', 'admin', NOW(), '自由SQL执行前是否先EXPLAIN'),
('AI自由SQL最大预估扫描行数',  'ai.free_sql.max_estimated_rows',   '50000', 'Y', 'admin', NOW(), 'EXPLAIN预估超过此行数则拒绝执行'),
('AI SQL超时时间',             'ai.sql.timeout_seconds',           '10',    'Y', 'admin', NOW(), 'SQL执行超时秒数'),
('AI是否默认展示SQL',          'ai.sql.show_sql_default',          'true',  'Y', 'admin', NOW(), '是否默认返回SQL给前端')
ON DUPLICATE KEY UPDATE
config_name = VALUES(config_name),
config_value = VALUES(config_value),
remark = VALUES(remark),
update_time = NOW();
