"""Multi-display recovery and fullscreen fallback tests."""

from ark_deskpet.display import Rect, recover_position
from ark_deskpet.fullscreen import (
    FullscreenDetector,
    evaluate_fullscreen,
    window_covers_display,
)


def test_position_on_second_display_is_preserved() -> None:
    screens = [Rect(0, 0, 1920, 1080), Rect(1920, 0, 1920, 1080)]
    assert recover_position((2300, 700), (300, 300), screens) == (2300, 700)


def test_offscreen_position_recovers_to_primary() -> None:
    screens = [Rect(0, 0, 1920, 1080)]
    x, y = recover_position((8000, -5000), (300, 300), screens)
    assert -240 <= x <= 1860
    assert -240 <= y <= 1020


def test_new_pet_defaults_to_primary_bottom_center() -> None:
    assert recover_position(None, (300, 300), [Rect(0, 0, 1920, 1080)]) == (
        810,
        780,
    )


def test_fullscreen_window_must_cover_relevant_display() -> None:
    display = Rect(0, 0, 1920, 1080)
    assert window_covers_display(Rect(0, 0, 1920, 1080), display)
    assert not window_covers_display(Rect(100, 100, 1200, 800), display)


def test_fullscreen_filters_pid_and_layer() -> None:
    display = Rect(0, 0, 1920, 1080)
    pet = Rect(900, 700, 200, 300)
    windows = [
        {"owner_pid": 11, "layer": 1, "bounds": display},
        {"owner_pid": 12, "layer": 0, "bounds": display},
        {"owner_pid": 11, "layer": 0, "bounds": Rect(0, 0, 1920, 1080)},
    ]
    assert evaluate_fullscreen(11, windows, pet, [display], own_pid=99)


def test_unavailable_metadata_fallback_logs_once(caplog) -> None:
    detector = FullscreenDetector(provider=lambda: (None, None))
    pet = Rect(0, 0, 100, 100)
    assert detector.detect(pet, [Rect(0, 0, 1920, 1080)]) is None
    assert detector.detect(pet, [Rect(0, 0, 1920, 1080)]) is None
    assert caplog.text.count("保持桌宠可见") == 1
