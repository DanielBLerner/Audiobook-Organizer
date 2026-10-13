# Audiobook Organizer — Desktop App Plan

## Overview
- One self-contained **Windows `.exe`** for Daniel's library at `D:\Media\1. Audiobooks\New`
- No Python, PATH, pip, or terminal for normal use
- Backend reuses `~/workspace/audiobook_organizer.py` engine (scan → report → preview → confirm → apply → undo)
- GUI: dark-themed, drag-and-drop import, audio preview, cover-art editing, duplicate detection, tags, library metadata database

## Features (v1)
1. **Scan (non-destructive, default):** recursively finds audio files **and ebooks** (EPUB, PDF, FB2, MOBI, AZW3), reads tags with mutagen, repairs mojibake, guesses language (RU/EN), flags transliterated Russian titles, produces in-app report with format/language breakdowns, metadata coverage, per-book details, needs-review list, and organization preview
2. **Tags:** add free-text tags per book (genre, language, narrator, etc.); filter/search library by tag
3. **Date added:** the app stamps each book's import date; visible and sortable in the library list
4. **Title editor:** edit book/author names in-app, apply proper Cyrillic corrections, apply → undo log saved
5. **Audio preview:** built-in player for unidentified files (play a few seconds to identify a book); works with MP3, M4B, M4A, OGG, WMA, FLAC
6. **Cover art:** embedded-art display; add cover art to books that have none, replace existing covers (audiobooks via embedded tags, ebooks via the EPUB cover page/metadata)
7. **Duplicates:** find exact-duplicate files (hash) and near-duplicate books (same author+title)
8. **Drag & drop import:** drop a folder onto the app window and it scans, imports, and appears in the library with today's date added
9. **Organize:** `Author/Book/NN - Title.ext` with preview, explicit confirmation, undo log
10. **Undo:** reverse the last apply operation

## Non-negotiables
- Nothing renames/moves anything without Daniel's explicit confirmation
- Undo log for every apply
- Transliterated Russian titles are flagged, never auto-renamed
- Lossy→lossy format conversion never happens automatically

## Architecture
- Backend module: scanning, metadata, mojibake repair, language guess, duplicates (from existing script)
- SQLite library DB: book records, tags, date added, cover art paths
- Frontend (PySide6): library grid/table, detail panel with title/author editor, tags editor, cover-art viewer/editor, built-in audio preview player, scan report view, organize preview with confirm, undo history
- Threading: scan runs in background so the UI never freezes
- Build: PyInstaller → single `.exe` via GitHub Actions workflow

## Build pipeline
1. Write backend engine (adapted from existing script)
2. Write GUI (PySide6, dark theme)
3. Write GitHub Actions workflow (`.github/workflows/build.yml`) → builds Windows `.exe` on push/tag
4. Push to GitHub (Daniel creates repo + token, or builds locally if he prefers)
5. Test on the real library, iterate

## Status
- [x] Plan written and approved
- [x] Backend engine written (backend/: scan incl. ebooks, mojibake, language guess, duplicates, organize+undo, cover art; db.py: tags, date added, cover cache)
- [x] GUI written (PySide6 dark theme: library, detail panel, player, report, duplicates, organize, drag & drop, background-thread workers)
- [x] GitHub workflow written (.github/workflows/build.yml — builds Windows .exe on tag push)
- [x] README written (plain-language .exe download + run-from-source instructions)
- [ ] First `.exe` built and tested — needs Daniel: create GitHub repo, push, tag v1.0.0, download from Releases
- [ ] Tested on the real library at `D:\Media\1. Audiobooks\New` — needs Daniel

## Test notes (2026-10-13, Linux)
- All backend modules pass functional tests: mojibake repair, transliteration flagging, MP3/EPUB/PDF/FB2/WAV scanning, MP3/FLAC/OGG/EPUB cover write+extract round-trips, EPUB cover replace leaves no duplicate entries, duplicate detection, organize+undo with DB path remapping end to end.
- Fixed during testing: db.py Lock → RLock deadlock; EPUB OPF fallback for files ebooklib can't parse; EPUB cover replace now removes the old cover page too.
- GUI compiles clean (py_compile) and was logic-reviewed; it could not be visually/run-tested here (no display). PySide6 API usage follows Qt6 patterns (QMediaPlayer + QAudioOutput, Signal/Slot).
- Known honest limitations are listed in README.md.
