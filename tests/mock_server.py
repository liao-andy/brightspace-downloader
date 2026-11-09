"""A tiny stand-in for the Brightspace REST API, used by the tests (and the demo).

It implements only the handful of routes the app calls, with cookie auth, paging, and a few
fault-injection hooks (flaky files, truncated responses, mid-session expiry).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .sample_toc import FILE_BYTES, SAMPLE_TOC, SIMPLE_TOC

VALID_COOKIE = "session-ok"

COURSES = [
    {"Id": 844457, "Name": "Software Engineering Methods (SEM)", "Code": "CSE2115+2026+1", "pin": True},
    {"Id": 101, "Name": "Intro: Programming / Basics?", "Code": "CSE1100", "pin": False},
    {"Id": 202, "Name": "Archived Course", "Code": "OLD1", "pin": False, "active": False},
]
TOCS = {844457: SAMPLE_TOC, 101: SIMPLE_TOC, 202: {"Modules": [], "Topics": []}}


class _State:
    def __init__(self):
        self.authed = True
        self.flaky_fail_count = 2   # topic 7000001 fails this many times, then succeeds
        self._flaky_seen = 0
        self.lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    server_version = "MockBrightspace/1.0"

    # silence console noise during tests
    def log_message(self, *args):  # noqa: D401
        pass

    @property
    def st(self) -> _State:
        return self.server.state  # type: ignore[attr-defined]

    def _authed(self) -> bool:
        if not self.st.authed:
            return False
        cookie = self.headers.get("Cookie", "")
        return f"d2lSessionVal={VALID_COOKIE}" in cookie

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json;charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _forbidden(self):
        self._send_json({"Errors": [{"Message": "Forbidden"}]}, status=403)

    def do_HEAD(self):
        self._dispatch()

    def do_GET(self):
        self._dispatch()

    # ------------------------------------------------------------------ routing
    def _dispatch(self):
        from urllib.parse import urlsplit, parse_qs

        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)
        try:
            if path == "/d2l/api/versions/":
                return self._versions()
            if path.endswith("/users/whoami"):
                return self._whoami()
            if "/enrollments/myenrollments/" in path:
                return self._enrollments(query)
            if path.endswith("/content/toc"):
                return self._toc(path)
            if "/content/topics/" in path and path.endswith("/file"):
                return self._file(path)
            if path in ("/d2l/home", "/"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(b"<html><body>home</body></html>")
                return
            self._send_json({"Errors": [{"Message": "Not found"}]}, status=404)
        except BrokenPipeError:
            pass

    def _versions(self):
        self._send_json([
            {"ProductCode": "lp", "LatestVersion": "1.64", "SupportedVersions": ["1.43", "1.64"]},
            {"ProductCode": "le", "LatestVersion": "1.100", "SupportedVersions": ["1.67", "1.100"]},
        ])

    def _whoami(self):
        if not self._authed():
            return self._forbidden()
        self._send_json({
            "Identifier": "99", "FirstName": "Robin", "LastName": "Tester",
            "UniqueName": "rtester", "ProfileIdentifier": "p99",
        })

    def _enrollments(self, query):
        if not self._authed():
            return self._forbidden()
        type_id = (query.get("orgUnitTypeId") or ["3"])[0]
        if type_id != "3":
            return self._send_json({"Items": [], "PagingInfo": {"Bookmark": "", "HasMoreItems": False}})
        bookmark = (query.get("bookmark") or [""])[0]
        # two pages, to exercise paging
        page1 = COURSES[:2]
        page2 = COURSES[2:]
        if not bookmark:
            items, more, next_bm = page1, True, "page2"
        else:
            items, more, next_bm = page2, False, ""
        self._send_json({
            "Items": [self._enrollment(c) for c in items],
            "PagingInfo": {"Bookmark": next_bm, "HasMoreItems": more},
        })

    @staticmethod
    def _enrollment(course):
        return {
            "OrgUnit": {
                "Id": course["Id"], "Name": course["Name"], "Code": course["Code"],
                "Type": {"Id": 3, "Code": "Course Offering", "Name": "Course Offering"},
                "HomeUrl": f"/d2l/home/{course['Id']}",
            },
            "Access": {"IsActive": course.get("active", True), "CanAccess": True,
                       "ClasslistRoleName": "Student", "LastAccessed": "2026-10-01T00:00:00.000Z"},
            "PinDate": "2026-09-01T00:00:00.000Z" if course.get("pin") else None,
        }

    def _toc(self, path):
        if not self._authed():
            return self._forbidden()
        try:
            ou = int(path.split("/content/toc")[0].rsplit("/", 1)[-1])
        except ValueError:
            return self._send_json({"Errors": [{"Message": "Bad org unit"}]}, status=404)
        toc = TOCS.get(ou)
        if toc is None:
            return self._send_json({"Errors": [{"Message": "No such course"}]}, status=404)
        self._send_json(toc)

    def _file(self, path):
        if not self._authed():
            return self._forbidden()
        try:
            topic_id = int(path.split("/content/topics/")[1].split("/file")[0])
        except (IndexError, ValueError):
            return self._send_json({"Errors": [{"Message": "Bad topic"}]}, status=404)

        if topic_id == 7000001:  # flaky: fail a few times, then serve
            with self.st.lock:
                self.st._flaky_seen += 1
                fail = self.st._flaky_seen <= self.st.flaky_fail_count
            if fail:
                return self._send_json({"Errors": [{"Message": "Service Unavailable"}]}, status=503)

        data = FILE_BYTES.get(topic_id)
        if data is None:
            return self._send_json({"Errors": [{"Message": "Not Found"}]}, status=404)

        if topic_id == 7000002:  # declare more bytes than we send -> truncated download
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data) + 50))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)  # short write; connection then closes
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="topic{topic_id}"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


class MockBrightspace:
    """Context manager that runs the mock server on a background thread."""

    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.state = _State()  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    @property
    def state(self) -> _State:
        return self.server.state  # type: ignore[attr-defined]

    def valid_cookies(self) -> list:
        from urllib.parse import urlsplit

        host = urlsplit(self.base_url).hostname
        return [{"name": "d2lSessionVal", "value": VALID_COOKIE, "domain": host, "path": "/"}]

    def expire_session(self):
        self.state.authed = False

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
