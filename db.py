"""SQLite library database.

Stores one row per *book*: scan metadata, free-text tags, the date
it was added (auto-stamped on first import), chapter count, and an
optional cover-art image path (a cached copy, so the library view stays
fast even if the book files move).

A book's files live in the ``chapters`` table - one row per chapter
file, in chapter order. A single-file book is just a book with one
chapter.

Schema:
    books(id, path UNIQUE, rel, kind, ext, author, book, title, track,
          lang, has_tags, mojibake, translit, has_art, date_added,
          cover_path, chapter_count)
    chapters(id, book_id, path UNIQUE, rel, title, track, ext, position)
    tags(book_id, tag)   -- one row per tag

For a folder-book, books.path is the book's folder; for a single-file
book it is the file itself.
"""

import sqlite3
import threading
from datetime import date
from pathlib import Path

BOOK_COLUMNS = ("id", "path", "rel", "kind", "ext", "author", "book",
                "title", "track", "lang", "has_tags", "mojibake",
                "translit", "has_art", "date_added", "cover_path",
                "chapter_count")

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
                    cover_path TEXT,
                    chapter_count INTEGER DEFAULT 1
                )""")
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS chapters (
                    id INTEGER PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    path TEXT UNIQUE NOT NULL,
                    rel TEXT,
                    title TEXT,
                    track TEXT,
                    ext TEXT,
                    position INTEGER DEFAULT 0,
                    FOREIGN KEY (book_id) REFERENCES books(id)
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
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chapters_book "
                "ON chapters(book_id)")

    # -- import ------------------------------------------------------

    def import_items(self, items):
        """Upsert scanned books. New rows get today's date_added.
        Chapters are synced per book (added/updated/removed).
        Returns the number of newly added books."""
        today = date.today().isoformat()
        new = 0
        with self._lock, self._conn:
            for it in items:
                chapters = it.get("chapters") or []
                cur = self._conn.execute(
                    "SELECT id FROM books WHERE path = ?", (it["path"],))
                row = cur.fetchone()
                if row is None:
                    cur = self._conn.execute("""
                        INSERT INTO books
                        (path, rel, kind, ext, author, book, title, track,
                         lang, has_tags, mojibake, translit, has_art,
                         date_added, chapter_count)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (it["path"], it["rel"], it["kind"], it["ext"],
                         it["author"], it["book"], it["title"], it["track"],
                         it["lang"], int(it["has_tags"]),
                         int(it["mojibake"]), int(it["translit"]),
                         int(it["has_art"]), today, len(chapters) or 1))
                    book_id = cur.lastrowid
                    new += 1
                else:
                    book_id = row["id"]
                    self._conn.execute("""
                        UPDATE books SET rel=?, kind=?, ext=?, author=?,
                            book=?, title=?, track=?, lang=?, has_tags=?,
                            mojibake=?, translit=?, has_art=?,
                            chapter_count=?
                        WHERE id=?""",
                        (it["rel"], it["kind"], it["ext"], it["author"],
                         it["book"], it["title"], it["track"], it["lang"],
                         int(it["has_tags"]), int(it["mojibake"]),
                         int(it["translit"]), int(it["has_art"]),
                         len(chapters) or 1, book_id))
                # Fold in stale per-file rows from before folder
                # grouping existed (their tags are merged, not lost).
                if chapters:
                    self._absorb_stale_rows(
                        book_id, [c["path"] for c in chapters])
                self._sync_chapters(book_id, chapters)
        return new

    def _absorb_stale_rows(self, book_id, chapter_paths):
        """Delete old per-file book rows now covered by a folder-book's
        chapters, merging their tags into the folder-book."""
        placeholders = ",".join("?" for _ in chapter_paths)
        rows = self._conn.execute(
            f"SELECT id FROM books WHERE path IN ({placeholders}) "
            f"AND id != ?", (*chapter_paths, book_id)).fetchall()
        if not rows:
            return
        merged = set(self.get_tags(book_id))
        for r in rows:
            merged.update(self.get_tags(r["id"]))
            self._conn.execute("DELETE FROM chapters WHERE book_id = ?",
                               (r["id"],))
            self._conn.execute("DELETE FROM tags WHERE book_id = ?",
                               (r["id"],))
            self._conn.execute("DELETE FROM books WHERE id = ?", (r["id"],))
        self.set_tags(book_id, sorted(merged))

    def _sync_chapters(self, book_id, chapters):
        """Make the chapters table match the scanned chapter list."""
        existing = {r["path"]: r["id"] for r in self._conn.execute(
            "SELECT id, path FROM chapters WHERE book_id = ?",
            (book_id,)).fetchall()}
        seen = set()
        for pos, ch in enumerate(chapters):
            seen.add(ch["path"])
            if ch["path"] in existing:
                self._conn.execute("""
                    UPDATE chapters SET rel=?, title=?, track=?, ext=?,
                        position=? WHERE id=?""",
                    (ch["rel"], ch["title"], ch["track"], ch["ext"],
                     pos, existing[ch["path"]]))
            else:
                self._conn.execute("""
                    INSERT INTO chapters
                    (book_id, path, rel, title, track, ext, position)
                    VALUES (?,?,?,?,?,?,?)""",
                    (book_id, ch["path"], ch["rel"], ch["title"],
                     ch["track"], ch["ext"], pos))
        if seen:
            self._conn.execute(
                f"""DELETE FROM chapters WHERE book_id = ?
                    AND path NOT IN ({','.join('?' for _ in seen)})""",
                (book_id, *seen))

    # -- reading -----------------------------------------------------

    def _get_chapters(self, book_id, book):
        rows = self._conn.execute(
            """SELECT path, rel, title, track, ext FROM chapters
               WHERE book_id = ? ORDER BY position, id""",
            (book_id,)).fetchall()
        chapters = [dict(r) for r in rows]
        if not chapters and book.get("path"):
            # Legacy row from before chapter tracking: the book's own
            # path is its single chapter.
            chapters = [{
                "path": book["path"], "rel": book.get("rel") or "",
                "title": book.get("title") or "",
                "track": book.get("track") or "",
                "ext": book.get("ext") or "",
            }]
        return chapters

    def _row_to_dict(self, row):
        d = {c: row[c] for c in BOOK_COLUMNS}
        for flag in ("has_tags", "mojibake", "translit", "has_art"):
            d[flag] = bool(d[flag])
        d["chapter_count"] = d.get("chapter_count") or 1
        d["chapters"] = self._get_chapters(d["id"], d)
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

    def set_location(self, book_id, path, rel):
        """Update a book's own path/rel (e.g. after organize moved its
        chapters into a new folder)."""
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE books SET path = ?, rel = ? WHERE id = ?",
                (path, rel, book_id))

    def mark_moved(self, old_path, new_path, new_rel):
        """Record a chapter file move (organize/undo).

        Returns the affected book id, or None when the path isn't
        tracked. Chapters move individually; the caller refreshes the
        book's own location with set_location() afterwards.
        """
        with self._lock, self._conn:
            ch = self._conn.execute(
                "SELECT id, book_id FROM chapters WHERE path = ?",
                (old_path,)).fetchone()
            if ch is not None:
                self._conn.execute(
                    "UPDATE chapters SET path = ?, rel = ? WHERE id = ?",
                    (new_path, new_rel, ch["id"]))
                return ch["book_id"]
            b = self._conn.execute(
                "SELECT id FROM books WHERE path = ?", (old_path,)).fetchone()
            if b is not None:
                self._conn.execute(
                    "UPDATE books SET path = ?, rel = ? WHERE id = ?",
                    (new_path, new_rel, b["id"]))
                return b["id"]
        return None

    def find_by_path(self, path):
        """Find the book owning a chapter file path (or a book path)."""
        with self._lock:
            row = self._conn.execute(
                """SELECT b.* FROM books b
                   JOIN chapters c ON c.book_id = b.id
                   WHERE c.path = ?""", (path,)).fetchone()
            if row is None:
                row = self._conn.execute(
                    "SELECT * FROM books WHERE path = ?", (path,)).fetchone()
            return self._row_to_dict(row) if row else None

    def prune_missing(self):
        """Drop books whose files no longer exist.

        A book survives while at least one chapter file exists;
        individually-missing chapters are dropped. Returns the number
        of books removed."""
        removed = 0
        with self._lock, self._conn:
            books = self._conn.execute(
                "SELECT id, path FROM books").fetchall()
            for b in books:
                chs = self._conn.execute(
                    "SELECT id, path FROM chapters WHERE book_id = ?",
                    (b["id"],)).fetchall()
                if chs:
                    alive = [c for c in chs if Path(c["path"]).exists()]
                    for c in chs:
                        if not Path(c["path"]).exists():
                            self._conn.execute(
                                "DELETE FROM chapters WHERE id = ?",
                                (c["id"],))
                    if alive:
                        self._conn.execute(
                            "UPDATE books SET chapter_count = ? WHERE id = ?",
                            (len(alive), b["id"]))
                        continue
                elif Path(b["path"]).exists():
                    continue  # legacy single-file row, file still there
                self._conn.execute("DELETE FROM chapters WHERE book_id = ?",
                                   (b["id"],))
                self._conn.execute("DELETE FROM tags WHERE book_id = ?",
                                   (b["id"],))
                self._conn.execute("DELETE FROM books WHERE id = ?",
                                   (b["id"],))
                removed += 1
        return removed

    def close(self):
        with self._lock:
            self._conn.close()
