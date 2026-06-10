from datetime import date

import httpx
import pytest

from employment_scheduler.sources.inthiswork import (
    BASE_URL,
    build_it_post_record,
    build_it_posts_params,
    fetch_it_posts,
)


def test_build_it_posts_params_uses_expected_filters() -> None:
    params = build_it_posts_params(date(2026, 6, 4), page=2, per_page=50)

    assert params == {
        "tags": "191700187",
        "categories": "191700167",
        "per_page": 50,
        "page": 2,
        "_fields": "id,content.rendered,title.rendered",
        "after": "2026-06-03T00:00:00",
        "before": "2026-06-04T00:00:00",
    }


def test_fetch_it_posts_requests_posts_with_expected_options() -> None:
    captured_request: httpx.Request | None = None
    posts = [{"id": 1, "link": "https://inthiswork.com/archives/1"}]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=posts)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    assert fetch_it_posts(client, date(2026, 6, 4)) == posts

    assert captured_request is not None
    assert str(captured_request.url.copy_with(query=None)) == BASE_URL
    assert captured_request.headers["Accept"] == "application/json"
    assert captured_request.url.params["tags"] == "191700187"
    assert captured_request.url.params["categories"] == "191700167"
    assert captured_request.url.params["_fields"] == "id,content.rendered,title.rendered"
    assert captured_request.url.params["after"] == "2026-06-03T00:00:00"
    assert captured_request.url.params["before"] == "2026-06-04T00:00:00"


def test_fetch_it_posts_raises_for_http_errors() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"error": "server error"})
        )
    )

    with pytest.raises(httpx.HTTPStatusError):
        fetch_it_posts(client, date(2026, 6, 4))


def test_fetch_it_posts_rejects_non_list_payload() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"error": "unexpected"})
        )
    )

    with pytest.raises(ValueError, match="Expected a list"):
        fetch_it_posts(client, date(2026, 6, 4))


def test_fetch_it_posts_rejects_non_dict_items() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[1]))
    )

    with pytest.raises(ValueError, match="Expected a list"):
        fetch_it_posts(client, date(2026, 6, 4))


def test_build_it_post_record_extracts_apply_link() -> None:
    apply_url = (
        "https://makinarocks.career.greetinghr.com/ko/o/157208"
        "?utm_source=inthiswork&ref=job-list&fbclid=abc"
    )
    record = build_it_post_record(
        {
            "id": 351552,
            "content": {
                "rendered": (
                    f'<p><a href="{apply_url}">'
                    "지원하러 가기"
                    "</a></p>"
                )
            },
            "title": {"rendered": " Backend Engineer "},
        },
        date(2026, 6, 4),
    )

    assert record.external_id == "351552"
    assert record.title == "Backend Engineer"
    assert (
        record.apply_link.normalized_url
        == "https://makinarocks.career.greetinghr.com/ko/o/157208?ref=job-list"
    )
    assert record.apply_link.normalization_rule == "apply_url"


def test_build_it_post_record_requires_apply_link() -> None:
    with pytest.raises(ValueError, match="지원하러 가기"):
        build_it_post_record(
            {
                "id": 351553,
                "title": {"rendered": "Backend Engineer"},
                "content": {
                    "rendered": (
                        '<p><a href="https://example.com/company">회사 소개</a></p>'
                    )
                },
            },
            date(2026, 6, 4),
        )


@pytest.mark.parametrize(
    "title",
    [
        None,
        {},
        {"rendered": None},
        {"rendered": "   "},
    ],
)
def test_build_it_post_record_requires_title(title) -> None:
    with pytest.raises(ValueError, match="title"):
        build_it_post_record(
            {
                "id": 351554,
                "title": title,
                "content": {
                    "rendered": (
                        '<p><a href="https://jobs.example.com/apply">'
                        "지원하러 가기"
                        "</a></p>"
                    )
                },
            },
            date(2026, 6, 4),
        )
