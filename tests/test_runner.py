from datetime import date

import httpx

from employment_scheduler.collection.runner import run_collection
from employment_scheduler.models import CollectionOptions
from employment_scheduler.storage.database import DatabaseStorage, connect


def test_run_collection_writes_database_outputs(tmp_path) -> None:
    apply_url = (
        "https://makinarocks.career.greetinghr.com/ko/o/157208"
        "?utm_source=inthiswork&ref=job-list"
    )
    normalized_apply_url = (
        "https://makinarocks.career.greetinghr.com/ko/o/157208?ref=job-list"
    )
    posts = [
        {
            "id": 351552,
            "content": {
                "rendered": f'<p><a href="{apply_url}">지원하러 가기</a></p>'
            },
            "title": {"rendered": "Backend Engineer"},
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

    assert job_post["apply_url"] == normalized_apply_url
    assert job_post["external_id"] == "351552"
    assert job_post["title"] == "Backend Engineer"
