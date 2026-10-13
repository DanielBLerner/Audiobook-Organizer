"""Duplicates tab: exact (hash) and near (same author+book) groups.

Detection is slow on big libraries (it hashes files), so it runs in a
worker thread and only when asked: once when the tab is first shown,
then on Refresh.
"""

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QAbstractItemView,
)

from gui.workers import DuplicatesWorker


class DuplicatesTab(QWidget):
    """Shows duplicate groups; never deletes anything."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._worker = None
        self._ran_once = False

        top = QHBoxLayout()
        self._status = QLabel("Not scanned yet.")
        self._status.setObjectName("dimLabel")
        self._refresh_btn = QPushButton("Find duplicates")
        self._refresh_btn.clicked.connect(self.run_detection)
        top.addWidget(self._status, 1)
        top.addWidget(self._refresh_btn)

        self._exact_label = QLabel("Exact duplicates (identical files)")
        self._exact_label.setObjectName("sectionHeader")
        self._exact_tree = QTreeWidget()
        self._exact_tree.setHeaderLabels(["File path"])
        self._exact_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)

        self._near_label = QLabel("Near duplicates (same author + book)")
        self._near_label.setObjectName("sectionHeader")
        self._near_tree = QTreeWidget()
        self._near_tree.setHeaderLabels(["File path"])
        self._near_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._exact_label)
        layout.addWidget(self._exact_tree, 1)
        layout.addWidget(self._near_label)
        layout.addWidget(self._near_tree, 1)

    # -- public ------------------------------------------------------

    def mark_stale(self):
        """Forget previous results; re-detect next time the tab is shown."""
        self._ran_once = False

    def maybe_run(self):
        """Run detection once, the first time the tab is shown."""
        if not self._ran_once and self._worker is None:
            self.run_detection()

    @Slot()
    def run_detection(self):
        if self._worker is not None and self._worker.isRunning():
            return
        books = self._db.list_books()
        self._status.setText(f"Checking {len(books)} files…")
        self._refresh_btn.setEnabled(False)
        self._worker = DuplicatesWorker(books, self)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    # -- slots -------------------------------------------------------

    @Slot(dict)
    def _on_done(self, result):
        self._ran_once = True
        self._refresh_btn.setEnabled(True)
        exact = result.get("exact", [])
        near = result.get("near", [])
        self._fill(self._exact_tree, exact, "identical files")
        self._fill(self._near_tree, near, "files")
        self._status.setText(
            f"{len(exact)} exact group(s), {len(near)} near group(s).")
        self._worker = None

    @Slot(str)
    def _on_error(self, msg):
        self._refresh_btn.setEnabled(True)
        self._status.setText(msg)
        self._worker = None

    # -- private -----------------------------------------------------

    def _fill(self, tree, groups, unit):
        tree.clear()
        for group in groups:
            first = group[0]
            header = (f"{first.get('author', '')} — {first.get('book', '')} "
                      f"({len(group)} {unit})")
            top = QTreeWidgetItem([header])
            top.setExpanded(False)
            for item in group:
                child = QTreeWidgetItem([item.get("path", "")])
                child.setToolTip(0, item.get("path", ""))
                top.addChild(child)
            tree.addTopLevelItem(top)
        tree.resizeColumnToContents(0)
