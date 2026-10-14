"""Library page: search / tag filter / sort, book rows, open-in-Explorer,
and the ⋮ button that opens the edit page."""

import html
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .fields import TagLineEdit

SORT_OPTIONS = [
    ("Date added (newest)", "date_added", True),
    ("Date added (oldest)", "date_added", False),
    ("Title A–Z", "title", False),
    ("Author A–Z", "author", False),
]

THUMB = 64


class _BookRow(QWidget):
    """One library row. Emits edit_requested via the page's signal."""

    def __init__(self, book, on_edit, parent=None):
        super().__init__(parent)
        book_id = book.get("id")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        more_btn = QPushButton("⋮")
        more_btn.setFixedWidth(36)
        more_btn.setToolTip("Edit this book")
        more_btn.clicked.connect(lambda _c=False, bid=book_id: on_edit(bid))
        layout.addWidget(more_btn)

        thumb = QLabel()
        thumb.setFixedSize(THUMB, THUMB)
        thumb.setAlignment(Qt.AlignCenter)
        cover_path = book.get("cover_path")
        pix = QPixmap(cover_path) if cover_path else QPixmap()
        if not pix.isNull():
            thumb.setPixmap(pix.scaled(
                THUMB, THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            thumb.setText("no cover")
            thumb.setObjectName("muted")
        layout.addWidget(thumb)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        series = (book.get("series") or "").strip()
        if series:
            series_label = QLabel("<b>%s</b>" % html.escape(series))
            text_col.addWidget(series_label)
        title_label = QLabel(html.escape(book.get("title") or "Untitled"))
        text_col.addWidget(title_label)
        author_label = QLabel(html.escape(book.get("author") or "Unknown author"))
        author_label.setObjectName("muted")
        text_col.addWidget(author_label)
        tags = book.get("tags") or []
        if tags:
            tags_label = QLabel(
                '<span style="color:#8a8a8a">%s</span>'
                % html.escape(", ".join(tags)))
        else:
            tags_label = QLabel("no tags")
            tags_label.setObjectName("muted")
        text_col.addWidget(tags_label)
        layout.addLayout(text_col, 1)

        date_label = QLabel(str(book.get("date_added") or "")[:10])
        date_label.setObjectName("muted")
        date_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(date_label)


class LibraryPage(QWidget):
    """The Library tab."""

    edit_requested = Signal(int)  # book id -> open the edit page
    status_message = Signal(str)

    def __init__(self, db, cfg, cover_cache_dir, parent=None):
        super().__init__(parent)
        self._db = db
        self._cfg = cfg
        self._cover_cache_dir = cover_cache_dir
        self._books = {}  # id -> book dict of the current listing

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # -- top bar ------------------------------------------------
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search title, author, series\u2026")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(lambda _t: self.refresh())
        bar.addWidget(self.search_edit, 2)

        self.tag_filter = TagLineEdit()
        self.tag_filter.setPlaceholderText("Filter by tags\u2026")
        self.tag_filter.textChanged.connect(lambda _t: self.refresh())
        bar.addWidget(self.tag_filter, 2)

        self.sort_combo = QComboBox()
        for label, _ob, _od in SORT_OPTIONS:
            self.sort_combo.addItem(label)
        self.sort_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        bar.addWidget(self.sort_combo)

        self.count_label = QLabel("0 books")
        self.count_label.setObjectName("muted")
        bar.addWidget(self.count_label)

        layout.addLayout(bar)

        # -- list / empty state --------------------------------------
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemClicked.connect(self._on_row_clicked)
        layout.addWidget(self.list, 1)

        self.empty_label = QLabel(
            "Your library is empty.<br><br>"
            "Head to the <b>Add</b> tab to file your first book.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label, 1)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        """Re-query and rebuild the row list."""
        _label, order_by, order_desc = SORT_OPTIONS[
            self.sort_combo.currentIndex()]
        search = self.search_edit.text().strip()
        try:
            books = self._db.list_books(
                search=search, order_by=order_by, order_desc=order_desc) or []
        except Exception as exc:
            self.status_message.emit("Could not load library: %s" % exc)
            books = []

        wanted = [t.strip().lower() for t in
                  self.tag_filter.text().split(",") if t.strip()]
        if wanted:
            books = [b for b in books
                     if all(t in [str(x).lower()
                                  for x in (b.get("tags") or [])]
                            for t in wanted)]

        try:
            self.tag_filter.set_tag_list(self._db.all_tags())
        except Exception:
            pass

        self._books = {b.get("id"): b for b in books}
        self.list.clear()
        for book in books:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, book.get("id"))
            row = _BookRow(book, self._on_edit_clicked)
            item.setSizeHint(QSize(0, 84))  # width stretches; fixed row height
            self.list.addItem(item)
            self.list.setItemWidget(item, row)

        n = len(books)
        self.count_label.setText("%d book%s" % (n, "" if n == 1 else "s"))

        filter_active = bool(search or wanted)
        self.empty_label.setVisible(n == 0)
        self.list.setVisible(n > 0)
        if n == 0:
            if filter_active:
                self.empty_label.setText("No books match your search.")
            else:
                self.empty_label.setText(
                    "Your library is empty.<br><br>"
                    "Head to the <b>Add</b> tab to file your first book.")

    # ------------------------------------------------------------------
    def _on_edit_clicked(self, book_id):
        if book_id is not None:
            self.edit_requested.emit(book_id)

    def _on_row_clicked(self, item):
        """Row click (not on ⋮) -> open the book's folder in Explorer."""
        book_id = item.data(Qt.UserRole)
        book = self._books.get(book_id)
        if not book:
            return
        library_path = book.get("library_path") or ""
        folder = str(Path(library_path).parent) if library_path else ""
        if folder and Path(folder).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            self.status_message.emit(
                "Book folder not found: %s" % (folder or library_path))
