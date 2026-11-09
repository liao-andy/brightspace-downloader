#!/usr/bin/env python3
"""Print the GitHub release notes for a tag, after checking the tag matches the app version.

Usage:  python packaging/release_notes.py v1.0.0 > notes.md

Fails (exit 1) if the tag isn't "v" + __version__ or CHANGELOG.md has no section for it, so a
mistyped tag can't publish a mislabelled release.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "liao-andy/brightspace-downloader"

DOWNLOADS = """\
## Downloads

| System | File |
| --- | --- |
| Windows 10/11 (x64) | `BrightspaceDownloader-{v}-windows-x64.exe` |
| macOS 11+ (Apple Silicon) | `BrightspaceDownloader-{v}-macos-arm64.zip` |
| macOS 11+ (Intel) | `BrightspaceDownloader-{v}-macos-x64.zip` |
| Linux (x64, glibc 2.35+) | `BrightspaceDownloader-{v}-linux-x64.tar.gz` |

The builds aren't code-signed. On Windows, click **More info → Run anyway** if SmartScreen
warns you; on macOS, right-click the app → **Open** the first time. See the
[README](https://github.com/{repo}#download) for details. `SHA256SUMS.txt` lists checksums.
"""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    tag = sys.argv[1]
    init = (ROOT / "brightspace_downloader" / "__init__.py").read_text(encoding="utf-8")
    version = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init, re.M).group(1)
    if tag != f"v{version}":
        print(f"Tag {tag!r} does not match __version__ {version!r} (expected 'v{version}').", file=sys.stderr)
        return 1

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |^\[[^\]]+\]:|\Z)",
                      changelog, re.M | re.S)
    if not match or not match.group(1).strip():
        print(f"CHANGELOG.md has no section for [{version}].", file=sys.stderr)
        return 1

    sys.stdout.write(match.group(1).strip() + "\n\n" + DOWNLOADS.format(v=version, repo=REPO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
