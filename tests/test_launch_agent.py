"""LaunchAgent definition and isolated enable/disable tests."""

from pathlib import Path
import plistlib

from ark_deskpet import launch_agent
from ark_deskpet.constants import WATCHER_ID


def test_launch_agent_definition_uses_required_identifier(tmp_path: Path) -> None:
    definition = launch_agent.launch_agent_definition(
        Path("/Example.app/Contents/Helpers/ArkCodexWatcher"), tmp_path
    )
    assert definition["Label"] == WATCHER_ID
    assert definition["RunAtLoad"] is True
    assert definition["KeepAlive"] is True


def test_enable_and_disable_touch_only_own_agent(
    tmp_path: Path, monkeypatch
) -> None:
    commands = []
    monkeypatch.setattr(
        launch_agent,
        "_run_launchctl",
        lambda arguments, check=True: commands.append((arguments, check)),
    )
    helper = tmp_path / "helper"
    helper.touch()
    launch_agent.enable_launch_agent(helper, tmp_path)
    target = (
        tmp_path
        / "Library"
        / "LaunchAgents"
        / f"{WATCHER_ID}.plist"
    )
    assert target.is_file()
    with target.open("rb") as file:
        assert plistlib.load(file)["ProgramArguments"] == [str(helper)]
    launch_agent.disable_launch_agent(tmp_path)
    assert not target.exists()
    assert len(commands) == 3
