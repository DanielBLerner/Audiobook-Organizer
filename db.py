"""SQLite library database.

Stores one row per book file: scan metadata, free-text tags, the date
it was added (auto-stamped on first import), and an optional cover-art
image path (a cached copy, so the library view stays fast even if the
book file moves).

Schema:
    books(id, path UNIQUE, rel, kind, ext, author, book, title, track,
          lang, has_tags, mojibake, translit, has_art, date_added,
          cover_path)
    tags(book_id, tag)   -- one row per tag
"""

import sqlite3
import threading
from datetime import date
from pathlib import Path

BOOK_COLUMNS = ("id", "path", "rel", "kind", "ext", "author", "book",
                "title", "track", "lang", "has_tags", "mojibake",
                "translit", "has_art", "date_added", "cover_path")

ORDER_COLUMNS = {"title": "title", "author": "author", "book": "book",
                 "date_added": "date_added", "kind": "kind", "lang": "lang"}


class LibraryDB:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # -- schema ------------------------------------------------------

    def _init_schema(self):
        with self._lock, self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    rel TEXT,
                    kind TEXT,
                    ext TEXT,
                    author TEXT,
                    book TEXT,
                    title TEXT,
                    track TEXT,
                    lang TEXT,
                    has_tags INTEGER DEFAULT 0,
                    mojibake INTEGER DEFAULT 0,
                    translit INTEGER DEFAULT 0,
                    has_art INTEGER DEFAULT 0,
                    date_added TEXT,
                    cover_path TEXT
                )""")
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    book_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    PRIMARY KEY (book_id, tag),
                    FOREIGN KEY (book_id) REFERENCES books(id)
                        ON DELETE CASCADE
                )""")
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag)")

    # -- import ------------------------------------------------------

    def import_items(self, items):
        """Upsert scan items. New rows get today's date_added.
        Returns the number of newly added books."""
        today = date.today().isoformat()
        new = 0
        with self._lock, self._conn:
            for it in items:
                cur = self._conn.execute(
                    "SELECT id FROM books WHERE path = ?", (it["path"],))
                row = cur.fetchone()
                if row is None:
                    self._conn.execute("""
                        INSERT INTO books
                        (path, rel, kind, ext, author, book, title, track,
                         lang, has_tags, mojibake, translit, has_art,
                         date_added)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (it["path"], it["rel"], it["kind"], it["ext"],
                         it["author"], it["book"], it["title"], it["track"],
                         it["lang"], int(it["has_tags"]),
                         int(it["mojibake"]), int(it["translit"]),
                         int(it["has_art"]), today))
                    new += 1
                else:
                    self._conn.execute("""
                        UPDATE books SET rel=?, kind=?, ext=?, author=?,
                            book=?, title=?, track=?, lang=?, has_tags=?,
                            mojibake=?, translit=?, has_art=?
                        WHERE id=?""",
                        (it["rel"], it["kind"], it["ext"], it["author"],
                         it["book"], it["title"], it["track"], it["lang"],
                         int(it["has_tags"]), int(it["mojibake"]),
                         int(it["translit"]), int(it["has_art"]), row["id"]))
        return new

    # -- reading -----------------------------------------------------

    def _row_to_dict(self, row):
        d = {c: row[c] for c in BOOK_COLUMNS}
        for flag in ("has_tags", "mojibake", "translit", "has_art"):
            d[flag] = bool(d[flag])
        d["tags"] = self.get_tags(d["id"])
        return d

    def list_books(self, search="", tag="", order_by="title",
                   order_desc=False):
        """Books matching search text and/or tag, sorted for the library."""
        order_col = ORDER_COLUMNS.get(order_by, "title")
        direction = "DESC" if order_desc else "ASC"
        sql = ("SELECT b.* FROM books b")
        params = []
        clauses = []
        if tag:
            sql += " JOIN tags t ON t.book_id = b.id"
            clauses.append("t.tag = ?")
            params.append(tag)
        if search:
            like = f"%{search}%"
            clauses.append(
                "(b.title LIKE ? OR b.author LIKE ? OR b.book LIKE ?)")
            params += [like, like, like]
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        # NULL/empty titles sort last-ish; keep it simple and predictable.
        sql += f" ORDER BY {order_col} COLLATE NOCASE {direction}"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_book(self, book_id):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
            return self._row_to_dict(row) if row else None

    def count(self):
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) AS n FROM books").fetchone()["n"]

    # -- editing -----------------------------------------------------

    def update_metadata(self, book_id, title, author):
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE books SET title = ?, author = ? WHERE id = ?",
                (title, author, book_id))

    def set_tags(self, book_id, tags):
        cleaned = sorted({t.strip() for t in tags if t and t.strip()})
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM tags WHERE book_id = ?",
                               (book_id,))
            self._conn.executemany(
                "INSERT INTO tags (book_id, tag) VALUES (?, ?)",
                [(book_id, t) for t in cleaned])

    def get_tags(self, book_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT tag FROM tags WHERE book_id = ? ORDER BY tag",
                (book_id,)).fetchall()
            return [r["tag"] for r in rows]

    def all_tags(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT tag FROM tags ORDER BY tag").fetchall()
            return [r["tag"] for r in rows]

    def set_cover(self, book_id, cover_path):
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE books SET cover_path = ?, has_art = 1 WHERE id = ?",
                (cover_path, book_id))

    def mark_moved(self, book_id, new_path, new_rel):
        """Update stored paths after an organize/rename move."""
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE books SET path = ?, rel = ? WHERE id = ?",
                (new_path, new_rel, book_id))

    def find_by_path(self, path):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM books WHERE path = ?", (path,)).fetchone()
            return self._row_to_dict(row) if row else None

    def prune_missing(self):
        """Drop rows whose files no longer exist. Returns count removed."""
        with self._lock, self._conn:
            rows = self._conn.execute("SELECT id, path FROM books").fetchall()
            gone = [r["id"] for r in rows
                    if not Path(r["path"]).exists()]
            for bid in gone:
                self._conn.execute("DELETE FROM tags WHERE book_id = ?",
                                   (bid,))
                self._conn.execute("DELETE FROM books WHERE id = ?", (bid,))
            return len(gone)

    def close(self):
        with self._lock:
            self._conn.close()
