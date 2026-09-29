SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS meta DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE meta;

CREATE TABLE IF NOT EXISTS metadata_release
(
    release_version  VARCHAR(64) PRIMARY KEY,
    manifest_json    JSON NOT NULL,
    manifest_sha256  CHAR(64) NOT NULL,
    status           VARCHAR(16) NOT NULL,
    active           TINYINT(1) NOT NULL DEFAULT 0,
    error_code       VARCHAR(64) NULL,
    created_at       DATETIME NOT NULL,
    validated_at     DATETIME NULL,
    activated_at     DATETIME NULL,
    INDEX idx_metadata_release_active (active, activated_at)
);

CREATE TABLE IF NOT EXISTS metadata_release_lock
(
    id         SMALLINT PRIMARY KEY,
    updated_at DATETIME NOT NULL
);

INSERT INTO metadata_release_lock (id, updated_at)
VALUES (1, UTC_TIMESTAMP())
ON DUPLICATE KEY UPDATE updated_at = VALUES(updated_at);

-- 发布仓储通过 SELECT ... FOR UPDATE 锁住上面的单行，串行化激活和回滚。

SET @has_metadata_release_version = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = 'meta'
      AND table_name = 'query_audit'
      AND column_name = 'metadata_release_version'
);
SET @migration_sql = IF(
    @has_metadata_release_version = 0,
    'ALTER TABLE query_audit ADD COLUMN metadata_release_version VARCHAR(64) NULL AFTER llm_cost_units',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
