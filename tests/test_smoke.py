from employment_scheduler.collection.cli import parse_options
from employment_scheduler.normalization import normalize_link
from employment_scheduler.sources.inthiswork import build_it_posts_params


def test_parse_options_accepts_source_and_date() -> None:
    options = parse_options(["--source", "inthiswork", "--date", "2026-06-04"])

    assert options.source == "inthiswork"
    assert options.target_date.isoformat() == "2026-06-04"


def test_inthiswork_params_use_categories_key() -> None:
    options = parse_options(["--date", "2026-06-04"])
    params = build_it_posts_params(options.target_date)

    assert params["categories"] == "191700167"
    assert "caegories" not in params


def test_normalize_inthiswork_archive_url_removes_tracking_query() -> None:
    result = normalize_link(
        "inthiswork",
        "https://inthiswork.com/archives/351552?utm_source=x&fbclid=y",
    )

    assert result.normalized_url == "https://inthiswork.com/archives/351552"
    assert result.normalization_rule == "inthiswork_archives"


def test_normalize_apply_url_removes_tracking_query() -> None:
    result = normalize_link(
        "apply_url",
        "https://jobs.example.com/apply?UTM_Source=x&position=backend&fbclid=y",
    )

    assert result.normalized_url == "https://jobs.example.com/apply?position=backend"
    assert result.normalization_rule == "apply_url"
