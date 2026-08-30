# -*- mode: python ; coding: utf-8 -*-
"""Build the arm64 GUI bundle and standalone watcher helper."""

from pathlib import Path
import plistlib

repository = Path(SPECPATH).parent
macos_root = repository / "ark-codex-skill" / "assets" / "deskpet-app-macos"
default_pet_name = "予愿安洁莉娜"
default_pet = (
    repository
    / "ark-codex-skill"
    / "assets"
    / "deskpet-app"
    / "pets"
    / default_pet_name
)
packaging = repository / "packaging"

with (packaging / "Info.plist").open("rb") as plist_file:
    info_plist = plistlib.load(plist_file)

app_analysis = Analysis(
    [str(macos_root / "main.py")],
    pathex=[str(macos_root)],
    binaries=[],
    datas=[
        (
            str(default_pet / "manifest.json"),
            f"pets/{default_pet_name}",
        ),
        (str(default_pet / "frames"), f"pets/{default_pet_name}/frames"),
        (
            str(packaging / "com.astrariax.arkcodexdeskpet.watcher.plist"),
            "LaunchAgent",
        ),
    ],
    hiddenimports=[
        "AppKit",
        "Foundation",
        "Quartz",
        "objc",
        "PySide6.QtNetwork",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["playwright", "pytest", "pytestqt"],
    noarchive=False,
)
app_pyz = PYZ(app_analysis.pure)
app_executable = EXE(
    app_pyz,
    app_analysis.scripts,
    [],
    exclude_binaries=True,
    name="Ark Codex Deskpet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch="arm64",
)
app_collection = COLLECT(
    app_executable,
    app_analysis.binaries,
    app_analysis.datas,
    strip=False,
    upx=False,
    name="Ark Codex Deskpet",
)
app_bundle = BUNDLE(
    app_collection,
    name="Ark Codex Deskpet.app",
    icon=str(packaging / "ArkCodexDeskpet.icns"),
    bundle_identifier="com.astrariax.arkcodexdeskpet",
    info_plist=info_plist,
    target_arch="arm64",
)

watcher_analysis = Analysis(
    [str(macos_root / "watcher_main.py")],
    pathex=[str(macos_root)],
    binaries=[],
    datas=[],
    hiddenimports=["AppKit", "Foundation", "objc"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide6", "Quartz", "playwright", "pytest", "pytestqt"],
    noarchive=False,
)
watcher_pyz = PYZ(watcher_analysis.pure)
watcher_executable = EXE(
    watcher_pyz,
    watcher_analysis.scripts,
    watcher_analysis.binaries,
    watcher_analysis.datas,
    [],
    name="ArkCodexWatcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch="arm64",
)
