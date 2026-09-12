"""Deterministic tests for the macOS automatic animation policy."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ark_deskpet.animation_policy import AnimationPolicy


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass
class FixedRandom:
    value: float = 0.5

    def uniform(self, lower: float, upper: float) -> float:
        return lower + (upper - lower) * self.value

    def random(self) -> float:
        return self.value


BASE_STATES = ("idle", "interact", "move", "sit", "sleep")


def test_policy_is_off_and_relaxed_by_default() -> None:
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())

    assert policy.enabled is False
    assert policy.state == "idle"
    assert policy.deadline is None
    assert policy.diversion_plan() == (
        ("interact", pytest.approx(50.0 * 100 / 90)),
        ("sit", pytest.approx(30.0 * 100 / 90)),
        ("sleep", pytest.approx(10.0 * 100 / 90)),
    )


def test_enable_starts_a_fresh_wall_clock_relax_timer() -> None:
    clock = FakeClock(100.0)
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())

    transition = policy.enable()

    assert transition.state == "idle"
    assert policy.deadline == pytest.approx(167.5)
    clock.advance(67.49)
    assert policy.on_animation_cycle_boundary() is None
    clock.advance(0.02)
    transition = policy.on_animation_cycle_boundary()
    assert transition is not None
    assert transition.state == "interact"
    assert transition.hold is False
    assert policy.deadline is None

    # The selected diversion is one complete animation cycle, then Relax
    # receives a fresh 45–90 second dwell.
    transition = policy.on_animation_cycle_boundary()
    assert transition is not None
    assert transition.state == "idle"
    assert policy.deadline == pytest.approx(clock.value + 67.5)


def test_special_slot_is_used_when_available() -> None:
    policy = AnimationPolicy(
        clock=FakeClock(),
        rng=FixedRandom(),
        available_states=(*BASE_STATES, "special"),
    )

    assert policy.diversion_plan() == (
        ("interact", 50.0),
        ("sit", 30.0),
        ("sleep", 10.0),
        ("special", 10.0),
    )
    policy = AnimationPolicy(
        clock=FakeClock(),
        rng=FixedRandom(0.95),
        available_states=(*BASE_STATES, "special"),
    )
    policy.enable()
    assert policy.select_diversion() == "special"


def test_unrelated_extra_state_does_not_become_a_special_slot() -> None:
    policy = AnimationPolicy(
        clock=FakeClock(),
        rng=FixedRandom(0.95),
        available_states=(*BASE_STATES, "wave"),
    )

    assert policy.special_state is None
    assert policy.select_diversion() == "sleep"


def test_inactivity_enters_continuous_sleep_at_a_boundary() -> None:
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())
    policy.enable()

    clock.advance(300.0)
    transition = policy.on_animation_cycle_boundary()

    assert transition is not None
    assert transition.state == "sleep"
    assert transition.hold is True
    assert policy.on_animation_cycle_boundary() is None


def test_running_mode_changes_at_cycle_boundary_and_repeats_move_interact() -> None:
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())
    policy.enable()

    assert policy.set_mode("running") is None
    assert policy.state == "idle"
    transition = policy.on_animation_cycle_boundary()
    assert transition is not None
    assert transition.state == "move"
    assert policy.deadline == pytest.approx(15.0)

    clock.advance(14.99)
    assert policy.on_animation_cycle_boundary() is None
    clock.advance(0.02)
    transition = policy.on_animation_cycle_boundary()
    assert transition is not None
    assert transition.state == "interact"
    assert transition.hold is False

    # A single completed interact cycle starts the next move block.
    transition = policy.on_animation_cycle_boundary()
    assert transition is not None
    assert transition.state == "move"
    assert policy.deadline == pytest.approx(clock.value + 15.0)

    # Leaving running takes effect at the next cycle boundary, without
    # waiting for the current 10–20 second move block to expire.
    assert policy.set_mode("idle") is None
    transition = policy.on_animation_cycle_boundary()
    assert transition is not None
    assert transition.state == "idle"


def test_sleep_is_interrupted_immediately_when_codex_starts_running() -> None:
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())
    policy.enable()
    clock.advance(300)
    assert policy.on_animation_cycle_boundary() is not None
    assert policy.state == "sleep"

    transition = policy.set_mode("running")

    assert transition is not None
    assert transition.state == "move"
    assert policy.state == "move"


def test_manual_sleep_override_finishes_before_running_mode_resumes() -> None:
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())
    policy.enable()
    policy.start_override("sleep")

    assert policy.set_mode("running") is None
    assert policy.state == "sleep"
    transition = policy.on_animation_cycle_boundary()

    assert transition is not None
    assert transition.state == "move"
    assert policy.override_active is False


def test_enabling_after_inactivity_starts_a_fresh_activity_window() -> None:
    clock = FakeClock(10.0)
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())
    clock.advance(300.0)

    policy.enable()

    assert policy.last_activity == pytest.approx(310.0)
    assert policy.on_animation_cycle_boundary() is None
    assert policy.state == "idle"


def test_running_to_idle_boundary_starts_a_fresh_inactivity_window() -> None:
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())
    policy.enable()
    policy.set_mode("running")
    assert policy.on_animation_cycle_boundary() is not None
    clock.advance(301.0)

    assert policy.set_mode("idle") is None
    transition = policy.on_animation_cycle_boundary()

    assert transition is not None
    assert transition.state == "idle"
    assert policy.last_activity == pytest.approx(clock.value)


def test_sleep_selected_as_a_diversion_returns_to_relax_after_one_cycle() -> None:
    clock = FakeClock()
    policy = AnimationPolicy(clock=clock, rng=FixedRandom(0.95))
    policy.enable()
    assert policy.deadline is not None
    clock.advance(policy.deadline - clock.value)

    transition = policy.on_animation_cycle_boundary()
    assert transition is not None and transition.state == "sleep"
    transition = policy.on_animation_cycle_boundary()

    assert transition is not None
    assert transition.state == "idle"


def test_one_shot_override_resets_inactivity_on_completion_and_resumes_auto() -> None:
    clock = FakeClock(20.0)
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())
    policy.enable()
    before = policy.last_activity

    transition = policy.start_override("interact")
    assert transition.state == "interact"
    assert policy.last_activity == before

    clock.advance(3.0)
    transition = policy.on_animation_cycle_boundary()
    assert transition is not None
    assert transition.state == "idle"
    assert policy.last_activity == pytest.approx(23.0)
    assert policy.deadline == pytest.approx(23.0 + 67.5)


def test_drag_override_stays_move_until_release_then_resets_activity() -> None:
    clock = FakeClock(50.0)
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())
    policy.enable()
    policy.start_drag()

    clock.advance(300.0)
    assert policy.on_animation_cycle_boundary() is None
    transition = policy.release_drag()

    assert transition is not None
    assert transition.state == "idle"
    assert policy.last_activity == pytest.approx(350.0)


def test_disabling_returns_to_relax_without_touching_activity_timestamp() -> None:
    clock = FakeClock(10.0)
    policy = AnimationPolicy(clock=clock, rng=FixedRandom())
    policy.enable()
    clock.advance(4.0)
    last_activity = policy.last_activity

    transition = policy.disable()

    assert transition.state == "idle"
    assert policy.enabled is False
    assert policy.deadline is None
    assert policy.last_activity == last_activity
