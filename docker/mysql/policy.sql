USE meta;

CREATE TABLE IF NOT EXISTS authz_policy_version
(
    id      TINYINT PRIMARY KEY,
    version BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS authz_policy
(
    id         VARCHAR(36) PRIMARY KEY,
    subject    VARCHAR(255) NOT NULL,
    resource   VARCHAR(255) NOT NULL,
    action     VARCHAR(32) NOT NULL,
    effect     VARCHAR(16) NOT NULL,
    version    BIGINT NOT NULL,
    active     BOOLEAN NOT NULL,
    created_by VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    revoked_at DATETIME(6),
    INDEX idx_authz_policy_subject (subject),
    INDEX idx_authz_policy_resource (resource),
    INDEX idx_authz_policy_active (active)
);

CREATE TABLE IF NOT EXISTS authz_policy_change
(
    id            VARCHAR(36) PRIMARY KEY,
    request_key   VARCHAR(64) NOT NULL UNIQUE,
    operation     VARCHAR(16) NOT NULL,
    policy_id     VARCHAR(36) NOT NULL,
    actor_user_id VARCHAR(255) NOT NULL,
    reason        TEXT NOT NULL,
    before_json   JSON,
    after_json    JSON NOT NULL,
    created_at    DATETIME(6) NOT NULL,
    INDEX idx_authz_change_policy (policy_id)
);

INSERT INTO authz_policy_version (id, version)
VALUES (1, 1)
ON DUPLICATE KEY UPDATE version = GREATEST(version, VALUES(version));

INSERT IGNORE INTO authz_policy
    (id, subject, resource, action, effect, version, active, created_by, created_at)
VALUES
    ('00000000-0000-4000-8000-000000000001', 'role:platform_admin', 'api:authz-policies', 'manage', 'allow', 1, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000002', 'role:metric_governor', 'api:metrics', 'read', 'allow', 1, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000003', 'role:metric_governor', 'api:metric-candidates', 'read', 'allow', 1, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000004', 'role:metric_governor', 'api:metric-candidates', 'review', 'allow', 1, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000005', 'role:analyst', 'api:query', 'execute', 'allow', 1, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000006', 'role:analyst', 'api:metrics', 'read', 'allow', 1, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000007', 'role:platform_admin', 'api:users', 'manage', 'allow', 1, TRUE, 'bootstrap', UTC_TIMESTAMP(6));
