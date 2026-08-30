"""Host matching and watcher ownership state transitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable

HOST_BUNDLE_IDS = frozenset({"com.openai.codex"})
HOST_NAMES = frozenset({"chatgpt", "codex"})


def is_matching_host(bundle_id: str | None, name: str | None) -> bool:
    """Matches supported host applications by identifier or fallback name."""
    normalized_id = (bundle_id or "").casefold()
    normalized_name = (name or "").removesuffix(".app").casefold()
    return normalized_id in HOST_BUNDLE_IDS or normalized_name in HOST_NAMES


def matching_hosts(applications: Iterable[dict[str, Any]]) -> set[int]:
    """Returns process identifiers for matching running applications."""
    result = set()
    for application in applications:
        pid = application.get("pid")
        if isinstance(pid, int) and is_matching_host(
            application.get("bundle_id"), application.get("name")
        ):
            result.add(pid)
    return result


class WatcherAction(str, Enum):
    """Actions requested by a watcher reconciliation."""

    NONE = "none"
    LAUNCH = "launch"
    SHUTDOWN = "shutdown"


@dataclass
class WatcherLifecycle:
    """Tracks host sessions and whether the watcher owns the pet process."""

    host_session_active: bool = False
    owns_pet: bool = False
    owned_pid: int | None = None
    suppressed: bool = False
    manual_seen: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "WatcherLifecycle":
        """Restores persisted lifecycle state with conservative defaults."""
        if not isinstance(value, dict):
            return cls()
        return cls(
            host_session_active=bool(value.get("host_session_active")),
            owns_pet=bool(value.get("owns_pet")),
            owned_pid=(
                value["owned_pid"]
                if isinstance(value.get("owned_pid"), int)
                else None
            ),
            suppressed=bool(value.get("suppressed")),
            manual_seen=bool(value.get("manual_seen")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Returns a JSON-serializable lifecycle snapshot."""
        return asdict(self)

    def reconcile(
        self,
        hosts_running: bool,
        pet_running: bool,
        pet_mode: str | None,
        pet_pid: int | None,
    ) -> WatcherAction:
        """Reconciles observed processes and returns the required action."""
        if hosts_running and not self.host_session_active:
            self.host_session_active = True
            self.suppressed = False
            self.manual_seen = False
            self.owns_pet = pet_running and pet_mode == "watcher"
            self.owned_pid = pet_pid if self.owns_pet else None
            if pet_running and not self.owns_pet:
                self.manual_seen = True
                return WatcherAction.NONE
            if not pet_running:
                return WatcherAction.LAUNCH
        elif not hosts_running and self.host_session_active:
            self.host_session_active = False
            self.manual_seen = False
            if self.owns_pet and pet_running:
                self.owns_pet = False
                self.owned_pid = None
                return WatcherAction.SHUTDOWN
            self.owns_pet = False
            self.owned_pid = None
            return WatcherAction.NONE

        if not hosts_running:
            self.owns_pet = False
            self.owned_pid = None
            return WatcherAction.NONE
        if pet_running:
            if pet_mode == "watcher" and self.owns_pet:
                self.owned_pid = pet_pid
            elif pet_mode != "watcher":
                self.manual_seen = True
                self.owns_pet = False
                self.owned_pid = None
            return WatcherAction.NONE
        if self.owns_pet:
            self.owns_pet = False
            self.owned_pid = None
            self.suppressed = True
            return WatcherAction.NONE
        if self.manual_seen or self.suppressed:
            return WatcherAction.NONE
        return WatcherAction.LAUNCH

    def note_launched(self, pid: int | None = None) -> None:
        """Marks a newly launched pet as watcher-owned."""
        self.owns_pet = True
        self.owned_pid = pid
