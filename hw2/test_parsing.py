import unittest
from statistics import quantiles

from analyze import build_graph, parse_links


class ParsingTests(unittest.TestCase):
    def test_uppercase_href_and_unknown_targets(self):
        html = ('<a HREF="1.html"> x </a><p><a href="2.html">y</a>'
                '<a HREF="99.html">z</a><a name="no-href">w</a>')
        self.assertEqual(parse_links(html, {"1.html", "2.html"}),
                         ["1.html", "2.html"])

    def test_duplicate_links_are_kept(self):
        pages = {
            "0.html": '<a HREF="1.html">a</a><a HREF="1.html">b</a>',
            "1.html": '<a HREF="0.html">c</a>',
            "2.html": "<p>no links</p>",
        }
        graph = build_graph(pages)
        self.assertEqual(graph["0.html"], ["1.html", "1.html"])
        self.assertEqual(graph["1.html"], ["0.html"])
        self.assertEqual(graph["2.html"], [])

    def test_quintiles_of_known_list(self):
        self.assertEqual(
            quantiles(range(1, 12), n=5, method="inclusive"),
            [3.0, 5.0, 7.0, 9.0])


if __name__ == "__main__":
    unittest.main()
