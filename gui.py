# -*- coding: utf-8 -*-
"""
宝可梦同人游戏翻译工具 —— 亚克力毛玻璃图形界面。

布局：
  左侧  圆形头像（悬停显示作者信息）+ 标题 + 8 个菜单（悬停放大 + 底部阴影）
  右侧  各功能页面
    · 菜单 1/2/3/4/5/6 右侧带「待操作文件」勾选侧边栏
    · 底部常驻状态条（进度 + 取消）
  菜单 9 为日志页，任务启动后自动跳转过去。
"""
import os
import queue
import subprocess
import threading
import time
import traceback
import webbrowser

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import bridge
import logger
import commands
import config
import env_check
import prefix_dict as PFD
import processor as PR
import settings
import term_sync as TS

log = None  # 延迟到 main() 里初始化


# ================================================================
# 主题：毛玻璃 + 宝可梦配色（精灵球红 / 宝可蓝 / 皮卡丘黄）
# ================================================================
BG_BASE      = "#EAF2FB"
CARD         = "#FAFCFF"
CARD_BORDER  = "#D5E4F5"
CARD_ALT     = "#F1F7FF"
SHADOW       = "#C3D6EC"
ACCENT       = "#2A6DB0"     # 宝可蓝
ACCENT_SOFT  = "#D9E9FA"
ACCENT_DEEP  = "#1B4E82"
POKE_RED     = "#E33539"     # 精灵球红
POKE_YELLOW  = "#FFCB05"     # 皮卡丘黄
TEXT         = "#1E2A38"
TEXT_DIM     = "#5C6B7D"
TEXT_FAINT   = "#92A1B3"
OK_COLOR     = "#2E9E6B"
WARN_COLOR   = "#C97A0B"
ERR_COLOR    = "#D0453F"

# 全局统一微软雅黑；字号在布局允许范围内适度放大
FONT_FAMILY  = "微软雅黑"
FONT         = (FONT_FAMILY, 11)
FONT_B       = (FONT_FAMILY, 11, "bold")
FONT_SMALL   = (FONT_FAMILY, 10)
FONT_TITLE   = (FONT_FAMILY, 13, "bold")
FONT_BIG     = (FONT_FAMILY, 12, "bold")
FONT_MONO    = (FONT_FAMILY, 10)

MENU_ITEMS = [
    ("1", "翻译"),
    ("2", "重翻检查报告"),
    ("3", "术语更新后重翻"),
    ("4", "前缀字典"),
    ("5", "中文润色"),
    ("6", "换行重排"),
    ("7", "Excel 转术语表"),
    ("8", "设置"),
    ("9", "日志"),
]

MENU_KEYS = {
    "1": "translate", "2": "report", "3": "terms", "4": "prefix",
    "5": "polish", "6": "reflow", "7": "excel", "8": "settings",
    "9": "log",
}


# ================================================================
# 小工具
# ================================================================
def round_rect(canvas, x1, y1, x2, y2, r=14, **kw):
    """圆角矩形（spline 近似）。"""
    r = max(0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    pts = [
        x1 + r, y1, x2 - r, y1,
        x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r,
        x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _blend(c1, c2, t):
    """两个 #RRGGBB 之间插值。"""
    def rgb(c):
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    a, b = rgb(c1), rgb(c2)
    return "#%02X%02X%02X" % tuple(
        int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)
    )


def paint_bg(canvas, w, h):
    """画毛玻璃底：柔和渐变 + 几团虚化的光斑。"""
    canvas.delete("all")
    if w < 4 or h < 4:
        return

    steps = 42
    for i in range(steps):
        t = i / (steps - 1)
        y0 = h * i / steps
        y1 = h * (i + 1) / steps + 1
        canvas.create_rectangle(
            0, y0, w, y1, width=0,
            fill=_blend("#E8F0FA", "#F4EEFA", t),
        )

    # 宝可梦配色的柔和光斑（精灵球红 / 宝可蓝 / 皮卡丘黄）
    blobs = [
        (w * 0.12, h * 0.10, min(w, h) * 0.34, "#A9CEFF"),
        (w * 0.88, h * 0.22, min(w, h) * 0.30, "#FFB3B6"),
        (w * 0.70, h * 0.92, min(w, h) * 0.32, "#FFE08A"),
        (w * 0.30, h * 0.66, min(w, h) * 0.24, "#B7E7D6"),
    ]
    for cx, cy, r, color in blobs:
        rings = 16
        for i in range(rings, 0, -1):
            rr = r * i / rings
            canvas.create_oval(
                cx - rr, cy - rr, cx + rr, cy + rr, width=0,
                fill=_blend(color, BG_BASE, 1 - i / (rings + 2)),
            )

    # 右上角一枚淡淡的精灵球
    pokeball_bg(canvas, w - min(w, h) * 0.16, h * 0.17,
                min(w, h) * 0.13, alpha=0.55)


def pokeball_bg(canvas, cx, cy, r, alpha=1.0):
    """在背景上画一个半透明的精灵球（纯装饰）。"""
    def mix(c1, c2, t):
        return _blend(c1, c2, t)
    top = mix("#E33539", BG_BASE, 1 - alpha)
    bottom = mix("#FFFFFF", BG_BASE, 1 - alpha)
    ring = mix("#2B2B2B", BG_BASE, 1 - alpha)
    canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                      start=0, extent=180, fill=top, outline="")
    canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                      start=180, extent=180, fill=bottom, outline="")
    canvas.create_rectangle(cx - r, cy - r * 0.10, cx + r, cy + r * 0.10,
                            fill=ring, outline="")
    canvas.create_oval(cx - r * 0.26, cy - r * 0.26,
                       cx + r * 0.26, cy + r * 0.26,
                       fill=bottom, outline=ring, width=max(1, int(r * 0.08)))


class PokeBall(tk.Canvas):
    """小精灵球图标。"""

    def __init__(self, master, size=22, bg=None):
        bg = bg or CARD
        tk.Canvas.__init__(self, master, width=size, height=size,
                           highlightthickness=0, bg=bg)
        r = size / 2 - 2
        cx = cy = size / 2
        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=0, extent=180, fill=POKE_RED, outline="")
        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=180, extent=180, fill="#FFFFFF",
                        outline="#D5E4F5")
        self.create_rectangle(cx - r, cy - 1.2, cx + r, cy + 1.2,
                              fill="#2B2B2B", outline="")
        self.create_oval(cx - r * 0.28, cy - r * 0.28,
                         cx + r * 0.28, cy + r * 0.28,
                         fill="#FFFFFF", outline="#2B2B2B", width=1)


class RoundCard(tk.Canvas):
    """毛玻璃卡片：圆角 + 描边 + 底部投影，内部放一个 Frame。"""

    def __init__(self, master, radius=16, fill=CARD, border=CARD_BORDER,
                 shadow=SHADOW, pad=14, bg=None, auto_height=False, **kw):
        bg = bg or BG_BASE
        kw.setdefault("width", 10)     # Tk Canvas 默认请求 378x265，会撑爆布局
        kw.setdefault("height", 10)
        tk.Canvas.__init__(self, master, highlightthickness=0, bg=bg, **kw)
        self.radius = radius
        self.fill = fill
        self.border = border
        self.shadow = shadow
        self.pad = pad
        self.auto_height = auto_height   # True: 高度由内容决定（不被拉伸时用）

        self.body = tk.Frame(self, bg=fill)
        self._win = self.create_window(0, 0, window=self.body, anchor="nw")
        self.bind("<Configure>", self._resize)
        if auto_height:
            self.body.bind("<Configure>", self._body_resize)

    def _body_resize(self, e):
        self.configure(height=e.height + self.pad * 2 + 8)

    def _resize(self, _e=None):
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 6 or h < 6:
            return
        self.delete("card")
        p = 3
        round_rect(self, p + 3, p + 4, w - p + 2, h - p + 2,
                   self.radius, fill=self.shadow, outline="", tags="card")
        round_rect(self, p, p, w - p - 2, h - p - 4,
                   self.radius, fill=self.fill,
                   outline=self.border, width=1, tags="card")
        self.coords(self._win, self.pad, self.pad)
        if self.auto_height:
            self.itemconfig(self._win,
                            width=max(10, w - self.pad * 2 - 6))
        else:
            self.itemconfig(self._win,
                            width=max(10, w - self.pad * 2 - 6),
                            height=max(10, h - self.pad * 2 - 8))


# 术语列表复选框（Treeview 首列以字符呈现勾选状态）
TERM_CHECK_ON = "☑"
TERM_CHECK_OFF = "☐"


class GlassButton(tk.Canvas):
    """圆角玻璃按钮。"""

    def __init__(self, master, text="", command=None, width=120, height=36,
                 primary=False, bg=None, font=None, state=True):
        bg = bg or BG_BASE
        tk.Canvas.__init__(self, master, width=width, height=height,
                           highlightthickness=0, bg=bg, cursor="hand2")
        self.command = command
        self.w = width
        self.h = height
        self.primary = primary
        self.font = font or (FONT_BIG if primary else FONT)
        self.text = text
        self.enabled = state
        self._hover = False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _colors(self):
        if not self.enabled:
            return "#E8ECF2", "#B9C2CE"
        if self.primary:
            return (ACCENT if not self._hover else _blend(ACCENT, "#FFFFFF", .15)), "#FFFFFF"
        return (CARD if not self._hover else ACCENT_SOFT), TEXT

    def _draw(self, pressed=False):
        self.delete("all")
        fill, fg = self._colors()
        off = 2 if (self._hover and self.enabled) else 0
        if self.enabled:
            round_rect(self, 3, 4, self.w - 2, self.h - 2 + off, 10,
                       fill=SHADOW, outline="")
        round_rect(self, 2, 2 - off, self.w - 4, self.h - 5 - off, 10,
                   fill=fill,
                   outline=(self.border_color() if not self.primary else fill),
                   width=1)
        self.create_text(
            self.w // 2, (self.h - 4 - off) // 2 + (1 if not off else 0),
            text=self.text, fill=fg, font=self.font,
        )

    def border_color(self):
        return ACCENT if self._hover else CARD_BORDER

    def _on_enter(self, _e):
        self._hover = True
        self._draw()

    def _on_leave(self, _e):
        self._hover = False
        self._draw()

    def _on_press(self, _e):
        if self.enabled:
            self._draw(pressed=True)

    def _on_release(self, _e):
        if not self.enabled:
            return
        self._draw()
        if self.command:
            self.command()

    def set_enabled(self, ok):
        self.enabled = bool(ok)
        self.configure(cursor="hand2" if ok else "arrow")
        self._draw()


class MenuItem(tk.Canvas):
    """左侧菜单项：悬停略微放大 + 底部阴影。"""

    def __init__(self, master, index, text, command=None,
                 width=188, height=44):
        tk.Canvas.__init__(self, master, width=width, height=height,
                           highlightthickness=0, bg=CARD, cursor="hand2")
        self.command = command
        self.w = width
        self.h = height
        self.text = text
        self.index = index
        self._hover = False
        self._active = False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", lambda e: self.command and self.command())

    def _draw(self):
        self.delete("all")
        grow = 3 if self._hover else 0
        x1, y1, x2, y2 = 3 - grow, 3 - grow, self.w - 4 + grow, self.h - 5 + grow

        if self._hover:
            # 底部阴影
            for i in range(6, 0, -1):
                round_rect(self, x1 + i * .4, y1 + i * .8,
                           x2 - i * .4, y2 + i * 1.1, 11,
                           fill=_blend(SHADOW, CARD, 1 - i / 7.0), outline="")

        if self._active:
            fill, fg, outline = ACCENT_SOFT, ACCENT, ACCENT
        elif self._hover:
            fill, fg, outline = _blend(CARD, "#FFFFFF", .6), TEXT, CARD_BORDER
        else:
            fill, fg, outline = CARD_ALT, TEXT, CARD_BORDER

        round_rect(self, x1, y1, x2, y2, 11, fill=fill, outline=outline, width=1)
        self.create_text(16, (y1 + y2) / 2, anchor="w",
                         text=self.index, fill=TEXT_FAINT,
                         font=(FONT_FAMILY, 10, "bold"))
        self.create_text(36, (y1 + y2) / 2, anchor="w",
                         text=self.text,
                         fill=fg,
                         font=(FONT_FAMILY, 11 + grow // 3,
                               "bold" if (self._active or self._hover) else "normal"))

    def set_active(self, on):
        self._active = bool(on)
        self._draw()

    def _on_enter(self, _e):
        self._hover = True
        self._draw()

    def _on_leave(self, _e):
        self._hover = False
        self._draw()


_AVATAR_CACHE = {}


class Avatar(tk.Canvas):
    """圆形头像，悬停弹出作者信息。"""

    def __init__(self, master, size=68, path=None):
        tk.Canvas.__init__(self, master, width=size, height=size,
                           highlightthickness=0, bg=CARD, cursor="hand2")
        self.size = size
        self.path = path
        self._photo = None
        self._tip = None
        self._tip_job = None

        self._load_image()
        # 不再画白色光圈：图片本身已按圆形 alpha 裁剪，圆外完全透明

        self.bind("<Enter>", self._schedule_tip)
        self.bind("<Leave>", self._hide_tip)
        self.bind("<ButtonRelease-1>", self._toggle_tip)

    # ---------- 图像 ----------
    def _load_image(self):
        s = self.size              # ★ 图片必须与画布同尺寸，圆形裁剪才可见
        photo = None
        key = (self.path, s)
        if key in _AVATAR_CACHE:
            photo = _AVATAR_CACHE[key]
        elif self.path and os.path.exists(self.path):
            try:
                from PIL import Image, ImageTk, ImageDraw
                Image.MAX_IMAGE_PIXELS = None     # 原图很大，解除告警阈值
                im = Image.open(self.path)
                # draft() 让 JPEG 在解码阶段就降采样，避免解码上亿像素
                try:
                    im.draft("RGB", (s, s))
                except Exception:
                    pass
                im = im.convert("RGBA").resize((s, s), Image.LANCZOS)
                mask = Image.new("L", (s, s), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, s, s), fill=255)
                im.putalpha(mask)
                photo = ImageTk.PhotoImage(im)
                _AVATAR_CACHE[key] = photo
            except Exception as e:
                photo = None
                try:
                    if log:
                        log.debug("头像加载失败：%s", e)
                except Exception:
                    pass

        if photo is not None:
            self._photo = photo          # 防 GC
            self.create_image(self.size // 2, self.size // 2, image=photo)
            return

        # 兜底：画一个渐变圆 + 首字
        r = self.size // 2 - 5
        cx = cy = self.size // 2
        for i in range(10, 0, -1):
            rr = r * i / 10
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, width=0,
                             fill=_blend("#F6C7DC", "#BFD7FF", 1 - i / 10))
        self.create_text(cx, cy, text="玛", fill="#FFFFFF",
                         font=(FONT_FAMILY, 22, "bold"))

    # ---------- 悬停信息 ----------
    def _schedule_tip(self, _e=None):
        self._cancel_hide()
        self._tip_job = self.after(180, self._show_tip)

    def _cancel_hide(self):
        if self._tip_job:
            try:
                self.after_cancel(self._tip_job)
            except Exception:
                pass
            self._tip_job = None

    def _show_tip(self):
        self._tip_job = None
        if self._tip and self._tip.winfo_exists():
            return

        tip = tk.Toplevel(self)
        tip.wm_overrideredirect(True)
        tip.configure(bg=BG_BASE)
        tip.attributes("-topmost", True)

        outer = tk.Frame(tip, bg=CARD, highlightthickness=1,
                         highlightbackground=CARD_BORDER)
        outer.pack(padx=6, pady=6)

        pad = {"padx": 14, "pady": 3}
        tk.Label(outer, text=config.AUTHOR_NAME, bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w", **pad)
        tk.Frame(outer, bg=CARD_BORDER, height=1).pack(fill="x", padx=12, pady=4)

        tk.Label(outer, text="GitHub", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(anchor="w", padx=14)
        lb1 = tk.Label(outer, text=config.AUTHOR_GITHUB, bg=CARD, fg=ACCENT,
                       font=FONT_SMALL, cursor="hand2")
        lb1.pack(anchor="w", padx=14)
        lb1.bind("<Button-1>", lambda e: webbrowser.open(config.AUTHOR_GITHUB))

        tk.Label(outer, text="Bilibili", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(anchor="w", padx=14, pady=(6, 0))
        lb2 = tk.Label(outer, text="玛俐大小姐想让我告白", bg=CARD, fg=ACCENT,
                       font=FONT_SMALL, cursor="hand2")
        lb2.pack(anchor="w", padx=14)
        lb2.bind("<Button-1>", lambda e: webbrowser.open(config.AUTHOR_BILIBILI))

        tk.Label(outer, text=f"{config.APP_NAME}  v{config.VERSION}",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL).pack(
            anchor="w", padx=14, pady=(8, 10))

        tip.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() + 6
        y = self.winfo_rooty()
        sw, sh = tip.winfo_screenwidth(), tip.winfo_screenheight()
        if x + tip.winfo_width() > sw:
            x = max(0, self.winfo_rootx() - tip.winfo_width() - 6)
        if y + tip.winfo_height() > sh:
            y = max(0, sh - tip.winfo_height() - 10)
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide_tip(self, _e=None):
        self._cancel_hide()
        if self._tip and self._tip.winfo_exists():
            self._tip.destroy()
        self._tip = None

    def _toggle_tip(self, _e=None):
        if self._tip and self._tip.winfo_exists():
            self._hide_tip()
        else:
            self._show_tip()


def make_scroll_area(parent, bg=CARD):
    """返回 (outer_frame, inner_frame)，带滚动条与滚轮支持。"""
    outer = tk.Frame(parent, bg=bg)
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0)
    sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=bg)

    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)

    # ★ 画布宽度决定 inner 宽度（经典写法：两个 Configure 各管各的）
    def _on_canvas_cfg(e):
        canvas.itemconfig(win, width=e.width)
    canvas.bind("<Configure>", _on_canvas_cfg)

    def _on_inner_cfg(_e):
        canvas.configure(scrollregion=canvas.bbox("all"))
    inner.bind("<Configure>", _on_inner_cfg)

    def _wheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        return "break"

    def _enter(_e):
        canvas.bind_all("<MouseWheel>", _wheel)

    def _leave(_e):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", _enter)
    canvas.bind("<Leave>", _leave)

    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return outer, inner


def bind_tree_wheel(tree):
    """给列表加上滚轮滚动（内容溢出时滚动条 + 滚轮都能用）。"""
    def _wheel(e):
        tree.yview_scroll(int(-1 * (e.delta / 120)), "units")
        return "break"

    def _enter(_e):
        tree.bind_all("<MouseWheel>", _wheel)

    def _leave(_e):
        tree.unbind_all("<MouseWheel>")

    tree.bind("<Enter>", _enter)
    tree.bind("<Leave>", _leave)


def bind_tree_edit(tree, columns, on_commit=None):
    """
    让 Treeview 的指定列可双击编辑。
    columns: {列 id: 是否可编辑}
    """
    editable = set(columns.keys())

    def on_double(e):
        row = tree.identify_row(e.y)
        if not row:
            return
        col = tree.identify_column(e.x)      # "#1" / "#2" ...
        if col not in editable:
            return
        if not tree.bbox(row, col):
            return
        x, y, w, h = tree.bbox(row, col)
        old = tree.set(row, col)

        entry = tk.Entry(tree, font=FONT, bd=1, relief="solid",
                         highlightthickness=1,
                         highlightbackground=ACCENT)
        entry.insert(0, old)
        entry.select_range(0, "end")
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()

        def commit(_e=None):
            if not entry.winfo_exists():
                return
            val = entry.get()
            entry.destroy()
            if val != old:
                tree.set(row, col, val)
                if on_commit:
                    on_commit(row, col, val)

        def cancel(_e=None):
            entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", cancel)

    tree.bind("<Double-1>", on_double)


# ================================================================
# Windows 亚克力 / 毛玻璃
# ================================================================
def enable_acrylic(hwnd, tint="#F3F7FD", alpha=0xC8):
    """让窗口背景变成真正的亚克力模糊（Win10 1709+）。失败静默降级。"""
    if os.name != "nt":
        return False
    try:
        import ctypes

        class ACCENT_POLICY(ctypes.Structure):
            _fields_ = [("AccentState", ctypes.c_int),
                        ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_uint),
                        ("AnimationId", ctypes.c_int)]

        class WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [("Attribute", ctypes.c_int),
                        ("Data", ctypes.POINTER(ACCENT_POLICY)),
                        ("SizeOfData", ctypes.c_size_t)]

        tint = tint.lstrip("#")
        r, g, b = (int(tint[i:i + 2], 16) for i in (0, 2, 4))
        gradient = (int(alpha) << 24) | (b << 16) | (g << 8) | r

        accent = ACCENT_POLICY()
        accent.AccentState = 4          # ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags = 0
        accent.GradientColor = gradient
        accent.AnimationId = 0

        data = WINCOMPATTRDATA()
        data.Attribute = 19             # WCA_ACCENT_POLICY
        data.Data = ctypes.pointer(accent)
        data.SizeOfData = ctypes.sizeof(accent)

        fn = getattr(ctypes.windll.user32, "SetWindowCompositionAttribute", None)
        if fn is None:
            return False
        return bool(fn(hwnd, ctypes.byref(data)))
    except Exception:
        return False


def apply_window_effects(root):
    """亚克力 + 轻微透明 + 圆角（均容错）。"""
    try:
        root.update_idletasks()
        hwnd = root.winfo_id()
        enable_acrylic(hwnd, tint="#EAF3FC", alpha=0xD0)
        try:
            import ctypes
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), ctypes.c_uint(33),
                ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int(2)))
        except Exception:
            pass
        root.attributes("-alpha", 0.975)
    except Exception:
        pass


# ================================================================
# 文件侧边栏
# ================================================================
class FilePanel(tk.Frame):
    """
    右侧「待操作文件」侧边栏：单个文件 / 整个文件夹 + 勾选列表。

    mode:
      "source" —— 菜单 1/3/4/5：不限格式，只跳过 *_translated.txt
                  与 *_translated_report.txt
      "report" —— 菜单 2：只识别 *_translated_report.txt
    """

    # 菜单 1/3/4/5 需要跳过的后缀
    SKIP_SUFFIX = ("_translated.txt", "_translated_report.txt")

    def __init__(self, master, bg=CARD, width=252, mode="source",
                 on_change=None):
        tk.Frame.__init__(self, master, bg=bg, width=width)
        self.bg = bg
        self.mode = mode
        self.on_change = on_change
        self.files = []
        self.vars = {}

        tk.Label(self, text="待操作文件", bg=bg, fg=TEXT,
                 font=FONT_B).pack(anchor="w", padx=10, pady=(8, 4))

        row = tk.Frame(self, bg=bg)
        row.pack(fill="x", padx=10)
        GlassButton(row, "单个文件", width=72, height=28, bg=bg,
                    font=FONT_SMALL, command=self.pick_file).pack(side="left")
        GlassButton(row, "整个文件夹", width=76, height=28, bg=bg,
                    font=FONT_SMALL, command=self.pick_dir).pack(
            side="left", padx=6)

        row2 = tk.Frame(self, bg=bg)
        row2.pack(fill="x", padx=10, pady=(6, 2))
        GlassButton(row2, "全选", width=52, height=26, bg=bg,
                    font=FONT_SMALL, command=self.select_all).pack(side="left")
        GlassButton(row2, "清空", width=52, height=26, bg=bg,
                    font=FONT_SMALL, command=self.clear).pack(side="left", padx=6)
        self.count_lbl = tk.Label(row2, text="已选 0", bg=bg, fg=TEXT_DIM,
                                  font=FONT_SMALL)
        self.count_lbl.pack(side="right")

        outer, inner = make_scroll_area(self, bg=bg)
        outer.pack(fill="both", expand=True, padx=6, pady=(4, 8))
        self.list_inner = inner

        self._hint = tk.Label(inner, text=self._hint_text(),
                              bg=bg, fg=TEXT_FAINT, font=FONT_SMALL,
                              justify="left", wraplength=210)
        self._hint.pack(anchor="w", padx=6, pady=10)

    # ---------- 筛选规则 ----------
    def _hint_text(self):
        if self.mode == "report":
            return "点击上方按钮选择检查报告\n（只识别 *_translated_report.txt）"
        return "点击上方按钮选择文件\n（不限格式，自动跳过译文与检查报告）"

    def _accept(self, name):
        low = name.lower()
        if self.mode == "report":
            return low.endswith("_translated_report.txt")
        return not low.endswith(self.SKIP_SUFFIX)

    def _filter(self, paths):
        return [p for p in paths
                if os.path.isfile(p) and self._accept(os.path.basename(p))]

    # ---------- 选择 ----------
    def _initial(self):
        d = config.Runtime.last_dir
        return d if d and os.path.isdir(d) else config.BASE_DIR

    def pick_file(self):
        if self.mode == "report":
            title = "选择检查报告（*_translated_report.txt）"
            types = [("检查报告", "*_translated_report.txt"),
                     ("所有文件", "*.*")]
        else:
            title = "选择要处理的文件"
            types = [("所有文件", "*.*")]
        paths = filedialog.askopenfilenames(
            title=title, initialdir=self._initial(), filetypes=types)
        paths = self._filter(list(paths))
        if paths:
            config.Runtime.set_dir(os.path.dirname(paths[0]))
            self.add_files(paths)

    def pick_dir(self):
        folder = filedialog.askdirectory(
            title="选择文件夹", initialdir=self._initial())
        if not folder:
            return
        config.Runtime.set_dir(folder)
        files = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if self._accept(f)
        )
        if not files:
            messagebox.showinfo("提示", self._hint_text().replace("\n", ""))
            return
        self.add_files(files)

    def add_files(self, paths, silent=False):
        if self._hint and self._hint.winfo_exists():
            self._hint.destroy()
            self._hint = None
        added = 0
        for p in paths:
            if p in self.vars:
                continue
            var = tk.BooleanVar(value=True)
            self.vars[p] = var
            cb = tk.Checkbutton(
                self.list_inner, text=os.path.basename(p),
                variable=var, bg=self.bg, fg=TEXT,
                activebackground=self.bg, activeforeground=TEXT,
                selectcolor="#FFFFFF", font=FONT_SMALL,
                anchor="w", relief="flat",
                command=self._update_count,
            )
            cb.pack(fill="x", padx=6, pady=1)
            self.files.append(p)
            added += 1
        self._update_count()
        if added and not silent and self.on_change:
            self.on_change(self.files)

    def set_files(self, paths):
        """整体替换（用于菜单之间的同步）。"""
        keep = dict(self.vars)
        self.clear(silent=True)
        self.add_files(self._filter(list(paths)), silent=True)

    def clear(self, silent=False):
        for w in self.list_inner.winfo_children():
            w.destroy()
        self.files = []
        self.vars = {}
        self._hint = tk.Label(
            self.list_inner, text=self._hint_text(),
            bg=self.bg, fg=TEXT_FAINT, font=FONT_SMALL, justify="left",
            wraplength=210)
        self._hint.pack(anchor="w", padx=6, pady=10)
        self._update_count()
        if not silent and self.on_change:
            self.on_change([])

    def select_all(self):
        for v in self.vars.values():
            v.set(True)
        self._update_count()

    def _update_count(self):
        n = sum(1 for v in self.vars.values() if v.get())
        self.count_lbl.config(text=f"已选 {n}")

    def selected(self):
        return [p for p, v in self.vars.items() if v.get()]

    def ensure(self):
        """没选文件时尝试用当前默认文件；仍为空返回 []。"""
        sel = self.selected()
        if sel:
            return sel
        cur = config.Runtime.input_file
        if self.mode == "report":
            cur = commands.report_path_for(cur)
        if cur and os.path.exists(cur):
            self.add_files([cur])
            return self.selected()
        return []


# ================================================================
# 添加术语弹窗
# ================================================================
class TermDialog(tk.Toplevel):
    """「添加术语」弹窗：输入原文与译文，结果放在 self.result = (原文, 译文)。"""

    def __init__(self, master, src_lang="", tgt_lang=""):
        tk.Toplevel.__init__(self, master, bg=BG_BASE)
        self.result = None
        self.title("添加术语")
        self.resizable(False, False)
        self.transient(master)

        card = RoundCard(self, radius=16, pad=16, width=452,
                         auto_height=True)
        card.pack(padx=12, pady=12)
        body = card.body

        tk.Label(body, text="添加术语", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w")
        tk.Label(body,
                 text="新术语会立即写入术语字典；点「应用术语」时会删除\n"
                      "相关句子的缓存并重新翻译。",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(2, 10))

        self.src_var = tk.StringVar()
        self.dst_var = tk.StringVar()
        first = None
        for text, var in ((f"原文（{src_lang or '源语言'}）", self.src_var),
                          (f"译文（{tgt_lang or '目标语言'}）", self.dst_var)):
            row = tk.Frame(body, bg=CARD)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=text, bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                     width=16, anchor="w").pack(side="left")
            ent = ttk.Entry(row, textvariable=var, width=26, font=FONT)
            ent.pack(side="left", padx=6)
            if first is None:
                first = ent

        btns = tk.Frame(body, bg=CARD)
        btns.pack(fill="x", pady=(14, 0))
        GlassButton(btns, "取消", width=76, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._cancel).pack(side="right")
        GlassButton(btns, "确定添加", width=110, height=32, primary=True,
                    bg=CARD, font=FONT_SMALL,
                    command=self._ok).pack(side="right", padx=6)

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        self._center(master)
        if first is not None:
            first.focus_set()
        try:
            self.grab_set()
        except Exception:
            pass

    def _center(self, master):
        try:
            x = master.winfo_rootx() + (master.winfo_width()
                                        - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height()
                                        - self.winfo_height()) // 3
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass

    def _ok(self):
        txt_src = self.src_var.get().strip()
        txt_dst = self.dst_var.get().strip()
        if not txt_src or not txt_dst:
            messagebox.showwarning("提示", "原文与译文都不能为空", parent=self)
            return
        self.result = (txt_src, txt_dst)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, master, src_lang="", tgt_lang=""):
        """弹出对话框并等待结果；返回 (原文, 译文)，取消则返回 None。"""
        dlg = cls(master, src_lang, tgt_lang)
        master.wait_window(dlg)
        return dlg.result


# ================================================================
# 主应用
# ================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self._cancel_flag = False
        self.pages = {}
        self.menu_btns = {}
        self.file_panels = []
        self._mode_btn_groups = []
        self.current = None

        self.src_var = tk.StringVar(value=config.SOURCE_LANG)
        self.tgt_var = tk.StringVar(value=config.TARGET_LANG)
        self.model_var = tk.StringVar(value=config.MODEL)
        self.model_combos = []
        self.models = []
        self.status_var = tk.StringVar(value="就绪")
        self.prog_var = tk.DoubleVar(value=0)

        self.term_rows = {}        # 术语表：iid → [来源, 原文, 译文]
        self.term_edits = {}       # 原文 → 新译文
        self.term_deletes = set()  # 待删除原文集合（应用前可撤回）
        self.term_delete_stack = []  # 删除操作栈，支持逐步撤回
        self.term_checks = set()   # 勾选的术语原文（供批量删除使用）
        self.term_added = []       # 本次「添加术语」新增的原文（应用术语时强制重翻）
        self._term_visible = []    # 当前过滤后可见的术语原文（顺序同列表）
        self.prefix_rows = {}      # 前缀表：iid → [原文, 译文]
        self.prefix_edits = {}
        self.sheet_vars = {}       # Excel sheet → BooleanVar
        self.setting_widgets = {}  # key → (widget, typ)

        self._style()
        self._build_root()
        self._build_sidebar()
        self._build_content()
        self._build_status()

        bridge.set_sinks(
            print_fn=lambda s: self.q.put(("log", s)),
            progress_fn=lambda d, t, x: self.q.put(("prog", (d, t, x))),
            cancel_fn=lambda: self._cancel_flag,
        )
        # logging 记录同步到「运行日志」页，与命令行里看到的内容一致
        logger.set_gui_sink(lambda s: self.q.put(("log", s)))

        self.root.after(80, self._pump)
        self.root.after(300, self._detect_models_async)
        self.root.after(500, self._env_check_async)
        self.root.after(1500, lambda: self._check_update(silent=True))

        self.show("translate")

    # ---------------- 样式 ----------------
    def _style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure(".", font=FONT, background=BG_BASE, foreground=TEXT)
        st.configure("TFrame", background=BG_BASE)
        st.configure("TLabel", background=CARD, foreground=TEXT)
        st.configure("TCombobox", fieldbackground="#FFFFFF",
                     background="#FFFFFF", bordercolor=CARD_BORDER,
                     lightcolor=CARD_BORDER, darkcolor=CARD_BORDER,
                     arrowcolor=TEXT_DIM, padding=3)
        st.map("TCombobox", fieldbackground=[("readonly", "#FFFFFF")])
        st.configure("TEntry", fieldbackground="#FFFFFF",
                     bordercolor=CARD_BORDER, padding=3)
        st.configure("Treeview", background="#FFFFFF",
                     fieldbackground="#FFFFFF", borderwidth=0,
                     rowheight=28, font=FONT)
        st.configure("Treeview.Heading", background="#EAF3FC",
                     foreground=ACCENT_DEEP, font=FONT_B, borderwidth=0,
                     relief="flat")
        st.map("Treeview",
               background=[("selected", ACCENT_SOFT)],
               foreground=[("selected", TEXT)])
        # ★ 滚动条：保证内容溢出时右侧始终有可用（可点可拖）的滚动条
        st.configure("TScrollbar", troughcolor="#E6EFFA",
                     background="#A9C4E4", borderwidth=0,
                     arrowcolor=ACCENT_DEEP, arrowsize=15, width=13)
        st.map("TScrollbar",
               background=[("active", ACCENT), ("pressed", ACCENT_DEEP)])
        st.configure("TProgressbar", troughcolor="#E4EDF8",
                     background=ACCENT, borderwidth=0, thickness=8)
        st.configure("TCheckbutton", background=CARD, foreground=TEXT)
        st.map("TCheckbutton", background=[("active", CARD)])

    # ---------------- 根布局 ----------------
    def _build_root(self):
        self.root.title(config.APP_TITLE)
        self.root.configure(bg=BG_BASE)
        self.root.minsize(1080, 680)
        try:
            self.root.geometry("1200x780")
        except Exception:
            pass
        try:
            icon = config.ICON_FILE
            if os.path.exists(icon):
                self.root.iconbitmap(icon)
        except Exception:
            pass

        self.bg_canvas = tk.Canvas(self.root, highlightthickness=0, bg=BG_BASE)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lower(self.bg_canvas)      # Canvas.lower() 是 tag_lower，别调错
        self.bg_canvas.bind("<Configure>", self._paint_root_bg)

        self.root.grid_columnconfigure(0, minsize=228)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

    def _paint_root_bg(self, e=None):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        paint_bg(self.bg_canvas, w, h)

    # ---------------- 左侧栏 ----------------
    def _build_sidebar(self):
        holder = tk.Frame(self.root, bg=BG_BASE, width=228)
        holder.grid(row=0, column=0, sticky="nsew", padx=(14, 6), pady=14)
        holder.pack_propagate(False)   # 子卡片是 pack 管理的

        card = RoundCard(holder, radius=18, pad=12)
        card.pack(fill="both", expand=True)
        body = card.body

        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x", pady=(2, 8))
        Avatar(head, size=66, path=config.AVATAR_FILE).pack(anchor="w")

        tk.Frame(body, bg=CARD_BORDER, height=1).pack(fill="x", pady=(2, 8))

        for idx, name in MENU_ITEMS:
            btn = MenuItem(body, idx, name,
                           command=lambda k=MENU_KEYS[idx]: self.show(k))
            btn.pack(fill="x", pady=3)
            self.menu_btns[MENU_KEYS[idx]] = btn

        tip = tk.Label(body, text="悬停头像查看作者信息", bg=CARD,
                       fg=TEXT_FAINT, font=FONT_SMALL)
        tip.pack(side="bottom", pady=(8, 0))

    # ---------------- 内容区 ----------------
    def _build_content(self):
        holder = tk.Frame(self.root, bg=BG_BASE)
        holder.grid(row=0, column=1, sticky="nsew", padx=(6, 14), pady=14)
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        for key in MENU_KEYS.values():
            page = tk.Frame(holder, bg=BG_BASE)
            page.grid(row=0, column=0, sticky="nsew")
            bgc = tk.Canvas(page, highlightthickness=0, bg=BG_BASE)
            bgc.place(x=0, y=0, relwidth=1, relheight=1)
            bgc.bind("<Configure>",
                     lambda e, c=bgc: paint_bg(c, e.width, e.height))
            self.pages[key] = page

        self._page_translate()
        self._page_report()
        self._page_terms()
        self._page_prefix()
        self._page_polish()
        self._page_reflow()
        self._page_excel()
        self._page_settings()
        self._page_log()

    # ---------------- 状态条 ----------------
    def _build_status(self):
        holder = tk.Frame(self.root, bg=BG_BASE, height=52)
        holder.grid(row=1, column=0, columnspan=2, sticky="ew",
                    padx=14, pady=(0, 12))
        holder.pack_propagate(False)   # 子控件是 pack 管理的，须用 pack_propagate

        card = RoundCard(holder, radius=14, pad=10)
        card.pack(fill="both", expand=True)
        body = card.body

        PokeBall(body, size=20).pack(side="left")
        self.status_lbl = tk.Label(body, textvariable=self.status_var,
                                   bg=CARD, fg=TEXT_DIM, font=FONT_SMALL)
        self.status_lbl.pack(side="left", padx=6)

        self.cancel_btn = GlassButton(body, "取消", width=70, height=28,
                                      bg=CARD, font=FONT_SMALL,
                                      command=self._on_cancel)
        self.cancel_btn.pack(side="right")
        self.cancel_btn.set_enabled(False)

        bar = ttk.Progressbar(body, variable=self.prog_var,
                              maximum=100, mode="determinate")
        bar.pack(side="right", fill="x", expand=True, padx=10)

    # ================================================================
    # 页面切换
    # ================================================================
    def show(self, key):
        if key not in self.pages:
            return
        if self.current == key:
            return
        self.current = key
        self.pages[key].tkraise()
        for k, btn in self.menu_btns.items():
            btn.set_active(k == key)
        if key == "terms":
            self._load_term_rows()
        elif key == "prefix":
            self._load_prefix_rows()
        elif key == "reflow":
            self._load_reflow_blocks()
        elif key == "log":
            pass

    def _make_file_panel(self, holder, mode):
        """统一创建右侧文件侧边栏，并把菜单 1 的选择同步给其余菜单。"""
        fp = FilePanel(holder.body, bg=CARD, mode=mode,
                       on_change=self._sync_file_panels)
        fp.pack(fill="both", expand=True)
        # ★ 别写 (self.file_panels or []).append() —— 空列表会被换成临时列表
        if self.file_panels is None:
            self.file_panels = []
        self.file_panels.append(fp)
        return fp

    def _sync_file_panels(self, paths):
        """
        菜单 1（翻译）选中文件后，自动同步到菜单 2~5。
        菜单 2 只认检查报告，所以这里做一次「源文件 → 报告」的换算。
        """
        paths = list(paths or [])
        for fp in self.file_panels:
            if fp is None or not fp.winfo_exists():
                continue
            if fp.mode == "report":
                target = [commands.report_path_for(p) for p in paths]
                target = [t for t in target if t and os.path.exists(t)]
                if not target:
                    continue
            else:
                target = paths
            fp.set_files(target)

    def _on_cancel(self):
        if not self.busy:
            return
        self._cancel_flag = True
        bridge.request_cancel()
        self.status_var.set("正在取消…（稍等当前批次结束）")

    # ================================================================
    # 通用控件
    # ================================================================
    def _labeled_combo(self, parent, text, var, values, width=18, side="left"):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=4, side=side, expand=(side == "left"))
        tk.Label(row, text=text, bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL, width=8, anchor="w").pack(side="left")
        cb = ttk.Combobox(row, textvariable=var, values=values, width=width,
                          state="normal", font=FONT)
        cb.pack(side="left", padx=6)
        return cb

    def _model_row(self, parent, label="模型"):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL, width=8, anchor="w").pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.model_var,
                          values=self.models or [config.MODEL],
                          width=22, state="normal", font=FONT)
        cb.pack(side="left", padx=6)
        self.model_combos.append(cb)
        GlassButton(row, "检测", width=58, height=28, bg=CARD,
                    font=FONT_SMALL,
                    command=self._detect_models_async).pack(side="left", padx=6)
        return cb

    # ---------- 翻译模式 ----------
    def _mode_row(self, parent, label="模式"):
        """本地 Ollama / 云端 API 切换。"""
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL, width=8, anchor="w").pack(side="left")

        holder = tk.Frame(row, bg=CARD_BORDER)
        holder.pack(side="left", padx=6)
        group = {}
        for mode, text in (("ollama", "本地 Ollama"), ("api", "云端 API")):
            btn = tk.Label(holder, text=text, font=FONT_SMALL,
                           padx=12, pady=5, cursor="hand2")
            btn.pack(side="left", padx=(1, 1), pady=1)
            btn.bind("<Button-1>",
                     lambda _e, m=mode: self._switch_mode(m))
            group[mode] = btn
        self._mode_btn_groups.append(group)
        self._paint_mode_row()
        return row

    def _paint_mode_row(self):
        cur = settings.current_mode()
        for group in getattr(self, "_mode_btn_groups", []):
            for mode, btn in group.items():
                if not btn.winfo_exists():
                    continue
                on = (mode == cur)
                btn.configure(bg=ACCENT if on else CARD,
                              fg="#FFFFFF" if on else TEXT_DIM)

    def _switch_mode(self, mode):
        mode = settings.normalize_mode(mode)
        if mode == settings.current_mode():
            return
        changes = settings.set_mode(mode)
        self._paint_mode_row()
        self.src_var.set(config.SOURCE_LANG)
        self.tgt_var.set(config.TARGET_LANG)
        self.model_var.set(config.API_MODEL if mode == "api"
                           else config.MODEL)
        self._detect_models_async()

        if changes:
            lines = [f"· {name}：{old}  →  {new}"
                     for name, old, new in changes]
            messagebox.showinfo(
                "已切换翻译模式",
                f"模式：{settings.MODE_LABELS[mode]}\n\n"
                "已自动调整对应参数，用户需适配修改：\n" + "\n".join(lines))
        else:
            messagebox.showinfo("已切换翻译模式",
                                f"模式：{settings.MODE_LABELS[mode]}")

    def _detect_models_async(self):
        def work():
            models = settings.list_models()
            self.q.put(("models", models))
        threading.Thread(target=work, daemon=True).start()

    def _apply_models(self, models):
        self.models = models or []
        cur = config.API_MODEL if settings.current_mode() == "api" else config.MODEL
        vals = self.models or [cur]
        for cb in self.model_combos:
            if cb.winfo_exists():
                cb.configure(values=vals)
        if (settings.current_mode() == "ollama" and self.models
                and self.model_var.get() not in self.models):
            self.model_var.set(self.models[0])
        # ★ 云端检测失败时把原因写进运行日志，避免「只显示一个模型」却不知为何
        if settings.current_mode() == "api" and not self.models:
            reason = settings.api_models_error() or "未知原因"
            self._append_log(
                f"[模型检测] 未能获取云端模型列表：{reason}"
                f"（当前只显示已填写的模型 {cur}）")

    def _env_check_async(self):
        def work():
            try:
                res = env_check.check_all(verbose=False)
                self.q.put(("env", res))
            except Exception as e:
                self.q.put(("env", {"error": str(e)}))
        threading.Thread(target=work, daemon=True).start()

    # ================================================================
    # 任务执行
    # ================================================================
    def set_busy(self, on, label=None):
        self.busy = on
        self.cancel_btn.set_enabled(on)
        for _, btn in self.menu_btns.items():
            pass
        if on:
            self._cancel_flag = False
            bridge.reset_cancel()
            self.prog_var.set(0)
            self.status_var.set(label or "运行中…")
        else:
            self.status_var.set(label or "就绪")

    def run_async(self, fn, label="运行中…", done_label="完成"):
        if self.busy:
            messagebox.showinfo("提示", "已有任务在运行，请稍候")
            return
        self.set_busy(True, label)

        def work():
            try:
                result = fn()
                self.q.put(("done", (result, done_label)))
            except bridge.CancelRequested:
                self.q.put(("done", (None, "已取消")))
            except Exception:
                self.q.put(("err", traceback.format_exc()))

        threading.Thread(target=work, daemon=True).start()

    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "prog":
                    self._on_progress(*payload)
                elif kind == "models":
                    self._apply_models(payload)
                elif kind == "env":
                    self._on_env(payload)
                elif kind == "done":
                    _result, label = payload
                    self.set_busy(False, label)
                    self.prog_var.set(100)
                    self._append_log(f"\n=== {label} ===\n")
                elif kind == "term_reload":
                    self._reset_term_pending(keep_added=bool(payload))
                elif kind == "report":
                    self.set_busy(False, "检查完成")
                    self._fill_report(payload)
                elif kind == "prefix_done":
                    messagebox.showinfo("完成",
                                        "前缀字典已写入并应用到翻译文件")
                elif kind == "excel_done":
                    if payload and payload.get("ok"):
                        messagebox.showinfo(
                            "完成",
                            f"共 {payload.get('total')} 条术语 → "
                            f"{payload.get('out_path')}")
                    else:
                        messagebox.showwarning(
                            "未完成",
                            "；".join((payload or {}).get("errors", [])
                                      or ["提取失败"]))
                elif kind == "update":
                    has, info, silent = payload
                    self._on_update_result(has, info, silent)
                elif kind == "err":
                    self.set_busy(False, "出错")
                    self._append_log("\n[异常] " + payload + "\n")
        except queue.Empty:
            pass
        self.root.after(90, self._pump)

    def _append_log(self, text):
        try:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", text if text.endswith("\n") else text + "\n")
            if len(self.log_text.get("1.0", "end-1c")) > 200000:
                self.log_text.delete("1.0", "50000.0")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except Exception:
            pass

        line = (text or "").strip().splitlines()
        if line:
            self.status_var.set(line[-1][:110])

    def _on_progress(self, done, total, text):
        try:
            if total:
                self.prog_var.set(min(100.0, 100.0 * (done or 0) / max(1, total)))
            if text:
                self.status_var.set(str(text)[:110])
        except Exception:
            pass

    def _on_env(self, res):
        if not isinstance(res, dict) or "error" in res:
            self.status_var.set("环境检查失败")
            return
        ok_service = res.get("ollama_service", (False, ""))[0]
        ok_model = res.get("ollama_model", (False, ""))[0]
        msg = res.get("ollama_service", (False, ""))[1]
        if ok_service and ok_model:
            self.status_var.set(f"Ollama 就绪：{msg}")
        elif ok_service:
            self.status_var.set("Ollama 已连接，但模型未安装：" + config.MODEL)
        else:
            self.status_var.set(f"Ollama 未连接：{msg}（翻译功能不可用）")

    # ================================================================
    # 页面 1：翻译
    # ================================================================
    def _page_translate(self):
        page = self.pages["translate"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # 上层：语言
        c1 = RoundCard(left, radius=16, pad=18)
        c1.configure(height=104)
        c1.pack_propagate(False)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="语言选择", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w")
        row = tk.Frame(c1.body, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        self._labeled_combo(row, "源语言", self.src_var, LANG_VALUES, 14)
        self._labeled_combo(row, "目标语言", self.tgt_var, LANG_VALUES, 14)

        # 中层：模型
        c2 = RoundCard(left, radius=16, pad=18)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tk.Label(c2.body, text="模型与模式", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w")
        self._mode_row(c2.body)
        self._model_row(c2.body)
        tk.Label(c2.body,
                 text="本地模式自动检测已安装的 Ollama 模型；"
                      "云端模式填写 API 地址与密钥后可用。",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(8, 0))

        # 下层：开始
        c3 = RoundCard(left, radius=16, pad=18)
        c3.configure(height=92)
        c3.pack_propagate(False)
        c3.grid(row=2, column=0, sticky="ew")
        GlassButton(c3.body, "开始翻译", width=180, height=44,
                    primary=True, bg=CARD,
                    command=self._do_translate).pack(anchor="w")
        tk.Label(c3.body, text="点击后跳转到日志页，实时查看进度",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL).pack(anchor="w",
                                                               pady=(6, 0))

        # 右侧文件栏
        fp_holder = RoundCard(page, radius=16, pad=8, width=252)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "source")
        self.fp_translate = fp

    def _do_translate(self):
        paths = self.fp_translate.ensure()
        if not paths:
            messagebox.showwarning("提示", "请先在右侧选择要翻译的文件")
            return
        src, tgt, model = self.src_var.get(), self.tgt_var.get(), self.model_var.get()
        if src and tgt and src == tgt:
            if not messagebox.askyesno("确认", f"源语言与目标语言相同（{src}），继续？"):
                return
        self.show("log")
        self.run_async(
            lambda: commands.translate_paths(paths, src, tgt, model),
            label=f"翻译 {len(paths)} 个文件…",
            done_label="翻译完成",
        )

    # ================================================================
    # 页面 2：重翻检查报告
    # ================================================================
    def _page_report(self):
        page = self.pages["report"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        c1 = RoundCard(left, radius=16, pad=18)
        c1.configure(height=158)
        c1.pack_propagate(False)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="语言与模型", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w")
        row = tk.Frame(c1.body, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        self._labeled_combo(row, "源语言", self.src_var, LANG_VALUES, 12)
        self._labeled_combo(row, "目标语言", self.tgt_var, LANG_VALUES, 12)
        self._mode_row(c1.body)
        self._model_row(c1.body)

        c2 = RoundCard(left, radius=16, pad=14)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        head = tk.Frame(c2.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="报告内容", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(side="left")
        GlassButton(head, "刷新报告", width=86, height=28, bg=CARD,
                    font=FONT_SMALL, command=self._do_check).pack(side="left",
                                                                  padx=10)
        self.report_stat = tk.Label(head, text="尚未检查", bg=CARD,
                                    fg=TEXT_DIM, font=FONT_SMALL)
        self.report_stat.pack(side="right")

        wrap = tk.Frame(c2.body, bg=CARD)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        cols = ("kind", "line", "src", "dst", "detail")
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=8)
        for c, w, t in (("kind", 90, "类型"), ("line", 50, "行"),
                        ("src", 210, "原文"), ("dst", 210, "译文"),
                        ("detail", 260, "说明")):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.report_tree = tree
        bind_tree_wheel(tree)

        c3 = RoundCard(left, radius=16, pad=18)
        c3.configure(height=92)
        c3.pack_propagate(False)
        c3.grid(row=2, column=0, sticky="ew")
        GlassButton(c3.body, "开始重翻", width=180, height=44,
                    primary=True, bg=CARD,
                    command=self._do_retranslate_report).pack(anchor="w")
        tk.Label(c3.body,
                 text="删除这些问题句的缓存并重新翻译（仅处理可修复类型）",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL).pack(anchor="w",
                                                               pady=(6, 0))

        fp_holder = RoundCard(page, radius=16, pad=8, width=252)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "report")
        self.fp_report = fp

    def _do_check(self):
        paths = self._report_sources()
        if not paths:
            messagebox.showwarning("提示",
                                   "请先选择检查报告（*_translated_report.txt）")
            return

        def work():
            res = commands.check_paths(paths)
            self.q.put(("report", res))

        if self.busy:
            messagebox.showinfo("提示", "已有任务在运行")
            return
        self.set_busy(True, "正在检查…")
        threading.Thread(target=work, daemon=True).start()

    def _fill_report(self, result):
        tree = self.report_tree
        for iid in tree.get_children():
            tree.delete(iid)
        total = 0
        for path, hits in (result or {}).items():
            for h in hits:
                total += 1
                tree.insert("", "end", values=(
                    h.get("kind", ""), h.get("line_no", ""),
                    (h.get("src") or "")[:200],
                    (h.get("dst") or "")[:200],
                    (h.get("detail") or "")[:200],
                ))
        self.report_stat.config(
            text=f"共 {total} 处问题 / {len(result or {})} 个文件")
        self.status_var.set(f"检查完成：{total} 处问题")

    def _report_sources(self):
        """菜单 2 里选的是检查报告，这里换回真正的源文件。"""
        paths = self.fp_report.ensure()
        srcs = []
        for p in paths:
            s = commands.source_path_for_report(p)
            if s:
                srcs.append(s)
            else:
                self._append_log(f"[跳过] 找不到报告对应的源文件：{p}\n")
        return srcs

    def _do_retranslate_report(self):
        paths = self._report_sources()
        if not paths:
            messagebox.showwarning("提示", "请先选择要重翻的文件")
            return
        src, tgt, model = self.src_var.get(), self.tgt_var.get(), self.model_var.get()
        self.show("log")
        self.run_async(
            lambda: commands.retranslate_report_paths(paths, src, tgt, model),
            label="重翻检查报告内容…",
            done_label="重翻完成",
        )

    # ================================================================
    # 页面 3：术语更新后重翻
    # ================================================================
    def _page_terms(self):
        page = self.pages["terms"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        c1 = RoundCard(left, radius=16, pad=18)
        c1.configure(height=158)
        c1.pack_propagate(False)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="语言与模型", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w")
        row = tk.Frame(c1.body, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        self._labeled_combo(row, "源语言", self.src_var, LANG_VALUES, 12)
        self._labeled_combo(row, "目标语言", self.tgt_var, LANG_VALUES, 12)
        self._mode_row(c1.body)
        self._model_row(c1.body)

        # 术语列表（中下层）
        c2 = RoundCard(left, radius=16, pad=14)
        c2.grid(row=1, column=0, sticky="nsew")
        head = tk.Frame(c2.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="术语列表（双击译文可编辑）", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(side="left")
        self.term_stat = tk.Label(head, text="", bg=CARD, fg=TEXT_DIM,
                                  font=FONT_SMALL)
        self.term_stat.pack(side="right")

        bar = tk.Frame(c2.body, bg=CARD)
        bar.pack(fill="x", pady=(6, 4))
        tk.Label(bar, text="搜索", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")
        self.term_search = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.term_search, width=18)
        ent.pack(side="left", padx=6)
        ent.bind("<KeyRelease>", lambda e: self._filter_terms())
        self.term_filter = tk.StringVar(value="全部")
        for lab, val in (("全部", "全部"), ("自动提取", "AUTO"),
                         ("本次新增", "新增")):
            tk.Radiobutton(bar, text=lab, value=val,
                           variable=self.term_filter, bg=CARD, fg=TEXT,
                           activebackground=CARD, selectcolor="#FFFFFF",
                           font=FONT_SMALL,
                           command=self._filter_terms).pack(side="left", padx=4)
        GlassButton(bar, "重新载入", width=76, height=26, bg=CARD,
                    font=FONT_SMALL,
                    command=self._load_term_rows).pack(side="left", padx=8)

        # 全选 / 取消全选（表头开关，支持半选 indeterminate）
        selbar = tk.Frame(c2.body, bg=CARD)
        selbar.pack(fill="x", pady=(2, 0))
        self.term_all_var = tk.IntVar(value=0)
        # ★ 用经典 tk.Checkbutton：ttk 的不保证支持 tristatevalue，
        #   而半选状态必须靠 -1 这个 tristatevalue 呈现
        self.term_all_chk = tk.Checkbutton(
            selbar, text="全选", variable=self.term_all_var,
            onvalue=1, offvalue=0, tristatevalue=-1,
            bg=CARD, fg=TEXT, activebackground=CARD,
            selectcolor="#FFFFFF", font=FONT_SMALL,
            command=self._on_term_toggle_all)
        self.term_all_chk.pack(side="left")
        self.term_check_stat = tk.Label(selbar, text="已选 0 条", bg=CARD,
                                        fg=TEXT_DIM, font=FONT_SMALL)
        self.term_check_stat.pack(side="left", padx=8)

        wrap = tk.Frame(c2.body, bg=CARD)
        wrap.pack(fill="both", expand=True)
        cols = ("sel", "origin", "src", "dst")
        tree = ttk.Treeview(wrap, columns=cols, show="headings",
                            height=10, selectmode="extended")
        for c, w, t in (("sel", 34, "✓"), ("origin", 86, "来源"),
                        ("src", 210, "原文"), ("dst", 210, "译文（可编辑）")):
            tree.heading(c, text=t)
            tree.column(c, width=w,
                        anchor="center" if c == "sel" else "w")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        # ★ 多了一列复选，译文可编辑列由 #3 变为 #4
        bind_tree_edit(tree, {"#4": True}, on_commit=self._on_term_edit)
        bind_tree_wheel(tree)
        tree.bind("<Button-1>", self._on_term_tree_click)
        self.term_tree = tree

        bottom = tk.Frame(c2.body, bg=CARD)
        bottom.pack(fill="x", pady=(8, 0))
        left_b = tk.Frame(bottom, bg=CARD)
        left_b.pack(side="left")
        tk.Label(left_b,
                 text="改动会写入术语字典",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL).pack(side="left")
        right_b = tk.Frame(bottom, bg=CARD)
        right_b.pack(side="right")
        GlassButton(right_b, "添加术语", width=84, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_term_add).pack(side="left", padx=4)
        GlassButton(right_b, "删除选中", width=84, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_term_delete_selected).pack(side="left",
                                                                padx=4)
        self.term_batch_btn = GlassButton(
            right_b, "批量删除", width=84, height=32, bg=CARD,
            font=FONT_SMALL, command=self._on_term_batch_delete)
        self.term_batch_btn.pack(side="left", padx=4)
        self.term_batch_btn.set_enabled(False)   # 未勾选任何术语时禁用
        GlassButton(right_b, "撤回", width=64, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_term_undo_delete).pack(side="left", padx=4)
        GlassButton(right_b, "应用术语", width=120, height=36, primary=True,
                    bg=CARD, command=self._do_apply_terms).pack(side="left",
                                                               padx=(8, 0))

        fp_holder = RoundCard(page, radius=16, pad=8, width=252)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "source")
        self.fp_terms = fp

    def _load_term_rows(self):
        _cur = {}
        try:
            auto = TS.load_auto_block()
        except Exception:
            auto = []
        try:
            _cur, added, _rm, modified, _ok = commands.analyze_terms()
        except Exception:
            added, modified = None, None

        added_set = {str(a) for a in (added or [])}

        rows = []
        for k, v in auto:
            rows.append(("新增" if k in added_set else "AUTO", k, v))
        for k in added_set:
            if any(r[1] == k for r in rows):
                continue
            rows.append(("新增", k,
                         _cur.get(k, "") if isinstance(_cur, dict) else ""))

        self._term_all = rows
        self._filter_terms()

    def _filter_terms(self):
        tree = self.term_tree
        for iid in tree.get_children():
            tree.delete(iid)
        kw = (self.term_search.get() or "").strip().lower()
        mode = self.term_filter.get()
        n = 0
        visible = []
        for origin, k, v in getattr(self, "_term_all", []):
            if k in self.term_deletes:
                continue  # 待删除：从列表隐藏
            edited = k in self.term_edits
            if edited:
                v = self.term_edits[k]
            if mode != "全部" and origin != mode:
                continue
            if kw and kw not in str(k).lower() and kw not in str(v).lower():
                continue
            visible.append(k)
            tree.insert("", "end",
                        values=(TERM_CHECK_ON if k in self.term_checks
                                else TERM_CHECK_OFF,
                                origin + ("·改" if edited else ""), k, v))
            n += 1
        self._term_visible = visible
        if hasattr(self, "term_stat"):
            total = len(getattr(self, "_term_all", []))
            parts = [f"显示 {n} 条 / 共 {total} 条"]
            if self.term_added:
                parts.append(f"本次新增术语 {len(self.term_added)} 条")
            if self.term_edits:
                parts.append(f"已改动 {len(self.term_edits)} 条")
            if self.term_deletes:
                parts.append(f"待删除 {len(self.term_deletes)} 条")
                if self.term_delete_stack:
                    parts.append(f"（可撤回 {len(self.term_delete_stack)} 次）")
            self.term_stat.config(text="，".join(parts))

        # 同步表头全选状态（含半选）与批量删除按钮可用性
        self._sync_term_all_state()

    def _on_term_edit(self, row, col, value):
        try:
            item = self.term_tree.item(row)
            src = item["values"][2]          # ★ 首列是复选框，索引顺移
            origin = str(item["values"][1]).replace("·改", "")
            self.term_edits[src] = value
            self.term_deletes.discard(src)  # 编辑与删除冲突时，编辑优先
            self.term_tree.set(row, "origin", origin + "·改")
        except Exception:
            pass

    # ---------- 术语删除 / 批量删除 / 撤回 ----------
    def _mark_delete(self, keys):
        """把一批 key 加入待删除集合，并压入撤回栈（应用前可撤回）。"""
        keys = [k for k in keys if k and k not in self.term_deletes]
        if not keys:
            return
        # 与编辑冲突时编辑优先撤销：整条删除会移除该术语
        for k in keys:
            self.term_edits.pop(k, None)
        self.term_deletes.update(keys)
        self.term_delete_stack.append(set(keys))
        self._filter_terms()
        self.q.put(("log", f"已标记删除 {len(keys)} 条术语（应用前可撤回）\n"))

    def _on_term_delete_selected(self):
        sel = self.term_tree.selection()
        keys = []
        for iid in sel:
            try:
                keys.append(self.term_tree.item(iid)["values"][2])
            except Exception:
                pass
        if not keys:
            messagebox.showinfo("提示", "请先在列表里选中要删除的术语（可多选）")
            return
        self._mark_delete(keys)

    def _on_term_batch_delete(self):
        """只删除已勾选的术语（批量操作，需确认）。"""
        vis = list(getattr(self, "_term_visible", []) or [])
        keys = [k for k in vis if k in self.term_checks]
        if not keys:
            messagebox.showinfo(
                "提示",
                "请先勾选要删除的术语：\n"
                "· 点每行最前面的复选框单独勾选\n"
                "· 或点列表上方「全选」一次性勾选")
            return
        if not messagebox.askyesno(
                "确认批量删除",
                f"确定删除已勾选的 {len(keys)} 条术语？\n"
                "（在「应用术语」之前都可以点「撤回」取消）"):
            return
        self._mark_delete(keys)
        # 已删除的术语从勾选集合里移除，再刷新列表与全选状态
        self.term_checks.difference_update(keys)
        self._filter_terms()

    # ---------- 勾选：行复选框 / 表头全选 ----------
    def _on_term_tree_click(self, event):
        """点首列复选框切换勾选；其它列保持正常选中与双击编辑。"""
        tree = self.term_tree
        if tree.identify_column(event.x) != "#1":
            return
        iid = tree.identify_row(event.y)
        if not iid:
            return
        try:
            k = tree.item(iid)["values"][2]
        except Exception:
            return
        if k in self.term_checks:
            self.term_checks.discard(k)
        else:
            self.term_checks.add(k)
        tree.set(iid, "sel",
                 TERM_CHECK_ON if k in self.term_checks else TERM_CHECK_OFF)
        self._sync_term_all_state()
        return "break"

    def _on_term_toggle_all(self):
        """表头全选 / 取消全选；半选（indeterminate）时点击 = 全选。"""
        vis = list(getattr(self, "_term_visible", []) or [])
        if not vis:
            self._sync_term_all_state()
            return
        if self.term_all_var.get() == 0:
            self.term_checks.difference_update(vis)   # 取消全选
        else:
            self.term_checks.update(vis)              # 全选
        self._refresh_term_checks()

    def _refresh_term_checks(self):
        """只刷新每行的勾选标记，不重建列表（保留滚动位置）。"""
        tree = self.term_tree
        for iid in tree.get_children():
            try:
                k = tree.item(iid)["values"][2]
            except Exception:
                continue
            tree.set(iid, "sel",
                     TERM_CHECK_ON if k in self.term_checks
                     else TERM_CHECK_OFF)
        self._sync_term_all_state()

    def _sync_term_all_state(self):
        """按可见行的勾选情况，同步全选框三态与批量删除按钮可用性。"""
        vis = list(getattr(self, "_term_visible", []) or [])
        n = sum(1 for k in vis if k in self.term_checks)
        if vis and n >= len(vis):
            state = 1        # 全部勾选
        elif n == 0 or not vis:
            state = 0        # 一个都没勾
        else:
            state = -1       # 半选（indeterminate）
        if hasattr(self, "term_all_var"):
            self.term_all_var.set(state)
        if hasattr(self, "term_check_stat"):
            self.term_check_stat.config(
                text=(f"已选 {n} / {len(vis)} 条" if vis else "已选 0 条"))
        if hasattr(self, "term_batch_btn"):
            self.term_batch_btn.set_enabled(n > 0)

    def _on_term_undo_delete(self):
        """撤回上一次删除操作，恢复被标记删除的术语。"""
        if not self.term_delete_stack:
            messagebox.showinfo("提示", "没有可撤回的删除操作")
            return
        last = self.term_delete_stack.pop()
        self.term_deletes.difference_update(last)
        self._filter_terms()
        self.q.put(("log", f"已撤回上一次删除（恢复 {len(last)} 条）\n"))

    # ---------- 添加术语 ----------
    def _find_term_key(self, src):
        """按归一化（去空格 + 小写）在现有术语里找同名原文；没有返回 None。"""
        norm = (src or "").strip().lower()
        if not norm:
            return None
        try:
            cur = TS.load_current_terms()
        except Exception:
            return None
        for k in cur:
            if str(k).strip().lower() == norm:
                return k
        return None

    def _on_term_add(self):
        """
        弹窗输入 原文 / 译文，立即写入术语字典。
        新增的原文记进 self.term_added，点「应用术语」时会强制纳入受影响术语
        （删除相关句子缓存并重翻）。
        """
        got = TermDialog.ask(self.root, self.src_var.get(), self.tgt_var.get())
        if not got:
            return
        src, dst = got

        exist = self._find_term_key(src)
        if exist is not None:
            old = ""
            try:
                old = TS.load_current_terms().get(exist, "")
            except Exception:
                pass
            if not messagebox.askyesno(
                    "术语已存在",
                    f"术语「{exist}」已存在\n当前译文：{old}\n\n"
                    f"是否把它的译文改为：{dst}？"):
                return
            n = TS.save_term_values({exist: dst})
            key = exist
            msg = (f"已更新术语「{exist}」的译文 → {dst}" if n
                   else f"术语「{exist}」的译文没有变化")
        else:
            ok, msg, key = TS.add_term(src, dst)
            if not ok:
                messagebox.showwarning("未能添加", msg)
                self.q.put(("log", f"[添加术语] {msg}\n"))
                return

        try:
            PR.load_terms(force=True)
        except Exception:
            pass
        if key and key not in self.term_added:
            self.term_added.append(key)
        self._load_term_rows()
        self.q.put(("log", f"{msg}（点「应用术语」即会重翻相关句子）\n"))

    def _reset_term_pending(self, keep_added=False):
        """
        清空编辑/删除的待应用状态，并重新载入术语列表。
        keep_added=True 时保留「本次新增术语」记录（新增还得靠重翻才生效，
        所以未选文件时会先留着，等下次带文件「应用术语」再重翻）。
        """
        self.term_edits.clear()
        self.term_deletes.clear()
        self.term_delete_stack.clear()
        self.term_checks.clear()
        if not keep_added:
            self.term_added.clear()
        try:
            self._load_term_rows()
        except Exception:
            pass

    def _do_apply_terms(self):
        edits = dict(self.term_edits)
        deletes = set(self.term_deletes)
        added = list(dict.fromkeys(self.term_added))   # 本次添加的术语（去重保序）
        if not (edits or deletes or added):
            messagebox.showinfo("提示", "没有需要应用的术语新增、改动或删除")
            return

        src, tgt, model = self.src_var.get(), self.tgt_var.get(), self.model_var.get()
        paths = self.fp_terms.ensure()

        if not paths:
            # 未选文件：仅把改动写入术语字典，不触发重翻
            def work_no_paths():
                changed = TS.save_term_values(edits) if edits else 0
                removed = TS.delete_term_keys(deletes) if deletes else 0
                try:
                    PR.load_terms(force=True)
                except Exception:
                    pass
                if added:
                    # ★ 新增术语只有重翻才会生效，所以先不推进基准，
                    #   否则下次「应用术语」就不会再把它们算作新增了
                    self.q.put(("log",
                                f"新增的 {len(added)} 条术语已写入字典；"
                                "本次未选择文件，未重翻受影响的句子。\n"
                                "选好文件后再点一次「应用术语」即可重翻。\n"))
                else:
                    try:
                        TS.save_snapshot(TS.load_current_terms())
                    except Exception:
                        pass
                self.q.put(("log", f"术语字典已写入 {changed} 条修改、"
                                   f"删除 {removed} 条\n"))
                self.q.put(("term_reload", True))   # 保留新增记录，等下次重翻
            self.show("log")
            self.run_async(work_no_paths, label="写入术语字典…",
                          done_label="术语字典已更新")
            return

        extra = list(edits.keys()) + list(deletes) + added

        def work():
            changed = TS.save_term_values(edits) if edits else 0
            removed = TS.delete_term_keys(deletes) if deletes else 0
            for k in deletes:
                self.term_edits.pop(k, None)
            try:
                PR.load_terms(force=True)
            except Exception:
                pass
            self.q.put(("log", f"术语字典已写入 {changed} 条修改、"
                               f"删除 {removed} 条\n"))
            result = commands.retranslate_terms_paths(
                paths, src, tgt, model, extra_terms=extra)
            self.q.put(("term_reload", None))
            return result

        self.show("log")
        self.run_async(work, label="应用术语并重翻…", done_label="术语重翻完成")

    # ================================================================
    # 页面 4：前缀字典
    # ================================================================
    def _page_prefix(self):
        page = self.pages["prefix"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        c = RoundCard(left, radius=16, pad=14)
        c.grid(row=0, column=0, sticky="nsew")

        head = tk.Frame(c.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="前缀字典（双击译文可编辑）", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(side="left")
        self.prefix_stat = tk.Label(head, text="", bg=CARD, fg=TEXT_DIM,
                                    font=FONT_SMALL)
        self.prefix_stat.pack(side="right")

        bar = tk.Frame(c.body, bg=CARD)
        bar.pack(fill="x", pady=(6, 4))
        tk.Label(bar, text="搜索", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")
        self.prefix_search = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.prefix_search, width=20)
        ent.pack(side="left", padx=6)
        ent.bind("<KeyRelease>", lambda e: self._filter_prefix())
        self.prefix_only_pending = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="只看未翻译", bg=CARD, fg=TEXT,
                       activebackground=CARD, selectcolor="#FFFFFF",
                       font=FONT_SMALL, variable=self.prefix_only_pending,
                       command=self._filter_prefix).pack(side="left", padx=6)
        GlassButton(bar, "重新载入", width=76, height=26, bg=CARD,
                    font=FONT_SMALL,
                    command=self._load_prefix_rows).pack(side="left", padx=8)
        GlassButton(bar, "打开字典文件", width=96, height=26, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self._open_path(PFD.DICT_FILE)).pack(
            side="left")

        wrap = tk.Frame(c.body, bg=CARD)
        wrap.pack(fill="both", expand=True)
        cols = ("src", "dst")
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=14)
        tree.heading("src", text="前缀原文")
        tree.heading("dst", text="译文（可编辑）")
        tree.column("src", width=330, anchor="w")
        tree.column("dst", width=330, anchor="w")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        bind_tree_edit(tree, {"#2": True}, on_commit=self._on_prefix_edit)
        bind_tree_wheel(tree)
        self.prefix_tree = tree

        bottom = tk.Frame(c.body, bg=CARD)
        bottom.pack(fill="x", pady=(10, 0))
        tk.Label(bottom,
                 text="译文留空表示沿用原文；应用后会把新前缀写回翻译文件",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL).pack(side="left")
        GlassButton(bottom, "应用前缀字典", width=140, height=36, primary=True,
                    bg=CARD, command=self._do_apply_prefix).pack(side="right")

        fp_holder = RoundCard(page, radius=16, pad=8, width=252)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "source")
        self.fp_prefix = fp

    def _load_prefix_rows(self):
        try:
            PFD.reload_dict()
            data = PFD.all_entries()
        except Exception:
            data = {}
        self._prefix_all = list(data.items())
        self._filter_prefix()

    def _filter_prefix(self):
        tree = self.prefix_tree
        for iid in tree.get_children():
            tree.delete(iid)
        kw = (self.prefix_search.get() or "").strip().lower()
        only_pending = self.prefix_only_pending.get()
        n = pending = 0
        for k, v in getattr(self, "_prefix_all", []):
            if k in self.prefix_edits:
                v = self.prefix_edits[k]
            if only_pending and v:
                continue
            if kw and kw not in str(k).lower() and kw not in str(v).lower():
                continue
            tree.insert("", "end", values=(k, v or ""))
            n += 1
            if not v:
                pending += 1
        if hasattr(self, "prefix_stat"):
            total = len(getattr(self, "_prefix_all", []))
            self.prefix_stat.config(
                text=f"显示 {n} 条 / 共 {total} 条（待翻译 {pending}）"
                     + (f"，已改动 {len(self.prefix_edits)} 条"
                        if self.prefix_edits else ""))

    def _on_prefix_edit(self, row, col, value):
        try:
            item = self.prefix_tree.item(row)
            src = item["values"][0]
            self.prefix_edits[src] = value
        except Exception:
            pass

    def _do_apply_prefix(self):
        paths = self.fp_prefix.ensure()
        if not paths:
            messagebox.showwarning("提示", "请先选择要应用的文件")
            return
        edits = dict(self.prefix_edits)

        def work():
            res = commands.apply_prefix_dict_paths(paths, entries_map=edits)
            self.q.put(("prefix_done", res))
            return res

        self.show("log")
        self.run_async(work, label="应用前缀字典…", done_label="前缀字典已应用")

    # ================================================================
    # 页面 5：中文润色
    # ================================================================
    def _page_polish(self):
        page = self.pages["polish"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        c1 = RoundCard(left, radius=16, pad=18)
        c1.configure(height=158)
        c1.pack_propagate(False)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="模型与模式", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w")
        self._mode_row(c1.body)
        self._model_row(c1.body)
        tk.Label(c1.body, text="中文润色不需要选择语言：直接把缓存里的中文译文再润色一遍",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(6, 0))

        c2 = RoundCard(left, radius=16, pad=18)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tk.Label(c2.body, text="说明", bg=CARD, fg=TEXT, font=FONT_B).pack(anchor="w")
        txt = ("· 逐条读取缓存中的中文译文，交给模型润色后覆盖原缓存\n"
               "· 保留全部占位符与控制码；占位符不全的条目会保留原译文\n"
               "· 润色完成后自动重写 *_translated.txt\n"
               "· 短句、纯控制符句不参与润色")
        tk.Label(c2.body, text=txt, bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(8, 0))

        c3 = RoundCard(left, radius=16, pad=18)
        c3.configure(height=92)
        c3.pack_propagate(False)
        c3.grid(row=2, column=0, sticky="ew")
        GlassButton(c3.body, "开始润色", width=180, height=44, primary=True,
                    bg=CARD, command=self._do_polish).pack(anchor="w")
        tk.Label(c3.body, text="点击后跳转到日志页，实时查看进度",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL).pack(anchor="w",
                                                               pady=(6, 0))

        fp_holder = RoundCard(page, radius=16, pad=8, width=252)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "source")
        self.fp_polish = fp

    def _do_polish(self):
        paths = self.fp_polish.ensure()
        if not paths:
            messagebox.showwarning("提示", "请先选择要润色的文件")
            return
        model = self.model_var.get()
        self.show("log")
        self.run_async(lambda: commands.polish_paths(paths, model),
                       label="中文润色中…", done_label="润色完成")

    # ================================================================
    # 页面 6：换行重排
    # ================================================================
    def _page_reflow(self):
        page = self.pages["reflow"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        self.reflow_cfgs = {}
        self.reflow_lists = {}
        self.reflow_previews = {}
        self.reflow_stats = {}
        self._reflow_data = {"newline": [], "space": []}

        specs = (
            ("newline", 0, "[map*] 区块的换行重排（\\n）",
             (("WRAP_CHARS_MIN", "换行下限", 15),
              ("WRAP_CHARS_MAX", "换行上限", 18),
              ("WRAP_MIN_GAP",   "换行最小间隔", 10))),
            ("space", 1, "其它区块标记的空格重排（空格）",
             (("WRAP_SPACE_MIN", "空格下限", 8),
              ("WRAP_SPACE_MAX", "空格上限", 10),
              ("WRAP_SPACE_MIN_GAP", "空格最小间隔", 5))),
        )
        for mode, row, title, fields in specs:
            card = RoundCard(page, radius=16, pad=14)
            card.grid(row=row, column=0, sticky="nsew", pady=(0, 8))
            self._build_reflow_half(card.body, mode, title, fields)

        fp_holder = RoundCard(page, radius=16, pad=8, width=252)
        fp_holder.grid(row=0, column=1, rowspan=2, sticky="nsew")
        fp_holder.grid_propagate(False)
        self.fp_reflow = self._make_file_panel(fp_holder, "source")

        # 右下角：开始重排
        bottom = tk.Frame(page, bg=BG_BASE)
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        tk.Label(bottom,
                 text="· 只重排换行方式，不改动译文文字、不调用模型；"
                      "两种重排各用一套参数（会保存到设置）",
                 bg=BG_BASE, fg=TEXT_FAINT, font=FONT_SMALL).pack(side="left")
        GlassButton(bottom, "开始重排", width=160, height=42, primary=True,
                    bg=BG_BASE,
                    command=self._do_reflow).pack(side="right", pady=(6, 0))

    def _build_reflow_half(self, body, mode, title, fields):
        """构建半屏重排面板：上=参数，左=区块列表，右=区块文本。"""
        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text=title, bg=CARD, fg=TEXT,
                 font=FONT_B).pack(side="left")
        stat = tk.Label(head, text="", bg=CARD, fg=TEXT_DIM, font=FONT_SMALL)
        stat.pack(side="right")

        cfgrow = tk.Frame(body, bg=CARD)
        cfgrow.pack(fill="x", pady=(6, 6))
        varmap = {}
        for key, name, default in fields:
            tk.Label(cfgrow, text=name, bg=CARD, fg=TEXT_DIM,
                     font=FONT_SMALL).pack(side="left", padx=(0, 4))
            var = tk.StringVar(value=str(getattr(config, key, default)))
            ttk.Entry(cfgrow, textvariable=var, width=6).pack(
                side="left", padx=(0, 12))
            varmap[key] = var
        GlassButton(cfgrow, "刷新列表", width=84, height=26, bg=CARD,
                    font=FONT_SMALL,
                    command=self._load_reflow_blocks).pack(side="left")

        mid = tk.Frame(body, bg=CARD)
        mid.pack(fill="both", expand=True)

        left = tk.Frame(mid, bg=CARD)
        left.pack(side="left", fill="both")
        tree = ttk.Treeview(left, columns=("block", "count"),
                            show="headings", height=5)
        tree.heading("block", text="区块")
        tree.heading("count", text="条数")
        tree.column("block", width=132, anchor="w")
        tree.column("count", width=46, anchor="center")
        sb = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        bind_tree_wheel(tree)
        tree.bind("<<TreeviewSelect>>",
                  lambda _e, m=mode: self._render_reflow_block(m))

        right = tk.Frame(mid, bg=CARD)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(right, text="区块文本（原文 / 译文）", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(anchor="w")
        box = tk.Text(right, height=5, wrap="none", font=FONT_MONO,
                      bg="#FFFFFF", fg=TEXT, relief="flat",
                      highlightthickness=1, highlightbackground=CARD_BORDER)
        vsb = ttk.Scrollbar(right, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True)
        box.configure(state="disabled")

        self.reflow_cfgs[mode] = varmap
        self.reflow_lists[mode] = tree
        self.reflow_previews[mode] = box
        self.reflow_stats[mode] = stat

    def _load_reflow_blocks(self):
        """扫描已选文件，按 [map*] / 其它区块 填入两半的列表。"""
        paths = []
        fp = getattr(self, "fp_reflow", None)
        if fp is not None:
            try:
                paths = fp.ensure() or []
            except Exception:
                paths = []

        try:
            self._reflow_data = (commands.scan_reflow_blocks(paths) if paths
                                 else {"newline": [], "space": []})
        except Exception:
            log.error("重排扫描失败：\n%s", traceback.format_exc())
            self._reflow_data = {"newline": [], "space": []}

        for mode in ("newline", "space"):
            tree = self.reflow_lists.get(mode)
            if tree is None or not tree.winfo_exists():
                continue
            for iid in tree.get_children():
                tree.delete(iid)
            blocks = self._reflow_data.get(mode, [])
            total = 0
            for b in blocks:
                tree.insert("", "end",
                            values=(f"{b['file']} · {b['block']}", b["total"]))
                total += b["total"]
            self.reflow_stats[mode].config(
                text=f"{len(blocks)} 个区块 / {total} 条译文")
            self._render_reflow_block(mode)

    def _render_reflow_block(self, mode):
        """把选中区块的原文 / 译文摘要填到右侧预览框。"""
        tree = self.reflow_lists.get(mode)
        box = self.reflow_previews.get(mode)
        if tree is None or box is None:
            return
        blocks = self._reflow_data.get(mode, [])
        lines = []
        sel = tree.selection()
        if sel:
            pos = tree.index(sel[0])
            if 0 <= pos < len(blocks):
                b = blocks[pos]
                lines.append(f"{b['file']}   {b['block']}   "
                             f"共 {b['total']} 条（下面显示前 {len(b['pairs'])} 条）")
                lines.append("")
                for n, (src, dst) in enumerate(b["pairs"], 1):
                    lines.append(f"{n}. 原文：{src}")
                    lines.append(f"   译文：{dst}")
                    lines.append("")
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")

    def _do_reflow(self):
        paths = self.fp_reflow.ensure()
        if not paths:
            messagebox.showwarning("提示", "请先选择要重排的文件")
            return

        # 先把两套参数写回设置（同时校验格式）
        for mode in ("newline", "space"):
            for key, var in self.reflow_cfgs.get(mode, {}).items():
                raw = (var.get() or "").strip()
                if not raw:
                    continue
                ok, msg, _v = settings.set_value(key, raw)
                if not ok:
                    messagebox.showwarning("参数有误", f"{key}：{msg}")
                    return

        newline_cfg = {"min": config.WRAP_CHARS_MIN,
                       "max": config.WRAP_CHARS_MAX,
                       "gap": getattr(config, "WRAP_MIN_GAP", 10)}
        space_cfg = {"min": getattr(config, "WRAP_SPACE_MIN", 8),
                     "max": getattr(config, "WRAP_SPACE_MAX", 10),
                     "gap": getattr(config, "WRAP_SPACE_MIN_GAP", 5)}

        self.show("log")
        self.run_async(
            lambda: commands.reflow_paths(paths, newline_cfg, space_cfg),
            label="换行重排中…", done_label="换行重排完成")

    # ================================================================
    # 页面 7：Excel 转术语表
    # ================================================================
    def _page_excel(self):
        page = self.pages["excel"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        c1 = RoundCard(left, radius=16, pad=18)
        c1.configure(height=104)
        c1.pack_propagate(False)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="语言选择（Excel 列名）", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w")
        row = tk.Frame(c1.body, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        self.excel_src = tk.StringVar(value=config.EXCEL_SOURCE_LANG)
        self.excel_tgt = tk.StringVar(value=config.EXCEL_TARGET_LANG)
        self._labeled_combo(row, "源语言", self.excel_src, EXCEL_LANGS, 14)
        self._labeled_combo(row, "目标语言", self.excel_tgt, EXCEL_LANGS, 14)

        c2 = RoundCard(left, radius=16, pad=14)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        head = tk.Frame(c2.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="工作表", bg=CARD, fg=TEXT, font=FONT_B).pack(side="left")
        self.excel_path = tk.StringVar(
            value=config.EXCEL_FILE if os.path.exists(config.EXCEL_FILE) else "")
        GlassButton(head, "选择 Excel", width=96, height=28, bg=CARD,
                    font=FONT_SMALL, command=self._pick_excel).pack(side="left",
                                                                    padx=10)
        GlassButton(head, "全选", width=56, height=28, bg=CARD,
                    font=FONT_SMALL, command=self._sheets_all).pack(side="left")
        self.excel_lbl = tk.Label(head, text="", bg=CARD, fg=TEXT_DIM,
                                  font=FONT_SMALL)
        self.excel_lbl.pack(side="right")

        outer, inner = make_scroll_area(c2.body, bg=CARD)
        outer.pack(fill="both", expand=True, pady=(8, 0))
        self.sheet_inner = inner

        c3 = RoundCard(left, radius=16, pad=18)
        c3.configure(height=92)
        c3.pack_propagate(False)
        c3.grid(row=2, column=0, sticky="ew")
        GlassButton(c3.body, "开始转换", width=180, height=44, primary=True,
                    bg=CARD, command=self._do_excel).pack(anchor="w")
        tk.Label(c3.body, text="提取结果写入 term_dict.py，完成后弹窗提示",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL).pack(anchor="w",
                                                               pady=(6, 0))

        right = tk.Frame(page, bg=BG_BASE, width=252)
        right.grid(row=0, column=1, sticky="nsew")
        right.pack_propagate(False)
        card = RoundCard(right, radius=16, pad=14)
        card.pack(fill="both", expand=True)
        tk.Label(card.body, text="提示", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w")
        tk.Label(card.body,
                 text="· 表头需同时包含所选的两种语言列名\n"
                      "· 多个工作表会跨表去重\n"
                      "· 转换后可在菜单 3 里逐条校对译文\n"
                      "· 输出文件：term_dict.py",
                 bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(8, 0))

        if self.excel_path.get():
            self._load_sheets(self.excel_path.get())

    def _pick_excel(self):
        path = filedialog.askopenfilename(
            title="选择 Excel 术语表",
            initialdir=config.Runtime.last_dir or config.BASE_DIR,
            filetypes=[("Excel 文件", "*.xlsx *.xlsm"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.excel_path.set(path)
        config.Runtime.set_dir(os.path.dirname(path))
        self._load_sheets(path)

    def _load_sheets(self, path):
        for w in self.sheet_inner.winfo_children():
            w.destroy()
        self.sheet_vars = {}
        self.excel_lbl.config(text=os.path.basename(path))
        try:
            import build_terms as BT
            sheets = BT.list_sheets(path)
        except Exception as e:
            tk.Label(self.sheet_inner, text=f"读取失败：{e}", bg=CARD,
                     fg=ERR_COLOR, font=FONT_SMALL).pack(anchor="w", padx=8)
            return
        for name, r, c in sheets:
            v = tk.BooleanVar(value=True)
            self.sheet_vars[name] = v
            tk.Checkbutton(self.sheet_inner,
                           text=f"{name}   ({r} 行 × {c} 列)",
                           variable=v, bg=CARD, fg=TEXT,
                           activebackground=CARD, selectcolor="#FFFFFF",
                           anchor="w", font=FONT_SMALL).pack(fill="x", padx=8)

    def _sheets_all(self):
        for v in self.sheet_vars.values():
            v.set(True)

    def _do_excel(self):
        path = self.excel_path.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning("提示", "请先选择 Excel 文件")
            return
        sheets = [n for n, v in self.sheet_vars.items() if v.get()]
        src, tgt = self.excel_src.get(), self.excel_tgt.get()
        if src and tgt and src == tgt:
            messagebox.showwarning("提示", "源语言与目标语言不能相同")
            return

        def work():
            res = commands.build_terms_from_excel(path, sheets or None, src, tgt)
            self.q.put(("excel_done", res))
            return res

        self.show("log")
        self.run_async(work, label="Excel 转换中…", done_label="转换完成")

    # ================================================================
    # 页面 7：设置
    # ================================================================
    def _page_settings(self):
        page = self.pages["settings"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        info = RoundCard(page, radius=16, pad=14, auto_height=True)
        info.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        head = tk.Frame(info.body, bg=CARD)
        head.pack(fill="x")
        Avatar(head, size=56, path=config.AVATAR_FILE).pack(side="left")
        box = tk.Frame(head, bg=CARD)
        box.pack(side="left", padx=12)
        tk.Label(box, text=config.AUTHOR_NAME, bg=CARD, fg=TEXT,
                 font=FONT_B).pack(anchor="w")
        lb1 = tk.Label(box, text=config.AUTHOR_GITHUB, bg=CARD, fg=ACCENT,
                       font=FONT_SMALL, cursor="hand2")
        lb1.pack(anchor="w")
        lb1.bind("<Button-1>", lambda e: webbrowser.open(config.AUTHOR_GITHUB))
        lb2 = tk.Label(box, text="bilibili：玛俐大小姐想让我告白", bg=CARD,
                       fg=ACCENT, font=FONT_SMALL, cursor="hand2")
        lb2.pack(anchor="w")
        lb2.bind("<Button-1>", lambda e: webbrowser.open(config.AUTHOR_BILIBILI))
        tk.Label(head, text=f"v{config.VERSION}", bg=CARD, fg=TEXT_FAINT,
                 font=FONT_SMALL).pack(side="right", anchor="ne")

        card = RoundCard(page, radius=16, pad=14)
        card.grid(row=1, column=0, sticky="nsew")
        head2 = tk.Frame(card.body, bg=CARD)
        head2.pack(fill="x")
        tk.Label(head2, text="各项设置", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(side="left")
        GlassButton(head2, "检查更新", width=86, height=30, bg=CARD,
                    font=FONT_SMALL, command=self._check_update).pack(
            side="right")
        GlassButton(head2, "保存设置", width=96, height=30, primary=True,
                    bg=CARD, command=self._save_settings).pack(
            side="right", padx=8)
        GlassButton(head2, "重新载入", width=86, height=30, bg=CARD,
                    font=FONT_SMALL, command=self._load_settings).pack(
            side="right")

        # 翻译模式切换（切换后会自动同步参数并弹窗提示）
        self._mode_row(card.body)
        tk.Label(card.body,
                 text="云端模式请在下方填写 API 服务地址 / 密钥 / 模型名"
                      "（OpenAI 兼容接口）",
                 bg=CARD, fg=TEXT_FAINT, font=FONT_SMALL).pack(anchor="w",
                                                               pady=(2, 6))

        outer, inner = make_scroll_area(card.body, bg=CARD)
        outer.pack(fill="both", expand=True, pady=(8, 0))
        self.setting_inner = inner
        self._load_settings()

    def _load_settings(self):
        for w in self.setting_inner.winfo_children():
            w.destroy()
        self.setting_widgets = {}

        try:
            current = settings.get_all()
        except Exception:
            current = {}

        for key, name, typ, desc in settings.EDITABLE:
            if key == "TRANSLATE_MODE":
                continue        # 由页面顶部的模式切换按钮负责

            row = tk.Frame(self.setting_inner, bg=CARD)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=name, bg=CARD, fg=TEXT, font=FONT_SMALL,
                     width=16, anchor="w").pack(side="left")

            val = current.get(key, "")
            if key == "MODEL":
                var = tk.StringVar(value=val)
                cb = ttk.Combobox(row, textvariable=var,
                                  values=self.models or [val],
                                  width=24, font=FONT_SMALL)
                cb.pack(side="left")
                self.model_combos.append(cb)
                widget, var_holder = cb, var
            elif typ == "bool":
                var = tk.BooleanVar(value=str(val).strip().lower() in
                                    ("true", "1", "yes", "y", "on"))
                cb = tk.Checkbutton(row, bg=CARD, activebackground=CARD,
                                    selectcolor="#FFFFFF", variable=var)
                cb.pack(side="left")
                widget, var_holder = cb, var
            elif key == "API_KEY":
                var = tk.StringVar(value=val)
                ent = ttk.Entry(row, textvariable=var, width=26,
                                font=FONT_SMALL, show="*")
                ent.pack(side="left")
                widget, var_holder = ent, var
            else:
                var = tk.StringVar(value=val)
                ent = ttk.Entry(row, textvariable=var, width=26,
                                font=FONT_SMALL)
                ent.pack(side="left")
                widget, var_holder = ent, var

            tk.Label(row, text=desc or "", bg=CARD, fg=TEXT_FAINT,
                     font=FONT_SMALL).pack(side="left", padx=10)
            self.setting_widgets[key] = (var_holder, typ, widget)

    # ---------- 检查更新 ----------
    def _check_update(self, silent=False):
        def work():
            try:
                import updater
                has, info = updater.check_update()
                self.q.put(("update", (has, info, silent)))
            except Exception as e:
                self.q.put(("update", (False, {"error": str(e)}, silent)))
        threading.Thread(target=work, daemon=True).start()

    def _on_update_result(self, has, info, silent):
        if isinstance(info, dict) and info.get("error"):
            if not silent:
                try:
                    import updater
                    home = updater.RELEASES_URL
                except Exception:
                    home = "https://github.com/nevermore-glimpse/pkmn_translator/releases"
                messagebox.showwarning(
                    "检查更新",
                    f"获取最新版本失败：\n{info['error']}\n\n"
                    f"可手动打开：{home}")
            else:
                self.status_var.set("检查更新失败（网络不通？）")
            return

        if not has:
            if silent:
                self.status_var.set("已是最新版本")
            else:
                messagebox.showinfo(
                    "检查更新",
                    f"当前已是最新版本：v{config.VERSION}")
            return

        tag = info.get("tag", "")
        url = info.get("url", "")
        notes = (info.get("notes") or "").strip()
        msg = (f"发现新版本：{tag}\n当前版本：v{config.VERSION}\n\n"
               f"{notes[:300] if notes else ''}\n\n"
               f"下载地址：\n{url}")
        if messagebox.askyesno("发现新版本", msg + "\n\n是否打开下载页面？"):
            webbrowser.open(url)

    def _save_settings(self):
        ok, fail = 0, []
        for key, (var, typ, _w) in self.setting_widgets.items():
            try:
                val = var.get()
                if typ == "bool":
                    val = "true" if val else "false"
                good, msg, _ = settings.set_value(key, val)
                if not good:
                    fail.append(f"{key}: {msg}")
                else:
                    ok += 1
            except Exception as e:
                fail.append(f"{key}: {e}")

        # 同步到界面上的语言/模型选择
        self.src_var.set(config.SOURCE_LANG)
        self.tgt_var.set(config.TARGET_LANG)
        self.model_var.set(config.API_MODEL
                           if settings.current_mode() == "api"
                           else config.MODEL)
        self._paint_mode_row()
        self._load_settings()

        if fail:
            messagebox.showwarning("部分失败", "\n".join(fail[:10]))
        else:
            messagebox.showinfo("设置", f"已保存 {ok} 项设置")
        self._load_settings()

    # ================================================================
    # 页面 8：日志
    # ================================================================
    def _page_log(self):
        page = self.pages["log"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        card = RoundCard(page, radius=16, pad=14)
        card.grid(row=0, column=0, sticky="nsew")

        head = tk.Frame(card.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="运行日志", bg=CARD, fg=TEXT,
                 font=FONT_B).pack(side="left")
        GlassButton(head, "清空", width=60, height=28, bg=CARD,
                    font=FONT_SMALL, command=self._clear_log).pack(side="right")
        GlassButton(head, "打开日志目录", width=104, height=28, bg=CARD,
                    font=FONT_SMALL, command=self._open_log_dir).pack(
            side="right", padx=8)

        wrap = tk.Frame(card.body, bg="#FFFFFF")
        wrap.pack(fill="both", expand=True, pady=(8, 0))

        self.log_text = tk.Text(wrap, wrap="word", font=FONT_MONO,
                                bg="#FFFFFF", fg="#334155",
                                relief="solid", bd=1,
                                highlightthickness=1,
                                highlightbackground=CARD_BORDER,
                                insertbackground=TEXT)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.log_text.configure(state="disabled")

        self.log_text.tag_config("ok", foreground=OK_COLOR)
        self.log_text.tag_config("warn", foreground=WARN_COLOR)
        self.log_text.tag_config("err", foreground=ERR_COLOR)

        self._append_log(f"{config.APP_TITLE} 已就绪\n"
                         f"工作目录：{config.BASE_DIR}\n"
                         f"术语表：{config.TERM_FILE}\n"
                         f"日志目录：{os.path.join(config.BASE_DIR, 'logs')}\n")

    def _clear_log(self):
        try:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")
        except Exception:
            pass

    def _open_log_dir(self):
        self._open_path(os.path.join(config.BASE_DIR, "logs"))

    def _open_path(self, path):
        try:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("打开失败", f"{e}")

    # ================================================================
    # 其它消息
    # ================================================================
    def _on_report_result(self, result):
        self._fill_report(result)


# ================================================================
# 语言常量
# ================================================================
def _lang_values():
    vals = list(commands.LANG_OPTIONS)
    for extra in (config.SOURCE_LANG, config.TARGET_LANG):
        if extra and extra not in vals:
            vals.append(extra)
    return vals


def _excel_lang_values():
    try:
        import build_terms as BT
        return list(BT.LANG_ALIASES.keys())
    except Exception:
        return ["英文", "简体中文"]


LANG_VALUES = []
EXCEL_LANGS = []


# ================================================================
# 入口
# ================================================================
def main():
    global log, LANG_VALUES, EXCEL_LANGS
    from logger import get_logger
    log = get_logger("gui")

    LANG_VALUES = _lang_values()
    EXCEL_LANGS = _excel_lang_values()

    root = tk.Tk()
    app = App(root)
    apply_window_effects(root)
    root.mainloop()


if __name__ == "__main__":
    main()
