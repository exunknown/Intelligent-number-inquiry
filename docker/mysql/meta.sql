SET NAMES utf8mb4;
CREATE DATABASE meta DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
GRANT ALL PRIVILEGES ON meta.* TO 'inquiry01'@'%';

USE meta;

DROP TABLE IF EXISTS table_info;
CREATE TABLE table_info
(
    id          VARCHAR(64) PRIMARY KEY COMMENT '表编号',
    name        VARCHAR(128) COMMENT '表名称',
    role        VARCHAR(32) COMMENT '表类型(fact/dim)',
    description TEXT COMMENT '表描述'
);



DROP TABLE IF EXISTS column_info;
CREATE TABLE column_info
(
    id          VARCHAR(64) PRIMARY KEY COMMENT '列编号',
    name        VARCHAR(128) COMMENT '列名称',
    type        VARCHAR(64) COMMENT '数据类型',
    role        VARCHAR(32) COMMENT '列类型(primary_key,foreign_key,measure,dimension)',
    examples    JSON COMMENT '数据示例',
    description TEXT COMMENT '列描述',
    alias       JSON COMMENT '列别名',
    table_id    VARCHAR(64) COMMENT '所属表编号'
);

DROP TABLE IF EXISTS metric_info;
CREATE TABLE metric_info
(
    id               VARCHAR(64) PRIMARY KEY COMMENT '指标编码',
    name             VARCHAR(128) COMMENT '指标名称',
    description      TEXT COMMENT '指标描述',
    relevant_columns JSON COMMENT '关联的列',
    alias            JSON COMMENT '指标别名'
);


DROP TABLE IF EXISTS column_metric;
CREATE TABLE column_metric
(
    column_id VARCHAR(64) COMMENT '列编号',
    metric_id VARCHAR(64) COMMENT '指标编号',
    PRIMARY KEY (column_id, metric_id)
);

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
