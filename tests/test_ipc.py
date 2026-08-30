"""QLocalServer commands and single-instance tests."""

from pathlib import Path
import tempfile
import time

from PySide6.QtCore import QCoreApplication, QIODevice
from PySide6.QtNetwork import QLocalSocket

from ark_deskpet.ipc import CommandServer


def short_socket_path() -> Path:
    """Returns a Unix socket path below macOS's sockaddr_un limit."""
    return Path(tempfile.mkdtemp(prefix="ark-ipc-", dir="/tmp")) / "socket"


def process_until(predicate, timeout: float = 1.0) -> None:
    """Processes core Qt events until a condition becomes true."""
    app = QCoreApplication.instance() or QCoreApplication([])
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


def test_ipc_command_and_single_instance() -> None:
    QCoreApplication.instance() or QCoreApplication([])
    socket_path = short_socket_path()
    received = []
    server = CommandServer(socket_path, received.append)
    assert server.listen(), server._server.errorString()
    second = CommandServer(socket_path)
    assert not second.listen()

    client = QLocalSocket()
    client.connectToServer(str(socket_path), QIODevice.WriteOnly)
    assert client.waitForConnected(1000)
    client.write(b"show\nrefresh-library\n")
    client.flush()
    process_until(lambda: received == ["show", "refresh-library"])
    client.abort()
    second.close()
    server.close()


def test_stale_socket_is_recovered() -> None:
    QCoreApplication.instance() or QCoreApplication([])
    socket_path = short_socket_path()
    socket_path.write_text("stale", encoding="utf-8")
    server = CommandServer(socket_path)
    assert server.listen(), server._server.errorString()
    server.close()
