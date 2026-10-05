"""Compatibility and pure runtime checks for the multi-group port."""

from __future__ import annotations

import json
from pathlib import Path

from ark_deskpet.display import Rect
from ark_deskpet.manifest import (
    animation_groups,
    available_states,
    group_fps,
    resolve_animation,
    validate_manifest,
)
from ark_deskpet.runtime import PhysicsBody, PetInstanceState, repel_bodies


def test_flat_manifest_is_read_without_migration(make_pet, tmp_path):
    pet = make_pet(tmp_path)
    raw = json.loads((pet / "manifest.json").read_text())
    before = (pet / "manifest.json").read_bytes()
    assert set(animation_groups(raw)) == {"default"}
    assert resolve_animation(raw, "idle").frame_state == "idle"
    validate_manifest(pet)
    assert (pet / "manifest.json").read_bytes() == before


def test_grouped_manifest_falls_back_without_inventing_path(make_pet, tmp_path):
    pet = make_pet(tmp_path)
    raw = json.loads((pet / "manifest.json").read_text())
    states = raw.pop("states")
    raw["groups"] = {"combat": {"fps": 30, "idle": states["idle"], "interact": states["interact"]}}
    (pet / "manifest.json").write_text(json.dumps(raw))
    # Move only the declared grouped frames; fallback must resolve to idle.
    group_dir = pet / "frames" / "combat"
    group_dir.mkdir()
    for state in ("idle", "interact"):
        (group_dir / state).mkdir()
        (group_dir / state / "frame_0000.png").write_bytes(
            (pet / "frames" / state / "frame_0000.png").read_bytes()
        )
    validate_manifest(pet)
    ref = resolve_animation(raw, "sleep", "combat")
    assert ref is not None and ref.frame_state == "idle"
    assert group_fps(raw, "combat") == 30
    assert available_states(raw, "combat") == ("idle", "interact")


def test_instances_and_physics_are_independent_and_bounded():
    first = PetInstanceState.from_dict({"scale": float("nan")}, instance_id="pet-1", pet="a")
    second = PetInstanceState.from_dict({"pos_x": 10}, instance_id="pet-2", pet="b")
    assert first.scale == 1.0 and second.pos_x == 10
    bodies = [PhysicsBody(10, 80, 40, 40), PhysicsBody(45, 80, 40, 40)]
    repel_bodies(bodies, minimum_gap=8, bounds=Rect(0, 0, 120, 120))
    assert bodies[0].x + bodies[0].width + 8 <= bodies[1].x
    bodies[0].step(5, Rect(0, 0, 120, 120), gravity=900, walk_speed=100)
    assert 0 <= bodies[0].x <= 80 and 0 <= bodies[0].y <= 80
