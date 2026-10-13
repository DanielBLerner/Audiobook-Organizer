"""Background workers.

Every slow operation (scan/import, organize, undo, duplicate detection)
runs in a QThread so the UI never freezes. Workers never touch widgets;
they only emit signals the main window connects to.

Note: the custom completion signal is called ``done``, not ``finished``,
because QThread already defines a ``finished`` signal.
"""

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from backend import (
    scan,
    apply_organize,
    undo_last,
    find_duplicates,
    extract_cover,
)


class ScanWorker(QThread):
    """Scan a folder, import results into the DB, cache cover art."""

    progress = Signal(int, int)   # done, total  (0, 0) = indeterminate step
    done = Signal(int, int)       # new_count, total_scanned
    error = Signal(str)

    def __init__(self, root, db, covers_dir, parent=None, group_root=False):
        super().__init__(parent)
        self._root = str(root)
        self._db = db
        self._covers_dir = Path(covers_dir)
        # group_root: treat loose audio files directly in *root* as one
        # book's chapters (used for drag-and-drop folder imports, where
        # the dropped folder usually IS the book).
        self._group_root = group_root

    def run(self):
        try:
            self.progress.emit(0, 0)  # scanning files...
            items = scan(self._root, group_root=self._group_root)
            self.progress.emit(0, 0)  # importing into library...
            new_count = self._db.import_items(items)
            total = len(items)
            self._covers_dir.mkdir(parents=True, exist_ok=True)
            for i, it in enumerate(items):
                try:
                    self._cache_cover(it)
                except Exception:
                    pass  # cover caching is best effort; never fails import
                if i % 25 == 0 or i == total - 1:
                    self.progress.emit(i + 1, max(total, 1))
            self.done.emit(new_count, total)
        except Exception as e:
            self.error.emit(f"Scan failed: {e}")

    def _cache_cover(self, item):
        book = self._db.find_by_path(item["path"])
        if not book:
            return
        existing = book.get("cover_path")
        if existing and Path(existing).exists():
            return  # already cached
        art = None
        # A cover image sitting next to the chapter files wins: copy it
        # into the cache (the original file is never moved).
        folder_cover = item.get("folder_cover")
        if folder_cover and Path(folder_cover).is_file():
            try:
                art = Path(folder_cover).read_bytes()
            except OSError:
                art = None
        if art is None:
            for ch in item.get("chapters") or []:
                art = extract_cover(ch["path"])
                if art:
                    break
        if art:
            cache = self._covers_dir / f"{book['id']}.jpg"
            cache.write_bytes(art)
            self._db.set_cover(book["id"], str(cache))


class OrganizeWorker(QThread):
    """Apply an organize plan (moves files). Emits the undo log path."""

    done = Signal(str)   # undo_log_path
    error = Signal(str)

    def __init__(self, root, plan, parent=None):
        super().__init__(parent)
        self._root = str(root)
        self._plan = list(plan)

    def run(self):
        try:
            log_path = apply_organize(self._root, self._plan)
            self.done.emit(log_path)
        except Exception as e:
            self.error.emit(f"Organize failed: {e}\n"
                            f"{traceback.format_exc(limit=5)}")


class UndoWorker(QThread):
    """Reverse the most recent organize/title-fix run."""

    done = Signal(int)   # number of moves reversed
    error = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self._root = str(root)

    def run(self):
        try:
            count = undo_last(self._root)
            self.done.emit(count)
        except Exception as e:
            self.error.emit(f"Undo failed: {e}")


class DuplicatesWorker(QThread):
    """Find exact and near-duplicate books. Can be slow: hashes files."""

    done = Signal(dict)  # {'exact': [[item...]], 'near': [[item...]]}
    error = Signal(str)

    def __init__(self, books, parent=None):
        super().__init__(parent)
        # books: list of dicts with at least path/rel/author/book keys
        self._books = list(books)

    def run(self):
        try:
            result = find_duplicates(self._books)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(f"Duplicate search failed: {e}")
