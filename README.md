# AudiobookOrganizer v2

A small Windows desktop app for building an organized, searchable
audiobook/ebook library **one book at a time**. You bring in a book,
fix its title/author/tags/cover, and file it into your clean library —
the app never bulk-reorganizes anything and never changes a file without
your explicit confirmation.

## Get the app (no Python needed)

1. Create a GitHub repo and upload these files to it. (If the repo's
   Actions tab shows a "get started" page instead of your build, the
   hidden `.github` folder didn't upload — create
   `.github/workflows/build.yml` in the repo manually and paste in the
   file from here.)
2. Make sure the repo's **Settings → Actions → General → Workflow
   permissions** is set to **Read and write**.
3. Go to **Releases → Create a new release**, create tag `v1.0.0`
   (or any `v*` tag), and publish. GitHub builds the `.exe`
   automatically (~5–10 minutes).
4. Download `AudiobookOrganizer.exe` from the release and double-click
   it. That's it — no install, no terminal.

On first launch the app asks where your clean library should live
(sensible default pre-filled), whether filing moves or copies files,
and shows the naming pattern. Your library database lives *inside*
your library folder (`.audiobook_organizer/library.db`), so updating
the app can never wipe it.

**Note:** Windows SmartScreen may warn about the download because the
`.exe` isn't code-signed. That's expected for a self-built app — click
"More info" → "Run anyway".

**GitHub lessons learned the hard way:**
- If the Actions tab shows no build for your tag, the hidden `.github`
  folder probably didn't upload — create
  `.github/workflows/build.yml` in the repo manually.
- **Upload every file, including `config.py` next to `main.py`.**
  PyInstaller does *not* fail the build when a file is missing from the
  repo — it only writes a warning into the build log and still ships an
  `.exe` that dies on startup with `ModuleNotFoundError`. If a fresh
  `.exe` won't start at all, check the repo has all the files, and
  search the Actions build log for "missing module named". The workflow
  now fails the build loudly if any of the app's own modules are
  missing, instead of shipping a dead `.exe`.
- Never re-run a release to fix the code — publish a **new** tag (e.g.
  `v2.1.1`); re-running replays the old code.

## Run from source

You need Python 3.12 on Windows.

```
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

## How it works

- **Add tab** — drag in a folder (or Browse). Three screens:
  1. *Book details:* cover (never stretched), tags with autocomplete,
     Title/Author/Series fields. Blue outline = the app's guess, gray =
     empty, green = edited by you. Flags like **transliterated?** appear
     under the field; they never change anything on their own.
  2. *Chapters:* reorder by dragging, preview any chapter by ear.
  3. *Review & file:* summary, duplicate warnings (same author+title
     already in your library, or byte-identical files), and a preview
     of exactly where every file will go
     (`Library/Author/Series/Book/001 - Chapter 1.mp3`). One
     "Add to library" button with a confirmation. Files are then moved
     into your library. One-way — no undo.
- **Library tab** — search by title/author/series, filter by tags, sort
  by date added/title/author. Click a row to open the book's folder;
  click **⋮** to edit (same layout as the Add page, with Back / Save
  Changes / Delete). Delete asks "Are you sure?" and moves the files to
  the Recycle Bin — recoverable, not permanent.

## Honest limitations

- Cover-art editing is supported for MP3, M4B/M4A, FLAC, OGG/Opus, and
  EPUB only; other formats tell you so instead of failing silently.
- The app never converts audio formats.
- Transliterated Russian titles are flagged for your review; the app
  never renames them on its own — you type the Cyrillic.
- If the app ever crashes on startup, it writes
  `AudiobookOrganizer-crash.log` next to the `.exe` — share that file
  when reporting the problem.
