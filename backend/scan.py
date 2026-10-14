"""Library scanning: finds audio files and ebooks, reads their metadata,
repairs garbled text, and guesses languages.

scan() is non-destructive - it only reads. Every item it returns is a
plain dict describing one *book* (a folder of chapter files counts as
one book - see backend.grouping), with these keys:

    path       absolute path: the book folder, or the file for a
               single-file book (str)
    rel        path relative to the scanned root (str, OS separators)
    kind       'audio' or 'ebook'
    ext        lowercase extension of the primary file, e.g. '.mp3'
    author     cleaned author name
    book       cleaned book title
    title      cleaned track/chapter title (single-file audio),
               book title (folder-book), or book title (ebook)
    track      track number as string, '' if unknown / not applicable
    lang       'Russian', 'Russian (transliterated?)', or 'English / other'
    has_tags   True when usable embedded metadata was found
    mojibake   True when a name looked garbled but repairable
    translit   True when the metadata looks like transliterated Russian
               (flag for human review only - never auto-renamed)
    has_art    True when embedded cover art (or a folder cover image)
               was found
    chapters   list of {path, rel, title, track, ext}, in chapter order
    chapter_count  len(chapters)
    folder_cover   absolute path of a cover image found in the book's
                   folder, or None
    sources    dict recording where the author/title guesses came from:
               {"author": "embedded tags"|"folder name"|"filename"|"none",
                "title":  "embedded tags"|"folder name"|"filename"|"none"}
               (the UI uses this to flag guesses that need human review)

Nothing here renames, moves, or deletes anything.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from mutagen import File as MutagenFile

from .text import (
    fix_mojibake, clean_name, looks_transliterated, guess_language,
)

AUDIO_EXTS = {".mp3", ".m4b", ".m4a", ".ogg", ".oga", ".opus", ".flac",
              ".wma", ".wav", ".aac", ".aiff", ".aif", ".ape", ".mpc"}
EBOOK_EXTS = {".epub", ".pdf", ".fb2", ".mobi", ".azw3"}
SUPPORTED_EXTS = AUDIO_EXTS | EBOOK_EXTS
OWN_PREFIX = "_audiobook_org_"
LEADING_NUM = re.compile(r"^\s*(\d{1,4})\s*[-._\s]+")


# --------------------------------------------------------------------------
# Metadata readers
# --------------------------------------------------------------------------

def read_audio_tags(path):
    """Return embedded audio metadata as a dict, or {} if none/unreadable."""
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        return {}
    if audio is None or not getattr(audio, "tags", None):
        return {}

    def g(*keys):
        for k in keys:
            if k in audio.tags:
                v = audio.tags[k]
                if isinstance(v, (list, tuple)) and v:
                    v = v[0]
                v = str(v).strip()
                if v:
                    return v
        return ""

    return {
        "title": g("title"),
        "author": g("artist", "albumartist", "author", "composer"),
        "book": g("album"),
        "track": g("tracknumber", "track"),
    }


def _audio_has_art(path):
    """True when the audio file carries embedded cover art."""
    try:
        audio = MutagenFile(path)
    except Exception:
        return False
    if audio is None or not hasattr(audio, "keys"):
        return False
    try:
        keys = list(audio.keys())
    except Exception:
        return False
    for k in keys:
        ku = str(k).upper()
        if (ku.startswith("APIC") or ku == "COVR"
                or ku == "METADATA_BLOCK_PICTURE"
                or ku == "WM/PICTURE"):
            return True
    return False


def read_ebook_meta(path):
    """Return ebook metadata as a dict: title, author, has_cover.

    Best effort per format; falls back to {} when nothing usable is found.
    """
    ext = Path(path).suffix.lower()
    try:
        if ext == ".epub":
            return _epub_meta(path)
        if ext == ".pdf":
            return _pdf_meta(path)
        if ext == ".fb2":
            return _fb2_meta(path)
    except Exception:
        pass
    return {}


def _epub_meta(path):
    try:
        return _epub_meta_ebooklib(path)
    except Exception:
        return _epub_meta_opf(path)


def _epub_meta_ebooklib(path):
    from ebooklib import epub
    book = epub.read_epub(str(path))
    title = ""
    author = ""
    t = book.get_metadata("DC", "title")
    if t:
        title = str(t[0][0]).strip()
    a = book.get_metadata("DC", "creator")
    if a:
        author = str(a[0][0]).strip()
    has_cover = False
    try:
        for item in book.get_items():
            name = item.get_name().lower()
            if "cover" in name and item.media_type.startswith("image/"):
                has_cover = True
                break
    except Exception:
        pass
    return {"title": title, "author": author, "has_cover": has_cover}


def _epub_meta_opf(path):
    """Fallback: read title/author straight from the EPUB's OPF XML."""
    import zipfile
    title, author, has_cover = "", "", False
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        container = [n for n in names if n.endswith("container.xml")]
        opf_name = None
        if container:
            root = ET.fromstring(zf.read(container[0]))
            for el in root.iter():
                if el.tag.rsplit("}", 1)[-1] == "rootfile":
                    opf_name = el.get("full-path")
                    break
        if not opf_name:
            opf_candidates = [n for n in names if n.endswith(".opf")]
            opf_name = opf_candidates[0] if opf_candidates else None
        if not opf_name:
            return {"title": "", "author": "", "has_cover": False}
        opf = ET.fromstring(zf.read(opf_name))

        def text_of(*local_names):
            for el in opf.iter():
                if el.tag.rsplit("}", 1)[-1] in local_names and el.text:
                    return el.text.strip()
            return ""

        title = text_of("title")
        author = text_of("creator")
        for el in opf.iter():
            local = el.tag.rsplit("}", 1)[-1]
            if local == "item":
                href = (el.get("href") or "").lower()
                mtype = (el.get("media-type") or "").lower()
                if "cover" in href and mtype.startswith("image/"):
                    has_cover = True
                    break
    return {"title": title, "author": author, "has_cover": has_cover}


def _pdf_meta(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    meta = reader.metadata or {}
    title = str(meta.get("/Title") or "").strip()
    author = str(meta.get("/Author") or "").strip()
    return {"title": title, "author": author, "has_cover": False}


def _fb2_meta(path):
    # FictionBook is XML; namespaces vary, so search by local tag name.
    tree = ET.parse(str(path))
    root = tree.getroot()

    def find_text(*names):
        for el in root.iter():
            local = el.tag.rsplit("}", 1)[-1]
            if local in names and el.text and el.text.strip():
                return el.text.strip()
        return ""

    title = find_text("book-title")
    first = find_text("first-name")
    last = find_text("last-name")
    author = " ".join(p for p in (first, last) if p)
    has_cover = any(
        el.tag.rsplit("}", 1)[-1] == "binary"
        and (el.get("id") or "").lower().startswith("cover")
        for el in root.iter()
    )
    return {"title": title, "author": author, "has_cover": has_cover}


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------

def _prettify(stem):
    s = re.sub(r"[_\.]+", " ", stem)
    return re.sub(r"\s+", " ", s).strip()


def _parse_tracknum(raw):
    m = re.match(r"\s*(\d{1,4})", raw or "")
    return m.group(1) if m else ""


def _should_skip(root, p):
    if p.name.startswith(OWN_PREFIX):
        return True
    rel = p.relative_to(root)
    return any(part.startswith(".") for part in rel.parts)


def _scan_audio(root, p, rel):
    tags = read_audio_tags(p)
    m = LEADING_NUM.match(p.stem)
    num = m.group(1) if m else ""
    stem_rest = p.stem[m.end():] if m else p.stem

    author_src = "embedded tags"
    raw_author = tags.get("author")
    if not raw_author:
        author_src = "none"
    author = clean_name(raw_author or "Unknown Author")

    title_src = "embedded tags"
    raw_book = tags.get("book")
    if not raw_book:
        # parent folder name is often the book title in messy rips
        raw_book = _prettify(p.parent.name) if p.parent != root else ""
        title_src = "folder name" if raw_book else "none"
    book = clean_name(raw_book or "Unknown Book")
    title = clean_name(tags.get("title") or _prettify(stem_rest) or p.stem)
    track = _parse_tracknum(tags.get("track")) or num

    return {
        "path": str(p),
        "rel": str(rel),
        "kind": "audio",
        "ext": p.suffix.lower(),
        "author": author,
        "book": book,
        "title": title,
        "track": track,
        "lang": guess_language(tags.get("author"), tags.get("book"),
                               tags.get("title")),
        "has_tags": bool(tags.get("title") or tags.get("book")),
        "mojibake": fix_mojibake(p.stem) != p.stem,
        "translit": looks_transliterated(
            " ".join([tags.get("author") or "", tags.get("book") or "",
                      tags.get("title") or ""])),
        "has_art": _audio_has_art(p),
        "sources": {"author": author_src, "title": title_src},
        # Raw tag values for folder-as-book grouping (most common
        # album/author across chapters wins). Stripped out by the
        # grouping step; never stored in the database.
        "_raw_author": tags.get("author") or "",
        "_raw_book": tags.get("book") or "",
    }


def _scan_ebook(root, p, rel):
    meta = read_ebook_meta(p)
    author_src = "embedded tags" if meta.get("author") else "none"
    title_src = "embedded tags" if meta.get("title") else "filename"
    author = clean_name(meta.get("author") or "Unknown Author")
    book = clean_name(meta.get("title") or _prettify(p.stem))
    return {
        "path": str(p),
        "rel": str(rel),
        "kind": "ebook",
        "ext": p.suffix.lower(),
        "author": author,
        "book": book,
        "title": book,
        "track": "",
        "lang": guess_language(meta.get("author"), meta.get("title"), ""),
        "has_tags": bool(meta.get("title")),
        "mojibake": fix_mojibake(p.stem) != p.stem,
        "translit": looks_transliterated(
            " ".join([meta.get("author") or "", meta.get("title") or ""])),
        "has_art": bool(meta.get("has_cover")),
        "sources": {"author": author_src, "title": title_src},
    }


def scan(root, group_root=False):
    """Recursively scan *root* for audiobooks and ebooks. Read-only.

    Returns one dict per *book*: a folder of chapter audio files is a
    single book (see backend.grouping). Each book dict carries a
    ``chapters`` list with one entry per file, plus a ``sources`` dict
    recording where the author/title guesses came from.
    """
    from .grouping import group_items  # local import: keeps import light
    root = Path(root).expanduser().resolve()
    file_items = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in SUPPORTED_EXTS:
            continue
        if _should_skip(root, p):
            continue
        rel = p.relative_to(root)
        if p.suffix.lower() in AUDIO_EXTS:
            file_items.append(_scan_audio(root, p, rel))
        else:
            file_items.append(_scan_ebook(root, p, rel))
    return group_items(file_items, root, group_root=group_root)


# --------------------------------------------------------------------------
# Report statistics (for the GUI scan view)
# --------------------------------------------------------------------------

def scan_stats(items):
    """Statistics over book dicts (as returned by scan()).

    NOTE: v2 has no organizer step, so there is no filing preview here -
    the intake flow plans filing per book with user confirmation.
    """
    formats = {}
    languages = {}
    chapters = 0
    for it in items:
        formats[it["ext"]] = formats.get(it["ext"], 0) + 1
        languages[it["lang"]] = languages.get(it["lang"], 0) + 1
        chapters += it.get("chapter_count") or 1

    books = {(it["author"], it["book"]) for it in items}
    suspects = sorted({(it["author"], it["book"]) for it in items
                       if it["translit"]})
    review = [it for it in items
              if not it["has_tags"] and it["author"] == "Unknown Author"]

    return {
        "total": len(items),
        "chapters": chapters,
        "formats": dict(sorted(formats.items(), key=lambda x: -x[1])),
        "languages": dict(sorted(languages.items(), key=lambda x: -x[1])),
        "tagged": sum(1 for it in items if it["has_tags"]),
        "mojibake": sum(1 for it in items if it["mojibake"]),
        "books": len(books),
        "suspects": suspects,
        "review": sorted(review, key=lambda x: x["rel"])[:50],
        "review_total": len(review),
    }
