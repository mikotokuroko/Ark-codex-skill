#!/usr/bin/env python3
"""Copy the deskpet app template into a new project and write initial settings."""

import argparse
import json
import shutil
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
APP_TEMPLATE = SKILL_DIR / "assets" / "deskpet-app"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--pet",
        default="结城理",
        help="initial pet name (default: bundled 结城理)",
    )
    args = parser.parse_args()

    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    for item in APP_TEMPLATE.iterdir():
        if item.name == "pets":
            continue
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    (target / "pets").mkdir(exist_ok=True)
    default_pack = SKILL_DIR / "assets" / "deskpet-app-macos" / "pets" / "结城理"
    shutil.copytree(default_pack, target / "pets" / "结城理", dirs_exist_ok=True)

    settings = {
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
        "pet": args.pet or "结城理",
        "pet_states": {},
        "autostart_with_codex": False,
    }
    (target / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("scaffolded deskpet project at", target)


if __name__ == "__main__":
    main()
