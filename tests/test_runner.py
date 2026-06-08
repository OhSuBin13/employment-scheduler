from datetime import date

import httpx

from employment_scheduler.collection.runner import run_collection
from employment_scheduler.models import CollectionOptions
from employment_scheduler.storage.database import DatabaseStorage, connect


def test_run_collection_writes_database_outputs(tmp_path) -> None:
    posts = [
        {
            "id": 351552,
            "date": "2026-06-03T09:00:00",
            "modified": "2026-06-03T09:30:00",
            "link": "https://inthiswork.com/archives/351552?utm_source=x",
            "title": {"rendered": "Backend Engineer"},
            "categories": [191700167],
            "tags": [191700187],
            "excerpt": {"rendered": "<p>Build internal tools.</p>"},
        }
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=posts))
    )

    db_path = tmp_path / "employment.sqlite"

    exit_code = run_collection(
        CollectionOptions(source="inthiswork", target_date=date(2026, 6, 4)),
        storage=DatabaseStorage(db_path),
        client=client,
    )

    assert exit_code == 0
    assert db_path.exists()
    with connect(db_path) as connection:
        job_post = connection.execute("SELECT * FROM job_posts").fetchone()
        run = connection.execute("SELECT * FROM collection_runs").fetchone()

    assert job_post["normalized_url"] == "https://inthiswork.com/archives/351552"
    assert job_post["title"] == "Backend Engineer"
    assert run["fetched_count"] == 1
    assert run["inserted_count"] == 1
