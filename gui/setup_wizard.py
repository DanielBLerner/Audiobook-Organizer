"""First-run setup dialog (also reused as the Settings dialog).

Asks for the library location and the file mode, and shows the naming
pattern as informational text. Constructed with the config dict;
result_config() returns the updated dict after Accept.
"""

import os

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config as config_module


class SetupWizard(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AudiobookOrganizer - Setup")
        self.setMinimumWidth(520)

        cfg = dict(cfg or {})
        self._initial = dict(cfg)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("<b>Where should your audiobook library live?</b>")
        layout.addWidget(title)

        form = QFormLayout()

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        self.library_edit = QLineEdit()
        self.library_edit.setText(
            cfg.get("library_root") or config_module.DEFAULT_LIBRARY)
        self.library_edit.setPlaceholderText(
            config_module.DEFAULT_LIBRARY)
        h.addWidget(self.library_edit, 1)
        browse_btn = QPushButton("Browse\u2026")
        browse_btn.clicked.connect(self._browse)
        h.addWidget(browse_btn)
        form.addRow("Library location:", row)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Move", "move")
        self.mode_combo.addItem("Copy", "copy")
        mode = cfg.get("file_mode") or "move"
        self.mode_combo.setCurrentIndex(1 if mode == "copy" else 0)
        form.addRow("File mode:", self.mode_combo)

        layout.addLayout(form)

        pattern = QLabel(
            "Files are filed using this pattern:<br>"
            "<code>Library/Author/[Series/]Book/001 - Chapter.ext</code>")
        pattern.setWordWrap(True)
        pattern.setObjectName("muted")
        layout.addWidget(pattern)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- slots --------------------------------------------------------
    def _browse(self):
        start = self.library_edit.text().strip() or os.path.expanduser("~")
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose library folder", start)
        if chosen:
            self.library_edit.setText(chosen)

    # -- result ---------------------------------------------------------
    def result_config(self):
        """Updated config dict (does not persist - caller saves it)."""
        cfg = dict(self._initial)
        cfg["library_root"] = self.library_edit.text().strip() or \
            config_module.DEFAULT_LIBRARY
        cfg["file_mode"] = self.mode_combo.currentData() or "move"
        cfg["setup_done"] = True
        return cfg
