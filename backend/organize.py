"""Organizing: build a rename/move plan, apply it only on explicit
confirmation, and write an undo log for every apply.

Nothing here runs without the caller asking: build_plan() only computes,
apply_organize()/apply_title_fixes() perform, undo_last() reverses.
"""

import json
import shutil
import time
from pathlib import Path

from .text import clean_name

OWN_PREFIX = "_audiobook_org_"


def build_plan(items):
    """Compute Author/Book/NN - Title.ext destinations.

    items: iterable of dicts with keys src (or path), author, book,
    title, track, ext. Returns [(src_path_str, dst_rel_str), ...].
    """
    plan = []
    used = set()
    for it in items:
        src = it.get("src") or it.get("path")
        if it.get("track"):
            fname = f"{int(it['track']):02d} - {it['title']}{it['ext']}"
        else:
            fname = f"{it['title']}{it['ext']}"
        fname = clean_name(fname, maxlen=120)
        dst_rel = Path(it["author"]) / it["book"] / fname
        base, i = dst_rel, 2
        while str(base).lower() in used:
            dst_rel = base.parent / f"{base.stem} ({i}){base.suffix}"
            base, i = dst_rel, i + 1
        used.add(str(dst_rel).lower())
        plan.append((str(src), str(dst_rel)))
    return plan


def _remove_empty_dirs(root):
    for p in sorted(root.rglob("*"), reverse=True):
        if p.is_dir() and p != root and not any(p.iterdir()):
            try:
                p.rmdir()
            except OSError:
                pass


def _write_undo_log(root, log):
    undo_file = root / f"{OWN_PREFIX}undo_{int(time.time())}.json"
    undo_file.write_text(json.dumps(log, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    return str(undo_file)


def apply_organize(root, plan):
    """Move files per plan. Returns the undo log path."""
    root = Path(root).expanduser().resolve()
    log = []
    for src, dst_rel in plan:
        src_p = Path(src)
        dst = root / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dst))
        log.append({"from": str(src_p.relative_to(root)),
                    "to": str(dst_rel)})
    _remove_empty_dirs(root)
    return _write_undo_log(root, log)


def apply_title_fixes(root, fixes):
    """Apply {old_rel: new_rel} renames. Returns the undo log path."""
    root = Path(root).expanduser().resolve()
    log = []
    for old_rel, new_rel in fixes.items():
        src = root / old_rel
        if not src.exists():
            continue
        dst = root / Path(new_rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        target, i = dst, 2
        while target.exists():
            target = dst.parent / f"{dst.stem} ({i}){dst.suffix}"
            i += 1
        shutil.move(str(src), str(target))
        log.append({"from": str(src.relative_to(root)),
                    "to": str(target.relative_to(root))})
    _remove_empty_dirs(root)
    return _write_undo_log(root, log)


def list_undo_logs(root):
    """Newest-first list of undo logs: [{'path','time','moves'}]."""
    root = Path(root).expanduser().resolve()
    entries = []
    for f in sorted(root.glob(f"{OWN_PREFIX}undo_*.json"), reverse=True):
        try:
            log = json.loads(f.read_text(encoding="utf-8"))
            entries.append({
                "path": str(f),
                "time": time.strftime("%Y-%m-%d %H:%M:%S",
                                      time.localtime(f.stat().st_mtime)),
                "moves": len(log),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return entries


def undo_last(root):
    """Reverse the most recent organize/fix-titles run.

    Returns the number of moves reversed.
    """
    root = Path(root).expanduser().resolve()
    logs = sorted(root.glob(f"{OWN_PREFIX}undo_*.json"))
    if not logs:
        return 0
    log = json.loads(logs[-1].read_text(encoding="utf-8"))
    n = 0
    for entry in reversed(log):
        src = root / entry["to"]
        dst = root / entry["from"]
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        target, i = dst, 2
        while target.exists():
            target = dst.parent / f"{dst.stem} ({i}){dst.suffix}"
            i += 1
        shutil.move(str(src), str(target))
        n += 1
    _remove_empty_dirs(root)
    logs[-1].unlink()
    return n
