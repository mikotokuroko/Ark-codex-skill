"""Read-only parsing of recent Codex session state."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import time
from typing import Any


def _tail(path: Path, size: int = 262_144) -> str:
    """Reads a UTF-8-safe tail of a session file."""
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


def _message_text(content: Any) -> str:
    """Extracts text from supported Codex message content shapes."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        item.get("text", "")
        for item in content
        if isinstance(item, dict)
        and item.get("type") in ("input_text", "output_text", "text")
        and isinstance(item.get("text", ""), str)
    )


def _clean(text: str, limit: int = 80) -> str:
    """Normalizes and truncates status text."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def _empty_status() -> dict[str, Any]:
    """Returns the status shown when no Codex session exists."""
    return {
        "active": False,
        "state": "idle",
        "task": None,
        "model": None,
        "progress": None,
        "elapsed": None,
        "tokens": None,
        "last_finished": None,
    }


def parse_session(path: Path, now: float | None = None) -> dict[str, Any]:
    """Parses status from a Codex rollout JSONL file without modifying it."""
    current_time = time.time() if now is None else now
    status = _empty_status()
    started_at = None
    last_finished = None
    saw_lifecycle = False
    try:
        modified = path.stat().st_mtime
        lines = _tail(path).splitlines()
    except OSError:
        return status
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get("type")
        if payload_type == "task_started":
            saw_lifecycle = True
            status["state"] = "running"
            value = payload.get("started_at")
            if isinstance(value, (int, float)):
                started_at = float(value)
        elif payload_type == "token_count":
            usage = (payload.get("info") or {}).get("total_token_usage") or {}
            value = usage.get("total_tokens")
            if isinstance(value, (int, float)):
                status["tokens"] = int(value)
        elif payload_type == "task_complete":
            saw_lifecycle = True
            status["state"] = "waiting"
            value = payload.get("completed_at")
            if isinstance(value, (int, float)):
                last_finished = float(value)
            message = payload.get("last_agent_message")
            if isinstance(message, str) and message.strip():
                status["progress"] = _clean(message)
        elif payload_type == "turn_aborted":
            saw_lifecycle = True
            reason = str(payload.get("reason", "")).lower()
            if reason in ("interrupted", "cancelled", "canceled"):
                status["state"] = "idle"
            else:
                status["state"] = "error"
                if reason:
                    status["progress"] = _clean(reason)
        elif payload_type in ("error", "task_failed", "fatal_error"):
            saw_lifecycle = True
            status["state"] = "error"
            message = payload.get("message") or payload.get("error")
            if isinstance(message, str) and message.strip():
                status["progress"] = _clean(message)
        if payload_type in ("user_message", "message") and payload.get(
            "role"
        ) in (None, "user"):
            text = payload.get("message")
            if not isinstance(text, str):
                text = _message_text(payload.get("content"))
            if (
                text
                and "<environment_context>" not in text
                and "permissions instructions" not in text
            ):
                marker = "My request for Codex:"
                status["task"] = _clean(text.split(marker, 1)[-1])
        if payload_type == "agent_message" and payload.get(
            "phase"
        ) == "commentary":
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                status["progress"] = _clean(message)
        thread_settings = payload.get("thread_settings")
        if isinstance(thread_settings, dict) and thread_settings.get("model"):
            status["model"] = str(thread_settings["model"])
        elif payload.get("model"):
            status["model"] = str(payload["model"])
    if not saw_lifecycle and current_time - modified < 8:
        status["state"] = "running"
    status["active"] = status["state"] == "running"
    if status["active"] and started_at is not None:
        status["elapsed"] = max(0, int(current_time - started_at))
    if last_finished is not None:
        status["last_finished"] = datetime.datetime.fromtimestamp(
            last_finished
        ).strftime("%H:%M")
    return status


def get_codex_status(
    sessions_root: Path | None = None, now: float | None = None
) -> dict[str, Any]:
    """Returns status from the newest Codex session file."""
    root = sessions_root or Path.home() / ".codex" / "sessions"
    try:
        files = list(root.glob("**/rollout-*.jsonl"))
        files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        return _empty_status()
    for path in files:
        status = parse_session(path, now=now)
        if status.get("model") != "codex-auto-review":
            return status
    return _empty_status()
