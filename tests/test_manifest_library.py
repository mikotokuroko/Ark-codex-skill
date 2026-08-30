"""Manifest and merged pet-library tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ark_deskpet.manifest import (
    ManifestError,
    merge_pet_libraries,
    validate_manifest,
)


def test_valid_manifest_and_unicode_name(tmp_path: Path, make_pet) -> None:
    pet = make_pet(tmp_path, "能天使·测试")
    manifest = validate_manifest(pet)
    assert manifest["fps"] == 20
    assert pet.name == "能天使·测试"


def test_missing_required_state_fails(tmp_path: Path, make_pet) -> None:
    pet = make_pet(tmp_path)
    path = pet / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["states"]["sleep"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ManifestError, match="sleep"):
        validate_manifest(pet)


def test_missing_frame_fails(tmp_path: Path, make_pet) -> None:
    pet = make_pet(tmp_path)
    (pet / "frames" / "move" / "frame_0000.png").unlink()
    with pytest.raises(ManifestError, match="无法读取帧"):
        validate_manifest(pet)


def test_corrupt_frame_fails(tmp_path: Path, make_pet) -> None:
    pet = make_pet(tmp_path)
    (pet / "frames" / "idle" / "frame_0000.png").write_bytes(b"not png")
    with pytest.raises(ManifestError, match="损坏"):
        validate_manifest(pet)


def test_user_pet_overrides_bundled_pet(tmp_path: Path, make_pet) -> None:
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled_pet = make_pet(bundled, "同名桌宠")
    user_pet = make_pet(user, "同名桌宠")
    make_pet(bundled, "仅内置")
    library = merge_pet_libraries(bundled, user)
    assert library["同名桌宠"].path == user_pet
    assert not library["同名桌宠"].bundled
    assert library["仅内置"].path != bundled_pet
    assert library["仅内置"].bundled
