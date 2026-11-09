"""Sequential batch downloader with progress reporting, retries and cancellation."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import requests

from .client import BrightspaceClient, BrightspaceError, ConnectionProblem, HttpError
from .content import FileEntry
from .paths import long_path

log = logging.getLogger(__name__)

CHUNK_SIZE = 256 * 1024
PROGRESS_INTERVAL = 0.1  # seconds between progress events
RETRY_DELAYS = (1.5, 4.0)  # pauses before the 2nd and 3rd attempt
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class Cancelled(Exception):
    pass


class SessionExpired(BrightspaceError):
    pass


class IncompleteDownload(BrightspaceError):
    pass


@dataclass
class DownloadSummary:
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: list = field(default_factory=list)  # [{"path": ..., "error": ...}]
    bytes: int = 0
    cancelled: bool = False
    aborted_reason: str = ""
    not_attempted: int = 0
    dest: str = ""
    seconds: float = 0.0

    def to_json(self) -> dict:
        return {
            "total": self.total,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
            "bytes": self.bytes,
            "cancelled": self.cancelled,
            "abortedReason": self.aborted_reason,
            "notAttempted": self.not_attempted,
            "dest": self.dest,
            "seconds": round(self.seconds, 1),
        }


def _exists(path: Path) -> bool:
    return os.path.lexists(long_path(path))


def _size(path: Path) -> int | None:
    try:
        return os.stat(long_path(path)).st_size
    except OSError:
        return None


def _numbered(path: Path, n: int) -> Path:
    stem, ext = os.path.splitext(path.name)
    if not stem:
        stem, ext = path.name, ""
    return path.with_name(f"{stem} ({n}){ext}")


class DownloadJob(threading.Thread):
    """Downloads FileEntries one after another into dest_dir, preserving their folder paths.

    existing_policy:
      'skip'      - leave files that already exist untouched (default; keeps your annotations)
      'overwrite' - replace them with the version on Brightspace
      'keep_both' - keep the old file and save the new one as 'name (1).ext',
                    unless an existing copy already has exactly the same size
    """

    def __init__(
        self,
        client: BrightspaceClient,
        org_unit_id: int,
        entries: Iterable[FileEntry],
        dest_dir: Path,
        existing_policy: str = "skip",
        known_sizes: dict | None = None,
        on_event: Callable[[str, dict], None] | None = None,
    ):
        super().__init__(name="download-job", daemon=True)
        self.client = client
        self.org_unit_id = int(org_unit_id)
        self.entries = list(entries)
        self.dest_dir = Path(dest_dir)
        self.policy = existing_policy if existing_policy in ("skip", "overwrite", "keep_both") else "skip"
        self.sizes = {int(k): v for k, v in (known_sizes or {}).items() if isinstance(v, int) and v >= 0}
        self.on_event = on_event or (lambda name, payload: None)
        self._cancel = threading.Event()
        self.summary = DownloadSummary(total=len(self.entries), dest=str(self.dest_dir))
        # progress bookkeeping
        self._all_sizes_known = all(e.topic_id in self.sizes for e in self.entries)
        self._total_bytes = sum(self.sizes.get(e.topic_id, 0) for e in self.entries)
        self._done_weight = 0.0  # bytes (if all sizes known) or files completed
        self._last_emit = 0.0
        self._speed_samples: list = []

    # ------------------------------------------------------------------ control
    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # ------------------------------------------------------------------ events
    def _emit(self, name: str, payload: dict) -> None:
        try:
            self.on_event(name, payload)
        except Exception:  # never let the UI break the download
            log.exception("event handler failed for %s", name)

    def _fraction(self, current_done: int, current_total: int | None) -> float:
        if self._all_sizes_known and self._total_bytes > 0:
            return min(1.0, (self._done_weight + current_done) / self._total_bytes)
        if not self.entries:
            return 1.0
        partial = (current_done / current_total) if current_total else 0.0
        return min(1.0, (self._done_weight + min(partial, 1.0)) / len(self.entries))

    def _speed(self) -> float:
        now = time.monotonic()
        samples = [s for s in self._speed_samples if now - s[0] <= 3.0]
        self._speed_samples = samples
        if len(samples) < 2:
            return 0.0
        span = samples[-1][0] - samples[0][0]
        return (samples[-1][1] - samples[0][1]) / span if span > 0 else 0.0

    def _progress(self, index: int, entry: FileEntry, done: int, total: int | None, force=False) -> None:
        now = time.monotonic()
        self._speed_samples.append((now, self.summary.bytes + done))
        if not force and now - self._last_emit < PROGRESS_INTERVAL:
            return
        self._last_emit = now
        self._emit("download:progress", {
            "index": index + 1,
            "total": len(self.entries),
            "name": entry.name,
            "path": entry.rel_path,
            "fileBytes": done,
            "fileTotal": total,
            "bytes": self.summary.bytes + done,
            "totalBytes": self._total_bytes if self._all_sizes_known else None,
            "fraction": self._fraction(done, total),
            "speed": self._speed(),
        })

    def _complete_weight(self, entry: FileEntry) -> None:
        if self._all_sizes_known:
            self._done_weight += self.sizes.get(entry.topic_id, 0)
        else:
            self._done_weight += 1

    # ------------------------------------------------------------------ main loop
    def run(self) -> None:
        started = time.monotonic()
        self._emit("download:start", {"total": len(self.entries), "dest": str(self.dest_dir),
                                      "totalBytes": self._total_bytes if self._all_sizes_known else None})
        for index, entry in enumerate(self.entries):
            if self.cancelled:
                self.summary.cancelled = True
                self.summary.not_attempted = len(self.entries) - index
                break
            self._progress(index, entry, 0, self.sizes.get(entry.topic_id), force=True)
            try:
                outcome = self._download_with_retries(index, entry)
                if outcome == "skipped":
                    self.summary.skipped += 1
                else:
                    self.summary.downloaded += 1
            except Cancelled:
                self.summary.cancelled = True
                self.summary.not_attempted = len(self.entries) - index
                break
            except SessionExpired as exc:
                self._record_failure(entry, str(exc))
                self.summary.aborted_reason = str(exc)
                self.summary.not_attempted = len(self.entries) - index - 1
                break
            except Exception as exc:  # report and continue with the next file
                message = str(exc) if isinstance(exc, BrightspaceError) else f"{type(exc).__name__}: {exc}"
                self._record_failure(entry, message)
            self._complete_weight(entry)
            self._progress(index, entry, 0, None, force=True)
        self.summary.seconds = time.monotonic() - started
        self._emit("download:done", self.summary.to_json())

    def _record_failure(self, entry: FileEntry, message: str) -> None:
        failure = {"path": entry.rel_path, "name": entry.name, "error": message}
        self.summary.failed.append(failure)
        self._emit("download:error", failure)

    def _download_with_retries(self, index: int, entry: FileEntry) -> str:
        attempt = 0
        while True:
            try:
                return self._download_one(index, entry)
            except HttpError as exc:
                if exc.status in (401, 403) and not self.client.is_logged_in():
                    raise SessionExpired(
                        "Your Brightspace session has expired. Log in again and restart the "
                        "download - files that were already downloaded will be skipped."
                    ) from exc
                if exc.status not in RETRYABLE_STATUS or attempt >= len(RETRY_DELAYS):
                    raise
            except (ConnectionProblem, IncompleteDownload, requests.RequestException, ConnectionError):
                if attempt >= len(RETRY_DELAYS):
                    raise
            self._sleep(RETRY_DELAYS[attempt])
            attempt += 1

    def _sleep(self, seconds: float) -> None:
        if self._cancel.wait(seconds):
            raise Cancelled()

    def _download_one(self, index: int, entry: FileEntry) -> str:
        target = self.dest_dir.joinpath(*entry.rel_parts)
        if self.policy == "skip" and _exists(target):
            return "skipped"

        response = self.client.open_file(self.org_unit_id, entry.topic_id)
        with response:
            length = response.headers.get("Content-Length", "")
            expected = int(length) if length.isdigit() else None
            if expected is not None:
                self.sizes.setdefault(entry.topic_id, expected)

            if _exists(target):
                if self.policy == "skip":  # appeared meanwhile
                    return "skipped"
                if self.policy == "keep_both":
                    target = self._keep_both_target(target, expected)
                    if target is None:
                        return "skipped"

            os.makedirs(long_path(target.parent), exist_ok=True)
            part = target.with_name(target.name + ".part")
            written = 0
            try:
                with open(long_path(part), "wb") as fh:
                    for chunk in response.iter_content(CHUNK_SIZE):
                        if self.cancelled:
                            raise Cancelled()
                        if not chunk:
                            continue
                        fh.write(chunk)
                        written += len(chunk)
                        self._progress(index, entry, written, expected)
                if expected is not None and written != expected:
                    raise IncompleteDownload(
                        f"Download incomplete ({written} of {expected} bytes received)."
                    )
                os.replace(long_path(part), long_path(target))
            except BaseException:
                try:
                    os.remove(long_path(part))
                except OSError:
                    pass
                raise
        self.summary.bytes += written
        return "downloaded"

    def _keep_both_target(self, target: Path, expected: int | None) -> Path | None:
        """Free 'name (n).ext' path, or None if an existing copy already has the same size."""
        candidate, n = target, 1
        while _exists(candidate):
            if expected is not None and _size(candidate) == expected:
                return None
            candidate = _numbered(target, n)
            n += 1
        return candidate
