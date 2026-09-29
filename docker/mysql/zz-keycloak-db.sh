#!/usr/bin/env bash
set -euo pipefail

: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"
: "${KEYCLOAK_DB_USER:?KEYCLOAK_DB_USER is required}"
: "${KEYCLOAK_DB_PASSWORD:?KEYCLOAK_DB_PASSWORD is required}"

keycloak_user_b64="$(printf '%s' "${KEYCLOAK_DB_USER}" | base64 | tr -d '\r\n')"
keycloak_password_b64="$(printf '%s' "${KEYCLOAK_DB_PASSWORD}" | base64 | tr -d '\r\n')"

mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE DATABASE IF NOT EXISTS keycloak CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
SET @keycloak_user = CONVERT(FROM_BASE64('${keycloak_user_b64}') USING utf8mb4);
SET @keycloak_password = CONVERT(FROM_BASE64('${keycloak_password_b64}') USING utf8mb4);
SET @account = CONCAT(QUOTE(@keycloak_user), '@', QUOTE('%'));
SET @drop_sql = CONCAT('DROP USER IF EXISTS ', @account);
PREPARE drop_stmt FROM @drop_sql;
EXECUTE drop_stmt;
DEALLOCATE PREPARE drop_stmt;
SET @create_sql = CONCAT('CREATE USER ', @account, ' IDENTIFIED BY ', QUOTE(@keycloak_password));
PREPARE create_stmt FROM @create_sql;
EXECUTE create_stmt;
DEALLOCATE PREPARE create_stmt;
SET @grant_sql = CONCAT('GRANT ALL PRIVILEGES ON keycloak.* TO ', @account);
PREPARE grant_stmt FROM @grant_sql;
EXECUTE grant_stmt;
DEALLOCATE PREPARE grant_stmt;
SQL
