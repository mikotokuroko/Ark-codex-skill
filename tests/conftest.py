"""Shared fixtures for Ark Codex Deskpet tests."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import zlib

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
APP_ROOT = (
    REPOSITORY / "ark-codex-skill" / "assets" / "deskpet-app-macos"
)
sys.path.insert(0, str(APP_ROOT))

from ark_deskpet.constants import REQUIRED_STATES  # noqa: E402


def png_bytes(width: int = 1, height: int = 1) -> bytes:
    """Returns a minimal valid RGBA PNG."""
    signature = b"\x89PNG\r\n\x1a\n"

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    pixels = b"".join(b"\x00" + b"\x00\x00\x00\x00" * width for _ in range(height))
    return (
        signature
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def make_pet():
    """Builds a complete tiny pet in a caller-provided directory."""

    def factory(root: Path, name: str = "测试桌宠") -> Path:
        pet = root / name
        states = {}
        for state in REQUIRED_STATES:
            frame_dir = pet / "frames" / state
            frame_dir.mkdir(parents=True)
            (frame_dir / "frame_0000.png").write_bytes(png_bytes())
            states[state] = {
                "duration": 50,
                "count": 1,
                "bbox": [0, 0, 0, 0],
                "source": f"{state}.webm",
            }
        manifest = {"fps": 20, "size": 1, "states": states}
        (pet / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        return pet

    return factory
