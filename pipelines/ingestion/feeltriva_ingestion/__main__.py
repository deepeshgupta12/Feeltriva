"""CLI: python -m feeltriva_ingestion {verify|audit|load}"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .archives import RAW_DIR, ROOT, ArchiveError, verify_all
from .audit import compare, run_audit


def main() -> int:
    parser = argparse.ArgumentParser(prog="feeltriva_ingestion")
    parser.add_argument("command", choices=["verify", "audit", "load"])
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "derived" / "ingestion_audit.json")
    args = parser.parse_args()
    started = time.monotonic()
    try:
        if args.command == "verify":
            entries = verify_all(args.raw_dir)
            for name, infos in entries.items():
                print(f"{name}: checksum ok, {len(infos)} entries passed safety checks")
            return 0
        if args.command == "audit":
            result = run_audit(args.raw_dir)
            diffs = compare(result)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            csv_rows = sum(f["rows"] for f in result["files"])
            print(
                f"{len(result['files'])} CSV files, {len(result['text_files'])} text files, {csv_rows} CSV rows; "
                f"{result['union_lexical_disease_labels']} lexical disease labels; "
                f"{time.monotonic() - started:.0f}s; report: {args.out}"
            )
            for diff in diffs:
                print("DIFF", diff)
            print("reproduces manifest and audit.json" if not diffs else f"{len(diffs)} differences")
            return 1 if diffs else 0
        from .load import load_reference

        for table, (inserted, total) in load_reference(args.raw_dir).items():
            print(f"{table}: {inserted} inserted, {total} total")
        return 0
    except ArchiveError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
