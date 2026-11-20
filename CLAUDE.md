# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python CLI (`takeout-restore`) that reads a Google Photos Takeout export (media files + JSON sidecars) and writes a merged, metadata-corrected copy elsewhere. exiftool does every metadata read and write; Python decides what to write. The source export is never modified.

## Commands

```sh
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"   # setup (Windows paths)
.venv/Scripts/python -m pytest                                             # all tests
.venv/Scripts/python -m pytest tests/test_sidecars.py -k truncated         # one test
.venv/Scripts/takeout-restore --help
```

exiftool must be installed (`winget install OliverBetz.ExifTool`; it lands in `%LOCALAPPDATA%\Programs\ExifTool`). Tests that need it are skipped when it's missing.

## Data and privacy

`takeout/` holds the user's real export (95 GB of personal photos) and is gitignored. Never commit real media, sidecars, or anything derived from them. Test fixtures use filenames only, or tiny images generated at test time.

## Takeout quirks the code must handle

These were measured on the real export; keep them in mind when changing matching or resolution logic.

- An export is split into parts (`takeout-<ts>-N-001`, `-002`, …), each with `Takeout/Google Photos/<folder>/`. A file and its sidecar can be in different parts, so folders are merged across parts before matching.
- Sidecar names come in several forms: `IMG_1.HEIC.supplemental-metadata.json`; that suffix truncated anywhere (`.supplemental-metada.json`, `.supplemental.json`, `.s.json`); and legacy `IMG_1.jpg.json`. All names are capped at 51 characters, so a sidecar stem can be cut to 46 and lose the media extension. Duplicate counters go after the suffix: `IMG(1).jpg` ↔ `IMG.jpg.supplemental-metadata(1).json`. If the counter collides with a real filename, the media is renumbered (`VID(2).mp4`) but the sidecar keeps `(1)`. The sidecar's `title` field holds the uploaded filename but doesn't follow counters, so it's only a last resort.
- Files with no sidecar are normal: Live Photo / Motion Photo videos (same base name as the still; `.MP4` that is really QuickTime, no extension, or `.fullsizerender`) and `-edited` copies.
- Extensions often don't match content (`.MP4` that is MOV, `.PNG` that is JPEG, no extension, `.fullsizerender`). Trust content, not extension.
- Sidecar `photoTakenTime.timestamp` is UTC epoch seconds with no time zone; EXIF `DateTimeOriginal` is local time with no zone unless `OffsetTimeOriginal` is set; QuickTime `CreateDate` is UTC.
- `geoData` of 0.0/0.0 means "no location". `geoData` without a non-zero `geoDataExif` is Google's estimate. Embedded GPS is more precise than the sidecar (which can be rounded to 4 decimals), so it is never overwritten.
