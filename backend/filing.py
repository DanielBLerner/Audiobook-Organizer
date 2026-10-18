"""Filing: move a reviewed book's files into the library's final layout.

Audiobook chapters:
    {library}/{author}/{series?}/{book_title}/{NNN} - {chapter_title}{ext}
    (NNN is 1-based, 3-digit zero-padded; the series level is skipped
    when empty)

Ebooks (kind == "ebook", single chapter):
    {library}/{author}/{series?}/{book_title}{ext}
    (file placed directly - no book folder)

Every path component is sanitized with clean_name. plan_destinations()
only plans; execute_plan() does the moves. There is no undo - moves
already done stay done, so the GUI confirms before calling
execute_plan().
"""

import os
import shutil
from pathlib import Path

from .text import clean_name


class FilingError(Exception):
    """A filing move failed. Moves already done stay done (no undo)."""


def _chapter_title(chapter):
    """Cleaned chapter title, or the original filename stem if empty."""
    title = clean_name(chapter.get("title") or "")
    if not title or title == "Unknown":
        stem = Path(chapter.get("path", "")).stem
        title = clean_name(stem)
    return title


def plan_destinations(book, library_root):
    """Return a list of (src_abs, dst_abs) tuples for a book.

    book keys: author, book (title), series (may be ""), chapters -
    each chapter is {path, title, ext, kind}.
    Pairs where src == dst are skipped.
    """
    lib = Path(library_root)
    author = clean_name(book.get("author") or "Unknown Author")
    series = clean_name(book.get("series") or "")
    if series == "Unknown":
        series = ""
    title = clean_name(book.get("book") or "Unknown Book")
    base = lib / author
    if series:
        base = base / series

    chapters = book.get("chapters") or []
    plan = []
    is_ebook = bool(chapters) and chapters[0].get("kind") == "ebook"
    if is_ebook:
        ch = chapters[0]
        src = Path(ch["path"])
        dst = base / f"{title}{ch.get('ext') or src.suffix.lower()}"
        if str(src) != str(dst):
            plan.append((str(src), str(dst)))
        return plan

    book_dir = base / title
    for i, ch in enumerate(chapters, start=1):
        src = Path(ch["path"])
        ext = ch.get("ext") or src.suffix.lower()
        num = f"{i:03d}"
        dst = book_dir / f"{num} - {_chapter_title(ch)}{ext}"
        if str(src) != str(dst):
            plan.append((str(src), str(dst)))
    return plan


def execute_plan(plan, mode="move"):
    """Create dirs and move (or copy) every (src, dst) pair.

    mode: "move" (default) or "copy". Raises FilingError on the first
    failure; completed operations stay done (the spec has no undo -
    the GUI confirms first).
    """
    if mode not in ("move", "copy"):
        raise FilingError(f"Unknown file mode: {mode!r}")
    op = shutil.move if mode == "move" else shutil.copy2
    verb = "move" if mode == "move" else "copy"
    for src, dst in plan:
        src_p, dst_p = Path(src), Path(dst)
        try:
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            op(str(src_p), str(dst_p))
        except Exception as e:
            raise FilingError(f"Could not {verb} '{src}' to '{dst}': {e}")


def fingerprint_paths(paths):
    """Return {abs_path: sha256} for every readable path; skip the rest."""
    from .duplicates import _sha256
    out = {}
    for p in paths or []:
        try:
            out[str(p)] = _sha256(str(p))
        except OSError:
            continue
    return out


def find_leftovers(plan):
    """Map each distinct source dir in the plan to the sorted list of
    entries in that dir which the plan does NOT move.

    Used by the review screen (Addendum C) to tell Daniel what will be
    left behind - and therefore that the source folder will be kept.
    """
    moved = {}
    for src, _dst in plan or []:
        d = os.path.dirname(os.path.abspath(src))
        moved.setdefault(d, set()).add(os.path.basename(src))
    leftovers = {}
    for d, names in moved.items():
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        rest = sorted(e for e in entries if e not in names)
        if rest:
            leftovers[d] = rest
    return leftovers


def remove_empty_dirs(dirs):
    """Remove each directory in `dirs` ONLY if it is completely empty.

    Returns (removed, kept) where `removed` is the list of dirs that
    were removed and `kept` maps each remaining dir to its sorted
    leftover entries. Parent directories are never touched - only the
    exact dirs given. os.rmdir() is inherently empty-only, so a folder
    that still contains anything at all can never be deleted here.
    """
    removed, kept = [], {}
    for d in dict.fromkeys(dirs or []):
        try:
            entries = sorted(os.listdir(d))
        except OSError:
            continue  # gone or unreadable: nothing to do
        if entries:
            kept[d] = entries
            continue
        try:
            os.rmdir(d)
        except OSError:
            continue  # raced or permission: leave it alone
        removed.append(d)
    return removed, kept
