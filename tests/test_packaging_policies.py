"""Static safeguards for installer and bundle policy."""

from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def test_installer_never_removes_application_support() -> None:
    installer = (
        REPOSITORY / "ark-codex-skill" / "scripts" / "install_macos.sh"
    ).read_text(encoding="utf-8")
    assert 'rm -rf -- "${SUPPORT_DIR}"' not in installer
    assert "--no-cache-dir" in installer
    assert "codesign --verify --deep --strict" in installer
    assert "-info" in installer


def test_uninstaller_requires_explicit_purge() -> None:
    uninstaller = (
        REPOSITORY / "ark-codex-skill" / "scripts" / "uninstall_macos.sh"
    ).read_text(encoding="utf-8")
    assert '"${1}" == "--purge-data"' in uninstaller
    assert 'if [[ "${purge_data}" == true ]]' in uninstaller


def test_windows_template_is_still_identical_to_upstream() -> None:
    import subprocess

    result = subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            "upstream/main",
            "--",
            "ark-codex-skill/assets/deskpet-app",
        ],
        cwd=REPOSITORY,
        check=False,
    )
    assert result.returncode == 0
