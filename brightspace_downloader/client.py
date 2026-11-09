"""Minimal Brightspace (D2L "Valence") REST client authenticated with browser session cookies.

Brightspace's own web UI calls the same ``/d2l/api/...`` routes with the session cookies a normal
login sets, so read-only GET requests work without registering an OAuth application.
"""

from __future__ import annotations

import http.client
import re
import threading
import urllib.parse
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter

from . import __version__

USER_AGENT = f"Mozilla/5.0 (compatible; BrightspaceDownloader/{__version__})"
DEFAULT_TIMEOUT = 30
# Used only if /d2l/api/versions/ cannot be read; every current Brightspace supports these.
FALLBACK_LP_VERSION = "1.43"
FALLBACK_LE_VERSION = "1.67"
COURSE_OFFERING_TYPE_ID = 3


class BrightspaceError(Exception):
    """An error with a message that can be shown to the user as-is."""


class ConnectionProblem(BrightspaceError):
    pass


class UnexpectedResponse(BrightspaceError):
    pass


class NotLoggedIn(BrightspaceError):
    pass


class HttpError(BrightspaceError):
    def __init__(self, status: int, reason: str = "", url: str = "", detail: str = ""):
        self.status = int(status)
        self.reason = reason or http.client.responses.get(self.status, "")
        self.url = url
        self.detail = (detail or "").strip()
        super().__init__(str(self))

    def __str__(self) -> str:
        text = f"HTTP {self.status}"
        if self.reason:
            text += f" {self.reason}"
        if self.detail and self.detail.lower() not in (self.reason.lower(), ""):
            text += f": {self.detail}"
        return text

    @property
    def is_auth_error(self) -> bool:
        return self.status in (401, 403) or 300 <= self.status < 400


def normalize_base_url(text: str) -> str:
    """'brightspace.tudelft.nl', 'https://brightspace.tudelft.nl/d2l/home' -> 'https://brightspace.tudelft.nl'."""
    value = (text or "").strip()
    if not value:
        raise ValueError("Enter the address of your Brightspace site, e.g. brightspace.tudelft.nl")
    if "://" not in value:
        value = "https://" + value
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"'{text}' is not a valid web address.")
    host = parts.hostname.lower()
    if not re.fullmatch(r"[a-z0-9.-]+|\[[0-9a-f:.]+\]", host):
        raise ValueError(f"'{text}' is not a valid web address.")
    netloc = host + (f":{parts.port}" if parts.port else "")
    return f"{parts.scheme}://{netloc}"


def host_of(base_url: str) -> str:
    return urllib.parse.urlsplit(base_url).hostname or ""


def _error_detail(resp: requests.Response) -> str:
    """Extract Brightspace's error message (e.g. '{ Errors: [ {Message: "Forbidden"} ] }')."""
    try:
        text = resp.text[:4000]
    except Exception:
        return ""
    match = re.search(r'"?Message"?\s*:\s*"([^"]{1,300})"', text)
    if match:
        return match.group(1)
    stripped = text.strip()
    if stripped and len(stripped) <= 200 and "<" not in stripped:
        return stripped
    return ""


def _describe_network_error(host: str, exc: requests.RequestException) -> str:
    if isinstance(exc, requests.exceptions.SSLError):
        return f"Secure connection to {host} failed ({exc.__class__.__name__})."
    if isinstance(exc, requests.exceptions.Timeout):
        return f"The connection to {host} timed out. Check your internet connection and try again."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return f"Could not connect to {host}. Check the address and your internet connection."
    return f"Network error while talking to {host}: {exc}"


class BrightspaceClient:
    def __init__(self, base_url: str, cookies: Iterable[dict] = (), timeout: float = DEFAULT_TIMEOUT):
        self.base_url = normalize_base_url(base_url)
        self.host = host_of(self.base_url)
        self.timeout = timeout
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=16, max_retries=0)
        self.http.mount("https://", adapter)
        self.http.mount("http://", adapter)
        self.lp_version: str | None = None
        self.le_version: str | None = None
        self._version_lock = threading.Lock()
        self.set_cookies(cookies)

    # ------------------------------------------------------------------ cookies
    def set_cookies(self, cookies: Iterable[dict]) -> None:
        self.http.cookies.clear()
        for cookie in cookies:
            name = cookie.get("name")
            if not name:
                continue
            domain = (cookie.get("domain") or self.host).strip()
            rest = {"HttpOnly": None} if cookie.get("httponly") else {}
            self.http.cookies.set_cookie(
                requests.cookies.create_cookie(
                    name=name,
                    value=cookie.get("value") or "",
                    domain=domain,
                    path=cookie.get("path") or "/",
                    secure=bool(cookie.get("secure")),
                    rest=rest,
                )
            )

    def export_cookies(self) -> list[dict]:
        return [
            {
                "name": c.name,
                "value": c.value or "",
                "domain": c.domain,
                "path": c.path or "/",
                "secure": bool(c.secure),
                "httponly": c.has_nonstandard_attr("HttpOnly"),
            }
            for c in self.http.cookies
        ]

    # ------------------------------------------------------------------ plumbing
    def _request(self, method: str, path: str, *, params=None, stream=False, allow_redirects=False,
                 accept: str = "application/json") -> requests.Response:
        url = path if "://" in path else self.base_url + path
        try:
            return self.http.request(
                method,
                url,
                params=params,
                stream=stream,
                timeout=self.timeout,
                allow_redirects=allow_redirects,
                headers={"Accept": accept},
            )
        except requests.RequestException as exc:
            raise ConnectionProblem(_describe_network_error(self.host, exc)) from exc

    def _get_json(self, path: str, params=None) -> Any:
        resp = self._request("GET", path, params=params)
        with resp:
            if 300 <= resp.status_code < 400:
                raise HttpError(resp.status_code, resp.reason, resp.url,
                                "redirected, probably to the login page")
            if resp.status_code >= 400:
                raise HttpError(resp.status_code, resp.reason, resp.url, _error_detail(resp))
            try:
                return resp.json()
            except ValueError as exc:
                raise UnexpectedResponse(
                    f"{self.host} returned something that is not Brightspace API data."
                ) from exc

    # ------------------------------------------------------------------ API
    def probe(self) -> None:
        """Check that base_url is a Brightspace site (the versions route needs no login)."""
        try:
            data = self._get_json("/d2l/api/versions/")
        except (HttpError, UnexpectedResponse) as exc:
            raise BrightspaceError(
                f"{self.host} does not look like a Brightspace site ({exc})."
            ) from exc
        if not isinstance(data, list) or not any(
            isinstance(p, dict) and p.get("ProductCode") == "lp" for p in data
        ):
            raise BrightspaceError(f"{self.host} does not look like a Brightspace site.")
        self._apply_versions(data)

    def _apply_versions(self, data: Any) -> None:
        lp, le = FALLBACK_LP_VERSION, FALLBACK_LE_VERSION
        if isinstance(data, list):
            for product in data:
                if not isinstance(product, dict):
                    continue
                if product.get("ProductCode") == "lp" and product.get("LatestVersion"):
                    lp = str(product["LatestVersion"])
                elif product.get("ProductCode") == "le" and product.get("LatestVersion"):
                    le = str(product["LatestVersion"])
        self.lp_version, self.le_version = lp, le

    def ensure_versions(self) -> None:
        with self._version_lock:
            if self.lp_version and self.le_version:
                return
            try:
                self._apply_versions(self._get_json("/d2l/api/versions/"))
            except (HttpError, UnexpectedResponse):
                self._apply_versions(None)

    def whoami(self) -> dict:
        """Return the logged-in user, or raise NotLoggedIn if the cookies are missing/expired."""
        self.ensure_versions()
        try:
            data = self._get_json(f"/d2l/api/lp/{self.lp_version}/users/whoami")
        except HttpError as exc:
            if exc.is_auth_error:
                raise NotLoggedIn("Not logged in to Brightspace (or the session has expired).") from exc
            raise
        except UnexpectedResponse as exc:
            raise NotLoggedIn("Not logged in to Brightspace (or the session has expired).") from exc
        if not isinstance(data, dict) or "Identifier" not in data:
            raise NotLoggedIn("Not logged in to Brightspace.")
        return data

    def is_logged_in(self) -> bool:
        try:
            self.whoami()
            return True
        except NotLoggedIn:
            return False
        except BrightspaceError:
            return True  # network trouble etc. - don't claim the session expired

    def _paged(self, path: str, params: dict) -> list:
        items: list = []
        bookmark = None
        for _ in range(500):
            query = dict(params)
            if bookmark:
                query["bookmark"] = bookmark
            data = self._get_json(path, query)
            if not isinstance(data, dict):
                break
            items.extend(data.get("Items") or [])
            paging = data.get("PagingInfo") or {}
            next_bookmark = paging.get("Bookmark")
            if not paging.get("HasMoreItems") or not next_bookmark or next_bookmark == bookmark:
                break
            bookmark = next_bookmark
        return items

    def list_courses(self) -> list[dict]:
        self.ensure_versions()
        path = f"/d2l/api/lp/{self.lp_version}/enrollments/myenrollments/"
        items = self._paged(path, {"orgUnitTypeId": COURSE_OFFERING_TYPE_ID})
        if not items:  # unusual installs may use another type id; filter by name instead
            items = [
                it for it in self._paged(path, {})
                if ((it.get("OrgUnit") or {}).get("Type") or {}).get("Code") == "Course Offering"
            ]
        courses = []
        seen = set()
        for item in items:
            org_unit = item.get("OrgUnit") or {}
            access = item.get("Access") or {}
            ou_id = org_unit.get("Id")
            if not ou_id or ou_id in seen or access.get("CanAccess") is False:
                continue
            seen.add(ou_id)
            courses.append(
                {
                    "id": int(ou_id),
                    "name": org_unit.get("Name") or f"Course {ou_id}",
                    "code": org_unit.get("Code") or "",
                    "homeUrl": org_unit.get("HomeUrl") or f"{self.base_url}/d2l/home/{ou_id}",
                    "lastAccessed": access.get("LastAccessed"),
                    "pinned": bool(item.get("PinDate") or item.get("IsPinned")),
                    "active": access.get("IsActive", True) is not False,
                    "role": access.get("ClasslistRoleName") or "",
                }
            )
        return courses

    def get_toc(self, org_unit_id: int) -> dict:
        self.ensure_versions()
        data = self._get_json(f"/d2l/api/le/{self.le_version}/{int(org_unit_id)}/content/toc")
        if not isinstance(data, dict):
            raise UnexpectedResponse("Brightspace returned an unexpected table of contents.")
        return data

    def topic_file_path(self, org_unit_id: int, topic_id: int) -> str:
        self.ensure_versions()
        return f"/d2l/api/le/{self.le_version}/{int(org_unit_id)}/content/topics/{int(topic_id)}/file"

    def head_file_size(self, org_unit_id: int, topic_id: int) -> int | None:
        resp = self._request("HEAD", self.topic_file_path(org_unit_id, topic_id),
                             allow_redirects=True, accept="*/*")
        with resp:
            if resp.status_code >= 400:
                raise HttpError(resp.status_code, resp.reason, resp.url)
            length = resp.headers.get("Content-Length", "")
            return int(length) if length.isdigit() else None

    def open_file(self, org_unit_id: int, topic_id: int) -> requests.Response:
        """Start downloading a topic's file. The caller must close the returned response."""
        resp = self._request("GET", self.topic_file_path(org_unit_id, topic_id),
                             stream=True, allow_redirects=True, accept="*/*")
        if resp.status_code >= 400:
            try:
                raise HttpError(resp.status_code, resp.reason, resp.url, _error_detail(resp))
            finally:
                resp.close()
        return resp
