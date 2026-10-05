"""User-facing speech and sound effects for the native desk pet.

The module deliberately owns no application policy or menu wiring.  Controllers can
opt into these effects while keeping the default quiet behaviour intact.
"""

from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
import re
import struct
import uuid
import urllib.parse
import urllib.request
import wave
from typing import Callable, Iterable

from PySide6.QtCore import QObject, QPoint, QEvent, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

try:  # QtMultimedia is optional in headless/test environments.
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - depends on the installed Qt bundle
    QSoundEffect = None  # type: ignore[assignment,misc]


DEFAULT_DIALOGUE = (
    "博士，工作辛苦了",
    "别忘了喝水",
    "今天也要加油哦",
    "有点困了……",
    "要休息一下吗？",
)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _doctor_line(line: str, doctor_name: str = "博士") -> str:
    """Replace common PRTS doctor placeholders without exposing wiki markup."""
    cleaned = re.sub(r"\{\{DrName[^}]*\}\}", doctor_name, line)
    cleaned = re.sub(r"\{\{DrName[^}]*$", doctor_name, cleaned)
    cleaned = cleaned.replace("{博士}", doctor_name)
    return re.sub(r"\s+", " ", cleaned).strip()


class DialogueProvider:
    """Read local dialogue and optionally cache lines fetched from PRTS.

    Network access is opt-in.  A failed request leaves cached or default lines
    available, so dialogue remains useful while offline.
    """

    def __init__(
        self,
        cache_dir: Path,
        fetcher: Callable[[str], Iterable[str]] | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.fetcher = fetcher or self._fetch_prts
        self._threads: set[QThread] = set()

    def _cache_path(self, operator_name: str) -> Path:
        label = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in operator_name).strip("._") or "operator"
        digest = hashlib.sha256(operator_name.encode("utf-8")).hexdigest()[:12]
        safe = f"{label[:48]}-{digest}"
        return self.cache_dir / "dialogue" / f"{safe}.json"

    @staticmethod
    def _operator_candidates(operator_name: str) -> tuple[str, ...]:
        base = operator_name.split("-", 1)[0].strip()
        return (operator_name, base) if base and base != operator_name else (operator_name,)

    def _read_cache(self, operator_name: str) -> list[str]:
        try:
            raw = json.loads(self._cache_path(operator_name).read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            return [item.strip() for item in raw if isinstance(item, str) and item.strip()]
        except (OSError, ValueError, TypeError):
            return []

    def _write_cache(self, operator_name: str, lines: Iterable[str]) -> list[str]:
        values = [item.strip() for item in lines if isinstance(item, str) and item.strip()]
        if not values:
            return []
        path = self._cache_path(operator_name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            temporary.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
            temporary.unlink(missing_ok=True)
        except OSError:
            # A read-only cache must never prevent dialogue from being shown.
            pass
        return values

    @staticmethod
    def _fetch_prts(operator_name: str) -> list[str]:
        page = urllib.parse.quote(f"{operator_name}/语音记录")
        url = f"https://prts.wiki/api.php?action=parse&page={page}&prop=wikitext&format=json"
        with urllib.request.urlopen(url, timeout=6) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw.get("parse", {}).get("wikitext", {}).get("*", "")
        return [match.strip() for match in re.findall(r"VoiceData/word\|中文\|(.*?)\}\}", text) if match.strip()]

    def _read_pet_lines(self, pet_dir: Path | None, operator_name: str) -> list[str]:
        if pet_dir is None:
            return []
        candidates = [Path(pet_dir) / "dialogue.json"]
        candidates.extend(Path(pet_dir) / "dialogue" / f"{name}.json" for name in self._operator_candidates(operator_name))
        for path in candidates:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    raw = raw.get("lines", [])
                if not isinstance(raw, list):
                    continue
                values = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
                if values:
                    return values
            except (OSError, ValueError, TypeError):
                continue
        return []

    def lines(
        self,
        operator_name: str = "default",
        doctor_name: str = "博士",
        pet_dir: Path | None = None,
        live: bool = False,
    ) -> list[str]:
        local = self._read_pet_lines(pet_dir, operator_name)
        cached = []
        for candidate in self._operator_candidates(operator_name):
            cached = self._read_cache(candidate)
            if cached:
                break
        if live:
            try:
                fetched = self._write_cache(operator_name, self.fetcher(operator_name))
                if not fetched and len(self._operator_candidates(operator_name)) > 1:
                    base = self._operator_candidates(operator_name)[1]
                    fetched = self._write_cache(base, self.fetcher(base))
                if fetched:
                    cached = fetched
            except Exception:
                pass
        return [_doctor_line(line, doctor_name) for line in (local or cached or DEFAULT_DIALOGUE)]

    def refresh_async(
        self,
        operator_name: str,
        doctor_name: str = "博士",
        callback: Callable[[list[str]], None] | None = None,
    ) -> "DialogueRefreshThread":
        """Fetch dialogue without blocking the GUI thread; cached lines remain usable."""
        worker = DialogueRefreshThread(self, operator_name, doctor_name)
        if callback is not None:
            worker.ready.connect(callback)
        self._threads.add(worker)
        worker.finished.connect(lambda: self._threads.discard(worker))
        worker.start()
        return worker

    def close(self, timeout_ms: int = 1500) -> None:
        """Stop refresh workers before their provider/controller is discarded."""
        workers = tuple(self._threads)
        for worker in workers:
            worker.requestInterruption()
        for worker in workers:
            worker.wait(max(0, int(timeout_ms)))
        self._threads.clear()


class DialogueRefreshThread(QThread):
    ready = Signal(list)
    failed = Signal(str)

    def __init__(self, provider: DialogueProvider, operator_name: str, doctor_name: str) -> None:
        super().__init__()
        self.provider = provider
        self.operator_name = operator_name
        self.doctor_name = doctor_name

    def run(self) -> None:
        try:
            if self.isInterruptionRequested():
                return
            values = self.provider._write_cache(self.operator_name, self.provider.fetcher(self.operator_name))
            if not values and len(self.provider._operator_candidates(self.operator_name)) > 1:
                base = self.provider._operator_candidates(self.operator_name)[1]
                values = self.provider._write_cache(base, self.provider.fetcher(base))
            if values and not self.isInterruptionRequested():
                self.ready.emit([_doctor_line(line, self.doctor_name) for line in values])
        except Exception as exc:  # network and cache errors are non-fatal
            self.failed.emit(str(exc))


class SpeechBubble(QWidget):
    """A translucent, independent bubble that follows a pet widget."""

    def __init__(self, anchor: QWidget | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._anchor: QWidget | None = None
        self._text = ""
        self._font = QFont(".AppleSystemUIFont", 12)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.set_anchor(anchor)

    def set_anchor(self, anchor: QWidget | None) -> None:
        if self._anchor is anchor:
            return
        if self._anchor is not None:
            self._anchor.removeEventFilter(self)
        self._anchor = anchor
        if anchor is not None:
            anchor.installEventFilter(self)
            self._reposition()

    def show_text(self, text: str, duration_ms: int = 3500) -> None:
        self._text = str(text).strip()
        if not self._text or self._anchor is None or not self._anchor.isVisible():
            self.hide()
            return
        metrics = QFontMetrics(self._font)
        screen = self._anchor.screen() if self._anchor is not None else None
        max_width = max(120, min(340, screen.availableGeometry().width() - 24)) if screen else 340
        width = min(max_width, max(90, metrics.horizontalAdvance(self._text) + 30))
        flags = int(Qt.TextWordWrap | Qt.AlignCenter)
        height = metrics.boundingRect(0, 0, width - 24, 1000, flags, self._text).height() + 24
        self.setFixedSize(width, max(44, min(180, height)))
        self._reposition()
        self.show()
        self.raise_()
        self.update()
        self._timer.start(max(250, int(duration_ms)))

    def _reposition(self) -> None:
        if self._anchor is None or not self._anchor.isVisible():
            return
        top_left = self._anchor.mapToGlobal(QPoint(0, 0))
        x = top_left.x() + (self._anchor.width() - self.width()) // 2
        y = top_left.y() - self.height() - 8
        screen = self._anchor.screen()
        if screen is not None:
            bounds = screen.availableGeometry().adjusted(8, 8, -8, -8)
            x = max(bounds.left(), min(x, bounds.right() - self.width() + 1))
            if y < bounds.top():
                y = top_left.y() + self._anchor.height() + 8
            y = min(y, bounds.bottom() - self.height() + 1)
        self.move(x, y)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        anchor = getattr(self, "_anchor", None)
        if watched is anchor and event.type() in {QEvent.Move, QEvent.Resize, QEvent.Show}:
            self._reposition()
        elif watched is anchor and event.type() in {QEvent.Hide, QEvent.Close, QEvent.Destroy}:
            self.hide()
        return super().eventFilter(watched, event)

    def paintEvent(self, event: object) -> None:  # noqa: ARG002 - Qt signature
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        body = self.rect().adjusted(0, 0, 0, -8)
        painter.setBrush(QColor(30, 30, 30, 225))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(body, 9, 9)
        painter.drawPolygon([QPoint(self.width() // 2 - 7, self.height() - 8), QPoint(self.width() // 2 + 7, self.height() - 8), QPoint(self.width() // 2, self.height())])
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(self._font)
        painter.drawText(body.adjusted(10, 5, -10, -5), Qt.AlignCenter | Qt.TextWordWrap, self._text)
        painter.end()

    def closeEvent(self, event: object) -> None:  # noqa: ARG002 - Qt signature
        self._timer.stop()
        self.set_anchor(None)
        event.accept()


class SpeechBubbleController(QObject):
    """Lifecycle-safe facade for speech bubbles used by a pet controller."""

    visibilityChanged = Signal(bool)

    def __init__(self, anchor: QWidget | None = None, enabled: bool = False) -> None:
        super().__init__(anchor)
        self.enabled = bool(enabled)
        self.bubble = SpeechBubble(anchor)
        if anchor is not None:
            anchor.destroyed.connect(lambda *_args: self.close())

    def show(self, text: str, duration_ms: int = 3500) -> bool:
        if not self.enabled:
            return False
        self.bubble.show_text(text, duration_ms)
        visible = self.bubble.isVisible()
        self.visibilityChanged.emit(visible)
        return visible

    def hide(self) -> None:
        self.bubble.hide()
        self.visibilityChanged.emit(False)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.hide()

    def close(self, *_args: object) -> None:
        if self.bubble is not None:
            # The anchor's destroyed signal can run during Qt teardown, when
            # closing an independent top-level widget may re-enter C++.
            # Hiding is sufficient; Qt owns the widget lifetime here.
            try:
                self.bubble.hide()
            except RuntimeError:
                # Qt may have already deleted the top-level widget.
                pass


def _tone(path: Path, frequency: float, duration: float, volume: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        for index in range(int(rate * duration)):
            seconds = index / rate
            envelope = max(0.0, 1.0 - seconds / duration)
            sample = int(volume * envelope * 32767 * math.sin(2 * math.pi * frequency * seconds))
            stream.writeframes(struct.pack("<h", max(-32768, min(32767, sample))))


class SoundEffects(QObject):
    """Optional click/drop playback with generated cache-local WAV fallbacks."""

    def __init__(self, cache_dir: Path, enabled: bool = False, volume: int = 50) -> None:
        super().__init__()
        self.enabled = bool(enabled)
        self.volume = max(0, min(100, int(volume)))
        self.cache_dir = Path(cache_dir)
        self._players: dict[str, object] = {}

    def _fallback(self, kind: str) -> Path:
        name = "drop.wav" if kind == "drop" else "click.wav"
        path = self.cache_dir / "sounds" / name
        if not path.is_file():
            _tone(path, 90 if kind == "drop" else 800, 0.15 if kind == "drop" else 0.08, 0.55)
        return path

    def play(self, kind: str = "click", source: Path | None = None) -> bool:
        if not self.enabled or QSoundEffect is None:
            return False
        path = Path(source) if source is not None else self._fallback(kind)
        if not path.is_file():
            path = self._fallback(kind)
        player = self._players.get(kind)
        if player is None:
            player = QSoundEffect(self)
            self._players[kind] = player
        player.setVolume(self.volume / 100.0)
        player.setSource(QUrl.fromLocalFile(str(path)))
        player.play()
        return True

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.stop()

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        for player in self._players.values():
            player.setVolume(self.volume / 100.0)

    def stop(self) -> None:
        for player in self._players.values():
            player.stop()

    def close(self) -> None:
        self.stop()
        self._players.clear()
