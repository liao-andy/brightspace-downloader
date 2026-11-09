"""Persistent user settings and the saved Brightspace session."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .paths import app_data_dir

log = logging.getLogger(__name__)

EXISTING_POLICIES = ("skip", "overwrite", "keep_both")


def _atomic_write_json(path: Path, data: Any, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        if private and sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("Ignoring unreadable %s: %s", path, exc)
        return None


@dataclass
class Settings:
    base_url: str = ""
    browser: str = "chrome"
    existing_policy: str = "skip"
    course_dirs: dict = field(default_factory=dict)

    @classmethod
    def path(cls) -> Path:
        return app_data_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        data = _read_json(cls.path())
        settings = cls()
        if isinstance(data, dict):
            for key in ("base_url", "browser", "existing_policy"):
                if isinstance(data.get(key), str):
                    setattr(settings, key, data[key])
            if isinstance(data.get("course_dirs"), dict):
                settings.course_dirs = {
                    str(k): v for k, v in data["course_dirs"].items() if isinstance(v, str)
                }
        if settings.existing_policy not in EXISTING_POLICIES:
            settings.existing_policy = "skip"
        return settings

    def save(self) -> None:
        try:
            _atomic_write_json(self.path(), asdict(self))
        except OSError as exc:
            log.warning("Could not save settings: %s", exc)


class SessionStore:
    """Stores the Brightspace session cookies (sensitive!) in the app data folder."""

    def __init__(self, path: Path | None = None):
        self._path = path or (app_data_dir() / "session.json")

    def load(self) -> dict | None:
        data = _read_json(self._path)
        if not isinstance(data, dict):
            return None
        if not isinstance(data.get("base_url"), str) or not isinstance(data.get("cookies"), list):
            return None
        return data

    def save(self, base_url: str, cookies: list, user: dict | None = None) -> None:
        payload = {
            "base_url": base_url,
            "saved_at": int(time.time()),
            "user": user or {},
            "cookies": cookies,
        }
        try:
            _atomic_write_json(self._path, payload, private=True)
        except OSError as exc:
            log.warning("Could not save session: %s", exc)

    def clear(self) -> None:
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.warning("Could not delete session file: %s", exc)
