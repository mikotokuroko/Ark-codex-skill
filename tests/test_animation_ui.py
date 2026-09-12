"""Small offscreen Qt checks for the automatic-animation controls."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMenu

import ark_deskpet.app as app_module
from ark_deskpet.app import (
    AUTO_ANIMATION_LABELS,
    DeskpetController,
    PetWindow,
)
from ark_deskpet.fullscreen import FullscreenDetector
from ark_deskpet.manifest import PetEntry
from ark_deskpet.storage import migrate_settings


@pytest.fixture(scope="module")
def qapp():
    application = QApplication.instance() or QApplication(["pytest"])
    yield application
    application.processEvents()


class StubController:
    def __init__(self, pet: Path) -> None:
        self.settings = migrate_settings({"pet": pet.name})
        self.library = {pet.name: PetEntry(pet.name, pet, False)}
        self.active_pet_name = pet.name
        self.user_hidden = False
        self.fullscreen_hidden = False
        self.fullscreen_detector = FullscreenDetector()
        self.auto_calls: list[bool] = []
        self.window: PetWindow | None = None

    def set_auto_animations(self, enabled: bool) -> None:
        value = bool(enabled)
        self.settings["auto_animations"] = value
        self.auto_calls.append(value)
        assert self.window is not None
        self.window.apply_auto_animations(value)

    def select_pet(self, name: str) -> None:
        del name

    def open_settings(self) -> None:
        return None

    def hide_pet(self) -> None:
        return None

    def quit(self) -> None:
        return None


class StubTray:
    def __init__(self) -> None:
        self.menu: QMenu | None = None

    def setContextMenu(self, menu: QMenu) -> None:
        self.menu = menu


def make_window(
    make_pet, tmp_path: Path, qapp, monkeypatch
) -> tuple[StubController, PetWindow]:
    monkeypatch.setattr(
        app_module,
        "settings_path",
        lambda: tmp_path / "settings.json",
    )
    monkeypatch.setattr(app_module, "get_codex_status", lambda: {"state": "idle"})
    pet = make_pet(tmp_path)
    controller = StubController(pet)
    window = PetWindow(controller)
    controller.window = window
    return controller, window


def test_window_starts_relaxed_without_legacy_dwell_timers(
    make_pet, tmp_path: Path, qapp, monkeypatch
) -> None:
    controller, window = make_window(make_pet, tmp_path, qapp, monkeypatch)

    assert window.state == "idle"
    assert window.animation_policy.enabled is False
    assert window.animation_policy.deadline is None
    assert not hasattr(window, "sit_timer")
    assert not hasattr(window, "sleep_timer")
    window.deleteLater()
    qapp.processEvents()


def test_context_toggle_is_bilingual_and_checked_from_persisted_setting(
    make_pet, tmp_path: Path, qapp, monkeypatch
) -> None:
    controller, window = make_window(make_pet, tmp_path, qapp, monkeypatch)
    menu = window.build_context_menu()
    action = next(
        item
        for item in menu.actions()
        if item.text() == AUTO_ANIMATION_LABELS["en"]
    )
    assert action.isCheckable() is True
    assert action.isChecked() is False
    action.trigger()
    assert controller.auto_calls == [True]
    assert action.isChecked() is True

    controller.settings["language"] = "zh-Hans"
    menu = window.build_context_menu()
    zh_action = next(
        item
        for item in menu.actions()
        if item.text() == AUTO_ANIMATION_LABELS["zh-Hans"]
    )
    assert zh_action.isChecked() is True
    window.deleteLater()
    qapp.processEvents()


def test_one_shot_click_path_resets_activity_after_cycle(
    make_pet, tmp_path: Path, qapp, monkeypatch
) -> None:
    controller, window = make_window(make_pet, tmp_path, qapp, monkeypatch)
    controller.set_auto_animations(True)
    before = window.animation_policy.last_activity

    window.play_one_shot("interact")
    assert window.state == "interact"
    assert window.animation_policy.override_active is True
    window.next_frame()  # The fixture has one frame per state.

    assert window.state == "idle"
    assert window.animation_policy.override_active is False
    assert window.animation_policy.last_activity >= before
    window.deleteLater()
    qapp.processEvents()


def test_tray_toggle_rebuilds_with_synchronized_checked_state(
    make_pet, tmp_path: Path, qapp, monkeypatch
) -> None:
    controller, window = make_window(make_pet, tmp_path, qapp, monkeypatch)
    controller_instance = DeskpetController.__new__(DeskpetController)
    controller_instance.window = window
    controller_instance.library = controller.library
    controller_instance.settings = controller.settings
    controller_instance.tray = StubTray()

    controller_instance._build_tray_menu()
    assert controller_instance.tray.menu is not None
    action = next(
        item
        for item in controller_instance.tray.menu.actions()
        if item.text() == AUTO_ANIMATION_LABELS["en"]
    )
    assert action.isChecked() is False
    action.trigger()

    assert controller.settings["auto_animations"] is True
    assert controller_instance.tray.menu is not None
    refreshed = next(
        item
        for item in controller_instance.tray.menu.actions()
        if item.text() == AUTO_ANIMATION_LABELS["en"]
    )
    assert refreshed.isChecked() is True
    window.deleteLater()
    qapp.processEvents()


def test_status_mode_changes_follow_animation_boundaries(
    make_pet, tmp_path: Path, qapp, monkeypatch
) -> None:
    controller, window = make_window(make_pet, tmp_path, qapp, monkeypatch)
    controller.set_auto_animations(True)
    monkeypatch.setattr(app_module, "get_codex_status", lambda: {"state": "running"})

    window.refresh_status()
    assert window.state == "idle"
    window.next_frame()
    assert window.state == "move"

    monkeypatch.setattr(app_module, "get_codex_status", lambda: {"state": "idle"})
    window.refresh_status()
    assert window.state == "move"
    window.next_frame()
    assert window.state == "idle"
    window.deleteLater()
    qapp.processEvents()
