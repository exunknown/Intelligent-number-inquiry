SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS meta DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
GRANT ALL PRIVILEGES ON meta.* TO 'inquiry01'@'%';

USE meta;

DROP TABLE IF EXISTS table_info;
CREATE TABLE table_info
(
    release_version VARCHAR(64) NOT NULL DEFAULT 'legacy' COMMENT '元数据发布版本',
    id          VARCHAR(64) COMMENT '表编号',
    name        VARCHAR(128) COMMENT '表名称',
    role        VARCHAR(32) COMMENT '表类型(fact/dim)',
    description TEXT COMMENT '表描述',
    PRIMARY KEY (release_version, id)
);



DROP TABLE IF EXISTS column_info;
CREATE TABLE column_info
(
    release_version VARCHAR(64) NOT NULL DEFAULT 'legacy' COMMENT '元数据发布版本',
    id          VARCHAR(64) COMMENT '列编号',
    name        VARCHAR(128) COMMENT '列名称',
    type        VARCHAR(64) COMMENT '数据类型',
    role        VARCHAR(32) COMMENT '列类型(primary_key,foreign_key,measure,dimension)',
    examples    JSON COMMENT '数据示例',
    description TEXT COMMENT '列描述',
    alias       JSON COMMENT '列别名',
    table_id    VARCHAR(64) COMMENT '所属表编号',
    PRIMARY KEY (release_version, id)
);

DROP TABLE IF EXISTS metric_info;
CREATE TABLE metric_info
(
    release_version VARCHAR(64) NOT NULL DEFAULT 'legacy' COMMENT '元数据发布版本',
    id               VARCHAR(64) COMMENT '指标编码',
    name             VARCHAR(128) COMMENT '指标名称',
    description      TEXT COMMENT '指标描述',
    relevant_columns JSON COMMENT '关联的列',
    alias            JSON COMMENT '指标别名',
    PRIMARY KEY (release_version, id)
);


DROP TABLE IF EXISTS column_metric;
CREATE TABLE column_metric
(
    release_version VARCHAR(64) NOT NULL DEFAULT 'legacy' COMMENT '元数据发布版本',
    column_id VARCHAR(64) COMMENT '列编号',
    metric_id VARCHAR(64) COMMENT '指标编号',
    PRIMARY KEY (release_version, column_id, metric_id)
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

CREATE TABLE IF NOT EXISTS knowledge_graph_node
(
    release_version VARCHAR(64) NOT NULL COMMENT '元数据发布版本',
    node_id         VARCHAR(192) NOT NULL COMMENT '图谱节点稳定编号',
    node_type       VARCHAR(64) NOT NULL COMMENT '图谱节点类型',
    title           VARCHAR(256) NOT NULL COMMENT '节点标题',
    description     TEXT NOT NULL COMMENT '节点描述',
    payload_json    JSON NOT NULL COMMENT '受控节点属性',
    source          VARCHAR(64) NOT NULL COMMENT '节点来源',
    confidence      DOUBLE NOT NULL COMMENT '节点置信度',
    created_at      DATETIME NOT NULL COMMENT '创建时间',
    PRIMARY KEY (release_version, node_id),
    INDEX idx_knowledge_graph_node_release_type (release_version, node_type)
);

CREATE TABLE IF NOT EXISTS knowledge_graph_edge
(
    release_version VARCHAR(64) NOT NULL COMMENT '元数据发布版本',
    edge_id         VARCHAR(192) NOT NULL COMMENT '图谱边稳定编号',
    source_node_id  VARCHAR(192) NOT NULL COMMENT '起点节点编号',
    target_node_id  VARCHAR(192) NOT NULL COMMENT '终点节点编号',
    edge_type       VARCHAR(64) NOT NULL COMMENT '图谱边类型',
    weight          DOUBLE NOT NULL COMMENT '边权重',
    evidence_json   JSON NOT NULL COMMENT '受控关系证据',
    source          VARCHAR(64) NOT NULL COMMENT '边来源',
    created_at      DATETIME NOT NULL COMMENT '创建时间',
    PRIMARY KEY (release_version, edge_id),
    INDEX idx_knowledge_graph_edge_release_source (release_version, source_node_id),
    INDEX idx_knowledge_graph_edge_release_target (release_version, target_node_id),
    INDEX idx_knowledge_graph_edge_release_type (release_version, edge_type)
);
