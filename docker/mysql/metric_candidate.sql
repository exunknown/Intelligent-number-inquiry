SET NAMES utf8mb4;
USE meta;

CREATE TABLE IF NOT EXISTS metric_candidate
(
    id               VARCHAR(36) PRIMARY KEY,
    query_hash       VARCHAR(64) NOT NULL,
    query_text       TEXT NOT NULL,
    route_reason     VARCHAR(64),
    source_request_id VARCHAR(64),
    status           VARCHAR(16) NOT NULL,
    occurrence_count INT NOT NULL,
    first_seen_at    DATETIME NOT NULL,
    last_seen_at     DATETIME NOT NULL,
    reviewed_at      DATETIME,
    review_note      TEXT,
    UNIQUE KEY uk_metric_candidate_query_hash (query_hash),
    KEY idx_metric_candidate_status_last_seen (status, last_seen_at)
);

SET @add_reviewed_at = (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE metric_candidate ADD COLUMN reviewed_at DATETIME NULL',
        'SELECT 1'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'metric_candidate'
      AND column_name = 'reviewed_at'
);
PREPARE add_reviewed_at_stmt FROM @add_reviewed_at;
EXECUTE add_reviewed_at_stmt;
DEALLOCATE PREPARE add_reviewed_at_stmt;

SET @add_review_note = (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE metric_candidate ADD COLUMN review_note TEXT NULL',
        'SELECT 1'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'metric_candidate'
      AND column_name = 'review_note'
);
PREPARE add_review_note_stmt FROM @add_review_note;
EXECUTE add_review_note_stmt;
DEALLOCATE PREPARE add_review_note_stmt;
