import argparse
import io
import platform
import time
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from statistics import mean, median, quantiles

from graph_algorithms import closeness_centrality, pagerank


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for key, value in attrs:
                if key == "href" and value is not None:
                    self.links.append(value)


def parse_links(content, valid_names):
    parser = LinkParser()
    parser.feed(content)
    parser.close()
    return [target for target in parser.links if target in valid_names]


def build_graph(pages):
    return {
        name: parse_links(content, pages)
        for name, content in pages.items()
    }


def page_sort_key(name):
    stem = name.rsplit(".", 1)[0]
    return (0, int(stem), name) if stem.isdigit() else (1, 0, name)


class Timer:
    def __init__(self):
        self.listing = 0.0
        self.download = 0.0
        self.bytes = 0
        self.retries = 0


def local_source(directory, limit, timer):
    start = time.perf_counter()
    files = sorted(Path(directory).glob("*.html"),
                   key=lambda p: page_sort_key(p.name))
    if limit:
        files = files[:limit]
    timer.listing = time.perf_counter() - start
    names = [p.name for p in files]

    def pages():
        for path in files:
            t0 = time.perf_counter()
            data = path.read_bytes()
            timer.download += time.perf_counter() - t0
            timer.bytes += len(data)
            yield path.name, data.decode("utf-8")

    return names, pages()


def make_client(use_auth):
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise SystemExit(
            "google-cloud-storage is not installed. Run:\n"
            "  pip install -r requirements.txt"
        ) from exc
    if use_auth:
        return storage.Client()
    return storage.Client.create_anonymous_client()


def bucket_source(bucket_name, prefix, limit, workers, batch_size,
                  timeout, use_auth, timer):
    client = make_client(use_auth)

    start = time.perf_counter()
    blobs = [
        blob for blob in client.list_blobs(bucket_name, prefix=prefix)
        if blob.name.endswith(".html")
    ]
    blobs.sort(key=lambda b: page_sort_key(b.name.rsplit("/", 1)[-1]))
    if limit:
        blobs = blobs[:limit]
    timer.listing = time.perf_counter() - start
    names = [b.name.rsplit("/", 1)[-1] for b in blobs]

    def download_one(blob):
        for attempt in range(1, 4):
            try:
                return blob.download_as_bytes(timeout=timeout)
            except Exception:
                if attempt == 3:
                    raise
                timer.retries += 1
                time.sleep(2 * attempt)

    def download_batch(batch):
        if workers <= 1:
            return [download_one(blob) for blob in batch]
        from google.cloud.storage import transfer_manager
        buffers = [io.BytesIO() for _ in batch]
        results = transfer_manager.download_many(
            list(zip(batch, buffers)),
            download_kwargs={"timeout": timeout},
            max_workers=workers,
            worker_type=transfer_manager.THREAD,
        )
        contents = []
        for blob, buffer, result in zip(batch, buffers, results):
            if isinstance(result, Exception):
                timer.retries += 1
                contents.append(download_one(blob))
            else:
                contents.append(buffer.getvalue())
        return contents

    def pages():
        for first in range(0, len(blobs), batch_size):
            batch = blobs[first:first + batch_size]
            t0 = time.perf_counter()
            contents = download_batch(batch)
            timer.download += time.perf_counter() - t0
            for blob, data in zip(batch, contents):
                timer.bytes += len(data)
                yield blob.name.rsplit("/", 1)[-1], data.decode("utf-8")

    return names, pages()


def print_statistics(label, values):
    cuts = (quantiles(values, n=5, method="inclusive")
            if len(values) > 1 else values * 4)
    quintiles = cuts + [max(values)]
    print(f"\n{label}")
    print(f"  Average: {mean(values):.4f}")
    print(f"  Median:  {median(values):.4f}")
    print(f"  Maximum: {max(values)}")
    print(f"  Minimum: {min(values)}")
    print("  Quintiles (20%, 40%, 60%, 80%, 100%): "
          + ", ".join(f"{v:.4f}" for v in quintiles))


def main():
    parser = argparse.ArgumentParser(
        description="Link statistics, PageRank and closeness centrality "
                    "for a directory of HTML pages.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bucket",
                        help="Google Cloud Storage bucket holding the pages")
    source.add_argument("--local",
                        help="Local directory holding the pages instead")
    parser.add_argument("--prefix", default="data/",
                        help="Object prefix (folder) inside the bucket "
                             "(default: data/)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel download threads using the storage "
                             "library's transfer manager (default: 1 = "
                             "fully sequential). Processing is always "
                             "single-threaded.")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Pages downloaded per batch (default: 500)")
    parser.add_argument("--timeout", type=float, default=120,
                        help="Per-request timeout in seconds (default: 120)")
    parser.add_argument("--auth", action="store_true",
                        help="Use your Google credentials instead of "
                             "anonymous access")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only read the first N pages (smoke tests)")
    args = parser.parse_args()

    start = time.perf_counter()
    timer = Timer()

    print("Python:", platform.python_version())
    print("Platform:", platform.platform())
    if args.bucket:
        print(f"Source: gs://{args.bucket}/{args.prefix} "
              f"(workers={args.workers}, "
              f"{'authenticated' if args.auth else 'anonymous'})")
        names, pages = bucket_source(
            args.bucket, args.prefix, args.limit, args.workers,
            args.batch_size, args.timeout, args.auth, timer)
    else:
        print(f"Source: local directory {args.local}")
        names, pages = local_source(args.local, args.limit, timer)

    if not names:
        parser.error("No HTML files found.")
    print(f"Files found: {len(names)} (listing took {timer.listing:.3f} s)",
          flush=True)
    print("Reading and parsing files...", flush=True)

    valid = set(names)
    graph = {}
    for number, (name, text) in enumerate(pages, 1):
        graph[name] = parse_links(text, valid)
        if number % 1000 == 0 or number == len(names):
            elapsed = time.perf_counter() - start
            print(f"  {number}/{len(names)} files, {elapsed:.1f} s",
                  flush=True)
    loaded = time.perf_counter()

    incoming = Counter()
    for targets in graph.values():
        incoming.update(targets)
    outgoing_counts = [len(graph[node]) for node in graph]
    incoming_counts = [incoming[node] for node in graph]
    assert sum(outgoing_counts) == sum(incoming_counts)

    print(f"\nPages (nodes): {len(graph)}")
    print(f"Links (edges): {sum(outgoing_counts)}")
    print_statistics("Outgoing links per page", outgoing_counts)
    print_statistics("Incoming links per page", incoming_counts)
    stats_done = time.perf_counter()

    print("\nComputing PageRank...", flush=True)
    history = []
    ranks, iterations = pagerank(graph, history=history)
    pr_done = time.perf_counter()
    print("  iter   sum of PR      sum change   sum|new-old|")
    for it, total, sum_change, l1 in history:
        print(f"  {it:4d}   {total:.10f}   {sum_change:.2e}   {l1:.2e}")
    print(f"PageRank converged after {iterations} iterations")
    print("Top 5 pages by PageRank:")
    for rank, (name, score) in enumerate(sorted(
            ranks.items(), key=lambda item: (-item[1], item[0]))[:5], 1):
        print(f"  {rank}. {name}: {score:.10f}")

    print("\nComputing closeness centrality (outward BFS from every "
          "page)...", flush=True)
    closeness = closeness_centrality(graph)
    cc_done = time.perf_counter()
    best = max(closeness.values())
    winners = sorted((name for name, score in closeness.items()
                      if score == best), key=page_sort_key)
    print("Best closeness centrality:", ", ".join(winners))
    print(f"Closeness score: {best:.10f}")

    network = timer.listing + timer.download
    parse = (loaded - start) - network
    mib = timer.bytes / 2**20
    print("\nTiming (seconds)")
    print(f"  Listing files:                 {timer.listing:10.3f}")
    print(f"  Downloading/reading files:     {timer.download:10.3f}"
          f"   ({mib:.1f} MiB, "
          f"{mib / timer.download if timer.download else 0:.2f} MiB/s)")
    print(f"  Parsing + graph construction:  {parse:10.3f}")
    print(f"  Link statistics:               {stats_done - loaded:10.3f}")
    print(f"  PageRank:                      {pr_done - stats_done:10.3f}")
    print(f"  Closeness centrality:          {cc_done - pr_done:10.3f}")
    print(f"  TOTAL:                         {cc_done - start:10.3f}")
    if timer.retries:
        print(f"  (download retries: {timer.retries})")


if __name__ == "__main__":
    main()
