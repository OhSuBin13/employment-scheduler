import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from employment_scheduler.analysis.models import (
    JobPostAnalysisTarget,
)


def select_analysis_targets(
    db_path: Path,
    source: str | None = None,
    seen_at: str | None = None,
    limit: int | None = None,
) -> list[JobPostAnalysisTarget]:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {db_path}")

    where_clauses: list[str] = []
    params: list[str | int] = []

    if source is not None:
        where_clauses.append("sources.key = ?")
        params.append(source)

    if seen_at is not None:
        where_clauses.append("job_posts.last_seen_at = ?")
        params.append(seen_at)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT ?"
        params.append(limit)

    query = f"""
        SELECT
          job_posts.id AS job_post_id,
          sources.key AS source_key,
          job_posts.external_id,
          job_posts.apply_url,
          job_posts.first_seen_at,
          job_posts.last_seen_at,
          job_posts.title
        FROM job_posts
        JOIN sources ON sources.id = job_posts.source_id
        {where_sql}
        ORDER BY job_posts.id
        {limit_sql}
    """

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()

    return [job_row_to_target(row) for row in rows]


def select_analysis_target_by_job_post_id(
    db_path: Path,
    job_post_id: int,
) -> JobPostAnalysisTarget | None:
    targets = select_analysis_targets_by_job_post_ids(db_path, [job_post_id])
    return targets[0] if targets else None


def select_analysis_targets_by_job_post_ids(
    db_path: Path,
    job_post_ids: Iterable[int],
) -> list[JobPostAnalysisTarget]:
    ids = list(dict.fromkeys(job_post_ids))
    if not ids:
        return []

    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {db_path}")

    placeholders = ", ".join("?" for _ in ids)
    query = f"""
        SELECT
          job_posts.id AS job_post_id,
          sources.key AS source_key,
          job_posts.external_id,
          job_posts.apply_url,
          job_posts.first_seen_at,
          job_posts.last_seen_at,
          job_posts.title
        FROM job_posts
        JOIN sources ON sources.id = job_posts.source_id
        WHERE job_posts.id IN ({placeholders})
        ORDER BY job_posts.id
    """

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(query, ids).fetchall()
    finally:
        connection.close()

    return [job_row_to_target(row) for row in rows]


def job_row_to_target(row: sqlite3.Row) -> JobPostAnalysisTarget:
    return JobPostAnalysisTarget(
        job_post_id=int(row["job_post_id"]),
        source_key=str(row["source_key"]),
        external_id=str(row["external_id"]),
        apply_url=str(row["apply_url"]),
        first_seen_at=str(row["first_seen_at"]),
        last_seen_at=str(row["last_seen_at"]),
        title=str(row["title"]),
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="minutes")
