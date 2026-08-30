"""Atomic settings and runtime-state persistence."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .constants import DEFAULT_SETTINGS, SETTINGS_VERSION


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Writes JSON beside its target and atomically replaces the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()


def migrate_settings(raw: Any) -> dict[str, Any]:
    """Merges stored values with current defaults and migrations."""
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return settings
    settings.update(raw)
    if not isinstance(settings.get("pet_states"), dict):
        settings["pet_states"] = {}
    legacy_pet = raw.get("active_pet")
    if legacy_pet and not raw.get("pet"):
        settings["pet"] = legacy_pet
    settings["version"] = SETTINGS_VERSION
    return settings


def load_settings(path: Path) -> dict[str, Any]:
    """Loads and migrates settings, returning defaults on corruption."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    return migrate_settings(raw)


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    """Migrates and atomically saves settings."""
    atomic_write_json(path, migrate_settings(settings))


def read_json(path: Path) -> dict[str, Any] | None:
    """Reads a JSON object, returning None for missing or invalid data."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def pid_is_alive(pid: object) -> bool:
    """Returns whether a process identifier names a live process."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def clean_stale_instance(instance_file: Path, socket_file: Path) -> bool:
    """Removes stale runtime files without touching persistent user data."""
    record = read_json(instance_file)
    if record is not None and pid_is_alive(record.get("pid")):
        return False
    removed = False
    for path in (instance_file, socket_file):
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed
