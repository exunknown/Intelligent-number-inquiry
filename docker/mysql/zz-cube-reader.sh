#!/usr/bin/env bash
set -euo pipefail

: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"
: "${CUBE_DB_USER:?CUBE_DB_USER is required}"
: "${CUBE_DB_PASSWORD:?CUBE_DB_PASSWORD is required}"

cube_user_b64="$(printf '%s' "${CUBE_DB_USER}" | base64 | tr -d '\r\n')"
cube_password_b64="$(printf '%s' "${CUBE_DB_PASSWORD}" | base64 | tr -d '\r\n')"

mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
SET @cube_user = CONVERT(FROM_BASE64('${cube_user_b64}') USING utf8mb4);
SET @cube_password = CONVERT(FROM_BASE64('${cube_password_b64}') USING utf8mb4);
SET @account = CONCAT(QUOTE(@cube_user), '@', QUOTE('%'));
SET @drop_sql = CONCAT('DROP USER IF EXISTS ', @account);
PREPARE drop_stmt FROM @drop_sql;
EXECUTE drop_stmt;
DEALLOCATE PREPARE drop_stmt;
SET @create_sql = CONCAT('CREATE USER ', @account, ' IDENTIFIED BY ', QUOTE(@cube_password));
PREPARE create_stmt FROM @create_sql;
EXECUTE create_stmt;
DEALLOCATE PREPARE create_stmt;
SET @grant_sql = CONCAT('GRANT SELECT ON dw.* TO ', @account);
PREPARE grant_stmt FROM @grant_sql;
EXECUTE grant_stmt;
DEALLOCATE PREPARE grant_stmt;
SQL
