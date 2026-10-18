"""Edit page: same layout as Add Screen 1 (plus a Chapters tab).

Stored values are Daniel's own, so they start GREEN ("edited"); empty
fields are gray; any change stays green. Back/close without saving
discards silently. Save persists metadata, chapter order and cover art.
Delete asks for confirmation, then removes the db row and sends every
chapter file to the Recycle Bin, pruning folders left empty.
"""

import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from backend import (
    CoverError,
    UnsupportedFormatError,
    can_set_cover,
    extract_cover,
    set_cover,
)

from . import save_cover_bytes
from .fields import (ChapterListWidget, StateDateField, StateField,
                     TagLineEdit)

try:
    from send2trash import send2trash
except ImportError:  # pragma: no cover - depends on the environment
    send2trash = None

COVER_BOX = 240


class EditPage(QDialog):
    book_saved = Signal(int)
    book_deleted = Signal(int)

    def __init__(self, db, cfg, cover_cache_dir, book_id, parent=None):
        super().__init__(parent)
        self._db = db
        self._cfg = cfg
        self._cover_cache_dir = cover_cache_dir
        self._book_id = book_id

        self.setWindowTitle("Edit book")
        self.setMinimumSize(760, 560)

        try:
            self._book = self._db.get_book(book_id)
        except Exception:
            self._book = None
        if not self._book:
            QTimer.singleShot(
                0, lambda: (
                    QMessageBox.warning(
                        self, "Edit book",
                        "Could not load this book from the database."),
                    self.reject()))
            return

        self._cover_bytes = self._load_cover_bytes(self._book)
        self._cover_path = self._book.get("cover_path")  # stored path or None
        self._cover_action = "keep"  # keep | replaced | removed

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # -- Back, top-left ------------------------------------------------
        top = QHBoxLayout()
        back_btn = QPushButton("Back")
        back_btn.clicked.connect(self.reject)  # discard silently
        top.addWidget(back_btn, 0, Qt.AlignLeft)
        top.addStretch(1)
        layout.addLayout(top)

        # -- tabs ----------------------------------------------------------
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        details = QWidget()
        self._build_details_tab(details)
        self.tabs.addTab(details, "Details")

        chapters_tab = QWidget()
        ctl = QVBoxLayout(chapters_tab)
        self._chapter_list = ChapterListWidget()
        self._chapter_list.set_chapters(self._book.get("chapters") or [])
        ctl.addWidget(self._chapter_list)
        self.tabs.addTab(chapters_tab, "Chapters")

        # -- Save / Delete, bottom-center ----------------------------------
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self._save_btn = QPushButton("Save Changes")
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setObjectName("danger")
        self._delete_btn.clicked.connect(self._on_delete)
        bottom.addWidget(self._save_btn)
        bottom.addWidget(self._delete_btn)
        bottom.addStretch(1)
        layout.addLayout(bottom)

    # ------------------------------------------------------------------
    # details tab (mirrors Add Screen 1)
    # ------------------------------------------------------------------
    def _build_details_tab(self, details):
        layout = QVBoxLayout(details)
        columns = QHBoxLayout()
        columns.setSpacing(24)
        layout.addLayout(columns, 1)

        left = QVBoxLayout()
        left.setSpacing(8)
        columns.addLayout(left)

        self._cover_label = QLabel()
        self._cover_label.setFixedSize(COVER_BOX, COVER_BOX)
        self._cover_label.setAlignment(Qt.AlignCenter)
        self._refresh_cover_label()
        left.addWidget(self._cover_label, 0, Qt.AlignCenter)

        cover_btns = QHBoxLayout()
        keep_btn = QPushButton("Keep")
        keep_btn.clicked.connect(self._keep_cover)
        replace_btn = QPushButton("Replace")
        replace_btn.clicked.connect(self._replace_cover)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_cover)
        cover_btns.addWidget(keep_btn)
        cover_btns.addWidget(replace_btn)
        cover_btns.addWidget(remove_btn)
        left.addLayout(cover_btns)

        left.addWidget(QLabel("Tags (comma-separated):"))
        self._tag_edit = TagLineEdit()
        try:
            self._tag_edit.set_tag_list(self._db.visible_tags())
        except Exception:
            pass
        self._tag_edit.setText(", ".join(self._book.get("tags") or []))
        left.addWidget(self._tag_edit)
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(16)
        columns.addLayout(right, 1)

        # Stored values are Daniel's own -> start green ("edited").
        self._title_field = StateField(
            "Title", initial=self._book.get("title") or "",
            start_edited=True)
        right.addWidget(self._title_field)
        self._author_field = StateField(
            "Author", initial=self._book.get("author") or "",
            start_edited=True)
        right.addWidget(self._author_field)
        self._series_field = StateField(
            "Series (optional)", initial=self._book.get("series") or "",
            start_edited=True)
        right.addWidget(self._series_field)
        # Addendum A: same Date field, same position as the Add page.
        self._date_field = StateDateField(
            "Date added",
            initial=self._book.get("date_added") or None,
            start_edited=True)
        right.addWidget(self._date_field)
        right.addStretch(1)

    # -- cover ------------------------------------------------------------
    def _load_cover_bytes(self, book):
        cover_path = book.get("cover_path")
        if cover_path and os.path.isfile(cover_path):
            try:
                with open(cover_path, "rb") as fh:
                    return fh.read()
            except OSError:
                pass
        for ch in book.get("chapters") or []:
            path = ch.get("path")
            if not path:
                continue
            try:
                data = extract_cover(path)
            except Exception:
                data = None
            if data:
                return data
        return None

    def _refresh_cover_label(self):
        if self._cover_bytes:
            pix = QPixmap()
            if pix.loadFromData(self._cover_bytes):
                self._cover_label.setPixmap(pix.scaled(
                    COVER_BOX, COVER_BOX, Qt.KeepAspectRatio,
                    Qt.SmoothTransformation))
                return
        pix = QPixmap(COVER_BOX, COVER_BOX)
        pix.fill(QColor("#2d2d2d"))
        painter = QPainter(pix)
        try:
            painter.setPen(QColor("#8a8a8a"))
            painter.drawText(pix.rect(), Qt.AlignCenter, "No cover")
        finally:
            painter.end()
        self._cover_label.setPixmap(pix)

    def _keep_cover(self):
        self._cover_action = "keep"
        self._cover_bytes = self._load_cover_bytes(self._book)
        self._cover_path = self._book.get("cover_path")
        self._refresh_cover_label()

    def _replace_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose cover image", os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        try:
            with open(path, "rb") as fh:
                self._cover_bytes = fh.read()
        except OSError as exc:
            QMessageBox.warning(self, "Cover",
                                "Could not read image:\n%s" % exc)
            return
        self._cover_action = "replaced"
        self._refresh_cover_label()

    def _remove_cover(self):
        self._cover_bytes = None
        self._cover_action = "removed"
        self._refresh_cover_label()

    # ------------------------------------------------------------------
    # save
    # ------------------------------------------------------------------
    def _on_save(self):
        title = self._title_field.text().strip()
        author = self._author_field.text().strip()
        series = self._series_field.text().strip()
        tags = self._tag_edit.tags()

        # Cover: copy a replaced cover into the cache; keep or drop.
        cover_path = self._cover_path
        if self._cover_action == "replaced" and self._cover_bytes:
            try:
                cover_path = save_cover_bytes(
                    self._cover_bytes, self._cover_cache_dir)
            except Exception as exc:
                QMessageBox.warning(
                    self, "Save",
                    "Could not cache the cover image:\n%s" % exc)
                return
        elif self._cover_action == "removed":
            cover_path = None

        try:
            self._db.update_book(self._book_id, title, author, series,
                                 tags, cover_path,
                                 date_added=self._date_field.date_iso()
                                 if self._date_field else None)
        except Exception as exc:
            QMessageBox.critical(self, "Save",
                                 "Could not save changes:\n%s" % exc)
            return

        # Chapter order.
        ordered = self._chapter_list.ordered_chapters()
        ids = [ch.get("id") for ch in ordered]
        if ids and all(i is not None for i in ids):
            try:
                self._db.update_chapter_order(self._book_id, ids)
            except Exception as exc:
                QMessageBox.warning(self, "Save",
                                    "Chapter order was not saved:\n%s" % exc)

        # Embed the cover into chapter files where supported.
        failures = []
        if self._cover_bytes:
            for ch in ordered:
                path = ch.get("path") or ""
                if not path or not os.path.isfile(path):
                    continue
                try:
                    if can_set_cover(Path(path).suffix):
                        set_cover(path, self._cover_bytes)
                except (CoverError, UnsupportedFormatError) as exc:
                    failures.append("%s: %s" % (os.path.basename(path), exc))
                except Exception as exc:
                    failures.append("%s: %s: %s"
                                    % (os.path.basename(path),
                                       type(exc).__name__, exc))
        if failures:
            QMessageBox.warning(
                self, "Save",
                "Changes saved, but cover art could not be embedded into "
                "%d file(s):\n- %s"
                % (len(failures), "\n- ".join(failures)))

        self.book_saved.emit(self._book_id)
        self.accept()

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------
    def _on_delete(self):
        title = self._title_field.text().strip() or "this book"
        answer = QMessageBox.question(
            self, "Delete book",
            "Are you sure you want to delete '%s'?\n\n"
            "The book will be removed from the library and its files "
            "will be moved to the Recycle Bin. This cannot be undone."
            % title,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if send2trash is None:
            QMessageBox.warning(
                self, "Delete book",
                "The 'send2trash' package is not installed, so files cannot "
                "be moved to the Recycle Bin safely. Deletion cancelled.")
            return

        chapters = self._book.get("chapters") or []
        file_paths = [ch.get("path") for ch in chapters if ch.get("path")]
        library_path = self._book.get("library_path") or ""

        try:
            self._db.delete_book(self._book_id)
        except Exception as exc:
            QMessageBox.critical(self, "Delete book",
                                 "Could not delete the book:\n%s" % exc)
            return

        failed = []
        for path in file_paths:
            try:
                if os.path.isfile(path):
                    send2trash(path)
            except Exception as exc:
                failed.append("%s: %s" % (path, exc))
        self._prune_empty_folders(library_path)

        if failed:
            QMessageBox.warning(
                self, "Delete book",
                "The book was removed from the library, but %d file(s) "
                "could not be moved to the Recycle Bin:\n- %s"
                % (len(failed), "\n- ".join(failed)))
        self.book_deleted.emit(self._book_id)
        self.accept()

    def _prune_empty_folders(self, library_path):
        """Remove the now-empty book folder, then series/author folders
        if they are empty too. Never removes the library root itself,
        and never removes a folder that still has files in it."""
        library_root = (self._cfg.get("library_root") or "").strip()
        folder = Path(library_path).parent if library_path else None
        root = Path(library_root) if library_root else None
        depth = 0
        while folder is not None and depth < 3:
            try:
                if root is not None and folder.resolve() == root.resolve():
                    break
            except OSError:
                break
            try:
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
                else:
                    break  # not empty (or not a dir): stop climbing
            except OSError:
                break
            folder = folder.parent
            depth += 1
