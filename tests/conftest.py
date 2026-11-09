import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.mock_server import MockBrightspace  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_app_data(tmp_path, monkeypatch):
    """Keep settings/session writes inside the test's tmp dir."""
    monkeypatch.setenv("BSDL_DATA_DIR", str(tmp_path / "appdata"))
    yield


@pytest.fixture
def server():
    with MockBrightspace() as mock:
        yield mock


@pytest.fixture
def client(server):
    from brightspace_downloader.client import BrightspaceClient

    return BrightspaceClient(server.base_url, server.valid_cookies())
