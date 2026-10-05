SET NAMES utf8mb4;
USE meta;

SET @has_missing_requirements_json = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_message'
      AND column_name = 'missing_requirements_json'
);
SET @migration_sql = IF(
    @has_missing_requirements_json = 0,
    'ALTER TABLE query_message ADD COLUMN missing_requirements_json JSON NULL',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
