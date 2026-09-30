SET NAMES utf8mb4;
USE meta;

CREATE TABLE IF NOT EXISTS query_session
(
    id                             VARCHAR(36) PRIMARY KEY,
    user_id                        VARCHAR(255) NOT NULL,
    username                       VARCHAR(255),
    title                          VARCHAR(200) NOT NULL,
    created_at                     DATETIME NOT NULL,
    updated_at                     DATETIME NOT NULL,
    message_count                  INT NOT NULL DEFAULT 0,
    last_request_id                VARCHAR(64),
    last_outcome                   VARCHAR(32),
    last_query_mode                VARCHAR(16),
    last_error_code                VARCHAR(64),
    last_metadata_release_version  VARCHAR(64),
    INDEX idx_query_session_user_updated (user_id, updated_at)
);

SET @has_session_id = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'session_id'
);
SET @migration_sql = IF(
    @has_session_id = 0,
    'ALTER TABLE query_audit ADD COLUMN session_id VARCHAR(36) NULL AFTER request_id',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_session_index = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND index_name = 'idx_query_audit_session_created'
);
SET @migration_sql = IF(
    @has_session_index = 0,
    'ALTER TABLE query_audit ADD INDEX idx_query_audit_session_created (session_id, created_at)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
