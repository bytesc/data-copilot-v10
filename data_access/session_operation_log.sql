CREATE TABLE IF NOT EXISTS `session_operation_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` VARCHAR(255) NOT NULL COMMENT '会话ID',
  `api_endpoint` VARCHAR(255) NOT NULL COMMENT '调用的API接口',
  `question` TEXT COMMENT '用户输入的问题',
  `ans` TEXT COMMENT '返回的结果',
  `code` TEXT COMMENT '生成的代码',
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
  `question` TEXT COMMENT '用户问题',
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
  `prompt` TEXT COMMENT '发送给LLM的prompt',
  `response` TEXT COMMENT 'LLM返回的响应',
  `user_decision` VARCHAR(50) COMMENT '用户决策: approve/reject/edit/skip',
  `exec_code` TEXT COMMENT '执行的代码',
  `exec_result` TEXT COMMENT '执行结果',
  `exec_error` TEXT COMMENT '执行错误',
  `token_estimate` INT COMMENT 'token估算',
  `created_at` DATETIME COMMENT '记录时间',
  PRIMARY KEY (`id`),
  INDEX `idx_session_id` (`session_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='观察周期日志表';
