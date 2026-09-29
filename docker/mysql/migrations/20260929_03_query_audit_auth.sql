USE meta;

SET @has_user_id = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'user_id'
);
SET @migration_sql = IF(
    @has_user_id = 0,
    'ALTER TABLE query_audit ADD COLUMN user_id VARCHAR(255) NULL AFTER created_at',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_username = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'username'
);
SET @migration_sql = IF(
    @has_username = 0,
    'ALTER TABLE query_audit ADD COLUMN username VARCHAR(255) NULL AFTER user_id',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_roles = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'roles'
);
SET @migration_sql = IF(
    @has_roles = 0,
    'ALTER TABLE query_audit ADD COLUMN roles JSON NULL AFTER username',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_policy_version = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'policy_version'
);
SET @migration_sql = IF(
    @has_policy_version = 0,
    'ALTER TABLE query_audit ADD COLUMN policy_version BIGINT UNSIGNED NULL AFTER roles',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_department_ids = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'allowed_department_ids'
);
SET @migration_sql = IF(
    @has_department_ids = 0,
    'ALTER TABLE query_audit ADD COLUMN allowed_department_ids JSON NULL AFTER policy_version',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_authz_outcome = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND column_name = 'authz_outcome'
);
SET @migration_sql = IF(
    @has_authz_outcome = 0,
    'ALTER TABLE query_audit ADD COLUMN authz_outcome VARCHAR(32) NULL AFTER allowed_department_ids',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

UPDATE query_audit
SET user_id = COALESCE(user_id, 'legacy-unknown'),
    roles = COALESCE(roles, JSON_ARRAY()),
    policy_version = COALESCE(policy_version, 0),
    allowed_department_ids = COALESCE(allowed_department_ids, JSON_ARRAY()),
    authz_outcome = COALESCE(authz_outcome, 'legacy')
WHERE user_id IS NULL
   OR roles IS NULL
   OR policy_version IS NULL
   OR allowed_department_ids IS NULL
   OR authz_outcome IS NULL;

ALTER TABLE query_audit
    MODIFY user_id VARCHAR(255) NOT NULL,
    MODIFY roles JSON NOT NULL,
    MODIFY policy_version BIGINT UNSIGNED NOT NULL,
    MODIFY allowed_department_ids JSON NOT NULL,
    MODIFY authz_outcome VARCHAR(32) NOT NULL;

SET @has_user_created_index = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND index_name = 'idx_query_audit_user_created'
);
SET @migration_sql = IF(
    @has_user_created_index = 0,
    'ALTER TABLE query_audit ADD INDEX idx_query_audit_user_created (user_id, created_at)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_policy_created_index = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = 'meta' AND table_name = 'query_audit'
      AND index_name = 'idx_query_audit_policy_created'
);
SET @migration_sql = IF(
    @has_policy_created_index = 0,
    'ALTER TABLE query_audit ADD INDEX idx_query_audit_policy_created (policy_version, created_at)',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;
