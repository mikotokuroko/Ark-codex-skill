import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget
import ark_deskpet.app as module
from ark_deskpet.app import PetWindow, SettingsDialog
from ark_deskpet.display import Rect
from ark_deskpet.storage import migrate_settings, save_settings, load_settings
from test_native_window_bridge import StubController
from test_animation_policy import FakeClock

@pytest.mark.parametrize('state', ['idle','sit','sleep','interact','move'])
def test_gravity_without_wandering_lands_then_stays_still(make_pet,tmp_path,qtbot,monkeypatch,state):
    clock=FakeClock()
    monkeypatch.setattr(module.time,'monotonic',clock)
    monkeypatch.setattr(module,'settings_path',lambda:tmp_path/'settings.json')
    monkeypatch.setattr(module,'get_codex_status',lambda:{'state':'idle'})
    controller=StubController(make_pet(tmp_path))
    controller.settings.update(gravity_enabled=True,motion_enabled=False)
    window=PetWindow(controller)
    qtbot.addWidget(window)
    window.show();window.set_state(state,True);window.move(100,100)
    monkeypatch.setattr(window,'_screens',lambda:[Rect(0,0,1000,800)])
    clock.advance(.05);window.update_physics()
    assert window.y()>100 and window.x()==100
    for _ in range(120):
        clock.advance(.05);window.update_physics()
    assert window.y()==800-window.height()
    landed=window.pos()
    for _ in range(20):
        clock.advance(.05);window.update_physics()
    assert window.pos()==landed
    window.move(100,100);window.press_global=QPoint(100,100)
    clock.advance(.1);window.update_physics()
    assert window.y()==100
    window.press_global=None
    clock.advance(.1);window.update_physics()
    assert window.y()>100
    controller.settings['gravity_enabled']=False
    frozen=window.pos()
    for _ in range(10):
        clock.advance(.1);window.update_physics()
    assert window.pos()==frozen


def test_gravity_switch_independent_and_saved(qtbot,tmp_path,monkeypatch):
    monkeypatch.setattr(module,'launch_agent_enabled',lambda:False)
    parent=QWidget();qtbot.addWidget(parent)
    dialog=SettingsDialog(migrate_settings({}),parent);qtbot.addWidget(dialog)
    dialog.motion.setChecked(False)
    assert dialog.gravity.isEnabled()
    dialog.gravity.setChecked(True)
    path=tmp_path/'settings.json'
    save_settings(path,dialog.values())
    assert load_settings(path)['gravity_enabled'] is True
    dialog.gravity.setChecked(False)
    save_settings(path,dialog.values())
    assert load_settings(path)['gravity_enabled'] is False


def test_gravity_and_wandering_work_together(make_pet, tmp_path, qtbot, monkeypatch):
    import random
    clock = FakeClock()
    monkeypatch.setattr(module.time, 'monotonic', clock)
    monkeypatch.setattr(module, 'settings_path', lambda: tmp_path / 'settings.json')
    monkeypatch.setattr(module, 'get_codex_status', lambda: {'state': 'running'})
    controller = StubController(make_pet(tmp_path))
    controller.settings.update(gravity_enabled=True, motion_enabled=True, auto_animations=True)
    window = PetWindow(controller)
    qtbot.addWidget(window)
    window.animation_policy._rng = random.Random(12)
    window.show()
    window.move(400, 100)
    monkeypatch.setattr(window, '_screens', lambda: [Rect(0, 0, 1000, 800)])
    falling = walking = 0
    for _ in range(4000):
        clock.advance(.05)
        window.next_frame()
        before = window.pos()
        window.update_physics()
        if window.y() != before.y():
            falling += 1
            assert window.x() == before.x()
        if window.x() != before.x():
            walking += 1
            assert window.state == 'move'
            assert window.y() == 800 - window.height()
    assert falling > 10
    assert walking > 100
