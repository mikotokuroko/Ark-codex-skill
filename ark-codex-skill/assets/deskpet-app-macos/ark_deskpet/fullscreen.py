"""Privacy-preserving fullscreen detection through AppKit and Quartz."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from .display import Rect, intersection_area

WindowProvider = Callable[[], tuple[int | None, list[dict[str, Any]] | None]]


def window_covers_display(window: Rect, display: Rect, tolerance: int = 2) -> bool:
    """Returns whether a normal window covers a complete display."""
    return (
        window.x <= display.x + tolerance
        and window.y <= display.y + tolerance
        and window.right >= display.right - tolerance
        and window.bottom >= display.bottom - tolerance
    )


def evaluate_fullscreen(
    frontmost_pid: int | None,
    windows: list[dict[str, Any]] | None,
    pet_rect: Rect,
    displays: list[Rect],
    own_pid: int | None = None,
) -> bool | None:
    """Evaluates visible Core Graphics metadata for fullscreen coverage."""
    if frontmost_pid is None or windows is None or not displays:
        return None
    if own_pid is not None and frontmost_pid == own_pid:
        return False
    display = max(displays, key=lambda item: intersection_area(pet_rect, item))
    candidates = []
    for item in windows:
        if item.get("owner_pid") != frontmost_pid or item.get("layer") != 0:
            continue
        bounds = item.get("bounds")
        if not isinstance(bounds, Rect):
            continue
        if intersection_area(bounds, display) > 0:
            candidates.append(bounds)
    if not candidates:
        return None
    return any(window_covers_display(window, display) for window in candidates)


def macos_window_metadata() -> tuple[int | None, list[dict[str, Any]] | None]:
    """Returns frontmost PID and normal-window metadata without privacy prompts."""
    try:
        import AppKit
        import Quartz
    except ImportError:
        return None, None
    frontmost = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    if frontmost is None:
        return None, None
    frontmost_pid = int(frontmost.processIdentifier())
    options = (
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements
    )
    raw_windows = Quartz.CGWindowListCopyWindowInfo(
        options, Quartz.kCGNullWindowID
    )
    if raw_windows is None:
        return frontmost_pid, None
    windows = []
    for item in raw_windows:
        bounds = item.get(Quartz.kCGWindowBounds)
        if not isinstance(bounds, dict):
            continue
        try:
            rect = Rect(
                int(round(bounds["X"])),
                int(round(bounds["Y"])),
                int(round(bounds["Width"])),
                int(round(bounds["Height"])),
            )
            windows.append(
                {
                    "owner_pid": int(item.get(Quartz.kCGWindowOwnerPID, -1)),
                    "layer": int(item.get(Quartz.kCGWindowLayer, -1)),
                    "bounds": rect,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return frontmost_pid, windows


class FullscreenDetector:
    """Detects fullscreen windows and logs unavailable metadata once."""

    def __init__(
        self,
        provider: WindowProvider = macos_window_metadata,
        logger: logging.Logger | None = None,
    ) -> None:
        self._provider = provider
        self._logger = logger or logging.getLogger(__name__)
        self._logged_unavailable = False

    def detect(self, pet_rect: Rect, displays: list[Rect]) -> bool | None:
        """Returns True, False, or None when metadata is unavailable."""
        frontmost_pid, windows = self._provider()
        result = evaluate_fullscreen(
            frontmost_pid, windows, pet_rect, displays, own_pid=os.getpid()
        )
        if result is None and not self._logged_unavailable:
            self._logger.warning(
                "macOS 未提供足够的前台窗口元数据；保持桌宠可见。"
            )
            self._logged_unavailable = True
        return result
