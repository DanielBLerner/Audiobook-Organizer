"""Duplicate detection.

find_duplicates(items) -> {'exact': [...], 'near': [...]}
  exact: groups of items that are byte-identical files (size + sha256).
  near:  groups of items with the same author+title but different files
         (e.g. the same book in MP3 and M4B, or two rips).

Hashing is done here (not during scan) so plain scans stay fast.
"""

import hashlib
from pathlib import Path


def _sha256(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def find_duplicates(items):
    exact_groups = []
    near_groups = []

    # Exact: same size + same sha256.
    by_size = {}
    for it in items:
        try:
            size = Path(it["path"]).stat().st_size
        except OSError:
            continue
        by_size.setdefault(size, []).append(it)

    for size, group in by_size.items():
        if len(group) < 2:
            continue
        by_hash = {}
        for it in group:
            try:
                digest = _sha256(it["path"])
            except OSError:
                continue
            by_hash.setdefault(digest, []).append(it)
        for digest, dupes in by_hash.items():
            if len(dupes) > 1:
                exact_groups.append(dupes)

    # Near: same normalized author+book, distinct files.
    by_book = {}
    for it in items:
        key = (it["author"].strip().lower(), it["book"].strip().lower())
        by_book.setdefault(key, []).append(it)
    for key, group in by_book.items():
        paths = {it["path"] for it in group}
        if len(paths) > 1:
            # skip groups already fully covered by an exact group
            near_groups.append(sorted(group, key=lambda x: x["rel"]))

    exact_groups.sort(key=lambda g: g[0]["rel"])
    near_groups.sort(key=lambda g: (g[0]["author"].lower(),
                                    g[0]["book"].lower()))
    return {"exact": exact_groups, "near": near_groups}
