"""Analyze collected apply URLs with Codex CLI and save Markdown reports."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import employment_scheduler.analysis.constants as analysis_constants
from employment_scheduler.analysis.models import (
    CodexApplyUrlAnalysisOptions,
    CodexApplyUrlAnalysisResult,
    JobPostAnalysisTarget,
)
from employment_scheduler.analysis.prompts import build_analysis_prompt
from employment_scheduler.analysis.repository import select_analysis_targets
from employment_scheduler.storage.database import DEFAULT_DB_PATH

CommandRunner = Callable[[Sequence[str], str], subprocess.CompletedProcess[str]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze_apply_urls.py",
        description="Analyze job_posts.apply_url values with Codex CLI.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Only analyze rows from this source key.",
    )
    parser.add_argument(
        "--seen-at",
        type=_iso_date,
        default=None,
        help="Only analyze rows whose job_posts.last_seen_at is this YYYY-MM-DD date.",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=None,
        help="Maximum number of DB rows to consider.",
    )
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=1,
        help="Number of Codex analyses to run in parallel. Defaults to 1.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run Codex even when an output file already exists.",
    )
    parser.add_argument(
        "--no-search",
        action="store_false",
        dest="enable_search",
        help="Do not pass Codex's global --search flag.",
    )
    return parser


def parse_options(argv: list[str] | None = None) -> CodexApplyUrlAnalysisOptions:
    args = build_parser().parse_args(argv)
    return CodexApplyUrlAnalysisOptions(
        db_path=DEFAULT_DB_PATH,
        output_dir=analysis_constants.DEFAULT_OUTPUT_DIR,
        source=args.source,
        seen_at=args.seen_at or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
        limit=args.limit,
        workers=args.workers,
        force=args.force,
        codex_bin=analysis_constants.DEFAULT_CODEX_BIN,
        model=analysis_constants.DEFAULT_CODEX_MODEL,
        reasoning_effort=analysis_constants.DEFAULT_REASONING_EFFORT,
        service_tier=analysis_constants.DEFAULT_SERVICE_TIER,
        sandbox=analysis_constants.DEFAULT_SANDBOX,
        enable_search=args.enable_search,
    )


def run_apply_url_analysis(
    options: CodexApplyUrlAnalysisOptions,
    run_command: CommandRunner | None = None,
) -> list[CodexApplyUrlAnalysisResult]:
    targets = select_analysis_targets(
        db_path=options.db_path,
        source=options.source,
        seen_at=options.seen_at,
        limit=options.limit,
    )
    if not targets:
        return []

    runner = run_command or _run_codex_command
    if options.workers == 1:
        return [
            _analyze_target_safely(target=target, options=options, runner=runner)
            for target in targets
        ]

    max_workers = min(options.workers, len(targets))
    results: list[CodexApplyUrlAnalysisResult | None] = [None] * len(targets)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_indexes = {
            executor.submit(
                _analyze_target_safely,
                target=target,
                options=options,
                runner=runner,
            ): index
            for index, target in enumerate(targets)
        }
        for future in as_completed(future_indexes):
            index = future_indexes[future]
            results[index] = future.result()

    return [result for result in results if result is not None]


def _analyze_target(
    target: JobPostAnalysisTarget,
    options: CodexApplyUrlAnalysisOptions,
    runner: CommandRunner,
) -> CodexApplyUrlAnalysisResult:
    output_path = build_output_path(options.output_dir, target)
    prompt_path = build_prompt_path(options.output_dir, target)
    prompt = build_analysis_prompt(target)
    command = build_codex_command(options, output_path)

    if output_path.exists() and not options.force:
        return CodexApplyUrlAnalysisResult(
            target=target,
            output_path=output_path,
            prompt_path=prompt_path,
            status="skipped",
            command=tuple(command),
        )

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

    if not output_path.exists() or not output_path.read_text(encoding="utf-8").strip():
        raise RuntimeError(
            "Codex analysis did not produce an output file for "
            f"job_post_id={target.job_post_id}: {output_path}"
        )

    return CodexApplyUrlAnalysisResult(
        target=target,
        output_path=output_path,
        prompt_path=prompt_path,
        status="analyzed",
        command=tuple(command),
    )


def _analyze_target_safely(
    target: JobPostAnalysisTarget,
    options: CodexApplyUrlAnalysisOptions,
    runner: CommandRunner,
) -> CodexApplyUrlAnalysisResult:
    try:
        return _analyze_target(target=target, options=options, runner=runner)
    except Exception as exc:  # noqa: BLE001
        return _failed_result(target, options, str(exc))


def _failed_result(
    target: JobPostAnalysisTarget,
    options: CodexApplyUrlAnalysisOptions,
    error_message: str,
) -> CodexApplyUrlAnalysisResult:
    output_path = build_output_path(options.output_dir, target)
    return CodexApplyUrlAnalysisResult(
        target=target,
        output_path=output_path,
        prompt_path=build_prompt_path(options.output_dir, target),
        status="failed",
        command=tuple(build_codex_command(options, output_path)),
        error_message=error_message,
    )


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
            "--output-last-message",
            str(output_path),
            "-",
        ]
    )
    return command


def build_output_path(output_dir: Path, target: JobPostAnalysisTarget) -> Path:
    seen_at = _safe_slug(target.last_seen_at)
    return (
        output_dir
        / "post"
        / seen_at
        / (f"{target.job_post_id}-{_safe_slug(target.title)}.md")
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

    failed_results = [result for result in results if result.status == "failed"]
    if failed_results:
        print("failed analyses:")
        for result in failed_results:
            print(
                f"- job_post_id={result.target.job_post_id}: "
                f"{result.error_message or 'unknown error'}"
            )
        return 1

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
    slug = re.sub(r"[^a-zA-Z0-9가-힣._-]+", "-", value).strip("-")
    return slug or "unknown"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a YYYY-MM-DD date") from exc
