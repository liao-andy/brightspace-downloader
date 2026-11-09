# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-09

First public release.

### Added

- Bulk-download every file in a Brightspace course's Content area, recreating the module
  folder structure inside the folder you choose.
- Sign in with an embedded login window (your institution's real login page, e.g. NetID),
  by importing a `cookies.txt`/JSON export, or (optionally) from an installed browser. The app
  never sees your password and needs no Brightspace OAuth app or admin approval.
- Saved sessions are re-checked on launch (Brightspace sessions last about 180 minutes).
- Course list with a qBittorrent-style checkbox tree of folders and files, all selected by
  default.
- Choose what happens to files you already have: skip, replace or keep both.
- Progress bar with the current file name and speed, automatic retries on transient errors, and
  clear HTTP error messages for anything that fails.
- "All done!" dialog with a button to open the download folder.
- Builds for Windows (x64), macOS (Apple Silicon and Intel) and Linux (x64).

[1.0.0]: https://github.com/liao-andy/brightspace-downloader/releases/tag/v1.0.0
