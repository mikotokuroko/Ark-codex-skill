"""Pure geometry helpers for multi-display recovery."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """A global display or window rectangle."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        """Returns the exclusive right edge."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Returns the exclusive bottom edge."""
        return self.y + self.height


def intersection_area(first: Rect, second: Rect) -> int:
    """Returns the overlapping area of two rectangles."""
    width = max(0, min(first.right, second.right) - max(first.x, second.x))
    height = max(0, min(first.bottom, second.bottom) - max(first.y, second.y))
    return width * height


def recover_position(
    position: tuple[int, int] | None,
    window_size: tuple[int, int],
    screens: list[Rect],
    visible_margin: int = 60,
) -> tuple[int, int]:
    """Keeps a saved pet position visible on one of the current displays."""
    if not screens:
        return (0, 0)
    width, height = window_size
    primary = screens[0]
    if position is None:
        return (
            primary.x + (primary.width - width) // 2,
            primary.bottom - height,
        )
    x, y = position
    pet = Rect(x, y, width, height)
    if any(intersection_area(pet, screen) > 0 for screen in screens):
        target = max(screens, key=lambda screen: intersection_area(pet, screen))
    else:
        target = primary
    minimum_x = target.x - width + visible_margin
    maximum_x = target.right - visible_margin
    minimum_y = target.y - height + visible_margin
    maximum_y = target.bottom - visible_margin
    return (
        max(minimum_x, min(x, maximum_x)),
        max(minimum_y, min(y, maximum_y)),
    )
