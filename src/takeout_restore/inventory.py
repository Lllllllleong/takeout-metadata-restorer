"""Find the parts of a Takeout export and merge their Google Photos folders."""
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MediaFile:
    folder: str
    name: str
    path: Path


@dataclass
class Sidecar:
    folder: str
    name: str
    path: Path
    data: dict


@dataclass
class Folder:
    name: str
    media: dict[str, MediaFile] = field(default_factory=dict)
    sidecars: list[Sidecar] = field(default_factory=list)


@dataclass
class Inventory:
    parts: list[Path]
    folders: dict[str, Folder]
    # Same folder and file name already seen in an earlier part.
    duplicates: list[MediaFile] = field(default_factory=list)
    # JSON files in media folders that couldn't be read or aren't media sidecars.
    bad_sidecars: list[tuple[Path, str]] = field(default_factory=list)


def find_photo_roots(root):
    """Return every `Google Photos` folder in an export: one per archive part."""
    root = Path(root)
    if root.name == "Google Photos":
        return [root]
    candidates = [root / "Google Photos", root / "Takeout" / "Google Photos"]
    candidates += sorted(root.glob("*/Takeout/Google Photos"))
    return [c for c in candidates if c.is_dir()]


def load(root):
    """Walk every part and merge folders with the same name, since a file and
    its sidecar can land in different parts."""
    parts = find_photo_roots(root)
    if not parts:
        raise FileNotFoundError(f"no 'Takeout/Google Photos' folder found under {root}")
    inv = Inventory(parts=parts, folders={})
    for photos_root in parts:
        for folder_path in sorted(p for p in photos_root.iterdir() if p.is_dir()):
            folder = inv.folders.setdefault(folder_path.name, Folder(folder_path.name))
            for path in sorted(folder_path.iterdir()):
                if not path.is_file():
                    continue
                if path.suffix.lower() == ".json":
                    if path.name != "metadata.json":  # album metadata, not a sidecar
                        _add_sidecar(inv, folder, path)
                elif path.name in folder.media:
                    inv.duplicates.append(MediaFile(folder.name, path.name, path))
                else:
                    folder.media[path.name] = MediaFile(folder.name, path.name, path)
    return inv


def _add_sidecar(inv, folder, path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        inv.bad_sidecars.append((path, str(e)))
        return
    if not isinstance(data, dict) or "photoTakenTime" not in data:
        inv.bad_sidecars.append((path, "not a media sidecar"))
        return
    folder.sidecars.append(Sidecar(folder.name, path.name, path, data))
