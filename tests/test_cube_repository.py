import base64
import json
import unittest
from unittest.mock import patch

import httpx

from app.conf.app_config import CubeConfig
from app.core.query_errors import QueryExecutionError
from app.repositories.cube.cube_repository import CubeRepository


class CubeRepositoryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.config = CubeConfig(
            base_url="http://cube/cubejs-api",
            api_secret="test-secret-with-at-least-thirty-two-bytes",
            timeout_seconds=10,
            max_limit=500,
            semantic_view="ecommerce",
        )

    async def test_get_metadata_uses_raw_jwt_authorization(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual("GET", request.method)
            self.assertEqual("/cubejs-api/v1/meta", request.url.path)
            token = request.headers["Authorization"]
            self.assertFalse(token.startswith("Bearer "))
            claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
            self.assertEqual(
                {"sub": "shopkeeper-agent", "iat": 1000, "exp": 1300}, claims
            )
            return httpx.Response(200, json={"cubes": []})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=self.config.base_url
        ) as client:
            result = await CubeRepository(
                client, self.config, clock=lambda: 1000
            ).get_metadata()

        self.assertEqual({"cubes": []}, result)

    async def test_load_posts_wrapped_query(self) -> None:
        cube_query = {"measures": ["ecommerce.gmv"]}

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual("POST", request.method)
            self.assertEqual("/cubejs-api/v1/load", request.url.path)
            self.assertEqual({"query": cube_query}, json.loads(request.content))
            return httpx.Response(200, json={"data": []})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=self.config.base_url
        ) as client:
            result = await CubeRepository(client, self.config).load(cube_query)

        self.assertEqual({"data": []}, result)

    async def test_unauthorized_responses_are_not_retryable(self) -> None:
        for status_code in (401, 403):
            with self.subTest(status_code=status_code):

                async def handler(_: httpx.Request) -> httpx.Response:
                    return httpx.Response(status_code, text="denied")

                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(handler),
                    base_url=self.config.base_url,
                ) as client:
                    with self.assertRaises(QueryExecutionError) as raised:
                        await CubeRepository(client, self.config).get_metadata()

                self.assertEqual("cube_unauthorized", raised.exception.code)
                self.assertFalse(raised.exception.retryable)

    async def test_timeout_is_retryable(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=self.config.base_url
        ) as client:
            with self.assertRaises(QueryExecutionError) as raised:
                await CubeRepository(client, self.config).get_metadata()

        self.assertEqual("cube_timeout", raised.exception.code)
        self.assertTrue(raised.exception.retryable)

    async def test_server_error_is_retryable(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="failure")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=self.config.base_url
        ) as client:
            with self.assertRaises(QueryExecutionError) as raised:
                await CubeRepository(client, self.config).get_metadata()

        self.assertEqual("cube_unavailable", raised.exception.code)
        self.assertTrue(raised.exception.retryable)

    async def test_unknown_member_is_metadata_out_of_sync(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="Unknown member ecommerce.old_metric")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=self.config.base_url
        ) as client:
            with self.assertRaises(QueryExecutionError) as raised:
                await CubeRepository(client, self.config).get_metadata()

        self.assertEqual("metadata_out_of_sync", raised.exception.code)
        self.assertFalse(raised.exception.retryable)

    async def test_member_not_found_is_metadata_out_of_sync(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="member not found")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=self.config.base_url
        ) as client:
            with self.assertRaises(QueryExecutionError) as raised:
                await CubeRepository(client, self.config).get_metadata()

        self.assertEqual("metadata_out_of_sync", raised.exception.code)
        self.assertFalse(raised.exception.retryable)

    async def test_request_error_is_retryable(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unavailable", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=self.config.base_url
        ) as client:
            with self.assertRaises(QueryExecutionError) as raised:
                await CubeRepository(client, self.config).get_metadata()

        self.assertEqual("cube_unavailable", raised.exception.code)
        self.assertTrue(raised.exception.retryable)

    async def test_other_client_error_is_not_retryable(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(422, text="invalid query")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=self.config.base_url
        ) as client:
            with self.assertRaises(QueryExecutionError) as raised:
                await CubeRepository(client, self.config).get_metadata()

        self.assertEqual("cube_unavailable", raised.exception.code)
        self.assertFalse(raised.exception.retryable)

    async def test_redirect_response_is_not_retryable(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(302, json={"redirect": "/cubejs-api/v1/meta"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url=self.config.base_url,
            follow_redirects=False,
        ) as client:
            with self.assertRaises(QueryExecutionError) as raised:
                await CubeRepository(client, self.config).get_metadata()

        self.assertEqual("cube_unavailable", raised.exception.code)
        self.assertFalse(raised.exception.retryable)

    async def test_json_array_response_is_logged_as_unavailable(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[])

        with patch("app.repositories.cube.cube_repository.logger") as logger:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url=self.config.base_url
            ) as client:
                with self.assertRaises(QueryExecutionError) as raised:
                    await CubeRepository(client, self.config).get_metadata()

        self.assertEqual("cube_unavailable", raised.exception.code)
        self.assertFalse(raised.exception.retryable)
        self.assertEqual("cube_unavailable", logger.info.call_args.args[-1])


if __name__ == "__main__":
    unittest.main()
