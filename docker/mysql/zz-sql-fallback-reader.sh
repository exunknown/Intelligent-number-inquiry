#!/usr/bin/env bash
set -euo pipefail

: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"
: "${SQL_FALLBACK_DB_USER:?SQL_FALLBACK_DB_USER is required}"
: "${SQL_FALLBACK_DB_PASSWORD:?SQL_FALLBACK_DB_PASSWORD is required}"

reader_user_b64="$(printf '%s' "${SQL_FALLBACK_DB_USER}" | base64 | tr -d '\r\n')"
reader_password_b64="$(printf '%s' "${SQL_FALLBACK_DB_PASSWORD}" | base64 | tr -d '\r\n')"

mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
SET @reader_user = CONVERT(FROM_BASE64('${reader_user_b64}') USING utf8mb4);
SET @reader_password = CONVERT(FROM_BASE64('${reader_password_b64}') USING utf8mb4);
SET @account = CONCAT(QUOTE(@reader_user), '@', QUOTE('%'));
SET @create_sql = CONCAT('CREATE USER IF NOT EXISTS ', @account, ' IDENTIFIED BY ', QUOTE(@reader_password));
PREPARE create_stmt FROM @create_sql;
EXECUTE create_stmt;
DEALLOCATE PREPARE create_stmt;
SET @alter_sql = CONCAT('ALTER USER ', @account, ' IDENTIFIED BY ', QUOTE(@reader_password));
PREPARE alter_stmt FROM @alter_sql;
EXECUTE alter_stmt;
DEALLOCATE PREPARE alter_stmt;
SET @revoke_sql = CONCAT('REVOKE ALL PRIVILEGES, GRANT OPTION FROM ', @account);
PREPARE revoke_stmt FROM @revoke_sql;
EXECUTE revoke_stmt;
DEALLOCATE PREPARE revoke_stmt;
SET @grant_sql_1 = CONCAT('GRANT SELECT ON dw.dim_region TO ', @account);
PREPARE grant_stmt_1 FROM @grant_sql_1;
EXECUTE grant_stmt_1;
DEALLOCATE PREPARE grant_stmt_1;
SET @grant_sql_2 = CONCAT('GRANT SELECT ON dw.dim_department TO ', @account);
PREPARE grant_stmt_2 FROM @grant_sql_2;
EXECUTE grant_stmt_2;
DEALLOCATE PREPARE grant_stmt_2;
SET @grant_sql_3 = CONCAT('GRANT SELECT ON dw.dim_customer TO ', @account);
PREPARE grant_stmt_3 FROM @grant_sql_3;
EXECUTE grant_stmt_3;
DEALLOCATE PREPARE grant_stmt_3;
SET @grant_sql_4 = CONCAT('GRANT SELECT ON dw.dim_product TO ', @account);
PREPARE grant_stmt_4 FROM @grant_sql_4;
EXECUTE grant_stmt_4;
DEALLOCATE PREPARE grant_stmt_4;
SET @grant_sql_5 = CONCAT('GRANT SELECT ON dw.dim_date TO ', @account);
PREPARE grant_stmt_5 FROM @grant_sql_5;
EXECUTE grant_stmt_5;
DEALLOCATE PREPARE grant_stmt_5;
SET @grant_sql_6 = CONCAT('GRANT SELECT ON dw.fact_order TO ', @account);
PREPARE grant_stmt_6 FROM @grant_sql_6;
EXECUTE grant_stmt_6;
DEALLOCATE PREPARE grant_stmt_6;
SQL
