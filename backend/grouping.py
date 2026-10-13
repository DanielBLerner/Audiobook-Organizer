"""Folder-as-book grouping.

Most audiobooks are a folder of chapter files (sometimes with a cover
image), not single files. group_items() turns the per-file scan results
into per-book dicts:

- a directory with 2+ audio files -> one book, files become chapters
  (sorted by track number, then naturally by name)
- a directory with 1 audio file -> one book with one chapter
- each ebook file -> its own book (unchanged)

A book dict keeps every key the old per-file dicts had (path, rel,
kind, ext, author, book, title, track, lang, has_tags, mojibake,
translit, has_art) so the report, duplicates and organize code keeps
working, and adds:

    chapters       list of {path, rel, title, track, ext}, in chapter order
    chapter_count  len(chapters)
    folder_cover   absolute path of a cover image found in the book's
                   folder (cover.jpg, folder.jpg, front.png, ...), or None

For a folder-book, ``path``/``rel`` point at the folder; for a
single-file book they point at the file (as before).

Book title/author inference: the most common embedded album/author tag
across chapters wins; otherwise the (mojibake-repaired) folder name is
used. Transliteration flags stay display-only - nothing is renamed.
"""

import os
import re
from collections import Counter
from pathlib import Path

from .text import clean_name, fix_mojibake, looks_transliterated

# Cover images commonly found next to chapter files. Matched
# case-insensitively; the original file is never moved, only copied
# into the app's cover cache.
COVER_FILENAMES = (
    "cover.jpg", "cover.jpeg", "cover.png", "cover.webp", "cover.bmp",
    "folder.jpg", "folder.jpeg", "folder.png",
    "front.jpg", "front.jpeg", "front.png",
    "albumart.jpg", "albumart.jpeg", "albumart.png",
)


def find_folder_cover(dirpath):
    """Return the Path of a cover image inside *dirpath*, or None."""
    d = Path(dirpath)
    if not d.is_dir():
        return None
    try:
        names = {p.name.lower(): p for p in d.iterdir() if p.is_file()}
    except OSError:
        return None
    for name in COVER_FILENAMES:
        if name in names:
            return names[name]
    return None


def natural_key(s):
    """Sort key so 'chapter 2' comes before 'chapter 10'."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", s or "")]


def chapter_sort_key(ch):
    """Order chapters by track number first, then naturally by title."""
    m = re.match(r"\s*(\d{1,4})", ch.get("track") or "")
    num = int(m.group(1)) if m else None
    return (0 if num is not None else 1, num or 0,
            natural_key(ch.get("title") or ch.get("path") or ""))


def _most_common(values):
    """Most frequent non-empty value, or ''."""
    counts = Counter(v for v in values if v and str(v).strip())
    return counts.most_common(1)[0][0] if counts else ""


def _without_raw(it):
    it = dict(it)
    it.pop("_raw_author", None)
    it.pop("_raw_book", None)
    return it


def _single_book(it, root):
    """One file -> one book with a single chapter."""
    parent = Path(it["path"]).parent
    cover = (find_folder_cover(parent)
             if parent != Path(root) else None)
    book = _without_raw(it)
    book["chapters"] = [{
        "path": it["path"], "rel": it["rel"], "title": it["title"],
        "track": it["track"], "ext": it["ext"],
    }]
    book["chapter_count"] = 1
    book["folder_cover"] = str(cover) if cover else None
    if cover:
        book["has_art"] = True
    return book


def _folder_book(dirpath, files, root):
    """Many chapter files in one directory -> a single book."""
    authors = [f.pop("_raw_author", "") for f in files]
    albums = [f.pop("_raw_book", "") for f in files]

    chapters = sorted(
        ({"path": f["path"], "rel": f["rel"], "title": f["title"],
          "track": f["track"], "ext": f["ext"]} for f in files),
        key=chapter_sort_key)

    folder_name = Path(dirpath).name
    album = _most_common(albums)
    book_title = clean_name(album) if album else clean_name(folder_name)
    author = _most_common(authors)
    author = clean_name(author) if author else "Unknown Author"

    fixed_folder = fix_mojibake(folder_name)
    cover = find_folder_cover(dirpath)

    return {
        "path": str(dirpath),
        "rel": os.path.relpath(str(dirpath), str(root)),
        "kind": "audio",
        "ext": chapters[0]["ext"],
        "author": author,
        "book": book_title,
        "title": book_title,
        "track": "",
        "lang": _most_common([f["lang"] for f in files])
        or "English / other",
        "has_tags": any(f["has_tags"] for f in files),
        "mojibake": (any(f["mojibake"] for f in files)
                     or fixed_folder != folder_name),
        "translit": (any(f["translit"] for f in files)
                     or looks_transliterated(fixed_folder)),
        "has_art": any(f["has_art"] for f in files) or cover is not None,
        "chapters": chapters,
        "chapter_count": len(chapters),
        "folder_cover": str(cover) if cover else None,
    }


def group_items(file_items, root, group_root=False):
    """Group per-file scan dicts into per-book dicts.

    Audio files are grouped by parent directory (2+ files = one book).
    Files sitting directly in *root* are only grouped when
    *group_root* is True (used for drag-and-drop folder imports, where
    the dropped folder usually IS the book); a library-wide scan keeps
    loose root files as individual books.
    """
    root = Path(root)
    books = []
    by_dir = {}
    for it in file_items:
        if it["kind"] == "ebook":
            books.append(_single_book(it, root))
        else:
            by_dir.setdefault(Path(it["path"]).parent, []).append(it)
    for dirpath in sorted(by_dir, key=str):
        files = by_dir[dirpath]
        if len(files) == 1:
            books.append(_single_book(files[0], root))
        elif dirpath == root and not group_root:
            for f in files:
                books.append(_single_book(f, root))
        else:
            books.append(_folder_book(dirpath, files, root))
    return books
