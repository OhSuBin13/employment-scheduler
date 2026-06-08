"""Inthiswork WordPress REST API client."""

from __future__ import annotations

from datetime import date, timedelta
from html import unescape
from typing import Any

import httpx
from bs4 import BeautifulSoup

from employment_scheduler.models import CollectedPost
from employment_scheduler.normalization import normalize_link

BASE_URL = "https://inthiswork.com/wp-json/wp/v2/posts"
SOURCE_KEY = "inthiswork"
TIMEZONE = "Asia/Seoul"


def build_it_posts_params(
    target_date: date, page: int = 1, per_page: int = 100
) -> dict[str, str | int]:
    before_date = target_date - timedelta(days=1)
    return {
        "tags": "191700187",
        "categories": "191700167",
        "per_page": per_page,
        "page": page,
        "_fields": "id,date,modified,link,title,categories,tags,excerpt",
        "after": f"{before_date.isoformat()}T00:00:00",
        "before": f"{target_date.isoformat()}T00:00:00",
    }


def fetch_it_posts(client: httpx.Client, target_date: date) -> list[dict[str, Any]]:
    params = build_it_posts_params(target_date)
    response = client.get(
        url=BASE_URL, params=params, headers={"Accept": "application/json"}
    )
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(
            "Expected a list[dict[str, Any]] of posts from the API response"
        )

    return data


def build_it_post_records(
    posts: list[dict[str, Any]], target_date: date
) -> list[CollectedPost]:
    return [build_it_post_record(post, target_date) for post in posts]


def build_it_post_record(post: dict[str, Any], target_date: date) -> CollectedPost:
    external_id = post.get("id")
    link = post.get("link")

    if external_id is None:
        raise ValueError("Inthiswork post is missing an id")
    if not isinstance(link, str) or not link:
        raise ValueError("Inthiswork post is missing a link")

    normalized = normalize_link(SOURCE_KEY, link)

    return CollectedPost(
        source=SOURCE_KEY,
        external_id=str(external_id),
        title=_extract_rendered_text(post.get("title"), "title", required=True)
        or "(untitled)",
        original_url=normalized.original_url,
        normalized_url=normalized.normalized_url,
        normalized_url_hash=normalized.normalized_url_hash,
        normalization_rule=normalized.normalization_rule,
        collected_date=target_date,
        source_published_at=_optional_string(post.get("date")),
        source_modified_at=_optional_string(post.get("modified")),
        categories=_as_tuple(post.get("categories")),
        tags=_as_tuple(post.get("tags")),
        excerpt_text=_extract_rendered_text(
            post.get("excerpt"), "excerpt", required=False
        )
        or None,
    )


def _extract_rendered_text(value: Any, field_name: str, *, required: bool) -> str:
    if value is None and not required:
        return ""

    if not isinstance(value, dict):
        raise ValueError(f"Expected {field_name} to be a dict with a 'rendered' field")

    rendered = value.get("rendered", "")

    if not isinstance(rendered, str):
        raise ValueError(f"Expected {field_name}.rendered to be a string")

    return unescape(BeautifulSoup(rendered, "html.parser").get_text(" ", strip=True))


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _as_tuple(value: Any) -> tuple[Any, ...]:
    if isinstance(value, list):
        return tuple(value)
    return ()
