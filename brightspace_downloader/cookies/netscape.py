"""Read cookies exported by browser extensions.

Supported formats:
* Netscape/Mozilla ``cookies.txt`` (e.g. the "Get cookies.txt LOCALLY" extension, yt-dlp, curl),
  including ``#HttpOnly_`` prefixed lines.
* JSON exports: a list of cookie objects (Cookie-Editor, EditThisCookie) or
  ``{"cookies": [...]}`` (Playwright storage state).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import CookieImportError

MAX_FILE_SIZE = 20 * 1024 * 1024


def _truthy(value: str) -> bool:
    return str(value).strip().upper() in ("TRUE", "1", "YES")


def parse_netscape(text: str) -> list:
    cookies = []
    for raw in text.splitlines():
        line = raw.rstrip("\r\n")
        httponly = False
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
            httponly = True
        elif not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            parts = line.split(None, 6)
        if len(parts) < 6:
            continue
        domain, _subdomains, path, secure, _expires, name = (p.strip() for p in parts[:6])
        value = "\t".join(parts[6:]) if len(parts) > 6 else ""
        if not name:
            continue
        cookies.append({
            "name": name,
            "value": value.strip(),
            "domain": domain,
            "path": path or "/",
            "secure": _truthy(secure),
            "httponly": httponly,
        })
    return cookies


def parse_json(text: str) -> list:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise CookieImportError(f"The file looks like JSON but could not be read: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("cookies", [])
    if not isinstance(data, list):
        raise CookieImportError("Unrecognised JSON cookie format.")
    cookies = []
    for item in data:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        domain = item.get("domain") or item.get("host") or ""
        cookies.append({
            "name": str(item["name"]),
            "value": str(item.get("value", "")),
            "domain": str(domain),
            "path": str(item.get("path") or "/"),
            "secure": bool(item.get("secure")),
            "httponly": bool(item.get("httpOnly", item.get("httponly", False))),
        })
    return cookies


def parse_cookie_text(text: str) -> list:
    stripped = text.lstrip("﻿").strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return parse_json(stripped)
    return parse_netscape(stripped)


def load_cookie_file(path: str) -> list:
    file = Path(path)
    try:
        if file.stat().st_size > MAX_FILE_SIZE:
            raise CookieImportError("That file is too large to be a cookie export.")
        raw = file.read_bytes()
    except FileNotFoundError as exc:
        raise CookieImportError(f"File not found: {path}") from exc
    except OSError as exc:
        raise CookieImportError(f"Could not read {path}: {exc.strerror or exc}") from exc
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
    cookies = parse_cookie_text(text)
    if not cookies:
        raise CookieImportError("No cookies found in that file. Is it a cookies.txt export?")
    return cookies
