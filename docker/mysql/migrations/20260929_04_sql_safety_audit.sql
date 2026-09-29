USE meta;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'normalized_sql'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN normalized_sql TEXT NULL AFTER sql_text',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'executed_sql'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN executed_sql TEXT NULL AFTER normalized_sql',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'sql_policy_outcome'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN sql_policy_outcome VARCHAR(32) NULL AFTER executed_sql',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'sql_rejection_reason'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN sql_rejection_reason VARCHAR(64) NULL AFTER sql_policy_outcome',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'sql_estimated_rows'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN sql_estimated_rows BIGINT NULL AFTER sql_rejection_reason',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'sql_query_cost'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN sql_query_cost DOUBLE NULL AFTER sql_estimated_rows',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'result_row_count'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN result_row_count INT NULL AFTER sql_query_cost',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'result_bytes'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN result_bytes BIGINT NULL AFTER result_row_count',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'result_truncated'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN result_truncated BOOLEAN NULL AFTER result_bytes',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'sql_execution_duration_ms'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN sql_execution_duration_ms INT NULL AFTER result_truncated',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
