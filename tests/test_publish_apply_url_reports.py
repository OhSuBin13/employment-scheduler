from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx

from employment_scheduler.analysis.repository.analyze_repo import (
    select_analysis_target_by_job_post_id,
)
from employment_scheduler.analysis.service.publish_reports import (
    PublishApplyUrlReportsOptions,
    build_notion_markdown,
    parse_options,
    publish_apply_url_reports,
)
from employment_scheduler.normalization import normalize_link
from employment_scheduler.notion.client import NotionClient, NotionPage, NotionParent
from employment_scheduler.storage.database import connect, initialize_database


class FakeNotionClient:
    def __init__(self) -> None:
        self.created: list[tuple[NotionParent, str]] = []
        self.updated: list[tuple[str, str]] = []

    def create_page_from_markdown(
        self,
        parent: NotionParent,
        markdown: str,
    ) -> NotionPage:
        self.created.append((parent, markdown))
        page_id = f"page-{len(self.created)}"
        return NotionPage(page_id=page_id, url=f"https://notion.so/{page_id}")

    def replace_page_markdown(self, page_id: str, markdown: str) -> NotionPage:
        self.updated.append((page_id, markdown))
        return NotionPage(page_id=page_id, url=f"https://notion.so/{page_id}")


def _seed_job_post(
    db_path: Path,
    external_id: str = "354304",
    apply_url: str = "https://nxt.career.greetinghr.com/ko/o/219827",
    title: str = "Backend Engineer",
    first_seen_at: str = "2026-06-10",
    last_seen_at: str = "2026-06-10",
) -> int:
    normalized = normalize_link("apply_url", apply_url)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with connect(db_path) as connection:
        initialize_database(connection)
        connection.execute(
            """
            INSERT OR IGNORE INTO sources (
              key, name, base_url, api_type, config_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inthiswork",
                "IN THIS WORK",
                "https://inthiswork.com/wp-json/wp/v2/posts",
                "wordpress-rest",
                "{}",
                now,
                now,
            ),
        )
        source_id = connection.execute(
            "SELECT id FROM sources WHERE key = ?",
            ("inthiswork",),
        ).fetchone()["id"]
        job_post_id = connection.execute(
            """
            INSERT INTO job_posts (
              source_id,
              external_id,
              apply_url,
              apply_url_hash,
              title,
              first_seen_at,
              last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                external_id,
                normalized.normalized_url,
                normalized.normalized_url_hash,
                title,
                first_seen_at,
                last_seen_at,
            ),
        ).lastrowid
        connection.commit()

    return int(job_post_id)


def _write_report(
    output_dir: Path,
    job_post_id: int,
    seen_at: str = "2026-06-10",
    body: str = "# 분석 결과\n\n본문",
) -> Path:
    report_path = output_dir / "post" / seen_at / f"{job_post_id}-Backend-Engineer.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(body, encoding="utf-8")
    return report_path


def _publish_record(db_path: Path, job_post_id: int) -> sqlite3.Row:
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT job_post_id, notion_page_id, notion_url, analysis_path, analysis_hash
            FROM notion_publish_records
            WHERE job_post_id = ?
            """,
            (job_post_id,),
        ).fetchone()
    assert row is not None
    return row


def test_publish_apply_url_reports_creates_notion_page_and_records_it(
    tmp_path,
) -> None:
    db_path = tmp_path / "employment.sqlite"
    output_dir = tmp_path / "analysis"
    job_post_id = _seed_job_post(db_path)
    report_path = _write_report(output_dir, job_post_id)
    notion_parent = NotionParent("page_id", "parent-page")
    notion_client = FakeNotionClient()

    results = publish_apply_url_reports(
        PublishApplyUrlReportsOptions(
            db_path=db_path,
            output_dir=output_dir,
            seen_at="2026-06-10",
            notion_parent=notion_parent,
        ),
        notion_client=notion_client,
    )

    assert [result.status for result in results] == ["created"]
    assert results[0].notion_page_id == "page-1"
    assert notion_client.created[0][0] == notion_parent
    assert "# Backend Engineer" in notion_client.created[0][1]
    assert "## 공고 메타데이터" in notion_client.created[0][1]

    row = _publish_record(db_path, job_post_id)
    assert row["notion_page_id"] == "page-1"
    assert row["notion_url"] == "https://notion.so/page-1"
    assert row["analysis_path"] == str(report_path)
    assert len(row["analysis_hash"]) == 64


def test_publish_apply_url_reports_skips_same_report_hash(tmp_path) -> None:
    db_path = tmp_path / "employment.sqlite"
    output_dir = tmp_path / "analysis"
    job_post_id = _seed_job_post(db_path)
    _write_report(output_dir, job_post_id)
    notion_parent = NotionParent("page_id", "parent-page")

    publish_apply_url_reports(
        PublishApplyUrlReportsOptions(
            db_path=db_path,
            output_dir=output_dir,
            seen_at="2026-06-10",
            notion_parent=notion_parent,
        ),
        notion_client=FakeNotionClient(),
    )

    second_client = FakeNotionClient()
    results = publish_apply_url_reports(
        PublishApplyUrlReportsOptions(
            db_path=db_path,
            output_dir=output_dir,
            seen_at="2026-06-10",
            notion_parent=notion_parent,
        ),
        notion_client=second_client,
    )

    assert [result.status for result in results] == ["skipped"]
    assert second_client.created == []
    assert second_client.updated == []


def test_publish_apply_url_reports_updates_existing_page_when_report_changes(
    tmp_path,
) -> None:
    db_path = tmp_path / "employment.sqlite"
    output_dir = tmp_path / "analysis"
    job_post_id = _seed_job_post(db_path)
    report_path = _write_report(output_dir, job_post_id, body="# 분석 결과\n\n초안")
    notion_parent = NotionParent("page_id", "parent-page")

    publish_apply_url_reports(
        PublishApplyUrlReportsOptions(
            db_path=db_path,
            output_dir=output_dir,
            seen_at="2026-06-10",
            notion_parent=notion_parent,
        ),
        notion_client=FakeNotionClient(),
    )
    before = _publish_record(db_path, job_post_id)["analysis_hash"]

    report_path.write_text("# 분석 결과\n\n수정됨", encoding="utf-8")
    update_client = FakeNotionClient()
    results = publish_apply_url_reports(
        PublishApplyUrlReportsOptions(
            db_path=db_path,
            output_dir=output_dir,
            seen_at="2026-06-10",
            notion_parent=notion_parent,
        ),
        notion_client=update_client,
    )

    assert [result.status for result in results] == ["updated"]
    assert update_client.updated[0][0] == "page-1"
    assert "수정됨" in update_client.updated[0][1]
    after = _publish_record(db_path, job_post_id)["analysis_hash"]
    assert after != before


def test_publish_apply_url_reports_dry_run_plans_create_without_notion_parent(
    tmp_path,
) -> None:
    db_path = tmp_path / "employment.sqlite"
    output_dir = tmp_path / "analysis"
    job_post_id = _seed_job_post(db_path)
    _write_report(output_dir, job_post_id)

    results = publish_apply_url_reports(
        PublishApplyUrlReportsOptions(
            db_path=db_path,
            output_dir=output_dir,
            seen_at="2026-06-10",
            dry_run=True,
            notion_parent=None,
        ),
        notion_client=FakeNotionClient(),
    )

    assert [result.status for result in results] == ["planned_create"]
    with connect(db_path) as connection:
        row_count = connection.execute(
            "SELECT COUNT(*) AS count FROM notion_publish_records"
        ).fetchone()["count"]
    assert row_count == 0


def test_build_notion_markdown_uses_report_body_and_metadata(tmp_path) -> None:
    db_path = tmp_path / "employment.sqlite"
    job_post_id = _seed_job_post(db_path, title="데이터 엔지니어")
    report_path = _write_report(tmp_path / "analysis", job_post_id)

    target = select_analysis_target_by_job_post_id(db_path, job_post_id)
    assert target is not None

    markdown = build_notion_markdown(
        target=target,
        report_path=report_path,
        report_markdown="# 분석 결과\n\n본문",
    )

    assert markdown.startswith("# 데이터 엔지니어\n")
    assert f"- job_post_id: `{job_post_id}`" in markdown
    assert "## Apply URL 분석\n\n# 분석 결과\n\n본문" in markdown


def test_notion_client_creates_page_with_supported_page_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if (
            request.method == "GET"
            and request.url.path == "/v1/data_sources/data-source"
        ):
            return httpx.Response(
                200,
                json={"properties": {"Report": {"type": "title"}}},
            )
        if request.method != "POST" or request.url.path != "/v1/pages":
            return httpx.Response(404, json={"message": "unexpected request"})
        return httpx.Response(
            200,
            json={"id": "created-page", "url": "https://notion.so/created-page"},
        )

    client = NotionClient(
        api_key="secret",
        base_url="https://notion.test",
        timeout=1,
        transport=httpx.MockTransport(handler),
    )

    page = client.create_page_from_markdown(
        NotionParent("data_source_id", "data-source"),
        "# 보고서\n본문",
    )

    assert page.page_id == "created-page"
    assert [request.method for request in requests] == ["GET", "POST"]
    assert requests[1].url.path == "/v1/pages"
    assert requests[1].headers["Notion-Version"] == "2026-03-11"
    payload = json.loads(requests[1].read())
    assert "markdown" not in payload
    assert payload["parent"] == {
        "type": "data_source_id",
        "data_source_id": "data-source",
    }
    assert payload["properties"]["Report"]["title"][0]["text"]["content"] == "보고서"
    assert [child["type"] for child in payload["children"]] == [
        "heading_1",
        "paragraph",
    ]
    assert (
        payload["children"][0]["heading_1"]["rich_text"][0]["text"]["content"]
        == "보고서"
    )
    assert (
        payload["children"][1]["paragraph"]["rich_text"][0]["text"]["content"] == "본문"
    )


def test_notion_client_creates_page_under_parent_page_with_title_property() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"id": "created-page", "url": "https://notion.so/created-page"},
        )

    client = NotionClient(
        api_key="secret",
        base_url="https://notion.test",
        timeout=1,
        transport=httpx.MockTransport(handler),
    )

    client.create_page_from_markdown(
        NotionParent("page_id", "parent-page"),
        "# 보고서\n본문",
    )

    assert [request.method for request in requests] == ["POST"]
    payload = json.loads(requests[0].read())
    assert payload["parent"] == {"type": "page_id", "page_id": "parent-page"}
    assert payload["properties"] == {
        "title": [
            {
                "type": "text",
                "text": {"content": "보고서", "link": None},
            }
        ]
    }


def test_notion_client_maps_database_parent_to_data_source_parent() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/v1/databases/database":
            return httpx.Response(
                200,
                json={"data_sources": [{"id": "data-source"}]},
            )
        if (
            request.method == "GET"
            and request.url.path == "/v1/data_sources/data-source"
        ):
            return httpx.Response(
                200,
                json={"properties": {"Report": {"type": "title"}}},
            )
        return httpx.Response(
            200,
            json={"id": "created-page", "url": "https://notion.so/created-page"},
        )

    client = NotionClient(
        api_key="secret",
        base_url="https://notion.test",
        timeout=1,
        transport=httpx.MockTransport(handler),
    )

    client.create_page_from_markdown(
        NotionParent("database_id", "database"),
        "# 보고서\n본문",
    )

    assert [request.method for request in requests] == ["GET", "GET", "POST"]
    payload = json.loads(requests[2].read())
    assert payload["parent"] == {
        "type": "data_source_id",
        "data_source_id": "data-source",
    }
    assert payload["properties"]["Report"]["title"][0]["text"]["content"] == "보고서"


def test_notion_client_replaces_page_markdown_with_block_children() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "results": [{"id": "block-1"}, {"id": "block-2"}],
                    "has_more": False,
                    "next_cursor": None,
                },
            )
        if request.method == "DELETE":
            return httpx.Response(
                200,
                json={"id": request.url.path.rsplit("/", 1)[-1]},
            )
        if request.method == "PATCH":
            return httpx.Response(200, json={"object": "list", "results": []})
        return httpx.Response(404, json={"message": "unexpected request"})

    client = NotionClient(
        api_key="secret",
        base_url="https://notion.test",
        timeout=1,
        transport=httpx.MockTransport(handler),
    )

    page = client.replace_page_markdown("existing-page", "# 새 본문\n본문")

    assert page.page_id == "existing-page"
    assert [request.method for request in requests] == [
        "GET",
        "DELETE",
        "DELETE",
        "PATCH",
    ]
    assert [request.url.path for request in requests] == [
        "/v1/blocks/existing-page/children",
        "/v1/blocks/block-1",
        "/v1/blocks/block-2",
        "/v1/blocks/existing-page/children",
    ]
    payload = json.loads(requests[3].read())
    assert "children" in payload
    assert [child["type"] for child in payload["children"]] == [
        "heading_1",
        "paragraph",
    ]
    assert (
        payload["children"][0]["heading_1"]["rich_text"][0]["text"]["content"]
        == "새 본문"
    )


def test_parse_options_reads_notion_parent_from_dotenv(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NOTION_DATA_SOURCE_ID", raising=False)
    (tmp_path / ".env").write_text(
        "NOTION_DATA_SOURCE_ID=dotenv-data-source\n",
        encoding="utf-8",
    )

    options = parse_options(["--seen-at", "2026-06-10"])

    assert options.notion_parent == NotionParent(
        "data_source_id",
        "dotenv-data-source",
    )
