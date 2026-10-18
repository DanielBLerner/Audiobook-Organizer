
"""JSON settings: %APPDATA%/AudiobookOrganizer/settings.json on Windows,
~/.audiobook_organizer/settings.json elsewhere.

Keys: setup_done (bool), library_root (str),
      file_mode ("move"|"copy", default "move").
"""

import json
import os
from pathlib import Path

DEFAULT_LIBRARY = r"D:\Media\1. Audiobooks\Library"

DEFAULTS = {
    "setup_done": False,
    "library_root": DEFAULT_LIBRARY,
    "file_mode": "move",
}


def _settings_path():
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        return base / "AudiobookOrganizer" / "settings.json"
    return Path.home() / ".audiobook_organizer" / "settings.json"


def load():
    """Return settings dict, merging saved values over the defaults."""
    cfg = dict(DEFAULTS)
    try:
        p = _settings_path()
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k in DEFAULTS:
                    if k in saved:
                        cfg[k] = saved[k]
    except Exception:
        pass
    if cfg.get("file_mode") not in ("move", "copy"):
        cfg["file_mode"] = "move"
    return cfg


def save(d):
    """Persist settings. Unknown keys are kept; file_mode is validated."""
    d = dict(d or {})
    if d.get("file_mode") not in ("move", "copy"):
        d["file_mode"] = "move"
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
