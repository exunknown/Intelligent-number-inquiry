SET NAMES utf8mb4;
USE meta;

SET @has_process_events_json = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_message'
      AND column_name = 'process_events_json'
);
SET @migration_sql = IF(
    @has_process_events_json = 0,
    'ALTER TABLE query_message ADD COLUMN process_events_json JSON NULL',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
