"""Event-driven ChatGPT/Codex host watcher for macOS."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

from .lifecycle import (
    WatcherAction,
    WatcherLifecycle,
    matching_hosts,
)
from .paths import (
    ensure_directories,
    instance_path,
    ipc_socket_path,
    log_dir,
    watcher_state_path,
)
from .storage import atomic_write_json, pid_is_alive, read_json


def configure_logging() -> None:
    """Configures the watcher log in the user's Library directory."""
    destination = log_dir() / "watcher.log"
    destination.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        destination, maxBytes=500_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def running_applications() -> list[dict[str, Any]]:
    """Returns visible NSWorkspace application identity metadata."""
    import AppKit

    applications = []
    for application in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        applications.append(
            {
                "pid": int(application.processIdentifier()),
                "bundle_id": application.bundleIdentifier(),
                "name": application.localizedName(),
            }
        )
    return applications


def _send_command(command: str) -> bool:
    """Sends one command directly to the QLocalServer Unix socket."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2.0)
            client.connect(str(ipc_socket_path()))
            client.sendall((command + "\n").encode("utf-8"))
    except OSError:
        return False
    return True


def _main_executable() -> Path:
    """Returns the main GUI executable beside the frozen helper."""
    executable = Path(sys.executable).resolve()
    if executable.parent.name == "Helpers":
        bundle = executable.parents[2]
        return bundle / "Contents" / "MacOS" / "Ark Codex Deskpet"
    configured = os.environ.get("ARK_CODEX_MAIN_EXECUTABLE")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "main.py"


class WatcherController:
    """Reconciles NSWorkspace events with persisted ownership state."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.lifecycle = WatcherLifecycle.from_dict(
            read_json(watcher_state_path())
        )

    def _pet_observation(self) -> tuple[bool, str | None, int | None]:
        record = read_json(instance_path())
        if record is None:
            return False, None, None
        pid = record.get("pid")
        if not pid_is_alive(pid):
            return False, None, None
        mode = record.get("mode")
        return True, mode if isinstance(mode, str) else None, pid

    def reconcile(self) -> None:
        """Handles a launch/termination event without process polling."""
        hosts = matching_hosts(running_applications())
        pet_running, pet_mode, pet_pid = self._pet_observation()
        action = self.lifecycle.reconcile(
            bool(hosts), pet_running, pet_mode, pet_pid
        )
        if action == WatcherAction.LAUNCH:
            executable = _main_executable()
            try:
                process = subprocess.Popen(
                    [str(executable), "--watcher-managed"],
                    cwd=str(executable.parent),
                    close_fds=True,
                    start_new_session=True,
                )
            except OSError:
                self.logger.exception("无法启动 watcher 管理的桌宠")
            else:
                self.lifecycle.note_launched(process.pid)
                self.logger.info("已启动 watcher 管理的桌宠 pid=%s", process.pid)
        elif action == WatcherAction.SHUTDOWN:
            if _send_command("shutdown"):
                self.logger.info("全部主程序已退出，已关闭 watcher 管理的桌宠")
            else:
                self.logger.warning("桌宠命令通道不可用，未强制终止进程")
        atomic_write_json(watcher_state_path(), self.lifecycle.to_dict())


def _make_workspace_observer(controller: WatcherController) -> object:
    """Creates an Objective-C observer retained for the event-loop lifetime."""
    import AppKit
    import objc

    class WorkspaceObserver(AppKit.NSObject):
        def initWithController_(self, value: WatcherController) -> object:
            self = objc.super(WorkspaceObserver, self).init()
            if self is not None:
                self.controller = value
            return self

        def applicationChanged_(self, notification: object) -> None:
            del notification
            self.controller.reconcile()

    return WorkspaceObserver.alloc().initWithController_(controller)


def run(probe_only: bool = False, list_only: bool = False) -> int:
    """Runs the NSWorkspace notification watcher or prints one host probe."""
    ensure_directories()
    if probe_only or list_only:
        applications = running_applications()
        hosts = [
            application
            for application in applications
            if application["pid"] in matching_hosts([application])
        ]
        print(
            json.dumps(
                applications if list_only else hosts,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if hosts else 1
    configure_logging()
    import AppKit

    controller = WatcherController()
    observer = _make_workspace_observer(controller)
    center = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
    center.addObserver_selector_name_object_(
        observer,
        "applicationChanged:",
        AppKit.NSWorkspaceDidLaunchApplicationNotification,
        None,
    )
    center.addObserver_selector_name_object_(
        observer,
        "applicationChanged:",
        AppKit.NSWorkspaceDidTerminateApplicationNotification,
        None,
    )
    controller.reconcile()
    try:
        AppKit.NSRunLoop.currentRunLoop().run()
    finally:
        center.removeObserver_(observer)
    return 0
