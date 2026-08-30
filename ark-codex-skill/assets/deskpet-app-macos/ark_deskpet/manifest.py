"""Pet-manifest validation and merged library discovery."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import struct
from typing import Any
import zlib

from .constants import REQUIRED_STATES

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ManifestError(ValueError):
    """Raised when a pet manifest or referenced frame is invalid."""


@dataclass(frozen=True)
class PetEntry:
    """A pet exposed by the merged library."""

    name: str
    path: Path
    bundled: bool


def _read_png_size(path: Path) -> tuple[int, int]:
    """Validates PNG chunks and returns the image dimensions."""
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ManifestError(f"无法读取帧：{path}") from error
    if not data.startswith(PNG_SIGNATURE):
        raise ManifestError(f"损坏的 PNG 帧：{path}")
    offset = len(PNG_SIGNATURE)
    width = 0
    height = 0
    saw_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            raise ManifestError(f"截断的 PNG 帧：{path}")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[end - 4 : end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ManifestError(f"PNG 校验失败：{path}")
        if chunk_type == b"IHDR":
            if length != 13:
                raise ManifestError(f"无效的 PNG 头：{path}")
            width, height = struct.unpack(">II", chunk_data[:8])
        elif chunk_type == b"IEND":
            saw_iend = True
            break
        offset = end
    if width <= 0 or height <= 0 or not saw_iend:
        raise ManifestError(f"不完整的 PNG 帧：{path}")
    return width, height


def validate_manifest(pet_dir: Path) -> dict[str, Any]:
    """Validates a pet manifest and every referenced PNG frame."""
    manifest_path = pet_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"无法读取 manifest.json：{pet_dir}") from error
    if not isinstance(manifest, dict):
        raise ManifestError("manifest.json 顶层必须是对象")
    fps = manifest.get("fps")
    size = manifest.get("size")
    states = manifest.get("states")
    if not isinstance(fps, (int, float)) or fps <= 0:
        raise ManifestError("fps 必须为正数")
    if not isinstance(size, int) or size <= 0:
        raise ManifestError("size 必须为正整数")
    if not isinstance(states, dict):
        raise ManifestError("states 必须是对象")
    missing = [state for state in REQUIRED_STATES if state not in states]
    if missing:
        raise ManifestError(f"缺少必需动作：{', '.join(missing)}")
    for state_name in REQUIRED_STATES:
        info = states[state_name]
        if not isinstance(info, dict):
            raise ManifestError(f"动作 {state_name} 必须是对象")
        count = info.get("count")
        bbox = info.get("bbox")
        if not isinstance(count, int) or count <= 0:
            raise ManifestError(f"动作 {state_name} 的 count 无效")
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or not all(isinstance(value, int) for value in bbox)
            or bbox[0] > bbox[2]
            or bbox[1] > bbox[3]
        ):
            raise ManifestError(f"动作 {state_name} 的 bbox 无效")
        for index in range(count):
            frame = (
                pet_dir
                / "frames"
                / state_name
                / f"frame_{index:04d}.png"
            )
            width, height = _read_png_size(frame)
            if width != size or height != size:
                raise ManifestError(
                    f"帧尺寸应为 {size}x{size}：{frame}"
                )
    return manifest


def _candidate_pets(root: Path, bundled: bool) -> dict[str, PetEntry]:
    """Returns manifest-bearing pet directories from one library root."""
    if not root.is_dir():
        return {}
    result = {}
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.is_dir() and (child / "manifest.json").is_file():
            result[child.name] = PetEntry(child.name, child, bundled)
    return result


def merge_pet_libraries(
    bundled_root: Path, user_root: Path
) -> dict[str, PetEntry]:
    """Merges pet libraries, with user pets overriding bundled pets."""
    pets = _candidate_pets(bundled_root, bundled=True)
    pets.update(_candidate_pets(user_root, bundled=False))
    return dict(sorted(pets.items(), key=lambda item: item[0]))
