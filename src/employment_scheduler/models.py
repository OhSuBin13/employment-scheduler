"""Shared data models for collection, storage, and normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class CollectionOptions:
    source: str
    target_date: date
    dry_run: bool = False


@dataclass(frozen=True)
class NormalizedLink:
    original_url: str
    normalized_url: str
    normalized_url_hash: str
    normalization_rule: str


@dataclass(frozen=True)
class CollectedPost:
    source: str
    external_id: str
    title: str
    original_url: str
    normalized_url: str
    normalized_url_hash: str
    normalization_rule: str
    collected_date: date
    source_published_at: str | None = None
    source_modified_at: str | None = None
    categories: tuple[Any, ...] = ()
    tags: tuple[Any, ...] = ()
    excerpt_text: str | None = None
