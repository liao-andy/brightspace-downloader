import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from brightspace_downloader.content import (
    build_tree,
    file_name_from_url,
    iter_files,
    sanitize_name,
)
from tests.sample_toc import SAMPLE_TOC


@pytest.mark.parametrize("raw,expected", [
    ("Lecture 1 - Introduction.pdf", "Lecture 1 - Introduction.pdf"),
    ("Slides: Agility?.pdf", "Slides - Agility.pdf"),
    ("a/b\\c:d|e.pdf", "a-b-c-d-e.pdf"),
    ("bad<>*name", "bad___name"),
    ("trailing dots... ", "trailing dots"),
    ("   ", "Untitled"),
])
def test_sanitize_name(raw, expected):
    assert sanitize_name(raw) == expected


def test_sanitize_reserved_and_length():
    assert sanitize_name("CON").startswith("_")
    assert sanitize_name("con.txt").startswith("_")
    long = "x" * 400 + ".pdf"
    out = sanitize_name(long)
    assert len(out) <= 150 and out.endswith(".pdf")


@pytest.mark.parametrize("url,expected", [
    ("/content/enforced/844457-CSE2115+2026+1/Lecture 1 - Introduction.pdf", "Lecture 1 - Introduction.pdf"),
    ("/content/enforced/1/code.zip", "code.zip"),
    ("https://host/path/My%20File.pdf", "My File.pdf"),
    ("/content/enforced/1/a+b c.pdf", "a+b c.pdf"),
])
def test_file_name_from_url(url, expected):
    assert file_name_from_url(url) == expected


def test_build_tree_counts_and_skips():
    tree = build_tree(SAMPLE_TOC)
    assert len(tree.files) == 7
    assert tree.skipped == {"link": 2, "media": 1, "broken": 1}


def test_build_tree_prunes_empty_modules():
    tree = build_tree(SAMPLE_TOC)
    top_names = [n["name"] for n in tree.nodes]
    assert top_names == ["Software Engineering Methods (SEM)"]
    # "Course Information" (only a link) and "Empty Module" must not appear.
    assert "Course Information" not in top_names
    assert "Empty Module" not in top_names


def test_build_tree_sem_example_path():
    """The exact mapping the user described."""
    tree = build_tree(SAMPLE_TOC)
    paths = {e.rel_path for e in tree.files.values()}
    assert "Software Engineering Methods (SEM)/Week 1/Lecture 1 - Introduction.pdf" in paths


def test_build_tree_orders_by_sortorder():
    tree = build_tree(SAMPLE_TOC)
    week1 = None
    for top in tree.nodes:
        for child in top["children"]:
            if child.get("name") == "Week 1":
                week1 = child
    assert week1 is not None
    file_names = [c["name"] for c in week1["children"] if c["type"] == "file"]
    # Reading Material (SortOrder 1) comes before Lecture 1.1 (2) and Lecture 1.2 (3)
    assert file_names.index("Reading Material - Copy.html") < file_names.index("Lecture 1 - Introduction.pdf")
    assert file_names.index("Lecture 1 - Introduction.pdf") < file_names.index("Slides - Agility.pdf")


def test_build_tree_dedupes_filenames():
    tree = build_tree(SAMPLE_TOC)
    names_in_week2 = sorted(
        e.name for e in tree.files.values() if e.folder[-1] == "Week 2"
    )
    assert "notes.pdf" in names_in_week2
    assert "notes (2).pdf" in names_in_week2


def test_iter_files_matches_file_map():
    tree = build_tree(SAMPLE_TOC)
    ids_from_nodes = {n["id"] for n in iter_files(tree.nodes)}
    assert ids_from_nodes == set(tree.files.keys())
