import unittest


class GraphSelectorTest(unittest.TestCase):
    def test_graph_contains_token_gate_and_conditional_selector_path(self):
        from app.agent.graph import graph

        compiled = graph.get_graph()
        self.assertIn("route_selector", compiled.nodes)
        self.assertIn("selector_agent", compiled.nodes)
        self.assertIn("apply_selector", compiled.nodes)

        edges = {(edge.source, edge.target) for edge in compiled.edges}
        self.assertIn(("route_selector", "add_extra_context"), edges)
        self.assertIn(("route_selector", "selector_agent"), edges)
        self.assertIn(("selector_agent", "apply_selector"), edges)
        self.assertIn(("apply_selector", "add_extra_context"), edges)


if __name__ == "__main__":
    unittest.main()
