"""SQLite-backed storage for collected employment posts."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from employment_scheduler.models import CollectedPost
from employment_scheduler.storage.models import DatabaseStorageResult

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


class DatabaseStorage:
    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
    ) -> None:
        self.db_path = Path(db_path)

    def write_collection(
        self,
        source: str,
        target_date: date,
        raw_posts: list[dict[str, Any]],
        records: list[CollectedPost],
    ) -> DatabaseStorageResult:
        connection = connect(self.db_path)
        try:
            initialize_database(connection)
            source_id = _ensure_source(connection, source)

            inserted_count = 0
            updated_count = 0
            job_post_ids_by_hash: dict[str, int] = {}
            seen_at = target_date.isoformat()
            for record in records:
                job_post_id = job_post_ids_by_hash.get(
                    record.apply_link.normalized_url_hash
                )
                if job_post_id is None:
                    job_post_id, inserted = _upsert_job_post(
                        connection=connection,
                        source_id=source_id,
                        record=record,
                        seen_at=seen_at,
                    )
                    job_post_ids_by_hash[record.apply_link.normalized_url_hash] = (
                        job_post_id
                    )
                    if inserted:
                        inserted_count += 1
                    else:
                        updated_count += 1

            unique_count = len(job_post_ids_by_hash)
            duplicate_count = len(records) - unique_count
            connection.commit()
        finally:
            connection.close()

        return DatabaseStorageResult(
            db_path=self.db_path,
            fetched_count=len(raw_posts),
            unique_count=unique_count,
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


def _upsert_job_post(
    connection: sqlite3.Connection,
    source_id: int,
    record: CollectedPost,
    seen_at: str,
) -> tuple[int, bool]:
    existing = _find_job_post_for_record(connection, source_id, record)

    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO job_posts (
              source_id,
              external_id,
              apply_url,
              apply_url_hash,
              first_seen_at,
              last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                record.external_id,
                record.apply_link.normalized_url,
                record.apply_link.normalized_url_hash,
                seen_at,
                seen_at,
            ),
        )
        return int(cursor.lastrowid), True

    job_post_id = int(existing["id"])
    _update_job_post(connection, job_post_id, source_id, record, seen_at)
    return job_post_id, False


def _find_job_post_for_record(
    connection: sqlite3.Connection,
    source_id: int,
    record: CollectedPost,
) -> sqlite3.Row | None:
    existing = connection.execute(
        """
        SELECT id
        FROM job_posts
        WHERE source_id = ? AND external_id = ?
        """,
        (source_id, record.external_id),
    ).fetchone()
    if existing is not None:
        return existing

    return connection.execute(
        """
        SELECT id
        FROM job_posts
        WHERE apply_url_hash = ?
        """,
        (record.apply_link.normalized_url_hash,),
    ).fetchone()


def _update_job_post(
    connection: sqlite3.Connection,
    job_post_id: int,
    source_id: int,
    record: CollectedPost,
    seen_at: str,
) -> None:
    connection.execute(
        """
        UPDATE job_posts
        SET source_id = ?,
            external_id = ?,
            apply_url = ?,
            apply_url_hash = ?,
            last_seen_at = ?
        WHERE id = ?
        """,
        (
            source_id,
            record.external_id,
            record.apply_link.normalized_url,
            record.apply_link.normalized_url_hash,
            seen_at,
            job_post_id,
        ),
    )


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
