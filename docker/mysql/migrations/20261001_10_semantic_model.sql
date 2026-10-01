SET NAMES utf8mb4;
USE meta;

CREATE TABLE IF NOT EXISTS semantic_cube
(
    release_version VARCHAR(64) NOT NULL,
    cube_name       VARCHAR(128) NOT NULL,
    sql_table       VARCHAR(256) NOT NULL,
    title           VARCHAR(256) NOT NULL,
    description     TEXT NOT NULL,
    public          TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (release_version, cube_name)
);

CREATE TABLE IF NOT EXISTS semantic_join
(
    release_version  VARCHAR(64) NOT NULL,
    cube_name        VARCHAR(128) NOT NULL,
    target_cube_name VARCHAR(128) NOT NULL,
    sql_expression   TEXT NOT NULL,
    relationship     VARCHAR(32) NOT NULL,
    editable         TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (release_version, cube_name, target_cube_name)
);

CREATE TABLE IF NOT EXISTS semantic_member
(
    release_version  VARCHAR(64) NOT NULL,
    member_id        VARCHAR(128) NOT NULL,
    cube_name        VARCHAR(128) NOT NULL,
    member_name      VARCHAR(128) NOT NULL,
    member_type      VARCHAR(32) NOT NULL,
    title            VARCHAR(256) NOT NULL,
    description      TEXT NOT NULL,
    data_type        VARCHAR(64) NOT NULL,
    source_column_id VARCHAR(128) NULL,
    ai_context       TEXT NOT NULL,
    aliases_json     JSON NOT NULL,
    filterable       TINYINT(1) NOT NULL DEFAULT 0,
    groupable        TINYINT(1) NOT NULL DEFAULT 0,
    status           VARCHAR(16) NOT NULL,
    created_by       VARCHAR(128) NOT NULL,
    updated_by       VARCHAR(128) NOT NULL,
    created_at       DATETIME NOT NULL,
    updated_at       DATETIME NOT NULL,
    PRIMARY KEY (release_version, member_id),
    INDEX idx_semantic_member_release_type (release_version, member_type),
    INDEX idx_semantic_member_release_status (release_version, status)
);

CREATE TABLE IF NOT EXISTS semantic_measure_definition
(
    release_version         VARCHAR(64) NOT NULL,
    member_id               VARCHAR(128) NOT NULL,
    expression              TEXT NOT NULL,
    aggregation_type        VARCHAR(32) NOT NULL,
    dependency_members_json JSON NOT NULL,
    PRIMARY KEY (release_version, member_id),
    CONSTRAINT fk_semantic_measure_member
        FOREIGN KEY (release_version, member_id)
        REFERENCES semantic_member (release_version, member_id)
);

CREATE TABLE IF NOT EXISTS semantic_dimension_definition
(
    release_version  VARCHAR(64) NOT NULL,
    member_id        VARCHAR(128) NOT NULL,
    dimension_type   VARCHAR(32) NOT NULL,
    time_granularity VARCHAR(32) NULL,
    primary_key      TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (release_version, member_id),
    CONSTRAINT fk_semantic_dimension_member
        FOREIGN KEY (release_version, member_id)
        REFERENCES semantic_member (release_version, member_id)
);

CREATE TABLE IF NOT EXISTS semantic_model_draft
(
    draft_id        VARCHAR(36) NOT NULL,
    release_version VARCHAR(64) NOT NULL,
    status          VARCHAR(32) NOT NULL,
    snapshot_json   JSON NOT NULL,
    created_by      VARCHAR(128) NOT NULL,
    updated_by      VARCHAR(128) NOT NULL,
    review_note     TEXT NULL,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL,
    PRIMARY KEY (draft_id),
    INDEX idx_semantic_draft_status (status, updated_at)
);

CREATE TABLE IF NOT EXISTS semantic_model_change
(
    change_id       VARCHAR(36) NOT NULL,
    draft_id        VARCHAR(36) NOT NULL,
    action          VARCHAR(32) NOT NULL,
    actor_id        VARCHAR(128) NOT NULL,
    reason          TEXT NOT NULL,
    idempotency_key VARCHAR(36) NOT NULL,
    created_at      DATETIME NOT NULL,
    PRIMARY KEY (change_id),
    UNIQUE KEY uq_semantic_change_idempotency (idempotency_key),
    INDEX idx_semantic_change_draft (draft_id, created_at)
);
