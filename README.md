<div align="center">

<img src="./docs/images/ark-codex-deskpet.png" width="160"
alt="Ark Codex Deskpet 图标">

# Ark Codex Skill

用 Codex 制作《明日方舟》透明桌宠，支持 Windows 和 Apple silicon Mac。

![macOS 13+](https://img.shields.io/badge/macOS-13%2B-black?style=flat-square&logo=apple)
![Apple silicon](https://img.shields.io/badge/Apple%20silicon-arm64-black?style=flat-square&logo=apple)
![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
[![Release](https://img.shields.io/github/v/release/mikotokuroko/Ark-codex-skill?include_prereleases&style=flat-square)](https://github.com/mikotokuroko/Ark-codex-skill/releases)
[![Release downloads](https://img.shields.io/github/downloads/mikotokuroko/Ark-codex-skill/total?style=flat-square&label=downloads)](https://github.com/mikotokuroko/Ark-codex-skill/releases)
[![skills.sh](https://skills.sh/b/mikotokuroko/ark-codex-skill)](https://skills.sh/mikotokuroko/ark-codex-skill)

[平台支持](#平台支持) · [功能特性](#功能特性) · [macOS 安装](#macos-安装) ·
[生成桌宠](#生成新桌宠) · [本地开发](#本地开发)

</div>

给 Codex 一个干员名和可选皮肤名，它会从 PRTS Wiki 导出基建动画，
转换成透明 PNG 帧，生成 `manifest.json`，并安装到正在运行的桌宠库。

项目同时提供原始 Windows 模板和独立的 macOS 桌宠应用。
Windows 与 macOS 生成的桌宠可以相互使用。

> [!NOTE]
> macOS 应用使用本机 ad-hoc 签名，面向本地安装和个人使用。
> 它不是 App Store 或公证发行包。

## 下载与安装 / Downloads and skill installation

[下载 v0.2.2-beta.1 完整源码包](https://github.com/mikotokuroko/Ark-codex-skill/releases/download/v0.2.2-beta.1/Ark-Codex-Deskpet-v0.2.2-beta.1-source.zip) · [全部版本](https://github.com/mikotokuroko/Ark-codex-skill/releases)

这是包含 skill、动画素材和构建文件的源码 ZIP，不是预编译应用。解压后，在项目根目录运行
`./ark-codex-skill/scripts/install_macos.sh`。请先满足下方的 macOS 环境要求。
保留解压后的项目目录，其中的 `.venv-macos` 也用于生成桌宠。

通过 skills.sh 为 Codex 安装 skill（需要 Node.js 和 npm）：

```bash
npx skills add mikotokuroko/Ark-codex-skill --skill ark-codex-skill --agent codex --global
```

该命令安装 skill 及其脚本和素材；macOS 应用仍需使用完整源码包单独安装。
若已有同名 skill，请先备份自己的修改，再确认替换。

## 平台支持

| 平台 | 支持状态 | 运行方式 |
|---|---|---|
| Windows 10/11 | 支持 | Python 本地模板和 `.bat` 启动脚本 |
| macOS 13+ Apple silicon | 支持 | ad-hoc 签名的本地 `.app` |
| Linux | 仅素材处理 | 可运行导出和转换脚本，不包含桌宠应用 |

## 功能特性

* 透明、无边框、始终置顶的桌宠窗口，不显示普通 Dock 图标
* 以 20 FPS 播放待机、互动、移动、坐下、睡眠和可选 Special 动画
* 可选“跟随 Codex 活动”：忙碌时移动与互动，空闲时以放松为主，五分钟后睡眠
* 支持单击互动、拖动、缩放、锁定、迷你模式和全屏自动隐藏
* 按角色保存位置、大小、动作倍速和选中状态
* 支持 Unicode 角色名，以及内置和用户桌宠库合并
* 中文右键菜单、设置窗口和菜单栏图标
* 使用 macOS 系统字体与原生明暗配色显示状态字幕，默认语言为英文
* 菜单栏提供显示、隐藏、桌宠库、字幕语言、设置、随 Codex 启动和退出
* 只读解析 `~/.codex/sessions/`，区分运行、等待输入、空闲和错误状态
* 支持多显示器，并自动找回落在屏幕外的桌宠位置
* 使用单实例 IPC，支持实时显示、隐藏、退出和刷新桌宠库
* 使用 macOS 应用事件监听 ChatGPT/Codex，不持续轮询进程
* 全屏检测不申请屏幕录制或辅助功能权限

macOS 应用内置予愿安洁莉娜及下列桌宠，安装后可在桌宠库切换。菜单栏使用 `docs/images/icon` 提供的角色图标。

| 桌宠 | 动画 | 来源 |
|---|---|---|
| 德克萨斯「意志」 | Relax、Interact、Move、Sit、Sleep、Special | [PRTS](https://prts.wiki/w/德克萨斯) |
| 结城理（默认服装） | Relax、Interact、Move、Sit、Sleep（此模型无 Special） | [PRTS](https://prts.wiki/w/结城理) |
| 丰川祥子「旋律的主人」 | Relax、Interact、Move、Sit、Sleep、Special | [PRTS](https://prts.wiki/w/丰川祥子) |
| 若叶睦「提线的本我」 | Relax、Interact、Move、Sit、Sleep、Special | [PRTS](https://prts.wiki/w/若叶睦) |
| 隐德来希「耀目之蓝」 | Relax、Interact、Move、Sit、Sleep、Special | [PRTS](https://prts.wiki/w/隐德来希) |

新增素材位于 `ark-codex-skill/assets/deskpet-app-macos/pets/`，构建时自动打包。
用户安装的同名桌宠仍优先于内置版本。


## macOS 环境要求

* Apple silicon Mac（`arm64`）
* macOS 13 或更高版本
* [Homebrew Python 3.11][python]
* Xcode Command Line Tools
* 可访问 PRTS Wiki 和 Python 软件包源

准备本机工具：

```bash
brew install python@3.11
xcode-select --install
```

Google Chrome 或 Chromium 可用于桌宠生成。
如果两者都未安装，安装器会把 Playwright Chromium 下载到仓库本地目录，
不会把浏览器打包进桌宠应用。

## macOS 安装

克隆或下载仓库后，在仓库根目录运行：

```bash
./ark-codex-skill/scripts/install_macos.sh
```

安装器会：

1. 检查 macOS、arm64、Python 3.11 和 Xcode Command Line Tools。
1. 重建仓库本地的 `.venv-macos`，并安装固定版本依赖。
1. 使用 PyInstaller 构建应用和后台 watcher。
1. 验证 arm64 架构、属性列表和签名。
1. ad-hoc 签名并安装到 `~/Applications/Ark Codex Deskpet.app`。
1. 启动应用，首次安装时保持登录启动关闭。

> [!IMPORTANT]
> 重复运行安装器只会安全替换已安装的 `.app`。
> 设置和用户生成的桌宠不会被删除。

所有 Python 依赖和 Playwright 浏览器都留在仓库本地，pip 缓存默认禁用。
安装过程不需要管理员权限。

## 使用桌宠

![德克萨斯「意志」桌宠动画演示](./docs/images/deskpet-demo.gif)

* **单击桌宠**：播放互动动画
* **双击桌宠**：切换迷你模式，隐藏或显示 Codex 状态条
* **拖动桌宠**：先在右键菜单选择“解锁拖动”，拖动时播放移动动画
* **右键桌宠**：选择当前角色的全部可用动作，或切换桌宠、缩放、锁定或退出
* **点击菜单栏图标**：显示桌宠
* **打开菜单栏菜单**：隐藏桌宠、切换角色、更改字幕语言、打开设置或退出

动作菜单使用双语标签：**放松/relax、互动/interact、移动/move、坐下/sit、睡眠/sleep**。
有 Special 的角色还会显示 **特殊/special**。右键菜单可直接选择，菜单栏菜单中
通过 **动画/animations** 子菜单选择；播放完整一次后恢复当前自动模式。

菜单栏和桌宠右键菜单中的 **Follow Codex activity / 跟随 Codex 活动**
控制自动动作，默认关闭；设置会保存并应用于所有角色。

| 模式 | 动作 |
| --- | --- |
| 关闭 | 默认放松；点击、拖动和手动选择动作仍可使用，不会自动坐下或睡觉 |
| 空闲不足五分钟 | 放松 45–90 秒，再完整播放一次互动、坐下、短暂睡眠或 Special（若有），然后返回放松 |
| 连续空闲五分钟 | 当前动作周期结束后持续睡眠 |
| Codex 正在运行任务 | 移动 10–20 秒，再完整播放一次互动，循环进行 |

放松之间的动作概率为互动 50%、坐下 30%、睡眠 10%、Special 10%；
角色没有 Special 时，其概率按比例分配给其他动作。
任一本机受监控任务运行时，都使用运行模式；等待输入、错误和 Codex 关闭视为空闲。
任务开始会立即唤醒睡眠，其他动作在当前周期结束后切换。
手动操作会暂时接管动作，完成后重新计算空闲时间并恢复自动模式。
动作播放倍速不改变上述等待时间。

状态字幕默认使用英文，并根据 Codex 的任务事件显示：

| 状态 | 英文字幕 | 含义 |
|---|---|---|
| 空闲 | `Codex Idle` | 当前没有正在处理的任务 |
| 运行 | `Codex Running` | Codex 正在处理任务 |
| 等待输入 | `Waiting for Input` | 上一轮已完成，等待用户继续输入 |
| 错误 | `Codex Error` | 任务异常中止或失败 |

要切换字幕语言，请打开 macOS 菜单栏中的桌宠图标，选择
**Language → English** 或 **Language → 简体中文**。
切换会立即生效，并保存在应用设置中供下次启动使用。

在设置中可以调整动作倍速、字幕长度、字幕大小、字条长度、
迷你模式、全屏自动隐藏和“随 ChatGPT/Codex 启动”。

登录启动默认关闭。
启用后，应用只会安装当前用户的 LaunchAgent，不需要管理员权限。

## 生成新桌宠

### 使用 Codex skill

先让 Codex 安装当前仓库中的 `ark-codex-skill/` skill，然后直接说：

```text
用 ark-codex-skill 制作干员 浊心斯卡蒂 的桌宠
```

指定皮肤：

```text
用 ark-codex-skill 制作干员 浊心斯卡蒂 的桌宠，皮肤用 升华
```

不写皮肤时默认使用原皮。
完整流程直接导出 `Interact / Move / Relax / Sit / Sleep`，存在 `Special` 时也会导出。
先验证模型版本和测试帧，再生成固定时间戳的透明 PNG；任何必需或已发现动作失败都会报告。

### 在 macOS 手动运行生成流程

```bash
.venv-macos/bin/python ark-codex-skill/scripts/export_pet.py \
  "浊心斯卡蒂" --skin "升华" \
  --out "$HOME/Library/Application Support/Ark Codex Deskpet/Exports/skadi-run"

.venv-macos/bin/python ark-codex-skill/scripts/install_pet_macos.py \
  "$HOME/Library/Application Support/Ark Codex Deskpet/Exports/skadi-run/pet" \
  --name "浊心斯卡蒂"
```

安装脚本会验证清单和每张 PNG，原子替换同名用户桌宠，
排除原始 WebM，并通知正在运行的应用刷新桌宠库。
不需要重新构建 `.app`。

> [!TIP]
> 直接导出与版本兼容排查见 `ark-codex-skill/references/direct-export.md`。
> PRTS 返回 HTTP 403 时会报告失败；已有下载素材可通过 `--source` 离线重现。
> 浏览器查看器仅作为显式后备方案。

## macOS 数据存储

应用包按只读资源处理。
设置、生成内容、运行状态和日志分别保存在：

| 内容 | 路径 |
|---|---|
| 设置和用户桌宠 | `~/Library/Application Support/Ark Codex Deskpet/` |
| 运行状态和 IPC | `~/Library/Caches/Ark Codex Deskpet/` |
| 应用与 watcher 日志 | `~/Library/Logs/Ark Codex Deskpet/` |

用户桌宠与内置桌宠同名时，用户版本优先。
设置文件通过临时文件和原子替换写入。

## macOS 卸载

普通卸载会移除应用、LaunchAgent、缓存和日志，保留设置和用户桌宠：

```bash
./ark-codex-skill/scripts/uninstall_macos.sh
```

只有显式指定 `--purge-data` 才会删除设置和桌宠：

```bash
./ark-codex-skill/scripts/uninstall_macos.sh --purge-data
```

> [!WARNING]
> `--purge-data` 会永久删除
> `~/Library/Application Support/Ark Codex Deskpet/`。

## macOS 工作原理

桌宠主程序使用 PySide6 绘制透明窗口，并通过 `QLocalServer` 保证单实例。
用户命令通过用户缓存目录中的本地 socket 发送。
状态条读取 Codex 会话的任务开始、完成、中止和失败事件，并忽略内部审批
审查会话，避免把内部状态显示给用户。
活动检测只监控当前 `com.openai.codex` 启动期间的本机任务；多个任务中任一运行
即保持忙碌，长时间没有新日志不会让任务提前变为空闲。旧启动记录不会显示为当前任务。

独立 watcher 使用 AppKit `NSWorkspace` 的应用启动和退出通知，识别：

* Bundle ID：`com.openai.codex`
* 应用名后备：`ChatGPT`、`Codex`

watcher 只会关闭由自己启动的桌宠。
手动启动的桌宠不会被 watcher 接管。

全屏自动隐藏通过 AppKit 获取前台应用，再使用 Core Graphics 比较普通窗口
与桌宠所在显示器的边界。
如果 macOS 没有提供足够元数据，桌宠会保持可见并只记录一次诊断信息。

## 目录结构

```text
Ark-codex-macos/
├── ark-codex-skill/
│   ├── SKILL.md
│   ├── assets/
│   │   ├── deskpet-app/          # 原始 Windows 模板
│   │   └── deskpet-app-macos/    # macOS 应用模板
│   ├── references/
│   └── scripts/
│       ├── install_macos.sh
│       ├── uninstall_macos.sh
│       ├── install_pet_macos.py
│       ├── prts_export.py
│       └── process_webm.py
├── docs/images/
├── packaging/                    # PyInstaller、Info.plist、LaunchAgent
├── tests/
└── requirements-macos.txt
```

## 本地开发

安装器会创建完整开发环境。
构建、签名、安装和启动：

```bash
./ark-codex-skill/scripts/install_macos.sh
```

运行自动化测试：

```bash
QT_QPA_PLATFORM=offscreen .venv-macos/bin/pytest -q
```

当前测试覆盖清单校验、Unicode 名称、桌宠库合并、语言设置迁移与原子写入、
Codex 会话状态解析、内部审查过滤、watcher 生命周期、IPC、过期 socket、多显示器、
全屏回退、桌宠安装和无损重装，也覆盖自动动作的时间与概率、手动覆盖、
双菜单设置同步、并发任务、旧启动记录、非有限时间戳与 Special 素材校验。

安装器会自动运行以下构建验证：

```bash
plutil -lint
codesign --verify --deep --strict
file
lipo -info
```

## Windows 使用

原始 Windows 模板保留在 `ark-codex-skill/assets/deskpet-app/`，
没有被 macOS 实现重构或替换。

两个平台继续使用相同的 `manifest.json` schema 和 PNG 帧目录结构，
因此生成的桌宠可以跨平台复制。

创建并启动 Windows 桌宠项目：

```bash
python ark-codex-skill/scripts/scaffold_deskpet.py \
  --target my-deskpet --pet "予愿安洁莉娜"
python ark-codex-skill/scripts/setup_env.py my-deskpet
my-deskpet/启动桌宠.bat
```

Windows 版本继续提供托盘、快捷方式、桌宠库和随 ChatGPT/Codex 启动。

## 常见问题

### 为什么 Dock 中没有应用图标？

这是预期行为。
应用设置了 `LSUIElement`，请使用 macOS 菜单栏图标管理桌宠。

### 打开后没有看到桌宠

先从菜单栏选择“显示桌宠”。
如果仍未出现，请查看：

```text
~/Library/Logs/Ark Codex Deskpet/deskpet.log
```

### PRTS 导出失败或找不到按钮

PRTS 页面改版可能影响自动化选择器。
请对照 `ark-codex-skill/references/prts-ui.md` 检查当前 DOM。

### 重装或卸载会删除我的桌宠吗？

不会。
重装和普通卸载都会保留 Application Support 中的设置和用户桌宠。
只有 `uninstall_macos.sh --purge-data` 会删除它们。

## 素材说明

> [!CAUTION]
> 《明日方舟》素材版权归 Hypergryph 所有，PRTS 资料遵循其站内许可。
> 本项目仅用于个人学习与自用，请勿用于商业发布。

<div align="center">

博士如果喜欢的话给repo点个star🌟 🥺

Tell Me👏 Tell Me👏嘎嘎米⭐️哟嘎嘎米⭐️  
一番👏好きな👏私👏👏になるの👏👏

</div>

[python]: https://formulae.brew.sh/formula/python@3.11
