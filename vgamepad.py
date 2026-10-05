# -*- coding: utf-8 -*-
"""vgamepad.py —— 虚拟手柄可视化控制面板（PySide6 + ViGEmBus）。

本文件把原来的 virtual_controller.py（全按键面板）和 virtual_left_joystick.py
（单左摇杆）合并重构为一个可切换布局的应用：

* 托盘常驻，启动时窗口隐藏；
* 单击托盘图标切换显示/隐藏，双击（或右键）弹出托盘菜单；
* 手柄型号（Xbox 360 / DualShock 4）与界面布局（全按键 / 单摇杆）随时可切；
* 自动显隐：config.ini 里列出的进程在前台时自动显示，否则自动隐藏；
* 所有配置保存在脚本同目录的 config.ini，窗口位置不保存。

注意：本文件与同目录下的 vgamepad/ 包同名。Python 的模块查找顺序里“包目录”
优先于同名 .py 文件，而本文件是以 __main__ 身份运行的，所以下面的
``import vgamepad`` 导入的是 vgamepad/ 包，两者不会冲突。

运行环境：Windows 11 x64 + 最新版 Python / PySide6。
"""

import configparser
import ctypes
import logging
import math
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

try:  # ViGEmBus 没装时，import 阶段就会抛异常
    import vgamepad as vg
except Exception as exc:  # pragma: no cover - 取决于本机环境
    vg = None
    VG_IMPORT_ERROR: Exception | None = exc
else:
    VG_IMPORT_ERROR = None


# ==========================================================================
# 常量与日志
# ==========================================================================

APP_NAME = "VGamepad"

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.ini"

#: 手柄型号
TYPE_XBOX360 = "xbox360"
TYPE_DS4 = "ds4"

#: 界面布局
LAYOUT_FULL = "full"    # 全按键
LAYOUT_STICK = "stick"  # 单摇杆

#: 布局的中文名（菜单与托盘提示共用，避免两处各写一份）
LAYOUT_TITLES = {LAYOUT_FULL: "全按键", LAYOUT_STICK: "单摇杆"}

#: 摇杆左右
SIDE_LEFT = "left"
SIDE_RIGHT = "right"

log = logging.getLogger("vgamepad")


def _setup_logging() -> None:
    """配置日志。用 pythonw 启动时没有 stderr，直接跳过。"""
    if sys.stderr is None:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


# ==========================================================================
# config.ini 读写
# ==========================================================================

DEFAULT_CONFIG_TEXT = """\
; ==========================================================================
; VGamepad 配置文件（UTF-8）
; 本文件由程序自动维护：改完数值保存即可，注释和自定义内容都会被保留。
; ==========================================================================

[general]
; 手柄型号：xbox360 = Xbox 360 手柄；ds4 = DualShock 4 手柄
gamepad = xbox360
; 界面布局：full = 全按键；stick = 单摇杆（只有左摇杆）
layout = stick
; 自动显隐：true = 按下面的进程列表自动显示/隐藏；false = 手动显隐（不做任何检测）
auto_show = false

[processes]
; 需要检测的进程名，每行一个，不区分大小写
; 写文件名（aaa.exe）或完整路径（D:\\Games\\aaa.exe）都行
; 列表里的进程在前台运行时显示手柄，切到后台自动隐藏
; 留空表示不检测任何进程。例如：
;   game.exe
;   aaa.exe
;   D:\\Steam\\steamapps\\common\\bbb\\bbb.exe
"""


@dataclass
class AppConfig:
    """程序的可持久化状态。窗口位置刻意不放在这里——按需求不保存位置。"""

    gamepad: str = TYPE_XBOX360
    layout: str = LAYOUT_STICK
    auto_show: bool = False
    processes: tuple[str, ...] = ()

    def process_names(self) -> frozenset[str]:
        """用于比对的进程名集合（只取文件名、统一小写）。"""
        return frozenset(Path(item).name.lower() for item in self.processes if item.strip())


def _is_comment(line: str) -> bool:
    return line.strip().startswith((";", "#"))


def _parse_entries(body: list[str]) -> tuple[str, ...]:
    """解析 [processes] 段：每行一个进程，跳过注释和空行。"""
    result: list[str] = []
    seen: set[str] = set()
    for line in body:
        if _is_comment(line):
            continue
        name = line.strip().lstrip("\ufeff").strip('"').strip("'")
        if name:
            _append_unique(result, seen, name)
    return tuple(result)


def _append_unique(result: list[str], seen: set[str], name: str) -> None:
    """按文件名去重后追加，保留用户书写的原样。"""
    key = Path(name).name.lower()
    if key in seen:
        return
    seen.add(key)
    result.append(name)


def _format_option(key: str, value: str) -> str:
    """格式化成 ``key = value`` 一行；空值不留行尾空格，保证存盘前后文本一致。"""
    return f"{key} = {value}".rstrip()


def _split_sections(text: str) -> list[list]:
    """把 ini 文本切块：block = [段名 或 None(文件头), 该段的所有行]。"""
    blocks: list[list] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            blocks.append([stripped[1:-1].strip(), []])
        elif blocks:
            blocks[-1][1].append(line)
        else:
            blocks.append([None, [line]])
    return blocks


def _patch_options(body: list[str], values: dict[str, str]) -> list[str]:
    """在“键 = 值”段里就地改写，其他行（注释、自定义键）原样保留。"""
    remaining = dict(values)  # 复制一份，边写边消费
    new_body: list[str] = []
    for line in body:
        stripped = line.strip()
        if stripped and not _is_comment(line) and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                new_body.append(_format_option(key, remaining.pop(key)))
                continue
        new_body.append(line)
    return new_body


def _patch_entries(body: list[str], entries: list[str]) -> list[str]:
    """在“每行一个条目”的段里就地改写，段内注释始终保留。

    新条目会顶掉原来的条目块；如果段里原本没有条目，就接在注释后面。
    """
    first = last = None
    for index, line in enumerate(body):
        if line.strip() and not _is_comment(line):
            if first is None:
                first = index
            last = index
    if first is None:
        return [*body, *entries]
    # 夹在条目中间的注释不能丢，挪到新条目后面
    kept = [line for line in body[first : last + 1] if _is_comment(line)]
    return [*body[:first], *entries, *kept, *body[last + 1 :]]


def _patch_ini(text: str, updates: dict[str, dict[str, str] | list[str]]) -> str:
    """把 updates 写回 ini 文本。

    逐行修补而不是整体重写，这样用户自己加的注释、空行和自定义键都不会被
    程序覆盖掉；文件里缺失的段会自动补到末尾。键值段传 dict，逐行列表段传 list。
    """
    blocks = _split_sections(text)

    handled: set[str] = set()
    for section, body in blocks:
        pending = updates.get(section)
        if pending is None:
            continue
        handled.add(section)
        body[:] = (
            _patch_options(body, pending)
            if isinstance(pending, dict)
            else _patch_entries(body, pending)
        )

    # 文件里没有的段，追加到末尾
    for section, values in updates.items():
        if section in handled:
            continue
        if isinstance(values, dict):
            blocks.append([section, [_format_option(k, v) for k, v in values.items()]])
        else:
            blocks.append([section, list(values)])

    lines: list[str] = []
    for section, body in blocks:
        while body and not body[-1].strip():  # 段尾空行交给下面的补空行逻辑统一处理
            body.pop()
        if section is None:
            lines.extend(body)
            continue
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{section}]")
        lines.extend(body)
    return "\n".join(lines).rstrip("\n") + "\n"


class ConfigStore:
    """config.ini 的读写封装。"""

    SECTION_GENERAL = "general"
    SECTION_PROCESSES = "processes"

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path

    def load(self) -> AppConfig:
        # [general] 是普通的“键 = 值”段，交给 configparser；
        # [processes] 是每行一个条目的列表段，configparser 读不了，自己解析。
        sections: dict[str, list[str]] = {}
        for name, body in _split_sections(self._read_text()):
            if name is not None:
                sections.setdefault(name, []).extend(body)

        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(
                f"[{self.SECTION_GENERAL}]\n"
                + "\n".join(sections.get(self.SECTION_GENERAL, []))
                + "\n",
                source=str(self.path),
            )
        except configparser.Error as exc:
            log.warning("config.ini 解析失败，改用默认配置：%s", exc)
            return AppConfig()

        gamepad = parser.get(self.SECTION_GENERAL, "gamepad", fallback=TYPE_XBOX360).strip().lower()
        if gamepad not in MODE_FACTORIES:
            log.warning("手柄型号 %r 无法识别，回退为 %s", gamepad, TYPE_XBOX360)
            gamepad = TYPE_XBOX360

        layout = parser.get(self.SECTION_GENERAL, "layout", fallback=LAYOUT_STICK).strip().lower()
        if layout not in PANEL_CLASSES:
            log.warning("界面布局 %r 无法识别，回退为 %s", layout, LAYOUT_STICK)
            layout = LAYOUT_STICK

        try:
            auto_show = parser.getboolean(self.SECTION_GENERAL, "auto_show", fallback=False)
        except ValueError:
            log.warning("auto_show 不是合法布尔值，回退为 false")
            auto_show = False

        processes = _parse_entries(sections.get(self.SECTION_PROCESSES, []))
        return AppConfig(gamepad=gamepad, layout=layout, auto_show=auto_show, processes=processes)

    def save(self, config: AppConfig) -> None:
        updates: dict[str, dict[str, str] | list[str]] = {
            self.SECTION_GENERAL: {
                "gamepad": config.gamepad,
                "layout": config.layout,
                "auto_show": "true" if config.auto_show else "false",
            },
            self.SECTION_PROCESSES: list(config.processes),  # 每行一个进程
        }
        current = self._read_text()
        updated = _patch_ini(current, updates)
        if updated == current:
            return
        try:
            self.path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            log.error("写入 config.ini 失败：%s", exc)

    def _read_text(self) -> str:
        """读取配置文本；文件不存在时先落一份带注释的默认配置。"""
        try:
            if not self.path.exists():
                self.path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
                return DEFAULT_CONFIG_TEXT
            # utf-8-sig 容忍记事本写进去的 BOM
            return self.path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            log.error("读取 config.ini 失败：%s", exc)
            return DEFAULT_CONFIG_TEXT


# ==========================================================================
# Win32：窗口样式 / 进程查询
# ==========================================================================

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# 显式声明参数与返回值类型，避免 64 位下被 ctypes 隐式截断
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t

_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.K32EnumProcesses.argtypes = (
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
)
_kernel32.K32EnumProcesses.restype = wintypes.BOOL


def make_window_no_activate(hwnd: int) -> None:
    """给窗口加上 WS_EX_NOACTIVATE，点面板时不会抢走游戏的焦点。"""
    try:
        style = _user32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        _user32.SetWindowLongPtrW(
            wintypes.HWND(hwnd), GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_LAYERED
        )
    except OSError as exc:
        log.warning("设置窗口样式失败：%s", exc)


def _process_name_by_pid(pid: int) -> str:
    """按 PID 取进程可执行文件名（小写）；取不到返回空串。"""
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return Path(buffer.value).name.lower()
    finally:
        _kernel32.CloseHandle(handle)
    return ""


def foreground_process_name() -> str:
    """当前前台窗口所属进程的文件名（小写）；没有前台窗口时返回空串。"""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    if not pid.value:
        return ""
    return _process_name_by_pid(pid.value)


def running_process_names() -> set[str]:
    """枚举当前所有进程的可执行文件名（小写）。

    用 EnumProcesses 拿到 PID 列表，再逐个取文件名——和前台检测走同一条
    “PID -> 文件名”的路径，行为完全一致。
    """
    capacity = 1024
    while True:
        buffer = (wintypes.DWORD * capacity)()
        needed = wintypes.DWORD()
        if not _kernel32.K32EnumProcesses(
            buffer, ctypes.sizeof(buffer), ctypes.byref(needed)
        ):
            log.warning("枚举进程失败")
            return set()
        count = needed.value // ctypes.sizeof(wintypes.DWORD)
        if count < capacity:  # 缓冲区够用，否则翻倍重试
            break
        capacity *= 2

    names: set[str] = set()
    for index in range(count):
        name = _process_name_by_pid(buffer[index])
        if name:  # 系统保护进程打不开，跳过即可
            names.add(name)
    return names


# ==========================================================================
# 虚拟手柄后端
# ==========================================================================

def _is_ds4_special(code) -> bool:
    """DS4 的 PS / Touchpad 必须走 press_special_button()。"""
    return code in (
        vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_PS,
        vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_TOUCHPAD,
    )


class GamepadBackend:
    """把界面操作翻译成 vgamepad 调用，并屏蔽两种手柄的差异。

    差异只有三处：X360 的 Y 轴方向相反、DS4 的 PS/Touchpad 属于“特殊按键”、
    DS4 的十字键是 8 向帽子开关。其余调用方式完全一致，界面层不需要关心。
    """

    def __init__(self) -> None:
        self._device = None
        self._type: str | None = None

    def connect(self, gamepad_type: str) -> bool:
        """创建指定型号的虚拟手柄，成功返回 True。"""
        self.disconnect()
        if vg is None:
            log.error("vgamepad 库不可用，无法创建虚拟手柄")
            return False
        try:
            device = vg.VX360Gamepad() if gamepad_type == TYPE_XBOX360 else vg.VDS4Gamepad()
        except Exception as exc:
            log.error("创建虚拟手柄失败：%s", exc)
            return False
        self._device = device
        self._type = gamepad_type
        log.info("已创建虚拟手柄：%s", gamepad_type)
        return True

    def disconnect(self) -> None:
        """复位并销毁当前虚拟手柄。"""
        device, self._device, self._type = self._device, None, None
        if device is None:
            return
        try:
            device.reset()
            device.update()
        except Exception:
            log.debug("销毁前复位虚拟手柄失败", exc_info=True)
        del device

    # ------------------------------------------------------------- 设备操作

    def move_stick(self, side: str, x: float, y: float) -> None:
        if self._device is None:
            return
        if self._type == TYPE_XBOX360:
            y = -y  # X360 的 Y 轴向上为正，与窗口坐标相反；DS4 与窗口坐标同向
        with self._guard():
            if side == SIDE_LEFT:
                self._device.left_joystick_float(x, y)
            else:
                self._device.right_joystick_float(x, y)

    def set_trigger(self, side: str, value: float) -> None:
        if self._device is None:
            return
        with self._guard():
            if side == SIDE_LEFT:
                self._device.left_trigger_float(value)
            else:
                self._device.right_trigger_float(value)

    def set_buttons(self, codes: tuple, pressed: bool) -> None:
        """按下/松开一组按键（X360 的斜向十字键就是两个方向键的组合）。"""
        if self._device is None or not codes:
            return
        with self._guard():
            for code in codes:
                self._press_one(code, pressed)

    def set_dpad(self, direction) -> None:
        """设置 DS4 十字键方向（帽子开关，只能整体设置）。"""
        if self._device is None or self._type != TYPE_DS4:
            return
        with self._guard():
            self._device.directional_pad(direction)

    def reset(self) -> None:
        """按键、扳机、摇杆全部回到初始状态。"""
        if self._device is None:
            return
        with self._guard():
            self._device.reset()

    # ----------------------------------------------------------------- 内部

    def _press_one(self, code, pressed: bool) -> None:
        device = self._device
        if self._type == TYPE_DS4 and _is_ds4_special(code):
            action = device.press_special_button if pressed else device.release_special_button
        else:
            action = device.press_button if pressed else device.release_button
        action(code)

    @contextmanager
    def _guard(self) -> Iterator[None]:
        """执行设备操作并发送状态；任何异常只记日志，不影响界面。"""
        try:
            yield
            self._device.update()
        except Exception as exc:
            log.warning("虚拟手柄操作失败：%s", exc)


# ==========================================================================
# 配色与样式
# ==========================================================================

class Theme:
    """集中管理配色，两个布局共用一套视觉。"""

    WINDOW_BG = QColor(20, 20, 20, 120)
    PANEL_RADIUS = 12

    BTN_NORMAL = "rgba(80, 80, 80, 150)"
    BTN_HOVER = "rgba(120, 120, 120, 180)"
    BTN_PRESSED_XBOX = "rgba(39, 174, 96, 200)"
    BTN_PRESSED_DS4 = "rgba(41, 128, 185, 200)"

    #: 托盘图标：Xbox 绿 / PlayStation 蓝
    TRAY_XBOX = QColor(16, 124, 16)
    TRAY_DS4 = QColor(0, 112, 209)

    #: 摇杆配色
    STICK_BASE_BRUSH = QColor(30, 30, 30, 100)
    STICK_BASE_PEN = QColor(100, 100, 100, 120)
    STICK_BRUSH = QColor(52, 152, 219, 180)
    STICK_BRUSH_ACTIVE = QColor(52, 172, 239, 230)
    STICK_PEN = QColor(41, 128, 185, 200)

    SLIDER_CSS = """
        QSlider { background: transparent; }
        QSlider::groove:vertical {
            background: rgba(51, 51, 51, 200);
            width: 6px;
            border-radius: 3px;
        }
        QSlider::handle:vertical {
            background: rgba(231, 76, 60, 200);
            height: 10px;
            margin: 0 -4px;
            border-radius: 5px;
        }
        QSlider::handle:vertical:hover { background: rgba(255, 100, 100, 255); }
        QSlider::sub-page:vertical { background: rgba(80, 80, 80, 100); }
        QSlider::add-page:vertical { background: rgba(192, 57, 43, 180); border-radius: 3px; }
    """

    CAPTION_CSS = "color: #aaaaaa; font-size: 9px; font-weight: bold; background: transparent;"

    @staticmethod
    def button_css(radius: int, font_size: int, pressed_color: str) -> str:
        return f"""
            QPushButton {{
                background: {Theme.BTN_NORMAL};
                color: white;
                border: 1px solid rgba(120, 120, 120, 100);
                border-radius: {radius}px;
                font-size: {font_size}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {Theme.BTN_HOVER};
                border: 1px solid rgba(200, 200, 200, 150);
            }}
            QPushButton:pressed {{
                background: {pressed_color};
                border: 1px solid rgba(255, 255, 255, 100);
            }}
        """


def make_tray_icon(color: QColor) -> QIcon:
    """托盘图标：一个纯色圆点（与原脚本一致的观感，只是按型号换颜色）。

    圆形铺满整张位图（不留边距），这样在 16x16 的托盘里能占满，不会显得比原脚本小。
    """
    icon = QIcon()
    for size in (16, 24, 32, 48, 64):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QRectF(0, 0, size, size))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


# ==========================================================================
# 基础控件
# ==========================================================================

class DragHandle(QWidget):
    """窗口拖动把手。

    带文字时是标题栏样式（全按键布局）；不带文字时是居中小圆点（单摇杆布局，
    与原脚本上方那个小圆点一致）。
    """

    dragged = Signal()

    def __init__(self, text: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text or ""
        self._hovering = False
        self._offset = None
        self.setFixedHeight(20 if self._text else 16)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    # --------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        if self._text:
            painter.setBrush(QColor(255, 255, 255, 40 if self._hovering else 20))
            path = QPainterPath()
            # 向下多画一个圆角半径，底部圆角被控件边界裁掉，只剩上方圆角
            path.addRoundedRect(
                QRectF(self.rect()).adjusted(0, 0, 0, Theme.PANEL_RADIUS),
                Theme.PANEL_RADIUS,
                Theme.PANEL_RADIUS,
            )
            painter.drawPath(path)

            font = painter.font()
            font.setBold(True)
            font.setPixelSize(11)
            painter.setFont(font)
            painter.setPen(QColor("#ffffff") if self._hovering else QColor("#dddddd"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        else:
            painter.setBrush(
                QColor(80, 80, 80, 180) if self._hovering else QColor(120, 120, 120, 90)
            )
            painter.drawEllipse(QPointF(self.width() / 2, self.height() / 2), 8.0, 8.0)

    def enterEvent(self, event) -> None:
        self._hovering = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovering = False
        self.update()

    # --------------------------------------------------------------- 拖动
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # 全局鼠标位置 - 窗口左上角 = 鼠标在窗口内的偏移，拖动时窗口才不“跳”
            self._offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._offset)
            self.dragged.emit()

    def mouseReleaseEvent(self, event) -> None:
        self._offset = None


class JoystickWidget(QWidget):
    """可视化摇杆：拖动时向外发送归一化到 -1.0~1.0 的 (x, y)，y 向下为正。"""

    moved = Signal(float, float)

    BASE_RADIUS = 60
    STICK_RADIUS = 25

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        side = self.BASE_RADIUS * 2 + 20
        self.setFixedSize(side, side)
        self._center = QPointF(side / 2, side / 2)
        self._max_distance = float(self.BASE_RADIUS - self.STICK_RADIUS)
        self._stick_pos = QPointF(0, 0)
        self._dragging = False
        self._hovering = False
        self.setMouseTracking(True)

    # --------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QBrush(Theme.STICK_BASE_BRUSH))
        painter.setPen(QPen(Theme.STICK_BASE_PEN, 2))
        painter.drawEllipse(self._center, self.BASE_RADIUS, self.BASE_RADIUS)

        active = self._dragging or self._hovering
        painter.setBrush(QBrush(Theme.STICK_BRUSH_ACTIVE if active else Theme.STICK_BRUSH))
        painter.setPen(QPen(Theme.STICK_PEN, 2))
        painter.drawEllipse(self._center + self._stick_pos, self.STICK_RADIUS, self.STICK_RADIUS)

    def enterEvent(self, event) -> None:
        self._hovering = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovering = False
        self.update()

    # --------------------------------------------------------------- 交互
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._distance_to_center(event.position()) < self.BASE_RADIUS:  # 按在底座圆内才算抓住
            self._dragging = True
            self._update_stick(event.position())

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._update_stick(event.position())

    def mouseReleaseEvent(self, event) -> None:
        self.reset()

    def reset(self) -> None:
        """摇杆回正（鼠标松开、窗口隐藏时都会调用）。"""
        if not self._dragging and self._stick_pos == QPointF(0, 0):
            return
        self._dragging = False
        self._stick_pos = QPointF(0, 0)
        self.update()
        self.moved.emit(0.0, 0.0)

    # --------------------------------------------------------------- 内部
    def _distance_to_center(self, pos: QPointF) -> float:
        delta = pos - self._center
        return math.hypot(delta.x(), delta.y())

    def _update_stick(self, pos: QPointF) -> None:
        delta = pos - self._center
        distance = math.hypot(delta.x(), delta.y())
        if distance > self._max_distance:  # 超出活动范围就沿原方向截断到圆周上
            delta *= self._max_distance / distance
        self._stick_pos = delta
        self.update()
        self.moved.emit(delta.x() / self._max_distance, delta.y() / self._max_distance)


class TriggerSlider(QSlider):
    """扳机滑块：向外发送 0.0~1.0，松手自动回弹到 0。"""

    value_float = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setInvertedAppearance(True)
        self.setRange(0, 100)
        self.setStyleSheet(Theme.SLIDER_CSS)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.valueChanged.connect(lambda value: self.value_float.emit(value / 100.0))

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.setValue(0)  # 回弹


# ==========================================================================
# 按键表：界面完全由数据驱动，两个手柄共用同一套面板代码
# ==========================================================================

@dataclass(frozen=True)
class ButtonSpec:
    """一个按键的完整描述。

    ``row`` / ``col`` 是相对所属容器的坐标：
      * 十字键 / 动作键 -> 3x3 子网格内的位置；
      * 底部功能键      -> 功能键行内的列号。
    """

    label: str
    codes: tuple = ()
    row: int = 0
    col: int = 0
    width: int = 35
    height: int = 25
    colspan: int = 1
    radius: int = 3
    font_size: int = 10
    #: DS4 十字键是帽子开关，这里存方向值；X360 则用上面的 codes 组合键
    dpad_direction: int | None = None


@dataclass(frozen=True)
class ModeSpec:
    """一个手柄型号的按键表。"""

    key: str
    title: str
    pressed_color: str
    tray_color: QColor
    shoulder_left: ButtonSpec
    shoulder_right: ButtonSpec
    left_trigger: str
    right_trigger: str
    dpad: tuple[ButtonSpec, ...]
    face: tuple[ButtonSpec, ...]
    system: tuple[ButtonSpec, ...]


def _xbox360_spec() -> ModeSpec:
    """Xbox 360 按键表。"""
    btn = vg.XUSB_BUTTON
    small = {"width": 35, "height": 22}
    cluster = {"width": 38, "height": 38, "font_size": 14}
    up, down = btn.XUSB_GAMEPAD_DPAD_UP, btn.XUSB_GAMEPAD_DPAD_DOWN
    left, right = btn.XUSB_GAMEPAD_DPAD_LEFT, btn.XUSB_GAMEPAD_DPAD_RIGHT

    return ModeSpec(
        key=TYPE_XBOX360,
        title="Xbox 360",
        pressed_color=Theme.BTN_PRESSED_XBOX,
        tray_color=Theme.TRAY_XBOX,
        shoulder_left=ButtonSpec("LB", (btn.XUSB_GAMEPAD_LEFT_SHOULDER,)),
        shoulder_right=ButtonSpec("RB", (btn.XUSB_GAMEPAD_RIGHT_SHOULDER,)),
        left_trigger="LT",
        right_trigger="RT",
        # X360 的十字键没有斜向档位：斜向 = 两个方向键的组合
        dpad=(
            ButtonSpec("↖", (up, left), 0, 0, radius=4, **cluster),
            ButtonSpec("↑", (up,), 0, 1, radius=4, **cluster),
            ButtonSpec("↗", (up, right), 0, 2, radius=4, **cluster),
            ButtonSpec("←", (left,), 1, 0, radius=4, **cluster),
            ButtonSpec("→", (right,), 1, 2, radius=4, **cluster),
            ButtonSpec("↙", (down, left), 2, 0, radius=4, **cluster),
            ButtonSpec("↓", (down,), 2, 1, radius=4, **cluster),
            ButtonSpec("↘", (down, right), 2, 2, radius=4, **cluster),
        ),
        face=(
            ButtonSpec("Y", (btn.XUSB_GAMEPAD_Y,), 0, 1, radius=19, **cluster),
            ButtonSpec("X", (btn.XUSB_GAMEPAD_X,), 1, 0, radius=19, **cluster),
            ButtonSpec("B", (btn.XUSB_GAMEPAD_B,), 1, 2, radius=19, **cluster),
            ButtonSpec("A", (btn.XUSB_GAMEPAD_A,), 2, 1, radius=19, **cluster),
        ),
        system=(
            ButtonSpec("L3", (btn.XUSB_GAMEPAD_LEFT_THUMB,), col=0, **small),
            ButtonSpec("Back", (btn.XUSB_GAMEPAD_BACK,), col=1, **small),
            ButtonSpec("Guide", (btn.XUSB_GAMEPAD_GUIDE,), col=2, colspan=2, width=45, height=22),
            ButtonSpec("Start", (btn.XUSB_GAMEPAD_START,), col=4, **small),
            ButtonSpec("R3", (btn.XUSB_GAMEPAD_RIGHT_THUMB,), col=5, **small),
        ),
    )


def _ds4_spec() -> ModeSpec:
    """DualShock 4 按键表。"""
    btn = vg.DS4_BUTTONS
    special = vg.DS4_SPECIAL_BUTTONS
    hat = vg.DS4_DPAD_DIRECTIONS
    small = {"width": 35, "height": 22}
    cluster = {"width": 38, "height": 38, "font_size": 14}

    def hat_button(label: str, row: int, col: int, direction) -> ButtonSpec:
        return ButtonSpec(
            label, row=row, col=col, radius=4, dpad_direction=direction, **cluster
        )

    return ModeSpec(
        key=TYPE_DS4,
        title="DualShock 4",
        pressed_color=Theme.BTN_PRESSED_DS4,
        tray_color=Theme.TRAY_DS4,
        shoulder_left=ButtonSpec("L1", (btn.DS4_BUTTON_SHOULDER_LEFT,)),
        shoulder_right=ButtonSpec("R1", (btn.DS4_BUTTON_SHOULDER_RIGHT,)),
        left_trigger="L2",
        right_trigger="R2",
        # DS4 的十字键是一个 8 向帽子开关，每个方向各占一档
        dpad=(
            hat_button("↖", 0, 0, hat.DS4_BUTTON_DPAD_NORTHWEST),
            hat_button("↑", 0, 1, hat.DS4_BUTTON_DPAD_NORTH),
            hat_button("↗", 0, 2, hat.DS4_BUTTON_DPAD_NORTHEAST),
            hat_button("←", 1, 0, hat.DS4_BUTTON_DPAD_WEST),
            hat_button("→", 1, 2, hat.DS4_BUTTON_DPAD_EAST),
            hat_button("↙", 2, 0, hat.DS4_BUTTON_DPAD_SOUTHWEST),
            hat_button("↓", 2, 1, hat.DS4_BUTTON_DPAD_SOUTH),
            hat_button("↘", 2, 2, hat.DS4_BUTTON_DPAD_SOUTHEAST),
        ),
        face=(
            ButtonSpec("▲", (btn.DS4_BUTTON_TRIANGLE,), 0, 1, radius=19, **cluster),
            ButtonSpec("■", (btn.DS4_BUTTON_SQUARE,), 1, 0, radius=19, **cluster),
            ButtonSpec("●", (btn.DS4_BUTTON_CIRCLE,), 1, 2, radius=19, **cluster),
            ButtonSpec("✖", (btn.DS4_BUTTON_CROSS,), 2, 1, radius=19, **cluster),
        ),
        system=(
            ButtonSpec("L3", (btn.DS4_BUTTON_THUMB_LEFT,), col=0, **small),
            ButtonSpec("Shr", (btn.DS4_BUTTON_SHARE,), col=1, **small),
            ButtonSpec("PS", (special.DS4_SPECIAL_BUTTON_PS,), col=2, **small),
            ButtonSpec("Opt", (btn.DS4_BUTTON_OPTIONS,), col=3, **small),
            ButtonSpec("Touch", (special.DS4_SPECIAL_BUTTON_TOUCHPAD,), col=4, **small),
            ButtonSpec("R3", (btn.DS4_BUTTON_THUMB_RIGHT,), col=5, **small),
        ),
    )


MODE_FACTORIES = {TYPE_XBOX360: _xbox360_spec, TYPE_DS4: _ds4_spec}


# ==========================================================================
# 面板
# ==========================================================================

class GamepadPanel(QWidget):
    """面板基类：可选圆角半透明背景 + 顶部拖动条 + 统一的控件工厂方法。"""

    def __init__(
        self,
        backend: GamepadBackend,
        spec: ModeSpec,
        *,
        drag_text: str | None = None,
        margins: tuple[int, int, int, int] = (0, 0, 0, 6),
        spacing: int = 2,
        background: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        self._spec = spec
        self._background = background

        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(*margins)
        self.content_layout.setSpacing(spacing)

        self.drag_handle = DragHandle(drag_text)
        self.content_layout.addWidget(self.drag_handle)

    def reset_inputs(self) -> None:
        """窗口隐藏时复位界面上的摇杆/扳机，避免按键卡住。"""

    # --------------------------------------------------------------- 背景
    def paintEvent(self, event) -> None:
        if not self._background:
            return  # 裸摇杆模式：不画底板，整块区域保持透明
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(Theme.WINDOW_BG))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            Theme.PANEL_RADIUS,
            Theme.PANEL_RADIUS,
        )

    # ----------------------------------------------------------- 控件工厂
    def _add_button(self, grid: QGridLayout, spec: ButtonSpec, row: int, col: int) -> QPushButton:
        button = QPushButton(spec.label, self)
        button.setFixedSize(spec.width, spec.height)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setStyleSheet(Theme.button_css(spec.radius, spec.font_size, self._spec.pressed_color))
        if spec.dpad_direction is not None:
            button.pressed.connect(partial(self._backend.set_dpad, spec.dpad_direction))
            button.released.connect(
                partial(self._backend.set_dpad, vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NONE)
            )
        else:
            button.pressed.connect(partial(self._backend.set_buttons, spec.codes, True))
            button.released.connect(partial(self._backend.set_buttons, spec.codes, False))
        grid.addWidget(button, row, col, 1, spec.colspan, alignment=Qt.AlignmentFlag.AlignCenter)
        return button

    def _add_trigger(
        self, grid: QGridLayout, caption: str, side: str, row: int, col: int
    ) -> TriggerSlider:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        label = QLabel(caption, container)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(Theme.CAPTION_CSS)

        slider = TriggerSlider(container)
        slider.setFixedSize(18, 55)
        slider.value_float.connect(partial(self._backend.set_trigger, side))

        layout.addWidget(label)
        layout.addWidget(slider, alignment=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(container, row, col, 2, 1)
        return slider

    def _add_cluster(
        self, grid: QGridLayout, specs: Iterable[ButtonSpec], row: int, col: int, spacing: int
    ) -> None:
        """把一组按键（十字键或动作键）作为一个 3x3 整体放进网格。"""
        frame = QWidget(self)
        sub_grid = QGridLayout(frame)
        sub_grid.setContentsMargins(0, 0, 0, 0)
        sub_grid.setSpacing(spacing)
        for spec in specs:
            self._add_button(sub_grid, spec, spec.row, spec.col)
        grid.addWidget(frame, row, col, 3, 2)


class FullKeyPanel(GamepadPanel):
    """全按键面板：肩键、扳机、十字键、动作键、功能键，两侧各一个摇杆。"""

    TRIGGER_ROW = 0
    CLUSTER_ROW = 2
    DPAD_COL = 0
    FACE_COL = 4
    SYSTEM_ROW = 5

    def __init__(self, backend: GamepadBackend, spec: ModeSpec, parent: QWidget | None = None) -> None:
        super().__init__(backend, spec, drag_text=spec.title, parent=parent)

        body = QWidget(self)
        row_layout = QHBoxLayout(body)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        # 左右摇杆固定在两侧
        self.left_stick = JoystickWidget(body)
        self.left_stick.moved.connect(partial(backend.move_stick, SIDE_LEFT))
        self.right_stick = JoystickWidget(body)
        self.right_stick.moved.connect(partial(backend.move_stick, SIDE_RIGHT))
        row_layout.addWidget(self.left_stick)

        # 中间的按键网格
        center = QWidget(body)
        grid = QGridLayout(center)
        grid.setContentsMargins(6, 0, 6, 0)
        grid.setSpacing(2)
        row_layout.addWidget(center)

        row_layout.addWidget(self.right_stick)

        # 顶部肩键与扳机
        self._add_button(grid, spec.shoulder_left, self.TRIGGER_ROW, 0)
        self._add_trigger(grid, spec.left_trigger, SIDE_LEFT, self.TRIGGER_ROW, 1)
        self._add_trigger(grid, spec.right_trigger, SIDE_RIGHT, self.TRIGGER_ROW, 4)
        self._add_button(grid, spec.shoulder_right, self.TRIGGER_ROW, 5)

        # 中部十字键与动作键
        self._add_cluster(grid, spec.dpad, self.CLUSTER_ROW, self.DPAD_COL, spacing=1)
        self._add_cluster(grid, spec.face, self.CLUSTER_ROW, self.FACE_COL, spacing=2)

        # 底部功能键
        for button in spec.system:
            self._add_button(grid, button, self.SYSTEM_ROW, button.col)

        self.content_layout.addWidget(body)

    def reset_inputs(self) -> None:
        self.left_stick.reset()
        self.right_stick.reset()
        for slider in self.findChildren(TriggerSlider):
            slider.setValue(0)


class SingleStickPanel(GamepadPanel):
    """单摇杆面板：只有左摇杆，和原脚本一样是裸摇杆（不画底板）。"""

    def __init__(self, backend: GamepadBackend, spec: ModeSpec, parent: QWidget | None = None) -> None:
        super().__init__(
            backend,
            spec,
            drag_text=None,
            margins=(0, 0, 0, 0),
            spacing=0,
            background=False,
            parent=parent,
        )

        self.stick = JoystickWidget(self)
        self.stick.moved.connect(partial(backend.move_stick, SIDE_LEFT))
        self.content_layout.addWidget(self.stick, alignment=Qt.AlignmentFlag.AlignCenter)

    def reset_inputs(self) -> None:
        self.stick.reset()


PANEL_CLASSES = {LAYOUT_FULL: FullKeyPanel, LAYOUT_STICK: SingleStickPanel}


# ==========================================================================
# 自动显隐检测
# ==========================================================================

class AutoShowWatcher(QTimer):
    """自动显隐检测器：两级检测，兼顾实时性与系统开销。

    进程列表里一个都没在运行时，每 ``IDLE_INTERVAL_MS`` 毫秒才枚举一次进程；
    一旦发现目标进程在运行，就切到 ``ACTIVE_INTERVAL_MS`` 的高频检测，只查前台
    窗口属于哪个进程。高频期间每隔 ``RESCAN_TICKS`` 次再做一次完整枚举，这样
    目标进程退出后能自动退回低频检测。
    """

    should_show = Signal(bool)

    IDLE_INTERVAL_MS = 5000
    ACTIVE_INTERVAL_MS = 300
    RESCAN_TICKS = 20  # 约 6 秒完整枚举一次

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTimerType(Qt.TimerType.CoarseTimer)
        self.timeout.connect(self._tick)
        self._names: frozenset[str] = frozenset()
        self._enabled = False
        self._running = False
        self._ticks = 0
        self._last_visible = False

    # --------------------------------------------------------------- 配置
    def set_processes(self, processes: Iterable[str]) -> None:
        """更新要检测的进程列表（只取文件名、统一小写）。"""
        names = frozenset(
            Path(str(item).strip()).name.lower() for item in processes if str(item).strip()
        )
        if names == self._names:
            return
        self._names = names
        self._restart()

    def set_enabled(self, enabled: bool) -> None:
        """开启/关闭检测。关闭时停止一切轮询，但不动窗口当前的显示状态。"""
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if enabled:
            self._restart()
        else:
            self.stop()
            self._running = False
            self._ticks = 0

    # --------------------------------------------------------------- 内部
    def _restart(self) -> None:
        """立刻重新评估一次，然后按状态决定后续轮询频率。"""
        if not self._enabled:
            return
        self._running = False
        self._ticks = 0
        self.start(0)

    def _tick(self) -> None:
        if not self._names:
            self.start(self.IDLE_INTERVAL_MS)
            self._emit_visible(False)
        elif self._running:
            self._foreground_tick()
        else:
            self._idle_tick()

    def _idle_tick(self) -> None:
        """低频：目标进程没在跑，只需要偶尔看看它启动了没有。"""
        if self._names & running_process_names():
            self._running = True
            self._ticks = 0
            self._foreground_tick()
        else:
            self.start(self.IDLE_INTERVAL_MS)
            self._emit_visible(False)

    def _foreground_tick(self) -> None:
        """高频：只查前台窗口是谁，同时定期完整枚举以确认目标进程还在。"""
        self._ticks += 1
        self.start(self.ACTIVE_INTERVAL_MS)
        if self._ticks >= self.RESCAN_TICKS:
            self._ticks = 0
            if not (self._names & running_process_names()):
                self._running = False
                self.start(self.IDLE_INTERVAL_MS)
                self._emit_visible(False)
                return
        self._emit_visible(foreground_process_name() in self._names)

    def _emit_visible(self, visible: bool) -> None:
        if visible == self._last_visible:
            return
        self._last_visible = visible
        self.should_show.emit(visible)


# ==========================================================================
# 主窗口
# ==========================================================================

class VGamepadWindow(QWidget):
    """主窗口：面板切换、托盘交互、自动显隐调度都在这里串起来。"""

    def __init__(self, config: AppConfig, store: ConfigStore) -> None:
        super().__init__()
        self._config = config
        self._store = store
        self._spec = MODE_FACTORIES[config.gamepad]()
        self._panel: GamepadPanel | None = None
        self._user_moved = False

        self.setWindowTitle(APP_NAME)
        # 无边框 / 永远置顶 / 工具窗口（不出现在任务栏）
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self._backend = GamepadBackend()
        self._backend_error_shown = False

        self._init_tray()

        if not self._backend.connect(config.gamepad):
            self._report_error("创建虚拟手柄失败，请确认已正确安装 ViGEmBus 驱动。")

        self._watcher = AutoShowWatcher(self)
        self._watcher.should_show.connect(self._apply_auto_visibility)
        self._watcher.set_processes(config.processes)

        self._rebuild_panel()
        make_window_no_activate(int(self.winId()))

    # ------------------------------------------------------------ 生命周期
    def start(self) -> None:
        """启动状态：窗口保持隐藏，自动显隐交给检测器决定。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # 托盘不可用时至少要让窗口能看见，否则程序就“消失”了
            log.warning("系统托盘不可用，直接显示窗口")
            self.show()
            return
        self.hide()
        self._watcher.set_enabled(self._config.auto_show)

    def quit(self) -> None:
        self._watcher.set_enabled(False)
        self._persist()
        self._backend.disconnect()
        self._tray.hide()
        QApplication.quit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        make_window_no_activate(int(self.winId()))

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        # 隐藏时把界面和后端一起复位，避免按住按键时窗口消失导致按键卡住
        if self._panel is not None:
            self._panel.reset_inputs()
        self._backend.reset()

    # ------------------------------------------------------------ 窗口位置
    def _move_to_bottom_center(self) -> None:
        """屏幕下方居中（与原脚本一致）；用户手动拖过之后就不再自动挪。"""
        screen = QApplication.primaryScreen() or self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        size = self.sizeHint()
        if size.width() <= 0 or size.height() <= 0:
            size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        x = area.center().x() - size.width() // 2
        y = area.bottom() - size.height() - 5
        self.move(x, y)

    def _on_panel_dragged(self) -> None:
        self._user_moved = True

    # ------------------------------------------------------------ 面板切换
    def _rebuild_panel(self) -> None:
        if self._panel is not None:
            self._root.removeWidget(self._panel)
            # 先断开父子关系：deleteLater 要等事件循环才生效，
            # 期间旧面板还会继续显示在窗口上，和新面板叠在一起。
            self._panel.setParent(None)
            self._panel.deleteLater()
            self._panel = None

        self._spec = MODE_FACTORIES[self._config.gamepad]()
        panel_class = PANEL_CLASSES[self._config.layout]
        self._panel = panel_class(self._backend, self._spec, self)
        self._panel.drag_handle.dragged.connect(self._on_panel_dragged)
        self._root.addWidget(self._panel)

        self.adjustSize()
        self._update_tray()
        if not self._user_moved:
            self._move_to_bottom_center()

    def _set_layout(self, layout: str) -> None:
        if layout == self._config.layout:
            return
        self._config.layout = layout
        self._rebuild_panel()
        self._persist()

    def _switch_gamepad(self) -> None:
        gamepad = TYPE_DS4 if self._config.gamepad == TYPE_XBOX360 else TYPE_XBOX360
        if not self._backend.connect(gamepad):
            self._report_error("切换手柄失败：无法创建虚拟手柄，请确认 ViGEmBus 驱动正常。")
            return
        self._config.gamepad = gamepad
        self._rebuild_panel()
        self._persist()

    # ------------------------------------------------------------ 托盘
    def _init_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        self._tray.activated.connect(self._on_tray_activated)

        # 菜单项只作为功能文字，不带勾选状态，避免把菜单撑宽；
        # 只有“自动显隐/手动显隐”这一项的文字会随状态变化。
        menu = QMenu(self)
        menu.addAction("切换手柄").triggered.connect(self._switch_gamepad)
        menu.addSeparator()
        menu.addAction(LAYOUT_TITLES[LAYOUT_FULL]).triggered.connect(
            lambda: self._set_layout(LAYOUT_FULL)
        )
        menu.addAction(LAYOUT_TITLES[LAYOUT_STICK]).triggered.connect(
            lambda: self._set_layout(LAYOUT_STICK)
        )
        menu.addSeparator()
        self._act_auto = menu.addAction("自动显隐")
        self._act_auto.triggered.connect(self._toggle_auto_show)
        menu.addSeparator()
        menu.addAction("退出").triggered.connect(self.quit)

        menu.aboutToShow.connect(self._sync_menu)
        self._menu = menu
        self._tray.setContextMenu(menu)  # 右键弹出菜单
        self._update_tray()
        self._tray.show()

    def _auto_action_text(self) -> str:
        """菜单项文字：表示“点下去会切到哪种模式”，所以和当前状态相反。"""
        return "手动显隐" if self._config.auto_show else "自动显隐"

    def _auto_state_text(self) -> str:
        """托盘提示文字：表示当前所处的模式。"""
        return "自动显隐" if self._config.auto_show else "手动显隐"

    def _update_tray(self) -> None:
        """托盘图标跟着手柄型号换颜色，悬浮提示按行显示当前三项状态。"""
        self._tray.setIcon(make_tray_icon(self._spec.tray_color))
        self._tray.setToolTip(
            "\n".join(
                (
                    self._spec.title,
                    LAYOUT_TITLES[self._config.layout],
                    self._auto_state_text(),
                )
            )
        )

    def _sync_menu(self) -> None:
        self._act_auto.setText(self._auto_action_text())

    def _on_tray_activated(self, reason) -> None:
        # 只处理左键单击：立即切换显隐。双击与右键都不再触发任何动作，
        # 菜单统一由右键弹出，所以单击没有等待双击判定的延迟。
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_visibility()

    # ------------------------------------------------------------ 显示控制
    def _toggle_visibility(self) -> None:
        """单击托盘：切换显示/隐藏。处于自动显隐时先切到手动，否则会被立刻藏回去。"""
        if self._config.auto_show:
            self._set_auto_show(False)
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def _set_auto_show(self, enabled: bool) -> None:
        if enabled == self._config.auto_show:
            return
        self._config.auto_show = enabled
        self._watcher.set_enabled(enabled)
        self._update_tray()  # 悬浮提示里的“自动/手动显隐”要跟着变
        self._persist()
        log.info("自动显隐已%s", "开启" if enabled else "关闭")

    def _toggle_auto_show(self) -> None:
        """菜单里那一项：点“自动显隐”就开启检测，点“手动显隐”就停止检测。"""
        self._set_auto_show(not self._config.auto_show)

    def _apply_auto_visibility(self, visible: bool) -> None:
        if visible == self.isVisible():
            return
        if visible:
            self.show()
        else:
            self.hide()

    # ------------------------------------------------------------ 杂项
    def _persist(self) -> None:
        self._store.save(self._config)

    def _report_error(self, message: str) -> None:
        log.error(message)
        if not self._backend_error_shown:
            self._backend_error_shown = True
            self._tray.showMessage(
                APP_NAME, message, QSystemTrayIcon.MessageIcon.Critical, 5000
            )


# ==========================================================================
# 入口
# ==========================================================================

def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # 有托盘图标，关掉窗口不退出程序

    if vg is None:
        QMessageBox.critical(
            None,
            APP_NAME,
            "无法加载 vgamepad 库：\n"
            f"{VG_IMPORT_ERROR}\n\n"
            "请确认已安装 ViGEmBus 驱动"
            "（https://github.com/nefarius/ViGEmBus/releases）后重试。",
        )
        return 1

    store = ConfigStore()
    window = VGamepadWindow(store.load(), store)
    window.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
