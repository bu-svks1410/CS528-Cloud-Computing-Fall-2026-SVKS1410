import argparse
import csv
import http.client
import itertools
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

WORKLOAD = Path(__file__).with_name("workload.csv")


def send(host, port, sequence, sample, timeout):
    path = sample["path"]
    headers = {key: value for key, value in sample.items() if key.startswith("X-")}
    headers["X-time"] = f"{date.today()} {sample['hour']}"
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    row = dict(sequence=sequence, sent=time.time(), path=path, country=headers["X-country"],
               status=None, zone=None, error=None)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        row.update(status=response.status, zone=response.getheader("X-Server-Zone"))
        response.read()
    except (OSError, http.client.HTTPException) as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        connection.close()
    row["received"] = time.time()
    return row


def run(host, port, output, stop, count=None):
    with WORKLOAD.open() as source:
        samples = list(csv.DictReader(source))
    lock = threading.Lock()

    with output.open("x", buffering=1) as log, ThreadPoolExecutor(max_workers=8) as pool:
        def record(seq, sample):
            row = send(host, port, seq, sample, 3)
            line = json.dumps(row)
            with lock:
                log.write(line + "\n")
                print(line, flush=True)

        start = time.monotonic()
        futures = []
        for seq, sample in enumerate(itertools.cycle(samples)):
            if count is not None and seq >= count:
                break
            if stop.wait(max(0, start + seq - time.monotonic())):
                break
            for future in list(futures):
                if future.done():
                    future.result()
                    futures.remove(future)
            futures.append(pool.submit(record, seq + 1, sample))
        for future in futures:
            future.result()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.host, args.port, args.output, threading.Event(), args.count)
