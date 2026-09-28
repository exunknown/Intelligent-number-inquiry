import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

from app.entities.cube_member import (
    CubeMember,
    extract_cube_members,
    iter_member_embedding_entries,
)
from app.services.cube_metadata_service import CubeMetadataService


def _metadata(source_column_id: str = "dim_region.region_name") -> dict:
    return {
        "compilerId": "compiler-42",
        "cubes": [
            {
                "name": "ecommerce",
                "public": True,
                "measures": [
                    {
                        "name": "ecommerce.gmv",
                        "type": "number",
                        "title": "销售额",
                        "description": "所有订单成交金额之和",
                        "meta": {
                            "aliases": ["GMV", "成交额"],
                            "ai_context": "统计成交金额，不代表利润",
                            "source_column_id": "fact_order.order_amount",
                            "filterable": False,
                        },
                    }
                ],
                "dimensions": [
                    {
                        "name": "ecommerce.region_name",
                        "type": "string",
                        "title": "大区",
                        "description": "订单所属大区",
                        "meta": {
                            "aliases": ["地区", "区域"],
                            "ai_context": "用于大区分析",
                            "source_column_id": source_column_id,
                            "filterable": True,
                        },
                    },
                    {
                        "name": "ecommerce.order_date",
                        "type": "time",
                        "title": "订单日期",
                        "description": "订单发生日期",
                        "meta": {
                            "aliases": ["日期"],
                            "ai_context": "用于按时间筛选",
                            "source_column_id": "dim_date.date_id",
                            "filterable": True,
                        },
                    },
                ],
            },
            {
                "name": "internal_orders",
                "public": False,
                "measures": [
                    {
                        "name": "internal_orders.secret_revenue",
                        "type": "number",
                        "title": "内部收入",
                        "description": "不得同步的内部指标",
                    }
                ],
                "dimensions": [],
            },
        ],
    }


class CubeMemberExtractionTest(unittest.TestCase):
    def test_extracts_only_governed_view_members_in_order(self) -> None:
        members, compiler_id = extract_cube_members(_metadata(), "ecommerce")

        self.assertEqual("compiler-42", compiler_id)
        self.assertEqual(
            [
                "ecommerce.gmv",
                "ecommerce.region_name",
                "ecommerce.order_date",
            ],
            [member.name for member in members],
        )
        self.assertEqual("measure", members[0].member_type)
        self.assertEqual("time_dimension", members[2].member_type)
        self.assertEqual(["地区", "区域"], members[1].aliases)
        self.assertTrue(members[1].filterable)
        with self.assertRaises(FrozenInstanceError):
            members[0].title = "changed"

    def test_embedding_entry_ids_are_stable_and_aliases_are_unique(self) -> None:
        member = CubeMember(
            name="ecommerce.region_name",
            cube_name="ecommerce",
            member_type="dimension",
            data_type="string",
            title="大区",
            description="订单所属大区",
            aliases=["地区", "区域", "地区"],
            ai_context="用于大区分析",
            source_column_id="dim_region.region_name",
            filterable=True,
        )

        first = iter_member_embedding_entries(member)
        second = iter_member_embedding_entries(member)

        self.assertEqual([entry.id for entry in first], [entry.id for entry in second])
        self.assertEqual(
            ["name", "title", "description", "alias", "alias", "ai_context"],
            [entry.embedding_kind for entry in first],
        )
        self.assertEqual(2, sum(entry.embedding_kind == "alias" for entry in first))

    def test_invalid_source_column_id_is_rejected_during_extraction(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_column_id"):
            extract_cube_members(_metadata("malformed"), "ecommerce")

    def test_missing_description_and_duplicate_names_are_rejected(self) -> None:
        missing_description = _metadata()
        del missing_description["cubes"][0]["measures"][0]["description"]
        with self.assertRaisesRegex(ValueError, "description"):
            extract_cube_members(missing_description, "ecommerce")

        duplicate = _metadata()
        duplicate["cubes"][0]["dimensions"][0]["name"] = "ecommerce.gmv"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            extract_cube_members(duplicate, "ecommerce")


class _FakeCubeRepository:
    def __init__(self, metadata: dict):
        self.metadata = metadata

    async def get_metadata(self) -> dict:
        return self.metadata


class _FakeEmbeddingClient:
    def __init__(self, operations: list[str], fail: bool = False):
        self.operations = operations
        self.fail = fail
        self.batches: list[list[str]] = []

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.operations.append(f"embed:{len(texts)}")
        self.batches.append(texts)
        if self.fail:
            raise RuntimeError("embedding unavailable")
        return [[float(index), 1.0] for index, _ in enumerate(texts)]


class _FakeCubeMemberQdrantRepository:
    def __init__(
        self,
        operations: list[str],
        *,
        previous: str | None = "cube_member_old",
        fail_old_delete: bool = False,
        swap_failure: str | None = None,
        fail_reconciliation: bool = False,
    ):
        self.operations = operations
        self.previous = previous
        self.fail_old_delete = fail_old_delete
        self.swap_failure = swap_failure
        self.fail_reconciliation = fail_reconciliation
        self.current_alias = previous
        self.alias_reads = 0
        self.swap_alias_calls: list[tuple[str, str | None]] = []
        self.deleted: list[str] = []
        self.entries = []
        self.embeddings = []

    async def create_physical_collection(self) -> str:
        self.operations.append("create:new")
        return "cube_member_new"

    async def upsert_entries(self, collection_name, entries, embeddings) -> None:
        self.operations.append("upsert:new")
        self.entries = list(entries)
        self.embeddings = list(embeddings)

    async def count_points(self, collection_name: str) -> int:
        self.operations.append("count:new")
        return len(self.entries)

    async def get_alias_target(self) -> str | None:
        self.operations.append("get_alias")
        self.alias_reads += 1
        if self.fail_reconciliation and self.alias_reads > 1:
            raise RuntimeError("alias reconciliation unavailable")
        return self.current_alias

    async def swap_alias(
        self, collection_name: str, previous_collection: str | None
    ) -> None:
        self.operations.append("swap:new")
        self.swap_alias_calls.append((collection_name, previous_collection))
        if self.swap_failure == "before":
            raise RuntimeError("swap failed before commit")
        self.current_alias = collection_name
        if self.swap_failure == "after":
            raise RuntimeError("swap response lost after commit")

    async def delete_collection(self, collection_name: str) -> None:
        self.operations.append(f"delete:{collection_name}")
        self.deleted.append(collection_name)
        if self.fail_old_delete and collection_name == self.previous:
            raise RuntimeError("old collection cleanup failed")


class CubeMetadataServiceTest(unittest.IsolatedAsyncioTestCase):
    def _service(
        self,
        qdrant_repository: _FakeCubeMemberQdrantRepository,
        embedding_client: _FakeEmbeddingClient,
        metadata: dict | None = None,
    ) -> CubeMetadataService:
        return CubeMetadataService(
            cube_repository=_FakeCubeRepository(metadata or _metadata()),
            cube_member_qdrant_repository=qdrant_repository,
            embedding_client=embedding_client,
            semantic_view="ecommerce",
        )

    async def test_count_precedes_single_alias_swap_and_old_delete_follows(
        self,
    ) -> None:
        operations: list[str] = []
        qdrant = _FakeCubeMemberQdrantRepository(operations)

        result = await self._service(qdrant, _FakeEmbeddingClient(operations)).sync()

        self.assertLess(operations.index("count:new"), operations.index("swap:new"))
        self.assertLess(
            operations.index("swap:new"), operations.index("delete:cube_member_old")
        )
        self.assertEqual(
            [("cube_member_new", "cube_member_old")], qdrant.swap_alias_calls
        )
        self.assertEqual("cube_member_new", result.collection_name)
        self.assertEqual(len(qdrant.entries), result.point_count)

    async def test_embedding_failure_deletes_staging_without_swapping_alias(
        self,
    ) -> None:
        operations: list[str] = []
        qdrant = _FakeCubeMemberQdrantRepository(operations)

        with self.assertRaisesRegex(RuntimeError, "embedding unavailable"):
            await self._service(
                qdrant, _FakeEmbeddingClient(operations, fail=True)
            ).sync()

        self.assertEqual([], qdrant.swap_alias_calls)
        self.assertEqual(["cube_member_new"], qdrant.deleted)

    async def test_repeated_metadata_submits_identical_ordered_point_ids(self) -> None:
        first_operations: list[str] = []
        first_qdrant = _FakeCubeMemberQdrantRepository(first_operations, previous=None)
        await self._service(first_qdrant, _FakeEmbeddingClient(first_operations)).sync()

        second_operations: list[str] = []
        second_qdrant = _FakeCubeMemberQdrantRepository(
            second_operations, previous=None
        )
        await self._service(
            second_qdrant, _FakeEmbeddingClient(second_operations)
        ).sync()

        self.assertEqual(
            [entry.id for entry in first_qdrant.entries],
            [entry.id for entry in second_qdrant.entries],
        )

    async def test_old_delete_failure_after_swap_still_returns_success(self) -> None:
        operations: list[str] = []
        qdrant = _FakeCubeMemberQdrantRepository(operations, fail_old_delete=True)

        with patch("app.services.cube_metadata_service.logger") as logger:
            result = await self._service(
                qdrant, _FakeEmbeddingClient(operations)
            ).sync()

        self.assertEqual("cube_member_new", result.collection_name)
        self.assertEqual(
            [("cube_member_new", "cube_member_old")], qdrant.swap_alias_calls
        )
        self.assertEqual(["cube_member_old"], qdrant.deleted)
        self.assertNotIn("cube_member_new", qdrant.deleted)
        logger.warning.assert_called_once()

    async def test_count_mismatch_cleans_staging_and_preserves_alias(self) -> None:
        operations: list[str] = []
        qdrant = _FakeCubeMemberQdrantRepository(operations)

        async def wrong_count(_: str) -> int:
            operations.append("count:new")
            return 0

        qdrant.count_points = wrong_count

        with self.assertRaisesRegex(RuntimeError, "point count"):
            await self._service(qdrant, _FakeEmbeddingClient(operations)).sync()

        self.assertEqual([], qdrant.swap_alias_calls)
        self.assertEqual(["cube_member_new"], qdrant.deleted)

    async def test_committed_swap_response_failure_is_reconciled(self) -> None:
        operations: list[str] = []
        qdrant = _FakeCubeMemberQdrantRepository(
            operations,
            swap_failure="after",
        )

        with patch("app.services.cube_metadata_service.logger") as logger:
            result = await self._service(
                qdrant, _FakeEmbeddingClient(operations)
            ).sync()

        self.assertEqual("cube_member_new", result.collection_name)
        self.assertEqual("cube_member_new", qdrant.current_alias)
        self.assertEqual(["cube_member_old"], qdrant.deleted)
        self.assertNotIn("cube_member_new", qdrant.deleted)
        logger.warning.assert_called_once()

    async def test_uncommitted_swap_failure_cleans_staging(self) -> None:
        operations: list[str] = []
        qdrant = _FakeCubeMemberQdrantRepository(
            operations,
            swap_failure="before",
        )

        with self.assertRaisesRegex(RuntimeError, "before commit"):
            await self._service(qdrant, _FakeEmbeddingClient(operations)).sync()

        self.assertEqual("cube_member_old", qdrant.current_alias)
        self.assertEqual(["cube_member_new"], qdrant.deleted)

    async def test_failed_swap_reconciliation_preserves_staging(self) -> None:
        operations: list[str] = []
        qdrant = _FakeCubeMemberQdrantRepository(
            operations,
            swap_failure="after",
            fail_reconciliation=True,
        )

        with patch("app.services.cube_metadata_service.logger") as logger:
            with self.assertRaises(RuntimeError):
                await self._service(qdrant, _FakeEmbeddingClient(operations)).sync()

        self.assertEqual([], qdrant.deleted)
        logger.warning.assert_called_once()

    async def test_empty_view_is_rejected_without_touching_qdrant(self) -> None:
        operations: list[str] = []
        qdrant = _FakeCubeMemberQdrantRepository(operations)
        metadata = _metadata()
        metadata["cubes"][0]["measures"] = []
        metadata["cubes"][0]["dimensions"] = []

        with self.assertRaisesRegex(ValueError, "no governed members"):
            await self._service(
                qdrant,
                _FakeEmbeddingClient(operations),
                metadata,
            ).sync()

        self.assertEqual([], operations)
        self.assertEqual([], qdrant.swap_alias_calls)
        self.assertEqual([], qdrant.deleted)


class _FakeClientManager:
    def __init__(self, *, init_error: Exception | None = None):
        self.client = SimpleNamespace()
        self.init_error = init_error
        self.close_calls = 0

    def init(self) -> None:
        if self.init_error is not None:
            raise self.init_error

    async def close(self) -> None:
        self.close_calls += 1


class SyncCubeMetadataScriptTest(unittest.IsolatedAsyncioTestCase):
    async def test_embedding_close_supports_async_close_method(self) -> None:
        from app.scripts.sync_cube_metadata import _close_embedding_client

        class SyncClient:
            def __init__(self):
                self.close_calls = 0

            def close(self) -> None:
                self.close_calls += 1

        class AsyncClient:
            def __init__(self):
                self.close_calls = 0

            async def close(self) -> None:
                self.close_calls += 1

        sync_client = SyncClient()
        async_client = AsyncClient()
        await _close_embedding_client(
            SimpleNamespace(client=sync_client, async_client=async_client)
        )

        self.assertEqual(1, sync_client.close_calls)
        self.assertEqual(1, async_client.close_calls)

    async def test_embedding_close_attempts_both_clients_after_one_failure(
        self,
    ) -> None:
        from app.scripts.sync_cube_metadata import _close_embedding_client

        class FailingAsyncClient:
            async def close(self) -> None:
                raise RuntimeError("async close failed")

        class SyncClient:
            def __init__(self):
                self.close_calls = 0

            def close(self) -> None:
                self.close_calls += 1

        sync_client = SyncClient()
        with self.assertRaises(ExceptionGroup):
            await _close_embedding_client(
                SimpleNamespace(
                    client=sync_client,
                    async_client=FailingAsyncClient(),
                )
            )

        self.assertEqual(1, sync_client.close_calls)

    async def test_later_init_failure_closes_already_started_clients(self) -> None:
        from app.scripts import sync_cube_metadata

        cube_manager = _FakeClientManager()
        qdrant_manager = _FakeClientManager()
        embedding_manager = _FakeClientManager(
            init_error=RuntimeError("embedding init failed")
        )

        with (
            patch.object(
                sync_cube_metadata,
                "get_cube_client_manager",
                return_value=cube_manager,
            ),
            patch.object(
                sync_cube_metadata,
                "get_qdrant_client_manager",
                return_value=qdrant_manager,
            ),
            patch.object(
                sync_cube_metadata,
                "get_embedding_client_manager",
                return_value=embedding_manager,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "embedding init failed"):
                await sync_cube_metadata.sync()

        self.assertEqual(1, cube_manager.close_calls)
        self.assertEqual(1, qdrant_manager.close_calls)


if __name__ == "__main__":
    unittest.main()
