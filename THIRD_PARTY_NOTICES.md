# 第三方组件声明

本仓库包含或依赖以下第三方组件，其版权归各自作者所有。
本项目自身的代码以 [MIT License](LICENSE) 发布。

---

## 1. vgamepad（已包含在本仓库中）

| | |
|---|---|
| 项目 | [yannbouteiller/vgamepad](https://github.com/yannbouteiller/vgamepad) |
| 作者 | Yann Bouteiller |
| 协议 | MIT License |
| 版权 | Copyright (c) Yann Bouteiller |

本仓库的 `vgamepad/` 目录（`__init__.py`、`vigem_client.py`、`vigem_commons.py`、
`virtual_gamepad.py` 以及 `vigem/ViGEmClient.dll`）是该项目的副本；
`VX360Gamepad.py`、`VDS4Gamepad.py` 也是依据该项目 API 整理的用法示例。

本项目只是为该库套了一层 PySide6 图形界面，**虚拟手柄的全部能力都来自这个库**。
上游的许可证原文见 <https://github.com/yannbouteiller/vgamepad/blob/main/LICENSE>。

---

## 2. ViGEmClient（已包含在本仓库中）

| | |
|---|---|
| 项目 | [nefarius/ViGEmClient](https://github.com/nefarius/ViGEmClient) |
| 作者 | Nefarius Software Solutions e.U. |
| 协议 | MIT License |
| 版权 | Copyright (c) Nefarius Software Solutions e.U. |

文件 `vgamepad/vigem/ViGEmClient.dll` 是 ViGEm Client SDK 编译出的动态库，
由上游 vgamepad 项目一并分发，本仓库原样保留。
上游的许可证原文见 <https://github.com/nefarius/ViGEmClient/blob/master/LICENSE>。

---

## 3. ViGEmBus 驱动（**未包含**在本仓库中）

| | |
|---|---|
| 项目 | [nefarius/ViGEmBus](https://github.com/nefarius/ViGEmBus) |
| 作者 | Nefarius Software Solutions e.U. |
| 协议 | BSD 3-Clause License |
| 版权 | Copyright (c) 2016-2020, Nefarius Software Solutions e.U. |

ViGEmBus 是 Windows 上的内核态驱动，**使用本项目前需要你自行安装**，
它不随本仓库分发，因此本仓库不承担其分发相关的署名义务。
许可证原文见 <https://github.com/nefarius/ViGEmBus/blob/master/LICENSE>。

---

## MIT License 全文

以下许可证适用于上面第 1、2 项组件（各自的版权行见对应章节）：

```
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
