"""Turn a Brightspace content table of contents into a downloadable folder/file tree."""

from __future__ import annotations

import os
import re
import unicodedata
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)
}
MAX_COMPONENT_LENGTH = 150


def sanitize_name(name: str, fallback: str = "Untitled", max_length: int = MAX_COMPONENT_LENGTH) -> str:
    """Make a single path component that is valid on Windows, macOS and Linux."""
    text = unicodedata.normalize("NFC", str(name or ""))
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = text.replace(": ", " - ")
    text = re.sub(r"[:/\\|]", "-", text)
    text = text.replace('"', "'").replace("?", "")
    text = re.sub(r"[<>*]", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.rstrip(". ")  # Windows silently drops trailing dots and spaces
    if not text:
        text = fallback
    if text.split(".")[0].upper() in _RESERVED_NAMES:
        text = "_" + text
    if len(text) > max_length:
        stem, ext = os.path.splitext(text)
        if 1 < len(ext) <= 12:
            text = stem[: max_length - len(ext)].rstrip(". ") + ext
        else:
            text = text[:max_length].rstrip(". ")
    return text


def file_name_from_url(url: str) -> str:
    """Original file name of a File topic, e.g. '/content/enforced/123-ABC/Lecture 1.pdf' -> 'Lecture 1.pdf'.

    Brightspace returns these paths unencoded (spaces, '+', '#' are literal), so only full URLs
    are parsed; plain paths are split on '/' as-is.
    """
    path = url or ""
    if re.match(r"^[a-z][a-z0-9+.-]*://", path, re.I):
        path = urllib.parse.urlsplit(path).path
    name = path.rstrip("/").rsplit("/", 1)[-1]
    if re.search(r"%[0-9A-Fa-f]{2}", name) and " " not in name:
        name = urllib.parse.unquote(name)
    return name


def _split_ext(name: str) -> tuple[str, str]:
    stem, ext = os.path.splitext(name)
    if not stem:  # dotfiles like ".gitignore"
        return name, ""
    return stem, ext


@dataclass
class FileEntry:
    topic_id: int
    title: str
    name: str
    folder: tuple  # sanitized folder names from the content root
    url: str = ""

    @property
    def rel_parts(self) -> tuple:
        return tuple(self.folder) + (self.name,)

    @property
    def rel_path(self) -> str:
        return "/".join(self.rel_parts)


@dataclass
class ContentTree:
    nodes: list = field(default_factory=list)  # JSON-ready tree for the UI
    files: dict = field(default_factory=dict)  # topic_id -> FileEntry (download order = insertion)
    skipped: dict = field(default_factory=dict)  # kind -> count of items that can't be downloaded

    def to_json(self) -> dict:
        return {"nodes": self.nodes, "fileCount": len(self.files), "skipped": self.skipped}


def classify_topic(topic: dict) -> str:
    """'file' if downloadable, otherwise the reason it is skipped."""
    type_id = str(topic.get("TypeIdentifier") or "")
    if type_id.lower() == "file":
        if not topic.get("Url"):
            return "broken"
        if topic.get("IsBroken"):
            return "broken"
        return "file"
    if type_id == "ContentService":
        return "media"
    if type_id.lower() == "link":
        return "link"
    return "other"


def _ordered_children(module: dict) -> list:
    """Topics and sub-modules interleaved in the order Brightspace displays them."""
    items = [("module", m) for m in module.get("Modules") or []]
    items += [("topic", t) for t in module.get("Topics") or []]
    # Python's sort is stable, so items without SortOrder keep the API order.
    return sorted(items, key=lambda kv: _sort_key(kv[1]))


class _NameAllocator:
    """Gives every file a unique name per directory (case-insensitively, like Windows/macOS)."""

    def __init__(self) -> None:
        self._used: dict = {}

    def reserve(self, folder: tuple, name: str) -> None:
        self._used.setdefault(tuple(n.lower() for n in folder), set()).add(name.lower())

    def allocate(self, folder: tuple, name: str) -> str:
        used = self._used.setdefault(tuple(n.lower() for n in folder), set())
        candidate = name
        stem, ext = _split_ext(name)
        counter = 2
        while candidate.lower() in used:
            candidate = f"{stem} ({counter}){ext}"
            counter += 1
        used.add(candidate.lower())
        return candidate


def _sort_key(item: dict) -> float:
    value = item.get("SortOrder")
    return value if isinstance(value, (int, float)) else 0


def build_tree(toc: dict) -> ContentTree:
    """Map the TOC to folders (modules) and files (File topics).

    Folder names come from module titles, file names from the uploaded file's original name
    (the topic URL), e.g. topic "Lecture 1.1 - Introduction and Course Organisation" in module
    "Software Engineering Methods (SEM)" > "Week 1" becomes
    "Software Engineering Methods (SEM)/Week 1/Lecture 1 - Introduction.pdf".
    """
    tree = ContentTree()
    skipped: Counter = Counter()
    names = _NameAllocator()

    def reserve_folder_names(module_list: list, folder: tuple) -> None:
        for module in module_list:
            names.reserve(folder, sanitize_name(module.get("Title"), "Untitled module"))

    def add_file(topic: dict, folder: tuple) -> dict | None:
        category = classify_topic(topic)
        if category != "file":
            skipped[category] += 1
            return None
        try:
            topic_id = int(topic.get("TopicId") or topic.get("Identifier"))
        except (TypeError, ValueError):
            skipped["other"] += 1
            return None
        if topic_id in tree.files:
            return None
        title = str(topic.get("Title") or "").strip()
        original = file_name_from_url(topic.get("Url") or "")
        if not _split_ext(original)[0] or original.startswith("."):
            original = (title or f"File {topic_id}") + _split_ext(original)[1]
        file_name = names.allocate(folder, sanitize_name(original, f"File {topic_id}"))
        entry = FileEntry(topic_id=topic_id, title=title, name=file_name, folder=folder,
                          url=topic.get("Url") or "")
        tree.files[topic_id] = entry
        return {"type": "file", "id": topic_id, "name": file_name, "title": title,
                "path": entry.rel_path}

    def walk(module: dict, parent: tuple) -> dict | None:
        title = str(module.get("Title") or "").strip() or "Untitled module"
        folder_name = sanitize_name(title, "Untitled module")
        path = parent + (folder_name,)
        reserve_folder_names(module.get("Modules") or [], path)
        children = []
        for kind, item in _ordered_children(module):
            node = walk(item, path) if kind == "module" else add_file(item, path)
            if node:
                children.append(node)
        if not children:
            return None  # nothing downloadable inside
        return {"type": "folder", "id": f"m{module.get('ModuleId', id(module))}",
                "name": folder_name, "title": title, "children": children}

    top_modules = toc.get("Modules") or []
    reserve_folder_names(top_modules, ())
    for module in sorted(top_modules, key=_sort_key):
        node = walk(module, ())
        if node:
            tree.nodes.append(node)
    for topic in sorted(toc.get("Topics") or [], key=_sort_key):  # rare: topics in the root
        node = add_file(topic, ())
        if node:
            tree.nodes.append(node)
    tree.skipped = dict(skipped)
    return tree


def describe_skipped(skipped: dict) -> str:
    labels = {
        "link": ("web link", "web links"),
        "media": ("embedded video", "embedded videos"),
        "broken": ("missing file", "missing files"),
        "other": ("other item", "other items"),
    }
    parts = []
    for key in ("link", "media", "broken", "other"):
        count = skipped.get(key, 0)
        if count:
            singular, plural = labels[key]
            parts.append(f"{count} {singular if count == 1 else plural}")
    return ", ".join(parts)


def iter_files(nodes: list) -> Any:
    for node in nodes:
        if node["type"] == "file":
            yield node
        else:
            yield from iter_files(node["children"])
