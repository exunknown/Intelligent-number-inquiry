import ast
import unittest
from pathlib import Path

from app.core.query_errors import QueryExecutionError
from app.entities.cube_member import CubeMember


def _measure(name="ecommerce.gmv"):
    return CubeMember(
        name=name,
        cube_name="ecommerce",
        member_type="measure",
        data_type="number",
        title="成交金额",
        description="成交金额",
        aliases=[],
        ai_context="",
        source_column_id="fact_order.amount",
        filterable=False,
    )


class HybridGraphTest(unittest.TestCase):
    def test_graph_contains_metric_path_and_existing_sql_fallback(self):
        from app.agent.graph import graph

        compiled = graph.get_graph()
        nodes = set(compiled.nodes)
        edges = {(edge.source, edge.target) for edge in compiled.edges}

        expected_nodes = {
            "extract_keywords",
            "recall_column",
            "recall_value",
            "recall_cube_member",
            "merge_retrieved_info",
            "semantic_coverage_gate",
            "generate_metric_query",
            "validate_metric_query",
            "execute_cube_query",
            "route_selector",
            "selector_agent",
            "apply_selector",
            "add_extra_context",
            "generate_sql",
            "validate_sql",
            "correct_sql",
            "run_sql",
        }
        self.assertTrue(expected_nodes <= nodes)
        self.assertNotIn("recall_metric", nodes)

        expected_edges = {
            ("extract_keywords", "recall_column"),
            ("extract_keywords", "recall_value"),
            ("extract_keywords", "recall_cube_member"),
            ("recall_column", "merge_retrieved_info"),
            ("recall_value", "merge_retrieved_info"),
            ("recall_cube_member", "merge_retrieved_info"),
            ("merge_retrieved_info", "semantic_coverage_gate"),
            ("semantic_coverage_gate", "generate_metric_query"),
            ("semantic_coverage_gate", "route_selector"),
            ("generate_metric_query", "validate_metric_query"),
            ("validate_metric_query", "execute_cube_query"),
            ("validate_metric_query", "route_selector"),
            ("execute_cube_query", "__end__"),
            ("route_selector", "add_extra_context"),
            ("route_selector", "selector_agent"),
            ("selector_agent", "apply_selector"),
            ("apply_selector", "add_extra_context"),
            ("add_extra_context", "generate_sql"),
            ("generate_sql", "validate_sql"),
            ("validate_sql", "run_sql"),
            ("validate_sql", "correct_sql"),
            ("correct_sql", "run_sql"),
            ("run_sql", "__end__"),
        }
        self.assertTrue(expected_edges <= edges)

    def test_local_debug_closes_all_resource_managers_in_finally(self):
        import app.agent.graph as graph_module

        tree = ast.parse(Path(graph_module.__file__).read_text(encoding="utf-8"))
        main_guard = next(
            node
            for node in tree.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        )
        debug_function = next(
            node
            for node in main_guard.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "test"
        )
        try_node = next(
            (node for node in debug_function.body if isinstance(node, ast.Try)), None
        )

        self.assertIsNotNone(try_node)
        protected_init_calls = [
            node
            for statement in try_node.body
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "init"
        ]
        finally_calls = [
            node
            for statement in try_node.finalbody
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
        ]
        manager_close_calls = [
            call
            for call in finally_calls
            if isinstance(call.func, ast.Attribute) and call.func.attr == "close"
        ]
        embedding_close_calls = [
            call
            for call in finally_calls
            if isinstance(call.func, ast.Name)
            and call.func.id == "_close_embedding_client"
        ]
        gather_calls = [
            call
            for call in finally_calls
            if isinstance(call.func, ast.Attribute)
            and call.func.attr == "gather"
            and any(
                keyword.arg == "return_exceptions"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in call.keywords
            )
        ]
        self.assertEqual(6, len(protected_init_calls))
        self.assertEqual(5, len(manager_close_calls))
        self.assertEqual(1, len(embedding_close_calls))
        self.assertEqual(1, len(gather_calls))


class HybridGraphNoFallbackTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _build_graph(sql_calls):
        from langgraph.constants import END, START
        from langgraph.graph import StateGraph

        from app.agent.context import DataAgentContext
        from app.agent.graph import route_query_mode
        from app.agent.nodes.execute_cube_query import execute_cube_query
        from app.agent.nodes.validate_metric_query import validate_metric_query
        from app.agent.state import DataAgentState

        async def fail_if_sql_runs(state):
            sql_calls.append(state)
            raise AssertionError("metric-path errors must not route to SQL")

        builder = StateGraph(
            state_schema=DataAgentState, context_schema=DataAgentContext
        )
        builder.add_node("validate_metric_query", validate_metric_query)
        builder.add_node("execute_cube_query", execute_cube_query)
        builder.add_node("run_sql", fail_if_sql_runs)
        builder.add_edge(START, "validate_metric_query")
        builder.add_conditional_edges(
            "validate_metric_query",
            route_query_mode,
            {"metric": "execute_cube_query", "sql": "run_sql"},
        )
        builder.add_edge("execute_cube_query", END)
        builder.add_edge("run_sql", END)
        return builder.compile()

    async def test_cube_errors_propagate_through_graph_without_sql_fallback(self):
        class _CubeRepository:
            def __init__(self, error):
                self.error = error
                self.calls = []

            async def load(self, query):
                self.calls.append(query)
                raise self.error

        measure = _measure()
        for code in (
            "cube_timeout",
            "cube_unauthorized",
            "cube_unavailable",
            "metadata_out_of_sync",
        ):
            with self.subTest(code=code):
                sql_calls = []
                error = QueryExecutionError(code, f"{code} message", False)
                repository = _CubeRepository(error)
                graph = self._build_graph(sql_calls)

                with self.assertRaises(QueryExecutionError) as raised:
                    await graph.ainvoke(
                        {
                            "retrieved_cube_measures": [measure],
                            "cube_member_catalog": {measure.name: measure},
                            "metric_query_raw": {
                                "status": "matched",
                                "query": {"measures": [measure.name]},
                            },
                        },
                        context={"cube_repository": repository},
                    )

                self.assertIs(error, raised.exception)
                self.assertEqual(1, len(repository.calls))
                self.assertEqual([], sql_calls)

    async def test_validation_error_stops_graph_before_any_execution_branch(self):
        class _CubeRepository:
            def __init__(self):
                self.calls = []

            async def load(self, query):
                self.calls.append(query)
                raise AssertionError("validation failure must not execute Cube")

        measure = _measure()
        repository = _CubeRepository()
        sql_calls = []
        graph = self._build_graph(sql_calls)

        with self.assertRaises(QueryExecutionError) as raised:
            await graph.ainvoke(
                {
                    "retrieved_cube_measures": [measure],
                    "cube_member_catalog": {measure.name: measure},
                    "metric_query_raw": {
                        "status": "matched",
                        "query": {"measures": ["ecommerce.unknown"]},
                    },
                },
                context={"cube_repository": repository},
            )

        self.assertEqual("unknown_member", raised.exception.code)
        self.assertEqual([], repository.calls)
        self.assertEqual([], sql_calls)


if __name__ == "__main__":
    unittest.main()
