# Brightspace Downloader

A lightweight, cross-platform desktop app that **bulk-downloads the files from the Content
area of your D2L Brightspace courses**, keeping the module/sub-module structure as folders on
disk.

Pick a course, tick the files you want (everything is selected by default, like opening a
`.torrent` in qBittorrent), choose a destination folder, and download. Folders mirror the
course's Content tree exactly, inside the folder you choose:

> With the destination set to `C:\Users\you\Documents\Brightspace\SEM`, a topic laid out on
> Brightspace as **Software Engineering Methods (SEM) → Week 1 → "Lecture 1.1 – Introduction
> and Course Organisation"** is saved as
> `C:\Users\you\Documents\Brightspace\SEM\Software Engineering Methods (SEM)\Week 1\Lecture 1 - Introduction.pdf`
>
> (the module path follows the destination folder; the file keeps its original uploaded name).

<p align="center"><em>Login → Courses → File picker → Progress → “All done!”</em></p>

---

## Download

Grab the latest build for your system from the
**[Releases page](https://github.com/liao-andy/brightspace-downloader/releases/latest)** — no
Python needed.

| System | File | How to run |
| --- | --- | --- |
| **Windows 10/11** (x64) | `BrightspaceDownloader-<version>-windows-x64.exe` | Double-click it. |
| **macOS 11+** Apple Silicon | `BrightspaceDownloader-<version>-macos-arm64.zip` | Unzip, move the app to *Applications*, open it. |
| **macOS 11+** Intel | `BrightspaceDownloader-<version>-macos-x64.zip` | Same as above. |
| **Linux** (x64, glibc 2.35+) | `BrightspaceDownloader-<version>-linux-x64.tar.gz` | `tar xzf` it, then run `BrightspaceDownloader/BrightspaceDownloader`. |

The builds are not code-signed (that costs money), so your OS will be cautious the first time:

- **Windows SmartScreen** ("Windows protected your PC"): click **More info → Run anyway**.
- **macOS Gatekeeper** ("cannot be opened because the developer cannot be verified"): right-click
  the app → **Open** → **Open**. If macOS says the app "is damaged", remove the download
  quarantine flag once: `xattr -dr com.apple.quarantine /Applications/BrightspaceDownloader.app`
- `SHA256SUMS.txt` on each release lets you verify your download.

---

## Features

- **No admin approval or API key needed.** It talks to the same `/d2l/api/…` endpoints the
  Brightspace website uses, authenticated with your normal browser session — no Brightspace
  OAuth app registration required.
- **Three ways to sign in**, none of which ever show this app your password:
  1. **Login window** (recommended) — opens the genuine Brightspace / institution login page in
     an embedded window; you sign in as usual and the app keeps only the resulting session.
  2. **Import a `cookies.txt` / JSON** export from a browser extension.
  3. **Read cookies from an installed browser** (optional — needs `browser_cookie3`).
- **Session is re-checked on every launch** (Brightspace sessions expire after ~180 minutes),
  and if it has expired you’re taken straight back to the login screen.
- **qBittorrent-style file picker** with a checkbox tree, tri-state folders, select-all/clear,
  and a running "N of M files selected" count.
- **Preserves the full folder structure**; de-duplicates clashing filenames; makes names valid
  on Windows, macOS and Linux.
- **Robust downloads** — live progress bar + current file name, transfer speed, automatic
  retries on transient errors, clear **HTTP error messages** for anything that fails, and a
  per-file *skip / overwrite / keep-both* choice for files you already have.
- **"All done!"** dialog with **Show in File Explorer** (Finder / file manager on other OSes),
  then back to your course list to grab another one.

---

## Running from source

### Requirements

- **Python 3.9+**
- **A system webview** (used for the window and the embedded login):
  - **Windows 10/11** — the WebView2 runtime, which is already present on current Windows.
    (If missing: <https://developer.microsoft.com/microsoft-edge/webview2/>.)
  - **macOS** — WKWebView, built in.
  - **Linux** — GTK WebKit, e.g. Debian/Ubuntu:
    `sudo apt install python3-gi gir1.2-webkit2-4.1` (or the Qt backend with `pip install pyqt6 pyqt6-webengine`).

### Install

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

# Optional: enables "Use cookies from an installed browser"
pip install -r requirements-optional.txt
```

### Run

```bash
python run.py
```

(equivalently `python -m brightspace_downloader`.)

---

## How to use it

1. **Enter your Brightspace address** (e.g. `brightspace.tudelft.nl`) and click **Connect**.
2. **Sign in** with the **Log in with a window** button. The real Brightspace login opens
   (for TU Delft this redirects to `login.tudelft.nl` for your NetID and back). Once you’re in,
   the window closes itself and your courses load. *(Or import a `cookies.txt`, or read cookies
   from an installed browser.)*
3. **Pick a course** from the list.
4. **Choose the files** — the whole tree is selected by default; untick anything you don’t want.
5. **Set the destination folder** (type a path or **Browse…**).
6. **Download.** Watch the progress bar and current file; any failures show their HTTP error.
7. On **"All done!"**, click **Show in File Explorer** or **OK** to return to your courses.

### What gets downloaded

Everything that is a real **file** in the Content area (PDF, slides, docs, zips, images, …).
The app skips things that aren’t downloadable files: external **web links**, **embedded videos**
(Brightspace "ContentService" media, which aren’t plain files), and **broken** items. The file
picker tells you how many of each were skipped.

### If a file already exists

Chosen per download:

| Option | Behaviour |
| --- | --- |
| **Skip it (keep my copy)** *(default)* | Leaves existing files untouched — safe to re-run, keeps your annotations. |
| **Replace it** | Re-downloads and overwrites. |
| **Keep both** | Keeps the old file and saves the new one as `name (1).ext` — unless an identical-size copy already exists. |

---

## Privacy & where things are stored

- This app **never sees or stores your password.** With the login window you authenticate on the
  real institution pages; the app only reads the resulting **session cookies**, and only for the
  Brightspace host you entered.
- Your settings and the saved session are stored locally, in your user profile:
  - **Windows:** `%LOCALAPPDATA%\BrightspaceDownloader\`
  - **macOS:** `~/Library/Application Support/BrightspaceDownloader/`
  - **Linux:** `~/.config/brightspace-downloader/`
  The session file (`session.json`) holds cookies that grant access to your account — treat it
  like a password. Use **Log out** to delete it.

---

## Packaging a standalone app

```bash
pip install -r requirements.txt pyinstaller
# Linux only: the standalone build uses the self-contained Qt web engine
pip install "pywebview[qt]"

python packaging/build.py             # -> dist/
python packaging/build.py --release   # -> also a versioned archive in dist/release/
```

This bundles the UI and produces `BrightspaceDownloader.exe` (single file) on Windows,
`BrightspaceDownloader.app` on macOS, or a `BrightspaceDownloader/` folder on Linux, with the
app logo as its icon. PyInstaller can't cross-compile, so each OS is built on that OS.

### Releases

Releases are built by GitHub Actions ([`.github/workflows/build.yml`](.github/workflows/build.yml)).
Every push runs the tests on Windows, macOS and Linux. Pushing a version tag also builds the app
for Windows x64, macOS arm64/x64 and Linux x64, launches each build once as a smoke test
(`BSDL_SMOKE_TEST`), and publishes them on a GitHub release with notes from
[`CHANGELOG.md`](CHANGELOG.md):

1. Bump `__version__` in `brightspace_downloader/__init__.py` and add a section to `CHANGELOG.md`.
2. Commit, then tag and push: `git tag v1.2.3 && git push origin main v1.2.3`.

### App icon

The logo lives in `brightspace_downloader/assets/logo.svg`; the window/taskbar/dock icons are
generated from it (`icon.ico` for Windows, `icon.png` for Linux and the macOS dock,
`icon.icns` for the macOS bundle). After changing the logo, regenerate them:

```bash
pip install resvg-py pillow
python packaging/make_icons.py
```

---

## Development

```bash
pip install -r requirements.txt pytest
pytest
```

The tests run against a built-in **mock Brightspace server** (`tests/mock_server.py`) — no real
account or network needed — and cover the API client, the TOC→folder mapping, cookie parsing,
and the full download engine (structure, skip/overwrite/keep-both, retries, truncated
responses, cancellation and mid-download session expiry).

To preview the UI in a normal browser without signing in, serve the repo and open
`demo/index.html` (it runs the real `app.js` against canned data):

```bash
python -m http.server 8777
# then open http://127.0.0.1:8777/demo/index.html
```

### Project layout

```
brightspace_downloader/
  app.py            window + GUI loop
  api.py            the pywebview JS bridge (pywebview.api.*)
  client.py         Brightspace REST client (cookie-authenticated)
  content.py        TOC -> folder/file tree + name sanitising
  downloader.py     batch download engine (progress, retries, policies)
  login.py          embedded-login window + cookie capture
  cookies/          cookies.txt/JSON parsing + optional browser import
  settings.py       persisted settings & saved session
  paths.py          platform dirs + "show in file explorer"
  web/              the UI (index.html, app.css, app.js)
  assets/           logo.svg + generated app icons
tests/              pytest suite + mock Brightspace server
packaging/
  build.py          PyInstaller build (+ --release archives)
  make_icons.py     regenerates the icons from logo.svg
  smoke_test.py     launches a packaged build once (used by CI)
  release_notes.py  release notes from CHANGELOG.md (used by CI)
.github/workflows/build.yml   CI: tests, multi-platform builds, GitHub releases
```

---

## Troubleshooting

- **The login window doesn’t finish / keeps showing the login page.** Complete the full sign-in
  (including any two-factor step). The window closes automatically once a valid session is
  detected. If your institution blocks the embedded webview, sign in with your normal browser
  and use **Import a cookies.txt file** or **Use cookies from an installed browser** instead.
- **"Your session has expired."** Brightspace sessions last about 180 minutes. Just log in
  again; already-downloaded files are skipped if you re-run with the default *skip* policy.
- **A course shows no files.** Its Content area may contain only links or embedded videos, which
  aren’t downloadable files — the picker says how many were skipped.
- **Windows: nothing opens.** Ensure the WebView2 runtime is installed (see Requirements).
- **Linux (from source): "web engine not found".** Install the GTK WebKit packages (see
  Requirements) or the Qt backend.
- **Linux (release build) doesn't start.** Run it from a terminal to see the error. Missing
  system libraries can be installed with e.g.
  `sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libnss3 libegl1`.

## Notes

This tool uses Brightspace’s read-only REST endpoints with your own session to download content
you already have access to. Respect your institution’s acceptable-use policy and copyright on
course materials.

This is an independent, unofficial project. It is not affiliated with, endorsed by or supported
by D2L Corporation; "D2L" and "Brightspace" are trademarks of D2L Corporation.

## License

[MIT](LICENSE)
