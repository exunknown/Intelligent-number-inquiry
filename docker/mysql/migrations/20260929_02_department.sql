USE dw;

CREATE TABLE IF NOT EXISTS dim_department
(
    department_id   VARCHAR(20) PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL
);

INSERT INTO dim_department (department_id, department_name, status)
VALUES ('D001', '直营网销部', 'active'),
       ('D002', '渠道销售部', 'active'),
       ('D003', '企业客户部', 'active')
ON DUPLICATE KEY UPDATE
    department_name = VALUES(department_name),
    status = VALUES(status);

SET @has_department_column = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = 'dw'
      AND table_name = 'fact_order'
      AND column_name = 'department_id'
);
SET @add_column_sql = IF(
    @has_department_column = 0,
    'ALTER TABLE fact_order ADD COLUMN department_id VARCHAR(20) NULL',
    'SELECT 1'
);
PREPARE add_column_stmt FROM @add_column_sql;
EXECUTE add_column_stmt;
DEALLOCATE PREPARE add_column_stmt;

UPDATE fact_order
SET department_id = CASE MOD(date_id, 3)
    WHEN 0 THEN 'D001'
    WHEN 1 THEN 'D002'
    ELSE 'D003'
END
WHERE department_id IS NULL;

DROP PROCEDURE IF EXISTS validate_department_backfill;
DELIMITER //
CREATE PROCEDURE validate_department_backfill()
BEGIN
    IF EXISTS (SELECT 1 FROM fact_order WHERE department_id IS NULL) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'fact_order.department_id backfill is incomplete';
    END IF;
END//
DELIMITER ;
CALL validate_department_backfill();
DROP PROCEDURE validate_department_backfill;

ALTER TABLE fact_order MODIFY department_id VARCHAR(20) NOT NULL;

SET @has_department_index = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = 'dw'
      AND table_name = 'fact_order'
      AND index_name = 'idx_fact_order_department'
);
SET @add_index_sql = IF(
    @has_department_index = 0,
    'ALTER TABLE fact_order ADD INDEX idx_fact_order_department (department_id)',
    'SELECT 1'
);
PREPARE add_index_stmt FROM @add_index_sql;
EXECUTE add_index_stmt;
DEALLOCATE PREPARE add_index_stmt;

SET @has_department_fk = (
    SELECT COUNT(*)
    FROM information_schema.table_constraints
    WHERE constraint_schema = 'dw'
      AND table_name = 'fact_order'
      AND constraint_name = 'fk_fact_order_department'
      AND constraint_type = 'FOREIGN KEY'
);
SET @add_fk_sql = IF(
    @has_department_fk = 0,
    'ALTER TABLE fact_order ADD CONSTRAINT fk_fact_order_department FOREIGN KEY (department_id) REFERENCES dim_department (department_id)',
    'SELECT 1'
);
PREPARE add_fk_stmt FROM @add_fk_sql;
EXECUTE add_fk_stmt;
DEALLOCATE PREPARE add_fk_stmt;
