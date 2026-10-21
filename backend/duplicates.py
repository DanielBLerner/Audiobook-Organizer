"""Duplicate detection for the intake flow.

check_new_book(new_book, db) -> {"meta": [...], "exact": [...]}

  meta:  database books whose normalized (author, title) match the new
         book's. Normalization = lowercase, strip, remove all
         punctuation, collapse extra whitespace. Each entry is the db
         book dict.
  exact: for each chapter path in the new book, the SHA-256 is computed
         and looked up with db.find_chapter_by_hash(). Each hit is
         {"new_path": ..., "book": db_book_dict, "chapter": db_chapter_dict}.

Hashing a new book's chapters is done here (at check time), not during
scan, so plain scans stay fast.
"""

import hashlib
import re
from pathlib import Path


def _sha256(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def _norm(s):
    """Lowercase, strip, remove all punctuation, collapse whitespace."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def author_key(name):
    """Word-order-insensitive author key (Addendum E): normalized with
    the words sorted, so 'Ливадный Андрей' and 'Андрей Ливадный'
    produce the same key."""
    return " ".join(sorted(_norm(name).split()))


def find_author_variants(author, db):
    """Existing library authors that are the same name written
    differently (Addendum E): same author_key, different raw text.
    An exact same spelling is not a variant - it files into the same
    author folder anyway."""
    author = (author or "").strip()
    if not author:
        return []
    key = author_key(author)
    if not key:
        return []
    out = []
    for existing in db.all_authors():
        existing = (existing or "").strip()
        if existing == author:
            continue
        if author_key(existing) == key:
            out.append(existing)
    return out


def check_new_book(new_book, db):
    """Compare a scanned book dict against the library database.

    new_book: a book dict as returned by scan() (keys: author, book,
    chapters -> [{path, ...}]). db: a LibraryDB instance.
    """
    key = (_norm(new_book.get("author")), _norm(new_book.get("book")))
    meta = [b for b in db.list_books()
            if (_norm(b.get("author")), _norm(b.get("title"))) == key]

    exact = []
    seen = set()
    for ch in new_book.get("chapters") or []:
        new_path = ch.get("path")
        if not new_path or new_path in seen:
            continue
        seen.add(new_path)
        try:
            digest = _sha256(new_path)
        except OSError:
            continue
        hit = db.find_chapter_by_hash(digest)
        if hit:
            book_dict, chapter_dict = hit
            exact.append({"new_path": new_path,
                          "book": book_dict,
                          "chapter": chapter_dict})
    return {"meta": meta, "exact": exact}
