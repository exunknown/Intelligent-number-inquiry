-- Existing-volume migration. Reuses the idempotent schema and bootstrap statements.
SOURCE /docker-entrypoint-initdb.d/policy.sql;
