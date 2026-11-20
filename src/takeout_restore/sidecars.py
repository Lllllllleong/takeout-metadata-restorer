"""Match JSON sidecars to media files, and link files that have no sidecar of
their own (Live Photo videos, `-edited` copies) to the file whose sidecar they share.

Takeout's naming rules, as observed:
- `IMG.jpg.supplemental-metadata.json`, with the suffix truncated anywhere
  (`.supplemental-metada.json`, `.supplemental.json`, ...), or legacy `IMG.jpg.json`.
- The whole stem is cut to 46 characters, which can eat the media extension.
- Duplicate uploads get a counter: `IMG(1).jpg` <-> `IMG.jpg.supplemental-metadata(1).json`.
- The sidecar's `title` is the uploaded filename, which doesn't always follow the
  counters, so it's only a last resort.
"""
import os
import re
from dataclasses import dataclass

from takeout_restore.inventory import MediaFile, Sidecar

SUFFIX = ".supplemental-metadata"
COUNTER = re.compile(r"^(.*)\((\d+)\)$")
EDITED = re.compile(r"-edited$", re.IGNORECASE)
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".3gp"}
STILL_PREFERENCE = (".heic", ".heif", ".jpg", ".jpeg")


@dataclass
class Match:
    media: MediaFile
    sidecar: Sidecar | None
    # How the sidecar was found: exact, prefix, title, edited, live-photo, or none.
    via: str
    # The file whose sidecar this one borrows (original of an edit, still of a Live Photo).
    partner: MediaFile | None = None


def split_counter(stem):
    m = COUNTER.match(stem)
    return (m.group(1), int(m.group(2))) if m else (stem, None)


def media_key(name):
    """`IMG(1).jpg` -> (`IMG.jpg`, 1)."""
    base, ext = os.path.splitext(name)
    base, n = split_counter(base)
    return base + ext, n


def sidecar_key(name):
    """`IMG.jpg.supplemental-metad(1).json` -> (`IMG.jpg`, 1).

    The returned stem is the media name, or a prefix of it when Takeout truncated it.
    """
    stem, n = split_counter(name[: -len(".json")])
    for k in range(len(SUFFIX), 0, -1):
        if stem.endswith(SUFFIX[:k]):
            return stem[:-k], n
    return stem, n


def with_counter(name, n):
    if n is None:
        return name
    base, ext = os.path.splitext(name)
    return f"{base}({n}){ext}"


def match_folder(folder):
    """Return (matches for every media file in the folder, sidecars that matched nothing)."""
    claimed = {}  # media name -> (sidecar, via)
    pending = []
    keys = {}

    for sc in folder.sidecars:
        stem, n = keys[sc.name] = sidecar_key(sc.name)
        target = with_counter(stem, n)
        if target in folder.media and target not in claimed:
            claimed[target] = (sc, "exact")
        else:
            pending.append(sc)

    unmatched = []
    for sc in pending:
        stem, n = keys[sc.name]
        target, via = _prefix_target(folder, claimed, sc, stem, n), "prefix"
        if not target:
            target, via = _title_target(folder, claimed, sc, n), "title"
        if target:
            claimed[target] = (sc, via)
        else:
            unmatched.append(sc)

    matches = []
    by_stem = {}  # lowercase stem without extension -> sidecar'd media, for partner lookups
    for name, (sc, via) in claimed.items():
        by_stem.setdefault(os.path.splitext(name)[0].lower(), []).append(folder.media[name])
    for name, media in folder.media.items():
        if name in claimed:
            sc, via = claimed[name]
            matches.append(Match(media, sc, via))
        else:
            matches.append(_borrow(media, by_stem, claimed))
    return matches, unmatched


def _prefix_target(folder, claimed, sc, stem, n):
    candidates = []
    for name in folder.media:
        if name in claimed:
            continue
        core, mn = media_key(name)
        if mn == n and core.startswith(stem):
            candidates.append(name)
    if len(candidates) > 1:
        candidates = [c for c in candidates if not EDITED.search(os.path.splitext(c)[0])] or candidates
    if len(candidates) > 1:
        title = sc.data.get("title")
        candidates = [c for c in candidates if title and c in (title, with_counter(title, n))]
    return candidates[0] if len(candidates) == 1 else None


def _title_target(folder, claimed, sc, n):
    title = sc.data.get("title")
    if not title:
        return None
    target = with_counter(title, n)
    return target if target in folder.media and target not in claimed else None


def _borrow(media, by_stem, claimed):
    stem, ext = os.path.splitext(media.name)
    if EDITED.search(stem):
        originals = by_stem.get(EDITED.sub("", stem).lower(), [])
        if originals:
            orig = _prefer(originals, ext.lower())
            return Match(media, claimed[orig.name][0], "edited", orig)
    if ext.lower() in VIDEO_EXTS:
        stills = [m for m in by_stem.get(stem.lower(), []) if os.path.splitext(m.name)[1].lower() not in VIDEO_EXTS]
        if stills:
            still = _prefer(stills)
            return Match(media, claimed[still.name][0], "live-photo", still)
    return Match(media, None, "none")


def _prefer(files, ext=None):
    def rank(m):
        e = os.path.splitext(m.name)[1].lower()
        if e == ext:
            return -1
        return STILL_PREFERENCE.index(e) if e in STILL_PREFERENCE else len(STILL_PREFERENCE)

    return min(files, key=rank)


def match_all(inventory):
    matches, unmatched = [], []
    for folder in inventory.folders.values():
        m, u = match_folder(folder)
        matches += m
        unmatched += u
    return matches, unmatched
