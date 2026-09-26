import unittest
from graph_algorithms import pagerank


class PageRankTests(unittest.TestCase):
    def test_three_page_cycle(self):
        graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        scores, _ = pagerank(graph)
        for score in scores.values():
            self.assertAlmostEqual(score, 1.0 / 3.0, places=8)

    def test_dangling_page(self):
        graph = {"A": ["B"], "B": []}
        scores, iterations = pagerank(graph)
        self.assertAlmostEqual(scores["A"], 20.0 / 57.0, places=8)
        self.assertAlmostEqual(scores["B"], 37.0 / 57.0, places=8)
        self.assertAlmostEqual(sum(scores.values()), 1.0, places=8)
        self.assertGreater(iterations, 1)


if __name__ == "__main__":
    unittest.main()
