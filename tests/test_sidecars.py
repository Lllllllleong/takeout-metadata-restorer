from pathlib import Path

import pytest

from takeout_restore.inventory import Folder, MediaFile, Sidecar
from takeout_restore.sidecars import match_folder, media_key, sidecar_key

# Synthetic names that follow the patterns seen in real exports.
FB = "123456789_123456789012345_1234567890123456789_"  # 46 chars, as Takeout truncates


def folder(media, sidecars):
    """sidecars: {json file name: title}"""
    f = Folder("Photos from 2020")
    for name in media:
        f.media[name] = MediaFile(f.name, name, Path(name))
    for name, title in sidecars.items():
        f.sidecars.append(Sidecar(f.name, name, Path(name), {"title": title, "photoTakenTime": {}}))
    return f


def by_media(f):
    matches, unmatched = match_folder(f)
    return {m.media.name: (m.sidecar.name if m.sidecar else None, m.via) for m in matches}, unmatched


@pytest.mark.parametrize(
    "json_name, key",
    [
        ("IMG_1001.HEIC.supplemental-metadata.json", ("IMG_1001.HEIC", None)),
        ("VID_20200101_120000_01.mp4.supplemental-metada.json", ("VID_20200101_120000_01.mp4", None)),
        ("2012-01-01 001 2011-12-01 001.JPG.supplemental.json", ("2012-01-01 001 2011-12-01 001.JPG", None)),
        ("IMG_1002.jpg.json", ("IMG_1002.jpg", None)),
        ("IMG_1003.jpg.supplemental-metadata(1).json", ("IMG_1003.jpg", 1)),
        ("IMG_1003.jpg(2).json", ("IMG_1003.jpg", 2)),
        (FB + "(1).json", (FB, 1)),
    ],
)
def test_sidecar_key(json_name, key):
    assert sidecar_key(json_name) == key


def test_media_key():
    assert media_key("IMG(12).jpg") == ("IMG.jpg", 12)
    assert media_key("IMG.jpg") == ("IMG.jpg", None)


def test_naming_variants_match_exactly():
    got, unmatched = by_media(folder(
        ["IMG_1001.HEIC", "VID_20200101_120000_01.mp4", "IMG_1002.jpg", "Photo (1).jpg"],
        {
            "IMG_1001.HEIC.supplemental-metadata.json": "IMG_1001.HEIC",
            "VID_20200101_120000_01.mp4.supplemental-metada.json": "VID_20200101_120000_01.mp4",
            "IMG_1002.jpg.json": "IMG_1002.jpg",
            "Photo (1).jpg.supplemental-metadata.json": "Photo (1).jpg",
        },
    ))
    assert all(via == "exact" for _, via in got.values())
    assert not unmatched


def test_duplicate_counters():
    got, _ = by_media(folder(
        ["IMG_1003.jpg", "IMG_1003(1).jpg"],
        {
            "IMG_1003.jpg.supplemental-metadata.json": "IMG_1003.jpg",
            "IMG_1003.jpg.supplemental-metadata(1).json": "IMG_1003.jpg",
        },
    ))
    assert got["IMG_1003.jpg"] == ("IMG_1003.jpg.supplemental-metadata.json", "exact")
    assert got["IMG_1003(1).jpg"] == ("IMG_1003.jpg.supplemental-metadata(1).json", "exact")


def test_truncated_extension_matches_by_prefix():
    name = "00000IMG_00000_BURST20200101093018478_COVER.jpg"
    got, _ = by_media(folder([name], {name[:46] + ".json": name}))
    assert got[name] == (name[:46] + ".json", "prefix")


def test_truncated_duplicates_follow_counters_not_titles():
    # Real case: the titles are crossed relative to the counters.
    got, unmatched = by_media(folder(
        [FB + "n.jpg", FB + "n(1).jpg"],
        {FB + ".json": FB + "n (1).jpg", FB + "(1).json": FB + "n.jpg"},
    ))
    assert got[FB + "n.jpg"] == (FB + ".json", "prefix")
    assert got[FB + "n(1).jpg"] == (FB + "(1).json", "prefix")
    assert not unmatched


def test_title_is_last_resort():
    got, _ = by_media(folder(["odd name.jpg"], {"unrelated.json": "odd name.jpg"}))
    assert got["odd name.jpg"] == ("unrelated.json", "title")


def test_edited_copy_borrows_original_sidecar():
    matches, _ = match_folder(folder(
        ["IMG_2000.jpg", "IMG_2000-edited.jpg"],
        {"IMG_2000.jpg.supplemental-metadata.json": "IMG_2000.jpg"},
    ))
    edited = next(m for m in matches if m.media.name == "IMG_2000-edited.jpg")
    assert edited.via == "edited"
    assert edited.partner.name == "IMG_2000.jpg"
    assert edited.sidecar.name == "IMG_2000.jpg.supplemental-metadata.json"


def test_live_photo_video_pairs_with_same_counter_still():
    matches, _ = match_folder(folder(
        ["IMG_3000.HEIC", "IMG_3000.MP4", "IMG_3000(1).HEIC", "IMG_3000(1).MP4"],
        {
            "IMG_3000.HEIC.supplemental-metadata.json": "IMG_3000.HEIC",
            "IMG_3000.HEIC.supplemental-metadata(1).json": "IMG_3000.HEIC",
        },
    ))
    got = {m.media.name: (m.via, m.partner.name if m.partner else None) for m in matches}
    assert got["IMG_3000.MP4"] == ("live-photo", "IMG_3000.HEIC")
    assert got["IMG_3000(1).MP4"] == ("live-photo", "IMG_3000(1).HEIC")


def test_live_photo_prefers_heic_still():
    matches, _ = match_folder(folder(
        ["FullSizeRender.jpg", "FullSizeRender.heic", "FullSizeRender.MP4"],
        {
            "FullSizeRender.jpg.supplemental-metadata.json": "FullSizeRender.jpg",
            "FullSizeRender.heic.supplemental-metadata.json": "FullSizeRender.heic",
        },
    ))
    video = next(m for m in matches if m.media.name == "FullSizeRender.MP4")
    assert video.partner.name == "FullSizeRender.heic"


def test_unpaired_and_unmatched():
    got, unmatched = by_media(folder(["random.mov"], {"missing.jpg.supplemental-metadata.json": "missing.jpg"}))
    assert got["random.mov"] == (None, "none")
    assert [s.name for s in unmatched] == ["missing.jpg.supplemental-metadata.json"]
