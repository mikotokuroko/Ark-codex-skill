"""Exercise a frozen Windows application and its real named-pipe IPC."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

executable = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as home:
    env = {**os.environ, "LOCALAPPDATA": home}
    process = subprocess.Popen([str(executable)], env=env)
    try:
        state = Path(home) / "Ark Codex Deskpet" / "Cache" / "instance.json"
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError(f'App exited early: {process.returncode}')
            if state.exists():
                break
            time.sleep(.25)
        else:
            raise RuntimeError('App did not create its instance record')
        time.sleep(3)
        for command in ['hide', 'show', 'refresh-library', 'shutdown']:
            result = subprocess.run([str(executable), '--command', command], env=env, timeout=30)
            assert result.returncode == 0, command
            time.sleep(.2)
        assert process.wait(timeout=30) == 0
        settings = json.loads((Path(home) / 'Ark Codex Deskpet' / 'settings.json').read_text(encoding='utf-8'))
        assert settings['pet'] == '结城理'
        assert 'gravity_enabled' in settings
        print('Frozen Windows launch, default pack, settings persistence and IPC passed.')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
