"""Reusable widgets: StateField, StateDateField, TagLineEdit,
ChapterListWidget, TagBubble, TagFlow."""

import html

from PySide6.QtCore import (QDate, QEvent, QPoint, QRect, QSize, Qt,
                            QStringListModel, Signal)
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

    def set_completions(self, options):
        """Autocomplete for the inner line edit (Addendum E): suggests
        existing values, matched case-insensitively anywhere in the
        name. Picking one fills the field."""
        model = QStringListModel(
            sorted({str(o) for o in (options or []) if o}), self)
        completer = QCompleter(model, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.edit.setCompleter(completer)
        self._completer = completer

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
    """Wrapping left-to-right layout for tag bubbles.

    align="right" right-aligns each wrapped line within the available
    width (Addendum D: library-row tags sit on the right).
    """

    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6,
                 align="left"):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._hspacing = hspacing
        self._vspacing = vspacing
        self._align = align
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
        left = rect.x() + margins.left()
        top = rect.y() + margins.top()
        width = rect.width() - margins.left() - margins.right()

        # Group items into lines first (needed for right alignment).
        lines = []
        cur, cur_w, cur_h = [], 0, 0
        for item in self._items:
            hint = item.sizeHint()
            w = hint.width()
            extra = w if not cur else self._hspacing + w
            if cur and cur_w + extra > width:
                lines.append((cur, cur_w, cur_h))
                cur, cur_w, cur_h = [], 0, 0
                extra = w
            cur.append((item, hint))
            cur_w += extra
            cur_h = max(cur_h, hint.height())
        if cur:
            lines.append((cur, cur_w, cur_h))

        y = top
        for line_items, line_w, line_h in lines:
            x = left
            if self._align == "right":
                x = left + max(0, width - line_w)
            for item, hint in line_items:
                if not test_only:
                    item.setGeometry(QRect(QPoint(x, y), hint))
                x += hint.width() + self._hspacing
            y += line_h + self._vspacing
        if not lines:
            return margins.top() + margins.bottom()
        return y - self._vspacing - rect.y() + margins.bottom()


class TagFlow(QWidget):
    """A wrapping row of TagBubble widgets for a book's tags.

    tags: list of tag strings.
    meta: {tag: {"color": hex, "hidden": bool}}; unknown tags get the
          default bubble color.
    """

    def __init__(self, tags, meta=None, parent=None, align_right=False):
        super().__init__(parent)
        from db import DEFAULT_TAG_COLOR
        meta = meta or {}
        layout = FlowLayout(self, margin=0,
                            align="right" if align_right else "left")
        for tag in tags or []:
            m = meta.get(tag) or {}
            bubble = TagBubble(tag, m.get("color") or DEFAULT_TAG_COLOR)
            layout.addWidget(bubble)


# ----------------------------------------------------------------------
# Tag entry widget (Addendum F): type + Enter makes colored bubbles
# underneath the field, like the Library rows show.
# ----------------------------------------------------------------------

class _TagChip(QWidget):
    """One committed tag inside TagEntry: colored pill + a × button."""

    removed = Signal(str)

    def __init__(self, text, color_hex, parent=None):
        super().__init__(parent)
        self._text = text
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(TagBubble(text, color_hex))
        btn = QPushButton("\u00d7")  # ×
        btn.setFlat(True)
        btn.setFixedWidth(18)
        btn.setToolTip("Remove tag")
        btn.clicked.connect(lambda _c=False: self.removed.emit(self._text))
        layout.addWidget(btn)


class TagEntry(QWidget):
    """Tag field where typing + Enter commits colored bubbles below.

    - Enter or a comma commits the typed tag; the field clears.
    - Autocomplete suggests known tags (set_tag_list); picking one
      commits it. A typed name that matches a known tag
      (case-insensitively) snaps to the known spelling and color.
    - Clicking a bubble's ×, or Backspace with an empty field, removes
      that tag. Committing a duplicate does nothing.
    - A brand-new name is kept as typed with the default color; its
      tag_meta row is created when the book is filed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags = []   # committed tag texts, in entry order
        self._meta = {}   # tag -> {"color": hex, "hidden": bool}
        self._known = []  # canonical tag names for autocomplete

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Type a tag, press Enter\u2026")
        layout.addWidget(self.edit)

        self._flow_host = QWidget()
        self._flow = FlowLayout(self._flow_host, margin=0)
        layout.addWidget(self._flow_host)

        self._completer = QCompleter(self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setModel(QStringListModel([], self._completer))
        self._completer.activated.connect(self._commit)
        self.edit.setCompleter(self._completer)

        self.edit.returnPressed.connect(
            lambda: self._commit(self.edit.text()))
        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.installEventFilter(self)

    # -- data -------------------------------------------------------
    def tags(self):
        return list(self._tags)

    def set_tags(self, tags):
        self._tags = []
        for t in tags or []:
            self._add(t)
        self._rebuild()

    def set_tag_list(self, tags):
        self._known = [str(t) for t in (tags or []) if t]
        self._completer.model().setStringList(sorted(set(self._known)))

    def set_meta(self, meta):
        self._meta = dict(meta or {})
        self._rebuild()

    # -- internals --------------------------------------------------
    def _canonical(self, text):
        low = text.lower()
        for known in self._known:
            if known.lower() == low:
                return known
        for existing in self._tags:
            if existing.lower() == low:
                return existing
        return text

    def _color_of(self, text):
        from db import DEFAULT_TAG_COLOR
        m = self._meta.get(text) or {}
        return m.get("color") or DEFAULT_TAG_COLOR

    def _commit(self, text):
        text = (text or "").strip().strip(",").strip()
        if text:
            self._add(text)
            self._rebuild()
        self.edit.clear()

    def _add(self, text):
        text = self._canonical((text or "").strip())
        if not text:
            return
        if any(t.lower() == text.lower() for t in self._tags):
            return
        self._tags.append(text)

    def _remove(self, text):
        self._tags = [t for t in self._tags if t != text]
        self._rebuild()

    def _rebuild(self):
        while self._flow.count():
            item = self._flow.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for tag in self._tags:
            chip = _TagChip(tag, self._color_of(tag))
            chip.removed.connect(self._remove)
            self._flow.addWidget(chip)
        self._flow_host.updateGeometry()

    def _on_text_changed(self, text):
        if "," in text:
            head, _sep, tail = text.partition(",")
            self._commit(head)
            if tail.strip():
                self.edit.setText(tail)

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Backspace \
                    and not self.edit.text() and self._tags:
                self._remove(self._tags[-1])
                return True
        return super().eventFilter(obj, event)
