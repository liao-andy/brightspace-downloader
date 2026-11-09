#!/usr/bin/env python3
"""Launch a packaged release build once and check that it really starts.

Usage:  python packaging/smoke_test.py [dist/release]

Unpacks the release archive found in the given folder into a temp dir (so the archive itself is
what gets tested), runs it with BSDL_SMOKE_TEST set, and checks the marker file the app writes
after its UI has rendered (see brightspace_downloader/app.py). On Linux without a display it
runs under xvfb-run. Exits non-zero on any failure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

TIMEOUT = 180  # seconds; the first launch of a one-file build unpacks itself first
NAME = "BrightspaceDownloader"


def find_artifact(folder: Path) -> Path:
    for pattern in ("*.exe", "*.zip", "*.tar.gz"):
        found = sorted(folder.glob(f"{NAME}-*{pattern[1:]}"))
        if found:
            return found[0]
    raise SystemExit(f"No release archive found in {folder}")


def unpack(artifact: Path, into: Path) -> list[str]:
    """Return the command that launches the unpacked app."""
    into.mkdir(parents=True, exist_ok=True)
    if artifact.suffix == ".exe":
        exe = into / artifact.name
        shutil.copy2(artifact, exe)
        return [str(exe)]
    if artifact.suffix == ".zip":  # macOS .app bundle; ditto preserves symlinks and signatures
        subprocess.run(["ditto", "-x", "-k", str(artifact), str(into)], check=True)
        return [str(into / f"{NAME}.app" / "Contents" / "MacOS" / NAME)]
    with tarfile.open(artifact) as tar:
        tar.extractall(into, filter="tar") if hasattr(tarfile, "data_filter") else tar.extractall(into)
    cmd = [str(into / NAME / NAME)]
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a", "-s", "-screen 0 1280x1024x24"] + cmd
    return cmd


def main() -> int:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/release")
    artifact = find_artifact(folder)
    print(f"Smoke-testing {artifact.name}", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cmd = unpack(artifact, tmp_path / "app")
        marker = tmp_path / "smoke.txt"
        env = dict(os.environ, BSDL_SMOKE_TEST=str(marker), BSDL_DATA_DIR=str(tmp_path / "data"))
        print("Running:", " ".join(cmd), flush=True)
        try:
            proc = subprocess.run(cmd, env=env, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            print(f"FAIL: the app did not finish within {TIMEOUT}s", file=sys.stderr)
            return 1
        report = marker.read_text(encoding="utf-8") if marker.exists() else ""
        print(f"exit code: {proc.returncode}\n{report or '(no marker written)'}", flush=True)
        if proc.returncode != 0 or "brand=Brightspace Downloader" not in report or "logo=True" not in report:
            print("FAIL: the app did not render its UI", file=sys.stderr)
            return 1
    print("OK: the app started and rendered its UI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
