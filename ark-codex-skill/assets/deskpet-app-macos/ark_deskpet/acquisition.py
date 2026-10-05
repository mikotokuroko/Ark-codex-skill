"""Native dialog for acquiring PRTS pets through the existing exporter."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from .pet_install import install_pet, validate_pet_name


def resolve_repository(configured: str | Path | None = None) -> tuple[Path, Path] | None:
    """Find the repository venv and exporter, without assuming a Claude path."""
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    if os.environ.get("ARK_CODEX_REPO"):
        candidates.append(Path(os.environ["ARK_CODEX_REPO"]).expanduser())
    here = Path(__file__).resolve()
    candidates.extend(here.parents)
    for root in candidates:
        script = root / "ark-codex-skill" / "scripts" / "export_pet.py"
        python = root / ".venv-macos" / "bin" / "python"
        if script.is_file() and python.is_file():
            return python, script
    return None


def build_export_command(python: Path, script: Path, operator: str, skin: str,
                         model_group: str, group: str, fps: int, output: Path) -> tuple[str, list[str]]:
    """Build an argument-vector command; values never pass through a shell."""
    return str(python), [str(script), operator, "--skin", skin, "--model-group",
                         model_group, "--group", group, "--fps", str(fps),
                         "--out", str(output)]


class PetAcquisitionDialog(QDialog):
    """Nonblocking multi-group acquisition and atomic installation dialog."""

    def __init__(self, library: Path, parent=None, repo_path: str | Path | None = None,
                 on_complete: Callable[[Path], None] | None = None):
        super().__init__(parent)
        self.setWindowTitle("添加桌宠")
        self.library = Path(library)
        self.on_complete = on_complete
        self._process: QProcess | None = None
        self._stage: Path | None = None
        self._jobs: list[tuple[str, str]] = []
        self._job_index = 0
        self._output = ""

        self.operator = QLineEdit(); self.operator.setPlaceholderText("例如 Texas")
        self.skin = QLineEdit("默认")
        self.pet_name = QLineEdit(); self.pet_name.setPlaceholderText("安装后的桌宠名称")
        self.model_groups = QLineEdit("基建")
        self.export_groups = QLineEdit("base")
        self.fps = QSpinBox(); self.fps.setRange(20, 60); self.fps.setSingleStep(40); self.fps.setValue(20)
        self.repository = QLineEdit(str(repo_path or os.environ.get("ARK_CODEX_REPO", "")))
        browse = QPushButton("选择")
        browse.clicked.connect(self.choose_repository)
        self.status = QLabel("填写信息后开始导出")
        self.status.setWordWrap(True)
        form = QFormLayout()
        form.addRow("干员", self.operator); form.addRow("时装", self.skin)
        form.addRow("桌宠名称", self.pet_name)
        form.addRow("模型组（逗号分隔）", self.model_groups)
        form.addRow("导出组名（对应顺序）", self.export_groups)
        form.addRow("帧率", self.fps)
        repo_row = QHBoxLayout(); repo_row.addWidget(self.repository); repo_row.addWidget(browse)
        form.addRow("工具仓库", repo_row)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.buttons.button(QDialogButtonBox.Ok).setText("开始导出")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.buttons.accepted.connect(self.start)
        self.buttons.rejected.connect(self.cancel)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addWidget(self.status); layout.addWidget(self.buttons)

    def choose_repository(self):
        selected = QFileDialog.getExistingDirectory(self, "选择 Ark Codex 仓库")
        if selected: self.repository.setText(selected)

    def _values(self):
        operator = self.operator.text().strip(); skin = self.skin.text().strip() or "默认"
        name = validate_pet_name(self.pet_name.text())
        models = [x.strip() for x in self.model_groups.text().split(",") if x.strip()]
        groups = [x.strip() for x in self.export_groups.text().split(",") if x.strip()]
        if not operator or not models or len(models) != len(groups):
            raise ValueError("干员、模型组和导出组必须填写，且两组数量一致")
        if any("/" in x or "\\" in x or x in {".", ".."} for x in groups):
            raise ValueError("导出组名不能包含路径分隔符")
        if self.fps.value() not in (20, 60): raise ValueError("帧率必须为 20 或 60")
        return operator, skin, name, list(zip(models, groups)), self.fps.value()

    def start(self):
        if self._process is not None: return
        try: operator, skin, name, jobs, fps = self._values()
        except ValueError as error:
            QMessageBox.warning(self, "无法开始", str(error)); return
        resolved = resolve_repository(self.repository.text().strip() or None)
        if not resolved:
            self.status.setText("找不到 .venv-macos 或 export_pet.py，请选择正确的工具仓库")
            return
        self._jobs = jobs; self._job_index = 0; self._output = ""
        self._operator, self._skin, self._name, self._fps = operator, skin, name, fps
        self._stage = Path(tempfile.mkdtemp(prefix=".ark-pet-acquire-")) / name
        existing = self.library / name
        if existing.is_dir(): shutil.copytree(existing, self._stage, dirs_exist_ok=True)
        else: self._stage.mkdir(parents=True)
        self._python, self._script = resolved
        self._start_next()

    def _start_next(self):
        if self._job_index >= len(self._jobs): return self._install()
        model, group = self._jobs[self._job_index]; self._job_index += 1
        program, args = build_export_command(self._python, self._script, self._operator,
                                             self._skin, model, group, self._fps, self._stage)
        self.status.setText(f"正在导出 {group}…")
        self._process = QProcess(self); self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read_output)
        self._process.finished.connect(self._finished)
        self._process.start(program, args)

    def _read_output(self):
        if self._process: self._output += bytes(self._process.readAllStandardOutput()).decode(errors="replace")

    def _finished(self, code, _status):
        self._read_output(); process = self._process; self._process = None
        if code != 0:
            detail = "PRTS 拒绝了请求（HTTP 403），请检查网络或访问权限。" if "403" in self._output else self._output[-800:]
            self.status.setText(f"导出失败：{detail}"); process.deleteLater(); self._cleanup(); return
        process.deleteLater(); self._start_next()

    def _install(self):
        try:
            target = install_pet(self._stage, self.library, self._name, notifier=None)
        except Exception as error:
            self.status.setText(f"安装失败：{error}"); self._cleanup(); return
        self.status.setText("导出并安装完成"); self._cleanup()
        if self.on_complete: self.on_complete(target)
        self.accept()

    def cancel(self):
        if self._process:
            self._process.kill(); self._process = None
        self._cleanup(); self.reject()

    def _cleanup(self):
        if self._stage:
            shutil.rmtree(self._stage.parent, ignore_errors=True); self._stage = None

    def closeEvent(self, event):
        self.cancel(); event.accept()
