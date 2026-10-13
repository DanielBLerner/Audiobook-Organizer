"""Library tab: toolbar, sortable book table, detail panel."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QPixmap, QColor, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QToolBar, QLineEdit, QComboBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QSplitter, QLabel,
    QAbstractItemView, QPushButton,
)

from gui.detail_panel import DetailPanel

SORT_FIELDS = [
    ("Title", "title"),
    ("Author", "author"),
    ("Book", "book"),
    ("Date added", "date_added"),
    ("Kind", "kind"),
    ("Language", "lang"),
]

COLUMNS = ["", "Title", "Author", "Book", "Kind", "Chapters", "Tags",
           "Date added", "Language"]
COL_COVER, COL_TITLE = 0, 1

THUMB = 44


class LibraryTab(QWidget):
    """Book table + detail panel. Emits scan requests to the main window."""

    selectFolderRequested = Signal()
    rescanRequested = Signal()
    importFolderRequested = Signal()

    def __init__(self, db, covers_dir, parent=None):
        super().__init__(parent)
        self._db = db
        self._covers_dir = Path(covers_dir)
        self._no_cover_thumb = QPixmap(THUMB, THUMB)
        self._no_cover_thumb.fill(QColor("#333333"))

        toolbar = QToolBar()
        select_btn = QPushButton("Select library folder…")
        select_btn.clicked.connect(self.selectFolderRequested)
        rescan_btn = QPushButton("Rescan")
        rescan_btn.clicked.connect(self.rescanRequested)
        import_btn = QPushButton("Import folder…")
        import_btn.clicked.connect(self.importFolderRequested)
        toolbar.addWidget(select_btn)
        toolbar.addWidget(rescan_btn)
        toolbar.addWidget(import_btn)
        toolbar.addSeparator()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search title / author / book…")
        self._search.setClearButtonEnabled(True)
        toolbar.addWidget(QLabel("Search:"))
        toolbar.addWidget(self._search)

        self._tag_combo = QComboBox()
        self._tag_combo.setMinimumWidth(140)
        toolbar.addWidget(QLabel("Tag:"))
        toolbar.addWidget(self._tag_combo)

        self._sort_combo = QComboBox()
        for label, _key in SORT_FIELDS:
            self._sort_combo.addItem(label)
        toolbar.addWidget(QLabel("Sort:"))
        toolbar.addWidget(self._sort_combo)
        self._sort_desc = QCheckBox("↓")
        self._sort_desc.setToolTip("Sort descending")
        toolbar.addWidget(self._sort_desc)

        self._table = QTableWidget()
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(THUMB + 8)
        self._table.itemSelectionChanged.connect(self._on_selection)

        self._detail = DetailPanel(db, covers_dir)
        self._detail.coverChanged.connect(self.refresh)
        self._detail.tagsChanged.connect(self.refresh_tags)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._table)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(toolbar)
        layout.addWidget(splitter, 1)

        # Debounced search so typing doesn't re-query on every keystroke.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(350)
        self._search_timer.timeout.connect(self.refresh)
        self._search.textChanged.connect(
            lambda _text: self._search_timer.start())
        self._tag_combo.currentIndexChanged.connect(self.refresh)
        self._sort_combo.currentIndexChanged.connect(self.refresh)
        self._sort_desc.toggled.connect(self.refresh)

        self.refresh_tags()

    # -- public ------------------------------------------------------

    @property
    def detail_panel(self):
        return self._detail

    def refresh_tags(self):
        current = self._tag_combo.currentData()
        self._tag_combo.blockSignals(True)
        self._tag_combo.clear()
        self._tag_combo.addItem("(all tags)", "")
        for tag in self._db.all_tags():
            self._tag_combo.addItem(tag, tag)
        if current:
            idx = self._tag_combo.findData(current)
            if idx >= 0:
                self._tag_combo.setCurrentIndex(idx)
        self._tag_combo.blockSignals(False)

    def refresh(self):
        keep_selected = self.selected_book_id()
        search = self._search.text().strip()
        tag = self._tag_combo.currentData() or ""
        order_by = SORT_FIELDS[self._sort_combo.currentIndex()][1]
        order_desc = self._sort_desc.isChecked()
        books = self._db.list_books(search=search, tag=tag,
                                    order_by=order_by,
                                    order_desc=order_desc)
        table = self._table
        table.setSortingEnabled(False)
        table.setRowCount(len(books))
        for row, book in enumerate(books):
            cover_item = QTableWidgetItem()
            cover_item.setData(Qt.UserRole, book["id"])
            cover_item.setIcon(QIcon(self._thumb(book)))
            cover_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            table.setItem(row, COL_COVER, cover_item)

            values = [
                book.get("title") or "",
                book.get("author") or "",
                book.get("book") or "",
                book.get("kind") or "",
                str(book.get("chapter_count") or 1),
                ", ".join(book.get("tags") or []),
                book.get("date_added") or "",
                book.get("lang") or "",
            ]
            for col, text in enumerate(values, start=1):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                table.setItem(row, col, item)
        table.setSortingEnabled(True)
        table.resizeColumnToContents(COL_COVER)
        table.horizontalHeader().setStretchLastSection(True)
        if keep_selected is not None:
            for row in range(table.rowCount()):
                item = table.item(row, COL_COVER)
                if item and item.data(Qt.UserRole) == keep_selected:
                    table.selectRow(row)
                    break

    def selected_book_id(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), COL_COVER)
        return item.data(Qt.UserRole) if item else None

    # -- private -----------------------------------------------------

    def _thumb(self, book):
        cover_path = book.get("cover_path")
        if cover_path and Path(cover_path).exists():
            pix = QPixmap(str(cover_path))
            if not pix.isNull():
                return pix.scaled(THUMB, THUMB, Qt.KeepAspectRatio,
                                  Qt.SmoothTransformation)
        return self._no_cover_thumb

    @Slot()
    def _on_selection(self):
        book_id = self.selected_book_id()
        if book_id is not None:
            self._detail.show_book(book_id)
