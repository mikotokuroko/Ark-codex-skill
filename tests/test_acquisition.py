"""Native acquisition dialog contracts."""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ark_deskpet.acquisition import PetAcquisitionDialog, build_export_command, resolve_repository


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication(["pytest"])


def test_command_uses_argument_vector_without_shell(tmp_path):
    program, args = build_export_command(Path("/venv/bin/python"), Path("/repo/export_pet.py"),
                                         "Amiya;touch", "默认", "基建", "base", 60, tmp_path)
    assert program.endswith("python")
    assert "Amiya;touch" in args and "--fps" in args and "60" in args
    assert all(";" not in arg for arg in args if arg != "Amiya;touch")


def test_values_require_matching_group_pairs(qapp, tmp_path):
    dialog = PetAcquisitionDialog(tmp_path)
    dialog.operator.setText("Texas")
    dialog.pet_name.setText("Texas")
    dialog.model_groups.setText("基建, 正面")
    dialog.export_groups.setText("base")
    with pytest.raises(ValueError, match="数量一致"):
        dialog._values()
    dialog.deleteLater()


def test_values_accept_multiple_groups_and_supported_fps(qapp, tmp_path):
    dialog = PetAcquisitionDialog(tmp_path)
    dialog.operator.setText("Texas")
    dialog.pet_name.setText("Texas")
    dialog.model_groups.setText("基建, 正面")
    dialog.export_groups.setText("base, front")
    dialog.fps.setValue(60)
    values = dialog._values()
    assert values[3] == [("基建", "base"), ("正面", "front")]
    assert values[4] == 60
    dialog.deleteLater()


def test_missing_repository_is_configurable(tmp_path):
    assert resolve_repository(tmp_path) is None
