#!/usr/bin/env python3
"""Build a standalone desktop app with PyInstaller.

Usage:
    pip install -r requirements.txt pyinstaller      # Linux: also  pip install "pywebview[qt]"
    python packaging/build.py             # build into dist/
    python packaging/build.py --release   # ...and package it into dist/release/ for publishing

Output in dist/:
    * Windows: BrightspaceDownloader.exe            (single file, no console window)
    * macOS:   BrightspaceDownloader.app            (app bundle)
    * Linux:   BrightspaceDownloader/BrightspaceDownloader   (folder; starts much faster than a
               single file because the Qt web engine is large)

With --release, dist/release/ gets one versioned archive per platform, e.g.
    BrightspaceDownloader-1.0.0-windows-x64.exe
    BrightspaceDownloader-1.0.0-macos-arm64.zip
    BrightspaceDownloader-1.0.0-linux-x64.tar.gz
"""

from __future__ import annotations

import argparse
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "brightspace_downloader"
WEB = PKG / "web"
ASSETS = PKG / "assets"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
NAME = "BrightspaceDownloader"
TITLE = "Brightspace Downloader"
BUNDLE_ID = "io.github.liao-andy.brightspace-downloader"


def app_version() -> str:
    text = (PKG / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not match:
        raise SystemExit("Could not find __version__ in brightspace_downloader/__init__.py")
    return match.group(1)


def platform_tag() -> str:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{arch}"


def windows_version_file(version: str) -> Path:
    """A version resource so Explorer > Properties > Details shows the app name and version."""
    nums = [int(p) for p in re.findall(r"\d+", version)[:4]]
    nums += [0] * (4 - len(nums))
    tup = tuple(nums)
    BUILD.mkdir(exist_ok=True)
    path = BUILD / "version_info.txt"
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('ProductName', '{TITLE}'),
      StringStruct('FileDescription', '{TITLE}'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('OriginalFilename', '{NAME}.exe'),
      StringStruct('InternalName', '{NAME}'),
      StringStruct('LegalCopyright', 'MIT License'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
    return path


def pyinstaller_args(version: str) -> list[str]:
    sep = ";" if sys.platform == "win32" else ":"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", NAME,
        "--windowed",  # no console window; on macOS this produces the .app bundle
        "--add-data", f"{WEB}{sep}brightspace_downloader/web",
        # Runtime window/taskbar/dock icons (see app._icon_path).
        "--add-data", f"{ASSETS}{sep}brightspace_downloader/assets",
    ]
    if sys.platform == "win32":
        args += ["--onefile", "--icon", str(ASSETS / "icon.ico"),
                 "--version-file", str(windows_version_file(version))]
    elif sys.platform == "darwin":
        args += ["--onedir", "--icon", str(ASSETS / "icon.icns"),
                 "--osx-bundle-identifier", BUNDLE_ID]
    else:
        # The Linux build uses pywebview's Qt backend (self-contained QtWebEngine). GTK would
        # need the user's exact system WebKitGTK, which a bundled app cannot rely on.
        args += ["--onedir", "--exclude-module", "gi"]
    args.append(str(ROOT / "run.py"))
    return args


def finish_macos_bundle(version: str) -> None:
    """Stamp the version into Info.plist, then re-sign (ad hoc) since editing it breaks the seal."""
    app = DIST / f"{NAME}.app"
    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as f:
        info = plistlib.load(f)
    info.update({
        "CFBundleDisplayName": TITLE,
        "CFBundleName": TITLE,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": info.get("LSMinimumSystemVersion", "11.0"),
    })
    with plist_path.open("wb") as f:
        plistlib.dump(info, f)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)


def package_release(version: str) -> Path:
    out_dir = DIST / "release"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{NAME}-{version}-{platform_tag()}"
    if sys.platform == "win32":
        out = out_dir / f"{stem}.exe"
        shutil.copy2(DIST / f"{NAME}.exe", out)
    elif sys.platform == "darwin":
        out = out_dir / f"{stem}.zip"
        # ditto keeps the bundle's symlinks, permissions and code signature intact.
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(DIST / f"{NAME}.app"), str(out)], check=True)
    else:
        out = out_dir / f"{stem}.tar.gz"
        with tarfile.open(out, "w:gz") as tar:
            tar.add(DIST / NAME, arcname=NAME)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", action="store_true", help="also package a versioned archive into dist/release/")
    opts = parser.parse_args()

    version = app_version()
    args = pyinstaller_args(version)
    print("Running:", " ".join(args), flush=True)
    try:
        subprocess.run(args, cwd=str(ROOT), check=True)
    except FileNotFoundError:
        print("PyInstaller is not installed. Run:  pip install pyinstaller", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        return exc.returncode

    if sys.platform == "darwin":
        finish_macos_bundle(version)
    print(f"\nBuilt {TITLE} {version} in: {DIST}")
    if opts.release:
        print(f"Release archive: {package_release(version)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
