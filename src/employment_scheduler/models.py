"""Shared data models for collection, storage, and normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


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
    apply_link: NormalizedLink
    collected_date: date
