"""Functional tests for AudiobookOrganizer v2 backend + database + config.

Plain asserts, runnable with: python3 tests/test_v2.py
Run from anywhere; the script adds the project root to sys.path.

Needs: mutagen, Pillow, ebooklib, pypdf (pip install), ffmpeg for the
MP3 fixtures (falls back to tagging-less WAV fixtures otherwise).
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import (  # noqa: E402
    scan, AUDIO_EXTS, EBOOK_EXTS, SUPPORTED_EXTS, find_folder_cover,
    extract_cover, set_cover, can_set_cover, CoverError,
    UnsupportedFormatError, check_new_book, plan_destinations,
    execute_plan, fingerprint_paths, FilingError,
    find_leftovers, remove_empty_dirs,
    fix_mojibake, clean_name, looks_transliterated, guess_language,
)
from backend.grouping import group_items  # noqa: E402
from db import LibraryDB, DEFAULT_TAG_COLOR  # noqa: E402
import config  # noqa: E402

PASS = []


def check(name, fn):
    try:
        fn()
    except AssertionError as e:
        print(f"FAIL {name}: {e}")
        raise SystemExit(1)
    PASS.append(name)
    print(f"ok   {name}")


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------

def make_mp3(path, title, artist, album, track):
    """Silent 0.5s MP3 with ID3 tags. Needs ffmpeg + libmp3lame."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.5",
         "-c:a", "libmp3lame", "-b:a", "128k", str(path)],
        check=True)
    from mutagen.mp3 import EasyMP3
    a = EasyMP3(str(path))
    a["title"] = title
    a["artist"] = artist
    a["album"] = album
    a["tracknumber"] = str(track)
    a.save()


def make_wav(path, leading_num, rest):
    """Minimal WAV with a leading-number filename (no embedded tags)."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00" * 100)
    os.rename(path, path.parent / f"{leading_num} - {rest}.wav")
    return path.parent / f"{leading_num} - {rest}.wav"


def tiny_jpg(path):
    from PIL import Image
    Image.new("RGB", (10, 10), (200, 30, 30)).save(path, "JPEG")


# --------------------------------------------------------------------------
# (a) scan a 3-chapter folder with group_root=True
# --------------------------------------------------------------------------

def t_scan_folder_book():
    tmp = Path(tempfile.mkdtemp())
    bookdir = tmp / "Test Book Folder"
    bookdir.mkdir()
    # scrambled track order on purpose; tags carry the real order
    make_mp3(bookdir / "z.mp3", "Chapter Two", "Scan Author",
             "Scan Book", 2)
    make_mp3(bookdir / "a.mp3", "Chapter One", "Scan Author",
             "Scan Book", 1)
    make_mp3(bookdir / "m.mp3", "Chapter Ten", "Scan Author",
             "Scan Book", 10)
    tiny_jpg(bookdir / "cover.jpg")

    books = scan(bookdir, group_root=True)
    assert len(books) == 1, f"expected 1 book, got {len(books)}"
    b = books[0]
    assert b["kind"] == "audio"
    assert len(b["chapters"]) == 3, b["chapters"]
    titles = [c["title"] for c in b["chapters"]]
    assert titles == ["Chapter One", "Chapter Two", "Chapter Ten"], titles
    assert b["author"] == "Scan Author", b["author"]
    assert b["book"] == "Scan Book", b["book"]
    assert b["folder_cover"] and b["folder_cover"].endswith("cover.jpg"), \
        b["folder_cover"]
    assert b["has_art"] is True
    src = b.get("sources")
    assert src, "sources dict missing"
    assert src["author"] == "embedded tags", src
    assert src["title"] == "embedded tags", src
    shutil.rmtree(tmp)


def t_scan_ebook_sources():
    tmp = Path(tempfile.mkdtemp())
    # ebook with no embedded metadata -> filename fallback
    p = tmp / "My Lone Ebook.epub"
    import zipfile
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml",
                    '<?xml version="1.0"?><container version="1.0" '
                    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                    '<rootfiles><rootfile full-path="content.opf" '
                    'media-type="application/oebps-package+xml"/>'
                    '</rootfiles></container>')
        zf.writestr("content.opf",
                    '<?xml version="1.0"?><package version="2.0" '
                    'xmlns="http://www.idpf.org/2007/opf" '
                    'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                    '<metadata><dc:title></dc:title></metadata></package>')
    books = scan(tmp, group_root=True)
    assert len(books) == 1, books
    b = books[0]
    assert b["kind"] == "ebook"
    assert b["book"] == "My Lone Ebook", b["book"]
    src = b.get("sources")
    assert src and src["title"] == "filename", src
    assert src["author"] == "none", src
    shutil.rmtree(tmp)


# --------------------------------------------------------------------------
# (b) plan_destinations naming
# --------------------------------------------------------------------------

def t_plan_series():
    book = {
        "author": "Dennis E. Taylor", "book": "All These Worlds",
        "series": "Bobiverse",
        "chapters": [
            {"path": "/in/01.mp3", "title": "Chapter 1", "ext": ".mp3",
             "kind": "audio"},
            {"path": "/in/02.mp3", "title": "Chapter 2", "ext": ".mp3",
             "kind": "audio"},
        ],
    }
    plan = plan_destinations(book, "/lib")
    assert len(plan) == 2
    s1, d1 = plan[0]
    assert s1 == "/in/01.mp3", s1
    expect = str(Path("/lib") / "Dennis E. Taylor" / "Bobiverse"
                 / "All These Worlds" / "001 - Chapter 1.mp3")
    assert d1 == expect, d1
    _, d2 = plan[1]
    assert d2.endswith(str(Path("All These Worlds") / "002 - Chapter 2.mp3")), d2


def t_plan_no_series():
    book = {
        "author": "Andy Weir", "book": "Project Hail Mary", "series": "",
        "chapters": [
            {"path": "/in/x.m4b", "title": "", "ext": ".m4b", "kind": "audio"},
        ],
    }
    plan = plan_destinations(book, "/lib")
    assert len(plan) == 1
    _, d = plan[0]
    # empty chapter title -> original filename stem used
    expect = str(Path("/lib") / "Andy Weir" / "Project Hail Mary"
                 / "001 - x.m4b")
    assert d == expect, d


def t_plan_ebook():
    book = {
        "author": "Brandon Sanderson", "book": "Mistborn", "series": "Era 1",
        "chapters": [
            {"path": "/in/mistborn.epub", "title": "Mistborn",
             "ext": ".epub", "kind": "ebook"},
        ],
    }
    plan = plan_destinations(book, "/lib")
    assert len(plan) == 1
    _, d = plan[0]
    expect = str(Path("/lib") / "Brandon Sanderson" / "Era 1"
                 / "Mistborn.epub")
    assert d == expect, d


def t_plan_skips_identical_src_dst():
    book = {
        "author": "A", "book": "B", "series": "",
        "chapters": [
            {"path": str(Path("/lib") / "A" / "B" / "001 - C.mp3"),
             "title": "C", "ext": ".mp3", "kind": "audio"},
        ],
    }
    assert plan_destinations(book, "/lib") == []


# --------------------------------------------------------------------------
# (c) execute_plan moves files
# --------------------------------------------------------------------------

def t_execute_plan():
    tmp = Path(tempfile.mkdtemp())
    srcdir = tmp / "inbox"
    srcdir.mkdir()
    for name in ("a.wav", "b.wav"):
        with wave.open(str(srcdir / name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(b"\x00\x00" * 50)
    book = {
        "author": "Exec Author", "book": "Exec Book", "series": "S1",
        "chapters": [
            {"path": str(srcdir / "a.wav"), "title": "First", "ext": ".wav",
             "kind": "audio"},
            {"path": str(srcdir / "b.wav"), "title": "Second", "ext": ".wav",
             "kind": "audio"},
        ],
    }
    plan = plan_destinations(book, tmp / "Library")
    assert len(plan) == 2
    execute_plan(plan)
    for src, dst in plan:
        assert not Path(src).exists(), src
        assert Path(dst).is_file(), dst
    shutil.rmtree(tmp)


def t_execute_plan_error():
    try:
        execute_plan([("/nonexistent/x.mp3", "/tmp/nowhere/y.mp3")])
    except FilingError:
        return
    raise AssertionError("execute_plan did not raise FilingError")


def t_execute_plan_copy():
    tmp = Path(tempfile.mkdtemp())
    srcdir = tmp / "inbox"
    srcdir.mkdir()
    with wave.open(str(srcdir / "a.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00" * 50)
    book = {
        "author": "Copy Author", "book": "Copy Book", "series": "",
        "chapters": [
            {"path": str(srcdir / "a.wav"), "title": "Only", "ext": ".wav",
             "kind": "audio"},
        ],
    }
    plan = plan_destinations(book, tmp / "Library")
    execute_plan(plan, mode="copy")
    for src, dst in plan:
        assert Path(src).is_file(), "copy mode must keep the source"
        assert Path(dst).is_file(), dst
    try:
        execute_plan(plan, mode="bogus")
    except FilingError:
        pass
    else:
        raise AssertionError("execute_plan accepted a bogus mode")
    shutil.rmtree(tmp)


# --------------------------------------------------------------------------
# (d) file_book round trip + list_books ordering/search/tag
# --------------------------------------------------------------------------

def _file_sample_book(db, libdir, author, title, tags, series=""):
    srcdir = libdir / "incoming" / title.replace(" ", "_")
    srcdir.mkdir(parents=True)
    ch_paths = []
    for i, name in enumerate(("c1", "c2"), start=1):
        p = srcdir / f"{name}.mp3"
        make_mp3(p, f"Ch {i}", author, title, i)
        ch_paths.append(p)
    book = {"author": author, "book": title, "series": series,
            "chapters": [
                {"path": str(ch_paths[0]), "title": "Ch 1", "ext": ".mp3",
                 "kind": "audio"},
                {"path": str(ch_paths[1]), "title": "Ch 2", "ext": ".mp3",
                 "kind": "audio"},
            ]}
    plan = plan_destinations(book, libdir)
    execute_plan(plan)
    fps = fingerprint_paths([dst for _, dst in plan])
    chapters = []
    for i, (src, dst) in enumerate(plan):
        rel = os.path.relpath(dst, libdir)
        chapters.append({"path": dst, "rel": rel,
                         "title": f"Ch {i + 1}", "track": str(i + 1),
                         "ext": ".mp3"})
    book_id = db.file_book(
        {"title": title, "author": author, "series": series},
        chapters, tags, None,
        str(Path(libdir) / author / (series or "") / title), fps)
    return book_id


def t_db_roundtrip():
    tmp = Path(tempfile.mkdtemp())
    db = LibraryDB(tmp / "lib.db")
    libdir = tmp / "Library"
    id1 = _file_sample_book(db, libdir, "Roundtrip Author", "Alpha Book",
                            ["russian", "fiction"], series="S")
    id2 = _file_sample_book(db, libdir, "Other Author", "Zulu Book",
                            ["english"])

    got = db.get_book(id1)
    assert got and got["title"] == "Alpha Book", got
    assert got["series"] == "S", got
    assert sorted(got["tags"]) == ["fiction", "russian"], got["tags"]
    assert len(got["chapters"]) == 2, got["chapters"]
    assert got["chapters"][0]["position"] == 0
    assert all(c["sha256"] for c in got["chapters"]), "missing fingerprints"

    # default order: date_added DESC (same day -> newest id first)
    listed = db.list_books()
    assert [b["id"] for b in listed] == [id2, id1], \
        [b["id"] for b in listed]

    # search is case-insensitive across title/author/series
    assert [b["id"] for b in db.list_books(search="roundtrip")] == [id1]
    assert [b["id"] for b in db.list_books(search="ALPHA")] == [id1]

    # tag filter
    assert [b["id"] for b in db.list_books(tag="russian")] == [id1]
    assert sorted(b["id"] for b in db.list_books(tag="english")) == [id2]
    assert db.list_books(tag="nope") == []

    # order_by variants
    by_title = db.list_books(order_by="title", order_desc=False)
    assert [b["title"] for b in by_title] == ["Alpha Book", "Zulu Book"]

    # all_tags
    assert db.all_tags() == ["english", "fiction", "russian"], db.all_tags()

    # update_book
    db.update_book(id1, "Alpha Book 2", "Roundtrip Author", "S",
                   ["russian"], None)
    got = db.get_book(id1)
    assert got["title"] == "Alpha Book 2" and got["tags"] == ["russian"]

    # update_chapter_order (reverse)
    ch_ids = [c["id"] for c in got["chapters"]]
    db.update_chapter_order(id1, list(reversed(ch_ids)))
    got = db.get_book(id1)
    assert [c["id"] for c in got["chapters"]] == list(reversed(ch_ids))

    # delete_book
    db.delete_book(id2)
    assert db.get_book(id2) is None
    assert [b["id"] for b in db.list_books()] == [id1]

    db.close()
    shutil.rmtree(tmp)


# --------------------------------------------------------------------------
# (e) check_new_book: meta + fingerprint matches
# --------------------------------------------------------------------------

def t_check_new_book():
    tmp = Path(tempfile.mkdtemp())
    db = LibraryDB(tmp / "lib.db")
    libdir = tmp / "Library"
    _file_sample_book(db, libdir, "Fyodor Dostoevsky",
                      "Crime and Punishment", ["russian"])

    # new scan with different punctuation/case + a byte-identical copy
    incoming = tmp / "incoming"
    incoming.mkdir()
    copy_path = incoming / "copy_of_c1.mp3"
    filed = db.list_books()[0]
    shutil.copyfile(filed["chapters"][0]["path"], copy_path)
    other = incoming / "unrelated.mp3"
    make_mp3(other, "Other", "Someone", "Else", 1)

    new_book = {
        "author": "Fyodor Dostoevsky!!",       # extra punctuation
        "book": "crime  and   punishment",     # case + extra whitespace
        "chapters": [
            {"path": str(copy_path), "title": "Ch 1", "track": "1",
             "ext": ".mp3"},
            {"path": str(other), "title": "Other", "track": "1",
             "ext": ".mp3"},
        ],
    }
    res = check_new_book(new_book, db)
    assert len(res["meta"]) == 1, res["meta"]
    assert res["meta"][0]["title"] == "Crime and Punishment"
    assert len(res["exact"]) == 1, res["exact"]
    hit = res["exact"][0]
    assert hit["new_path"] == str(copy_path), hit
    assert hit["book"]["title"] == "Crime and Punishment"
    assert hit["chapter"]["sha256"] == filed["chapters"][0]["sha256"]

    # clean book -> no hits
    clean = {"author": "New Author", "book": "New Book",
             "chapters": [{"path": str(other), "title": "Other",
                           "track": "1", "ext": ".mp3"}]}
    res2 = check_new_book(clean, db)
    assert res2["meta"] == [] and res2["exact"] == [], res2
    db.close()
    shutil.rmtree(tmp)


# --------------------------------------------------------------------------
# (f) schema migration from an old schema
# --------------------------------------------------------------------------

def t_migration():
    tmp = Path(tempfile.mkdtemp())
    p = tmp / "old.db"
    conn = sqlite3.connect(p)
    # old schema: books missing `series`; no chapters table at all;
    # no tags table; also drop a stray index situation
    conn.execute(
        "CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, "
        "author TEXT, date_added TEXT, cover_path TEXT, library_path TEXT, "
        "chapter_count INTEGER DEFAULT 1)")
    conn.execute(
        "INSERT INTO books (title, author, date_added, library_path) "
        "VALUES ('Old Title', 'Old Author', '2026-01-01', '/x')")
    conn.commit()
    conn.close()

    db = LibraryDB(p)
    books = db.list_books()          # must not crash
    assert len(books) == 1, books
    assert books[0]["series"] == "", books[0]   # missing col -> default

    # chapters table exists now with sha256 column
    cur = db._conn.cursor()
    cur.execute("PRAGMA table_info(chapters)")
    cols = {r["name"] for r in cur.fetchall()}
    assert "sha256" in cols, cols
    assert "position" in cols, cols

    # file a book into the migrated db
    chp = tmp / "ch.mp3"
    make_mp3(chp, "C", "A", "B", 1)
    fps = fingerprint_paths([str(chp)])
    bid = db.file_book({"title": "New", "author": "A", "series": ""},
                       [{"path": str(chp), "rel": "ch.mp3", "title": "C",
                         "track": "1", "ext": ".mp3"}],
                       ["tag1"], None, str(tmp), fps)
    got = db.get_book(bid)
    assert got["chapter_count"] == 1 and got["tags"] == ["tag1"]
    hit = db.find_chapter_by_hash(fps[str(chp)])
    assert hit is not None, "hash lookup failed after migration"
    db.close()

    # second variant: chapters table exists but missing `sha256`
    p2 = tmp / "old2.db"
    conn = sqlite3.connect(p2)
    conn.execute(
        "CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, "
        "author TEXT, series TEXT DEFAULT '', date_added TEXT, "
        "cover_path TEXT, library_path TEXT, chapter_count INTEGER)")
    conn.execute(
        "CREATE TABLE chapters (id INTEGER PRIMARY KEY, book_id INTEGER, "
        "path TEXT UNIQUE, rel TEXT, title TEXT, track TEXT, ext TEXT, "
        "position INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE tags (book_id INTEGER, tag TEXT)")
    conn.commit()
    conn.close()
    db2 = LibraryDB(p2)
    cur = db2._conn.cursor()
    cur.execute("PRAGMA table_info(chapters)")
    cols2 = {r["name"] for r in cur.fetchall()}
    assert "sha256" in cols2, cols2
    assert db2.list_books() == []
    db2.close()
    shutil.rmtree(tmp)


# --------------------------------------------------------------------------
# (g) config defaults / save-load round trip
# --------------------------------------------------------------------------

def t_config():
    cfg = config.load()
    assert cfg["file_mode"] == "move", cfg
    assert cfg["setup_done"] is False
    assert cfg["library_root"] == config.DEFAULT_LIBRARY
    assert config.DEFAULT_LIBRARY == r"D:\Media\1. Audiobooks\Library"

    tmp = Path(tempfile.mkdtemp())
    orig = config._settings_path
    config._settings_path = lambda: tmp / "settings.json"
    try:
        config.save({"setup_done": True, "library_root": r"C:\Lib",
                     "file_mode": "copy", "extra": 1})
        back = config.load()
        assert back["setup_done"] is True
        assert back["library_root"] == r"C:\Lib"
        assert back["file_mode"] == "copy"
        # invalid file_mode resets to move
        config.save({"file_mode": "bogus"})
        assert config.load()["file_mode"] == "move"
    finally:
        config._settings_path = orig
    shutil.rmtree(tmp)


def t_covers_api():
    assert can_set_cover(".mp3") is True
    assert can_set_cover(".epub") is True
    assert can_set_cover(".pdf") is False
    tmp = Path(tempfile.mkdtemp())
    p = tmp / "t.mp3"
    make_mp3(p, "T", "A", "B", 1)
    tiny = tmp / "tiny.jpg"
    tiny_jpg(tiny)
    set_cover(str(p), tiny.read_bytes())
    art = extract_cover(str(p))
    assert art and art[:2] == b"\xff\xd8", art[:10] if art else None
    try:
        set_cover(str(p.with_suffix(".pdf")), b"x")
    except UnsupportedFormatError:
        pass
    else:
        raise AssertionError("expected UnsupportedFormatError")
    shutil.rmtree(tmp)


def main():
    # ffmpeg presence decides whether MP3 fixtures run
    try:
        subprocess.run(["ffmpeg", "-version"], check=True,
                       capture_output=True)
    except Exception:
        print("SKIP: ffmpeg not available - MP3 fixture tests need it")
        return 2

    check("(a) scan folder book", t_scan_folder_book)
    check("(a2) scan ebook sources", t_scan_ebook_sources)
    check("(b) plan with series", t_plan_series)
    check("(b2) plan without series", t_plan_no_series)
    check("(b3) plan ebook", t_plan_ebook)
    check("(b4) plan skips src==dst", t_plan_skips_identical_src_dst)
    check("(c) execute_plan moves", t_execute_plan)
    check("(c2) execute_plan error", t_execute_plan_error)
    check("(c3) execute_plan copy mode", t_execute_plan_copy)
    check("(d) db round trip", t_db_roundtrip)
    check("(e) check_new_book", t_check_new_book)
    check("(f) schema migration", t_migration)
    check("(g) config", t_config)
    check("(extra) covers api", t_covers_api)
    check("(h) date added backdate", t_date_added)
    check("(i) tag metadata", t_tag_meta)
    check("(j) folder cleanup", t_folder_cleanup)
    print(f"\nALL {len(PASS)} TESTS PASSED")
    return 0


# --------------------------------------------------------------------------
# (h) Addendum A: date_added comes from the Date field (backdatable)
# --------------------------------------------------------------------------

def t_date_added():
    tmp = Path(tempfile.mkdtemp())
    db = LibraryDB(tmp / "lib.db")

    def file_dated(title, date):
        chp = tmp / f"{title}.mp3"
        make_mp3(chp, "C", "A", "B", 1)
        fps = fingerprint_paths([str(chp)])
        return db.file_book(
            {"title": title, "author": "A", "series": ""},
            [{"path": str(chp), "rel": "x.mp3", "title": "C",
              "track": "1", "ext": ".mp3"}],
            [], None, str(tmp), fps, date_added=date)

    # backdated book keeps its given date
    id_old = file_dated("oldbook", "2020-05-04")
    assert db.get_book(id_old)["date_added"] == "2020-05-04"

    # omitted date -> today (the auto-populate behavior)
    id_new = file_dated("newbook", None)
    import datetime as _dt
    assert db.get_book(id_new)["date_added"] == _dt.date.today().isoformat()

    # library sort puts the backdated book in its true chronological place
    listed = db.list_books(order_by="date_added", order_desc=False)
    assert [b["title"] for b in listed] == ["oldbook", "newbook"], \
        [b["title"] for b in listed]

    # the edit page can change the date later
    db.update_book(id_new, "newbook", "A", "", [], None,
                   date_added="2019-01-01")
    assert db.get_book(id_new)["date_added"] == "2019-01-01"
    # update without a date leaves the stored date alone
    db.update_book(id_new, "newbook", "A", "", [], None)
    assert db.get_book(id_new)["date_added"] == "2019-01-01"

    db.close()
    shutil.rmtree(tmp)


# --------------------------------------------------------------------------
# (i) Addendum B: tag metadata (color, hidden), rename, duplicates,
#     migration backfill
# --------------------------------------------------------------------------

def t_tag_meta():
    tmp = Path(tempfile.mkdtemp())
    db = LibraryDB(tmp / "lib.db")

    # fresh tag gets the default color, not hidden
    db.ensure_tag_meta("sci-fi")
    m = db.get_tag_meta("sci-fi")
    assert m["color"] == DEFAULT_TAG_COLOR and m["hidden"] is False, m

    # set color + hidden
    db.set_tag_meta("sci-fi", color="#ff0000", hidden=True)
    m = db.get_tag_meta("sci-fi")
    assert m["color"] == "#ff0000" and m["hidden"] is True, m

    # hidden tags are excluded from filter/autocomplete lists...
    assert "sci-fi" not in db.visible_tags()
    # ...but still known to the manager
    assert any(t["tag"] == "sci-fi" and t["hidden"]
               for t in db.all_tag_meta())

    # un-hide restores
    db.set_tag_meta("sci-fi", hidden=False)
    assert "sci-fi" in db.visible_tags()

    # filing a book ensures meta rows for its tags
    chp = tmp / "c.mp3"
    make_mp3(chp, "C", "A", "B", 1)
    fps = fingerprint_paths([str(chp)])
    bid = db.file_book(
        {"title": "T", "author": "A", "series": ""},
        [{"path": str(chp), "rel": "c.mp3", "title": "C",
          "track": "1", "ext": ".mp3"}],
        ["sci-fi", "russian"], None, str(tmp), fps)
    assert db.get_tag_meta("russian")["color"] == DEFAULT_TAG_COLOR
    assert sorted(db.visible_tags()) == ["russian", "sci-fi"]

    # rename propagates to every book using the tag
    bid2 = db.file_book(
        {"title": "T2", "author": "A", "series": ""},
        [{"path": str(chp), "rel": "c.mp3", "title": "C",
          "track": "1", "ext": ".mp3"}],
        ["russian"], None, str(tmp), fps)
    db.rename_tag("russian", "Russian Lit")
    assert db.get_book(bid)["tags"] == ["Russian Lit", "sci-fi"], \
        db.get_book(bid)["tags"]
    assert db.get_book(bid2)["tags"] == ["Russian Lit"]
    assert db.get_tag_meta("russian") is None
    assert db.get_tag_meta("Russian Lit") is not None

    # duplicate names blocked (case-insensitive)
    assert db.tag_name_taken("russian lit", ignore="Russian Lit") is False
    assert db.tag_name_taken("RUSSIAN LIT") is True
    assert db.tag_name_taken("sci-fi") is True
    try:
        db.rename_tag("sci-fi", "russian lit")
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate rename was not blocked")
    assert db.get_tag_meta("sci-fi") is not None  # unchanged

    db.close()

    # migration: an old db with tags but no tag_meta gets it backfilled
    p = tmp / "oldtags.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("CREATE TABLE tags (book_id INTEGER, tag TEXT)")
    conn.execute("INSERT INTO books (id, title) VALUES (1, 'X')")
    conn.execute("INSERT INTO tags VALUES (1, 'mystery')")
    conn.commit()
    conn.close()
    db2 = LibraryDB(p)
    m = db2.get_tag_meta("mystery")
    assert m is not None and m["color"] == DEFAULT_TAG_COLOR, m
    assert db2.visible_tags() == ["mystery"]
    db2.close()
    shutil.rmtree(tmp)


# --------------------------------------------------------------------------
# (j) Addendum C: emptied source folder removal (empty-only, safe)
# --------------------------------------------------------------------------

def t_folder_cleanup():
    tmp = Path(tempfile.mkdtemp())

    # case 1: leftovers keep the folder; leftovers are reported
    src1 = tmp / "incoming" / "book1"
    src1.mkdir(parents=True)
    f1 = make_wav(src1 / "a.wav", 1, "ch1")
    f2 = make_wav(src1 / "b.wav", 2, "ch2")
    (src1 / "notes.nfo").write_text("nfo")
    (src1 / "cover.jpg").write_text("fake")
    plan = [(str(f1), str(tmp / "lib" / "a.mp3")),
            (str(f2), str(tmp / "lib" / "b.mp3"))]
    left = find_leftovers(plan)
    assert str(src1) in left, left
    assert sorted(left[str(src1)]) == ["cover.jpg", "notes.nfo"], left
    # nothing moved yet -> folder still has the audio files too
    removed, kept = remove_empty_dirs([str(src1)])
    assert removed == [] and str(src1) in kept, (removed, kept)
    assert sorted(kept[str(src1)]) == ["1 - ch1.wav", "2 - ch2.wav",
                                       "cover.jpg", "notes.nfo"]

    # case 2: after the audio files move out, empties get removed
    libd = tmp / "lib"
    libd.mkdir(parents=True)
    execute_plan(plan)  # move mode
    removed, kept = remove_empty_dirs([str(src1)])
    assert removed == []  # nfo/jpg still there
    assert str(src1) in kept
    for name in ("notes.nfo", "cover.jpg"):
        (src1 / name).unlink()
    removed, kept = remove_empty_dirs([str(src1)])
    assert removed == [str(src1)], (removed, kept)
    assert not src1.exists()
    # parents are never touched
    assert (tmp / "incoming").exists()
    assert tmp.exists()

    # case 3: a source dir that is already empty is removed quietly
    src3 = tmp / "incoming" / "emptybook"
    src3.mkdir(parents=True)
    removed, kept = remove_empty_dirs([str(src3)])
    assert removed == [str(src3)] and kept == {}
    assert (tmp / "incoming").exists()  # parent still there

    # case 4: missing/unreadable dirs are skipped, not errors
    removed, kept = remove_empty_dirs([str(tmp / "nope")])
    assert removed == [] and kept == {}

    shutil.rmtree(tmp)



if __name__ == "__main__":
    sys.exit(main())
