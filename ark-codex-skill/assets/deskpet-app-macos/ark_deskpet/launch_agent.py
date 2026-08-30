"""Install and remove the watcher user LaunchAgent."""

from __future__ import annotations

import os
from pathlib import Path
import plistlib
import subprocess
from typing import Any

from .constants import WATCHER_ID
from .paths import launch_agent_path, log_dir


class LaunchAgentError(RuntimeError):
    """Raised when launchd rejects a watcher configuration change."""


def launch_agent_enabled(home: Path | None = None) -> bool:
    """Returns whether the watcher LaunchAgent file is installed."""
    return launch_agent_path(home).is_file()


def _run_launchctl(arguments: list[str], check: bool = True) -> None:
    """Runs launchctl without requesting administrator privileges."""
    result = subprocess.run(
        ["/bin/launchctl", *arguments],
        capture_output=True,
        check=False,
        text=True,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise LaunchAgentError(detail or "launchctl 命令失败")


def launch_agent_definition(
    watcher_executable: Path, home: Path | None = None
) -> dict[str, Any]:
    """Builds the property list used for login-time host watching."""
    logs = log_dir(home)
    return {
        "Label": WATCHER_ID,
        "ProgramArguments": [str(watcher_executable)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "watcher.log"),
        "StandardErrorPath": str(logs / "watcher-error.log"),
    }


def enable_launch_agent(
    watcher_executable: Path, home: Path | None = None
) -> None:
    """Atomically installs and bootstraps the user watcher LaunchAgent."""
    target = launch_agent_path(home)
    target.parent.mkdir(parents=True, exist_ok=True)
    log_dir(home).mkdir(parents=True, exist_ok=True)
    definition = launch_agent_definition(watcher_executable, home)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as file:
        plistlib.dump(definition, file, sort_keys=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, target)
    domain = f"gui/{os.getuid()}"
    _run_launchctl(["bootout", domain, str(target)], check=False)
    try:
        _run_launchctl(["bootstrap", domain, str(target)])
    except LaunchAgentError:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        raise


def disable_launch_agent(home: Path | None = None) -> None:
    """Boots out and removes only this app's user LaunchAgent."""
    target = launch_agent_path(home)
    domain = f"gui/{os.getuid()}"
    _run_launchctl(["bootout", domain, str(target)], check=False)
    try:
        target.unlink()
    except FileNotFoundError:
        pass
