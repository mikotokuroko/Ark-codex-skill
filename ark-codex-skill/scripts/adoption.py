#!/usr/bin/env python3
"""Optional, best-effort adoption counts. No reporting without saved consent."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import uuid
from urllib.request import Request, urlopen

ENDPOINT = 'https://ark-adoption.hoicheoklam.workers.dev/events'

def state_path():
    if sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support'
    elif os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return base / 'Ark Codex Deskpet' / 'adoption.json'

def disabled():
    return any(os.environ.get(k) for k in ('ARK_DISABLE_REPORTING', 'DISABLE_TELEMETRY', 'DO_NOT_TRACK', 'CI', 'PYTEST_CURRENT_TEST'))

@contextmanager
def locked():
    path = state_path(); path.parent.mkdir(parents=True, exist_ok=True)
    # Do not wait on another process: counters must not stall the user's task.
    lock = path.with_suffix('.lock'); lock.mkdir()
    try: yield path
    finally: lock.rmdir()

def read(path):
    if not path.exists(): return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict): raise ValueError('Invalid reporting settings')
    return data

def save(path, data):
    temp = path.with_suffix('.tmp')
    with open(temp, 'w', encoding='utf-8') as f:
        os.chmod(temp, 0o600)
        json.dump(data, f)
    os.replace(temp, path)

def consent(choice=None):
    """Prompt only on a terminal. Automation never implies consent."""
    if disabled() and choice is None: return False
    try:
        with locked() as path:
            data = read(path)
            if choice is None and isinstance(data.get('enabled'), bool): return data['enabled']
            if choice is None:
                if not sys.stdin.isatty(): return False
                answer = input('Share optional installation and successful pet-generation counts with the developer via Cloudflare? Sends only a random event ID and event type; no prompts, names or paths. [y/N] ')
                choice = answer.strip().lower() in ('y', 'yes')
            data['enabled'] = bool(choice)
            if not choice: data.pop('pending', None)
            save(path, data)
            return bool(choice)
    except Exception:
        return False

def record(kind):
    """Call only after success. Retries reuse IDs; reinstall counts once per state."""
    if disabled() or kind not in ('installation', 'pet_generation'): return
    try:
        with locked() as path:
            data = read(path)
            if data.get('enabled') is not True: return
            pending = data.setdefault('pending', [])
            if kind == 'installation':
                if not data.get('installation_recorded'):
                    pending.append({'event_id': str(uuid.uuid4()), 'kind': kind})
                    data['installation_recorded'] = True
            else:
                pending.append({'event_id': str(uuid.uuid4()), 'kind': kind})
            # Bounded local queue. Only accepted events are included in totals.
            data['pending'] = pending = pending[-100:]
            save(path, data)
            # One request per successful action, with a short timeout.
            if pending:
                req = Request(ENDPOINT, data=json.dumps(pending[0]).encode(),
                              headers={'Content-Type': 'application/json', 'User-Agent': 'ArkCodex-Adoption/1.0'}, method='POST')
                with urlopen(req, timeout=2) as response:
                    if response.status != 202: return
                pending.pop(0); save(path, data)
    except Exception:
        pass  # Counting must never turn a successful install/export into failure.

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable', 'disable', 'status', 'installation'])
    args = parser.parse_args()
    if args.action in ('enable', 'disable'):
        consent(args.action == 'enable')
    elif args.action == 'installation':
        if consent(): record('installation')
    else:
        try: print('enabled' if read(state_path()).get('enabled') is True else 'disabled')
        except Exception: print('disabled')

if __name__ == '__main__': main()
