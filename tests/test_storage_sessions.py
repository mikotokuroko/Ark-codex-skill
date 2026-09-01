"""Settings, runtime cleanup, and Codex session parsing tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ark_deskpet.constants import DEFAULT_PET, SETTINGS_VERSION
from ark_deskpet.sessions import get_codex_status, parse_session
from ark_deskpet.storage import (
    atomic_write_json,
    clean_stale_instance,
    load_settings,
    save_settings,
)


def test_settings_defaults_migration_and_unknown_values(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"active_pet": "旧角色", "pet_states": None, "future": 7}),
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings["version"] == SETTINGS_VERSION
    assert settings["language"] == "en"
    assert settings["pet"] == "旧角色"
    assert settings["pet_states"] == {}
    assert settings["future"] == 7


def test_corrupt_settings_return_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{", encoding="utf-8")
    assert load_settings(path)["pet"] == DEFAULT_PET


def test_settings_write_is_atomic_and_unicode_safe(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(path, {"pet": "夕", "pet_states": {}})
    assert json.loads(path.read_text(encoding="utf-8"))["pet"] == "夕"
    assert not list(tmp_path.glob("*.tmp"))


def test_stale_pid_and_socket_recovery(tmp_path: Path) -> None:
    instance = tmp_path / "instance.json"
    socket = tmp_path / "command.socket"
    atomic_write_json(instance, {"pid": 2_147_483_647})
    socket.write_text("stale", encoding="utf-8")
    assert clean_stale_instance(instance, socket)
    assert not instance.exists()
    assert not socket.exists()


def test_live_pid_is_not_cleaned(tmp_path: Path) -> None:
    instance = tmp_path / "instance.json"
    socket = tmp_path / "command.socket"
    atomic_write_json(instance, {"pid": os.getpid()})
    socket.touch()
    assert not clean_stale_instance(instance, socket)
    assert instance.exists() and socket.exists()


def test_codex_session_parsing(tmp_path: Path) -> None:
    session = tmp_path / "rollout-test.jsonl"
    events = [
        {"payload": {"type": "task_started", "started_at": 90}},
        {
            "payload": {
                "type": "user_message",
                "message": "制作一个 macOS 桌宠",
            }
        },
        {
            "payload": {
                "type": "token_count",
                "info": {"total_token_usage": {"total_tokens": 1234}},
            }
        },
        {
            "payload": {
                "type": "agent_message",
                "phase": "commentary",
                "message": "正在测试",
                "model": "gpt-test",
            }
        },
    ]
    session.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events),
        encoding="utf-8",
    )
    os.utime(session, (100, 100))
    status = parse_session(session, now=105)
    assert status["active"]
    assert status["state"] == "running"
    assert status["task"] == "制作一个 macOS 桌宠"
    assert status["tokens"] == 1234
    assert status["elapsed"] == 15
    assert status["progress"] == "正在测试"
    assert status["model"] == "gpt-test"


def test_missing_sessions_are_idle(tmp_path: Path) -> None:
    status = get_codex_status(tmp_path)
    assert status["active"] is False
    assert status["state"] == "idle"


def test_completed_session_waits_for_input(tmp_path: Path) -> None:
    session = tmp_path / "rollout-test.jsonl"
    session.write_text(
        "\n".join(
            json.dumps({"payload": payload})
            for payload in (
                {"type": "task_started", "started_at": 90},
                {"type": "task_complete", "completed_at": 100},
            )
        ),
        encoding="utf-8",
    )
    status = parse_session(session, now=105)
    assert status["active"] is False
    assert status["state"] == "waiting"


def test_failed_session_reports_error(tmp_path: Path) -> None:
    session = tmp_path / "rollout-test.jsonl"
    session.write_text(
        json.dumps(
            {"payload": {"type": "task_failed", "message": "Network lost"}}
        ),
        encoding="utf-8",
    )
    status = parse_session(session, now=105)
    assert status["state"] == "error"
    assert status["progress"] == "Network lost"


def test_recent_long_session_tail_still_reports_running(tmp_path: Path) -> None:
    session = tmp_path / "rollout-test.jsonl"
    session.write_text(
        json.dumps({"payload": {"type": "token_count"}}),
        encoding="utf-8",
    )
    os.utime(session, (100, 100))
    status = parse_session(session, now=105)
    assert status["active"] is True
    assert status["state"] == "running"


def test_internal_review_session_is_not_shown(tmp_path: Path) -> None:
    user_session = tmp_path / "rollout-user.jsonl"
    user_session.write_text(
        json.dumps({"payload": {"type": "task_complete"}}),
        encoding="utf-8",
    )
    review_session = tmp_path / "rollout-review.jsonl"
    review_session.write_text(
        json.dumps(
            {
                "payload": {
                    "type": "task_complete",
                    "model": "codex-auto-review",
                }
            }
        ),
        encoding="utf-8",
    )
    os.utime(user_session, (100, 100))
    os.utime(review_session, (101, 101))
    status = get_codex_status(tmp_path, now=105)
    assert status["state"] == "waiting"
    assert status["model"] is None
