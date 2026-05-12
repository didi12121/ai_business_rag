-- ============================================================
-- Data Agent 查询规划模式：数据库迁移
-- ============================================================

-- 1. 新增 Agent 运行记录表
CREATE TABLE IF NOT EXISTS ai_agent_run (
  id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(100) DEFAULT NULL,
  user_id VARCHAR(100) DEFAULT NULL,
  question TEXT NOT NULL,
  query_mode VARCHAR(50) DEFAULT 'agent',
  plan_json JSON DEFAULT NULL,
  final_answer LONGTEXT DEFAULT NULL,
  success TINYINT DEFAULT 1,
  error_code VARCHAR(100) DEFAULT NULL,
  error_msg TEXT DEFAULT NULL,
  duration_ms INT DEFAULT NULL,
  model_name VARCHAR(100) DEFAULT NULL,
  create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_session_id (session_id),
  KEY idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI Agent运行记录';

-- 2. 新增 Agent 步骤日志表
CREATE TABLE IF NOT EXISTS ai_agent_step_log (
  id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  step_id INT NOT NULL,
  step_name VARCHAR(255) DEFAULT NULL,
  purpose TEXT DEFAULT NULL,
  sql_text TEXT DEFAULT NULL,
  used_tables JSON DEFAULT NULL,
  row_count INT DEFAULT NULL,
  rows_preview JSON DEFAULT NULL,
  estimated_rows BIGINT DEFAULT NULL,
  success TINYINT DEFAULT 1,
  error_code VARCHAR(100) DEFAULT NULL,
  error_msg TEXT DEFAULT NULL,
  duration_ms INT DEFAULT NULL,
  create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_run_id (run_id),
  KEY idx_step_id (step_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI Agent步骤日志';

-- 3. ai_table_schema 增加 allow_query（如果还没加）
ALTER TABLE ai_table_schema ADD COLUMN allow_query TINYINT DEFAULT 0 COMMENT '是否允许AI自由SQL/Agent查询';

-- 4. 设置允许 AI 查询的业务表
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

-- 5. ai_chat_log 增加字段（如果还没加）
ALTER TABLE ai_chat_log ADD COLUMN query_mode VARCHAR(50) DEFAULT NULL COMMENT '查询模式';
ALTER TABLE ai_chat_log ADD COLUMN free_sql_reason TEXT NULL COMMENT '自由SQL生成理由';
ALTER TABLE ai_chat_log ADD COLUMN used_tables JSON NULL COMMENT '使用的表';
ALTER TABLE ai_chat_log ADD COLUMN risk_level VARCHAR(50) DEFAULT NULL COMMENT '风险等级';
ALTER TABLE ai_chat_log ADD COLUMN estimated_rows BIGINT DEFAULT NULL COMMENT 'EXPLAIN预估扫描行数';

-- 6. sys_config 插入 Agent 配置
INSERT INTO sys_config (config_name, config_key, config_value, config_type, create_by, create_time, remark)
VALUES
('AI Agent开关',           'ai.agent.enabled',              'true', 'Y', 'admin', NOW(), '是否启用Data Agent查询规划模式'),
('AI Agent最大执行步数',    'ai.agent.max_steps',            '5',    'Y', 'admin', NOW(), 'Agent最多执行几步SQL'),
('AI Agent默认LIMIT',      'ai.agent.default_limit',        '100',  'Y', 'admin', NOW(), 'Agent每步默认LIMIT'),
('AI是否展示查询计划',      'ai.agent.show_plan',            'true', 'Y', 'admin', NOW(), '前端是否展示Query Plan'),
('AI是否展示步骤SQL',       'ai.agent.show_step_sql',        'true', 'Y', 'admin', NOW(), '前端是否展示每步SQL'),
('AI是否允许追加查询步骤',  'ai.agent.allow_followup_steps', 'true', 'Y', 'admin', NOW(), '是否允许Agent追加后续查询步骤'),

('AI自由SQL开关',           'ai.free_sql.enabled',              'true',  'Y', 'admin', NOW(), ''),
('AI自由SQL是否需要确认',   'ai.free_sql.require_confirm',      'false', 'Y', 'admin', NOW(), ''),
('AI自由SQL最大返回行数',   'ai.free_sql.max_rows',             '200',   'Y', 'admin', NOW(), ''),
('AI自由SQL是否执行EXPLAIN','ai.free_sql.explain_before_run',   'true',  'Y', 'admin', NOW(), ''),
('AI自由SQL最大预估扫描行数','ai.free_sql.max_estimated_rows',  '50000', 'Y', 'admin', NOW(), ''),

('AI SQL超时时间',          'ai.sql.timeout_seconds',           '10',    'Y', 'admin', NOW(), ''),
('AI是否默认展示SQL',       'ai.sql.show_sql_default',          'true',  'Y', 'admin', NOW(), '')
ON DUPLICATE KEY UPDATE
config_name = VALUES(config_name),
config_value = VALUES(config_value),
remark = VALUES(remark),
update_time = NOW();
