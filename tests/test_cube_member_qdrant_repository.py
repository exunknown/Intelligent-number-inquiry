import re
import unittest
from types import SimpleNamespace

from qdrant_client.models import (
    CreateAliasOperation,
    DeleteAliasOperation,
    Distance,
    MatchAny,
)

from app.entities.cube_member import CubeMember, iter_member_embedding_entries
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)


def _member(name: str = "ecommerce.gmv", member_type: str = "measure") -> CubeMember:
    return CubeMember(
        name=name,
        cube_name="ecommerce",
        member_type=member_type,
        data_type="number" if member_type == "measure" else "string",
        title="销售额" if member_type == "measure" else "大区",
        description="用于测试的成员描述",
        aliases=["测试别名"],
        ai_context="用于测试",
        source_column_id="fact_order.order_amount",
        filterable=member_type != "measure",
    )


class _FakeQdrantClient:
    def __init__(self):
        self.created: list[dict] = []
        self.upserts: list[dict] = []
        self.count_calls: list[dict] = []
        self.aliases = []
        self.alias_updates: list[list] = []
        self.deleted: list[str] = []
        self.query_calls: list[dict] = []
        self.query_points_result = SimpleNamespace(points=[])
        self.scroll_calls: list[dict] = []
        self.scroll_results: list[tuple[list, object]] = []
        self.create_error: Exception | None = None

    async def create_collection(self, **kwargs):
        self.created.append(kwargs)
        if self.create_error is not None:
            raise self.create_error
        return True

    async def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    async def count(self, **kwargs):
        self.count_calls.append(kwargs)
        return SimpleNamespace(count=7)

    async def get_aliases(self):
        return SimpleNamespace(aliases=self.aliases)

    async def update_collection_aliases(self, change_aliases_operations):
        self.alias_updates.append(change_aliases_operations)
        return True

    async def delete_collection(self, collection_name):
        self.deleted.append(collection_name)
        return True

    async def query_points(self, **kwargs):
        self.query_calls.append(kwargs)
        return self.query_points_result

    async def scroll(self, **kwargs):
        self.scroll_calls.append(kwargs)
        return self.scroll_results.pop(0)


class CubeMemberQdrantRepositoryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = _FakeQdrantClient()
        self.repository = CubeMemberQdrantRepository(self.client)

    async def test_create_physical_collection_uses_cosine_config(self) -> None:
        name = await self.repository.create_physical_collection()

        self.assertRegex(name, re.compile(r"^cube_member_\d{8}T\d{12}Z_[0-9a-f]{8}$"))
        self.assertEqual(name, self.client.created[0]["collection_name"])
        vectors = self.client.created[0]["vectors_config"]
        self.assertEqual(Distance.COSINE, vectors.distance)
        self.assertGreater(vectors.size, 0)

    async def test_create_response_failure_best_effort_deletes_staging(self) -> None:
        self.client.create_error = RuntimeError("create response lost")

        with self.assertRaisesRegex(RuntimeError, "create response lost"):
            await self.repository.create_physical_collection()

        self.assertEqual(1, len(self.client.deleted))
        self.assertEqual(
            self.client.created[0]["collection_name"], self.client.deleted[0]
        )

    async def test_upsert_entries_validates_lengths_and_batches_by_eight(self) -> None:
        entries = iter_member_embedding_entries(_member()) * 2
        embeddings = [[1.0, 0.0] for _ in entries]

        await self.repository.upsert_entries("cube_member_new", entries, embeddings)

        self.assertEqual(
            [8, len(entries) - 8], [len(c["points"]) for c in self.client.upserts]
        )
        payload = self.client.upserts[0]["points"][0].payload
        self.assertEqual(_member().__dict__, payload)
        self.assertNotIn("embedding_text", payload)
        self.assertNotIn("embedding", payload)

        with self.assertRaisesRegex(ValueError, "length"):
            await self.repository.upsert_entries(
                "cube_member_new", entries, embeddings[:-1]
            )

    async def test_count_is_exact_and_alias_swap_is_one_atomic_request(self) -> None:
        count = await self.repository.count_points("cube_member_new")
        self.assertEqual(7, count)
        self.assertEqual(
            {"collection_name": "cube_member_new", "exact": True},
            self.client.count_calls[0],
        )

        self.client.aliases = [
            SimpleNamespace(
                alias_name="cube_member_collection",
                collection_name="cube_member_old",
            )
        ]
        self.assertEqual("cube_member_old", await self.repository.get_alias_target())
        await self.repository.swap_alias("cube_member_new", "cube_member_old")

        self.assertEqual(1, len(self.client.alias_updates))
        operations = self.client.alias_updates[0]
        self.assertEqual(2, len(operations))
        self.assertIsInstance(operations[0], DeleteAliasOperation)
        self.assertIsInstance(operations[1], CreateAliasOperation)
        self.assertEqual(
            "cube_member_collection", operations[0].delete_alias.alias_name
        )
        self.assertEqual("cube_member_new", operations[1].create_alias.collection_name)

    async def test_swap_without_existing_alias_sends_only_create(self) -> None:
        await self.repository.swap_alias("cube_member_new", None)

        operations = self.client.alias_updates[0]
        self.assertEqual(1, len(operations))
        self.assertIsInstance(operations[0], CreateAliasOperation)

    async def test_delete_collection_rejects_alias_and_unrelated_names(self) -> None:
        for name in ("cube_member_collection", "metric_info_collection"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "physical"):
                    await self.repository.delete_collection(name)

        await self.repository.delete_collection("cube_member_old")
        self.assertEqual(["cube_member_old"], self.client.deleted)

    async def test_search_uses_alias_match_any_and_deduplicates_in_order(self) -> None:
        gmv = _member()
        region = _member("ecommerce.region_name", "dimension")
        self.client.query_points_result = SimpleNamespace(
            points=[
                SimpleNamespace(payload=gmv.__dict__),
                SimpleNamespace(payload=gmv.__dict__),
                SimpleNamespace(payload=region.__dict__),
            ]
        )

        result = await self.repository.search(
            [1.0, 0.0], {"dimension", "time_dimension"}
        )

        self.assertEqual(
            ["ecommerce.gmv", "ecommerce.region_name"], [m.name for m in result]
        )
        call = self.client.query_calls[0]
        self.assertEqual("cube_member_collection", call["collection_name"])
        self.assertEqual(0.6, call["score_threshold"])
        self.assertEqual(10, call["limit"])
        condition = call["query_filter"].must[0]
        self.assertEqual("member_type", condition.key)
        self.assertIsInstance(condition.match, MatchAny)
        self.assertEqual(["dimension", "time_dimension"], condition.match.any)

    async def test_list_members_scrolls_all_pages_and_deduplicates(self) -> None:
        gmv = _member()
        region = _member("ecommerce.region_name", "dimension")
        self.client.scroll_results = [
            ([SimpleNamespace(payload=gmv.__dict__)], "next-offset"),
            (
                [
                    SimpleNamespace(payload=gmv.__dict__),
                    SimpleNamespace(payload=region.__dict__),
                ],
                None,
            ),
        ]

        result = await self.repository.list_members()

        self.assertEqual(
            ["ecommerce.gmv", "ecommerce.region_name"], [m.name for m in result]
        )
        self.assertEqual(2, len(self.client.scroll_calls))
        self.assertIsNone(self.client.scroll_calls[0]["offset"])
        self.assertEqual("next-offset", self.client.scroll_calls[1]["offset"])
        self.assertTrue(all(call["with_payload"] for call in self.client.scroll_calls))
        self.assertTrue(
            all(not call["with_vectors"] for call in self.client.scroll_calls)
        )


if __name__ == "__main__":
    unittest.main()
