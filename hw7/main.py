import argparse
import json
import logging
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import apache_beam as beam
from apache_beam.io import fileio
from apache_beam.io.filesystems import FileSystems
from apache_beam.options.pipeline_options import (
    PipelineOptions,
    SetupOptions,
    StandardOptions,
)
from apache_beam.runners.runner import PipelineState

from pipeline import build_analysis
from reader import ReadPage


def file_name(metadata):
    return metadata.path.rsplit("/", 1)[-1]



def assemble_report(unused, **values):
    if values["page_count"] == 0:
        raise ValueError("No HTML files were processed")
    if values["link_count"] != values["incoming_total"]:
        raise ValueError("Incoming and outgoing link totals do not match")
    return values


def encode_report(report):
    return json.dumps(report, sort_keys=True)


def print_results(report):
    print(f"\nFiles processed: {report['page_count']}")
    print(f"Total outgoing links: {report['link_count']}")
    print(f"Total incoming links: {report['incoming_total']}")
    print(f"Total trigram occurrences: {report['trigram_count']}")

    sections = [
        ("Top 5 files by incoming links", "top_incoming"),
        ("Top 5 files by outgoing links", "top_outgoing"),
        ("Top 5 most frequent trigrams", "top_trigrams"),
    ]

    for title, key in sections:
        print(f"\n{title}")
        for rank, (name, count) in enumerate(report[key], 1):
            print(f"{rank}. {name}: {count}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timing-file", required=True)
    parser.add_argument("--expected-files", type=int)
    args, beam_args = parser.parse_known_args()

    options = PipelineOptions(beam_args)
    options.view_as(SetupOptions).save_main_session = True
    runner = options.view_as(StandardOptions).runner or "DirectRunner"

    if runner == "DataflowRunner" and not args.output.startswith("gs://"):
        parser.error("Dataflow output must use a gs:// path")

    if not args.output.startswith("gs://"):
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    timing_path = Path(args.timing_file)
    timing_path.parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()

    pipeline = beam.Pipeline(options=options)

    matched = (
        pipeline
        | "FindHTMLFiles" >> fileio.MatchFiles(
            args.input,
            empty_match_treatment=fileio.EmptyMatchTreatment.DISALLOW,
        )
    )

    names = matched | "ExtractFileNames" >> beam.Map(file_name)

    pages = (
        matched
        | "DistributeFiles" >> beam.Reshuffle()
        | "ReadHTML" >> beam.ParDo(
            ReadPage(options.get_all_options().get("project"))
        )
    )

    analysis = build_analysis(pages, names)

    report_keys = [
        "top_incoming",
        "top_outgoing",
        "top_trigrams",
        "page_count",
        "link_count",
        "incoming_total",
        "trigram_count",
    ]

    report_inputs = {
        key: beam.pvalue.AsSingleton(analysis[key])
        for key in report_keys
    }

    report = (
        pipeline
        | "CreateReportSeed" >> beam.Create([None])
        | "AssembleReport" >> beam.Map(
            assemble_report,
            **report_inputs,
        )
    )

    (
        report
        | "EncodeReport" >> beam.Map(encode_report)
        | "SaveReport" >> beam.io.WriteToText(
            args.output,
            file_name_suffix=".json",
            num_shards=1,
            shard_name_template="",
        )
    )

    print(f"Runner: {runner}", flush=True)
    print(f"Input: {args.input}", flush=True)
    print("Starting pipeline...", flush=True)

    result = pipeline.run()

    job_id = None
    if hasattr(result, "job_id"):
        job_id = result.job_id()
        print(f"Dataflow job ID: {job_id}", flush=True)

    state = result.wait_until_finish()
    elapsed = time.perf_counter() - started

    timing = {
        "runner": runner,
        "state": str(state),
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "timing_scope": (
            "Pipeline construction, input listing and reading, processing, "
            "output writing, and waiting for completion. Dataflow also "
            "includes submission, staging, and worker startup."
        ),
        "input": args.input,
        "output": args.output + ".json",
        "python_version": platform.python_version(),
        "beam_version": beam.__version__,
        "launch_platform": platform.platform(),
        "launch_machine": platform.machine(),
        "dataflow_job_id": job_id,
        "pipeline_options": {
            key: options.get_all_options().get(key)
            for key in [
                "direct_num_workers",
                "direct_running_mode",
                "region",
                "num_workers",
                "max_num_workers",
                "machine_type",
                "autoscaling_algorithm",
            ]
        },
    }

    timing_path.write_text(
        json.dumps(timing, indent=2) + "\n",
        encoding="utf-8",
    )

    if state != PipelineState.DONE:
        raise RuntimeError(f"Pipeline did not finish successfully: {state}")

    with FileSystems.open(args.output + ".json") as stream:
        saved_report = json.loads(stream.read().decode("utf-8"))

    if (
        args.expected_files is not None
        and saved_report["page_count"] != args.expected_files
    ):
        raise RuntimeError(
            f"Expected {args.expected_files} files, "
            f"processed {saved_report['page_count']}"
        )

    print_results(saved_report)
    print(f"\nElapsed time: {elapsed:.3f} seconds")
    print(f"Results saved to: {args.output}.json")
    print(f"Timing saved to: {timing_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
