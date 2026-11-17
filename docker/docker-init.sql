-- Docker MySQL bootstrap.
-- Database names MUST match config/config.yaml:
--   mysql       -> singapore_land_2            (business data DB)
--   mysql_sys   -> data_copilot_v10_land_sys   (session logs, knowledge, audit)
--   readonly user -> readonly@'%' on singapore_land_2 (used by exe_sql for SELECT/SHOW)
-- Keep this file in sync with the root init.sql (system-table definitions).

-- Read-only user: used by the backend exe_sql for SELECT/SHOW.
-- Grants are scoped to the business DB so the account can show tables/views there.
-- The password must match mysql_readonly in config/config.yaml.
CREATE USER IF NOT EXISTS 'readonly'@'%' IDENTIFIED BY '123456';
-- Business database (empty container; import your own data into it).
CREATE DATABASE IF NOT EXISTS singapore_land_2 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT SELECT, SHOW VIEW ON singapore_land_2.* TO 'readonly'@'%';
FLUSH PRIVILEGES;

-- System database (must match mysql_sys).
CREATE DATABASE IF NOT EXISTS data_copilot_v10_land_sys DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE data_copilot_v10_land_sys;

CREATE TABLE IF NOT EXISTS `session_operation_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` VARCHAR(255) NOT NULL COMMENT '会话ID',
  `api_endpoint` VARCHAR(255) NOT NULL COMMENT '调用的API接口',
  `question` LONGTEXT COMMENT '用户输入的问题',
  `ans` LONGTEXT COMMENT '返回的结果',
  `code` LONGTEXT COMMENT '生成的代码',
  `result_type` VARCHAR(50) COMMENT 'success/error',
  `msg` VARCHAR(512) COMMENT '处理结果描述',
  `prompt_length` INT COMMENT 'prompt长度',
  `created_at` DATETIME COMMENT '记录时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话操作记录表';

CREATE TABLE IF NOT EXISTS `observe_session_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` VARCHAR(255) NOT NULL COMMENT '会话ID',
  `question` LONGTEXT COMMENT '用户问题',
  `status` VARCHAR(50) COMMENT '会话状态',
  `conversation_history` LONGTEXT COMMENT '完整对话上下文(JSON数组)',
  `trimmed_context` LONGTEXT COMMENT '送给LLM的裁剪后上下文(JSON数组)',
  `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '是否已删除(1=已删除,0=未删除)',
  `created_at` DATETIME COMMENT '创建时间',
  `updated_at` DATETIME COMMENT '更新时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='观察会话日志表';

CREATE TABLE IF NOT EXISTS `report_generation_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` VARCHAR(255) NOT NULL COMMENT '会话ID',
  `file_name` VARCHAR(512) COMMENT '生成的文件名',
  `chat_history` LONGTEXT COMMENT '输入的聊天历史(JSON)',
  `outline` LONGTEXT COMMENT '生成的大纲',
  `full_text` LONGTEXT COMMENT '生成的全文',
  `created_at` DATETIME COMMENT '记录时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报告生成日志表';

CREATE TABLE IF NOT EXISTS `llm_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` VARCHAR(255) COMMENT '会话ID（可能为空）',
  `input` LONGTEXT COMMENT '输入消息(JSON字符串，已去除图片base64)',
  `output` LONGTEXT COMMENT '输出文本',
  `prompt_tokens` INT COMMENT 'prompt token数',
  `completion_tokens` INT COMMENT 'completion token数',
  `total_tokens` INT COMMENT '总token数',
  `reasoning_tokens` INT COMMENT 'reasoning token数',
  `first_token_ms` INT COMMENT '首字符响应延迟(ms)，非流式为NULL',
  `duration_ms` INT COMMENT '本次调用总耗时(ms)',
  `created_at` DATETIME COMMENT '记录时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM调用日志表';

CREATE TABLE IF NOT EXISTS `web_access_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` VARCHAR(255) COMMENT '会话ID（可能为空）',
  `access_type` VARCHAR(50) COMMENT '行为类型：web_search / fetch_webpage',
  `query` LONGTEXT COMMENT '搜索关键词（web_search）',
  `urls` LONGTEXT COMMENT '抓取的URL列表(JSON数组，fetch_webpage)',
  `success` TINYINT(1) COMMENT '是否成功',
  `error` VARCHAR(1024) COMMENT '失败原因',
  `duration_ms` INT COMMENT '本次访问耗时(ms)',
  `result` LONGTEXT COMMENT '返回结果(JSON字符串)',
  `created_at` DATETIME COMMENT '记录时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Web搜索/抓取日志表';

CREATE TABLE IF NOT EXISTS `base_knowledge` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '基础知识键',
  `value` LONGTEXT COMMENT '基础知识值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础知识表';

CREATE TABLE IF NOT EXISTS `db_query_guide` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '查询指南键',
  `value` LONGTEXT COMMENT '查询指南值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='查询指南表';

CREATE TABLE IF NOT EXISTS `doc_guide` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '文档指南键',
  `value` LONGTEXT COMMENT '文档指南值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档指南表';

CREATE TABLE IF NOT EXISTS `code_guide` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '代码指南键',
  `value` LONGTEXT COMMENT '代码指南值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='代码指南表';

CREATE TABLE IF NOT EXISTS `graph_code_guide` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '图表代码指南键',
  `value` LONGTEXT COMMENT '图表代码指南值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='图谱代码指南表';

CREATE TABLE IF NOT EXISTS `think_guide` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '思考指南键',
  `value` LONGTEXT COMMENT '思考指南值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='思考指南表';

CREATE TABLE IF NOT EXISTS `brief_info` (
  `attr` TEXT NOT NULL COMMENT '属性名称',
  `value` LONGTEXT COMMENT '属性值'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='简要信息表';

INSERT INTO `brief_info` (`attr`, `value`) VALUES ('db_brief', '');
INSERT INTO `brief_info` (`attr`, `value`) VALUES ('base_knowledge_brief', '');
INSERT INTO `brief_info` (`attr`, `value`) VALUES ('mcp_brief', '');
INSERT INTO `brief_info` (`attr`, `value`) VALUES ('custom_func_brief', '');
