<div align="center">

<img src="./docs/images/ark-codex-deskpet.png" width="160" alt="Ark Codex Deskpet 图标">

# Ark Codex Skill

让《明日方舟》角色陪你写代码。用 Codex 生成透明桌宠，在 Windows 和 Mac 上互动、散步、跟随任务状态。

![Windows 10/11](https://img.shields.io/badge/Windows-10%2F11_x64-0078D4?style=flat-square)
![macOS 13+](https://img.shields.io/badge/macOS-13%2B_Apple_silicon-black?style=flat-square&logo=apple)
[![Release](https://img.shields.io/github/v/release/mikotokuroko/Ark-codex-skill?style=flat-square)](https://github.com/mikotokuroko/Ark-codex-skill/releases)
[![Release downloads](https://img.shields.io/github/downloads/mikotokuroko/Ark-codex-skill/total?style=flat-square&label=downloads)](https://github.com/mikotokuroko/Ark-codex-skill/releases)
[![skills.sh](https://skills.sh/b/mikotokuroko/ark-codex-skill)](https://skills.sh/mikotokuroko/ark-codex-skill)

[下载与安装](#下载与安装) · [使用桌宠](#使用桌宠) · [生成新桌宠](#生成新桌宠) · [开发](#开发)

![德克萨斯「意志」桌宠演示](./docs/images/deskpet-demo.gif)

</div>

给 Codex 一个干员名和皮肤名，skill 会从 PRTS 导出动画，生成透明 PNG 帧并安装到桌宠库。Windows 与 macOS 共用桌宠格式和应用核心。

- **随机散步与休息**：选择附近目的地，走路时播放移动动画，落地后的坐下与放松保持原地。
- **独立重力开关**：开启后松手下落，关闭后停在当前位置。
- **跟随 Codex 活动**：工作时移动、互动，空闲时放松，长时间空闲后睡眠。
- **自由调整外观**：缩放、翻转、透明度、迷你模式、双语字幕与自定义托盘图标。
- **多只桌宠**：切换角色、动画组和可用动作，为每只副本保存位置与大小。
- **桌面交互**：拖动、锁定、点击穿透、全屏隐藏、音效与语音气泡。

发行包内置 **结城理**。其他角色可通过 skill 生成或导入。

## 下载与安装

| 平台 | 下载 | 安装方式 |
|---|---|---|
| Windows 10/11 x64 | [便携 ZIP · 130 MiB](https://github.com/mikotokuroko/Ark-codex-skill/releases/download/v.0.2.3/Ark-Codex-Deskpet-Windows-x64.zip) | 解压整个目录，运行 `Ark Codex Deskpet.exe`。保留旁边的 `_internal` 文件夹。 |
| macOS 13+ Apple silicon | [源码 ZIP · 77.4 MiB](https://github.com/mikotokuroko/Ark-codex-skill/releases/download/v.0.2.3/Ark-Codex-Deskpet-v.0.2.3-source.zip) | 解压后按下方步骤构建并安装。 |

[全部版本](https://github.com/mikotokuroko/Ark-codex-skill/releases) · [Windows 校验文件](https://github.com/mikotokuroko/Ark-codex-skill/releases/download/v.0.2.3/SHA256SUMS-Windows.txt) · [源码校验文件](https://github.com/mikotokuroko/Ark-codex-skill/releases/download/v.0.2.3/SHA256SUMS.txt)

Windows 便携版可直接运行。生成新桌宠或自行构建时，请使用[最新源码](https://github.com/mikotokuroko/Ark-codex-skill/archive/refs/heads/macos.zip)；Windows 环境配置见 [Windows 使用说明](docs/windows.md)。

### macOS 安装

准备 Homebrew Python 3.11 和 Xcode Command Line Tools：

```bash
brew install python@3.11
xcode-select --install
```

在解压后的项目根目录运行：

```bash
./ark-codex-skill/scripts/install_macos.sh
```

安装器创建 Python 环境、构建并本地签名应用，安装到 `~/Applications/Ark Codex Deskpet.app` 后启动。生成素材所需的浏览器也会自动准备。

### 更新

**Windows**：退出桌宠，解压新版 ZIP 并运行。启用了随 Codex 启动时，请保持应用路径一致。

**macOS**：下载最新源码后重新运行安装器；使用 Git 的用户可在仓库目录执行：

```bash
git pull --ff-only origin macos
./ark-codex-skill/scripts/install_macos.sh
```

设置和导入的角色保存在独立的用户目录，更新应用后继续使用。

## 使用桌宠

| 操作 | 效果 |
|---|---|
| 单击 | 播放互动动画 |
| 双击 | 切换迷你模式，显示或隐藏状态条 |
| 解锁后拖动 | 移动桌宠的位置 |
| 右键 | 选择动作、动画组、缩放、翻转、透明度和点击穿透 |
| 菜单栏 / 系统托盘 | 显示桌宠、切换角色、添加副本、打开设置或退出 |

动作菜单包含 **放松、互动、移动、坐下、睡眠**，提供 Special 的角色还会显示 **特殊**。手动选择动作后，播放一个完整周期再恢复自动模式。

### 动作与移动

在 **设置… → 动作与移动** 中调整：

| 设置 | 作用 |
|---|---|
| 自主移动 | 随机散步，穿插放松、坐下和互动 |
| 启用重力 | 松手后落到屏幕底部，可独立开关 |
| 活动频率 | 调整选择新动作的频率，默认 100% |
| 散步比例 | 调整新动作中散步所占比例，默认 60% |
| 散步速度 | 默认 24 px/s，每次散步随机浮动 |
| 最远散步距离 | 限制目的地距离，默认 160 px |
| 最短 / 最长休息 | 设置休息时间范围，默认 8–25 秒 |

桌宠到达目的地或屏幕边界后停下，完成走路动画再休息。点击、手动动作和拖动会接管自主移动。

菜单中的 **Follow Codex activity / 跟随 Codex 活动** 可以与自主移动同时开启。桌宠会根据本机 Codex 任务切换活动状态，空闲五分钟后睡眠，任务开始时唤醒。

**外观与其他** 标签页提供动作倍速、字幕、全屏隐藏、音效、托盘图标和随 ChatGPT/Codex 启动选项。字幕语言可通过 **Language → English / 简体中文** 切换。

## 生成新桌宠

### 安装 Codex skill

使用 Node.js 和 npm：

```bash
npx skills add mikotokuroko/Ark-codex-skill --skill ark-codex-skill --agent codex --global
```

然后对 Codex 说：

```text
用 ark-codex-skill 制作干员 浊心斯卡蒂 的桌宠，皮肤用 升华
```

省略皮肤名时使用原皮。skill 会导出模型支持的动作，并将生成的角色安装到桌宠库。应用菜单中的 **添加桌宠** 也可打开生成工具。

### 命令行生成（macOS）

完成 macOS 安装后，在项目根目录运行：

```bash
.venv-macos/bin/python ark-codex-skill/scripts/export_pet.py \
  "浊心斯卡蒂" --skin "升华" \
  --out "$HOME/Library/Application Support/Ark Codex Deskpet/Exports/skadi-run"

.venv-macos/bin/python ark-codex-skill/scripts/install_pet_macos.py \
  "$HOME/Library/Application Support/Ark Codex Deskpet/Exports/skadi-run/pet" \
  --name "浊心斯卡蒂"
```

导出参数和离线素材处理见[直接导出说明](ark-codex-skill/references/direct-export.md)，Windows 步骤见[生成新桌宠](docs/windows.md#generate-new-pets)。

## 数据与卸载

| 平台 | 设置和用户桌宠 | 日志 |
|---|---|---|
| Windows | `%LOCALAPPDATA%\Ark Codex Deskpet\` | 同目录下的 `Logs\` |
| macOS | `~/Library/Application Support/Ark Codex Deskpet/` | `~/Library/Logs/Ark Codex Deskpet/` |

用户桌宠放在 `Pets` 子目录，同名时优先使用用户版本。

Windows 卸载：在设置中关闭随 Codex 启动，退出应用并删除应用文件夹。

macOS 卸载：

```bash
./ark-codex-skill/scripts/uninstall_macos.sh
```

普通卸载保留设置和角色；添加 `--purge-data` 会一并删除这些数据。

## 开发

两个平台共用 `ark-codex-skill/assets/deskpet-app-macos/ark_deskpet/` 中的运行时。Windows 系统集成位于 `windows_platform.py`，原始 Windows 模板保留在 `assets/deskpet-app/`。

| 目录 | 内容 |
|---|---|
| `ark-codex-skill/scripts/` | 动画导出、桌宠安装和应用安装脚本 |
| `ark-codex-skill/references/` | PRTS 导出与素材处理说明 |
| `packaging/` | macOS / Windows 构建配置 |
| `tests/` | 动作、移动、设置、状态检测和平台集成测试 |
| `docs/` | 平台指南与实现说明 |

macOS 测试：

```bash
QT_QPA_PLATFORM=offscreen .venv-macos/bin/python -m pytest -q
```

Windows 构建（Python 3.11）：

```powershell
.\packaging\build_windows.ps1
```

[Windows 构建工作流](.github/workflows/windows-build.yml) 会执行功能与原生测试、构建可执行文件，并检查打包程序的启动和命令通道。

## 常见问题

**桌宠不见了，或误开点击穿透？** 通过菜单栏 / 系统托盘选择“显示桌宠”，也可以重新打开应用来恢复显示和鼠标操作。

**Mac 上没有 Dock 图标？** 桌宠通过菜单栏图标管理。右键 → 设置可更换或隐藏该图标。

**PRTS 导出失败？** 查看[导出说明](ark-codex-skill/references/direct-export.md)和[查看器排查](ark-codex-skill/references/prts-ui.md)。

**安装统计如何设置？** 可选统计默认关闭，设置方式见[统计说明](docs/adoption-metrics.md#private-opt-in-counters)。

动画来源：[PRTS Wiki](https://prts.wiki/)。角色素材归原权利方所有，详见[素材说明](docs/pet-assets.md)。

<div align="center">

博士如果喜欢的话，给 repo 点个 star 🌟

</div>
