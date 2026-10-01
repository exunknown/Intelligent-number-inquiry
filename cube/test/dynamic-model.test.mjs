import assert from "node:assert/strict";
import test from "node:test";

import cubeConfig from "../cube.js";

const { createSemanticModelProvider } = cubeConfig;

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
