from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from ark_deskpet.effects import DEFAULT_DIALOGUE, DialogueProvider, SoundEffects, SpeechBubbleController


@pytest.fixture(scope="session")
def effects_app():
    app = QApplication.instance() or QApplication([])
    return app


def test_dialogue_defaults_and_doctor_substitution(tmp_path: Path):
    provider = DialogueProvider(tmp_path)
    lines = provider.lines("Amiya")
    assert lines == list(DEFAULT_DIALOGUE)
    provider.fetcher = lambda name: ["{{DrName}}，您好", "  你好  "]
    assert provider.lines("Amiya", doctor_name="凯尔希", live=True)[0] == "凯尔希，您好"
    cache_file = next((tmp_path / "dialogue").glob("Amiya-*.json"))
    cached = json.loads(cache_file.read_text())
    assert cached == ["{{DrName}}，您好", "你好"]


def test_dialogue_network_failure_uses_cache_or_defaults(tmp_path: Path):
    provider = DialogueProvider(tmp_path, fetcher=lambda name: (_ for _ in ()).throw(OSError("offline")))
    assert provider.lines("Offline") == list(DEFAULT_DIALOGUE)
    cache = provider._cache_path("Offline")
    cache.parent.mkdir()
    cache.write_text(json.dumps(["缓存对白"]))
    assert provider.lines("Offline", live=True) == ["缓存对白"]


def test_cache_validation_and_literal_doctor_placeholder(tmp_path: Path):
    provider = DialogueProvider(tmp_path, fetcher=lambda name: ["{博士}，请注意", 42])
    assert provider.lines("Saria", doctor_name="Doctor", live=True) == ["Doctor，请注意"]
    provider._cache_path("Saria").write_text(json.dumps({"lines": ["错误"]}))
    assert provider.lines("Saria", doctor_name="Doctor") == list(DEFAULT_DIALOGUE)


def test_pet_local_dialogue_and_async_refresh(tmp_path: Path, effects_app):
    pet = tmp_path / "pet"
    pet.mkdir()
    (pet / "dialogue.json").write_text(json.dumps(["{{DrName}}，本地对白"]))
    provider = DialogueProvider(tmp_path, fetcher=lambda name: ["{{DrName}}，网络对白"])
    assert provider.lines("Amiya", doctor_name="博士", pet_dir=pet) == ["博士，本地对白"]
    received = []
    worker = provider.refresh_async("Amiya", doctor_name="凯尔希", callback=lambda lines: received.append(lines))
    assert worker.wait(2000)
    effects_app.processEvents()
    assert received == [["凯尔希，网络对白"]]
    provider.close()


def test_skin_dialogue_falls_back_to_base_operator(tmp_path: Path):
    provider = DialogueProvider(tmp_path, fetcher=lambda name: ["{{DrName}} base"] if name == "Amiya" else [])
    assert provider.lines("Amiya-skin-01", doctor_name="博士", live=True) == ["博士 base"]


def test_bubble_follows_anchor_hides_and_cleans_up(effects_app):
    anchor = QWidget()
    anchor.resize(120, 80)
    anchor.show()
    controller = SpeechBubbleController(anchor, enabled=True)
    assert controller.show("a long line that should remain readable", duration_ms=1000)
    first = controller.bubble.pos()
    anchor.move(anchor.x() + 20, anchor.y() + 10)
    effects_app.processEvents()
    assert controller.bubble.pos() != first
    controller.hide()
    assert not controller.bubble.isVisible()
    controller.show("temporary", duration_ms=250)
    QTest.qWait(300)
    assert not controller.bubble.isVisible()
    anchor.hide()
    effects_app.processEvents()
    assert not controller.bubble.isVisible()
    controller.close()
    anchor.close()


def test_sound_disabled_does_not_create_or_play(tmp_path: Path):
    effects = SoundEffects(tmp_path, enabled=False)
    assert effects.play("click") is False
    assert not (tmp_path / "sounds").exists()
    effects.close()


def test_sound_fallback_is_cache_local_and_cleanup_is_safe(tmp_path: Path):
    effects = SoundEffects(tmp_path, enabled=True)
    path = effects._fallback("drop")
    assert path == tmp_path / "sounds" / "drop.wav"
    assert path.read_bytes()[:4] == b"RIFF"
    effects.close()
    assert effects._players == {}
