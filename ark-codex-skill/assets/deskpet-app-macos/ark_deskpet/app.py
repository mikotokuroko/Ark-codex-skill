"""PySide6 desktop-pet application for macOS."""

from __future__ import annotations

from ctypes import c_void_p
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time
from typing import Any

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .animation_policy import AnimationPolicy, PolicyTransition
from .constants import (
    APP_NAME,
    AUTO_ANIMATIONS_KEY,
    BUNDLE_ID,
    DEFAULT_PET,
)
from .display import Rect, recover_position
from .fullscreen import FullscreenDetector
from .ipc import CommandServer, send_command
from .launch_agent import (
    disable_launch_agent,
    enable_launch_agent,
    launch_agent_enabled,
)
from .manifest import ManifestError, PetEntry, merge_pet_libraries
from .paths import (
    app_bundle_path,
    bundled_pets_dir,
    cache_dir,
    ensure_directories,
    instance_path,
    ipc_socket_path,
    log_dir,
    resource_root,
    settings_path,
    user_pets_dir,
)
from .sessions import get_codex_status
from .storage import (
    atomic_write_json,
    clean_stale_instance,
    load_settings,
    save_settings,
)

PADDING = 12
STATUS_HEIGHT = 46
MIN_SCALE = 0.3
MAX_SCALE = 2.0
SPEED_OPTIONS = (
    ("0.5x", 0.5),
    ("0.75x", 0.75),
    ("1.0x", 1.0),
    ("1.25x", 1.25),
    ("1.5x", 1.5),
)
SUBTITLE_LEVELS = {
    "short": {
        "label": "简短",
        "task_limit": 14,
        "show_model": False,
        "show_progress": False,
    },
    "medium": {
        "label": "标准",
        "task_limit": 36,
        "show_model": True,
        "show_progress": False,
    },
    "long": {
        "label": "详细",
        "task_limit": 80,
        "show_model": True,
        "show_progress": True,
    },
}
CAPTION_TEXT = {
    "en": {
        "idle": "Codex Idle",
        "running": "Codex Running",
        "waiting": "Waiting for Input",
        "error": "Codex Error",
        "elapsed": "Running {value}",
        "model": "Model {value}",
    },
    "zh-Hans": {
        "idle": "Codex 待机",
        "running": "Codex 运行中",
        "waiting": "等待输入",
        "error": "Codex 错误",
        "elapsed": "已运行 {value}",
        "model": "模型 {value}",
    },
}

AUTO_ANIMATION_LABELS = {
    "en": "Follow Codex activity",
    "zh-Hans": "跟随 Codex 活动",
}

ANIMATION_LABELS = (
    ("idle", "放松/relax"),
    ("interact", "互动/interact"),
    ("move", "移动/move"),
    ("sit", "坐下/sit"),
    ("sleep", "睡眠/sleep"),
    ("special", "特殊/special"),
)
MENU_ICON_RESOURCE = Path("resources") / "ark-codex-tray.webp"
MENU_ICON_SIZE = 22
MENU_ICON_DEVICE_PIXEL_RATIOS = (1, 2, 3)


def configure_logging() -> None:
    """Configures a rotating log in the user's Library directory."""
    destination = log_dir() / "deskpet.log"
    destination.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        destination, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _fallback_menu_icon() -> QIcon:
    """Returns a visible fallback when the bundled tray image is unavailable."""
    icon = QIcon()
    for device_pixel_ratio in MENU_ICON_DEVICE_PIXEL_RATIOS:
        pixel_size = MENU_ICON_SIZE * device_pixel_ratio
        pixmap = QPixmap(pixel_size, pixel_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(35, 145, 90))
        painter.setPen(Qt.NoPen)
        margin = 1.5 * device_pixel_ratio
        diameter = 19 * device_pixel_ratio
        painter.drawEllipse(margin, margin, diameter, diameter)
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(12 * device_pixel_ratio)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "A")
        painter.end()
        pixmap.setDevicePixelRatio(device_pixel_ratio)
        icon.addPixmap(pixmap)
    return icon


def make_menu_icon() -> QIcon:
    """Loads the supplied character image as a color-preserving tray icon."""
    image_path = resource_root() / MENU_ICON_RESOURCE
    image = QImage(str(image_path))
    if image.isNull():
        logging.getLogger(__name__).warning(
            "Unable to load tray icon resource: %s", image_path
        )
        return _fallback_menu_icon()

    icon = QIcon()
    for device_pixel_ratio in MENU_ICON_DEVICE_PIXEL_RATIOS:
        pixel_size = MENU_ICON_SIZE * device_pixel_ratio
        scaled = image.scaled(
            QSize(pixel_size, pixel_size),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        pixmap = QPixmap(pixel_size, pixel_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        x = (pixel_size - scaled.width()) // 2
        y = (pixel_size - scaled.height()) // 2
        painter.drawImage(x, y, scaled)
        painter.end()
        pixmap.setDevicePixelRatio(device_pixel_ratio)
        icon.addPixmap(pixmap)
    return icon


class SettingsDialog(QDialog):
    """Chinese settings dialog for appearance and host startup."""

    def __init__(self, settings: dict[str, Any], parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ark Codex 桌宠设置")
        self.setModal(True)
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.speed_combo = QComboBox()
        for label, value in SPEED_OPTIONS:
            self.speed_combo.addItem(label, value)
        speed = float(settings.get("speed", 1.0))
        speed_index = min(
            range(len(SPEED_OPTIONS)),
            key=lambda index: abs(SPEED_OPTIONS[index][1] - speed),
        )
        self.speed_combo.setCurrentIndex(speed_index)

        self.subtitle_combo = QComboBox()
        for key, info in SUBTITLE_LEVELS.items():
            self.subtitle_combo.addItem(info["label"], key)
        subtitle = settings.get("subtitle_length", "medium")
        subtitle_keys = list(SUBTITLE_LEVELS)
        self.subtitle_combo.setCurrentIndex(
            subtitle_keys.index(subtitle) if subtitle in subtitle_keys else 1
        )

        self.subtitle_size = QSlider(Qt.Horizontal)
        self.subtitle_size.setRange(14, 26)
        self.subtitle_size.setValue(int(settings.get("subtitle_size", 19)))
        size_row, self.size_label = self._slider_row(
            self.subtitle_size, "px"
        )

        self.bar_length = QSlider(Qt.Horizontal)
        self.bar_length.setRange(40, 100)
        self.bar_length.setValue(int(settings.get("bar_length", 100)))
        bar_row, self.bar_label = self._slider_row(self.bar_length, "%")

        self.mini_mode = QCheckBox("迷你模式（隐藏字幕条）")
        self.mini_mode.setChecked(bool(settings.get("mini_mode")))
        self.auto_hide = QCheckBox("全屏应用时自动隐藏")
        self.auto_hide.setChecked(
            bool(settings.get("auto_hide_fullscreen"))
        )
        self.autostart = QCheckBox(
            "随 ChatGPT/Codex 启动（登录后监听主程序）"
        )
        self.autostart.setChecked(launch_agent_enabled())

        form.addRow("动作倍速", self.speed_combo)
        form.addRow("字幕长度", self.subtitle_combo)
        form.addRow("字幕大小", size_row)
        form.addRow("字条长度", bar_row)
        form.addRow("", self.mini_mode)
        form.addRow("", self.auto_hide)
        form.addRow("", self.autostart)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _slider_row(slider: QSlider, suffix: str) -> tuple[QWidget, QLabel]:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(f"{slider.value()}{suffix}")
        slider.valueChanged.connect(
            lambda value: label.setText(f"{value}{suffix}")
        )
        row_layout.addWidget(slider, 1)
        row_layout.addWidget(label)
        return row, label

    def values(self) -> dict[str, Any]:
        """Returns values selected by the user."""
        return {
            "speed": self.speed_combo.currentData(),
            "subtitle_length": self.subtitle_combo.currentData(),
            "subtitle_size": self.subtitle_size.value(),
            "bar_length": self.bar_length.value(),
            "mini_mode": self.mini_mode.isChecked(),
            "auto_hide_fullscreen": self.auto_hide.isChecked(),
            "autostart_with_codex": self.autostart.isChecked(),
        }


class PetWindow(QWidget):
    """Transparent animated desktop-pet window."""

    def __init__(self, controller: "DeskpetController") -> None:
        super().__init__()
        self.controller = controller
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setMouseTracking(True)

        self.state = "idle"
        self.frame_index = 0
        self.hold_state = False
        self.cache: dict[int, QImage] = {}
        self.dragging = False
        self.press_global: QPoint | None = None
        self.press_window: QPoint | None = None
        self.press_time = 0.0
        self.pre_drag_state = "idle"
        self.pre_drag_hold = False
        self.status_text = CAPTION_TEXT[self.language]["idle"]
        self.status_active = False
        self.animation_policy = AnimationPolicy(clock=time.monotonic)

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.next_frame)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(2000)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start()
        self.fullscreen_timer = QTimer(self)
        self.fullscreen_timer.setInterval(2000)
        self.fullscreen_timer.timeout.connect(self.check_fullscreen)
        self.fullscreen_timer.start()

        self.pet: PetEntry
        self.manifest: dict[str, Any]
        self.scale = 1.0
        self.speed = 1.0
        self.load_pet(controller.active_pet_name, recover=True)
        self.apply_auto_animations(
            bool(self.settings.get(AUTO_ANIMATIONS_KEY, False))
        )
        self.refresh_status()

    @property
    def settings(self) -> dict[str, Any]:
        """Returns controller-owned settings."""
        return self.controller.settings

    def showEvent(self, event: object) -> None:
        """Keeps the pet above windows from other macOS applications."""
        super().showEvent(event)
        import AppKit
        import objc

        native_view = objc.objc_object(c_void_p=int(self.winId()))
        native_view.window().setLevel_(AppKit.NSFloatingWindowLevel)

    @property
    def show_status(self) -> bool:
        """Returns whether the Codex status strip is visible."""
        return not bool(self.settings.get("mini_mode"))

    @property
    def language(self) -> str:
        """Returns the selected caption language."""
        value = self.settings.get("language", "en")
        return value if value in CAPTION_TEXT else "en"

    def tick_ms(self) -> int:
        """Returns the animation interval after speed scaling."""
        fps = float(self.manifest.get("fps", 20))
        return max(10, int(round(1000.0 / fps / self.speed)))

    def load_pet(self, name: str, recover: bool = True) -> None:
        """Loads a pet and restores its per-character state."""
        entry = self.controller.library.get(name)
        if entry is None:
            raise ManifestError(f"桌宠库中不存在：{name}")
        from .manifest import validate_manifest

        manifest = validate_manifest(entry.path)
        if hasattr(self, "pet"):
            self.save_pet_state()
        self.pet = entry
        self.manifest = manifest
        self.animation_policy.set_available_states(manifest["states"])
        self.controller.active_pet_name = name
        self.settings["pet"] = name
        pet_state = self.settings.get("pet_states", {}).get(name, {})
        self.scale = max(
            MIN_SCALE,
            min(
                MAX_SCALE,
                float(pet_state.get("scale", self.settings.get("scale", 1.0))),
            ),
        )
        self.speed = float(
            pet_state.get("speed", self.settings.get("speed", 1.0))
        )
        self.cache.clear()
        policy_state = getattr(self.animation_policy, "state", "idle")
        if policy_state not in self.manifest["states"]:
            policy_state = "idle"
        self.set_state(
            policy_state,
            bool(getattr(self.animation_policy, "hold", False)),
        )
        self.animation_timer.setInterval(self.tick_ms())
        self.animation_timer.start()
        if recover:
            position = None
            x = pet_state.get("pos_x", self.settings.get("pos_x"))
            y = pet_state.get("pos_y", self.settings.get("pos_y"))
            if x is not None and y is not None:
                position = (int(x), int(y))
            self.move(*recover_position(position, (self.width(), self.height()), self._screens()))
        save_settings(settings_path(), self.settings)
        if self.isVisible():
            self.show()
        self.update()

    def _screens(self) -> list[Rect]:
        return [
            Rect(
                screen.geometry().x(),
                screen.geometry().y(),
                screen.geometry().width(),
                screen.geometry().height(),
            )
            for screen in QGuiApplication.screens()
        ]

    def set_state(self, name: str, hold: bool = False) -> None:
        """Switches animation state when supported by the active pet."""
        if name not in self.manifest["states"]:
            return
        self.state = name
        self.hold_state = hold
        self.frame_index = 0
        self.cache.clear()
        self.apply_geometry()
        self.update()

    def _apply_policy_transition(
        self, transition: PolicyTransition | None
    ) -> None:
        """Applies a state selected by the pure wall-clock policy."""
        if transition is not None:
            self.set_state(transition.state, transition.hold)

    def apply_auto_animations(self, enabled: bool) -> None:
        """Applies the persisted automatic-animation preference."""
        transition = self.animation_policy.set_enabled(bool(enabled))
        self._apply_policy_transition(transition)

    def play_one_shot(self, state: str) -> None:
        """Plays one complete manual animation and then resumes policy mode."""
        if state not in self.manifest["states"]:
            return
        transition = self.animation_policy.start_override(state)
        self._apply_policy_transition(transition)

    def apply_geometry(self) -> None:
        """Crops the transparent window around the current animation bbox."""
        old_x, old_y = self.x(), self.y()
        old_width, old_height = self.width(), self.height()
        bbox = self.manifest["states"][self.state]["bbox"]
        width = int((bbox[2] - bbox[0] + 1) * self.scale) + PADDING * 2
        status_height = STATUS_HEIGHT if self.show_status else 0
        height = (
            int((bbox[3] - bbox[1] + 1) * self.scale)
            + PADDING * 2
            + status_height
        )
        self.resize(width, height)
        if old_width and old_height:
            self.move(
                int(old_x + old_width / 2 - width / 2),
                int(old_y + old_height - height),
            )

    def frame_path(self) -> Path:
        """Returns the current PNG frame path."""
        return (
            self.pet.path
            / "frames"
            / self.state
            / f"frame_{self.frame_index:04d}.png"
        )

    def current_image(self) -> QImage:
        """Loads the current frame with a small in-memory cache."""
        cached = self.cache.get(self.frame_index)
        if cached is not None:
            return cached
        image = QImage(str(self.frame_path()))
        if not image.isNull():
            if len(self.cache) > 6:
                self.cache.clear()
            self.cache[self.frame_index] = image
        return image

    def next_frame(self) -> None:
        """Advances the active animation at its configured frame rate."""
        count = int(self.manifest["states"][self.state]["count"])
        if self.frame_index >= count - 1:
            transition = self.animation_policy.on_animation_cycle_boundary()
            if transition is not None:
                self._apply_policy_transition(transition)
                return
            if self.state in ("interact", "sit", "sleep") and not self.hold_state:
                self.set_state("idle", True)
                return
        self.frame_index = (self.frame_index + 1) % count
        self.update()

    def paintEvent(self, event: object) -> None:
        """Paints the transparent animation and optional status strip."""
        del event
        bbox = self.manifest["states"][self.state]["bbox"]
        image = self.current_image()
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        status_height = STATUS_HEIGHT if self.show_status else 0
        if not image.isNull():
            painter.drawImage(
                QRectF(
                    PADDING - bbox[0] * self.scale,
                    status_height + PADDING - bbox[1] * self.scale,
                    image.width() * self.scale,
                    image.height() * self.scale,
                ),
                image,
            )
        if self.show_status:
            bar_width = max(
                120,
                int(
                    (self.width() - 12)
                    * int(self.settings.get("bar_length", 100))
                    / 100.0
                ),
            )
            bar = QRectF(6, 4, bar_width, STATUS_HEIGHT - 8)
            palette = QApplication.palette()
            painter.setBrush(palette.color(QPalette.Window))
            painter.setPen(palette.color(QPalette.Mid))
            painter.drawRoundedRect(bar, 8, 8)
            font = QApplication.font()
            font.setPixelSize(int(self.settings.get("subtitle_size", 19)))
            painter.setFont(font)
            text = QFontMetrics(font).elidedText(
                self.status_text, Qt.ElideRight, int(bar.width() - 16)
            )
            painter.setPen(palette.color(QPalette.WindowText))
            painter.drawText(
                bar.adjusted(8, 0, -8, 0),
                Qt.AlignVCenter | Qt.AlignLeft,
                text,
            )
        painter.end()

    def mousePressEvent(self, event: Any) -> None:
        """Begins a click or drag interaction."""
        if event.button() != Qt.LeftButton:
            return
        self.dragging = False
        self.pre_drag_state = self.state
        self.pre_drag_hold = self.hold_state
        self.press_global = event.globalPosition().toPoint()
        self.press_window = self.pos()
        self.press_time = time.monotonic()

    def mouseMoveEvent(self, event: Any) -> None:
        """Moves an unlocked pet and shows its move animation."""
        if self.press_global is None or bool(self.settings.get("locked", True)):
            return
        current = event.globalPosition().toPoint()
        delta = current - self.press_global
        if not self.dragging and delta.manhattanLength() > 6:
            self.dragging = True
            self._apply_policy_transition(self.animation_policy.start_drag())
        if self.dragging and event.buttons() & Qt.LeftButton:
            self.move(self.press_window + delta)

    def mouseReleaseEvent(self, event: Any) -> None:
        """Completes click interaction or persists a dragged position."""
        if event.button() != Qt.LeftButton or self.press_global is None:
            return
        current = event.globalPosition().toPoint()
        delta = current - self.press_global
        elapsed = time.monotonic() - self.press_time
        self.press_global = None
        self.press_window = None
        if self.dragging:
            self.dragging = False
            self._apply_policy_transition(self.animation_policy.release_drag())
            self.save_pet_state()
        elif elapsed < 0.5 and delta.manhattanLength() <= 6:
            self.play_one_shot("interact")

    def mouseDoubleClickEvent(self, event: Any) -> None:
        """Toggles mini mode on a left-button double click."""
        if event.button() == Qt.LeftButton:
            self.toggle_mini()

    def contextMenuEvent(self, event: Any) -> None:
        """Shows the pet context menu with a synchronized auto toggle."""
        self.build_context_menu().exec(event.globalPos())

    def add_animation_actions(self, menu: QMenu) -> None:
        """Adds bilingual actions for animations in the active manifest."""
        states = self.manifest.get("states", {})
        for state, label in ANIMATION_LABELS:
            if state in states:
                menu.addAction(
                    label,
                    lambda checked=False, state=state: self.play_one_shot(
                        state
                    ),
                )

    def build_context_menu(self) -> QMenu:
        """Builds the pet context menu for display or UI smoke tests."""
        menu = QMenu(self)
        self.add_animation_actions(menu)
        library = menu.addMenu("桌宠库")
        group = QActionGroup(library)
        group.setExclusive(True)
        for name in self.controller.library:
            action = library.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == self.pet.name)
            action.triggered.connect(
                lambda checked=False, name=name: self.controller.select_pet(name)
            )
            group.addAction(action)
        menu.addSeparator()
        mini = menu.addAction("迷你模式（隐藏字幕）")
        mini.setCheckable(True)
        mini.setChecked(not self.show_status)
        mini.triggered.connect(self.toggle_mini)
        fullscreen = menu.addAction("全屏应用时自动隐藏")
        fullscreen.setCheckable(True)
        fullscreen.setChecked(
            bool(self.settings.get("auto_hide_fullscreen"))
        )
        fullscreen.triggered.connect(self.toggle_fullscreen_auto_hide)
        auto_animations = menu.addAction(
            AUTO_ANIMATION_LABELS[self.language]
        )
        auto_animations.setCheckable(True)
        auto_animations.setChecked(
            bool(self.settings.get(AUTO_ANIMATIONS_KEY, False))
        )
        auto_animations.toggled.connect(
            self.controller.set_auto_animations
        )
        menu.addAction(
            "解锁拖动" if self.settings.get("locked", True) else "锁定拖动",
            self.toggle_lock,
        )
        menu.addAction("设置…", self.controller.open_settings)
        menu.addAction("放大", lambda: self.set_scale(self.scale + 0.1))
        menu.addAction("缩小", lambda: self.set_scale(self.scale - 0.1))
        menu.addSeparator()
        menu.addAction("隐藏桌宠", self.controller.hide_pet)
        menu.addAction("退出", self.controller.quit)
        return menu

    def set_scale(self, scale: float) -> None:
        """Changes and persists the active pet scale."""
        self.scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        self.apply_geometry()
        self.save_pet_state()
        self.update()

    def toggle_mini(self) -> None:
        """Toggles the status strip while preserving the pet's feet position."""
        self.settings["mini_mode"] = self.show_status
        save_settings(settings_path(), self.settings)
        self.apply_geometry()
        self.update()

    def toggle_lock(self) -> None:
        """Toggles whether dragging is allowed."""
        self.settings["locked"] = not bool(self.settings.get("locked", True))
        self.dragging = False
        self.press_global = None
        self.press_window = None
        save_settings(settings_path(), self.settings)

    def toggle_fullscreen_auto_hide(self) -> None:
        """Toggles fullscreen auto-hide without requesting privacy access."""
        key = "auto_hide_fullscreen"
        self.settings[key] = not bool(self.settings.get(key))
        save_settings(settings_path(), self.settings)
        self.check_fullscreen()

    def check_fullscreen(self) -> None:
        """Hides only for confirmed fullscreen coverage and restores safely."""
        if self.controller.user_hidden:
            return
        if not bool(self.settings.get("auto_hide_fullscreen")):
            if self.controller.fullscreen_hidden:
                self.controller.fullscreen_hidden = False
                self.show()
            return
        pet_rect = Rect(self.x(), self.y(), self.width(), self.height())
        result = self.controller.fullscreen_detector.detect(
            pet_rect, self._screens()
        )
        if result is True and self.isVisible():
            self.controller.fullscreen_hidden = True
            self.hide()
        elif result is False and self.controller.fullscreen_hidden:
            self.controller.fullscreen_hidden = False
            self.show()

    def save_pet_state(self) -> None:
        """Persists position, scale, and speed for the active character."""
        pet_states = self.settings.setdefault("pet_states", {})
        pet_states[self.pet.name] = {
            "scale": self.scale,
            "speed": self.speed,
            "pos_x": self.x(),
            "pos_y": self.y(),
            "selected": True,
        }
        self.settings.update(
            {
                "pet": self.pet.name,
                "scale": self.scale,
                "speed": self.speed,
                "pos_x": self.x(),
                "pos_y": self.y(),
            }
        )
        save_settings(settings_path(), self.settings)

    def _format_elapsed(self, seconds: int) -> str:
        minutes, second = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if self.language == "en":
            if hours:
                return f"{hours}h {minutes}m"
            if minutes:
                return f"{minutes}m {second}s"
            return f"{second}s"
        if hours:
            return f"{hours}小时{minutes}分"
        if minutes:
            return f"{minutes}分{second}秒"
        return f"{second}秒"

    @staticmethod
    def _format_tokens(count: int) -> str:
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        if count >= 1_000:
            return f"{count / 1_000:.1f}k"
        return str(count)

    @staticmethod
    def _cut(text: str, limit: int) -> str:
        normalized = " ".join(text.split())
        return (
            normalized
            if len(normalized) <= limit
            else normalized[: limit - 1] + "…"
        )

    def refresh_status(self) -> None:
        """Reads recent Codex status without writing to the sessions directory."""
        status = get_codex_status()
        state = status.get("state", "idle")
        if state not in ("idle", "running", "waiting", "error"):
            state = "idle"
        self.status_active = state == "running"
        self._apply_policy_transition(
            self.animation_policy.set_mode(
                "running" if self.status_active else "idle"
            )
        )
        text = CAPTION_TEXT[self.language]
        level = SUBTITLE_LEVELS.get(
            self.settings.get("subtitle_length"), SUBTITLE_LEVELS["medium"]
        )
        parts = [text[state]]
        if self.status_active and status.get("elapsed") is not None:
            parts.append(
                text["elapsed"].format(
                    value=self._format_elapsed(status["elapsed"])
                )
            )
        if self.status_active and status.get("tokens") is not None:
            parts.append(f"Token {self._format_tokens(status['tokens'])}")
        if status.get("task"):
            parts.append(self._cut(status["task"], level["task_limit"]))
        if level["show_model"] and status.get("model"):
            parts.append(
                text["model"].format(
                    value=self._cut(status["model"], 24)
                )
            )
        if level["show_progress"] and status.get("progress"):
            parts.append(self._cut(status["progress"], 80))
        self.status_text = " · ".join(parts)
        self.update()


class DeskpetController:
    """Coordinates the pet window, status-menu icon, settings, and IPC."""

    def __init__(self, app: QApplication, launch_mode: str) -> None:
        self.app = app
        self.launch_mode = launch_mode
        self.settings = load_settings(settings_path())
        self.library: dict[str, PetEntry] = {}
        self.active_pet_name = DEFAULT_PET
        self.user_hidden = bool(self.settings.get("user_hidden"))
        self.fullscreen_hidden = False
        self.fullscreen_detector = FullscreenDetector()
        self.refresh_library(create_window=False)
        self.window = PetWindow(self)
        self.app.aboutToQuit.connect(self.window.save_pet_state)
        self.tray = QSystemTrayIcon(make_menu_icon(), self.app)
        self.tray.setToolTip("Ark Codex 桌宠")
        self.tray.activated.connect(self._tray_activated)
        self._build_tray_menu()
        self.tray.show()
        if not self.user_hidden:
            self.window.show()

    def refresh_library(self, create_window: bool = True) -> None:
        """Reloads bundled and user pets, honoring user overrides."""
        self.library = merge_pet_libraries(
            bundled_pets_dir(), user_pets_dir()
        )
        if not self.library:
            raise ManifestError("桌宠库为空")
        requested = self.settings.get("pet")
        self.active_pet_name = (
            requested if requested in self.library else next(iter(self.library))
        )
        if create_window and hasattr(self, "window"):
            current_name = self.window.pet.name
            target = current_name if current_name in self.library else self.active_pet_name
            self.window.load_pet(target, recover=False)
            self._build_tray_menu()

    def _build_tray_menu(self) -> None:
        menu = QMenu()
        menu.addAction("显示桌宠", self.show_pet)
        menu.addAction("隐藏桌宠", self.hide_pet)
        library_menu = menu.addMenu("桌宠库")
        group = QActionGroup(library_menu)
        group.setExclusive(True)
        current = self.window.pet.name
        for name in self.library:
            action = library_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == current)
            action.triggered.connect(
                lambda checked=False, name=name: self.select_pet(name)
            )
            group.addAction(action)
        animation_menu = menu.addMenu("动画/animations")
        self.window.add_animation_actions(animation_menu)
        language_menu = menu.addMenu("Language")
        language_group = QActionGroup(language_menu)
        language_group.setExclusive(True)
        for code, label in (("en", "English"), ("zh-Hans", "简体中文")):
            action = language_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.window.language == code)
            action.triggered.connect(
                lambda checked=False, code=code: self.set_language(code)
            )
            language_group.addAction(action)
        menu.addAction("设置…", self.open_settings)
        menu.addSeparator()
        autostart = menu.addAction("随 ChatGPT/Codex 启动")
        autostart.setCheckable(True)
        autostart.setChecked(launch_agent_enabled())
        autostart.toggled.connect(self.set_autostart)
        auto_animations = menu.addAction(
            AUTO_ANIMATION_LABELS[self.window.language]
        )
        auto_animations.setCheckable(True)
        auto_animations.setChecked(
            bool(self.settings.get(AUTO_ANIMATIONS_KEY, False))
        )
        auto_animations.toggled.connect(self.set_auto_animations)
        menu.addSeparator()
        menu.addAction("退出", self.quit)
        self.tray.setContextMenu(menu)

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.show_pet()

    def show_pet(self) -> None:
        """Shows the pet and clears explicit user hiding."""
        self.user_hidden = False
        self.fullscreen_hidden = False
        self.settings["user_hidden"] = False
        save_settings(settings_path(), self.settings)
        self.window.show()
        self.window.raise_()

    def hide_pet(self) -> None:
        """Hides the pet while leaving the status-menu icon active."""
        self.user_hidden = True
        self.settings["user_hidden"] = True
        save_settings(settings_path(), self.settings)
        self.window.hide()

    def select_pet(self, name: str) -> None:
        """Switches pets and rebuilds checked menu state."""
        try:
            self.window.load_pet(name)
        except ManifestError as error:
            QMessageBox.warning(self.window, APP_NAME, str(error))
            return
        self._build_tray_menu()

    def set_language(self, language: str) -> None:
        """Changes the caption language and persists the selection."""
        if language not in CAPTION_TEXT:
            return
        self.settings["language"] = language
        save_settings(settings_path(), self.settings)
        self.window.refresh_status()
        self._build_tray_menu()

    def set_auto_animations(self, enabled: bool) -> None:
        """Persists and applies the synchronized automatic-animation toggle."""
        value = bool(enabled)
        self.settings[AUTO_ANIMATIONS_KEY] = value
        save_settings(settings_path(), self.settings)
        self.window.apply_auto_animations(value)
        self._build_tray_menu()

    def watcher_executable(self) -> Path:
        """Returns the helper executable embedded in the installed bundle."""
        return app_bundle_path() / "Contents" / "Helpers" / "ArkCodexWatcher"

    def set_autostart(self, enabled: bool) -> None:
        """Enables or disables launchd host watching for this user."""
        try:
            if enabled:
                helper = self.watcher_executable()
                if not helper.is_file():
                    raise FileNotFoundError(f"找不到后台助手：{helper}")
                enable_launch_agent(helper)
            else:
                disable_launch_agent()
        except (OSError, RuntimeError) as error:
            QMessageBox.warning(
                self.window,
                APP_NAME,
                f"随 ChatGPT/Codex 启动设置失败：\n{error}",
            )
        actual = launch_agent_enabled()
        self.settings["autostart_with_codex"] = actual
        save_settings(settings_path(), self.settings)
        self._build_tray_menu()

    def open_settings(self) -> None:
        """Shows settings and applies accepted values immediately."""
        self.settings["speed"] = self.window.speed
        dialog = SettingsDialog(self.settings, self.window)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        old_autostart = launch_agent_enabled()
        self.settings.update(values)
        self.window.speed = float(values["speed"])
        self.window.animation_timer.setInterval(self.window.tick_ms())
        self.window.apply_geometry()
        self.window.save_pet_state()
        if bool(values["autostart_with_codex"]) != old_autostart:
            self.set_autostart(bool(values["autostart_with_codex"]))
        self.window.check_fullscreen()
        self.window.update()

    def handle_command(self, command: str) -> None:
        """Dispatches one IPC command."""
        if command == "show":
            self.show_pet()
        elif command == "hide":
            self.hide_pet()
        elif command == "refresh-library":
            try:
                self.refresh_library()
            except ManifestError as error:
                logging.getLogger(__name__).error("刷新桌宠库失败：%s", error)
        elif command == "shutdown":
            self.quit()

    def quit(self) -> None:
        """Saves state and terminates the complete app."""
        self.window.save_pet_state()
        self.tray.hide()
        self.app.quit()


def _set_accessory_activation_policy() -> None:
    """Suppresses the Dock icon during development and frozen execution."""
    try:
        import AppKit

        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory
        )
    except (ImportError, AttributeError):
        logging.getLogger(__name__).warning("无法设置 accessory 激活策略")


def run(argv: list[str] | None = None) -> int:
    """Runs the single-instance desktop-pet application."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_directories()
    configure_logging()
    application = QApplication([sys.argv[0], *arguments])
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(APP_NAME)
    application.setOrganizationName("AstrariaX")
    application.setQuitOnLastWindowClosed(False)
    _set_accessory_activation_policy()

    command = None
    if "--command" in arguments:
        index = arguments.index("--command")
        if index + 1 < len(arguments):
            command = arguments[index + 1]
    socket_path = ipc_socket_path()
    if command is not None:
        return 0 if send_command(socket_path, command) else 2
    if send_command(socket_path, "show", timeout_ms=250):
        return 0
    clean_stale_instance(instance_path(), socket_path)
    server = CommandServer(socket_path)
    if not server.listen():
        logging.error("无法建立单实例命令通道")
        return 2
    launch_mode = "watcher" if "--watcher-managed" in arguments else "manual"
    atomic_write_json(
        instance_path(),
        {"pid": os.getpid(), "mode": launch_mode, "bundle_id": BUNDLE_ID},
    )
    try:
        controller = DeskpetController(application, launch_mode)
        server.command_received.connect(controller.handle_command)
        exit_code = application.exec()
        del controller
        return exit_code
    except Exception:
        logging.exception("桌宠启动失败")
        raise
    finally:
        server.close()
        try:
            instance_path().unlink()
        except FileNotFoundError:
            pass
