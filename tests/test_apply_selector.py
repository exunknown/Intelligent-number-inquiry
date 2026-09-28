import copy
import unittest


class ApplySelectorTest(unittest.TestCase):
    def test_keeps_tables_and_selected_values_without_mutating_input(self):
        from app.agent.nodes.apply_selector import apply_selector_decision

        table_infos = [
            {
                "name": "orders",
                "role": "fact",
                "description": "订单事实表",
                "columns": [
                    {
                        "name": "amount",
                        "type": "decimal",
                        "role": "measure",
                        "examples": [100, 200],
                        "description": "订单金额",
                        "alias": [],
                    },
                    {
                        "name": "region_name",
                        "type": "varchar",
                        "role": "dimension",
                        "examples": ["华北", "华南"],
                        "description": "地区",
                        "alias": [],
                    },
                ],
            },
            {
                "name": "users",
                "role": "dimension",
                "description": "用户维度表",
                "columns": [
                    {
                        "name": "user_id",
                        "type": "bigint",
                        "role": "key",
                        "examples": [],
                        "description": "用户 ID",
                        "alias": [],
                    }
                ],
            },
        ]
        original = copy.deepcopy(table_infos)
        candidates = {
            "tables": [
                {
                    "id": "table-orders",
                    "name": "orders",
                    "role": "fact",
                    "description": "订单事实表",
                    "columns": [
                        {
                            "id": "column-amount",
                            "table_id": "table-orders",
                            "name": "amount",
                            "type": "decimal",
                            "role": "measure",
                            "examples": [100, 200],
                            "description": "订单金额",
                            "alias": [],
                        },
                        {
                            "id": "column-region",
                            "table_id": "table-orders",
                            "name": "region_name",
                            "type": "varchar",
                            "role": "dimension",
                            "examples": ["华北", "华南"],
                            "description": "地区",
                            "alias": [],
                        },
                    ],
                },
                {
                    "id": "table-users",
                    "name": "users",
                    "role": "dimension",
                    "description": "用户维度表",
                    "columns": [],
                },
            ],
            "metrics": [],
            "values": [
                {"id": "value-north", "value": "华北", "column_id": "column-region"},
                {"id": "value-south", "value": "华南", "column_id": "column-region"},
            ],
        }
        decision = {
            "keep_tables": ["table-orders"],
            "drop_tables": ["table-users"],
            "keep_values": [{"value_id": "value-north", "column_id": "column-region"}],
        }

        result = apply_selector_decision(table_infos, candidates, decision)

        self.assertEqual([table["name"] for table in result], ["orders"])
        self.assertEqual(result[0]["columns"][1]["examples"], ["华北"])
        self.assertEqual(table_infos, original)


if __name__ == "__main__":
    unittest.main()
