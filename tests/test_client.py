import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from brightspace_downloader.client import (
    BrightspaceClient,
    HttpError,
    NotLoggedIn,
    normalize_base_url,
)
from tests.sample_toc import FILE_BYTES


@pytest.mark.parametrize("raw,expected", [
    ("brightspace.tudelft.nl", "https://brightspace.tudelft.nl"),
    ("https://brightspace.tudelft.nl/d2l/home", "https://brightspace.tudelft.nl"),
    ("HTTP://Example.COM:8443/x", "http://example.com:8443"),
])
def test_normalize_base_url(raw, expected):
    assert normalize_base_url(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", "ftp://x", "not a url", "http://"])
def test_normalize_base_url_rejects(bad):
    with pytest.raises(ValueError):
        normalize_base_url(bad)


def test_probe_and_versions(client):
    client.probe()
    assert client.lp_version == "1.64"
    assert client.le_version == "1.100"


def test_whoami(client):
    user = client.whoami()
    assert user["Identifier"] == "99"
    assert user["FirstName"] == "Robin"


def test_whoami_without_cookies(server):
    client = BrightspaceClient(server.base_url)  # no cookies
    assert client.is_logged_in() is False
    with pytest.raises(NotLoggedIn):
        client.whoami()


def test_whoami_after_expiry(client, server):
    assert client.is_logged_in() is True
    server.expire_session()
    assert client.is_logged_in() is False


def test_list_courses_pagination(client):
    courses = client.list_courses()
    ids = {c["id"] for c in courses}
    assert ids == {844457, 101, 202}
    by_id = {c["id"]: c for c in courses}
    assert by_id[844457]["pinned"] is True
    assert by_id[202]["active"] is False


def test_get_toc(client):
    toc = client.get_toc(844457)
    assert toc["Modules"][0]["Title"] == "Course Information"


def test_head_file_size(client):
    size = client.head_file_size(844457, 4775880)
    assert size == len(FILE_BYTES[4775880])


def test_open_file_streams_bytes(client):
    resp = client.open_file(844457, 4775881)
    try:
        data = resp.content
    finally:
        resp.close()
    assert data == FILE_BYTES[4775881]


def test_open_file_404_raises_http_error(client):
    with pytest.raises(HttpError) as excinfo:
        client.open_file(844457, 99999999)
    assert excinfo.value.status == 404


def test_http_error_message_includes_detail(client, server):
    server.expire_session()
    err = HttpError(403, "Forbidden", detail="Forbidden")
    assert "403" in str(err) and "Forbidden" in str(err)
