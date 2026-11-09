"""Tests for the JS-bridge API layer (without a real webview window)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from brightspace_downloader.api import Api


@pytest.fixture
def api(server, monkeypatch, tmp_path):
    monkeypatch.setenv("BSDL_DATA_DIR", str(tmp_path / "appdata2"))
    a = Api()
    # No window: events become no-ops, dialogs are not used in these tests.
    return a


def login(api, server):
    result = api.import_cookie_file  # ensure attribute exists
    assert callable(result)
    # Authenticate directly with the mock's valid cookies.
    res = api._login_with_cookies(server.base_url, server.valid_cookies())
    assert res["ok"], res
    return res


def test_set_base_url_probes(api, server):
    res = api.set_base_url(server.base_url)
    assert res["ok"] is True
    assert res["host"] == "127.0.0.1"


def test_login_and_list_courses(api, server):
    api.settings.base_url = server.base_url
    login(api, server)
    res = api.list_courses()
    assert res["ok"] is True
    names = [c["name"] for c in res["courses"]]
    assert "Software Engineering Methods (SEM)" in names
    # pinned course should sort first
    assert res["courses"][0]["pinned"] is True


def test_load_content_returns_tree(api, server):
    api.settings.base_url = server.base_url
    login(api, server)
    res = api.load_content(844457)
    assert res["ok"] is True
    assert res["fileCount"] == 7
    assert res["skippedText"]
    assert res["nodes"][0]["name"] == "Software Engineering Methods (SEM)"


def test_suggested_dir_defaults_to_course_folder(api, server):
    api.settings.base_url = server.base_url
    login(api, server)
    api.list_courses()  # populates the course-name cache
    res = api.load_content(844457)
    assert res["defaultDir"].replace("\\", "/").endswith("Brightspace/Software Engineering Methods (SEM)")


def test_list_courses_requires_login(api, server):
    api.settings.base_url = server.base_url
    res = api.list_courses()
    assert res["ok"] is False
    assert "not logged in" in res["error"].lower()


def test_resume_session_after_expiry(api, server):
    api.settings.base_url = server.base_url
    login(api, server)  # saves session
    server.expire_session()
    fresh = Api()
    fresh.sessions = api.sessions
    res = fresh.resume_session()
    assert res["ok"] is False
    assert res.get("expired") is True


def test_start_download_runs(api, server, tmp_path):
    api.settings.base_url = server.base_url
    login(api, server)
    api.load_content(844457)
    tree = api._trees[844457]
    ids = list(tree.files.keys())
    dest = tmp_path / "dl"
    res = api.start_download(844457, ids, str(dest), "Software Engineering Methods (SEM)", "skip")
    assert res["ok"] is True
    api._job.join(timeout=30)
    assert not api._job.is_alive()
    assert api._job.summary.downloaded == len(ids)
    # The chosen folder directly contains the module tree (no extra course-name folder).
    expected = dest / "Software Engineering Methods (SEM)" / "Week 1" / "Lecture 1 - Introduction.pdf"
    assert expected.is_file()
    assert res["dest"] == str(dest)
