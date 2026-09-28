import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException


class MetricGovernanceAuthTest(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_when_governance_key_is_not_configured(self):
        from app.api.dependencies import require_metric_governance_key

        with patch(
            "app.api.dependencies.app_config.metric_governance",
            SimpleNamespace(api_key=""),
        ):
            with self.assertRaises(HTTPException) as context:
                await require_metric_governance_key(None)

        self.assertEqual(503, context.exception.status_code)

    async def test_rejects_missing_or_invalid_key(self):
        from app.api.dependencies import require_metric_governance_key

        with patch(
            "app.api.dependencies.app_config.metric_governance",
            SimpleNamespace(api_key="expected-secret"),
        ):
            with self.assertRaises(HTTPException) as missing:
                await require_metric_governance_key(None)
            with self.assertRaises(HTTPException) as invalid:
                await require_metric_governance_key("wrong-secret")

        self.assertEqual(401, missing.exception.status_code)
        self.assertEqual(401, invalid.exception.status_code)

    async def test_accepts_matching_key(self):
        from app.api.dependencies import require_metric_governance_key

        with patch(
            "app.api.dependencies.app_config.metric_governance",
            SimpleNamespace(api_key="expected-secret"),
        ):
            result = await require_metric_governance_key("expected-secret")

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
