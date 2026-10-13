"""Audiobook Organizer backend engine.

Scanning, metadata, text repair, duplicates, cover art, and organizing
with undo support. The GUI layer calls these functions; the functions
never touch the GUI and never rename/move/delete anything unless the
caller explicitly asks (apply_organize / apply_title_fixes / set_cover).
"""

from .text import (
    fix_mojibake,
    clean_name,
    cyrillic_ratio,
    looks_transliterated,
    guess_language,
)
from .scan import (
    AUDIO_EXTS,
    EBOOK_EXTS,
    SUPPORTED_EXTS,
    scan,
    scan_stats,
    read_audio_tags,
    read_ebook_meta,
)
from .grouping import (
    group_items,
    find_folder_cover,
    chapter_sort_key,
    COVER_FILENAMES,
)
from .duplicates import find_duplicates
from .organize import (
    build_plan,
    apply_organize,
    apply_title_fixes,
    undo_last,
    list_undo_logs,
)
from .covers import (
    CoverError,
    UnsupportedFormatError,
    can_set_cover,
    extract_cover,
    set_cover,
)

__all__ = [
    "fix_mojibake", "clean_name", "cyrillic_ratio",
    "looks_transliterated", "guess_language",
    "AUDIO_EXTS", "EBOOK_EXTS", "SUPPORTED_EXTS",
    "scan", "scan_stats", "read_audio_tags", "read_ebook_meta",
    "group_items", "find_folder_cover", "chapter_sort_key",
    "COVER_FILENAMES",
    "find_duplicates",
    "build_plan", "apply_organize", "apply_title_fixes",
    "undo_last", "list_undo_logs",
    "CoverError", "UnsupportedFormatError",
    "can_set_cover", "extract_cover", "set_cover",
]
