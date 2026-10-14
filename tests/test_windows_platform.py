"""Portable coverage of Windows path, process and export contracts."""
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
from ark_deskpet import paths, acquisition, storage, windows_platform, pet_install
from ark_deskpet.host_activity import snapshot_from_applications


def test_windows_paths_use_local_appdata(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    assert paths.settings_path() == tmp_path / 'Ark Codex Deskpet/settings.json'
    assert paths.cache_dir() == tmp_path / 'Ark Codex Deskpet/Cache'
    assert paths.log_dir() == tmp_path / 'Ark Codex Deskpet/Logs'
    assert paths.user_pets_dir() == tmp_path / 'Ark Codex Deskpet/Pets'


def test_windows_pid_probe_does_not_signal_process(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setitem(sys.modules, 'psutil', SimpleNamespace(pid_exists=lambda pid: pid == 42))
    monkeypatch.setattr(storage.os, 'kill', lambda *args: pytest.fail('Windows must not use os.kill'))
    assert storage.pid_is_alive(42)
    assert not storage.pid_is_alive(43)


def test_windows_host_identity_and_start_time(monkeypatch):
    entries = [SimpleNamespace(pid=10, info={'name':'Codex.exe','create_time':100}),
               SimpleNamespace(pid=11, info={'name':'ChatGPT.exe','create_time':90}),
               SimpleNamespace(pid=12, info={'name':'unrelated.exe','create_time':50})]
    monkeypatch.setitem(sys.modules, 'psutil', SimpleNamespace(process_iter=lambda fields: entries,
                         NoSuchProcess=ProcessLookupError, AccessDenied=PermissionError))
    apps = windows_platform.running_applications()
    assert {a['pid'] for a in apps} == {10,11}
    snapshot = snapshot_from_applications(apps, process_start_provider=lambda pid: 100)
    assert snapshot.running
    assert snapshot.cutoff == 100


def test_windows_exporter_uses_windows_virtualenv(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    python = tmp_path / '.venv-windows/Scripts/python.exe'
    script = tmp_path / 'ark-codex-skill/scripts/export_pet.py'
    for p in (python,script):
        p.parent.mkdir(parents=True,exist_ok=True);p.touch()
    assert acquisition.resolve_repository(tmp_path) == (python,script)


@pytest.mark.parametrize('name', ['../x', r'..\x', 'CON', 'nul.txt', 'bad:name', 'bad.'])
def test_windows_pet_names_are_safe(name, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    with pytest.raises(ValueError):
        pet_install.validate_pet_name(name)


def test_frozen_watcher_command_handles_spaces(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    assert windows_platform.application_command(Path('C:/My Pets/Ark.exe')) == [str(Path('C:/My Pets/Ark.exe'))]
