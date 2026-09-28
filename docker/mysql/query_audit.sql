SET NAMES utf8mb4;
USE meta;

CREATE TABLE IF NOT EXISTS query_audit
(
    id           VARCHAR(36) PRIMARY KEY,
    request_id   VARCHAR(64),
    created_at   DATETIME NOT NULL,
    query_text   TEXT NOT NULL,
    query_mode   VARCHAR(16),
    route_reason VARCHAR(64),
    metric_query JSON,
    cube_query   JSON,
    sql_text     TEXT,
    outcome      VARCHAR(32) NOT NULL,
    error_code   VARCHAR(64),
    verified     BOOLEAN,
    duration_ms  INT NOT NULL
);
