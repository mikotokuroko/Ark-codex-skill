import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
import ark_deskpet.app as module

def test_macos_tray_click_keeps_open_menu_and_quit_action(monkeypatch):
    app = QApplication.instance() or QApplication([])
    controller = module.DeskpetController.__new__(module.DeskpetController)
    controller.settings = {}
    controller.windows = {}
    controller.tray = QSystemTrayIcon()
    controller.save_all_states = Mock()
    controller.app = Mock()
    def rebuild():
        menu = QMenu()
        menu.addAction('Quit', controller.quit)
        controller.tray.setContextMenu(menu)
    controller._build_tray_menu = rebuild
    monkeypatch.setattr(module.sys, 'platform', 'darwin')
    monkeypatch.setattr(module, 'save_settings', Mock())
    monkeypatch.setattr(module, 'settings_path', Mock())
    rebuild()
    original = controller.tray.contextMenu()
    controller._tray_activated(QSystemTrayIcon.Trigger)
    assert controller.tray.contextMenu() is original
    original.actions()[0].trigger()
    controller.app.quit.assert_called_once()
    controller.save_all_states.assert_called_once()

def test_non_macos_tray_click_still_shows_pet(monkeypatch):
    controller = module.DeskpetController.__new__(module.DeskpetController)
    controller.show_pet = Mock()
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    controller._tray_activated(QSystemTrayIcon.Trigger)
    controller.show_pet.assert_called_once()
