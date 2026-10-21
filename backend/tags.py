"""Write the library's confirmed metadata back into audio files' tags
(Addendum I, Daniel's request).

At filing time - and again when a filed book's details are saved from
the edit page - each audio file gets:
    album  = the book title as confirmed on the review step
    artist = the author
    title  = the chapter title (a single-file book: the book title)
    track  = the chapter number

Tags are written as proper Unicode, so Cyrillic displays correctly in
any player. Only these four fields are touched; other frames (encoder,
year, length) are left as they are. Ebooks are never written - their
metadata lives in incompatible formats. Failures are reported to the
caller, never fatal: the book is filed regardless.
"""

import os
from pathlib import Path

from .filing import _chapter_title


class TagError(Exception):
    """Tags for a file could not be written."""


class UnsupportedTagFormat(TagError):
    """The file's format has no tag writer here."""


_WRITE_EXTS = {".mp3", ".m4a", ".m4b", ".mp4", ".flac", ".ogg", ".opus"}


def can_write_tags(path_or_ext):
    ext = str(path_or_ext or "")
    if not ext.startswith("."):
        ext = Path(ext).suffix
    return ext.lower() in _WRITE_EXTS


def write_tags(path, *, title, artist, album, track):
    """Set title/artist/album/track on one audio file, in place.

    Raises TagError (or UnsupportedTagFormat) on failure.
    """
    ext = Path(path).suffix.lower()
    try:
        if ext == ".mp3":
            _write_id3(path, title, artist, album, track)
        elif ext in (".m4a", ".m4b", ".mp4"):
            _write_mp4(path, title, artist, album, track)
        elif ext in (".flac", ".ogg", ".opus"):
            _write_vorbis(path, title, artist, album, track)
        else:
            raise UnsupportedTagFormat(
                "no tag writer for '%s' files" % (ext or "unknown"))
    except TagError:
        raise
    except Exception as e:
        raise TagError("%s: %s" % (type(e).__name__, e))


def _write_id3(path, title, artist, album, track):
    from mutagen.id3 import ID3, TALB, TIT2, TPE1, TRCK

    try:
        tags = ID3(path)
    except Exception:
        tags = ID3()  # no ID3 tag yet: start one
    for frame, value in ((TIT2, title), (TPE1, artist), (TALB, album)):
        tags.delall(frame.__name__)
        tags.add(frame(encoding=3, text=value))
    tags.delall("TRCK")
    tags.add(TRCK(encoding=3, text=str(track)))
    tags.save(path)


def _write_mp4(path, title, artist, album, track):
    from mutagen.mp4 import MP4

    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    audio.tags["\xa9nam"] = title
    audio.tags["\xa9ART"] = artist
    audio.tags["\xa9alb"] = album
    audio.tags["trkn"] = [(int(track), 0)]
    audio.save()


def _write_vorbis(path, title, artist, album, track):
    ext = Path(path).suffix.lower()
    if ext == ".flac":
        from mutagen.flac import FLAC
        audio = FLAC(path)
    elif ext == ".ogg":
        from mutagen.oggvorbis import OggVorbis
        audio = OggVorbis(path)
    else:
        from mutagen.oggopus import OggOpus
        audio = OggOpus(path)
    audio["title"] = title
    audio["artist"] = artist
    audio["album"] = album
    audio["tracknumber"] = str(track)
    audio.save()


def write_book_tags(book, plan, chapters):
    """Write tags for a whole filed book. Returns failure strings.

    book: {title, author}. plan: [(src, dst), ...] in chapter order.
    chapters: the filing chapter dicts ({title, ext, track}) in the
    same order as the plan. A single-file book's title tag is the
    book title; otherwise each file's title tag is its chapter title
    (the same cleaned title its filename carries).
    """
    failures = []
    pairs = list(zip(plan or [], chapters or []))
    single = len(pairs) == 1
    book_title = (book or {}).get("title") or ""
    author = (book or {}).get("author") or ""
    for pos, ((src, dst), ch) in enumerate(pairs):
        if not can_write_tags(dst):
            failures.append("%s: no tag writer for '%s' files"
                            % (os.path.basename(dst),
                               Path(dst).suffix.lower() or "unknown"))
            continue
        if single:
            title = book_title
        else:
            title = _chapter_title({"title": ch.get("title") or "",
                                    "path": src})
        try:
            write_tags(dst, title=title, artist=author,
                       album=book_title, track=pos + 1)
        except TagError as exc:
            failures.append("%s: %s" % (os.path.basename(dst), exc))
        except Exception as exc:  # unexpected: report, continue
            failures.append("%s: %s: %s" % (os.path.basename(dst),
                                            type(exc).__name__, exc))
    return failures
