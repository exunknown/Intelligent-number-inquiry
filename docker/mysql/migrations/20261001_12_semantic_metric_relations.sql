SET NAMES utf8mb4;
USE meta;

SET @has_calculation_note = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'semantic_member'
      AND column_name = 'calculation_note'
);
SET @migration_sql = IF(
    @has_calculation_note = 0,
    'ALTER TABLE semantic_member ADD COLUMN calculation_note TEXT NULL DEFAULT ('''') AFTER ai_context',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @has_unit = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'semantic_member'
      AND column_name = 'unit'
);
SET @migration_sql = IF(
    @has_unit = 0,
    'ALTER TABLE semantic_member ADD COLUMN unit VARCHAR(64) NULL DEFAULT '''' AFTER calculation_note',
    'SELECT 1'
);
PREPARE migration_stmt FROM @migration_sql;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

CREATE TABLE IF NOT EXISTS semantic_metric_equivalence_group
(
    release_version      VARCHAR(64) NOT NULL,
    group_id              VARCHAR(128) NOT NULL,
    canonical_member_id   VARCHAR(128) NOT NULL,
    group_name            VARCHAR(256) NOT NULL,
    description           TEXT NOT NULL,
    PRIMARY KEY (release_version, group_id),
    UNIQUE KEY uq_semantic_metric_equivalence_canonical
        (release_version, canonical_member_id),
    CONSTRAINT fk_semantic_metric_equivalence_canonical
        FOREIGN KEY (release_version, canonical_member_id)
        REFERENCES semantic_member (release_version, member_id),
    INDEX idx_semantic_metric_equivalence_canonical
        (release_version, canonical_member_id)
);

CREATE TABLE IF NOT EXISTS semantic_metric_equivalence_member
(
    release_version VARCHAR(64) NOT NULL,
    group_id       VARCHAR(128) NOT NULL,
    member_id      VARCHAR(128) NOT NULL,
    match_type     VARCHAR(16) NOT NULL,
    note           TEXT NOT NULL,
    PRIMARY KEY (release_version, group_id, member_id),
    UNIQUE KEY uq_semantic_metric_equivalence_member
        (release_version, member_id),
    CONSTRAINT chk_semantic_metric_equivalence_match_type
        CHECK (match_type IN ('exact', 'compatible')),
    CONSTRAINT fk_semantic_metric_equivalence_group
        FOREIGN KEY (release_version, group_id)
        REFERENCES semantic_metric_equivalence_group (release_version, group_id),
    CONSTRAINT fk_semantic_metric_equivalence_member
        FOREIGN KEY (release_version, member_id)
        REFERENCES semantic_member (release_version, member_id),
    INDEX idx_semantic_metric_equivalence_member
        (release_version, member_id)
);

CREATE TABLE IF NOT EXISTS semantic_metric_attachment
(
    release_version    VARCHAR(64) NOT NULL,
    primary_member_id  VARCHAR(128) NOT NULL,
    attached_member_id VARCHAR(128) NOT NULL,
    relation_type      VARCHAR(32) NOT NULL,
    display_order      INT NOT NULL DEFAULT 0,
    default_visible    BOOLEAN NOT NULL DEFAULT 0,
    note               TEXT NOT NULL,
    PRIMARY KEY (release_version, primary_member_id, attached_member_id),
    CONSTRAINT chk_semantic_metric_attachment_relation_type
        CHECK (
            relation_type IN (
                'supporting',
                'comparison',
                'efficiency',
                'breakdown'
            )
        ),
    CONSTRAINT fk_semantic_metric_attachment_primary
        FOREIGN KEY (release_version, primary_member_id)
        REFERENCES semantic_member (release_version, member_id),
    CONSTRAINT fk_semantic_metric_attachment_attached
        FOREIGN KEY (release_version, attached_member_id)
        REFERENCES semantic_member (release_version, member_id),
    INDEX idx_semantic_metric_attachment_attached
        (release_version, attached_member_id)
);
