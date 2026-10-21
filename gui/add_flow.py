"""Add page: bring a book in -> Screen 1 (details) -> Screen 2 (chapters)
-> Screen 3 (review & file). Strictly one book at a time, no queue;
leaving mid-book discards everything silently.
"""

import html
import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend import (check_new_book, extract_cover, find_author_variants,
                     find_leftovers, plan_destinations, scan)

from .fields import (ChapterListWidget, StateDateField, StateField,
                     TagEntry)
from .workers import FileWorker, ScanWorker

LANG_TAG = {
    "Russian": "Russian",
    "Russian (transliterated?)": "Russian",
}

COVER_BOX = 260  # px; the "about 1/4 of screen" cover on Screen 1


class _DropArea(QWidget):
    """Landing panel that accepts dropped folders/files."""

    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        hint = QLabel(
            "<b>Drag a book folder (or audio files) here</b><br>"
            '<span style="color:#9a9a9a">or use the Browse button below. '
            "Scanning never modifies your files.</span>")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.browse_btn = QPushButton("Browse\u2026")
        layout.addWidget(self.browse_btn, 0, Qt.AlignCenter)

        self.status_label = QLabel("")
        self.status_label.setObjectName("muted")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        paths = [p for p in paths if p]
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()


class _BookPickDialog(QDialog):
    """Shown when a scan finds several books: pick one (no queue)."""

    def __init__(self, books, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Which book?")
        self.setMinimumWidth(460)
        self._books = list(books or [])

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("The scan found several books. Pick one:"))

        self.list = QListWidget()
        for book in self._books:
            author = book.get("author") or "Unknown author"
            title = book.get("title") or book.get("book") or "Untitled"
            n = book.get("chapter_count") or len(book.get("chapters") or [])
            QListWidgetItem("%s - %s (%d chapters)" % (author, title, n),
                            self.list)
        layout.addWidget(self.list)
        if self._books:
            self.list.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_book(self):
        row = self.list.currentRow()
        if 0 <= row < len(self._books):
            return self._books[row]
        return None


class AddFlowWidget(QWidget):
    """The Add tab."""

    book_filed = Signal(int)      # emitted with the new book id
    status_message = Signal(str)

    def __init__(self, db, db_path, cfg, cover_cache_dir, parent=None):
        super().__init__(parent)
        self._db = db
        self._db_path = db_path
        self._cfg = cfg
        self._cover_cache_dir = cover_cache_dir

        self._book = None            # scanned book dict
        self._cover_bytes = None     # current cover choice (bytes or None)
        self._plan = []              # [(src, dst)]
        self._filing = {}            # payload for FileWorker
        self._scan_worker = None
        self._file_worker = None
        self._scan_roots = []

        # Screen-1/2 widget refs (rebuilt per book)
        self._title_field = self._author_field = self._series_field = None
        self._date_field = None
        self._tag_edit = None
        self._cover_label = None
        self._chapter_list = None
        self._chapters_screen_built = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        self._landing = _DropArea()
        self._landing.browse_btn.clicked.connect(self._browse_folder)
        self._landing.files_dropped.connect(self._start_scan)
        self.stack.addWidget(self._landing)

        self._screen1 = QWidget()
        self.stack.addWidget(self._screen1)
        self._screen2 = QWidget()
        self.stack.addWidget(self._screen2)
        self._screen3 = QWidget()
        self.stack.addWidget(self._screen3)

        self.reset()

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------
    def reset(self):
        """Back to the empty landing state (mid-book work is discarded)."""
        self._book = None
        self._cover_bytes = None
        self._plan = []
        self._filing = {}
        self._scan_roots = []
        self._title_field = self._author_field = self._series_field = None
        self._date_field = None
        self._tag_edit = None
        self._cover_label = None
        self._chapter_list = None
        self._chapters_screen_built = False
        self._leftovers = {}
        self._landing.status_label.setText("")
        self._landing.browse_btn.setEnabled(True)
        self._clear_widget(self._screen1)
        self._clear_widget(self._screen2)
        self._clear_widget(self._screen3)
        self.stack.setCurrentWidget(self._landing)

    @staticmethod
    def _clear_widget(widget):
        layout = widget.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.deleteLater()

    @staticmethod
    def _finish_worker(worker):
        if worker is not None:
            worker.quit()
            worker.wait()
            worker.deleteLater()

    # ------------------------------------------------------------------
    # bringing a book in
    # ------------------------------------------------------------------
    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a book folder", os.path.expanduser("~"))
        if folder:
            self._start_scan([folder])

    def _start_scan(self, paths):
        # Files are scanned via their parent directory; duplicate roots
        # are scanned only once. The first root goes through the
        # background worker; any extra roots are scanned synchronously
        # afterwards (a drop rarely carries more than one or two).
        roots = []
        for p in paths:
            if os.path.isdir(p):
                roots.append(p)
            elif os.path.isfile(p):
                roots.append(os.path.dirname(p) or ".")
        roots = list(dict.fromkeys(roots))
        if not roots:
            return
        self._scan_roots = roots[1:]
        self._landing.status_label.setText("Scanning\u2026")
        self._landing.browse_btn.setEnabled(False)
        self._scan_worker = ScanWorker(roots[0], self)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_error(self, message):
        self._finish_worker(self._scan_worker)
        self._scan_worker = None
        self._landing.status_label.setText("")
        self._landing.browse_btn.setEnabled(True)
        QMessageBox.warning(self, "Scan failed",
                            "Could not scan the dropped files:\n%s" % message)

    def _on_scan_finished(self, books):
        self._finish_worker(self._scan_worker)
        self._scan_worker = None
        self._landing.status_label.setText("")
        self._landing.browse_btn.setEnabled(True)

        merged = list(books or [])
        seen = {b.get("path") for b in merged}
        for root in self._scan_roots:
            try:
                for b in scan(root, group_root=True) or []:
                    if b.get("path") not in seen:
                        seen.add(b.get("path"))
                        merged.append(b)
            except Exception as exc:
                self.status_message.emit(
                    "Scan of %s failed: %s" % (root, exc))
        self._scan_roots = []

        if not merged:
            self.status_message.emit("No audiobooks found in the dropped files.")
            QMessageBox.information(
                self, "Nothing found",
                "No supported audiobook files were found in what you dropped.")
            return
        if len(merged) == 1:
            self._load_book(merged[0])
            return
        dlg = _BookPickDialog(merged, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_book() is not None:
            self._load_book(dlg.selected_book())
        # else: user cancelled -> stay on landing, nothing kept

    # ------------------------------------------------------------------
    # Screen 1 - book details
    # ------------------------------------------------------------------
    def _load_book(self, book):
        self._book = book
        self._cover_bytes = self._detect_cover(book)
        self._chapters_screen_built = False

        self._clear_widget(self._screen1)
        layout = QVBoxLayout(self._screen1)

        columns = QHBoxLayout()
        columns.setSpacing(24)
        layout.addLayout(columns, 1)

        # -- left column: cover + tags -------------------------------
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
        keep_btn.setToolTip("Keep the current cover")
        keep_btn.clicked.connect(
            lambda: self.status_message.emit("Cover kept."))
        replace_btn = QPushButton("Replace")
        replace_btn.clicked.connect(self._replace_cover)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_cover)
        cover_btns.addWidget(keep_btn)
        cover_btns.addWidget(replace_btn)
        cover_btns.addWidget(remove_btn)
        left.addLayout(cover_btns)

        left.addWidget(QLabel("Tags:"))
        self._tag_edit = TagEntry()
        try:
            self._tag_edit.set_tag_list(self._db.visible_tags())
            self._tag_edit.set_meta(
                {m["tag"]: m for m in self._db.all_tag_meta()})
        except Exception:
            pass
        suggested = LANG_TAG.get((book.get("lang") or "").strip(), "English")
        self._tag_edit.set_tags([suggested])
        left.addWidget(self._tag_edit)
        left.addStretch(1)

        # -- right column: Title / Author / Series --------------------
        right = QVBoxLayout()
        right.setSpacing(16)
        columns.addLayout(right, 1)

        title_guess = book.get("title") or book.get("book") or ""
        author_guess = book.get("author") or ""
        if author_guess.strip().lower() == "unknown author":
            author_guess = ""  # not a real guess; flagged instead

        sources = book.get("sources") or {}

        def _note(key):
            src = (sources.get(key) or "").strip().lower()
            if src in ("embedded tags", "folder name", "filename"):
                return "from " + src
            if not src or src == "none":
                return "not found"
            return "from " + src

        title_flags = []
        if book.get("translit"):
            title_flags.append(("transliterated?", _note("title")))
        if book.get("mojibake"):
            title_flags.append(("mojibake repaired", _note("title")))
        self._title_field = StateField("Title", initial=title_guess,
                                       flags=title_flags)
        right.addWidget(self._title_field)

        author_flags = []
        if book.get("translit"):
            author_flags.append(("transliterated?", _note("author")))
        if not author_guess:
            author_flags.append(("no author found", _note("author")))
        self._author_field = StateField("Author", initial=author_guess,
                                        flags=author_flags)
        # Addendum E: suggest authors already in the library so an
        # existing spelling gets reused instead of duplicated.
        try:
            self._author_field.set_completions(self._db.all_authors())
        except Exception:
            pass
        right.addWidget(self._author_field)

        self._series_field = StateField("Series (optional)", initial="")
        right.addWidget(self._series_field)

        # Addendum A: Date field directly under Series. Auto-populated
        # with today (blue); Daniel can backdate it (green).
        self._date_field = StateDateField("Date added")
        right.addWidget(self._date_field)
        right.addStretch(1)

        # -- nav ------------------------------------------------------
        nav = QHBoxLayout()
        back_btn = QPushButton("Back")
        back_btn.clicked.connect(self.reset)  # discard silently
        next_btn = QPushButton("Next")
        next_btn.clicked.connect(self._screen1_next)
        nav.addWidget(back_btn)
        nav.addStretch(1)
        nav.addWidget(next_btn)
        layout.addLayout(nav)

        self.stack.setCurrentWidget(self._screen1)

    def _screen1_next(self):
        chapters = (self._book.get("chapters") or []) if self._book else []
        if len(chapters) <= 1:
            self._build_review()  # single-chapter books skip Screen 2
        else:
            self._build_chapters_screen()

    # -- cover handling -------------------------------------------------
    def _detect_cover(self, book):
        """Embedded art first, then a folder cover image, else None."""
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
        folder_cover = book.get("folder_cover")
        if folder_cover and os.path.isfile(folder_cover):
            try:
                with open(folder_cover, "rb") as fh:
                    return fh.read()
            except OSError:
                return None
        return None

    def _refresh_cover_label(self):
        if self._cover_label is None:
            return
        if self._cover_bytes:
            pix = QPixmap()
            if pix.loadFromData(self._cover_bytes):
                # Scaled to FIT, never stretched: aspect ratio is kept and
                # the image is centered in the fixed-size label.
                scaled = pix.scaled(COVER_BOX, COVER_BOX, Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation)
                self._cover_label.setPixmap(scaled)
                return
        self._cover_label.setPixmap(self._placeholder_pixmap())

    @staticmethod
    def _placeholder_pixmap():
        pix = QPixmap(COVER_BOX, COVER_BOX)
        pix.fill(QColor("#2d2d2d"))
        painter = QPainter(pix)
        try:
            painter.setPen(QColor("#8a8a8a"))
            painter.drawText(pix.rect(), Qt.AlignCenter, "No cover")
        finally:
            painter.end()
        return pix

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
        self._refresh_cover_label()
        self.status_message.emit("Cover replaced.")

    def _remove_cover(self):
        self._cover_bytes = None
        self._refresh_cover_label()
        self.status_message.emit("Cover removed.")

    # ------------------------------------------------------------------
    # Screen 2 - chapters
    # ------------------------------------------------------------------
    def _build_chapters_screen(self):
        self._clear_widget(self._screen2)
        self._chapters_screen_built = True
        layout = QVBoxLayout(self._screen2)

        hint = QLabel("Drag chapters to reorder. Click a row to load it, "
                      "double-click (or \u25b6) to play.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._chapter_list = ChapterListWidget()
        self._chapter_list.set_chapters(
            (self._book or {}).get("chapters") or [])
        layout.addWidget(self._chapter_list, 1)

        nav = QHBoxLayout()
        back_btn = QPushButton("Back")
        back_btn.clicked.connect(
            lambda: self.stack.setCurrentWidget(self._screen1))
        next_btn = QPushButton("Next")
        next_btn.clicked.connect(self._build_review)
        nav.addWidget(back_btn)
        nav.addStretch(1)
        nav.addWidget(next_btn)
        layout.addLayout(nav)

        self.stack.setCurrentWidget(self._screen2)

    def _final_chapters(self):
        """Chapters in their final (possibly reordered) order."""
        if self._chapters_screen_built and self._chapter_list is not None:
            return self._chapter_list.ordered_chapters()
        return list((self._book or {}).get("chapters") or [])

    # ------------------------------------------------------------------
    # Screen 3 - review & file
    # ------------------------------------------------------------------
    def _current_values(self):
        return {
            "title": self._title_field.text().strip()
                     if self._title_field else "",
            "author": self._author_field.text().strip()
                      if self._author_field else "",
            "series": self._series_field.text().strip()
                      if self._series_field else "",
            "date_added": self._date_field.date_iso()
                          if self._date_field else "",
            "tags": self._tag_edit.tags() if self._tag_edit else [],
        }

    def _build_review(self):
        values = self._current_values()
        chapters = self._final_chapters()
        library_root = (self._cfg.get("library_root") or "").strip()

        plan_book = {
            "author": values["author"],
            "book": values["title"],
            "series": values["series"],
            "kind": (self._book or {}).get("kind") or "audio",
            "chapters": [
                {"path": ch.get("path") or "",
                 "title": ch.get("title") or "",
                 "ext": ch.get("ext") or Path(ch.get("path") or "").suffix}
                for ch in chapters
            ],
        }
        try:
            self._plan = plan_destinations(plan_book, library_root) or []
        except Exception as exc:
            QMessageBox.warning(self, "Review",
                                "Could not plan destinations:\n%s" % exc)
            return

        new_book = {
            "author": values["author"],
            "book": values["title"],
            "chapters": [{"path": ch.get("path") or ""} for ch in chapters],
        }
        try:
            dup = check_new_book(new_book, self._db) or {}
        except Exception as exc:
            dup = {}
            self.status_message.emit("Duplicate check failed: %s" % exc)

        self._filing = {
            "book": {"title": values["title"],
                     "author": values["author"],
                     "series": values["series"]},
            "chapters": [
                {"title": ch.get("title") or "",
                 "ext": ch.get("ext") or Path(ch.get("path") or "").suffix,
                 "track": ch.get("track") or ""}
                for ch in chapters
            ],
            "tags": values["tags"],
            "date_added": values["date_added"],
            "library_dir": str(Path(self._plan[0][1]).parent)
                           if self._plan else "",
            "source_dirs": sorted({os.path.dirname(os.path.abspath(src))
                                   for src, _dst in self._plan}),
        }

        # Addendum C: figure out now (for the review screen) which files
        # in the source folder(s) are NOT part of this book. Those stay
        # behind, so the source folder will be kept.
        try:
            self._leftovers = find_leftovers(self._plan) or {}
        except Exception:
            self._leftovers = {}

        self._clear_widget(self._screen3)
        layout = QVBoxLayout(self._screen3)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, 1)
        content = QWidget()
        scroll.setWidget(content)
        cl = QVBoxLayout(content)
        cl.setSpacing(10)

        # -- summary -------------------------------------------------
        summary = QHBoxLayout()
        thumb = QLabel()
        thumb.setFixedSize(64, 64)
        thumb.setAlignment(Qt.AlignCenter)
        if self._cover_bytes:
            pix = QPixmap()
            if pix.loadFromData(self._cover_bytes):
                thumb.setPixmap(pix.scaled(
                    64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setText("no cover")
                thumb.setObjectName("muted")
        else:
            thumb.setText("no cover")
            thumb.setObjectName("muted")
        summary.addWidget(thumb)

        info = QVBoxLayout()
        if values["series"]:
            info.addWidget(QLabel("<b>%s</b>" % html.escape(values["series"])))
        info.addWidget(QLabel("<b>%s</b>"
                              % html.escape(values["title"] or "Untitled")))
        info.addWidget(QLabel(html.escape(values["author"] or "Unknown author")))
        if values["date_added"]:
            date_row = QLabel(html.escape(values["date_added"]))
            date_row.setObjectName("muted")
            info.addWidget(date_row)
        if values["tags"]:
            info.addWidget(QLabel(html.escape(", ".join(values["tags"]))))
        else:
            no_tags = QLabel("no tags")
            no_tags.setObjectName("muted")
            info.addWidget(no_tags)
        summary.addLayout(info, 1)
        cl.addLayout(summary)

        cl.addWidget(QLabel("<b>Chapters (final order):</b>"))
        ch_list = QListWidget()
        ch_list.setMaximumHeight(160)
        for i, ch in enumerate(chapters):
            QListWidgetItem("%03d - %s" % (i + 1, ch.get("title") or ""),
                            ch_list)
        cl.addWidget(ch_list)

        cl.addWidget(QLabel("<b>Destination preview:</b>"))
        dest_list = QListWidget()
        dest_list.setMaximumHeight(160)
        for src, dst in self._plan:
            QListWidgetItem("%s  \u2192  %s" % (src, dst), dest_list)
        cl.addWidget(dest_list)

        cl.addWidget(QLabel("<b>Duplicates:</b>"))
        dup_label = QLabel()
        dup_label.setWordWrap(True)
        dup_label.setTextFormat(Qt.RichText)
        dup_lines = self._duplicate_lines(dup, len(chapters))
        if dup_lines:
            dup_label.setText("<br>".join(html.escape(l) for l in dup_lines))
        else:
            dup_label.setText('<span style="color:#8a8a8a">'
                              "No duplicates found.</span>")
        cl.addWidget(dup_label)

        # Addendum E: same author, different word order/spelling ->
        # warn and offer the existing name, so the book doesn't file
        # into a second author folder. Daniel decides; the app never
        # renames on its own.
        try:
            author_variants = find_author_variants(values["author"],
                                                   self._db)
        except Exception:
            author_variants = []
        if author_variants:
            cl.addWidget(QLabel("<b>Author name:</b>"))
            for variant in author_variants:
                row = QHBoxLayout()
                warn = QLabel(
                    "Your library already has this author as '%s'."
                    % html.escape(variant))
                warn.setWordWrap(True)
                row.addWidget(warn, 1)
                use_btn = QPushButton("Use '%s'" % variant)
                use_btn.clicked.connect(
                    lambda _c=False, v=variant:
                    self._use_author_variant(v))
                row.addWidget(use_btn)
                cl.addLayout(row)

        # Addendum C: warn when leftover files will keep the source
        # folder in place.
        if self._leftovers:
            left_label = QLabel()
            left_label.setWordWrap(True)
            parts = []
            for d, names in self._leftovers.items():
                shown = ", ".join(names[:8])
                if len(names) > 8:
                    shown += ", \u2026 (%d more)" % (len(names) - 8)
                parts.append(
                    "The source folder will be kept - these %d file(s) "
                    "are not part of the book and will stay behind:<br>"
                    "&nbsp;&nbsp;%s" % (len(names), html.escape(shown)))
            left_label.setText("<br><br>".join(parts))
            cl.addWidget(left_label)

        # -- actions -------------------------------------------------
        actions = QHBoxLayout()
        back_btn = QPushButton("Back")
        back_btn.clicked.connect(self._review_back)
        self._add_btn = QPushButton("Add to library")
        self._add_btn.setDefault(True)
        self._add_btn.clicked.connect(self._on_add_clicked)
        actions.addWidget(back_btn)
        actions.addStretch(1)
        actions.addWidget(self._add_btn)
        layout.addLayout(actions)

        self.stack.setCurrentWidget(self._screen3)

    def _duplicate_lines(self, dup, total):
        lines = []
        for m in dup.get("meta") or []:
            title = m.get("title") or "?"
            date = str(m.get("date_added") or "")[:10]
            if date:
                lines.append(
                    "Same author and title as '%s' already in your library "
                    "(filed %s)." % (title, date))
            else:
                lines.append(
                    "Same author and title as '%s' already in your library."
                    % title)
        by_book = {}
        for e in dup.get("exact") or []:
            key = e.get("book")
            if isinstance(key, int):  # tolerate an id instead of a title
                try:
                    found = self._db.get_book(key)
                    key = (found or {}).get("title") or key
                except Exception:
                    pass
            by_book[key] = by_book.get(key, 0) + 1
        for key, n in by_book.items():
            lines.append(
                "%d of these %d files are byte-identical to files in '%s'."
                % (n, total, key))
        return lines

    def _use_author_variant(self, variant):
        """Addendum E: adopt the existing author spelling, then rebuild
        the review so the destination preview and filing use it."""
        if self._author_field is not None:
            self._author_field.set_text(variant)
        self._build_review()

    def _review_back(self):
        chapters = (self._book or {}).get("chapters") or []
        if len(chapters) <= 1:
            self.stack.setCurrentWidget(self._screen1)
        else:
            self.stack.setCurrentWidget(self._screen2)

    def _on_add_clicked(self):
        n = len(self._plan)
        if not self._plan:
            QMessageBox.warning(self, "Add to library",
                                "Nothing to file: the destination plan is empty.")
            return
        library_root = (self._cfg.get("library_root") or "").strip()
        verb = "Move" if (self._cfg.get("file_mode") or "move") == "move" \
            else "Copy"
        answer = QMessageBox.question(
            self, "Add to library",
            "%s %d file%s to %s?\n\nThis cannot be undone."
            % (verb, n, "" if n == 1 else "s", library_root),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._add_btn.setEnabled(False)
        self.status_message.emit("Filing %d file%s\u2026"
                                 % (n, "" if n == 1 else "s"))
        self._file_worker = FileWorker(
            self._plan, self._db_path, self._filing,
            self._cover_bytes, self._cover_cache_dir,
            file_mode=(self._cfg.get("file_mode") or "move"), parent=self)
        self._file_worker.finished.connect(self._on_file_finished)
        self._file_worker.error.connect(self._on_file_error)
        self._file_worker.start()

    def _on_file_finished(self, book_id, cover_failures, folder_report):
        self._finish_worker(self._file_worker)
        self._file_worker = None
        detail = "The book was added to your library."
        if cover_failures:
            detail += ("\n\nCover art could not be embedded into "
                       "%d file(s):\n- %s"
                       % (len(cover_failures), "\n- ".join(cover_failures)))
        folder_report = folder_report or {}
        removed = folder_report.get("removed") or []
        kept = folder_report.get("kept") or {}
        if removed:
            detail += ("\n\nEmptied source folder removed:\n- %s"
                       % "\n- ".join(removed))
        if kept:
            bits = []
            for d, names in kept.items():
                shown = ", ".join(names[:8])
                if len(names) > 8:
                    shown += ", \u2026 (%d more)" % (len(names) - 8)
                bits.append("%s\n  (kept: %s)" % (d, shown))
            detail += ("\n\nSource folder kept - not empty:\n- %s"
                       % "\n- ".join(bits))
        QMessageBox.information(self, "Added to library", detail)
        self.status_message.emit("Book added to the library.")
        self.book_filed.emit(book_id)
        self.reset()

    def _on_file_error(self, message):
        self._finish_worker(self._file_worker)
        self._file_worker = None
        if hasattr(self, "_add_btn"):
            self._add_btn.setEnabled(True)
        QMessageBox.critical(self, "Filing failed",
                             "The book was NOT added:\n%s" % message)
        self.status_message.emit("Filing failed - nothing was filed.")
