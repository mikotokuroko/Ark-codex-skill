"""Windows desktop integration, imported only on Windows."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ArkCodexDeskpetWatcher"


def running_applications():
    import psutil
    applications = []
    for process in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            name = (process.info["name"] or "").lower()
            if name in {"codex.exe", "chatgpt.exe"}:
                applications.append({"pid": process.pid, "name": name[:-4],
                                     "bundle_id": "com.openai.codex" if name == "codex.exe" else "com.openai.chatgpt",
                                     "launch_time": process.info["create_time"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return applications


def startup_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_NAME)
        return bool(value)
    except FileNotFoundError:
        return False


def application_command(executable: Path | None = None) -> list[str]:
    executable = executable or Path(sys.executable)
    if getattr(sys, "frozen", False):
        return [str(executable)]
    return [str(executable), str(Path(__file__).resolve().parents[1] / "main.py")]


def set_startup(executable: Path | None) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if executable is None:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass
        else:
            command = subprocess.list2cmdline([*application_command(executable), "--watch"])
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, command)
    if executable is not None:
        subprocess.Popen([*application_command(executable), "--watch"], creationflags=subprocess.CREATE_NO_WINDOW)


def _user32():
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    api.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    api.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    api.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    api.GetForegroundWindow.restype = wintypes.HWND
    api.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    api.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    api.MonitorFromWindow.restype = wintypes.HANDLE
    api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    api.IsIconic.argtypes = [wintypes.HWND]
    api.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    return api


def set_click_through(hwnd: int, enabled: bool) -> None:
    api = _user32()
    style = api.GetWindowLongPtrW(hwnd, -20)
    # Layered windows with WS_EX_TRANSPARENT pass input to windows underneath.
    style = (style | 0x80000 | 0x20) if enabled else (style & ~0x20)
    ctypes.set_last_error(0)
    result = api.SetWindowLongPtrW(hwnd, -20, style)
    if not result and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())


def is_fullscreen(pet_hwnd: int) -> bool | None:
    api = _user32()
    front = api.GetForegroundWindow()
    if not front:
        return None
    pid = wintypes.DWORD()
    api.GetWindowThreadProcessId(front, ctypes.byref(pid))
    if pid.value == os.getpid() or api.IsIconic(front):
        return False
    name = ctypes.create_unicode_buffer(256)
    api.GetClassNameW(front, name, 256)
    if name.value in {"Progman", "WorkerW", "Shell_TrayWnd"}:
        return False
    monitor = api.MonitorFromWindow(pet_hwnd, 2)
    if api.MonitorFromWindow(front, 2) != monitor:
        return False

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                    ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

    info = MonitorInfo(); info.size = ctypes.sizeof(info)
    rect = wintypes.RECT()
    if not api.GetMonitorInfoW(monitor, ctypes.byref(info)) or not api.GetWindowRect(front, ctypes.byref(rect)):
        return None
    screen = info.monitor
    return (rect.left <= screen.left + 2 and rect.top <= screen.top + 2
            and rect.right >= screen.right - 2 and rect.bottom >= screen.bottom - 2)


def run_watcher() -> int:
    """Watch host lifecycle in a separate process without blocking animation."""
    from PySide6.QtCore import QCoreApplication, QTimer
    from .ipc import CommandServer, send_command
    from .lifecycle import WatcherLifecycle, WatcherAction, matching_hosts
    from .paths import ensure_directories, instance_path, ipc_socket_path, cache_dir, watcher_state_path
    from .storage import read_json, pid_is_alive, atomic_write_json

    ensure_directories()
    app = QCoreApplication(sys.argv)
    server = CommandServer(cache_dir() / "watcher.socket")
    if not server.listen():
        return 0
    lifecycle = WatcherLifecycle.from_dict(read_json(watcher_state_path()))

    def reconcile():
        if not startup_enabled():
            app.quit()
            return
        record = read_json(instance_path()) or {}
        action = lifecycle.reconcile(bool(matching_hosts(running_applications())),
                                     pid_is_alive(record.get("pid")), record.get("mode"), record.get("pid"))
        if action == WatcherAction.LAUNCH:
            process = subprocess.Popen([*application_command(), "--watcher-managed"], creationflags=subprocess.CREATE_NO_WINDOW)
            lifecycle.note_launched(process.pid)
        elif action == WatcherAction.SHUTDOWN:
            send_command(ipc_socket_path(), "shutdown")
        atomic_write_json(watcher_state_path(), lifecycle.to_dict())

    timer = QTimer(); timer.setInterval(2000); timer.timeout.connect(reconcile)
    timer.start(); QTimer.singleShot(0, reconcile)
    try:
        return app.exec()
    finally:
        server.close()
