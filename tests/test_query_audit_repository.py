import unittest
from unittest.mock import AsyncMock, Mock

from app.entities.query_audit import QueryAuditRecord
from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository


class QueryAuditRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_save_maps_audit_record_and_commits(self):
        session = Mock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        repository = QueryAuditRepository(session)
        record = QueryAuditRecord(
            query_text="统计 GMV",
            query_mode="metric",
            route_reason="governed_measure_matched",
            metric_query={"status": "matched"},
            cube_query={"measures": ["ecommerce.gmv"]},
            sql=None,
            outcome="success",
            error_code=None,
            verified=True,
            duration_ms=12,
        )

        await repository.save(record)

        model = session.add.call_args.args[0]
        self.assertEqual(record.query_text, model.query_text)
        self.assertEqual(record.metric_query, model.metric_query)
        self.assertEqual(record.cube_query, model.cube_query)
        self.assertEqual(record.outcome, model.outcome)
        session.commit.assert_awaited_once()

    async def test_save_rolls_back_when_database_write_fails(self):
        session = Mock()
        session.commit = AsyncMock(side_effect=RuntimeError("database unavailable"))
        session.rollback = AsyncMock()
        repository = QueryAuditRepository(session)
        record = QueryAuditRecord(
            query_text="统计 GMV",
            query_mode=None,
            route_reason=None,
            metric_query=None,
            cube_query=None,
            sql=None,
            outcome="error",
            error_code="internal_error",
            verified=None,
            duration_ms=1,
        )

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            await repository.save(record)

        session.rollback.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
