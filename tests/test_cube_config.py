import unittest


class CubeConfigTest(unittest.TestCase):
    def test_cube_config_is_loaded(self) -> None:
        from app.conf.app_config import app_config

        self.assertEqual(500, app_config.cube.max_limit)
        self.assertEqual("ecommerce", app_config.cube.semantic_view)
        self.assertTrue(app_config.cube.base_url.endswith("/cubejs-api"))


if __name__ == "__main__":
    unittest.main()
