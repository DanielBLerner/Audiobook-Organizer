"""Reusable widgets: StateField, StateDateField, TagLineEdit,
ChapterListWidget, TagBubble, TagFlow."""

import html

from PySide6.QtCore import QDate, QPoint, QRect, QSize, Qt, QStringListModel
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLayout,
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


# ----------------------------------------------------------------------
# Date field with the same outline-state rules as StateField
# (Addendum A)
# ----------------------------------------------------------------------

class StateDateField(QWidget):
    """A labelled date picker (QDateEdit + calendar popup).

    Layout: label ABOVE the picker. Outline states via the ``fstate``
    dynamic property, same rules as StateField:
      - initial value (today)            -> "auto"   (blue)
      - user picks a different date      -> "edited" (green)
    A date can't be empty; there is no "empty" state.
    Programmatic set_date() never marks the field edited.
    """

    def __init__(self, label_text, initial=None, parent=None,
                 start_edited=False):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self.label = QLabel(label_text)
        layout.addWidget(self.label)

        self.edit = QDateEdit()
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd")
        self.edit.setDate(self._to_qdate(initial) or QDate.currentDate())
        layout.addWidget(self.edit)

        self.edit.dateChanged.connect(self._on_user_date_changed)

        if initial and start_edited:
            self._state = "edited"
        else:
            self._state = "auto"
        self._apply_state()

    # -- state ------------------------------------------------------
    @staticmethod
    def _to_qdate(value):
        if isinstance(value, QDate):
            return value if value.isValid() else None
        if isinstance(value, str) and value.strip():
            d = QDate.fromString(value.strip()[:10], "yyyy-MM-dd")
            return d if d.isValid() else None
        return None

    def _on_user_date_changed(self, _date):
        self._state = "edited"
        self._apply_state()

    def _apply_state(self):
        self.edit.setProperty("fstate", self._state)
        refresh_style(self.edit)

    def state(self):
        return self._state

    # -- value ------------------------------------------------------
    def date(self):
        return self.edit.date()

    def date_iso(self):
        return self.edit.date().toString("yyyy-MM-dd")

    def set_date(self, value):
        """Programmatic set: does not touch the state."""
        d = self._to_qdate(value)
        if d is None:
            return
        self.edit.blockSignals(True)
        try:
            self.edit.setDate(d)
        finally:
            self.edit.blockSignals(False)


# ----------------------------------------------------------------------
# Tag bubbles (Addendum B)
# ----------------------------------------------------------------------

def bubble_text_color(hex_color):
    """Black or white text, whichever reads better on the bubble."""
    try:
        c = QColor(str(hex_color))
        if not c.isValid():
            return "#ffffff"
        # Relative luminance (sRGB).
        r, g, b = (c.redF(), c.greenF(), c.blueF())

        def _lin(v):
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

        lum = 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
        return "#111111" if lum > 0.45 else "#ffffff"
    except Exception:
        return "#ffffff"


class TagBubble(QLabel):
    """A tag rendered as a colored rounded pill (per Daniel's sketch)."""

    def __init__(self, text, color_hex="#4aa3ff", parent=None):
        super().__init__(text, parent)
        self.set_color(color_hex, text)

    def set_color(self, color_hex, text=None):
        color_hex = str(color_hex or "#4aa3ff")
        if text is not None:
            self.setText(text)
        fg = bubble_text_color(color_hex)
        self.setStyleSheet(
            "QLabel { background-color: %s; color: %s; "
            "border-radius: 10px; padding: 3px 12px; }"
            % (color_hex, fg))


class FlowLayout(QLayout):
    """Wrapping left-to-right layout for tag bubbles."""

    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._hspacing = hspacing
        self._vspacing = vspacing
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(),
                      margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0
        max_x = rect.x() + rect.width() - margins.right()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._hspacing
            if next_x - self._hspacing > max_x and line_height > 0:
                x = rect.x() + margins.left()
                y += line_height + self._vspacing
                next_x = x + hint.width() + self._hspacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class TagFlow(QWidget):
    """A wrapping row of TagBubble widgets for a book's tags.

    tags: list of tag strings.
    meta: {tag: {"color": hex, "hidden": bool}}; unknown tags get the
          default bubble color.
    """

    def __init__(self, tags, meta=None, parent=None):
        super().__init__(parent)
        from db import DEFAULT_TAG_COLOR
        meta = meta or {}
        layout = FlowLayout(self, margin=0)
        for tag in tags or []:
            m = meta.get(tag) or {}
            bubble = TagBubble(tag, m.get("color") or DEFAULT_TAG_COLOR)
            layout.addWidget(bubble)
