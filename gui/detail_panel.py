"""Detail panel: cover art, metadata editor, tags, audio preview."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QFormLayout, QListWidget, QListWidgetItem,
    QAbstractItemView,
)

from mutagen import File as MutagenFile

from backend import (
    AUDIO_EXTS,
    can_set_cover,
    set_cover,
    extract_cover,
    CoverError,
    UnsupportedFormatError,
)
from gui.player import PlayerWidget


def _chapter_label(ch):
    track = (ch.get("track") or "").strip()
    title = ch.get("title") or Path(ch.get("path") or "").name
    return f"{track} — {title}" if track else title


def _flag_text(book):
    flags = []
    if book.get("mojibake"):
        flags.append("mojibake in name")
    if book.get("translit"):
        flags.append("transliterated?")
    if book.get("has_tags"):
        flags.append("has tags")
    if book.get("has_art"):
        flags.append("has cover")
    return ", ".join(flags) if flags else "none"


class DetailPanel(QWidget):
    """Right-side panel for the selected book."""

    coverChanged = Signal()        # refresh library thumbnails
    tagsChanged = Signal()         # refresh tag filter list
    statusMessage = Signal(str)    # show a line in the main status bar

    def __init__(self, db, covers_dir, parent=None):
        super().__init__(parent)
        self._db = db
        self._covers_dir = Path(covers_dir)
        self._book_id = None

        self._cover_label = QLabel()
        self._cover_label.setFixedSize(220, 220)
        self._cover_label.setAlignment(Qt.AlignCenter)
        self._cover_label.setStyleSheet(
            "border: 1px solid #3d3d3d; border-radius: 4px;")

        self._add_cover_btn = QPushButton("Add cover…")
        self._add_cover_btn.clicked.connect(self._pick_cover)
        self._replace_cover_btn = QPushButton("Replace cover…")
        self._replace_cover_btn.clicked.connect(self._pick_cover)

        self._title_edit = QLineEdit()
        self._author_edit = QLineEdit()
        self._meta_save_btn = QPushButton("Save title/author")
        self._meta_save_btn.clicked.connect(self._save_metadata)

        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("comma, separated, tags")
        self._tags_save_btn = QPushButton("Save tags")
        self._tags_save_btn.clicked.connect(self._save_tags)

        self._player = PlayerWidget()

        self._chapter_label = QLabel("Chapters")
        self._chapter_list = QListWidget()
        self._chapter_list.setMaximumHeight(150)
        self._chapter_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._chapter_list.itemClicked.connect(self._on_chapter_clicked)
        self._chapter_list.itemDoubleClicked.connect(
            self._on_chapter_double_clicked)

        self._info_path = QLabel()
        self._info_path.setWordWrap(True)
        self._info_path.setTextInteractionFlags(
            Qt.TextSelectableByMouse)
        self._info_path.setObjectName("dimLabel")
        self._info_format = QLabel()
        self._info_lang = QLabel()
        self._info_added = QLabel()
        self._info_flags = QLabel()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        layout.addWidget(QLabel("Cover"))
        layout.addWidget(self._cover_label, alignment=Qt.AlignHCenter)
        cover_btns = QHBoxLayout()
        cover_btns.addWidget(self._add_cover_btn)
        cover_btns.addWidget(self._replace_cover_btn)
        layout.addLayout(cover_btns)

        form = QFormLayout()
        form.addRow("Title", self._title_edit)
        form.addRow("Author", self._author_edit)
        layout.addLayout(form)
        layout.addWidget(self._meta_save_btn)

        layout.addWidget(QLabel("Tags"))
        layout.addWidget(self._tags_edit)
        layout.addWidget(self._tags_save_btn)

        self._player_title = QLabel("Preview")
        layout.addWidget(self._player_title)
        layout.addWidget(self._chapter_label)
        layout.addWidget(self._chapter_list)
        layout.addWidget(self._player)

        layout.addWidget(QLabel("Details"))
        details = QFormLayout()
        details.addRow("Path", self._info_path)
        details.addRow("Format", self._info_format)
        details.addRow("Language", self._info_lang)
        details.addRow("Date added", self._info_added)
        details.addRow("Flags", self._info_flags)
        layout.addLayout(details)
        layout.addStretch(1)

    # -- public ------------------------------------------------------

    def show_book(self, book_id):
        self._book_id = book_id
        book = self._db.get_book(book_id)
        if not book:
            return
        self._title_edit.setText(book.get("title") or "")
        self._author_edit.setText(book.get("author") or "")
        self._tags_edit.setText(", ".join(book.get("tags") or []))

        pix = QPixmap()
        cover_path = book.get("cover_path")
        if cover_path and Path(cover_path).exists():
            pix.load(str(cover_path))
        if pix.isNull():
            pix = QPixmap(200, 200)
            pix.fill(QColor("#2a2a2a"))
        self._cover_label.setPixmap(
            pix.scaled(220, 220, Qt.KeepAspectRatio,
                       Qt.SmoothTransformation))
        has_cover = bool(cover_path and Path(cover_path).exists())
        self._add_cover_btn.setVisible(not has_cover)
        self._replace_cover_btn.setVisible(has_cover)

        self._info_path.setText(book.get("path") or "")
        self._info_format.setText(
            f"{book.get('kind', '')} ({book.get('ext', '')})")
        self._info_lang.setText(book.get("lang") or "")
        self._info_added.setText(book.get("date_added") or "")
        self._info_flags.setText(_flag_text(book))

        if book.get("kind") == "audio":
            chapters = book.get("chapters") or []
            multi = len(chapters) > 1
            self._player_title.setVisible(True)
            self._player.setVisible(True)
            self._chapter_label.setVisible(multi)
            self._chapter_list.setVisible(multi)
            if multi:
                self._chapter_list.blockSignals(True)
                self._chapter_list.clear()
                for ch in chapters:
                    item = QListWidgetItem(_chapter_label(ch))
                    item.setData(Qt.UserRole, ch["path"])
                    item.setToolTip(ch["path"])
                    self._chapter_list.addItem(item)
                self._chapter_list.blockSignals(False)
                if chapters:
                    self._chapter_list.setCurrentRow(0)
                    self._player.load(chapters[0]["path"])
                else:
                    self._player.clear()
            else:
                self._player.load(chapters[0]["path"] if chapters
                                  else book["path"])
        else:
            self._player_title.setVisible(False)
            self._player.setVisible(False)
            self._chapter_label.setVisible(False)
            self._chapter_list.setVisible(False)
            self._player.clear()

    def clear(self):
        self._book_id = None
        self._chapter_list.clear()
        self._player.clear()

    # -- slots -------------------------------------------------------

    @Slot()
    def _on_chapter_clicked(self):
        item = self._chapter_list.currentItem()
        if item:
            self._player.load(item.data(Qt.UserRole))

    @Slot()
    def _on_chapter_double_clicked(self):
        item = self._chapter_list.currentItem()
        if item:
            self._player.load(item.data(Qt.UserRole))
            self._player.play()

    @Slot()
    def _pick_cover(self):
        if self._book_id is None:
            return
        book = self._db.get_book(self._book_id)
        if not book:
            return
        # A folder-book's cover belongs on every chapter file that can
        # carry one; a single-file book behaves exactly as before.
        targets = [ch["path"] for ch in (book.get("chapters") or [])
                   if can_set_cover(ch.get("ext") or "")]
        if not targets:
            QMessageBox.warning(
                self, "Cover art not supported",
                "None of this book's files can carry cover art. "
                "Supported: MP3, M4B/M4A, FLAC, OGG/Opus, EPUB.")
            return
        fname, _ = QFileDialog.getOpenFileName(
            self, "Choose cover image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not fname:
            return
        try:
            image_bytes = Path(fname).read_bytes()
        except OSError as e:
            QMessageBox.warning(self, "Couldn't read image",
                                f"Couldn't read that file:\n{e}")
            return
        written, skipped = [], []
        for target in targets:
            try:
                set_cover(target, image_bytes)
                written.append(target)
            except (UnsupportedFormatError, CoverError):
                skipped.append(Path(target).name)
        if not written:
            QMessageBox.warning(self, "Couldn't set cover",
                                "None of the book's files accepted the "
                                "cover image. Nothing was changed.")
            return
        # Cache a copy so the library view stays fast.
        try:
            art = extract_cover(written[0]) or image_bytes
            self._covers_dir.mkdir(parents=True, exist_ok=True)
            cache = self._covers_dir / f"{book['id']}.jpg"
            cache.write_bytes(art)
            self._db.set_cover(book["id"], str(cache))
        except OSError as e:
            self.statusMessage.emit(f"Cover set, but caching failed: {e}")
        self.show_book(book["id"])
        self.coverChanged.emit()
        if skipped:
            names = ", ".join(skipped[:3]) + ("…" if len(skipped) > 3 else "")
            self.statusMessage.emit(
                f"Cover written to {len(written)} file(s); "
                f"skipped {len(skipped)}: {names}")
        else:
            self.statusMessage.emit(
                f"Cover written to {len(written)} file(s).")

    @Slot()
    def _save_metadata(self):
        if self._book_id is None:
            return
        title = self._title_edit.text().strip()
        author = self._author_edit.text().strip()
        # The library database always updates, even if the file itself
        # can't carry the new tags.
        self._db.update_metadata(self._book_id, title, author)
        book = self._db.get_book(self._book_id)
        if not book:
            self.statusMessage.emit("That book is no longer in the library.")
            return
        note = self._write_embedded_tags(book, title, author)
        if note:
            self.statusMessage.emit(f"Saved to library. {note}")
        else:
            self.statusMessage.emit("Title/author saved (library + file).")
        self.coverChanged.emit()  # refresh the table row

    @Slot()
    def _save_tags(self):
        if self._book_id is None:
            return
        tags = [t.strip() for t in self._tags_edit.text().split(",")]
        self._db.set_tags(self._book_id, tags)
        self.tagsChanged.emit()
        self.statusMessage.emit("Tags saved.")

    # -- helpers -----------------------------------------------------

    def _write_embedded_tags(self, book, title, author):
        """Write title/author into the file(s) themselves. Returns None
        on success, or a short note explaining what didn't happen.

        For a folder-book the book title goes into each chapter's
        *album* tag (chapter titles are left alone) and the author into
        *artist*; single-file books keep the old title/artist behavior.
        """
        chapters = book.get("chapters") or []
        if len(chapters) > 1 and book.get("kind") == "audio":
            return self._write_chapter_tags(chapters, title, author)
        path = book.get("path") or ""
        ext = (book.get("ext") or "").lower()
        if not path or not Path(path).exists():
            return "The file is missing, so only the library was updated."
        try:
            if ext in AUDIO_EXTS:
                audio = MutagenFile(path, easy=True)
                if audio is None:
                    return (f"Mutagen can't tag {ext} files; "
                            "library updated only.")
                audio["title"] = [title]
                audio["artist"] = [author]
                audio.save()
            elif ext == ".epub":
                from ebooklib import epub
                from ebooklib.epub import NAMESPACES
                bk = epub.read_epub(path)
                dc = bk.metadata.get(NAMESPACES["DC"], {})
                dc.pop("title", None)
                dc.pop("creator", None)
                bk.set_title(title)
                bk.add_author(author)
                epub.write_epub(path, bk)
            else:
                return (f"Embedded tags aren't writable for {ext}; "
                        "library updated only.")
        except Exception as e:
            return f"Couldn't write into the file ({e}); library updated only."
        return None

    @staticmethod
    def _write_chapter_tags(chapters, book_title, author):
        """Write album/artist into every audio chapter. Returns None on
        success or a note."""
        ok, total = 0, 0
        for ch in chapters:
            ext = (ch.get("ext") or "").lower()
            if ext not in AUDIO_EXTS or not Path(ch["path"]).exists():
                continue
            total += 1
            try:
                audio = MutagenFile(ch["path"], easy=True)
                if audio is None:
                    continue
                audio["album"] = [book_title]
                audio["artist"] = [author]
                audio.save()
                ok += 1
            except Exception:
                continue
        if not total:
            return "No chapter files could be tagged; library updated only."
        if ok < total:
            return (f"Saved to library. Tags written to {ok} of {total} "
                    f"chapter files.")
        return None
