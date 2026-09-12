"""Settings, runtime cleanup, and Codex session parsing tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ark_deskpet.constants import AUTO_ANIMATIONS_KEY, DEFAULT_PET, SETTINGS_VERSION
from ark_deskpet.host_activity import HostSnapshot, snapshot_from_applications
import ark_deskpet.sessions as sessions_module
from ark_deskpet.sessions import (
    clear_session_cache,
    get_codex_status,
    parse_session,
)
from ark_deskpet.storage import (
    atomic_write_json,
    clean_stale_instance,
    load_settings,
    save_settings,
)


def _write_rollout(path: Path, *payloads: dict[str, object]) -> None:
    path.write_text(
        "\n".join(json.dumps({"payload": payload}) for payload in payloads),
        encoding="utf-8",
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
    assert settings[AUTO_ANIMATIONS_KEY] is False


def test_auto_animation_setting_migrates_as_a_persisted_boolean(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({AUTO_ANIMATIONS_KEY: True}), encoding="utf-8")
    assert load_settings(path)[AUTO_ANIMATIONS_KEY] is True

    path.write_text(json.dumps({AUTO_ANIMATIONS_KEY: "yes"}), encoding="utf-8")
    assert load_settings(path)[AUTO_ANIMATIONS_KEY] is False


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


def test_active_task_wins_over_newer_waiting_rollout(tmp_path: Path) -> None:
    old = tmp_path / "rollout-old.jsonl"
    new = tmp_path / "rollout-new.jsonl"
    _write_rollout(
        old,
        {"type": "task_started", "started_at": 110, "task_id": "old"},
        {"type": "user_message", "message": "long running task"},
    )
    _write_rollout(
        new,
        {"type": "task_started", "started_at": 120, "task_id": "new"},
        {"type": "user_message", "message": "new task"},
        {"type": "task_complete", "completed_at": 130, "task_id": "new"},
    )
    status = get_codex_status(
        tmp_path,
        now=500,
        host_snapshot=HostSnapshot(True, launch_time=100),
    )
    assert status["active"] is True
    assert status["task"] == "long running task"
    assert status["task_id"] == "old"


def test_newest_active_task_supplies_caption_details(tmp_path: Path) -> None:
    first = tmp_path / "rollout-first.jsonl"
    second = tmp_path / "rollout-second.jsonl"
    _write_rollout(
        first,
        {"type": "task_started", "started_at": 110, "task_id": "first"},
        {"type": "user_message", "message": "first task"},
    )
    _write_rollout(
        second,
        {"type": "task_started", "started_at": 210, "task_id": "second"},
        {"type": "user_message", "message": "second task"},
    )
    status = get_codex_status(
        tmp_path,
        now=500,
        host_snapshot={"running": True, "launch_time": 100},
    )
    assert status["active"] is True
    assert status["task"] == "second task"
    assert status["task_id"] == "second"


def test_task_started_before_host_launch_is_ignored(tmp_path: Path) -> None:
    session = tmp_path / "rollout-stale.jsonl"
    _write_rollout(
        session,
        {"type": "task_started", "started_at": 90, "task_id": "stale"},
        {"type": "user_message", "message": "stale task"},
    )
    status = get_codex_status(
        tmp_path,
        now=500,
        host_snapshot=HostSnapshot(True, launch_time=100),
    )
    assert status["active"] is False
    assert status["state"] == "idle"


def test_filtered_prelaunch_task_does_not_leak_caption(tmp_path: Path) -> None:
    session = tmp_path / "rollout-stale-caption.jsonl"
    _write_rollout(
        session,
        {"type": "task_started", "started_at": 90, "task_id": "stale"},
        {"type": "user_message", "message": "historical task title"},
    )
    status = get_codex_status(
        tmp_path,
        now=500,
        host_snapshot=HostSnapshot(True, launch_time=100),
    )
    assert status["active"] is False
    assert status["state"] == "idle"
    assert status["task"] is None


def test_nonfinite_task_timestamp_is_ignored_without_crashing(tmp_path: Path) -> None:
    session = tmp_path / "rollout-nonfinite.jsonl"
    _write_rollout(
        session,
        {"type": "task_started", "started_at": float("inf"), "task_id": "bad"},
    )
    status = parse_session(
        session,
        now=500,
        host_snapshot=HostSnapshot(True, launch_time=100),
    )
    assert status["active"] is True
    assert status["elapsed"] is None


def test_silent_task_stays_running_without_a_short_timeout(tmp_path: Path) -> None:
    session = tmp_path / "rollout-silent.jsonl"
    _write_rollout(
        session,
        {"type": "task_started", "started_at": 110, "task_id": "silent"},
    )
    status = get_codex_status(
        tmp_path,
        now=100_000,
        host_snapshot=HostSnapshot(True, launch_time=100),
    )
    assert status["active"] is True
    assert status["task_id"] == "silent"


def test_closed_host_forces_silent_task_to_idle(tmp_path: Path) -> None:
    session = tmp_path / "rollout-silent.jsonl"
    _write_rollout(
        session,
        {"type": "task_started", "started_at": 110, "task_id": "silent"},
    )
    status = get_codex_status(
        tmp_path,
        now=100_000,
        host_snapshot=HostSnapshot(False, launch_time=100),
    )
    assert status["active"] is False
    assert status["state"] == "idle"


def test_cancelled_abort_matches_lifecycle_id(tmp_path: Path) -> None:
    session = tmp_path / "rollout-cancelled.jsonl"
    _write_rollout(
        session,
        {"type": "task_started", "started_at": 110, "task_id": "cancel-me"},
        {
            "type": "turn_aborted",
            "reason": "cancelled",
            "turn_id": "cancel-me",
        },
    )
    status = get_codex_status(
        tmp_path,
        now=500,
        host_snapshot=HostSnapshot(True, launch_time=100),
    )
    assert status["active"] is False
    assert status["state"] == "idle"


def test_mismatched_lifecycle_id_does_not_close_silent_task(tmp_path: Path) -> None:
    session = tmp_path / "rollout-ids.jsonl"
    _write_rollout(
        session,
        {"type": "task_started", "started_at": 110, "task_id": "keep"},
        {"type": "task_complete", "completed_at": 120, "task_id": "other"},
    )
    status = get_codex_status(
        tmp_path,
        now=500,
        host_snapshot=HostSnapshot(True, launch_time=100),
    )
    assert status["active"] is True
    assert status["task_id"] == "keep"


def test_malformed_new_rollout_does_not_hide_valid_active_task(tmp_path: Path) -> None:
    valid = tmp_path / "rollout-valid.jsonl"
    malformed = tmp_path / "rollout-new.jsonl"
    _write_rollout(
        valid,
        {"type": "task_started", "started_at": 110, "task_id": "valid"},
    )
    malformed.write_text("not json\n{partial", encoding="utf-8")
    status = get_codex_status(
        tmp_path,
        now=500,
        host_snapshot=HostSnapshot(True, launch_time=100),
    )
    assert status["active"] is True
    assert status["task_id"] == "valid"


def test_rollout_cache_updates_incrementally_after_append(tmp_path: Path) -> None:
    clear_session_cache()
    session = tmp_path / "rollout-cache.jsonl"
    _write_rollout(
        session,
        {"type": "task_started", "started_at": 110, "task_id": "cache"},
    )
    host = HostSnapshot(True, launch_time=100)
    first = get_codex_status(tmp_path, now=200, host_snapshot=host)
    assert first["active"] is True
    with session.open("a", encoding="utf-8") as file:
        file.write(
            "\n"
            + json.dumps(
                {
                    "payload": {
                        "type": "task_complete",
                        "completed_at": 150,
                        "task_id": "cache",
                    }
                }
            )
        )
    second = get_codex_status(tmp_path, now=200, host_snapshot=host)
    assert second["active"] is False
    assert second["state"] == "waiting"


def test_rollout_cache_avoids_repeated_full_parse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clear_session_cache()
    session = tmp_path / "rollout-cache-incremental.jsonl"
    session.write_text(
        json.dumps(
            {
                "payload": {
                    "type": "task_started",
                    "started_at": 110,
                    "task_id": "cache",
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    full_parses = 0
    original = sessions_module._full_cache_entry

    def counted(*args: object, **kwargs: object):
        nonlocal full_parses
        full_parses += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(sessions_module, "_full_cache_entry", counted)
    host = HostSnapshot(True, launch_time=100)
    get_codex_status(tmp_path, now=200, host_snapshot=host)
    get_codex_status(tmp_path, now=201, host_snapshot=host)
    assert full_parses == 1

    with session.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                {
                    "payload": {
                        "type": "task_complete",
                        "completed_at": 150,
                        "task_id": "cache",
                    }
                }
            )
            + "\n"
        )
    status = get_codex_status(tmp_path, now=201, host_snapshot=host)
    assert status["state"] == "waiting"
    assert full_parses == 1


def test_long_rollout_keeps_start_before_tail_window(tmp_path: Path) -> None:
    session = tmp_path / "rollout-long.jsonl"
    lines = [
        json.dumps(
            {
                "payload": {
                    "type": "task_started",
                    "started_at": 110,
                    "task_id": "long",
                }
            }
        )
    ]
    lines.extend(
        json.dumps(
            {
                "payload": {
                    "type": "token_count",
                    "info": {"total_token_usage": {"total_tokens": index}},
                }
            }
        )
        for index in range(6_000)
    )
    session.write_text("\n".join(lines), encoding="utf-8")
    status = get_codex_status(
        tmp_path,
        now=100_000,
        host_snapshot=HostSnapshot(True, launch_time=100),
    )
    assert status["active"] is True
    assert status["task_id"] == "long"
    assert status["tokens"] == 5_999


def test_host_snapshot_uses_os_start_fallback_and_codex_bundle_precedence() -> None:
    snapshot = snapshot_from_applications(
        [
            {
                "pid": 7,
                "bundle_id": "com.openai.codex",
                "name": "Codex",
                "launch_time": None,
            },
            {
                "pid": 8,
                "bundle_id": None,
                "name": "ChatGPT",
                "launch_time": 50,
            },
        ],
        monitor_started_at=10,
        process_start_provider=lambda pid: 100 + pid,
    )
    assert snapshot.running is True
    assert snapshot.pids == (7,)
    assert snapshot.cutoff == 107


def test_host_snapshot_falls_back_to_monitor_start() -> None:
    snapshot = snapshot_from_applications(
        [{"pid": 7, "bundle_id": "com.openai.codex", "name": "Codex"}],
        monitor_started_at=123,
        process_start_provider=lambda pid: None,
    )
    assert snapshot.running is True
    assert snapshot.cutoff == 123


def test_generic_chatgpt_process_alone_is_not_a_codex_host() -> None:
    snapshot = snapshot_from_applications(
        [{"pid": 8, "bundle_id": None, "name": "ChatGPT", "launch_time": 50}],
        monitor_started_at=123,
    )
    assert snapshot.running is False
    assert snapshot.cutoff == 123
