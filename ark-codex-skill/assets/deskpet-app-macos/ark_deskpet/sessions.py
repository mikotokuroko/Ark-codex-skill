"""Read-only aggregation of recent Codex session state.

Codex writes one append-only JSONL rollout file per thread.  Looking only at
the newest file makes a completed thread hide an older thread which is still
running, and a silent thread is easy to mistake for an abandoned one.  This
module keeps a small parsed state for every rollout, merges the states, and
uses the current local host process as the lifetime boundary.

The public functions retain the original two-argument API.  Host information
and the clock are optional keyword-only injections so the reader can be tested
without a real AppKit process, while the app can keep calling
``get_codex_status()`` unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import json
import math
from pathlib import Path
import time
from typing import Any


TAIL_SIZE = 262_144
AUTO_REVIEW_MODEL = "codex-auto-review"


def _empty_status() -> dict[str, Any]:
    """Returns the status shown when no eligible Codex session exists."""

    return {
        "active": False,
        "state": "idle",
        "task": None,
        "model": None,
        "progress": None,
        "elapsed": None,
        "tokens": None,
        "last_finished": None,
        # These fields are useful to callers that need to correlate a caption
        # with a rollout, while remaining harmless to older callers.
        "task_id": None,
        "turn_id": None,
        "lifecycle_id": None,
    }


def _clean(text: str, limit: int = 80) -> str:
    """Normalizes and truncates status text."""

    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def _message_text(content: Any) -> str:
    """Extracts text from supported Codex message content shapes."""

    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        value = content.get("text")
        return value if isinstance(value, str) else ""
    if not isinstance(content, list):
        return ""
    pieces = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in (
            "input_text",
            "output_text",
            "text",
            "input",
            "output",
        ):
            continue
        value = item.get("text")
        if isinstance(value, str):
            pieces.append(value)
    return "".join(pieces)


def _clock_time(clock: Any = None) -> float:
    """Returns time from an injected callable/object or the system clock."""

    if clock is None:
        return time.time()
    value = clock() if callable(clock) else clock.time()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("clock must return a numeric Unix timestamp")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        raise TypeError("clock must return a numeric Unix timestamp") from None
    if not math.isfinite(result):
        raise TypeError("clock must return a numeric Unix timestamp")
    return result


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


def _timestamp(value: Any) -> float | None:
    """Converts numeric, ISO, and NSDate-like values to Unix seconds."""

    number = _number(value)
    if number is not None:
        return number
    for method_name in ("timeIntervalSince1970", "timestamp"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                number = _number(method())
            except (AttributeError, OSError, TypeError, ValueError):
                number = None
            if number is not None:
                return number
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                parsed = datetime.datetime.fromisoformat(
                    text.replace("Z", "+00:00")
                )
            except ValueError:
                parsed = None
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=datetime.timezone.utc)
                return parsed.timestamp()
    return None


def _value_as_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _identifier_values(item: dict[str, Any], payload: dict[str, Any]) -> set[str]:
    """Returns lifecycle IDs from common Codex field spellings."""

    values: set[str] = set()
    for source in (payload, item):
        for key in (
            "task_id",
            "taskId",
            "task_uuid",
            "taskUuid",
            "turn_id",
            "turnId",
            "thread_id",
            "threadId",
            "lifecycle_id",
            "lifecycleId",
            "id",
        ):
            value = source.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                text = str(value).strip()
                if text:
                    values.add(text)
        for key in ("task", "turn", "lifecycle"):
            nested = source.get(key)
            if isinstance(nested, dict):
                nested_id = nested.get("id") or nested.get("uuid")
                if isinstance(nested_id, (str, int)) and not isinstance(
                    nested_id, bool
                ):
                    values.add(str(nested_id).strip())
    return {value for value in values if value}


def _task_id(item: dict[str, Any], payload: dict[str, Any]) -> str | None:
    for source in (payload, item):
        for key in ("task_id", "taskId", "task_uuid", "taskUuid"):
            value = source.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                return str(value)
    return None


def _turn_id(item: dict[str, Any], payload: dict[str, Any]) -> str | None:
    for source in (payload, item):
        for key in ("turn_id", "turnId"):
            value = source.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                return str(value)
    return None


def _lifecycle_id(item: dict[str, Any], payload: dict[str, Any]) -> str | None:
    """Returns a stable preferred lifecycle identifier."""

    for source in (payload, item):
        for key in (
            "task_id",
            "taskId",
            "task_uuid",
            "taskUuid",
            "turn_id",
            "turnId",
            "lifecycle_id",
            "lifecycleId",
            "id",
        ):
            value = source.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                text = str(value).strip()
                if text:
                    return text
    return None


def _event_payload(item: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Unwraps event envelopes while tolerating partial/malformed records."""

    if not isinstance(item, dict):
        return None
    payload = item.get("payload")
    if isinstance(payload, dict):
        # A few rollout writers wrap the actual event one level deeper.
        nested = payload.get("payload")
        if isinstance(nested, dict) and isinstance(nested.get("type"), str):
            return item, nested
        # Also accept a compact record such as
        # ``{"type": "task_started", "payload": {"started_at": ...}}``.
        if not isinstance(payload.get("type"), str):
            envelope_type = item.get("type")
            if isinstance(envelope_type, str) and envelope_type.casefold() not in {
                "event_msg",
                "event",
                "message",
            }:
                payload = dict(payload)
                payload["type"] = envelope_type
        return item, payload
    if isinstance(item.get("type"), str):
        return item, item
    return None


def _event_type(payload: dict[str, Any]) -> str:
    value = payload.get("type") or payload.get("event_type")
    return value.casefold() if isinstance(value, str) else ""


def _event_timestamp(item: dict[str, Any], payload: dict[str, Any]) -> float | None:
    event_type = _event_type(payload)
    if "start" in event_type:
        preferred = (
            "started_at",
            "start_time",
            "created_at",
            "timestamp",
            "time",
        )
    elif any(
        token in event_type
        for token in ("complete", "finish", "abort", "error", "fail")
    ):
        preferred = (
            "completed_at",
            "finished_at",
            "created_at",
            "timestamp",
            "time",
        )
    else:
        preferred = (
            "timestamp",
            "created_at",
            "time",
            "started_at",
            "completed_at",
        )
    for source in (payload, item):
        for key in preferred:
            value = _timestamp(source.get(key))
            if value is not None:
                return value
    return None


def _event_message(payload: dict[str, Any]) -> str | None:
    for key in ("message", "last_agent_message", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
        if key == "content":
            text = _message_text(value)
            if text:
                return text
    return None


def _is_review_model(model: Any) -> bool:
    if not isinstance(model, str):
        return False
    return model.casefold().strip() == AUTO_REVIEW_MODEL


def _format_finished(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(value).strftime("%H:%M")
    except (OverflowError, OSError, ValueError):
        return None


def _model_from(payload: dict[str, Any]) -> str | None:
    settings = payload.get("thread_settings")
    if isinstance(settings, dict):
        for key in ("model", "model_name"):
            value = _value_as_text(settings.get(key))
            if value:
                return value
    for key in ("model", "model_name"):
        value = _value_as_text(payload.get(key))
        if value:
            return value
    return None


@dataclass
class _Start:
    """State belonging to one task/turn start event."""

    ids: set[str] = field(default_factory=set)
    task_id: str | None = None
    turn_id: str | None = None
    started_at: float | None = None
    sequence: int = 0
    task: str | None = None
    model: str | None = None
    progress: str | None = None
    tokens: int | None = None


@dataclass
class _SessionState:
    """Incrementally accumulated state for one rollout file."""

    active: list[_Start] = field(default_factory=list)
    ignored_ids: set[str] = field(default_factory=set)
    pending_task: str | None = None
    task: str | None = None
    model: str | None = None
    progress: str | None = None
    tokens: int | None = None
    terminal_state: str | None = None
    terminal_progress: str | None = None
    terminal_task: str | None = None
    terminal_model: str | None = None
    terminal_tokens: int | None = None
    terminal_finished_at: float | None = None
    terminal_task_id: str | None = None
    terminal_turn_id: str | None = None
    terminal_lifecycle_id: str | None = None
    latest_event_at: float | None = None
    latest_sequence: int = 0
    saw_signal: bool = False
    saw_lifecycle: bool = False
    stale_anonymous_starts: int = 0

    def _latest_active(self) -> _Start | None:
        return self.active[-1] if self.active else None

    def _apply_task(self, text: str | None) -> None:
        if not text:
            return
        cleaned = _clean(text)
        if not cleaned:
            return
        self.task = cleaned
        self.pending_task = cleaned
        current = self._latest_active()
        if current is not None:
            current.task = cleaned

    def _apply_model(self, model: str | None) -> None:
        if not model:
            return
        self.model = model
        current = self._latest_active()
        if current is not None:
            current.model = model

    def _apply_progress(self, message: str | None) -> None:
        if not message or not message.strip():
            return
        cleaned = _clean(message)
        self.progress = cleaned
        current = self._latest_active()
        if current is not None:
            current.progress = cleaned

    def _apply_tokens(self, value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        self.tokens = int(value)
        current = self._latest_active()
        if current is not None:
            current.tokens = int(value)

    def _remember_terminal(
        self,
        state: str,
        *,
        item: dict[str, Any],
        payload: dict[str, Any],
        event_time: float | None,
        record: _Start | None,
        message: str | None = None,
    ) -> None:
        self.terminal_state = state
        self.terminal_finished_at = event_time
        self.terminal_task = (
            record.task if record and record.task else self.task or self.pending_task
        )
        self.terminal_model = (
            record.model if record and record.model else self.model
        )
        self.terminal_tokens = (
            record.tokens if record and record.tokens is not None else self.tokens
        )
        self.terminal_progress = (
            _clean(message)
            if message and message.strip()
            else record.progress
            if record and record.progress
            else self.progress
        )
        self.terminal_task_id = (
            record.task_id if record else _task_id(item, payload)
        )
        self.terminal_turn_id = (
            record.turn_id if record else _turn_id(item, payload)
        )
        self.terminal_lifecycle_id = _lifecycle_id(item, payload)

    def _matching_start(self, ids: set[str]) -> _Start | None:
        if not ids:
            return self.active[-1] if self.active else None
        for record in reversed(self.active):
            if record.ids.intersection(ids):
                return record
        return None

    def _remove_start(self, record: _Start) -> None:
        try:
            self.active.remove(record)
        except ValueError:
            pass

    def consume(
        self,
        item: dict[str, Any],
        *,
        file_modified: float,
        launch_cutoff: float | None,
    ) -> None:
        event = _event_payload(item)
        if event is None:
            return
        envelope, payload = event
        kind = _event_type(payload)
        model = _model_from(payload) or _model_from(envelope)
        if model:
            self._apply_model(model)
        event_time = _event_timestamp(envelope, payload)
        if event_time is not None:
            self.latest_event_at = event_time
        else:
            self.latest_event_at = max(
                self.latest_event_at or file_modified, file_modified
            )

        is_start = kind in {
            "task_started",
            "task_start",
            "turn_started",
            "turn_start",
            "task_created",
        }
        is_complete = kind in {
            "task_complete",
            "task_completed",
            "turn_complete",
            "turn_completed",
        }
        is_abort = kind in {
            "turn_aborted",
            "turn_abort",
            "task_aborted",
            "task_abort",
            "task_cancelled",
            "task_canceled",
            "turn_cancelled",
            "turn_canceled",
        }
        is_error = kind in {
            "error",
            "task_error",
            "turn_error",
            "task_failed",
            "turn_failed",
            "fatal_error",
        }
        if is_start or is_complete or is_abort or is_error:
            self.saw_lifecycle = True
            self.saw_signal = True
        elif kind in {
            "user_message",
            "message",
            "user_input",
            "token_count",
            "agent_message",
            "assistant_message",
            "session_meta",
            "thread_settings",
        } or model:
            self.saw_signal = True

        if is_start:
            ids = _identifier_values(envelope, payload)
            start_time = event_time
            # A timestamp-less historical rollout must not survive a host
            # restart merely because the file was touched later.  File mtime
            # is the least-wrong fallback for this rare old format.
            effective_start = file_modified if start_time is None else start_time
            stale = (
                launch_cutoff is not None and effective_start < launch_cutoff
            )
            if stale:
                if ids:
                    self.ignored_ids.update(ids)
                else:
                    self.stale_anonymous_starts += 1
                if not self.active:
                    self.pending_task = None
                    self.task = None
                    self.model = None
                    self.progress = None
                    self.tokens = None
                return
            record = _Start(
                ids=ids,
                task_id=_task_id(envelope, payload),
                turn_id=_turn_id(envelope, payload),
                started_at=start_time,
                sequence=self.latest_sequence,
                task=self.pending_task or self.task,
                model=model or self.model,
                progress=self.progress,
                tokens=self.tokens,
            )
            self.active.append(record)
            self.terminal_state = None
            return

        if kind in {"user_message", "message", "user_input"}:
            role = payload.get("role")
            if role in (None, "user"):
                message_ids = _identifier_values(envelope, payload)
                if (
                    not self.active
                    and (self.ignored_ids or self.stale_anonymous_starts)
                    and not message_ids.intersection(self.ignored_ids)
                ):
                    # A user message following a filtered pre-launch start
                    # belongs to that historical task; do not leak its title
                    # into the current host's caption.
                    return
                if message_ids.intersection(self.ignored_ids):
                    return
                text = _event_message(payload)
                if (
                    text
                    and "<environment_context>" not in text
                    and "permissions instructions" not in text
                ):
                    marker = "My request for Codex:"
                    self._apply_task(text.split(marker, 1)[-1])
            return

        if kind == "token_count":
            if not self.active and (self.ignored_ids or self.stale_anonymous_starts):
                return
            usage = payload.get("info") or {}
            if isinstance(usage, dict):
                total_usage = usage.get("total_token_usage") or {}
                if isinstance(total_usage, dict):
                    self._apply_tokens(total_usage.get("total_tokens"))
            return

        if kind in {"agent_message", "assistant_message"}:
            if not self.active and (self.ignored_ids or self.stale_anonymous_starts):
                return
            if payload.get("phase") == "commentary" or kind == "assistant_message":
                self._apply_progress(_event_message(payload))
            return

        if not (is_complete or is_abort or is_error):
            # Unknown records containing useful metadata should still make a
            # well-formed file visible to the aggregator, but never create an
            # active task by themselves.
            if model or kind in {"session_meta", "thread_settings"}:
                self.saw_signal = True
            return

        ids = _identifier_values(envelope, payload)
        if ids and ids.intersection(self.ignored_ids):
            return
        if (
            launch_cutoff is not None
            and event_time is not None
            and event_time < launch_cutoff
        ):
            return
        record = self._matching_start(ids)
        if (
            record is None
            and not self.active
            and (self.ignored_ids or self.stale_anonymous_starts)
        ):
            return
        # An explicit ID must match the start which it terminates.  This is
        # what prevents a newer waiting task from closing an older silent task
        # (and vice versa) when rollout files contain interleaved lifecycles.
        if ids and record is None and self.active:
            return
        if record is not None:
            self._remove_start(record)
        reason = str(payload.get("reason", "")).casefold()
        if is_abort and (
            reason in {"interrupted", "cancelled", "canceled", "user_cancelled"}
            or reason.startswith("cancel")
            or reason.startswith("interrupt")
        ):
            state = "idle"
        elif is_complete:
            state = "waiting"
        else:
            state = "error"
        self._remember_terminal(
            state,
            item=envelope,
            payload=payload,
            event_time=event_time,
            record=record,
            message=_event_message(payload),
        )

    def status(
        self,
        *,
        now: float,
        file_modified: float,
        legacy_recent_fallback: bool,
        launch_cutoff: float | None,
    ) -> dict[str, Any]:
        status = _empty_status()
        current = self._latest_active()
        if current is not None:
            status["state"] = "running"
            status["task"] = current.task or self.task or self.pending_task
            status["model"] = current.model or self.model
            status["progress"] = current.progress or self.progress
            status["tokens"] = (
                current.tokens if current.tokens is not None else self.tokens
            )
            status["task_id"] = current.task_id
            status["turn_id"] = current.turn_id
            status["lifecycle_id"] = (
                current.task_id
                or current.turn_id
                or next(iter(sorted(current.ids)), None)
            )
            if current.started_at is not None:
                status["elapsed"] = max(0, int(now - current.started_at))
        elif self.terminal_state:
            status["state"] = self.terminal_state
            status["task"] = self.terminal_task or self.task or self.pending_task
            status["model"] = self.terminal_model or self.model
            status["progress"] = self.terminal_progress or self.progress
            status["tokens"] = (
                self.terminal_tokens
                if self.terminal_tokens is not None
                else self.tokens
            )
            status["task_id"] = self.terminal_task_id
            status["turn_id"] = self.terminal_turn_id
            status["lifecycle_id"] = self.terminal_lifecycle_id
        elif (
            legacy_recent_fallback
            and self.saw_signal
            and not self.saw_lifecycle
            and now - file_modified < 8
            and (launch_cutoff is None or file_modified >= launch_cutoff)
        ):
            # Retains compatibility with old rollouts that contain only a
            # token/message record while avoiding a timeout for explicit,
            # long-running lifecycle records.
            status["state"] = "running"
            status["task"] = self.task or self.pending_task
            status["model"] = self.model
            status["progress"] = self.progress
            status["tokens"] = self.tokens
        else:
            if not (self.ignored_ids or self.stale_anonymous_starts):
                status["task"] = self.task or self.pending_task
                status["model"] = self.model
                status["progress"] = self.progress
                status["tokens"] = self.tokens

        status["active"] = status["state"] == "running"
        if current is None:
            status["last_finished"] = _format_finished(
                self.terminal_finished_at
            )
        return status


@dataclass
class _CacheEntry:
    signature: tuple[int, int]
    state: _SessionState
    offset: int
    pending: bytes
    launch_cutoff: float | None


_SESSION_CACHE: dict[Path, _CacheEntry] = {}


def clear_session_cache() -> None:
    """Clears the process-local rollout cache (primarily useful in tests)."""

    _SESSION_CACHE.clear()


def _tail(path: Path, size: int = TAIL_SIZE) -> str:
    """Reads a UTF-8-safe tail of a session file.

    Kept as a public-in-module helper for compatibility with earlier callers;
    status aggregation uses a full initial read plus incremental appends so a
    long task's start event is not lost outside this tail window.
    """

    with path.open("rb") as file:
        file.seek(0, 2)
        length = file.tell()
        start = max(0, length - size)
        file.seek(start)
        data = file.read().decode("utf-8", errors="replace")
    if start:
        newline = data.find("\n")
        return data[newline + 1 :] if newline >= 0 else ""
    return data


def _parse_line(line: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(line.decode("utf-8", errors="replace"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _consume_bytes(
    state: _SessionState,
    data: bytes,
    *,
    file_modified: float,
    launch_cutoff: float | None,
    sequence_start: int = 0,
) -> bytes:
    """Consumes complete JSONL records and returns the unfinished suffix."""

    state.latest_sequence = sequence_start
    parts = data.split(b"\n")
    pending = parts.pop() if parts else b""
    for line in parts:
        if not line.strip():
            continue
        item = _parse_line(line.rstrip(b"\r"))
        if item is None:
            continue
        state.latest_sequence += 1
        state.consume(
            item,
            file_modified=file_modified,
            launch_cutoff=launch_cutoff,
        )
    # A writer is allowed to leave the final JSON object without a newline.
    # Parse it now for compatibility, retain the raw bytes, and force a full
    # reparse if it changes so it cannot be applied twice after an append.
    if pending.strip():
        item = _parse_line(pending.rstrip(b"\r"))
        if item is not None:
            state.latest_sequence += 1
            state.consume(
                item,
                file_modified=file_modified,
                launch_cutoff=launch_cutoff,
            )
    return pending


def _full_cache_entry(
    path: Path,
    signature: tuple[int, int],
    *,
    file_modified: float,
    launch_cutoff: float | None,
) -> _CacheEntry | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    state = _SessionState()
    pending = _consume_bytes(
        state,
        data,
        file_modified=file_modified,
        launch_cutoff=launch_cutoff,
    )
    entry = _CacheEntry(
        signature=signature,
        state=state,
        offset=len(data),
        pending=pending,
        launch_cutoff=launch_cutoff,
    )
    _SESSION_CACHE[path] = entry
    return entry


def _cached_entry(
    path: Path, launch_cutoff: float | None
) -> tuple[_CacheEntry | None, float | None]:
    try:
        metadata = path.stat()
        signature = (int(metadata.st_mtime_ns), int(metadata.st_size))
        file_modified = float(metadata.st_mtime)
    except OSError:
        _SESSION_CACHE.pop(path, None)
        return None, None

    old = _SESSION_CACHE.get(path)
    if old is None or old.launch_cutoff != launch_cutoff:
        return (
            _full_cache_entry(
                path,
                signature,
                file_modified=file_modified,
                launch_cutoff=launch_cutoff,
            ),
            file_modified,
        )
    if old.signature == signature:
        return old, file_modified

    # Appends are common and can be read from the previous offset.  A retained
    # unterminated JSONL record is reparsed in full when the file changes,
    # because it may have become complete.
    if (
        signature[1] > old.signature[1]
        and not old.pending
        and old.offset <= signature[1]
    ):
        try:
            with path.open("rb") as file:
                file.seek(old.offset)
                data = file.read()
        except OSError:
            return None, file_modified
        pending = _consume_bytes(
            old.state,
            data,
            file_modified=file_modified,
            launch_cutoff=launch_cutoff,
            sequence_start=old.state.latest_sequence,
        )
        old.signature = signature
        old.offset = signature[1]
        old.pending = pending
        return old, file_modified
    return (
        _full_cache_entry(
            path,
            signature,
            file_modified=file_modified,
            launch_cutoff=launch_cutoff,
        ),
        file_modified,
    )


def _snapshot_parts(
    snapshot: Any,
    *,
    monitor_started_at: float | None,
) -> tuple[bool | None, float | None]:
    """Normalizes HostSnapshot/dict/list injections without importing AppKit."""

    from .host_activity import (
        HostSnapshot,
        launch_cutoff as snapshot_cutoff,
        snapshot_from_applications,
        snapshot_running,
    )

    if callable(snapshot):
        snapshot = snapshot()
    if isinstance(snapshot, (list, tuple)):
        snapshot = snapshot_from_applications(
            snapshot, monitor_started_at=monitor_started_at
        )
    running = snapshot_running(snapshot)
    cutoff = snapshot_cutoff(snapshot, monitor_started_at=monitor_started_at)
    if isinstance(snapshot, HostSnapshot) and cutoff is None:
        cutoff = monitor_started_at
    if running is None and isinstance(snapshot, dict):
        applications = snapshot.get("applications")
        if isinstance(applications, (list, tuple)):
            normalized = snapshot_from_applications(
                applications, monitor_started_at=monitor_started_at
            )
            running = normalized.running
            cutoff = snapshot_cutoff(
                normalized, monitor_started_at=monitor_started_at
            )
    return running, cutoff


def _resolve_host(
    *,
    sessions_root: Path | None,
    host_snapshot: Any,
    launch_cutoff: float | None,
    host_launch_cutoff: float | None,
    monitor_started_at: float | None,
) -> tuple[bool, float | None]:
    explicit_cutoff = (
        launch_cutoff if launch_cutoff is not None else host_launch_cutoff
    )
    if host_snapshot is not None:
        running, discovered_cutoff = _snapshot_parts(
            host_snapshot, monitor_started_at=monitor_started_at
        )
        return bool(True if running is None else running), (
            explicit_cutoff
            if explicit_cutoff is not None
            else discovered_cutoff
        )
    if explicit_cutoff is not None:
        # A caller providing only a boundary is explicitly describing a live
        # host (useful for deterministic tests).
        return True, explicit_cutoff
    if sessions_root is not None:
        # Existing callers passed temporary roots directly to test parsing.
        # Keep that API useful without pretending the real desktop host is
        # running when the app calls the no-argument form.
        return True, None
    from .host_activity import current_host_snapshot

    snapshot = current_host_snapshot(monitor_started_at=monitor_started_at)
    running, discovered_cutoff = _snapshot_parts(
        snapshot, monitor_started_at=monitor_started_at
    )
    return bool(running), discovered_cutoff


def _is_eligible(status: dict[str, Any]) -> bool:
    return not _is_review_model(status.get("model"))


def parse_session(
    path: Path,
    now: float | None = None,
    *,
    host_snapshot: Any = None,
    launch_cutoff: float | None = None,
    host_launch_cutoff: float | None = None,
    monitor_started_at: float | None = None,
    clock: Any = None,
) -> dict[str, Any]:
    """Parses one Codex rollout without modifying it.

    ``parse_session`` remains a file-level parser and therefore assumes the
    host exists when no snapshot is supplied.  Pass ``host_snapshot=False`` to
    force an idle result, or use :func:`get_codex_status` for the real host
    probe.
    """

    current_time = _clock_time(clock) if now is None else float(now)
    running, cutoff = _resolve_host(
        sessions_root=path.parent,
        host_snapshot=host_snapshot,
        launch_cutoff=launch_cutoff,
        host_launch_cutoff=host_launch_cutoff,
        monitor_started_at=monitor_started_at,
    )
    if not running:
        return _empty_status()
    entry, modified = _cached_entry(path, cutoff)
    if entry is None or modified is None:
        return _empty_status()
    return entry.state.status(
        now=current_time,
        file_modified=modified,
        legacy_recent_fallback=True,
        launch_cutoff=cutoff,
    )


def _candidate_key(
    status: dict[str, Any],
    *,
    path: Path,
    modified: float,
    active: bool,
) -> tuple[float, int, int, str]:
    started = _number(status.get("_started_at"))
    event = _number(status.get("_event_at"))
    return (
        started if started is not None else event if event is not None else modified,
        1 if active else 0,
        int(modified * 1_000_000),
        str(path),
    )


def _status_with_metadata(
    entry: _CacheEntry,
    status: dict[str, Any],
) -> dict[str, Any]:
    current = entry.state._latest_active()
    status["_started_at"] = (
        current.started_at
        if current is not None
        else entry.state.terminal_finished_at
    )
    status["_event_at"] = entry.state.latest_event_at
    status["_signal"] = entry.state.saw_signal
    status["_lifecycle"] = entry.state.saw_lifecycle
    return status


def get_codex_status(
    sessions_root: Path | None = None,
    now: float | None = None,
    *,
    host_snapshot: Any = None,
    launch_cutoff: float | None = None,
    host_launch_cutoff: float | None = None,
    monitor_started_at: float | None = None,
    clock: Any = None,
) -> dict[str, Any]:
    """Aggregates all eligible rollouts for the current local host.

    Any active task wins over waiting/error/idle tasks.  Among active tasks,
    the newest lifecycle start supplies caption details.  If none is active,
    the newest eligible terminal status is returned.  Automatic review
    rollouts are excluded at every stage.
    """

    current_time = _clock_time(clock) if now is None else float(now)
    running, cutoff = _resolve_host(
        sessions_root=sessions_root,
        host_snapshot=host_snapshot,
        launch_cutoff=launch_cutoff,
        host_launch_cutoff=host_launch_cutoff,
        monitor_started_at=monitor_started_at,
    )
    if not running:
        return _empty_status()
    root = sessions_root or Path.home() / ".codex" / "sessions"
    try:
        files = list(root.glob("**/rollout-*.jsonl"))
    except (OSError, ValueError):
        return _empty_status()

    active_candidates: list[tuple[tuple[float, int, int, str], dict[str, Any]]] = []
    terminal_candidates: list[tuple[tuple[float, int, int, str], dict[str, Any]]] = []
    for path in files:
        entry, modified = _cached_entry(path, cutoff)
        if entry is None or modified is None:
            continue
        status = _status_with_metadata(
            entry,
            entry.state.status(
                now=current_time,
                file_modified=modified,
                # A valid explicit lifecycle is required for the no-TTL
                # guarantee.  Legacy recent records remain visible for the
                # direct parser and for compatibility with old rollouts.
                legacy_recent_fallback=True,
                launch_cutoff=cutoff,
            ),
        )
        if not status.get("_signal") or not _is_eligible(status):
            continue
        active = bool(status.get("active"))
        key = _candidate_key(status, path=path, modified=modified, active=active)
        if active:
            active_candidates.append((key, status))
        else:
            terminal_candidates.append((key, status))

    if active_candidates:
        _, selected = max(active_candidates, key=lambda item: item[0])
    elif terminal_candidates:
        _, selected = max(terminal_candidates, key=lambda item: item[0])
    else:
        return _empty_status()
    for key in ("_started_at", "_event_at", "_signal", "_lifecycle"):
        selected.pop(key, None)
    return selected
