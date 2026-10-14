# -*- mode: python ; coding: utf-8 -*-
"""Windows x64 build of the shared desktop-pet runtime."""
from pathlib import Path
repository = Path(SPECPATH).parent
runtime = repository / "ark-codex-skill" / "assets" / "deskpet-app-macos"
pet = runtime / "pets" / "结城理"
a = Analysis([str(runtime / "main.py")], pathex=[str(runtime)],
             datas=[(str(pet), "pets/结城理"),
                    (str(runtime / "resources" / "ark-codex-tray.webp"), "resources")],
             hiddenimports=["psutil", "PySide6.QtNetwork", "PySide6.QtMultimedia"],
             excludes=["AppKit", "Foundation", "Quartz", "objc", "pytest", "pytestqt", "playwright"],
             binaries=[], hookspath=[], runtime_hooks=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Ark Codex Deskpet",
          console=False, debug=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Ark Codex Deskpet", strip=False, upx=False)
