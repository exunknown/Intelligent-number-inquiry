import unittest


class SelectorConfigTest(unittest.TestCase):
    def test_selector_config_is_loaded(self):
        from app.conf.app_config import app_config

        self.assertTrue(app_config.selector.enabled)
        self.assertGreater(app_config.selector.schema_token_threshold, 0)
        self.assertGreater(app_config.selector.token_estimate_chars_per_token, 0)


if __name__ == "__main__":
    unittest.main()
