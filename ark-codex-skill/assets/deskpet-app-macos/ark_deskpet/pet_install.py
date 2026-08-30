"""Atomic installation of generated pets into Application Support."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable

from .manifest import validate_manifest


def validate_pet_name(name: str) -> str:
    """Validates a Unicode pet-library directory name."""
    normalized = name.strip()
    if not normalized or normalized in (".", ".."):
        raise ValueError("桌宠名称不能为空")
    if "/" in normalized or "\x00" in normalized:
        raise ValueError("桌宠名称不能包含路径分隔符")
    return normalized


def install_pet(
    source: Path,
    library: Path,
    name: str | None = None,
    notifier: Callable[[str], bool] | None = None,
) -> Path:
    """Validates and atomically installs one pet, then refreshes the app."""
    pet_name = validate_pet_name(name if name is not None else source.name)
    validate_manifest(source)
    library.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=".ark-pet-install-", dir=library)
    )
    staged_pet = staging_root / pet_name
    target = library / pet_name
    backup = library / f".{pet_name}.previous-{os.getpid()}"
    try:
        shutil.copytree(
            source,
            staged_pet,
            ignore=shutil.ignore_patterns("*.webm", "webm"),
        )
        validate_manifest(staged_pet)
        if target.exists():
            os.replace(target, backup)
        os.replace(staged_pet, target)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
    if notifier is not None:
        notifier("refresh-library")
    return target
