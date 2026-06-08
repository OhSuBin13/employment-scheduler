"""SQLite-backed storage for collected employment posts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from employment_scheduler.models import CollectedPost

DEFAULT_DB_PATH = Path("data/employment.sqlite")
DEFAULT_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "migrations" / "001_init.sql"
)


SOURCE_METADATA: dict[str, dict[str, Any]] = {
    "inthiswork": {
        "name": "IN THIS WORK",
        "base_url": "https://inthiswork.com/wp-json/wp/v2/posts",
        "api_type": "wordpress-rest",
        "config": {
            "category_ids": [191700167],
            "tag_ids": [191700187],
            "timezone": "Asia/Seoul",
        },
    },
}


@dataclass(frozen=True)
class DatabaseStorageResult:
    db_path: Path
    run_id: int
    fetched_count: int
    unique_count: int
    inserted_count: int
    updated_count: int
    duplicate_count: int


class DatabaseStorage:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def write_collection(
        self,
        source: str,
        target_date: date,
        raw_posts: list[dict[str, Any]],
        records: list[CollectedPost],
        request_params: dict[str, Any] | None = None,
    ) -> DatabaseStorageResult:
        unique_records = _deduplicate_records(records)
        duplicate_count = len(records) - len(unique_records)
        raw_posts_by_external_id = _raw_posts_by_external_id(raw_posts)

        connection = connect(self.db_path)
        try:
            initialize_database(connection)
            source_id = _ensure_source(connection, source)
            run_id = _start_collection_run(
                connection=connection,
                source_id=source_id,
                target_date=target_date,
                request_params=request_params or {},
            )

            inserted_count = 0
            updated_count = 0
            for record in unique_records:
                job_post_id, inserted = _upsert_job_post(
                    connection=connection,
                    source_id=source_id,
                    record=record,
                    seen_at=target_date.isoformat(),
                )
                if inserted:
                    inserted_count += 1
                else:
                    updated_count += 1

                _upsert_source_record(
                    connection=connection,
                    source_id=source_id,
                    job_post_id=job_post_id,
                    collection_run_id=run_id,
                    record=record,
                    raw_post=raw_posts_by_external_id.get(record.external_id),
                    seen_at=target_date.isoformat(),
                )

            _finish_collection_run(
                connection=connection,
                run_id=run_id,
                status="complete",
                fetched_count=len(raw_posts),
                inserted_count=inserted_count,
                updated_count=updated_count,
                duplicate_count=duplicate_count,
            )
            connection.commit()
        finally:
            connection.close()

        return DatabaseStorageResult(
            db_path=self.db_path,
            run_id=run_id,
            fetched_count=len(raw_posts),
            unique_count=len(unique_records),
            inserted_count=inserted_count,
            updated_count=updated_count,
            duplicate_count=duplicate_count,
        )


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(
    connection: sqlite3.Connection,
    migration_path: Path = DEFAULT_MIGRATION_PATH,
) -> None:
    connection.executescript(migration_path.read_text(encoding="utf-8"))


def _ensure_source(connection: sqlite3.Connection, source: str) -> int:
    metadata = SOURCE_METADATA.get(
        source,
        {
            "name": source,
            "base_url": "",
            "api_type": "unknown",
            "config": {},
        },
    )
    now = _utc_now()
    config_json = _dump_json(metadata["config"])
    existing = connection.execute(
        "SELECT id FROM sources WHERE key = ?",
        (source,),
    ).fetchone()

    if existing is not None:
        connection.execute(
            """
            UPDATE sources
            SET name = ?,
                base_url = ?,
                api_type = ?,
                config_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                metadata["name"],
                metadata["base_url"],
                metadata["api_type"],
                config_json,
                now,
                existing["id"],
            ),
        )
        return int(existing["id"])

    cursor = connection.execute(
        """
        INSERT INTO sources (
          key, name, base_url, api_type, config_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            metadata["name"],
            metadata["base_url"],
            metadata["api_type"],
            config_json,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _start_collection_run(
    connection: sqlite3.Connection,
    source_id: int,
    target_date: date,
    request_params: dict[str, Any],
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO collection_runs (
          source_id, mode, target_date, status, request_params_json, started_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            "daily",
            target_date.isoformat(),
            "running",
            _dump_json(request_params),
            _utc_now(),
        ),
    )
    return int(cursor.lastrowid)


def _finish_collection_run(
    connection: sqlite3.Connection,
    run_id: int,
    status: str,
    fetched_count: int,
    inserted_count: int,
    updated_count: int,
    duplicate_count: int,
) -> None:
    connection.execute(
        """
        UPDATE collection_runs
        SET status = ?,
            fetched_count = ?,
            inserted_count = ?,
            updated_count = ?,
            duplicate_count = ?,
            finished_at = ?
        WHERE id = ?
        """,
        (
            status,
            fetched_count,
            inserted_count,
            updated_count,
            duplicate_count,
            _utc_now(),
            run_id,
        ),
    )


def _upsert_job_post(
    connection: sqlite3.Connection,
    source_id: int,
    record: CollectedPost,
    seen_at: str,
) -> tuple[int, bool]:
    existing = connection.execute(
        "SELECT id FROM job_posts WHERE normalized_url_hash = ?",
        (record.normalized_url_hash,),
    ).fetchone()

    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO job_posts (
              normalized_url,
              normalized_url_hash,
              title,
              excerpt_text,
              first_seen_at,
              last_seen_at,
              latest_source_id,
              latest_source_published_at,
              latest_source_modified_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.normalized_url,
                record.normalized_url_hash,
                record.title,
                record.excerpt_text,
                seen_at,
                seen_at,
                source_id,
                record.source_published_at,
                record.source_modified_at,
            ),
        )
        return int(cursor.lastrowid), True

    connection.execute(
        """
        UPDATE job_posts
        SET normalized_url = ?,
            title = ?,
            excerpt_text = ?,
            last_seen_at = ?,
            latest_source_id = ?,
            latest_source_published_at = ?,
            latest_source_modified_at = ?
        WHERE id = ?
        """,
        (
            record.normalized_url,
            record.title,
            record.excerpt_text,
            seen_at,
            source_id,
            record.source_published_at,
            record.source_modified_at,
            existing["id"],
        ),
    )
    return int(existing["id"]), False


def _upsert_source_record(
    connection: sqlite3.Connection,
    source_id: int,
    job_post_id: int,
    collection_run_id: int,
    record: CollectedPost,
    raw_post: dict[str, Any] | None,
    seen_at: str,
) -> None:
    existing = connection.execute(
        """
        SELECT id
        FROM source_records
        WHERE source_id = ? AND external_id = ?
        """,
        (source_id, record.external_id),
    ).fetchone()

    values = (
        job_post_id,
        collection_run_id,
        record.original_url,
        record.normalized_url,
        record.title,
        record.source_published_at,
        record.source_modified_at,
        _dump_json(list(record.categories)),
        _dump_json(list(record.tags)),
        _dump_json(raw_post) if raw_post is not None else None,
        seen_at,
    )

    if existing is not None:
        connection.execute(
            """
            UPDATE source_records
            SET job_post_id = ?,
                collection_run_id = ?,
                original_url = ?,
                normalized_url = ?,
                title_raw = ?,
                source_published_at = ?,
                source_modified_at = ?,
                categories_json = ?,
                tags_json = ?,
                raw_json = ?,
                last_seen_at = ?
            WHERE id = ?
            """,
            (*values, existing["id"]),
        )
        return

    connection.execute(
        """
        INSERT INTO source_records (
          source_id,
          job_post_id,
          collection_run_id,
          external_id,
          original_url,
          normalized_url,
          title_raw,
          source_published_at,
          source_modified_at,
          categories_json,
          tags_json,
          raw_json,
          first_seen_at,
          last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            job_post_id,
            collection_run_id,
            record.external_id,
            record.original_url,
            record.normalized_url,
            record.title,
            record.source_published_at,
            record.source_modified_at,
            _dump_json(list(record.categories)),
            _dump_json(list(record.tags)),
            _dump_json(raw_post) if raw_post is not None else None,
            seen_at,
            seen_at,
        ),
    )


def _deduplicate_records(records: list[CollectedPost]) -> list[CollectedPost]:
    unique: dict[str, CollectedPost] = {}
    for record in records:
        unique.setdefault(record.normalized_url_hash, record)
    return list(unique.values())


def _raw_posts_by_external_id(
    raw_posts: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for post in raw_posts:
        external_id = post.get("id")
        if external_id is not None:
            indexed.setdefault(str(external_id), post)
    return indexed


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
