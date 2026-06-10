from datetime import date

from employment_scheduler.models import CollectedPost
from employment_scheduler.normalization import normalize_link
from employment_scheduler.storage.database import DatabaseStorage, connect, initialize_database


def _record(
    external_id: str,
    apply_url: str,
    target_date: date = date(2026, 6, 4),
    title: str = "Backend Engineer",
) -> CollectedPost:
    return CollectedPost(
        source="inthiswork",
        external_id=external_id,
        apply_link=normalize_link("apply_url", apply_url),
        title=title,
        collected_date=target_date,
    )


def _column_names(connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f'PRAGMA table_info("{table_name}")')
    }


def test_database_storage_writes_only_sources_and_job_posts(
    tmp_path,
) -> None:
    apply_url = (
        "https://makinarocks.career.greetinghr.com/ko/o/157208"
        "?utm_source=inthiswork&ref=career"
    )
    duplicate_apply_url = (
        "https://makinarocks.career.greetinghr.com/ko/o/157208"
        "?fbclid=abc&ref=career"
    )
    db_path = tmp_path / "employment.sqlite"
    storage = DatabaseStorage(db_path)

    result = storage.write_collection(
        source="inthiswork",
        target_date=date(2026, 6, 4),
        raw_posts=[{"id": 1}, {"id": 2}],
        records=[
            _record("1", apply_url),
            _record("2", duplicate_apply_url),
        ],
    )

    with connect(db_path) as connection:
        source = connection.execute("SELECT * FROM sources").fetchone()
        job_post = connection.execute("SELECT * FROM job_posts").fetchone()
        counts = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM sources) AS sources_count,
              (SELECT COUNT(*) FROM job_posts) AS job_posts_count
            """
        ).fetchone()
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        job_post_columns = _column_names(connection, "job_posts")

    assert result.fetched_count == 2
    assert result.unique_count == 1
    assert result.inserted_count == 1
    assert result.updated_count == 0
    assert result.duplicate_count == 1

    assert tables >= {"sources", "job_posts"}
    assert "collection_runs" not in tables
    assert "source_records" not in tables
    assert counts["sources_count"] == 1
    assert counts["job_posts_count"] == 1
    assert source["key"] == "inthiswork"
    assert job_post["source_id"] == source["id"]
    assert job_post["external_id"] == "1"
    assert job_post["title"] == "Backend Engineer"
    assert (
        job_post["apply_url"]
        == "https://makinarocks.career.greetinghr.com/ko/o/157208?ref=career"
    )
    assert job_post["apply_url_hash"] == normalize_link(
        "apply_url",
        apply_url,
    ).normalized_url_hash

    assert job_post_columns == {
        "id",
        "source_id",
        "external_id",
        "apply_url",
        "apply_url_hash",
        "title",
        "first_seen_at",
        "last_seen_at",
    }


def test_database_storage_updates_same_job_post_when_apply_link_changes(
    tmp_path,
) -> None:
    db_path = tmp_path / "employment.sqlite"
    storage = DatabaseStorage(db_path)
    first_apply_url = "https://jobs.example.com/apply?position=backend"
    updated_apply_url = "https://jobs.example.com/apply?position=platform"

    storage.write_collection(
        "inthiswork",
        date(2026, 6, 4),
        [{"id": 1}],
        [_record("1", first_apply_url, date(2026, 6, 4))],
    )
    result = storage.write_collection(
        "inthiswork",
        date(2026, 6, 5),
        [{"id": 1}],
        [
            _record(
                "1",
                updated_apply_url,
                date(2026, 6, 5),
                title="Platform Engineer",
            )
        ],
    )

    with connect(db_path) as connection:
        job_post = connection.execute("SELECT * FROM job_posts").fetchone()
        counts = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM sources) AS sources_count,
              (SELECT COUNT(*) FROM job_posts) AS job_posts_count
            """
        ).fetchone()

    assert result.inserted_count == 0
    assert result.updated_count == 1
    assert counts["sources_count"] == 1
    assert counts["job_posts_count"] == 1
    assert job_post["external_id"] == "1"
    assert job_post["title"] == "Platform Engineer"
    assert job_post["apply_url"] == updated_apply_url
    assert job_post["apply_url_hash"] == normalize_link(
        "apply_url",
        updated_apply_url,
    ).normalized_url_hash
    assert job_post["first_seen_at"] == "2026-06-04"
    assert job_post["last_seen_at"] == "2026-06-05"


def test_initialize_database_creates_minimal_init_schema(tmp_path) -> None:
    db_path = tmp_path / "employment.sqlite"

    with connect(db_path) as connection:
        initialize_database(connection)
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        job_post_columns = _column_names(connection, "job_posts")

    assert tables >= {"sources", "job_posts"}
    assert "schema_migrations" not in tables
    assert "collection_runs" not in tables
    assert "source_records" not in tables
    assert job_post_columns == {
        "id",
        "source_id",
        "external_id",
        "apply_url",
        "apply_url_hash",
        "title",
        "first_seen_at",
        "last_seen_at",
    }


def test_storage_preserves_existing_database_before_applying_init_schema(
    tmp_path,
) -> None:
    db_path = tmp_path / "employment.sqlite"

    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE collection_runs (id INTEGER PRIMARY KEY);
            CREATE TABLE source_records (id INTEGER PRIMARY KEY);
            CREATE TABLE stale_table (id INTEGER PRIMARY KEY);
            """
        )

    storage = DatabaseStorage(db_path)
    storage.write_collection(
        source="inthiswork",
        target_date=date(2026, 6, 4),
        raw_posts=[{"id": 1}],
        records=[
            _record(
                "1",
                "https://jobs.example.com/apply?utm_source=inthiswork",
            ),
        ],
    )

    with connect(db_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        job_post = connection.execute("SELECT * FROM job_posts").fetchone()
        job_post_columns = _column_names(connection, "job_posts")

    assert tables >= {"sources", "job_posts"}
    assert "collection_runs" in tables
    assert "source_records" in tables
    assert "stale_table" in tables
    assert job_post_columns == {
        "id",
        "source_id",
        "external_id",
        "apply_url",
        "apply_url_hash",
        "title",
        "first_seen_at",
        "last_seen_at",
    }
    assert job_post["external_id"] == "1"
    assert job_post["title"] == "Backend Engineer"
    assert job_post["apply_url"] == "https://jobs.example.com/apply"
