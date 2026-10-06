USE meta;

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
