import unittest
from types import SimpleNamespace

from app.entities.cube_member import CubeMember


def _member(
    name: str,
    member_type: str,
    title: str,
    aliases: list[str] | None = None,
) -> CubeMember:
    return CubeMember(
        name=name,
        cube_name="ecommerce",
        member_type=member_type,
        data_type="number" if member_type == "measure" else "string",
        title=title,
        description=f"{title} description",
        aliases=aliases or [],
        ai_context="",
        source_column_id=None,
        filterable=member_type != "measure",
    )


class _FakeCubeMemberRepository:
    def __init__(self, members: list[CubeMember]):
        self.members = members
        self.calls = 0

    async def list_members(self) -> list[CubeMember]:
        self.calls += 1
        return self.members


class MetricCatalogServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_lists_measures_by_default_and_filters_search_text(self):
        from app.services.metric_catalog_service import MetricCatalogService

        repository = _FakeCubeMemberRepository(
            [
                _member("ecommerce.gmv", "measure", "成交金额", ["销售额"]),
                _member("ecommerce.order_count", "measure", "订单数"),
                _member("ecommerce.region_name", "dimension", "地区"),
            ]
        )

        result = await MetricCatalogService(repository).list_members(q="销售额")

        self.assertEqual(1, repository.calls)
        self.assertEqual(["ecommerce.gmv"], [member.name for member in result])

    async def test_can_return_all_member_types(self):
        from app.services.metric_catalog_service import MetricCatalogService

        repository = _FakeCubeMemberRepository(
            [
                _member("ecommerce.gmv", "measure", "成交金额"),
                _member("ecommerce.region_name", "dimension", "地区"),
                _member("ecommerce.order_date", "time_dimension", "下单日期"),
            ]
        )

        result = await MetricCatalogService(repository).list_members(member_type="all")

        self.assertEqual(
            ["ecommerce.gmv", "ecommerce.region_name", "ecommerce.order_date"],
            [member.name for member in result],
        )


class MetricCatalogRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_route_serializes_governed_member_fields(self):
        from app.api.routers.metric_catalog_router import metric_catalog_handler

        member = _member("ecommerce.gmv", "measure", "成交金额", ["销售额"])
        response = await metric_catalog_handler(
            member_type="measure",
            q=None,
            metric_catalog_service=SimpleNamespace(
                list_members=lambda **kwargs: _return_members([member])
            ),
        )

        self.assertEqual(1, response.total)
        self.assertEqual("ecommerce.gmv", response.items[0].name)
        self.assertEqual("measure", response.items[0].member_type)
        self.assertEqual(["销售额"], response.items[0].aliases)


async def _return_members(members: list[CubeMember]):
    return members


if __name__ == "__main__":
    unittest.main()
