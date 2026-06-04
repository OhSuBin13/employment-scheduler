"""Inthiswork WordPress REST API client skeleton."""

from __future__ import annotations

from datetime import date, timedelta


BASE_URL = "https://inthiswork.com/wp-json/wp/v2/posts"
SOURCE_KEY = "inthiswork"
TIMEZONE = "Asia/Seoul"


def build_posts_params(target_date: date, page: int = 1, per_page: int = 100) -> dict[str, str | int]:
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
