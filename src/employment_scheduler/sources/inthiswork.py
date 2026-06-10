"""Inthiswork WordPress REST API client."""

from __future__ import annotations

from datetime import date, timedelta
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from employment_scheduler.models import CollectedPost
from employment_scheduler.normalization import normalize_link

BASE_URL = "https://inthiswork.com/wp-json/wp/v2/posts"
SOURCE_KEY = "inthiswork"


def build_it_posts_params(
    target_date: date, page: int = 1, per_page: int = 100
) -> dict[str, str | int]:
    before_date = target_date - timedelta(days=1)
    return {
        "tags": "191700187",
        "categories": "191700167",
        "per_page": per_page,
        "page": page,
        "_fields": "id,content.rendered,title.rendered",
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

    if external_id is None:
        raise ValueError("Inthiswork post is missing an id")

    apply_url = _extract_apply_url(post.get("content"))
    if apply_url is None:
        raise ValueError("Inthiswork post is missing a '지원하러 가기' link")

    title = _extract_title(post.get("title"))

    return CollectedPost(
        source=SOURCE_KEY,
        external_id=str(external_id),
        apply_link=normalize_link("apply_url", apply_url),
        title=title,
        collected_date=target_date,
    )


def _extract_apply_url(content: Any) -> str | None:
    if not isinstance(content, dict):
        return None

    rendered = content.get("rendered", "")
    if not isinstance(rendered, str) or not rendered:
        return None

    soup = BeautifulSoup(rendered, "html.parser")
    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.get_text(" ", strip=True).split())
        if "지원하러 가기" not in label:
            continue

        href = anchor.get("href")
        if not isinstance(href, str):
            continue

        url = urljoin("https://inthiswork.com", unescape(href).strip())
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return url

    return None


def _extract_title(title: Any) -> str:
    if not isinstance(title, dict):
        raise ValueError("Inthiswork title is missing or not a string")

    rendered = title.get("rendered")
    if not isinstance(rendered, str):
        raise ValueError("Inthiswork title is missing or not a string")

    title_text = " ".join(
        BeautifulSoup(unescape(rendered), "html.parser")
        .get_text(" ", strip=True)
        .split()
    )
    if not title_text:
        raise ValueError("Inthiswork title is blank")

    return title_text
