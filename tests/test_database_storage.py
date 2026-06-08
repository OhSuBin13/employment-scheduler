import json
from datetime import date

from employment_scheduler.models import CollectedPost
from employment_scheduler.storage.database import DatabaseStorage, connect


def test_database_storage_writes_run_posts_and_records(tmp_path) -> None:
    record = CollectedPost(
        source="inthiswork",
        external_id="1",
        title="Backend Engineer",
        original_url="https://inthiswork.com/archives/1?utm_source=x",
        normalized_url="https://inthiswork.com/archives/1",
        normalized_url_hash="hash-1",
        normalization_rule="inthiswork_archives",
        collected_date=date(2026, 6, 4),
        source_published_at="2026-06-03T09:00:00",
        categories=(191700167,),
        tags=(191700187,),
    )
    duplicate = CollectedPost(
        source="inthiswork",
        external_id="2",
        title="Backend Engineer Duplicate",
        original_url="https://inthiswork.com/archives/1",
        normalized_url="https://inthiswork.com/archives/1",
        normalized_url_hash="hash-1",
        normalization_rule="inthiswork_archives",
        collected_date=date(2026, 6, 4),
    )
    db_path = tmp_path / "employment.sqlite"
    storage = DatabaseStorage(db_path)

    result = storage.write_collection(
        source="inthiswork",
        target_date=date(2026, 6, 4),
        raw_posts=[{"id": 1}, {"id": 2}],
        records=[record, duplicate],
        request_params={"tags": "191700187"},
    )

    assert result.fetched_count == 2
    assert result.unique_count == 1
    assert result.inserted_count == 1
    assert result.updated_count == 0
    assert result.duplicate_count == 1

    with connect(db_path) as connection:
        run = connection.execute("SELECT * FROM collection_runs").fetchone()
        job_post = connection.execute("SELECT * FROM job_posts").fetchone()
        source_record = connection.execute("SELECT * FROM source_records").fetchone()

    assert run["status"] == "complete"
    assert run["fetched_count"] == 2
    assert run["inserted_count"] == 1
    assert run["duplicate_count"] == 1
    assert json.loads(run["request_params_json"]) == {"tags": "191700187"}

    assert job_post["title"] == "Backend Engineer"
    assert job_post["normalized_url"] == "https://inthiswork.com/archives/1"
    assert job_post["normalized_url_hash"] == "hash-1"
    assert job_post["first_seen_at"] == "2026-06-04"
    assert job_post["last_seen_at"] == "2026-06-04"

    assert source_record["external_id"] == "1"
    assert (
        source_record["original_url"]
        == "https://inthiswork.com/archives/1?utm_source=x"
    )
    assert json.loads(source_record["categories_json"]) == [191700167]
    assert json.loads(source_record["tags_json"]) == [191700187]
    assert json.loads(source_record["raw_json"]) == {"id": 1}


def test_database_storage_updates_previously_seen_posts(tmp_path) -> None:
    db_path = tmp_path / "employment.sqlite"
    storage = DatabaseStorage(db_path)
    record = CollectedPost(
        source="inthiswork",
        external_id="1",
        title="Backend Engineer",
        original_url="https://inthiswork.com/archives/1",
        normalized_url="https://inthiswork.com/archives/1",
        normalized_url_hash="hash-1",
        normalization_rule="inthiswork_archives",
        collected_date=date(2026, 6, 4),
    )

    storage.write_collection("inthiswork", date(2026, 6, 4), [{"id": 1}], [record])
    result = storage.write_collection(
        "inthiswork", date(2026, 6, 5), [{"id": 1}], [record]
    )

    with connect(db_path) as connection:
        job_post = connection.execute("SELECT * FROM job_posts").fetchone()
        source_record = connection.execute("SELECT * FROM source_records").fetchone()
        run_count = connection.execute(
            "SELECT COUNT(*) AS count FROM collection_runs"
        ).fetchone()

    assert result.inserted_count == 0
    assert result.updated_count == 1
    assert job_post["first_seen_at"] == "2026-06-04"
    assert job_post["last_seen_at"] == "2026-06-05"
    assert source_record["first_seen_at"] == "2026-06-04"
    assert source_record["last_seen_at"] == "2026-06-05"
    assert run_count["count"] == 2
