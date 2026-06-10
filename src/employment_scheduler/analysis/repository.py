import sqlite3
from pathlib import Path

from employment_scheduler.analysis.models import JobPostAnalysisTarget


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
          job_posts.apply_url_hash,
          job_posts.first_seen_at,
          job_posts.last_seen_at
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

    return [
        JobPostAnalysisTarget(
            job_post_id=int(row["job_post_id"]),
            source_key=str(row["source_key"]),
            external_id=str(row["external_id"]),
            apply_url=str(row["apply_url"]),
            apply_url_hash=str(row["apply_url_hash"]),
            first_seen_at=str(row["first_seen_at"]),
            last_seen_at=str(row["last_seen_at"]),
        )
        for row in rows
    ]
