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
        "_fields": "id,date,modified,link,title,categories,tags,excerpt",
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


def test_build_it_post_record_normalizes_rendered_fields() -> None:
    record = build_it_post_record(
        {
            "id": 351552,
            "date": "2026-06-03T09:00:00",
            "modified": "2026-06-03T10:00:00",
            "link": "https://inthiswork.com/archives/351552?utm_source=newsletter",
            "title": {"rendered": "백엔드 &amp; 플랫폼 개발자"},
            "categories": [191700167],
            "tags": [191700187],
            "excerpt": {"rendered": "<p>Python 개발자를 채용합니다.</p>"},
        },
        date(2026, 6, 4),
    )

    assert record.external_id == "351552"
    assert record.title == "백엔드 & 플랫폼 개발자"
    assert record.normalized_url == "https://inthiswork.com/archives/351552"
    assert record.source_published_at == "2026-06-03T09:00:00"
    assert record.source_modified_at == "2026-06-03T10:00:00"
    assert record.categories == (191700167,)
    assert record.tags == (191700187,)
    assert record.excerpt_text == "Python 개발자를 채용합니다."
