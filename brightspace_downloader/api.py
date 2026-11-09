"""The ``pywebview`` JS API: everything the frontend (web/) can call as ``pywebview.api.*``.

Every method returns a JSON-friendly dict and never raises across the bridge: failures come back
as ``{"ok": False, "error": "<message to show the user>"}``. Long-running work (downloads, the
login window) reports progress by pushing events to the page via :meth:`_emit`.
"""

from __future__ import annotations

import functools
import logging
import os
import threading
from pathlib import Path

import webview

from . import APP_TITLE, __version__
from .client import (
    BrightspaceClient,
    BrightspaceError,
    NotLoggedIn,
    host_of,
    normalize_base_url,
)
from .content import build_tree, describe_skipped
from .cookies import CookieImportError, filter_for_host, from_browser
from .cookies.netscape import load_cookie_file
from .downloader import DownloadJob
from .login import LoginWindow
from .paths import default_download_root, file_manager_name, reveal_folder
from .settings import Settings, SessionStore

log = logging.getLogger(__name__)


def bridge(func):
    """Wrap a bridge method so any error becomes a clean {'ok': False, 'error': ...} result."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            result = func(self, *args, **kwargs)
            if isinstance(result, dict) and "ok" not in result:
                result = {"ok": True, **result}
            return result if result is not None else {"ok": True}
        except BrightspaceError as exc:
            return {"ok": False, "error": str(exc)}
        except CookieImportError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("bridge call %s failed", func.__name__)
            return {"ok": False, "error": f"Something went wrong: {exc}"}

    return wrapper


class Api:
    def __init__(self):
        self.settings = Settings.load()
        self.sessions = SessionStore()
        self.client: BrightspaceClient | None = None
        self.user: dict = {}
        self._window: webview.Window | None = None
        self._job: DownloadJob | None = None
        self._trees: dict = {}  # org_unit_id -> ContentTree (kept so downloads use the same names)
        self._courses_cache: list = []
        self._lock = threading.Lock()

    def bind_window(self, window: webview.Window) -> None:
        self._window = window

    # ------------------------------------------------------------------ events
    def _emit(self, name: str, payload: dict) -> None:
        if not self._window:
            return
        import json

        data = json.dumps({"event": name, "payload": payload})
        try:
            self._window.evaluate_js(f"window.__bsdlEvent && window.__bsdlEvent({data})")
        except Exception:
            log.debug("could not deliver event %s", name, exc_info=True)

    # ------------------------------------------------------------------ startup
    @bridge
    def get_initial_state(self) -> dict:
        return {
            "appTitle": APP_TITLE,
            "version": __version__,
            "baseUrl": self.settings.base_url,
            "defaultDir": str(default_download_root()),
            "fileManager": file_manager_name(),
            "existingPolicy": self.settings.existing_policy,
            "hasSavedSession": self.sessions.load() is not None,
            "browserImport": {
                "available": from_browser.is_available(),
                "browsers": from_browser.available_browsers(),
            },
        }

    @bridge
    def resume_session(self) -> dict:
        """Re-check a previously saved session (Brightspace sessions expire ~180 min)."""
        saved = self.sessions.load()
        if not saved:
            return {"ok": False, "error": "No saved session."}
        client = BrightspaceClient(saved["base_url"], saved.get("cookies") or [])
        try:
            user = client.whoami()
        except NotLoggedIn:
            self.sessions.clear()
            return {"ok": False, "expired": True,
                    "error": "Your saved session has expired. Please log in again."}
        self._activate(client, user, saved["base_url"])
        return {"ok": True, "user": self._user_public(user), "baseUrl": client.base_url}

    # ------------------------------------------------------------------ base url
    @bridge
    def set_base_url(self, url: str) -> dict:
        base = normalize_base_url(url)
        client = BrightspaceClient(base)
        client.probe()
        self.settings.base_url = base
        self.settings.save()
        return {"baseUrl": base, "host": host_of(base)}

    # ------------------------------------------------------------------ auth
    @bridge
    def login_with_window(self) -> dict:
        base = self._require_base_url()
        done = threading.Event()
        box: dict = {}

        def on_success(cookies, user):
            box["cookies"], box["user"] = cookies, user
            done.set()

        def on_cancel():
            box["cancelled"] = True
            done.set()

        login = LoginWindow(base, on_success, on_cancel,
                            on_status=lambda msg: self._emit("login:status", {"message": msg}))
        login.open()
        if not done.wait(600):
            return {"ok": False, "error": "Login timed out. Please try again."}
        if box.get("cancelled"):
            return {"ok": False, "cancelled": True}

        cookies = filter_for_host(box["cookies"], host_of(base)) or box["cookies"]
        client = BrightspaceClient(base, cookies)
        user = box["user"]
        self._activate(client, user, base)
        return {"ok": True, "user": self._user_public(user), "baseUrl": base}

    @bridge
    def pick_cookie_file(self) -> dict:
        types = ("Cookie files (*.txt;*.json)", "All files (*.*)")
        selection = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=types) if self._window else None
        if not selection:
            return {"ok": False, "cancelled": True}
        return self.import_cookie_file(selection[0])

    @bridge
    def import_cookie_file(self, path: str) -> dict:
        base = self._require_base_url()
        cookies = load_cookie_file(path)
        matching = filter_for_host(cookies, host_of(base))
        if not matching:
            return {"ok": False, "error":
                    f"That file has no cookies for {host_of(base)}. Export cookies while signed in "
                    "to Brightspace, or use the login window."}
        return self._login_with_cookies(base, matching)

    @bridge
    def import_from_browser(self, browser: str) -> dict:
        base = self._require_base_url()
        cookies = from_browser.read_cookies(browser, host_of(base))
        return self._login_with_cookies(base, cookies)

    def _login_with_cookies(self, base: str, cookies: list) -> dict:
        client = BrightspaceClient(base, cookies)
        try:
            user = client.whoami()
        except NotLoggedIn:
            return {"ok": False, "error":
                    "Those cookies are not a valid Brightspace session (they may have expired). "
                    "Sign in to Brightspace in your browser and export fresh cookies, or use the "
                    "login window."}
        self._activate(client, user, base)
        return {"ok": True, "user": self._user_public(user), "baseUrl": base}

    @bridge
    def logout(self) -> dict:
        self.sessions.clear()
        self.client = None
        self.user = {}
        self._trees.clear()
        return {"ok": True}

    def _activate(self, client: BrightspaceClient, user: dict, base: str) -> None:
        self.client = client
        self.user = user
        self.settings.base_url = base
        self.settings.save()
        self.sessions.save(base, client.export_cookies(), self._user_public(user))

    # ------------------------------------------------------------------ courses
    @bridge
    def list_courses(self) -> dict:
        client = self._require_client()
        courses = client.list_courses()
        for course in courses:
            course["savedDir"] = self.settings.course_dirs.get(str(course["id"]), "")
        courses.sort(key=lambda c: (not c["pinned"], not c["active"], c["name"].lower()))
        self._courses_cache = courses
        return {"courses": courses, "user": self._user_public(self.user)}

    @bridge
    def load_content(self, org_unit_id: int) -> dict:
        client = self._require_client()
        tree = build_tree(client.get_toc(int(org_unit_id)))
        self._trees[int(org_unit_id)] = tree
        result = tree.to_json()
        result["skippedText"] = describe_skipped(tree.skipped)
        result["defaultDir"] = self._suggested_dir(int(org_unit_id))
        return result

    def _suggested_dir(self, org_unit_id: int) -> str:
        """Remembered folder for this course, else Documents/Brightspace/<course name>."""
        saved = self.settings.course_dirs.get(str(org_unit_id))
        if saved:
            return saved
        from .content import sanitize_name

        name = ""
        for course in getattr(self, "_courses_cache", []) or []:
            if course.get("id") == org_unit_id:
                name = course.get("name") or ""
                break
        root = default_download_root()
        return str(root / sanitize_name(name, "Course")) if name else str(root)

    # ------------------------------------------------------------------ folders
    @bridge
    def pick_folder(self, initial: str = "") -> dict:
        start = initial or str(default_download_root())
        try:
            os.makedirs(start, exist_ok=True)
        except OSError:
            start = str(Path.home())
        selection = self._window.create_file_dialog(
            webview.FileDialog.FOLDER, directory=start) if self._window else None
        if not selection:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": selection[0]}

    # ------------------------------------------------------------------ download
    @bridge
    def start_download(self, org_unit_id: int, topic_ids: list, dest: str,
                       course_name: str = "", existing_policy: str = "") -> dict:
        client = self._require_client()
        org_unit_id = int(org_unit_id)
        with self._lock:
            if self._job and self._job.is_alive():
                return {"ok": False, "error": "A download is already running."}
            tree = self._trees.get(org_unit_id)
            if not tree:
                tree = build_tree(client.get_toc(org_unit_id))
                self._trees[org_unit_id] = tree
            wanted = {int(t) for t in topic_ids}
            entries = [tree.files[tid] for tid in tree.files if tid in wanted]
            if not entries:
                return {"ok": False, "error": "No files are selected to download."}

            # The chosen folder IS the course root: the Brightspace module tree is written
            # directly inside it (e.g. <dest>/Software Engineering Methods (SEM)/Week 1/...).
            dest_root = Path(dest).expanduser()
            try:
                os.makedirs(dest_root, exist_ok=True)
            except OSError as exc:
                return {"ok": False, "error": f"Cannot create the download folder: {exc.strerror or exc}"}

            policy = existing_policy or self.settings.existing_policy
            self.settings.existing_policy = policy
            self.settings.course_dirs[str(org_unit_id)] = str(dest_root)
            self.settings.save()

            job = DownloadJob(client, org_unit_id, entries, dest_root,
                              existing_policy=policy, on_event=self._emit)
            self._job = job
            job.start()
        return {"ok": True, "count": len(entries), "dest": str(dest_root)}

    @bridge
    def cancel_download(self) -> dict:
        job = self._job
        if job and job.is_alive():
            job.cancel()
            return {"ok": True, "cancelling": True}
        return {"ok": True, "cancelling": False}

    @bridge
    def reveal(self, path: str) -> dict:
        reveal_folder(path)
        return {"ok": True}

    # ------------------------------------------------------------------ helpers
    def _require_base_url(self) -> str:
        if self.client:
            return self.client.base_url
        if self.settings.base_url:
            return self.settings.base_url
        raise BrightspaceError("Enter your Brightspace web address first.")

    def _require_client(self) -> BrightspaceClient:
        if not self.client:
            raise NotLoggedIn("You are not logged in to Brightspace.")
        return self.client

    @staticmethod
    def _user_public(user: dict) -> dict:
        first = (user or {}).get("FirstName") or ""
        last = (user or {}).get("LastName") or ""
        name = (first + " " + last).strip() or (user or {}).get("UniqueName") or "Signed in"
        return {"name": name, "uniqueName": (user or {}).get("UniqueName", "")}
