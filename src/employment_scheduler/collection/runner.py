"""Collection runner skeleton."""

from __future__ import annotations

from employment_scheduler.models import CollectionOptions


def run_collection(options: CollectionOptions) -> int:
    if options.dry_run:
        print(
            "dry-run: "
            f"source={options.source} "
            f"target_date={options.target_date.isoformat()}"
        )
        return 0

    raise NotImplementedError("Collection implementation is not wired yet.")
