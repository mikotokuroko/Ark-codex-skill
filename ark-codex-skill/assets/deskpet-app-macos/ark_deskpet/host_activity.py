"""Read-only discovery of the local ChatGPT/Codex host process.

The status reader needs one small piece of process information that is not
stored in a rollout file: whether the host which owns the current session is
still running, and when that host was launched.  This module keeps the
platform-specific lookup here so the JSONL parser remains usable on its own
and in tests on non-macOS systems.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as _datetime
import math
import subprocess
import time
from typing import Any, Callable, Iterable

from .lifecycle import is_matching_host


# This is deliberately captured once.  If AppKit and ``ps`` cannot provide a
# launch date, the monitor's startup is the conservative boundary for session
# events.  Capturing it at import time also prevents the boundary moving on
# every two-second status refresh.
MONITOR_STARTED_AT = time.time()


@dataclass(frozen=True)
class HostSnapshot:
    """A point-in-time observation of the local Codex/ChatGPT host.

    ``launch_time`` is preferred when available.  ``process_start_time`` is
    the fallback obtained from the operating system.  ``monitor_started_at``
    is carried for callers which want to preserve the exact fallback boundary
    used by the monitor.  All times are Unix seconds.
    """

    running: bool
    launch_time: float | None = None
    process_start_time: float | None = None
    monitor_started_at: float | None = None
    pids: tuple[int, ...] = ()
    effective_cutoff: float | None = None

    @property
    def launch_date(self) -> float | None:
        """Compatibility alias for AppKit's ``launchDate`` terminology."""

        return self.launch_time

    @property
    def cutoff(self) -> float | None:
        """Returns the best launch boundary represented by this snapshot."""

        for value in (
            self.effective_cutoff,
            self.launch_time,
            self.process_start_time,
            self.monitor_started_at,
        ):
            normalized = _number(value)
            if normalized is not None:
                return normalized
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            result = float(value)
        except (OverflowError, TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None
    return None


def _date_timestamp(value: Any) -> float | None:
    """Converts common NSDate/JSON date shapes to Unix seconds."""

    number = _number(value)
    if number is not None:
        return number
    for method_name in ("timeIntervalSince1970", "timestamp"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                result = method()
            except (AttributeError, OSError, TypeError, ValueError):
                continue
            number = _number(result)
            if number is not None:
                return number
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                parsed = _datetime.datetime.fromisoformat(
                    text.replace("Z", "+00:00")
                )
            except ValueError:
                parsed = None
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=_datetime.timezone.utc)
                return parsed.timestamp()
    return None


def running_applications() -> list[dict[str, Any]]:
    """Returns matching NSWorkspace application metadata when available.

    The shape intentionally follows :func:`watcher.running_applications` so
    callers can inject the same dictionaries in tests.  Importing AppKit is
    delayed and failures are treated as an unavailable host probe.
    """

    try:
        import AppKit
    except ImportError:
        return []

    try:
        applications = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
    except (AttributeError, OSError, TypeError):
        return []
    result: list[dict[str, Any]] = []
    for application in applications or ():
        try:
            pid = int(application.processIdentifier())
        except (AttributeError, TypeError, ValueError):
            continue
        try:
            bundle_id = application.bundleIdentifier()
        except AttributeError:
            bundle_id = None
        try:
            name = application.localizedName()
        except AttributeError:
            name = None
        try:
            launch_date = application.launchDate()
        except AttributeError:
            launch_date = None
        result.append(
            {
                "pid": pid,
                "bundle_id": bundle_id,
                "name": name,
                "launch_time": _date_timestamp(launch_date),
                "launch_date": launch_date,
            }
        )
    return result


def _process_start_time(pid: int) -> float | None:
    """Reads a process start time from ``ps`` on macOS.

    This fallback is kept in a small function so tests can inject it without
    importing AppKit or spawning a process.
    """

    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    if not value:
        return None
    try:
        # ``ps lstart`` is rendered in the machine's local timezone.  A
        # naive datetime therefore intentionally uses the local timezone when
        # converted to Unix seconds.
        return _datetime.datetime.strptime(
            value, "%a %b %d %H:%M:%S %Y"
        ).timestamp()
    except ValueError:
        return None


def _matching_applications(
    applications: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for application in applications:
        if not isinstance(application, dict):
            continue
        bundle_id = application.get("bundle_id")
        name = application.get("name")
        if not isinstance(bundle_id, str):
            bundle_id = None
        if not isinstance(name, str):
            name = None
        if is_matching_host(bundle_id, name):
            result.append(application)
    # Status belongs to the concrete Codex desktop host.  A separately running
    # ChatGPT process can have the same display name fallback but must not keep
    # old Codex rollouts alive after Codex exits.
    concrete = [
        application
        for application in result
        if str(application.get("bundle_id") or "").casefold()
        == "com.openai.codex"
    ]
    return concrete


def snapshot_from_applications(
    applications: Iterable[dict[str, Any]],
    *,
    monitor_started_at: float | None = None,
    process_start_provider: Callable[[int], float | None] = _process_start_time,
) -> HostSnapshot:
    """Builds a host snapshot from injectable application dictionaries."""

    matching = _matching_applications(applications)
    if not matching:
        return HostSnapshot(
            running=False,
            monitor_started_at=(
                MONITOR_STARTED_AT
                if monitor_started_at is None
                else monitor_started_at
            ),
        )

    launch_times = []
    process_starts = []
    effective_times = []
    pids = []
    for application in matching:
        pid = application.get("pid")
        if isinstance(pid, int) and pid > 0:
            pids.append(pid)
        launch_time = _date_timestamp(
            application.get("launch_time", application.get("launch_date"))
        )
        if launch_time is not None:
            launch_times.append(launch_time)
            effective_times.append(launch_time)
        if launch_time is None and isinstance(pid, int) and pid > 0:
            try:
                process_start = process_start_provider(pid)
            except (OSError, TypeError, ValueError):
                process_start = None
            process_start = _date_timestamp(process_start)
            if process_start is not None:
                process_starts.append(process_start)
                effective_times.append(process_start)

    return HostSnapshot(
        running=True,
        # Multiple host applications can be open at once.  Retain the oldest
        # live host boundary so a task belonging to the still-open application
        # is not discarded when another host was launched later.
        launch_time=min(launch_times) if launch_times else None,
        process_start_time=(
            min(process_starts) if process_starts else None
        ),
        monitor_started_at=(
            MONITOR_STARTED_AT if monitor_started_at is None else monitor_started_at
        ),
        pids=tuple(sorted(set(pids))),
        effective_cutoff=min(effective_times) if effective_times else None,
    )


def current_host_snapshot(
    *,
    monitor_started_at: float | None = None,
    applications_provider: Callable[
        [], Iterable[dict[str, Any]]
    ] = running_applications,
    process_start_provider: Callable[[int], float | None] = _process_start_time,
) -> HostSnapshot:
    """Returns the current local host snapshot."""

    try:
        applications = applications_provider()
    except (OSError, TypeError, ValueError):
        applications = ()
    return snapshot_from_applications(
        applications,
        monitor_started_at=monitor_started_at,
        process_start_provider=process_start_provider,
    )


def launch_cutoff(
    snapshot: HostSnapshot | dict[str, Any] | None,
    *,
    monitor_started_at: float | None = None,
) -> float | None:
    """Returns the preferred launch boundary from a snapshot-like value."""

    if snapshot is None:
        return monitor_started_at
    if isinstance(snapshot, HostSnapshot):
        value = snapshot.cutoff
        return value if value is not None else monitor_started_at
    if isinstance(snapshot, dict):
        for key in (
            "effective_cutoff",
            "launch_time",
            "launch_date",
            "host_launch",
            "process_start_time",
            "process_start",
            "start_time",
            "monitor_started_at",
        ):
            value = _date_timestamp(snapshot.get(key))
            if value is not None:
                return value
    return monitor_started_at


def snapshot_running(
    snapshot: HostSnapshot | dict[str, Any] | bool | None,
) -> bool | None:
    """Returns a normalized running flag, or ``None`` when unspecified."""

    if isinstance(snapshot, HostSnapshot):
        return snapshot.running
    if isinstance(snapshot, bool):
        return snapshot
    if isinstance(snapshot, dict):
        value = snapshot.get("running", snapshot.get("host_running"))
        if isinstance(value, bool):
            return value
        applications = snapshot.get("applications")
        if isinstance(applications, (list, tuple)):
            return bool(_matching_applications(applications))
    return None


# Friendly aliases for callers/tests that prefer an imperative name.
get_host_snapshot = current_host_snapshot
get_launch_cutoff = launch_cutoff
