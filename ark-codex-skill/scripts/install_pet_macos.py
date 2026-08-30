#!/usr/bin/env python3
"""Validate and atomically install a generated pet on macOS."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

SKILL_ROOT = Path(__file__).resolve().parent.parent
MACOS_APP_ROOT = SKILL_ROOT / "assets" / "deskpet-app-macos"
sys.path.insert(0, str(MACOS_APP_ROOT))

from ark_deskpet.ipc import send_command  # noqa: E402
from ark_deskpet.paths import ipc_socket_path, user_pets_dir  # noqa: E402
from ark_deskpet.pet_install import install_pet  # noqa: E402


def main() -> int:
    """Installs one generated pet and refreshes a running app if present."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="completed pet directory")
    parser.add_argument("--name", help="library name; defaults to source name")
    parser.add_argument(
        "--library",
        type=Path,
        default=user_pets_dir(),
        help="override the user pet library (primarily for tests)",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="do not notify a running Ark Codex Deskpet instance",
    )
    arguments = parser.parse_args()

    notifier = None
    if not arguments.no_refresh:
        notifier = lambda command: send_command(ipc_socket_path(), command)
    destination = install_pet(
        arguments.source.resolve(),
        arguments.library.expanduser().resolve(),
        name=arguments.name,
        notifier=notifier,
    )
    print(f"已安装桌宠：{destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
