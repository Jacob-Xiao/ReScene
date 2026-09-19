"""Disk retention for locally stored request artefacts.

Every YOLO/GPT request writes its input and output images under
``data/images``. Nothing removed them, so a long-running or busy server grows
the directory without bound until the disk fills and the service dies.

Pure stdlib so the pruning rules are unit-testable without Flask or the DB.
"""

import os
import time

# Only the artefacts this server writes; leaves operator files alone.
DEFAULT_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def _candidate_files(directory: str, suffixes) -> list:
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return []

    files = []
    for name in names:
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        if suffixes is not None and not name.lower().endswith(tuple(suffixes)):
            continue
        files.append(path)
    return files


def prune_files(
    directory: str,
    max_age_seconds: float,
    max_files: int,
    now: float = None,
    suffixes=DEFAULT_SUFFIXES,
) -> dict:
    """Delete stale and surplus files from ``directory``.

    Two independent bounds, applied in order:

    1. age — anything last modified longer ago than ``max_age_seconds``
    2. count — if more than ``max_files`` remain, the oldest go first

    Returns a summary dict; individual failures (a file already removed by
    another process) are counted and skipped rather than raising.
    """
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be >= 0")
    if max_files < 0:
        raise ValueError("max_files must be >= 0")

    now = time.time() if now is None else now
    entries = []
    for path in _candidate_files(directory, suffixes):
        try:
            entries.append((os.path.getmtime(path), os.path.getsize(path), path))
        except OSError:
            continue

    removed = 0
    freed = 0
    failures = 0
    survivors = []

    cutoff = now - max_age_seconds
    for mtime, size, path in entries:
        if mtime < cutoff:
            if _unlink(path):
                removed += 1
                freed += size
            else:
                failures += 1
        else:
            survivors.append((mtime, size, path))

    if len(survivors) > max_files:
        survivors.sort(key=lambda entry: entry[0])
        surplus = len(survivors) - max_files
        for _mtime, size, path in survivors[:surplus]:
            if _unlink(path):
                removed += 1
                freed += size
            else:
                failures += 1
        survivors = survivors[surplus:]

    return {
        "removed": removed,
        "failed": failures,
        "freed_bytes": freed,
        "kept": len(survivors),
    }


def _unlink(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except OSError:
        return False
