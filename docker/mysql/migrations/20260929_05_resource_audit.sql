USE meta;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'llm_call_count'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN llm_call_count INT NOT NULL DEFAULT 0 AFTER sql_execution_duration_ms',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'embedding_call_count'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN embedding_call_count INT NOT NULL DEFAULT 0 AFTER llm_call_count',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'llm_input_tokens'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN llm_input_tokens INT NULL AFTER embedding_call_count',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'llm_output_tokens'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN llm_output_tokens INT NULL AFTER llm_input_tokens',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'llm_cost_units'
);
SET @migration_sql = IF(@has_column = 0,
    'ALTER TABLE query_audit ADD COLUMN llm_cost_units DOUBLE NULL AFTER llm_output_tokens',
    'SELECT 1');
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
