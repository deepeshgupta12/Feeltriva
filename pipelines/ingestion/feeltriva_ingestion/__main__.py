"""CLI: python -m feeltriva_ingestion {verify|audit|load|load-cases|load-features|load-lists|load-chunks|search-text|
load-evidence|store-archives|completeness|derive-meanings|load-release|link-vocabularies|link-ontologies|
suggest-relations}"""

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
    parser.add_argument(
        "command",
        choices=[
            "verify",
            "audit",
            "load",
            "load-cases",
            "load-features",
            "load-lists",
            "load-chunks",
            "search-text",
            "load-evidence",
            "store-archives",
            "completeness",
            "derive-meanings",
            "load-release",
            "link-vocabularies",
            "link-ontologies",
            "suggest-relations",
        ],
    )
    parser.add_argument("query", nargs="?", help="search-text: words to search for in the narrative chunks")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "derived" / "ingestion_audit.json")
    parser.add_argument("--files", nargs="+", help="load-cases / load-features: only these file names (default: all)")
    parser.add_argument(
        "--batch-rows",
        type=int,
        default=None,
        help="rows per transaction (default 20,000 cases / 250,000 feature values)",
    )
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
        if args.command == "load-cases":
            from .cases import compare_with_manifest, load_cases

            result = load_cases(
                args.raw_dir, only=set(args.files) if args.files else None, batch_rows=args.batch_rows or 20_000
            )
            for name, counts in result["files"].items():
                print(
                    f"{name}: read {counts['rows_read']}, inserted {counts['records_inserted']} records / "
                    f"{counts['cases_inserted']} cases / {counts['labels_inserted']} labels"
                )
            print(f"finalise: {result['finalise']}")
            for name, summary in result["summary"].items():
                print(f"{name}: {summary}")
            diffs = compare_with_manifest(result)
            for diff in diffs:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + ("matches manifest" if not diffs else f"{len(diffs)} differences")
            )
            return 1 if diffs else 0
        if args.command == "load-features":
            import json as _json

            from .audit import REFERENCE_AUDIT
            from .features import check, load_case_features

            result = load_case_features(
                args.raw_dir, only=set(args.files) if args.files else None, batch_rows=args.batch_rows or 250_000
            )
            for name, counts in result["files"].items():
                print(f"{name}: {counts}")
            for name, summary in result["summary"].items():
                by_header = summary.pop("conflict_cases_by_header")
                print(f"{name}: stored {summary}; headers with conflicts: {len(by_header)}")
                summary["conflict_cases_by_header"] = by_header
            diffs = check(result, _json.loads(REFERENCE_AUDIT.read_text(encoding="utf-8"))["files"])
            for diff in diffs:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + ("consistent with the files and data_audit/audit.json" if not diffs else f"{len(diffs)} differences")
            )
            return 1 if diffs else 0
        if args.command == "load-lists":
            from .lists import check as check_lists
            from .lists import load_symptom_lists

            result = load_symptom_lists(
                args.raw_dir, only=set(args.files) if args.files else None, batch_rows=args.batch_rows or 250_000
            )
            for name, counts in result["files"].items():
                print(f"{name}: {counts}")
            for name, summary in result["summary"].items():
                print(f"{name}: stored {summary}")
            for name, counts in result["matrix_counts"].items():
                print(f"{name}: declared symptom count check {counts}")
            diffs = check_lists(result)
            for diff in diffs:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + ("consistent with the files" if not diffs else f"{len(diffs)} differences")
            )
            return 1 if diffs else 0
        if args.command == "load-chunks":
            from .archives import load_manifest
            from .chunks import TEXT_ARCHIVE, load_chunks
            from .chunks import check as check_chunks

            totals = load_chunks(args.raw_dir)
            print({k: v for k, v in totals.items() if not isinstance(v, list)})
            expected = sum(1 for entry in load_manifest().text_files if entry["archive"] == TEXT_ARCHIVE)
            diffs = check_chunks(totals, expected)
            for diff in diffs:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + ("consistent with the files and the manifest" if not diffs else f"{len(diffs)} differences")
            )
            return 1 if diffs else 0
        if args.command == "search-text":
            from .chunks import search_chunks

            if not args.query:
                parser.error('search-text needs a query, for example: search-text "night cough wheezing"')
            hits = search_chunks(None, args.query)
            print("Review search over PENDING imported text. Not served to users; not reviewed medical content.")
            for hit in hits:
                section = " > ".join(hit["section_path"]) or "(lead)"
                print(
                    f"[{hit['rank']}] {hit['disease']} | {section} | release {hit['release_status']} "
                    f"| chars {hit['char_start']}-{hit['char_end']}\n    {hit['snippet']}"
                )
            print(f"{len(hits)} result(s)")
            return 0
        if args.command == "load-evidence":
            from .evidence import check as check_evidence
            from .evidence import load_evidence

            result = load_evidence()
            print(f"narrative mentions: {result['narrative']}")
            cooccurrence = result["cooccurrence"]
            print(
                f"co-occurrence: inserted {cooccurrence['proposals_inserted']}, "
                f"recounted for repeated columns {cooccurrence['pairs_recounted_for_repeated_columns']}"
            )
            for name, source in cooccurrence["per_source"].items():
                print(f"  {name}: {source}")
            print(f"stored: {result['stored']}")
            diffs = check_evidence(result)
            for diff in diffs:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + ("consistent; every row is a pending proposal" if not diffs else f"{len(diffs)} differences")
            )
            return 1 if diffs else 0
        if args.command == "store-archives":
            from .objectstore import ObjectStoreError, store_archives
            from .objectstore import check as check_store

            try:
                result = store_archives(args.raw_dir)
            except ObjectStoreError as exc:
                print(f"ERROR {exc}", file=sys.stderr)
                return 2
            print(f"bucket: {result['bucket']}")
            for name, stored in result["archives"].items():
                print(
                    f"{name}: {'uploaded' if stored['uploaded'] else 'already stored'}, "
                    f"{stored['size_bytes']} bytes, re-read and verified, version {stored['version_id']}, "
                    f"anonymous request -> HTTP {stored['anonymous_http_status']}"
                )
            print(f"manifest copy: {'uploaded' if result['manifest']['uploaded'] else 'already stored'}")
            print(f"registry: {result['registry']}")
            diffs = check_store(result)
            for diff in diffs:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + (
                    "all archives stored unchanged in a private, versioned bucket"
                    if not diffs
                    else f"{len(diffs)} differences"
                )
            )
            return 1 if diffs else 0
        if args.command == "completeness":
            from .completeness import OK, render, run_completeness

            report = run_completeness(
                args.raw_dir, progress=lambda message: print(f"... {message}", file=sys.stderr, flush=True)
            )
            mismatches, deferred = report.mismatches, report.deferred
            lines = [render(report), ""]
            lines.extend(f"later    T{c.row} {c.measure}: {c.loaded} ({c.expected})" for c in deferred)
            lines.extend(f"MISMATCH T{c.row} {c.measure}: expected {c.expected}, loaded {c.loaded}" for c in mismatches)
            lines.append(
                f"{len(report.checks)} checks over the {len(report.table)} rows of the mapping table and the M1 "
                f"acceptance criteria: {sum(1 for c in report.checks if c.status == OK)} ok, {len(mismatches)} "
                f"mismatches, {len(deferred)} left to a later sub-step; {time.monotonic() - started:.0f}s"
            )
            lines.append(
                "Read-only. Idempotent reruns are covered by the test suite, not by this command. Everything "
                "checked here is still pending review: this is a loading check, not clinical validation."
            )
            text = "\n".join(lines)
            print(text)
            out = args.out.with_name("ingestion_completeness.txt")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text + "\n", encoding="utf-8")
            print(f"report: {out}")
            return 1 if mismatches else 0
        if args.command == "suggest-relations":
            from .relations import suggest_relations

            result = suggest_relations()
            print(f"candidates compared: {result['subjects']}")
            for (subject_type, relation), n in sorted(result["suggested"].items()):
                print(f"{subject_type}: {relation}: {n} suggested, {result['inserted'][(subject_type, relation)]} new")
            for (subject_type, relation, signal), n in sorted(result["signals"].items()):
                print(f"  {subject_type}: {relation}: because {signal.replace('_', ' ')}: {n}")
            print(f"stored, by review status: {result['stored']}")
            print(
                f"{time.monotonic() - started:.0f}s; suggestions only: nothing is merged, and a decided pair keeps its decision"
            )
            return 0
        if args.command == "link-vocabularies":
            from .release import load_supplementary
            from .vocabulary import check as check_links
            from .vocabulary import link_vocabularies
            from .vocabulary import summarise as summarise_links
            from .vocabulary import write_review as write_links_review

            loinc = next((e for e in load_supplementary() if e.get("kind") == "loinc_release"), None)
            result = link_vocabularies(
                args.raw_dir,
                loinc_entry=loinc,
                progress=lambda message: print(f"... {message}", file=sys.stderr, flush=True),
            )
            summary = summarise_links(result)
            print(
                f"ICD-11 release {result['release']}; {result['api_calls']} new API calls; links inserted {result['inserted']}"
            )
            for (group, outcome), n in sorted(summary["rows"].items()):
                print(f"  {group}: {outcome}: {n}")
            for (group, chapter), n in sorted(summary["chapters"].items(), key=lambda kv: (kv[0][0], -kv[1])):
                print(f"  {group}: ICD-11 chapter {chapter} {result['chapters'].get(chapter, '')}: {n}")
            print(f"stored: {result['table']}")
            print(f"review file (outside Git): {write_links_review(result)}")
            diffs = check_links(result)
            for diff in diffs[:20]:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + (
                    "every link is a name match, carries code, title and URI, and is pending review"
                    if not diffs
                    else f"{len(diffs)} differences"
                )
            )
            return 1 if diffs else 0
        if args.command == "link-ontologies":
            from .ontology_links import check as check_ontology_links
            from .ontology_links import link_ontologies
            from .ontology_links import summarise as summarise_ontology_links
            from .ontology_links import write_review as write_ontology_review

            result = link_ontologies(
                args.raw_dir, progress=lambda message: print(f"... {message}", file=sys.stderr, flush=True)
            )
            for vocabulary in result["vocabularies"]:
                counted = vocabulary.inventory
                print(
                    f"{vocabulary.system} release {vocabulary.version}: {counted['terms']} terms "
                    f"({counted['current']} current, {counted['obsolete']} obsolete); "
                    f"{counted['entries_of_other_vocabularies']} entries of other vocabularies not read; "
                    f"{counted['linkable']} terms may be linked"
                )
                print(
                    f"  names read: {counted['labels']} labels, {counted['exact_synonyms']} exact synonyms "
                    f"({counted['synonyms_that_are_not_names']} of them abbreviations or otherwise not names), "
                    f"{counted['looser_synonyms']} looser synonyms; {counted['parent_links']} parent links"
                )
                for branch, n in sorted(counted["by_branch"].items(), key=lambda kv: -kv[1]):
                    print(f"  current terms in branch {branch}: {n}")
            summary = summarise_ontology_links(result)
            for (group, system, outcome), n in sorted(summary["rows"].items()):
                print(f"{group} ({summary['groups'][group]}): {system}: {outcome}: {n}")
            for (group, outcome), n in sorted(summary["linked"].items()):
                print(f"{group} ({summary['groups'][group]}): {outcome}: {n}")
            print(f"case labels: {result['case_labels']}")
            print(f"links inserted now: {result['inserted']}")
            for system, status, count, _incomplete, _unsigned in result["stored"]:
                print(f"stored: {system}: {status}: {count}")
            print(f"review file (outside Git): {write_ontology_review(result)}")
            diffs = check_ontology_links(result)
            for diff in diffs[:20]:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + (
                    "every term of both files is counted, every name has a recorded outcome, and every link is an "
                    "exact name match stored for review"
                    if not diffs
                    else f"{len(diffs)} differences"
                )
            )
            return 1 if diffs else 0
        if args.command == "load-release":
            from .release import check as check_release
            from .release import load_release

            result = load_release(args.raw_dir)
            for name, facts in result["releases"].items():
                print(
                    f"{name}: {facts['questions']} questions ({facts['antecedents']} antecedents), "
                    f"{facts['conditions']} conditions, answer types {facts['answer_types']}, rows {facts['release_rows']}"
                )
                for file, found in facts["files"].items():
                    print(
                        f"  {file}: {found['traced']} of {found['rows']} rows traced to the release, "
                        f"{found['not_in_release']} not found; {found['mappings_with_a_dictionary_entry']} of "
                        f"{found['mappings']} columns in the dictionary, {found['headings_that_start_the_question']} "
                        "headings are the start of their question"
                    )
                    for run in found["runs"][:10]:
                        print(
                            f"    our rows {run['our_first_row']}-{run['our_first_row'] + run['rows'] - 1} = release "
                            f"{run['release_split']} rows {run['release_first_row']}-{run['release_first_row'] + run['rows'] - 1}"
                        )
                print(f"  changed: {facts['changed']}")
            diffs = check_release(result)
            for diff in diffs:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + (
                    "every row and every question column is accounted for in the release"
                    if not diffs
                    else f"{len(diffs)} differences"
                )
            )
            return 1 if diffs else 0
        if args.command == "derive-meanings":
            from .meanings_load import check as check_meanings
            from .meanings_load import derive_meanings, summarise, write_review

            result = derive_meanings(args.raw_dir)
            summary = summarise(result)
            for (name, kind), n in sorted(summary["kinds"].items()):
                print(f"kind  {name}: {kind} {n}")
            for (name, zero), n in sorted(summary["zeros"].items()):
                print(f"zero  {name}: {zero} {n}")
            for file, twin in result["twins"].items():
                print(f"same cases: {twin['rows']} rows of {twin['list_file']} exist one for one in {file}")
            for sid, population in result["populations"].items():
                if "age" in population:
                    age = population["age"]
                    print(
                        f"age   {result['sources'][sid]}: {age['minimum']:g} to {age['maximum']:g}, "
                        f"proposed unit {age['unit_proposed']}"
                    )
            print(f"changed: {result['changed']}; stored: {result['stored']}")
            for path in write_review(result):
                print(f"review file: {path}")
            diffs = check_meanings(result)
            for diff in diffs:
                print("DIFF", diff)
            print(
                f"{time.monotonic() - started:.0f}s; "
                + ("every proposal has a basis and is pending review" if not diffs else f"{len(diffs)} differences")
            )
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
