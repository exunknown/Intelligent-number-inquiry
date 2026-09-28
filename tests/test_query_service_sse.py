import json
import unittest
from unittest.mock import patch

from app.core.query_errors import QueryExecutionError
from app.services.query_service import QueryService


class QueryServiceSSETest(unittest.IsolatedAsyncioTestCase):
    class _AuditRepository:
        def __init__(self, error=None):
            self.records = []
            self.error = error

        async def save(self, record):
            if self.error is not None:
                raise self.error
            self.records.append(record)

    class _CandidateRepository:
        def __init__(self, error=None):
            self.calls = []
            self.error = error

        async def upsert_pending(self, query_text, route_reason):
            if self.error is not None:
                raise self.error
            self.calls.append((query_text, route_reason))

    @staticmethod
    def _service(audit_repository=None, candidate_repository=None):
        return QueryService(
            meta_mysql_repository=None,
            embedding_client=None,
            dw_mysql_repository=None,
            column_qdrant_repository=None,
            cube_member_qdrant_repository=None,
            cube_repository=None,
            value_es_repository=None,
            query_audit_repository=audit_repository,
            metric_candidate_repository=candidate_repository,
        )

    async def _collect_events(self, service):
        chunks = [chunk async for chunk in service.query("test query")]
        self.assertTrue(
            all(
                chunk.startswith("data: ") and chunk.endswith("\n\n")
                for chunk in chunks
            )
        )
        return [json.loads(chunk.removeprefix("data: ").strip()) for chunk in chunks]

    async def test_preserves_custom_events_unchanged(self):
        custom_event = {
            "type": "progress",
            "step": "recall",
            "status": "running",
            "extra": {"source": "graph"},
        }

        async def fake_astream(**kwargs):
            yield custom_event

        with patch("app.services.query_service.graph.astream", fake_astream):
            events = await self._collect_events(self._service())

        self.assertEqual([custom_event], events)

    async def test_serializes_query_execution_error_with_public_fields(self):
        async def fake_astream(**kwargs):
            raise QueryExecutionError("cube_timeout", "指标平台请求超时", True)
            yield

        with patch("app.services.query_service.graph.astream", fake_astream):
            events = await self._collect_events(self._service())

        self.assertEqual(
            [
                {
                    "type": "error",
                    "code": "cube_timeout",
                    "message": "指标平台请求超时",
                    "retryable": True,
                }
            ],
            events,
        )

    async def test_hides_unexpected_exception_details(self):
        raw_message = "mysql://user:password@host:3306/dw"

        async def fake_astream(**kwargs):
            raise RuntimeError(raw_message)
            yield

        with patch("app.services.query_service.graph.astream", fake_astream):
            events = await self._collect_events(self._service())

        self.assertEqual(
            [
                {
                    "type": "error",
                    "code": "internal_error",
                    "message": "服务内部错误，请稍后重试",
                    "retryable": False,
                }
            ],
            events,
        )

    async def test_persists_audit_and_filters_internal_audit_events(self):
        audit_repository = self._AuditRepository()
        route_event = {
            "type": "route",
            "mode": "metric",
            "reason": "governed_measure_matched",
        }
        audit_event = {
            "type": "audit",
            "metric_query": {
                "status": "matched",
                "query": {"measures": ["ecommerce.gmv"]},
            },
            "cube_query": {"measures": ["ecommerce.gmv"]},
        }
        result_event = {
            "type": "result",
            "data": [{"ecommerce.gmv": "12.3"}],
            "source": "metric",
            "verified": True,
            "warning": None,
        }

        async def fake_astream(**kwargs):
            yield route_event
            yield audit_event
            yield result_event

        with patch("app.services.query_service.graph.astream", fake_astream):
            events = await self._collect_events(
                self._service(audit_repository=audit_repository)
            )

        self.assertEqual([route_event, result_event], events)
        self.assertEqual(1, len(audit_repository.records))
        record = audit_repository.records[0]
        self.assertEqual("test query", record.query_text)
        self.assertEqual("metric", record.query_mode)
        self.assertEqual("governed_measure_matched", record.route_reason)
        self.assertEqual(audit_event["metric_query"], record.metric_query)
        self.assertEqual(audit_event["cube_query"], record.cube_query)
        self.assertEqual("success", record.outcome)
        self.assertIsNone(record.error_code)
        self.assertTrue(record.verified)
        self.assertGreaterEqual(record.duration_ms, 0)

    async def test_persists_query_execution_error_without_replacing_sse_error(self):
        audit_repository = self._AuditRepository()

        async def fake_astream(**kwargs):
            yield {"type": "route", "mode": "metric", "reason": "matched"}
            raise QueryExecutionError("cube_timeout", "Cube timeout", True)
            yield

        with patch("app.services.query_service.graph.astream", fake_astream):
            events = await self._collect_events(
                self._service(audit_repository=audit_repository)
            )

        self.assertEqual("cube_timeout", events[-1]["code"])
        record = audit_repository.records[0]
        self.assertEqual("error", record.outcome)
        self.assertEqual("cube_timeout", record.error_code)
        self.assertEqual("metric", record.query_mode)

    async def test_audit_failure_does_not_break_query_stream(self):
        audit_repository = self._AuditRepository(
            error=RuntimeError("audit unavailable")
        )

        async def fake_astream(**kwargs):
            yield {"type": "result", "data": [], "source": "metric", "verified": True}

        with patch("app.services.query_service.graph.astream", fake_astream):
            events = await self._collect_events(
                self._service(audit_repository=audit_repository)
            )

        self.assertEqual("result", events[0]["type"])

    async def test_sql_route_is_added_to_metric_candidate_pool(self):
        candidate_repository = self._CandidateRepository()

        async def fake_astream(**kwargs):
            yield {
                "type": "route",
                "mode": "sql",
                "reason": "missing_dimension_mapping",
            }
            yield {
                "type": "result",
                "data": [],
                "source": "sql",
                "verified": False,
            }

        with patch("app.services.query_service.graph.astream", fake_astream):
            await self._collect_events(
                self._service(candidate_repository=candidate_repository)
            )

        self.assertEqual(
            [("test query", "missing_dimension_mapping")],
            candidate_repository.calls,
        )

    async def test_metric_route_is_not_added_to_metric_candidate_pool(self):
        candidate_repository = self._CandidateRepository()

        async def fake_astream(**kwargs):
            yield {
                "type": "route",
                "mode": "metric",
                "reason": "governed_measure_matched",
            }
            yield {
                "type": "result",
                "data": [],
                "source": "metric",
                "verified": True,
            }

        with patch("app.services.query_service.graph.astream", fake_astream):
            await self._collect_events(
                self._service(candidate_repository=candidate_repository)
            )

        self.assertEqual([], candidate_repository.calls)


if __name__ == "__main__":
    unittest.main()
