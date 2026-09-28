import unittest


class SelectorPolicyTest(unittest.TestCase):
    def test_uses_injected_token_counter(self):
        from app.agent.selector import estimate_token_count

        self.assertEqual(
            estimate_token_count("schema", token_counter=lambda text: 17),
            17,
        )

    def test_selector_starts_only_when_count_exceeds_threshold(self):
        from app.agent.selector import should_use_selector

        self.assertEqual(
            should_use_selector("schema", threshold=10, token_counter=lambda _: 10),
            (False, 10),
        )
        self.assertEqual(
            should_use_selector("schema", threshold=10, token_counter=lambda _: 11),
            (True, 11),
        )


class SelectorValidationTest(unittest.TestCase):
    def test_validates_complete_table_and_value_selection(self):
        from app.agent.selector import validate_selector_result

        decision = validate_selector_result(
            {
                "keep_tables": ["orders"],
                "drop_tables": ["users"],
                "keep_values": [{"value_id": "v-north", "column_id": "region-name"}],
            },
            candidate_tables={"orders", "users"},
            candidate_values={"v-north": "region-name"},
            candidate_columns={"region-name"},
        )

        self.assertEqual(decision["keep_tables"], ["orders"])
        self.assertEqual(decision["keep_values"][0]["column_id"], "region-name")

    def test_rejects_value_bound_to_wrong_column(self):
        from app.agent.selector import validate_selector_result

        with self.assertRaises(ValueError):
            validate_selector_result(
                {
                    "keep_tables": ["orders"],
                    "drop_tables": ["users"],
                    "keep_values": [{"value_id": "v-north", "column_id": "order-id"}],
                },
                candidate_tables={"orders", "users"},
                candidate_values={"v-north": "region-name"},
                candidate_columns={"region-name", "order-id"},
            )

    def test_rejects_unknown_keys(self):
        from app.agent.selector import validate_selector_result

        with self.assertRaises(ValueError):
            validate_selector_result(
                {
                    "keep_tables": ["orders"],
                    "drop_tables": ["users"],
                    "keep_values": [],
                    "explanation": "not allowed",
                },
                candidate_tables={"orders", "users"},
                candidate_values={},
                candidate_columns=set(),
            )


if __name__ == "__main__":
    unittest.main()
