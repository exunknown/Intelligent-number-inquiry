SET NAMES utf8mb4;
USE meta;

CREATE TABLE IF NOT EXISTS query_export
(
    id            VARCHAR(36) PRIMARY KEY,
    request_id    VARCHAR(64) NOT NULL,
    user_id       VARCHAR(255) NOT NULL,
    policy_version BIGINT UNSIGNED NOT NULL,
    session_id    VARCHAR(36),
    object_key    VARCHAR(255) NOT NULL UNIQUE,
    content_type  VARCHAR(128) NOT NULL DEFAULT 'application/json; charset=utf-8',
    result_bytes  INT NOT NULL,
    row_count     INT,
    created_at    DATETIME NOT NULL,
    expires_at    DATETIME NOT NULL,
    INDEX idx_query_export_user_created (user_id, created_at),
    INDEX idx_query_export_expires (expires_at)
);

SET @has_policy_version = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_export'
      AND column_name = 'policy_version'
);
SET @migration_sql = IF(
    @has_policy_version = 0,
    'ALTER TABLE query_export ADD COLUMN policy_version BIGINT UNSIGNED NOT NULL DEFAULT 0 AFTER user_id',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
