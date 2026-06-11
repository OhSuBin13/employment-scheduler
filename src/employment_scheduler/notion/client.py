"""Small Notion REST client for publishing Markdown pages."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx

DEFAULT_NOTION_BASE_URL = "https://api.notion.com"
DEFAULT_NOTION_VERSION = "2026-03-11"
MAX_NOTION_BLOCKS_PER_REQUEST = 100
MAX_RICH_TEXT_CONTENT_LENGTH = 2000

NotionParentType = Literal["data_source_id", "database_id", "page_id"]
NotionBlock = dict[str, Any]

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*#*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
_QUOTE_RE = re.compile(r"^>\s?(.+)$")
_FENCE_RE = re.compile(r"^\s*```([\w#+.-]*)\s*$")
_DIVIDER_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")

_SUPPORTED_CODE_LANGUAGES = {
    "abap",
    "arduino",
    "bash",
    "basic",
    "c",
    "clojure",
    "coffeescript",
    "c++",
    "c#",
    "css",
    "dart",
    "diff",
    "docker",
    "elixir",
    "elm",
    "erlang",
    "flow",
    "fortran",
    "f#",
    "gherkin",
    "glsl",
    "go",
    "graphql",
    "groovy",
    "haskell",
    "html",
    "java",
    "java/c/c++/c#",
    "javascript",
    "json",
    "julia",
    "kotlin",
    "latex",
    "less",
    "lisp",
    "livescript",
    "lua",
    "makefile",
    "markdown",
    "markup",
    "matlab",
    "mermaid",
    "nix",
    "objective-c",
    "ocaml",
    "pascal",
    "perl",
    "php",
    "plain text",
    "powershell",
    "prolog",
    "protobuf",
    "python",
    "r",
    "reason",
    "ruby",
    "rust",
    "sass",
    "scala",
    "scheme",
    "scss",
    "shell",
    "sql",
    "swift",
    "typescript",
    "vb.net",
    "verilog",
    "vhdl",
    "visual basic",
    "webassembly",
    "xml",
    "yaml",
}

_CODE_LANGUAGE_ALIASES = {
    "md": "markdown",
    "py": "python",
    "sh": "shell",
    "text": "plain text",
    "ts": "typescript",
    "js": "javascript",
    "yml": "yaml",
    "zsh": "shell",
}


class NotionConfigurationError(ValueError):
    """Raised when required Notion settings are missing."""


class NotionApiError(RuntimeError):
    """Raised when Notion returns a non-success response."""


@dataclass(frozen=True)
class NotionParent:
    parent_type: NotionParentType
    parent_id: str

    def to_payload(self) -> dict[str, str]:
        return {"type": self.parent_type, self.parent_type: self.parent_id}


@dataclass(frozen=True)
class NotionPage:
    page_id: str
    url: str | None = None


class NotionClient:
    def __init__(
        self,
        api_key: str,
        notion_version: str = DEFAULT_NOTION_VERSION,
        base_url: str = DEFAULT_NOTION_BASE_URL,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Notion-Version": notion_version,
            },
        )
        self._title_property_cache: dict[NotionParent, str] = {}

    @classmethod
    def from_env(cls) -> NotionClient:
        api_key = os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_TOKEN")
        if not api_key:
            raise NotionConfigurationError(
                "NOTION_API_KEY is required to publish reports to Notion."
            )

        return cls(
            api_key=api_key,
            notion_version=os.environ.get(
                "NOTION_VERSION",
                DEFAULT_NOTION_VERSION,
            ),
        )

    def create_page_from_markdown(
        self,
        parent: NotionParent,
        markdown: str,
    ) -> NotionPage:
        create_parent = self._create_page_parent(parent)
        blocks = markdown_to_notion_blocks(markdown)
        response = self._client.post(
            "/v1/pages",
            json={
                "parent": create_parent.to_payload(),
                "properties": self._page_title_properties(
                    create_parent,
                    _extract_markdown_title(markdown),
                ),
                "children": blocks[:MAX_NOTION_BLOCKS_PER_REQUEST],
            },
        )
        page = _page_from_response(response)
        if not page.page_id:
            raise NotionApiError("Notion API response did not include a page id.")
        self._append_block_children(
            page.page_id,
            blocks[MAX_NOTION_BLOCKS_PER_REQUEST:],
        )
        return page

    def replace_page_markdown(self, page_id: str, markdown: str) -> NotionPage:
        for block_id in self._iter_child_block_ids(page_id):
            _ensure_success(self._client.delete(f"/v1/blocks/{block_id}"))
        self._append_block_children(page_id, markdown_to_notion_blocks(markdown))
        return NotionPage(page_id=page_id)

    def _append_block_children(
        self,
        block_id: str,
        blocks: Sequence[NotionBlock],
    ) -> None:
        for block_chunk in _chunks(blocks, MAX_NOTION_BLOCKS_PER_REQUEST):
            response = self._client.patch(
                f"/v1/blocks/{block_id}/children",
                json={"children": list(block_chunk)},
            )
            _ensure_success(response)

    def _iter_child_block_ids(self, block_id: str) -> Iterator[str]:
        next_cursor: str | None = None
        while True:
            params: dict[str, str | int] = {"page_size": MAX_NOTION_BLOCKS_PER_REQUEST}
            if next_cursor is not None:
                params["start_cursor"] = next_cursor

            data = _json_from_response(
                self._client.get(
                    f"/v1/blocks/{block_id}/children",
                    params=params,
                )
            )
            for child in data.get("results", []):
                if isinstance(child, dict):
                    block_child_id = child.get("id")
                    if isinstance(block_child_id, str) and block_child_id:
                        yield block_child_id

            if not data.get("has_more"):
                return
            cursor = data.get("next_cursor")
            if not isinstance(cursor, str) or not cursor:
                return
            next_cursor = cursor

    def _page_title_properties(
        self,
        parent: NotionParent,
        title: str,
    ) -> dict[str, Any]:
        rich_text = _rich_text(title[:MAX_RICH_TEXT_CONTENT_LENGTH])
        if parent.parent_type == "page_id":
            return {"title": rich_text}

        return {self._title_property_name(parent): {"title": rich_text}}

    def _title_property_name(self, parent: NotionParent) -> str:
        cached = self._title_property_cache.get(parent)
        if cached is not None:
            return cached

        if parent.parent_type == "data_source_id":
            path = f"/v1/data_sources/{parent.parent_id}"
        elif parent.parent_type == "database_id":
            path = f"/v1/databases/{parent.parent_id}"
        else:
            raise NotionConfigurationError(
                f"Unsupported Notion parent type for title lookup: {parent.parent_type}"
            )

        data = _json_from_response(self._client.get(path))
        properties = data.get("properties")
        if isinstance(properties, dict):
            for name, schema in properties.items():
                if isinstance(name, str) and _is_title_property(schema):
                    self._title_property_cache[parent] = name
                    return name

        raise NotionConfigurationError(
            f"Could not find a title property for Notion parent {parent.parent_id}."
        )

    def _create_page_parent(self, parent: NotionParent) -> NotionParent:
        if parent.parent_type != "database_id":
            return parent

        data = _json_from_response(
            self._client.get(f"/v1/databases/{parent.parent_id}")
        )
        data_sources = data.get("data_sources")
        if isinstance(data_sources, list):
            for data_source in data_sources:
                if not isinstance(data_source, dict):
                    continue
                data_source_id = data_source.get("id")
                if isinstance(data_source_id, str) and data_source_id:
                    return NotionParent("data_source_id", data_source_id)

        return parent


def resolve_notion_parent(
    data_source_id: str | None = None,
    database_id: str | None = None,
    parent_page_id: str | None = None,
) -> NotionParent | None:
    data_source_id = data_source_id or os.environ.get("NOTION_DATA_SOURCE_ID")
    if data_source_id:
        return NotionParent("data_source_id", data_source_id)

    database_id = database_id or os.environ.get("NOTION_DATABASE_ID")
    if database_id:
        return NotionParent("database_id", database_id)

    parent_page_id = parent_page_id or os.environ.get("NOTION_PARENT_PAGE_ID")
    if parent_page_id:
        return NotionParent("page_id", parent_page_id)

    return None


def _page_from_response(
    response: httpx.Response,
    fallback_page_id: str | None = None,
) -> NotionPage:
    data = _json_from_response(response)
    return NotionPage(
        page_id=str(data.get("id") or fallback_page_id or ""),
        url=_optional_str(data.get("url")),
    )


def markdown_to_notion_blocks(markdown: str) -> list[NotionBlock]:
    blocks: list[NotionBlock] = []
    paragraph_lines: list[str] = []
    lines = markdown.splitlines()
    index = 0

    def flush_paragraph() -> None:
        if paragraph_lines:
            blocks.append(_text_block("paragraph", "\n".join(paragraph_lines)))
            paragraph_lines.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        fence_match = _FENCE_RE.match(line)
        if fence_match is not None:
            flush_paragraph()
            language = fence_match.group(1)
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and _FENCE_RE.match(lines[index]) is None:
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            blocks.append(_code_block("\n".join(code_lines), language))
            continue

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match is not None:
            flush_paragraph()
            level = len(heading_match.group(1))
            blocks.append(_text_block(f"heading_{level}", heading_match.group(2)))
            index += 1
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match is not None:
            flush_paragraph()
            blocks.append(_text_block("bulleted_list_item", bullet_match.group(1)))
            index += 1
            continue

        numbered_match = _NUMBERED_RE.match(line)
        if numbered_match is not None:
            flush_paragraph()
            blocks.append(_text_block("numbered_list_item", numbered_match.group(1)))
            index += 1
            continue

        quote_match = _QUOTE_RE.match(line)
        if quote_match is not None:
            flush_paragraph()
            blocks.append(_text_block("quote", quote_match.group(1)))
            index += 1
            continue

        if _DIVIDER_RE.match(stripped) is not None:
            flush_paragraph()
            blocks.append({"type": "divider", "divider": {}})
            index += 1
            continue

        paragraph_lines.append(line.rstrip())
        index += 1

    flush_paragraph()
    return blocks


def _text_block(block_type: str, text: str) -> NotionBlock:
    payload: dict[str, Any] = {
        "rich_text": _rich_text(text),
        "color": "default",
    }
    if block_type.startswith("heading_"):
        payload["is_toggleable"] = False
    return {"type": block_type, block_type: payload}


def _code_block(text: str, language: str) -> NotionBlock:
    return {
        "type": "code",
        "code": {
            "rich_text": _rich_text(text),
            "caption": [],
            "language": _normalize_code_language(language),
        },
    }


def _rich_text(text: str) -> list[dict[str, Any]]:
    if not text:
        return []

    return [
        {
            "type": "text",
            "text": {
                "content": chunk,
                "link": None,
            },
        }
        for chunk in _split_text(text, MAX_RICH_TEXT_CONTENT_LENGTH)
    ]


def _extract_markdown_title(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        heading_match = _HEADING_RE.match(stripped)
        if heading_match is not None and len(heading_match.group(1)) == 1:
            return _clean_markdown_text(heading_match.group(2))

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped:
            return _clean_markdown_text(stripped)

    return "Untitled report"


def _clean_markdown_text(text: str) -> str:
    cleaned = re.sub(r"`([^`]*)`", r"\1", text)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = cleaned.strip(" *_#")
    return cleaned or "Untitled report"


def _normalize_code_language(language: str) -> str:
    normalized = language.strip().lower()
    normalized = _CODE_LANGUAGE_ALIASES.get(normalized, normalized)
    if normalized in _SUPPORTED_CODE_LANGUAGES:
        return normalized
    return "plain text"


def _split_text(text: str, chunk_size: int) -> Iterator[str]:
    for start in range(0, len(text), chunk_size):
        yield text[start : start + chunk_size]


def _chunks(
    values: Sequence[NotionBlock],
    chunk_size: int,
) -> Iterator[Sequence[NotionBlock]]:
    for start in range(0, len(values), chunk_size):
        yield values[start : start + chunk_size]


def _is_title_property(schema: Any) -> bool:
    return isinstance(schema, dict) and schema.get("type") == "title"


def _ensure_success(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise NotionApiError(_format_error(response))


def _json_from_response(response: httpx.Response) -> dict[str, Any]:
    _ensure_success(response)
    try:
        data = response.json()
    except ValueError as exc:
        raise NotionApiError(
            f"Notion API response was not valid JSON: status={response.status_code}"
        ) from exc
    if not isinstance(data, dict):
        raise NotionApiError(
            f"Notion API response was not a JSON object: status={response.status_code}"
        )
    return data


def _format_error(response: httpx.Response) -> str:
    try:
        data: Any = response.json()
    except ValueError:
        data = response.text
    return f"Notion API request failed: status={response.status_code} body={data!r}"


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
