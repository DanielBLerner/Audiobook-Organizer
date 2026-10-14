"""QThread workers. Signals only - workers never touch the GUI.

backend/db imports happen inside run() (or at module top where the
module is only imported by GUI code that already requires the backend).
"""

import os
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from backend import (
    CoverError,
    FilingError,
    UnsupportedFormatError,
    can_set_cover,
    execute_plan,
    fingerprint_paths,
    scan,
    set_cover,
)
from db import LibraryDB

from . import save_cover_bytes


class ScanWorker(QThread):
    """Read-only library scan of a dropped folder / files' directory."""

    finished = Signal(list)   # list of scanned book dicts
    error = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self._root = root

    def run(self):
        try:
            books = scan(self._root, group_root=True)
            self.finished.emit(list(books or []))
        except Exception as exc:  # never let a scan kill the UI
            self.error.emit("%s: %s" % (type(exc).__name__, exc))


class HashWorker(QThread):
    """Fingerprint a list of file paths (SHA-256)."""

    finished = Signal(dict)   # {path: sha256}
    error = Signal(str)

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self._paths = list(paths or [])

    def run(self):
        try:
            self.finished.emit(fingerprint_paths(self._paths))
        except Exception as exc:
            self.error.emit("%s: %s" % (type(exc).__name__, exc))


class FileWorker(QThread):
    """Execute a filing plan in the background.

    Steps: execute_plan -> embed cover art into moved files (failures
    are collected, never fatal) -> fingerprint moved files ->
    db.file_book. A fresh LibraryDB connection is opened inside this
    thread; the GUI's db instance is never touched from here.

    ``filing`` dict keys:
        book:        {title, author, series}
        chapters:    ordered list of {title, ext, track} matching plan order
        tags:        list of str
        library_dir: the book's folder inside the library (str)
    """

    finished = Signal(int, list)  # (book_id, cover_failures: [str])
    error = Signal(str)

    def __init__(self, plan, db_path, filing, cover_bytes, cover_cache_dir,
                 file_mode="move", parent=None):
        super().__init__(parent)
        self._plan = list(plan or [])
        self._db_path = db_path
        self._filing = dict(filing or {})
        self._cover_bytes = cover_bytes
        self._cover_cache_dir = cover_cache_dir
        self._file_mode = file_mode if file_mode in ("move", "copy") else "move"

    def run(self):
        db = None
        try:
            execute_plan(self._plan, mode=self._file_mode)

            dest_paths = [dst for _src, dst in self._plan]

            # Embed cover art into the moved files (best effort).
            cover_failures = []
            if self._cover_bytes:
                for dst in dest_paths:
                    ext = Path(dst).suffix
                    try:
                        if can_set_cover(ext):
                            set_cover(dst, self._cover_bytes)
                    except (CoverError, UnsupportedFormatError) as exc:
                        cover_failures.append(
                            "%s: %s" % (os.path.basename(dst), exc))
                    except Exception as exc:  # unexpected: report, continue
                        cover_failures.append(
                            "%s: %s: %s" % (os.path.basename(dst),
                                           type(exc).__name__, exc))

            fingerprints = fingerprint_paths(dest_paths)

            cover_path = None
            if self._cover_bytes:
                cover_path = save_cover_bytes(
                    self._cover_bytes, self._cover_cache_dir)

            library_dir = self._filing.get("library_dir") or (
                str(Path(dest_paths[0]).parent) if dest_paths else "")

            src_chapters = self._filing.get("chapters") or []
            db_chapters = []
            for pos, ((_src, dst), ch) in enumerate(
                    zip(self._plan, src_chapters)):
                db_chapters.append({
                    "path": dst,
                    "rel": os.path.relpath(dst, library_dir)
                           if library_dir else os.path.basename(dst),
                    "title": ch.get("title") or "",
                    "track": ch.get("track") or str(pos + 1),
                    "ext": ch.get("ext") or Path(dst).suffix,
                })

            db = LibraryDB(self._db_path)
            try:
                book_id = db.file_book(
                    self._filing.get("book") or {},
                    db_chapters,
                    self._filing.get("tags") or [],
                    cover_path,
                    library_dir,
                    fingerprints,
                )
            finally:
                db.close()
                db = None

            self.finished.emit(book_id, cover_failures)
        except FilingError as exc:
            self.error.emit("Filing failed: %s" % exc)
        except Exception as exc:
            self.error.emit("%s: %s" % (type(exc).__name__, exc))
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
