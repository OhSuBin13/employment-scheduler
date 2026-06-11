"""Publish apply URL analysis Markdown reports to Notion."""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import employment_scheduler.analysis.utils.constants as analysis_constants
from employment_scheduler.analysis.models import (
    JobPostAnalysisTarget,
    PublishApplyUrlReportResult,
    PublishApplyUrlReportsOptions,
    PublishApplyUrlReportTarget,
)
from employment_scheduler.analysis.repository.analyze_repo import (
    select_analysis_targets_by_job_post_ids,
)
from employment_scheduler.analysis.repository.publish_repo import (
    get_notion_publish_record,
    insert_notion_publish_record,
    update_notion_publish_record,
)
from employment_scheduler.analysis.utils.cli_utils import _iso_date, _positive_int
from employment_scheduler.analysis.utils.report_paths import (
    find_report_paths,
    parse_job_post_id,
)
from employment_scheduler.notion.client import (
    NotionClient,
    NotionConfigurationError,
    NotionPage,
    NotionParent,
    resolve_notion_parent,
)
from employment_scheduler.storage.database import (
    DEFAULT_DB_PATH,
    connect,
    initialize_database,
)


class NotionPageWriter(Protocol):
    def create_page_from_markdown(
        self,
        parent: NotionParent,
        markdown: str,
    ) -> NotionPage: ...

    def replace_page_markdown(self, page_id: str, markdown: str) -> NotionPage: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="publish_apply_url_reports.py",
        description="Publish apply URL analysis Markdown reports to Notion.",
    )
    parser.add_argument(
        "--seen-at",
        type=_iso_date,
        default=None,
        help="Publish reports from data/analysis/apply_urls/post/YYYY-MM-DD.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Only publish reports whose job_posts source key matches this value.",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=None,
        help="Maximum number of report files to publish after filtering.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-write existing Notion pages even when the report hash is unchanged.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned create/update operations without calling Notion.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path. Defaults to data/employment.sqlite.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=analysis_constants.DEFAULT_OUTPUT_DIR,
        help="Analysis output directory. Defaults to data/analysis/apply_urls.",
    )

    parent_group = parser.add_mutually_exclusive_group()
    parent_group.add_argument(
        "--notion-data-source-id",
        default=None,
        help="Notion data source parent ID. Also read from NOTION_DATA_SOURCE_ID.",
    )
    parent_group.add_argument(
        "--notion-database-id",
        default=None,
        help="Legacy Notion database parent ID. Also read from NOTION_DATABASE_ID.",
    )
    parent_group.add_argument(
        "--notion-parent-page-id",
        default=None,
        help="Notion page parent ID. Also read from NOTION_PARENT_PAGE_ID.",
    )
    return parser


def parse_options(argv: list[str] | None = None) -> PublishApplyUrlReportsOptions:
    load_dotenv(dotenv_path=Path(".env"))
    args = build_parser().parse_args(argv)
    return PublishApplyUrlReportsOptions(
        db_path=args.db_path,
        output_dir=args.output_dir,
        seen_at=args.seen_at or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
        source=args.source,
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
        notion_parent=resolve_notion_parent(
            data_source_id=args.notion_data_source_id,
            database_id=args.notion_database_id,
            parent_page_id=args.notion_parent_page_id,
        ),
    )


def publish_apply_url_reports(
    options: PublishApplyUrlReportsOptions,
    notion_client: NotionPageWriter | None = None,
) -> list[PublishApplyUrlReportResult]:
    targets = select_publish_targets(options)
    if not targets:
        return []

    if not options.dry_run and options.notion_parent is None:
        raise NotionConfigurationError(
            "Set NOTION_DATA_SOURCE_ID, NOTION_DATABASE_ID, "
            "NOTION_PARENT_PAGE_ID, or pass the matching CLI option."
        )

    client = notion_client
    if not options.dry_run and client is None:
        client = NotionClient.from_env()

    results: list[PublishApplyUrlReportResult] = []
    connection = connect(options.db_path)
    try:
        initialize_database(connection)
        for report_target in targets:
            results.append(
                _publish_report_target(
                    connection=connection,
                    report_target=report_target,
                    options=options,
                    notion_client=client,
                )
            )
        connection.commit()
    finally:
        connection.close()

    return results


def select_publish_targets(
    options: PublishApplyUrlReportsOptions,
) -> list[PublishApplyUrlReportTarget]:
    if options.seen_at is None:
        raise ValueError("seen_at is required")

    report_paths = find_report_paths(options.output_dir, options.seen_at)
    job_post_ids_by_path = {
        report_path: parse_job_post_id(report_path) for report_path in report_paths
    }
    targets_by_id = {
        target.job_post_id: target
        for target in select_analysis_targets_by_job_post_ids(
            options.db_path,
            job_post_ids_by_path.values(),
        )
    }

    publish_targets: list[PublishApplyUrlReportTarget] = []
    for report_path, job_post_id in job_post_ids_by_path.items():
        target = targets_by_id.get(job_post_id)
        if target is None:
            continue
        if options.source is not None and target.source_key != options.source:
            continue

        markdown = build_notion_markdown(
            target=target,
            report_path=report_path,
            report_markdown=report_path.read_text(encoding="utf-8"),
        )
        publish_targets.append(
            PublishApplyUrlReportTarget(
                target=target,
                report_path=report_path,
                markdown=markdown,
                markdown_hash=_hash_text(markdown),
            )
        )
        if options.limit is not None and len(publish_targets) >= options.limit:
            break

    return publish_targets


def build_notion_markdown(
    target: JobPostAnalysisTarget,
    report_path: Path,
    report_markdown: str,
) -> str:
    report_body = report_markdown.strip()
    return "\n".join(
        [
            f"# {target.title}",
            "",
            "## 공고 메타데이터",
            "",
            f"- source: `{target.source_key}`",
            f"- job_post_id: `{target.job_post_id}`",
            f"- external_id: `{target.external_id}`",
            f"- apply_url: {target.apply_url}",
            f"- first_seen_at: `{target.first_seen_at}`",
            f"- last_seen_at: `{target.last_seen_at}`",
            f"- analysis_path: `{report_path}`",
            "",
            "## Apply URL 분석",
            "",
            report_body,
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_options(argv)
        results = publish_apply_url_reports(options)
    except (NotionConfigurationError, FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not results:
        print("no apply URL analysis reports matched the publish options")
        return 0

    for result in results:
        target = result.target
        target_text = (
            f"job_post_id={target.job_post_id} title={target.title}"
            if target is not None
            else "job_post_id=unknown"
        )
        print(
            f"{result.status}: {target_text} "
            f"report={result.report_path} "
            f"notion_page_id={result.notion_page_id or ''}"
        )
        if result.error_message:
            print(f"  error: {result.error_message}")

    return 1 if any(result.status == "failed" for result in results) else 0


def _publish_report_target(
    connection: sqlite3.Connection,
    report_target: PublishApplyUrlReportTarget,
    options: PublishApplyUrlReportsOptions,
    notion_client: NotionPageWriter | None,
) -> PublishApplyUrlReportResult:
    existing = get_notion_publish_record(connection, report_target.target.job_post_id)

    if existing is not None:
        if (
            existing["analysis_hash"] == report_target.markdown_hash
            and not options.force
        ):
            return PublishApplyUrlReportResult(
                target=report_target.target,
                report_path=report_target.report_path,
                status="skipped",
                notion_page_id=str(existing["notion_page_id"]),
                notion_url=_optional_row_str(existing, "notion_url"),
            )

        if options.dry_run:
            return PublishApplyUrlReportResult(
                target=report_target.target,
                report_path=report_target.report_path,
                status="planned_update",
                notion_page_id=str(existing["notion_page_id"]),
                notion_url=_optional_row_str(existing, "notion_url"),
            )

        assert notion_client is not None
        return _update_existing_page(
            connection=connection,
            report_target=report_target,
            notion_client=notion_client,
            notion_page_id=str(existing["notion_page_id"]),
            notion_url=_optional_row_str(existing, "notion_url"),
        )

    if options.dry_run:
        return PublishApplyUrlReportResult(
            target=report_target.target,
            report_path=report_target.report_path,
            status="planned_create",
        )

    assert notion_client is not None
    assert options.notion_parent is not None
    return _create_new_page(
        connection=connection,
        report_target=report_target,
        notion_client=notion_client,
        notion_parent=options.notion_parent,
    )


def _create_new_page(
    connection: sqlite3.Connection,
    report_target: PublishApplyUrlReportTarget,
    notion_client: NotionPageWriter,
    notion_parent: NotionParent,
) -> PublishApplyUrlReportResult:
    try:
        page = notion_client.create_page_from_markdown(
            notion_parent,
            report_target.markdown,
        )
        insert_notion_publish_record(connection, report_target, page)
    except Exception as exc:  # noqa: BLE001
        return _failed_result(report_target, str(exc))

    return PublishApplyUrlReportResult(
        target=report_target.target,
        report_path=report_target.report_path,
        status="created",
        notion_page_id=page.page_id,
        notion_url=page.url,
    )


def _update_existing_page(
    connection: sqlite3.Connection,
    report_target: PublishApplyUrlReportTarget,
    notion_client: NotionPageWriter,
    notion_page_id: str,
    notion_url: str | None,
) -> PublishApplyUrlReportResult:
    try:
        page = notion_client.replace_page_markdown(
            notion_page_id,
            report_target.markdown,
        )
        if page.url is None and notion_url is not None:
            page = NotionPage(page_id=page.page_id, url=notion_url)
        update_notion_publish_record(connection, report_target, page)
    except Exception as exc:  # noqa: BLE001
        return _failed_result(report_target, str(exc))

    return PublishApplyUrlReportResult(
        target=report_target.target,
        report_path=report_target.report_path,
        status="updated",
        notion_page_id=page.page_id,
        notion_url=page.url,
    )


def _failed_result(
    report_target: PublishApplyUrlReportTarget,
    error_message: str,
) -> PublishApplyUrlReportResult:
    return PublishApplyUrlReportResult(
        target=report_target.target,
        report_path=report_target.report_path,
        status="failed",
        error_message=error_message,
    )


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _optional_row_str(row: sqlite3.Row, key: str) -> str | None:
    value = row[key]
    return value if isinstance(value, str) and value else None
