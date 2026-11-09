"""Optional convenience: read the session cookies your installed browser already holds.

This is a thin wrapper around the third-party ``browser_cookie3`` package (an optional
dependency). It is **not** bundled and no decryption is implemented here - if the package is
not installed the app simply hides this option and offers the login window or cookies.txt
import instead. Whatever is read is immediately filtered to the single Brightspace host the
user entered, so only that site's cookies ever leave the browser.
"""

from __future__ import annotations

from . import CookieImportError, filter_for_host

# name shown in the UI -> browser_cookie3 loader attribute
SUPPORTED_BROWSERS = {
    "chrome": "chrome",
    "edge": "edge",
    "firefox": "firefox",
    "brave": "brave",
    "chromium": "chromium",
    "opera": "opera",
    "vivaldi": "vivaldi",
}


def is_available() -> bool:
    try:
        import browser_cookie3  # noqa: F401
    except Exception:
        return False
    return True


def available_browsers() -> list:
    try:
        import browser_cookie3
    except Exception:
        return []
    return [name for name, attr in SUPPORTED_BROWSERS.items() if hasattr(browser_cookie3, attr)]


def read_cookies(browser: str, host: str) -> list:
    """Return the cookies ``browser`` holds for ``host`` (and its parent domain)."""
    try:
        import browser_cookie3
    except Exception as exc:  # pragma: no cover - exercised only without the package
        raise CookieImportError(
            "Reading cookies from an installed browser needs the optional 'browser_cookie3' "
            "package. Install it with 'pip install browser_cookie3', or use the login window "
            "or a cookies.txt file instead."
        ) from exc

    loader = SUPPORTED_BROWSERS.get(browser)
    if not loader or not hasattr(browser_cookie3, loader):
        raise CookieImportError(f"Reading cookies from '{browser}' is not supported.")

    # Restrict to the Brightspace registrable domain so we never pull unrelated sites' cookies.
    labels = host.split(".")
    domain = ".".join(labels[-2:]) if len(labels) >= 2 else host
    try:
        jar = getattr(browser_cookie3, loader)(domain_name=domain)
    except Exception as exc:
        raise CookieImportError(_friendly_error(browser, exc)) from exc

    cookies = [
        {
            "name": c.name,
            "value": c.value or "",
            "domain": c.domain,
            "path": c.path or "/",
            "secure": bool(getattr(c, "secure", False)),
            "httponly": bool(c._rest.get("HTTPOnly", c._rest.get("HttpOnly", False)))
            if getattr(c, "_rest", None) else False,
        }
        for c in jar
    ]
    result = filter_for_host(cookies, host)
    if not result:
        raise CookieImportError(
            f"No {host} cookies were found in {browser.title()}. Open {host} in {browser.title()} "
            "and sign in first, then try again - or use the login window."
        )
    return result


def _friendly_error(browser: str, exc: Exception) -> str:
    text = str(exc).lower()
    if "permission" in text or "locked" in text or "being used" in text:
        return (
            f"Could not read {browser.title()}'s cookies - it may be open. Close {browser.title()} "
            "completely and try again, or use the login window instead."
        )
    return (
        f"Could not read cookies from {browser.title()} ({exc}). Try the login window or a "
        "cookies.txt file instead."
    )
