SET NAMES utf8mb4;
USE meta;

CREATE TABLE IF NOT EXISTS app_user
(
    user_id              VARCHAR(255) PRIMARY KEY,
    username             VARCHAR(255),
    display_name         VARCHAR(255),
    email                VARCHAR(255),
    observed_roles_json  JSON NOT NULL,
    status               VARCHAR(16) NOT NULL,
    first_seen_at        DATETIME(6) NOT NULL,
    last_seen_at         DATETIME(6) NOT NULL,
    disabled_at          DATETIME(6),
    disabled_by          VARCHAR(255),
    updated_at           DATETIME(6) NOT NULL,
    INDEX idx_app_user_status_last_seen (status, last_seen_at),
    INDEX idx_app_user_username (username)
);

CREATE TABLE IF NOT EXISTS app_user_role
(
    id          VARCHAR(36) PRIMARY KEY,
    user_id     VARCHAR(255) NOT NULL,
    role_code   VARCHAR(64) NOT NULL,
    assigned_by VARCHAR(255) NOT NULL,
    assigned_at DATETIME(6) NOT NULL,
    revoked_at  DATETIME(6),
    INDEX idx_app_user_role_user_role_revoked (user_id, role_code, revoked_at)
);

CREATE TABLE IF NOT EXISTS app_user_change
(
    id            VARCHAR(36) PRIMARY KEY,
    request_key   VARCHAR(64) UNIQUE NOT NULL,
    user_id       VARCHAR(255) NOT NULL,
    operation     VARCHAR(32) NOT NULL,
    actor_user_id VARCHAR(255) NOT NULL,
    reason        TEXT NOT NULL,
    before_json   JSON,
    after_json    JSON NOT NULL,
    created_at    DATETIME(6) NOT NULL,
    INDEX idx_app_user_change_user_created (user_id, created_at)
);

INSERT IGNORE INTO authz_policy
    (id, subject, resource, action, effect, version, active, created_by, created_at)
VALUES
    ('00000000-0000-4000-8000-000000000007',
     'role:platform_admin',
     'api:users',
     'manage',
     'allow',
     1,
     TRUE,
     'bootstrap',
     UTC_TIMESTAMP(6));
