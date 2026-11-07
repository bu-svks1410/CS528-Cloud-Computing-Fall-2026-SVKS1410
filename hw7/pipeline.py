import apache_beam as beam

from parsing import parse_page


def ranking_key(item):
    return -item[1], item[0]


class ParsePage(beam.DoFn):
    def process(self, page, valid_names):
        name, content = page
        links, trigrams = parse_page(content)
        valid_links = [target for target in links if target in valid_names]

        yield beam.pvalue.TaggedOutput("outgoing", (name, len(valid_links)))
        yield beam.pvalue.TaggedOutput("incoming", (name, 0))

        for target in valid_links:
            yield beam.pvalue.TaggedOutput("incoming", (target, 1))

        for trigram, count in trigrams.items():
            yield beam.pvalue.TaggedOutput("trigrams", (trigram, count))


def build_analysis(pages, names):
    valid_names = names | "PrepareValidNames" >> beam.Map(
        lambda name: (name, True)
    )

    parsed = (
        pages
        | "ParsePages" >> beam.ParDo(
            ParsePage(),
            valid_names=beam.pvalue.AsDict(valid_names),
        ).with_outputs("outgoing", "incoming", "trigrams")
    )

    outgoing = parsed.outgoing

    incoming = (
        parsed.incoming
        | "SumIncomingLinks" >> beam.CombinePerKey(sum)
    )

    trigrams = (
        parsed.trigrams
        | "SumTrigramOccurrences" >> beam.CombinePerKey(sum)
    )

    top_outgoing = (
        outgoing
        | "TopFiveOutgoing" >> beam.combiners.Top.Smallest(
            5, key=ranking_key
        )
    )

    top_incoming = (
        incoming
        | "TopFiveIncoming" >> beam.combiners.Top.Smallest(
            5, key=ranking_key
        )
    )

    top_trigrams = (
        trigrams
        | "TopFiveTrigrams" >> beam.combiners.Top.Smallest(
            5, key=ranking_key
        )
    )

    page_count = (
        outgoing
        | "CountPages" >> beam.combiners.Count.Globally()
    )

    link_count = (
        outgoing
        | "ExtractOutgoingCounts" >> beam.Values()
        | "CountAllLinks" >> beam.CombineGlobally(sum)
    )

    incoming_total = (
        incoming
        | "ExtractIncomingCounts" >> beam.Values()
        | "CountAllIncomingLinks" >> beam.CombineGlobally(sum)
    )

    trigram_count = (
        trigrams
        | "ExtractTrigramCounts" >> beam.Values()
        | "CountAllTrigrams" >> beam.CombineGlobally(sum)
    )

    return {
        "outgoing": outgoing,
        "incoming": incoming,
        "trigrams": trigrams,
        "top_outgoing": top_outgoing,
        "top_incoming": top_incoming,
        "top_trigrams": top_trigrams,
        "page_count": page_count,
        "link_count": link_count,
        "incoming_total": incoming_total,
        "trigram_count": trigram_count,
    }
