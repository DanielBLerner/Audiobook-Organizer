"""Report tab: scan statistics, quality flags, organization preview."""

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QListWidget, QScrollArea, QAbstractItemView,
)

from backend import scan_stats


def _kv_table(pairs):
    table = QTableWidget()
    table.setColumnCount(2)
    table.setHorizontalHeaderLabels(["", "Count"])
    table.setRowCount(len(pairs))
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.verticalHeader().setVisible(False)
    for row, (key, value) in enumerate(pairs):
        table.setItem(row, 0, QTableWidgetItem(str(key)))
        count_item = QTableWidgetItem(str(value))
        count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        table.setItem(row, 1, count_item)
    table.resizeColumnsToContents()
    table.setMaximumHeight(min(60 + 28 * len(pairs), 320))
    return table


def _section(title):
    label = QLabel(title)
    label.setObjectName("sectionHeader")
    return label


class ReportTab(QWidget):
    """Read-only scan report. Recomputed from the library on refresh."""

    def __init__(self, db, get_root, parent=None):
        super().__init__(parent)
        self._db = db
        self._get_root = get_root  # callable returning the library root str

        header = QHBoxLayout()
        self._summary = QLabel()
        self._summary.setObjectName("dimLabel")
        refresh_btn = QPushButton("Refresh report")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._summary, 1)
        header.addWidget(refresh_btn)

        self._body = QVBoxLayout()
        self._body.setSpacing(10)
        container = QWidget()
        container.setLayout(self._body)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(scroll, 1)

    @Slot()
    def refresh(self):
        books = self._db.list_books()
        stats = scan_stats(books)

        # Clear previous content.
        while self._body.count():
            child = self._body.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._summary.setText(
            f"{stats['total']} files · {stats['books']} books · "
            f"library folder: {self._get_root()}")

        self._body.addWidget(_section("Formats"))
        self._body.addWidget(_kv_table(list(stats["formats"].items())))

        self._body.addWidget(_section("Languages"))
        self._body.addWidget(_kv_table(list(stats["languages"].items())))

        self._body.addWidget(_section("Data quality"))
        quality = QLabel(
            f"Files with embedded tags: {stats['tagged']} of {stats['total']}\n"
            f"Files with mojibake in the name: {stats['mojibake']}")
        quality.setObjectName("dimLabel")
        self._body.addWidget(quality)

        self._body.addWidget(_section("Transliteration suspects"))
        note = QLabel("Flagged for review — never auto-renamed.")
        note.setObjectName("dimLabel")
        self._body.addWidget(note)
        suspects = QListWidget()
        suspects.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        for author, book in stats["suspects"]:
            suspects.addItem(f"{author} — {book}")
        suspects.setMaximumHeight(min(60 + 24 * len(stats["suspects"]), 240))
        self._body.addWidget(suspects)

        self._body.addWidget(_section("Needs review (no tags, unknown author)"))
        review = QListWidget()
        review.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for item in stats["review"]:
            review.addItem(item["rel"])
        review.setMaximumHeight(min(60 + 24 * len(stats["review"]), 240))
        self._body.addWidget(review)
        if stats["review_total"] > len(stats["review"]):
            more = QLabel(f"…and {stats['review_total'] - len(stats['review'])} more")
            more.setObjectName("dimLabel")
            self._body.addWidget(more)

        self._body.addWidget(_section("Organization preview (first 15)"))
        preview = QTableWidget()
        preview.setColumnCount(2)
        preview.setHorizontalHeaderLabels(["Current path", "New path"])
        rows = stats["preview"]
        preview.setRowCount(len(rows))
        preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        preview.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        preview.verticalHeader().setVisible(False)
        for i, (src, dst) in enumerate(rows):
            preview.setItem(i, 0, QTableWidgetItem(src))
            preview.setItem(i, 1, QTableWidgetItem(dst))
        preview.resizeColumnsToContents()
        preview.horizontalHeader().setStretchLastSection(True)
        preview.setMaximumHeight(min(60 + 28 * len(rows), 420))
        self._body.addWidget(preview)
        if stats["preview_total"] > len(rows):
            more = QLabel(
                f"…and {stats['preview_total'] - len(rows)} more")
            more.setObjectName("dimLabel")
            self._body.addWidget(more)

        self._body.addStretch(1)
