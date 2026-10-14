"""Share asynchronous Codex status scans across all pet windows."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot


class _StatusReader(QThread):
    ready = Signal(dict)

    def __init__(self, read: Callable[[], dict[str, Any]], parent: QObject):
        super().__init__(parent)
        self.read = read

    def run(self) -> None:
        try:
            self.ready.emit(self.read())
        except Exception:
            logging.getLogger(__name__).exception("Unable to refresh Codex status")


class StatusMonitor(QObject):
    """Keep disk/process inspection off the GUI thread; never overlap scans."""

    updated = Signal()

    def __init__(self, read: Callable[[], dict[str, Any]], parent: QObject):
        super().__init__(parent)
        self.snapshot: dict[str, Any] = {"state": "idle"}
        self._closed = False
        self._reader = _StatusReader(read, self)
        self._reader.ready.connect(self._received)
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.poll)

    def start(self) -> None:
        self._timer.start()
        self.poll()

    @Slot()
    def poll(self) -> None:
        if not self._closed and not self._reader.isRunning():
            self._reader.start()

    @Slot(dict)
    def _received(self, status: dict[str, Any]) -> None:
        if not self._closed:
            self.snapshot = status
            self.updated.emit()

    @Slot()
    def close(self) -> None:
        self._closed = True
        self._timer.stop()
        self._reader.wait()
