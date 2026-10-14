"""Native checks run separately using Qt's Windows backend on Windows CI."""
import sys
import subprocess
import uuid
from pathlib import Path
import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows native APIs')


def test_click_through_preserves_other_window_styles(qtbot):
    from PySide6.QtWidgets import QWidget
    from PySide6.QtCore import Qt
    from ark_deskpet.windows_platform import _user32, set_click_through, is_fullscreen
    window = QWidget()
    window.setAttribute(Qt.WA_TranslucentBackground)
    window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    qtbot.addWidget(window);window.show()
    hwnd = int(window.winId())
    api = _user32()
    original = api.GetWindowLongPtrW(hwnd, -20)
    set_click_through(hwnd, True)
    assert api.GetWindowLongPtrW(hwnd, -20) & 0x20
    set_click_through(hwnd, False)
    restored = api.GetWindowLongPtrW(hwnd, -20)
    assert not restored & 0x20
    assert restored & original == original & ~0x20
    assert is_fullscreen(hwnd) in (True, False, None)


def test_pid_probe_keeps_process_alive():
    from ark_deskpet.storage import pid_is_alive
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        assert pid_is_alive(child.pid)
        assert child.poll() is None
    finally:
        child.terminate();child.wait(timeout=10)
    assert not pid_is_alive(child.pid)


def test_startup_registry_round_trip(monkeypatch):
    from ark_deskpet import windows_platform as platform
    monkeypatch.setattr(platform, 'RUN_NAME', 'ArkDeskpetTest-' + uuid.uuid4().hex)
    monkeypatch.setattr(platform.subprocess, 'Popen', lambda *args, **kwargs: None)
    try:
        assert not platform.startup_enabled()
        platform.set_startup(Path(sys.executable))
        assert platform.startup_enabled()
        platform.set_startup(None)
        assert not platform.startup_enabled()
    finally:
        platform.set_startup(None)
