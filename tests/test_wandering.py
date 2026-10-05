"""Movement must follow the walking animation, never leak into resting poses."""
import random
import pytest
from ark_deskpet.app import PetWindow
import ark_deskpet.app as app_module
from ark_deskpet.display import Rect
from ark_deskpet.runtime import PhysicsBody
from test_native_window_bridge import StubController
from ark_deskpet.animation_policy import AnimationPolicy
from ark_deskpet.runtime import WanderMotion
from test_animation_policy import FakeClock


@pytest.mark.parametrize('state', ['idle', 'sit', 'sleep', 'interact'])
def test_resting_pet_never_drifts(make_pet, tmp_path, qtbot, monkeypatch, state):
    monkeypatch.setattr(app_module, 'settings_path', lambda: tmp_path / 'settings.json')
    monkeypatch.setattr(app_module, 'get_codex_status', lambda: {'state': 'idle'})
    controller = StubController(make_pet(tmp_path))
    controller.settings['motion_enabled'] = True
    window = PetWindow(controller)
    qtbot.addWidget(window)
    window.show()
    window.set_state(state, True)
    window.move(100, 100)
    window._physics_body = PhysicsBody(100, 100, window.width(), window.height(), vx=18, vy=20)
    monkeypatch.setattr(window, '_screens', lambda: [Rect(0, 0, 1000, 800)])
    monkeypatch.setattr(app_module.time, 'monotonic', lambda: 10.0)
    window._physics_clock = 9.9
    window.update_physics()
    assert (window.x(), window.y()) == (100, 100)


def test_boundary_stops_instead_of_bouncing():
    body = PhysicsBody(79, 50, 20, 20)
    body.step(.1, Rect(0, 0, 100, 100), walk_speed=30)
    assert body.x == 80
    assert body.vx == 0


def test_wandering_varies_choices_and_pauses_even_when_codex_is_running():
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=random.Random(41))
    policy.enable()
    policy.set_mode('running')
    policy.set_motion_enabled(True)
    actions, pauses = [], []
    for _ in range(40):
        assert policy.state == 'idle'
        pauses.append(policy.deadline - clock.value)
        clock.value = policy.deadline + .01
        action = policy.on_animation_cycle_boundary()
        actions.append(action.state)
        assert action.state in ('idle', 'move', 'sit', 'interact')
        # Status polling must not override the chosen walk or resting action.
        assert policy.set_mode('running') is None
        if action.state == 'move':
            clock.value = policy.deadline + .01
        for _ in range(3):
            if policy.state == 'idle':
                break
            policy.on_animation_cycle_boundary()
        assert policy.state == 'idle'
    assert {'move', 'sit', 'interact'} <= set(actions)
    assert len(set(round(p, 2) for p in pauses)) > 20
    assert all(8 <= p <= 25 for p in pauses)


def test_motion_alone_works_and_respects_manual_overrides():
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=random.Random(7))
    policy.set_motion_enabled(True)
    assert not policy.enabled
    policy.start_override('sit')
    assert policy.finish_walk() is None
    assert policy.state == 'sit'
    assert policy.on_animation_cycle_boundary().state == 'idle'
    policy.start_drag()
    clock.advance(100)
    assert policy.on_animation_cycle_boundary() is None
    assert policy.release_drag().state == 'idle'
    assert policy.deadline > clock.value
    policy.set_motion_enabled(False)
    assert policy.state == 'idle'
    assert policy.on_animation_cycle_boundary() is None


def test_group_without_walking_frames_never_selects_walk():
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=random.Random(7), available_states=('idle', 'sit'))
    policy.set_motion_enabled(True)
    for _ in range(30):
        clock.value = policy.deadline + .01
        assert policy.on_animation_cycle_boundary().state in ('sit', 'idle')
        for _ in range(3):
            if policy.state == 'idle':
                break
            policy.on_animation_cycle_boundary()
        assert policy.state == 'idle'


def test_destinations_vary_without_forced_left_right_alternation():
    motion = WanderMotion(random.Random(3))
    bounds = Rect(-500, -200, 1500, 1000)
    directions, distances, speeds = [], [], []
    for _ in range(20):
        body = PhysicsBody(200, 100, 80, 80)
        assert motion.begin(body, bounds)
        directions.append(motion.speed > 0)
        distances.append(abs(motion.target - body.x))
        speeds.append(abs(motion.speed))
        target = motion.target
        for tick in range(300):
            if motion.step(body, bounds, .05):
                break
        assert body.x == pytest.approx(target)
        assert body.y == 100
        assert body.vx == body.vy == 0
        assert tick < 299
    assert set(directions) == {True, False}
    assert any(a == b for a, b in zip(directions, directions[1:]))
    assert len(set(round(d, 2) for d in distances)) > 15
    assert len(set(round(s, 2) for s in speeds)) > 15


@pytest.mark.parametrize('x', [0, 80])
def test_walk_from_edge_goes_inward_then_stops(x):
    motion = WanderMotion(random.Random(2))
    body = PhysicsBody(x, 10, 20, 20)
    bounds = Rect(0, 0, 100, 100)
    assert motion.begin(body, bounds)
    assert (motion.speed > 0) == (x == 0)
    for _ in range(100):
        if motion.step(body, bounds, .1):
            break
        assert 0 <= body.x <= 80
    assert motion.target is None
    assert body.vx == 0


def test_real_window_moves_only_while_walk_animation_owns_playback(make_pet, tmp_path, qtbot, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(app_module, 'settings_path', lambda: tmp_path / 'settings.json')
    monkeypatch.setattr(app_module, 'get_codex_status', lambda: {'state': 'running'})
    monkeypatch.setattr(app_module.time, 'monotonic', clock)
    controller = StubController(make_pet(tmp_path))
    controller.settings.update(motion_enabled=True, auto_animations=True)
    window = PetWindow(controller)
    qtbot.addWidget(window)
    window.animation_policy._rng = random.Random(12)
    window._wander = WanderMotion(random.Random(3))
    window.move(400, 100)
    window.show()
    monkeypatch.setattr(window, '_screens', lambda: [Rect(0, 0, 1000, 800)])
    transitions = []
    moving_ticks = stationary_ticks = 0
    for tick in range(6000):
        clock.advance(.05)
        old_state = window.state
        window.next_frame()
        before = (window.x(), window.y())
        state_during_step = window.state
        window.update_physics()
        after = (window.x(), window.y())
        if before != after:
            # All fixture poses share geometry, so any change is motion.
            assert state_during_step == 'move'
            assert before[1] == after[1]
            moving_ticks += 1
        else:
            stationary_ticks += 1
        if window.state != old_state:
            transitions.append(window.state)
        if tick % 40 == 0:
            window.refresh_status()
    assert moving_ticks > 100
    assert stationary_ticks > moving_ticks
    assert {'idle', 'move', 'sit', 'interact'} <= set(transitions)
    window.play_one_shot('sit')
    before = window.pos()
    clock.advance(.1)
    window.update_physics()
    assert window.pos() == before
    controller.settings['motion_enabled'] = False
    window.apply_motion(False)
    for _ in range(20):
        clock.advance(.1)
        window.update_physics()
    assert window.pos() == before


def test_idle_sleep_and_wake_remain_compatible_with_motion():
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=random.Random(4))
    policy.enable()
    policy.set_motion_enabled(True)
    clock.advance(301)
    assert policy.on_animation_cycle_boundary().state == 'sleep'
    assert policy.set_mode('running').state == 'idle'
    clock.advance(400)
    policy.set_mode('idle')
    assert policy.last_activity == clock.value
    assert policy.on_animation_cycle_boundary().state != 'sleep'


def test_walk_preserves_height_even_if_pet_overlaps_screen_edge():
    motion = WanderMotion(random.Random(4))
    body = PhysicsBody(50, 90, 20, 30)
    bounds = Rect(0, 0, 200, 100)
    assert motion.begin(body, bounds)
    motion.step(body, bounds, .1)
    assert body.y == 90
