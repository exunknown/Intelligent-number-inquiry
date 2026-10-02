import assert from "node:assert/strict";
import test from "node:test";

import semanticModel from "../semantic-model.js";

const {
  createSemanticModelProvider,
  createSemanticModelRepositoryFactory,
  buildSemanticSchemaSource,
} = semanticModel;

test("provider caches the compiled model by active release version", async () => {
  const snapshots = [
    {
      release_version: "release-1",
      status: "active",
      members: [],
      cubes: [],
      joins: [],
    },
    {
      release_version: "release-1",
      status: "active",
      members: [],
      cubes: [],
      joins: [],
    },
    {
      release_version: "release-2",
      status: "active",
      members: [],
      cubes: [],
      joins: [],
    },
  ];
  let reads = 0;
  const provider = createSemanticModelProvider({
    readSnapshot: async () => snapshots[reads++],
  });

  const first = await provider.getModel();
  const second = await provider.getModel();
  const third = await provider.getModel();

  assert.equal(first.releaseVersion, "release-1");
  assert.strictEqual(first, second);
  assert.equal(third.releaseVersion, "release-2");
  assert.notStrictEqual(second, third);
  assert.equal(reads, 3);
});

test("provider rejects drafts and missing active releases", async () => {
  const provider = createSemanticModelProvider({
    readSnapshot: async () => ({
      release_version: "draft-1",
      status: "draft",
      members: [],
      cubes: [],
      joins: [],
    }),
  });

  await assert.rejects(provider.getModel(), /active semantic release/);
});

test("repository factory exposes only the active snapshot as a Cube schema", async () => {
  const factory = createSemanticModelRepositoryFactory({
    readSnapshot: async () => ({
      release_version: "release-3",
      status: "active",
      cubes: [
        {
          cube_name: "orders",
          sql_table: "dw.fact_order",
          title: "订单",
          description: "订单事实",
          public: false,
        },
      ],
      joins: [],
      members: [],
    }),
  });

  const repository = factory({ requestId: "test" });
  const files = await repository.dataSchemaFiles();

  assert.equal(files.length, 1);
  assert.equal(files[0].fileName, "semantic-model.js");
  assert.match(files[0].content, /release-3/);
  assert.match(files[0].content, /dw\.fact_order/);
});

test("schema source rejects non-active snapshots", () => {
  assert.throws(
    () =>
      buildSemanticSchemaSource({
        release_version: "draft-1",
        status: "draft",
        cubes: [],
        joins: [],
        members: [],
      }),
    /active semantic release/,
  );
});

test("schema source keeps physical cubes and exposes the semantic view", () => {
  const content = buildSemanticSchemaSource({
    release_version: "release-4",
    status: "active",
    cubes: [
      {
        cube_name: "customers",
        sql_table: "dw.dim_customer",
        title: "客户",
        description: "客户维度",
        public: false,
      },
      {
        cube_name: "orders",
        sql_table: "dw.fact_order",
        title: "订单",
        description: "订单事实",
        public: false,
      },
      {
        cube_name: "ecommerce",
        sql_table: "",
        title: "电商经营分析",
        description: "公开语义视图",
        public: true,
      },
    ],
    joins: [
      {
        release_version: "release-4",
        cube_name: "orders",
        target_cube_name: "customers",
        sql_expression: "{CUBE}.customer_id = {customers}.customer_id",
        relationship: "many_to_one",
      },
    ],
    members: [
      {
        release_version: "release-4",
        member_id: "measure:ecommerce:gmv",
        cube_name: "ecommerce",
        member_name: "gmv",
        member_type: "measure",
        title: "销售额",
        description: "成交金额",
        data_type: "number",
        source_column_id: "fact_order.order_amount",
        ai_context: "",
        aliases: [],
        filterable: false,
        groupable: false,
        status: "published",
        measure: {
          expression: "fact_order.order_amount",
          aggregation_type: "sum",
          dependency_members: [],
        },
      },
      {
        release_version: "release-4",
        member_id: "dimension:ecommerce:customer_name",
        cube_name: "ecommerce",
        member_name: "customer_name",
        member_type: "dimension",
        title: "客户名称",
        description: "客户名称",
        data_type: "string",
        source_column_id: "dim_customer.customer_name",
        ai_context: "",
        aliases: [],
        filterable: true,
        groupable: true,
        status: "published",
        dimension: {
          dimension_type: "string",
          time_granularity: null,
          primary_key: false,
        },
      },
    ],
  });

  assert.match(content, /cube\("orders"/);
  assert.match(content, /cube\("customers"/);
  assert.match(content, /view\("ecommerce"/);
  assert.match(content, /dw\.fact_order/);
  assert.match(
    content,
    /"order_id": \{"sql": "order_id".*"primary_key": true/,
  );
  assert.match(content, /\{orders\}\.customer_id/);
  assert.match(content, /"join_path": "orders"/);
  assert.match(content, /"join_path": "orders\.customers"/);
  assert.doesNotMatch(content, /cube\("ecommerce"/);
});
