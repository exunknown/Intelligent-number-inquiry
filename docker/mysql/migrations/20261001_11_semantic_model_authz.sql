SET NAMES utf8mb4;
USE meta;

SET @semantic_policy_version = COALESCE(
    (SELECT version FROM authz_policy_version WHERE id = 1),
    0
) + 1;

INSERT IGNORE INTO authz_policy
    (id, subject, resource, action, effect, version, active, created_by, created_at)
VALUES
    ('00000000-0000-4000-8000-000000000008', 'role:platform_admin', 'api:semantic-model', 'read', 'allow', @semantic_policy_version, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000009', 'role:platform_admin', 'api:semantic-model', 'edit', 'allow', @semantic_policy_version, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000010', 'role:platform_admin', 'api:semantic-model', 'review', 'allow', @semantic_policy_version, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000011', 'role:platform_admin', 'api:semantic-model', 'publish', 'allow', @semantic_policy_version, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000012', 'role:platform_admin', 'api:semantic-model', 'rollback', 'allow', @semantic_policy_version, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000013', 'role:metric_governor', 'api:semantic-model', 'read', 'allow', @semantic_policy_version, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000014', 'role:metric_governor', 'api:semantic-model', 'edit', 'allow', @semantic_policy_version, TRUE, 'bootstrap', UTC_TIMESTAMP(6)),
    ('00000000-0000-4000-8000-000000000015', 'role:metric_governor', 'api:semantic-model', 'review', 'allow', @semantic_policy_version, TRUE, 'bootstrap', UTC_TIMESTAMP(6));

SET @semantic_policy_rows = ROW_COUNT();

UPDATE authz_policy_version
SET version = version + IF(@semantic_policy_rows > 0, 1, 0)
WHERE id = 1;
