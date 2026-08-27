CREATE DATABASE IF NOT EXISTS 2026start_v3 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS med_data_sys DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE med_data_sys;

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
  `total_cycles` INT COMMENT '总循环次数',
  `total_tokens` INT COMMENT '总token数',
  `conversation_history` LONGTEXT COMMENT '完整对话上下文(JSON数组)',
  `trimmed_context` LONGTEXT COMMENT '送给LLM的裁剪后上下文(JSON数组)',
  `created_at` DATETIME COMMENT '创建时间',
  `updated_at` DATETIME COMMENT '更新时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='观察会话日志表';

CREATE TABLE IF NOT EXISTS `observe_cycle_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` VARCHAR(255) NOT NULL COMMENT '会话ID',
  `cycle_index` INT NOT NULL COMMENT '循环序号',
  `phase` VARCHAR(50) NOT NULL COMMENT '阶段: think/execute/observe',
  `sub_phase` VARCHAR(100) COMMENT '子阶段: filter_db/filter_func/plan/gen_code/exec_code/result',
  `prompt` LONGTEXT COMMENT '发送给LLM的prompt',
  `response` LONGTEXT COMMENT 'LLM返回的响应',
  `user_decision` VARCHAR(50) COMMENT '用户决策: approve/reject/edit/skip',
  `exec_code` LONGTEXT COMMENT '执行的代码',
  `exec_result` LONGTEXT COMMENT '执行结果',
  `exec_error` LONGTEXT COMMENT '执行错误',
  `token_estimate` INT COMMENT 'token估算',
  `created_at` DATETIME COMMENT '记录时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='观察周期日志表';

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

CREATE TABLE IF NOT EXISTS `doc_knowledge` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '文档知识键',
  `value` LONGTEXT COMMENT '文档知识值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档知识表';

CREATE TABLE IF NOT EXISTS `code_guide` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '图表代码指南键',
  `value` LONGTEXT COMMENT '图表代码指南值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='图表代码指南表';

CREATE TABLE IF NOT EXISTS `think_knowledge` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '思考知识键',
  `value` LONGTEXT COMMENT '思考知识值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='思考知识表';

CREATE DATABASE IF NOT EXISTS data_copilot_v10_sys DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE data_copilot_v10_sys;

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
  `total_cycles` INT COMMENT '总循环次数',
  `total_tokens` INT COMMENT '总token数',
  `conversation_history` LONGTEXT COMMENT '完整对话上下文(JSON数组)',
  `trimmed_context` LONGTEXT COMMENT '送给LLM的裁剪后上下文(JSON数组)',
  `created_at` DATETIME COMMENT '创建时间',
  `updated_at` DATETIME COMMENT '更新时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='观察会话日志表';

CREATE TABLE IF NOT EXISTS `observe_cycle_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` VARCHAR(255) NOT NULL COMMENT '会话ID',
  `cycle_index` INT NOT NULL COMMENT '循环序号',
  `phase` VARCHAR(50) NOT NULL COMMENT '阶段: think/execute/observe',
  `sub_phase` VARCHAR(100) COMMENT '子阶段: filter_db/filter_func/plan/gen_code/exec_code/result',
  `prompt` LONGTEXT COMMENT '发送给LLM的prompt',
  `response` LONGTEXT COMMENT 'LLM返回的响应',
  `user_decision` VARCHAR(50) COMMENT '用户决策: approve/reject/edit/skip',
  `exec_code` LONGTEXT COMMENT '执行的代码',
  `exec_result` LONGTEXT COMMENT '执行结果',
  `exec_error` LONGTEXT COMMENT '执行错误',
  `token_estimate` INT COMMENT 'token估算',
  `created_at` DATETIME COMMENT '记录时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='观察周期日志表';

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

CREATE TABLE IF NOT EXISTS `doc_knowledge` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '文档知识键',
  `value` LONGTEXT COMMENT '文档知识值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档知识表';

CREATE TABLE IF NOT EXISTS `code_guide` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '图表代码指南键',
  `value` LONGTEXT COMMENT '图表代码指南值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='图表代码指南表';

CREATE TABLE IF NOT EXISTS `think_knowledge` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `key` TEXT NOT NULL COMMENT '思考知识键',
  `value` LONGTEXT COMMENT '思考知识值',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='思考知识表';

CREATE TABLE IF NOT EXISTS `brief_info` (
  `attr` TEXT NOT NULL COMMENT '属性名称',
  `value` LONGTEXT COMMENT '属性值'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='简要信息表';

INSERT INTO `brief_info` (`attr`, `value`) VALUES ('db_brief', '');
INSERT INTO `brief_info` (`attr`, `value`) VALUES ('base_knowledge_brief', '');