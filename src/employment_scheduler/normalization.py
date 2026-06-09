"""URL normalization helpers."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from employment_scheduler.models import NormalizedLink

TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "gad_source",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "yclid",
}
TRACKING_QUERY_PREFIXES = ("utm_",)


def normalize_link(source_key: str, original_url: str) -> NormalizedLink:
    parsed = urlsplit(original_url)
    scheme = parsed.scheme.lower() or "https"
    host = parsed.hostname.lower() if parsed.hostname else ""
    port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
    netloc = f"{host}{port}"

    query_items = [(key, value) for key, value in parse_qsl(parsed.query)]
    query = urlencode(sorted(query_items), doseq=True)

    path = parsed.path or "/"
    rule = "default"

    if source_key == "inthiswork" and path.startswith("/archives/"):
        query = ""
        rule = "inthiswork_archives"
    elif source_key == "apply_url":
        query_items = _remove_tracking_query_items(query_items)
        query = urlencode(sorted(query_items), doseq=True)
        rule = "apply_url"

    normalized_url = urlunsplit((scheme, netloc, path, query, ""))
    normalized_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()

    return NormalizedLink(
        original_url=original_url,
        normalized_url=normalized_url,
        normalized_url_hash=normalized_hash,
        normalization_rule=rule,
    )


def _remove_tracking_query_items(
    query_items: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    return [
        (key, value)
        for key, value in query_items
        if not _is_tracking_query_key(key)
    ]


def _is_tracking_query_key(key: str) -> bool:
    normalized_key = key.lower()
    return normalized_key in TRACKING_QUERY_KEYS or normalized_key.startswith(
        TRACKING_QUERY_PREFIXES
    )
