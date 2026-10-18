"""AudiobookOrganizer v2 GUI package (PySide6, dark theme).

Pages: Library, Add (+ first-run setup wizard, edit dialog).
The GUI codes ONLY against the backend/db/config API contract; it never
imports backend internals.
"""

import os
import uuid

__all__ = ["save_cover_bytes"]


def save_cover_bytes(cover_bytes, cache_dir, prefix="cover"):
    """Write raw cover image bytes into the cover cache dir.

    Returns the absolute path of the written file. Raises ValueError
    when cover_bytes is empty. The extension is sniffed from magic
    bytes (JPEG/PNG), defaulting to .jpg.
    """
    if not cover_bytes:
        raise ValueError("no cover bytes to save")
    os.makedirs(cache_dir, exist_ok=True)
    if cover_bytes[:3] == b"\xff\xd8\xff":
        ext = ".jpg"
    elif cover_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        ext = ".png"
    else:
        ext = ".jpg"
    name = "%s_%s%s" % (prefix, uuid.uuid4().hex, ext)
    path = os.path.join(cache_dir, name)
    with open(path, "wb") as fh:
        fh.write(cover_bytes)
    return path
