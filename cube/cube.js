"use strict";

const DEPARTMENT_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const MEMBER_REFERENCE_PATTERN = /\{([^{}]+)\}/g;

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

function createSemanticModelProvider({ readSnapshot }) {
  if (typeof readSnapshot !== "function") {
    throw new TypeError("readSnapshot must be a function");
  }

  const modelCache = new Map();

  async function readActiveSnapshot() {
    const snapshot = await readSnapshot();
    if (!snapshot || snapshot.status !== "active" || !snapshot.release_version) {
      throw new Error("active semantic release is unavailable");
    }
    return snapshot;
  }

  return {
    async getModel() {
      const snapshot = await readActiveSnapshot();
      const cached = modelCache.get(snapshot.release_version);
      if (cached) {
        return cached;
      }
      const model = buildSemanticModel(snapshot);
      modelCache.set(snapshot.release_version, model);
      return model;
    },

    async schemaVersion() {
      const snapshot = await readActiveSnapshot();
      return snapshot.release_version;
    },
  };
}

async function readActiveSemanticSnapshot() {
  const mysql = require("mysql2/promise");
  const connection = await mysql.createConnection({
    host: process.env.CUBE_META_DB_HOST || process.env.CUBEJS_DB_HOST || "mysql",
    port: Number(
      process.env.CUBE_META_DB_PORT || process.env.CUBEJS_DB_PORT || "3306",
    ),
    database: process.env.CUBE_META_DB_NAME || "meta",
    user: process.env.CUBE_META_DB_USER || process.env.CUBEJS_DB_USER,
    password: process.env.CUBE_META_DB_PASS || process.env.CUBEJS_DB_PASS,
  });

  try {
    const [releaseRows] = await connection.execute(
      `SELECT release_version
       FROM metadata_release
       WHERE active = 1 AND status = 'active'
       ORDER BY activated_at DESC
       LIMIT 1`,
    );
    if (releaseRows.length === 0) {
      return null;
    }
    const releaseVersion = releaseRows[0].release_version;
    const [cubeRows] = await connection.execute(
      `SELECT release_version, cube_name, sql_table, title, description, public
       FROM semantic_cube
       WHERE release_version = ?`,
      [releaseVersion],
    );
    const [joinRows] = await connection.execute(
      `SELECT release_version, cube_name, target_cube_name, sql_expression,
              relationship, editable
       FROM semantic_join
       WHERE release_version = ?`,
      [releaseVersion],
    );
    const [memberRows] = await connection.execute(
      `SELECT member.release_version, member.member_id, member.cube_name,
              member.member_name, member.member_type, member.title,
              member.description, member.data_type, member.source_column_id,
              member.ai_context, member.aliases_json, member.filterable,
              member.groupable, member.status, measure.expression,
              measure.aggregation_type, measure.dependency_members_json,
              dimension.dimension_type, dimension.time_granularity,
              dimension.primary_key
       FROM semantic_member AS member
       LEFT JOIN semantic_measure_definition AS measure
         ON measure.release_version = member.release_version
        AND measure.member_id = member.member_id
       LEFT JOIN semantic_dimension_definition AS dimension
         ON dimension.release_version = member.release_version
        AND dimension.member_id = member.member_id
       WHERE member.release_version = ?
         AND member.status = 'published'`,
      [releaseVersion],
    );
    return {
      release_version: releaseVersion,
      status: "active",
      cubes: cubeRows,
      joins: joinRows,
      members: memberRows.map(normalizeMemberRow),
    };
  } finally {
    await connection.end();
  }
}

function normalizeMemberRow(row) {
  const aliases =
    typeof row.aliases_json === "string"
      ? JSON.parse(row.aliases_json)
      : row.aliases_json || [];
  const member = {
    release_version: row.release_version,
    member_id: row.member_id,
    cube_name: row.cube_name,
    member_name: row.member_name,
    member_type: row.member_type,
    title: row.title,
    description: row.description,
    data_type: row.data_type,
    source_column_id: row.source_column_id,
    ai_context: row.ai_context,
    aliases,
    filterable: Boolean(row.filterable),
    groupable: Boolean(row.groupable),
    status: row.status,
  };
  if (row.member_type === "measure") {
    member.measure = {
      expression: row.expression,
      aggregation_type: row.aggregation_type,
      dependency_members:
        typeof row.dependency_members_json === "string"
          ? JSON.parse(row.dependency_members_json)
          : row.dependency_members_json || [],
    };
  } else {
    member.dimension = {
      dimension_type: row.dimension_type,
      time_granularity: row.time_granularity,
      primary_key: Boolean(row.primary_key),
    };
  }
  return member;
}

function buildSemanticModel(snapshot) {
  const measures = {};
  const dimensions = {};
  for (const member of snapshot.members || []) {
    const metadata = {
      member_id: member.member_id,
      member_type: member.member_type,
      aliases: member.aliases || [],
      ai_context: member.ai_context || "",
      source_column_id: member.source_column_id || null,
    };
    if (member.member_type === "measure") {
      const definition = member.measure;
      measures[member.member_name] = {
        sql: measureSql(member, definition),
        type: definition.aggregation_type,
        title: member.title,
        description: member.description,
        meta: metadata,
      };
    } else {
      dimensions[member.member_name] = {
        sql: physicalColumnSql(member),
        type: member.member_type === "time_dimension"
          ? "time"
          : member.dimension.dimension_type,
        title: member.title,
        description: member.description,
        meta: metadata,
      };
    }
  }
  return {
    releaseVersion: snapshot.release_version,
    ecommerce: {
      title: "电商经营分析",
      description: "已治理的电商订单指标与分析维度",
      public: true,
      measures,
      dimensions,
    },
  };
}

function measureSql(member, definition) {
  if (["sum", "count", "count_distinct"].includes(definition.aggregation_type)) {
    return physicalColumnSql(member);
  }
  return definition.expression.replace(
    MEMBER_REFERENCE_PATTERN,
    (_, reference) => `{${reference.split(".").pop()}}`,
  );
}

function physicalColumnSql(member) {
  if (!member.source_column_id) {
    throw new Error(`source column is required: ${member.member_name}`);
  }
  return member.source_column_id.split(".").pop();
}

module.exports = {
  createSemanticModelProvider,
  queryRewrite,
  readActiveSemanticSnapshot,
};
