from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import pytest

from employment_scheduler.analysis.service.codex_apply_urls import (
    CodexApplyUrlAnalysisOptions,
    build_analysis_prompt,
    build_codex_command,
    run_apply_url_analysis,
    select_analysis_targets,
)
from employment_scheduler.analysis.utils.report_paths import build_output_path
from employment_scheduler.normalization import normalize_link
from employment_scheduler.storage.database import connect, initialize_database


def _seed_job_post(
    db_path: Path,
    external_id: str = "354304",
    apply_url: str = "https://nxt.career.greetinghr.com/ko/o/219827",
    title: str = "Backend Engineer",
    first_seen_at: str = "2026-06-09",
    last_seen_at: str = "2026-06-09",
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


def test_select_analysis_targets_reads_job_posts_from_database(tmp_path) -> None:
    db_path = tmp_path / "employment.sqlite"
    job_post_id = _seed_job_post(db_path)

    targets = select_analysis_targets(
        db_path,
        source="inthiswork",
        seen_at="2026-06-09",
        limit=1,
    )

    assert len(targets) == 1
    assert targets[0].job_post_id == job_post_id
    assert targets[0].source_key == "inthiswork"
    assert targets[0].external_id == "354304"
    assert targets[0].apply_url == "https://nxt.career.greetinghr.com/ko/o/219827"


def test_select_analysis_targets_filters_by_last_seen_at(tmp_path) -> None:
    db_path = tmp_path / "employment.sqlite"
    _seed_job_post(
        db_path,
        external_id="354303",
        apply_url="https://nxt.career.greetinghr.com/ko/o/219826",
        last_seen_at="2026-06-08",
    )
    matching_job_post_id = _seed_job_post(
        db_path,
        external_id="354304",
        apply_url="https://nxt.career.greetinghr.com/ko/o/219827",
        last_seen_at="2026-06-09",
    )

    targets = select_analysis_targets(
        db_path,
        source="inthiswork",
        seen_at="2026-06-09",
    )

    assert [target.job_post_id for target in targets] == [matching_job_post_id]


def test_build_codex_command_uses_high_fast_defaults(tmp_path) -> None:
    options = CodexApplyUrlAnalysisOptions(output_dir=tmp_path)

    command = build_codex_command(options, tmp_path / "analysis.md")

    assert command == [
        "codex",
        "--search",
        "-a",
        "never",
        "exec",
        "-m",
        "gpt-5.5",
        "-c",
        'model_reasoning_effort="high"',
        "-c",
        'service_tier="priority"',
        "-s",
        "read-only",
        "--ephemeral",
        "--color",
        "never",
        "--output-last-message",
        str(tmp_path / "analysis.md"),
        "-",
    ]


def test_build_analysis_prompt_includes_apply_url_metadata(tmp_path) -> None:
    db_path = tmp_path / "employment.sqlite"
    _seed_job_post(db_path)
    target = select_analysis_targets(db_path)[0]

    prompt = build_analysis_prompt(target)

    assert "apply_url: https://nxt.career.greetinghr.com/ko/o/219827" in prompt
    assert "job_posts.id: 1" in prompt
    assert "지원 판단 메모" in prompt
    assert "do not invent details" in prompt


def test_build_output_path_includes_last_seen_at_and_title_slug(tmp_path) -> None:
    db_path = tmp_path / "employment.sqlite"
    _seed_job_post(db_path, last_seen_at="2026-06-09")
    target = select_analysis_targets(db_path)[0]

    output_path = build_output_path(tmp_path, target)

    assert output_path.parent == tmp_path / "post" / "2026-06-09"
    assert output_path.name == f"{target.job_post_id}-Backend-Engineer.md"


def test_run_apply_url_analysis_writes_prompt_and_uses_output_file(
    tmp_path,
) -> None:
    db_path = tmp_path / "employment.sqlite"
    _seed_job_post(db_path)
    calls: list[tuple[Sequence[str], str]] = []

    def fake_runner(
        command: Sequence[str], prompt: str
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, prompt))
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("# 분석 결과\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    results = run_apply_url_analysis(
        CodexApplyUrlAnalysisOptions(db_path=db_path, output_dir=tmp_path),
        run_command=fake_runner,
    )

    assert len(results) == 1
    assert results[0].status == "analyzed"
    assert results[0].output_path.read_text(encoding="utf-8") == "# 분석 결과\n"
    assert results[0].prompt_path.exists()
    assert calls[0][0][0:5] == ["codex", "--search", "-a", "never", "exec"]
    assert "apply_url: https://nxt.career.greetinghr.com/ko/o/219827" in calls[0][1]


@pytest.mark.parametrize("workers", [1, 2])
def test_run_apply_url_analysis_keeps_going_after_failure(
    tmp_path,
    workers: int,
) -> None:
    db_path = tmp_path / "employment.sqlite"
    first_job_post_id = _seed_job_post(
        db_path,
        external_id="354303",
        apply_url="https://nxt.career.greetinghr.com/ko/o/219826",
    )
    second_job_post_id = _seed_job_post(
        db_path,
        external_id="354304",
        apply_url="https://nxt.career.greetinghr.com/ko/o/219827",
    )
    calls: list[tuple[Sequence[str], str]] = []

    def fake_runner(
        command: Sequence[str], prompt: str
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, prompt))
        if "219826" in prompt:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="blocked")

        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("# 분석 결과\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    results = run_apply_url_analysis(
        CodexApplyUrlAnalysisOptions(
            db_path=db_path,
            output_dir=tmp_path,
            workers=workers,
        ),
        run_command=fake_runner,
    )

    assert [result.target.job_post_id for result in results] == [
        first_job_post_id,
        second_job_post_id,
    ]
    assert [result.status for result in results] == ["failed", "analyzed"]
    assert results[0].error_message
    assert "blocked" in results[0].error_message
    assert len(calls) == 2


def test_run_apply_url_analysis_skips_existing_output(tmp_path) -> None:
    db_path = tmp_path / "employment.sqlite"
    _seed_job_post(db_path)

    output_path = build_output_path(tmp_path, select_analysis_targets(db_path)[0])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("existing\n", encoding="utf-8")

    second_results = run_apply_url_analysis(
        CodexApplyUrlAnalysisOptions(db_path=db_path, output_dir=tmp_path),
        run_command=lambda command, prompt: subprocess.CompletedProcess(
            command, 0, stdout="", stderr=""
        ),
    )

    assert second_results[0].status == "skipped"
    assert second_results[0].output_path.read_text(encoding="utf-8") == "existing\n"
