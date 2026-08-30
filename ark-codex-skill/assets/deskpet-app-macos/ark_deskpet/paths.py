"""Resolve read-only resources and writable macOS application paths."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from .constants import APP_NAME, IPC_SERVER_NAME, WATCHER_ID


def resource_root() -> Path:
    """Returns the read-only root containing bundled resources."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def bundled_pets_dir() -> Path:
    """Returns the bundled, read-only pet directory."""
    return resource_root() / "pets"


def application_support_dir(home: Path | None = None) -> Path:
    """Returns the directory containing settings and user pets."""
    base = home if home is not None else Path.home()
    return base / "Library" / "Application Support" / APP_NAME


def cache_dir(home: Path | None = None) -> Path:
    """Returns the directory containing runtime state and sockets."""
    base = home if home is not None else Path.home()
    return base / "Library" / "Caches" / APP_NAME


def log_dir(home: Path | None = None) -> Path:
    """Returns the application log directory."""
    base = home if home is not None else Path.home()
    return base / "Library" / "Logs" / APP_NAME


def user_pets_dir(home: Path | None = None) -> Path:
    """Returns the writable pet library directory."""
    return application_support_dir(home) / "Pets"


def settings_path(home: Path | None = None) -> Path:
    """Returns the settings JSON path."""
    return application_support_dir(home) / "settings.json"


def ipc_socket_path(home: Path | None = None) -> Path:
    """Returns the QLocalServer Unix-domain socket path."""
    return cache_dir(home) / f"{IPC_SERVER_NAME}.socket"


def instance_path(home: Path | None = None) -> Path:
    """Returns the current app-instance record path."""
    return cache_dir(home) / "instance.json"


def watcher_state_path(home: Path | None = None) -> Path:
    """Returns the watcher lifecycle state path."""
    return cache_dir(home) / "watcher-state.json"


def launch_agent_path(home: Path | None = None) -> Path:
    """Returns the user LaunchAgent property-list path."""
    base = home if home is not None else Path.home()
    return base / "Library" / "LaunchAgents" / f"{WATCHER_ID}.plist"


def ensure_directories(home: Path | None = None) -> None:
    """Creates all writable application directories."""
    for path in (
        application_support_dir(home),
        user_pets_dir(home),
        cache_dir(home),
        log_dir(home),
    ):
        path.mkdir(parents=True, exist_ok=True)


def app_bundle_path() -> Path:
    """Returns the enclosing app bundle, or a development approximation."""
    executable = Path(sys.executable).resolve()
    for parent in (executable, *executable.parents):
        if parent.suffix == ".app":
            return parent
    configured = os.environ.get("ARK_CODEX_APP_BUNDLE")
    if configured:
        return Path(configured)
    return resource_root()
