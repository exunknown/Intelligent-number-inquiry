import unittest
from pathlib import Path

import yaml


class CubeModelContractTest(unittest.TestCase):
    def _documents(self) -> list[dict]:
        repo_root = Path(__file__).parents[1]
        model_dir = repo_root / "cube" / "model"
        return [
            yaml.safe_load(model_path.read_text(encoding="utf-8"))
            for model_path in sorted(model_dir.glob("*.yml"))
        ]

    def test_compose_pins_cube_and_does_not_enable_dev_mode(self) -> None:
        repo_root = Path(__file__).parents[1]
        compose_path = repo_root / "docker" / "docker-compose.yaml"
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

        self.assertIn("cube", compose["services"])

        cube = compose["services"]["cube"]
        self.assertEqual("cubejs/cube:v1.7.46", cube["image"])
        self.assertEqual("false", cube["environment"]["CUBEJS_DEV_MODE"])
        self.assertEqual("mysql", cube["environment"]["CUBEJS_DB_HOST"])
        self.assertEqual("dw", cube["environment"]["CUBEJS_DB_NAME"])
        self.assertEqual("3306", cube["environment"]["CUBEJS_DB_PORT"])
        self.assertEqual("${CUBE_API_SECRET}", cube["environment"]["CUBEJS_API_SECRET"])
        self.assertEqual("${CUBE_DB_USER}", cube["environment"]["CUBEJS_DB_USER"])
        self.assertEqual("${CUBE_DB_PASSWORD}", cube["environment"]["CUBEJS_DB_PASS"])
        self.assertIn("../cube:/cube/conf", cube["volumes"])

    def test_only_ecommerce_view_is_public(self) -> None:
        documents = self._documents()

        self.assertTrue(documents, "Cube model documents must exist")

        cubes = [cube for document in documents for cube in document.get("cubes", [])]
        self.assertEqual(
            {"orders", "regions", "products", "customers", "dates"},
            {cube["name"] for cube in cubes},
        )
        self.assertTrue(all(cube.get("public") is False for cube in cubes))

        base_cubes = {cube["name"]: cube for cube in cubes}
        self.assertEqual(
            {"gmv", "order_count", "sales_quantity", "aov"},
            {measure["name"] for measure in base_cubes["orders"]["measures"]},
        )

        expected_dimensions = {
            "regions": {"region_name", "province", "country"},
            "products": {"product_name", "category", "brand"},
            "customers": {"customer_name", "gender", "member_level"},
            "dates": {"order_date"},
        }
        for cube_name, expected_names in expected_dimensions.items():
            dimensions = base_cubes[cube_name]["dimensions"]
            primary_keys = {
                dimension["name"]
                for dimension in dimensions
                if dimension.get("primary_key")
            }
            self.assertEqual(
                expected_names,
                {dimension["name"] for dimension in dimensions} - primary_keys,
            )

        views = [view for document in documents for view in document.get("views", [])]
        self.assertEqual(1, len(views))
        self.assertEqual("ecommerce", views[0]["name"])
        self.assertIs(True, views[0]["public"])

    def test_ecommerce_exposes_governed_members(self) -> None:
        documents = self._documents()
        views = [view for document in documents for view in document.get("views", [])]
        ecommerce_views = [view for view in views if view.get("name") == "ecommerce"]

        self.assertEqual(1, len(ecommerce_views))

        ecommerce = ecommerce_views[0]
        expected_join_paths = {
            "orders",
            "orders.regions",
            "orders.products",
            "orders.customers",
            "orders.dates",
        }
        self.assertEqual(
            expected_join_paths,
            {cube["join_path"] for cube in ecommerce["cubes"]},
        )
        self.assertTrue(all(cube["prefix"] is False for cube in ecommerce["cubes"]))

        expected_members = {
            "gmv",
            "order_count",
            "sales_quantity",
            "aov",
            "region_name",
            "province",
            "country",
            "product_name",
            "category",
            "brand",
            "customer_name",
            "gender",
            "member_level",
            "order_date",
        }
        self.assertEqual(
            expected_members,
            {
                member_name
                for cube in ecommerce["cubes"]
                for member_name in cube["includes"]
            },
        )

    def test_reader_grant_converges_to_select_only(self) -> None:
        repo_root = Path(__file__).parents[1]
        script_path = repo_root / "docker" / "mysql" / "zz-cube-reader.sh"
        script = script_path.read_text(encoding="utf-8")

        self.assertIn("GRANT SELECT ON dw.* TO", script)
        self.assertNotIn("`dw`", script)

        drop_sql = "SET @drop_sql = CONCAT('DROP USER IF EXISTS ', @account);"
        create_sql = "SET @create_sql = CONCAT('CREATE USER ', @account,"
        grant_sql = "SET @grant_sql = CONCAT('GRANT SELECT ON dw.* TO ', @account);"

        self.assertIn(drop_sql, script)
        self.assertIn("PREPARE drop_stmt FROM @drop_sql;", script)
        self.assertIn("EXECUTE drop_stmt;", script)
        self.assertIn(create_sql, script)
        self.assertIn(grant_sql, script)
        self.assertNotIn("CREATE USER IF NOT EXISTS", script)
        self.assertNotIn("ALTER USER", script)
        self.assertLess(script.index(drop_sql), script.index(create_sql))
        self.assertLess(script.index(create_sql), script.index(grant_sql))

    def test_compose_configures_single_node_cubestore(self) -> None:
        repo_root = Path(__file__).parents[1]
        compose_path = repo_root / "docker" / "docker-compose.yaml"
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

        self.assertIn("cubestore", compose["services"])

        cubestore = compose["services"]["cubestore"]
        self.assertEqual("cubejs/cubestore:v1.7.46", cubestore["image"])
        self.assertFalse(cubestore.get("ports"))
        self.assertEqual("/cube/data", cubestore["environment"]["CUBESTORE_REMOTE_DIR"])
        self.assertIn("cubestore_data:/cube/data", cubestore["volumes"])

        cube = compose["services"]["cube"]
        self.assertEqual("cubestore", cube["environment"]["CUBEJS_CUBESTORE_HOST"])
        self.assertEqual("3030", cube["environment"]["CUBEJS_CUBESTORE_PORT"])
        self.assertIn("cubestore", cube["depends_on"])
        self.assertIn("cubestore_data", compose["volumes"])


if __name__ == "__main__":
    unittest.main()
