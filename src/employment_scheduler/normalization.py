"""URL normalization helpers."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from employment_scheduler.models import NormalizedLink


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

    normalized_url = urlunsplit((scheme, netloc, path, query, ""))
    normalized_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()

    return NormalizedLink(
        original_url=original_url,
        normalized_url=normalized_url,
        normalized_url_hash=normalized_hash,
        normalization_rule=rule,
    )
