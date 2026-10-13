"""Audiobook Organizer - desktop app entry point.

Run with:  py -3.12 main.py        (after pip install -r requirements.txt)
"""

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from backend import (
    AUDIO_EXTS,
    EBOOK_EXTS,
    SUPPORTED_EXTS,
    scan,
    scan_stats,
    find_duplicates,
    build_plan,
    apply_organize,
    apply_title_fixes,
    undo_last,
    list_undo_logs,
)
from db import LibraryDB
from gui.main_window import MainWindow
from gui.styles import DARK_QSS

APP_NAME = "AudiobookOrganizer"
DEFAULT_LIBRARY = Path(r"D:\Media\1. Audiobooks\New")


def app_data_dir():
    """Per-user data dir: %APPDATA%/AudiobookOrganizer on Windows,
    ~/.audiobook_organizer elsewhere."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        data = base / APP_NAME
    else:
        data = Path.home() / ".audiobook_organizer"
    (data / "covers").mkdir(parents=True, exist_ok=True)
    return data


def resolve_library_root(settings):
    saved = settings.value("library_root", "")
    if saved and Path(saved).exists():
        return str(Path(saved))
    if DEFAULT_LIBRARY.exists():
        return str(DEFAULT_LIBRARY)
    return str(Path.home())


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setStyleSheet(DARK_QSS)

    data_dir = app_data_dir()
    db = LibraryDB(data_dir / "library.db")

    settings = QSettings(APP_NAME, APP_NAME)
    library_root = resolve_library_root(settings)
    # Persist whatever we resolved so the next launch agrees.
    settings.setValue("library_root", library_root)

    window = MainWindow(db, data_dir, library_root)
    window.show()

    exit_code = app.exec()
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
