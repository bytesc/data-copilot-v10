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
