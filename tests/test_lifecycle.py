"""Host matching and watcher ownership lifecycle tests."""

from ark_deskpet.lifecycle import (
    WatcherAction,
    WatcherLifecycle,
    is_matching_host,
    matching_hosts,
)


def test_host_identifier_and_name_fallbacks() -> None:
    assert is_matching_host("com.openai.codex", "Anything")
    assert is_matching_host(None, "ChatGPT")
    assert is_matching_host(None, "Codex.app")
    assert not is_matching_host("com.example.editor", "Editor")
    assert matching_hosts(
        [
            {"pid": 7, "bundle_id": "com.openai.codex", "name": "Codex"},
            {"pid": 8, "bundle_id": "com.example", "name": "Other"},
        ]
    ) == {7}


def test_watcher_managed_pet_shuts_down_with_last_host() -> None:
    state = WatcherLifecycle()
    assert state.reconcile(True, False, None, None) == WatcherAction.LAUNCH
    state.note_launched(50)
    assert state.reconcile(True, True, "watcher", 50) == WatcherAction.NONE
    assert state.reconcile(False, True, "watcher", 50) == WatcherAction.SHUTDOWN


def test_manual_pet_is_independent() -> None:
    state = WatcherLifecycle()
    assert state.reconcile(True, True, "manual", 60) == WatcherAction.NONE
    assert state.manual_seen and not state.owns_pet
    assert state.reconcile(False, True, "manual", 60) == WatcherAction.NONE


def test_managed_quit_suppresses_relaunch_until_new_session() -> None:
    state = WatcherLifecycle()
    assert state.reconcile(True, False, None, None) == WatcherAction.LAUNCH
    state.note_launched(70)
    assert state.reconcile(True, False, None, None) == WatcherAction.NONE
    assert state.suppressed
    assert state.reconcile(True, False, None, None) == WatcherAction.NONE
    assert state.reconcile(False, False, None, None) == WatcherAction.NONE
    assert state.suppressed
    assert state.reconcile(True, False, None, None) == WatcherAction.LAUNCH
    assert not state.suppressed


def test_manual_quit_does_not_create_watcher_owned_pet() -> None:
    state = WatcherLifecycle()
    state.reconcile(True, True, "manual", 80)
    assert state.reconcile(True, False, None, None) == WatcherAction.NONE
    assert not state.owns_pet
