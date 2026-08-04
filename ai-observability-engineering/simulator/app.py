"""Command line entry point for the simulator.

    aiobs-sim run --all
    aiobs-sim run --chapter 6 --verbose
    aiobs-sim run --example ch01.traditional_vs_llm_span --format json
    aiobs-sim run --all --html report.html
    aiobs-sim list
    aiobs-sim scenarios
    aiobs-sim coverage

Exit code is 0 when every selected example passes, 1 otherwise, so the
simulator drops straight into CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aiobs import __version__
from aiobs.semconv import SEMCONV_VERSION
from aiobs.testing.scenarios import SCENARIOS
from chapters.registry import CHAPTER_TITLES, all_examples, coverage

from .report import render_html, render_json, render_terminal
from .runner import run, select


def _cmd_run(args: argparse.Namespace) -> int:
    specs = select(chapter=args.chapter, example_ids=args.example, pillar=args.pillar)
    if not specs:
        print("no examples matched that selection", file=sys.stderr)
        return 2

    report = run(specs, strict=not args.lenient)

    if args.format == "json":
        print(render_json(report))
    elif args.format == "quiet":
        print(f"{report.passed}/{report.total} passed")
    else:
        print(render_terminal(report, color=not args.no_color, verbose=args.verbose))

    if args.html:
        path = Path(args.html)
        path.write_text(render_html(report), encoding="utf-8")
        print(f"\nHTML report written to {path.resolve()}", file=sys.stderr)

    if args.json_out:
        path = Path(args.json_out)
        path.write_text(render_json(report), encoding="utf-8")
        print(f"JSON report written to {path.resolve()}", file=sys.stderr)

    return 0 if report.ok else 1


def _cmd_list(args: argparse.Namespace) -> int:
    current = None
    for spec in all_examples():
        if spec.chapter != current:
            current = spec.chapter
            print(f"\nChapter {current:02d}  {CHAPTER_TITLES[current]}")
        listing = f"Listing {spec.listing}" if spec.listing else "-"
        flag = "  [demonstrates failure]" if spec.demonstrates_failure else ""
        print(f"  {spec.id:<40}{listing:<14}{spec.pillar.value:<16}{spec.title}{flag}")
    print()
    return 0


def _cmd_scenarios(args: argparse.Namespace) -> int:
    for key, scenario in SCENARIOS.items():
        print(f"{key}\n  {scenario.title}\n  {scenario.description}")
        print(f"  pillar: {scenario.pillar}\n  detected by: {scenario.detected_by}\n")
    return 0


def _cmd_coverage(args: argparse.Namespace) -> int:
    print(json.dumps(coverage(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiobs-sim",
        description="Run every example in AI Observability Engineering.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"aiobs {__version__} (GenAI semconv {SEMCONV_VERSION})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="run examples")
    target = run_cmd.add_mutually_exclusive_group()
    target.add_argument("--all", action="store_true", help="run every example (default)")
    target.add_argument("--chapter", type=int, metavar="N", help="run one chapter, 1-17")
    run_cmd.add_argument("--example", action="append", metavar="ID", help="run specific example ids")
    run_cmd.add_argument("--pillar", choices=["performance", "roi", "risk", "responsibility"])
    run_cmd.add_argument("--format", choices=["text", "json", "quiet"], default="text")
    run_cmd.add_argument("--html", metavar="PATH", help="also write a standalone HTML report")
    run_cmd.add_argument("--json-out", metavar="PATH", help="also write the report as JSON")
    run_cmd.add_argument("--verbose", action="store_true", help="include tracebacks")
    run_cmd.add_argument("--no-color", action="store_true")
    run_cmd.add_argument(
        "--lenient",
        action="store_true",
        help="skip semantic convention and PII enforcement",
    )
    run_cmd.set_defaults(func=_cmd_run)

    list_cmd = sub.add_parser("list", help="list every registered example")
    list_cmd.set_defaults(func=_cmd_list)

    scen_cmd = sub.add_parser("scenarios", help="list the named failure scenarios")
    scen_cmd.set_defaults(func=_cmd_scenarios)

    cov_cmd = sub.add_parser("coverage", help="report pillar, layer, and chapter coverage")
    cov_cmd.set_defaults(func=_cmd_coverage)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
