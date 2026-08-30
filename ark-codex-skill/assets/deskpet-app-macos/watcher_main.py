#!/usr/bin/env python3
"""Entry point for the event-driven watcher helper."""

import sys

from ark_deskpet.watcher import run


if __name__ == "__main__":
    raise SystemExit(
        run(
            probe_only="--probe-hosts" in sys.argv[1:],
            list_only="--list-apps" in sys.argv[1:],
        )
    )
