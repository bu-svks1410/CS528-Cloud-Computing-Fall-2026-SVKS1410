import unittest
from collections import Counter

from parsing import parse_page


class ParsingTests(unittest.TestCase):
    def test_repeated_links_and_uppercase_href(self):
        content = (
            '<a HREF="1.html">First</a>'
            '<a href="1.html">Second</a>'
            '<a href="0.html">Third</a>'
        )
        links, _ = parse_page(content)
        self.assertEqual(links, ["1.html", "1.html", "0.html"])

    def test_words_exclude_html_attributes(self):
        content = '<p>Hello, WORLD!</p><a href="999.html">Again</a>'
        _, trigrams = parse_page(content)
        self.assertEqual(trigrams, Counter({"hello world again": 1}))

    def test_overlapping_repeated_trigrams(self):
        _, trigrams = parse_page("<p>one two one two one</p>")
        self.assertEqual(
            trigrams,
            Counter({"one two one": 2, "two one two": 1}),
        )

    def test_sequences_continue_across_lines_and_paragraphs(self):
        _, trigrams = parse_page("<p>one\ntwo</p><p>three four</p>")
        self.assertEqual(
            trigrams,
            Counter({"one two three": 1, "two three four": 1}),
        )

    def test_short_and_empty_files(self):
        for content in ("", "<html><body></body></html>", "<p>one two</p>"):
            with self.subTest(content=content):
                links, trigrams = parse_page(content)
                self.assertEqual(links, [])
                self.assertEqual(trigrams, Counter())

    def test_files_remain_separate(self):
        _, first = parse_page("<p>one two</p>")
        _, second = parse_page("<p>three four</p>")
        self.assertEqual(first + second, Counter())

    def test_hidden_text_is_excluded(self):
        content = (
            "<p>one two</p>"
            "<script>hidden script words</script>"
            "<style>hidden style words</style>"
            "<p>three</p>"
        )
        _, trigrams = parse_page(content)
        self.assertEqual(trigrams, Counter({"one two three": 1}))


if __name__ == "__main__":
    unittest.main()
