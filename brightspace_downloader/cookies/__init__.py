"""Ways to obtain Brightspace session cookies without typing a password into this app."""

from __future__ import annotations


class CookieImportError(Exception):
    """A user-facing error while importing cookies."""


def domain_matches(cookie_domain: str, host: str) -> bool:
    """True if a cookie set for cookie_domain would be sent to host."""
    domain = (cookie_domain or "").strip().lstrip(".").lower()
    host = (host or "").lower()
    return bool(domain) and (host == domain or host.endswith("." + domain))


def filter_for_host(cookies: list, host: str) -> list:
    return [c for c in cookies if c.get("name") and domain_matches(c.get("domain", ""), host)]
