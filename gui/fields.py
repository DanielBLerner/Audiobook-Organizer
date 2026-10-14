"""Reusable widgets: StateField, TagLineEdit, ChapterListWidget."""

import html

from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .styles import refresh_style


class StateField(QWidget):
    """A labelled text field with a colored outline showing its state.

    Layout: label ABOVE, the QLineEdit, then display-only flags BELOW
    as bold tags each followed by a small gray source note.

    State rules (outline color via the ``fstate`` dynamic property):
      - initial text non-empty  -> "auto"  (blue), unless
        ``start_edited`` is True -> "edited" (green)
      - initial text empty      -> "empty" (gray)
      - any change made by the user -> "edited" (green), or "empty"
        (gray) when the user clears the field
    Programmatic set_text() never marks the field edited.
    """

    def __init__(self, label_text, initial="", flags=None, parent=None,
                 start_edited=False):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self.label = QLabel(label_text)
        layout.addWidget(self.label)

        self.edit = QLineEdit()
        self.edit.setText(initial or "")
        layout.addWidget(self.edit)

        self.flags_label = QLabel()
        self.flags_label.setTextFormat(Qt.RichText)
        self.flags_label.setWordWrap(True)
        self.set_flags(flags or [])
        layout.addWidget(self.flags_label)

        self.edit.textChanged.connect(self._on_user_text_changed)

        if initial:
            self._state = "edited" if start_edited else "auto"
        else:
            self._state = "empty"
        self._apply_state()

    # -- state ------------------------------------------------------
    def _on_user_text_changed(self, text):
        self._state = "edited" if text.strip() else "empty"
        self._apply_state()

    def _apply_state(self):
        self.edit.setProperty("fstate", self._state)
        refresh_style(self.edit)

    def state(self):
        """One of "auto", "empty", "edited"."""
        return self._state

    # -- value ------------------------------------------------------
    def text(self):
        return self.edit.text()

    def set_text(self, text):
        """Programmatic set: does not touch the state."""
        self.edit.blockSignals(True)
        try:
            self.edit.setText(text or "")
        finally:
            self.edit.blockSignals(False)

    def set_flags(self, flags):
        """flags: list of (bold_text, gray_source_note) tuples."""
        parts = []
        for bold_text, note in flags:
            chunk = "<b>%s</b>" % html.escape(str(bold_text))
            if note:
                chunk += ' <span style="color:#8a8a8a">%s</span>' % html.escape(
                    str(note))
            parts.append(chunk)
        self.flags_label.setText("&nbsp;&nbsp;".join(parts))
        self.flags_label.setVisible(bool(parts))


class TagLineEdit(QLineEdit):
    """Free-text comma-separated tag field with autocomplete.

    The completer suggests from the tag list for the token currently
    being typed (the text after the last comma).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._completer = QCompleter(self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setModel(QStringListModel([], self._completer))
        self._completer.activated.connect(self._on_completion)
        self.setCompleter(self._completer)
        self.textEdited.connect(lambda _t: self._update_prefix())

    def set_tag_list(self, tags):
        model = self._completer.model()
        model.setStringList(sorted({str(t) for t in (tags or []) if t}))

    def tags(self):
        """Parsed list of non-empty stripped tags."""
        return [t.strip() for t in self.text().split(",") if t.strip()]

    # -- internals --------------------------------------------------
    def _current_token(self):
        return self.text().rsplit(",", 1)[-1].strip()

    def _update_prefix(self):
        token = self._current_token()
        self._completer.setCompletionPrefix(token)
        if token:
            self._completer.complete()

    def _on_completion(self, completion):
        prefix = self.text()
        head, _sep, _tail = prefix.rpartition(",")
        new_token = completion.strip()
        if head:
            self.setText(head + ", " + new_token + ", ")
        else:
            self.setText(new_token + ", ")


class ChapterListWidget(QWidget):
    """Reorderable chapter list with per-row play buttons and a preview
    player underneath.

    Chapters are dicts with at least ``path`` and ``title`` (extra keys
    such as ``ext``, ``id`` are preserved untouched).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Local import: player.py only needs QtMultimedia, no cycle.
        from .player import PreviewPlayer

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.list, 1)

        self.player = PreviewPlayer()
        layout.addWidget(self.player)

        self.list.itemClicked.connect(self._on_item_clicked)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list.model().rowsMoved.connect(
            lambda *args: self._renumber_rows())

    # -- data -------------------------------------------------------
    def set_chapters(self, chapters):
        self.list.clear()
        for ch in chapters or []:
            self._add_row(dict(ch))
        self._renumber_rows()

    def ordered_chapters(self):
        """Chapter dicts in the current UI order."""
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            out.append(item.data(Qt.UserRole))
        return out

    # -- rows -------------------------------------------------------
    def _add_row(self, chapter):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, chapter)
        self.list.addItem(item)

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(8)

        num_label = QLabel()
        num_label.setObjectName("chapter_title")
        h.addWidget(num_label, 1)

        play_btn = QPushButton("\u25b6")  # ▶
        play_btn.setFixedWidth(40)
        play_btn.setToolTip("Play this chapter")
        play_btn.clicked.connect(
            lambda _checked=False, ch=chapter: self._play_chapter(ch))
        h.addWidget(play_btn)

        item.setSizeHint(row.sizeHint())
        self.list.setItemWidget(item, row)

    def _renumber_rows(self):
        for i in range(self.list.count()):
            item = self.list.item(i)
            chapter = item.data(Qt.UserRole) or {}
            row = self.list.itemWidget(item)
            if row is None:
                continue
            label = row.findChild(QLabel, "chapter_title")
            if label is not None:
                label.setText("%03d - %s" % (i + 1, chapter.get("title") or ""))

    # -- playback ---------------------------------------------------
    def _chapter_of_item(self, item):
        return item.data(Qt.UserRole) if item is not None else None

    def _on_item_clicked(self, item):
        chapter = self._chapter_of_item(item)
        if chapter and chapter.get("path"):
            self.player.load(chapter["path"])

    def _on_item_double_clicked(self, item):
        chapter = self._chapter_of_item(item)
        if chapter and chapter.get("path"):
            self.player.load(chapter["path"])
            self.player.play()

    def _play_chapter(self, chapter):
        if chapter and chapter.get("path"):
            self.player.load(chapter["path"])
            self.player.play()
