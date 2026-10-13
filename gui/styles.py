"""Dark theme stylesheet for the Audiobook Organizer."""

ACCENT = "#4d9fff"
ACCENT_DARK = "#2f6fd0"
BG = "#1e1e1e"
BG_LIGHT = "#2a2a2a"
BG_LIGHTER = "#333333"
TEXT = "#e0e0e0"
TEXT_DIM = "#a0a0a0"
BORDER = "#3d3d3d"

DARK_QSS = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background-color: {BG};
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background-color: {BG};
}}
QTabBar::tab {{
    background-color: {BG_LIGHT};
    color: {TEXT_DIM};
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background-color: {BG_LIGHTER};
    color: {TEXT};
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}
QPushButton {{
    background-color: {BG_LIGHTER};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background-color: #3d3d3d;
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: #2f2f2f;
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    background-color: {BG_LIGHT};
}}
QPushButton#confirmButton {{
    background-color: {ACCENT_DARK};
    color: white;
    font-weight: bold;
    font-size: 14px;
    padding: 10px 20px;
}}
QPushButton#confirmButton:hover {{
    background-color: {ACCENT};
}}
QPushButton#confirmButton:disabled {{
    background-color: {BG_LIGHT};
    color: {TEXT_DIM};
}}
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {BG_LIGHT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {ACCENT_DARK};
}}
QLineEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox QAbstractItemView {{
    background-color: {BG_LIGHT};
    color: {TEXT};
    selection-background-color: {ACCENT_DARK};
}}
QTableWidget, QTableView, QTreeWidget, QListWidget {{
    background-color: {BG_LIGHT};
    alternate-background-color: #242424;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    gridline-color: {BORDER};
    selection-background-color: {ACCENT_DARK};
    selection-color: white;
}}
QHeaderView::section {{
    background-color: {BG_LIGHTER};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px;
    font-weight: bold;
}}
QLabel {{
    color: {TEXT};
}}
QLabel#dimLabel {{
    color: {TEXT_DIM};
}}
QLabel#sectionHeader {{
    color: {ACCENT};
    font-weight: bold;
    font-size: 14px;
}}
QSplitter::handle {{
    background-color: {BORDER};
}}
QSplitter::handle:horizontal {{
    width: 3px;
}}
QSplitter::handle:vertical {{
    height: 3px;
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {BG};
    border: none;
    width: 12px;
    height: 12px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background-color: {BG_LIGHTER};
    border-radius: 6px;
    min-height: 20px;
    min-width: 20px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}
QSlider::groove:horizontal {{
    background-color: {BG_LIGHTER};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background-color: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}}
QCheckBox {{
    color: {TEXT};
    spacing: 6px;
}}
QToolBar {{
    background-color: {BG};
    border: none;
    spacing: 6px;
    padding: 4px;
}}
QStatusBar {{
    background-color: {BG_LIGHT};
    color: {TEXT_DIM};
}}
QMessageBox {{
    background-color: {BG};
}}
QToolTip {{
    background-color: {BG_LIGHTER};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
"""
