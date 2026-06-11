from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import employment_scheduler.analysis.constants as analysis_constants
from employment_scheduler.notion.client import NotionParent
from employment_scheduler.storage.database import DEFAULT_DB_PATH

AnalysisStatus = Literal["analyzed", "failed", "planned", "skipped"]
PublishStatus = Literal[
    "created",
    "updated",
    "skipped",
    "planned_create",
    "planned_update",
    "failed",
]


@dataclass(frozen=True)
class JobPostAnalysisTarget:
    job_post_id: int
    source_key: str
    external_id: str
    apply_url: str
    first_seen_at: str
    last_seen_at: str
    title: str


@dataclass(frozen=True)
class CodexApplyUrlAnalysisOptions:
    db_path: Path = DEFAULT_DB_PATH
    output_dir: Path = analysis_constants.DEFAULT_OUTPUT_DIR
    source: str | None = None
    seen_at: str | None = None
    limit: int | None = None
    workers: int = 1
    force: bool = False
    codex_bin: str = analysis_constants.DEFAULT_CODEX_BIN
    model: str = analysis_constants.DEFAULT_CODEX_MODEL
    reasoning_effort: str = analysis_constants.DEFAULT_REASONING_EFFORT
    service_tier: str = analysis_constants.DEFAULT_SERVICE_TIER
    sandbox: str = analysis_constants.DEFAULT_SANDBOX
    enable_search: bool = True


@dataclass(frozen=True)
class CodexApplyUrlAnalysisResult:
    target: JobPostAnalysisTarget
    output_path: Path
    prompt_path: Path
    status: AnalysisStatus
    command: tuple[str, ...]
    error_message: str | None = None


@dataclass(frozen=True)
class PublishApplyUrlReportsOptions:
    db_path: Path = DEFAULT_DB_PATH
    output_dir: Path = analysis_constants.DEFAULT_OUTPUT_DIR
    seen_at: str | None = None
    source: str | None = None
    limit: int | None = None
    force: bool = False
    dry_run: bool = False
    notion_parent: NotionParent | None = None


@dataclass(frozen=True)
class PublishApplyUrlReportTarget:
    target: JobPostAnalysisTarget
    report_path: Path
    markdown: str
    markdown_hash: str


@dataclass(frozen=True)
class PublishApplyUrlReportResult:
    target: JobPostAnalysisTarget | None
    report_path: Path
    status: PublishStatus
    notion_page_id: str | None = None
    notion_url: str | None = None
    error_message: str | None = None
