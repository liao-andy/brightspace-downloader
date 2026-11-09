"""Create the desktop window and start the GUI loop."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import webview

from . import APP_TITLE
from .api import Api
from .paths import app_data_dir

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
APP_USER_MODEL_ID = "BrightspaceDownloader.App"


def _icon_path() -> str | None:
    """The window/taskbar/dock icon: .ico for WinForms, .png for Cocoa, GTK and Qt."""
    icon = ASSETS_DIR / ("icon.ico" if sys.platform == "win32" else "icon.png")
    return str(icon) if icon.is_file() else None


def _linux_gui() -> str | None:
    """Pick the Linux web engine up front instead of letting pywebview try GTK first.

    The standalone Linux build ships Qt only; letting pywebview attempt GTK there logs a scary
    "GTK cannot be loaded" traceback before it falls back. From source, GTK stays the default.
    """
    if not sys.platform.startswith("linux"):
        return None
    import importlib.util

    if importlib.util.find_spec("gi") is None and importlib.util.find_spec("qtpy") is not None:
        return "qt"
    return None


def _set_windows_app_id() -> None:
    """Give the process its own taskbar identity on Windows.

    Without this, running via ``python run.py`` groups the window under python.exe and the
    taskbar shows Python's icon instead of ours.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:  # pragma: no cover - cosmetic only
        log.debug("could not set AppUserModelID", exc_info=True)


def _configure_logging() -> None:
    level = logging.DEBUG if os.environ.get("BSDL_DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _maybe_install_smoke_test(window) -> None:
    """Release-build self check, used by CI: ``BSDL_SMOKE_TEST=<file>``.

    Once the UI has loaded, writes what the page rendered to <file> and closes the app. This
    proves a packaged build can open its window, start the web engine and render the bundled UI.
    """
    marker = os.environ.get("BSDL_SMOKE_TEST")
    if not marker:
        return

    def on_loaded():
        try:
            brand = window.evaluate_js("document.querySelector('.brand-name').textContent")
            logo = window.evaluate_js(
                "(() => { const i = document.querySelector('img.brand-mark');"
                " return !!(i && i.complete && i.naturalWidth > 0); })()")
            Path(marker).write_text(f"brand={brand}\nlogo={logo}\nicon={_icon_path()}\n",
                                    encoding="utf-8")
        finally:
            window.destroy()

    window.events.loaded += on_loaded


def main() -> int:
    _configure_logging()
    index = WEB_DIR / "index.html"
    if not index.exists():
        print(f"UI files are missing: {index}", file=sys.stderr)
        return 1

    _set_windows_app_id()
    api = Api()
    window = webview.create_window(
        APP_TITLE,
        url=str(index),
        js_api=api,
        width=1120,
        height=820,
        min_size=(860, 620),
        background_color="#0f172a",
        text_select=False,
    )
    api.bind_window(window)
    _maybe_install_smoke_test(window)

    debug = bool(os.environ.get("BSDL_DEBUG"))
    # private_mode=False + a storage path keeps the embedded-login cookies between runs, so a
    # still-valid Brightspace session (they last ~180 min) does not force a fresh login.
    storage = app_data_dir() / "webview"
    storage.mkdir(parents=True, exist_ok=True)
    webview.start(gui=_linux_gui(), debug=debug, private_mode=False, storage_path=str(storage),
                  icon=_icon_path())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
