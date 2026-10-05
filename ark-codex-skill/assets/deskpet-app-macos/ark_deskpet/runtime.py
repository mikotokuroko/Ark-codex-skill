"""Pure runtime helpers for independent desk-pet instances."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Iterable

from .display import Rect


@dataclass
class PetInstanceState:
    """Persistable presentation and motion state for one pet copy."""

    instance_id: str
    pet: str
    group: str = "default"
    pos_x: int | None = None
    pos_y: int | None = None
    scale: float = 1.0
    opacity: float = 1.0
    flipped: bool = False
    click_through: bool = False
    motion_enabled: bool = False
    sounds_enabled: bool = False

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, value: object, *, instance_id: str, pet: str) -> "PetInstanceState":
        data = value if isinstance(value, dict) else {}
        def number(key: str, default: float, low: float, high: float) -> float:
            raw = data.get(key, default)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                return default
            if not math.isfinite(value):
                return default
            return max(low, min(high, value))
        return cls(
            instance_id=str(data.get("instance_id", instance_id)),
            pet=str(data.get("pet", pet)),
            group=str(data.get("group", "default")),
            pos_x=data.get("pos_x") if isinstance(data.get("pos_x"), int) else None,
            pos_y=data.get("pos_y") if isinstance(data.get("pos_y"), int) else None,
            scale=number("scale", 1.0, 0.3, 2.0),
            opacity=number("opacity", 1.0, 0.15, 1.0),
            flipped=bool(data.get("flipped", False)),
            click_through=bool(data.get("click_through", False)),
            motion_enabled=bool(data.get("motion_enabled", False)),
            sounds_enabled=bool(data.get("sounds_enabled", False)),
        )


@dataclass
class PhysicsBody:
    """A bounded desktop body with optional gravity and horizontal wandering."""

    x: float
    y: float
    width: float
    height: float
    vx: float = 0.0
    vy: float = 0.0
    grounded: bool = True

    def step(self, dt: float, bounds: Rect, *, gravity: float = 0.0,
             walk_speed: float = 0.0) -> None:
        dt = max(0.0, min(float(dt), 0.1))
        if dt == 0:
            return
        if walk_speed and abs(self.vx) < 1e-3:
            self.vx = walk_speed
        self.vy += gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        left, right = bounds.x, bounds.right - self.width
        floor = bounds.bottom - self.height
        ceiling = bounds.y
        if self.x <= left or self.x >= right:
            self.x = max(left, min(self.x, right))
            self.vx *= -1
        if self.y >= floor:
            self.y, self.vy, self.grounded = floor, 0.0, True
        elif self.y <= ceiling:
            self.y, self.vy = ceiling, 0.0
            self.grounded = False
        else:
            self.grounded = False


def repel_bodies(bodies: list[PhysicsBody], minimum_gap: float = 12.0,
                 bounds: Rect | None = None) -> None:
    """Separates overlapping bodies deterministically without changing y."""
    for index, first in enumerate(bodies):
        for second in bodies[index + 1:]:
            overlap = min(first.x + first.width, second.x + second.width) - max(first.x, second.x)
            vertical = min(first.y + first.height, second.y + second.height) - max(first.y, second.y)
            if overlap < -minimum_gap or vertical <= 0:
                continue
            center_first = first.x + first.width / 2
            center_second = second.x + second.width / 2
            direction = -1.0 if center_first <= center_second else 1.0
            shift = (max(0.0, overlap) + minimum_gap) / 2
            first.x += direction * shift
            second.x -= direction * shift
            first.vx = -abs(first.vx) if direction < 0 else abs(first.vx)
            second.vx = -first.vx
    if bounds is not None:
        for body in bodies:
            body.x = max(bounds.x, min(body.x, bounds.right - body.width))
            body.y = max(bounds.y, min(body.y, bounds.bottom - body.height))


def next_instance_id(states: Iterable[PetInstanceState]) -> str:
    used = {state.instance_id for state in states}
    index = 1
    while f"pet-{index}" in used:
        index += 1
    return f"pet-{index}"
