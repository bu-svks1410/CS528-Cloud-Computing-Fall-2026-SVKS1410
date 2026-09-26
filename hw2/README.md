# CS528 HW2

Reads the HTML files from a Google Cloud Storage bucket, builds the link graph and prints:

- Average, median, max, min and quintiles of incoming and outgoing links
- Top 5 pages by PageRank
- The page with the best closeness centrality

## Files

- `analyze.py` – main program
- `graph_algorithms.py` – PageRank and closeness centrality
- `test_graph_algorithms.py`, `test_closeness.py`, `test_parsing.py` – tests
- `generate-content.py` – data generator given with the assignment
- `requirements.txt` – required library

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the tests

```bash
python3 -m unittest -v
```

## Run the program

```bash
python3 analyze.py --bucket <BUCKET_NAME> --workers 16
```

The bucket name is given in the report.

| Option | Meaning |
|---|---|
| `--bucket NAME` | Bucket to read the files from |
| `--prefix P` | Folder inside the bucket (default `data/`) |
| `--workers N` | Number of parallel downloads (default `1`) |
| `--batch-size N` | Files downloaded per batch (default `500`) |
| `--timeout S` | Timeout per request in seconds (default `120`) |
| `--limit N` | Only read the first N files |
| `--auth` | Use Google credentials instead of anonymous access |
| `--local DIR` | Read the files from a local folder instead of a bucket |
