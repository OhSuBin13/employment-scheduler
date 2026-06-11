import sqlite3

from employment_scheduler.analysis.models import PublishApplyUrlReportTarget
from employment_scheduler.analysis.repository.analyze_repo import utc_now
from employment_scheduler.notion.client import NotionPage


def get_notion_publish_record(
    connection: sqlite3.Connection,
    job_post_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id, notion_page_id, notion_url, analysis_hash
        FROM notion_publish_records
        WHERE job_post_id = ?
        """,
        (job_post_id,),
    ).fetchone()


def insert_notion_publish_record(
    connection: sqlite3.Connection,
    report_target: PublishApplyUrlReportTarget,
    page: NotionPage,
) -> None:
    now = utc_now()
    connection.execute(
        """
        INSERT INTO notion_publish_records (
          job_post_id,
          notion_page_id,
          notion_url,
          analysis_path,
          analysis_hash,
          published_at,
          updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_target.target.job_post_id,
            page.page_id,
            page.url,
            str(report_target.report_path),
            report_target.markdown_hash,
            now,
            now,
        ),
    )


def update_notion_publish_record(
    connection: sqlite3.Connection,
    report_target: PublishApplyUrlReportTarget,
    page: NotionPage,
) -> None:
    connection.execute(
        """
        UPDATE notion_publish_records
        SET notion_page_id = ?,
            notion_url = ?,
            analysis_path = ?,
            analysis_hash = ?,
            updated_at = ?
        WHERE job_post_id = ?
        """,
        (
            page.page_id,
            page.url,
            str(report_target.report_path),
            report_target.markdown_hash,
            utc_now(),
            report_target.target.job_post_id,
        ),
    )
