SET NAMES utf8mb4;
USE meta;

CREATE TABLE IF NOT EXISTS query_turn_context
(
    id                         VARCHAR(36) PRIMARY KEY,
    session_id                 VARCHAR(36) NOT NULL,
    user_id                    VARCHAR(255) NOT NULL,
    request_id                 VARCHAR(64) NOT NULL,
    user_message_sequence_no  INT UNSIGNED NOT NULL,
    effective_query            TEXT NOT NULL,
    query_mode                 VARCHAR(16) NOT NULL,
    context_json               JSON NOT NULL,
    result_summary_json        JSON,
    metadata_release_version   VARCHAR(128),
    inherited_from_context_id  VARCHAR(36),
    context_schema_version     SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    created_at                 DATETIME NOT NULL,
    UNIQUE KEY uq_query_turn_context_request (request_id),
    INDEX idx_query_turn_context_session_created (session_id, created_at, id),
    INDEX idx_query_turn_context_user_session_created
        (user_id, session_id, created_at)
);

SET @has_query_turn_context_request_index = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = 'meta'
      AND table_name = 'query_turn_context'
      AND index_name = 'uq_query_turn_context_request'
);
SET @migration_sql = IF(
    @has_query_turn_context_request_index = 0,
    'ALTER TABLE query_turn_context ADD UNIQUE INDEX uq_query_turn_context_request (request_id)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_query_turn_context_session_index = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = 'meta'
      AND table_name = 'query_turn_context'
      AND index_name = 'idx_query_turn_context_session_created'
);
SET @migration_sql = IF(
    @has_query_turn_context_session_index = 0,
    'ALTER TABLE query_turn_context ADD INDEX idx_query_turn_context_session_created (session_id, created_at, id)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_query_turn_context_user_session_index = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = 'meta'
      AND table_name = 'query_turn_context'
      AND index_name = 'idx_query_turn_context_user_session_created'
);
SET @migration_sql = IF(
    @has_query_turn_context_user_session_index = 0,
    'ALTER TABLE query_turn_context ADD INDEX idx_query_turn_context_user_session_created (user_id, session_id, created_at)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
