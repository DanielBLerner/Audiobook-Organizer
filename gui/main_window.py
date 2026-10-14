"""Main window: Library + Add tabs, Settings menu, status bar.

Constructed as MainWindow(db, config, cover_cache_dir):
  db               - a LibraryDB instance (used in the GUI thread)
  config           - the settings dict (library_root, file_mode, ...)
  cover_cache_dir  - <library_root>/.audiobook_organizer/covers/

First-run setup is handled by main.py before this window is created;
the Settings menu reopens the same wizard for later changes.
"""

import os

from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
)

import config as config_module

from .add_flow import AddFlowWidget
from .edit_page import EditPage
from .library_page import LibraryPage
from .setup_wizard import SetupWizard


class MainWindow(QMainWindow):
    def __init__(self, db, cfg, cover_cache_dir, parent=None):
        super().__init__(parent)
        self._db = db
        self._cfg = cfg
        self._cover_cache_dir = cover_cache_dir
        # Workers open their own LibraryDB connection on this path so the
        # GUI-thread db instance is never touched from a worker thread.
        self._db_path = os.path.join(
            (cfg.get("library_root") or "").strip(),
            ".audiobook_organizer", "library.db")

        self.setWindowTitle("AudiobookOrganizer")
        self.resize(1100, 750)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.library_page = LibraryPage(db, cfg, cover_cache_dir, self)
        self.add_flow = AddFlowWidget(db, self._db_path, cfg,
                                      cover_cache_dir, self)
        self.tabs.addTab(self.library_page, "Library")
        self.tabs.addTab(self.add_flow, "Add")

        # -- menu ------------------------------------------------------
        settings_menu = self.menuBar().addMenu("Settings")
        settings_action = settings_menu.addAction("Library settings\u2026")
        settings_action.triggered.connect(self._open_settings)

        # -- status bar --------------------------------------------------
        self.statusBar().showMessage("Ready")

        # -- wiring ------------------------------------------------------
        self.library_page.edit_requested.connect(self._open_edit)
        self.library_page.status_message.connect(self._show_status)
        self.add_flow.book_filed.connect(self._on_book_filed)
        self.add_flow.status_message.connect(self._show_status)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------
    def _show_status(self, message):
        self.statusBar().showMessage(message, 8000)

    def _on_tab_changed(self, index):
        if self.tabs.widget(index) is self.library_page:
            self.library_page.refresh()

    def _on_book_filed(self, _book_id):
        self.library_page.refresh()
        self.tabs.setCurrentWidget(self.library_page)

    def _open_edit(self, book_id):
        dlg = EditPage(self._db, self._cfg, self._cover_cache_dir,
                       book_id, self)
        dlg.book_saved.connect(
            lambda _bid: (self.library_page.refresh(),
                          self._show_status("Changes saved.")))
        dlg.book_deleted.connect(
            lambda _bid: (self.library_page.refresh(),
                          self._show_status("Book deleted.")))
        dlg.exec()

    def _open_settings(self):
        old_root = (self._cfg.get("library_root") or "").strip()
        wiz = SetupWizard(self._cfg, self)
        if wiz.exec() != wiz.Accepted:
            return
        new_cfg = wiz.result_config()
        self._cfg.update(new_cfg)
        try:
            config_module.save(self._cfg)
        except Exception as exc:
            self._show_status("Settings could not be saved: %s" % exc)
            return
        new_root = (self._cfg.get("library_root") or "").strip()
        if new_root != old_root:
            self._show_status(
                "Library location changed - restart the app to use the "
                "new library.")
        else:
            self._show_status("Settings saved.")
