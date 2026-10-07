SET NAMES utf8mb4;
USE meta;

SET @has_business_graph_snapshot_version = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = 'meta'
      AND table_name = 'query_audit'
      AND column_name = 'business_graph_snapshot_version'
);
SET @migration_sql = IF(
    @has_business_graph_snapshot_version = 0,
    'ALTER TABLE query_audit ADD COLUMN business_graph_snapshot_version VARCHAR(128) NULL AFTER metadata_release_version',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
