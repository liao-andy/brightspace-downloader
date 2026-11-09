import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from brightspace_downloader import downloader as dl
from brightspace_downloader.content import FileEntry, build_tree
from tests.sample_toc import FILE_BYTES, SAMPLE_TOC


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr(dl, "RETRY_DELAYS", (0, 0, 0))


def collect(on_events):
    def handler(name, payload):
        on_events.append((name, payload))
    return handler


def run_job(client, entries, dest, **kw):
    events = []
    job = dl.DownloadJob(client, 844457, entries, dest, on_event=collect(events), **kw)
    job.run()  # synchronous for deterministic tests
    return job.summary, events


def sem_entries():
    return list(build_tree(SAMPLE_TOC).files.values())


def test_full_download_preserves_structure(client, tmp_path):
    entries = sem_entries()
    summary, events = run_job(client, entries, tmp_path)

    assert summary.downloaded == len(entries)
    assert summary.failed == []
    lecture = tmp_path / "Software Engineering Methods (SEM)" / "Week 1" / "Lecture 1 - Introduction.pdf"
    assert lecture.is_file()
    assert lecture.read_bytes() == FILE_BYTES[4775880]
    # duplicate names were separated
    assert (tmp_path / "Software Engineering Methods (SEM)" / "Week 2" / "notes.pdf").is_file()
    assert (tmp_path / "Software Engineering Methods (SEM)" / "Week 2" / "notes (2).pdf").is_file()
    # a "done" event is emitted
    assert any(name == "download:done" for name, _ in events)


def test_progress_events_increase(client, tmp_path):
    summary, events = run_job(client, sem_entries(), tmp_path)
    fractions = [p["fraction"] for name, p in events if name == "download:progress"]
    assert fractions, "expected progress events"
    assert fractions == sorted(fractions)
    assert fractions[-1] == pytest.approx(1.0, abs=0.001) or summary.downloaded == len(sem_entries())


def test_skip_policy_second_run(client, tmp_path):
    entries = sem_entries()
    run_job(client, entries, tmp_path)
    summary, _ = run_job(client, entries, tmp_path, existing_policy="skip")
    assert summary.skipped == len(entries)
    assert summary.downloaded == 0


def test_overwrite_policy(client, tmp_path):
    entries = sem_entries()
    run_job(client, entries, tmp_path)
    lecture = tmp_path / "Software Engineering Methods (SEM)" / "Week 1" / "Lecture 1 - Introduction.pdf"
    lecture.write_bytes(b"tampered")
    summary, _ = run_job(client, entries, tmp_path, existing_policy="overwrite")
    assert summary.downloaded == len(entries)
    assert lecture.read_bytes() == FILE_BYTES[4775880]


def test_keep_both_skips_identical_then_duplicates_changed(client, tmp_path):
    entries = sem_entries()
    run_job(client, entries, tmp_path)
    # identical content already on disk -> keep_both should skip everything
    summary, _ = run_job(client, entries, tmp_path, existing_policy="keep_both")
    assert summary.skipped == len(entries)

    # change one file's size on disk -> keep_both makes a numbered copy for it
    lecture = tmp_path / "Software Engineering Methods (SEM)" / "Week 1" / "Lecture 1 - Introduction.pdf"
    lecture.write_bytes(b"different size now")
    summary2, _ = run_job(client, entries, tmp_path, existing_policy="keep_both")
    assert summary2.downloaded == 1
    assert (lecture.parent / "Lecture 1 - Introduction (1).pdf").is_file()


def test_failure_is_reported_and_continues(client, tmp_path):
    entries = [
        FileEntry(4775880, "ok", "ok.pdf", ("f",), "/x"),
        FileEntry(99999999, "missing", "missing.pdf", ("f",), "/y"),  # 404
        FileEntry(4775881, "ok2", "ok2.html", ("f",), "/z"),
    ]
    summary, events = run_job(client, entries, tmp_path)
    assert summary.downloaded == 2
    assert len(summary.failed) == 1
    assert summary.failed[0]["name"] == "missing.pdf"
    assert "404" in summary.failed[0]["error"]
    assert any(name == "download:error" for name, _ in events)


def test_cancel_before_start(client, tmp_path):
    entries = sem_entries()
    events = []
    job = dl.DownloadJob(client, 844457, entries, tmp_path, on_event=collect(events))
    job.cancel()
    job.run()
    assert job.summary.cancelled is True
    assert job.summary.downloaded == 0
    assert job.summary.not_attempted == len(entries)


def test_flaky_file_retries_then_succeeds(client, tmp_path):
    entries = [FileEntry(7000001, "flaky", "flaky.bin", ("f",), "/x")]
    summary, _ = run_job(client, entries, tmp_path)
    assert summary.downloaded == 1
    assert (tmp_path / "f" / "flaky.bin").read_bytes() == FILE_BYTES[7000001]


def test_truncated_download_fails(client, tmp_path):
    entries = [FileEntry(7000002, "trunc", "trunc.bin", ("f",), "/x")]
    summary, _ = run_job(client, entries, tmp_path)
    assert summary.downloaded == 0
    assert len(summary.failed) == 1
    # the incomplete .part file must not be left behind
    assert not (tmp_path / "f" / "trunc.bin").exists()
    assert not (tmp_path / "f" / "trunc.bin.part").exists()


def test_session_expiry_mid_download_aborts(client, server, tmp_path):
    entries = [
        FileEntry(4775880, "a", "a.pdf", ("f",), "/x"),
        FileEntry(4775881, "b", "b.html", ("f",), "/y"),
        FileEntry(4775882, "c", "c.pdf", ("f",), "/z"),
    ]

    def expire_after_first(name, payload):
        # When the 2nd file is about to start (1-based index == 2), kill the session.
        if name == "download:progress" and payload.get("index", 0) >= 2:
            server.expire_session()

    job = dl.DownloadJob(client, 844457, entries, tmp_path, on_event=expire_after_first)
    job.run()
    assert job.summary.aborted_reason
    assert "expired" in job.summary.aborted_reason.lower()
    assert job.summary.downloaded >= 1
