import re
from pathlib import Path

from employment_scheduler.analysis.models import JobPostAnalysisTarget


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
    seen_at = _safe_slug(target.last_seen_at)

    return output_dir / "prompts" / seen_at / f"{output_path.stem}.prompt.md"


def find_report_paths(output_dir: Path, seen_at: str) -> list[Path]:
    reports_dir = output_dir / "post" / seen_at
    if not reports_dir.exists():
        return []
    return sorted(path for path in reports_dir.glob("*.md") if path.is_file())


def parse_job_post_id(report_path: Path) -> int:
    match = re.match(r"^(\d+)-", report_path.name)
    if match is None:
        raise ValueError(f"Cannot parse job_post_id from report file: {report_path}")
    return int(match.group(1))


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9가-힣._-]+", "-", value).strip("-")
    return slug or "unknown"
