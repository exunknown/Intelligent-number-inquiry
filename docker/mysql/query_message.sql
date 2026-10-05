SET NAMES utf8mb4;
USE meta;

CREATE TABLE IF NOT EXISTS query_message
(
    id                   VARCHAR(36) PRIMARY KEY,
    session_id           VARCHAR(36) NOT NULL,
    user_id              VARCHAR(255) NOT NULL,
    request_id           VARCHAR(64),
    sequence_no          INT UNSIGNED NOT NULL,
    role                 VARCHAR(16) NOT NULL,
    content              TEXT NOT NULL,
    status               VARCHAR(16) NOT NULL,
    steps_json           JSON,
    process_events_json  JSON NULL,
    missing_requirements_json JSON NULL,
    metrics_json         JSON,
    query_mode           VARCHAR(16),
    route_reason         VARCHAR(64),
    result_preview_json  JSON,
    verified             BOOLEAN,
    warning              TEXT,
    row_count            INT,
    truncated            BOOLEAN,
    export_id            VARCHAR(36),
    error_message        TEXT,
    error_code           VARCHAR(64),
    retryable            BOOLEAN,
    created_at           DATETIME NOT NULL,
    UNIQUE KEY uq_query_message_session_sequence (session_id, sequence_no),
    INDEX idx_query_message_session_created (session_id, created_at),
    INDEX idx_query_message_user_created (user_id, created_at)
);

SET @has_archived_at = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_session'
      AND column_name = 'archived_at'
);
SET @migration_sql = IF(
    @has_archived_at = 0,
    'ALTER TABLE query_session ADD COLUMN archived_at DATETIME NULL',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_deleted_at = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_session'
      AND column_name = 'deleted_at'
);
SET @migration_sql = IF(
    @has_deleted_at = 0,
    'ALTER TABLE query_session ADD COLUMN deleted_at DATETIME NULL',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_session_state_index = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = 'meta' AND table_name = 'query_session'
      AND index_name = 'idx_query_session_user_state_updated'
);
SET @migration_sql = IF(
    @has_session_state_index = 0,
    'ALTER TABLE query_session ADD INDEX idx_query_session_user_state_updated (user_id, archived_at, deleted_at, updated_at)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
