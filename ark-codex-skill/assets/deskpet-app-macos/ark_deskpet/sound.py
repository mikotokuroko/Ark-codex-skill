"""Optional sound discovery without making multimedia a runtime dependency."""

from __future__ import annotations

from pathlib import Path


def sound_path(pet_dir: Path, name: str) -> Path | None:
    """Returns a safe, pet-local audio file path when one exists."""
    candidate = (pet_dir / "sounds" / name).resolve()
    root = (pet_dir / "sounds").resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() and candidate.suffix.lower() in {".wav", ".mp3", ".m4a", ".ogg"} else None
