"""AudiobookOrganizer v2 - desktop app entry point.

Run from source:  py -3.12 main.py        (after pip install -r requirements.txt)

Any unhandled exception is written to a log file next to the executable
(a lesson from v1, which died with a bare dialog and no log).
"""

import os
import sys
import traceback
from pathlib import Path


def _log_dir():
    """Folder next to the exe (or next to main.py when run from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _install_crash_handler():
    log_file = _log_dir() / "AudiobookOrganizer-crash.log"

    def _hook(exc_type, exc_value, exc_tb):
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("=" * 70 + "\n")
                import datetime
                f.write(datetime.datetime.now().isoformat() + "\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except OSError:
            pass
        # Show the dialog too, pointing at the log.
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                None, "AudiobookOrganizer crashed",
                "Something went wrong.\n\n"
                f"Details were written to:\n{log_file}\n\n"
                "Please share that file when reporting the problem.")
        except Exception:
            pass
        sys.exit(1)

    sys.excepthook = _hook


def main():
    _install_crash_handler()

    from PySide6.QtWidgets import QApplication, QDialog

    import config
    from db import LibraryDB
    from gui.main_window import MainWindow
    from gui.setup_wizard import SetupWizard
    from gui.styles import DARK_QSS

    app = QApplication(sys.argv)
    app.setApplicationName("AudiobookOrganizer")
    app.setOrganizationName("AudiobookOrganizer")
    app.setStyleSheet(DARK_QSS)

    cfg = config.load()
    if not cfg.get("setup_done") or not cfg.get("library_root"):
        wiz = SetupWizard(cfg)
        if wiz.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)  # user closed setup: quit quietly
        cfg = wiz.result_config()
        config.save(cfg)

    library_root = Path(cfg["library_root"])
    library_root.mkdir(parents=True, exist_ok=True)

    # The database lives INSIDE the library folder, so reinstalling or
    # updating the app can never wipe it.
    app_dir = library_root / ".audiobook_organizer"
    app_dir.mkdir(parents=True, exist_ok=True)
    cover_cache = app_dir / "covers"
    cover_cache.mkdir(parents=True, exist_ok=True)

    db = LibraryDB(app_dir / "library.db")

    window = MainWindow(db, cfg, str(cover_cache))
    window.show()

    exit_code = app.exec()
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
