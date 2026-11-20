import json

import pytest

from takeout_restore.inventory import load


def write_part(root, part, files):
    base = root / part / "Takeout" / "Google Photos"
    for rel, content in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content) if isinstance(content, dict) else content, encoding="utf-8")


def test_merges_parts_and_skips_album_metadata(tmp_path):
    sidecar = {"title": "IMG_1.jpg", "photoTakenTime": {"timestamp": "0"}}
    write_part(tmp_path, "takeout-1-001", {"Photos from 2020/IMG_1.jpg": "x", "Album/metadata.json": {}})
    write_part(tmp_path, "takeout-1-002", {"Photos from 2020/IMG_1.jpg.supplemental-metadata.json": sidecar})

    inv = load(tmp_path)

    assert len(inv.parts) == 2
    folder = inv.folders["Photos from 2020"]
    assert list(folder.media) == ["IMG_1.jpg"]
    assert [s.name for s in folder.sidecars] == ["IMG_1.jpg.supplemental-metadata.json"]
    assert inv.folders["Album"].sidecars == []


def test_reports_duplicates_and_bad_json(tmp_path):
    write_part(tmp_path, "takeout-1-001", {"Photos from 2020/IMG_1.jpg": "a", "Photos from 2020/broken.json": "{"})
    write_part(tmp_path, "takeout-1-002", {"Photos from 2020/IMG_1.jpg": "b", "Photos from 2020/other.json": {"x": 1}})

    inv = load(tmp_path)

    assert [d.name for d in inv.duplicates] == ["IMG_1.jpg"]
    assert sorted(p.name for p, _ in inv.bad_sidecars) == ["broken.json", "other.json"]


def test_accepts_google_photos_folder_directly(tmp_path):
    write_part(tmp_path, "part", {"Photos from 2020/a.jpg": "x"})
    assert load(tmp_path / "part" / "Takeout" / "Google Photos").folders["Photos from 2020"].media


def test_missing_export(tmp_path):
    with pytest.raises(FileNotFoundError):
        load(tmp_path)
