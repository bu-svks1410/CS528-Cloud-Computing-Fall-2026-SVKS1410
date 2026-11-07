import re
from collections import Counter
from html.parser import HTMLParser


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.text_parts = []
        self.hidden_tags = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden_tags.append(tag)
        if tag == "a":
            for key, value in attrs:
                if key == "href" and value is not None:
                    self.links.append(value)
                    break

    def handle_endtag(self, tag):
        if self.hidden_tags and tag == self.hidden_tags[-1]:
            self.hidden_tags.pop()

    def handle_data(self, data):
        if not self.hidden_tags:
            self.text_parts.append(data)


def parse_page(content):
    parser = PageParser()
    parser.feed(content)
    parser.close()
    words = re.findall(r"[a-z]+", " ".join(parser.text_parts).lower())
    trigrams = Counter(
        " ".join(words[index:index + 3])
        for index in range(len(words) - 2)
    )
    return parser.links, trigrams
