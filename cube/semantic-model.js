"use strict";

const MEMBER_REFERENCE_PATTERN = /\{([^{}]+)\}/g;

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

function createSemanticModelRepositoryFactory({ readSnapshot }) {
  if (typeof readSnapshot !== "function") {
    throw new TypeError("readSnapshot must be a function");
  }

  return () => ({
    localPath: () => process.cwd(),
    dataSchemaFiles: async () => [
      {
        fileName: "semantic-model.js",
        content: buildSemanticSchemaSource(await readSnapshot()),
        isModule: false,
      },
    ],
  });
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
        type:
          member.member_type === "time_dimension"
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

function buildSemanticSchemaSource(snapshot) {
  if (!snapshot || snapshot.status !== "active" || !snapshot.release_version) {
    throw new Error("active semantic release is unavailable");
  }

  const physicalCubes = (snapshot.cubes || []).filter(
    (cube) => cube.cube_name !== "ecommerce" && cube.sql_table,
  );
  if (physicalCubes.length === 0) {
    throw new Error("active semantic release has no physical source cube");
  }

  const rootCube = selectRootCube(snapshot, physicalCubes);
  const membersByCube = new Map(
    physicalCubes.map((cube) => [cube.cube_name, []]),
  );
  for (const member of snapshot.members || []) {
    const cubeName = resolveMemberCube(member, snapshot.members, physicalCubes);
    if (!cubeName) {
      throw new Error(`no physical cube for semantic member: ${member.member_name}`);
    }
    membersByCube.get(cubeName).push(member);
  }

  const sourceLines = physicalCubes.map((cube) => {
    const measures = {};
    const dimensions = {};
    for (const member of membersByCube.get(cube.cube_name)) {
      const metadata = memberMetadata(member);
      if (member.member_type === "measure") {
        measures[member.member_name] = {
          sql: cubeSqlExpression(
            measureSql(member, member.measure),
            cube.cube_name,
          ),
          type: member.measure.aggregation_type,
          title: member.title,
          description: member.description,
          meta: metadata,
        };
      } else {
        dimensions[member.member_name] = {
          sql: cubeSqlExpression(dimensionSql(member), cube.cube_name),
          type:
            member.member_type === "time_dimension"
              ? "time"
              : member.dimension.dimension_type,
          title: member.title,
          description: member.description,
          meta: metadata,
        };
      }
    }
    addPhysicalPrimaryKey(cube, dimensions);

    const joins = {};
    for (const join of snapshot.joins || []) {
      if (join.cube_name === cube.cube_name) {
        joins[join.target_cube_name] = {
          sql: cubeSqlExpression(join.sql_expression, cube.cube_name),
          relationship: join.relationship,
        };
      }
    }

    const cubeDefinition = {
      sql_table: cube.sql_table,
      public: false,
      joins,
      measures,
      dimensions,
    };
    if (cube.title) {
      cubeDefinition.title = cube.title;
    }
    if (cube.description) {
      cubeDefinition.description = cube.description;
    }
    return `cube(${JSON.stringify(cube.cube_name)}, ${serializeJavaScriptValue(cubeDefinition)});`;
  });

  const viewCubes = [];
  for (const [cubeName, members] of membersByCube) {
    if (members.length === 0) {
      continue;
    }
    viewCubes.push({
      join_path: cubeJoinPath(rootCube.cube_name, cubeName, snapshot.joins),
      includes: members.map((member) => member.member_name),
    });
  }
  viewCubes.sort((left, right) => left.join_path.localeCompare(right.join_path));

  sourceLines.push(
    `view("ecommerce", ${serializeJavaScriptValue({
      title: "电商经营分析",
      description: "已治理的电商订单指标与分析维度",
      public: true,
      cubes: viewCubes,
      meta: {
        semantic_release_version: snapshot.release_version,
      },
    })});`,
  );

  return [
    "// Generated from metadata_release.active. Do not edit.",
    ...sourceLines,
    "",
  ].join("\n");
}

function memberMetadata(member) {
  return {
    member_id: member.member_id,
    member_type: member.member_type,
    aliases: member.aliases || [],
    ai_context: member.ai_context || "",
    source_column_id: member.source_column_id || null,
  };
}

function tableName(sqlTable) {
  return sqlTable.split(".").pop();
}

function sourceTableName(member) {
  return member.source_column_id?.split(".")[0] || null;
}

function addPhysicalPrimaryKey(cube, dimensions) {
  const primaryKey = {
    customers: "customer_id",
    dates: "date_id",
    departments: "department_id",
    orders: "order_id",
    products: "product_id",
    regions: "region_id",
  }[cube.cube_name];
  if (!primaryKey || dimensions[primaryKey]) {
    return;
  }
  dimensions[primaryKey] = {
    sql: primaryKey,
    type: cube.cube_name === "dates" ? "number" : "string",
    primary_key: true,
  };
}

function selectRootCube(snapshot, physicalCubes) {
  const measureTables = new Set(
    (snapshot.members || [])
      .filter((member) => member.member_type === "measure")
      .map(sourceTableName)
      .filter(Boolean),
  );
  return (
    physicalCubes.find((cube) => measureTables.has(tableName(cube.sql_table))) ||
    physicalCubes.find((cube) => cube.cube_name === "orders") ||
    physicalCubes[0]
  );
}

function resolveMemberCube(member, allMembers, physicalCubes) {
  const sourceTable = sourceTableName(member);
  if (sourceTable) {
    const directMatch = physicalCubes.find(
      (cube) => tableName(cube.sql_table) === sourceTable,
    );
    if (directMatch) {
      return directMatch.cube_name;
    }
  }

  for (const dependency of member.measure?.dependency_members || []) {
    const dependencyMember = allMembers.find(
      (candidate) =>
        candidate.member_id === dependency ||
        `${candidate.cube_name}.${candidate.member_name}` === dependency,
    );
    if (dependencyMember) {
      const dependencyCube = resolveMemberCube(
        dependencyMember,
        allMembers,
        physicalCubes,
      );
      if (dependencyCube) {
        return dependencyCube;
      }
    }
  }
  return null;
}

function cubeJoinPath(rootCubeName, targetCubeName, joins) {
  if (rootCubeName === targetCubeName) {
    return rootCubeName;
  }
  const queue = [{ cubeName: rootCubeName, path: [rootCubeName] }];
  const visited = new Set([rootCubeName]);
  while (queue.length > 0) {
    const current = queue.shift();
    for (const join of joins || []) {
      if (join.cube_name !== current.cubeName || visited.has(join.target_cube_name)) {
        continue;
      }
      const path = [...current.path, join.target_cube_name];
      if (join.target_cube_name === targetCubeName) {
        return path.join(".");
      }
      visited.add(join.target_cube_name);
      queue.push({ cubeName: join.target_cube_name, path });
    }
  }
  throw new Error(
    `no join path from ${rootCubeName} to semantic member cube ${targetCubeName}`,
  );
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

function dimensionSql(member) {
  const column = physicalColumnSql(member);
  if (member.member_type === "time_dimension") {
    return `STR_TO_DATE(CAST({CUBE}.${column} AS CHAR), '%Y%m%d')`;
  }
  return column;
}

function cubeSqlExpression(expression, cubeName) {
  return {
    __cubeSql: expression.replace(
      /\{([^{}]+)\}/g,
      (_, reference) => `\${${reference === "CUBE" ? cubeName : reference}}`,
    ),
  };
}

function serializeJavaScriptValue(value) {
  if (value && typeof value === "object" && "__cubeSql" in value) {
    return `\`${value.__cubeSql.replaceAll("`", "\\`")}\``;
  }
  if (Array.isArray(value)) {
    return `[${value.map(serializeJavaScriptValue).join(", ")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.entries(value)
      .map(
        ([key, nestedValue]) =>
          `${JSON.stringify(key)}: ${serializeJavaScriptValue(nestedValue)}`,
      )
      .join(", ")}}`;
  }
  return JSON.stringify(value);
}

function physicalColumnSql(member) {
  if (!member.source_column_id) {
    throw new Error(`source column is required: ${member.member_name}`);
  }
  return member.source_column_id.split(".").pop();
}

module.exports = {
  buildSemanticModel,
  buildSemanticSchemaSource,
  createSemanticModelProvider,
  createSemanticModelRepositoryFactory,
  normalizeMemberRow,
  readActiveSemanticSnapshot,
};
