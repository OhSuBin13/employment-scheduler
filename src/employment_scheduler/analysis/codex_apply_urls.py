"""Analyze collected apply URLs with Codex CLI and save Markdown reports."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from employment_scheduler.storage.database import DEFAULT_DB_PATH

DEFAULT_OUTPUT_DIR = Path("data/analysis/apply_urls")
DEFAULT_CODEX_BIN = "codex"
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_SERVICE_TIER = "priority"
DEFAULT_SANDBOX = "read-only"

AnalysisStatus = Literal["analyzed", "planned", "skipped"]
CommandRunner = Callable[[Sequence[str], str], subprocess.CompletedProcess[str]]


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
    output_dir: Path = DEFAULT_OUTPUT_DIR
    source: str | None = None
    job_post_ids: tuple[int, ...] = ()
    limit: int | None = None
    force: bool = False
    dry_run: bool = False
    codex_bin: str = DEFAULT_CODEX_BIN
    model: str = DEFAULT_CODEX_MODEL
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    service_tier: str = DEFAULT_SERVICE_TIER
    sandbox: str = DEFAULT_SANDBOX
    enable_search: bool = True
    extra_codex_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodexApplyUrlAnalysisResult:
    target: JobPostAnalysisTarget
    output_path: Path
    prompt_path: Path
    status: AnalysisStatus
    command: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze_apply_urls.py",
        description="Analyze job_posts.apply_url values with Codex CLI.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path. Defaults to data/employment.sqlite.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for Markdown reports. Defaults to data/analysis/apply_urls.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Only analyze rows from this source key.",
    )
    parser.add_argument(
        "--job-post-id",
        type=int,
        action="append",
        dest="job_post_ids",
        default=[],
        help="Analyze a specific job_posts.id. Repeat for multiple ids.",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=None,
        help="Maximum number of DB rows to consider.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run Codex even when an output file already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned work without writing prompts or running Codex.",
    )
    parser.add_argument(
        "--codex-bin",
        default=DEFAULT_CODEX_BIN,
        help="Codex executable name or path. Defaults to codex.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_CODEX_MODEL,
        help=f"Codex model. Defaults to {DEFAULT_CODEX_MODEL}.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        help=f"Codex reasoning effort. Defaults to {DEFAULT_REASONING_EFFORT}.",
    )
    parser.add_argument(
        "--service-tier",
        default=DEFAULT_SERVICE_TIER,
        help=(
            "Codex service tier. Defaults to priority, the local CLI catalog's "
            "Fast tier id."
        ),
    )
    parser.add_argument(
        "--sandbox",
        default=DEFAULT_SANDBOX,
        choices=("read-only", "workspace-write", "danger-full-access"),
        help="Sandbox mode for the Codex exec process. Defaults to read-only.",
    )
    parser.add_argument(
        "--no-search",
        action="store_false",
        dest="enable_search",
        help="Do not pass Codex's global --search flag.",
    )
    parser.add_argument(
        "--extra-codex-arg",
        action="append",
        default=[],
        help="Additional argument passed after 'codex exec'. Repeat as needed.",
    )
    return parser


def parse_options(argv: list[str] | None = None) -> CodexApplyUrlAnalysisOptions:
    args = build_parser().parse_args(argv)
    return CodexApplyUrlAnalysisOptions(
        db_path=args.db,
        output_dir=args.output_dir,
        source=args.source,
        job_post_ids=tuple(args.job_post_ids),
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
        codex_bin=args.codex_bin,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        service_tier=args.service_tier,
        sandbox=args.sandbox,
        enable_search=args.enable_search,
        extra_codex_args=tuple(args.extra_codex_arg),
    )


def run_apply_url_analysis(
    options: CodexApplyUrlAnalysisOptions,
    run_command: CommandRunner | None = None,
) -> list[CodexApplyUrlAnalysisResult]:
    targets = select_analysis_targets(
        db_path=options.db_path,
        source=options.source,
        job_post_ids=options.job_post_ids,
        limit=options.limit,
    )
    if not targets:
        return []

    runner = run_command or _run_codex_command
    results: list[CodexApplyUrlAnalysisResult] = []

    for target in targets:
        output_path = build_output_path(options.output_dir, target)
        prompt_path = build_prompt_path(options.output_dir, target)
        prompt = build_analysis_prompt(target)
        command = build_codex_command(options, output_path)

        if output_path.exists() and not options.force:
            results.append(
                CodexApplyUrlAnalysisResult(
                    target=target,
                    output_path=output_path,
                    prompt_path=prompt_path,
                    status="skipped",
                    command=tuple(command),
                )
            )
            continue

        if options.dry_run:
            results.append(
                CodexApplyUrlAnalysisResult(
                    target=target,
                    output_path=output_path,
                    prompt_path=prompt_path,
                    status="planned",
                    command=tuple(command),
                )
            )
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")

        completed = runner(command, prompt)
        if completed.returncode != 0:
            raise RuntimeError(
                "Codex analysis failed for "
                f"job_post_id={target.job_post_id}: {completed.stderr.strip()}"
            )

        if not output_path.exists() and completed.stdout.strip():
            output_path.write_text(completed.stdout, encoding="utf-8")

        if not output_path.exists() or not output_path.read_text(
            encoding="utf-8"
        ).strip():
            raise RuntimeError(
                "Codex analysis did not produce an output file for "
                f"job_post_id={target.job_post_id}: {output_path}"
            )

        results.append(
            CodexApplyUrlAnalysisResult(
                target=target,
                output_path=output_path,
                prompt_path=prompt_path,
                status="analyzed",
                command=tuple(command),
            )
        )

    return results


def select_analysis_targets(
    db_path: Path,
    source: str | None = None,
    job_post_ids: tuple[int, ...] = (),
    limit: int | None = None,
) -> list[JobPostAnalysisTarget]:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {db_path}")

    where_clauses: list[str] = []
    params: list[str | int] = []

    if source is not None:
        where_clauses.append("sources.key = ?")
        params.append(source)

    if job_post_ids:
        placeholders = ", ".join("?" for _ in job_post_ids)
        where_clauses.append(f"job_posts.id IN ({placeholders})")
        params.extend(job_post_ids)

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


def build_analysis_prompt(target: JobPostAnalysisTarget) -> str:
    return f"""\
You are analyzing one employment application page collected by the local employment-scheduler pipeline.

Open and inspect the apply URL when web access is available. If the page is unavailable, blocked, dynamic, or not directly inspectable, state that clearly and do not invent details.

Return a Korean Markdown report with these sections:

1. 기본 정보
2. 회사 및 포지션 추정
3. 주요 업무
4. 자격 요건
5. 우대 사항 및 기술 키워드
6. 지원 판단 메모
7. 확인 불가 또는 리스크

Keep the report concise but evidence-based. Include the source URL and any uncertainty.

Collected job post metadata:

- job_posts.id: {target.job_post_id}
- source: {target.source_key}
- external_id: {target.external_id}
- apply_url: {target.apply_url}
- first_seen_at: {target.first_seen_at}
- last_seen_at: {target.last_seen_at}
"""


def build_codex_command(
    options: CodexApplyUrlAnalysisOptions,
    output_path: Path,
) -> list[str]:
    command = [options.codex_bin]
    if options.enable_search:
        command.append("--search")
    command.extend(["-a", "never"])

    command.extend(
        [
            "exec",
            "-m",
            options.model,
            "-c",
            _toml_setting("model_reasoning_effort", options.reasoning_effort),
            "-c",
            _toml_setting("service_tier", options.service_tier),
            "-s",
            options.sandbox,
            "--ephemeral",
            "--color",
            "never",
            *options.extra_codex_args,
            "--output-last-message",
            str(output_path),
            "-",
        ]
    )
    return command


def build_output_path(output_dir: Path, target: JobPostAnalysisTarget) -> Path:
    external_id = _safe_slug(target.external_id)
    return output_dir / (
        f"job-post-{target.job_post_id}-{external_id}-"
        f"{target.apply_url_hash[:12]}.md"
    )


def build_prompt_path(output_dir: Path, target: JobPostAnalysisTarget) -> Path:
    output_path = build_output_path(output_dir, target)
    return output_dir / "prompts" / f"{output_path.stem}.prompt.md"


def main(argv: list[str] | None = None) -> int:
    options = parse_options(argv)
    results = run_apply_url_analysis(options)

    if not results:
        print("no apply_url rows matched the analysis options")
        return 0

    for result in results:
        print(
            f"{result.status}: "
            f"job_post_id={result.target.job_post_id} "
            f"apply_url={result.target.apply_url} "
            f"output={result.output_path}"
        )

    return 0


def _run_codex_command(
    command: Sequence[str], prompt: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
    )


def _toml_setting(key: str, value: str) -> str:
    return f"{key}={json.dumps(value)}"


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return slug or "unknown"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed
