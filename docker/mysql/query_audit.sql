SET NAMES utf8mb4;
USE meta;

CREATE TABLE IF NOT EXISTS query_audit
(
    id           VARCHAR(36) PRIMARY KEY,
    request_id   VARCHAR(64),
    created_at   DATETIME NOT NULL,
    user_id      VARCHAR(255) NOT NULL,
    username     VARCHAR(255),
    roles        JSON NOT NULL,
    policy_version BIGINT UNSIGNED NOT NULL,
    allowed_department_ids JSON NOT NULL,
    authz_outcome VARCHAR(32) NOT NULL,
    query_text   TEXT NOT NULL,
    query_mode   VARCHAR(16),
    route_reason VARCHAR(64),
    metric_query JSON,
    cube_query   JSON,
    sql_text     TEXT,
    outcome      VARCHAR(32) NOT NULL,
    error_code   VARCHAR(64),
    verified     BOOLEAN,
    duration_ms  INT NOT NULL,
    INDEX idx_query_audit_user_created (user_id, created_at),
    INDEX idx_query_audit_policy_created (policy_version, created_at)
);
