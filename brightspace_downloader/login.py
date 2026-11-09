"""Embedded login: open the real Brightspace site in a window and capture the session cookies.

The user signs in on the genuine institution pages (for TU Delft, brightspace.tudelft.nl
redirects to login.tudelft.nl for the NetID login and back again). This app never sees the
password - it only reads the session cookies the browser receives once the login succeeds, and
only for the Brightspace host.
"""

from __future__ import annotations

import logging
import threading
import urllib.parse
from typing import Callable

import webview

from .client import BrightspaceClient, BrightspaceError, host_of, normalize_base_url

log = logging.getLogger(__name__)


def cookies_from_window(window: "webview.Window") -> list:
    """Convert pywebview's SimpleCookie list for the current page into our cookie dicts."""
    result = []
    for simple in window.get_cookies() or []:
        for name, morsel in simple.items():
            result.append({
                "name": name,
                "value": morsel.value,
                "domain": morsel["domain"] or "",
                "path": morsel["path"] or "/",
                "secure": bool(morsel["secure"]),
                "httponly": bool(morsel["httponly"]),
            })
    return result


class LoginWindow:
    """Drives one embedded-login attempt. Call open() from any thread once webview.start() runs."""

    def __init__(self, base_url: str, on_success: Callable[[list, dict], None],
                 on_cancel: Callable[[], None], on_status: Callable[[str], None] | None = None):
        self.base_url = normalize_base_url(base_url)
        self.host = host_of(self.base_url)
        self._on_success = on_success
        self._on_cancel = on_cancel
        self._on_status = on_status or (lambda message: None)
        self._window: webview.Window | None = None
        self._finished = threading.Event()
        self._checking = threading.Lock()

    def open(self) -> None:
        self._window = webview.create_window(
            "Log in to Brightspace",
            url=self.base_url + "/d2l/home",
            width=1000,
            height=760,
            min_size=(640, 560),
        )
        self._window.events.loaded += self._on_loaded
        self._window.events.closed += self._on_closed

    # ------------------------------------------------------------------ handlers
    def _on_loaded(self) -> None:
        if self._finished.is_set():
            return
        window = self._window
        try:
            current = window.get_current_url() if window else None
        except Exception:
            current = None
        host = urllib.parse.urlsplit(current).hostname if current else None
        if host and host.lower() == self.host.lower():
            self._on_status("Checking your Brightspace session...")
            threading.Thread(target=self._try_capture, daemon=True).start()
        elif host:
            self._on_status(f"Signing in at {host}...")

    def _try_capture(self) -> None:
        if not self._checking.acquire(blocking=False):
            return
        try:
            if self._finished.is_set() or not self._window:
                return
            try:
                cookies = cookies_from_window(self._window)
            except Exception as exc:
                log.warning("Could not read cookies yet: %s", exc)
                return
            if not cookies:
                return
            try:
                client = BrightspaceClient(self.base_url, cookies)
                user = client.whoami()
            except BrightspaceError:
                return  # not logged in yet; wait for more navigation
            self._finish_success(cookies, user)
        finally:
            self._checking.release()

    def _finish_success(self, cookies: list, user: dict) -> None:
        if self._finished.is_set():
            return
        self._finished.set()
        self._on_status("Signed in. Loading your courses...")
        try:
            self._on_success(cookies, user)
        finally:
            self._close_window()

    def _on_closed(self) -> None:
        if self._finished.is_set():
            return
        self._finished.set()
        self._on_cancel()

    def _close_window(self) -> None:
        window, self._window = self._window, None
        if not window:
            return
        try:
            window.events.closed -= self._on_closed
        except Exception:
            pass
        try:
            window.destroy()
        except Exception:
            pass
