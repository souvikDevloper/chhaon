"""Tiny helpers for API Gateway HTTP API (payload format 2.0)."""
from __future__ import annotations

import base64
import json
import re


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def respond(status: int, body: dict | list, cache: str = "no-store") -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8", "cache-control": cache},
        "body": json.dumps(body, ensure_ascii=False),
    }


def body(event: dict) -> dict:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    if len(raw) > 20000:
        raise HttpError(413, "request too large")
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        raise HttpError(400, "invalid JSON")
    if not isinstance(data, dict):
        raise HttpError(400, "expected a JSON object")
    return data


def source_ip(event: dict) -> str:
    return ((event.get("requestContext") or {}).get("http") or {}).get("sourceIp", "unknown")


def query(event: dict) -> dict:
    return event.get("queryStringParameters") or {}


ID_RE = re.compile(r"^[A-Za-z0-9]{4,32}$")


def valid_id(value: str) -> str:
    if not ID_RE.match(value or ""):
        raise HttpError(400, "bad id")
    return value
