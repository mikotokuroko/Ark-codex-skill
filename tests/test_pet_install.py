"""Atomic pet installation and live-refresh tests."""

from pathlib import Path

import pytest

from ark_deskpet.pet_install import install_pet, validate_pet_name


def test_install_pet_excludes_webm_and_notifies(tmp_path: Path, make_pet) -> None:
    source = make_pet(tmp_path / "source", "令")
    (source / "webm").mkdir()
    (source / "webm" / "raw.webm").write_bytes(b"raw")
    commands = []
    installed = install_pet(
        source,
        tmp_path / "library",
        notifier=lambda command: commands.append(command) or True,
    )
    assert installed.name == "令"
    assert (installed / "manifest.json").is_file()
    assert not (installed / "webm").exists()
    assert commands == ["refresh-library"]


def test_reinstall_replaces_same_pet_without_touching_other_data(
    tmp_path: Path, make_pet
) -> None:
    library = tmp_path / "library"
    first = make_pet(tmp_path / "first", "Unicode 夕")
    install_pet(first, library)
    persistent = tmp_path / "Application Support" / "settings.json"
    persistent.parent.mkdir()
    persistent.write_text("keep", encoding="utf-8")
    second = make_pet(tmp_path / "second", "Unicode 夕")
    (second / "marker.txt").write_text("new", encoding="utf-8")
    install_pet(second, library)
    assert (library / "Unicode 夕" / "marker.txt").read_text() == "new"
    assert persistent.read_text() == "keep"


def test_invalid_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_pet_name("../escape")
