"""SQLite library database (v2 schema).

Robustness rule (a crash on launch is unacceptable): _migrate()
inspects EVERY table with PRAGMA table_info and ALTER TABLE ...
ADD COLUMN for each expected column that is missing. The schema is
never trusted from CREATE TABLE IF NOT EXISTS alone.

Tables:
  books    (id, title, author, series DEFAULT '', date_added, cover_path,
            library_path, chapter_count DEFAULT 1)
  chapters (id, book_id FK, path UNIQUE, rel, title, track, ext,
            position DEFAULT 0, sha256)
  tags     (book_id, tag, PK(book_id, tag))
  + index on chapters(sha256)

All methods are thread-safe via an RLock. delete_book() removes the
book, its chapters and tags - the actual files are handled by the
caller (moved to the Windows Recycle Bin by the GUI).
"""

import datetime
import sqlite3
import threading
from pathlib import Path

EXPECTED_COLUMNS = {
    "books": [
        ("id", "INTEGER PRIMARY KEY"),
        ("title", "TEXT"),
        ("author", "TEXT"),
        ("series", "TEXT DEFAULT ''"),
        ("date_added", "TEXT"),
        ("cover_path", "TEXT"),
        ("library_path", "TEXT"),
        ("chapter_count", "INTEGER DEFAULT 1"),
    ],
    "chapters": [
        ("id", "INTEGER PRIMARY KEY"),
        ("book_id", "INTEGER"),
        ("path", "TEXT UNIQUE"),
        ("rel", "TEXT"),
        ("title", "TEXT"),
        ("track", "TEXT"),
        ("ext", "TEXT"),
        ("position", "INTEGER DEFAULT 0"),
        ("sha256", "TEXT"),
    ],
    "tags": [
        ("book_id", "INTEGER"),
        ("tag", "TEXT"),
    ],
}


class LibraryDB:
    def __init__(self, db_path):
        self._lock = threading.RLock()
        self.path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._migrate()

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _migrate(self):
        cur = self._conn.cursor()
        for table, columns in EXPECTED_COLUMNS.items():
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,))
            exists = cur.fetchone() is not None
            if not exists:
                cols = ", ".join(f"{name} {dtype}" for name, dtype in columns)
                cur.execute(f"CREATE TABLE {table} ({cols})")
            else:
                cur.execute(f"PRAGMA table_info({table})")
                present = {row["name"] for row in cur.fetchall()}
                for name, dtype in columns:
                    if name not in present:
                        cur.execute(
                            f"ALTER TABLE {table} ADD COLUMN {name} {dtype}")
            if table == "tags":
                # tags needs the composite PK; recreate only if it is
                # missing entirely (a plain CREATE without PK is fine
                # functionally, but redo it right).
                cur.execute(f"PRAGMA table_info({table})")
                info = {row["name"]: row["pk"] for row in cur.fetchall()}
                if info.get("book_id") != 1 or info.get("tag") != 2:
                    cur.execute("ALTER TABLE tags RENAME TO _tags_old")
                    cur.execute(
                        "CREATE TABLE tags (book_id INTEGER, tag TEXT, "
                        "PRIMARY KEY (book_id, tag))")
                    cur.execute(
                        "INSERT OR IGNORE INTO tags (book_id, tag) "
                        "SELECT book_id, tag FROM _tags_old")
                    cur.execute("DROP TABLE _tags_old")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_chapters_sha256 "
            "ON chapters(sha256)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_chapters_book "
            "ON chapters(book_id)")
        self._conn.commit()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def file_book(self, book, chapters, tags, cover_path, library_dir,
                  fingerprints):
        """Store a filed book. Returns the new book id.

        book:         {title, author, series}
        chapters:     ordered list of {path (final abs path), rel,
                      title, track, ext}
        tags:         list of tag strings
        cover_path:   absolute path of the cover art, or None
        library_dir:  absolute path of the book's folder in the library
        fingerprints: {path: sha256}
        Stamps date_added with today's ISO date.
        """
        with self._lock:
            cur = self._conn.cursor()
            today = datetime.date.today().isoformat()
            cur.execute(
                "INSERT INTO books (title, author, series, date_added, "
                "cover_path, library_path, chapter_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (book.get("title") or "", book.get("author") or "",
                 book.get("series") or "", today, cover_path,
                 str(library_dir), len(chapters)))
            book_id = cur.lastrowid
            for pos, ch in enumerate(chapters):
                path = str(ch.get("path") or "")
                cur.execute(
                    "INSERT OR REPLACE INTO chapters "
                    "(book_id, path, rel, title, track, ext, position, "
                    "sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (book_id, path, ch.get("rel") or "",
                     ch.get("title") or "", ch.get("track") or "",
                     ch.get("ext") or "", pos,
                     (fingerprints or {}).get(path)))
            for tag in tags or []:
                if tag and str(tag).strip():
                    cur.execute(
                        "INSERT OR IGNORE INTO tags (book_id, tag) "
                        "VALUES (?, ?)",
                        (book_id, str(tag).strip()))
            self._conn.commit()
            return book_id

    def update_book(self, book_id, title, author, series, tags, cover_path):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE books SET title=?, author=?, series=?, "
                "cover_path=? WHERE id=?",
                (title or "", author or "", series or "", cover_path,
                 book_id))
            cur.execute("DELETE FROM tags WHERE book_id=?", (book_id,))
            for tag in tags or []:
                if tag and str(tag).strip():
                    cur.execute(
                        "INSERT OR IGNORE INTO tags (book_id, tag) "
                        "VALUES (?, ?)", (book_id, str(tag).strip()))
            self._conn.commit()

    def update_chapter_order(self, book_id, ordered_chapter_ids):
        with self._lock:
            cur = self._conn.cursor()
            for pos, ch_id in enumerate(ordered_chapter_ids):
                cur.execute(
                    "UPDATE chapters SET position=? "
                    "WHERE id=? AND book_id=?", (pos, ch_id, book_id))
            self._conn.commit()

    def delete_book(self, book_id):
        """Delete the book, its chapters and tags (files are the
        caller's responsibility)."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM chapters WHERE book_id=?", (book_id,))
            cur.execute("DELETE FROM tags WHERE book_id=?", (book_id,))
            cur.execute("DELETE FROM books WHERE id=?", (book_id,))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _book_row_to_dict(self, row, cur):
        book_id = row["id"]
        cur.execute("SELECT tag FROM tags WHERE book_id=? ORDER BY tag",
                    (book_id,))
        tags = [r["tag"] for r in cur.fetchall()]
        cur.execute("SELECT * FROM chapters WHERE book_id=? "
                    "ORDER BY position, id", (book_id,))
        chapters = [dict(r) for r in cur.fetchall()]
        return {
            "id": book_id,
            "title": row["title"] or "",
            "author": row["author"] or "",
            "series": row["series"] or "",
            "tags": tags,
            "date_added": row["date_added"] or "",
            "cover_path": row["cover_path"],
            "library_path": row["library_path"],
            "chapter_count": row["chapter_count"] or len(chapters),
            "chapters": chapters,
        }

    def list_books(self, search="", tag="", order_by="date_added",
                   order_desc=True):
        if order_by not in ("date_added", "title", "author"):
            order_by = "date_added"
        direction = "DESC" if order_desc else "ASC"
        with self._lock:
            cur = self._conn.cursor()
            sql = "SELECT * FROM books"
            where, params = [], []
            if search:
                where.append(
                    "(title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' "
                    "OR series LIKE ? ESCAPE '\\')")
                like = ("%" + search.replace("\\", "\\\\")
                        .replace("%", "\\%").replace("_", "\\_") + "%")
                params.extend([like, like, like])
            if tag:
                where.append(
                    "id IN (SELECT book_id FROM tags WHERE tag=?)")
                params.append(tag)
            if where:
                sql += " WHERE " + " AND ".join(where)
            # NULLs last for a stable default (date_added DESC) order.
            sql += (f" ORDER BY {order_by} IS NULL, {order_by} {direction}, "
                    f"id {direction}")
            cur.execute(sql, params)
            return [self._book_row_to_dict(r, cur) for r in cur.fetchall()]

    def get_book(self, book_id):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM books WHERE id=?", (book_id,))
            row = cur.fetchone()
            return self._book_row_to_dict(row, cur) if row else None

    def all_tags(self):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT DISTINCT tag FROM tags ORDER BY tag")
            return [r["tag"] for r in cur.fetchall()]

    def find_chapter_by_hash(self, sha256):
        """Return (book_dict, chapter_dict) for the chapter with this
        SHA-256, or None."""
        if not sha256:
            return None
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM chapters WHERE sha256=?", (sha256,))
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute("SELECT * FROM books WHERE id=?", (row["book_id"],))
            brow = cur.fetchone()
            if brow is None:
                return None
            return self._book_row_to_dict(brow, cur), dict(row)

    def close(self):
        with self._lock:
            self._conn.commit()
            self._conn.close()
