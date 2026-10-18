"""Tag manager (Addendum B).

Reached from Settings -> "Edit tags". Two dialogs:

- TagManagerDialog: the tag list page. Every tag rendered as its
  colored bubble (clickable to edit), hidden tags dimmed with a
  "hidden" marker, plus a "New tag" button.
- TagEditorDialog: the tag editor page (per Daniel's sketch). Text
  field with label above, live preview bubble, hue slider, "Hide tag"
  checkbox, Save bottom-center. Leaving without Save discards
  everything silently.

Tags are NEVER deletable - there is no delete button anywhere here.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .fields import TagBubble, bubble_text_color


def _pill_stylesheet(color_hex):
    fg = bubble_text_color(color_hex)
    return (
        "QPushButton { background-color: %s; color: %s; "
        "border-radius: 12px; padding: 6px 18px; border: none; "
        "font-size: 13px; }"
        "QPushButton:hover { border: 1px solid %s; }"
        % (color_hex, fg, fg)
    )


class TagEditorDialog(QDialog):
    """Create or edit one tag."""

    tag_saved = Signal()

    def __init__(self, db, tag=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._original = (tag or "").strip()  # "" means "creating"

        meta = db.get_tag_meta(self._original) if self._original else None
        start_color = (meta or {}).get("color") or "#4aa3ff"
        start_hidden = bool((meta or {}).get("hidden"))

        self.setWindowTitle("Edit tag" if self._original else "New tag")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 20)

        # -- text field (label above, per app conventions) -------------
        layout.addWidget(QLabel("Tag text:"))
        self.text_edit = QLineEdit()
        if self._original:
            self.text_edit.setText(self._original)
        self.text_edit.setPlaceholderText("e.g. sci-fi")
        layout.addWidget(self.text_edit)

        # -- live preview bubble (Daniel's sketch) ----------------------
        self.preview = TagBubble(
            self._original or "tag", start_color)
        self.preview.setAlignment(Qt.AlignCenter)
        preview_row = QHBoxLayout()
        preview_row.addStretch(1)
        preview_row.addWidget(self.preview)
        preview_row.addStretch(1)
        layout.addLayout(preview_row)

        # -- color slider (hue) -----------------------------------------
        layout.addWidget(QLabel("Bubble color:"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 359)
        start_hue = QColor(start_color).hsvHue()
        if start_hue < 0:
            start_hue = 210  # grayscale fallback -> blue
        self.slider.setValue(start_hue)
        self.slider.setToolTip("Drag to choose the bubble color")
        layout.addWidget(self.slider)

        # -- hide checkbox ----------------------------------------------
        self.hide_box = QCheckBox("Hide tag")
        self.hide_box.setChecked(start_hidden)
        self.hide_box.setToolTip(
            "Hidden tags don't appear in the Library tag filter or in "
            "tag autocomplete. Books already using the tag keep it.")
        layout.addWidget(self.hide_box)

        # -- Save, bottom-center -----------------------------------------
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        save_row.addWidget(self.save_btn)
        save_row.addStretch(1)
        layout.addLayout(save_row)

        # -- live preview wiring -----------------------------------------
        self.text_edit.textChanged.connect(self._refresh_preview)
        self.slider.valueChanged.connect(self._refresh_preview)
        self._refresh_preview()

    # ------------------------------------------------------------------
    def _current_color(self):
        hue = self.slider.value()
        return QColor.fromHsv(hue, 210, 240).name()

    def _refresh_preview(self):
        text = self.text_edit.text().strip() or "tag"
        self.preview.set_color(self._current_color(), text)

    def _on_save(self):
        name = self.text_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Save tag",
                                "Tag text can't be empty.")
            return
        if self._db.tag_name_taken(name, ignore=self._original):
            QMessageBox.warning(
                self, "Save tag",
                "A tag named '%s' already exists.\n\n"
                "Pick a different name." % name)
            return
        color = self._current_color()
        hidden = self.hide_box.isChecked()
        try:
            if self._original:
                if name != self._original:
                    self._db.rename_tag(self._original, name)
                self._db.set_tag_meta(name, color=color, hidden=hidden)
            else:
                self._db.set_tag_meta(name, color=color, hidden=hidden)
        except ValueError as exc:
            QMessageBox.warning(self, "Save tag", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Save tag",
                                 "Could not save the tag:\n%s" % exc)
            return
        self.tag_saved.emit()
        self.accept()
    # Note: reject()/close without Save stores nothing - changes are
    # discarded silently, per the spec.


class TagManagerDialog(QDialog):
    """The tag list page."""

    tags_changed = Signal()  # a tag was created/edited

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self.setWindowTitle("Edit tags")
        self.setMinimumSize(440, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 16)

        new_btn = QPushButton("New tag")
        new_btn.clicked.connect(self._on_new_tag)
        layout.addWidget(new_btn, 0, Qt.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, 1)
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch(1)
        scroll.setWidget(self._list_host)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        close_row.addStretch(1)
        layout.addLayout(close_row)

        self.refresh_list()

    # ------------------------------------------------------------------
    def refresh_list(self):
        # Clear existing rows (keep the trailing stretch).
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.deleteLater()
        try:
            metas = self._db.all_tag_meta()
        except Exception:
            metas = []
        for meta in metas:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(10)

            btn = QPushButton(meta["tag"])
            btn.setStyleSheet(_pill_stylesheet(meta["color"]))
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _c=False, t=meta["tag"]: self._on_edit_tag(t))
            if meta["hidden"]:
                eff = QGraphicsOpacityEffect(btn)
                eff.setOpacity(0.45)
                btn.setGraphicsEffect(eff)
                marker = QLabel("hidden")
                marker.setObjectName("muted")
                h.addWidget(btn)
                h.addWidget(marker)
            else:
                h.addWidget(btn)
            h.addStretch(1)
            self._list_layout.insertWidget(
                self._list_layout.count() - 1, row)

    def _on_new_tag(self):
        dlg = TagEditorDialog(self._db, None, self)
        dlg.tag_saved.connect(self._after_change)
        dlg.exec()

    def _on_edit_tag(self, tag):
        dlg = TagEditorDialog(self._db, tag, self)
        dlg.tag_saved.connect(self._after_change)
        dlg.exec()

    def _after_change(self):
        self.refresh_list()
        self.tags_changed.emit()
