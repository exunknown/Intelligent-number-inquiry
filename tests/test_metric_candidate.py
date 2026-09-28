import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.entities.metric_candidate import MetricCandidate
from app.repositories.mysql.meta.metric_candidate_repository import (
    MetricCandidateRepository,
    normalize_query,
    query_hash,
)
from app.services.metric_candidate_service import MetricCandidateService


class MetricCandidateRepositoryTest(unittest.IsolatedAsyncioTestCase):
    def test_normalizes_whitespace_and_case_before_hashing(self):
        self.assertEqual("gmv 按地区", normalize_query("  GMV   按地区 "))
        self.assertEqual(query_hash("GMV 按地区"), query_hash("  gmv   按地区 "))

    async def test_upsert_executes_and_commits(self):
        session = Mock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        repository = MetricCandidateRepository(session)

        await repository.upsert_pending("GMV 按地区", "no_measure_candidate")

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    async def test_upsert_rolls_back_on_failure(self):
        session = Mock()
        session.execute = AsyncMock(side_effect=RuntimeError("database unavailable"))
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        repository = MetricCandidateRepository(session)

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            await repository.upsert_pending("GMV 按地区", "no_measure_candidate")

        session.rollback.assert_awaited_once()

    async def test_reviews_candidate_and_commits(self):
        from app.models.metric_candidate import MetricCandidateMySQL

        now = datetime(2026, 9, 28, 12, 0, 0)
        model = MetricCandidateMySQL(
            id="candidate-id",
            query_hash="hash",
            query_text="GMV 按地区",
            route_reason="no_measure_candidate",
            source_request_id="request-id",
            status="pending",
            occurrence_count=2,
            first_seen_at=now,
            last_seen_at=now,
        )
        session = Mock()
        session.get = AsyncMock(return_value=model)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        repository = MetricCandidateRepository(session)

        result = await repository.review(
            "candidate-id", status="approved", review_note="已补充到指标模型"
        )

        self.assertEqual("approved", result.status)
        self.assertEqual("已补充到指标模型", result.review_note)
        self.assertIsNotNone(result.reviewed_at)
        session.commit.assert_awaited_once()

    async def test_review_returns_none_for_missing_candidate(self):
        session = Mock()
        session.get = AsyncMock(return_value=None)
        repository = MetricCandidateRepository(session)

        result = await repository.review(
            "missing-id", status="rejected", review_note="暂不治理"
        )

        self.assertIsNone(result)


class MetricCandidateServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_lists_candidates_with_status_and_limit(self):
        now = datetime(2026, 9, 28, 12, 0, 0)
        candidate = MetricCandidate(
            id="candidate-id",
            query_text="GMV 按地区",
            route_reason="no_measure_candidate",
            source_request_id="request-id",
            status="pending",
            occurrence_count=2,
            first_seen_at=now,
            last_seen_at=now,
            reviewed_at=None,
            review_note=None,
        )

        class _Repository:
            def __init__(self):
                self.calls = []

            async def list_candidates(self, status, limit):
                self.calls.append((status, limit))
                return [candidate]

        repository = _Repository()
        result = await MetricCandidateService(repository).list_candidates(
            status="pending", limit=20
        )

        self.assertEqual([candidate], result)
        self.assertEqual([("pending", 20)], repository.calls)

    async def test_reviews_candidate(self):
        candidate = MetricCandidate(
            id="candidate-id",
            query_text="GMV 按地区",
            route_reason="no_measure_candidate",
            source_request_id="request-id",
            status="approved",
            occurrence_count=2,
            first_seen_at=datetime(2026, 9, 28, 12, 0, 0),
            last_seen_at=datetime(2026, 9, 28, 12, 0, 0),
            reviewed_at=datetime(2026, 9, 28, 12, 1, 0),
            review_note="已补充到指标模型",
        )

        class _Repository:
            async def review(self, candidate_id, status, review_note):
                self.args = (candidate_id, status, review_note)
                return candidate

        repository = _Repository()
        service = MetricCandidateService(repository)
        result = await service.review_candidate(
            "candidate-id", status="approved", review_note="已补充到指标模型"
        )

        self.assertEqual(candidate, result)
        self.assertEqual(
            ("candidate-id", "approved", "已补充到指标模型"), repository.args
        )


class MetricCandidateRouterTest(unittest.IsolatedAsyncioTestCase):
    async def test_route_serializes_candidate_summary(self):
        from app.api.routers.metric_candidate_router import metric_candidate_handler

        now = datetime(2026, 9, 28, 12, 0, 0)
        candidate = MetricCandidate(
            id="candidate-id",
            query_text="GMV 按地区",
            route_reason="no_measure_candidate",
            source_request_id="request-id",
            status="pending",
            occurrence_count=2,
            first_seen_at=now,
            last_seen_at=now,
            reviewed_at=None,
            review_note=None,
        )
        service = SimpleNamespace(
            list_candidates=lambda **kwargs: _return_candidates([candidate])
        )

        response = await metric_candidate_handler(
            status="pending", limit=20, metric_candidate_service=service
        )

        self.assertEqual(1, response.total)
        self.assertEqual("candidate-id", response.items[0].id)
        self.assertEqual(2, response.items[0].occurrence_count)

    async def test_review_route_returns_updated_candidate(self):
        from app.api.routers.metric_candidate_router import (
            metric_candidate_review_handler,
        )
        from app.api.schemas.metric_candidate_schema import MetricCandidateReviewRequest

        candidate = MetricCandidate(
            id="candidate-id",
            query_text="GMV 按地区",
            route_reason="no_measure_candidate",
            source_request_id="request-id",
            status="approved",
            occurrence_count=2,
            first_seen_at=datetime(2026, 9, 28, 12, 0, 0),
            last_seen_at=datetime(2026, 9, 28, 12, 0, 0),
            reviewed_at=datetime(2026, 9, 28, 12, 1, 0),
            review_note="已补充到指标模型",
        )
        service = SimpleNamespace(
            review_candidate=lambda **kwargs: _return_candidate(candidate)
        )

        response = await metric_candidate_review_handler(
            candidate_id="candidate-id",
            request=MetricCandidateReviewRequest(
                status="approved", review_note="已补充到指标模型"
            ),
            metric_candidate_service=service,
        )

        self.assertEqual("approved", response.status)
        self.assertEqual("已补充到指标模型", response.review_note)

    async def test_review_route_returns_404_for_missing_candidate(self):
        from fastapi import HTTPException

        from app.api.routers.metric_candidate_router import (
            metric_candidate_review_handler,
        )
        from app.api.schemas.metric_candidate_schema import MetricCandidateReviewRequest

        service = SimpleNamespace(
            review_candidate=lambda **kwargs: _return_candidate(None)
        )

        with self.assertRaises(HTTPException) as context:
            await metric_candidate_review_handler(
                candidate_id="missing-id",
                request=MetricCandidateReviewRequest(status="rejected"),
                metric_candidate_service=service,
            )

        self.assertEqual(404, context.exception.status_code)


async def _return_candidates(candidates: list[MetricCandidate]):
    return candidates


async def _return_candidate(candidate: MetricCandidate | None):
    return candidate


if __name__ == "__main__":
    unittest.main()
