from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit


RESOURCE_NORMALIZATION_VERSION = "resource-normalization-v1"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)
LONG_HEX_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
NUMERIC_RE = re.compile(r"^\d+$")
DATE_OR_TIME_RE = re.compile(r"^\d{4}[-_]?\d{2}[-_]?\d{2}([tT_-]?\d{2}[:_]?\d{2}[:_]?\d{2})?$")
TOKEN_QUERY_KEYS = {
    "access_token",
    "auth",
    "key",
    "nonce",
    "password",
    "secret",
    "session",
    "signature",
    "sig",
    "token",
}


def normalize_resource_identifier(value: Any) -> dict[str, str]:
    raw = str(value or "").strip()
    if not raw or not _looks_like_resource(raw):
        return {}

    parsed = urlsplit(raw)
    path = parsed.path or raw.split("?", 1)[0]
    if not path.startswith("/"):
        return {}

    template_path = _normalize_path(path)
    query_template = _normalize_query(parsed.query)
    template = template_path if not query_template else f"{template_path}?{query_template}"
    fingerprint = hashlib.sha256(template.encode("utf-8")).hexdigest()[:16]
    return {
        "url_template": template,
        "resource_fingerprint": fingerprint,
        "resource_normalization_version": RESOURCE_NORMALIZATION_VERSION,
    }


def _looks_like_resource(value: str) -> bool:
    return value.startswith("/") or value.startswith("http://") or value.startswith("https://")


def _normalize_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    normalized = [_normalize_segment(part) for part in parts]
    return "/" + "/".join(normalized)


def _normalize_segment(segment: str) -> str:
    lowered = segment.lower()
    if UUID_RE.match(lowered):
        return "{uuid}"
    if LONG_HEX_RE.match(lowered):
        return "{hash}"
    if DATE_OR_TIME_RE.match(lowered):
        return "{timestamp}"
    if NUMERIC_RE.match(lowered):
        return "{id}"
    return segment


def _normalize_query(query: str) -> str:
    if not query:
        return ""
    parts: list[str] = []
    for key, _value in sorted(parse_qsl(query, keep_blank_values=True)):
        normalized_key = key.lower()
        if normalized_key in TOKEN_QUERY_KEYS or normalized_key.endswith("_token"):
            continue
        parts.append(f"{key}={{value}}")
    return "&".join(parts)
