-- ============================================================
-- AI 模型配置表：支持多个 LLM 模型切换
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_llm_model (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL COMMENT '显示名称，如 DeepSeek V3',
    base_url VARCHAR(255) NOT NULL COMMENT 'API 地址',
    api_key VARCHAR(255) NOT NULL COMMENT 'API Key',
    model VARCHAR(100) NOT NULL COMMENT '模型标识，如 deepseek-chat',
    timeout INT DEFAULT 120 COMMENT '请求超时秒数',
    is_active TINYINT(1) DEFAULT 0 COMMENT '是否激活',
    sort_order INT DEFAULT 0 COMMENT '排序',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI模型配置';

-- 从 sys_config 迁移现有 LLM 配置到模型表（仅当模型表为空时）
INSERT INTO ai_llm_model (name, base_url, api_key, model, timeout, is_active)
SELECT
    '默认模型',
    COALESCE((SELECT config_value FROM sys_config WHERE config_key = 'ai.llm.base_url'), ''),
    COALESCE((SELECT config_value FROM sys_config WHERE config_key = 'ai.llm.api_key'), ''),
    COALESCE((SELECT config_value FROM sys_config WHERE config_key = 'ai.llm.model'), ''),
    COALESCE((SELECT CAST(config_value AS UNSIGNED) FROM sys_config WHERE config_key = 'ai.llm.timeout'), 120),
    1
WHERE NOT EXISTS (SELECT 1 FROM ai_llm_model);
