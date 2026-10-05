# VGamepad 虚拟手柄面板

在 Windows 桌面上放一个悬浮小面板，用鼠标直接操作**虚拟 Xbox 360 / DualShock 4 手柄**。
给不支持手柄的游戏、或者需要模拟手柄输入的脚本喂输入用。

> ## ⚠️ 免责声明
>
> 本项目的 `vgamepads.py` 代码**完全由 AI 编写、也完全由 AI 测试**。
> **不保证完全可用**，也不保证在你的机器、你的游戏上表现一致。请自行评估风险后再使用。

---

## 功能

- **两种手柄**：Xbox 360（默认）和 DualShock 4，随时切换，托盘图标跟着变绿 / 变蓝
- **两种界面**
  - **单摇杆**（默认）：只有一个左摇杆，纯裸摇杆不带底板，适合当悬浮摇杆用
  - **全按键**：肩键、扳机、十字键、动作键、功能键、左右摇杆一应俱全
- **托盘常驻**：启动后窗口是隐藏的，不占屏幕
- **自动显隐**：配置好进程列表后，目标进程切到前台自动显示、切走自动隐藏
- **不抢游戏焦点**：窗口带 `WS_EX_NOACTIVATE`，点面板不会把游戏切到后台
- **配置持久化**：手柄型号、界面布局、自动显隐开关、进程列表都存在 `config.ini`

## 运行环境

| 项目 | 说明 |
|---|---|
| 系统 | Windows 11 x64（未在其它 Windows 版本上测试） |
| Python | 3.10 及以上（开发环境 3.14.7） |
| PySide6 | 6.x（开发环境 6.11.2） |
| 驱动 | [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases) —— **必须安装**，否则程序无法创建虚拟手柄 |

## 快速开始

有两种用法，选一种即可。

### 方式一：直接下载本仓库运行

仓库里已经带了 [yannbouteiller/vgamepad](https://github.com/yannbouteiller/vgamepad) 库的副本，
不需要额外准备什么，克隆或下载解压后：

```bash
pip install PySide6
python vgamepads.py
```

### 方式二：自己装好 vgamepad 库，只跑 vgamepads.py

如果你已经装过 [yannbouteiller/vgamepad](https://github.com/yannbouteiller/vgamepad)
（这个库的 pip 安装脚本会自动帮你安装 ViGEmBus 驱动）：

```bash
pip install vgamepad PySide6
python vgamepads.py
```

这种方式下**只留 `vgamepads.py` 一个文件就够了**，仓库里的 `vgamepad/` 目录可以删掉，
程序会自动改用你已安装的库。反过来，如果 `vgamepad/` 目录还在，程序优先用它。

> 无论哪种方式，都要确保 **ViGEmBus 驱动已经安装**；没有它程序会在启动时弹窗提示。

### 启动之后

1. **窗口默认是隐藏的**，右下角托盘会出现一个小圆点：Xbox 360 是绿色，DualShock 4 是蓝色。
2. **左键单击这个圆点**就能把面板调出来，再点一下收起。
3. 想让它随游戏自动显隐，就编辑 `config.ini` 里的进程列表（见下文）。

不想看到控制台黑窗口的话，用 `pythonw vgamepads.py` 启动。

## 使用说明

### 托盘图标

| 操作 | 效果 |
|---|---|
| 左键单击 | 显示 / 隐藏面板（立即响应） |
| 右键单击 | 弹出菜单 |
| 鼠标悬停 | 分三行显示当前手柄、当前布局、当前显隐模式 |

### 托盘菜单

```
切换手柄
──────────────
全按键
单摇杆
──────────────
自动显隐 / 手动显隐
──────────────
退出
```

菜单项不带勾选状态。其中「自动显隐 / 手动显隐」一项的文字表示**点下去会切到哪种模式**：

- 现在显示「自动显隐」→ 当前是手动模式，点一下开始检测进程；
- 现在显示「手动显隐」→ 当前是自动模式，点一下停止检测。

### 面板操作

- **移动窗口**：拖动顶部标题栏（全按键模式）或顶部小圆点（单摇杆模式）。
- 窗口默认出现在**屏幕下方居中**；手动拖动过之后就不再自动归位。
- **摇杆**：鼠标拖动，松手自动回正；只有按在底座圆内才算抓住摇杆。
- **扳机**：拖动滑块，松手自动归零。

## config.ini

程序首次运行会在脚本同目录自动生成这个文件。
程序**只修改具体的值，不会重写整个文件** —— 你自己加的注释、空行和自定义配置项都会保留。

```ini
[general]
; 手柄型号：xbox360 = Xbox 360 手柄；ds4 = DualShock 4 手柄
gamepad = xbox360
; 界面布局：full = 全按键；stick = 单摇杆（只有左摇杆）
layout = stick
; 自动显隐：true = 按下面的进程列表自动显示/隐藏；false = 手动显隐（不做任何检测）
auto_show = false

[processes]
; 需要检测的进程名，每行一个，不区分大小写
; 写文件名（aaa.exe）或完整路径（D:\Games\aaa.exe）都行
; 列表里的进程在前台运行时显示手柄，切到后台自动隐藏
game.exe
aaa.exe
D:\Steam\steamapps\common\bbb\bbb.exe
```

> 注释请**单独占一行**（以 `;` 或 `#` 开头）。程序按标准 ini 解析，不支持写在值后面的行内注释。

> 这个文件存的是每个用户自己的配置（尤其是进程列表），已经加进 `.gitignore`，不会提交到仓库。

### 自动显隐的工作方式

开启后分两级检测，在实时性和系统开销之间取平衡：

- 列表里的进程**一个都没在运行时**：每 **5 秒**才枚举一次进程，几乎不占资源；
- 一旦发现目标进程**在运行**：切到每 **300 毫秒**检测一次前台窗口，目标进程在前台就显示面板、切走就隐藏；
- 高频检测期间每约 6 秒做一次完整枚举，目标进程退出后自动退回低频检测。

另外，自动模式下**单击托盘图标会先切回手动模式**，否则下一次检测会立刻把面板藏回去。

## 目录结构

```
vgamepads.py                 主程序，全部功能都在这一个文件里
config.ini                   配置文件，首次运行自动生成（已被 .gitignore 忽略）
VX360Gamepad.py              Xbox 360 全部按键的用法示例
VDS4Gamepad.py               DualShock 4 全部按键的用法示例
vgamepad/                    第三方库副本（yannbouteiller/vgamepad），装了库的话可以删
└── vigem/ViGEmClient.dll    ViGEm 客户端动态库
```

## 依赖与致谢

本项目的虚拟手柄能力完全来自下面这些项目，在此表示衷心感谢：

- **[yannbouteiller/vgamepad](https://github.com/yannbouteiller/vgamepad)** —— 作者 **Yann Bouteiller**。
  本项目依赖的 Python 库，提供了操作虚拟手柄的整套 API；`vgamepad/` 目录就是它的副本，
  `VX360Gamepad.py`、`VDS4Gamepad.py` 两个示例文件也基于它的用法整理。
  **感谢作者的出色工作 —— 这个项目只是给这个库套了一层图形界面而已。**
  MIT License。
- **[nefarius/ViGEmClient](https://github.com/nefarius/ViGEmClient)** —— 作者 **Nefarius Software Solutions e.U.**。
  `vgamepad/vigem/ViGEmClient.dll` 来自这个项目。MIT License。
- **[nefarius/ViGEmBus](https://github.com/nefarius/ViGEmBus)** —— 作者 **Nefarius Software Solutions e.U.**。
  Windows 上的虚拟手柄驱动，正是它让"虚拟手柄"这件事成立。BSD 3-Clause License，
  需要你自行安装，未包含在本仓库中。

三方组件的完整版权声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 开源协议

[MIT License](LICENSE)，与上游项目
[yannbouteiller/vgamepad](https://github.com/yannbouteiller/vgamepad) 保持一致。

---

## English

A small always-on-top panel that lets you drive a **virtual Xbox 360 / DualShock 4 gamepad**
on Windows with the mouse. Built with PySide6 on top of
[yannbouteiller/vgamepad](https://github.com/yannbouteiller/vgamepad).

> **Disclaimer:** `vgamepads.py` was **written and tested entirely by AI**.
> It is **not guaranteed to be fully functional** — use it at your own risk.

**Requirements:** Windows 11 x64, Python 3.10+, PySide6, and the
[ViGEmBus](https://github.com/nefarius/ViGEmBus/releases) driver (mandatory).

**Two ways to run:**

1. **Download this repo** — it bundles a copy of the `vgamepad` library:
   `pip install PySide6` then `python vgamepads.py`.
2. **Bring your own library** — install [yannbouteiller/vgamepad](https://github.com/yannbouteiller/vgamepad)
   (`pip install vgamepad PySide6`), then run `python vgamepads.py`. In this case the bundled
   `vgamepad/` folder can be deleted.

Use `pythonw vgamepads.py` for no console window.
The panel starts hidden — **left-click the tray dot** to show it, **right-click** for the menu.
Settings live in `config.ini`.

**License:** [MIT](LICENSE). The bundled `vgamepad/` package is a copy of
yannbouteiller/vgamepad (MIT, Copyright (c) Yann Bouteiller); see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for details.
