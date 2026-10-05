"""User controls drive actual behavior, persistence and cycle-safe stopping."""
import random
from pathlib import Path
import pytest
from PySide6.QtWidgets import QWidget
from ark_deskpet.app import SettingsDialog, PetWindow
import ark_deskpet.app as module
from ark_deskpet.animation_policy import AnimationPolicy
from ark_deskpet.constants import BEHAVIOR_RANGES
from ark_deskpet.storage import migrate_settings, save_settings, load_settings
from ark_deskpet.runtime import WanderMotion, PhysicsBody
from ark_deskpet.display import Rect
from test_animation_policy import FakeClock
from test_native_window_bridge import StubController


def test_controls_round_trip_and_constrain_pause_range(tmp_path, qtbot, monkeypatch):
    monkeypatch.setattr(module, 'launch_agent_enabled', lambda: False)
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = SettingsDialog(migrate_settings({}), parent)
    qtbot.addWidget(dialog)
    dialog.motion.setChecked(True)
    values = {'activity_frequency': 175, 'walking_frequency': 35, 'walking_speed': 40,
              'walking_distance': 220, 'pause_min': 10, 'pause_max': 40}
    for key, value in values.items():
        dialog.behavior_controls[key].setValue(value)
    path = tmp_path / 'settings.json'
    save_settings(path, dialog.values())
    restored = load_settings(path)
    assert all(restored[k] == v for k, v in values.items())
    dialog.behavior_controls['pause_min'].setValue(60)
    assert dialog.values()['pause_max'] == 60
    dialog.behavior_controls['pause_max'].setValue(20)
    assert dialog.values()['pause_min'] == 20
    dialog.motion.setChecked(False)
    assert not dialog.behavior_controls['walking_speed'].isEnabled()
    assert dialog.behavior_controls['activity_frequency'].isEnabled()


def test_existing_settings_receive_defaults_and_invalid_values_are_bounded():
    settings = migrate_settings({'walking_speed': 'oops', 'pause_min': 90,
                                 'pause_max': 2, 'walking_frequency': 999,
                                 'walking_distance': float('nan')})
    assert settings['walking_speed'] == 24
    assert settings['walking_frequency'] == 100
    assert settings['walking_distance'] == 160
    assert settings['pause_max'] == 90
    assert settings['activity_frequency'] == 100


def choices(frequency=100, walking=60):
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=random.Random(50))
    policy.activity_frequency = frequency
    policy.walking_frequency = walking
    policy.set_motion_enabled(True)
    result = []
    for _ in range(200):
        clock.value = policy.deadline + .01
        result.append(policy.on_animation_cycle_boundary().state)
        if policy.state == 'move':
            policy.finish_walk()
        for _ in range(3):
            if policy.state == 'idle':
                break
            policy.on_animation_cycle_boundary()
        assert policy.state == 'idle'
    return result


def test_activity_frequency_changes_action_rate():
    quiet, busy = choices(25), choices(200)
    assert quiet.count('idle') > busy.count('idle') + 80


def test_walking_frequency_zero_and_full_have_expected_meaning():
    assert 'move' not in choices(walking=0)
    assert set(choices(walking=100)) == {'idle', 'move'}


def test_speed_and_distance_control_real_walks():
    motion = WanderMotion(random.Random(4))
    motion.base_speed = 40
    motion.max_distance = 60
    body = PhysicsBody(300, 100, 80, 80)
    assert motion.begin(body, Rect(0, 0, 1000, 800))
    assert abs(motion.target - body.x) <= 60
    assert 32 <= abs(motion.speed) <= 48
    start = body.x
    motion.step(body, Rect(0, 0, 1000, 800), .1)
    assert abs(body.x - start) == pytest.approx(abs(motion.speed) * .1)


def test_arrival_finishes_animation_cycle_without_restarting_walk(make_pet, tmp_path, qtbot, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(module.time, 'monotonic', clock)
    monkeypatch.setattr(module, 'settings_path', lambda: tmp_path / 'settings.json')
    monkeypatch.setattr(module, 'get_codex_status', lambda: {'state': 'idle'})
    controller = StubController(make_pet(tmp_path))
    controller.settings.update(motion_enabled=True, walking_speed=40, walking_distance=50)
    window = PetWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.move(300, 100)
    policy = window.animation_policy
    window._apply_policy_transition(policy._transition('move', True))
    monkeypatch.setattr(window, '_screens', lambda: [Rect(0, 0, 1000, 800)])
    for _ in range(100):
        clock.advance(.1)
        window.update_physics()
        if policy.walk_finished:
            break
    assert policy.walk_finished
    assert window.state == 'move'
    position = window.pos()
    for _ in range(10):
        clock.advance(.1)
        window.update_physics()
    assert window.pos() == position
    window.next_frame()
    assert window.state == 'idle'
    assert policy.deadline > clock.value


def test_rest_actions_repeat_complete_cycles():
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=random.Random(19), available_states=('idle', 'sit'))
    policy.activity_frequency = 200
    policy.set_motion_enabled(True)
    lengths = []
    for _ in range(50):
        clock.value = policy.deadline + .01
        policy.on_animation_cycle_boundary()
        cycles = 0
        while policy.state == 'sit':
            assert policy.hold
            cycles += 1
            policy.on_animation_cycle_boundary()
        if cycles:
            lengths.append(cycles)
    assert set(lengths) == {1, 2, 3}
