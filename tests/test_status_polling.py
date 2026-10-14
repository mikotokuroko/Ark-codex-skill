"""Session scans must not block the real controller's animation thread."""
import threading
from PySide6.QtCore import QTimer
import ark_deskpet.app as module


def test_controller_keeps_animating_during_shared_status_scan(make_pet, tmp_path, qtbot, monkeypatch):
    pet = make_pet(tmp_path)
    monkeypatch.setattr(module, 'bundled_pets_dir', lambda: tmp_path)
    monkeypatch.setattr(module, 'user_pets_dir', lambda: tmp_path / 'empty')
    monkeypatch.setattr(module, 'settings_path', lambda: tmp_path / 'settings.json')
    main_thread = threading.get_ident()
    release = threading.Event()
    entered = threading.Event()
    calls = []

    def slow_status():
        assert threading.get_ident() != main_thread, 'session scan blocks the UI thread'
        calls.append(1)
        entered.set()
        release.wait(2)
        return {'state': 'running'}

    monkeypatch.setattr(module, 'get_codex_status', slow_status)
    controller = None
    try:
        controller = module.DeskpetController(module.QApplication.instance(), 'manual')
        qtbot.addWidget(controller.window)
        qtbot.waitUntil(entered.is_set)
        ticks = []
        controller.window.animation_timer.timeout.connect(lambda: ticks.append(1))
        for _ in range(5):
            controller.status_monitor.poll()
        qtbot.waitUntil(lambda: len(ticks) >= 3)
        assert calls == [1]
        release.set()
        qtbot.waitUntil(lambda: controller.status_monitor.snapshot.get('state') == 'running')
        controller.window.refresh_status()
        assert controller.window.status_active
    finally:
        release.set()
        if controller is not None:
            controller.status_monitor.close()
            controller.tray.hide()
