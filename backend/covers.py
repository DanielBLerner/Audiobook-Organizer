"""Cover art: extract embedded art, and add/replace it.

Supported for writing: MP3, M4B/M4A, FLAC, OGG/Opus (embedded tags)
and EPUB (cover page). Other formats raise UnsupportedFormatError with
a plain-language explanation - the GUI shows that message instead of
failing silently.

Images are normalized to JPEG (max 1400px) via Pillow before embedding.
"""

import base64
import io
import struct
from pathlib import Path

from PIL import Image

WRITABLE_AUDIO = {".mp3", ".m4b", ".m4a", ".flac", ".ogg", ".oga", ".opus"}
WRITABLE_EBOOK = {".epub"}


class CoverError(Exception):
    """Something went wrong reading or writing cover art."""


class UnsupportedFormatError(CoverError):
    """This file format can't carry cover art (at least not via this app)."""


def can_set_cover(ext):
    return ext.lower() in (WRITABLE_AUDIO | WRITABLE_EBOOK)


def _normalize_image(image_bytes):
    """Convert any image to a reasonable JPEG for embedding."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        raise CoverError(f"Could not read that image file: {e}")
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA")
                 else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((1400, 1400), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

def _parse_flac_picture_block(block):
    """Pull raw image bytes out of a FLAC/Vorbis picture block."""
    try:
        off = 4  # picture type
        mime_len = struct.unpack(">I", block[off:off + 4])[0]
        off += 4
        off += mime_len  # mime string
        desc_len = struct.unpack(">I", block[off:off + 4])[0]
        off += 4 + desc_len  # description
        off += 16  # width, height, depth, colors
        data_len = struct.unpack(">I", block[off:off + 4])[0]
        off += 4
        return block[off:off + data_len]
    except (struct.error, IndexError):
        return None


def extract_cover(path):
    """Return embedded cover art as image bytes, or None."""
    ext = Path(path).suffix.lower()
    try:
        if ext == ".mp3":
            return _extract_mp3(path)
        if ext in (".m4b", ".m4a"):
            return _extract_mp4(path)
        if ext == ".flac":
            return _extract_flac(path)
        if ext in (".ogg", ".oga", ".opus"):
            return _extract_ogg(path)
        if ext == ".epub":
            return _extract_epub(path)
    except Exception:
        return None
    return None


def _extract_mp3(path):
    from mutagen.mp3 import MP3
    from mutagen.id3 import APIC
    audio = MP3(path)
    if audio.tags is None:
        return None
    for value in audio.tags.values():
        if isinstance(value, APIC) and value.data:
            return bytes(value.data)
    return None


def _extract_mp4(path):
    from mutagen.mp4 import MP4
    audio = MP4(path)
    if audio.tags is None:
        return None
    covr = audio.tags.get("covr")
    if covr:
        return bytes(covr[0])
    return None


def _extract_flac(path):
    from mutagen.flac import FLAC
    audio = FLAC(path)
    for pic in audio.pictures:
        if pic.data:
            return bytes(pic.data)
    return None


def _extract_ogg(path):
    from mutagen import File as MutagenFile
    audio = MutagenFile(path)
    if audio is None:
        return None
    blocks = audio.get("metadata_block_picture")
    if not blocks:
        return None
    return _parse_flac_picture_block(base64.b64decode(blocks[0]))


def _extract_epub(path):
    try:
        from ebooklib import epub
        book = epub.read_epub(str(path))
        for item in book.get_items():
            name = item.get_name().lower()
            if "cover" in name and item.media_type.startswith("image/"):
                return item.get_content()
    except Exception:
        pass
    # Fallback: pull the cover image straight out of the zip.
    try:
        import zipfile
        with zipfile.ZipFile(path) as zf:
            for n in zf.namelist():
                low = n.lower()
                if ("cover" in low
                        and low.endswith((".jpg", ".jpeg", ".png", ".webp"))):
                    return zf.read(n)
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def set_cover(path, image_bytes):
    """Add or replace cover art. Raises CoverError / UnsupportedFormatError."""
    ext = Path(path).suffix.lower()
    if not can_set_cover(ext):
        raise UnsupportedFormatError(
            f"Cover art can't be changed for {ext.upper()} files in this "
            f"version - the format doesn't support embedded covers cleanly. "
            f"MP3, M4B/M4A, FLAC, OGG and EPUB are supported.")
    jpeg = _normalize_image(image_bytes)
    try:
        if ext == ".mp3":
            _set_mp3(path, jpeg)
        elif ext in (".m4b", ".m4a"):
            _set_mp4(path, jpeg)
        elif ext == ".flac":
            _set_flac(path, jpeg)
        elif ext in (".ogg", ".oga", ".opus"):
            _set_ogg(path, jpeg)
        elif ext == ".epub":
            _set_epub(path, jpeg)
    except UnsupportedFormatError:
        raise
    except Exception as e:
        raise CoverError(f"Could not write cover art: {e}")


def _set_mp3(path, jpeg):
    from mutagen.mp3 import MP3
    from mutagen.id3 import APIC
    audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.delall("APIC")
    audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3,
                        desc="Cover", data=jpeg))
    audio.save()


def _set_mp4(path, jpeg):
    from mutagen.mp4 import MP4, MP4Cover
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    audio.tags["covr"] = [MP4Cover(jpeg, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _set_flac(path, jpeg):
    from mutagen.flac import FLAC, Picture
    audio = FLAC(path)
    audio.clear_pictures()
    pic = Picture()
    pic.type = 3  # front cover
    pic.mime = "image/jpeg"
    pic.desc = ""
    pic.data = jpeg
    audio.add_picture(pic)
    audio.save()


def _set_ogg(path, jpeg):
    from mutagen import File as MutagenFile
    from mutagen.flac import Picture
    audio = MutagenFile(path)
    if audio is None:
        raise CoverError("Could not read audio tags.")
    pic = Picture()
    pic.type = 3
    pic.mime = "image/jpeg"
    pic.desc = ""
    pic.data = jpeg
    block = base64.b64encode(pic.write()).decode("ascii")
    if "metadata_block_picture" in audio:
        del audio["metadata_block_picture"]
    audio["metadata_block_picture"] = [block]
    audio.save()


def _set_epub(path, jpeg):
    from ebooklib import epub
    try:
        book = epub.read_epub(str(path))
    except Exception:
        raise CoverError(
            "This EPUB file looks damaged (its internal index can't be "
            "read), so the cover can't be replaced safely. The file itself "
            "was left untouched.")
    book.items = [it for it in book.items
                  if not _is_cover_item(it)]
    book.set_cover("cover.jpg", jpeg)
    epub.write_epub(str(path), book)


def _is_cover_item(item):
    """True for an existing cover image or cover page.

    Matches ebooklib's own cover ids ('cover', 'cover-img') as well as
    image files with 'cover' in the name, so replacing a cover never
    leaves a stale duplicate behind.
    """
    if item.get_id() in ("cover", "cover-img"):
        return True
    return (item.media_type.startswith("image/")
            and "cover" in item.get_name().lower())
