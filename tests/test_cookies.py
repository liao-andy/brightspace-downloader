import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from brightspace_downloader.cookies import domain_matches, filter_for_host
from brightspace_downloader.cookies.netscape import (
    load_cookie_file,
    parse_cookie_text,
    parse_netscape,
)
from brightspace_downloader.cookies import CookieImportError


NETSCAPE_SAMPLE = """# Netscape HTTP Cookie File
# comment line
brightspace.tudelft.nl\tFALSE\t/\tTRUE\t1999999999\td2lSessionVal\tabc123
#HttpOnly_brightspace.tudelft.nl\tFALSE\t/d2l\tTRUE\t1999999999\td2lSecureSessionVal\tsecret
.tudelft.nl\tTRUE\t/\tFALSE\t0\tother\tvalue
"""

JSON_SAMPLE = """[
  {"name": "d2lSessionVal", "value": "abc123", "domain": "brightspace.tudelft.nl", "path": "/", "secure": true},
  {"name": "x", "value": "y", "domain": ".tudelft.nl", "path": "/", "httpOnly": true}
]"""


@pytest.mark.parametrize("domain,host,expected", [
    ("brightspace.tudelft.nl", "brightspace.tudelft.nl", True),
    (".tudelft.nl", "brightspace.tudelft.nl", True),
    ("tudelft.nl", "brightspace.tudelft.nl", True),
    ("example.com", "brightspace.tudelft.nl", False),
    ("eltudelft.nl", "brightspace.tudelft.nl", False),
])
def test_domain_matches(domain, host, expected):
    assert domain_matches(domain, host) is expected


def test_parse_netscape():
    cookies = parse_netscape(NETSCAPE_SAMPLE)
    names = {c["name"]: c for c in cookies}
    assert set(names) == {"d2lSessionVal", "d2lSecureSessionVal", "other"}
    assert names["d2lSessionVal"]["value"] == "abc123"
    assert names["d2lSessionVal"]["secure"] is True
    assert names["d2lSecureSessionVal"]["httponly"] is True


def test_parse_json():
    cookies = parse_cookie_text(JSON_SAMPLE)
    names = {c["name"]: c for c in cookies}
    assert names["d2lSessionVal"]["value"] == "abc123"
    assert names["x"]["httponly"] is True


def test_filter_for_host():
    cookies = parse_netscape(NETSCAPE_SAMPLE)
    kept = filter_for_host(cookies, "brightspace.tudelft.nl")
    assert len(kept) == 3  # all three match tudelft.nl / brightspace.tudelft.nl
    kept_other = filter_for_host(cookies, "example.com")
    assert kept_other == []


def test_load_cookie_file_roundtrip(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(NETSCAPE_SAMPLE, encoding="utf-8")
    cookies = load_cookie_file(str(path))
    assert any(c["name"] == "d2lSessionVal" for c in cookies)


def test_load_cookie_file_json(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text(JSON_SAMPLE, encoding="utf-8")
    cookies = load_cookie_file(str(path))
    assert any(c["name"] == "d2lSessionVal" for c in cookies)


def test_load_cookie_file_missing(tmp_path):
    with pytest.raises(CookieImportError):
        load_cookie_file(str(tmp_path / "nope.txt"))


def test_load_cookie_file_empty(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("# just a comment\n", encoding="utf-8")
    with pytest.raises(CookieImportError):
        load_cookie_file(str(path))
