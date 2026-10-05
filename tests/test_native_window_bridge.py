"""Safe offscreen regression for the Cocoa native-window bridge."""

from __future__ import annotations

import os
import sys
import inspect
import textwrap
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QWidget
import pytest

import ark_deskpet.app as app_module
from ark_deskpet.app import PetWindow
from ark_deskpet.fullscreen import FullscreenDetector
from ark_deskpet.manifest import PetEntry
from ark_deskpet.storage import migrate_settings


class StubController:
    def __init__(self, pet) -> None:
        self.settings = migrate_settings({"pet": pet.name})
        self.library = {pet.name: PetEntry(pet.name, pet, False)}
        self.active_pet_name = pet.name
        self.fullscreen_detector = FullscreenDetector()
        self.user_hidden = False
        self.fullscreen_hidden = False


def test_offscreen_pet_window_never_dereferences_cocoa_object(
    make_pet, tmp_path, qtbot, monkeypatch
) -> None:
    """The real init/show/toggle seam must stop before objc_object on offscreen."""
    pet = make_pet(tmp_path)
    controller = StubController(pet)
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    native_calls: list[str] = []

    def sentinel(*args, **kwargs):
        del args, kwargs
        native_calls.append("objc_object")
        raise AssertionError("[sentinel] unsafe native objc_object dereference")

    # Keep the real offscreen backend. The fake modules are only a safety net:
    # current guards must return before importing or calling either bridge.
    monkeypatch.setitem(sys.modules, "objc", SimpleNamespace(objc_object=sentinel))
    monkeypatch.setitem(
        sys.modules,
        "AppKit",
        SimpleNamespace(NSFloatingWindowLevel=3),
    )

    window = PetWindow(controller)
    qtbot.addWidget(window)
    assert native_calls == []
    window.toggle_click_through()
    assert native_calls == []

    window.showEvent(QShowEvent())
    assert native_calls == []


def test_preguard_show_event_mutation_goes_red_safely(
    make_pet, tmp_path, qtbot, monkeypatch
) -> None:
    """Removing only the platform guard reproduces the unsafe boundary safely."""
    pet = make_pet(tmp_path)
    controller = StubController(pet)
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    native_calls: list[str] = []

    def sentinel(*args, **kwargs):
        del args, kwargs
        native_calls.append("objc_object")
        raise AssertionError("[sentinel] unsafe native objc_object dereference")

    monkeypatch.setitem(sys.modules, "objc", SimpleNamespace(objc_object=sentinel))
    monkeypatch.setitem(
        sys.modules,
        "AppKit",
        SimpleNamespace(NSFloatingWindowLevel=3),
    )

    # Build an isolated, clearly labelled mutation artifact from the checked
    # in method: remove only the Cocoa platform guard, leaving the caller path.
    source = textwrap.dedent(inspect.getsource(PetWindow.showEvent))
    source = source.replace(
        '    if QApplication.platformName().lower() != "cocoa":\n        return\n',
        "",
        1,
    )
    source = source.replace("    super().showEvent(event)\n", "    QWidget.showEvent(self, event)\n", 1)
    mutation = tmp_path / "preguard_show_event.py"
    mutation.write_text(source, encoding="utf-8")
    namespace = {
        "QApplication": app_module.QApplication,
        "QWidget": QWidget,
        "c_void_p": app_module.c_void_p,
    }
    exec(compile(source, str(mutation), "exec"), namespace)
    monkeypatch.setattr(PetWindow, "showEvent", namespace["showEvent"])

    window = PetWindow(controller)
    qtbot.addWidget(window)
    with pytest.raises(AssertionError, match="unsafe native"):
        window.showEvent(QShowEvent())
    assert native_calls == ["objc_object"]
