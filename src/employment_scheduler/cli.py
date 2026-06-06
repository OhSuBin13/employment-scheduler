"""Command-line entrypoints for the local collection pipeline."""

from __future__ import annotations

import argparse
from datetime import date

from employment_scheduler.collection.runner import run_collection
from employment_scheduler.models import CollectionOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collect_today.py",
        description="Collect employment posts for a target date.",
    )
    parser.add_argument(
        "--source",
        default="inthiswork",
        help="Source key to collect from. Defaults to inthiswork.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Collection window end date in YYYY-MM-DD format. "
        "Collects posts from the previous day. Defaults to the local date.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build collection options without writing data.",
    )
    return parser


def parse_options(argv: list[str] | None = None) -> CollectionOptions:
    args = build_parser().parse_args(argv)
    target_date = date.fromisoformat(args.date) if args.date else date.today()
    return CollectionOptions(
        source=args.source,
        target_date=target_date,
        dry_run=args.dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    options = parse_options(argv)
    return run_collection(options)
