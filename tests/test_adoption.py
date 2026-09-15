import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

spec = importlib.util.spec_from_file_location('adoption', Path(__file__).parents[1] / 'ark-codex-skill/scripts/adoption.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(a, 'state_path', lambda: tmp_path / 'adoption.json')
    monkeypatch.setattr(a, 'disabled', lambda: False)
    send = MagicMock(); send.return_value.__enter__.return_value.status = 202
    monkeypatch.setattr(a, 'urlopen', send)
    return send

def test_no_consent_no_network(env):
    a.record('installation'); assert not env.called

def test_noninteractive_does_not_consent(env, monkeypatch):
    monkeypatch.setattr(a.sys.stdin, 'isatty', lambda: False)
    assert not a.consent(); a.record('pet_generation'); assert not env.called

def test_prompt_defaults_no(env, monkeypatch):
    monkeypatch.setattr(a.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda _: '')
    assert not a.consent(); assert a.read(a.state_path())['enabled'] is False

def test_install_once_and_generations_separate(env):
    a.consent(True)
    a.record('installation'); a.record('installation')
    a.record('pet_generation'); a.record('pet_generation')
    payloads = [json.loads(c.args[0].data) for c in env.call_args_list]
    assert [p['kind'] for p in payloads] == ['installation','pet_generation','pet_generation']
    assert len({p['event_id'] for p in payloads}) == 3
    assert all(set(p) == {'event_id','kind'} for p in payloads)

def test_failed_send_retries_same_id_and_optout_clears_queue(env):
    a.consent(True); env.side_effect = OSError('offline')
    a.record('installation'); first = json.loads(env.call_args.args[0].data)
    env.side_effect = None; a.record('installation')
    assert json.loads(env.call_args.args[0].data) == first
    env.side_effect = OSError('offline'); a.record('pet_generation')
    assert a.read(a.state_path())['pending']
    a.consent(False); assert 'pending' not in a.read(a.state_path())
    env.reset_mock(); a.record('pet_generation'); assert not env.called

def test_corrupt_state_and_contention_do_not_break_work(env):
    a.state_path().write_text('not json'); a.record('installation'); assert not env.called
    a.state_path().with_suffix('.lock').mkdir(); assert not a.consent(True)

def test_disabled_overrides_saved_consent(env, monkeypatch):
    a.consent(True); monkeypatch.setattr(a, 'disabled', lambda: True)
    a.record('installation'); assert not env.called
