from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
import ark_deskpet.app as module
from ark_deskpet.app import PetWindow, DeskpetController
from test_native_window_bridge import StubController


def test_animation_loop_reuses_decoded_frames(make_pet, tmp_path, qtbot, monkeypatch):
    pet = make_pet(tmp_path)
    monkeypatch.setattr(module, 'settings_path', lambda: tmp_path / 'settings.json')
    window = PetWindow(StubController(pet))
    qtbot.addWidget(window)
    original = module.QImage
    loads = []
    def image(path):
        loads.append(path)
        return original(32, 32, QImage.Format_ARGB32)
    monkeypatch.setattr(module, 'QImage', image)
    for _ in range(2):
        for frame in range(12):
            window.frame_index = frame
            window.current_image()
    assert len(loads) == 12


def test_show_pet_recovers_mouse_control(make_pet, tmp_path, qtbot, monkeypatch):
    pet = make_pet(tmp_path)
    monkeypatch.setattr(module, 'settings_path', lambda: tmp_path / 'settings.json')
    controller = StubController(pet)
    window = PetWindow(controller)
    qtbot.addWidget(window)
    controller.windows = {'primary': window}
    window.toggle_click_through()
    assert window.click_through
    DeskpetController.show_pet(controller)
    assert not window.click_through
    assert not window.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert not controller.settings['pet_states'][pet.name]['click_through']


def test_cached_frame_preserves_crop_and_budget(make_pet, tmp_path, qtbot, monkeypatch):
    pet = make_pet(tmp_path)
    monkeypatch.setattr(module, 'settings_path', lambda: tmp_path / 'settings.json')
    window = PetWindow(StubController(pet))
    qtbot.addWidget(window)
    source = QImage(32, 32, QImage.Format_ARGB32)
    source.fill(Qt.red)
    source.setPixelColor(4, 6, Qt.blue)
    source.save(str(pet / 'frames/idle/frame_0000.png'))
    window.manifest['states']['idle']['bbox'] = [4, 6, 15, 20]
    cropped = window.current_image()
    assert (cropped.width(), cropped.height()) == (12, 15)
    assert cropped.pixelColor(0, 0) == Qt.blue
    monkeypatch.setattr(module, 'FRAME_CACHE_BYTES', cropped.sizeInBytes())
    for frame in range(1, 4):
        source.save(str(pet / f'frames/idle/frame_{frame:04d}.png'))
        window.frame_index = frame
        window.current_image()
        assert sum(image.sizeInBytes() for image in window.cache.values()) <= module.FRAME_CACHE_BYTES
