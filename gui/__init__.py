"""PySide6 GUI for the Audiobook Organizer.

The GUI never touches files directly: every rename/move/delete goes
through the backend's apply_*/undo_* functions, each behind an explicit
user confirmation.
"""
