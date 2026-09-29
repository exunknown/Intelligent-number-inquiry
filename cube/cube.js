"use strict";

const DEPARTMENT_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

function queryRewrite(query, { securityContext } = {}) {
  const departmentIds = securityContext?.department_ids;
  if (!Array.isArray(departmentIds) || departmentIds.length === 0) {
    throw new Error("Department scope is required");
  }
  if (
    departmentIds.some(
      (value) =>
        typeof value !== "string" || !DEPARTMENT_ID_PATTERN.test(value),
    )
  ) {
    throw new Error("Department scope is invalid");
  }

  const authorizedDepartments = [...new Set(departmentIds)].sort();
  return {
    ...query,
    filters: [
      ...(Array.isArray(query.filters) ? query.filters : []),
      {
        member: "ecommerce.department_id",
        operator: "equals",
        values: authorizedDepartments,
      },
    ],
  };
}

module.exports = { queryRewrite };
