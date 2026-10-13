# Audiobook Organizer

A small Windows desktop app that tames a messy audiobook/ebook library:
it scans your folders (without touching anything), shows you what's in
there, lets you fix titles, tags and cover art, preview audio, find
duplicates, and — only when you say so — reorganizes everything into
neat `Author / Book / NN - Title` folders, with undo.

Built for a library with transliterated Russian names, mojibake
filenames, and mixed formats (MP3, M4B, FLAC, OGG, EPUB, PDF, FB2, …).

## Option A — download the .exe (no Python needed)

1. Create a GitHub repo named **audiobook-organizer** and push these files to it.
2. Tag the release and push the tag:
   ```
   git tag v1.0.0
   git push origin v1.0.0
   ```
   GitHub Actions builds the Windows `.exe` automatically.
3. Go to the repo's **Releases** page and download `AudiobookOrganizer.exe`.
4. Double-click it. That's it — no install, no terminal.

## Option B — run from source

You need Python 3.12 on Windows.

```
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

## How each feature works

- **Library tab** — every book the app has ever scanned, with cover
  thumbnails. Search by title/author, filter by tag, sort by clicking a
  column header or with the sort control. Drag a folder onto the window
  (or use *Import folder*) to scan it in; scanning only reads files.
- **Report tab** — format and language breakdowns, how many files have
  tags or mojibake in the name, a list of transliterated-Russian
  suspects (*flagged for review — never auto-renamed*), files that need
  review, and a preview of the first 15 planned moves.
- **Duplicates tab** — groups of byte-identical files, and groups that
  are the same author + book in different files. Expand a group to see
  the paths. The app never deletes anything; you decide what to do.
- **Detail panel** (right side of the Library tab) — view/replace cover
  art, edit the title and author, edit comma-separated tags, preview
  audio for audiobooks, and see the file path, format, language, date
  added, and flags.
- **Organize tab** — full preview table of current path → new path. The
  **Confirm & Organize** button asks "Move N files? This can be undone."
  first, and only moves after you say yes. Every run writes an undo log;
  **Undo last** moves the files back.

## Honest limitations

- Cover-art editing is unsupported for WMA, WAV, PDF, MOBI, AZW3, and
  FB2 files — the app will tell you so instead of failing silently.
  Supported: MP3, M4B/M4A, FLAC, OGG/Opus, EPUB.
- The title/author **Save** button writes into the file's embedded tags
  for audiobooks and EPUBs only; for other formats it updates the
  library database and tells you the file itself was left alone.
- Metadata edits (titles, tags, covers) are **not** covered by the
  organize undo log — undo reverses file *moves* only.
- The app never converts audio formats, and nothing is renamed, moved,
  or deleted without your explicit confirmation.
