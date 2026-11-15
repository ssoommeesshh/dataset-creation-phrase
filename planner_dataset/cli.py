from __future__ import annotations

import argparse
import json

from .exporter import export_boundaries, summarize
from .prepare import prepare_manifest
from .psst import annotate_record
from .schema import SchemaError, validate_record
from .util import read_jsonl, write_jsonl


def _records(path): return list(read_jsonl(path))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="planner-dataset")
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("prepare"); p.add_argument("manifest"); p.add_argument("output"); p.add_argument("--split-by", choices=["source", "speaker"], default="source"); p.add_argument("--seed", default="planner-dataset-v1")
    p = subs.add_parser("validate"); p.add_argument("records")
    p = subs.add_parser("import-psst"); p.add_argument("records"); p.add_argument("psst_outputs"); p.add_argument("output")
    p = subs.add_parser("annotate-psst", help="Optional live PSST inference; requires .[psst] and model download")
    p.add_argument("records"); p.add_argument("output"); p.add_argument("--model", default="NathanRoll/psst-medium-en")
    p.add_argument("--revision"); p.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    p.add_argument("--max-audio-seconds", type=float, default=30.0); p.add_argument("--max-new-tokens", type=int, default=250)
    p = subs.add_parser("export-boundaries"); p.add_argument("records"); p.add_argument("output")
    p = subs.add_parser("summarize"); p.add_argument("records")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        rows = prepare_manifest(args.manifest, split_by=args.split_by, seed=args.seed); write_jsonl(args.output, rows); print(f"prepared {len(rows)} records")
    elif args.command == "validate":
        rows = _records(args.records)
        for row in rows: validate_record(row)
        print(f"valid: {len(rows)} records")
    elif args.command == "import-psst":
        records = _records(args.records); outputs = {row.get("recording_id"): row for row in read_jsonl(args.psst_outputs)}
        if len(outputs) != sum(1 for _ in read_jsonl(args.psst_outputs)):
            raise ValueError("duplicate or missing recording_id in PSST outputs")
        missing = [row["recording"]["id"] for row in records if row["recording"]["id"] not in outputs]
        if missing: raise ValueError(f"missing PSST outputs for: {missing}")
        rows = [annotate_record(row, outputs[row["recording"]["id"]]) for row in records]
        write_jsonl(args.output, rows); print(f"reconciled {len(rows)} records")
    elif args.command == "annotate-psst":
        from .psst_inference import annotate_live
        rows = annotate_live(_records(args.records), records_path=args.records, model_name=args.model,
                             revision=args.revision, device=args.device, max_audio_seconds=args.max_audio_seconds,
                             max_new_tokens=args.max_new_tokens)
        write_jsonl(args.output, rows); print(f"PSST annotated {len(rows)} records")
    elif args.command == "export-boundaries":
        rows = export_boundaries(_records(args.records)); write_jsonl(args.output, rows); print(f"exported {len(rows)} word junctions")
    else:
        print(json.dumps(summarize(_records(args.records)), sort_keys=True))


if __name__ == "__main__": main()
