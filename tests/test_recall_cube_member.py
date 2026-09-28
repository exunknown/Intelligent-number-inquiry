import unittest
from types import SimpleNamespace

from app.entities.cube_member import CubeMember


def _member(
    name: str,
    member_type: str,
    *,
    source_column_id: str | None = None,
) -> CubeMember:
    return CubeMember(
        name=name,
        cube_name="ecommerce",
        member_type=member_type,
        data_type="number" if member_type == "measure" else "string",
        title=name,
        description=f"{name} description",
        aliases=[],
        ai_context="",
        source_column_id=source_column_id,
        filterable=member_type == "dimension",
    )


class _FakeEmbeddingClient:
    def __init__(self):
        self.calls: list[str] = []

    async def aembed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return [float(len(self.calls))]


class _FakeCubeMemberRepository:
    def __init__(self, members: list[CubeMember]):
        self.members = members
        self.search_calls: list[tuple[list[float], set[str]]] = []

    async def search(
        self, embedding: list[float], member_types: set[str]
    ) -> list[CubeMember]:
        self.search_calls.append((embedding, member_types))
        call_number = len(self.search_calls)
        if member_types == {"measure"}:
            if call_number == 1:
                return [self.members[0]]
            return [self.members[0], self.members[1]]
        if call_number == 2:
            return [self.members[2], self.members[3]]
        return [self.members[2]]

    async def list_members(self) -> list[CubeMember]:
        return self.members


class RecallCubeMemberTest(unittest.IsolatedAsyncioTestCase):
    async def test_embeds_each_unique_term_once_and_searches_both_member_groups(self):
        from app.agent.nodes.recall_cube_member import recall_cube_member

        members = [
            _member("ecommerce.gmv", "measure"),
            _member("ecommerce.order_count", "measure"),
            _member(
                "ecommerce.region_name",
                "dimension",
                source_column_id="dim_region.region_name",
            ),
            _member("ecommerce.order_date", "time_dimension"),
        ]
        embedding_client = _FakeEmbeddingClient()
        repository = _FakeCubeMemberRepository(members)
        events = []
        runtime = SimpleNamespace(
            context={
                "embedding_client": embedding_client,
                "cube_member_qdrant_repository": repository,
            },
            stream_writer=events.append,
        )

        result = await recall_cube_member(
            {
                "query": "华东销售额",
                "keywords": ["销售额", "华东销售额", "地区", "销售额"],
            },
            runtime,
        )

        self.assertEqual(["华东销售额", "销售额", "地区"], embedding_client.calls)
        self.assertEqual(6, len(repository.search_calls))
        self.assertEqual(
            [
                {"measure"},
                {"dimension", "time_dimension"},
            ]
            * 3,
            [member_types for _, member_types in repository.search_calls],
        )
        self.assertEqual(
            ["ecommerce.gmv", "ecommerce.order_count"],
            [member.name for member in result["retrieved_cube_measures"]],
        )
        self.assertEqual(
            ["ecommerce.region_name", "ecommerce.order_date"],
            [member.name for member in result["retrieved_cube_dimensions"]],
        )
        self.assertEqual(
            {member.name: member for member in members}, result["cube_member_catalog"]
        )
        self.assertEqual("running", events[0]["status"])
        self.assertEqual("success", events[-1]["status"])

    async def test_catalog_measures_are_included_when_similarity_search_misses_them(
        self,
    ):
        from app.agent.nodes.recall_cube_member import recall_cube_member

        members = [
            _member("ecommerce.gmv", "measure"),
            _member("ecommerce.aov", "measure"),
            _member("ecommerce.order_date", "time_dimension"),
        ]
        repository = _FakeCubeMemberRepository(members)

        async def search_without_measures(embedding, member_types):
            if member_types == {"dimension", "time_dimension"}:
                return []
            return []

        repository.search = search_without_measures
        runtime = SimpleNamespace(
            context={
                "embedding_client": _FakeEmbeddingClient(),
                "cube_member_qdrant_repository": repository,
            },
            stream_writer=lambda event: None,
        )

        result = await recall_cube_member(
            {"query": "平均客单价", "keywords": []}, runtime
        )

        self.assertEqual(
            ["ecommerce.gmv", "ecommerce.aov"],
            [member.name for member in result["retrieved_cube_measures"]],
        )

    async def test_catalog_time_dimensions_are_included_when_search_misses_them(self):
        from app.agent.nodes.recall_cube_member import recall_cube_member

        members = [
            _member("ecommerce.gmv", "measure"),
            _member("ecommerce.region_name", "dimension"),
            _member("ecommerce.order_date", "time_dimension"),
        ]
        repository = _FakeCubeMemberRepository(members)

        async def search_without_time(embedding, member_types):
            if member_types == {"measure"}:
                return [members[0]]
            return [members[1]]

        repository.search = search_without_time
        runtime = SimpleNamespace(
            context={
                "embedding_client": _FakeEmbeddingClient(),
                "cube_member_qdrant_repository": repository,
            },
            stream_writer=lambda event: None,
        )

        result = await recall_cube_member(
            {"query": "上季度平均客单价", "keywords": []}, runtime
        )

        self.assertEqual(
            ["ecommerce.region_name", "ecommerce.order_date"],
            [member.name for member in result["retrieved_cube_dimensions"]],
        )


class SemanticCoverageGateTest(unittest.IsolatedAsyncioTestCase):
    async def test_empty_measure_candidates_route_to_sql_without_model_work(self):
        from app.agent.nodes.semantic_coverage_gate import semantic_coverage_gate

        events = []
        runtime = SimpleNamespace(stream_writer=events.append)

        result = await semantic_coverage_gate({"retrieved_cube_measures": []}, runtime)

        self.assertEqual(
            {"query_mode": "sql", "route_reason": "no_measure_candidate"}, result
        )
        self.assertEqual(
            [{"type": "route", "mode": "sql", "reason": "no_measure_candidate"}],
            events,
        )

    async def test_measure_candidate_continues_without_emitting_metric_route(self):
        from app.agent.nodes.semantic_coverage_gate import semantic_coverage_gate

        events = []
        runtime = SimpleNamespace(stream_writer=events.append)

        result = await semantic_coverage_gate(
            {"retrieved_cube_measures": [_member("ecommerce.gmv", "measure")]},
            runtime,
        )

        self.assertEqual({"query_mode": "metric"}, result)
        self.assertEqual([], events)


if __name__ == "__main__":
    unittest.main()
