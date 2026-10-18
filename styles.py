"""Dark theme stylesheet for AudiobookOrganizer v2.

StateField outline colors are driven by the dynamic Qt property
``fstate`` on the inner QLineEdit:

    "auto"   (blue)  - auto-filled guess, untouched by the user
    "empty"  (gray)  - empty field
    "edited" (green) - edited by the user

After changing the property at runtime, call refresh_style(widget) so
the new selector matches are applied.
"""

DARK_QSS = """
QWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #1e1e1e;
}
QLabel {
    background: transparent;
}
QLabel#muted {
    color: #9a9a9a;
}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QDateEdit {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 5px;
    selection-background-color: #2a5a8a;
}
QLineEdit[fstate="auto"], QDateEdit[fstate="auto"] {
    border: 2px solid #4aa3ff;
}
QLineEdit[fstate="empty"], QDateEdit[fstate="empty"] {
    border: 2px solid #6e6e6e;
}
QLineEdit[fstate="edited"], QDateEdit[fstate="edited"] {
    border: 2px solid #3ecf5a;
}
QLineEdit:disabled {
    color: #7a7a7a;
}
QComboBox QAbstractItemView {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    selection-background-color: #2a5a8a;
}
QPushButton {
    background-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #3a3a3a;
    border-color: #4aa3ff;
}
QPushButton:pressed {
    background-color: #1a1a1a;
}
QPushButton:disabled {
    color: #7a7a7a;
    background-color: #252526;
}
QPushButton#danger {
    background-color: #5a2020;
    border-color: #8a3030;
}
QPushButton#danger:hover {
    background-color: #6e2828;
    border-color: #c05050;
}
QListWidget {
    background-color: #1e1e1e;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    outline: none;
}
QListWidget::item {
    border-bottom: 1px solid #2a2a2a;
}
QListWidget::item:selected {
    background-color: #2a4a6a;
}
QListWidget::item:hover {
    background-color: #2a2a2a;
}
QTabWidget::pane {
    border: 1px solid #3c3c3c;
    border-radius: 4px;
}
QTabBar::tab {
    background: #252526;
    color: #b0b0b0;
    padding: 8px 20px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #1e1e1e;
    color: #ffffff;
    border-bottom: 2px solid #4aa3ff;
}
QMenuBar {
    background-color: #252526;
}
QMenuBar::item:selected {
    background-color: #3a3a3a;
}
QMenu {
    background-color: #252526;
    border: 1px solid #3c3c3c;
}
QMenu::item:selected {
    background-color: #2a5a8a;
}
QStatusBar {
    background-color: #252526;
    color: #b0b0b0;
}
QScrollBar:vertical {
    background: #1e1e1e;
    width: 12px;
}
QScrollBar::handle:vertical {
    background: #4a4a4a;
    min-height: 20px;
    border-radius: 6px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #1e1e1e;
    height: 12px;
}
QScrollBar::handle:horizontal {
    background: #4a4a4a;
    min-width: 20px;
    border-radius: 6px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QSlider::groove:horizontal {
    background: #3c3c3c;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #4aa3ff;
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
QToolTip {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
}
QGroupBox {
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: bold;
}
"""


def refresh_style(widget):
    """Re-apply the stylesheet to a widget whose dynamic properties
    (e.g. ``fstate``) changed, so property selectors re-match."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
