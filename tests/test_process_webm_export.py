"""Offline checks for grouped WebM discovery and path-safe state names."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'ark-codex-skill/scripts/process_webm.py'
spec = importlib.util.spec_from_file_location('process_webm', SCRIPT)
process_webm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_webm)


def test_discover_state_files_keeps_extra_actions(tmp_path):
    for name in ('Relax', 'Interact', 'Move', 'Sit', 'Sleep', 'Front Wave'):
        (tmp_path / f'operator-基建-{name}.webm').write_bytes(b'x' * 1000)
    states = process_webm.discover_state_files(str(tmp_path))
    assert states['idle'].endswith('Relax.webm')
    assert states['front_wave'].endswith('Front Wave.webm')


def test_group_filter_uses_action_after_group_and_x_suffix(tmp_path):
    (tmp_path / 'pet-default-正面-Attack-x1.webm').write_bytes(b'x' * 1000)
    (tmp_path / 'pet-default-正面-Skill_1-x1.webm').write_bytes(b'x' * 1000)
    (tmp_path / 'pet-default-背面-Attack-x1.webm').write_bytes(b'x' * 1000)
    states = process_webm.discover_state_files(str(tmp_path), '正面')
    assert set(states) == {'attack', 'skill_1'}


def test_group_name_and_fps_validation(tmp_path):
    with pytest.raises(ValueError, match='group'):
        process_webm.run(str(tmp_path), 'pet', str(tmp_path / 'out'), '../base')
    with pytest.raises(ValueError, match='FPS'):
        process_webm.run(str(tmp_path), 'pet', str(tmp_path / 'out'), 'base', 24)


def test_group_capture_failure_leaves_existing_package_unchanged(tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'pet-default-front-Attack-x1.webm').write_bytes(b'x' * 1000)
    destination = tmp_path / 'pet'
    (destination / 'sentinel.txt').parent.mkdir()
    (destination / 'sentinel.txt').write_text('old')

    class Page:
        def goto(self, *args, **kwargs):
            raise RuntimeError('capture failed')
    class Browser:
        def new_page(self, **kwargs): return Page()
        def close(self): pass
    class Playwright:
        chromium = type('Chromium', (), {'launch': lambda *args, **kwargs: Browser()})()
    class Runner:
        def __enter__(self): return Playwright()
        def __exit__(self, *args): return False
    class Server:
        server_address = ('127.0.0.1', 12345)
        def serve_forever(self): pass
        def shutdown(self): pass

    monkeypatch.setattr(process_webm, 'sync_playwright', lambda: Runner())
    monkeypatch.setattr(process_webm.socketserver, 'ThreadingTCPServer', lambda *args, **kwargs: Server())
    with pytest.raises(RuntimeError, match='capture failed'):
        process_webm.run(str(source), 'pet', str(destination), 'front')
    assert (destination / 'sentinel.txt').read_text() == 'old'
