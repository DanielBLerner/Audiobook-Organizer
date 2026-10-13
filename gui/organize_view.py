"""Organize tab: move preview, confirm button, undo history.

This tab never moves files itself. The Confirm button asks for explicit
confirmation first; the main window then runs the move in a worker
thread. Undo reverses the most recent confirmed run.
"""

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QListWidget, QAbstractItemView, QMessageBox,
)


class OrganizeTab(QWidget):
    organizeRequested = Signal()
    undoRequested = Signal()
    refreshRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plan = []

        top = QHBoxLayout()
        top.addWidget(QLabel("Preview of the planned moves:"), 1)
        self._refresh_btn = QPushButton("Refresh preview")
        self._refresh_btn.clicked.connect(self.refreshRequested)
        top.addWidget(self._refresh_btn)

        self._note = QLabel()
        self._note.setObjectName("dimLabel")
        self._note.setWordWrap(True)

        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Current path", "New path"])
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._table.verticalHeader().setVisible(False)

        self._confirm_btn = QPushButton("Confirm && Organize")
        self._confirm_btn.setObjectName("confirmButton")
        self._confirm_btn.clicked.connect(self._on_confirm_clicked)

        undo_row = QHBoxLayout()
        undo_row.addWidget(QLabel("Undo history:"), 1)
        self._undo_btn = QPushButton("Undo last")
        self._undo_btn.clicked.connect(self._on_undo_clicked)
        undo_row.addWidget(self._undo_btn)

        self._undo_list = QListWidget()
        self._undo_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._undo_list.setMaximumHeight(140)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._note)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._confirm_btn)
        layout.addLayout(undo_row)
        layout.addWidget(self._undo_list)

    # -- public ------------------------------------------------------

    def set_plan(self, plan, outside_count=0):
        """Show the (src, dst_rel) plan computed by the main window."""
        self._plan = list(plan)
        if outside_count:
            self._note.setText(
                f"{outside_count} book(s) live outside the library folder "
                "and are not included in this plan.")
        else:
            self._note.setText("")
        table = self._table
        table.setRowCount(len(self._plan))
        for i, (src, dst) in enumerate(self._plan):
            table.setItem(i, 0, QTableWidgetItem(src))
            table.setItem(i, 1, QTableWidgetItem(dst))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        self._confirm_btn.setEnabled(bool(self._plan))
        self._confirm_btn.setText(
            f"Confirm && Organize ({len(self._plan)} files)"
            if self._plan else "Confirm && Organize")

    def set_undo_logs(self, logs):
        self._undo_list.clear()
        for entry in logs:
            self._undo_list.addItem(
                f"{entry['time']} — {entry['moves']} moves")
        self._undo_btn.setEnabled(bool(logs))

    def plan(self):
        return list(self._plan)

    # -- slots -------------------------------------------------------

    @Slot()
    def _on_confirm_clicked(self):
        if not self._plan:
            return
        answer = QMessageBox.question(
            self, "Confirm organize",
            f"Move {len(self._plan)} files into Author/Book folders?\n"
            "This can be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.organizeRequested.emit()

    @Slot()
    def _on_undo_clicked(self):
        answer = QMessageBox.question(
            self, "Confirm undo",
            "Reverse the most recent organize/title-fix run and move "
            "the files back?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.undoRequested.emit()
