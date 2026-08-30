"""Shared application constants."""

APP_NAME = "Ark Codex Deskpet"
BUNDLE_ID = "com.astrariax.arkcodexdeskpet"
WATCHER_ID = "com.astrariax.arkcodexdeskpet.watcher"
DEFAULT_PET = "予愿安洁莉娜"
REQUIRED_STATES = ("idle", "interact", "move", "sit", "sleep")
IPC_COMMANDS = ("show", "hide", "shutdown", "refresh-library")
IPC_SERVER_NAME = "com.astrariax.arkcodexdeskpet.command"
SETTINGS_VERSION = 2

DEFAULT_SETTINGS = {
    "version": SETTINGS_VERSION,
    "speed": 1.0,
    "subtitle_length": "medium",
    "subtitle_size": 19,
    "bar_length": 100,
    "mini_mode": False,
    "auto_hide_fullscreen": False,
    "locked": True,
    "scale": 1.0,
    "pos_x": None,
    "pos_y": None,
    "pet": DEFAULT_PET,
    "pet_states": {},
    "autostart_with_codex": False,
    "user_hidden": False,
}
