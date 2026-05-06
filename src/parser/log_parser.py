from __future__ import annotations

import json
import re
import shlex
import uuid
from datetime import datetime, timezone
from typing import Any

from src.schemas import NormalizedLog

SYSLOG_PREFIX_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<gateway>\S+)\s+vpnd:\s+(?P<body>.+)$"
)


def _parse_time(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _to_status(result: str | None, event_type: str | None) -> str:
    normalized = (result or "").upper()
    if normalized in {"SUCCESS", "OK", "ALLOW"}:
        return "success"
    if normalized in {"FAIL", "FAILED"}:
        return "failed"
    if normalized in {"DENIED", "BLOCKED"}:
        return "denied"
    ev = (event_type or "").upper()
    if "FAIL" in ev:
        return "failed"
    if "DENY" in ev or "BLOCK" in ev:
        return "denied"
    if "ERROR" in ev or "CRITICAL" in ev:
        return "error"
    return "success"


def _to_action(source_type: str, event_type: str | None, resource: str | None) -> str:
    ev = (event_type or "").upper()
    if ev in {"LOGIN_SUCCESS", "LOGIN_FAIL"}:
        return "login"
    if "LOGOUT" in ev:
        return "logout"
    if source_type == "api":
        return "api_call"
    if resource and any(x in resource.lower() for x in ("download", "export", "upload", "admin")):
        if "download" in resource.lower() or "export" in resource.lower():
            return "download"
        if "upload" in resource.lower():
            return "upload"
        return "admin_action"
    return "access"


def _parse_json(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _parse_syslog(raw: str) -> dict[str, Any] | None:
    m = SYSLOG_PREFIX_RE.match(raw)
    if not m:
        return None
    result: dict[str, Any] = {
        "timestamp": m.group("timestamp"),
        "vpn_gateway": m.group("gateway"),
    }
    body = m.group("body")
    for token in shlex.split(body):
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        result[k] = v.strip('"')
    if "user" in result and "username" not in result:
        result["username"] = result["user"]
    if "event" in result and "event_type" not in result:
        result["event_type"] = result["event"]
    if "src_geo" in result:
        country, _, city = result["src_geo"].partition("/")
        result["src_country"] = country
        result["src_city"] = city
    if "duration" in result:
        result["session_duration_sec"] = int(result["duration"].rstrip("s"))
    if "bytes_recv" in result:
        try:
            result["bytes_recv"] = int(result["bytes_recv"])
        except ValueError:
            pass
    if "bytes_sent" in result:
        try:
            result["bytes_sent"] = int(result["bytes_sent"])
        except ValueError:
            pass
    if "risk_score" in result:
        try:
            result["risk_score"] = int(result["risk_score"])
        except ValueError:
            pass
    return result


def parse_log_line(raw_message: str) -> dict[str, Any]:
    parsed = _parse_json(raw_message)
    if parsed is not None:
        return parsed
    parsed = _parse_syslog(raw_message)
    if parsed is not None:
        return parsed
    return {"message": raw_message}


def normalize_raw_record(payload: str | dict[str, Any], source_type_hint: str = "vpn") -> NormalizedLog:
    raw_message = ""
    source_type = source_type_hint

    if isinstance(payload, str):
        maybe_envelope = _parse_json(payload)
        if maybe_envelope and "raw_message" in maybe_envelope:
            source_type = maybe_envelope.get("source_type", source_type_hint)
            raw_message = str(maybe_envelope["raw_message"])
        elif maybe_envelope and "message" in maybe_envelope and "timestamp" not in maybe_envelope:
            source_type = str(maybe_envelope.get("source_type", source_type_hint))
            raw_message = str(maybe_envelope["message"])
        elif maybe_envelope:
            parsed = maybe_envelope
            raw_message = json.dumps(parsed, ensure_ascii=False)
            return _build_normalized(parsed, raw_message=raw_message, source_type=source_type)
        else:
            raw_message = payload
    elif isinstance(payload, dict):
        if "raw_message" in payload:
            source_type = str(payload.get("source_type", source_type_hint))
            raw_message = str(payload["raw_message"])
        elif "message" in payload and "timestamp" not in payload and "event_time" not in payload:
            source_type = str(payload.get("source_type", source_type_hint))
            raw_message = str(payload["message"])
        else:
            raw_message = json.dumps(payload, ensure_ascii=False)
            return _build_normalized(payload, raw_message=raw_message, source_type=source_type)

    parsed = parse_log_line(raw_message)
    return _build_normalized(parsed, raw_message=raw_message, source_type=source_type)


def _build_normalized(parsed: dict[str, Any], raw_message: str, source_type: str) -> NormalizedLog:
    event_time = _parse_time(parsed.get("timestamp") or parsed.get("event_time"))
    ingest_time = datetime.now(timezone.utc)

    username = parsed.get("username") or parsed.get("user")
    src_ip = parsed.get("src_ip")
    event_type = parsed.get("event_type")
    result = parsed.get("result")

    dst_ip = parsed.get("dst_internal_ip")
    if isinstance(dst_ip, str) and dst_ip.upper() == "N/A":
        dst_ip = None

    resource = parsed.get("resource") or dst_ip or parsed.get("vpn_gateway")
    action = _to_action(source_type, event_type, resource)
    status = _to_status(result, event_type)

    risk_tags_raw = parsed.get("risk_tags")
    risk_tags: list[str] = []
    if isinstance(risk_tags_raw, str):
        risk_tags = [x.strip() for x in risk_tags_raw.split(",") if x.strip() and x.strip() != "正常"]
    elif isinstance(risk_tags_raw, list):
        risk_tags = [str(x) for x in risk_tags_raw if str(x).strip()]

    message = parsed.get("message")
    if not message:
        message = (
            f"event_type={event_type or 'UNKNOWN'} user={username or 'unknown'} "
            f"src_ip={src_ip or 'unknown'} status={status}"
        )

    normalized = {
        "event_id": str(uuid.uuid4()),
        "event_time": event_time,
        "ingest_time": ingest_time,
        "source_type": source_type if source_type in {"vpn", "oa", "api", "system", "security_device"} else "vpn",
        "username": username,
        "src_ip": src_ip,
        "src_port": _safe_int(parsed.get("src_port")),
        "dst_ip": dst_ip,
        "dst_port": _safe_int(parsed.get("dst_port")),
        "action": action,
        "resource": resource,
        "status": status,
        "http_method": parsed.get("http_method"),
        "user_agent": parsed.get("user_agent") or parsed.get("client_software"),
        "message": str(message),
        "raw_message": raw_message,
        "risk_tags": risk_tags,
        "trace_id": parsed.get("trace_id") or parsed.get("session_id"),
        "original_fields": parsed,
    }
    return NormalizedLog.model_validate(normalized)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
