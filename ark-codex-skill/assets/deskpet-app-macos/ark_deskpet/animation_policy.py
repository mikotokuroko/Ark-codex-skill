"""Pure wall-clock policy for the desk-pet's optional automatic animations.

The Qt window owns frame playback.  This module only decides which animation
should be active at an animation-cycle boundary and when its wall-clock dwell
ends.  Keeping that decision state independent from Qt makes the behaviour
deterministic in tests and keeps the user's playback speed from changing the
policy's real-time cadence.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Any, Callable, Iterable, Mapping


RELAX_STATE = "idle"
RUNNING_MODE = "running"
IDLE_MODE = "idle"
IDLE_MIN_SECONDS = 45.0
IDLE_MAX_SECONDS = 90.0
MOVE_MIN_SECONDS = 10.0
MOVE_MAX_SECONDS = 20.0
INACTIVITY_SLEEP_SECONDS = 300.0

# The values are relative weights for selecting one diversion animation.  If
# a pet has no optional state, its 10-point slot is redistributed over the
# other slots in proportion to their original weights.
DIVERSION_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("interact", 50.0),
    ("sit", 30.0),
    ("sleep", 10.0),
    ("special", 10.0),
)
BASE_STATES = frozenset(("idle", "interact", "move", "sit", "sleep"))


@dataclass(frozen=True)
class PolicyTransition:
    """A requested visual state change returned by :class:`AnimationPolicy`."""

    state: str
    hold: bool
    reason: str = "auto"


class AnimationPolicy:
    """State machine for automatic dwell and activity-following behaviour.

    ``clock`` is expected to return a monotonic value in seconds.  ``rng`` can
    be any object exposing ``uniform(lower, upper)`` (including
    :class:`random.Random`), or a callable accepting the same arguments.
    Every method accepts an optional explicit ``now`` value so tests and host
    integrations can advance time without sleeping.
    """

    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        rng: Any | None = None,
        available_states: Iterable[str] | Mapping[str, Any] | None = None,
    ) -> None:
        self._clock = clock or time.monotonic
        self._rng = rng or random.Random()
        now = float(self._clock())
        self.enabled = False
        self.mode = IDLE_MODE
        self._active_mode = IDLE_MODE
        self._pending_mode: str | None = None
        self.state = RELAX_STATE
        self.hold = True
        self.deadline: float | None = None
        self.last_activity = now
        self._diversion_active = False
        self._available_states = set(BASE_STATES)
        self._override: dict[str, Any] | None = None
        self.set_available_states(available_states)

    @property
    def override_active(self) -> bool:
        """Whether a click, menu action, or drag currently owns playback."""
        return self._override is not None

    @property
    def dragging(self) -> bool:
        """Whether the active override is a drag that lasts until release."""
        return bool(self._override and self._override.get("drag"))

    @property
    def special_state(self) -> str | None:
        """Whether the loaded manifest contains the named optional state."""
        return "special" if "special" in self._available_states else None

    def _now(self, value: float | None) -> float:
        return float(self._clock() if value is None else value)

    def _uniform(self, lower: float, upper: float) -> float:
        source = self._rng
        if hasattr(source, "uniform"):
            value = source.uniform(lower, upper)
        elif callable(source):
            value = source(lower, upper)
        else:
            raise TypeError("rng must expose uniform(lower, upper)")
        return max(lower, min(upper, float(value)))

    def set_available_states(
        self,
        states: Iterable[str] | Mapping[str, Any] | None,
    ) -> None:
        """Updates the optional diversion state from a pet manifest.

        Pet manifests currently require five base states and may contain the
        optional state literally named ``special``.
        """
        if states is None:
            values = set(BASE_STATES)
        elif isinstance(states, Mapping):
            values = {str(value) for value in states}
        else:
            values = {str(value) for value in states}
        self._available_states = set(values) | set(BASE_STATES)

    def diversion_plan(self) -> tuple[tuple[str, float], ...]:
        """Returns weighted choices for one complete diversion.

        The numbers are relative weights rather than dwell durations.  The
        chosen animation plays once and the policy then returns to Relax.
        """
        special = self.special_state
        if special is not None:
            return DIVERSION_WEIGHTS
        base_total = sum(weight for _, weight in DIVERSION_WEIGHTS[:-1])
        full_total = sum(weight for _, weight in DIVERSION_WEIGHTS)
        factor = full_total / base_total
        return tuple(
            (state, weight * factor)
            for state, weight in DIVERSION_WEIGHTS[:-1]
        )

    def _random_unit(self) -> float:
        """Returns a deterministic unit draw from the injected random source."""
        source = self._rng
        if hasattr(source, "random"):
            value = source.random()
        elif hasattr(source, "uniform"):
            value = source.uniform(0.0, 1.0)
        elif callable(source):
            try:
                value = source()
            except TypeError:
                value = source(0.0, 1.0)
        else:
            raise TypeError("rng must expose random() or uniform(lower, upper)")
        return max(0.0, min(1.0, float(value)))

    def select_diversion(self) -> str:
        """Selects one action using the configured weighted distribution."""
        plan = self.diversion_plan()
        draw = self._random_unit() * sum(weight for _, weight in plan)
        cursor = 0.0
        for state, weight in plan:
            cursor += weight
            if draw < cursor:
                return state
        return plan[-1][0]

    def _transition(
        self, state: str, hold: bool, reason: str = "auto"
    ) -> PolicyTransition:
        self.state = state
        self.hold = hold
        return PolicyTransition(state, hold, reason)

    def _enter_relax(
        self, now: float, *, reset_activity: bool = False
    ) -> PolicyTransition:
        self._active_mode = IDLE_MODE
        if reset_activity:
            self.last_activity = now
        self._diversion_active = False
        self.deadline = now + self._uniform(IDLE_MIN_SECONDS, IDLE_MAX_SECONDS)
        return self._transition(RELAX_STATE, True, "auto-relax")

    def _enter_running(self, now: float) -> PolicyTransition:
        self._active_mode = RUNNING_MODE
        self._diversion_active = False
        self.deadline = now + self._uniform(MOVE_MIN_SECONDS, MOVE_MAX_SECONDS)
        return self._transition("move", True, "auto-running")

    def _enter_sleep(self) -> PolicyTransition:
        self._diversion_active = False
        self.deadline = None
        return self._transition("sleep", True, "continuous-sleep")

    def _start_diversion(self) -> PolicyTransition:
        self._active_mode = IDLE_MODE
        self._diversion_active = True
        self.deadline = None
        return self._transition(
            self.select_diversion(), False, "auto-diversion"
        )

    def enable(self, now: float | None = None) -> PolicyTransition:
        """Enables automatic playback and starts a fresh wall-clock dwell."""
        timestamp = self._now(now)
        self.enabled = True
        self.last_activity = timestamp
        self._pending_mode = None
        self._override = None
        if self.mode == RUNNING_MODE:
            return self._enter_running(timestamp)
        return self._enter_relax(timestamp)

    def disable(self, now: float | None = None) -> PolicyTransition:
        """Disables automatic playback and immediately returns to Relax."""
        del now  # Disabling must not count as user activity.
        self.enabled = False
        self._pending_mode = None
        self._override = None
        self._active_mode = IDLE_MODE
        self._diversion_active = False
        self.deadline = None
        return self._transition(RELAX_STATE, True, "manual-relax")

    def set_enabled(
        self, enabled: bool, now: float | None = None
    ) -> PolicyTransition:
        """Sets the auto toggle, returning the state that should be shown."""
        return self.enable(now) if enabled else self.disable(now)

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        return RUNNING_MODE if str(mode).lower() == RUNNING_MODE else IDLE_MODE

    def set_mode(
        self, mode: str, now: float | None = None
    ) -> PolicyTransition | None:
        """Requests an idle/running mode change for the next cycle boundary.

        Continuous sleep is the deliberate exception: a newly running Codex
        session interrupts it immediately so the pet reflects active work.
        """
        requested = self._normalize_mode(mode)
        timestamp = self._now(now)
        self.mode = requested
        if not self.enabled:
            return None
        if (
            requested == RUNNING_MODE
            and self.state == "sleep"
            and self._override is None
        ):
            self._override = None
            self._pending_mode = None
            return self._enter_running(timestamp)
        if self._override is not None:
            self._pending_mode = requested
            return None
        if requested == self._active_mode:
            self._pending_mode = None
            return None
        self._pending_mode = requested
        return None

    def _resume_after_override(self, now: float) -> PolicyTransition:
        self._override = None
        self.last_activity = now
        if not self.enabled:
            self._active_mode = IDLE_MODE
            self.deadline = None
            return self._transition(RELAX_STATE, True, "override-complete")
        self._pending_mode = None
        if self.mode == RUNNING_MODE:
            return self._enter_running(now)
        return self._enter_relax(now)

    def start_override(
        self, state: str, now: float | None = None
    ) -> PolicyTransition:
        """Starts a one-cycle manual animation without resetting activity yet."""
        del now
        target = str(state)
        if target not in self._available_states:
            target = RELAX_STATE
        self._override = {"state": target, "drag": False}
        self._diversion_active = False
        self.deadline = None
        return self._transition(target, False, "manual-override")

    def start_drag(self, now: float | None = None) -> PolicyTransition:
        """Starts a Move override that remains active until release."""
        del now  # Starting a drag is activity only when the release completes.
        self._override = {"state": "move", "drag": True}
        self._diversion_active = False
        self.deadline = None
        return self._transition("move", True, "manual-drag")

    def release_drag(self, now: float | None = None) -> PolicyTransition:
        """Completes a drag, records activity, and resumes the policy."""
        if not self.dragging:
            return self._transition(self.state, self.hold, "manual-release")
        return self._resume_after_override(self._now(now))

    def complete_override(
        self, now: float | None = None
    ) -> PolicyTransition | None:
        """Completes a one-shot override at its animation-cycle boundary."""
        if self._override is None:
            return None
        if self.dragging:
            return None
        return self._resume_after_override(self._now(now))

    def record_activity(self, now: float | None = None) -> None:
        """Records explicit user activity without changing the current state."""
        self.last_activity = self._now(now)

    def inactivity(self, now: float | None = None) -> float:
        """Returns elapsed real seconds since the latest completed override."""
        return max(0.0, self._now(now) - self.last_activity)

    def remaining(self, now: float | None = None) -> float | None:
        """Returns seconds until the current dwell expires, if one exists."""
        if self.deadline is None:
            return None
        return self.deadline - self._now(now)

    def on_animation_cycle_boundary(
        self, now: float | None = None
    ) -> PolicyTransition | None:
        """Advances the policy at an explicit visual animation boundary.

        Calling this at a frame boundary is safe even when no transition is
        due.  A late call advances only one phase, so a delayed event loop
        cannot skip a complete diversion or produce several visible state
        changes at once.
        """
        timestamp = self._now(now)

        if self._override is not None:
            if self.dragging:
                return None
            return self._resume_after_override(timestamp)

        if not self.enabled:
            return None

        if self._pending_mode is not None:
            requested = self._pending_mode
            self._pending_mode = None
            if requested == RUNNING_MODE:
                return self._enter_running(timestamp)
            return self._enter_relax(
                timestamp,
                reset_activity=self._active_mode == RUNNING_MODE,
            )

        if self._active_mode == RUNNING_MODE:
            if self.state == "move":
                if self.deadline is None or timestamp < self.deadline:
                    return None
                self.deadline = None
                return self._transition("interact", False, "auto-running-interact")
            if self.state == "interact":
                return self._enter_running(timestamp)
            return self._enter_running(timestamp)

        # Inactivity is evaluated only here, at a visual boundary.  Automatic
        # transitions never update ``last_activity``.
        if self.inactivity(timestamp) >= INACTIVITY_SLEEP_SECONDS:
            if self.state != "sleep":
                return self._enter_sleep()
            return None
        if self._diversion_active:
            # A selected diversion is one complete animation cycle.  Keep the
            # inactivity threshold boundary-aware, then start a fresh Relax
            # dwell for the next cycle.
            if self.inactivity(timestamp) >= INACTIVITY_SLEEP_SECONDS:
                return self._enter_sleep()
            return self._enter_relax(timestamp)
        if self.state == "sleep":
            return None
        if self.deadline is None or timestamp >= self.deadline:
            return self._start_diversion()
        return None


__all__ = [
    "AnimationPolicy",
    "BASE_STATES",
    "DIVERSION_WEIGHTS",
    "IDLE_MAX_SECONDS",
    "IDLE_MIN_SECONDS",
    "INACTIVITY_SLEEP_SECONDS",
    "MOVE_MAX_SECONDS",
    "MOVE_MIN_SECONDS",
    "PolicyTransition",
    "RELAX_STATE",
]
