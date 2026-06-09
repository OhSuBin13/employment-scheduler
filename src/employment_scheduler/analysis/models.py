from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import employment_scheduler.analysis.constants as analysis_constants
from employment_scheduler.storage.database import DEFAULT_DB_PATH

AnalysisStatus = Literal["analyzed", "planned", "skipped"]


@dataclass(frozen=True)
class JobPostAnalysisTarget:
    job_post_id: int
    source_key: str
    external_id: str
    apply_url: str
    apply_url_hash: str
    first_seen_at: str
    last_seen_at: str


@dataclass(frozen=True)
class CodexApplyUrlAnalysisOptions:
    db_path: Path = DEFAULT_DB_PATH
    output_dir: Path = analysis_constants.DEFAULT_OUTPUT_DIR
    source: str | None = None
    job_post_ids: tuple[int, ...] = ()
    limit: int | None = None
    force: bool = False
    dry_run: bool = False
    codex_bin: str = analysis_constants.DEFAULT_CODEX_BIN
    model: str = analysis_constants.DEFAULT_CODEX_MODEL
    reasoning_effort: str = analysis_constants.DEFAULT_REASONING_EFFORT
    service_tier: str = analysis_constants.DEFAULT_SERVICE_TIER
    sandbox: str = analysis_constants.DEFAULT_SANDBOX
    enable_search: bool = True
    extra_codex_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodexApplyUrlAnalysisResult:
    target: JobPostAnalysisTarget
    output_path: Path
    prompt_path: Path
    status: AnalysisStatus
    command: tuple[str, ...]
