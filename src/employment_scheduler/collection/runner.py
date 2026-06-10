"""Collection runner for local SQLite-backed employment post storage."""

from __future__ import annotations

from contextlib import nullcontext
from typing import ContextManager

import httpx

from employment_scheduler.models import CollectionOptions
from employment_scheduler.sources.inthiswork import (
    SOURCE_KEY as INTHISWORK_SOURCE_KEY,
)
from employment_scheduler.sources.inthiswork import (
    build_it_post_records,
    fetch_it_posts,
)
from employment_scheduler.storage.database import DatabaseStorage


def run_collection(
    options: CollectionOptions,
    storage: DatabaseStorage | None = None,
    client: httpx.Client | None = None,
) -> int:

    if options.source != INTHISWORK_SOURCE_KEY:
        raise ValueError(f"Unsupported source: {options.source}")

    storage = storage or DatabaseStorage()

    client_context: ContextManager[httpx.Client]
    if client is None:
        client_context = httpx.Client(timeout=20.0)
    else:
        client_context = nullcontext(client)

    with client_context as active_client:
        raw_posts = fetch_it_posts(active_client, options.target_date)

    records = build_it_post_records(raw_posts, options.target_date)
    result = storage.write_collection(
        source=options.source,
        target_date=options.target_date,
        raw_posts=raw_posts,
        records=records,
    )

    print(
        "collection complete: "
        f"source={options.source} "
        f"target_date={options.target_date.isoformat()} "
        f"fetched={result.fetched_count} "
        f"unique={result.unique_count} "
        f"inserted={result.inserted_count} "
        f"updated={result.updated_count} "
        f"duplicates={result.duplicate_count} "
        f"db={result.db_path}"
    )
    return 0
