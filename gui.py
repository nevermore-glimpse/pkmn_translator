# -*- coding: utf-8 -*-
"""
宝可梦同人游戏翻译工具 —— 亚克力毛玻璃图形界面。

布局：
  左侧  圆形头像（悬停显示作者信息）+ 标题 + 10 个菜单（悬停放大 + 底部阴影）
  右侧  各功能页面
    · 菜单 2/3/4/5/6/7 右侧带「待操作文件」勾选侧边栏
    · 菜单 10 右侧带「切换适配」清单侧边栏
    · 底部常驻状态条（进度 + 取消）
  菜单 11 为日志页，任务启动后自动跳转过去。
"""
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import webbrowser
from collections import Counter

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import bridge
import logger
import commands
import config
import env_check
import prefix_dict as PFD
import processor as PR
import providers as PV
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
ACCENT       = "#1667C4"     # 宝可蓝
ACCENT_SOFT  = "#D9E9FA"
ACCENT_DEEP  = "#0F4C86"
POKE_RED     = "#D61F26"     # 精灵球红（重要数字 / 统计）
TEXT         = "#11202F"     # 正文：加深，远距离也清楚
TEXT_DIM     = "#3C5064"     # 次要文字
TEXT_FAINT   = "#5C7085"     # 说明文字（比原来更深，不再发灰）
OK_COLOR     = "#0F8A56"
WARN_COLOR   = "#B25F09"
ERR_COLOR    = "#C42A24"

# ★ 统一字号表（改这里就能整体缩放）
FONT_SIZES = {
    "body":  11,   # 正文 / 普通按钮
    "small": 10,   # 说明文字 / 小按钮
    "title": 15,   # 卡片标题
    "big":   12,   # 主按钮 / 醒目数字
    "mono":  10,   # 日志 / 等宽区
}

# ★ 全局统一字体：优先使用随程序分发的萝莉体（config.FONT_FILE），
#   运行时用 GDI 私有加载，目标机器无需安装；
#   取不到就退回黑体 / 微软雅黑，避免方框尺寸与实际字体不匹配。
#   族名与字号会在 main() 里由 resolve_font_family() 定稿。
FONT_FAMILY  = "Lolita"
FONT         = (FONT_FAMILY, FONT_SIZES["body"])
FONT_B       = (FONT_FAMILY, FONT_SIZES["body"], "bold")
FONT_SMALL   = (FONT_FAMILY, FONT_SIZES["small"])
FONT_TITLE   = (FONT_FAMILY, FONT_SIZES["title"], "bold")   # 卡片标题
FONT_BIG     = (FONT_FAMILY, FONT_SIZES["big"], "bold")     # 主按钮 / 醒目数字
FONT_MONO    = (FONT_FAMILY, FONT_SIZES["mono"])

# ★ 语义色：重要信息统一用这些常量标记
C_TITLE   = ACCENT_DEEP   # 卡片标题
C_KEY     = POKE_RED      # 关键统计数字
C_HINT    = TEXT_FAINT    # 说明文字
C_WARN    = WARN_COLOR    # 需要注意
C_OK      = OK_COLOR      # 成功 / 正常

# llama.cpp 中层那句固定说明 —— 状态行会拼在它后面，两行刚好，
# 不能塞太多文字，否则中层卡片（高度受挤压）装不下。
PV_LLAMA_HINT = ("先指好「程序目录」和「模型目录」，启动时会自动 -m 加载"
                 "选中的 GGUF，并带 --reasoning off 关掉推理。")

# 方框内文字的左右 / 上下留白（按钮按文字大小自适应时用）
BTN_PAD_X = 22
BTN_PAD_Y = 16

MENU_ITEMS = [
    ("1", "文本提取与编译"),
    ("2", "翻译"),
    ("3", "重翻检查报告"),
    ("4", "术语更新后重翻"),
    ("5", "前缀字典"),
    ("6", "中文润色"),
    ("7", "换行重排"),
    ("8", "Excel 转术语表"),
    ("9", "设置"),
    ("10", "本地模型服务"),
    ("11", "日志"),
]

MENU_KEYS = {
    "1": "intl", "2": "translate", "3": "report", "4": "terms",
    "5": "prefix", "6": "polish", "7": "reflow", "8": "excel",
    "9": "settings", "10": "provider", "11": "log",
}


# ================================================================
# 小工具
# ================================================================
def _intl_outs(report):
    """把提取/编译报告里的输出位置拼成一句话（新版是两个文件夹、多份 dat）。"""
    if not report:
        return ""
    outs = report.get("outs")
    if outs:
        return "、".join(os.path.basename(o["out"]) for o in outs)
    dirs = report.get("dirs") or {}
    if dirs:
        return "、".join(os.path.basename(p) for p in dirs.values())
    return report.get("out") or ""


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


def _font_metrics(font):
    """返回 (文字宽度测量函数, 行高)。测量失败时按字号粗估。"""
    try:
        import tkinter.font as tkfont
        f = tkfont.Font(font=font)
        return f.measure, max(f.metrics("linespace"), 1)
    except Exception:
        size = font[1] if isinstance(font, (tuple, list)) and len(font) > 1 else 11
        return (lambda s: len(s) * size), int(size * 1.6)


def fit_text_box(text, font, width, height):
    """
    按文字实际尺寸放大方框，保证文字既不被裁掉、也不顶到边框。
    只在给定尺寸不够时才放大，不会把按钮缩小。
    """
    measure, line_h = _font_metrics(font)
    lines = [ln for ln in str(text or "").split("\n")]
    need_w = max((measure(ln) for ln in lines), default=0) + BTN_PAD_X
    need_h = line_h * len(lines) + BTN_PAD_Y
    return max(int(width), int(need_w)), max(int(height), int(need_h))


class GlassButton(tk.Canvas):
    """圆角玻璃按钮（方框尺寸按文字自适应，绝不裁字）。"""

    def __init__(self, master, text="", command=None, width=120, height=36,
                 primary=False, bg=None, font=None, state=True):
        bg = bg or BG_BASE
        self.font = font or (FONT_BIG if primary else FONT)
        self.text = text
        w, h = fit_text_box(text, self.font, width, height)
        tk.Canvas.__init__(self, master, width=w, height=h,
                           highlightthickness=0, bg=bg, cursor="hand2")
        self.command = command
        self.w = w
        self.h = h
        self.primary = primary
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
    """左侧菜单项：悬停略微放大 + 底部阴影（宽度按文字自适应）。"""

    def __init__(self, master, index, text, command=None,
                 width=228, height=52):
        font = (FONT_FAMILY, FONT[1], "bold")
        w, _h = fit_text_box(text, font, width, height)
        # 序号占前 36px，文字从这里开始，故测量宽度要算上这段偏移
        w = max(w, 36 + _font_metrics(font)[0](text) + BTN_PAD_X)
        tk.Canvas.__init__(self, master, width=w, height=max(_h, height),
                           highlightthickness=0, bg=CARD, cursor="hand2")
        self.command = command
        self.w = w
        self.h = max(_h, height)
        self.text = text
        self.index = index
        self._hover = False
        self._active = False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", lambda e: self.command and self.command())
        # 侧栏变宽/变窄时按实际分配宽度重画，避免圆角框与文字错位
        self.bind("<Configure>", lambda _e: self._draw())

    def _draw(self):
        self.delete("all")
        grow = 3 if self._hover else 0
        # ★ 用实际分配宽度（pack(fill="x") 会拉宽），没有再用最小宽度
        try:
            real_w = self.winfo_width()
        except Exception:
            real_w = 0
        w = max(self.w, real_w)
        h = max(self.h, self.winfo_height() or 0)
        x1, y1, x2, y2 = 3 - grow, 3 - grow, w - 4 + grow, h - 5 + grow

        if self._hover:
            # 底部阴影
            for i in range(6, 0, -1):
                round_rect(self, x1 + i * .4, y1 + i * .8,
                           x2 - i * .4, y2 + i * 1.1, 11,
                           fill=_blend(SHADOW, CARD, 1 - i / 7.0), outline="")

        if self._active:
            fill, fg, outline = ACCENT_SOFT, ACCENT_DEEP, ACCENT
        elif self._hover:
            fill, fg, outline = _blend(CARD, "#FFFFFF", .6), TEXT, CARD_BORDER
        else:
            fill, fg, outline = CARD_ALT, TEXT, CARD_BORDER

        round_rect(self, x1, y1, x2, y2, 11, fill=fill, outline=outline, width=1)
        self.create_text(18, (y1 + y2) / 2, anchor="w",
                         text=self.index, fill=TEXT_FAINT,
                         font=(FONT_FAMILY, FONT_SMALL[1], "bold"))
        self.create_text(42, (y1 + y2) / 2, anchor="w",
                         text=self.text,
                         fill=fg,
                         font=(FONT_FAMILY, FONT[1] + 1 + grow // 3,
                               "bold"))

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
                         font=(FONT_FAMILY, max(10, self.size // 3), "bold"))

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

        pad = {"padx": 16, "pady": 4}
        tk.Label(outer, text=config.AUTHOR_NAME, bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", **pad)
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
                 bg=CARD, fg=C_KEY, font=FONT_B).pack(
            anchor="w", padx=16, pady=(10, 12))

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


# ================================================================
# 复制到剪贴板
#   · 列表：右键菜单（选中 / 全部 / 该单元格）+ Ctrl+C，导出为制表符分隔
#   · 日志、文本框：右键菜单 + Ctrl+C（选中优先，无选中则整段）
#   · 文件名、统计数字等：右键即可复制
# ================================================================
def clipboard_set(widget, text):
    """把 text 写进系统剪贴板。widget 用任意 Tk 控件即可（取它的 root）。"""
    if text is None or str(text) == "":
        return False
    try:
        widget.clipboard_clear()
        widget.clipboard_append(str(text))
        widget.update_idletasks()
        return True
    except Exception as e:
        if log:
            log.warning("写入剪贴板失败：%s", e)
        return False


def _cell_text(v):
    """单元格 → 纯文本；去掉术语冲突「保留」列前面的 ● 标记。"""
    s = "" if v is None else str(v)
    return s[2:] if s.startswith("● ") else s


def tree_text(tree, iids=None, with_header=True):
    """
    把 Treeview 的行导出成制表符分隔文本（可直接粘进 Excel）。
    iids 为 None 表示全部行。
    """
    try:
        rows = []
        if with_header:
            rows.append("\t".join(
                str(tree.heading(c, "text")) for c in tree["columns"]))
        for iid in (tree.get_children() if iids is None else iids):
            vals = list(tree.item(iid, "values"))
            rows.append("\t".join(_cell_text(v) for v in vals))
        return "\n".join(rows)
    except Exception as e:
        if log:
            log.warning("导出列表失败：%s", e)
        return ""


def tree_cell_text(tree, col_id, row_id):
    """取某单元格的纯文本。col_id 形如 '#3'。"""
    try:
        s = str(col_id)
        idx = int(s[1:]) - 1 if s.startswith("#") and s[1:].isdigit() else -1
        vals = list(tree.item(row_id, "values"))
        return _cell_text(vals[idx]) if 0 <= idx < len(vals) else ""
    except Exception:
        return ""


def _copy_menu(widget):
    """统一样式的右键菜单（父控件即菜单的 master，随控件一起销毁）。"""
    return tk.Menu(widget, tearoff=0, font=FONT_SMALL,
                   bg=CARD, fg=TEXT,
                   activebackground=ACCENT_SOFT, activeforeground=ACCENT_DEEP,
                   bd=1, relief="solid")


def _fire_copy(widget, app, text):
    """执行复制：有 App 就让它统一反馈状态栏，否则直接写剪贴板。"""
    if app is not None and hasattr(app, "copy_to_clipboard"):
        return app.copy_to_clipboard(text)
    return clipboard_set(widget, text)


def attach_copy(widget, getters, app=None, hotkey=True):
    """
    给任意控件挂右键复制菜单（+ 可选 Ctrl+C）。

    getters: [(菜单文字, 取文本的函数), ...]，第一项同时作为 Ctrl+C 的行为。

    ★ 菜单是**右键时临时创建、用完即销毁**的：控件所在容器经常被
      `for w in children: w.destroy()` 批量清空（如文件列表），
      常驻菜单会跟着一起被销毁，之后再用就报 invalid command name。
    """
    entries = [(label, fn) for label, fn in getters if fn]
    if not entries:
        return None
    widget._copy_getters = entries       # 便于自检 / 调试

    def _popup(e):
        menu = _copy_menu(widget)
        for label, fn in entries:
            menu.add_command(
                label=label,
                command=lambda f=fn: _fire_copy(widget, app, f()))
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
            menu.destroy()
        return "break"

    widget.bind("<Button-3>", _popup, add="+")
    if hotkey:
        first = entries[0][1]

        def _hotkey(_e):
            _fire_copy(widget, app, first())
            return "break"

        widget.bind("<Control-c>", _hotkey, add="+")
        widget.bind("<Control-C>", _hotkey, add="+")
    return entries


def label_text(label):
    """取 Label 当前显示的文字（兼容用 textvariable 的标签）。"""
    try:
        var = str(label.cget("textvariable") or "")
        if var:
            val = label.getvar(var)
            if val is not None:
                return str(val)
    except Exception:
        pass
    try:
        return str(label.cget("text"))
    except Exception:
        return ""


def attach_label_copy(label, app=None, label_name="文字"):
    """给只读文字（Label）挂右键复制。"""
    return attach_copy(label,
                       [(f"复制这段{label_name}",
                         lambda w=label: label_text(w))],
                       app=app, hotkey=False)


def _edge_row(tree, y):
    """鼠标拖到列表上下的空白处时，把落点夹到第一行 / 最后一行。"""
    rows = tree.get_children()
    if not rows:
        return None
    try:
        b_last = tree.bbox(rows[-1])
        if b_last and y > b_last[1] + b_last[3]:
            return rows[-1]
        b_first = tree.bbox(rows[0])
        if b_first and y < b_first[1]:
            return rows[0]
    except Exception:
        pass
    return None


def attach_tree_copy(tree, app=None, cell_label="复制该单元格"):
    """
    列表复制：

      · 鼠标滑动选中 —— 按住左键上下拖动，连续选中一段行（Tk 8.6 的
        Treeview 已经把拖动刷选去掉了，这里自己补回来）
      · Ctrl+C / 右键「复制」—— 复制选中的行（一行没选时复制全部）
      · 右键「复制全部（含表头）」「复制该单元格」

    导出为制表符分隔，可直接粘进 Excel。
    """
    pos = [0, 0]
    anchor = [None]        # 鼠标按下时所在的行，拖动时作为区间起点

    def _sel_or_all():
        iids = tree.selection()
        return tree_text(tree, iids if iids else None)

    def _all():
        return tree_text(tree)

    def _cell():
        iid = tree.identify_row(pos[1])
        col = tree.identify_column(pos[0])
        return tree_cell_text(tree, col, iid) if iid and col else ""

    entries = [
        ("复制（选中行，未选中则全部）", _sel_or_all),
        ("复制全部（含表头）", _all),
        (cell_label, _cell),
    ]
    tree._copy_getters = entries

    # ---------- 鼠标滑动选中 ----------
    def _press(e):
        # 按在表头（分隔线）上时交给 Treeview 自己处理列宽拖动
        try:
            region = tree.identify_region(e.x, e.y)
        except Exception:
            region = ""
        anchor[0] = (tree.identify_row(e.y)
                     if region in ("cell", "tree") else None)
        # ★ 不返回 "break"：让单击选择、表头拖动等默认行为照常发生
        return None

    def _drag(e):
        if not anchor[0]:
            return None
        iid = tree.identify_row(e.y) or _edge_row(tree, e.y)
        if not iid:
            return "break"
        rows = tree.get_children()
        try:
            i0, i1 = rows.index(anchor[0]), rows.index(iid)
        except ValueError:          # 数据被刷新过，锚点已失效
            anchor[0] = None
            return "break"
        lo, hi = min(i0, i1), max(i0, i1)
        tree.selection_set(rows[lo:hi + 1])
        tree.focus(iid)
        return "break"

    def _release(_e):
        anchor[0] = None
        return None

    def _popup(e):
        pos[0], pos[1] = e.x, e.y
        menu = _copy_menu(tree)
        menu.add_command(
            label=entries[0][0],
            command=lambda: _fire_copy(tree, app, _sel_or_all()))
        menu.add_command(
            label=entries[1][0],
            command=lambda: _fire_copy(tree, app, _all()))
        menu.add_separator()
        menu.add_command(
            label=entries[2][0],
            command=lambda: _fire_copy(tree, app, _cell()))
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
            menu.destroy()
        return "break"

    def _hotkey(_e):
        _fire_copy(tree, app, _sel_or_all())
        return "break"

    tree.bind("<ButtonPress-1>", _press, add="+")
    tree.bind("<B1-Motion>", _drag, add="+")
    tree.bind("<ButtonRelease-1>", _release, add="+")
    tree.bind("<Button-3>", _popup, add="+")
    tree.bind("<Control-c>", _hotkey, add="+")
    tree.bind("<Control-C>", _hotkey, add="+")
    return entries


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
      "source" —— 菜单 2/4/5/6/7：不限格式，只跳过 *_translated.txt
                  与 *_translated_report.txt
      "report" —— 菜单 3：只识别 *_translated_report.txt
    """

    # 菜单 2/4/5/6/7 需要跳过的后缀
    SKIP_SUFFIX = ("_translated.txt", "_translated_report.txt")

    def __init__(self, master, bg=CARD, width=272, mode="source",
                 on_change=None, app=None, allow_game_root=False,
                 on_game_root=None):
        tk.Frame.__init__(self, master, bg=bg, width=width)
        self.bg = bg
        self.mode = mode
        self.on_change = on_change
        self.app = app                # 用于复制到剪贴板时的状态栏反馈
        self.panel_w = width          # ★ 供 clear() 等重画提示文字时算 wraplength
        self.allow_game_root = allow_game_root
        self.on_game_root = on_game_root
        self.game_root = None
        self.files = []
        self.vars = {}

        tk.Label(self, text="待操作文件", bg=bg, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=10, pady=(8, 4))

        row = tk.Frame(self, bg=bg)
        row.pack(fill="x", padx=10)
        GlassButton(row, "单个文件", width=88, height=34, bg=bg,
                    font=FONT_SMALL, command=self.pick_file).pack(side="left")
        GlassButton(row, "整个文件夹", width=88, height=34, bg=bg,
                    font=FONT_SMALL, command=self.pick_dir).pack(
            side="left", padx=6)

        row2 = tk.Frame(self, bg=bg)
        row2.pack(fill="x", padx=10, pady=(6, 2))
        GlassButton(row2, "全选", width=64, height=32, bg=bg,
                    font=FONT_SMALL, command=self.select_all).pack(side="left")
        GlassButton(row2, "清空", width=64, height=32, bg=bg,
                    font=FONT_SMALL, command=self.clear).pack(side="left", padx=6)
        self.count_lbl = tk.Label(row2, text="已选 0", bg=bg, fg=C_KEY,
                                  font=FONT_BIG)
        self.count_lbl.pack(side="right")

        # ★ 菜单 7：可以直接选游戏根目录（自动扫描里面的 txt 文件）
        if allow_game_root:
            row3 = tk.Frame(self, bg=bg)
            row3.pack(fill="x", padx=10, pady=(4, 2))
            GlassButton(row3, "游戏根目录", width=120, height=32, bg=bg,
                        font=FONT_SMALL,
                        command=self.pick_game_root).pack(side="left")
            self.root_lbl = tk.Label(row3, text="未选择", bg=bg, fg=C_HINT,
                                     font=FONT_SMALL, anchor="w",
                                     wraplength=max(100, width - 150))
            self.root_lbl.pack(side="left", padx=6)

        outer, inner = make_scroll_area(self, bg=bg)
        outer.pack(fill="both", expand=True, padx=6, pady=(4, 8))
        self.list_inner = inner

        # ★ 在列表空白处右键 → 复制所有已选文件的完整路径
        attach_copy(self.list_inner, [
            ("复制已选文件的完整路径", self._paths_text),
        ], app=self.app, hotkey=False)

        self._hint = tk.Label(inner, text=self._hint_text(),
                              bg=bg, fg=C_HINT, font=FONT_SMALL,
                              justify="left",
                              wraplength=max(120, self.panel_w - 62))
        self._hint.pack(anchor="w", padx=6, pady=10)

    # ---------- 复制 ----------
    def _paths_text(self):
        """已勾选文件的完整路径（每行一个）。"""
        return "\n".join(p for p in self.files
                         if self.vars.get(p) and self.vars[p].get())

    # ---------- 筛选规则 ----------
    def _hint_text(self):
        if self.mode == "report":
            return "点击上方按钮选择检查报告\n（只识别 *_translated_report.txt）"
        text = "点击上方按钮选择文件\n（不限格式，自动跳过译文与检查报告）"
        if getattr(self, "allow_game_root", False):
            text += "\n也可点「游戏根目录」自动扫描里面的 txt 文件"
        return text

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

    def pick_game_root(self):
        """选择游戏根目录：自动扫描里面的 txt 文件（跳过译文与报告）。"""
        folder = filedialog.askdirectory(
            title="选择游戏根目录（会自动扫描里面的 .txt 文件）",
            initialdir=self._initial())
        if not folder:
            return
        config.Runtime.set_dir(folder)
        found = []
        for root, dirs, files in os.walk(folder):
            # 别钻进太深的目录，也跳过生成物目录
            depth = os.path.relpath(root, folder).count(os.sep)
            if depth > 4:
                dirs[:] = []
                continue
            for f in files:
                if not f.lower().endswith(".txt"):
                    continue
                if not self._accept(f):
                    continue
                found.append(os.path.join(root, f))
                if len(found) >= 2000:
                    break
            if len(found) >= 2000:
                break
        found.sort()
        if not found:
            messagebox.showinfo(
                "提示", f"该目录下没找到可处理的 .txt 文件：\n{folder}")
            return
        self.game_root = folder
        self.root_lbl.config(text=os.path.basename(folder) or folder)
        self.add_files(found)
        if self.on_game_root:
            try:
                self.on_game_root(folder)
            except Exception:
                pass

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
            # ★ 右键文件名 → 复制文件名 / 完整路径
            attach_copy(cb, [
                ("复制文件名", lambda f=p: os.path.basename(f)),
                ("复制完整路径", lambda f=p: f),
            ], app=self.app, hotkey=False)
            self.files.append(p)
            added += 1
        self._update_count()
        if added and not silent and self.on_change:
            self.on_change(self.files)

    def set_files(self, paths):
        """整体替换（用于菜单之间的同步）。"""
        self.clear(silent=True)
        self.add_files(self._filter(list(paths)), silent=True)

    def clear(self, silent=False):
        for w in self.list_inner.winfo_children():
            w.destroy()
        self.files = []
        self.vars = {}
        self._hint = tk.Label(
            self.list_inner, text=self._hint_text(),
            bg=self.bg, fg=C_HINT, font=FONT_SMALL, justify="left",
            wraplength=max(120, self.panel_w - 62))
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

        card = RoundCard(self, radius=16, pad=16, width=520,
                         auto_height=True)
        card.pack(padx=12, pady=12)
        body = card.body

        tk.Label(body, text="添加术语", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(body,
                 text="新术语会立即写入术语字典；点「应用术语」时会删除\n"
                      "相关句子的缓存并重新翻译。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(4, 12))

        self.src_var = tk.StringVar()
        self.dst_var = tk.StringVar()
        first = None
        for text, var in ((f"原文（{src_lang or '源语言'}）", self.src_var),
                          (f"译文（{tgt_lang or '目标语言'}）", self.dst_var)):
            row = tk.Frame(body, bg=CARD)
            row.pack(fill="x", pady=6)
            tk.Label(row, text=text, bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                     width=18, anchor="w").pack(side="left")
            ent = ttk.Entry(row, textvariable=var, width=26, font=FONT)
            ent.pack(side="left", padx=8)
            if first is None:
                first = ent

        btns = tk.Frame(body, bg=CARD)
        btns.pack(fill="x", pady=(16, 0))
        GlassButton(btns, "取消", width=92, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._cancel).pack(side="right")
        GlassButton(btns, "确定添加", width=128, height=40, primary=True,
                    bg=CARD, font=FONT_SMALL,
                    command=self._ok).pack(side="right", padx=8)

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


class _AskText(tk.Toplevel):
    """通用的单行文本输入弹窗（术语冲突「自定义译文」用）。"""

    def __init__(self, master, title, prompt, initial="", width=520):
        tk.Toplevel.__init__(self, master, bg=BG_BASE)
        self.result = None
        self.title(title)
        self.resizable(False, False)
        self.transient(master)

        card = RoundCard(self, radius=16, pad=16, width=width,
                         auto_height=True)
        card.pack(padx=12, pady=12)
        body = card.body

        tk.Label(body, text=title, bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(body, text=prompt, bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(4, 10))

        self.var = tk.StringVar(value=initial or "")
        ent = ttk.Entry(body, textvariable=self.var, width=44, font=FONT)
        ent.pack(fill="x", pady=(0, 12))

        btns = tk.Frame(body, bg=CARD)
        btns.pack(fill="x")
        GlassButton(btns, "取消", width=92, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._cancel).pack(side="right")
        GlassButton(btns, "确定", width=110, height=40, primary=True,
                    bg=CARD, font=FONT_SMALL,
                    command=self._ok).pack(side="right", padx=8)

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        self._center(master)
        ent.focus_set()
        ent.select_range(0, "end")
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
        val = self.var.get().strip()
        if not val:
            messagebox.showwarning("提示", "内容不能为空", parent=self)
            return
        self.result = val
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, master, title, prompt, initial=""):
        dlg = cls(master, title, prompt, initial)
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

        self.term_edits = {}       # 原文 → 新译文
        self.term_deletes = set()  # 待删除原文集合（应用前可撤回）
        self.term_delete_stack = []  # 删除操作栈，支持逐步撤回
        self.term_checks = set()   # 勾选的术语原文（供批量删除使用）
        self.term_added = []       # 本次「添加术语」新增的原文（应用术语时强制重翻）
        self._term_visible = []    # 当前过滤后可见的术语原文（顺序同列表）
        self.prefix_edits = {}
        self.sheet_vars = {}       # Excel sheet → BooleanVar
        self.setting_widgets = {}  # key → (widget, typ)

        # 菜单 10（本地模型服务）
        self.pv_param_vars = {}    # config key → StringVar
        self._pv_btn_groups = []   # 提供商分段按钮组
        self._pv_models = []       # 当前列表里的模型行
        self._pv_adapt_text = ""   # 右侧适配清单（供复制）

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
                     rowheight=38, font=FONT)
        st.configure("Treeview.Heading", background="#EAF3FC",
                     foreground=ACCENT_DEEP, font=(FONT_FAMILY, FONT_B[1], "bold"),
                     borderwidth=0, relief="flat")
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
        self.root.minsize(1240, 760)
        # ★ 目标尺寸 1500x1000；屏幕放不下时按可用空间收缩，避免窗口被裁
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            w = min(1500, max(1000, sw - 40))
            h = min(1000, max(640, sh - 80))
            self.root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+"
                               f"{max(0, (sh - h) // 3)}")
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

        self.root.grid_columnconfigure(0, minsize=268)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

    def _paint_root_bg(self, e=None):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        paint_bg(self.bg_canvas, w, h)

    # ---------------- 左侧栏 ----------------
    def _build_sidebar(self):
        holder = tk.Frame(self.root, bg=BG_BASE, width=268)
        holder.grid(row=0, column=0, sticky="nsew", padx=(14, 6), pady=14)
        holder.pack_propagate(False)   # 子卡片是 pack 管理的

        card = RoundCard(holder, radius=18, pad=12)
        card.pack(fill="both", expand=True)
        body = card.body

        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x", pady=(2, 8))
        Avatar(head, size=76, path=config.AVATAR_FILE).pack(anchor="w")

        tk.Frame(body, bg=CARD_BORDER, height=1).pack(fill="x", pady=(2, 8))

        for idx, name in MENU_ITEMS:
            btn = MenuItem(body, idx, name,
                           command=lambda k=MENU_KEYS[idx]: self.show(k))
            btn.pack(fill="x", pady=4)
            self.menu_btns[MENU_KEYS[idx]] = btn

        tip = tk.Label(body, text="悬停头像查看作者信息", bg=CARD,
                       fg=C_HINT, font=FONT_SMALL)
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

        self._page_intl()
        self._page_translate()
        self._page_report()
        self._page_terms()
        self._page_prefix()
        self._page_polish()
        self._page_reflow()
        self._page_excel()
        self._page_settings()
        self._page_provider()
        self._page_log()

    # ---------------- 状态条 ----------------
    def _build_status(self):
        holder = tk.Frame(self.root, bg=BG_BASE, height=64)
        holder.grid(row=1, column=0, columnspan=2, sticky="ew",
                    padx=14, pady=(0, 12))
        holder.pack_propagate(False)   # 子控件是 pack 管理的，须用 pack_propagate

        card = RoundCard(holder, radius=14, pad=10)
        card.pack(fill="both", expand=True)
        body = card.body

        PokeBall(body, size=24).pack(side="left")
        self.status_lbl = tk.Label(body, textvariable=self.status_var,
                                   bg=CARD, fg=TEXT, font=FONT_B)
        self.status_lbl.pack(side="left", padx=8)
        attach_label_copy(self.status_lbl, self, "状态")

        self.cancel_btn = GlassButton(body, "取消", width=84, height=34,
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
        elif key == "provider":
            self._pv_refresh()
        elif key == "log":
            pass

    def _make_file_panel(self, holder, mode, allow_game_root=False,
                         on_game_root=None):
        """统一创建右侧文件侧边栏，并把菜单 2 的选择同步给其余菜单。"""
        fp = FilePanel(holder.body, bg=CARD, mode=mode,
                       on_change=self._sync_file_panels, app=self,
                       allow_game_root=allow_game_root,
                       on_game_root=on_game_root)
        fp.pack(fill="both", expand=True)
        self.file_panels.append(fp)
        return fp

    def _sync_file_panels(self, paths):
        """
        菜单 2（翻译）选中文件后，自动同步到菜单 3~6。
        菜单 3 只认检查报告，所以这里做一次「源文件 → 报告」的换算。
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
        # ★ 不给固定 width：按文字实际宽度排，避免长标签被截断
        tk.Label(row, text=text, bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL, anchor="w").pack(side="left")
        cb = ttk.Combobox(row, textvariable=var, values=values, width=width,
                          state="normal", font=FONT)
        cb.pack(side="left", padx=8)
        return cb

    def _model_row(self, parent, label="模型"):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL, anchor="w").pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.model_var,
                          values=self.models or [config.MODEL],
                          width=22, state="normal", font=FONT)
        cb.pack(side="left", padx=8)
        self.model_combos.append(cb)
        GlassButton(row, "检测", width=72, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._detect_models_async).pack(side="left", padx=8)
        return cb

    # ---------- 翻译模式 ----------
    def _mode_row(self, parent, label="模式"):
        """本地 Ollama / 云端 API 切换。"""
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL, anchor="w").pack(side="left")

        holder = tk.Frame(row, bg=CARD_BORDER)
        holder.pack(side="left", padx=8)
        group = {}
        for mode, text in (("ollama", "本地 Ollama"), ("api", "云端 API")):
            btn = tk.Label(holder, text=text, font=FONT_SMALL,
                           padx=16, pady=7, cursor="hand2")
            btn.pack(side="left", padx=(1, 1), pady=1)
            btn.bind("<Button-1>",
                     lambda _e, m=mode: self._switch_mode(m))
            group[mode] = btn
        self._mode_btn_groups.append(group)
        self._paint_mode_row()
        return row

    def _mode_text(self, mode):
        """模式按钮的显示名：本地 OpenAI 兼容服务时显示它自己的名字。"""
        if mode == "ollama":
            return "本地 Ollama"
        try:
            key = PV.current()
            if key in ("llamacpp", "lmstudio"):
                return PV.label_of(key)
        except Exception:
            pass
        return "云端 API"

    def _paint_mode_row(self):
        cur = settings.current_mode()
        for group in getattr(self, "_mode_btn_groups", []):
            for mode, btn in group.items():
                if not btn.winfo_exists():
                    continue
                on = (mode == cur)
                btn.configure(text=self._mode_text(mode),
                              bg=ACCENT if on else CARD,
                              fg="#FFFFFF" if on else TEXT_DIM,
                              font=(FONT_FAMILY, FONT_SMALL[1],
                                    "bold" if on else "normal"))

    def _switch_mode(self, mode):
        mode = settings.normalize_mode(mode)
        if mode == settings.current_mode():
            return
        changes = settings.set_mode(mode)
        PV.sync_with_mode(mode)
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
                elif kind == "term_conflict_done":
                    self._after_conflicts(payload)
                elif kind == "intl_extract_done":
                    r = (payload or [{}])[0] if isinstance(payload, list) else {}
                    if r.get("ok") is False:
                        self.intl_extract_lbl.config(
                            text=f"✘ {r.get('error', '失败')}")
                    else:
                        self.intl_extract_stat.config(
                            text=f"{r.get('sections', r.get('files', 0))} 段 / "
                                 f"{r.get('entries', 0)} 条")
                        outs = _intl_outs(r)
                        self.intl_extract_lbl.config(
                            text="✔ 已写出：" + outs)
                        self.intl_last_out = outs
                elif kind == "intl_compile_done":
                    r = payload or {}
                    if r.get("ok") is False:
                        self.intl_compile_lbl.config(
                            text=f"✘ {r.get('error', '失败')}")
                    else:
                        self.intl_compile_stat.config(
                            text=f"{r.get('sections', r.get('files', 0))} 段 / "
                                 f"{r.get('entries', 0)} 条")
                        txt = "✔ 已写出：" + _intl_outs(r)
                        lang = r.get("language") or {}
                        if lang.get("changed"):
                            txt += (f"\n语言表：已把"
                                    f" [\"{lang.get('display')}\", "
                                    f"\"{lang.get('fragment')}\"] "
                                    f"写进 Settings"
                                    + ("（并补了中文注释）"
                                       if lang.get("comment") else ""))
                        elif lang:
                            txt += f"\n语言表：{lang.get('reason') or '没有改动'}"
                        self.intl_compile_lbl.config(text=txt)
                elif kind == "plugin_done":
                    r = (payload or [{}])[0] if isinstance(payload, list) else {}
                    fam = r.get("font", "")
                    self.plugin_stat.config(
                        text=f"已植入（字体 {fam}）" if fam else "已植入")
                    self._refresh_plugin_font()
                elif kind == "plugin_restore_done":
                    r = (payload or [{}])[0] if isinstance(payload, list) else {}
                    removed = r.get("removed") or []
                    self.plugin_stat.config(text="")
                    self.plugin_restore_lbl.config(
                        text=("已还原：" + "、".join(removed)) if removed
                        else "没有找到插件脚本（可能本来就没植入过）")
                elif kind == "prefix_done":
                    messagebox.showinfo("完成",
                                        "前缀字典已写入并应用到翻译文件")
                elif kind == "prefix_terms_done":
                    r = payload or {}
                    messagebox.showinfo(
                        "应用术语完成",
                        f"前缀命中术语并替换：{r.get('changed', 0)} 条\n"
                        f"已写回译文文件：{r.get('files', 0)} 个")
                elif kind == "excel_done":
                    if payload and payload.get("ok"):
                        msg = [f"合计 {payload.get('total')} 条术语 → "
                               f"{payload.get('out_path')}"]
                        if (payload.get("mode") == "append"
                                and payload.get("existing")):
                            msg.append(
                                f"原有 {payload['existing']} 条，"
                                f"本次追加 {payload.get('added', 0)} 条，"
                                f"已存在跳过 "
                                f"{payload.get('skipped_existing', 0)} 条")
                            cf = payload.get("conflicts") or []
                            if cf:
                                msg.append(
                                    f"\n⚠ {len(cf)} 条术语的译法与已有字典不同，"
                                    f"已保留原有译法（未覆盖）：")
                                for s, old, new in cf[:6]:
                                    msg.append(f"  · {s}：保留「{old}」"
                                               f"（Excel 里是「{new}」）")
                                if len(cf) > 6:
                                    msg.append(f"  …另有 {len(cf) - 6} 条，"
                                               f"详见日志")
                        elif payload.get("mode") == "append":
                            msg.append(f"本次新建 {payload.get('added', 0)} 条")
                        messagebox.showinfo("完成", "\n".join(msg))
                    else:
                        messagebox.showwarning(
                            "未完成",
                            "；".join((payload or {}).get("errors", [])
                                      or ["提取失败"]))
                elif kind == "pv_autodet":
                    self._pv_apply_autodetect(*payload)
                elif kind == "pv_probe":
                    ok, msg = payload
                    self.pv_probe_lbl.configure(
                        text=("✔ " if ok else "✘ ") + msg,
                        fg=C_OK if ok else C_WARN)
                elif kind == "pv_models":
                    self._pv_apply_models(*payload)
                elif kind == "pv_deploy":
                    ok, msg, model = payload
                    self.set_busy(False, "部署完成" if ok else "部署失败")
                    if ok:
                        messagebox.showinfo("部署完成", f"{model}\n\n{msg}")
                    else:
                        messagebox.showwarning("部署未成功", f"{model}\n\n{msg}")
                    self._pv_refresh()
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

    # ================================================================
    # 复制到剪贴板
    # ================================================================
    def copy_to_clipboard(self, text, what="内容"):
        """统一复制入口：写剪贴板 + 状态栏反馈。返回是否成功。"""
        text = "" if text is None else str(text)
        if not text.strip():
            self.status_var.set("没有可复制的内容")
            return False
        ok = clipboard_set(self.root, text)
        if not ok:
            self.status_var.set("复制失败（剪贴板被其他程序占用）")
            return False
        n = len(text.splitlines())
        if n > 1:
            self.status_var.set(
                f"已复制{what} {n} 行到剪贴板，可直接粘贴到 Excel / 文本编辑器")
        else:
            self.status_var.set(f"已复制{what}到剪贴板：{text[:60]}")
        return True

    def _text_all(self, box):
        """取文本框全部内容。"""
        try:
            return box.get("1.0", "end-1c")
        except Exception:
            return ""

    def _text_pick(self, box):
        """文本框有选中就返回选中内容，否则返回全部。"""
        try:
            sel = box.get("sel.first", "sel.last")
            if sel.strip():
                return sel
        except Exception:
            pass
        return self._text_all(box)

    def _copy_report_list(self):
        """把报告列表当前显示的内容复制成制表符分隔文本。"""
        self.copy_to_clipboard(tree_text(self.report_tree), "报告列表")

    def _copy_log(self):
        """日志页「复制全部」按钮。"""
        self.copy_to_clipboard(self._text_all(self.log_text), "日志")

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

        # ★ 提示按菜单 10 选的提供商走，不写死 Ollama
        label, cur_model = "Ollama", config.MODEL
        try:
            import providers as PV
            label = PV.label_of(PV.current())
            cur_model = PV.current_model(PV.current()) or config.MODEL
        except Exception:
            pass

        if ok_service and ok_model:
            self.status_var.set(f"{label} 就绪：{msg}")
        elif ok_service:
            self.status_var.set(f"{label} 已连接，但模型未就绪：{cur_model}")
        else:
            self.status_var.set(f"{label} 未连接：{msg}（翻译功能不可用）")

    # ================================================================
    # 页面 1：文本提取与编译
    # ================================================================
    def _page_intl(self):
        self.intl_srcs = []          # 待编译的文本（文件 / 文件夹）
        self.intl_last_out = None
        page = self.pages["intl"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        # ★ 三层卡片加起来比窗口高，放进滚动区 —— 窗口小也不会被裁掉
        outer, inner = make_scroll_area(left, bg=BG_BASE)
        outer.pack(fill="both", expand=True)

        # ---- 上层：提取文本 ----
        c1 = RoundCard(inner, radius=16, pad=16, auto_height=True)
        c1.pack(fill="x", pady=(0, 10))
        head1 = tk.Frame(c1.body, bg=CARD)
        head1.pack(fill="x")
        tk.Label(head1, text="提取文本", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        self.intl_extract_stat = tk.Label(head1, text="", bg=CARD,
                                          fg=C_KEY, font=FONT_BIG)
        self.intl_extract_stat.pack(side="right")
        attach_label_copy(self.intl_extract_stat, self, "提取统计")
        row1 = tk.Frame(c1.body, bg=CARD)
        row1.pack(fill="x", pady=(8, 0))
        GlassButton(row1, "提取文本", width=140, height=46, primary=True,
                    bg=CARD, command=self._do_intl_extract).pack(side="left")
        self.intl_extract_lbl = tk.Label(c1.body, text="", bg=CARD,
                                         fg=C_KEY, font=FONT_SMALL,
                                         justify="left", wraplength=560)
        self.intl_extract_lbl.pack(anchor="w", pady=(6, 0))
        attach_label_copy(self.intl_extract_lbl, self, "提取结果")
        self.intl_extract_hint = tk.Label(
            c1.body,
            text="等同于在游戏 debug 菜单里执行 Extract Text：读游戏 "
                 "Data 下已编译的原文表，按游戏自己的格式写出 "
                 "intl.txt（放在游戏根目录）。已存在时先自动备份。",
            bg=CARD, fg=C_HINT, font=FONT_SMALL,
            justify="left", wraplength=560)
        self.intl_extract_hint.pack(anchor="w", pady=(6, 0))
        attach_label_copy(self.intl_extract_hint, self, "提取说明")

        # ---- 中层：编译文本 ----
        c2 = RoundCard(inner, radius=16, pad=16, auto_height=True)
        c2.pack(fill="x", pady=(0, 10))
        head2 = tk.Frame(c2.body, bg=CARD)
        head2.pack(fill="x")
        tk.Label(head2, text="编译文本", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        self.intl_compile_stat = tk.Label(head2, text="", bg=CARD,
                                          fg=C_KEY, font=FONT_BIG)
        self.intl_compile_stat.pack(side="right")
        attach_label_copy(self.intl_compile_stat, self, "编译统计")

        row2 = tk.Frame(c2.body, bg=CARD)
        row2.pack(fill="x", pady=(8, 0))
        GlassButton(row2, "选择文本文件", width=120, height=36, bg=CARD,
                    font=FONT_SMALL,
                    command=self._intl_pick_texts).pack(side="left")
        GlassButton(row2, "选择文件夹", width=110, height=36, bg=CARD,
                    font=FONT_SMALL,
                    command=self._intl_pick_text_dir).pack(side="left",
                                                           padx=6)
        GlassButton(row2, "清空", width=72, height=36, bg=CARD,
                    font=FONT_SMALL,
                    command=self._intl_clear_srcs).pack(side="left")
        self.intl_src_lbl = tk.Label(c2.body, text="未选择（默认用提取出来的 "
                                                   "intl.txt）",
                                     bg=CARD, fg=C_HINT, font=FONT_SMALL,
                                     justify="left", wraplength=560)
        self.intl_src_lbl.pack(anchor="w", pady=(6, 0))
        attach_label_copy(self.intl_src_lbl, self, "待编译文本")

        row3 = tk.Frame(c2.body, bg=CARD)
        row3.pack(fill="x", pady=(10, 0))
        GlassButton(row3, "编译文本", width=140, height=46, primary=True,
                    bg=CARD, command=self._do_intl_compile).pack(side="left")
        self.intl_lang_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            row3, text="编译后把中文加进游戏语言表",
            variable=self.intl_lang_var, bg=CARD, fg=TEXT,
            activebackground=CARD, activeforeground=TEXT,
            selectcolor="#FFFFFF", font=FONT_SMALL,
            cursor="hand2").pack(side="left", padx=12)
        self.intl_compile_lbl = tk.Label(c2.body, text="", bg=CARD,
                                         fg=C_KEY, font=FONT_SMALL,
                                         justify="left", wraplength=560)
        self.intl_compile_lbl.pack(anchor="w", pady=(6, 0))
        attach_label_copy(self.intl_compile_lbl, self, "编译结果")
        self.intl_compile_hint = tk.Label(
            c2.body,
            text="等同于在游戏 debug 菜单里执行 Compile Text。",
            bg=CARD, fg=C_HINT, font=FONT_SMALL,
            justify="left", wraplength=560)
        self.intl_compile_hint.pack(anchor="w", pady=(6, 0))
        attach_label_copy(self.intl_compile_hint, self, "编译说明")

        # ---- 下层：加载中文文本处理插件 ----
        c3 = RoundCard(inner, radius=16, pad=16, auto_height=True)
        c3.pack(fill="x")
        head3 = tk.Frame(c3.body, bg=CARD)
        head3.pack(fill="x")
        tk.Label(head3, text="加载中文文本处理插件", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        self.plugin_stat = tk.Label(head3, text="", bg=CARD, fg=C_KEY,
                                    font=FONT_SMALL)
        self.plugin_stat.pack(side="left", padx=10)
        attach_label_copy(self.plugin_stat, self, "插件统计")

        row_font = tk.Frame(c3.body, bg=CARD)
        row_font.pack(fill="x", pady=(8, 0))
        GlassButton(row_font, "选择字体", width=110, height=36, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pick_plugin_font).pack(side="left")
        self.plugin_font_lbl = tk.Label(row_font, text="", bg=CARD,
                                        fg=C_HINT, font=FONT_SMALL,
                                        justify="left", wraplength=330)
        self.plugin_font_lbl.pack(side="left", padx=10)
        attach_label_copy(self.plugin_font_lbl, self, "字体信息")
        GlassButton(row_font, "加载插件并编译", width=150, height=40,
                    primary=True, bg=CARD,
                    command=self._do_plugin_inject).pack(side="right")
        tk.Label(c3.body,
                 text="把「中文文本处理」插件放进游戏的 Plugins 目录、把选定字体"
                      "写进插件设置（字体文件复制到游戏 Fonts），然后把**全部**"
                      "插件一起编译进 Data/PluginScripts.rxdata —— "
                      "不用进游戏、也不用开调试模式。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=560).pack(anchor="w", pady=(6, 0))

        row_restore = tk.Frame(c3.body, bg=CARD)
        row_restore.pack(fill="x", pady=(10, 0))
        GlassButton(row_restore, "还原", width=100, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._do_plugin_restore).pack(side="left")
        tk.Label(row_restore,
                 text="删掉本工具植入的插件目录与当初复制进 Fonts 的字体"
                      "（游戏自带字体与其它插件不动）",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=420).pack(side="left", padx=10)
        self.plugin_restore_lbl = tk.Label(c3.body, text="", bg=CARD,
                                           fg=C_KEY, font=FONT_SMALL,
                                           justify="left", wraplength=560)
        self.plugin_restore_lbl.pack(anchor="w", pady=(4, 0))
        attach_label_copy(self.plugin_restore_lbl, self, "插件还原结果")
        self._refresh_plugin_font()

        # ---- 右侧：游戏文件夹 + 提示 ----
        fp_holder = RoundCard(page, radius=16, pad=8, width=272)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        body = fp_holder.body
        tk.Label(body, text="游戏文件夹", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=10, pady=(8, 4))
        GlassButton(body, "选择游戏根目录", width=132, height=36, bg=CARD,
                    font=FONT_SMALL,
                    command=self._intl_pick_folder).pack(anchor="w", padx=10)
        self.intl_folder_lbl = tk.Label(body, text="未选择", bg=CARD,
                                        fg=C_KEY, font=FONT_SMALL,
                                        wraplength=200, justify="left")
        self.intl_folder_lbl.pack(anchor="w", padx=10, pady=(6, 0))
        attach_copy(self.intl_folder_lbl, [
            ("复制路径", lambda: getattr(self, "intl_folder", "")),
        ], app=self, hotkey=False)
        self.intl_info_lbl = tk.Label(body, text="", bg=CARD, fg=C_KEY,
                                      font=FONT_SMALL, wraplength=200,
                                      justify="left")
        self.intl_info_lbl.pack(anchor="w", padx=10, pady=(4, 0))
        attach_label_copy(self.intl_info_lbl, self, "游戏信息")
        self.intl_hint_lbl = tk.Label(
            body,
            text="提示：\n"
                 "· 要选游戏根目录：里面有 Data 文件夹和 .exe 启动程序\n"
                 "· 适用于 Pokémon Essentials / mkxp / RMXP 游戏\n"
                 "· 提取出的 intl.txt 在游戏根目录；"
                 "数组段每 3 行一条（序号/原文/译文），"
                 "哈希段每 2 行一条（原文/译文）\n"
                 "· 翻译时**只改每个条目的最后一行**，上一行原文原样留着\n"
                 "· 编译前会自动备份原来的语言文件\n"
                 "· 插件只在游戏切到中文语言时生效",
            bg=CARD, fg=C_HINT, font=FONT_SMALL,
            justify="left", wraplength=200)
        self.intl_hint_lbl.pack(anchor="w", padx=10, pady=(10, 0))
        attach_label_copy(self.intl_hint_lbl, self, "使用提示")

    # ---------- 菜单 1：小工具 ----------
    def _intl_pick_folder(self):
        d = filedialog.askdirectory(
            title="选择游戏根目录（里面有 Data 文件夹和 .exe 启动程序）",
            initialdir=(config.Runtime.last_dir
                        if config.Runtime.last_dir
                        and os.path.isdir(config.Runtime.last_dir)
                        else config.BASE_DIR))
        if not d:
            return
        import game_scripts as GS
        ok, why = GS.check_game_root(d)
        self.intl_folder = d
        config.Runtime.set_dir(d)
        self.intl_folder_lbl.config(text=d)
        if not ok:
            self.intl_info_lbl.config(text=f"⚠ {why}", fg=C_WARN)
            messagebox.showwarning("这个目录不太对", why)
            return
        self._intl_refresh_info()

    def _intl_refresh_info(self):
        """
        显示识别到的游戏信息，并按**文本方案**刷新各层的说明：
          legacy → 一个 intl.txt ↔ 一个语言 .dat
          split  → Text_<语言>_core/ 与 _game/ ↔ 两份 messages_*.dat
        """
        d = getattr(self, "intl_folder", None)
        if not d:
            return
        try:
            import intl_text as IT
            info = IT.detect_scheme(d)
            frag = info.get("fragment") or "chinese"
            ver = info.get("essentials") or ""
            split = info["scheme"] == IT.SCHEME_SPLIT

            parts = []
            if ver:
                parts.append(f"Essentials {ver}")
            parts.append("新版拆分方案" if split else "旧版单文件方案")
            self.intl_info_lbl.config(text="✔ " + " · ".join(parts), fg=C_KEY)

            if split:
                self.intl_extract_hint.config(
                    text=f"这个游戏把文本分成 core（引擎）和 game（游戏）两份："
                         f"会导出成 Text_{frag}_core/ 与 Text_{frag}_game/ "
                         f"两个文件夹，里面**每个分段一个 txt**"
                         f"（BOM + 说明行 + [段名] + 条目）。"
                         f"已翻过的部分会带出来作对照。")
                self.intl_compile_hint.config(
                    text="选 Text_<语言>_core / Text_<语言>_game 两个文件夹"
                         "（或直接选里面的 txt），会分别编出 "
                         f"Data/messages_{frag}_core.dat 与 "
                         f"messages_{frag}_game.dat。覆盖前自动备份。")
                self.intl_src_lbl.config(
                    text="未选择（默认用提取出来的两个 Text_ 文件夹）")
            else:
                self.intl_extract_hint.config(
                    text="等同于在游戏 debug 菜单里执行 Extract Text：读游戏 "
                         "Data 下已编译的原文表，按游戏自己的格式写出 "
                         "intl.txt（放在游戏根目录）。已存在时先自动备份。")
                self.intl_compile_hint.config(
                    text="等同于 Compile Text：可以只选一个 txt，也可以选整个"
                         "文件夹（里面的 .txt 按文件名顺序合并）。输出位置按"
                         "游戏 Settings::LANGUAGES 自动定，覆盖前自动备份。")
                self.intl_src_lbl.config(
                    text="未选择（默认用提取出来的 intl.txt）")
        except Exception:
            self.intl_info_lbl.config(text="")

    def _intl_folder(self):
        """取当前游戏目录；没选或不合格时提示并返回 None。"""
        d = getattr(self, "intl_folder", None)
        if not d or not os.path.isdir(d):
            messagebox.showwarning("提示", "请先在右侧选择游戏根目录")
            return None
        import game_scripts as GS
        ok, why = GS.check_game_root(d)
        if not ok:
            messagebox.showwarning("这个目录不太对", why)
            return None
        return d

    def _intl_pick_texts(self):
        paths = filedialog.askopenfilenames(
            title="选择要编译的文本（intl 格式的 .txt）",
            initialdir=(config.Runtime.last_dir or config.BASE_DIR),
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not paths:
            return
        paths = [p for p in paths if p.lower().endswith(".txt")]
        if not paths:
            messagebox.showinfo("提示", "请选择 .txt 文本文件")
            return
        config.Runtime.set_dir(os.path.dirname(paths[0]))
        for p in paths:
            if p not in self.intl_srcs:
                self.intl_srcs.append(p)
        self._intl_refresh_srcs()

    def _intl_pick_text_dir(self):
        d = filedialog.askdirectory(
            title="选择文件夹（里面的 .txt 会全部参与编译）",
            initialdir=(config.Runtime.last_dir or config.BASE_DIR))
        if not d:
            return
        config.Runtime.set_dir(d)
        if d not in self.intl_srcs:
            self.intl_srcs.append(d)
        self._intl_refresh_srcs()

    def _intl_clear_srcs(self):
        self.intl_srcs = []
        self._intl_refresh_srcs()

    def _intl_refresh_srcs(self):
        srcs = getattr(self, "intl_srcs", [])
        if not srcs:
            self.intl_src_lbl.config(
                text="未选择（默认用提取出来的 intl.txt）", fg=C_HINT)
            return
        shown = "、".join(os.path.basename(p) for p in srcs[:3])
        if len(srcs) > 3:
            shown += f" 等 {len(srcs)} 项"
        self.intl_src_lbl.config(text=f"已选 {len(srcs)} 项：{shown}",
                                 fg=C_KEY)

    def _do_intl_extract(self):
        d = self._intl_folder()
        if not d:
            return
        self.show("log")

        def work():
            res = commands.intl_extract_paths([d])
            self.q.put(("intl_extract_done", res))
            return res

        self.run_async(work, label="提取文本中…", done_label="文本提取完成")

    def _do_intl_compile(self):
        d = self._intl_folder()
        if not d:
            return
        import intl_text as IT
        srcs = list(getattr(self, "intl_srcs", []))
        if not srcs:
            guess = IT.extract_target(d)
            paths = guess if isinstance(guess, (list, tuple)) else [guess]
            paths = [p for p in paths if os.path.exists(p)]
            if not paths:
                messagebox.showwarning(
                    "提示",
                    "还没选要编译的文本。\n\n"
                    "可以点「选择文本文件」/「选择文件夹」，"
                    "或者先执行「提取文本」再回来编译。")
                return
            srcs = paths
        apply_lang = bool(self.intl_lang_var.get())
        self.show("log")

        def work():
            res = commands.intl_compile_paths(
                d, srcs, apply_language=apply_lang)
            self.q.put(("intl_compile_done", res))
            return res

        self.run_async(work, label="编译文本中…", done_label="文本编译完成")

    # ================================================================
    # 页面 2：翻译
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
        c1.configure(height=140)
        c1.pack_propagate(False)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="语言选择", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        row = tk.Frame(c1.body, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        self._labeled_combo(row, "源语言", self.src_var, LANG_VALUES, 14)
        self._labeled_combo(row, "目标语言", self.tgt_var, LANG_VALUES, 14)

        # 中层：模型
        c2 = RoundCard(left, radius=16, pad=18)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tk.Label(c2.body, text="模型与模式", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        self._mode_row(c2.body)
        self._model_row(c2.body)
        tk.Label(c2.body,
                 text="本地模式自动检测已安装的 Ollama 模型；"
                      "云端模式填写 API 地址与密钥后可用。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(10, 0))

        # 下层：开始
        c3 = RoundCard(left, radius=16, pad=18)
        c3.configure(height=136)
        c3.pack_propagate(False)
        c3.grid(row=2, column=0, sticky="ew")
        GlassButton(c3.body, "开始翻译", width=200, height=52,
                    primary=True, bg=CARD,
                    command=self._do_translate).pack(anchor="w")
        tk.Label(c3.body, text="点击后跳转到日志页，实时查看进度",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL).pack(anchor="w",
                                                           pady=(8, 0))

        # 右侧文件栏
        fp_holder = RoundCard(page, radius=16, pad=8, width=272)
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

        # 报告页状态：report = 5 列问题列表；conflict = 4 列术语冲突列表
        self.report_mode = "report"
        self.report_hits = []
        self.report_counts = {}
        self.report_kind_vars = {}
        self.conflict_choices = {}
        self._conflict_entry = None

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        c1 = RoundCard(left, radius=16, pad=18, auto_height=True)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="语言与模型", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        row = tk.Frame(c1.body, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        self._labeled_combo(row, "源语言", self.src_var, LANG_VALUES, 12)
        self._labeled_combo(row, "目标语言", self.tgt_var, LANG_VALUES, 12)
        self._mode_row(c1.body)
        self._model_row(c1.body)

        c2 = RoundCard(left, radius=16, pad=14)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        head = tk.Frame(c2.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="报告内容", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        GlassButton(head, "刷新报告", width=104, height=34, bg=CARD,
                    font=FONT_SMALL, command=self._do_check).pack(side="left",
                                                                  padx=12)
        # ★ 白名单：加进来的词不再报「疑似未翻译」，
        #   加进来的整句在重翻时会被跳过
        GlassButton(head, "白名单", width=92, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._open_whitelist).pack(side="left")
        self.report_stat = tk.Label(head, text="尚未检查", bg=CARD,
                                    fg=C_KEY, font=FONT_BIG)
        self.report_stat.pack(side="right")
        attach_label_copy(self.report_stat, self, "统计")

        # ★ 重翻类型选择（刷新报告后按实际出现的问题类型动态生成）
        self.report_kind_bar = tk.Frame(c2.body, bg=CARD)
        self.report_kind_bar.pack(fill="x", pady=(6, 0))

        wrap = tk.Frame(c2.body, bg=CARD)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        self.report_wrap = wrap
        cols = ("kind", "line", "src", "dst", "detail")
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=3)
        for c, w, t in (("kind", 78, "类型"), ("line", 44, "行"),
                        ("src", 178, "原文"), ("dst", 178, "译文"),
                        ("detail", 176, "说明")):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.report_tree = tree
        tree.tag_configure("k_old", background="#E3F0FF")
        tree.tag_configure("k_new", background="#E4F7EA")
        tree.tag_configure("k_custom", background="#FFF4D6")
        tree.bind("<Button-1>", self._on_conflict_click)
        tree.bind("<Double-1>", self._on_conflict_dblclick)
        bind_tree_wheel(tree)
        attach_tree_copy(tree, self)      # ★ 右键 / Ctrl+C 复制列表

        # ★ 底部操作区：常规模式 / 术语冲突模式，同一位置切换（省高度）
        c3 = RoundCard(left, radius=16, pad=18, auto_height=True)
        c3.grid(row=2, column=0, sticky="ew")

        self.c3_normal = tk.Frame(c3.body, bg=CARD)
        btn_row = tk.Frame(self.c3_normal, bg=CARD)
        btn_row.pack(fill="x")
        GlassButton(btn_row, "开始重翻", width=200, height=52,
                    primary=True, bg=CARD,
                    command=self._do_retranslate_report).pack(side="left")
        self.conflict_btn = GlassButton(btn_row, "解决术语冲突", width=180,
                                        height=52, bg=CARD, font=FONT_BIG,
                                        command=self._toggle_conflict_view)
        self.conflict_btn.pack(side="left", padx=10)
        self.conflict_btn.set_enabled(False)
        GlassButton(btn_row, "复制列表", width=140, height=52, bg=CARD,
                    font=FONT_BIG,
                    command=self._copy_report_list).pack(side="left",
                                                        padx=(10, 0))
        self.report_hint = tk.Label(
            self.c3_normal,
            text="删除勾选类型的问题句缓存并重新翻译；"
                 "「译文残留控制码」等类型不参与重翻",
            bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
            wraplength=560)
        self.report_hint.pack(anchor="w", pady=(8, 0))

        self.c3_conflict = tk.Frame(c3.body, bg=CARD)
        self._build_conflict_bar(self.c3_conflict)

        self.c3_normal.pack(fill="x")

        fp_holder = RoundCard(page, radius=16, pad=8, width=272)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "report")
        self.fp_report = fp

    def _show_c3_mode(self, mode):
        """切换底部操作区：report = 常规；conflict = 术语冲突。"""
        if mode == "conflict":
            self.c3_normal.pack_forget()
            self.c3_conflict.pack(fill="x")
        else:
            self.c3_conflict.pack_forget()
            self.c3_normal.pack(fill="x")
        # 冲突视图里隐藏「重翻类型」，避免误以为它作用于冲突列表
        try:
            if mode == "conflict":
                self.report_kind_bar.pack_forget()
            elif not self.report_kind_bar.winfo_ismapped():
                self.report_kind_bar.pack(fill="x", pady=(6, 0),
                                          before=self.report_wrap)
        except Exception:
            pass

    # ----------------------------------------------------------------
    # 报告页：重翻类型
    # ----------------------------------------------------------------
    def _render_kind_bar(self):
        """按当前报告里出现的问题类型生成可勾选的重翻类型。"""
        bar = self.report_kind_bar
        for w in bar.winfo_children():
            w.destroy()
        self.report_kind_vars = {}

        counts = getattr(self, "report_counts", {}) or {}
        if not counts:
            tk.Label(bar, text="重翻类型：刷新报告后可逐项勾选", bg=CARD,
                     fg=C_HINT, font=FONT_SMALL).pack(anchor="w")
            return

        order = list(commands.REPORT_KIND_ORDER)
        for k in counts:
            if k not in order:
                order.append(k)

        tk.Label(bar, text="重翻类型", bg=CARD, fg=C_TITLE,
                 font=FONT_B).grid(row=0, column=0, sticky="w",
                                   padx=(0, 10), pady=2)
        col, row = 1, 0
        for kind in order:
            n = counts.get(kind)
            if not n:
                continue
            if col >= 4:                      # 每行最多 3 个，放不下时换行
                col, row = 1, row + 1
            if kind in commands.NEVER_RETRANSLATE_KINDS:
                tk.Label(bar, text=f"{kind}({n}) 需手动", bg=CARD, fg=C_HINT,
                         font=FONT_SMALL).grid(row=row, column=col,
                                               sticky="w", padx=6, pady=2)
            else:
                var = tk.BooleanVar(value=(kind in commands.RETRANSLATE_KINDS))
                tk.Checkbutton(
                    bar, text=f"{kind}({n})", variable=var,
                    bg=CARD, fg=C_KEY if kind in commands.RETRANSLATE_KINDS
                    else TEXT,
                    activebackground=CARD, activeforeground=TEXT,
                    selectcolor="#FFFFFF", font=FONT_SMALL,
                    cursor="hand2",
                    command=self._render_report_rows).grid(
                        row=row, column=col, sticky="w", padx=6, pady=2)
                self.report_kind_vars[kind] = var
            col += 1

        # 全选 / 全不选
        if col >= 4:
            col, row = 1, row + 1
        for text, val in (("全选", True), ("全不选", False)):
            lbl = tk.Label(bar, text=f"[{text}]", bg=CARD, fg=ACCENT,
                           font=FONT_SMALL, cursor="hand2")
            lbl.grid(row=row, column=col, sticky="w", padx=4, pady=2)
            lbl.bind("<Button-1>",
                     lambda _e, v=val: self._toggle_all_kinds(v))
            col += 1

    def _toggle_all_kinds(self, value):
        for var in self.report_kind_vars.values():
            var.set(value)
        self._render_report_rows()

    def _selected_kinds(self):
        return [k for k, v in self.report_kind_vars.items() if v.get()]

    def _render_report_rows(self):
        """按勾选的类型过滤报告列表。"""
        if getattr(self, "report_mode", "report") == "conflict":
            return
        tree = self.report_tree
        for iid in tree.get_children():
            tree.delete(iid)
        sel = set(self._selected_kinds())
        has_filter = bool(getattr(self, "report_kind_vars", {}))
        shown = 0
        # ★ 行号 → hit 的映射：双击时要拿回完整原文（列表里是截断显示的）
        self.report_iid_map = {}
        for _path, h in getattr(self, "report_hits", []):
            kind = h.get("kind", "")
            if has_filter and kind not in sel:
                continue
            shown += 1
            iid = tree.insert("", "end", values=(
                kind, h.get("line_no", ""),
                (h.get("src") or "")[:200],
                (h.get("dst") or "")[:200],
                (h.get("detail") or "")[:200],
            ))
            self.report_iid_map[iid] = h
        total = len(getattr(self, "report_hits", []))
        self.report_stat.config(text=f"显示 {shown} / 共 {total} 处问题")

    # ================================================================
    # 白名单（词 + 句子）
    # ================================================================
    def _open_whitelist(self):
        import checker as CK
        CK.reload_whitelist()

        win = tk.Toplevel(self.root)
        win.title("白名单")
        win.configure(bg=CARD)
        win.transient(self.root)
        win.resizable(False, False)

        def sec(text, tip):
            tk.Label(win, text=text, bg=CARD, fg=C_TITLE,
                     font=FONT_TITLE).pack(anchor="w", padx=16, pady=(12, 0))
            tk.Label(win, text=tip, bg=CARD, fg=C_HINT, font=FONT_SMALL,
                     justify="left", wraplength=600).pack(anchor="w", padx=16)

        # ---------- ① 词白名单 ----------
        sec("检查白名单（词）",
            "加了词的句子不再报「疑似未翻译」。区分大小写，"
            "例如加 Tab 不会顺带放行 tab。")
        wrow = tk.Frame(win, bg=CARD)
        wrow.pack(fill="x", padx=16, pady=(6, 0))
        word_var = tk.StringVar()
        went = ttk.Entry(wrow, textvariable=word_var, width=26,
                         font=FONT_SMALL)
        went.pack(side="left")
        wlist = tk.Listbox(win, height=5, font=FONT_SMALL, bg="#FFFFFF",
                           fg=TEXT, relief="solid", bd=1,
                           highlightthickness=1,
                           highlightbackground=CARD_BORDER)
        wlist.pack(fill="x", padx=16, pady=(6, 0))

        def refresh_words():
            wlist.delete(0, "end")
            for w in sorted(CK.user_words()):
                wlist.insert("end", w)
            wcnt.configure(text=f"共 {len(CK.user_words())} 个")

        def add_word():
            ok, msg = CK.add_word(word_var.get())
            if not ok:
                messagebox.showwarning("没加进去", msg, parent=win)
                return
            word_var.set("")
            refresh_words()

        def del_word():
            sel = wlist.curselection()
            if not sel:
                return
            CK.remove_word(wlist.get(sel[0]))
            refresh_words()

        GlassButton(wrow, "加入", width=64, height=32, bg=CARD,
                    font=FONT_SMALL, command=add_word).pack(side="left",
                                                            padx=6)
        GlassButton(wrow, "删除选中", width=96, height=32, bg=CARD,
                    font=FONT_SMALL, command=del_word).pack(side="left")
        wcnt = tk.Label(wrow, text="", bg=CARD, fg=C_HINT, font=FONT_SMALL)
        wcnt.pack(side="left", padx=10)
        went.bind("<Return>", lambda _e: add_word())

        # ---------- ② 句子白名单 ----------
        sec("重翻白名单（整句）",
            "加进来的句子在「重翻检查报告内容」时会被跳过，不再重翻。"
            "可以直接把上面报告里选中的行加进来。")
        srow = tk.Frame(win, bg=CARD)
        srow.pack(fill="x", padx=16, pady=(6, 0))
        slist = tk.Listbox(win, height=5, font=FONT_SMALL, bg="#FFFFFF",
                           fg=TEXT, relief="solid", bd=1,
                           highlightthickness=1,
                           highlightbackground=CARD_BORDER)
        slist.pack(fill="x", padx=16, pady=(6, 0))

        def refresh_sents():
            slist.delete(0, "end")
            for s in sorted(CK.user_sentences()):
                slist.insert("end", s)
            scnt.configure(text=f"共 {len(CK.user_sentences())} 句")

        def add_selected():
            picked = []
            try:
                for iid in self.report_tree.selection():
                    vals = self.report_tree.item(iid, "values")
                    if vals and str(vals[2]).strip():
                        picked.append(str(vals[2]))
            except Exception:
                pass
            if not picked:
                messagebox.showinfo(
                    "没有选中",
                    "请先在报告列表里选中要加白名单的行（可按住 Ctrl / Shift 多选）。",
                    parent=win)
                return
            n = CK.add_sentences(picked)
            refresh_sents()
            messagebox.showinfo("已加入", f"新增 {n} 句（重复的不计）",
                                parent=win)

        def del_sent():
            sel = slist.curselection()
            if not sel:
                return
            CK.remove_sentence(slist.get(sel[0]))
            refresh_sents()

        GlassButton(srow, "把报告里选中的行加入", width=180, height=32,
                    bg=CARD, font=FONT_SMALL,
                    command=add_selected).pack(side="left")
        GlassButton(srow, "删除选中", width=96, height=32, bg=CARD,
                    font=FONT_SMALL, command=del_sent).pack(side="left",
                                                            padx=6)
        scnt = tk.Label(srow, text="", bg=CARD, fg=C_HINT, font=FONT_SMALL)
        scnt.pack(side="left", padx=10)

        refresh_words()
        refresh_sents()

        bar = tk.Frame(win, bg=CARD)
        bar.pack(fill="x", padx=16, pady=12)
        tk.Label(bar, text=f"文件：{CK.WHITELIST_FILE}", bg=CARD, fg=C_HINT,
                 font=FONT_SMALL).pack(side="left")
        GlassButton(bar, "关闭", width=72, height=32, primary=True, bg=CARD,
                    command=win.destroy).pack(side="right")

        # 居中
        try:
            win.update_idletasks()
            x = self.root.winfo_rootx() + (
                self.root.winfo_width() - win.winfo_width()) // 2
            y = self.root.winfo_rooty() + 120
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
        win.grab_set()
        win.focus_force()

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
        if self.report_mode != "report":
            self.report_mode = "report"
            self._set_report_columns("report")
            self._show_c3_mode("report")

        hits = []
        for path, hs in (result or {}).items():
            for h in hs:
                hits.append((path, h))
        self.report_hits = hits
        self.report_counts = Counter(h.get("kind", "") for _p, h in hits)

        self._render_kind_bar()
        self._render_report_rows()

        n_conf = sum(1 for _p, h in hits if h.get("kind") == "术语冲突")
        try:
            self.conflict_btn.set_enabled(n_conf > 0)
        except Exception:
            pass
        self.report_hint.config(
            text=(f"发现 {n_conf} 处术语冲突，可点「解决术语冲突」逐条处理；"
                  "重翻只对勾选的类型生效" if n_conf else
                  "删除勾选类型的问题句缓存并重新翻译；"
                  "「译文残留控制码」等类型不参与重翻"))
        self.status_var.set(
            f"检查完成：{len(hits)} 处问题 / {len(result or {})} 个文件")

    # ----------------------------------------------------------------
    # 术语冲突：三列视图 + 逐条选择
    # ----------------------------------------------------------------
    _CONFLICT_COLS = (("term", 150, "术语原文"),
                      ("old", 170, "已有译文"),
                      ("new", 170, "新增译文"),
                      ("keep", 150, "保留"))

    def _set_report_columns(self, mode):
        tree = self.report_tree
        if mode == "conflict":
            cols = [c for c, _w, _t in self._CONFLICT_COLS]
            tree.configure(columns=cols, show="headings")
            for c, w, t in self._CONFLICT_COLS:
                tree.heading(c, text=t)
                tree.column(c, width=w, anchor="w")
        else:
            cols = ("kind", "line", "src", "dst", "detail")
            tree.configure(columns=cols, show="headings")
            for c, w, t in (("kind", 78, "类型"), ("line", 44, "行"),
                            ("src", 178, "原文"), ("dst", 178, "译文"),
                            ("detail", 176, "说明")):
                tree.heading(c, text=t)
                tree.column(c, width=w, anchor="w")

    def _build_conflict_bar(self, bar):
        tk.Label(bar, text="单击「已有译文」或「新增译文」选中该译文；"
                           "双击「保留」列可输入自定义译文；"
                           "双击「术语原文」可修改术语原文",
                 bg=CARD, fg=C_WARN, font=FONT_SMALL,
                 justify="left", wraplength=560).pack(anchor="w")
        row = tk.Frame(bar, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        for text, cmd in (
                ("全部保留已有", lambda: self._conflict_keep_all("old")),
                ("全部保留新增", lambda: self._conflict_keep_all("new")),
                ("自定义译文", self._conflict_custom_selected),
                ("返回报告", self._toggle_conflict_view)):
            GlassButton(row, text, width=112, height=40, bg=CARD,
                        font=FONT_SMALL, command=cmd).pack(side="left",
                                                           padx=(0, 8))
        row2 = tk.Frame(bar, bg=CARD)
        row2.pack(fill="x", pady=(8, 0))
        tk.Label(row2, text="写入术语字典 → 删缓存 → 重翻",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL).pack(side="left")
        GlassButton(row2, "应用并重翻", width=150, height=46, primary=True,
                    bg=CARD, font=FONT_BIG,
                    command=self._apply_conflicts).pack(side="right")

    def _toggle_conflict_view(self):
        if self._conflict_entry is not None:
            try:
                self._conflict_entry.destroy()
            except Exception:
                pass
            self._conflict_entry = None

        if self.report_mode == "conflict":
            self.report_mode = "report"
            self._set_report_columns("report")
            self._show_c3_mode("report")
            self.report_hint.config(
                text="删除勾选类型的问题句缓存并重新翻译；"
                     "「译文残留控制码」等类型不参与重翻")
            self._render_report_rows()
            self._refresh_conflict_btn()
            return

        # 收集报告里的术语冲突（按术语原文去重）
        rows = []
        seen = set()
        for _path, h in getattr(self, "report_hits", []):
            if h.get("kind") != "术语冲突":
                continue
            term = (h.get("term_src") or "").strip()
            if not term or term in seen:
                continue
            seen.add(term)
            rows.append((term, h.get("term_old", "") or "",
                         h.get("term_new", "") or ""))
        if not rows:
            messagebox.showinfo("提示", "当前报告里没有术语冲突")
            return

        self.report_mode = "conflict"
        self._set_report_columns("conflict")
        tree = self.report_tree
        for iid in tree.get_children():
            tree.delete(iid)
        self.conflict_choices = {}
        for term, old, new in rows:
            val = old or new
            keep = "old" if old else "new"
            iid = tree.insert("", "end", values=(
                term, old, new, f"● {val}"), tags=(f"k_{keep}",))
            self.conflict_choices[iid] = {
                "term": term, "old": old, "new": new,
                "keep": keep, "value": val,
            }
        self.report_stat.config(text=f"术语冲突 {len(rows)} 条")
        self._show_c3_mode("conflict")
        self._refresh_conflict_btn()

    def _refresh_conflict_btn(self):
        n = sum(1 for _p, h in getattr(self, "report_hits", [])
                if h.get("kind") == "术语冲突")
        try:
            self.conflict_btn.set_enabled(
                n > 0 and self.report_mode != "conflict")
        except Exception:
            pass

    def _conflict_set_keep(self, iid, keep, value=None):
        info = self.conflict_choices.get(iid)
        if not info:
            return
        if value is None:
            value = info.get("old") if keep == "old" else info.get("new")
        info["keep"] = keep
        info["value"] = value or ""
        tree = self.report_tree
        term = info.get("new_term") or info["term"]
        tree.item(iid, values=(term, info["old"], info["new"],
                              f"● {info['value']}"), tags=(f"k_{keep}",))

    def _conflict_set_term(self, iid, new_term):
        """修改术语原文（写回术语字典时先改名）。"""
        info = self.conflict_choices.get(iid)
        if not info:
            return
        new_term = (new_term or "").strip()
        if not new_term or new_term == info["term"]:
            info.pop("new_term", None)
        else:
            info["new_term"] = new_term
        tree = self.report_tree
        term = info.get("new_term") or info["term"]
        tree.item(iid, values=(term, info["old"], info["new"],
                              f"● {info['value']}"),
                  tags=(f"k_{info['keep']}",))

    def _conflict_keep_all(self, keep):
        for iid in list(getattr(self, "conflict_choices", {}).keys()):
            self._conflict_set_keep(iid, keep)

    def _conflict_custom_selected(self):
        sel = self.report_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表里选中要自定义的术语")
            return
        first = self.conflict_choices.get(sel[0], {})
        val = _AskText.ask(self.root, "自定义译文",
                           f"术语：{first.get('term', '')}\n"
                           f"已有：{first.get('old', '')}   "
                           f"新增：{first.get('new', '')}\n"
                           f"请输入要保留的译文",
                           initial=first.get("value", ""))
        if not val:
            return
        for iid in sel:
            self._conflict_set_keep(iid, "custom", val)

    def _conflict_cell_entry(self, iid, col="#4"):
        tree = self.report_tree
        bbox = tree.bbox(iid, col)
        if not bbox:
            return
        x, y, w, h = bbox
        info = self.conflict_choices.get(iid, {})
        ent = tk.Entry(tree, font=FONT_SMALL, relief="solid", bd=1)
        ent.insert(0, info.get("value", ""))
        ent.select_range(0, "end")
        ent.place(x=x, y=y, width=max(w, 120), height=h)
        ent.focus_set()
        self._conflict_entry = ent
        state = {"done": False}

        def close():
            if state["done"]:
                return False
            state["done"] = True
            try:
                ent.destroy()
            except Exception:
                pass
            self._conflict_entry = None
            return True

        def commit(_e=None):
            val = ent.get().strip()
            if not close():
                return
            if val:
                self._conflict_set_keep(iid, "custom", val)

        def cancel(_e=None):
            close()

        ent.bind("<Return>", commit)
        ent.bind("<FocusOut>", commit)
        ent.bind("<Escape>", cancel)

    def _conflict_edit_term(self, iid):
        """双击「术语原文」列：就地输入新的术语原文。"""
        tree = self.report_tree
        bbox = tree.bbox(iid, "#1")
        if not bbox:
            return
        x, y, w, h = bbox
        info = self.conflict_choices.get(iid, {})
        ent = tk.Entry(tree, font=FONT_SMALL, relief="solid", bd=1)
        ent.insert(0, info.get("new_term") or info.get("term", ""))
        ent.select_range(0, "end")
        ent.place(x=x, y=y, width=max(w, 120), height=h)
        ent.focus_set()
        self._conflict_entry = ent
        state = {"done": False}

        def close():
            if state["done"]:
                return False
            state["done"] = True
            try:
                ent.destroy()
            except Exception:
                pass
            self._conflict_entry = None
            return True

        def commit(_e=None):
            val = ent.get().strip()
            if not close():
                return
            if val:
                self._conflict_set_term(iid, val)

        def cancel(_e=None):
            close()

        ent.bind("<Return>", commit)
        ent.bind("<FocusOut>", commit)
        ent.bind("<Escape>", cancel)

    def _on_conflict_click(self, event):
        if getattr(self, "report_mode", "report") != "conflict":
            return
        tree = self.report_tree
        iid = tree.identify_row(event.y)
        col = tree.identify_column(event.x)
        if not iid:
            return
        if col == "#2":
            self._conflict_set_keep(iid, "old")
        elif col == "#3":
            self._conflict_set_keep(iid, "new")

    def _on_conflict_dblclick(self, event):
        if getattr(self, "report_mode", "report") != "conflict":
            # ★ 常规报告模式：双击任意一行 → 打开「原文 / 译文」编辑窗
            self._on_report_dblclick(event)
            return
        tree = self.report_tree
        iid = tree.identify_row(event.y)
        col = tree.identify_column(event.x)
        if iid and col == "#4":
            self._conflict_cell_entry(iid, col)
        elif iid and col == "#1":
            self._conflict_edit_term(iid)

    def _on_report_dblclick(self, event):
        """报告列表双击 → 弹窗编辑这一句的译文。"""
        tree = self.report_tree
        iid = tree.identify_row(event.y)
        if not iid:
            return
        hit = getattr(self, "report_iid_map", {}).get(iid)
        if hit is None:
            return
        self._open_report_edit(iid, hit)

    def _open_report_edit(self, iid, hit):
        """
        编辑单句译文：上方原文（只读，用来对照）、下方译文（可编辑）。
        保存后写入翻译缓存，并把这句归入「已编辑」类型。
        """
        src = hit.get("src") or ""
        dst = hit.get("dst") or ""
        if not src.strip():
            messagebox.showinfo("提示", "这一行没有原文，无法定位缓存条目")
            return

        win = tk.Toplevel(self.root)
        win.title("编辑译文")
        win.configure(bg=BG_BASE)
        win.transient(self.root)

        card = RoundCard(win, radius=16, pad=16, width=640, auto_height=True)
        card.pack(padx=12, pady=12)
        body = card.body

        tk.Label(body, text="编辑译文", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(body,
                 text="保存后：写入翻译缓存，并把这一句归入「已编辑」类型"
                      "（默认不勾选，也不会被重翻覆盖）。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=600).pack(anchor="w", pady=(4, 10))

        def textbox(parent, title, value, readonly, height):
            tk.Label(parent, text=title, bg=CARD, fg=TEXT_DIM,
                     font=FONT_SMALL).pack(anchor="w")
            box = tk.Text(parent, height=height, wrap="word", font=FONT,
                          bg="#F5F7FA" if readonly else "#FFFFFF",
                          fg=TEXT_DIM if readonly else TEXT,
                          relief="solid", bd=1, highlightthickness=1,
                          highlightbackground=CARD_BORDER,
                          padx=6, pady=6, undo=True)
            box.insert("1.0", value)
            if readonly:
                box.configure(state="disabled")
            box.pack(fill="x", pady=(4, 10))
            return box

        textbox(body, f"原文（{self.src_var.get() or '源语言'}） · 只读，用于对照",
                src, True, 5)
        dst_box = textbox(body, f"译文（{self.tgt_var.get() or '目标语言'}）"
                                f" · 可编辑",
                          dst, False, 7)
        dst_box.focus_set()
        dst_box.tag_configure("sel", background="#CFE3FF")

        def commit():
            new = dst_box.get("1.0", "end-1c")
            if new == dst:
                win.destroy()
                return
            if not new.strip():
                if not messagebox.askyesno(
                        "译文是空的",
                        "保存空译文会让这一句在游戏里显示为空。\n确定吗？"):
                    return
            try:
                res = commands.save_report_edit(src, new)
            except Exception as e:
                messagebox.showerror("保存失败", str(e))
                return
            win.destroy()
            # ★ 就地改成「已编辑」，并刷新类型栏与列表
            hit["dst"] = new
            hit["kind"] = "已编辑"
            hit["detail"] = "已手工编辑"
            self.report_counts = Counter(
                h.get("kind", "") for _p, h in
                getattr(self, "report_hits", []))
            self._render_kind_bar()
            # 勾上「已编辑」，让用户马上看到改过的句子
            var = self.report_kind_vars.get("已编辑")
            if var is not None:
                var.set(True)
            self._render_report_rows()
            self.status_var.set("已保存：译文写入缓存，该句归入「已编辑」")
            self._append_log(f"[编辑] 已写入缓存：{os.path.basename(res['cache'])}"
                             f"（{len(new)} 字）\n")

        def cancel():
            win.destroy()

        bar = tk.Frame(body, bg=CARD)
        bar.pack(fill="x")
        GlassButton(bar, "取消", width=92, height=40, bg=CARD,
                    font=FONT_SMALL, command=cancel).pack(side="right")
        GlassButton(bar, "保存", width=120, height=40, primary=True,
                    bg=CARD, font=FONT_SMALL,
                    command=commit).pack(side="right", padx=8)

        win.bind("<Escape>", lambda _e: cancel())
        win.protocol("WM_DELETE_WINDOW", cancel)
        try:
            win.update_idletasks()
            x = self.root.winfo_rootx() + (
                self.root.winfo_width() - win.winfo_width()) // 2
            y = self.root.winfo_rooty() + 90
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
        win.grab_set()

    def _apply_conflicts(self):
        choices = [dict(v) for v in
                   getattr(self, "conflict_choices", {}).values()]
        if not choices:
            messagebox.showinfo("提示", "没有可应用的术语冲突")
            return
        paths = self._report_sources()
        src, tgt, model = (self.src_var.get(), self.tgt_var.get(),
                           self.model_var.get())
        if not paths:
            if not messagebox.askyesno(
                    "确认",
                    "没有选择文件，只会把选中的译文写入术语字典，"
                    "不会删除缓存或重翻。\n继续吗？"):
                return

        def work():
            res = commands.apply_term_conflicts(choices, paths, src, tgt, model)
            self.q.put(("term_conflict_done", res))
            return res

        self.show("log")
        self.run_async(work, label="解决术语冲突并重翻…",
                       done_label="术语冲突已处理")

    def _after_conflicts(self, res):
        """术语冲突应用完成：提示结果，稍后回到报告页自动刷新。"""
        r = res or {}
        messagebox.showinfo(
            "术语冲突已处理",
            f"写入术语字典：{r.get('saved', 0)} 条\n"
            + (f"修改术语原文：{r.get('renamed', 0)} 条\n"
               if r.get('renamed') else "")
            + f"重翻文件：{r.get('files', 0)} 个\n"
            f"删除缓存：{r.get('removed', 0)} 条")
        if getattr(self, "report_mode", "report") == "conflict":
            try:
                self._toggle_conflict_view()
            except Exception:
                pass
        self.root.after(500, self._refresh_after_conflicts)

    def _refresh_after_conflicts(self):
        """重翻结束后重新检查一次，让报告反映最新状态。"""
        if self.busy:
            self.root.after(500, self._refresh_after_conflicts)
            return
        try:
            self.show("report")
        except Exception:
            pass
        if self._report_sources():
            self._do_check()

    def _report_sources(self):
        """菜单 3 里选的是检查报告，这里换回真正的源文件。"""
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
        kinds = self._selected_kinds()
        if not kinds:
            messagebox.showwarning("提示", "请至少勾选一种要重翻的问题类型")
            return
        src, tgt, model = self.src_var.get(), self.tgt_var.get(), self.model_var.get()
        self.show("log")
        self.run_async(
            lambda: commands.retranslate_report_paths(paths, src, tgt, model,
                                                      kinds=kinds),
            label=f"重翻（{'、'.join(kinds)}）…",
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

        c1 = RoundCard(left, radius=16, pad=18, auto_height=True)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="语言与模型", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        row = tk.Frame(c1.body, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        self._labeled_combo(row, "源语言", self.src_var, LANG_VALUES, 12)
        self._labeled_combo(row, "目标语言", self.tgt_var, LANG_VALUES, 12)
        self._mode_row(c1.body)
        self._model_row(c1.body)

        # 术语列表（中下层）
        c2 = RoundCard(left, radius=16, pad=14)
        c2.grid(row=1, column=0, sticky="nsew")
        head = tk.Frame(c2.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="术语列表", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        self.term_stat = tk.Label(head, text="", bg=CARD, fg=C_KEY,
                                  font=FONT_BIG)
        self.term_stat.pack(side="right")
        attach_label_copy(self.term_stat, self, "统计")

        bar = tk.Frame(c2.body, bg=CARD)
        bar.pack(fill="x", pady=(8, 4))
        tk.Label(bar, text="搜索", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")
        self.term_search = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.term_search, width=12,
                        font=FONT)
        ent.pack(side="left", padx=8)
        ent.bind("<KeyRelease>", lambda e: self._filter_terms())
        self.term_filter = tk.StringVar(value="全部")
        for lab, val in (("全部", "全部"), ("自动提取", "AUTO"),
                         ("本次新增", "新增")):
            tk.Radiobutton(bar, text=lab, value=val,
                           variable=self.term_filter, bg=CARD, fg=TEXT,
                           activebackground=CARD, selectcolor="#FFFFFF",
                           font=FONT_SMALL,
                           command=self._filter_terms).pack(side="left", padx=4)
        GlassButton(bar, "重新载入", width=92, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._load_term_rows).pack(side="left", padx=8)

        # 全选 / 取消全选（表头开关，支持半选 indeterminate）
        selbar = tk.Frame(c2.body, bg=CARD)
        selbar.pack(fill="x", pady=(4, 0))
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
                                        fg=C_KEY, font=FONT_BIG)
        self.term_check_stat.pack(side="left", padx=10)

        wrap = tk.Frame(c2.body, bg=CARD)
        wrap.pack(fill="both", expand=True)
        cols = ("sel", "origin", "src", "dst")
        tree = ttk.Treeview(wrap, columns=cols, show="headings",
                            height=4, selectmode="extended")
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
        attach_tree_copy(tree, self)      # ★ 右键 / Ctrl+C 复制术语
        tree.bind("<Button-1>", self._on_term_tree_click, add="+")
        self.term_tree = tree

        # 提示单独一行，避免和按钮挤在同一行被挤出卡片
        hint_row = tk.Frame(c2.body, bg=CARD)
        hint_row.pack(fill="x", pady=(10, 0))
        tk.Label(hint_row,
                 text="改动会写入术语字典；双击译文可编辑；右键可复制",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL).pack(side="left")

        bottom = tk.Frame(c2.body, bg=CARD)
        bottom.pack(fill="x", pady=(6, 0))
        right_b = tk.Frame(bottom, bg=CARD)
        right_b.pack(side="right")
        GlassButton(right_b, "添加术语", width=88, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_term_add).pack(side="left", padx=3)
        GlassButton(right_b, "删除选中", width=88, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_term_delete_selected).pack(side="left",
                                                                padx=3)
        self.term_batch_btn = GlassButton(
            right_b, "批量删除", width=88, height=40, bg=CARD,
            font=FONT_SMALL, command=self._on_term_batch_delete)
        self.term_batch_btn.pack(side="left", padx=3)
        self.term_batch_btn.set_enabled(False)   # 未勾选任何术语时禁用
        GlassButton(right_b, "撤回", width=64, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_term_undo_delete).pack(side="left", padx=3)
        GlassButton(right_b, "应用术语", width=124, height=44, primary=True,
                    bg=CARD, command=self._do_apply_terms).pack(side="left",
                                                               padx=(8, 0))

        fp_holder = RoundCard(page, radius=16, pad=8, width=272)
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
            _cur, added, _rm, _modified, _ok = commands.analyze_terms()
        except Exception:
            added = None

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
        tk.Label(head, text="前缀字典", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        self.prefix_stat = tk.Label(head, text="", bg=CARD, fg=C_KEY,
                                    font=FONT_BIG)
        self.prefix_stat.pack(side="right")
        attach_label_copy(self.prefix_stat, self, "统计")

        bar = tk.Frame(c.body, bg=CARD)
        bar.pack(fill="x", pady=(8, 4))
        tk.Label(bar, text="搜索", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")
        self.prefix_search = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.prefix_search, width=14,
                        font=FONT)
        ent.pack(side="left", padx=8)
        ent.bind("<KeyRelease>", lambda e: self._filter_prefix())
        self.prefix_only_pending = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="只看未翻译", bg=CARD, fg=TEXT,
                       activebackground=CARD, selectcolor="#FFFFFF",
                       font=FONT_SMALL, variable=self.prefix_only_pending,
                       command=self._filter_prefix).pack(side="left", padx=8)
        GlassButton(bar, "重新载入", width=92, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._load_prefix_rows).pack(side="left", padx=8)
        GlassButton(bar, "打开字典文件", width=120, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self._open_path(PFD.DICT_FILE)).pack(
            side="left")

        wrap = tk.Frame(c.body, bg=CARD)
        wrap.pack(fill="both", expand=True)
        cols = ("src", "dst")
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=11)
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
        attach_tree_copy(tree, self)      # ★ 右键 / Ctrl+C 复制前缀
        self.prefix_tree = tree

        bottom = tk.Frame(c.body, bg=CARD)
        bottom.pack(fill="x", pady=(10, 0))
        tk.Label(bottom,
                 text="译文留空 = 沿用原文；双击译文可编辑；右键可复制",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL).pack(side="left")
        GlassButton(bottom, "应用前缀字典", width=160, height=44, primary=True,
                    bg=CARD, command=self._do_apply_prefix).pack(side="right")

        # ★ 「应用术语」：让前缀去匹配术语字典，命中就替换
        #   目前只替换 \tg[...] 里的内容（角色名），控制码参数不动
        bottom2 = tk.Frame(c.body, bg=CARD)
        bottom2.pack(fill="x", pady=(8, 0))
        tk.Label(bottom2,
                 text="应用术语：只替换 \\tg[...] 里的内容",
                 bg=CARD, fg=C_WARN, font=FONT_SMALL).pack(side="left")
        GlassButton(bottom2, "应用术语", width=140, height=44, bg=CARD,
                    font=FONT_BIG,
                    command=self._do_apply_prefix_terms).pack(side="right")

        fp_holder = RoundCard(page, radius=16, pad=8, width=272)
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
            txt = f"显示 {n} / 共 {total} / 待译 {pending}"
            if self.prefix_edits:
                txt += f" / 改 {len(self.prefix_edits)}"
            self.prefix_stat.config(text=txt)
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

    # ---------- 前缀字典 · 应用术语 ----------
    def _do_apply_prefix_terms(self):
        """
        让前缀去匹配术语字典：命中术语就把对应部分替换掉。
        ★ 当前只替换 \\tg[...] 里的内容（角色名），控制码参数保持不动。
        """
        try:
            # ★ 统一走 commands 的命令层：内部已含 PFD.reload_dict()
            changes, stats = commands.scan_prefix_terms()
        except Exception as e:
            messagebox.showerror("应用术语", f"扫描前缀字典失败：{e}")
            return

        if not changes:
            messagebox.showinfo(
                "应用术语",
                f"前缀字典共 {stats['total']} 条，"
                f"没有 \\tg[...] 里的文字命中术语，无需改动。")
            return

        preview = "\n".join(
            f"· {c['src']}\n    → {c['new']}" for c in changes[:8])
        term_txt = "、".join(
            f"{s}→{d}" for c in changes[:6] for s, d in c["terms"][:2])

        if not messagebox.askyesno(
                "应用术语",
                f"命中术语的前缀：{len(changes)} 条 / 共 {stats['total']} 条\n"
                f"涉及术语：{term_txt}\n\n"
                f"{preview}"
                + (f"\n  … 其余 {len(changes) - 8} 条省略"
                   if len(changes) > 8 else "")
                + "\n\n只替换 \\tg[...] 里的内容，确定应用？"):
            return

        paths = self.fp_prefix.ensure() or []

        def work():
            res = commands.apply_prefix_terms_paths(paths or None)
            self.q.put(("prefix_terms_done", res))
            return res

        self.show("log")
        self.run_async(work, label="前缀应用术语…",
                       done_label="前缀术语已应用")

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

        c1 = RoundCard(left, radius=16, pad=18, auto_height=True)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="模型与模式", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        self._mode_row(c1.body)
        self._model_row(c1.body)
        tk.Label(c1.body,
                 text="中文润色不需要选择语言：直接把缓存里的中文译文再润色一遍；"
                      "已润色过的条目会自动跳过，中断后重跑会接着来",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=560).pack(anchor="w", pady=(10, 0))

        c2 = RoundCard(left, radius=16, pad=18)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tk.Label(c2.body, text="说明", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        txt = ("· 逐条读取缓存中的中文译文，交给模型润色后覆盖原缓存\n"
               "· 保留全部占位符与控制码；占位符不全的条目会保留原译文\n"
               "· 短句、纯控制符句不参与润色\n"
               "· 断点续翻：进度存在 *_polish_cache.json，润色过的会跳过，"
               "中途改动的译文会自动重润（CLI 菜单 6 答 y 可清空进度全量重做）\n"
               "· 润色完成后自动重写 *_translated.txt，并生成 <输出名>_polished.txt "
               "明细报告（改动 / 未变 / 跳过三段逐条列出）")
        tk.Label(c2.body, text=txt, bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                 justify="left", wraplength=600).pack(anchor="w", pady=(10, 0))

        c3 = RoundCard(left, radius=16, pad=18)
        c3.configure(height=136)
        c3.pack_propagate(False)
        c3.grid(row=2, column=0, sticky="ew")
        GlassButton(c3.body, "开始润色", width=200, height=52, primary=True,
                    bg=CARD, command=self._do_polish).pack(anchor="w")
        tk.Label(c3.body, text="点击后跳转到日志页，实时查看进度",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL).pack(anchor="w",
                                                           pady=(8, 0))

        fp_holder = RoundCard(page, radius=16, pad=8, width=272)
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
    # 页面 7：换行重排 + 中文文本处理插件
    # ================================================================
    # 两种重排模式的参数（原上下两层已合并为一层，按区块类型切换）
    _REFLOW_SPECS = {
        "newline": ("[map*] 区块（\\n 换行）",
                    (("WRAP_CHARS_MIN", "换行下限", 15),
                     ("WRAP_CHARS_MAX", "换行上限", 18),
                     ("WRAP_MIN_GAP",   "换行最小间隔", 10))),
        "space":   ("其它区块（插空格）",
                    (("WRAP_SPACE_MIN",     "空格下限", 8),
                     ("WRAP_SPACE_MAX",     "空格上限", 10),
                     ("WRAP_SPACE_MIN_GAP", "空格最小间隔", 5))),
    }

    def _page_reflow(self):
        page = self.pages["reflow"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # ---- 换行重排（[map*] / 其它区块 合并为一层） ----
        # ★ 植入中文文本处理插件已移到菜单 1 的下层
        c1 = RoundCard(left, radius=16, pad=14)
        c1.grid(row=0, column=0, sticky="nsew")
        self._build_reflow_panel(c1.body)

        # ---- 右侧：待操作的译文 txt 文件 ----
        fp_holder = RoundCard(page, radius=16, pad=8, width=272)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        self.fp_reflow = self._make_file_panel(fp_holder, "source")

    def _build_reflow_panel(self, body):
        self.reflow_cfgs = {}
        self._reflow_cfg_frames = {}
        self._reflow_mode = "newline"
        self._reflow_data = {"newline": [], "space": []}

        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="换行重排", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        # 切换方式：选择 [map*] 或其它区块
        holder = tk.Frame(head, bg=CARD_BORDER)
        holder.pack(side="left", padx=12)
        self._reflow_tab_btns = {}
        for mode, text in (("newline", "[map*] 区块"),
                           ("space", "其它区块")):
            btn = tk.Label(holder, text=text, font=FONT_SMALL, padx=14,
                           pady=6, cursor="hand2")
            btn.pack(side="left", padx=(1, 1), pady=1)
            btn.bind("<Button-1>",
                     lambda _e, m=mode: self._reflow_switch(m))
            self._reflow_tab_btns[mode] = btn
        stat = tk.Label(head, text="", bg=CARD, fg=C_KEY, font=FONT_BIG)
        stat.pack(side="right")
        attach_label_copy(stat, self, "统计")
        self.reflow_stat = stat

        tk.Label(body,
                 text="只重排换行方式，不改动译文文字；"
                      "两种重排各用一套参数（会保存到设置）",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(4, 0))

        cfgrow = tk.Frame(body, bg=CARD)
        cfgrow.pack(fill="x", pady=(8, 8))
        self.reflow_cfg_holder = tk.Frame(cfgrow, bg=CARD)
        self.reflow_cfg_holder.pack(side="left")
        for mode, (_title, fields) in self._REFLOW_SPECS.items():
            fr = tk.Frame(self.reflow_cfg_holder, bg=CARD)
            varmap = {}
            for key, name, default in fields:
                tk.Label(fr, text=name, bg=CARD, fg=TEXT_DIM,
                         font=FONT_SMALL).pack(side="left", padx=(0, 4))
                var = tk.StringVar(value=str(getattr(config, key, default)))
                ttk.Entry(fr, textvariable=var, width=6,
                          font=FONT).pack(side="left", padx=(0, 14))
                varmap[key] = var
            self.reflow_cfgs[mode] = varmap
            self._reflow_cfg_frames[mode] = fr
        GlassButton(cfgrow, "刷新列表", width=100, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._load_reflow_blocks).pack(side="left")
        GlassButton(cfgrow, "开始重排", width=120, height=40, primary=True,
                    bg=CARD, command=self._do_reflow).pack(side="right")

        mid = tk.Frame(body, bg=CARD)
        mid.pack(fill="both", expand=True)

        blockfr = tk.Frame(mid, bg=CARD)
        blockfr.pack(side="left", fill="both")
        tree = ttk.Treeview(blockfr, columns=("block", "count"),
                            show="headings", height=3)
        tree.heading("block", text="区块")
        tree.heading("count", text="条数")
        tree.column("block", width=160, anchor="w")
        tree.column("count", width=56, anchor="center")
        sb = ttk.Scrollbar(blockfr, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        bind_tree_wheel(tree)
        attach_tree_copy(tree, self)      # ★ 右键 / Ctrl+C 复制区块列表
        tree.bind("<<TreeviewSelect>>", lambda _e: self._render_reflow_block())
        self.reflow_tree = tree

        right = tk.Frame(mid, bg=CARD)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(right, text="区块文本（原文 / 译文）", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(anchor="w")
        box = tk.Text(right, height=3, wrap="none", font=FONT_MONO,
                      bg="#FFFFFF", fg=TEXT, relief="flat",
                      highlightthickness=1, highlightbackground=CARD_BORDER)
        vsb = ttk.Scrollbar(right, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True)
        box.configure(state="disabled")
        attach_copy(box, [                # ★ 右键 / Ctrl+C 复制区块文本
            ("复制（选中，未选中则全部）", lambda b=box: self._text_pick(b)),
            ("复制全部", lambda b=box: self._text_all(b)),
        ], app=self)
        self.reflow_preview = box

    def _reflow_switch(self, mode):
        if mode == getattr(self, "_reflow_mode", "newline"):
            return
        self._reflow_mode = mode
        self._paint_reflow_tabs()
        self._load_reflow_blocks()

    def _paint_reflow_tabs(self):
        cur = getattr(self, "_reflow_mode", "newline")
        for mode, btn in getattr(self, "_reflow_tab_btns", {}).items():
            if not btn.winfo_exists():
                continue
            on = (mode == cur)
            btn.configure(bg=ACCENT if on else CARD,
                          fg="#FFFFFF" if on else TEXT_DIM,
                          font=(FONT_FAMILY, FONT_SMALL[1],
                                "bold" if on else "normal"))
        fr_cur = self._reflow_cfg_frames.get(cur)
        for fr in self._reflow_cfg_frames.values():
            if fr is not fr_cur:
                fr.pack_forget()
        if fr_cur is not None:
            fr_cur.pack(side="left")

    # ---------- 插件字体 ----------
    def _current_plugin_font(self):
        """返回当前生效的字体文件路径（未自选时为空 = 内置萝莉体）。"""
        p = getattr(self, "plugin_font", None) or ""
        if p and os.path.isfile(p):
            return p
        p = getattr(config.Runtime, "plugin_font", "") or ""
        if p and os.path.isfile(p):
            self.plugin_font = p
            return p
        return ""

    def _refresh_plugin_font(self):
        """刷新字体标签（文件名 + 字族名 + 来源）。"""
        lbl = getattr(self, "plugin_font_lbl", None)
        if lbl is None:
            return
        path = self._current_plugin_font()
        if not path:
            family = config.FONT_NAME or "Lolita"
            src = "内置萝莉体"
            name = os.path.basename(config.FONT_FILE)
        else:
            family = ""
            try:
                import plugin_tools as PT
                family = PT.ttf_family_name(path) or (config.FONT_NAME or "")
            except Exception:
                family = config.FONT_NAME or ""
            family = family or config.FONT_NAME or "Lolita"
            src = "自选"
            name = os.path.basename(path)
        self.plugin_font_lbl.config(
            text=f"{name}（族名「{family}」· {src}）"
                 + ("" if path else "\n不选则使用内置萝莉体"))

    def _pick_plugin_font(self):
        """自选字体文件（任意 TTF/OTF，纯本地操作，不影响其它文件）。"""
        init = (self._current_plugin_font() or config.FONT_FILE)
        path = filedialog.askopenfilename(
            title="选择字体（任意 TTF / OTF）",
            initialdir=os.path.dirname(os.path.abspath(init)),
            filetypes=[("字体文件", "*.ttf *.otf"), ("所有文件", "*.*")])
        if not path:
            return
        if not os.path.isfile(path):
            messagebox.showwarning("提示", "文件不存在，请选择有效的字体文件")
            return
        self.plugin_font = path
        config.Runtime.plugin_font = path
        try:
            config.Runtime.save()
        except Exception:
            pass
        self._refresh_plugin_font()

    def _do_plugin_inject(self):
        """加载中文文本处理插件并编译进 Data/PluginScripts.rxdata。"""
        d = self._intl_folder()
        if not d:
            return
        font_file = self._current_plugin_font() or None

        def work():
            res = commands.plugin_inject_paths([d], font_file=font_file)
            self.q.put(("plugin_done", res))
            return res

        self.show("log")
        self.run_async(work, label="加载插件并编译中…",
                       done_label="插件加载完成")

    def _do_plugin_restore(self):
        """还原插件植入（删插件目录 + 当初复制进 Fonts 的字体）。"""
        d = self._intl_folder()
        if not d:
            return
        import plugin_tools as PT
        if not messagebox.askyesno(
                "还原插件植入",
                f"将删除该游戏里的：\n"
                f"· Plugins/{PT.PLUGIN_DIR_NAME}/（本工具植入的那个）\n"
                f"· Fonts 里当初复制进去的字体（游戏自带字体不动）\n\n"
                f"游戏：{d}\n\n确定还原吗？"):
            return

        def work():
            res = commands.plugin_restore_paths([d])
            self.q.put(("plugin_restore_done", res))
            return res

        self.show("log")
        self.run_async(work, label="还原插件植入中…",
                       done_label="插件还原完成")

    def _load_reflow_blocks(self):
        """扫描已选文件，按当前模式（[map*] / 其它区块）填入列表。"""
        self._paint_reflow_tabs()
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

        self._render_reflow_list()
        self._render_reflow_block()

    def _render_reflow_list(self):
        mode = getattr(self, "_reflow_mode", "newline")
        tree = getattr(self, "reflow_tree", None)
        if tree is None or not tree.winfo_exists():
            return
        for iid in tree.get_children():
            tree.delete(iid)
        blocks = self._reflow_data.get(mode, [])
        total = 0
        for b in blocks:
            tree.insert("", "end",
                        values=(f"{b['file']} · {b['block']}", b["total"]))
            total += b["total"]
        self.reflow_stat.config(
            text=f"{len(blocks)} 个区块 / {total} 条译文")

    def _render_reflow_block(self):
        """把选中区块的原文 / 译文摘要填到右侧预览框。"""
        mode = getattr(self, "_reflow_mode", "newline")
        tree = getattr(self, "reflow_tree", None)
        box = getattr(self, "reflow_preview", None)
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
        c1.configure(height=140)
        c1.pack_propagate(False)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="语言选择（Excel 列名）", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        row = tk.Frame(c1.body, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        self.excel_src = tk.StringVar(value=config.EXCEL_SOURCE_LANG)
        self.excel_tgt = tk.StringVar(value=config.EXCEL_TARGET_LANG)
        self._labeled_combo(row, "源语言", self.excel_src, EXCEL_LANGS, 14)
        self._labeled_combo(row, "目标语言", self.excel_tgt, EXCEL_LANGS, 14)

        c2 = RoundCard(left, radius=16, pad=14)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        head = tk.Frame(c2.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="工作表", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        self.excel_path = tk.StringVar(
            value=config.EXCEL_FILE if os.path.exists(config.EXCEL_FILE) else "")
        GlassButton(head, "选择 Excel", width=116, height=34, bg=CARD,
                    font=FONT_SMALL, command=self._pick_excel).pack(side="left",
                                                                    padx=12)
        GlassButton(head, "全选", width=68, height=34, bg=CARD,
                    font=FONT_SMALL, command=self._sheets_all).pack(side="left")
        self.excel_lbl = tk.Label(head, text="", bg=CARD, fg=C_KEY,
                                  font=FONT_BIG)
        self.excel_lbl.pack(side="right")
        attach_label_copy(self.excel_lbl, self, "统计")

        outer, inner = make_scroll_area(c2.body, bg=CARD)
        outer.pack(fill="both", expand=True, pady=(8, 0))
        self.sheet_inner = inner

        c3 = RoundCard(left, radius=16, pad=18)
        c3.configure(height=136)
        c3.pack_propagate(False)
        c3.grid(row=2, column=0, sticky="ew")
        Brow = tk.Frame(c3.body, bg=CARD)
        Brow.pack(fill="x")
        GlassButton(Brow, "开始转换", width=200, height=52, primary=True,
                    bg=CARD, command=self._do_excel).pack(side="left")

        # ★ 已有术语字典时的写入方式：默认追加（不冲掉校对过的译法）
        self.excel_append = tk.BooleanVar(
            value=bool(getattr(config, "EXCEL_APPEND", True)))
        cb = tk.Checkbutton(
            Brow, text="已有术语字典时追加到末尾", variable=self.excel_append,
            bg=CARD, fg=TEXT, activebackground=CARD, selectcolor="#FFFFFF",
            font=FONT_SMALL, anchor="w",
            command=self._excel_append_changed)
        cb.pack(side="left", padx=14)
        attach_label_copy(cb, self, "Excel 写入方式")

        self.excel_hint = tk.Label(
            c3.body, text="", bg=CARD, fg=C_HINT, font=FONT_SMALL,
            anchor="w", justify="left")
        self.excel_hint.pack(fill="x", pady=(8, 0))
        self._refresh_excel_hint()

        right = tk.Frame(page, bg=BG_BASE, width=330)
        right.grid(row=0, column=1, sticky="nsew")
        right.pack_propagate(False)
        card = RoundCard(right, radius=16, pad=14)
        card.pack(fill="both", expand=True)
        tk.Label(card.body, text="提示", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(card.body,
                 text="· 表头需同时包含所选的两种语言列名\n"
                      "· 多个工作表会跨表去重\n"
                      "· 默认追加：已有术语只加不覆盖\n"
                      "· 新译法与旧译法不同会提示冲突\n"
                      "· 转换后可在菜单 4 里逐条校对译文\n"
                      "· 输出文件：term_dict.py",
                 bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(10, 0))

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
            cb = tk.Checkbutton(self.sheet_inner,
                                text=f"{name}   ({r} 行 × {c} 列)",
                                variable=v, bg=CARD, fg=TEXT,
                                activebackground=CARD, selectcolor="#FFFFFF",
                                anchor="w", font=FONT_SMALL)
            cb.pack(fill="x", padx=8)
            attach_label_copy(cb, self, "工作表名")

    def _sheets_all(self):
        for v in self.sheet_vars.values():
            v.set(True)

    def _excel_append_changed(self):
        """勾选框变化 → 记下偏好，方便下次打开还是这个选择。"""
        val = bool(self.excel_append.get())
        try:
            settings.set_value("EXCEL_APPEND", val)
            config.EXCEL_APPEND = val
        except Exception:
            pass
        self._refresh_excel_hint()

    def _refresh_excel_hint(self):
        """底部那行说明：让用户一眼看清这次会追加还是覆盖。"""
        if not hasattr(self, "excel_hint"):
            return
        n = 0
        try:
            import build_terms as BT
            n = len(BT.read_existing_terms(config.TERM_FILE))
        except Exception:
            n = 0
        if self.excel_append.get():
            if n:
                txt = (f"追加模式：已有 term_dict.py（{n} 条），"
                       f"新术语接在末尾，原译法不动")
            else:
                txt = "追加模式：还没有术语字典，本次会新建 term_dict.py"
        else:
            txt = (f"⚠ 覆盖模式：会清掉原有 {n} 条术语，"
                   f"只留本次 Excel 的内容" if n else
                   "覆盖模式：本次会重写 term_dict.py")
        self.excel_hint.configure(text=txt,
                                 fg=(C_HINT if self.excel_append.get()
                                     else C_WARN))

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

        mode = "append" if self.excel_append.get() else "overwrite"
        if mode == "overwrite":
            try:
                import build_terms as BT
                n = len(BT.read_existing_terms(config.TERM_FILE))
            except Exception:
                n = 0
            if n and not messagebox.askyesno(
                    "确认覆盖",
                    f"term_dict.py 里已有 {n} 条术语，覆盖后只剩本次 Excel 的"
                    f"内容（菜单 4 里校对过的译法也会丢）。\n\n确定要覆盖吗？"):
                return

        def work():
            res = commands.build_terms_from_excel(path, sheets or None, src,
                                                  tgt, mode=mode)
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
        Avatar(head, size=64, path=config.AVATAR_FILE).pack(side="left")
        box = tk.Frame(head, bg=CARD)
        box.pack(side="left", padx=14)
        tk.Label(box, text=config.AUTHOR_NAME, bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        lb1 = tk.Label(box, text=config.AUTHOR_GITHUB, bg=CARD, fg=ACCENT,
                       font=FONT_SMALL, cursor="hand2")
        lb1.pack(anchor="w")
        lb1.bind("<Button-1>", lambda e: webbrowser.open(config.AUTHOR_GITHUB))
        lb2 = tk.Label(box, text="bilibili：玛俐大小姐想让我告白", bg=CARD,
                       fg=ACCENT, font=FONT_SMALL, cursor="hand2")
        lb2.pack(anchor="w")
        lb2.bind("<Button-1>", lambda e: webbrowser.open(config.AUTHOR_BILIBILI))
        tk.Label(head, text=f"v{config.VERSION}", bg=CARD, fg=C_KEY,
                 font=FONT_B).pack(side="right", anchor="ne")

        card = RoundCard(page, radius=16, pad=14)
        card.grid(row=1, column=0, sticky="nsew")
        head2 = tk.Frame(card.body, bg=CARD)
        head2.pack(fill="x")
        tk.Label(head2, text="各项设置", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        GlassButton(head2, "检查更新", width=104, height=38, bg=CARD,
                    font=FONT_SMALL, command=self._check_update).pack(
            side="right")
        GlassButton(head2, "保存设置", width=112, height=38, primary=True,
                    bg=CARD, command=self._save_settings).pack(
            side="right", padx=8)
        GlassButton(head2, "重新载入", width=104, height=38, bg=CARD,
                    font=FONT_SMALL, command=self._load_settings).pack(
            side="right")

        # 翻译模式切换（切换后会自动同步参数并弹窗提示）
        self._mode_row(card.body)
        tk.Label(card.body,
                 text="云端模式请在下方填写 API 服务地址 / 密钥 / 模型名"
                      "（OpenAI 兼容接口）",
                 bg=CARD, fg=C_WARN, font=FONT_SMALL).pack(anchor="w",
                                                           pady=(4, 8))

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
            row.pack(fill="x", pady=5)
            tk.Label(row, text=name, bg=CARD, fg=TEXT, font=FONT_SMALL,
                     width=18, anchor="w").pack(side="left")

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

            tk.Label(row, text=desc or "", bg=CARD, fg=TEXT_DIM,
                     font=FONT_SMALL).pack(side="left", padx=12)
            # ★ 右键可复制该项的当前值（Ctrl+C 保持 Entry 原生行为）
            if typ != "bool":
                attach_copy(widget, [
                    ("复制该设置的当前值",
                     lambda w=widget: self._entry_value(w)),
                ], app=self, hotkey=False)
            self.setting_widgets[key] = (var_holder, typ, widget)

    def _entry_value(self, widget):
        """读输入框当前内容（有选中文本就只复制选中的）。"""
        try:
            sel = str(widget.selection_get())
            if sel.strip():
                return sel
        except Exception:
            pass
        try:
            return str(widget.get())
        except Exception:
            return ""

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
    # 页面 9：本地模型服务（Ollama / llama.cpp / LM Studio / 自定义）
    # ================================================================
    def _page_provider(self):
        page = self.pages["provider"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # ---------- 上层：切换服务提供商 ----------
        c1 = RoundCard(left, radius=16, pad=16, auto_height=True)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        # ★ 标题与「一句话说明」同行，省下一整行高度给下面的模型列表
        head1 = tk.Frame(c1.body, bg=CARD)
        head1.pack(fill="x")
        tk.Label(head1, text="服务提供商", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        self.pv_summary = tk.Label(head1, text="", bg=CARD, fg=C_HINT,
                                   font=FONT_SMALL, anchor="w")
        self.pv_summary.pack(side="left", padx=12)

        seg = tk.Frame(c1.body, bg=CARD)
        seg.pack(fill="x", pady=(8, 0))
        self._pv_provider_row(seg)

        url_row = tk.Frame(c1.body, bg=CARD)
        url_row.pack(fill="x", pady=(8, 0))
        tk.Label(url_row, text="服务地址", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")
        self.pv_url_var = tk.StringVar()
        ent = ttk.Entry(url_row, textvariable=self.pv_url_var, width=42,
                        font=FONT_SMALL)
        ent.pack(side="left", padx=8)
        attach_copy(ent, [("复制服务地址",
                           lambda w=ent: self._entry_value(w))],
                    app=self, hotkey=False)
        GlassButton(url_row, "保存", width=64, height=32, bg=CARD,
                    font=FONT_SMALL, command=self._pv_save_url).pack(side="left")
        GlassButton(url_row, "检测连接", width=92, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pv_probe).pack(side="left", padx=6)
        # ★ 一键把对应应用叫起来，省得用户自己去桌面找
        GlassButton(url_row, "尝试启动服务", width=124, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pv_launch).pack(side="left")

        self.pv_probe_lbl = tk.Label(c1.body, text="", bg=CARD, fg=C_HINT,
                                     font=FONT_SMALL, anchor="w",
                                     justify="left")
        self.pv_probe_lbl.pack(fill="x", pady=(6, 0))

        # ---------- 中层：模型列表 ----------
        c2 = RoundCard(left, radius=16, pad=16)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        head = tk.Frame(c2.body, bg=CARD)
        head.pack(fill="x")
        self.pv_mid_title = tk.Label(head, text="模型列表", bg=CARD,
                                     fg=C_TITLE, font=FONT_TITLE)
        self.pv_mid_title.pack(side="left")
        GlassButton(head, "刷新", width=72, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pv_refresh_mid).pack(side="right")
        self.pv_model_hint = tk.Label(head, text="", bg=CARD, fg=C_HINT,
                                      font=FONT_SMALL)
        self.pv_model_hint.pack(side="right", padx=10)
        # ★ llama.cpp 专用按钮放在标题行里，省下一整行高度给下面
        self.pv_llama_head = tk.Frame(head, bg=CARD)

        # ★ 中层有两套内容，按提供商切换：
        #   · norm  —— 通用：模型列表 + 详情 + 模型名
        #   · llama —— llama.cpp 专用：选程序目录 / 扫本地 GGUF / 选模型
        self.pv_mid_norm = tk.Frame(c2.body, bg=CARD)
        self.pv_mid_llama = tk.Frame(c2.body, bg=CARD)

        wrap = tk.Frame(self.pv_mid_norm, bg=CARD)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        cols = (("name", "模型名称", 250), ("params", "参数量", 70),
                ("ctx", "上下文", 80), ("size", "体积", 80),
                ("quant", "量化", 90), ("status", "状态", 80))
        # ★ height 只是「最小需求」，卡片有多余空间时列表会自动长高
        tree = ttk.Treeview(wrap, columns=[c[0] for c in cols],
                            show="headings", height=3)
        for cid, text, w in cols:
            tree.heading(cid, text=text)
            tree.column(cid, width=w, anchor="w", stretch=(cid == "name"))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        bind_tree_wheel(tree)
        attach_tree_copy(tree, self)
        tree.bind("<<TreeviewSelect>>", self._pv_on_select)
        self.pv_tree = tree

        self.pv_detail = tk.Text(self.pv_mid_norm, height=3, wrap="word",
                                 font=FONT_SMALL, bg="#FFFFFF", fg=TEXT,
                                 relief="solid", bd=1, highlightthickness=1,
                                 highlightbackground=CARD_BORDER, spacing1=2)
        self.pv_detail.pack(fill="x", pady=(8, 0))
        self.pv_detail.configure(state="disabled")
        attach_copy(self.pv_detail,
                    [("复制模型信息",
                      lambda: self._text_pick(self.pv_detail))], app=self)

        # 选中的模型名 + 设为当前（放在列表下面，跟模型走）
        mrow = tk.Frame(self.pv_mid_norm, bg=CARD)
        mrow.pack(fill="x", pady=(8, 0))
        tk.Label(mrow, text="模型名", bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                 width=8, anchor="w").pack(side="left")
        self.pv_model_var = tk.StringVar()
        ttk.Entry(mrow, textvariable=self.pv_model_var, width=34,
                  font=FONT_SMALL).pack(side="left", padx=8)
        GlassButton(mrow, "设为当前模型", width=124, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pv_use_model).pack(side="left", padx=6)

        self._pv_build_llama_mid(self.pv_mid_llama)

        # ---------- 下层：参数设置与部署 ----------
        c3 = RoundCard(left, radius=16, pad=16, auto_height=True)
        c3.grid(row=2, column=0, sticky="ew")
        tk.Label(c3.body, text="参数设置与部署", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")

        self._pv_param_row(c3.body, [
            ("上下文", "NUM_CTX", 8), ("最大生成", "NUM_PREDICT", 8),
            ("温度", "TEMPERATURE", 6), ("top_p", "TOP_P", 6),
        ])

        trow = tk.Frame(c3.body, bg=CARD)
        trow.pack(fill="x", pady=4)
        self.pv_think_var = tk.BooleanVar()
        self.pv_think_cb = tk.Checkbutton(
            trow, text="推理模式 think", bg=CARD, activebackground=CARD,
            selectcolor="#FFFFFF", variable=self.pv_think_var,
            font=FONT_SMALL, fg=TEXT)
        self.pv_think_cb.pack(side="left")
        # ★ OpenAI 兼容端没有 think 参数，改用 reasoning_effort=none 关推理
        self.pv_noreason_var = tk.BooleanVar()
        self.pv_noreason_cb = tk.Checkbutton(
            trow, text="关推理(API端)", bg=CARD, activebackground=CARD,
            selectcolor="#FFFFFF", variable=self.pv_noreason_var,
            font=FONT_SMALL, fg=TEXT)
        self.pv_noreason_cb.pack(side="left", padx=(14, 0))
        for text, attr, width in (("驻留", "pv_keep_var", 8),
                                  ("每批条数", "pv_batch_var", 6)):
            tk.Label(trow, text=text, bg=CARD, fg=TEXT_DIM,
                     font=FONT_SMALL).pack(side="left", padx=(16, 4))
            var = tk.StringVar()
            setattr(self, attr, var)
            self.pv_param_vars["KEEP_ALIVE" if text == "驻留" else "BATCH_SIZE"] = var
            ttk.Entry(trow, textvariable=var, width=width,
                      font=FONT_SMALL).pack(side="left")

        # 分批 / 重试 / 超时（本地小模型最容易卡在这几个值上）
        self._pv_param_row(c3.body, [
            ("单批字符", "MAX_BATCH_CHARS", 7),
            ("术语上限", "MAX_TERMS_IN_PROMPT", 6),
            ("整批重试", "BATCH_RETRIES", 5),
            ("超时(秒)", "TIMEOUT", 7),
        ])

        self.pv_param_hint = tk.Label(c3.body, text="", bg=CARD, fg=C_HINT,
                                      font=FONT_SMALL, anchor="w",
                                      justify="left")
        self.pv_param_hint.pack(fill="x", pady=(2, 0))

        brow = tk.Frame(c3.body, bg=CARD)
        brow.pack(fill="x", pady=(10, 0))
        GlassButton(brow, "一键部署模型", width=150, height=42, primary=True,
                    bg=CARD, command=self._pv_deploy).pack(side="left")
        GlassButton(brow, "保存参数", width=104, height=42, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pv_save_params).pack(side="left", padx=8)
        GlassButton(brow, "打开官网", width=104, height=42, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pv_open_home).pack(side="left")

        # ---------- 右侧：切换适配 ----------
        right = RoundCard(page, radius=16, pad=12, width=272)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        tk.Label(right.body, text="切换适配", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        # ★ 侧栏只有 242px 宽，长标题必须允许换行，否则会被裁掉
        self.pv_from_to = tk.Label(right.body, text="", bg=CARD, fg=C_KEY,
                                   font=FONT_SMALL, anchor="w",
                                   justify="left", wraplength=238)
        self.pv_from_to.pack(fill="x", pady=(4, 6))

        outer, inner = make_scroll_area(right.body, bg=CARD)
        outer.pack(fill="both", expand=True)
        self.pv_adapt_text = tk.Text(inner, wrap="word", font=FONT_SMALL,
                                     bg=CARD, fg=TEXT, relief="flat", bd=0,
                                     highlightthickness=0, spacing1=3,
                                     spacing3=3)
        self.pv_adapt_text.pack(fill="both", expand=True)
        self.pv_adapt_text.tag_config(
            "h", foreground=ACCENT_DEEP,
            font=(FONT_FAMILY, FONT_SMALL[1], "bold"))
        self.pv_adapt_text.tag_config("warn", foreground=C_WARN)
        self.pv_adapt_text.tag_config("ok", foreground=C_OK)
        self.pv_adapt_text.configure(state="disabled")
        attach_copy(self.pv_adapt_text,
                    [("复制适配清单",
                      lambda: self._text_all(self.pv_adapt_text))], app=self)

        b1 = tk.Frame(right.body, bg=CARD)
        b1.pack(fill="x", pady=(8, 0))
        GlassButton(b1, "一键适配", width=200, height=40, primary=True,
                    bg=CARD, command=self._pv_adapt_apply).pack(anchor="w")
        b2 = tk.Frame(right.body, bg=CARD)
        b2.pack(fill="x", pady=(6, 0))
        GlassButton(b2, "复制清单", width=96, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pv_copy_adapt).pack(side="left")
        GlassButton(b2, "打开官网", width=96, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pv_open_home).pack(side="left", padx=6)

        # ★ LM Studio 专用：右下角「操作指南」，按 LM1/LM2/LM3 顺序看图
        self.pv_guide_btn = GlassButton(
            right.body, "操作指南", width=120, height=38, bg=CARD,
            font=FONT_SMALL, command=self._pv_open_guide)

        self._pv_render_adapt()

    # ---------- 中层：llama.cpp 专用（选目录 / 扫模型 / 选模型） ----------
    def _pv_build_llama_mid(self, parent):
        """
        llama.cpp 专用中层：定程序目录 / 扫 GGUF / 选模型 / 预览启动命令。

        ★ 这一坨要塞进高度固定的中层卡片里，所以刻意压扁：
          「自动查找」按钮挂到卡片标题行、状态与说明合成一个 Laber 两行、
          启动命令用单行只读 Entry（要复制有右键菜单）。
        """
        # ---- 标题行右侧：自动查找 ----
        GlassButton(self.pv_llama_head, "自动查找程序/模型目录", width=196,
                    height=32, bg=CARD, font=FONT_SMALL,
                    command=self._pv_autodetect).pack(side="left", padx=6)

        # ---- 说明 + 状态（两行，省掉单独的状态行）----
        self.pv_llama_exe_lbl = tk.Label(
            parent, text=PV_LLAMA_HINT,
            bg=CARD, fg=C_HINT, font=FONT_SMALL, anchor="w", justify="left",
            wraplength=846)
        self.pv_llama_exe_lbl.pack(fill="x", pady=(4, 0))

        # ---- 两个目录 ----
        for attr, text, key, extra in (
                ("pv_llama_dir_var", "llama.cpp 目录", "LLAMACPP_DIR", False),
                ("pv_modeldir_var", "GGUF 模型目录", "LLAMACPP_MODEL_DIR", True)):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=(4, 0))
            tk.Label(row, text=text, bg=CARD, fg=TEXT_DIM,
                     font=FONT_SMALL, width=13, anchor="w").pack(side="left")
            var = tk.StringVar()
            setattr(self, attr, var)
            ent = ttk.Entry(row, textvariable=var, width=50,
                            font=FONT_SMALL)
            ent.pack(side="left", padx=8)
            attach_copy(ent, [("复制路径",
                               lambda w=ent: self._entry_value(w))],
                        app=self, hotkey=False)
            GlassButton(row, "选择", width=64, height=30, bg=CARD,
                        font=FONT_SMALL,
                        command=lambda v=var, k=key, r=extra:
                        self._pv_pick_dir(v, k, r)).pack(side="left")
            if extra:
                GlassButton(row, "扫描", width=64, height=30, bg=CARD,
                            font=FONT_SMALL,
                            command=self._pv_scan_gguf).pack(side="left",
                                                             padx=6)

        # ---- 选模型 ----
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text="选择模型", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL, width=13, anchor="w").pack(side="left")
        self.pv_gguf_var = tk.StringVar()
        self.pv_gguf_cb = ttk.Combobox(row, textvariable=self.pv_gguf_var,
                                       values=[], width=50,
                                       state="readonly", font=FONT_SMALL)
        self.pv_gguf_cb.pack(side="left", padx=8)
        self.pv_gguf_cb.bind("<<ComboboxSelected>>", self._pv_pick_gguf)
        self.pv_gguf_lbl = tk.Label(row, text="", bg=CARD, fg=C_HINT,
                                    font=FONT_SMALL)
        self.pv_gguf_lbl.pack(side="left", padx=6)

        # ---- 启动命令预览（单行只读 Entry，右键可复制全文）----
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text="启动命令", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL, width=13, anchor="w").pack(side="left")
        self.pv_cmd_var = tk.StringVar()
        self.pv_cmd_ent = ttk.Entry(row, textvariable=self.pv_cmd_var,
                                    font=FONT_MONO, state="readonly")
        self.pv_cmd_ent.pack(side="left", fill="x", expand=True, padx=8)
        attach_copy(self.pv_cmd_ent,
                    [("复制启动命令",
                      lambda: self._entry_value(self.pv_cmd_ent))], app=self)

        bar = tk.Frame(parent, bg=CARD)
        bar.pack(fill="x", pady=(4, 0))
        GlassButton(bar, "用这个模型启动服务", width=180, height=32,
                    primary=True, bg=CARD,
                    command=self._pv_launch).pack(side="left")
        GlassButton(bar, "重新扫描模型", width=124, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pv_scan_gguf).pack(side="left", padx=8)

    def _pv_pick_dir(self, var, key, rescan=False):
        cur = var.get().strip()
        initial = cur if os.path.isdir(cur) else config.BASE_DIR
        d = filedialog.askdirectory(title="选择文件夹", initialdir=initial)
        if not d:
            return
        d = os.path.normpath(d)
        var.set(d)
        ok, msg = settings.set_value(key, d)
        if not ok:
            messagebox.showwarning("保存失败", msg)
            return
        self.status_var.set(f"已设置：{d}")
        if rescan:
            self._pv_scan_gguf()
        else:
            self._pv_refresh_llama()

    def _pv_save_llama_dirs(self):
        """把界面上填的两个目录写回配置（用户手打路径时也要生效）。"""
        for var, key in ((self.pv_llama_dir_var, "LLAMACPP_DIR"),
                         (self.pv_modeldir_var, "LLAMACPP_MODEL_DIR")):
            v = var.get().strip()
            if v and v != str(getattr(config, key, "") or ""):
                settings.set_value(key, v)

    def _pv_scan_gguf(self):
        self._pv_save_llama_dirs()
        models = PV.scan_gguf()
        self._pv_gguf_models = models
        vals = [m["rel"] for m in models]
        self.pv_gguf_cb.configure(values=vals or ["（没扫到 .gguf 文件）"])

        cur = str(getattr(config, "LLAMACPP_MODEL_PATH", "") or "")
        hit = next((m for m in models if m["path"] == cur), None)
        if hit:
            self.pv_gguf_var.set(hit["rel"])
        elif models:
            self.pv_gguf_var.set(models[0]["rel"])
            self._pv_pick_gguf()          # 默认先选第一个
        else:
            self.pv_gguf_var.set("")
        self.pv_gguf_lbl.configure(
            text=(f"共 {len(models)} 个" if models else "没扫到模型"))
        self._pv_refresh_cmd()

    def _pv_pick_gguf(self, _e=None):
        rel = self.pv_gguf_var.get().strip()
        m = next((x for x in getattr(self, "_pv_gguf_models", [])
                  if x["rel"] == rel), None)
        if not m:
            return
        settings.set_value("LLAMACPP_MODEL_PATH", m["path"])
        # llama.cpp 用 -a 指定的别名做模型名，这里同步成同名
        alias = os.path.splitext(m["name"])[0][:40]
        settings.set_value("API_MODEL", alias)
        self.pv_model_var.set(alias)
        self.pv_gguf_lbl.configure(text=m["size_text"] or "")
        self._pv_refresh_cmd()

    def _pv_refresh_cmd(self):
        argv, msg = PV.llamacpp_args()
        if argv:
            self.pv_cmd_var.set(" ".join(argv))
        else:
            self.pv_cmd_var.set(str(msg).replace("\n", " "))

    def _pv_refresh_llama(self):
        self.pv_llama_dir_var.set(
            str(getattr(config, "LLAMACPP_DIR", "") or ""))
        self.pv_modeldir_var.set(
            str(getattr(config, "LLAMACPP_MODEL_DIR", "") or ""))
        exe = PV.find_llama_server()
        status = ("✔ 已找到 llama-server.exe" if exe else
                  "✘ 没找到 llama-server.exe，点右上角「自动查找」或手动选目录")
        self.pv_llama_exe_lbl.configure(
            text=PV_LLAMA_HINT + "\n" + status,
            fg=(C_HINT if exe else C_WARN))
        self._pv_scan_gguf()

    def _pv_autodetect(self):
        """扫一遍磁盘根目录，把 llama.cpp 目录和模型目录自动填上。"""
        self.pv_llama_exe_lbl.configure(
            text=PV_LLAMA_HINT + "\n正在查找…", fg=C_HINT)

        def work():
            d1 = PV.autodetect_llama_dir()
            d2 = PV.autodetect_model_dir()
            self.q.put(("pv_autodet", (d1, d2)))
        threading.Thread(target=work, daemon=True).start()

    def _pv_apply_autodetect(self, d1, d2):
        msg = []
        if d1:
            self.pv_llama_dir_var.set(d1)
            settings.set_value("LLAMACPP_DIR", d1)
            msg.append("程序目录：" + d1)
        else:
            msg.append("程序目录：没找到（请手动选）")
        if d2:
            self.pv_modeldir_var.set(d2)
            settings.set_value("LLAMACPP_MODEL_DIR", d2)
            msg.append("模型目录：" + d2)
        else:
            msg.append("模型目录：没找到（请手动选）")
        self._pv_refresh_llama()
        self.status_var.set("；".join(msg)[:110])
        self._append_log("[llama.cpp 自动查找] " + "；".join(msg) + "\n")

    def _pv_refresh_mid(self):
        if PV.current() == "llamacpp":
            self._pv_scan_gguf()
        else:
            self._pv_refresh_models()

    # ---------- 「尝试启动服务」 ----------
    def _pv_launch(self):
        key = PV.current()
        argv, msg = PV.launch_command(key)
        if not argv:
            messagebox.showinfo("无法自动启动", msg)
            return
        if not messagebox.askyesno(
                "尝试启动服务",
                "即将执行：\n" + " ".join(argv) + "\n\n" + msg +
                "\n\n启动后要等几秒才会就绪，届时状态栏会自动更新。"
                "\n\n是否继续？"):
            return
        ok, m = PV.launch_app(key)
        self.status_var.set(("已启动 " if ok else "启动失败 ") +
                            PV.label_of(key))
        self._append_log("$ " + " ".join(argv) + "\n" + m + "\n")
        if ok:
            # 起来要时间，隔几秒自动复查几次
            for delay in (4000, 8000, 15000, 25000):
                self.root.after(delay, self._pv_probe)

    # ---------- 操作指南（LM Studio） ----------
    @staticmethod
    def _guide_sort_key(name):
        """按文件名里的数字排序：LM1 < LM2 < LM3 < LM10。"""
        m = re.search(r"(\d+)", name)
        return (int(m.group(1)) if m else 999, name.lower())

    def _guide_images(self, folder):
        exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif")
        return sorted((f for f in os.listdir(folder)
                       if f.lower().endswith(exts)), key=self._guide_sort_key)

    def _guide_stable_dir(self, folder, imgs):
        """
        打包运行时指南躺在 _MEIPASS 里，exe 一退整目录就被删，
        拼出来的 HTML 图片会全部裂掉。所以复制一份到 %TEMP% 的稳定目录。
        """
        mei = getattr(sys, "_MEIPASS", None)
        if not mei:
            return folder
        try:
            inside = os.path.abspath(folder).lower().startswith(
                os.path.abspath(mei).lower())
        except Exception:
            inside = False
        if not inside:
            return folder          # 用户放在 exe 旁边的，直接用原目录

        dst = os.path.join(tempfile.gettempdir(), "pkmn_translator_guide")
        try:
            os.makedirs(dst, exist_ok=True)
            for f in imgs:
                shutil.copyfile(os.path.join(folder, f),
                                os.path.join(dst, f))
            return dst
        except Exception as e:
            self._append_log(f"[指南] 复制到临时目录失败，直接用解包目录：{e}")
            return folder

    def _pv_open_guide(self):
        folder = getattr(config, "GUIDE_DIR", "") or os.path.join(
            config.BASE_DIR, "LM操作指南")
        if not os.path.isdir(folder):
            messagebox.showinfo(
                "没有找到指南",
                "没找到「LM操作指南」文件夹。\n\n"
                "· 打包版：正常情况下它已经打进 exe 内部；\n"
                "  若确实缺图，把文件夹放到程序目录下也能生效：\n"
                f"{config.BASE_DIR}")
            return

        try:
            imgs = self._guide_images(folder)
        except Exception as e:
            messagebox.showinfo("读取失败", f"{folder}\n{e}")
            return
        if not imgs:
            messagebox.showinfo("没有图片",
                                f"{folder}\n下面没有找到图片文件。")
            return

        # ★ 图片要放到「exe 退出后依然存在」的目录，否则 HTML 会裂图
        view_dir = self._guide_stable_dir(folder, imgs)

        # 拼一个本地 HTML 按 1/2/3 顺序展示，比连开三个图片窗口好用
        try:
            import urllib.parse as _up
            parts = []
            for f in imgs:
                url = "file:///" + _up.quote(
                    os.path.join(view_dir, f).replace("\\", "/"), safe="/:")
                parts.append('<figure><figcaption>' + f + '</figcaption>'
                             '<img src="' + url + '"></figure>')
            order = "→".join(str(i) for i in range(1, len(imgs) + 1))
            # ★ 别用 % 或 format 拼：CSS 里的 100% 会和格式化占位符打架
            html = ("<!doctype html><meta charset='utf-8'>"
                    "<title>LM Studio 操作指南</title>"
                    "<style>body{margin:0;padding:18px;background:#eef3fa;"
                    "font-family:'Microsoft YaHei',sans-serif;"
                    "text-align:center}"
                    "h1{font-size:20px;color:#0F4C86;margin:6px 0 18px}"
                    "figure{margin:0 0 26px}"
                    "figcaption{font-size:14px;color:#3C5064;"
                    "margin-bottom:6px}"
                    "img{max-width:100%;border-radius:10px;"
                    "box-shadow:0 4px 16px rgba(0,0,0,.15)}</style>"
                    "<h1>LM Studio 操作指南（按 " + order + " 顺序）</h1>"
                    + "".join(parts))
            path = os.path.join(tempfile.gettempdir(),
                                "LM操作指南_view.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            webbrowser.open("file:///" + path.replace("\\", "/"))
            self.status_var.set(f"已打开操作指南（共 {len(imgs)} 张）")
            return
        except Exception as e:
            self._append_log(f"[指南] HTML 方式失败，改为逐个打开：{e}")

        # 兜底：按顺序逐个打开
        for f in imgs:
            self._open_path(os.path.join(view_dir, f))
        self.status_var.set(f"已打开操作指南（共 {len(imgs)} 张）")

    def _pv_provider_row(self, parent):
        """提供商分段按钮组。"""
        holder = tk.Frame(parent, bg=CARD_BORDER)
        holder.pack(side="left")
        group = {}
        for key in PV.keys():
            btn = tk.Label(holder, text=PV.label_of(key), font=FONT_SMALL,
                           padx=14, pady=7, cursor="hand2")
            btn.pack(side="left", padx=1, pady=1)
            btn.bind("<Button-1>", lambda _e, k=key: self._pv_switch(k))
            group[key] = btn
        self._pv_btn_groups.append(group)
        self._pv_paint_btns()
        return holder

    def _pv_paint_btns(self):
        cur = PV.current()
        for group in self._pv_btn_groups:
            for key, btn in group.items():
                if not btn.winfo_exists():
                    continue
                on = (key == cur)
                btn.configure(bg=ACCENT if on else CARD,
                              fg="#FFFFFF" if on else TEXT_DIM,
                              font=(FONT_FAMILY, FONT_SMALL[1],
                                    "bold" if on else "normal"))

    def _pv_param_row(self, parent, fields):
        """一行「标签 + 输入框」，变量名登记进 self.pv_param_vars。"""
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=4)
        for i, (text, key, width) in enumerate(fields):
            tk.Label(row, text=text, bg=CARD, fg=TEXT_DIM,
                     font=FONT_SMALL).pack(side="left",
                                           padx=(0 if i == 0 else 14, 4))
            var = tk.StringVar()
            ttk.Entry(row, textvariable=var, width=width,
                      font=FONT_SMALL).pack(side="left")
            self.pv_param_vars[key] = var
        return row

    @staticmethod
    def _pv_fmt_ctx(v):
        try:
            return f"{int(v):,}"
        except Exception:
            return str(v) if v else "-"

    def _pv_refresh(self):
        """把 config 里的当前值刷进页面。"""
        key = PV.current()
        p = PV.get(key)

        self._pv_paint_btns()
        self.pv_url_var.set(PV.stored_url(key))
        self.pv_model_var.set(PV.current_model(key))
        self.pv_summary.configure(text=p["summary"])

        for k, var in self.pv_param_vars.items():
            var.set(str(getattr(config, k, "")))
        self.pv_think_var.set(bool(getattr(config, "THINK", False)))
        self.pv_noreason_var.set(bool(getattr(config, "NO_REASONING", True)))

        # 只有 Ollama 认 think / keep_alive
        self.pv_think_cb.configure(
            state=("normal" if p["think"] else "disabled"))
        self.pv_param_hint.configure(
            text=("think / 驻留随每次请求发给 Ollama；取消勾选即关闭推理。"
                  if p["think"] else
                  f"{p['label']} 不认 think 与驻留，改用「关推理(API端)」"
                  f"（发 reasoning_effort=none）；上下文请在服务端设。"))
        self.pv_probe_lbl.configure(
            text="实际调用：" + PV.endpoints_text(key), fg=C_HINT)

        # ★ 中层：llama.cpp 换成「选目录 / 扫模型 / 选模型」，其余用通用列表
        if key == "llamacpp":
            self.pv_mid_norm.pack_forget()
            self.pv_mid_llama.pack(fill="both", expand=True)
            self.pv_mid_title.configure(text="模型地址与选择")
            self.pv_model_hint.configure(text="")
            self.pv_llama_head.pack(side="right")     # 标题行右侧的「自动查找」
        else:
            self.pv_mid_llama.pack_forget()
            self.pv_llama_head.pack_forget()
            self.pv_mid_norm.pack(fill="both", expand=True)
            self.pv_mid_title.configure(text="模型列表")

        # ★ LM Studio 才有操作指南按钮
        if key == "lmstudio":
            self.pv_guide_btn.pack(side="right", pady=(6, 0))
        else:
            self.pv_guide_btn.pack_forget()

        self._pv_render_adapt()
        if key == "llamacpp":
            self._pv_refresh_llama()
        else:
            self._pv_refresh_models()
        # ★ 顺手探一次，切完立刻能看到新服务通不通
        self._pv_probe()

    def _pv_switch(self, key):
        key = PV.normalize(key)
        old = PV.current()
        if key == old:
            return

        PV.set_prev_provider(old)
        changes = PV.apply_provider(key)

        # 同步菜单 2 / 菜单 9 上的模式与模型显示
        self._paint_mode_row()
        self.model_var.set(PV.current_model(key))
        self._detect_models_async()
        self._pv_refresh()

        _auto, manual = PV.adaptation(old, key)
        lines = [f"· {n}：{o}  →  {v}" for n, o, v in changes]
        msg = (f"已切换到 {PV.label_of(key)}\n\n已自动调整：\n"
               + ("\n".join(lines) if lines else "（无需调整）"))
        if manual:
            msg += ("\n\n还需要你手动处理（右侧「切换适配」栏可复制）：\n"
                    + "\n".join(f"· {it['title']}" for it in manual))
        messagebox.showinfo("已切换服务提供商", msg)

    def _pv_save_url(self):
        key = PV.current()
        url = self.pv_url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "服务地址不能为空")
            return
        ok, msg = PV.set_url(url, key)
        if not ok:
            messagebox.showwarning("保存失败", msg)
            return
        # 非 Ollama 走 OpenAI 兼容，地址要同步给 API_BASE_URL
        if PV.get(key)["protocol"] != "ollama":
            settings.set_value("API_BASE_URL", PV.base_url(key))
        self.status_var.set(f"服务地址已更新：{url}")
        self._pv_refresh()     # 内含重新探测


    def _pv_probe(self):
        key = PV.current()
        self.pv_probe_lbl.configure(
            text=f"正在检测 {PV.label_of(key)} …", fg=C_HINT)

        def work():
            self.q.put(("pv_probe", PV.probe(key)))
        threading.Thread(target=work, daemon=True).start()

    def _pv_refresh_models(self):
        key = PV.current()
        self.pv_model_hint.configure(text="正在读取模型列表…")

        def work():
            rows = PV.all_models(key)
            probed = PV.probe(key, timeout=2)[0]
            self.q.put(("pv_models", (key, rows, probed)))
        threading.Thread(target=work, daemon=True).start()

    def _pv_apply_models(self, key, rows, probed=True):
        if key != PV.current() or not self.pv_tree.winfo_exists():
            return
        self._pv_models = rows or []
        tree = self.pv_tree
        tree.delete(*tree.get_children())

        cur = str(PV.current_model(key) or "")
        hit = None
        for r in self._pv_models:
            name = r.get("name", "")
            iid = tree.insert("", "end", values=(
                name,
                r.get("params", "") or "-",
                self._pv_fmt_ctx(r.get("ctx", "")),
                r.get("size", "") or "-",
                r.get("quant", "") or "-",
                "已安装" if r.get("installed") else "可拉取",
            ))
            if str(name) == cur:
                hit = iid

        if hit is not None:
            tree.selection_set(hit)
            tree.see(hit)
            row = next((r for r in self._pv_models
                        if str(r.get("name", "")) == cur), None)
            if row:
                self._pv_show_detail(PV.info_from_row(row, key))

        n_inst = sum(1 for r in self._pv_models if r.get("installed"))
        if not probed:
            self.pv_model_hint.configure(
                text=f"服务未响应，下面是推荐目录（{len(self._pv_models)} 个）")
        elif n_inst:
            self.pv_model_hint.configure(
                text=f"服务在线：已装 {n_inst} 个 / 共 {len(self._pv_models)} 个")
        else:
            self.pv_model_hint.configure(
                text="服务在线但还没加载模型，下面是推荐目录")

    def _pv_show_detail(self, info):
        box = self.pv_detail
        box.configure(state="normal")
        box.delete("1.0", "end")
        name = info.get("name", "")
        box.insert("end", f"{info.get('display') or name}\n")
        box.insert("end",
                   f"参数量 {info.get('params') or '—'}　"
                   f"上下文 {self._pv_fmt_ctx(info.get('ctx', ''))}　"
                   f"体积 {info.get('size') or '—'}　"
                   f"量化 {info.get('quant') or '—'}　"
                   f"{'已安装' if info.get('installed') else '未部署'}\n")
        if info.get("level"):
            box.insert("end", f"定位：{info['level']}\n")
        if info.get("note"):
            box.insert("end", info["note"] + "\n")
        if info.get("think"):
            box.insert("end",
                       "注意：会输出思考过程，Ollama 下用 think=False 关掉。\n")
        box.configure(state="disabled")

    def _pv_on_select(self, _e=None):
        sel = self.pv_tree.selection()
        if not sel:
            return
        vals = self.pv_tree.item(sel[0], "values")
        if not vals:
            return
        name = str(vals[0])
        self.pv_model_var.set(name)
        # ★ 直接用列表里已有的那行，不再为每次点击打一次本地服务
        row = next((r for r in self._pv_models
                    if str(r.get("name", "")) == name), {"name": name})
        self._pv_show_detail(PV.info_from_row(row, PV.current()))

    def _pv_use_model(self):
        name = self.pv_model_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "模型名不能为空")
            return
        if PV.set_current_model(name, PV.current()):
            self.model_var.set(name)
            self.status_var.set(f"已设为当前模型：{name}")
            self._pv_refresh_models()
        else:
            messagebox.showwarning("失败", f"写入模型名失败：{name}")

    def _pv_save_params(self):
        fail = []
        for key, var in self.pv_param_vars.items():
            ok, msg, _v = settings.set_value(key, var.get())
            if not ok:
                fail.append(f"{key}：{msg}")
        for key, var in (("THINK", self.pv_think_var),
                         ("NO_REASONING", self.pv_noreason_var)):
            ok, msg, _v = settings.set_value(key, var.get())
            if not ok:
                fail.append(f"{key}：{msg}")

        self._pv_refresh()
        if fail:
            messagebox.showwarning("部分失败", "\n".join(fail[:8]))
        else:
            messagebox.showinfo("设置", "参数已保存，当前会话立即生效")

    def _pv_deploy(self):
        key = PV.current()
        model = self.pv_model_var.get().strip()
        if not model:
            messagebox.showwarning("提示", "请先在模型列表里选一个模型")
            return

        argv, note = PV.deploy_command(model, key)
        if not argv:
            messagebox.showinfo("无法一键部署", note)
            return

        if not messagebox.askyesno(
                "一键部署模型",
                f"即将执行：\n{' '.join(argv)}\n\n{note}\n\n"
                "模型体积较大时会比较久，输出会实时写进日志页。是否开始？"):
            return

        def work():
            ok, msg = PV.run_deploy(model, key, emit=bridge.emit)
            return (ok, msg, model)

        self.show("log")
        self._pv_async(work, label=f"部署 {model}…", done_kind="pv_deploy")

    def _pv_async(self, fn, label, done_kind):
        """与 run_async 同款，但结果交给 done_kind 自己处理。"""
        if self.busy:
            messagebox.showinfo("提示", "已有任务在运行，请稍候")
            return
        self.set_busy(True, label)

        def work():
            try:
                self.q.put((done_kind, fn()))
            except Exception:
                self.q.put(("err", traceback.format_exc()))
        threading.Thread(target=work, daemon=True).start()

    def _pv_render_adapt(self):
        cur = PV.current()
        pre = PV.prev_provider()
        if pre == cur:
            self.pv_from_to.configure(
                text=f"当前：{PV.label_of(cur)}（未发生跨提供商切换）")
        else:
            self.pv_from_to.configure(
                text=f"{PV.label_of(pre)}  →  {PV.label_of(cur)}")

        # ★ 只展示「需要你手动处理」：自动改掉的那些在切换时已经弹窗列过了，
        #   留在侧栏只是占地方。
        _auto, manual = PV.adaptation(pre, cur)
        box = self.pv_adapt_text
        box.configure(state="normal")
        box.delete("1.0", "end")

        if manual:
            box.insert("end", "需要你手动处理\n", ("h",))
            for it in manual:
                box.insert("end", "⚠ " + it["title"] + "\n", ("warn",))
                box.insert("end", "   " + it["detail"] + "\n")
        else:
            box.insert("end", "当前没有需要手动处理的事项。\n", ("ok",))

        box.configure(state="disabled")
        self._pv_adapt_text = box.get("1.0", "end-1c")

    def _pv_copy_adapt(self):
        self.copy_to_clipboard(self._pv_adapt_text, "适配清单")

    def _pv_adapt_apply(self):
        cur = PV.current()
        pre = PV.prev_provider()
        if pre == cur:
            messagebox.showinfo("无需适配",
                                f"当前就是 {PV.label_of(cur)}，"
                                "没有跨提供商切换。")
            return

        changes = PV.apply_adaptation(pre, cur)
        self._paint_mode_row()
        self.model_var.set(PV.current_model(cur))
        self._detect_models_async()
        self._pv_refresh()

        if not changes:
            messagebox.showinfo("一键适配",
                                "参数已经是适配后的推荐值，无需改动。")
            return
        messagebox.showinfo(
            "一键适配完成",
            f"已为 {PV.label_of(cur)} 套用模型名与推荐参数：\n"
            + "\n".join(f"· {n}：{o}  →  {v}" for n, o, v in changes))

    def _pv_open_home(self):
        p = PV.get(PV.current())
        url = p.get("install_url") or p.get("home")
        if not url:
            messagebox.showinfo(
                "提示", "自定义服务没有官方地址，请直接填你自己的服务地址。")
            return
        webbrowser.open(url)

    # ================================================================
    # 页面 10：日志
    # ================================================================
    def _page_log(self):
        page = self.pages["log"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        card = RoundCard(page, radius=16, pad=14)
        card.grid(row=0, column=0, sticky="nsew")

        head = tk.Frame(card.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="运行日志", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        GlassButton(head, "清空", width=72, height=34, bg=CARD,
                    font=FONT_SMALL, command=self._clear_log).pack(side="right")
        GlassButton(head, "打开日志目录", width=128, height=34, bg=CARD,
                    font=FONT_SMALL, command=self._open_log_dir).pack(
            side="right", padx=8)
        GlassButton(head, "复制全部", width=104, height=34, bg=CARD,
                    font=FONT_SMALL, command=self._copy_log).pack(side="right")

        tk.Label(card.body,
                 text="提示：文本可拖选后按 Ctrl+C 复制；"
                      "列表 / 日志右键都有「复制」菜单（列表可导出为"
                      "制表符分隔，直接粘进 Excel）",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=760).pack(anchor="w", pady=(6, 0))

        wrap = tk.Frame(card.body, bg="#FFFFFF")
        wrap.pack(fill="both", expand=True, pady=(8, 0))

        self.log_text = tk.Text(wrap, wrap="word", font=FONT_MONO,
                                bg="#FFFFFF", fg=TEXT,
                                relief="solid", bd=1,
                                highlightthickness=1,
                                highlightbackground=CARD_BORDER,
                                insertbackground=TEXT,
                                spacing1=2, spacing3=2)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.log_text.configure(state="disabled")

        self.log_text.tag_config("ok", foreground=OK_COLOR)
        self.log_text.tag_config("warn", foreground=WARN_COLOR)
        self.log_text.tag_config("err", foreground=ERR_COLOR)

        # ★ 右键 / Ctrl+C 复制：有选中就复制选中，否则整篇日志
        attach_copy(self.log_text, [
            ("复制（选中，未选中则全部）",
             lambda: self._text_pick(self.log_text)),
            ("复制全部", lambda: self._text_all(self.log_text)),
        ], app=self)

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


def enable_dpi_awareness():
    """
    让界面按物理像素 1:1 渲染。

    不做这一步时，系统会把窗口整体拉伸（125% 缩放 → 窗口被放大 1.25 倍），
    「1500x1000 px」就变成了 1875x1250 px，超出屏幕后被压回，字号也发虚。
    调用必须在创建任何窗口之前。非 Windows / 失败时静默忽略。
    """
    try:
        import ctypes
        try:
            # 1 = PROCESS_SYSTEM_DPI_AWARE
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            return True
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                return True
            except Exception:
                return False
    except Exception:
        return False


def load_private_font(path):
    """
    用 Windows GDI 的 AddFontResourceExW(FR_PRIVATE) 把字体加载进当前进程。

    优点：不写注册表、不安装到系统，打包成 exe 分享给别人也能用。
    非 Windows 或加载失败时返回 False，由调用方回退到系统字体。
    """
    if not path or not os.path.exists(path):
        return False
    try:
        import ctypes
        gdi = ctypes.WinDLL("gdi32")
        FR_PRIVATE = 0x10
        added = gdi.AddFontResourceExW(ctypes.c_wchar_p(str(path)),
                                       ctypes.c_uint(FR_PRIVATE), 0)
        if log:
            log.info("私有加载字体 %s → 注册 %d 个字面", path, added)
        return bool(added)
    except Exception as e:
        if log:
            log.warning("私有加载字体失败：%s", e)
        return False


def _ttf_family_name(path):
    """
    直接解析 TTF/OTF 的 name 表取字体族名（nameID=1）。
    这样即便系统里没有安装该字体，也能拿到正确的族名交给 Tk。
    """
    try:
        import struct
        with open(path, "rb") as f:
            d = f.read()
    except Exception:
        return None
    if len(d) < 12 or d[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
        return None
    try:
        num = struct.unpack(">H", d[4:6])[0]
        off, name_off, name_len = 12, None, None
        for _ in range(num):
            tag = d[off:off + 4]
            _cs, o, ln = struct.unpack(">III", d[off + 4:off + 16])
            if tag == b"name":
                name_off, name_len = o, ln
                break
            off += 16
        if name_off is None:
            return None
        tbl = d[name_off:name_off + name_len]
        _fmt, cnt, soff = struct.unpack(">HHH", tbl[:6])
        best = None
        for i in range(cnt):
            rec = tbl[6 + 12 * i:18 + 12 * i]
            plat, _enc, lang, nid, ln, o = struct.unpack(">HHHHHH", rec)
            if nid != 1:
                continue
            raw = tbl[soff + o: soff + o + ln]
            if plat == 3:
                s = raw.decode("utf-16-be", "ignore")
            elif plat == 1:
                s = raw.decode("latin-1", "ignore")
            else:
                continue
            s = s.replace("\x00", "").strip()
            if not s:
                continue
            # 简体中文 / 英文优先
            if lang in (0x0804, 0x0409, 0x0C04, 0x1004):
                return s
            if best is None:
                best = s
        return best
    except Exception:
        return None


def resolve_font_family(root=None):
    """
    确定最终使用的字体族名：
      ① 优先私有加载 config.FONT_FILE（萝莉体），读其 family name
      ② 失败则退回黑体 → 微软雅黑
    并把字号按 FONT_SIZES 刷新。
    """
    global FONT_FAMILY, FONT, FONT_B, FONT_SMALL, FONT_TITLE, FONT_BIG, FONT_MONO

    try:
        import tkinter.font as tkfont
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()

    chosen = None
    fpath = getattr(config, "FONT_FILE", "")
    if fpath and os.path.exists(fpath) and load_private_font(fpath):
        fam = _ttf_family_name(fpath) or getattr(config, "FONT_NAME", "")
        if fam:
            chosen = fam
            if log:
                log.info("使用随程序分发的字体：%s（%s）", fam, fpath)

    if not chosen:
        for cand in ("SimHei", "黑体", "Microsoft YaHei", "微软雅黑"):
            if cand in fams:
                chosen = cand
                break
    FONT_FAMILY = chosen or "SimHei"

    # 字号：相对基准统一取值，方便一处调整
    S = FONT_SIZES
    FONT       = (FONT_FAMILY, S["body"])
    FONT_B     = (FONT_FAMILY, S["body"], "bold")
    FONT_SMALL = (FONT_FAMILY, S["small"])
    FONT_TITLE = (FONT_FAMILY, S["title"], "bold")
    FONT_BIG   = (FONT_FAMILY, S["big"], "bold")
    FONT_MONO  = (FONT_FAMILY, S["mono"])
    return FONT_FAMILY


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

    enable_dpi_awareness()         # ★ 必须早于 tk.Tk()，否则 1500x1000 会被缩放
    root = tk.Tk()
    resolve_font_family(root)      # ★ 必须在 App 构建前定好字体
    app = App(root)               # ★ 必须持有引用：App 靠它存活（回调里持 self）
    apply_window_effects(root)
    app.root.mainloop()


if __name__ == "__main__":
    main()
