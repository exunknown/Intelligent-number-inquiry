import unittest
from pathlib import Path


class EnvExampleTest(unittest.TestCase):
    def test_ini_api_key_has_a_non_secret_placeholder(self):
        content = Path(".env.example").read_text(encoding="utf-8")

        self.assertIn("INI_API_KEY=your_ini_api_key_here", content.splitlines())


if __name__ == "__main__":
    unittest.main()
