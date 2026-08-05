"""DR2C 存档助手：轻量像素风 CustomTkinter 图形界面。"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_APP_DIR_EARLY = Path(__file__).resolve().parent
_VENDOR_DIR = _APP_DIR_EARLY / "vendor"
if _VENDOR_DIR.is_dir():
    sys.path.insert(0, str(_VENDOR_DIR))

import customtkinter as ctk
from PIL import Image, ImageOps

from dr2c_core import (
    APP_DIR, DATA_DIR, DEFAULT_SAVE_DIR, RESOURCE_LABELS, STAT_LABELS, STAT_NAMES,
    SaveError, assert_same_gstats_structure, backup_and_replace, convert_bytes,
    gstats_filename, load_mapping, patch_activity, read_activity, read_gstats,
    replace_trunk_weapons, save_filename, set_gstats_fields, slot_filename,
)

def _load_pixel_font() -> None:
    """临时注册随软件分发的点阵字体，不要求用户安装到系统。"""
    font_file = APP_DIR / "resource" / "VonwaonBitmap-16px.ttf"
    if font_file.is_file() and sys.platform == "win32":
        try:
            ctypes.windll.gdi32.AddFontResourceExW(str(font_file), 0x10, 0)
        except OSError:
            pass


_load_pixel_font()
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(1.14)

# 浅色像素纸张风：重点色克制，信息层级用墨色和米白而不是高饱和光污染。
BG, TOP, PANEL, PANEL_ALT, INSET = "#f4f1e8", "#ffffff", "#ffffff", "#e9e6dc", "#f8f7f2"
INK, MUTED, LINE = "#28302f", "#68716d", "#c8c9c1"
ACCENT, ACCENT_HOVER, GOLD, DANGER, OK = "#3f7d68", "#579984", "#a66c28", "#c14d52", "#33845f"
SELECT_GREEN, SELECT_GOLD = "#bfddc4", "#ecd7ae"
PIXEL_FONT, BODY_FONT, MONO = "VonwaonBitmap 16px", "Microsoft YaHei UI", "Consolas"
APP_VERSION = "1.0.1"
APP_CODENAME = "旅途启程"


def game_running() -> bool:
    try:
        output = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True, encoding="mbcs", errors="ignore")
    except (OSError, subprocess.CalledProcessError):
        return False
    return "deathroadtocanada" in output.lower()


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(path)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Weapon:
    base_id: int
    chinese: str
    english: str
    tier: str
    category: str
    note: str
    details: dict[str, object]


class KeqingCarousel(ctk.CTkFrame):
    """自动读取 resource/keqingIMG 的像素风图片轮播。"""
    EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    INTERVAL_MS = 7000
    DISPLAY_WIDTH = 375
    DISPLAY_HEIGHT = 559

    def __init__(self, master: ctk.CTkFrame) -> None:
        super().__init__(master, fg_color="transparent")
        folder = APP_DIR / "resource" / "keqingIMG"
        self.paths = sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in self.EXTENSIONS) if folder.is_dir() else []
        if not self.paths:
            self.paths = [APP_DIR / "resource" / "keqing_help.png"]
        self.index = 0
        self.paused = False
        self.current_image: ctk.CTkImage | None = None
        self.image_label = ctk.CTkLabel(self, text="", width=self.DISPLAY_WIDTH, height=self.DISPLAY_HEIGHT, fg_color="#f1edf8", corner_radius=0)
        self.image_label.pack(padx=10, pady=(8, 5))
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=10)
        ctk.CTkButton(controls, text="‹", width=32, height=27, font=(MONO, 18, "bold"), fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda: self.move(-1)).pack(side="left")
        self.counter = ctk.CTkLabel(controls, text="", font=(MONO, 10), text_color="#806d96")
        self.counter.pack(side="left", expand=True)
        self.pause_button = ctk.CTkButton(controls, text="暂停", width=50, height=27, font=(BODY_FONT, 10), fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=self.toggle_pause)
        self.pause_button.pack(side="right", padx=(4, 0))
        ctk.CTkButton(controls, text="›", width=32, height=27, font=(MONO, 18, "bold"), fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda: self.move(1)).pack(side="right")
        self.show_current()
        if len(self.paths) > 1:
            self.after(self.INTERVAL_MS, self.auto_move)

    def make_image(self, path: Path) -> ctk.CTkImage:
        with Image.open(path) as source:
            image = source.convert("RGBA")
        contained = ImageOps.contain(image, (361, 532), method=Image.Resampling.BICUBIC )
        canvas = Image.new("RGBA", (self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT), (241, 237, 248, 255))
        canvas.alpha_composite(contained, ((self.DISPLAY_WIDTH - contained.width) // 2, (self.DISPLAY_HEIGHT - contained.height) // 2))
        return ctk.CTkImage(light_image=canvas, dark_image=canvas, size=(self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT))

    def show_current(self) -> None:
        try:
            self.current_image = self.make_image(self.paths[self.index])
        except (OSError, ValueError):
            self.image_label.configure(text="图片无法读取", image=None, text_color=DANGER)
            return
        self.image_label.configure(image=self.current_image, text="")
        self.counter.configure(text=f"画廊  {self.index + 1} / {len(self.paths)}")

    def move(self, amount: int) -> None:
        self.index = (self.index + amount) % len(self.paths)
        self.show_current()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.configure(text="继续" if self.paused else "暂停")

    def auto_move(self) -> None:
        if self.winfo_exists():
            if not self.paused:
                self.move(1)
            self.after(self.INTERVAL_MS, self.auto_move)


class WeaponCatalog:
    def __init__(self) -> None:
        raw = json.loads((DATA_DIR / "weapon_data_zh_cn.json").read_text(encoding="utf-8"))
        self.items: list[Weapon] = []
        for entry in raw["weapons"]:
            weapon = entry["weapon"]
            self.items.append(Weapon(
                int(weapon["id"]), weapon.get("name", "未命名"), weapon.get("englishName", "Unknown"),
                str(entry.get("tier") or "?"), str(entry.get("category") or "other"),
                str(entry.get("notes") or entry.get("englishNotes") or "暂无 Wiki 介绍。"),
                entry,
            ))
        self.by_base_id = {item.base_id: item for item in self.items}

    def runtime_id(self, weapon: Weapon, chinese: bool) -> int:
        return weapon.base_id + (1 if chinese else 0)

    def display(self, runtime_id: int, chinese: bool) -> str:
        if runtime_id == 0:
            return "空栏"
        base_id = runtime_id - (1 if chinese else 0)
        item = self.by_base_id.get(base_id)
        if item is None:
            return f"未知武器（运行时 ID {runtime_id}）"
        name = item.chinese if chinese else item.english
        return f"{name}  ·  TIER {item.tier}  ·  ID {runtime_id}"


CATALOG = WeaponCatalog()


class ConfirmDialog(ctk.CTkToplevel):
    def __init__(self, master: ctk.CTk, message: str) -> None:
        super().__init__(master)
        self.result = False
        self.title("覆盖确认")
        self.geometry("560x390")
        self.minsize(520, 340)
        self.resizable(True, True)
        self.configure(fg_color=BG)
        self.transient(master)
        self.grab_set()
        ctk.CTkLabel(self, text="SAVE OVERWRITE?", font=(PIXEL_FONT, 21), text_color=GOLD).pack(anchor="w", padx=24, pady=(24, 6))
        message_label = ctk.CTkLabel(self, text=message, justify="left", wraplength=500, font=(BODY_FONT, 13), text_color=INK)
        message_label.pack(anchor="w", padx=24, fill="x")
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=24, pady=22)
        ctk.CTkButton(actions, text="取消", fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=self.destroy).pack(side="right")
        ctk.CTkButton(actions, text="已退出游戏，继续", fg_color=DANGER, hover_color="#c65b60", command=self.accept).pack(side="right", padx=(0, 8))
        self.update_idletasks()
        # 根据换行后的实际文本高度扩展弹窗，底部两个确认按钮绝不被裁切。
        required_height = max(340, min(600, message_label.winfo_reqheight() + 190))
        self.geometry(f"560x{required_height}")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def accept(self) -> None:
        self.result = True
        self.destroy()


class StepField(ctk.CTkFrame):
    """带 + / - 的小型数值输入；基本属性可传入 0~6 边界。"""
    def __init__(self, master: ctk.CTkFrame, variable: ctk.StringVar, *, minimum: int | None = None, maximum: int | None = None, width: int = 96) -> None:
        super().__init__(master, fg_color="transparent")
        self.variable, self.minimum, self.maximum = variable, minimum, maximum
        ctk.CTkButton(self, text="−", width=24, height=27, font=(MONO, 15, "bold"), fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda: self.adjust(-1)).pack(side="left")
        ctk.CTkEntry(self, textvariable=variable, width=width - 48, height=27, justify="center", font=(MONO, 12), fg_color=INSET, border_color=LINE).pack(side="left", padx=2)
        ctk.CTkButton(self, text="+", width=24, height=27, font=(MONO, 15, "bold"), fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda: self.adjust(1)).pack(side="left")

    def adjust(self, delta: int) -> None:
        try:
            value = float(self.variable.get()) + delta
        except ValueError:
            value = float(self.minimum or 0)
        if self.minimum is not None:
            value = max(self.minimum, value)
        if self.maximum is not None:
            value = min(self.maximum, value)
        self.variable.set(str(int(value)) if value.is_integer() else f"{value:g}")


class WeaponPicker(ctk.CTkToplevel):
    """按名称和 TIER 过滤的武器选择器；分页避免一次渲染数百行。"""
    PAGE_SIZE = 18

    def __init__(self, master: ctk.CTk, *, chinese: bool, callback: Callable[[int], None], allow_empty: bool = False) -> None:
        super().__init__(master)
        self.chinese, self.callback, self.allow_empty = chinese, callback, allow_empty
        self.search = ctk.StringVar()
        self.tier = ctk.StringVar(value="全部")
        self.manual_id = ctk.StringVar()
        self.page = 0
        self.title("选择武器")
        self.geometry("1000x690")
        self.minsize(680, 550)
        self.configure(fg_color=BG)
        self.transient(master)
        self.grab_set()
        self.build()

    def build(self) -> None:
        header = ctk.CTkFrame(self, fg_color=TOP, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(header, text="WEAPON LOCKER", font=(PIXEL_FONT, 21), text_color=GOLD).pack(anchor="w", padx=20, pady=(16, 2))
        ctk.CTkLabel(header, text="按名称搜索；TIER 是 Wiki 资料中的武器等级。当前补丁中文运行时 ID 会在此现场 +1 计算。", font=(BODY_FONT, 11), text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 12))
        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.pack(fill="x", padx=20, pady=(0, 14))
        search = ctk.CTkEntry(controls, textvariable=self.search, placeholder_text="搜索中文名 / English name / ID", width=350, fg_color=INSET, border_color=LINE)
        search.pack(side="left")
        self.search.trace_add("write", lambda *_: self.reset_page())
        ctk.CTkOptionMenu(controls, values=["全部", "S", "A", "B", "C", "D", "E", "F", "G", "P", "?"], variable=self.tier, width=110, command=lambda _: self.reset_page()).pack(side="left", padx=8)
        ctk.CTkEntry(controls, textvariable=self.manual_id, placeholder_text="手动 ID", width=86, fg_color=INSET, border_color=LINE, font=(MONO, 11)).pack(side="right", padx=4)
        ctk.CTkButton(controls, text="使用 ID", width=70, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=self.choose_manual).pack(side="right")
        if self.allow_empty:
            ctk.CTkButton(controls, text="设为空栏", width=90, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda: self.choose(0)).pack(side="right")
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=10)
        footer = ctk.CTkFrame(self, fg_color=TOP, corner_radius=0)
        footer.pack(fill="x")
        self.page_label = ctk.CTkLabel(footer, text="", font=(MONO, 11), text_color=MUTED)
        self.page_label.pack(side="left", padx=16, pady=12)
        ctk.CTkButton(footer, text="上一页", width=75, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda: self.move(-1)).pack(side="right", padx=(5, 14), pady=8)
        ctk.CTkButton(footer, text="下一页", width=75, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda: self.move(1)).pack(side="right", padx=5, pady=8)
        self.render()

    def filtered(self) -> list[Weapon]:
        query = self.search.get().strip().lower()
        tier = self.tier.get()
        result = [item for item in CATALOG.items if tier == "全部" or item.tier == tier]
        if query:
            result = [item for item in result if query in item.chinese.lower() or query in item.english.lower() or query == str(CATALOG.runtime_id(item, self.chinese))]
        return result

    def reset_page(self) -> None:
        self.page = 0
        self.render()

    def move(self, delta: int) -> None:
        count = max(1, (len(self.filtered()) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page = max(0, min(count - 1, self.page + delta))
        self.render()

    def render(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        items = self.filtered()
        total_pages = max(1, (len(items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page = min(self.page, total_pages - 1)
        self.page_label.configure(text=f"{len(items)} 件结果  ·  第 {self.page + 1}/{total_pages} 页")
        visible = items[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]
        if not visible:
            ctk.CTkLabel(self.list_frame, text="没有匹配的武器。", font=(BODY_FONT, 14), text_color=MUTED).pack(pady=40)
        for item in visible:
            row = ctk.CTkFrame(self.list_frame, fg_color=PANEL, corner_radius=0)
            row.pack(fill="x", padx=2, pady=3)
            name = item.chinese if self.chinese else item.english
            runtime_id = CATALOG.runtime_id(item, self.chinese)
            row.grid_columnconfigure(2, weight=1)
            ctk.CTkLabel(row, text=f"{runtime_id:>3}  {name}", width=175, anchor="w", font=(BODY_FONT, 14, "bold"), text_color=INK).grid(row=0, column=0, padx=(9, 4), pady=8, sticky="w")
            ctk.CTkLabel(row, text=f"TIER {item.tier}\n{item.category}", width=70, justify="left", anchor="w", font=(MONO, 10), text_color=GOLD).grid(row=0, column=1, padx=3, pady=5, sticky="w")
            ctk.CTkLabel(row, text=item.note[:58], justify="left", wraplength=170, anchor="w", font=(BODY_FONT, 10), text_color=MUTED).grid(row=0, column=2, padx=5, pady=5, sticky="ew")
            ctk.CTkButton(row, text="详情", width=54, height=27, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda weapon=item: self.details(weapon)).grid(row=0, column=3, padx=3, pady=7)
            ctk.CTkButton(row, text="选择", width=54, height=27, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TOP, command=lambda value=runtime_id: self.choose(value)).grid(row=0, column=4, padx=(3, 8), pady=7)

    def choose(self, runtime_id: int) -> None:
        self.callback(runtime_id)
        self.destroy()

    def choose_manual(self) -> None:
        try:
            runtime_id = int(self.manual_id.get().strip())
        except ValueError:
            return
        if runtime_id < 0 or (runtime_id == 0 and not self.allow_empty):
            return
        self.choose(runtime_id)

    def details(self, weapon: Weapon) -> None:
        WeaponDetailDialog(self, weapon=weapon, chinese=self.chinese, callback=self.choose)


class WeaponDetailDialog(ctk.CTkToplevel):
    """武器选择器的第三级页面：完整显示 Wiki 资料，避免列表页被长文本挤坏。"""
    def __init__(self, master: ctk.CTkToplevel, *, weapon: Weapon, chinese: bool, callback: Callable[[int], None]) -> None:
        super().__init__(master)
        self.weapon, self.chinese, self.callback = weapon, chinese, callback
        self.title("武器详情")
        self.geometry("720x680")
        self.minsize(580, 500)
        self.configure(fg_color=BG)
        self.transient(master)
        self.grab_set()
        self.build()

    @staticmethod
    def value(value: object) -> str:
        if value is None or value == "":
            return "—"
        if isinstance(value, list):
            return "、".join(str(item) for item in value) or "—"
        if isinstance(value, dict):
            return "  ·  ".join(f"{key}: {item}" for key, item in value.items()) or "—"
        return str(value)

    def build(self) -> None:
        runtime_id = CATALOG.runtime_id(self.weapon, self.chinese)
        name = self.weapon.chinese if self.chinese else self.weapon.english
        alternate = self.weapon.english if self.chinese else self.weapon.chinese
        header = ctk.CTkFrame(self, fg_color=TOP, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(header, text=f"{name}  ·  ID {runtime_id}", font=(PIXEL_FONT, 21), text_color=GOLD).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(header, text=f"{alternate}    |    TIER {self.weapon.tier}    |    {self.weapon.category}", font=(MONO, 11), text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 14))
        scroll = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=14, pady=12)
        details = self.weapon.details
        stats = ctk.CTkFrame(scroll, fg_color=PANEL, corner_radius=0)
        stats.pack(fill="x", padx=2, pady=3)
        ctk.CTkLabel(stats, text="战斗参数", font=(PIXEL_FONT, 15), text_color=GOLD).pack(anchor="w", padx=13, pady=(9, 4))
        grid = ctk.CTkFrame(stats, fg_color="transparent")
        grid.pack(fill="x", padx=11, pady=(0, 9))
        fields = [("Power", "power"), ("Cooldown", "cooldown"), ("Knockback", "knockback"), ("Extra Hits", "extraHits"), ("Break Scale", "breakScale"), ("Reload", "reload"), ("Penetrate", "penetrate"), ("Ammunition", "ammunition"), ("Spread", "spread")]
        for index, (label, key) in enumerate(fields):
            cell = ctk.CTkFrame(grid, fg_color=PANEL_ALT, corner_radius=0)
            cell.grid(row=index // 3, column=index % 3, padx=3, pady=3, sticky="ew")
            ctk.CTkLabel(cell, text=label, font=(MONO, 10), text_color=MUTED).pack(anchor="w", padx=7, pady=(4, 0))
            ctk.CTkLabel(cell, text=self.value(details.get(key)), font=(BODY_FONT, 12, "bold"), text_color=INK, wraplength=175, justify="left").pack(anchor="w", padx=7, pady=(0, 5))
        for column in range(3):
            grid.grid_columnconfigure(column, weight=1)
        self.long_section(scroll, "简介", self.weapon.note)
        self.long_section(scroll, "常见地点", self.value(details.get("locations")))
        self.long_section(scroll, "商人 / 事件", f"商人：{self.value(details.get('vendors'))}\n事件：{self.value(details.get('events'))}")
        footer = ctk.CTkFrame(self, fg_color=TOP, corner_radius=0)
        footer.pack(fill="x")
        ctk.CTkButton(footer, text="返回列表", fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=self.destroy).pack(side="right", padx=14, pady=10)
        ctk.CTkButton(footer, text="选用这把武器", fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TOP, command=lambda: self.choose(runtime_id)).pack(side="right", padx=5, pady=10)

    def long_section(self, parent: ctk.CTkScrollableFrame, title: str, content: str) -> None:
        section = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=0)
        section.pack(fill="x", padx=2, pady=3)
        ctk.CTkLabel(section, text=title, font=(PIXEL_FONT, 14), text_color=GOLD).pack(anchor="w", padx=13, pady=(8, 0))
        ctk.CTkLabel(section, text=content, wraplength=620, justify="left", anchor="w", font=(BODY_FONT, 12), text_color=INK).pack(anchor="w", fill="x", padx=13, pady=(0, 9))

    def choose(self, runtime_id: int) -> None:
        self.callback(runtime_id)
        self.destroy()


class TrunkDialog(ctk.CTkToplevel):
    def __init__(self, master: ctk.CTk, *, chinese: bool, items: list[tuple[int, int]], callback: Callable[[list[tuple[int, int]]], None]) -> None:
        super().__init__(master)
        self.chinese, self.callback = chinese, callback
        self.items = [[weapon_id, amount] for weapon_id, amount in items]
        self.title("编辑后备箱武器")
        self.geometry("720x620")
        self.configure(fg_color=BG)
        self.transient(master)
        self.grab_set()
        ctk.CTkLabel(self, text="TRUNK WEAPON LOCKER", font=(PIXEL_FONT, 20), text_color=GOLD).pack(anchor="w", padx=20, pady=(18, 3))
        ctk.CTkLabel(self, text="可添加、移除或更换武器；保存时会安全重建后备箱武器清单。", font=(BODY_FONT, 11), text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 8))
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        self.list_frame.pack(fill="both", expand=True, padx=14, pady=8)
        actions = ctk.CTkFrame(self, fg_color=TOP, corner_radius=0)
        actions.pack(fill="x")
        ctk.CTkButton(actions, text="+ 添加武器", fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TOP, command=self.add).pack(side="left", padx=14, pady=10)
        ctk.CTkButton(actions, text="取消", fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=self.destroy).pack(side="right", padx=14, pady=10)
        ctk.CTkButton(actions, text="应用清单", fg_color=GOLD, hover_color="#bf813a", text_color=TOP, command=self.apply).pack(side="right", padx=5, pady=10)
        self.render()

    def render(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        if not self.items:
            ctk.CTkLabel(self.list_frame, text="后备箱没有武器。可以点击“添加武器”。", text_color=MUTED, font=(BODY_FONT, 14)).pack(pady=40)
        for index, item in enumerate(self.items):
            row = ctk.CTkFrame(self.list_frame, fg_color=PANEL, corner_radius=0)
            row.pack(fill="x", padx=3, pady=4)
            ctk.CTkLabel(row, text=CATALOG.display(item[0], self.chinese), anchor="w", font=(BODY_FONT, 13), text_color=INK).pack(side="left", fill="x", expand=True, padx=12, pady=9)
            ctk.CTkButton(row, text="更换", width=60, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda i=index: self.pick(i)).pack(side="left", padx=4)
            variable = ctk.StringVar(value=str(item[1]))
            variable.trace_add("write", lambda *_args, i=index, var=variable: self.update_amount(i, var))
            StepField(row, variable, minimum=0, width=86).pack(side="left", padx=4)
            ctk.CTkButton(row, text="移除", width=58, fg_color="#97575b", hover_color=DANGER, text_color=TOP, command=lambda i=index: self.remove(i)).pack(side="left", padx=(4, 9))

    def update_amount(self, index: int, variable: ctk.StringVar) -> None:
        try:
            self.items[index][1] = int(variable.get())
        except ValueError:
            pass

    def pick(self, index: int) -> None:
        WeaponPicker(self, chinese=self.chinese, callback=lambda weapon_id: self.replace(index, weapon_id))

    def replace(self, index: int, weapon_id: int) -> None:
        if weapon_id == 0:
            self.remove(index)
            return
        self.items[index][0] = weapon_id
        self.render()

    def add(self) -> None:
        WeaponPicker(self, chinese=self.chinese, callback=lambda weapon_id: self.add_item(weapon_id))

    def add_item(self, weapon_id: int) -> None:
        if weapon_id and all(item[0] != weapon_id for item in self.items):
            self.items.append([weapon_id, 1])
            self.render()

    def remove(self, index: int) -> None:
        self.items.pop(index)
        self.render()

    def apply(self) -> None:
        try:
            result = [(int(weapon_id), int(amount)) for weapon_id, amount in self.items]
        except (ValueError, TypeError):
            return
        self.callback(result)
        self.destroy()


class EditorPanel:
    """编辑页只渲染一名当前队员的属性，以消除旧版读取时的控件卡顿。"""
    def __init__(self, app: "DR2CApp", parent: ctk.CTkFrame, *, custom: bool) -> None:
        self.app, self.parent, self.custom = app, parent, custom
        self.language = ctk.StringVar(value="中文" if custom else "英文")
        self.slot = ctk.StringVar(value="0")
        self.slot_display = ctk.StringVar(value="第 1 位")
        self.model = None
        self.path: Path | None = None
        self.vars: dict[tuple[str, int, int | str | None], ctk.StringVar] = {}
        self.selected_id: int | None = None
        self.trunk_items: list[tuple[int, int]] = []
        self._header()
        self.content = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0)
        self.content.pack(fill="both", expand=True, pady=(8, 0))
        self.empty = ctk.CTkLabel(self.content, text="选择语言与存档位，再点击「读取」。\n读取只分析文件，不会写入。", font=(BODY_FONT, 14), text_color=MUTED)
        self.empty.pack(pady=70)

    def _header(self) -> None:
        bar = ctk.CTkFrame(self.parent, fg_color=TOP, corner_radius=0)
        bar.pack(fill="x")
        ctk.CTkLabel(bar, text="CUSTOM CHARACTER BAY" if self.custom else "ACTIVE SAVE GARAGE", font=(PIXEL_FONT, 18), text_color=GOLD).pack(side="left", padx=16, pady=12)
        ctk.CTkSegmentedButton(bar, values=["英文", "中文"], variable=self.language, selected_color=SELECT_GREEN, selected_hover_color="#d4e9d8", unselected_color=PANEL_ALT, unselected_hover_color=LINE, text_color=INK).pack(side="left", padx=6)
        if not self.custom:
            ctk.CTkLabel(bar, text="存档位", font=(BODY_FONT, 11), text_color=MUTED).pack(side="left", padx=(14, 2))
            ctk.CTkSegmentedButton(bar, values=["第 1 位", "第 2 位", "第 3 位"], variable=self.slot_display, command=self._select_slot, selected_color=SELECT_GOLD, selected_hover_color="#f4e5c8", unselected_color=PANEL_ALT, unselected_hover_color=LINE, text_color=INK, width=180).pack(side="left")
        ctk.CTkButton(bar, text="读取", width=76, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=self.load).pack(side="right", padx=(5, 14))
        ctk.CTkButton(bar, text="保存修改", width=104, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TOP, command=self.save).pack(side="right", padx=5)

    def _select_slot(self, label: str) -> None:
        self.slot.set(str(["第 1 位", "第 2 位", "第 3 位"].index(label)))

    def source_path(self) -> Path:
        return self.app.save_dir / save_filename(int(self.slot.get()), self.language.get() == "中文", self.custom)

    def get_var(self, key: tuple[str, int, int | str | None], value: object) -> ctk.StringVar:
        if key not in self.vars:
            self.vars[key] = ctk.StringVar(value=str(value))
        return self.vars[key]

    def load(self) -> None:
        self.path = self.source_path()
        if not self.path.is_file():
            self.app.notice(f"找不到 {self.path.name}。", error=True)
            return
        try:
            self.model = read_activity(self.path.read_bytes())
        except SaveError as exc:
            self.app.notice(str(exc), error=True)
            return
        self.vars.clear()
        self.trunk_items = sorted((weapon_id, amount) for weapon_id, amount in self.model.trunk_weapons.items() if weapon_id)
        self.selected_id = next(iter(sorted(self.model.characters)), None)
        self.build()
        self.app.notice(f"已读取 {self.path.name}；现在可选择一名角色编辑。")

    def clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def section(self, title: str, subtitle: str = "") -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content, fg_color=PANEL, corner_radius=0)
        frame.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(frame, text=title, font=(PIXEL_FONT, 15), text_color=GOLD).pack(anchor="w", padx=13, pady=(10, 0))
        if subtitle:
            ctk.CTkLabel(frame, text=subtitle, font=(BODY_FONT, 10), text_color=MUTED).pack(anchor="w", padx=13, pady=(0, 7))
        return frame

    def build(self) -> None:
        assert self.model is not None
        self.clear()
        if not self.custom:
            self.resources_panel()
            self.vehicle_panel()
        selector = self.section("队员资料" if not self.custom else "自建角色", "点选队员后只载入这一人的属性控件，避免旧版整页渲染卡顿。")
        cards = ctk.CTkFrame(selector, fg_color="transparent")
        cards.pack(fill="x", padx=12, pady=8)
        for char_id, character in sorted(self.model.characters.items()):
            selected = char_id == self.selected_id
            ctk.CTkButton(cards, text=f"#{char_id}  {character.name or '未命名'}", width=150, fg_color=SELECT_GOLD if selected else PANEL_ALT, hover_color="#f4e5c8" if selected else LINE, text_color=INK, command=lambda value=char_id: self.select_character(value)).pack(side="left", padx=3)
        self.detail_host = ctk.CTkFrame(self.content, fg_color="transparent")
        self.detail_host.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        if self.selected_id is not None:
            self.character_panel()
        if not self.custom:
            trunk = self.section("后备箱武器", "武器选择器可以按名称和 TIER 筛选，支持添加、删除、更换及调整数量/充能。")
            summary = ", ".join(CATALOG.display(weapon_id, self.language.get() == "中文") for weapon_id, _ in self.trunk_items[:3]) or "暂无武器"
            ctk.CTkLabel(trunk, text=summary + (" …" if len(self.trunk_items) > 3 else ""), font=(BODY_FONT, 12), text_color=INK).pack(side="left", padx=13, pady=10)
            ctk.CTkButton(trunk, text="编辑后备箱武器", fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TOP, command=self.edit_trunk).pack(side="right", padx=13, pady=8)

    def resources_panel(self) -> None:
        assert self.model is not None
        icons = {1: "food", 2: "gas", 3: "medical", 4: "pistol_ammo", 5: "rifle_ammo", 6: "shotgun_ammo"}
        frame = self.section("后备箱物资", "直接修改数量；彩色像素图标只作识别，不参与存档数据。")
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=9)
        for resource_id, label in RESOURCE_LABELS.items():
            cell = ctk.CTkFrame(row, fg_color=PANEL_ALT, corner_radius=0)
            cell.pack(side="left", padx=3)
            icon = self.app.asset(f"icons/{icons[resource_id]}.png", (32, 32))
            ctk.CTkLabel(cell, text="", image=icon).pack(side="left", padx=(7, 3), pady=6)
            mini = ctk.CTkFrame(cell, fg_color="transparent")
            mini.pack(side="left", padx=(0, 7), pady=5)
            ctk.CTkLabel(mini, text=label, font=(BODY_FONT, 10), text_color=MUTED).pack(anchor="w")
            StepField(mini, self.get_var(("resource", resource_id, None), self.model.resources.get(resource_id, 0)), minimum=0, width=86).pack(anchor="w")

    def vehicle_panel(self) -> None:
        assert self.model is not None
        frame = self.section("行程与车辆", "剩余天数会自动换算为 road-trip-days。底盘/引擎分别保存当前值和最大值。")
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=13, pady=9)
        values = [
            ("剩余天数", ("remaining", 0, None), self.model.remaining_days or 0, 0, 99),
            ("底盘当前", ("vehicle", 0, "car-chassis"), self.model.vehicle.get("car-chassis", 0), 0, None),
            ("底盘上限", ("vehicle", 0, "car-max-chassis"), self.model.vehicle.get("car-max-chassis", 0), 0, None),
            ("引擎当前", ("vehicle", 0, "car-engine"), self.model.vehicle.get("car-engine", 0), 0, None),
            ("引擎上限", ("vehicle", 0, "car-max-engine"), self.model.vehicle.get("car-max-engine", 0), 0, None),
        ]
        for label, key, value, lower, upper in values:
            cell = ctk.CTkFrame(row, fg_color=PANEL_ALT, corner_radius=0)
            cell.pack(side="left", padx=3)
            ctk.CTkLabel(cell, text=label, font=(BODY_FONT, 10), text_color=MUTED).pack(padx=7, pady=(5, 0))
            StepField(cell, self.get_var(key, value), minimum=lower, maximum=upper, width=94).pack(padx=7, pady=(0, 6))

    def select_character(self, char_id: int) -> None:
        self.selected_id = char_id
        self.build()

    def character_panel(self) -> None:
        assert self.model is not None and self.selected_id is not None
        for child in self.detail_host.winfo_children():
            child.destroy()
        char = self.model.characters[self.selected_id]
        frame = ctk.CTkFrame(self.detail_host, fg_color=PANEL, corner_radius=0)
        frame.pack(fill="both", expand=True)
        ctk.CTkLabel(frame, text=f"CHARACTER #{char.char_id}", font=(PIXEL_FONT, 18), text_color=GOLD).pack(anchor="w", padx=14, pady=(12, 0))
        ctk.CTkLabel(frame, text="请注意，自建角色的PERK / TRAIT 建议在游戏中修改并保存。在此处修改，PERK/TRAIT的开局属性不会生效！！！！\n修改已开局的游戏存档不会修改角色属性，只有部分特质如The Big Shot受影响。请按需同步属性、bonus、武器和物资。", font=(BODY_FONT, 10), text_color=MUTED).pack(anchor="w", padx=14, pady=(0, 8))
        identity = ctk.CTkFrame(frame, fg_color="transparent")
        identity.pack(fill="x", padx=12, pady=4)
        self.text_field(identity, "名字", ("name", char.char_id, None), char.name, 160)
        self.combo_field(identity, "PERK", ("perk", char.char_id, None), char.perk, self.perk_options(), 150)
        self.combo_field(identity, "TRAIT", ("trait", char.char_id, None), char.trait, self.trait_options(), 150)
        self.health_field(frame, char)
        weapons = ctk.CTkFrame(frame, fg_color=INSET, corner_radius=0)
        weapons.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(weapons, text="手持武器", font=(PIXEL_FONT, 13), text_color=GOLD).pack(side="left", padx=10)
        for field, slot in (("weapona", "武器 1"), ("weaponb", "武器 2"), ("weaponc", "武器 3")):
            variable = self.get_var((field, char.char_id, None), char.weapons.get(field, 0))
            button = ctk.CTkButton(weapons, text=f"{slot}：{CATALOG.display(int(variable.get() or 0), self.language.get() == '中文')}", width=205, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, anchor="w", command=lambda var=variable: self.pick_hand_weapon(var))
            button.pack(side="left", padx=3, pady=7)
            variable.trace_add("write", lambda *_args, var=variable, btn=button, label=slot: btn.configure(text=f"{label}：{CATALOG.display(self.safe_int(var.get()), self.language.get() == '中文')}"))
        stats = ctk.CTkFrame(frame, fg_color=INSET, corner_radius=0)
        stats.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(stats, text="基础属性限定 0–6；bonus 是额外加成，最终属性通常为基础 + bonus。每项右侧“显示”开关就是已揭示状态：打开后游戏内属性面板可见，关闭则仍是隐藏属性；它不改变属性数值。", font=(BODY_FONT, 10), text_color=MUTED, wraplength=980, justify="left").pack(anchor="w", padx=9, pady=(7, 3))
        grid = ctk.CTkFrame(stats, fg_color="transparent")
        grid.pack(fill="x", padx=7, pady=(0, 7))
        # 生命上限已在上方和当前 HP 联动显示，不在属性网格重复一遍。
        for index, stat_id in enumerate(stat for stat in sorted(STAT_NAMES) if stat != 12):
            self.stat_card(grid, char, stat_id, index)

    def text_field(self, parent: ctk.CTkFrame, label: str, key: tuple[str, int, int | str | None], value: str, width: int) -> None:
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.pack(side="left", padx=3)
        ctk.CTkLabel(cell, text=label, font=(BODY_FONT, 10), text_color=MUTED).pack(anchor="w")
        ctk.CTkEntry(cell, textvariable=self.get_var(key, value), width=width, fg_color=INSET, border_color=LINE, font=(BODY_FONT, 12)).pack()

    def combo_field(self, parent: ctk.CTkFrame, label: str, key: tuple[str, int, int | str | None], value: str, options: list[str], width: int) -> None:
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.pack(side="left", padx=3)
        ctk.CTkLabel(cell, text=label, font=(BODY_FONT, 10), text_color=MUTED).pack(anchor="w")
        choices = [value] + [option for option in options if option != value]
        ctk.CTkComboBox(cell, values=choices, variable=self.get_var(key, value), width=width, fg_color=INSET, border_color=LINE, button_color=ACCENT, button_hover_color=ACCENT_HOVER, font=(BODY_FONT, 12), dropdown_font=(BODY_FONT, 12)).pack()

    def health_field(self, frame: ctk.CTkFrame, char: object) -> None:
        values = char.stats.get(12, {})
        hp = self.get_var(("hp", char.char_id, None), char.hp if char.hp is not None else 0)
        base = self.get_var(("stat", char.char_id, 12), values.get("stat", 0))
        bonus = self.get_var(("bonus", char.char_id, 12), values.get("bonus", 0))
        known = self.get_var(("knownstat", char.char_id, 12), values.get("knownstat", 0))
        frame_health = ctk.CTkFrame(frame, fg_color="#e5f0e8", corner_radius=0)
        frame_health.pack(fill="x", padx=12, pady=7)
        ctk.CTkLabel(frame_health, text="HP & VITALITY", font=(PIXEL_FONT, 14), text_color=ACCENT).pack(side="left", padx=10)
        ctk.CTkLabel(frame_health, text="当前 HP", font=(BODY_FONT, 10), text_color=MUTED).pack(side="left", padx=(8, 2))
        StepField(frame_health, hp, minimum=0, width=95).pack(side="left")
        ctk.CTkLabel(frame_health, text="生命上限基础", font=(BODY_FONT, 10), text_color=MUTED).pack(side="left", padx=(12, 2))
        StepField(frame_health, base, minimum=0, maximum=6, width=95).pack(side="left")
        ctk.CTkLabel(frame_health, text="bonus", font=(MONO, 10), text_color=MUTED).pack(side="left", padx=(8, 2))
        StepField(frame_health, bonus, width=95).pack(side="left")
        cap = ctk.CTkLabel(frame_health, text="", font=(BODY_FONT, 11, "bold"), text_color=GOLD)
        cap.pack(side="left", padx=10)
        def refresh(*_: object) -> None:
            cap.configure(text=f"有效上限：{self.safe_int(base.get()) + self.safe_int(bonus.get())}")
        base.trace_add("write", refresh)
        bonus.trace_add("write", refresh)
        refresh()
        ctk.CTkSwitch(frame_health, text="已揭示", variable=known, onvalue="1", offvalue="0", fg_color="#4b5350", progress_color=OK, button_color=INK, font=(BODY_FONT, 10)).pack(side="right", padx=10)

    def stat_card(self, parent: ctk.CTkFrame, char: object, stat_id: int, index: int) -> None:
        values = char.stats.get(stat_id, {})
        card = ctk.CTkFrame(parent, fg_color=PANEL_ALT, corner_radius=0)
        card.grid(row=index // 3, column=index % 3, padx=2, pady=2, sticky="ew")
        ctk.CTkLabel(card, text=STAT_LABELS[STAT_NAMES[stat_id]], font=(BODY_FONT, 10, "bold"), text_color=INK).pack(anchor="w", padx=7, pady=(4, 0))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(padx=5, pady=(0, 3))
        ctk.CTkLabel(row, text="基础", font=(BODY_FONT, 9), text_color=MUTED).pack(side="left")
        StepField(row, self.get_var(("stat", char.char_id, stat_id), values.get("stat", 0)), minimum=0, maximum=6, width=86).pack(side="left", padx=(1, 4))
        ctk.CTkLabel(row, text="bonus", font=(MONO, 9), text_color=MUTED).pack(side="left")
        StepField(row, self.get_var(("bonus", char.char_id, stat_id), values.get("bonus", 0)), width=86).pack(side="left", padx=(1, 4))
        ctk.CTkSwitch(row, text="显示", width=52, variable=self.get_var(("knownstat", char.char_id, stat_id), values.get("knownstat", 0)), onvalue="1", offvalue="0", fg_color="#aeb7b1", progress_color=OK, button_color=TOP, text_color=MUTED, font=(BODY_FONT, 9)).pack(side="left")

    def perk_options(self) -> list[str]:
        mapping = load_mapping()["perk"]
        return sorted(mapping.values() if self.language.get() == "中文" else mapping)

    def trait_options(self) -> list[str]:
        mapping = load_mapping()["trait"]
        return sorted(mapping.values() if self.language.get() == "中文" else mapping)

    def pick_hand_weapon(self, variable: ctk.StringVar) -> None:
        WeaponPicker(self.app, chinese=self.language.get() == "中文", allow_empty=True, callback=lambda value: variable.set(str(value)))

    def edit_trunk(self) -> None:
        TrunkDialog(self.app, chinese=self.language.get() == "中文", items=self.trunk_items, callback=self.set_trunk)

    def set_trunk(self, items: list[tuple[int, int]]) -> None:
        self.trunk_items = items
        self.build()

    @staticmethod
    def safe_int(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0

    def save(self) -> None:
        if self.path is None or self.model is None:
            self.app.notice("请先读取存档。", error=True)
            return
        updates: dict[tuple[str, int, int | str | None], int | float | str] = {}
        try:
            for key, variable in self.vars.items():
                field, char_or_id, extra = key
                value = variable.get().strip()
                if field in {"name", "perk", "trait"}:
                    updates[key] = value
                elif field == "remaining":
                    if self.model.near_canada_day is None:
                        raise SaveError("缺少 nearcanada-day，不能安全换算剩余天数。")
                    updates[("road", 0, "road-trip-days")] = self.model.near_canada_day + 1 - int(value)
                elif field == "vehicle":
                    updates[key] = float(value)
                else:
                    numeric = int(value)
                    if field == "stat" and not 0 <= numeric <= 6:
                        raise SaveError("基础属性只能是 0 到 6。请把额外值填入 bonus。")
                    if field == "knownstat" and numeric not in (0, 1):
                        raise SaveError("已揭示只能是 0 或 1。")
                    if field in {"hp", "resource", "weapona", "weaponb", "weaponc"} and numeric < 0:
                        raise SaveError("HP、物资和武器 ID 不能为负数。")
                    updates[key] = numeric
        except ValueError:
            self.app.notice("数值字段只能填写整数；车辆字段可填写小数。", error=True)
            return
        raw = self.path.read_bytes()
        try:
            output = patch_activity(raw, updates)
            if not self.custom:
                output = replace_trunk_weapons(output, self.trunk_items)
        except SaveError as exc:
            self.app.notice(str(exc), error=True)
            return
        self.app.write_with_confirmation(self.path, output, f"将覆盖 {self.path.name}。\n原文件会自动备份到软件目录 backups。\n请确认游戏已完全退出。")


class GlobalStatsPanel:
    """gstats.save / gstats-mod.save 的安全转换与一键升级页。"""
    def __init__(self, app: "DR2CApp", parent: ctk.CTkFrame) -> None:
        self.app, self.parent = app, parent
        self.language = ctk.StringVar(value="英文")
        self.path: Path | None = None
        self.fields: dict[str, int] = {}
        self.header()
        self.content = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0)
        self.content.pack(fill="both", expand=True, pady=(8, 0))
        self.empty = ctk.CTkLabel(self.content, text="全局升级存档记录模式解锁、PERK/TRAIT 解锁等级和累计统计。\n选择版本后点击「读取全局存档」。", font=(BODY_FONT, 14), text_color=MUTED, justify="center")
        self.empty.pack(pady=80)

    def header(self) -> None:
        bar = ctk.CTkFrame(self.parent, fg_color=TOP, corner_radius=0)
        bar.pack(fill="x")
        ctk.CTkLabel(bar, text="GLOBAL PROGRESSION", font=(PIXEL_FONT, 18), text_color=GOLD).pack(side="left", padx=16, pady=12)
        ctk.CTkSegmentedButton(bar, values=["英文", "中文"], variable=self.language, selected_color=SELECT_GREEN, selected_hover_color="#d4e9d8", unselected_color=PANEL_ALT, unselected_hover_color=LINE, text_color=INK).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="读取全局存档", width=108, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=self.load).pack(side="right", padx=14)

    def current_path(self) -> Path:
        return self.app.save_dir / gstats_filename(self.language.get() == "中文")

    def clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def section(self, title: str, subtitle: str = "", *, danger: bool = False) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.content, fg_color="#fff3f1" if danger else PANEL, corner_radius=0)
        frame.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(frame, text=title, font=(PIXEL_FONT, 16), text_color=DANGER if danger else GOLD).pack(anchor="w", padx=14, pady=(11, 0))
        if subtitle:
            ctk.CTkLabel(frame, text=subtitle, font=(BODY_FONT, 11), text_color="#92565a" if danger else MUTED, wraplength=970, justify="left").pack(anchor="w", padx=14, pady=(0, 9))
        return frame

    def load(self) -> None:
        self.path = self.current_path()
        if not self.path.is_file():
            self.app.notice(f"找不到 {self.path.name}。", error=True)
            return
        try:
            self.fields = read_gstats(self.path.read_bytes())
        except (SaveError, OSError) as exc:
            self.app.notice(f"无法读取全局升级存档：{exc}", error=True)
            return
        self.build()
        self.app.notice(f"已读取 {self.path.name}；尚未写入。")

    def build(self) -> None:
        self.clear()
        wins = {name: value for name, value in self.fields.items() if name.startswith("wins-")}
        perks = {name: value for name, value in self.fields.items() if name.startswith("perk-")}
        traits = {name: value for name, value in self.fields.items() if name.startswith("trait-")}
        overview = self.section("当前全局进度", "这是账号级解锁与统计，不是某一局游戏的活动存档。")
        cards = ctk.CTkFrame(overview, fg_color="transparent")
        cards.pack(fill="x", padx=12, pady=(0, 11))
        values = [
            ("模式 / wins", f"{sum(value > 0 for value in wins.values())} / {len(wins)}"),
            ("PERK 已满级", f"{sum(value >= 3 for value in perks.values())} / {len(perks)}"),
            ("TRAIT 已满级", f"{sum(value >= 3 for value in traits.values())} / {len(traits)}"),
            ("全部字段", str(len(self.fields))),
        ]
        for label, value in values:
            card = ctk.CTkFrame(cards, fg_color=PANEL_ALT, corner_radius=0)
            card.pack(side="left", padx=3)
            ctk.CTkLabel(card, text=label, font=(BODY_FONT, 11), text_color=MUTED).pack(padx=13, pady=(6, 0))
            ctk.CTkLabel(card, text=value, font=(PIXEL_FONT, 18), text_color=INK).pack(padx=13, pady=(0, 7))

        transfer = self.section("英文 / 中文全局升级存档互转", "gstats.save 和 gstats-mod.save 的 136 个字段结构与顺序一致。转换会完整复制来源文件，保留所有解锁、统计与累计数据。")
        action = ctk.CTkFrame(transfer, fg_color="transparent")
        action.pack(fill="x", padx=14, pady=(0, 11))
        ctk.CTkButton(action, text="英文 gstats → 中文 gstats-mod", fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TOP, command=lambda: self.convert(False)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(action, text="中文 gstats-mod → 英文 gstats", fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TOP, command=lambda: self.convert(True)).pack(side="left", padx=6)

        warning = self.section(
            "强力解锁操作：请三思",
            "这些按钮会永久覆盖对应字段的现有数值。虽然软件会自动备份，但解锁后再自行重置可能破坏游戏乐趣。操作前务必退出游戏。",
            danger=True,
        )
        ctk.CTkLabel(warning, text="模式解锁原理：所有 wins-* 字段会被直接改为 1，代表“至少通关一次”。这会覆盖已有模式的真实通关次数，以及名称中带 wins 的连胜记录。", font=(BODY_FONT, 11), text_color="#8b454a", wraplength=970, justify="left").pack(anchor="w", padx=14, pady=(0, 8))
        actions = ctk.CTkFrame(warning, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(0, 13))
        ctk.CTkButton(actions, text="一键解锁全部游戏模式", height=38, fg_color=DANGER, hover_color="#aa3e43", text_color=TOP, command=self.unlock_modes).pack(side="left", padx=(0, 7))
        ctk.CTkButton(actions, text="PERK / TRAIT 全部升至 3 级", height=38, fg_color="#97575b", hover_color=DANGER, text_color=TOP, command=self.max_unlocks).pack(side="left", padx=7)

    def convert(self, source_chinese: bool) -> None:
        source = self.app.save_dir / gstats_filename(source_chinese)
        target = self.app.save_dir / gstats_filename(not source_chinese)
        if not source.is_file():
            self.app.notice(f"找不到来源 {source.name}。", error=True)
            return
        try:
            source_data = source.read_bytes()
            read_gstats(source_data)
            if target.is_file() and target.stat().st_size:
                assert_same_gstats_structure(source_data, target.read_bytes())
        except (SaveError, OSError) as exc:
            self.app.notice(f"全局升级存档转换已阻止：{exc}", error=True)
            return
        self.app.write_with_confirmation(target, source_data, f"将把 {source.name} 的全部全局升级数据复制到 {target.name}。\n目标旧文件会备份到软件目录 backups。\n该操作不翻译任何字段，因为两版本结构相同。")

    def unlock_modes(self) -> None:
        self.apply_unlock(
            prefixes=("wins-",),
            value=1,
            message="危险操作：所有 wins-* 字段都会改成 1。\n这代表各模式“已通关一次”，会解锁模式；同时会覆盖原有通关次数和 wins 连胜记录。\n\n确定要继续吗？",
        )

    def max_unlocks(self) -> None:
        self.apply_unlock(
            prefixes=("perk-", "trait-"),
            value=3,
            message="危险操作：所有 perk-* 和 trait-* 字段都会改成最高等级 3。\n这会直接解锁全部 PERK/TRAIT，可能显著降低长期游玩的探索乐趣。\n\n确定要继续吗？",
        )

    def apply_unlock(self, *, prefixes: tuple[str, ...], value: int, message: str) -> None:
        if self.path is None:
            self.app.notice("请先读取要修改的全局升级存档。", error=True)
            return
        try:
            output, count = set_gstats_fields(self.path.read_bytes(), prefixes=prefixes, value=value)
        except (SaveError, OSError) as exc:
            self.app.notice(f"操作已阻止：{exc}", error=True)
            return
        self.app.write_with_confirmation(self.path, output, f"{message}\n\n将修改 {count} 个字段并覆盖 {self.path.name}。原文件会自动备份。")


class DR2CApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DR2C 存档助手 // SAVE EDITOR")
        self.geometry("1500x1080")
        self.minsize(800, 600)
        self.configure(fg_color=BG)
        self.save_dir = DEFAULT_SAVE_DIR
        self.title_clicks = 0
        self.images: dict[tuple[str, tuple[int, int]], ctk.CTkImage] = {}
        self.build()

    def asset(self, relative: str, size: tuple[int, int]) -> ctk.CTkImage:
        key = (relative, size)
        if key not in self.images:
            source = APP_DIR / "resource" / relative
            image = Image.open(source)
            self.images[key] = ctk.CTkImage(light_image=image, dark_image=image, size=size)
        return self.images[key]

    def build(self) -> None:
        top = ctk.CTkFrame(self, fg_color=TOP, corner_radius=0, height=70)
        top.pack(fill="x")
        top.pack_propagate(False)
        title = ctk.CTkLabel(top, text="DR2C  SAVE EDITOR", font=(PIXEL_FONT, 25), text_color=GOLD, cursor="hand2")
        title.pack(side="left", padx=22)
        title.bind("<Button-1>", self.title_click)
        ctk.CTkLabel(top, text=f"v{APP_VERSION} · {APP_CODENAME}  |  ORIGINAL 20260727  ·  CN PATCH 906.2", font=(MONO, 10), text_color=MUTED).pack(side="left", padx=5)
        ctk.CTkButton(top, text="打开存档目录", width=112, fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=lambda: open_folder(self.save_dir)).pack(side="right", padx=16)
        self.status = ctk.CTkLabel(self, text="就绪：请先关闭游戏，再读取、预览或写入。", anchor="w", font=(BODY_FONT, 12), text_color=MUTED)
        self.status.pack(fill="x", padx=18, pady=(7, 0))
        tabs = ctk.CTkTabview(self, fg_color=BG, segmented_button_fg_color=TOP, segmented_button_selected_color=SELECT_GREEN, segmented_button_selected_hover_color="#d4e9d8", segmented_button_unselected_color=PANEL, segmented_button_unselected_hover_color=LINE, text_color=INK)
        tabs.pack(fill="both", expand=True, padx=14, pady=10)
        for name in ("双语转换", "已开局存档编辑", "自建角色", "全局升级存档", "使用说明/开发者"):
            tabs.add(name)
        self.converter(tabs.tab("双语转换"))
        self.activity_editor = EditorPanel(self, tabs.tab("已开局存档编辑"), custom=False)
        self.custom_editor = EditorPanel(self, tabs.tab("自建角色"), custom=True)
        self.global_stats = GlobalStatsPanel(self, tabs.tab("全局升级存档"))
        self.help_page(tabs.tab("使用说明/开发者"))

    def converter(self, tab: ctk.CTkFrame) -> None:
        self.convert_kind = ctk.StringVar(value="活动存档")
        self.convert_direction = ctk.StringVar(value="英文 → 中文")
        self.convert_slot = ctk.StringVar(value="0")
        card = ctk.CTkFrame(tab, fg_color=PANEL, corner_radius=0)
        card.pack(fill="x", padx=14, pady=14)
        ctk.CTkLabel(card, text="MOVE SAVES BETWEEN EDITIONS", font=(PIXEL_FONT, 21), text_color=GOLD).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(card, text="把英文原版与简体中文汉化补丁的同一份存档互相转换，方便更换游戏版本后继续游玩。\n转换会覆盖目标版本的同名存档；执行前可预览，并会自动备份目标。", font=(BODY_FONT, 13), text_color=INK, justify="left").pack(anchor="w", padx=20, pady=(0, 15))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 5))
        ctk.CTkLabel(row, text="要转移的内容", font=(BODY_FONT, 11), text_color=MUTED).pack(side="left", padx=(0, 7))
        ctk.CTkSegmentedButton(row, values=["活动存档", "自建角色"], variable=self.convert_kind, command=lambda _: self.refresh_convert_kind(), selected_color=SELECT_GREEN, selected_hover_color="#d4e9d8", unselected_color=PANEL_ALT, unselected_hover_color=LINE, text_color=INK).pack(side="left")
        ctk.CTkLabel(row, text="转换方向", font=(BODY_FONT, 11), text_color=MUTED).pack(side="left", padx=(25, 7))
        ctk.CTkSegmentedButton(row, values=["英文 → 中文", "中文 → 英文"], variable=self.convert_direction, selected_color=SELECT_GOLD, selected_hover_color="#f4e5c8", unselected_color=PANEL_ALT, unselected_hover_color=LINE, text_color=INK).pack(side="left")
        self.slot_host = ctk.CTkFrame(card, fg_color="transparent")
        self.slot_host.pack(fill="x", padx=20, pady=(5, 4))
        self.deck_notice = ctk.CTkLabel(card, text="", font=(BODY_FONT, 11), text_color=GOLD, justify="left", wraplength=940)
        self.deck_notice.pack(anchor="w", padx=20, pady=(0, 12))
        self.refresh_convert_kind()
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(actions, text="预览这次转换", fg_color=PANEL_ALT, hover_color=LINE, text_color=INK, command=self.preview_conversion).pack(side="right", padx=5)
        ctk.CTkButton(actions, text="备份后执行转换", fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TOP, command=self.convert).pack(side="right", padx=5)
        self.preview_box = ctk.CTkTextbox(tab, height=380, font=(MONO, 12), fg_color=INSET, text_color=INK, border_color=LINE, border_width=1, corner_radius=0)
        self.preview_box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.show_preview("这里会显示来源、目标、将修改的字段数量，以及任何安全阻止原因。\n")

    def refresh_convert_kind(self) -> None:
        for child in self.slot_host.winfo_children():
            child.destroy()
        if self.convert_kind.get() == "活动存档":
            self.deck_notice.configure(text="活动存档跨语言会重置地区／路途随机事件牌堆，避免目标语言版在读取 Forth 状态时中断；这可能让少量已见事件再次出现。两个转换方向都会处理。")
            ctk.CTkLabel(self.slot_host, text="活动存档位", font=(BODY_FONT, 11), text_color=MUTED).pack(side="left", padx=(0, 8))
            for index, label in enumerate(["第 1 个存档位  ·  0.save", "第 2 个存档位  ·  1.save", "第 3 个存档位  ·  2.save"]):
                ctk.CTkButton(self.slot_host, text=label, width=168, fg_color=SELECT_GOLD if self.convert_slot.get() == str(index) else PANEL_ALT, hover_color="#f4e5c8" if self.convert_slot.get() == str(index) else LINE, text_color=INK, command=lambda value=index: self.choose_convert_slot(value)).pack(side="left", padx=3)
        else:
            self.deck_notice.configure(text="")
            ctk.CTkLabel(self.slot_host, text="自建角色没有存档位：会转换 custchars.save 与 custchars-mod.save。", font=(BODY_FONT, 12), text_color=MUTED).pack(side="left")

    def choose_convert_slot(self, slot: int) -> None:
        self.convert_slot.set(str(slot))
        self.refresh_convert_kind()

    def conversion_paths(self) -> tuple[Path, Path, str, bool]:
        custom = self.convert_kind.get() == "自建角色"
        en_to_zh = self.convert_direction.get() == "英文 → 中文"
        slot = int(self.convert_slot.get())
        source = self.save_dir / save_filename(slot, not en_to_zh, custom)
        target = self.save_dir / save_filename(slot, en_to_zh, custom)
        return source, target, "en_to_zh" if en_to_zh else "zh_to_en", not custom

    def show_preview(self, text: str) -> None:
        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", "end")
        self.preview_box.insert("1.0", text)
        self.preview_box.configure(state="disabled")

    def preview_conversion(self) -> tuple[Path, Path, bytes, Path | None, bytes | None] | None:
        source, target, direction, activity = self.conversion_paths()
        if not source.is_file():
            self.show_preview(f"[找不到来源]\n{source.name}\n\n确认你选择的是正确的游戏版本、活动存档位，并且它已存在。\n")
            return None
        source_slot: Path | None = None
        target_slot: Path | None = None
        slot_data: bytes | None = None
        if activity:
            en_to_zh = direction == "en_to_zh"
            source_slot = self.save_dir / slot_filename(int(self.convert_slot.get()), not en_to_zh)
            target_slot = self.save_dir / slot_filename(int(self.convert_slot.get()), en_to_zh)
            if not source_slot.is_file() or source_slot.stat().st_size == 0:
                self.show_preview(
                    f"[已阻止，未写入]\n找不到有效的菜单摘要文件：{source_slot.name}\n\n"
                    "活动存档转换必须同步复制 .slot 文件，否则目标版本的菜单不会显示这个存档位。"
                )
                return None
            slot_data = source_slot.read_bytes()
        try:
            output, report = convert_bytes(source.read_bytes(), direction, activity=activity)
        except (SaveError, OSError) as exc:
            self.show_preview(f"[已阻止，未写入]\n{exc}\n")
            return None
        save_kind = "活动存档" if activity else "自建角色存档"
        slot_note = (f"\n菜单摘要：{source_slot.name}  →  {target_slot.name}（原样复制，让目标版本菜单显示该存档位）。\n" if source_slot and target_slot else "\n自建角色没有 .slot 菜单摘要文件。\n")
        self.show_preview(
            f"转换内容：{save_kind}\n"
            f"来源：{source.name}\n目标：{target.name}\n\n"
            f"将转换：PERK {report.perks} 项、TRAIT {report.traits} 项、武器运行时 ID {report.weapons} 项。\n"
            f"中文名替换为 A1/A2…：{report.renamed} 项。\n"
            + (f"\n跨语言兼容（两个方向一致）：会重置 {report.transient_stacks} 组地区／路途随机事件牌堆；这些牌堆保存的是带语言包 Forth 词标识与富文本的剩余事件序列，不能只翻译显示文字。保留角色、物资、车辆、天数、游戏模式和当前主流程；目标版本会重新生成这些牌堆，后续事件可能重复。逐项无损保留事件牌堆尚未实现。\n" if activity else "")
            +
            f"合计：{report.changed} 个字段。\n{slot_note}\n"
            "下一步：点击「备份后执行转换」才会覆盖目标文件。目标旧文件会备份到软件目录 backups。\n"
            "安全说明：活动存档使用二进制定点替换，原始 Forth 控制字节会保留；未知 perk/trait 会直接阻止转换。\n"
        )
        self.notice("预览完成，尚未写入文件。")
        return source, target, output, target_slot, slot_data

    def convert(self) -> None:
        preview = self.preview_conversion()
        if preview is None:
            return
        _, target, output, target_slot, slot_data = preview
        companion = (target_slot, slot_data) if target_slot is not None and slot_data is not None else None
        slot_line = f"\n同时覆盖菜单摘要：{target_slot.name}。" if target_slot else ""
        self.write_with_confirmation(target, output, f"将覆盖目标文件：{target.name}。{slot_line}\n旧目标会备份到软件目录 backups。\n请务必先完全退出游戏。", companion=companion)

    def write_with_confirmation(self, target: Path, output: bytes, message: str, *, companion: tuple[Path, bytes] | None = None) -> None:
        if game_running():
            message = "检测到 Death Road to Canada 可能仍在运行。\n\n" + message
        dialog = ConfirmDialog(self, message)
        self.wait_window(dialog)
        if not dialog.result:
            self.notice("已取消，未写入任何文件。")
            return
        try:
            backup = backup_and_replace(target, output)
            companion_backup = backup_and_replace(*companion) if companion else None
        except (SaveError, OSError) as exc:
            self.notice(f"写入失败：{exc}；如主存档已写入，请从 backups 恢复后重试。", error=True)
            return
        suffix = f"主存档备份：{backup.name}" if backup else "主目标原本不存在，无需备份"
        if companion:
            suffix += f"；菜单摘要备份：{companion_backup.name}" if companion_backup else "；菜单摘要目标原本不存在，无需备份"
        self.notice(f"写入完成：{target.name}；{suffix}。")

    def help_page(self, tab: ctk.CTkFrame) -> None:
        split = ctk.CTkFrame(tab, fg_color=BG, corner_radius=0)
        split.pack(fill="both", expand=True, padx=14, pady=14)
        left = ctk.CTkFrame(split, fg_color=PANEL, corner_radius=0)
        left.pack(side="left", fill="both", expand=True)
        box = ctk.CTkTextbox(left, font=(BODY_FONT, 13), fg_color=PANEL, text_color=INK, corner_radius=0)
        box.pack(fill="both", expand=True, padx=10, pady=10)
        box.insert("1.0", """使用说明 / 开发者

版本：1.0.1 · 旅途启程

这是用来在英文原版与简体中文汉化补丁之间转移存档的工具，也可以直接编辑捏人和活动存档。

• 操作前完全退出游戏。游戏运行时可能把旧内存存档重新覆盖回来。
• 转换会覆盖目标版本的同名文件，但软件每次都会在自身 backups 文件夹留下完整备份。
• 活动存档混有 Forth 原始控制字节。请不要用普通文本编辑器“另存为”；本工具只替换已识别字段。
• 活动存档在英文／中文间转换时，会重置地区／路途随机事件牌堆：它们控制许多事件的短期不重复，但内部含本地化 Forth 词标识，不能原样跨语言读取。角色、物资、天数、模式和当前主流程会保留；代价是少量已见事件可能再次出现。英→中和中→英都会这样处理，逐项无损保留牌堆尚未实现。
• PERK/TRAIT 改名后，部分每次触发的字符串判定可能有效；开局赠送属性、武器、资源等不会自动重跑。
• 基础属性有效范围为 0–6；bonus 是独立额外加成，通常能让最终属性超过 6。
• 属性编辑区的“显示 / 已揭示”开关只控制该属性是否已经在游戏内面板公开，不会改变属性数值；关闭后，它仍可能被游戏事件重新揭示。
• “全局升级存档”页操作的是 gstats.save / gstats-mod.save；一键模式解锁会把 wins-* 全部写为 1，连胜字段也会被覆盖。PERK/TRAIT 全解锁会写为最高 3 级，请三思。

已测试：原版 20260727，简体中文补丁 906.2。其他版本或 Mod 未经测试，不保证兼容。

开发者：绯海·三代
B站主页：https://space.bilibili.com/1418606
汉化补丁/攻略：https://www.bilibili.com/opus/852265599123849222
全新 Mod 版本资源站：https://dr2c.top/
DR2C Wiki：https://deathroadtocanada.fandom.com/wiki/Death_Road_to_Canada_Wiki

加拿大维修之路：1群 748853148（快满）、2群 634638288、3群 923508276、4群 908091369。
群会定时清理 1 级水友腾位置；频道不会清人，推荐同步加入 QQ 频道：https://pd.qq.com/s/nfetjmmb（尽量不要重复加群）。
""")
        box.configure(state="disabled")
        right = ctk.CTkFrame(split, fg_color="#f1edf8", width=420, corner_radius=0)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)
        ctk.CTkLabel(right, text="SPECIAL VISITOR", font=(PIXEL_FONT, 16), text_color="#765994").pack(pady=(18, 3))
        ctk.CTkLabel(right, text="她会守好你的备份。", font=(BODY_FONT, 11), text_color="#806d96").pack()
        KeqingCarousel(right).pack(fill="x", pady=(3, 6))
        ctk.CTkLabel(right, text="雷光划破死亡之路，\n但不会划坏存档。", font=(BODY_FONT, 13, "bold"), text_color="#654777", justify="center").pack(pady=(0, 9))

    def title_click(self, _: object) -> None:
        self.title_clicks += 1
        if self.title_clicks == 7:
            self.title_clicks = 0
            self.notice("雷光彩蛋已常驻在「使用说明」页面。")

    def notice(self, message: str, *, error: bool = False) -> None:
        self.status.configure(text=("错误：" if error else "") + message, text_color=DANGER if error else MUTED)


if __name__ == "__main__":
    DR2CApp().mainloop()
