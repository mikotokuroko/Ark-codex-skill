"""Per-copy visibility and removal persist independently of global hiding."""
from ark_deskpet.app import DeskpetController, PetWindow
import ark_deskpet.app as module
from ark_deskpet.storage import load_settings
from test_native_window_bridge import StubController


def controller_with_copies(make_pet, tmp_path, qtbot, monkeypatch):
    pet = make_pet(tmp_path)
    monkeypatch.setattr(module, 'settings_path', lambda: tmp_path / 'settings.json')
    controller = DeskpetController.__new__(DeskpetController)
    controller.__dict__.update(StubController(pet).__dict__)
    controller.windows = {}
    controller._build_tray_menu = lambda: None
    controller.window = PetWindow(controller)
    qtbot.addWidget(controller.window)
    controller.windows['primary'] = controller.window
    extra = controller.add_pet_instance(pet.name)
    qtbot.addWidget(extra)
    controller.window.show()
    return controller, extra


def test_hide_one_survives_fullscreen_and_restart(make_pet, tmp_path, qtbot, monkeypatch):
    controller, extra = controller_with_copies(make_pet, tmp_path, qtbot, monkeypatch)
    controller.set_instance_hidden(extra, True)
    assert controller.window.isVisible()
    assert not extra.isVisible()
    extra.fullscreen_hidden = True
    extra.check_fullscreen()
    assert not extra.isVisible()
    controller.save_all_states()
    controller.settings = load_settings(tmp_path / 'settings.json')
    restored = PetWindow(controller, extra.instance_key)
    qtbot.addWidget(restored)
    assert restored.user_hidden
    controller.set_instance_hidden(extra, False)
    assert extra.isVisible()
    assert not extra.user_hidden


def test_show_one_after_hide_all_leaves_others_hidden(make_pet, tmp_path, qtbot, monkeypatch):
    controller, extra = controller_with_copies(make_pet, tmp_path, qtbot, monkeypatch)
    controller.hide_pet()
    controller.set_instance_hidden(extra, False)
    assert extra.isVisible()
    assert not controller.window.isVisible()
    assert controller.window.user_hidden
    controller.window.check_fullscreen()
    assert not controller.window.isVisible()


def test_remove_extra_does_not_restore_on_restart(make_pet, tmp_path, qtbot, monkeypatch):
    controller, extra = controller_with_copies(make_pet, tmp_path, qtbot, monkeypatch)
    key = extra.instance_key
    controller.remove_pet_instance(extra)
    controller.save_all_states()
    assert key not in controller.windows
    assert key not in load_settings(tmp_path / 'settings.json')['instance_states']
    assert controller.window.isVisible()


def test_remove_primary_preserves_remaining_copy(make_pet, tmp_path, qtbot, monkeypatch):
    controller, extra = controller_with_copies(make_pet, tmp_path, qtbot, monkeypatch)
    extra.move(120, 180)
    controller.set_instance_hidden(extra, True)
    controller.remove_pet_instance(controller.window)
    assert controller.window is extra
    assert extra.instance_key == 'primary'
    assert extra.user_hidden
    saved = load_settings(tmp_path / 'settings.json')
    assert list(saved['instance_states']) == ['primary']
    assert saved['pet_states'][extra.pet.name]['pos_x'] == 120
