"""AudiobookOrganizer v2 backend."""

from .scan import (
    scan, AUDIO_EXTS, EBOOK_EXTS, SUPPORTED_EXTS,
)
from .grouping import find_folder_cover
from .covers import (
    extract_cover, set_cover, can_set_cover,
    CoverError, UnsupportedFormatError,
)
from .duplicates import check_new_book, author_key, find_author_variants
from .filing import (
    plan_destinations, execute_plan, fingerprint_paths, FilingError,
    find_leftovers, remove_empty_dirs,
)
from .text import (
    fix_mojibake, clean_name, looks_transliterated, guess_language,
)

__all__ = [
    "scan", "AUDIO_EXTS", "EBOOK_EXTS", "SUPPORTED_EXTS",
    "find_folder_cover",
    "extract_cover", "set_cover", "can_set_cover",
    "CoverError", "UnsupportedFormatError",
    "check_new_book", "author_key", "find_author_variants",
    "plan_destinations", "execute_plan", "fingerprint_paths", "FilingError",
    "find_leftovers", "remove_empty_dirs",
    "fix_mojibake", "clean_name", "looks_transliterated", "guess_language",
]
