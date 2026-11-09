"""Platform-specific locations and file-manager helpers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_DIR_NAME = "BrightspaceDownloader"


def app_data_dir() -> Path:
    """Directory for settings, the saved session and the embedded browser profile.

    Can be overridden with the BSDL_DATA_DIR environment variable (used by tests).
    """
    override = os.environ.get("BSDL_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / APP_DIR_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        path = Path(base) / "brightspace-downloader"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _windows_documents_dir() -> Path | None:
    """Real 'Documents' folder on Windows (respects OneDrive/folder redirection)."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        folder_id = GUID(
            0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7)
        )
        out = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        return None


def _linux_documents_dir() -> Path | None:
    try:
        result = subprocess.run(
            ["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=3
        )
        value = result.stdout.strip()
        if result.returncode == 0 and value and Path(value) != Path.home():
            return Path(value)
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def documents_dir() -> Path:
    found = None
    if sys.platform == "win32":
        found = _windows_documents_dir()
    elif sys.platform.startswith("linux"):
        found = _linux_documents_dir()
    if found and found.is_dir():
        return found
    candidate = Path.home() / "Documents"
    return candidate if candidate.is_dir() else Path.home()


def default_download_root() -> Path:
    return documents_dir() / "Brightspace"


def file_manager_name() -> str:
    if sys.platform == "win32":
        return "File Explorer"
    if sys.platform == "darwin":
        return "Finder"
    return "File Manager"


def reveal_folder(path: str | os.PathLike) -> None:
    """Open a folder in the platform's file manager."""
    folder = os.path.abspath(os.fspath(path))
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"Folder does not exist: {folder}")
    if sys.platform == "win32":
        os.startfile(folder)  # type: ignore[attr-defined]  # opens File Explorer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


def long_path(path: str | os.PathLike) -> str:
    """Return a path string usable for file operations even beyond Windows' 260-char limit."""
    text = os.path.abspath(os.fspath(path))
    if os.name != "nt" or text.startswith("\\\\?\\") or len(text) < 240:
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text
