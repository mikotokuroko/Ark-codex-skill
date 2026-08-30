"""Single-instance QLocalServer command channel."""

from __future__ import annotations

import logging
from pathlib import Path
import socket
from typing import Callable

from PySide6.QtCore import QIODevice, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .constants import IPC_COMMANDS


def send_command(
    socket_path: Path, command: str, timeout_ms: int = 1500
) -> bool:
    """Sends one supported command to a running Qt local server."""
    if command not in IPC_COMMANDS:
        raise ValueError(f"unsupported IPC command: {command}")
    client = QLocalSocket()
    client.connectToServer(str(socket_path), QIODevice.WriteOnly)
    if not client.waitForConnected(timeout_ms):
        return False
    client.write((command + "\n").encode("utf-8"))
    client.flush()
    client.waitForBytesWritten(timeout_ms)
    client.disconnectFromServer()
    return True


def send_command_stdlib(socket_path: Path, command: str) -> bool:
    """Sends a command without importing Qt, for the watcher helper."""
    if command not in IPC_COMMANDS:
        raise ValueError(f"unsupported IPC command: {command}")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.5)
            client.connect(str(socket_path))
            client.sendall((command + "\n").encode("utf-8"))
    except OSError:
        return False
    return True


class CommandServer(QObject):
    """Accepts newline-delimited commands from one QLocalServer."""

    command_received = Signal(str)

    def __init__(
        self,
        socket_path: Path,
        handler: Callable[[str], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._socket_path = socket_path
        self._logger = logging.getLogger(__name__)
        self._clients: set[QLocalSocket] = set()
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept_connections)
        if handler is not None:
            self.command_received.connect(handler)

    def listen(self) -> bool:
        """Starts listening, removing only a stale runtime socket if needed."""
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self._server.listen(str(self._socket_path)):
            return True
        probe = QLocalSocket()
        probe.connectToServer(str(self._socket_path), QIODevice.WriteOnly)
        if probe.waitForConnected(250):
            probe.disconnectFromServer()
            return False
        QLocalServer.removeServer(str(self._socket_path))
        return self._server.listen(str(self._socket_path))

    def close(self) -> None:
        """Closes the server and removes its runtime socket."""
        for client in tuple(self._clients):
            try:
                client.readyRead.disconnect()
                client.disconnected.disconnect()
            except RuntimeError:
                pass
            client.abort()
            client.deleteLater()
        self._clients.clear()
        self._server.close()
        QLocalServer.removeServer(str(self._socket_path))

    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is None:
                continue
            self._clients.add(client)
            client.readyRead.connect(lambda client=client: self._read(client))
            client.disconnected.connect(
                lambda client=client: self._drop(client)
            )

    def _read(self, client: QLocalSocket) -> None:
        data = bytes(client.readAll()).decode("utf-8", errors="replace")
        for raw_command in data.splitlines():
            command = raw_command.strip()
            if command in IPC_COMMANDS:
                self.command_received.emit(command)
            elif command:
                self._logger.warning("忽略未知 IPC 命令：%s", command)

    def _drop(self, client: QLocalSocket) -> None:
        self._clients.discard(client)
        client.deleteLater()
