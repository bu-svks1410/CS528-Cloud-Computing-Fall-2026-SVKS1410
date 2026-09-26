import unittest
from graph_algorithms import closeness_centrality


class ClosenessTests(unittest.TestCase):
    def test_directed_chain(self):
        graph = {"A": ["B"], "B": ["C"], "C": []}
        scores = closeness_centrality(graph)
        self.assertAlmostEqual(scores["A"], 2.0 / 3.0)
        self.assertAlmostEqual(scores["B"], 0.5)
        self.assertEqual(scores["C"], 0.0)

    def test_outward_star(self):
        graph = {"A": ["B", "C", "D"], "B": [], "C": [], "D": []}
        scores = closeness_centrality(graph)
        self.assertEqual(scores["A"], 1.0)
        for node in ["B", "C", "D"]:
            self.assertEqual(scores[node], 0.0)

    def test_disconnected_and_duplicate_links(self):
        graph = {"A": ["A", "B", "B", "C"], "B": [], "C": [], "D": []}
        scores = closeness_centrality(graph)
        self.assertAlmostEqual(scores["A"], 2.0 / 3.0)
        self.assertEqual(scores["D"], 0.0)


if __name__ == "__main__":
    unittest.main()
