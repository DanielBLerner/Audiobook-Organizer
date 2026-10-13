"""Main window: tabbed interface wiring the backend to the GUI."""

import json
import os
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, Slot
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QFileDialog, QMessageBox,
)

from backend import build_plan, list_undo_logs

from gui.library_view import LibraryTab
from gui.scan_view import ReportTab
from gui.duplicates_view import DuplicatesTab
from gui.organize_view import OrganizeTab
from gui.workers import ScanWorker, OrganizeWorker, UndoWorker


class MainWindow(QMainWindow):
    def __init__(self, db, app_data_dir, library_root, parent=None):
        super().__init__(parent)
        self._db = db
        self._app_data = Path(app_data_dir)
        self._covers_dir = self._app_data / "covers"
        self._covers_dir.mkdir(parents=True, exist_ok=True)
        self._library_root = str(library_root)
        self._settings = QSettings("AudiobookOrganizer", "AudiobookOrganizer")

        self.setWindowTitle("Audiobook Organizer")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self._library_tab = LibraryTab(db, self._covers_dir)
        self._report_tab = ReportTab(db, self._get_root)
        self._duplicates_tab = DuplicatesTab(db)
        self._organize_tab = OrganizeTab()

        self._tabs = QTabWidget()
        self._tabs.addTab(self._library_tab, "Library")
        self._tabs.addTab(self._report_tab, "Report")
        self._tabs.addTab(self._duplicates_tab, "Duplicates")
        self._tabs.addTab(self._organize_tab, "Organize")
        self.setCentralWidget(self._tabs)

        self.statusBar().showMessage(
            f"Library folder: {self._library_root}")

        # Library toolbar actions.
        self._library_tab.selectFolderRequested.connect(self._select_folder)
        self._library_tab.rescanRequested.connect(self._rescan)
        self._library_tab.importFolderRequested.connect(self._import_folder)
        self._library_tab.detail_panel.statusMessage.connect(
            self.statusBar().showMessage)

        # Organize actions.
        self._organize_tab.organizeRequested.connect(self._start_organize)
        self._organize_tab.undoRequested.connect(self._start_undo)
        self._organize_tab.refreshRequested.connect(self._refresh_organize)

        # Lazy duplicate detection when the tab is first shown.
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._scan_worker = None
        self._organize_worker = None
        self._undo_worker = None
        self._pending_scans = []

        self._library_tab.refresh()
        self._report_tab.refresh()
        self._refresh_organize()

    # -- library root ------------------------------------------------

    def _get_root(self):
        return self._library_root

    def _set_root(self, root):
        self._library_root = str(root)
        self._settings.setValue("library_root", self._library_root)
        self.statusBar().showMessage(
            f"Library folder: {self._library_root}")
        self._refresh_organize()

    # -- scanning ----------------------------------------------------

    @Slot()
    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select library folder", self._library_root)
        if folder:
            self._set_root(folder)
            self._start_scan(folder)

    @Slot()
    def _rescan(self):
        self._start_scan(self._library_root)

    @Slot()
    def _import_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Import folder into library", self._library_root)
        if folder:
            self._start_scan(folder)

    def _start_scan(self, root):
        if self._scan_worker is not None and self._scan_worker.isRunning():
            self.statusBar().showMessage("A scan is already running…")
            return
        self._scan_worker = ScanWorker(root, self._db, self._covers_dir,
                                       self)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.done.connect(self._on_scan_done)
        self._scan_worker.error.connect(
            lambda msg: self._on_worker_error("scan", msg))
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_worker.start()
        self.statusBar().showMessage(f"Scanning {root}…")

    @Slot(int, int)
    def _on_scan_progress(self, done, total):
        if total <= 0:
            self.statusBar().showMessage("Scanning files…")
        else:
            self.statusBar().showMessage(
                f"Importing… {done}/{total} files")

    @Slot(int, int)
    def _on_scan_done(self, new_count, total):
        self._scan_worker = None
        self.statusBar().showMessage(
            f"Scan complete: {total} files, {new_count} new books added.")
        self._library_tab.refresh_tags()
        self._library_tab.refresh()
        self._report_tab.refresh()
        self._refresh_organize()
        # Run the next queued scan (e.g. several dropped folders).
        if self._pending_scans:
            self._start_scan(self._pending_scans.pop(0))

    @Slot(str, str)
    def _on_worker_error(self, which, msg):
        if which == "scan":
            self._scan_worker = None
        elif which == "organize":
            self._organize_worker = None
        elif which == "undo":
            self._undo_worker = None
        QMessageBox.warning(self, "Something went wrong", msg)
        if self._pending_scans:
            self._start_scan(self._pending_scans.pop(0))

    # -- organize / undo ---------------------------------------------

    @staticmethod
    def _is_under(path, root):
        """True if path is inside root (same drive, no ValueError)."""
        try:
            root_n = os.path.normcase(os.path.abspath(root))
            path_n = os.path.normcase(os.path.abspath(path))
            return os.path.commonpath([root_n, path_n]) == root_n
        except (ValueError, OSError):
            return False

    def _refresh_organize(self):
        books = [b for b in self._db.list_books()
                 if b.get("path") and Path(b["path"]).exists()]
        # Organize only moves files inside the library folder: the undo
        # log stores paths relative to the root, so files elsewhere
        # would break it.
        inside = [b for b in books
                  if self._is_under(b["path"], self._library_root)]
        outside = len(books) - len(inside)
        try:
            plan = build_plan(inside)
        except Exception as e:
            plan = []
            self.statusBar().showMessage(f"Couldn't build preview: {e}")
        self._organize_tab.set_plan(plan, outside_count=outside)
        try:
            logs = list_undo_logs(self._library_root)
        except Exception:
            logs = []
        self._organize_tab.set_undo_logs(logs)

    @Slot()
    def _start_organize(self):
        if (self._organize_worker is not None
                and self._organize_worker.isRunning()):
            return
        plan = self._organize_tab.plan()
        if not plan:
            return
        self._organize_worker = OrganizeWorker(self._library_root, plan,
                                               self)
        self._organize_worker.done.connect(self._on_organize_done)
        self._organize_worker.error.connect(
            lambda msg: self._on_worker_error("organize", msg))
        self._organize_worker.finished.connect(
            self._organize_worker.deleteLater)
        self._organize_worker.start()
        self.statusBar().showMessage(
            f"Moving {len(plan)} files…")

    @Slot(str)
    def _on_organize_done(self, log_path):
        self._organize_worker = None
        root = Path(self._library_root)
        moved = 0
        try:
            entries = json.loads(Path(log_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            entries = []
        for entry in entries:
            old_abs = str(root / entry["from"])
            new_abs = str(root / entry["to"])
            book = self._db.find_by_path(old_abs)
            if book:
                self._db.mark_moved(book["id"], new_abs, entry["to"])
                moved += 1
        pruned = self._db.prune_missing()
        self._duplicates_tab.mark_stale()  # paths changed; re-detect later
        self._library_tab.refresh()
        self._report_tab.refresh()
        self._refresh_organize()
        self.statusBar().showMessage(
            f"Organized {moved} files. Undo log saved "
            f"({Path(log_path).name})."
            + (f" {pruned} missing file(s) removed from the library."
               if pruned else ""))

    @Slot()
    def _start_undo(self):
        if self._undo_worker is not None and self._undo_worker.isRunning():
            return
        logs = list_undo_logs(self._library_root)
        if not logs:
            return
        # Read the newest log BEFORE undoing: undo_last deletes it.
        try:
            self._undo_entries = json.loads(
                Path(logs[0]["path"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._undo_entries = []
        self._undo_worker = UndoWorker(self._library_root, self)
        self._undo_worker.done.connect(self._on_undo_done)
        self._undo_worker.error.connect(
            lambda msg: self._on_worker_error("undo", msg))
        self._undo_worker.finished.connect(self._undo_worker.deleteLater)
        self._undo_worker.start()
        self.statusBar().showMessage("Undoing last organize…")

    @Slot(int)
    def _on_undo_done(self, count):
        self._undo_worker = None
        root = Path(self._library_root)
        for entry in getattr(self, "_undo_entries", []):
            was_abs = str(root / entry["to"])    # where the file was
            back_abs = str(root / entry["from"])  # where it is again
            book = self._db.find_by_path(was_abs)
            if book:
                self._db.mark_moved(book["id"], back_abs, entry["from"])
        self._undo_entries = []
        self._db.prune_missing()
        self._duplicates_tab.mark_stale()
        self._library_tab.refresh()
        self._report_tab.refresh()
        self._refresh_organize()
        self.statusBar().showMessage(f"Undone: {count} file(s) moved back.")

    # -- tabs / drag & drop ------------------------------------------

    @Slot(int)
    def _on_tab_changed(self, index):
        if self._tabs.widget(index) is self._duplicates_tab:
            self._duplicates_tab.maybe_run()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        folders = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local and Path(local).is_dir():
                folders.append(local)
        if not folders:
            event.ignore()
            return
        event.acceptProposedAction()
        answer = QMessageBox.question(
            self, "Import dropped folders",
            f"Scan and import {len(folders)} dropped folder(s) into the "
            f"library?\nThis only reads files; nothing is renamed or moved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._pending_scans.extend(folders)
        if self._scan_worker is None or not self._scan_worker.isRunning():
            self._start_scan(self._pending_scans.pop(0))
