import unittest

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.testing.util import assert_that, equal_to

from pipeline import build_analysis


class PipelineTests(unittest.TestCase):
    def test_known_dataset(self):
        pages = [
            (
                "0.html",
                '<p>one two one two one</p>'
                '<a HREF="1.html"></a>'
                '<a href="1.html"></a>'
                '<a href="2.html"></a>'
                '<a href="99.html"></a>',
            ),
            (
                "1.html",
                '<p>one two three four five six seven eight</p>'
                '<a href="0.html"></a>',
            ),
            (
                "2.html",
                '<p>one two three</p>'
                '<a href="2.html"></a>',
            ),
            ("3.html", "<p>one two</p>"),
            ("4.html", "<p>three four</p>"),
            ("5.html", "<html><body></body></html>"),
        ]

        outgoing = [
            ("0.html", 3),
            ("1.html", 1),
            ("2.html", 1),
            ("3.html", 0),
            ("4.html", 0),
            ("5.html", 0),
        ]

        incoming = [
            ("0.html", 1),
            ("1.html", 2),
            ("2.html", 2),
            ("3.html", 0),
            ("4.html", 0),
            ("5.html", 0),
        ]

        trigrams = [
            ("one two one", 2),
            ("two one two", 1),
            ("one two three", 2),
            ("two three four", 1),
            ("three four five", 1),
            ("four five six", 1),
            ("five six seven", 1),
            ("six seven eight", 1),
        ]

        options = PipelineOptions(
            ["--runner=DirectRunner", "--direct_num_workers=1"]
        )

        with beam.Pipeline(options=options) as pipeline:
            page_collection = (
                pipeline
                | "CreateTestPages" >> beam.Create(pages)
            )
            names = (
                pipeline
                | "CreateTestNames" >> beam.Create(
                    [name for name, _ in pages]
                )
            )

            results = build_analysis(page_collection, names)

            expected = {
                "outgoing": outgoing,
                "incoming": incoming,
                "trigrams": trigrams,
                "top_outgoing": [[
                    ("0.html", 3),
                    ("1.html", 1),
                    ("2.html", 1),
                    ("3.html", 0),
                    ("4.html", 0),
                ]],
                "top_incoming": [[
                    ("1.html", 2),
                    ("2.html", 2),
                    ("0.html", 1),
                    ("3.html", 0),
                    ("4.html", 0),
                ]],
                "top_trigrams": [[
                    ("one two one", 2),
                    ("one two three", 2),
                    ("five six seven", 1),
                    ("four five six", 1),
                    ("six seven eight", 1),
                ]],
                "page_count": [6],
                "link_count": [5],
                "incoming_total": [5],
                "trigram_count": [10],
            }

            for name, values in expected.items():
                assert_that(
                    results[name],
                    equal_to(values),
                    label=f"Check_{name}",
                )


if __name__ == "__main__":
    unittest.main()
