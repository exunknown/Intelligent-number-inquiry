SET NAMES utf8mb4;
USE meta;

-- 将已有元数据归入 legacy 版本，再允许同一业务 id 在不同发布版本并存。
SET @table_release_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'table_info'
      AND column_name = 'release_version'
);
SET @sql = IF(
    @table_release_column = 0,
    'ALTER TABLE table_info ADD COLUMN release_version VARCHAR(64) NOT NULL DEFAULT ''legacy'' FIRST',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @column_release_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'column_info'
      AND column_name = 'release_version'
);
SET @sql = IF(
    @column_release_column = 0,
    'ALTER TABLE column_info ADD COLUMN release_version VARCHAR(64) NOT NULL DEFAULT ''legacy'' FIRST',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @metric_release_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'metric_info'
      AND column_name = 'release_version'
);
SET @sql = IF(
    @metric_release_column = 0,
    'ALTER TABLE metric_info ADD COLUMN release_version VARCHAR(64) NOT NULL DEFAULT ''legacy'' FIRST',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @relation_release_column = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = 'meta' AND table_name = 'column_metric'
      AND column_name = 'release_version'
);
SET @sql = IF(
    @relation_release_column = 0,
    'ALTER TABLE column_metric ADD COLUMN release_version VARCHAR(64) NOT NULL DEFAULT ''legacy'' FIRST',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @table_pk_version = (
    SELECT COUNT(*) FROM information_schema.key_column_usage
    WHERE table_schema = 'meta' AND table_name = 'table_info'
      AND constraint_name = 'PRIMARY' AND column_name = 'release_version'
);
SET @sql = IF(
    @table_pk_version = 0,
    'ALTER TABLE table_info DROP PRIMARY KEY, ADD PRIMARY KEY (release_version, id)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @column_pk_version = (
    SELECT COUNT(*) FROM information_schema.key_column_usage
    WHERE table_schema = 'meta' AND table_name = 'column_info'
      AND constraint_name = 'PRIMARY' AND column_name = 'release_version'
);
SET @sql = IF(
    @column_pk_version = 0,
    'ALTER TABLE column_info DROP PRIMARY KEY, ADD PRIMARY KEY (release_version, id)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @metric_pk_version = (
    SELECT COUNT(*) FROM information_schema.key_column_usage
    WHERE table_schema = 'meta' AND table_name = 'metric_info'
      AND constraint_name = 'PRIMARY' AND column_name = 'release_version'
);
SET @sql = IF(
    @metric_pk_version = 0,
    'ALTER TABLE metric_info DROP PRIMARY KEY, ADD PRIMARY KEY (release_version, id)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @relation_pk_version = (
    SELECT COUNT(*) FROM information_schema.key_column_usage
    WHERE table_schema = 'meta' AND table_name = 'column_metric'
      AND constraint_name = 'PRIMARY' AND column_name = 'release_version'
);
SET @sql = IF(
    @relation_pk_version = 0,
    'ALTER TABLE column_metric DROP PRIMARY KEY, ADD PRIMARY KEY (release_version, column_id, metric_id)',
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 已存在活动 manifest 的旧环境，把 legacy 数据复制到当前活动版本。
INSERT INTO table_info (release_version, id, name, role, description)
SELECT mr.release_version, source.id, source.name, source.role, source.description
FROM metadata_release mr
JOIN table_info source ON source.release_version = 'legacy'
WHERE mr.active = 1 AND mr.status = 'active'
ON DUPLICATE KEY UPDATE
    name = VALUES(name), role = VALUES(role), description = VALUES(description);

INSERT INTO column_info (
    release_version, id, name, type, role, examples, description, alias, table_id
)
SELECT mr.release_version, source.id, source.name, source.type, source.role,
       source.examples, source.description, source.alias, source.table_id
FROM metadata_release mr
JOIN column_info source ON source.release_version = 'legacy'
WHERE mr.active = 1 AND mr.status = 'active'
ON DUPLICATE KEY UPDATE
    name = VALUES(name), type = VALUES(type), role = VALUES(role),
    examples = VALUES(examples), description = VALUES(description),
    alias = VALUES(alias), table_id = VALUES(table_id);

INSERT INTO metric_info (
    release_version, id, name, description, relevant_columns, alias
)
SELECT mr.release_version, source.id, source.name, source.description,
       source.relevant_columns, source.alias
FROM metadata_release mr
JOIN metric_info source ON source.release_version = 'legacy'
WHERE mr.active = 1 AND mr.status = 'active'
ON DUPLICATE KEY UPDATE
    name = VALUES(name), description = VALUES(description),
    relevant_columns = VALUES(relevant_columns), alias = VALUES(alias);

INSERT INTO column_metric (release_version, column_id, metric_id)
SELECT mr.release_version, source.column_id, source.metric_id
FROM metadata_release mr
JOIN column_metric source ON source.release_version = 'legacy'
WHERE mr.active = 1 AND mr.status = 'active'
ON DUPLICATE KEY UPDATE column_id = VALUES(column_id);
