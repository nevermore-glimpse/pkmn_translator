# -*- coding: utf-8 -*-
"""
宝可梦同人工具 —— 亚克力毛玻璃图形界面。

布局：
  左侧  圆形头像（**点击回主页** + 悬停显示作者信息）+ 菜单列表（悬停放大 +
        底部阴影，菜单装不下时整列可上下滑动）
  右侧  各功能页面
    · 主页（头像全身照 + 作者姓名 + Bilibili / GitHub 主页链接）—— **不在左侧
      菜单里**，**工具启动时默认就是它**，点左上角头像随时回来
    · 菜单 2「游戏汉化」＝汉化流程的入口页：右侧列出各步骤，点一项进入对应
      界面（进去后顶部有「← 返回游戏汉化」回来）；这些子页面本身**不在左侧
      菜单里**（见 HANHUA_SUBMENUS）
    · 菜单 6「存档编辑」＝存档修改的入口页：右侧选游戏存档，中间列出 5 个编辑
      界面（主角 / 同行宝可梦 / 背包 / PC 盒子 / 开关变量），同样点进去编辑，
      顶部有「← 返回存档编辑」（见 SAVE_SUBMENUS）
    · 汉化子页面右侧带「待操作文件」勾选侧边栏；存档编辑各页右侧带「选择游戏
      存档」侧边栏
    · 菜单 3「设置」 4「本地模型服务」右侧带侧边栏（适配清单）
    · 底部常驻状态条（进度 + 取消）
  菜单 7「日志」为日志页，任务启动后自动跳转过去。
"""
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from collections import Counter

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import bridge
import logger
import commands
import config
import dict_editor as DE
import env_check
import pbs_edit
import prefix_dict as PFD
import processor as PR
import providers as PV
import save_tools as ST
import settings
import term_sync as TS

log = None  # 延迟到 main() 里初始化

# 报告里问题类型的固定顺序（与 term_fix.KIND_ORDER 保持一致；GUI 筛选用）
TFX_KIND_ORDER = ["译名为空", "同词不同译", "未翻（回显原文）",
                  "译文残留英文", "疑似机翻残留"]


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
C_FLOW    = "#D64545"     # 翻译流程说明（正红，区别于灰色说明）

# PBS 编辑界面：输入框用醒目的宝可蓝描边（聚焦时更深），一眼就能找到要改哪里
FIELD_BORDER       = "#1667C4"   # 宝可蓝：够醒目但不刺眼
FIELD_BORDER_FOCUS = POKE_RED    # 光标进去时变宝可红

# llama.cpp 中层那句固定说明 —— 状态行会拼在它后面，两行刚好，
# 不能塞太多文字，否则中层卡片（高度受挤压）装不下。
PV_LLAMA_HINT = ("先指好「程序目录」和「模型目录」，启动时自动 -m 加载选中的"
                 "GGUF（关推理、关只涨不降的历史缓存）。")

# 方框内文字的左右 / 上下留白（按钮按文字大小自适应时用）
BTN_PAD_X = 22
BTN_PAD_Y = 16

MENU_ITEMS = [
    ("1", "文本提取与编译"),
    ("2", "游戏汉化"),
    ("3", "PBS编辑"),
    ("4", "本地模型服务"),
    ("5", "开启DEBUG"),
    ("6", "存档编辑"),
    ("7", "设置"),
    ("8", "日志"),
]

# ★ 左侧菜单：序号 → 页面键。
#   "0"（主页）**不进左侧菜单**（用户要求）：只留在这里，供 _build_content
#   建页面用；进入方式是点左上角头像。
#   ★ 顺序按用户要求：「设置」挪到「日志」上一位，「PBS编辑」紧挨「游戏汉化」下面。
MENU_KEYS = {
    "0": "home",
    "1": "intl", "2": "hanhua", "3": "pbsedit",
    "4": "provider", "5": "debug",
    "6": "saveedit", "7": "settings", "8": "log",
}

# ★ 被「游戏汉化」统合的子页面：左侧菜单里**没有它们**，
#   统一从「游戏汉化」页点进去（进去后顶部会出现「← 返回游戏汉化」）。
#   (页面键, 名称, 一句话说明)
HANHUA_SUBMENUS = [
    ("termextract", "术语提取",
     "从游戏文本里读名字文件（宝可梦/招式/道具/特性/属性/地图…），"
     "交给模型翻好后写进术语表。"),
    ("termcheck", "术语检查报告",
     "只看术语提取的缓存与术语表，列出有问题的译名，可双击改译名并写回，"
     "改译名不走模型；「术语重翻」删缓存重翻会调用模型。"),
    ("translate", "翻译",
     "选好文件，把原文翻成目标语言，生成译文与检查报告。"),
    ("report", "重翻检查报告",
     "按问题类型筛选，把有问题的句子重新翻一遍。"),
    ("terms", "术语更新后重翻",
     "术语表改过之后，只重翻受影响的句子。"),
    ("prefix", "前缀字典",
     "按前缀批量替换 / 校对译文。"),
    ("polish", "中文润色",
     "对已有译文再润色一遍。"),
    ("reflow", "换行重排",
     "把游戏里过长的一行重新断行。"),
    ("excel", "术语字典 / Excel 转换",
     "查看并编辑术语字典，或从 Excel 导进术语。"),
]

# ★ 「游戏汉化」页右侧的翻译流程说明（原文照抄，不要改写 / 不要另加序号）。
#   注意第六步里的 "\t" 是普通反斜杠 + t，不是制表符，必须写成 "\\tg[]"。
HANHUA_FLOW_STEPS = [
    "第一步：术语提取，所有要翻译的文件先走术语提取",
    "第二步：术语检查，检查术语是否遗漏或错翻并直接改译文",
    "第三步：翻译，翻译非术语文件",
    "第四步：重翻检查报告，修正有问题的句子",
    "第五步：检查术语，看是否要更新术语并修正相关句子",
    "第六步：查看前缀字典，只翻译\\tg[]里的",
    "第七步：中文润色，提供翻译质量",
    "第八步：换行重排，重新设置句子的换行",
    "第九步：翻译全部完成后，在9.术语字典里删除自动提取术语",
]

# ★ 「翻译流程」说明的字号（手动调整就改这两个数字，单位 pt）。
#   17pt 是最小窗口 1240×760 下的边界：正文高 462px，加上 20pt 标题后
#   仍不超过左侧 10 个按钮撑出来的 560px；再大一号（18pt）正文高 611px，
#   版面会被撑高。标题固定比正文大 3pt，保持层级。
HANHUA_FLOW_TITLE_PT = 20
HANHUA_FLOW_BODY_PT = 17
# wraplength 必须跟着字号一起放大：460 是 10pt 时代的取值，17pt 下沿用会把
# 每行挤到更窄、行数变多，反而撑破版面。590 是 1240 最小窗口下的可用宽度。
HANHUA_FLOW_WRAP = 590

# ★ 同样的套路：「存档编辑」统合的 6 个编辑界面
#   (页面键, 名称, 一句话说明)
SAVE_SUBMENUS = [
    ("save_trainer", "主角编辑",
     "名字、金钱、徽章、图鉴与形态图鉴、服装、训练家类型等通用字段。"),
    ("save_party", "同行宝可梦编辑",
     "昵称、种族、个体值／努力值、性格、特性、当前 HP、招式、携带道具、"
     "状态、亲密度、异色、捕获用球、孵蛋步数、形态、勋章 —— "
     "改完自动重算六项能力值。"),
    ("save_bag", "背包编辑",
     "各口袋的道具与数量，以及「登记道具」。"),
    ("save_box", "PC 盒子编辑",
     "24 个箱子里的宝可梦：编辑、删除、改名、移入队伍。"),
    ("save_switch", "开关与变量",
     "按编号查看 / 修改全局开关与全局变量（编号从 1 开始，与游戏里一致）。"),
]

# ★ 「PBS编辑」页里点「编辑 PBS 文件」进去的编辑窗口
#   (页面键, 名称, 一句话说明)
PBS_SUBMENUS = [
    ("pbs_editor", "PBS 编辑窗口",
     "左边挑一个 txt，右边按它的类型显示对应的编辑界面。"),
]

# 子页面的键集合 / 键 → 上级页面 / 键 → 名称
#   （show() 靠 SUBMENU_PARENT 决定左侧高亮谁、顶部返回条写什么）
SUBMENU_PARENT = {}
SUBMENU_TITLES = {}
for _k, _n, _d in HANHUA_SUBMENUS:
    SUBMENU_PARENT[_k] = "hanhua"
    SUBMENU_TITLES[_k] = _n
for _k, _n, _d in SAVE_SUBMENUS:
    SUBMENU_PARENT[_k] = "saveedit"
    SUBMENU_TITLES[_k] = _n
for _k, _n, _d in PBS_SUBMENUS:
    SUBMENU_PARENT[_k] = "pbsedit"
    SUBMENU_TITLES[_k] = _n
SUBMENU_KEYS = set(SUBMENU_PARENT)

# 「存档编辑」的 5 个子页面（供 show() 判断该刷新哪个编辑界面）
SAVE_SUBMENUS_KEYS = {k for k, _n, _d in SAVE_SUBMENUS}

# 上级页面 → 顶部返回条的文字
BACK_TEXTS = {
    "hanhua": "← 返回游戏汉化",
    "saveedit": "← 返回存档编辑",
    "pbsedit": "← 返回PBS编辑",
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
                 shadow=SHADOW, pad=14, bg=None, auto_height=False,
                 scrollable=False, **kw):
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

        if scrollable:
            # 内容超高时整块滚动：窗口里放的是滚动区 outer（仍被钉成卡片
            # 尺寸，见 _resize），self.body 指向滚动区的 inner —— inner 不
            # 再被钉高，超高部分溢出后可由画布滚动。外部 card.body 写法不变。
            _outer, _inner = make_scroll_area(self, bg=fill)
            self.body = _inner
            self._win = self.create_window(0, 0, window=_outer, anchor="nw")
        else:
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
# 主页大图缓存：原图是上亿像素的 JPEG，缩放很贵，只做一次
_HERO_CACHE = {}


def load_fitted_photo(path, max_w, max_h):
    """
    把图片按比例缩进 max_w×max_h（保持宽高比）→ PhotoImage；失败返回 None。

    ★ 原图可能上亿像素：先用 PIL 的 draft() 让 JPEG 在**解码阶段**就降采样，
      再用 LANCZOS 缩到目标尺寸，避免一次性解码出巨大的位图。
    """
    if not path or not os.path.exists(path):
        return None
    key = (path, max_w, max_h)
    if key in _HERO_CACHE:
        return _HERO_CACHE[key]
    photo = None
    try:
        from PIL import Image, ImageTk
        Image.MAX_IMAGE_PIXELS = None          # 原图很大，解除告警阈值
        im = Image.open(path)
        im.draft("RGB", (max_w, max_h))
        im = im.convert("RGB")
        w, h = im.size
        scale = min(float(max_w) / w, float(max_h) / h, 1.0)
        size = (max(1, int(w * scale)), max(1, int(h * scale)))
        if size != (w, h):
            im = im.resize(size, Image.LANCZOS)
        photo = ImageTk.PhotoImage(im)
    except Exception as e:                     # noqa: BLE001
        photo = None
        try:
            if log:
                log.debug("主页图片加载失败：%s", e)
        except Exception:                      # noqa: BLE001
            pass
    if photo is not None:
        _HERO_CACHE[key] = photo
    return photo


class Avatar(tk.Canvas):
    """圆形头像：悬停弹出作者信息，点击（给了 on_click 时）跳转主页。"""

    def __init__(self, master, size=68, path=None, on_click=None):
        tk.Canvas.__init__(self, master, width=size, height=size,
                           highlightthickness=0, bg=CARD, cursor="hand2")
        self.size = size
        self.path = path
        self.on_click = on_click
        self._photo = None
        self._tip = None
        self._tip_job = None

        self._load_image()
        # 不再画白色光圈：图片本身已按圆形 alpha 裁剪，圆外完全透明

        self.bind("<Enter>", self._schedule_tip)
        self.bind("<Leave>", self._hide_tip)
        self.bind("<ButtonRelease-1>", self._click)

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

    def _click(self, _e=None):
        """点击：给了 on_click 就跳转（如回主页），否则切换作者信息气泡。"""
        if self.on_click is not None:
            self._hide_tip()
            self.on_click()
            return
        self._toggle_tip()

    def _toggle_tip(self, _e=None):
        if self._tip and self._tip.winfo_exists():
            self._hide_tip()
        else:
            self._show_tip()


def make_scroll_area(parent, bg=CARD):
    """返回 (outer_frame, inner_frame)，带滚动条与滚轮支持。"""
    outer = tk.Frame(parent, bg=bg)
    # ★ Tk Canvas 不给 width/height 时默认请求 378x265，会把外层容器
    #   （右侧栏只有 310 宽）的「请求宽度」顶爆 →  fill="x" 的子控件按
    #   请求宽度排版、超出容器右边被裁。所有调用处都是 fill+expand，给个
    #   小尺寸不影响显示（RoundCard 里也是这么绕的）。
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, width=10, height=10)
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
def pick_game_exe_dialog(parent, initialdir=None,
                         title="选择游戏主程序（如 Game.exe）"):
    """
    统一的「选游戏」对话框：让用户选**游戏主程序 exe**，自动推出游戏根目录。

    ★ 为什么不让用户选目录：目录选到哪一层全靠猜（很多人会误选到 Data/ 里），
      而 exe 只有那一个，选它最不容易出错。根目录由 exe 所在位置推出来。

    返回 (game_root, exe_path)；用户取消返回 (None, None)。
    """
    import game_scripts as GS

    p = filedialog.askopenfilename(
        parent=parent, title=title,
        initialdir=initialdir or config.BASE_DIR,
        filetypes=[("游戏主程序", "*.exe"), ("所有文件", "*.*")])
    if not p:
        return None, None
    root, note = GS.game_root_from_exe(p)
    if note:
        messagebox.showinfo("提示", note, parent=parent)
    return root, p


class FilePanel(tk.Frame):
    """
    右侧「待操作文件」侧边栏：单个文件 / 整个文件夹 + 勾选列表。

    mode:
      "source"     —— 翻译页：源文件，不限格式，只跳过译文与检查报告
      "report"     —— 重翻检查报告页：只识别 *_translated_report.txt
      "cache"      —— 术语重翻 / 中文润色页：只识别翻译缓存 *_cache.json
      "translated" —— 换行重排页：只识别译文 *_translated.txt
      "dict"       —— 前缀字典页：固定用工具目录下的 prefix_dict.json，不给选
    """

    # 翻译页需要跳过的后缀
    # 源文件之外的「工具产物」一律不列出来（译文 / 报告 / 缓存 / 润色稿…）
    SKIP_SUFFIX = ("_translated.txt", "_translated_report.txt",
                   "_polished.txt", "_unknown_ctrl.txt",
                   "_cache.json", "_cache_edited.json",
                   "_conflicts.json", "_placeholder.json",
                   "_polish_cache.json",
                   # ★ 术语提取的缓存 / 报告：同样以 _cache.json 结尾，
                   #   不显式排除会被「翻译缓存」过滤器当成翻译缓存列出来
                   "_terms_cache.json", "_terms_report.txt")

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

        # ★ "dict" 模式（前缀字典页）：字典文件固定，不用给选择按钮
        if self.mode != "dict":
            row = tk.Frame(self, bg=bg)
            row.pack(fill="x", padx=10)
            GlassButton(row, "单个文件", width=88, height=34, bg=bg,
                        font=FONT_SMALL,
                        command=self.pick_file).pack(side="left")
            GlassButton(row, "整个文件夹", width=88, height=34, bg=bg,
                        font=FONT_SMALL, command=self.pick_dir).pack(
                side="left", padx=6)

        row2 = tk.Frame(self, bg=bg)
        row2.pack(fill="x", padx=10, pady=(6, 2))
        if self.mode != "dict":
            GlassButton(row2, "全选", width=64, height=32, bg=bg,
                        font=FONT_SMALL,
                        command=self.select_all).pack(side="left")
            GlassButton(row2, "清空", width=64, height=32, bg=bg,
                        font=FONT_SMALL,
                        command=self.clear).pack(side="left", padx=6)
        self.count_lbl = tk.Label(row2, text="已选 0", bg=bg, fg=C_KEY,
                                  font=FONT_BIG)
        self.count_lbl.pack(side="right")

        # ★ 换行重排页：可以直接选游戏根目录（自动扫描里面的 txt 文件）
        if allow_game_root:
            row3 = tk.Frame(self, bg=bg)
            row3.pack(fill="x", padx=10, pady=(4, 2))
            GlassButton(row3, "游戏主程序", width=120, height=32, bg=bg,
                        font=FONT_SMALL,
                        command=self.pick_game_root).pack(side="left")
            self.root_lbl = tk.Label(row3, text="未选择", bg=bg, fg=C_HINT,
                                     font=FONT_SMALL, anchor="w",
                                     wraplength=max(100, width - 150))
            self.root_lbl.pack(side="left", padx=6)

        # ★ 列表不再自己滚：整块面板由外层右栏的可滚卡片承载（决策 B）。
        #   这里保留 list_inner 这个名字与「塞子控件」的语义，只把画布容器
        #   换成普通 Frame，让列表按自然高度展开。
        self.list_inner = tk.Frame(self, bg=bg)
        self.list_inner.pack(fill="both", padx=6, pady=(4, 8))

        # ★ 在列表空白处右键 → 复制所有已选文件的完整路径
        attach_copy(self.list_inner, [
            ("复制已选文件的完整路径", self._paths_text),
        ], app=self.app, hotkey=False)

        self._hint = tk.Label(self.list_inner, text=self._hint_text(),
                              bg=bg, fg=C_HINT, font=FONT_SMALL,
                              justify="left",
                              wraplength=max(120, self.panel_w - 62))
        self._hint.pack(anchor="w", padx=6, pady=10)

        # ★ 前缀字典页：字典文件固定写在工具目录下，直接列出来
        if self.mode == "dict":
            try:
                import prefix_dict as PFD
                dict_file = PFD.DICT_FILE
            except Exception:
                dict_file = os.path.join(config.BASE_DIR, "prefix_dict.json")
            self.add_files([dict_file], silent=True)

    # ---------- 复制 ----------
    def _paths_text(self):
        """已勾选文件的完整路径（每行一个）。"""
        return "\n".join(p for p in self.files
                         if self.vars.get(p) and self.vars[p].get())

    # ---------- 筛选规则 ----------
    def _hint_text(self):
        if self.mode == "report":
            return "点击上方按钮选择检查报告\n（只识别 *_translated_report.txt）"
        if self.mode == "cache":
            return ("点击上方按钮选择翻译缓存\n"
                    "（只识别 *_cache.json，也就是翻译时生成的那个缓存）")
        if self.mode == "translated":
            return ("点击上方按钮选择译文文件\n"
                    "（只识别 *_translated.txt）")
        if self.mode == "dict":
            return "前缀字典固定放在工具目录下，不用选"
        text = "点击上方按钮选择文件\n（不限格式，自动跳过译文与检查报告）"
        if getattr(self, "allow_game_root", False):
            text += "\n也可点「游戏主程序」自动扫描游戏目录里的 txt 文件"
        return text

    def _accept(self, name, path=""):
        low = name.lower()
        if self.mode == "report":
            return low.endswith("_translated_report.txt")
        if self.mode == "cache":
            # ★ 术语提取的缓存也叫 xxx_terms_cache.json，结尾同样是
            #   _cache.json —— 必须先排除它，否则会被当成翻译缓存选进去
            if low.endswith("_terms_cache.json"):
                return False
            return low.endswith("_cache.json")
        if self.mode == "translated":
            return low.endswith("_translated.txt")
        if self.mode == "dict":
            return low == "prefix_dict.json"
        # ★ 源文件模式（翻译页）：名字类文件不列出来 ——
        #   那批归「术语提取」管，翻译与重排都不该碰。
        #   判据用 term_extract.resolve_names，与术语提取页完全一致。
        try:
            import term_extract as TE
            if TE.is_term_source_file(path):
                return False
        except Exception:
            pass
        return not low.endswith(self.SKIP_SUFFIX)

    def _filter(self, paths):
        return [p for p in paths
                if os.path.isfile(p) and self._accept(os.path.basename(p), p)]

    # ---------- 选择 ----------
    def _initial(self):
        d = config.Runtime.last_dir
        return d if d and os.path.isdir(d) else config.BASE_DIR

    def pick_file(self):
        if self.mode == "report":
            title = "选择检查报告（*_translated_report.txt）"
            types = [("检查报告", "*_translated_report.txt"),
                     ("所有文件", "*.*")]
        elif self.mode == "cache":
            title = "选择翻译缓存（*_cache.json）"
            types = [("翻译缓存", "*_cache.json"), ("所有文件", "*.*")]
        elif self.mode == "translated":
            title = "选择译文文件（*_translated.txt）"
            types = [("译文文件", "*_translated.txt"), ("所有文件", "*.*")]
        elif self.mode == "dict":
            return
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
        if self.mode == "dict":
            return
        folder = filedialog.askdirectory(
            title="选择文件夹", initialdir=self._initial())
        if not folder:
            return
        config.Runtime.set_dir(folder)
        files = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            # ★ 只收文件（别把「翻译中间文件」这类子目录也列进来）
            if self._accept(f, os.path.join(folder, f))
            and os.path.isfile(os.path.join(folder, f))
        )
        # ★ 再扫一层「翻译中间文件」夹 —— 缓存 / 报告 / 润色稿现在都放里面，
        #   用户选源文件夹时应该能直接选到它们（否则得再点进子目录一次）。
        #   游戏文本常按子目录分组（如 Text_chinese/A、/B），所以子目录下的
        #   「翻译中间文件」也要扫到，否则报告 / 缓存会被整层跳过。
        candidates = [folder] + [
            os.path.join(folder, f)
            for f in sorted(os.listdir(folder))
            if os.path.isdir(os.path.join(folder, f))
        ]
        wd_name = getattr(config, "WORK_DIR_NAME", "")
        for cand in candidates:
            wd = os.path.join(cand, wd_name)
            if os.path.isdir(wd):
                files += sorted(
                    os.path.join(wd, f)
                    for f in os.listdir(wd)
                    if self._accept(f, os.path.join(wd, f))
                    and os.path.isfile(os.path.join(wd, f))
                )
            if len(files) >= 2000:      # 防大目录卡死，与 pick_game_root 同上限
                break
        if not files:
            messagebox.showinfo("提示", self._hint_text().replace("\n", ""))
            return
        self.add_files(files)

    def pick_game_root(self):
        """选游戏主程序 exe → 推出游戏根目录 → 扫描里面的 txt 文件。"""
        folder, _exe = pick_game_exe_dialog(
            self, initialdir=self._initial(),
            title="选择游戏主程序（会自动扫描游戏目录里的 .txt）")
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
            # ★ 跳过工具建的「翻译中间文件」夹（里面全是缓存 / 报告 / 润色稿）
            wd = getattr(config, "WORK_DIR_NAME", "")
            if wd:
                dirs[:] = [d for d in dirs if d != wd]
            for f in files:
                if not f.lower().endswith(".txt"):
                    continue
                if not self._accept(f, os.path.join(root, f)):
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
        """没选文件时尝试用当前默认文件（按本页认的格式换算）；仍为空返回 []。"""
        sel = self.selected()
        if sel:
            return sel
        cur = config.Runtime.input_file
        if self.mode == "report":
            cur = commands.report_path_for(cur)
        elif self.mode == "cache":
            cur = commands.cache_path_for(cur)
        elif self.mode == "translated":
            cur = commands.translated_path_for(cur)
        elif self.mode == "dict":
            return self.selected()
        if cur and os.path.exists(cur):
            self.add_files([cur])
            return self.selected()
        return []


# ================================================================
# 添加术语弹窗
# ================================================================
class TermDialog(tk.Toplevel):
    """术语弹窗：输入原文与译文，结果放在 self.result = (原文, 译文)。

    默认是「添加术语」；术语字典页也用它做「修改」（init_src / init_dst
    预填当前值，标题与按钮文案换成修改）。
    """

    def __init__(self, master, src_lang="", tgt_lang="", init_src="",
                 init_dst="", title="添加术语", ok_text="确定添加", note=None):
        tk.Toplevel.__init__(self, master, bg=BG_BASE)
        self.result = None
        self.title(title)
        self.resizable(False, False)
        self.transient(master)

        card = RoundCard(self, radius=16, pad=16, width=520,
                         auto_height=True)
        card.pack(padx=12, pady=12)
        body = card.body

        tk.Label(body, text=title, bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        if note is None:
            note = ("新术语会立即写入术语字典；点「应用术语」时会删除\n"
                    "相关句子的缓存并重新翻译。")
        tk.Label(body, text=note, bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(4, 12))

        self.src_var = tk.StringVar(value=init_src or "")
        self.dst_var = tk.StringVar(value=init_dst or "")
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
        GlassButton(btns, ok_text, width=128, height=40, primary=True,
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
    def ask(cls, master, src_lang="", tgt_lang="", **kw):
        """弹出对话框并等待结果；返回 (原文, 译文)，取消则返回 None。"""
        dlg = cls(master, src_lang, tgt_lang, **kw)
        master.wait_window(dlg)
        return dlg.result


class _AskText(tk.Toplevel):
    """通用的单行文本输入弹窗。"""

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


class AntiDebugDialog(tk.Toplevel):
    """
    反调试「复核」窗口：把疑似反调试的代码原样摆给用户看。

    用户可以：
      · 直接在框里改（改完点「用我改的这段」）
      · 点「自动注释」让工具按老规矩加 `# [pkmn-debug] `
      · 点「加入白名单并跳过」——这段以后再也不问（落盘到
        `antidebug_whitelist.json`；引擎自带的 F9 呼出调试菜单那段已内置）
      · 点「跳过」本次不动它
      · 点「取消」整次「开启 DEBUG」都不做了

    result = {"action": "comment" | "manual" | "skip" | "cancel",
              "text": 改好后的整份脚本文本（skip / cancel 时没有）}
    """

    CTX = 3          # 上下各带几行上下文

    def __init__(self, master, src, idx=1, total=1):
        tk.Toplevel.__init__(self, master, bg=BG_BASE)
        import debug_tool as DT
        self.DT = DT
        self.src = src
        self.result = None
        self.title("发现疑似「反调试」代码")
        self.transient(master)
        self.configure(padx=0, pady=0)

        card = RoundCard(self, radius=16, pad=16, width=720,
                         auto_height=True)
        card.pack(padx=12, pady=12)
        body = card.body

        where = ("解包文件 %s" % src["path"]
                 if src.get("mode") == "file"
                 else ("PluginScripts.rxdata 里插件第 %s 个 · 第 %s 个文件"
                       % (src["key"][0], src["key"][1])
                       if src.get("mode") == "plugin"
                       else "Scripts.rxdata 第 %s 条" % src.get("key")))
        tk.Label(body, text="发现疑似「反调试」代码", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(body,
                 text=("第 %d/%d 处　脚本：%s\n位置：%s"
                       % (idx, total, src.get("name") or "", where)),
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(4, 2))
        tk.Label(body,
                 text="下面这段每帧把 $DEBUG 摁回 false（或把场景踢掉）。\n"
                      "确认是反调试就注释掉；正常代码就加白名单。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=670).pack(anchor="w", pady=(2, 8))

        lines = src["text"].split("\n")
        lo, hi = DT.region_of(src["text"], src["blocks"], self.CTX)
        pos = "、".join("第 %d–%d 行" % (b["start"] + 1, b["end"] + 1)
                        for b in src["blocks"])
        tk.Label(body, text="被判为反调试的部分：%s（下面带 %d 行上下文，"
                            "行号从 %d 起）" % (pos, self.CTX, lo + 1),
                 bg=CARD, fg=C_KEY, font=FONT_SMALL).pack(anchor="w")

        box = tk.Frame(body, bg=CARD)
        box.pack(fill="both", expand=True, pady=(4, 10))
        self.txt = tk.Text(box, width=88, height=14, font=FONT_MONO,
                           wrap="none", bg="#FFFFFF", fg="#20304A",
                           relief="solid", borderwidth=1,
                           insertbackground="#20304A")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.txt.insert("1.0", "\n".join(lines[lo:hi + 1]))
        self.txt.edit_modified(False)

        btns = tk.Frame(body, bg=CARD)
        btns.pack(fill="x")
        GlassButton(btns, "取消（中止）", width=110, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._cancel).pack(side="left")
        GlassButton(btns, "跳过本次", width=100, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._skip).pack(side="left", padx=6)
        GlassButton(btns, "加入白名单并跳过", width=150, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._whitelist).pack(side="left")
        GlassButton(btns, "用我改的这段", width=120, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._manual).pack(side="right", padx=6)
        GlassButton(btns, "自动注释", width=110, height=40, primary=True,
                    bg=CARD, font=FONT_SMALL,
                    command=self._auto).pack(side="right")

        self.update_idletasks()
        self._center(master)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.txt.focus_set()
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

    # ---- 各按钮 ----
    def _text_now(self):
        return self.txt.get("1.0", "end-1c")

    def _auto(self):
        # edited=None → enable_debug 按原来的规矩给那几行加 `# [pkmn-debug] `
        self.result = {"action": "comment", "edited": None}
        self.destroy()

    def _manual(self):
        cur = self._text_now()
        orig = self.DT.region_text(self.src["text"], self.src["blocks"],
                                   self.CTX)
        if cur == orig:
            if not messagebox.askyesno(
                    "没有改动", "这段代码你没改过，按原样写回等于不动它。\n"
                    "要继续吗？（一般该点「跳过」或「自动注释」）",
                    parent=self):
                return
        self.result = {"action": "manual", "edited": cur}
        self.destroy()

    def _skip(self):
        self.result = {"action": "skip"}
        self.destroy()

    def _whitelist(self):
        code = self.DT.block_text(self.src["text"], self.src["blocks"])
        added, n = self.DT.add_antidebug_whitelist(code)
        if added:
            messagebox.showinfo(
                "已加入白名单",
                "这段代码已记进白名单（共 %d 条），以后开 DEBUG 不再问它。\n\n"
                "要删掉的话，编辑程序目录下的 antidebug_whitelist.json。"
                % n, parent=self)
        self.result = {"action": "skip"}
        self.destroy()

    def _cancel(self):
        self.result = {"action": "cancel"}
        self.destroy()

    @classmethod
    def review(cls, master, src, idx=1, total=1):
        dlg = cls(master, src, idx, total)
        master.wait_window(dlg)
        return dlg.result or {"action": "cancel"}


# ================================================================
# 存档编辑：公共小控件与侧边栏
# ================================================================
STATUS_CHOICES = [(name, idx) for idx, name in sorted(ST.STATUS_NAMES.items())]
SHINY_CHOICES = [("按个体 ID 自动判定", "auto"),
                 ("一定异色（闪光）", "yes"),
                 ("一定不异色", "no")]

# 六项能力值的中文名（顺序与 ST.STAT_IVARS 一致）
EV_LABELS = list(ST.STAT_KEYS)


def sfmt(v) -> str:
    """把任意值显示成短字符串（None 显示为 —）。"""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "是" if v else "否"
    return str(v)


class SearchCombo(ttk.Combobox):
    """
    可搜索下拉框：pairs = [(显示名, 值)]，边打字边过滤（显示名里带 #编号，好搜）。

    ★ 值可能是 int（编号）也可能是字符串（异色那种），所以不要用 Combobox
      自带的 get() 取值 —— 统一走 value_of()。
    """

    def __init__(self, master, pairs=None, width=30, font=None, value=None,
                 resolver=None):
        self.pairs: list = []
        self._labels: list = []
        self._map: dict = {}
        # ★ 手输解析器：下拉里没有的写法（内部名 / 编号）交给它认。
        #   物种 / 道具 / 招式那几个框会挂上 GameData.find_species 之类。
        self._resolver = resolver
        ttk.Combobox.__init__(self, master, width=width, values=[],
                              font=font or FONT_SMALL)
        self.set_pairs(pairs or [], keep=False)
        self.bind("<KeyRelease>", self._on_key)
        if value is not None:
            self.set_value(value)


    # -- 数据 --------------------------------------------------------------
    def set_pairs(self, pairs, keep: bool = True):
        old = self.value_of() if keep else None
        self.pairs = list(pairs or [])
        self._labels = [str(p[0]) for p in self.pairs]
        self._map = {str(p[0]): p[1] for p in self.pairs}
        self["values"] = self._labels
        if old is not None:
            self.set_value(old)

    def set_value(self, value):
        """按值选中对应项；找不到就显示 (＃值)。"""
        for label, v in self.pairs:
            if v == value and type(v) is type(value) and value is not None:
                self.set(str(label))
                return
        for label, v in self.pairs:
            if v == value:
                self.set(str(label))
                return
        self.set("" if value is None else f"（#{value}）")

    def value_of(self):
        """当前选中项的值；认不出来返回 None。

        ★ 除了下拉里选的（含打字过滤后选中的），还接受**手输**：
          纯数字编号，或交给 _resolver 认内部名 / 显示名。
        """
        txt = self.get().strip()
        if txt in self._map:
            return self._map[txt]
        if txt.lstrip("-").isdigit():
            return int(txt)
        # set_value() 认不出时会填「（#955）」这种占位 —— 也当编号认
        m = re.fullmatch(r"[（(]\s*#?(\d+)\s*[)）]", txt)
        if m:
            return int(m.group(1))
        if self._resolver is not None and txt:
            try:
                return self._resolver(txt)
            except Exception:                       # noqa: BLE001
                return None
        return None

    def value_or_text(self):
        """
        选中项的值；**认不出来就把原文原样返回**（空则 None）。

        ★ 给「没选游戏数据」的场景用：这时对照表读不到，解析器认不出内部名，
          但现代存档本来就能直接写内部名 —— 所以把原文交给 core 去判断，
          core 认不出来会给出「必须用内部名」的明确报错。
        """
        v = self.value_of()
        if v is not None:
            return v
        txt = self.get().strip()
        return txt or None

    # -- 过滤 --------------------------------------------------------------
    def _on_key(self, e=None):
        if e is not None and e.keysym in ("Up", "Down", "Return", "Escape",
                                          "Tab", "Left", "Right", "Home",
                                          "End", "Prior", "Next"):
            return
        txt = self.get().strip().lower()
        if not txt:
            self["values"] = self._labels
            return
        hits = [s for s in self._labels if txt in s.lower()]
        self["values"] = hits[:300] if hits else ["（没有匹配项）"]


def make_manual_resolver(get_save, kind, get_pm=None):
    """
    「手输解析器」工厂：把用户打的内部名 / 编号 / 显示名换算成下拉用的取值。

    支持 kind：species / item / move / nature / status / ability / trainer_type
    get_save —— 返回当前 SaveFile 的可调用对象（没有数据时返回 None）
    get_pm   —— 可选；特性解析要结合「这只宝可梦的可选特性列表」

    ★ 认不出来就返回 None：调用方用 `SearchCombo.value_or_text()` 时会把
      原文交给 core，由 core 按内部名处理（没选游戏数据时的必需通路）。
    """
    def fn(txt):
        sv = get_save()
        if sv is None:
            return None
        d = sv.data
        if kind == "species":
            return d.find_species(txt)
        if kind == "item":
            return d.find_item(txt)
        if kind == "move":
            return d.find_move(txt)
        if kind == "nature":
            return d.nature_index_by_name(txt)
        if kind == "status":
            return d.status_code_by_name(txt)
        if kind == "trainer_type":
            return d.find_trainer_type(txt)
        if kind == "ability":
            pm = get_pm() if get_pm else None
            if pm is None:
                return d.find_ability(txt)
            return sv._ability_index_for(pm, txt)
        return None
    return fn


def _lbl(parent, text, **kw):
    kw.setdefault("bg", CARD)
    kw.setdefault("fg", TEXT_DIM)
    kw.setdefault("font", FONT_SMALL)
    kw.setdefault("anchor", "w")
    return tk.Label(parent, text=text, **kw)


def _hint(parent, text, **kw):
    kw.setdefault("bg", CARD)
    kw.setdefault("fg", C_HINT)
    kw.setdefault("font", FONT_SMALL)
    kw.setdefault("justify", "left")
    kw.setdefault("anchor", "w")
    return tk.Label(parent, text=text, **kw)


def _entry(parent, var, width=14):
    return ttk.Entry(parent, textvariable=var, width=width, font=FONT_SMALL)


def bind_autowrap(label, pad=8, minimum=80):
    """
    让 Label 的 wraplength 跟着它的**实际宽度**走。

    固定值（如 wraplength=760）在宽窗里够用，窗口一窄就整行冲出控件边界、
    被卡片/窗口边缘裁掉。绑了 <Configure> 之后，控件多宽就换行到多宽。
    """
    def _on_cfg(e):
        w = max(minimum, e.width - pad)
        try:
            if label.cget("wraplength") != w:
                label.configure(wraplength=w)
        except Exception:
            pass
    label.bind("<Configure>", _on_cfg)
    return label


def btn_grid(parent, specs, columns=2, bg=None, width=118, height=33):
    r"""
    把一排按钮排成网格。

    ★ 侧边栏旁边那列本来就窄（存档页左边只有 250~290px），一行硬塞 3 个按钮
      会被裁掉（用户反馈过「按钮被挤没了」）。固定列数就不会。
    specs = [(文字, 回调), ...]
    """
    bg = bg or CARD
    grid = tk.Frame(parent, bg=bg)
    for i, (text, cmd) in enumerate(specs):
        GlassButton(grid, text, width=width, height=height, bg=bg,
                    font=FONT_SMALL, command=cmd).grid(
            row=i // columns, column=i % columns, sticky="w",
            padx=(0, 6), pady=3)
    return grid


# ================================================================
# 存档编辑：字段级校验 / 写回差异 / 编码标记 —— 表格化小工具
#   ★ 这一节全是**纯函数**（不碰 Tk）：把内核给的 dict 列表格式化成
#     Treeview 的行数据，可以脱离窗口单独跑测试。
# ================================================================
SAVE_ISSUE_COLUMNS = [("lv", "等级"), ("where", "位置"),
                      ("field", "字段"), ("why", "原因")]
SAVE_DIFF_COLUMNS = [("where", "位置"), ("field", "字段"),
                     ("old", "原值"), ("new", "新值")]
SAVE_DIFF_ROW_CAP = 200        # 写回前差异清单最多列这么多条，多出来的注明


def _save_norm_field(name):
    """字段名归一化：去掉 @ / $ / 下划线 / 空白再转小写（校验标红靠它匹配）。"""
    s = "" if name is None else str(name)
    for ch in ("@", "$", "_", " ", "\t", "\n"):
        s = s.replace(ch, "")
    return s.strip().lower()


def _save_visible_text(text):
    """
    把文本里残留的孤立代理字符转成可见的 \\uXXXX 转义（只影响显示，不改数据）。

    ★ 0xDC80..0xDCFF 是 Python 的 surrogateescape 区间：旧版内核对没解码成功的
      Ruby 字符串只做了 repr，这些字符会原样进到界面，Tk 铺到表格里就成了方块/
      乱码，某些平台还会直接抛 TclError。
    """
    s = "" if text is None else str(text)
    if not any(0xD800 <= ord(ch) <= 0xDFFF for ch in s):
        return s
    out = []
    for ch in s:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def _save_issue_rows(items):
    """校验 / 读取提示 → Treeview 行数据 [(iid, (等级, 位置, 字段, 原因)), ...]。"""
    rows = []
    for i, it in enumerate(items or []):
        if not isinstance(it, dict):
            it = {"原因": str(it)}
        rows.append((str(i), (str(it.get("等级") or "警告"),
                              _save_visible_text(it.get("位置") or "—"),
                              _save_visible_text(it.get("字段") or "—"),
                              _save_visible_text(
                                  str(it.get("原因") or "").replace("\n", " ")))))
    return rows


def _save_diff_rows(changes, cap=SAVE_DIFF_ROW_CAP):
    """写回差异 → (Treeview 行数据, 被截断的条数)。"""
    items = [c for c in (changes or []) if isinstance(c, dict)]
    rows = []
    for i, c in enumerate(items[:cap]):
        old = c.get("原值") if "原值" in c else c.get("旧值")
        rows.append((str(i), (str(c.get("位置") or "—"),
                              str(c.get("字段") or "—"),
                              sfmt(old), sfmt(c.get("新值")))))
    return rows, max(0, len(items) - cap)


def _save_byte_note(diff_count, roundtrip):
    """
    写回前的「字节级结论」文字 + 级别（ok / warn / err）。

    ★ roundtrip=None 表示内核还没提供 roundtrip_ok()，这时只说差异条数，
      不硬下结论（降级路径）。
    """
    if roundtrip is True:
        return "未改动任何字段：写出的字节与原文件完全一致", "ok"
    if diff_count:
        return (f"有 {diff_count} 处改动：写出的字节与原文件不同"
                f"（改过东西本来就会变，属于预期）"), "warn"
    return ("★ 字段级比对没发现改动，但写出的字节与原文件不同：说明还有"
            "无法归因的字节差异（可能是外层封装／逐流封装重排）。"
            "建议先备份存档，再决定要不要写入。"), "err"


def _save_encoding_health(report):
    """encoding_report() → 一句话健康度摘要（拿不到报告返回「未知」）。"""
    if not isinstance(report, dict) or not report:
        return "未知（内核未提供编码标记统计）"
    bad = int(report.get("nonascii_unmarked") or 0)
    marked = int(report.get("nonascii_marked") or 0)
    susp = len(report.get("suspicious") or [])
    if bad <= 0 and susp == 0:
        return f"健康（非 ASCII 字符串都带标记：{marked} 个）"
    parts = [f"{bad} 个非 ASCII 字符串没带 UTF-8 标记"]
    if marked:
        parts.append(f"带标记 {marked} 个")
    if susp:
        parts.append(f"可疑 {susp} 处")
    return "需注意（" + "，".join(parts) + "）"


def _save_encoding_note(report):
    """编码标记的完整说明（放进读取提示条，用来解释「游戏仍报编码错」）。"""
    if not isinstance(report, dict) or not report:
        return ""
    marked = int(report.get("nonascii_marked") or 0)
    bad = int(report.get("nonascii_unmarked") or 0)
    binm = int(report.get("nonascii_binary") or 0)
    if not (marked or bad or binm):
        return ""
    txt = (f"编码标记：非 ASCII 字符串里带 UTF-8 标记 {marked} 个、"
           f"未带标记 {bad} 个")
    if binm:
        txt += f"、按二进制原样保留 {binm} 个"
    txt += "。"
    if bad:
        txt += ("★ 写回后若游戏仍报 ASCII-8BIT / UTF-8 不兼容，"
                "说明这款游戏用的是别的编码方案（不是本工具写得不对）。")
    return txt


def _save_filter_rows(rows, keyword):
    """
    按关键词过滤表格行（名字 / 编号 / 位置都能搜；空关键词原样返回）。

    ★ 行 iid 仍是数据里的原始下标，过滤只是「少显示几行」—— 筛完再选中
      一行，依然能对回正确的宝可梦 / 道具。
    """
    k = str(keyword or "").strip().lower()
    if not k:
        return list(rows or [])
    out = []
    for row in rows or []:
        try:
            iid, values = row
        except (TypeError, ValueError):
            continue
        text = (str(iid) + " "
                + " ".join(str(v) for v in (values or ()))).lower()
        if k in text:
            out.append((iid, values))
    return out


def _save_tree_col_kinds(values_rows, ncols):
    """
    判断每一列是不是「纯数字列」（用来右对齐）。

    ★ 空表 / 空单元格不算数字；只要有一格是文字，这列就按左对齐处理 ——
      「（空）」这种占位符正好落在文字一侧。
    """
    kinds = []
    for i in range(ncols):
        seen = False
        numeric = True
        for row in values_rows:
            if i >= len(row):
                continue
            txt = str(row[i]).strip()
            if not txt:
                continue
            seen = True
            if not re.fullmatch(r"-?\d+(\.\d+)?", txt):
                numeric = False
                break
        kinds.append(bool(seen and numeric))
    return kinds


# ★ 下面是旧版内核的兜底：旧内核 validate() 的「字段」用中文名（金钱 / 等级 /
#   个体值…），而表单变量键是英文（money / level / iv0…）。新版内核会在每条
#   问题里带「字段键」（稳定英文键），_highlight_save_issues 优先用它直接匹配；
#   只有没有「字段键」时才查这张表 —— 它只兜旧版内核，别指望它覆盖新增校验项。
SAVE_FIELD_ALIASES = {
    "金钱": ("money",),
    "名字": ("name",),
    "训练家名": ("name",),
    "训练家id": ("id",),
    "id": ("id",),
    "服装编号": ("outfit",),
    "语种": ("language",),
    "昵称": ("nick",),
    "等级": ("level",),
    "经验": ("exp",),
    "形态": ("form",),
    "个体值": ("iv0", "iv1", "iv2", "iv3", "iv4", "iv5"),
    "努力值": ("ev0", "ev1", "ev2", "ev3", "ev4", "ev5"),
    "hp": ("hp",),
    "招式": ("move0", "move1", "move2", "move3"),
    "pp": ("mpp0", "mpp1", "mpp2", "mpp3"),
    "亲密度": ("happy",),
    "孵化步数": ("eggsteps",),
    "pid": ("pid",),
    "初训家": ("ot",),
}


def _save_highlight_keys(field, where=""):
    """
    「校验问题里的一条」→ 要标红的输入框键名集合（已归一化）。

    ★ 先按中文别名表翻（金钱 → money），翻不出来就把原字段名归一化后原样
      返回 —— 内核以后直接给英文键名时也不用改这里。
    """
    raw = _save_norm_field(field)
    keys = set()
    for alias in (raw, _save_norm_field(where)):
        if alias and alias in SAVE_FIELD_ALIASES:
            keys.update(SAVE_FIELD_ALIASES[alias])
    if raw:
        keys.add(raw)
    return keys


def _dialog_parent(master):
    """弹窗用的父控件：传进来的是 App 时换成它的 root 窗口。"""
    if hasattr(master, "tk"):
        return master
    root = getattr(master, "root", None)
    return root if hasattr(root, "tk") else master


def _center_window(win, master, y_div=3):
    """弹窗居中到 master（与 _AskText._center 同一套算法）。"""
    try:
        x = master.winfo_rootx() + (master.winfo_width()
                                    - win.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height()
                                    - win.winfo_height()) // y_div
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    except Exception:
        pass


class SaveIssuesDialog(tk.Toplevel):
    """
    存档校验 / 读取提示的详情窗口。

    ★ 不用 messagebox 堆纯文本：问题逐条列成表格（等级 / 位置 / 字段 / 原因），
      一眼就能看出是哪个字段出的问题。
    ★ 默认按钮跟着「有没有错误级」走：有错误 → 默认「返回修改」（别手一抖
      就把坏数据写进去）；只有警告 → 默认「继续写入」。
    """

    def __init__(self, master, title, items, allow_write=False,
                 encoding_note=""):
        # ★ master 可能传进来的是 App（它没有 .tk）——Toplevel 只认控件，
        #   这里统一换成 App.root，弹窗才建得起来
        master = _dialog_parent(master)
        tk.Toplevel.__init__(self, master, bg=BG_BASE)
        self.result = "back"
        self.title(title)
        self.transient(master)
        self.minsize(640, 360)

        items = list(items or [])
        errs = [it for it in items
                if isinstance(it, dict) and str(it.get("等级")) == "错误"]

        card = RoundCard(self, radius=16, pad=16)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        body = card.body
        card.configure(width=800, height=440)

        tk.Label(body, text=title, bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        if items:
            head = (f"共 {len(items)} 条：错误 {len(errs)} 条、"
                    f"警告 {len(items) - len(errs)} 条。")
        else:
            head = "没有发现问题。"
        hl = tk.Label(body, text=head, bg=CARD,
                      fg=(ERR_COLOR if errs else C_WARN), font=FONT_B,
                      anchor="w", justify="left")
        hl.pack(fill="x", pady=(2, 6))
        bind_autowrap(hl, pad=4, minimum=200)

        wrap = tk.Frame(body, bg=CARD)
        wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(wrap, columns=[c[0] for c in SAVE_ISSUE_COLUMNS],
                            show="headings", height=12)
        for ck, ctitle in SAVE_ISSUE_COLUMNS:
            tree.heading(ck, text=ctitle)
            tree.column(ck, width=(74 if ck == "lv" else 180),
                        minwidth=60, anchor="w", stretch=(ck == "why"))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for iid, values in _save_issue_rows(items):
            tree.insert("", "end", iid=iid, values=values)
        bind_tree_wheel(tree)
        try:
            attach_tree_copy(tree, app=master)
        except Exception:
            pass

        if encoding_note:
            nl = tk.Label(body, text=encoding_note, bg=CARD, fg=C_HINT,
                          font=FONT_SMALL, anchor="w", justify="left")
            nl.pack(fill="x", pady=(6, 0))
            bind_autowrap(nl, pad=4, minimum=200)

        btns = tk.Frame(body, bg=CARD)
        btns.pack(fill="x", pady=(10, 0))
        if allow_write:
            default_write = not errs
            GlassButton(btns, "返回修改", width=110, height=38, bg=CARD,
                        font=FONT_SMALL, primary=not default_write,
                        command=self._back).pack(side="right")
            GlassButton(btns, "仍要写入", width=120, height=38,
                        primary=default_write, bg=CARD, font=FONT_SMALL,
                        command=self._write).pack(side="right", padx=8)
            self._default = "write" if default_write else "back"
        else:
            GlassButton(btns, "关闭", width=110, height=38, primary=True,
                        bg=CARD, font=FONT_SMALL,
                        command=self._back).pack(side="right")
            self._default = "back"

        self.bind("<Return>", lambda _e: self._run_default())
        self.bind("<Escape>", lambda _e: self._back())
        self.protocol("WM_DELETE_WINDOW", self._back)

        self.update_idletasks()
        _center_window(self, master)
        try:
            self.grab_set()
        except Exception:
            pass

    def _run_default(self):
        if self._default == "write":
            self._write()
        else:
            self._back()

    def _write(self):
        self.result = "write"
        self.destroy()

    def _back(self):
        self.result = "back"
        self.destroy()


class SaveWriteDialog(tk.Toplevel):
    """
    写回前确认：差异清单 + 字节级结论 + 备份 / 读档提示。

    ★ 「回游戏重新读档」这句必须留着 —— 玩家最常见的困惑就是
      「我改了存档，怎么游戏里没变化」（继续游戏不会重读存档）。
    ★ diff 为空但 roundtrip 为 False 时说明有无法归因的字节差异，
      这时默认按钮不给「写入」，先让用户看清再决定。
    """

    def __init__(self, master, sv, changes, roundtrip):
        master = _dialog_parent(master)      # ★ 同上：App 没有 .tk
        tk.Toplevel.__init__(self, master, bg=BG_BASE)
        self.result = False
        self.title("保存到存档")
        self.transient(master)
        self.minsize(720, 440)

        items = [c for c in (changes or []) if isinstance(c, dict)]
        rows, cut = _save_diff_rows(items)
        note, level = _save_byte_note(len(items), roundtrip)
        color = {"ok": OK_COLOR, "warn": WARN_COLOR,
                 "err": ERR_COLOR}.get(level, C_HINT)

        card = RoundCard(self, radius=16, pad=16)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        body = card.body
        card.configure(width=940, height=520)

        tk.Label(body, text="保存到存档", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        pl = tk.Label(body, text=f"写入这个文件：{sv.path}", bg=CARD,
                      fg=C_KEY, font=FONT_SMALL, anchor="w", justify="left")
        pl.pack(fill="x", pady=(2, 6))
        bind_autowrap(pl, pad=4, minimum=200)

        # 字节级结论先给出来：别等写完才发现对不上
        nl = tk.Label(body, text=note, bg=CARD, fg=color, font=FONT_B,
                      anchor="w", justify="left")
        nl.pack(fill="x", pady=(0, 6))
        bind_autowrap(nl, pad=4, minimum=200)

        tk.Label(body, text="下面是要写进去的字段改动（位置 / 字段 / 原值 → 新值）：",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 anchor="w").pack(anchor="w")

        wrap = tk.Frame(body, bg=CARD)
        wrap.pack(fill="both", expand=True, pady=(2, 0))
        tree = ttk.Treeview(wrap, columns=[c[0] for c in SAVE_DIFF_COLUMNS],
                            show="headings", height=13)
        for ck, ctitle in SAVE_DIFF_COLUMNS:
            tree.heading(ck, text=ctitle)
            tree.column(ck, width=(200 if ck == "where" else 130),
                        minwidth=60, anchor="w", stretch=(ck == "where"))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for iid, values in rows:
            tree.insert("", "end", iid=iid, values=values)
        bind_tree_wheel(tree)
        try:
            attach_tree_copy(tree, app=master)
        except Exception:
            pass

        if not rows:
            tk.Label(body, text="（没有任何字段被改动）", bg=CARD, fg=C_HINT,
                     font=FONT_SMALL, anchor="w").pack(anchor="w", pady=(4, 0))
        elif cut:
            tk.Label(body,
                     text=f"★ 只列出前 {SAVE_DIFF_ROW_CAP} 条，"
                          f"另有 {cut} 条改动没显示（照样会写入）。",
                     bg=CARD, fg=C_WARN, font=FONT_SMALL,
                     anchor="w").pack(anchor="w", pady=(4, 0))

        bak = str(getattr(sv, "path", "") or "") + ".bak"
        tip_txt = ""
        if not os.path.exists(bak):
            tip_txt += f"第一次保存会先生成备份 {os.path.basename(bak)}。\n"
        tip_txt += ("要在游戏里看到效果，需要回游戏重新「读档」"
                    "（继续游戏不会重读存档）。")
        tl = tk.Label(body, text=tip_txt, bg=CARD, fg=C_WARN,
                      font=FONT_SMALL, anchor="w", justify="left")
        tl.pack(fill="x", pady=(8, 0))
        bind_autowrap(tl, pad=4, minimum=200)

        btns = tk.Frame(body, bg=CARD)
        btns.pack(fill="x", pady=(10, 0))
        default_ok = level != "err"
        GlassButton(btns, "取消", width=96, height=38, bg=CARD,
                    font=FONT_SMALL,
                    command=self._cancel).pack(side="right")
        GlassButton(btns, "仍要写入" if not default_ok else "写入存档",
                    width=124, height=38, primary=default_ok, bg=CARD,
                    font=FONT_B,
                    command=self._ok).pack(side="right", padx=8)

        self.bind("<Return>", lambda _e: (self._ok() if default_ok
                                          else self._cancel()))
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        _center_window(self, master)
        try:
            self.grab_set()
        except Exception:
            pass

    def _ok(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


class SavePanel(tk.Frame):
    """
    右侧「选择游戏存档」侧边栏。

    ★ 两件事分开：
        ① 游戏根目录 —— **只当数据源**（读 .dat / PBS，决定名字/种族值/成长曲线）
        ② 存档选择   —— **完全由用户手选存档文件**（各作品命名五花八门：
           Game.rxdata / 1.rxdata / Auto 1.rxdata / 文件 A.rxdata / Partida 1.rxdata…，
           位置也各不相同，常见于 %APPDATA%\\Roaming\\<游戏名>\\，所以不做目录扫描、
           也不猜，直接让用户点文件）。
      两条信息都会记进 .runtime.json，下次打开自动带回。
    """

    def __init__(self, master, bg=CARD, width=340, app=None):
        tk.Frame.__init__(self, master, bg=bg, width=width)
        self.bg = bg
        self.app = app
        self.panel_w = width
        self.root_dir = config.Runtime.game_root or ""
        self.files: list = list(config.Runtime.save_files or [])
        self.current = None
        self.rows: dict = {}

        tk.Label(self, text="选择游戏存档", bg=bg, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=10, pady=(8, 2))
        tk.Label(self, text="「游戏数据」和「存档文件」分开选 —— 很多游戏的存档"
                            "在 AppData 里、文件名也各不相同。",
                 bg=bg, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=width - 40).pack(anchor="w", padx=10, pady=(0, 6))

        # ---- ① 游戏根目录（读数据用；可不选） ----
        tk.Label(self, text="① 游戏数据（可选）", bg=bg, fg=C_TITLE,
                 font=FONT_B).pack(anchor="w", padx=10)
        r1 = tk.Frame(self, bg=bg)
        r1.pack(fill="x", padx=10, pady=(2, 0))
        GlassButton(r1, "选游戏主程序", width=124, height=34, bg=bg,
                    font=FONT_SMALL,
                    command=self.pick_root).pack(side="left")
        self.root_lbl = tk.Label(self, text="", bg=bg, fg=C_HINT,
                                 font=FONT_SMALL, anchor="w", justify="left",
                                 wraplength=width - 40)
        self.root_lbl.pack(fill="x", padx=10, pady=(2, 6))

        # ---- ② 存档选择 ----
        tk.Label(self, text="② 存档选择", bg=bg, fg=C_TITLE,
                 font=FONT_B).pack(anchor="w", padx=10)
        r2 = tk.Frame(self, bg=bg)
        r2.pack(fill="x", padx=10, pady=(2, 2))
        GlassButton(r2, "选择存档文件", width=140, height=36, bg=bg,
                    font=FONT_B,
                    command=self.pick_file).pack(side="left")
        self.count_lbl = tk.Label(r2, text="", bg=bg, fg=C_KEY, font=FONT_BIG)
        self.count_lbl.pack(side="left", padx=(10, 0))

        # ★ 同 FilePanel：去掉内层滚动，整块面板跟着右栏卡片一起滚。
        self.list_inner = tk.Frame(self, bg=bg)
        self.list_inner.pack(fill="both", padx=6, pady=(2, 4))
        self._hint = tk.Label(
            self.list_inner,
            text="点「选择存档文件」挑一个 .rxdata\n"
                 "（可以一次选多个；列表里点一下切换）\n\n"
                 "存档一般在游戏目录里，或在\n"
                 "%APPDATA%\\Roaming\\<游戏名>\\ 这类位置。",
            bg=bg, fg=C_HINT, font=FONT_SMALL, justify="left",
            wraplength=max(120, width - 62))
        self._hint.pack(anchor="w", padx=6, pady=10)

        # ---- 底部：存档信息 + 保存按钮 ----
        # ★ 单独一帧、side="bottom" 钉在面板底边。原来按顺序 pack，面板
        #   稍微矮一点（或列表变高）整行按钮就被挤出面板、被卡片裁掉——
        #   用户截图里「保存到存档／还原备份」整个看不见（991 高的窗口）。
        foot = tk.Frame(self, bg=bg)
        foot.pack(side="bottom", fill="x")

        tk.Frame(foot, bg=CARD_BORDER, height=1).pack(fill="x", padx=10,
                                                      pady=6)

        self.title_lbl = tk.Label(foot, text="还没有选择存档", bg=bg, fg=TEXT,
                                  font=FONT_B, anchor="w", justify="left",
                                  wraplength=width - 40)
        bind_autowrap(self.title_lbl, pad=4)
        self.title_lbl.pack(fill="x", padx=10)
        self.info_lbl = tk.Label(foot, text="", bg=bg, fg=TEXT_DIM,
                                 font=FONT_SMALL, anchor="w", justify="left",
                                 wraplength=width - 40)
        bind_autowrap(self.info_lbl, pad=4)
        self.info_lbl.pack(fill="x", padx=10, pady=(2, 0))
        self.dirty_lbl = tk.Label(foot, text="", bg=bg, fg=C_WARN,
                                  font=FONT_SMALL, anchor="w", justify="left",
                                  wraplength=width - 40)
        bind_autowrap(self.dirty_lbl, pad=4)
        self.dirty_lbl.pack(fill="x", padx=10)

        btnrow = tk.Frame(foot, bg=bg)
        btnrow.pack(fill="x", padx=10, pady=(6, 6))
        self.save_btn = GlassButton(btnrow, "保存到存档", width=136, height=38,
                                    primary=True, bg=bg, font=FONT_B,
                                    command=self._save)
        self.save_btn.pack(side="left")
        GlassButton(btnrow, "还原备份", width=100, height=38, bg=bg,
                    font=FONT_SMALL, command=self._restore).pack(side="left",
                                                                 padx=6)

        self._sync_labels()
        self._render_list()

    # ---------- ① 游戏根目录 ----------
    def _initial(self):
        d = config.Runtime.last_dir
        return d if d and os.path.isdir(d) else config.BASE_DIR

    def pick_root(self):
        folder, _exe = pick_game_exe_dialog(
            self, initialdir=(self.root_dir or self._initial()),
            title="选择游戏主程序（用它的位置推游戏数据目录）")
        if folder:
            config.Runtime.set_dir(folder)
            self.set_root(folder)

    def set_root(self, folder, auto_add_saves: bool = True):
        """
        设定游戏根目录（数据源）。

        顺手看一眼它自己的 `Data/Savestates` —— 有些游戏的存档就在那里，
        列表为空时自动带进来，省得再点一次。
        """
        self.root_dir = folder or ""
        config.Runtime.set_game_root(self.root_dir)
        if auto_add_saves and self.root_dir and not self.files:
            found = ST.savestate_files(self.root_dir)
            if found:
                self.files = list(found)
                config.Runtime.set_save_files(self.files)
        self._sync_labels()
        self._render_list()

    # ---------- ② 存档选择 ----------
    def pick_file(self):
        paths = filedialog.askopenfilenames(
            title="选择存档文件（可多选；*.rxdata）",
            initialdir=(os.path.dirname(self.files[0]) if self.files
                        else self._initial()),
            filetypes=[("存档", "*.rxdata"), ("所有文件", "*.*")])
        if not paths:
            return
        paths = list(paths)
        config.Runtime.set_dir(os.path.dirname(paths[0]))
        added = [p for p in paths if p not in self.files]
        self.files.extend(added)
        config.Runtime.set_save_files(self.files)
        # ① 没选的话，试着从存档位置往上认出游戏目录
        if not self.root_dir:
            guess = ST.guess_game_root(paths[0])
            if guess and os.path.isdir(os.path.join(guess, "Data")):
                self.root_dir = guess
                config.Runtime.set_game_root(guess)
        self._sync_labels()
        self._render_list()
        self._select(added[0] if added else paths[0])

    def remove_file(self, path):
        if path in self.files:
            self.files.remove(path)
            config.Runtime.set_save_files(self.files)
        if self.current == path:
            self.current = None
        self._sync_labels()
        self._render_list()
        if self.files:
            self._select(self.files[0])

    # ---------- 列表 ----------
    def _sync_labels(self):
        if self.root_dir:
            ok = os.path.isdir(os.path.join(self.root_dir, "Data"))
            title = ST.game_title(self.root_dir)
            self.root_lbl.config(
                text=f"{os.path.basename(self.root_dir)}"
                     + (f"（{title}）" if title else "")
                     + ("　Data ✓" if ok else "　⚠ 这层没有 Data 目录"),
                fg=C_HINT if ok else C_WARN)
        else:
            self.root_lbl.config(
                text="未选择（可以不选）—— 名字/种族值会显示不全，\n"
                     "改「种族 / 道具 / 特性」等时请填**英文内部名或编号**。",
                fg=C_HINT)
        self.count_lbl.config(text=f"已选 {len(self.files)} 个" if self.files
                              else "")

    def _render_list(self):
        for w in self.list_inner.winfo_children():
            if w is not self._hint:
                w.destroy()
        self.rows = {}
        if not self.files:
            self._hint.pack(anchor="w", padx=6, pady=10)
            return
        self._hint.pack_forget()
        for p in self.files:
            self._make_row(p).pack(fill="x", padx=4, pady=2)

    def _make_row(self, path):
        name = os.path.basename(path)
        folder = os.path.dirname(path)
        parts = folder.replace("/", os.sep).split(os.sep)
        short = os.sep.join(parts[-2:]) if len(parts) > 2 else folder
        try:
            size = os.path.getsize(path)
            stamp = time.strftime("%m-%d %H:%M",
                                  time.localtime(os.path.getmtime(path)))
            sub = f"{short} · {size // 1024} KB · {stamp}"
        except OSError:
            sub = short
        box = tk.Frame(self.list_inner, bg=CARD_ALT, cursor="hand2")
        # ★ fill="x" + wraplength 跟实际宽度走：固定值在面板一窄时会把
        #   路径行末几个字裁掉
        lab = tk.Label(box, text=name, bg=CARD_ALT, fg=TEXT, font=FONT_SMALL,
                       anchor="w", justify="left",
                       wraplength=max(120, self.panel_w - 88))
        bind_autowrap(lab, pad=4, minimum=100)
        lab.pack(fill="x", padx=8, pady=(4, 0))
        sub_lab = tk.Label(box, text=sub, bg=CARD_ALT, fg=C_HINT,
                           font=(FONT_FAMILY, max(8, FONT_SIZES["small"] - 1)),
                           anchor="w", justify="left",
                           wraplength=max(120, self.panel_w - 88))
        bind_autowrap(sub_lab, pad=4, minimum=100)
        sub_lab.pack(fill="x", padx=8, pady=(0, 4))
        for w in (box, lab, sub_lab):
            w.bind("<Button-1>", lambda e, pp=path: self._select(pp))
            w.bind("<Button-3>", lambda e, pp=path: self._row_menu(e, pp))
        self.rows[path] = (box, lab, sub_lab)
        self._paint_row(path)
        return box

    def _row_menu(self, event, path):
        """右键：复制路径 / 从列表移除。"""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="复制完整路径",
                         command=lambda: clipboard_set(self, path))
        menu.add_command(label="从列表移除",
                         command=lambda: self.remove_file(path))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _paint_row(self, path):
        row = self.rows.get(path)
        if not row:
            return
        fill = ACCENT_SOFT if path == self.current else CARD_ALT
        fg = ACCENT_DEEP if path == self.current else TEXT
        box, lab, sub_lab = row
        try:
            box.configure(bg=fill)
            lab.configure(bg=fill, fg=fg)
            sub_lab.configure(bg=fill)
        except Exception:
            pass

    def _select(self, path):
        self.sync_selection(path)
        if self.app:
            # ★ 只把「游戏根目录」当数据源 —— 存档可能在 AppData 里
            self.app.select_save(path, root=self.root_dir or None)

    def sync_selection(self, path):
        """只更新高亮，不触发加载（其它侧边栏同步时用）。"""
        old, self.current = self.current, path
        for p in (old, path):
            if p:
                self._paint_row(p)

    # ---------- 概览 ----------
    def set_info(self, sv, dirty=None):
        if sv is None:
            self.title_lbl.config(text="还没有选择存档")
            self.info_lbl.config(text="")
            return
        tr = sv.g("$Trainer").ivars
        party = [p for p in (tr.get("@party") or []) if not sv.empty_slot(p)]
        bag = sv.g("$PokemonBag").ivars.get("@pockets") or []
        items = sum(len(p) for p in bag if isinstance(p, list))
        boxes = list(sv.boxes())
        in_box = sum(len([p for p in (b.ivars.get("@pokemon") or [])
                          if not sv.empty_slot(p)]) for b in boxes)
        badges = sum(1 for b in (tr.get("@badges") or []) if b)
        self.title_lbl.config(text=os.path.basename(sv.path))
        self.info_lbl.config(text=(
            f"存档格式：{sv.fmt}{'（v19+）' if sv.fmt == 'hash' else '（v16~v18）'}"
            + (f"　封装：{sv.encoding_label}" if sv.encoding_label else "")
            + "\n"
            f"主角：{sfmt(tr.get('@name'))}    ID：{sfmt(tr.get('@id'))}\n"
            f"金钱：{sfmt(tr.get('@money'))}    徽章：{badges}\n"
            f"同行：{len(party)} 只    箱子：{in_box} 只（{len(boxes)} 箱）\n"
            f"背包：{items} 种    名称来源：{sv.data.source}"))
        self.set_dirty(dirty)
        self._sync_labels()

    def set_dirty(self, dirty):
        if dirty is None:
            return
        self.dirty_lbl.config(text="● 有未保存的修改" if dirty else "已同步到文件")

    # ---------- 写回 / 还原 ----------
    def _save(self):
        if self.app:
            self.app.write_save()

    def _restore(self):
        path = self.current
        if not path:
            messagebox.showinfo("提示", "先选一份存档。", parent=self)
            return
        bak = path + ".bak"
        if not os.path.isfile(bak):
            messagebox.showinfo(
                "没有备份",
                "这份存档还没有备份。\n第一次点「保存到存档」时会自动生成 "
                f"{os.path.basename(bak)}。", parent=self)
            return
        if not messagebox.askyesno(
                "还原备份",
                f"要用备份覆盖当前存档吗？\n\n备份：{os.path.basename(bak)}\n"
                f"目标：{os.path.basename(path)}\n\n"
                "当前存档里已保存的修改会全部丢失。", parent=self):
            return
        try:
            shutil.copyfile(bak, path)
        except OSError as e:
            messagebox.showerror("还原失败", str(e), parent=self)
            return
        if self.app:
            self.app.select_save(path, force=True, root=self.root_dir or None)
        messagebox.showinfo("已还原", "备份已覆盖存档，已重新读取。", parent=self)


class PokemonForm:
    """
    宝可梦编辑表单（同行队伍与 PC 盒子共用）。

    字段联动：改种族会刷新「可用特性 / 形态」提示；点「应用修改」时把各字段
    一次性写回，**最后统一重算六项能力值**（IV/EV/性格/等级/种族/形态的联动
    都在 save_tools 里，界面只负责收集输入）。
    """

    def __init__(self, parent, app, compact=False):
        self.app = app
        self.pm = None
        self.where = ""
        self.totalhp = 0
        # ★ 种族 / 昵称联动用：记住「载入时的种族与昵称」，
        #   用户在种族下拉里换了项时据此判断要不要把昵称一起改掉。
        self._last_sid = None        # 上一次的种族编号
        self._loaded_nick = ""       # 载入时的昵称（判断用户有没有手动改过）
        self.frame = tk.Frame(parent, bg=CARD)
        self.vars = {}
        self._build(compact)

    # ---------- 取值 ----------
    def _var(self, key, default=""):
        v = tk.StringVar(value=default)
        self.vars[key] = v
        return v

    def _get_int(self, key, default=None, lo=None, hi=None):
        try:
            n = int(str(self.vars[key].get()).strip())
        except (KeyError, TypeError, ValueError):
            return default
        if lo is not None:
            n = max(lo, n)
        if hi is not None:
            n = min(hi, n)
        return n

    # ---------- 建界面 ----------
    def _build(self, compact):
        f = self.frame
        top = tk.Frame(f, bg=CARD)
        top.pack(fill="x")
        self.title_lbl = tk.Label(top, text="（先选中一只宝可梦）", bg=CARD,
                                  fg=C_TITLE, font=FONT_TITLE)
        self.title_lbl.pack(side="left")
        # ★ quick_lbl 单独一行：原来和标题挤在同一行，标题一长（长种族名 /
        #   「第 40 箱 · 第 12 格」）左边的标题就被压扁看不见
        self.quick_lbl = tk.Label(top, text="", bg=CARD, fg=C_KEY, font=FONT_B,
                                  anchor="w", justify="left")
        self.quick_lbl.pack(fill="x")
        bind_autowrap(self.quick_lbl, pad=4, minimum=120)

        # ★ 表单内容不再自己滚：整个 PokemonForm 由所在右栏卡片滚动承载。
        #   继续用 make_scroll_area 的话，画布 height=10 会在没有固定高度的
        #   父容器里塌成 0 高，整个表单看不见。
        g = tk.Frame(f, bg=CARD)
        g.pack(fill="both", pady=(6, 0))

        # --- 基本 ---
        sec = tk.Frame(g, bg=CARD)
        sec.pack(fill="x", pady=(0, 6))
        r = tk.Frame(sec, bg=CARD)
        r.pack(fill="x", pady=2)
        _lbl(r, "昵称", width=7).pack(side="left")
        _entry(r, self._var("nick"), 14).pack(side="left")
        # ★ 输入框一律显示**存档原始数据**（如 ASHPIKACHU1），框下一行
        #   只读「译文」：有游戏数据时按原始数据翻出来；没有就留空。
        #   输入框本身不再做术语表替换；有游戏数据时仍可下拉选择。
        spcol = tk.Frame(r, bg=CARD)
        spcol.pack(side="left", padx=(12, 0))
        sprow = tk.Frame(spcol, bg=CARD)
        sprow.pack(fill="x")
        _lbl(sprow, "种族", width=7).pack(side="left")
        self.sp_combo = SearchCombo(sprow, [], width=20,
                                    resolver=self._manual_resolver("species"))
        self.sp_combo.pack(side="left")
        self.sp_combo.bind("<<ComboboxSelected>>",
                           lambda e: self._refresh_species())
        self.sp_combo.bind("<FocusOut>", lambda e: self._refresh_species())
        self.sp_trans = _hint(spcol, "", fg=C_KEY)
        self.sp_trans.pack(fill="x")
        # ★ 手输提醒：下拉里找不到时可以自己填（必须用英文内部名或编号）
        self.sp_hint = _hint(sec, "以上「种族 / 性格 / 特性 / 状态 / 道具 / 招式」"
                                  "都可以直接打字手输 —— 必须用英文内部名"
                                  "（PIKACHU / MODEST / POKEBALL…）或编号；"
                                  "没选「游戏数据」时只能填内部名或编号",
                             wraplength=520)

        r2 = tk.Frame(sec, bg=CARD)
        r2.pack(fill="x", pady=2)
        _lbl(r2, "等级", width=8).pack(side="left")
        _entry(r2, self._var("level"), 6).pack(side="left")
        _lbl(r2, "经验", width=8).pack(side="left", padx=(12, 0))
        _entry(r2, self._var("exp"), 10).pack(side="left")
        _lbl(r2, "形态", width=8).pack(side="left", padx=(12, 0))
        _entry(r2, self._var("form"), 6).pack(side="left")
        # ★ 可用形态提示单独一行：塞在 r2 里会把整行顶宽（形态表长时
        #   后面的字段全被裁掉），独立一行让它自己换行
        self.form_hint = _hint(sec, "", wraplength=400)
        bind_autowrap(self.form_hint, pad=4, minimum=120)
        self.form_hint.pack(anchor="w")
        bind_autowrap(self.sp_hint, pad=4, minimum=140)
        self.sp_hint.pack(anchor="w")

        r3 = tk.Frame(sec, bg=CARD)
        r3.pack(fill="x", pady=2)
        _lbl(r3, "性格", width=8).pack(side="left")
        self.nat_combo = SearchCombo(
            r3, [(f"{n}（{ST.NATURES_EN[i]}）", i)
                 for i, n in enumerate(ST.NATURES)], width=16,
            resolver=self._manual_resolver("nature"))
        self._nat_base = list(self.nat_combo.pairs)
        self.nat_combo.pack(side="left")
        abcol = tk.Frame(r3, bg=CARD)
        abcol.pack(side="left", padx=(12, 0))
        abrow = tk.Frame(abcol, bg=CARD)
        abrow.pack(fill="x")
        _lbl(abrow, "特性", width=8).pack(side="left")
        self.ab_combo = SearchCombo(abrow, [], width=16,
                                    resolver=self._manual_resolver("ability"))
        self.ab_combo.pack(side="left")
        self.ab_trans = _hint(abcol, "", fg=C_KEY)
        self.ab_trans.pack(fill="x")

        r4 = tk.Frame(sec, bg=CARD)
        r4.pack(fill="x", pady=2)
        _lbl(r4, "当前 HP", width=8).pack(side="left")
        _entry(r4, self._var("hp"), 6).pack(side="left")
        self.hp_lbl = _hint(r4, "")
        self.hp_lbl.pack(side="left", padx=(4, 0))
        GlassButton(r4, "回满", width=64, height=30, bg=CARD, font=FONT_SMALL,
                    command=self._fill_hp).pack(side="left", padx=(10, 0))
        stcol = tk.Frame(r4, bg=CARD)
        stcol.pack(side="left", padx=(12, 0))
        strow = tk.Frame(stcol, bg=CARD)
        strow.pack(fill="x")
        _lbl(strow, "状态", width=8).pack(side="left")
        self.st_combo = SearchCombo(strow, STATUS_CHOICES, width=12,
                                    resolver=self._manual_resolver("status"))
        self.st_combo.pack(side="left")
        self.st_trans = _hint(stcol, "", fg=C_KEY)
        self.st_trans.pack(fill="x")

        # --- 个体值 / 努力值 ---
        box = tk.Frame(g, bg=CARD_ALT)
        box.pack(fill="x", pady=(4, 6))
        _lbl(box, "个体值 IV（0–31）", bg=CARD_ALT, fg=C_TITLE).pack(
            anchor="w", padx=8, pady=(6, 2))
        ivrow = tk.Frame(box, bg=CARD_ALT)
        ivrow.pack(fill="x", padx=8)
        for i, name in enumerate(EV_LABELS):
            col = tk.Frame(ivrow, bg=CARD_ALT)
            col.pack(side="left", padx=(0, 8))
            _lbl(col, name, bg=CARD_ALT, anchor="center").pack()
            _entry(col, self._var(f"iv{i}"), 4).pack()
        btn = tk.Frame(ivrow, bg=CARD_ALT)
        btn.pack(side="left", padx=(10, 0))
        for text, val in (("全 31", 31), ("全 0", 0)):
            GlassButton(btn, text, width=70, height=30, bg=CARD_ALT,
                        font=FONT_SMALL,
                        command=lambda v=val: self._set_all("iv", v)).pack(
                side="left", padx=2)

        _lbl(box, "努力值 EV（0–252，总和 ≤510）", bg=CARD_ALT,
             fg=C_TITLE).pack(anchor="w", padx=8, pady=(8, 2))
        evrow = tk.Frame(box, bg=CARD_ALT)
        evrow.pack(fill="x", padx=8)
        for i, name in enumerate(EV_LABELS):
            col = tk.Frame(evrow, bg=CARD_ALT)
            col.pack(side="left", padx=(0, 8))
            _lbl(col, name, bg=CARD_ALT, anchor="center").pack()
            _entry(col, self._var(f"ev{i}"), 4).pack()
        ebtn = tk.Frame(evrow, bg=CARD_ALT)
        ebtn.pack(side="left", padx=(10, 0))
        GlassButton(ebtn, "清空", width=64, height=30, bg=CARD_ALT,
                    font=FONT_SMALL,
                    command=lambda: self._set_all("ev", 0)).pack(side="left")
        self.ev_lbl = _lbl(ebtn, "", bg=CARD_ALT, fg=C_KEY)
        self.ev_lbl.pack(side="left", padx=(8, 0))
        for i in range(6):
            self.vars[f"ev{i}"].trace_add(
                "write", lambda *a: self._update_ev_sum())
        tk.Frame(box, bg=CARD_ALT, height=6).pack()

        # --- 招式 ---
        mv = tk.Frame(g, bg=CARD)
        mv.pack(fill="x", pady=(2, 6))
        _lbl(mv, "招式（最多 4 个；PP 留空表示用招式默认 PP）").pack(anchor="w")
        self.move_combos = []
        self.move_trans = []
        for i in range(4):
            rr = tk.Frame(mv, bg=CARD)
            rr.pack(fill="x", pady=2)
            mvcol = tk.Frame(rr, bg=CARD)
            mvcol.pack(side="left")
            mvrow = tk.Frame(mvcol, bg=CARD)
            mvrow.pack(fill="x")
            _lbl(mvrow, f"招式 {i + 1}", width=8).pack(side="left")
            cb = SearchCombo(mvrow, [], width=26,
                             resolver=self._manual_resolver("move"))
            cb.pack(side="left")
            tl = _hint(mvcol, "", fg=C_KEY)
            tl.pack(fill="x")
            self.move_trans.append(tl)
            _lbl(rr, "PP", width=4).pack(side="left", padx=(10, 0))
            _entry(rr, self._var(f"mpp{i}"), 6).pack(side="left")
            self.move_combos.append(cb)

        # --- 其它 ---
        ot = tk.Frame(g, bg=CARD)
        ot.pack(fill="x", pady=(2, 4))
        r5 = tk.Frame(ot, bg=CARD)
        r5.pack(fill="x", pady=2)
        itcol = tk.Frame(r5, bg=CARD)
        itcol.pack(side="left")
        itrow = tk.Frame(itcol, bg=CARD)
        itrow.pack(fill="x")
        _lbl(itrow, "携带道具", width=8).pack(side="left")
        self.item_combo = SearchCombo(itrow, [], width=16,
                                      resolver=self._manual_resolver("item"))
        self.item_combo.pack(side="left")
        self.item_trans = _hint(itcol, "", fg=C_KEY)
        self.item_trans.pack(fill="x")
        bdcol = tk.Frame(r5, bg=CARD)
        bdcol.pack(side="left", padx=(14, 0))
        bdrow = tk.Frame(bdcol, bg=CARD)
        bdrow.pack(fill="x")
        _lbl(bdrow, "捕获用球", width=8).pack(side="left")
        self.ball_combo = SearchCombo(bdrow, [], width=16,
                                      resolver=self._manual_resolver("item"))
        self.ball_combo.pack(side="left")
        self.ball_trans = _hint(bdcol, "", fg=C_KEY)
        self.ball_trans.pack(fill="x")

        r6 = tk.Frame(ot, bg=CARD)
        r6.pack(fill="x", pady=2)
        _lbl(r6, "亲密度", width=8).pack(side="left")
        _entry(r6, self._var("happy"), 8).pack(side="left", padx=(0, 14))
        _lbl(r6, "孵蛋步数", width=8).pack(side="left")
        _entry(r6, self._var("eggsteps"), 10).pack(side="left")

        r7 = tk.Frame(ot, bg=CARD)
        r7.pack(fill="x", pady=2)
        _lbl(r7, "异色", width=8).pack(side="left")
        self.shiny_combo = SearchCombo(r7, SHINY_CHOICES, width=16)
        self.shiny_combo.pack(side="left", padx=(0, 14))
        _lbl(r7, "勋章", width=8).pack(side="left")
        _entry(r7, self._var("ribbons"), 17).pack(side="left")

        r8 = tk.Frame(ot, bg=CARD)
        r8.pack(fill="x", pady=2)
        _lbl(r8, "初训家", width=7).pack(side="left")
        _entry(r8, self._var("ot"), 10).pack(side="left", padx=(0, 8))
        _lbl(r8, "训练家 ID", width=7).pack(side="left")
        _entry(r8, self._var("tid"), 8).pack(side="left", padx=(0, 8))
        _lbl(r8, "个体 ID", width=7).pack(side="left")
        _entry(r8, self._var("pid"), 8).pack(side="left")

        # --- 底部 ---
        foot = tk.Frame(f, bg=CARD)
        foot.pack(fill="x", pady=(6, 0))
        # ★ wraplength 跟实际宽度走：固定 760 在窄窗里会整行冲出边界被裁
        self.stat_lbl = tk.Label(foot, text="", bg=CARD, fg=TEXT_DIM,
                                 font=FONT_SMALL, justify="left", anchor="w",
                                 wraplength=760)
        bind_autowrap(self.stat_lbl, pad=8, minimum=200)
        self.stat_lbl.pack(fill="x")
        act = tk.Frame(foot, bg=CARD)
        act.pack(fill="x", pady=(4, 0))
        self.apply_btn = GlassButton(act, "应用修改", width=120, height=38,
                                     primary=True, bg=CARD, font=FONT_B,
                                     command=self.apply)
        self.apply_btn.pack(side="left")
        self.apply_btn.set_enabled(False)

    # ---------- 小联动 ----------
    def _set_all(self, kind, value):
        for i in range(6):
            self.vars[f"{kind}{i}"].set(str(value))
        self._update_ev_sum()

    def _update_ev_sum(self):
        total = sum(self._get_int(f"ev{i}", 0) or 0 for i in range(6))
        self.ev_lbl.config(
            text=f"总和 {total}" + ("（超出 510！）" if total > 510 else ""),
            fg=ERR_COLOR if total > 510 else C_KEY)

    def _fill_hp(self):
        self.vars["hp"].set(str(self.totalhp or 0))

    def _manual_resolver(self, kind):
        """本编辑器的手输解析器（见 make_manual_resolver）。"""
        return make_manual_resolver(self.app.current_save, kind,
                                    get_pm=lambda: self.pm)

    def _refresh_species(self, ab_raw=None, ab_flag=None):
        """种族/形态变了 → 刷新可用特性与形态提示，并把昵称一起同步。

        ab_raw / ab_flag：载入时存档里存着的特性内部名（Symbol）与序号 ——
        没有特性数据（游戏没给 PBS/.dat）时把它显示出来，对齐网页版。
        """
        sv = self.app.current_save()
        sid = self.sp_combo.value_of()
        if sv is None or sid is None:
            return
        form = self._get_int("form", 0) or 0
        opts = sv.data.ability_options(sid, form)
        if not opts and ab_raw is not None and ab_flag is not None:
            opts = [(f"{ab_raw}（内部名）", ab_flag)]
        self.ab_combo.set_pairs(opts, keep=False)
        forms = sv.data.forms_of(sid)
        if forms:
            self.form_hint.config(text=f"可用形态：{', '.join(map(str, forms[:12]))}",
                                  fg=C_HINT)
        else:
            self.form_hint.config(text="形态表未记录，按数字填（0 = 基础形态）",
                                  fg=C_HINT)

        # ★ 用户明确要求：**改了种族就把昵称一起改成新种族名**。
        #   否则存档里会出现「@species 是果然翁、@name 还写着电灯怪」，
        #   队伍小图标 / 图鉴大图看着跟名字对不上。
        #   只有当用户**手动输入过自定义昵称**（与载入时不同）才保留它。
        if self._last_sid is not None and sid != self._last_sid:
            new_name = sv.data.species(sid)
            cur = self.vars["nick"].get().strip()
            if cur in ("", (self._loaded_nick or "").strip()):
                self.vars["nick"].set(new_name)
                self._loaded_nick = new_name
        self._last_sid = sid

    # ---------- 载入 / 应用 ----------
    def load(self, pm, where=""):
        """
        把一只宝可梦读进表单。

        ★ 一律走 `sv.read_pokemon()`（格式无关）—— v19+ 的 @species 是 Symbol、
          @iv 是 Hash、道具是 Symbol，直接翻 ivar 会读出乱码。
        """
        sv = self.app.current_save()
        self.pm, self.where = pm, where
        if sv is None or pm is None:
            self.clear()
            return
        d = sv.data
        r = sv.read_pokemon(pm)
        sid = r["species"]
        sp_raw = r.get("species_raw")
        self._sp_raw = sp_raw
        self.title_lbl.config(text=f"{where}：{d.species_label(sid, sp_raw)}")
        sp_pairs = [(f"{n}（#{i}）", i) for n, i in d.species_list()]
        # ★ 认不出编号的种族（游戏没给 PBS/.dat）：把存档里的原始内部名作为
        #   可选项显示出来（网页版编辑器显示的就是它）；现代存档的 @species
        #   本来就是 Symbol，选中后「应用修改」也能按内部名写回
        if sid is None and sp_raw:
            sp_pairs.append((f"{sp_raw}（内部名）", sp_raw))
        self.sp_combo.set_pairs(sp_pairs, keep=False)
        # ★ 输入框显示**存档原始数据**：Symbol 内部名（现代存档）或编号
        #   （旧存档）；译文单独显示在框下一行（只读）
        if sp_raw:
            self.sp_combo.set(str(sp_raw))
        elif sid is not None:
            self.sp_combo.set(str(sid))
        else:
            self.sp_combo.set("")
        self.sp_trans.config(
            text=f"译文：{d.species(sid)}" if sid is not None else "")
        # 性格显示名跟着术语表走
        self.nat_combo.set_pairs(d.nature_options(), keep=False)
        # ★ 先认下当前种族，_refresh_species 才不会把「载入」误当成「用户改种族」
        self._last_sid = sid
        self._refresh_species(ab_raw=r.get("ability_raw"),
                              ab_flag=r.get("ability_flag"))
        # 特性：框里显示原始数据（@ability 的 Symbol 名或 flag 序号），
        # 译文行显示按游戏数据翻出来的名字
        ab_raw_sym = r.get("ability_raw")
        ab_flag_v = r.get("ability_flag")
        if ab_raw_sym:
            self.ab_combo.set(str(ab_raw_sym))
        elif ab_flag_v is not None:
            self.ab_combo.set(str(ab_flag_v))
        else:
            self.ab_combo.set("")
        ab_nm = r.get("ability_name")
        if ab_nm and (not ab_raw_sym or str(ab_nm) != str(ab_raw_sym)):
            self.ab_trans.config(text=f"译文：{ab_nm}")
        else:
            self.ab_trans.config(text="")

        self.vars["nick"].set(str(r.get("name") or ""))
        self._loaded_nick = str(r.get("name") or "")
        self.vars["level"].set(str(r["level"]))
        self.vars["exp"].set(str(r["exp"]))
        self.vars["form"].set(str(r.get("form") or 0))
        self.nat_combo.set_value(r["nature"])
        for i in range(6):
            self.vars[f"iv{i}"].set(str(r["ivs"][i]))
            self.vars[f"ev{i}"].set(str(r["evs"][i]))
        self._update_ev_sum()
        self.totalhp = r.get("totalhp") or 0
        self.vars["hp"].set(str(r.get("hp") or 0))
        self.st_combo.set_value(r["status"])
        self.st_trans.config(text="")          # 状态是内置枚举，无译文行

        items = [("（无）", 0)] + [(f"{n}（#{i}）", i) for n, i in d.item_list()]
        self.item_combo.set_pairs(items, keep=False)
        self.ball_combo.set_pairs([("（未知）", 0)] +
                                  [(f"{n}（#{i}）", i) for n, i in d.item_list()],
                                  keep=False)
        # ★ 道具 / 球：框里显示存档原始数据（Symbol 内部名或编号），译文在框下
        it_raw = r.get("item_raw")
        it_id = r.get("item") or 0
        if it_raw:
            self.item_combo.set(str(it_raw))
        elif it_id:
            self.item_combo.set(str(it_id))
        else:
            self.item_combo.set("（无）")
        self.item_trans.config(
            text=f"译文：{d.item(it_id)}" if it_id else "")
        bd_raw = r.get("ball_raw")
        bd_id = r.get("ball") or 0
        if bd_raw:
            self.ball_combo.set(str(bd_raw))
        elif bd_id:
            self.ball_combo.set(str(bd_id))
        else:
            self.ball_combo.set("（未知）")
        self.ball_trans.config(
            text=f"译文：{d.item(bd_id)}" if bd_id else "")

        self.vars["happy"].set(str(r.get("happiness") or 0))
        self.vars["eggsteps"].set(str(r.get("eggsteps") or 0))
        sf = r.get("shiny")
        self.shiny_combo.set_value("auto" if sf is None
                                   else ("yes" if sf else "no"))
        rb = r.get("ribbons")
        if isinstance(rb, list):
            txt = ",".join(str(x) for x in rb)
        else:
            txt = "" if rb is None else str(rb)
        self.vars["ribbons"].set(txt)
        self.vars["ot"].set(str(r.get("ot") or ""))
        self.vars["tid"].set(str(r.get("ot_id") or 0))
        self.vars["pid"].set(str(r.get("pid") or 0))

        moves = [("（空）", 0)] + [(f"{n}（#{i}）", i) for n, i in d.move_list()]
        arr = r["moves"]
        moves_raw = r.get("moves_raw") or []
        for i in range(4):
            # ★ 认不出编号的招式（游戏没给 moves 数据）：把存档里的原始内部名
            #   作为可选项显示出来；现代存档的招式 @id 是 Symbol，能按名写回
            extra = []
            if i < len(arr) and not arr[i][0] and i < len(moves_raw) \
                    and moves_raw[i]:
                extra = [(f"{moves_raw[i]}（内部名）", moves_raw[i])]
            self.move_combos[i].set_pairs(moves + extra, keep=False)
            # ★ 框里显示**存档原始数据**（内部名 / 编号），译文显示在框下
            m_raw = moves_raw[i] if i < len(moves_raw) else None
            m_id = arr[i][0] if i < len(arr) else 0
            if i >= len(arr):
                self.move_combos[i].set("（空）")
                self.move_trans[i].config(text="")
            elif m_raw:
                self.move_combos[i].set(str(m_raw))
                self.move_trans[i].config(
                    text=f"译文：{d.move(m_id)}" if m_id else "")
            elif m_id:
                self.move_combos[i].set(str(m_id))
                self.move_trans[i].config(text=f"译文：{d.move(m_id)}")
            else:
                self.move_combos[i].set("（空）")
                self.move_trans[i].config(text="")
            if i < len(arr):
                self.vars[f"mpp{i}"].set(str(arr[i][1] or ""))
            else:
                self.vars[f"mpp{i}"].set("")

        self.apply_btn.set_enabled(True)
        # 「当前 HP」输入框里已经有当前值，这里只显示上限，省下的宽度
        # 给同一行的「状态」下拉
        self.hp_lbl.config(text=f"/ {self.totalhp}")
        self._show_stats(pm)



    def clear(self):
        self.pm = None
        self.totalhp = 0
        self._last_sid = None
        self._loaded_nick = ""
        self.title_lbl.config(text="（先选中一只宝可梦）")
        self.quick_lbl.config(text="")
        self.stat_lbl.config(text="")
        self.hp_lbl.config(text="")
        for lbl in ([getattr(self, "sp_trans", None),
                     getattr(self, "ab_trans", None),
                     getattr(self, "item_trans", None),
                     getattr(self, "ball_trans", None)]
                    + list(getattr(self, "move_trans", []))):
            if lbl is not None:
                lbl.config(text="")
        self.apply_btn.set_enabled(False)

    def _show_stats(self, pm):
        sv = self.app.current_save()
        if sv is None:
            return
        d = sv.pokemon(pm)
        stored = [d["能力值"][k] for k in EV_LABELS]
        self.quick_lbl.config(
            text="  ".join(f"{EV_LABELS[i]} {sfmt(stored[i])}"
                           for i in range(6)))
        sid = d["全国图鉴编号"]
        form = d.get("形态") or 0
        base_v = sv.data.base_stats(sid, form)
        # 读不到种族值时 base_stats 兜底成全 1 —— 别把 [1,1,1,1,1,1]
        # 当真数据显示出来（没有 PBS/.dat 的同人游戏）
        base_txt = ("未知（无游戏数据）" if all(b == 1 for b in base_v)
                    else str(base_v))
        self.stat_lbl.config(
            text=("六项能力值（由种族/等级/IV/EV/性格算出）："
                  + "  ".join(f"{EV_LABELS[i]} {sfmt(stored[i])}"
                              for i in range(6))
                  + f"\nHP {d['HP']}"
                  + ("" if d.get("能力值已缓存", True)
                     else "    （这份存档不缓存能力值，数值是现算的）")
                  + f"    种族值 {base_txt}"
                  + f"    种族 {d['宝可梦']}"
                  + (f"（形态 {form}）" if form else "")
                  + f"    属性 {sv.data.type_names_of(sid, form)}"))

    def _parse_int(self, key, lo=None, hi=None, empty_ok=True):
        """
        把输入框解析成整数。返回 ``(值, 提示)``：

        * 空且 empty_ok → ``(None, None)``（表示「这一项不修改」）
        * 不是整数 → ``(None, "要填整数…")``
        * 超出 [lo, hi] → ``(截断值, "已按 X 写入")``（截断 + 警告，不阻止）
        * 正常 → ``(值, None)``
        """
        t = str(self.vars[key].get()).strip()
        if not t and empty_ok:
            return None, None
        if not t:
            return (lo if lo is not None else 0), None
        try:
            n = int(t)
        except ValueError:
            return None, f"要填整数（收到「{t}」）"
        if lo is not None and n < lo:
            return lo, f"「{t}」小于下限 {lo}，已按 {lo} 写入"
        if hi is not None and n > hi:
            return hi, f"「{t}」大于上限 {hi}，已按 {hi} 写入"
        return n, None

    def apply(self):
        sv = self.app.current_save()
        pm = self.pm
        if sv is None or pm is None:
            messagebox.showinfo("提示", "先选中一只宝可梦。", parent=self.frame)
            return
        # ★ 所有字段都允许手输；**填错只警告、不阻止**：
        #   逐项写入，写得动的照常写，写不动的（认不出 / 不是整数）收集成
        #   problems，最后一次性弹出来。原来「预检不通过就整体 return」的
        #   逻辑会让人改 10 个字段时因为 1 个填错全丢，已去掉。
        problems = []

        def put(label, fn):
            try:
                fn()
            except Exception as e:                              # noqa: BLE001
                problems.append(f"{label}：{e}")

        # 种族（空 = 不改种族）
        sid = self.sp_combo.value_or_text()
        if sid in (None, ""):
            sid = sv.read_pokemon(pm)["species"]
        # 经验要写在「等级」前面：两个都填时以等级为准（等级会重算经验）
        exp = self.vars["exp"].get().strip()
        if exp:
            try:
                sv.set_pokemon(pm, "经验", int(exp), recalc=False)
            except ValueError:
                problems.append(f"经验要填整数（收到「{exp}」），未修改")
        # ★ sid 仍是 None（认不出编号、也没有内部名可写）时跳过：
        #   写 0 只会让 core 报「种族认不出来」，不如原样不动
        if sid not in (None, ""):
            put("种族", lambda: sv.set_pokemon(pm, "种族", sid, recalc=False))

        form, warn = self._parse_int("form", 0)
        if warn:
            problems.append(f"形态{warn}，未修改" if form is None else f"形态{warn}")
        if form is not None:
            put("形态", lambda: sv.set_pokemon(pm, "形态", form, recalc=False))

        put("昵称", lambda: sv.set_pokemon(pm, "昵称", self.vars["nick"].get()))

        level, warn = self._parse_int("level", 1, 100)
        if warn:
            problems.append(f"等级{warn}，未修改" if level is None else f"等级{warn}")
        if level is not None:
            put("等级", lambda: sv.set_pokemon(pm, "等级", level, recalc=False))

        # 个体值 / 努力值：六个框一个不合法就整项跳过（空 = 0）
        for prefix, label, hi in (("iv", "个体值", 31), ("ev", "努力值", 255)):
            vals, bad = [], None
            for i in range(6):
                t = self.vars[f"{prefix}{i}"].get().strip()
                if not t:
                    vals.append(0)
                    continue
                try:
                    vals.append(int(t))
                except ValueError:
                    bad = t
                    break
            if bad is not None:
                problems.append(f"{label}要填整数（收到「{bad}」），未修改")
                continue
            vals = [max(0, min(hi, v)) for v in vals]
            put(label, lambda k=label, v=vals: sv.set_pokemon(
                pm, k, v, recalc=False))

        nat = self.nat_combo.value_or_text()
        if nat is not None:
            put("性格", lambda: sv.set_pokemon(pm, "性格", nat, recalc=False))
        ab = self.ab_combo.value_or_text()
        if ab is not None:
            put("特性", lambda: sv.set_pokemon(pm, "特性", ab, recalc=False))

        # 招式：四个格子共用一次写入，逐格预检，认不出的格子按「空招式」
        #   跳过（其余格子照常写），PP 填错就用招式默认 PP。
        raw_moves = []
        for i in range(4):
            mv = self.move_combos[i].value_or_text()
            pp = self.vars[f"mpp{i}"].get().strip()
            if mv not in (None, "", 0):
                _v, err = sv.coerce_ref(mv, "move")
                if err:
                    problems.append(f"招式 {i + 1}：{err}")
                    mv = 0
            if pp:
                try:
                    int(pp)
                except ValueError:
                    problems.append(
                        f"招式 {i + 1} 的 PP 要填整数（收到「{pp}」），"
                        f"已改用默认 PP")
                    pp = None
            raw_moves.append((mv or 0, pp or None))
        put("招式", lambda: sv.set_moves(pm, raw_moves))

        put("携带道具", lambda: sv.set_pokemon(
            pm, "携带道具", self.item_combo.value_or_text() or 0))
        put("捕获用球", lambda: sv.set_pokemon(
            pm, "捕获用球", self.ball_combo.value_or_text() or 0))

        for prefix, field, disp, lo, hi in (
                ("happy", "亲密度", "亲密度", 0, 255),
                ("eggsteps", "孵蛋步数", "孵蛋步数", 0, None),
                ("tid", "训练家ID", "训练家 ID", 0, None),
                ("pid", "个体ID", "个体 ID", 0, None)):
            v, warn = self._parse_int(prefix, lo, hi)
            if warn:
                problems.append(f"{disp}{warn}，未修改" if v is None
                                else f"{disp}{warn}")
            if v is not None:
                put(disp, lambda k=field, x=v: sv.set_pokemon(pm, k, x,
                                                              recalc=False))

        put("状态", lambda: sv.set_pokemon(
            pm, "状态", self.st_combo.value_or_text() or 0))
        sf = self.shiny_combo.value_of()
        put("异色", lambda: sv.set_pokemon(
            pm, "异色", None if sf in (None, "auto") else (sf == "yes")))
        put("勋章", lambda: sv.set_pokemon(pm, "勋章",
                                           self.vars["ribbons"].get()))
        put("初训家", lambda: sv.set_pokemon(pm, "初训家",
                                             self.vars["ot"].get()))

        hp, warn = self._parse_int("hp", 0)
        if warn:
            problems.append(f"当前 HP{warn}，未修改" if hp is None
                            else f"当前 HP{warn}")
        if hp is not None:
            put("当前 HP", lambda: sv.set_pokemon(pm, "当前HP", hp))

        # 努力值超上限：只警告，不阻止（游戏会自己裁掉）
        ev_sum = sum(self._get_int(f"ev{i}", 0) or 0 for i in range(6))
        if ev_sum > 510:
            messagebox.showwarning(
                "努力值超出上限",
                f"努力值总和 {ev_sum}，超过游戏的 510 上限。\n"
                "游戏里超出部分会被裁掉，实际数值可能与此处不一致。\n"
                "已按填写值写入。", parent=self.frame)

        # ★ 前面都关掉了自动重算，这里统一算一次六项能力值
        try:
            sv.recalc_pokemon(pm)
        except Exception as e:                                  # noqa: BLE001
            problems.append(f"能力值重算失败：{e}")

        self.app.mark_dirty()
        self.app.refresh_save_lists()
        self.load(pm, self.where)
        self.stat_lbl.config(
            text=self.stat_lbl.cget("text") + "      ✔ 已按新数值重算能力值")
        if problems:
            messagebox.showwarning(
                "部分字段没写进去",
                "以下字段填写有误或写不进这份存档，已跳过"
                "（其他字段照常改好）：\n\n"
                + "\n".join(f"· {p}" for p in problems)
                + "\n\n" + ST.GameData.MANUAL_INPUT_HINT,
                parent=self.frame)


# ================================================================
# 编辑窗口里，每类文件给一句「这界面怎么用」的说明
PBS_FORM_HINTS = {
    "generic": "一行一个字段，改完点右上角「保存到 txt」；"
               "「编译到 .dat」会顺手把它写进游戏。",
    "trainers": "段名 = 训练家类型,名字,版本。\n"
                "下面每一只宝可梦一块：种族、等级，以及招式／道具／努力值等。",
    "encounters": "每一类遭遇一块：上面是「类型,步数概率」，\n"
                  "下面一行一条槽位「概率,种族,最低级,最高级」。",
    "townmap": "一个区域一段：编号 + 名字 + 图片文件名，\n地点写成「x,y,名字,说明」。",
    "connections": "一张连接一行：地图A,边A(N/S/E/W),坐标A,地图B,边B,坐标B。",
    "regional": "一个图鉴一段，名单里一行若干只（逗号分隔）。",
    "phone": "消息一行一条（同一类可以有好几条）。",
    "facility": "一组一个段：训练家名单文件 + 宝可梦名单文件。",
    "metadata": "第 0 段是全局设置，后面是玩家角色。",
}


class PbsGamePanel(tk.Frame):
    """
    右侧「选择游戏主程序」侧边栏（PBS 编辑用）。

    和存档编辑那块一样：**选 exe 不选目录**（exe 只有那一个，选它不会选错层，
    根目录由 exe 位置推出）。选好后显示：
      · 游戏名 / Data 目录在不在
      · 识别到的 Essentials 版本族（v19 / v20 / v21）
      · PBS 文件夹里已经有哪些 txt
    """

    def __init__(self, master, bg=CARD, width=340, app=None):
        tk.Frame.__init__(self, master, bg=bg, width=width)
        self.bg = bg
        self.app = app
        self.panel_w = width
        self.root_dir = config.Runtime.game_root or ""
        self.family = ""

        tk.Label(self, text="选择游戏主程序", bg=bg, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=10, pady=(8, 2))
        tk.Label(self, text="PBS 的三个动作都在这一个游戏上进行 —— "
                            "提取写到它的 PBS 文件夹，编译写回它的 Data 文件夹。",
                 bg=bg, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=width - 40).pack(anchor="w", padx=10, pady=(0, 6))

        r1 = tk.Frame(self, bg=bg)
        r1.pack(fill="x", padx=10, pady=(2, 0))
        GlassButton(r1, "选游戏主程序", width=140, height=40, primary=True,
                    bg=bg, font=FONT_B, command=self.pick_root).pack(side="left")
        GlassButton(r1, "打开PBS文件夹", width=132, height=40, bg=bg,
                    font=FONT_SMALL,
                    command=self.open_pbs_dir).pack(side="left", padx=(8, 0))

        self.root_lbl = tk.Label(self, text="", bg=bg, fg=C_HINT,
                                 font=FONT_SMALL, anchor="w", justify="left",
                                 wraplength=width - 40)
        self.root_lbl.pack(fill="x", padx=10, pady=(6, 2))
        bind_autowrap(self.root_lbl, pad=4)

        self.info_lbl = tk.Label(self, text="", bg=bg, fg=TEXT_DIM,
                                 font=FONT_SMALL, anchor="w", justify="left",
                                 wraplength=width - 40)
        self.info_lbl.pack(fill="x", padx=10, pady=(2, 0))
        bind_autowrap(self.info_lbl, pad=4)

        tk.Frame(self, bg=CARD_BORDER, height=1).pack(fill="x", padx=10,
                                                      pady=8)
        tk.Label(self, text="游戏里的 PBS 文件", bg=bg, fg=C_TITLE,
                 font=FONT_B).pack(anchor="w", padx=10)

        # ★ 同 FilePanel：去掉内层滚动，整块面板跟着右栏卡片一起滚。
        self.list_inner = tk.Frame(self, bg=bg)
        self.list_inner.pack(fill="both", padx=6, pady=(2, 4))
        self._hint = tk.Label(
            self.list_inner,
            text="先在上面选好游戏。\n\n支持的版本：Essentials v19 / "
                        "v20 / v21（v16～v18 的老游戏\n自带 PBS 目录，"
                        "交给游戏自己编译就行）。",
            bg=bg, fg=C_HINT, font=FONT_SMALL, justify="left",
            wraplength=max(120, width - 62))
        self._hint.pack(anchor="w", padx=6, pady=10)

        self._sync()

    # ---------- 选游戏 ----------
    def _initial(self):
        d = config.Runtime.last_dir
        return d if d and os.path.isdir(d) else config.BASE_DIR

    def pick_root(self):
        folder, _exe = pick_game_exe_dialog(
            self, initialdir=(self.root_dir or self._initial()),
            title="选择游戏主程序（用它的位置推游戏目录）")
        if folder:
            config.Runtime.set_dir(folder)
            self.set_root(folder)

    def set_root(self, folder):
        self.root_dir = folder or ""
        config.Runtime.set_game_root(self.root_dir)
        self._sync()
        if self.app is not None:
            self.app.on_pbs_root_changed()

    def open_pbs_dir(self):
        if not self.root_dir:
            messagebox.showinfo("提示", "还没选游戏。")
            return
        d = pbs_edit.pbs_dir(self.root_dir)
        try:
            os.makedirs(d, exist_ok=True)
            if hasattr(os, "startfile"):
                os.startfile(d)
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:                                  # noqa: BLE001
            messagebox.showwarning("打开失败", str(e))

    # ---------- 显示 ----------
    def _sync(self):
        if not self.root_dir:
            self.root_lbl.config(text="未选择")
            self.info_lbl.config(text="")
            self._render_list([])
            return
        ok = os.path.isdir(os.path.join(self.root_dir, "Data"))
        fam, why = (pbs_edit.detect_family(self.root_dir)
                    if ok else ("", ""))
        self.family = fam
        title = ""
        try:
            title = ST.game_title(self.root_dir) or ""
        except Exception:
            pass
        self.root_lbl.config(
            text="%s%s" % (os.path.basename(self.root_dir),
                           ("（%s）" % title) if title else "")
            + ("　Data ✓" if ok else "　⚠ 这层没有 Data 目录"),
            fg=C_HINT if ok else C_WARN)
        if ok:
            if fam:
                self.info_lbl.config(text="版本族：%s（%s）" % (fam, why),
                                     fg=C_KEY)
            else:
                self.info_lbl.config(
                    text="⚠ 认不出版本：%s\n（支持 Essentials v16 ~ v21.1）" % why,
                    fg=C_WARN)
        else:
            self.info_lbl.config(text="")
        files = pbs_edit.list_pbs_txt(self.root_dir, fam) if fam else []
        self._render_list(files)

    def _render_list(self, files):
        for w in self.list_inner.winfo_children():
            if w is not self._hint:
                w.destroy()
        if not files:
            self._hint.pack(anchor="w", padx=6, pady=10)
            return
        self._hint.pack_forget()
        for f in files:
            row = tk.Frame(self.list_inner, bg=CARD)
            row.pack(fill="x", padx=4, pady=2)
            tk.Label(row, text=f["name"], bg=CARD, fg=TEXT,
                     font=FONT_SMALL, anchor="w").pack(side="left")
            tk.Label(row, text=("%.1f KB" % (f["size"] / 1024.0)), bg=CARD,
                     fg=C_HINT, font=FONT_SMALL).pack(side="right")


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

        # 存档编辑（菜单 6）
        self.save_panels = []      # 各页右侧的「选择游戏存档」侧边栏
        self.save_path = None      # 当前选中的存档
        self.save_obj = None       # 当前存档的 SaveFile（全局共用一份）
        # ★ 页面顶部的「读取提示」条 / 校验标红的输入框，统一记在这里，
        #   切存档和重新校验时才能一次性清干净（不记住旧控件就清不掉）
        self._save_bars = {}       # 页面键 → 顶部「读取提示」条 Frame
        self._save_highlights = []  # [(控件, 原 style), ...]（校验标红用）
        self._save_left = {}       # 页面键 → 该页左半区 Frame（找输入框用）
        self._save_search = {}     # 页面键 → (搜索用 StringVar, 输入框)

        # PBS 编辑（菜单 3）
        self.pbs_panel = None      # 右侧「选择游戏主程序」侧边栏
        self.pbs_doc = None        # 编辑窗口里正在改的那份文档
        self.pbs_doc_path = ""
        self.pbs_cur_idx = None    # 当前条目下标
        self.pbs_file_list = []    # 左侧 txt 列表
        self.pbs_file_box = None
        self.pbs_form_getters = [] # 表单里每个字段的「取当前值」回调
        self.save_dirty = False    # 有未保存的修改

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

        # 「术语字典」视图（与 Excel 转换视图共用一个页面）
        self.excel_view = None      # Excel 转换视图
        self.termdict_view = None   # 术语字典列表视图
        self.dict_editor = None     # dict_editor.TermDictEditor（首次进入时建）
        self.dict_loaded = False    # 视图是否已渲染过
        self.dict_checks = set()    # 勾选的行（用原始原文标识）
        self.dict_row_orig = {}     # 列表 iid → 原始原文
        self.dict_visible = []      # 当前可见的原始原文（顺序同列表）
        self.dict_show_limit = DE.VIEW_LIMIT_DEFAULT

        # 本地模型服务（菜单 4）
        self.pv_param_vars = {}    # config key → StringVar
        self._pv_btn_groups = []   # 提供商分段按钮组
        self._pv_models = []       # 当前列表里的模型行
        self._pv_adapt_text = ""   # 右侧适配清单（供复制）

        self._style()
        self._build_root()
        self._build_sidebar()
        self._build_content()
        self._build_status()
        self._bind_save_hotkeys()   # ★ Ctrl+S / F5 / Ctrl+F（只在存档页生效）

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

        self.show("home")      # ★ 启动首页 = 主页（点头像随时回来）

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
        # ★ 存档校验标红用：出问题的字段输入框换成这个 style（改回
        #   "TEntry" 即清除）。用语义色常量，不另开一套配色。
        st.configure("SaveErr.TEntry", fieldbackground="#FDECEA",
                     bordercolor=ERR_COLOR, lightcolor=ERR_COLOR,
                     darkcolor=ERR_COLOR, foreground=TEXT, padding=3)
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
        # ★ 点头像 → 主页
        Avatar(head, size=76, path=config.AVATAR_FILE,
               on_click=lambda: self.show("home")).pack(anchor="w")

        tk.Frame(body, bg=CARD_BORDER, height=1).pack(fill="x", pady=(2, 8))

        # ★ 菜单装不下时整列可以上下滑动（菜单项变多 / 窗口变矮都靠它）
        outer, mbody = make_scroll_area(body, bg=CARD)
        outer.pack(fill="both", expand=True)

        for idx, name in MENU_ITEMS:
            btn = MenuItem(mbody, idx, name,
                           command=lambda k=MENU_KEYS[idx]: self.show(k))
            btn.pack(fill="x", pady=4)
            self.menu_btns[MENU_KEYS[idx]] = btn

        tip = tk.Label(body, text="点头像回主页 · 悬停看作者信息", bg=CARD,
                       fg=C_HINT, font=FONT_SMALL)
        tip.pack(side="bottom", pady=(8, 0))

    # ---------------- 内容区 ----------------
    def _build_content(self):
        holder = tk.Frame(self.root, bg=BG_BASE)
        holder.grid(row=0, column=1, sticky="nsew", padx=(6, 14), pady=14)
        holder.grid_rowconfigure(0, weight=0)      # 顶部「返回」条
        holder.grid_rowconfigure(1, weight=1)      # 页面本体
        holder.grid_columnconfigure(0, weight=1)
        self.content_holder = holder

        # ★ 子页面顶部条：只有进「游戏汉化」的子菜单时才出现
        #   （平时 grid_remove → row0 高度塌成 0，页面仍占满整块区域）
        self.sub_header = tk.Frame(holder, bg=BG_BASE)
        self.sub_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.sub_back = GlassButton(self.sub_header, "← 返回", width=148,
                                    height=38, bg=BG_BASE, font=FONT_SMALL,
                                    command=self._on_sub_back)
        self.sub_back.pack(side="left")
        self.sub_title = tk.Label(self.sub_header, text="", bg=BG_BASE,
                                  fg=C_TITLE, font=FONT_TITLE)
        self.sub_title.pack(side="left", padx=(12, 0))
        self.sub_header.grid_remove()

        for key in list(MENU_KEYS.values()) + list(SUBMENU_KEYS):
            page = tk.Frame(holder, bg=BG_BASE)
            page.grid(row=1, column=0, sticky="nsew")
            bgc = tk.Canvas(page, highlightthickness=0, bg=BG_BASE)
            bgc.place(x=0, y=0, relwidth=1, relheight=1)
            bgc.bind("<Configure>",
                     lambda e, c=bgc: paint_bg(c, e.width, e.height))
            self.pages[key] = page

        # ★ 文本保护规则：进界面就先装一次（smart/custom 模式下生效）
        try:
            import text_rules
            text_rules.ensure_applied()
        except Exception as _e:
            log.warning("文本保护规则装载失败（用内置规则继续）：%s", _e)

        self._page_home()
        self._page_intl()
        self._page_hanhua()
        self._page_termextract()
        self._page_termcheck()
        self._page_translate()
        self._page_report()
        self._page_terms()
        self._page_prefix()
        self._page_polish()
        self._page_reflow()
        self._page_excel()
        self._page_settings()
        self._page_provider()
        self._page_debug()
        self._page_saveedit()
        self._page_save_trainer()
        self._page_save_party()
        self._page_save_bag()
        self._page_save_box()
        self._page_save_switch()
        self._page_pbsedit()
        self._page_pbs_editor()
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
        # ★ 子页面（被「游戏汉化」/「存档编辑」统合进来的那些）在左侧没有自己的
        #   按钮，高亮统一落在上级菜单上，并显示顶部返回条。
        active = SUBMENU_PARENT.get(key, key)
        for k, btn in self.menu_btns.items():
            btn.set_active(k == active)
        self._sync_sub_header(key)
        if key == "terms":
            self._load_term_rows()
        elif key == "prefix":
            self._load_prefix_rows()
        elif key == "reflow":
            self._load_reflow_blocks()
        elif key == "provider":
            self._pv_refresh()
        elif key == "saveedit":
            self._refresh_save_overview()
        elif key in SAVE_SUBMENUS_KEYS:
            self._refresh_save_page(key)
        elif key == "pbsedit":
            if getattr(self, "pbs_panel", None) is not None:
                self.pbs_panel._sync()
        elif key == "pbs_editor":
            self._pbs_reload_file_list()
        elif key == "log":
            pass

    def _on_sub_back(self):
        """顶部「← 返回」条：回到当前子页面的上级页面。"""
        self.show(SUBMENU_PARENT.get(self.current, "home"))

    def _sync_sub_header(self, key):
        """在子页面里显示顶部返回条（文字按上级页面变），其它页面隐藏。"""
        try:
            if key in SUBMENU_KEYS:
                parent = SUBMENU_PARENT.get(key, "hanhua")
                self.sub_title.config(text=SUBMENU_TITLES.get(key, ""))
                self.sub_back.config(text=BACK_TEXTS.get(
                    parent, "← 返回" + SUBMENU_TITLES.get(parent, "")))
                self.sub_header.grid()
                self.sub_header.tkraise()
            else:
                self.sub_header.grid_remove()
        except Exception:
            pass

    def _make_file_panel(self, holder, mode, allow_game_root=False,
                         on_game_root=None):
        """统一创建右侧文件侧边栏，并把「翻译」页的选择同步给其它子页面。"""
        fp = FilePanel(holder.body, bg=CARD, mode=mode,
                       on_change=self._sync_file_panels, app=self,
                       allow_game_root=allow_game_root,
                       on_game_root=on_game_root)
        fp.pack(fill="both", expand=True)
        self.file_panels.append(fp)
        return fp

    def _drop_names_files(self, paths, action=""):
        """
        菜单 2–7 的公共入口：把**名字类文件**从待处理清单里剔除。

        名字文件（*_NAMES / 开头 [编号] 是名字区块的那批）归「术语提取」管，
        翻译 / 检查报告 / 术语重翻 / 中文润色 / 换行重排都不该碰它们 ——
        否则同一批名词会被两条流水线各翻一遍，译法还可能不一致。

        返回过滤后的清单；有跳过时弹一次提示（最多列 5 个文件名）。
        """
        import term_extract as TE

        keep, skipped = TE.split_out_names_files(paths)
        if skipped:
            names = "、".join(os.path.basename(p) for p in skipped[:5])
            more = f" 等 {len(skipped)} 个" if len(skipped) > 5 else ""
            messagebox.showinfo(
                "已跳过名字类文件",
                f"{action or '该操作'}不处理名字类文本，已跳过：\n{names}{more}\n\n"
                f"名字类文件请在「游戏汉化 → 术语提取」里处理。")
        return keep

    def _sync_file_panels(self, paths):
        """
        「游戏汉化 → 翻译」页选中文件后，自动同步到其它子页面。

        ★ 各菜单认的文件不一样，这里统一做一次换算：
            重翻检查报告 → 检查报告 *_translated_report.txt
            术语重翻 / 中文润色 → 翻译缓存 *_cache.json
            换行重排 → 译文 *_translated.txt
            前缀字典 → 字典文件固定，不同步
          源文件的换算走 commands.source_of()，所以把缓存 / 译文直接拖进来也能认。
        """
        paths = list(paths or [])
        # ★ 先统一换回源文件：术语重翻 / 润色里勾的是缓存、换行重排里勾的是译文，
        #   直接同步过去会把这些文件塞进翻译页，翻译时会当成文本去读。
        base = [commands.source_of(p) for p in paths]
        for fp in self.file_panels:
            if fp is None or not fp.winfo_exists():
                continue
            if fp.mode == "report":
                target = [commands.report_path_for(p) for p in base]
            elif fp.mode == "cache":
                target = [commands.cache_path_for(p) for p in base]
            elif fp.mode == "translated":
                target = [commands.translated_path_for(p) for p in base]
            elif fp.mode == "dict":
                continue                      # 固定字典文件，别动它
            else:
                target = base
            target = [t for t in target if t and os.path.exists(t)]
            if not target:
                continue
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
                elif kind == "termcheck":
                    self.set_busy(False, "术语检查完成")
                    self._fill_termcheck(payload)
                elif kind == "termcheck_applied":
                    self._after_tc_applied(payload)
                elif kind == "termcheck_retranslated":
                    self._after_tc_retranslated(payload)
                elif kind == "conflict_applied":
                    self.set_busy(False, "已应用手工编辑")
                    self._after_conflict_applied(payload)
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
                            txt += (f"\n语言表：已加入 "
                                    f"{lang.get('entry') or '[\"Chinese\", …]'}"
                                    f"（复制第一条语言并改名）"
                                    + ("；原本被注释的那条已取消注释"
                                       if lang.get("uncommented") else ""))
                        elif lang:
                            txt += f"\n语言表：{lang.get('reason') or '没有改动'}"
                        self.intl_compile_lbl.config(text=txt)
                elif kind == "plugin_done":
                    r = (payload or [{}])[0] if isinstance(payload, list) else {}
                    fam = r.get("font", "")
                    ver = r.get("variant", "")
                    how = "塞进脚本" if r.get("mode") == "scripts" else "Plugins"
                    tag = f"{ver} 版/{how}，" if ver else ""
                    self.plugin_stat.config(
                        text=(f"已植入（{tag}字体 {fam}）" if fam
                              else f"已植入（{tag}）"))
                    self._refresh_plugin_font()
                elif kind == "plugin_restore_done":
                    r = (payload or [{}])[0] if isinstance(payload, list) else {}
                    removed = r.get("removed") or []
                    self.plugin_stat.config(text="")
                    self.plugin_restore_lbl.config(
                        text=("已还原：" + "、".join(removed)) if removed
                        else "没有找到插件脚本（可能本来就没植入过）")
                elif kind == "dbg_enable_done":
                    r = payload or {}
                    if r.get("mode_error"):
                        # ★ 方式函数抛异常：以前只写进 res["mode_error"]、
                        #   全项目**没有任何地方读它** → 界面上只显示
                        #   「方式三未命中（None）」，真实原因只在日志里。
                        self.dbg_do_lbl.config(
                            text=f"✘ 方式执行失败：{r['mode_error']}",
                            fg=ERR_COLOR)
                    elif not r.get("ok"):
                        self.dbg_do_lbl.config(
                            text=f"✘ {r.get('reason') or '失败'}",
                            fg=ERR_COLOR)
                    elif r.get("changed"):
                        what = []
                        if any(t.get("written") for t in
                               ((r.get("debug") or {}).get("targets") or [])):
                            what.append("写入 $DEBUG=true")
                        if any(t.get("written") for t in
                               ((r.get("antidebug") or {}).get("targets")
                                or [])):
                            what.append("注释反调试代码")
                        if (r.get("guard") or {}).get("added"):
                            what.append("关闭启动时的全量编译")
                        mres = r.get("mode_res") or {}
                        mode = r.get("mode") or "main"
                        mname = {"main": "通用", "keys": "方式二",
                                 "special": "方式三",
                                 "special_menu": "方式四",
                                 "repel": "方式五",
                                 "repel_menu": "方式六",
                                 "rewrite": "方式七",
                                 "launcher": "方式八"}.get(mode, mode)
                        if mode != "main":
                            if mode == "rewrite":
                                if mres.get("ok"):
                                    bits = []
                                    if mres.get("replaced"):
                                        bits.append(
                                            f"顶掉 {mres['replaced']} 个函数")
                                    if mres.get("renamed"):
                                        bits.append(
                                            f"改名 {mres['renamed']} 处调用")
                                    if mres.get("compat"):
                                        bits.append(
                                            f"保留旧名 {mres['compat']} 处")
                                    if mres.get("stripped"):
                                        bits.append(
                                            f"删$DEBUG条件 {mres['stripped']} 处")
                                    if mres.get("repaired"):
                                        bits.append(
                                            f"修回误改名 {mres['repaired']} 处")
                                    if mres.get("keyed"):
                                        bits.append("注册 T 键")
                                    if mres.get("plugin"):
                                        bits.append("写入插件")
                                    if (mres.get("rxdata") or {}).get("ok"):
                                        rx = (mres["rxdata"].get("action")
                                              == "appended" and "追加进 rxdata"
                                              or "并入 rxdata")
                                        bits.append(rx)
                                    if mres.get("norecompile"):
                                        bits.append("关闭插件重编译")
                                    if mres.get("guarded"):
                                        bits.append(
                                            f"依赖保护 {mres['guarded']} 处")
                                    if mres.get("reordered"):
                                        bits.append(
                                            f"调插件顺序 {mres['reordered']} 条")
                                    what.append(f"{mname}已应用"
                                                + ("（" + "、".join(bits) + "）"
                                                   if bits else ""))
                                else:
                                    what.append(
                                        f"{mname}未命中（{mres.get('reason')}）")
                            elif mres.get("ok"):
                                what.append(f"{mname}已应用")
                            else:
                                what.append(f"{mname}未命中（{mres.get('reason')}）")
                        self.dbg_do_lbl.config(
                            text="✔ 已完成：" + ("、".join(what) or "检查通过"),
                            fg=C_OK)
                    else:
                        self.dbg_do_lbl.config(
                            text="· 没有需要改动的地方（已经是开启状态）",
                            fg=C_KEY)
                    self._dbg_refresh_folder_info()
                    # ★ 任务2：方式②没认出任何 $DEBUG 条件 → 问要不要按基准补行
                    if r.get("ok") and r.get("mode_none"):
                        self._ask_baseline_strip(r)
                elif kind == "dbg_overwrite_ver":
                    # 覆盖前「读不出版本号」→ 检测认完版本后继续走确认流程
                    _d, _chk = payload[0], payload[1]
                    _tag = payload[2] if len(payload) > 2 else "menus"
                    _bver = (_chk or {}).get("baseline") or ""
                    _by = ""
                    if _bver:
                        _exact = (_chk or {}).get("exact")
                        _by = ("指纹完全吻合" if _exact else "最接近的一份基准")
                        self._emit_log(
                            f"[覆盖] 认出是 v{_bver}，用它覆盖\n")
                    # ★ 这两个 ask 里会 run_async：必须先让本队列里的
                    #   "done" 把 busy 清掉再弹确认框，否则 run_async 撞上
                    #   busy=True → 弹「已有任务在运行」且覆盖静默不执行。
                    if _tag == "scene_map":
                        self.root.after(
                            0, lambda: self._do_overwrite_scene_map_ask(
                                _d, _bver, _by))
                    else:
                        self.root.after(
                            0, lambda: self._do_overwrite_menus_ask(
                                _d, _bver, _by))
                elif kind == "dbg_scene_overwrite_done":
                    r = payload or {}
                    if r.get("ok"):
                        names = "、".join(r.get("written") or [])
                        self.dbg_ow_lbl.config(
                            text=f"✔ 已用基准覆盖地图更新（Scene_Map）：{names}",
                            fg=C_OK)
                        messagebox.showinfo(
                            "覆盖地图更新完成",
                            "已用官方同版本基准覆盖游戏的 Scene_Map"
                            f"（地图更新）：\n  {names}\n\n"
                            "原作者对 Scene_Map 的改动已被替换掉（原文件已备份，"
                            "可用「还原覆盖」恢复）。\n\n"
                            "建议接着用「方式② 删条件 / 方式③④ F6 键」——"
                            "现在 $DEBUG 条件是官方写法，一定能认出来。")
                    else:
                        why = r.get("reason") or "覆盖失败"
                        self.dbg_ow_lbl.config(text=f"✘ {why}", fg=ERR_COLOR)
                        messagebox.showerror("覆盖地图更新失败", why)
                elif kind == "dbg_strip_baseline_done":
                    r = payload or {}
                    n = r.get("added", 0)
                    names = "、".join(t.get("script", "")
                                     for t in (r.get("targets") or []))
                    if r.get("ok") and n:
                        self._emit_log(
                            f"[方式二·兜底] 完成：共补 {n} 处（{names}）\n")
                        messagebox.showinfo(
                            "已按基准补行",
                            f"已按官方 v{r.get('version')} 基准，在对应位置补了"
                            f" {n} 处「去掉 debug 条件」的代码：\n  {names}\n\n"
                            "只加了代码、没有删任何东西；原文件已备份，"
                            "可用「还原」恢复。")
                    else:
                        self._emit_log(
                            "[方式二·兜底] 没有需要补的地方\n")
                        messagebox.showinfo(
                            "没有需要补的地方",
                            r.get("reason") or
                            "官方基准里带 $DEBUG 的地方，游戏里要么已经有了、"
                            "要么找不到对应函数 —— 没有可补的。\n\n"
                            "可以试试「用基准覆盖地图更新」把 Scene_Map 盖回"
                            "官方版，再开方式②。")
                elif kind == "dbg_overwrite_done":
                    r = payload or {}
                    if r.get("ok"):
                        names = "、".join(r.get("written") or [])
                        self.dbg_ow_lbl.config(
                            text=f"✔ 已覆盖 {len(r.get('written') or [])} 个"
                                 f"调试菜单脚本：{names}",
                            fg=C_OK)
                    else:
                        self.dbg_ow_lbl.config(
                            text=f"✘ {r.get('reason') or '覆盖失败'}",
                            fg=ERR_COLOR)
                elif kind == "dbg_overwrite_restore_done":
                    r = payload or {}
                    n = r.get("restored", 0)
                    self.dbg_ow_lbl.config(
                        text=(f"✔ 已还原 {n} 个脚本" if n
                              else "· 没有找到本工具覆盖过的备份"),
                        fg=C_OK if n else C_KEY)
                elif kind == "dbg_launcher_done":
                    r = payload or {}
                    if r.get("ok"):
                        files = r.get("files") or []
                        note = r.get("note") or ""
                        self.dbg_do_lbl.config(
                            text=f"✔ 调试启动器已生成：{ '、'.join(files) }\n"
                                 + (f"  {note}\n" if note else "")
                                 + f"  到游戏目录双击「{r.get('main', '启动文件')}」"
                                   f"即以调试模式进入。",
                            fg=C_OK)
                        messagebox.showinfo(
                            "调试启动器已生成",
                            "已在游戏目录生成：\n  "
                            + "\n  ".join(files)
                            + (("\n\n" + note) if note else "")
                            + f"\n\n双击「{r.get('main', '启动文件')}」"
                              "即以调试模式进入游戏。")
                    else:
                        why = r.get("reason") or "生成失败"
                        self.dbg_do_lbl.config(text=f"✘ {why}", fg=ERR_COLOR)
                        if r.get("unsupported"):
                            messagebox.showwarning(
                                "这类游戏暂时开不了调试", why)
                        else:
                            messagebox.showerror("生成调试启动器失败", why)
                elif kind == "pbs_extract_done":
                    out, _res = payload if isinstance(payload, tuple) \
                        else ([], None)
                    self._pbs_after_extract(out)
                elif kind == "pbs_compile_done":
                    self._pbs_after_compile(payload or [])
                elif kind == "dbg_apply_report_done":
                    r = payload or {}
                    applied = r.get("applied") or []
                    if applied:
                        messagebox.showinfo(
                            "写回完成",
                            f"已写回 {len(applied)} 个函数：\n"
                            + "\n".join(applied[:20])
                            + (f"\n…另有 {len(applied) - 20} 个"
                               if len(applied) > 20 else ""))
                    else:
                        messagebox.showwarning(
                            "没有写回任何内容",
                            r.get("reason") or "没有可应用的已编辑条目。")
                elif kind == "dbg_restore_done":
                    r = payload or {}
                    n = r.get("restored", 0)
                    self.dbg_do_lbl.config(
                        text=(f"✔ 已还原 {n} 处改动" if n
                              else "· 没有找到本工具做过的备份"),
                        fg=C_OK if n else C_KEY)
                    self._dbg_refresh_folder_info()
                elif kind == "dbg_unpack_done":
                    r = payload or {}
                    if r.get("ok"):
                        self.dbg_unpack_lbl.config(
                            text=f"✔ 已解包 {r.get('plugins', 0)} 个插件 / "
                                 f"{r.get('files', 0)} 个文件 → {r.get('root', '')}",
                            fg=C_OK)
                    else:
                        errs = r.get("errors") or []
                        self.dbg_unpack_lbl.config(
                            text="✘ 解包失败：" + ("；".join(errs) if errs
                                                else "未知原因"),
                            fg=ERR_COLOR)
                elif kind == "dbg_compile_done":
                    r = payload or {}
                    if r.get("ok"):
                        n = r.get("updated", 0)
                        bak = r.get("backup")
                        self.dbg_compile_lbl.config(
                            text=(f"✔ 已更新 {n} 个文件 → "
                                  f"{r.get('container', '')}"
                                  + (f"（备份 {os.path.basename(bak)}）"
                                     if bak else "")
                                  if n else
                                  "· 没有需要更新的文件（改完 Plugins-p 里的 "
                                  ".rb 再来点）"),
                            fg=C_OK if n else C_KEY)
                    else:
                        errs = r.get("errors") or []
                        self.dbg_compile_lbl.config(
                            text="✘ 编译回容器失败：" + ("；".join(errs)
                                                    if errs else "未知原因"),
                            fg=ERR_COLOR)
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
        except Exception as e:                          # noqa: BLE001
            # ★ 单点故障保险：原来只捕 `queue.Empty`，`after` 也在 try 外面
            #   → 任何一个 handler 抛异常（控件已销毁的 TclError、消息体
            #   形状不对…）都会让**日志泵永久停摆**：之后所有后台任务的
            #   done/err 没人消费，`set_busy(False)` 再也不执行，状态条
            #   永远停在「运行中…」，且 `run_async` 会一直被 busy 拒绝。
            try:
                self._append_log(f"\n[界面] 处理消息时出错（已忽略）：{e}\n")
            except Exception:
                pass
        finally:
            try:
                self.root.after(90, self._pump)
            except Exception:
                pass

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

    def _apply_report_edits(self):
        """
        应用已编辑：把报告里手工改过的句子写进翻译缓存与译文文件。

        ★ 编辑记录来自双击报告行弹出的编辑窗（<缓存名>_edited.json），
          这里只是把它真正落到 *_translated.txt 和缓存里。
        """
        paths = self._report_sources()
        if not paths:
            messagebox.showwarning("提示",
                                   "请先选择检查报告（*_translated_report.txt）")
            return
        try:
            n_files, n_edit = commands.count_manual_edits(paths)
        except Exception:
            n_files, n_edit = 0, 0
        if not n_edit:
            messagebox.showinfo(
                "没有手工编辑",
                "这些文件还没有手工编辑记录。\n\n"
                "在报告列表里**双击任意一行**就会弹出编辑窗，改完整句译文后"
                "保存即可；保存过的句子都会记在 <缓存名>_edited.json 里，"
                "然后回到这里点「应用已编辑」。")
            return
        if not messagebox.askyesno(
                "应用已编辑",
                f"将把 {n_files} 个文件里的 {n_edit} 条手工编辑译文写入：\n"
                f"· 翻译缓存（<主名>_cache.json）\n"
                f"· 已生成的译文文件（<主名>_translated.txt）\n\n"
                f"译文文件里**其它行不会被改动**。\n继续吗？"):
            return
        self.show("log")
        self.run_async(
            lambda: commands.apply_manual_edits(paths),
            label="应用已编辑…", done_label="已应用手工编辑")

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

        # ★ 提示按「本地模型服务」里选的提供商走，不写死 Ollama
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
    # 页面 0：主页（点左侧头像进来；工具启动时默认也是它）
    # ================================================================
    def _page_home(self):
        page = self.pages["home"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        outer, inner = make_scroll_area(page, bg=BG_BASE)
        outer.grid(row=0, column=0, sticky="nsew")

        card = RoundCard(inner, radius=18, pad=20, auto_height=True)
        card.pack(fill="x")
        body = card.body

        # ---- 顶部声明（用户要求）----
        notice = tk.Label(body, text="本工具完全免费，不会有任何盈利行为",
                          bg=CARD, fg=ACCENT_DEEP,
                          font=(FONT_FAMILY, FONT_SIZES["big"] + 1, "bold"))
        notice.pack(anchor="center", pady=(0, 16))

        # ---- 头像全身照 ----
        box = tk.Frame(body, bg=CARD)
        box.pack(anchor="center")
        photo = load_fitted_photo(config.AVATAR_FILE, 760, 520)
        self.home_photo_lbl = tk.Label(box, bg=CARD, bd=0,
                                       highlightthickness=0)
        self.home_photo_lbl.pack()
        if photo is not None:
            self.home_photo_lbl.configure(image=photo)
            self.home_photo_lbl.image = photo          # 防 GC
        else:
            self.home_photo_lbl.configure(
                text="（没找到头像：%s）"
                     % os.path.basename(config.AVATAR_FILE),
                fg=C_HINT, font=FONT_SMALL)

        # ---- 作者姓名 ----
        name = tk.Label(body, text=config.AUTHOR_NAME, bg=CARD, fg=C_TITLE,
                        font=(FONT_FAMILY, FONT_SIZES["title"] + 4, "bold"))
        name.pack(anchor="center", pady=(18, 12))
        attach_label_copy(name, self, "作者名")

        # ---- 主页链接 ----
        row = tk.Frame(body, bg=CARD)
        row.pack(anchor="center")
        self._home_link(row, "Bilibili 主页", config.AUTHOR_BILIBILI)
        self._home_link(row, "GitHub 主页", config.AUTHOR_GITHUB)

        tk.Label(body, text=f"{config.APP_NAME}  v{config.VERSION}",
                 bg=CARD, fg=C_KEY, font=FONT_B).pack(
            anchor="center", pady=(16, 0))

    def _home_link(self, parent, text, url):
        """主页上的一个「XX 主页」链接按钮 + 底下那行网址（都能点开）。"""
        col = tk.Frame(parent, bg=CARD)
        col.pack(side="left", padx=10)
        GlassButton(col, text, width=176, height=46, primary=True, bg=CARD,
                    command=lambda: webbrowser.open(url)).pack()
        link = tk.Label(col, text=url, bg=CARD, fg=ACCENT,
                        font=FONT_SMALL, cursor="hand2")
        link.pack(pady=(6, 0))
        link.bind("<Button-1>", lambda e: webbrowser.open(url))
        attach_label_copy(link, self, "主页网址")

    # ================================================================
    # 页面 2：游戏汉化（汉化流程的入口页）
    # ================================================================
    def _page_hanhua(self):
        """
        把原来分散的菜单（翻译 / 重翻检查报告 / 术语更新后重翻 / 前缀字典 /
        中文润色 / 换行重排 / 术语字典）收进这一个菜单：右侧列出各步骤，
        点一项就跳到对应界面，界面顶部有「← 返回游戏汉化」可以回来。
        """
        page = self.pages["hanhua"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        outer, inner = make_scroll_area(page, bg=BG_BASE)
        outer.grid(row=0, column=0, sticky="nsew")

        card = RoundCard(inner, radius=18, pad=18, auto_height=True)
        card.pack(fill="x")
        body = card.body
        tk.Label(body, text="游戏汉化", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(body, text="汉化的每一步都在这里，点一项进入对应界面：",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=560).pack(anchor="w",
                                                      pady=(4, 10))

        grid = tk.Frame(body, bg=CARD)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)
        for i, (key, name, _desc) in enumerate(HANHUA_SUBMENUS):
            GlassButton(grid, f"{i + 1}. {name}", width=228, height=46,
                        primary=(i == 0), bg=CARD, font=FONT_B,
                        command=lambda k=key: self.show(k)).grid(
                row=i, column=0, sticky="w", pady=5)

        # ★ 右侧空白处：翻译流程说明（红色，逐行照抄 HANHUA_FLOW_STEPS）
        #   字号定稿在 HANHUA_FLOW_TITLE_PT / HANHUA_FLOW_BODY_PT（见文件头），
        #   wraplength 按最小窗口 1240 的可用宽取，保证最窄时也不冲出卡片。
        flow = tk.Frame(grid, bg=CARD)
        flow.grid(row=0, column=1, rowspan=len(HANHUA_SUBMENUS),
                  sticky="nw", padx=(24, 0), pady=5)
        tk.Label(flow, text="翻译流程（先启动本地模型服务）", bg=CARD, fg=C_FLOW,
                 font=(FONT_FAMILY, HANHUA_FLOW_TITLE_PT, "bold")).pack(anchor="w")
        self.hanhua_flow_lbl = tk.Label(
            flow, text="\n".join(HANHUA_FLOW_STEPS), bg=CARD, fg=C_FLOW,
            font=(FONT_FAMILY, HANHUA_FLOW_BODY_PT),
            justify="left", wraplength=HANHUA_FLOW_WRAP)
        self.hanhua_flow_lbl.pack(anchor="w", pady=(6, 0))

        # ★ 翻译期开关（默认值以 config.py 为准，勾选状态写回配置持久保存）
        optrow2 = tk.Frame(body, bg=CARD)
        optrow2.pack(fill="x", pady=(14, 0))
        self.hanhua_opt_vars = {}
        for _key, _text in (("PREFILTER_ENABLE", "预过滤"),
                            ("POST_REPLACEMENT_ENABLE", "译后替换"),
                            ("PRE_REPLACEMENT_ENABLE", "译前替换"),
                            ("THINKING_BLOCK", "思考块"),
                            ("TERM_STATS_ENABLE", "术语命中统计")):
            _var = tk.BooleanVar(value=bool(getattr(config, _key, False)))
            self.hanhua_opt_vars[_key] = _var
            tk.Checkbutton(
                optrow2, text=_text, variable=_var,
                bg=CARD, activebackground=CARD, selectcolor="#FFFFFF",
                font=FONT_SMALL, fg=TEXT,
                command=lambda k=_key, v=_var: self._toggle_config(k, v)
            ).pack(side="left", padx=(0, 8))
        tk.Label(body,
                 text="预过滤：不含源语言字符的行不送模型、按原文缓存；译前/译后替换按 "
                      "replacements/ 目录规则执行；思考块让模型先想再翻；"
                      "术语命中统计写 terms_stats.json。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=560).pack(anchor="w", pady=(4, 0))

        # ★ 文本保护规则模式（见 text_preserve/README.md）：
        #   自定义控制码写进 text_preserve/custom.json。
        optrow3 = tk.Frame(body, bg=CARD)
        optrow3.pack(fill="x", pady=(8, 0))
        tk.Label(optrow3, text="文本保护规则：", bg=CARD, fg=TEXT,
                 font=FONT_SMALL).pack(side="left")
        self.tp_mode_combo = ttk.Combobox(
            optrow3, values=list(self._TP_MODE_LABELS),
            width=24, state="readonly", font=FONT_SMALL)
        self.tp_mode_combo.current(self._TP_MODE_INDEX.get(
            str(getattr(config, "TEXT_PRESERVE_MODE", "smart")).lower(), 1))
        self.tp_mode_combo.pack(side="left")
        self.tp_mode_combo.bind("<<ComboboxSelected>>", self._on_tp_mode)
        GlassButton(optrow3, "重载规则", width=88, height=26, bg=CARD,
                    font=FONT_SMALL,
                    command=self._reload_tp_rules).pack(side="left",
                                                        padx=(8, 0))
        GlassButton(optrow3, "打开规则文件夹", width=118, height=26, bg=CARD,
                    font=FONT_SMALL,
                    command=self._open_tp_dir).pack(side="left", padx=(6, 0))
        GlassButton(optrow3, "译前替换", width=84, height=26, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self._open_replacement_manager(
                        "pre")).pack(side="left", padx=(12, 0))
        GlassButton(optrow3, "译后替换", width=84, height=26, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self._open_replacement_manager(
                        "post")).pack(side="left", padx=(6, 0))
        tk.Label(body,
                 text="控制码识别规则（text_preserve/ 下的 JSON）：off 只用内置；"
                      "smart 再加项目自带规则集；custom 再叠加 custom.json。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=560).pack(anchor="w", pady=(4, 0))

        tk.Label(body,
                 text="进入某一项后，点左上角「← 返回游戏汉化」回到本页；"
                      "带右侧文件栏的页面要先选好文件。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=560).pack(anchor="w", pady=(12, 0))

    def _toggle_config(self, key, var):
        """勾选框 → 写回配置（当前会话立即生效并持久保存）。"""
        ok, _msg, val = settings.set_value(key, bool(var.get()))
        if ok:
            var.set(bool(val))

    # ---- 文本保护规则（text_preserve） ----
    _TP_MODE_LABELS = ("off（只用内置）", "smart（内置 + 自带规则集）",
                       "custom（叠加自定义）")
    _TP_MODE_VALUES = ("off", "smart", "custom")
    _TP_MODE_INDEX = {"off": 0, "smart": 1, "custom": 2}

    def _on_tp_mode(self, _e=None):
        """切换文本保护规则模式 → 写回配置并立即重载规则。"""
        i = self.tp_mode_combo.current()
        mode = self._TP_MODE_VALUES[i if 0 <= i <= 2 else 1]
        ok, msg, _val = settings.set_value("TEXT_PRESERVE_MODE", mode)
        if not ok:
            messagebox.showwarning("保存失败", msg)
            return
        n = self._reload_tp_rules(silent=True)
        self.status_var.set(f"文本保护规则模式：{mode}（{n} 条规则生效）")

    def _reload_tp_rules(self, silent=False):
        """按当前配置重新装载规则（改完 JSON 点一下即可生效，不用重启）。"""
        try:
            import text_rules
            n = text_rules.apply()
        except Exception as e:
            log.warning("文本保护规则重载失败：%s", e)
            if not silent:
                messagebox.showwarning("重载失败", str(e))
            return 0
        if not silent:
            self.status_var.set(f"文本保护规则已重载：{n} 条生效")
        return n

    def _open_tp_dir(self):
        """打开规则文件夹，方便用户编辑 custom.json。"""
        try:
            import text_rules
            d = text_rules.rules_dir()
            os.makedirs(d, exist_ok=True)
            if hasattr(os, "startfile"):
                os.startfile(d)          # Windows
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            messagebox.showwarning("打开失败", str(e))

    # ---- 替换预设管理器（replacements/pre、replacements/post） ----
    def _open_replacement_manager(self, kind):
        import replacement as REPL

        label = "译前" if kind == "pre" else "译后"
        key = ("PRE_REPLACEMENT_PRESETS" if kind == "pre"
               else "POST_REPLACEMENT_PRESETS")

        win = tk.Toplevel(self.root)
        win.title(f"{label}替换预设")
        win.geometry("660x460")
        win.configure(bg=BG_BASE)

        tk.Label(win, text=f"目录：{REPL._presets_root(kind)}", bg=BG_BASE,
                 fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=620).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Label(win, text="点一行切换启用/停用；双击打开该预设文件。"
                          "留空名单 = 全部启用。",
                 bg=BG_BASE, fg=C_HINT, font=FONT_SMALL).pack(anchor="w",
                                                              padx=12)

        box = tk.Frame(win, bg=BG_BASE)
        box.pack(fill="both", expand=True, padx=12, pady=8)
        lb = tk.Listbox(box, font=FONT_SMALL, activestyle="none",
                        selectmode="extended",
                        bg="#FFFFFF", highlightthickness=1)
        lb.pack(fill="both", expand=True)

        state = {"rows": []}

        def enabled_set():
            raw = getattr(config, key, "") or ""
            names = [n.strip() for n in str(raw).replace("；", ",").split(",")
                     if n.strip()]
            return set(names) if names else None

        def refresh():
            lb.delete(0, "end")
            rows = REPL.list_presets(kind)
            state["rows"] = rows
            on = enabled_set()
            for p in rows:
                mark = "[✓]" if (on is None or p["name"] in on) else "[  ]"
                lb.insert("end", f"{mark} {p['name']}     （{p['count']} 条）")

        def write_enabled(names):
            ok, msg, _v = settings.set_value(key, ",".join(names))
            if not ok:
                messagebox.showwarning("保存失败", msg, parent=win)
            refresh()

        def toggle(_e=None):
            sels = lb.curselection()
            if not sels:
                return
            on = enabled_set()
            allnames = [p["name"] for p in state["rows"]]
            if on is None:
                on = set(allnames)          # 从「全部启用」转成显式名单
            for i in sels:
                if i >= len(state["rows"]):
                    continue
                name = state["rows"][i]["name"]
                if name in on:
                    on.discard(name)
                else:
                    on.add(name)
            write_enabled([n for n in allnames if n in on])

        def open_file(_e=None):
            sel = lb.curselection()
            if not sel:
                return
            p = state["rows"][sel[0]]["file"]
            try:
                if hasattr(os, "startfile"):
                    os.startfile(p)
                else:
                    subprocess.Popen(["xdg-open", p])
            except Exception as e:
                messagebox.showwarning("打开失败", str(e), parent=win)

        lb.bind("<ButtonRelease-1>", toggle)
        lb.bind("<Double-Button-1>", open_file)

        bar = tk.Frame(win, bg=BG_BASE)
        bar.pack(fill="x", padx=12, pady=(0, 10))

        def do_import():
            p = filedialog.askopenfilename(
                parent=win, title=f"导入{label}替换规则",
                filetypes=[("规则文件", "*.json *.xlsx"),
                           ("JSON", "*.json"), ("Excel", "*.xlsx"),
                           ("所有文件", "*.*")])
            if not p:
                return
            rules = REPL.import_rules_file(p)
            if not rules:
                messagebox.showinfo("提示", "这个文件里没有可用的规则。",
                                    parent=win)
                return
            name = filedialog.askstring(
                "预设名称", "导入后存成哪个预设？", parent=win,
                initialvalue=re.sub(
                    r'[\\/:*?"<>|]', "_",
                    os.path.splitext(os.path.basename(p))[0]) or "imported")
            if not name:
                return
            REPL.save_preset(kind, name, rules)
            refresh()
            self.status_var.set(f"已导入 {label}替换预设：{name}（{len(rules)} 条）")

        def do_export():
            sel = lb.curselection()
            if not sel:
                messagebox.showinfo("提示", "先选中要导出的预设。", parent=win)
                return
            p = state["rows"][sel[0]]
            out = filedialog.asksaveasfilename(
                parent=win, title="导出预设（同时写出 .json 和 .xlsx）",
                defaultextension=".json", initialfile=p["name"],
                filetypes=[("JSON", "*.json")])
            if not out:
                return
            base = os.path.splitext(out)[0]
            j, x = REPL.export_preset_files(kind, p["name"],
                                            REPL.read_rules_file(p["file"]),
                                            base_path=base)
            self.status_var.set(
                f"已导出：{os.path.basename(j)}" + (f" + {os.path.basename(x)}"
                                                    if x else "（Excel 跳过）"))

        def do_open_dir():
            d = REPL._presets_root(kind)
            os.makedirs(d, exist_ok=True)
            try:
                if hasattr(os, "startfile"):
                    os.startfile(d)
                else:
                    subprocess.Popen(["xdg-open", d])
            except Exception as e:
                messagebox.showwarning("打开失败", str(e), parent=win)

        for text, cmd in (("导入 JSON / Excel", do_import),
                          ("导出选中", do_export),
                          ("全部启用", lambda: write_enabled([])),
                          ("打开文件夹", do_open_dir),
                          ("刷新", refresh)):
            GlassButton(bar, text, width=118, height=30, bg=BG_BASE,
                        font=FONT_SMALL, command=cmd).pack(side="left",
                                                           padx=(0, 6))
        GlassButton(bar, "关闭", width=76, height=30, bg=BG_BASE,
                    font=FONT_SMALL, command=win.destroy).pack(side="right")

        refresh()

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
            text="按分段从游戏 Data 里读出已编译的原文表，拆成多个 "
                 "Text_<语言> 系列 txt（已存在时先备份）。",
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
                                                   "Text_ 文件夹）",
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
        row3b = tk.Frame(c2.body, bg=CARD)
        row3b.pack(fill="x", pady=(6, 0))
        self.intl_lang_first_var = tk.BooleanVar(
            value=bool(getattr(config, "LANG_ENTRY_FIRST", True)))
        tk.Checkbutton(
            row3b, text="中文设为默认语言（排语言表第一条）",
            variable=self.intl_lang_first_var, bg=CARD, fg=TEXT,
            activebackground=CARD, activeforeground=TEXT,
            selectcolor="#FFFFFF", font=FONT_SMALL,
            cursor="hand2").pack(side="left")
        self.intl_compile_lbl = tk.Label(c2.body, text="", bg=CARD,
                                         fg=C_KEY, font=FONT_SMALL,
                                         justify="left", wraplength=560)
        self.intl_compile_lbl.pack(anchor="w", pady=(6, 0))
        attach_label_copy(self.intl_compile_lbl, self, "编译结果")
        self.intl_compile_hint = tk.Label(
            c2.body,
            text="把译文写回游戏文本（等同于 debug 菜单的 Compile Text）："
                 "只编译 *_translated.txt，没有对应译文的源文件则编译源文件本身。",
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
                 text="按游戏版本挑对应插件本体（16 / 17.2 / 18.1 / 19.1 / 20.1 / "
                      "21.1），装进游戏、把字体复制到 Fonts，并把引擎脚本里的"
                      "字体定义一起改掉（不用进游戏、也不用开调试）。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=560).pack(anchor="w", pady=(6, 0))

        row_restore = tk.Frame(c3.body, bg=CARD)
        row_restore.pack(fill="x", pady=(10, 0))
        GlassButton(row_restore, "还原", width=100, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._do_plugin_restore).pack(side="left")
        tk.Label(row_restore,
                 text="删掉本工具装进游戏的插件与字体",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=420).pack(side="left", padx=10)
        self.plugin_restore_lbl = tk.Label(c3.body, text="", bg=CARD,
                                           fg=C_KEY, font=FONT_SMALL,
                                           justify="left", wraplength=560)
        self.plugin_restore_lbl.pack(anchor="w", pady=(4, 0))
        attach_label_copy(self.plugin_restore_lbl, self, "插件还原结果")
        self._refresh_plugin_font()

        # ---- 右侧：游戏文件夹 + 提示 ----
        fp_holder = RoundCard(page, radius=16, pad=8, width=272,
                                scrollable=True)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        body = fp_holder.body
        tk.Label(body, text="游戏文件夹", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=10, pady=(8, 4))
        GlassButton(body, "选择游戏主程序", width=132, height=36, bg=CARD,
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
                 "选游戏主程序（Game.exe，Data 文件夹和它同一层）：提取出的"
                 "文本落在根目录的 Text_ 系列文件夹，翻译只改每条的译文行，"
                 "编译前自动备份，插件仅在中文语言下生效。",
            bg=CARD, fg=C_HINT, font=FONT_SMALL,
            justify="left", wraplength=200)
        self.intl_hint_lbl.pack(anchor="w", padx=10, pady=(10, 0))
        attach_label_copy(self.intl_hint_lbl, self, "使用提示")

    # ---------- 菜单 1（文本提取与编译）：小工具 ----------
    def _intl_pick_folder(self):
        d, _exe = pick_game_exe_dialog(
            self.root,
            initialdir=(config.Runtime.last_dir
                        if config.Runtime.last_dir
                        and os.path.isdir(config.Runtime.last_dir)
                        else config.BASE_DIR),
            title="选择游戏主程序（Data 文件夹和它在同一层）")
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
          legacy → Text_<语言>/ 里多个 txt ↔ 一个语言 .dat
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
                    text=f"这个游戏分 core（引擎）与 game（游戏）两份，会导出成 "
                         f"Text_{frag}_core/ 与 Text_{frag}_game/ 两个文件夹"
                         f"（每个分段一个 txt）。")
                self.intl_compile_hint.config(
                    text="选 Text_<语言>_core / Text_<语言>_game 两个文件夹"
                         "（或里面的 txt），分别编出 "
                         f"messages_{frag}_core.dat 与 "
                         f"messages_{frag}_game.dat；覆盖前自动备份。")
                self.intl_src_lbl.config(
                    text="未选择（默认用提取出来的两个 Text_ 文件夹）")
            else:
                self.intl_extract_hint.config(
                    text="读游戏 Data 下已编译的原文表，按分段拆成 "
                         "Text_<语言> 文件夹里的 txt（已存在时先备份）。")
                self.intl_compile_hint.config(
                    text="可以只选一个 txt，也可以选整个文件夹（里面的 .txt "
                         "按文件名顺序合并）；输出位置按游戏 "
                         "Settings::LANGUAGES 定，覆盖前自动备份。")
                self.intl_src_lbl.config(
                    text="未选择（默认用提取出来的 Text_ 文件夹）")
        except Exception:
            self.intl_info_lbl.config(text="")

    def _intl_folder(self):
        """取当前游戏目录；没选或不合格时提示并返回 None。"""
        d = getattr(self, "intl_folder", None)
        if not d or not os.path.isdir(d):
            messagebox.showwarning("提示", "请先在右侧选择游戏主程序")
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
                text="未选择（默认用提取出来的 Text_ 文件夹）", fg=C_HINT)
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
        lang_first = bool(self.intl_lang_first_var.get())
        self.show("log")

        def work():
            res = commands.intl_compile_paths(
                d, srcs, apply_language=apply_lang, lang_first=lang_first)
            self.q.put(("intl_compile_done", res))
            return res

        self.run_async(work, label="编译文本中…", done_label="文本编译完成")

    # ================================================================
    # 页面 2：翻译
    # ================================================================
    # ================================================================
    # 页面：术语提取（读名字文本文件 → 模型翻译 → 写术语表）
    # ================================================================
    def _page_termextract(self):
        page = self.pages["termextract"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)
        # ★ 行 1（名字文件卡）吃掉剩余高度。RoundCard 默认请求高度只有 10
        #   （防 Canvas 默认 378x265 撑爆布局），pack(fill="x") 不撑高度 →
        #   卡片塌成一条线、内容全看不见。必须 grid + 行权重，写法对齐
        #   _page_translate / _page_terms / _page_polish。
        left.grid_rowconfigure(1, weight=1)

        # ---- 卡 1：说明 ----
        c1 = RoundCard(left, radius=16, pad=18, auto_height=True)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="术语提取", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(c1.body,
                 text="从名字文本文件里读专有名词，交给模型翻成目标语言，"
                      "写进术语表的「自动提取区」。\n"
                      "可选单个名字文本，也可选整个文本文件夹。\n"
                      "翻译走与「翻译」同一套提示词（system_translate_jsonline），"
                      "只是在翻完后把原文与译文计入术语表。\n"
                      "与翻译一样带缓存：中途取消 / 中断后重跑，已翻过的"
                      "条目不会重复送模型（缓存在目标文件夹的「翻译中间文件」夹）。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=560).pack(anchor="w", pady=(4, 0))

        # ---- 卡 2：识别到的名字文件 ----
        c2 = RoundCard(left, radius=16, pad=16)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tk.Label(c2.body, text="识别到的名字文件", bg=CARD, fg=C_TITLE,
                 font=FONT_B).pack(anchor="w")
        # ★ 整套文本夹能识别出几十个名字文件，列表放滚动区里，不会溢出卡片
        scr_outer, scr_inner = make_scroll_area(c2.body, bg=CARD)
        scr_outer.pack(fill="both", expand=True, pady=(6, 0))
        self.te_files_lbl = tk.Label(
            scr_inner, text="（还没选文件）", bg=CARD, fg=TEXT,
            font=FONT_SMALL, justify="left", anchor="w", wraplength=560)
        self.te_files_lbl.pack(anchor="w")
        tk.Label(c2.body,
                 text="读法（区块号优先）：① 开头的 [编号] 是名字区块（如 "
                      "[1] 宝可梦名 / [5] 招式 / [7] 道具 / [12] 属性 / [30] 昵称）；"
                      "② 文件名含独立的 NAME / NAMES / NICKNAMES 词。\n"
                      "不读：「翻译中间文件」夹、*_translated 译文、描述 / 正文 / "
                      "图鉴类文件。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=560).pack(anchor="w", pady=(6, 0))

        # ---- 卡 3：预览 / 开始 ----
        c3 = RoundCard(left, radius=16, pad=18, auto_height=True)
        c3.grid(row=2, column=0, sticky="ew")
        row = tk.Frame(c3.body, bg=CARD)
        row.pack(fill="x")
        GlassButton(row, "预览待翻条数", width=150, height=42, bg=CARD,
                    font=FONT_SMALL,
                    command=self._te_preview).pack(side="left")
        GlassButton(row, "开始提取并翻译", width=180, height=46, primary=True,
                    bg=CARD, font=FONT_B,
                    command=self._te_run).pack(side="left", padx=(10, 0))
        # ★ 提取之后的检查/修正功能：检查报告（可直接改译文，不走模型）
        GlassButton(row, "检查报告", width=120, height=46, bg=CARD,
                    font=FONT_B,
                    command=self._goto_termcheck).pack(side="left",
                                                       padx=(10, 0))
        self.te_stat_lbl = tk.Label(c3.body, text="", bg=CARD, fg=C_KEY,
                                    font=FONT_SMALL, justify="left",
                                    wraplength=560)
        self.te_stat_lbl.pack(anchor="w", pady=(10, 0))
        attach_label_copy(self.te_stat_lbl, self, "术语提取结果")

        # ---- 右侧：文本文件来源 ----
        holder = RoundCard(page, radius=16, pad=10, width=300,
                           scrollable=True)
        holder.grid(row=0, column=1, sticky="nsew")
        holder.grid_propagate(False)
        body = holder.body
        tk.Label(body, text="要翻译的文本文件", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=8, pady=(8, 4))
        GlassButton(body, "选择文本文件", width=150, height=38, bg=CARD,
                    font=FONT_SMALL,
                    command=self._te_pick_file).pack(anchor="w", padx=8)
        GlassButton(body, "选择文件夹", width=150, height=38, bg=CARD,
                    font=FONT_SMALL,
                    command=self._te_pick_folder).pack(anchor="w", padx=8,
                                                       pady=(6, 0))
        self.te_src_lbl = tk.Label(body, text="未选择", bg=CARD, fg=C_KEY,
                                   font=FONT_SMALL, wraplength=270,
                                   justify="left")
        self.te_src_lbl.pack(anchor="w", padx=8, pady=(6, 0))
        attach_label_copy(self.te_src_lbl, self, "文本文件来源")
        self.te_info_lbl = tk.Label(body, text="", bg=CARD, fg=C_HINT,
                                    font=FONT_SMALL, wraplength=270,
                                    justify="left")
        self.te_info_lbl.pack(anchor="w", padx=8, pady=(8, 0))
        tk.Label(body,
                 text="选单个名字文本，或整个游戏文本文件夹（如 Text_chinese）。\n"
                      "文件夹只读名字文件；单个文件按 [编号] 区块判定。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, wraplength=270,
                 justify="left").pack(anchor="w", padx=8, pady=(10, 0))

        self.te_target = ""

    def _te_pick_file(self):
        path = filedialog.askopenfilename(
            title="选择要提取术语的文本文件",
            initialdir=(os.path.dirname(self.te_target)
                        if os.path.isfile(self.te_target)
                        else (self.te_target or config.Runtime.last_dir
                              or config.BASE_DIR)),
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        config.Runtime.set_dir(os.path.dirname(path) or config.BASE_DIR)
        self.te_target = path
        self._sync_te_src_labels()
        self._te_preview()

    def _te_pick_folder(self):
        folder = filedialog.askdirectory(
            title="选择放着名字文本的文件夹（如 Text_chinese）",
            initialdir=(self.te_target
                        if os.path.isdir(self.te_target)
                        else (config.Runtime.last_dir or config.BASE_DIR)))
        if not folder:
            return
        config.Runtime.set_dir(folder)
        self.te_target = folder
        self._sync_te_src_labels()
        self._te_preview()

    def _te_preview(self):
        """算一遍「有哪些要翻」但不调模型。"""
        import term_extract as TE

        target = getattr(self, "te_target", "")
        if not target:
            self.te_info_lbl.config(text="先选文本文件或文件夹。")
            self.te_files_lbl.config(text="（还没选文件）")
            return
        try:
            p = TE.plan(target)
        except Exception as e:
            self.te_stat_lbl.config(text=f"读文本文件失败：{e}")
            self.te_info_lbl.config(text="")
            self.te_files_lbl.config(text="（读取失败）")
            return

        if p["files"]:
            rows = []
            for f in p["files"]:
                blk = (f"区块 {f['block']}" if f["block"] is not None
                       else "无区块")
                rows.append(f"· {os.path.basename(f['path'])}"
                            f"　[{f['label']}／{blk}]　{f['count']} 条")
            self.te_files_lbl.config(text="\n".join(rows))
        else:
            self.te_files_lbl.config(
                text="（没找到名字文件 —— 需要文件名含 NAME / NAMES / NICKNAMES 词，"
                     "或开头 [编号] 是名字区块）")

        warn = ""
        if p["problems"]:
            warn = "\n⚠ " + "；".join(
                f"{os.path.basename(a)}：{b}" for a, b in p["problems"][:2])

        lines = [f"{TE.label_of(k)}：{len(v)}"
                 for k, v in p["by_section"].items()]
        # ★ 缓存命中要单独说：与正常翻译一样，「取消/中断后重跑」时
        #   这部分不会重新送模型，用户看到数字才对得上。
        cache_note = ""
        if p.get("in_cache"):
            cache_note = (f"\n其中 {p['in_cache']} 条上次已翻过（有缓存），"
                          f"这次不会重复送模型。")
        self.te_stat_lbl.config(
            text=f"共识别 {len(p['files'])} 个名字文件、{p['found']} 条候选；"
                 f"术语表里还没有的有 {p['todo']} 条（只会翻这些）。\n"
                 + ("　".join(lines) if lines else "　（都已有译名）")
                 + cache_note
                 + warn)
        self.te_info_lbl.config(text="已读取文本文件 ✔")

    def _te_run(self):
        import term_extract as TE

        target = getattr(self, "te_target", "")
        if not target:
            messagebox.showwarning("提示", "请先在右侧选择文本文件或文件夹")
            return
        try:
            p = TE.plan(target)
        except Exception as e:
            messagebox.showwarning("读不到文本文件", str(e))
            return
        if not p["files"]:
            messagebox.showinfo(
                "提示",
                "没找到名字文件。\n可读的是名字类文本（如 ITEM_NAMES.txt /"
                " TYPE_NAMES.txt / POKEMON_NICKNAMES.txt）：文件名含独立的 "
                "NAME / NAMES / NICKNAMES 词，或开头 [编号] 是名字区块。")
            return
        if not p["todo"]:
            # 没有待翻项也可能是「上次翻到一半」：缓存里的译文要补进术语表
            msg = "术语表里已经有全部候选的译名，无需提取。"
            if p.get("in_cache"):
                msg = (f"待翻的都翻完了，但缓存里还有 {p['in_cache']} 条"
                       f"上次翻好、没写进术语表的译名。\n"
                       f"现在把它们补进术语表（自动提取区）吗？")
                if not messagebox.askyesno("确认", msg):
                    return
                self.show("log")
                self.run_async(
                    lambda: TE.run_extract(
                        target, cancel=lambda: self._cancel_flag),
                    label=f"补写 {p['in_cache']} 条缓存术语…",
                    done_label="术语提取完成")
                return
            messagebox.showinfo("提示", msg)
            return
        resume = ""
        if p.get("in_cache"):
            resume = (f"\n其中 {p['in_cache']} 条上次已翻过（有缓存），"
                      f"不会重复送模型。")
        if not messagebox.askyesno(
                "确认", f"将从 {len(p['files'])} 个名字文件里读到的 "
                        f"{p['todo']} 条术语送模型翻译，"
                        f"翻完自动写进术语表（自动提取区）。\n"
                        f"（走与「翻译」同一条流水线，会同时产出译文文件"
                        f"与检查报告）"
                        f"{resume}"
                        f"\n中途取消也没关系：已翻的会进缓存，下次接着翻。"
                        f"\n继续？"):
            return
        self.show("log")
        # ★ run_extract 内部的正常翻译批循环看的是 bridge.cancelled()，
        #   所以它会把传进去的 cancel 接到 bridge 上再还原。这里必须传
        #   **GUI 自己的取消标志**，不能传 bridge.cancelled —— 那会让
        #   run_extract 写成 bridge._cancel_fn = lambda: bridge.cancelled()，
        #   自引用递归到上限后被 except 吞掉、恒返回 False，取消按钮就失效了。
        self.run_async(
            lambda: TE.run_extract(target, cancel=lambda: self._cancel_flag),
            label=f"提取并翻译 {p['todo']} 条术语…",
            done_label="术语提取完成",
        )

    # ================================================================
    # 页面：术语检查报告（只读缓存与术语表；改译名不走模型，重翻走模型）
    # ================================================================
    def _page_termcheck(self):
        page = self.pages["termcheck"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=0)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        c1 = RoundCard(left, radius=16, pad=18, auto_height=True)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(c1.body, text="术语检查报告", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(c1.body,
                 text="只看术语提取的缓存与术语表，把有问题的译名列出来。\n"
                      "双击「译名」列即可改，点「应用修改」写回缓存、译文文件"
                      "与术语表（改译名 / 应用修改不走模型）；\n"
                      "点「术语重翻」会删掉选中条目的缓存并重走翻译流水线"
                      "（★ 会调用模型），\n"
                      "重翻时每批翻完立刻把新译名并进术语表自动提取区，"
                      "同一文件的后续批次马上用上。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=560).pack(anchor="w", pady=(4, 0))

        c2 = RoundCard(left, radius=16, pad=14)
        c2.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        head = tk.Frame(c2.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="问题列表", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        GlassButton(head, "刷新报告", width=104, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._do_term_check).pack(side="left", padx=12)
        self.tc_stat = tk.Label(head, text="尚未检查", bg=CARD, fg=C_KEY,
                                font=FONT_BIG)
        self.tc_stat.pack(side="right")
        attach_label_copy(self.tc_stat, self, "统计")

        # 搜索框（与重翻检查报告页同风格）+ 问题类型筛选
        sb = tk.Frame(c2.body, bg=CARD)
        sb.pack(fill="x", pady=(8, 0))
        tk.Label(sb, text="搜索", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")
        self.tc_search = tk.StringVar()
        ent = ttk.Entry(sb, textvariable=self.tc_search, width=16, font=FONT)
        ent.pack(side="left", padx=6)
        ent.bind("<KeyRelease>", lambda _e: self._render_tc_rows())
        ent.bind("<Return>", lambda _e: self._render_tc_rows())
        tk.Label(sb, text="问题类型", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left", padx=(14, 4))
        self.tc_kind_vars = {}
        for kind in TFX_KIND_ORDER:
            var = tk.BooleanVar(value=True)
            self.tc_kind_vars[kind] = var
            tk.Checkbutton(sb, text=kind, variable=var,
                           bg=CARD, fg=TEXT, activebackground=CARD,
                           selectcolor="#FFFFFF", font=FONT_SMALL,
                           command=self._render_tc_rows).pack(side="left")

        wrap = tk.Frame(c2.body, bg=CARD)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        cols = ("kind", "section", "src", "dst", "detail")
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=3)
        for c, w, t in (("kind", 130, "问题类型"), ("section", 92, "类别"),
                        ("src", 170, "原文"), ("dst", 150, "译名（可编辑）"),
                        ("detail", 200, "说明")):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w")
        sb2 = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb2.set)
        tree.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        # ★ 只开放「译名」列（#4）编辑，原文列只读
        bind_tree_edit(tree, {"#4": True}, on_commit=self._on_tc_edit)
        self.tc_tree = tree
        tree.tag_configure("k_bad", background="#FFE9E9")
        tree.tag_configure("k_warn", background="#FFF4D6")
        tree.tag_configure("k_edit", background="#E3F2E1")
        bind_tree_wheel(tree)
        attach_tree_copy(tree, self)

        c3 = RoundCard(left, radius=16, pad=18, auto_height=True)
        c3.grid(row=2, column=0, sticky="ew")
        btn_row = tk.Frame(c3.body, bg=CARD)
        btn_row.pack(fill="x")
        GlassButton(btn_row, "复制列表", width=118, height=46, bg=CARD,
                    font=FONT_BIG,
                    command=self._copy_tc_list).pack(side="left")
        GlassButton(btn_row, "撤销改动", width=118, height=46, bg=CARD,
                    font=FONT_BIG,
                    command=self._undo_tc_edits).pack(side="left", padx=10)
        GlassButton(btn_row, "应用修改", width=140, height=46, primary=True,
                    bg=CARD, font=FONT_BIG,
                    command=self._do_apply_tc).pack(side="left", padx=10)
        GlassButton(btn_row, "术语重翻", width=140, height=46, primary=True,
                    bg=CARD, font=FONT_BIG,
                    command=self._do_tc_retranslate).pack(side="right")
        tk.Label(c3.body,
                 text="本页数据都来自缓存与术语表，不生成报告文件；"
                      "双击「译名」列改完点「应用修改」即可同时更新缓存、"
                      "译文文件（如有）与术语表自动提取区（不走模型）；"
                      "「术语重翻」会删掉选中条目的缓存并重走翻译流水线"
                      "（会调用模型），\n"
                      "并把每批翻出的新译名逐批写进术语表自动提取区。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=560).pack(anchor="w", pady=(8, 0))

        # 右侧：目标文件来源（与术语提取页共用 te_target）
        holder = RoundCard(page, radius=16, pad=8, width=272,
                           scrollable=True)
        holder.grid(row=0, column=1, sticky="nsew", rowspan=3)
        holder.grid_propagate(False)
        body = holder.body
        tk.Label(body, text="要检查的文本", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=8, pady=(8, 4))
        GlassButton(body, "选择文本文件", width=150, height=38, bg=CARD,
                    font=FONT_SMALL,
                    command=self._te_pick_file).pack(anchor="w", padx=8)
        GlassButton(body, "选择文件夹", width=150, height=38, bg=CARD,
                    font=FONT_SMALL,
                    command=self._te_pick_folder).pack(anchor="w", padx=8,
                                                       pady=(6, 0))
        self.tc_src_lbl = tk.Label(body, text="未选择", bg=CARD, fg=C_KEY,
                                   font=FONT_SMALL, wraplength=250,
                                   justify="left")
        self.tc_src_lbl.pack(anchor="w", padx=8, pady=(6, 0))
        self.tc_info_lbl = tk.Label(body, text="", bg=CARD, fg=C_HINT,
                                    font=FONT_SMALL, wraplength=250,
                                    justify="left")
        self.tc_info_lbl.pack(anchor="w", padx=8, pady=(8, 0))
        tk.Label(body,
                 text="选单个名字文本，或整个游戏文本文件夹。\n"
                      "读的就是术语提取缓存里已有的那些译名。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, wraplength=250,
                 justify="left").pack(anchor="w", padx=8, pady=(10, 0))

    def _te_target_ready(self, lbl):
        """术语检查 / 修正共用的目标检查：没选目标就提示并返回 ""。"""
        target = getattr(self, "te_target", "")
        if not target:
            messagebox.showwarning("提示", "请先在右侧选择文本文件或文件夹")
            return ""
        return target

    def _do_term_check(self):
        import term_fix as TFX

        target = self._te_target_ready(None)
        if not target:
            return

        def work():
            hits = TFX.check_terms(target)
            self.q.put(("termcheck", (hits, "")))

        if self.busy:
            messagebox.showinfo("提示", "已有任务在运行")
            return
        self.set_busy(True, "正在检查术语…")
        threading.Thread(target=work, daemon=True).start()

    def _fill_termcheck(self, payload):
        hits, path = payload if isinstance(payload, tuple) else (payload, "")
        self.tc_hits = list(hits or [])
        self.tc_edits = {}           # {原文: 新译名}
        self.tc_edit_stack = []      # [(原文, 旧译名, 新译名)] 供撤销
        self._render_tc_rows()
        n = len(self.tc_hits)
        self.status_var.set(f"术语检查完成：{n} 处问题")

    def _tc_filtered_hits(self):
        """当前**筛选后显示**的问题条目（口径与 _render_tc_rows 完全一致）。"""
        kw = (self.tc_search.get() or "").strip().lower()
        kinds = {k for k, v in getattr(self, "tc_kind_vars", {}).items()
                 if v.get()}
        out = []
        for h in getattr(self, "tc_hits", []) or []:
            if kinds and h.get("kind", "") not in kinds:
                continue
            if kw and kw not in (h.get("src", "") + h.get("dst", "")
                                 + h.get("detail", "")
                                 + h.get("kind", "")).lower():
                continue
            out.append(h)
        return out

    def _render_tc_rows(self):
        tree = self.tc_tree
        for iid in tree.get_children():
            tree.delete(iid)
        edits = getattr(self, "tc_edits", {}) or {}
        shown = 0
        for h in self._tc_filtered_hits():
            dst = edits.get(h.get("src", ""), h.get("dst", ""))
            tag = ("k_bad" if h["kind"] in ("译名为空", "未翻（回显原文）",
                                            "疑似机翻残留", "译文残留英文")
                   else "k_warn")
            if h.get("src", "") in edits:
                tag = "k_edit"
            tree.insert("", "end", values=(h.get("kind", ""),
                                           h.get("section", ""),
                                           h.get("src", ""),
                                           dst or "（空）",
                                           h.get("detail", "")), tags=(tag,))
            shown += 1
        total = len(getattr(self, "tc_hits", []) or [])
        n_edit = len(edits)
        txt = f"显示 {shown} / 共 {total} 处问题"
        if n_edit:
            txt += f" / 改 {n_edit}"
        self.tc_stat.config(text=txt)

    def _on_tc_edit(self, row, col, value):
        """双击改完「译名」列：记进待应用清单（原文列不可编辑）。"""
        try:
            src = self.tc_tree.item(row)["values"][2]
        except Exception:
            return
        if not str(value).strip():
            messagebox.showinfo("提示", "译名不能为空；要清空请到术语字典里删。")
            self._render_tc_rows()       # 回滚显示
            return
        self.tc_edits = getattr(self, "tc_edits", {}) or {}
        self.tc_edit_stack = getattr(self, "tc_edit_stack", []) or []
        old = ""
        for h in getattr(self, "tc_hits", []) or []:
            if h.get("src", "") == src:
                old = h.get("dst", "") or ""
                break
        if value == old:
            if src in getattr(self, "tc_edits", {}):
                del self.tc_edits[src]
        else:
            self.tc_edits[src] = value
            self.tc_edit_stack.append((src, old, value))
        self._render_tc_rows()
        self.q.put(("log", f"[术语检查] {src}：{old or '（空）'} → {value}\n"))

    def _undo_tc_edits(self):
        """撤销最近一次改动（可连续点）。"""
        stack = getattr(self, "tc_edit_stack", None) or []
        if not stack:
            messagebox.showinfo("提示", "还没有改动可以撤销")
            return
        src, old, _new = stack.pop()
        if src in self.tc_edits:
            del self.tc_edits[src]
        self._render_tc_rows()
        self.q.put(("log", f"[术语检查] 已撤销：{src} → {old or '（空）'}\n"))

    def _do_apply_tc(self):
        import term_fix as TFX

        target = self._te_target_ready(None)
        if not target:
            return
        edits = dict(getattr(self, "tc_edits", {}) or {})
        if not edits:
            messagebox.showinfo("提示", "还没有改动：双击「译名」列改一条再应用")
            return
        if not messagebox.askyesno(
                "确认",
                f"将把 {len(edits)} 条译名写进：\n"
                f"① 术语提取缓存\n"
                f"② 名字文件的译文文件（如有）\n"
                f"③ 术语表的自动提取区\n\n"
                f"整个过程不调用模型。继续？"):
            return

        def work():
            st = TFX.apply_fixes(target, edits)
            self.q.put(("termcheck_applied", st))

        self.show("log")
        self.run_async(work, label=f"写入 {len(edits)} 条译名…",
                       done_label="术语检查修改已应用")

    def _after_tc_applied(self, st):
        st = st or {}
        msg = (f"术语检查修改完成：缓存 {st.get('cache', 0)} 条、"
               f"术语表 {st.get('dict', 0)} 条")
        if st.get("files"):
            msg += f"、译文文件 {st['files']} 个"
        if st.get("missing"):
            msg += f"；有 {st['missing']} 条在译文文件里没找到对应行"
        self.q.put(("log", msg + "\n"))
        self.tc_edits = {}
        self.tc_edit_stack = []
        try:
            self._do_term_check()        # 重新检查，刷新列表
        except Exception:
            pass

    def _do_tc_retranslate(self):
        """
        「术语重翻」：对当前筛选显示的条目，删掉缓存里的 key，
        再走一遍正常翻译流水线让模型重翻（★ 会调用模型）。
        """
        import term_fix as TFX

        target = self._te_target_ready(None)
        if not target:
            return

        hits = self._tc_filtered_hits()
        items = [{"src": h.get("src", ""), "path": h.get("path", "")}
                 for h in hits if h.get("src") and h.get("path")]
        if not items:
            messagebox.showinfo(
                "提示", "当前筛选后没有可重翻的条目。\n"
                        "（请先「刷新报告」，并确认问题类型没有全被取消勾选）")
            return

        n_files = len({it["path"] for it in items})
        if not messagebox.askyesno(
                "确认重翻",
                f"将对当前筛选后显示的 {len(items)} 条术语重翻，"
                f"涉及 {n_files} 个名字文件：\n\n"
                f"① 删掉这些条目在翻译缓存里的 key\n"
                f"② 走正常翻译流水线重翻（会重新解析、注入术语、"
                f"分批送模型）\n\n"
                f"★ 这一步会调用模型，请确认已配好模型。继续？"):
            return

        def work():
            import term_extract as TE
            # ★ 逐批提取：每批翻完立刻并进术语表并重载，同一文件后续批次
            #   马上用上新译名（与术语提取页同一条流水线）。
            st = TFX.retranslate(
                target, items,
                cancel=lambda: self._cancel_flag,
                batch_term_hook=TE.make_batch_term_hook(None))
            self.q.put(("termcheck_retranslated", st))

        self.show("log")
        self.run_async(work, label=f"重翻 {len(items)} 条…",
                       done_label="术语重翻完成")

    def _after_tc_retranslated(self, st):
        st = st or {}
        msg = (f"术语重翻完成：{st.get('translated', 0)} 条 / "
               f"{st.get('files', 0)} 个文件，删掉缓存 {st.get('removed', 0)} 条")
        self.q.put(("log", msg + "\n"))
        # ★ 这条消息和 run_async 的 "done" 会落在**同一次** _pump 里，
        #   现在 self.busy 还是 True，直接 _do_term_check() 会被 busy 挡掉；
        #   挪到下一轮再刷新列表。
        try:
            self.root.after(150, self._do_term_check)
        except Exception:
            pass

    def _copy_tc_list(self):
        """把术语检查报告当前显示的内容复制成制表符分隔文本。"""
        self.copy_to_clipboard(tree_text(self.tc_tree), "术语检查列表")

    def _goto_termcheck(self):
        """术语提取 → 检查报告：带着同一个目标过去。"""
        self.show("termcheck")
        target = getattr(self, "te_target", "")
        if target:
            self._sync_te_src_labels()
            self._do_term_check()
        else:
            self.tc_info_lbl.config(text="请在右侧选择文本文件或文件夹。")

    def _sync_te_src_labels(self):
        """术语页共用 te_target，把右侧来源标签同步成当前目标。"""
        target = getattr(self, "te_target", "") or "未选择"
        for lbl in ("te_src_lbl", "tc_src_lbl"):
            w = getattr(self, lbl, None)
            if w is not None:
                try:
                    w.config(text=target)
                except Exception:
                    pass

    # ================================================================
    # 页面：翻译
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
        fp_holder = RoundCard(page, radius=16, pad=8, width=272,
                                scrollable=True)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "source")
        self.fp_translate = fp

    def _do_translate(self):
        paths = self.fp_translate.ensure()
        if not paths:
            messagebox.showwarning("提示", "请先在右侧选择要翻译的文件")
            return
        paths = self._drop_names_files(paths, "翻译")
        if not paths:
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

        # 报告页状态：report = 问题列表；conflict = 术语冲突解决视图
        self.report_mode = "report"
        self.report_hits = []
        self.report_counts = {}
        self.report_kind_vars = {}
        # ★ 术语冲突视图
        self.conflict_rows = []       # commands.load_conflict_rows() 的结果
        self.conflict_row_iids = {}   # iid → conflict_rows 下标
        self.conflict_sent_iids = {}  # iid → 句子 dict（含 src/dst/path）
        self.conflict_sel = None      # 当前选中的行下标

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.report_left = left

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
        # ★ 搜索：在报告里按关键字过滤（原文 / 译文 / 说明 / 类型 / 文件名），
        #   输入后忽略「重翻类型」勾选，方便查找历史遗留句
        #   （术语冲突视图里会连同「重翻类型」一起藏起来）
        self.report_search_box = tk.Frame(head, bg=CARD)
        self.report_search_box.pack(side="left", padx=(14, 0))
        tk.Label(self.report_search_box, text="搜索", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left", padx=(0, 4))
        self.report_search = tk.StringVar()
        self.report_search_ent = ttk.Entry(self.report_search_box,
                                           textvariable=self.report_search,
                                           width=14, font=FONT)
        self.report_search_ent.pack(side="left")
        self.report_search_ent.bind("<KeyRelease>",
                                    lambda _e: self._render_report_rows())
        self.report_search_ent.bind("<Return>",
                                    lambda _e: self._render_report_rows())
        self.report_search_ent.bind("<Escape>",
                                    lambda _e: self._clear_report_search())
        clr = tk.Label(self.report_search_box, text="[清除]", bg=CARD,
                       fg=ACCENT, font=FONT_SMALL, cursor="hand2")
        clr.pack(side="left", padx=6)
        clr.bind("<Button-1>", lambda _e: self._clear_report_search())
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
                        ("detail", 176, "来源")):
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
        tree.bind("<Double-1>", self._on_report_dblclick)
        bind_tree_wheel(tree)
        attach_tree_copy(tree, self)      # ★ 右键 / Ctrl+C 复制列表

        # ★ 底部操作区
        c3 = RoundCard(left, radius=16, pad=18, auto_height=True)
        c3.grid(row=2, column=0, sticky="ew")

        self.c3_normal = tk.Frame(c3.body, bg=CARD)
        btn_row = tk.Frame(self.c3_normal, bg=CARD)
        btn_row.pack(fill="x")
        GlassButton(btn_row, "开始重翻", width=180, height=52,
                    primary=True, bg=CARD,
                    command=self._do_retranslate_report).pack(side="left")
        self.conflict_btn = GlassButton(btn_row, "解决术语冲突", width=154,
                                        height=52, bg=CARD, font=FONT_BIG,
                                        command=self._toggle_conflict_view)
        self.conflict_btn.pack(side="left", padx=10)
        self.conflict_btn.set_enabled(False)
        GlassButton(btn_row, "复制列表", width=118, height=52, bg=CARD,
                    font=FONT_BIG,
                    command=self._copy_report_list).pack(side="left",
                                                        padx=(10, 0))
        # ★ 应用已编辑：把报告里手工改过的句子写进缓存与译文文件
        GlassButton(btn_row, "应用已编辑", width=118, height=52, bg=CARD,
                    font=FONT_BIG,
                    command=self._apply_report_edits).pack(side="left",
                                                           padx=(10, 0))
        self.report_hint = tk.Label(
            self.c3_normal,
            text="删除勾选类型的问题句缓存并重新翻译；"
                 "「译文残留控制码」等类型不参与重翻；"
                 "「应用已编辑」把双击改过的译文写进缓存与译文文件",
            bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
            wraplength=560)
        self.report_hint.pack(anchor="w", pady=(8, 0))

        self.c3_normal.pack(fill="x")

        fp_holder = RoundCard(page, radius=16, pad=8, width=272,
                                scrollable=True)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "report")
        self.fp_report = fp

        # ★ 术语冲突解决视图（占左侧主区域，与报告视图互相切换；
        #   右侧的文件面板保持不动）
        self._build_conflict_view()

    # ----------------------------------------------------------------
    # 术语冲突：上方术语列表 + 下方命中的句子
    # ----------------------------------------------------------------
    _CONFLICT_TERM_COLS = (("term", 210, "术语原文"),
                           ("old", 210, "已有译文"),
                           ("new", 210, "新增译文"),
                           ("state", 124, "状态（可点）"))

    def _build_conflict_view(self):
        page = self.pages["report"]
        view = tk.Frame(page, bg=BG_BASE)
        self.conflict_page = view
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(0, weight=3)     # 上：术语列表
        view.grid_rowconfigure(1, weight=2)     # 下：命中的句子

        # ---------- 上：术语冲突列表 ----------
        c1 = RoundCard(view, radius=16, pad=14)
        c1.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        head = tk.Frame(c1.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="术语冲突", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        self.conflict_stat = tk.Label(head, text="", bg=CARD, fg=C_KEY,
                                      font=FONT_BIG)
        self.conflict_stat.pack(side="left", padx=12)
        attach_label_copy(self.conflict_stat, self, "统计")
        GlassButton(head, "应用已编辑", width=118, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._apply_conflict_edits).pack(side="right")
        GlassButton(head, "返回报告", width=104, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._toggle_conflict_view).pack(side="right",
                                                             padx=(0, 8))

        tk.Label(c1.body,
                 text="选中一条术语 → 下方列出命中它的句子 → 点「编辑译文」"
                      "改这一句的译文；保存后该术语自动标记为「已编辑」"
                      "并排到列表最后。"
                      "也可以直接点「状态」列，手动在 待解决 / 已编辑 之间切换。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=680).pack(anchor="w", pady=(6, 0))

        wrap = tk.Frame(c1.body, bg=CARD)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        cols = [c for c, _w, _t in self._CONFLICT_TERM_COLS]
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=4)
        for c, w, t in self._CONFLICT_TERM_COLS:
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.tag_configure("k_done", background="#E4F7EA", foreground="#4A6B55")
        tree.bind("<<TreeviewSelect>>",
                  lambda _e: self._on_conflict_term_select())
        # ★ 点「状态」列 → 手动切换 待解决 / 已编辑
        tree.bind("<Button-1>", self._on_conflict_term_click)
        bind_tree_wheel(tree)
        attach_tree_copy(tree, self)
        self.conflict_term_tree = tree

        # ---------- 下：命中该术语的句子 ----------
        c2 = RoundCard(view, radius=16, pad=14)
        c2.grid(row=1, column=0, sticky="nsew")

        head2 = tk.Frame(c2.body, bg=CARD)
        head2.pack(fill="x")
        self.conflict_sent_title = tk.Label(head2, text="产生冲突的句子",
                                            bg=CARD, fg=C_TITLE,
                                            font=FONT_TITLE)
        self.conflict_sent_title.pack(side="left")
        self.conflict_edit_btn = GlassButton(
            head2, "编辑译文", width=132, height=40, primary=True, bg=CARD,
            font=FONT_BIG, command=self._conflict_edit_selected)
        self.conflict_edit_btn.pack(side="right")
        self.conflict_edit_btn.set_enabled(False)

        wrap2 = tk.Frame(c2.body, bg=CARD)
        wrap2.pack(fill="both", expand=True, pady=(8, 0))
        cols2 = ("src", "dst")
        tree2 = ttk.Treeview(wrap2, columns=cols2, show="headings", height=4)
        for c, w, t in (("src", 380, "原文"), ("dst", 380, "译文")):
            tree2.heading(c, text=t)
            tree2.column(c, width=w, anchor="w")
        sb2 = ttk.Scrollbar(wrap2, orient="vertical", command=tree2.yview)
        tree2.configure(yscrollcommand=sb2.set)
        tree2.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        tree2.bind("<Double-1>", lambda _e: self._conflict_edit_selected())
        bind_tree_wheel(tree2)
        attach_tree_copy(tree2, self)
        self.conflict_sent_tree = tree2

        tk.Label(c2.body,
                 text="译文取自翻译缓存；保存后写入缓存，"
                      "要让译文文件（*_translated.txt）也更新，"
                      "点上方「应用已编辑」。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=640).pack(anchor="w", pady=(8, 0))

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

    # ---------- 报告搜索 ----------
    def _report_search_text(self):
        """当前搜索关键字（已去首尾空白、转小写）。"""
        try:
            return (self.report_search.get() or "").strip().lower()
        except Exception:
            return ""

    def _clear_report_search(self):
        """清空搜索框并重绘报告列表。"""
        try:
            self.report_search.set("")
        except Exception:
            pass
        try:
            self.report_search_ent.focus_set()
        except Exception:
            pass
        self._render_report_rows()

    @staticmethod
    def _hit_search_text(path, h):
        """把一条报告记录拍平成小写文本，供关键字包含匹配。"""
        parts = [str(h.get(k) or "") for k in
                 ("kind", "line_no", "src", "dst", "detail",
                  "term_src", "term_old", "term_new")]
        if path:
            parts.append(str(path))
            parts.append(os.path.basename(str(path)))
        return " ".join(parts).lower()

    def _render_report_rows(self):
        """按勾选的类型过滤报告列表；搜索框有内容时忽略类型勾选。"""
        if getattr(self, "report_mode", "report") == "conflict":
            return
        tree = self.report_tree
        for iid in tree.get_children():
            tree.delete(iid)
        sel = set(self._selected_kinds())
        has_filter = bool(getattr(self, "report_kind_vars", {}))
        kw = self._report_search_text()
        shown = 0
        # ★ 行号 → hit 的映射：双击时要拿回完整原文（列表里是截断显示的）
        self.report_iid_map = {}
        for _path, h in getattr(self, "report_hits", []):
            kind = h.get("kind", "")
            if kw:
                # 搜索模式：在全量记录里找，不受「重翻类型」勾选限制
                if kw not in self._hit_search_text(_path, h):
                    continue
            elif has_filter and kind not in sel:
                continue
            shown += 1
            # ★ 说明列显示该句所属的源文件名（多文件报告一眼区分）；
            #   report_iid_map 存 (path, hit)，编辑时能精确定位对应缓存
            iid = tree.insert("", "end", values=(
                kind, h.get("line_no", ""),
                (h.get("src") or "")[:200],
                (h.get("dst") or "")[:200],
                (os.path.basename(_path)
                 if _path else (h.get("detail") or ""))[:200],
            ))
            self.report_iid_map[iid] = (_path, h)
        total = commands.count_problems(getattr(self, "report_hits", []))
        if kw:
            short = kw if len(kw) <= 12 else kw[:12] + "…"
            self.report_stat.config(
                text=f"搜索「{short}」：{shown} / {total} 处")
        else:
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
            self._show_report_view()

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
                  "「译文残留控制码」等类型不参与重翻；"
                  "「应用已编辑」把双击改过的译文写进缓存与译文文件"))
        self.status_var.set(
            f"检查完成：{commands.count_problems(hits)} 处问题 / "
            f"{len(result or {})} 个文件")

    # ----------------------------------------------------------------
    # 术语冲突：上方术语列表 + 下方命中的句子
    # ----------------------------------------------------------------
    def _conflict_source_paths(self):
        """冲突视图要读哪些源文件的记录：优先用右侧已选文件。"""
        paths = self._report_sources()
        if paths:
            return paths
        out = []
        for path, _h in getattr(self, "report_hits", []):
            sp = commands.source_path_for_report(path)
            if sp and sp not in out:
                out.append(sp)
        return out

    def _show_conflict_view(self, rows=None):
        """进入术语冲突视图：占左侧主区域（右侧文件面板不动）。"""
        self.report_mode = "conflict"
        self.report_left.grid_remove()
        self.conflict_page.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._load_conflict_view(rows)

    def _show_report_view(self):
        """回到报告视图（问题列表）。"""
        self.report_mode = "report"
        try:
            self.conflict_page.grid_remove()
        except Exception:
            pass
        self.report_left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

    def _load_conflict_view(self, rows=None):
        """读冲突记录 → 刷新上下两个列表（默认选中第一条术语）。"""
        if rows is None:
            rows = commands.load_conflict_rows(self._conflict_source_paths())
        self.conflict_rows = rows
        self.conflict_sel = 0 if rows else None
        self._render_conflict_terms()
        self._render_conflict_sents(self.conflict_sel)
        return rows

    def _render_conflict_terms(self):
        """渲染上方术语列表：待解决在前、已编辑在后。"""
        tree = self.conflict_term_tree
        for iid in tree.get_children():
            tree.delete(iid)
        self.conflict_row_iids = {}
        for idx, row in enumerate(self.conflict_rows):
            iid = tree.insert("", "end", values=(
                row.get("term", ""), row.get("old", ""), row.get("new", ""),
                "已编辑" if row.get("edited") else "待解决",
            ), tags=("k_done",) if row.get("edited") else ())
            self.conflict_row_iids[iid] = idx

        n = len(self.conflict_rows)
        n_open = sum(1 for r in self.conflict_rows if not r.get("edited"))
        self.conflict_stat.config(
            text=f"待解决 {n_open} / 共 {n} 条" if n else "没有术语冲突")

        if self.conflict_sel is not None:
            for iid, idx in self.conflict_row_iids.items():
                if idx == self.conflict_sel:
                    tree.selection_set(iid)
                    tree.see(iid)
                    break

    def _on_conflict_term_select(self):
        sel = self.conflict_term_tree.selection()
        idx = self.conflict_row_iids.get(sel[0]) if sel else None
        self.conflict_sel = idx
        self._render_conflict_sents(idx)

    def _on_conflict_term_click(self, event):
        """
        点「状态」列 → 主动在 待解决 / 已编辑 之间切换（立即写回 json）。

        返回 None，让 Treeview 继续做默认的选中处理。
        """
        tree = self.conflict_term_tree
        if tree.identify_region(event.x, event.y) != "cell":
            return
        if tree.identify_column(event.x) != "#4":
            return
        iid = tree.identify_row(event.y)
        idx = self.conflict_row_iids.get(iid) if iid else None
        if idx is None or not (0 <= idx < len(self.conflict_rows)):
            return

        row = self.conflict_rows[idx]
        new_state = not bool(row.get("edited"))
        srcs = row.get("sources") or []
        try:
            commands.set_term_conflicts_edited(row.get("term", ""), srcs,
                                               new_state)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return

        row["edited"] = new_state
        if new_state:
            # 手动标为已编辑 → 与「保存译文」一样排到最下方
            self._conflict_seq = getattr(self, "_conflict_seq", 0) + 1
            row["_edited_seq"] = self._conflict_seq
        else:
            row.pop("_edited_seq", None)
        self._resort_conflict_rows(row)
        self.status_var.set(
            f"术语冲突「{row.get('term', '')}」已标记为"
            f"{'已编辑' if new_state else '待解决'}")

    def _render_conflict_sents(self, idx):
        """渲染下方句子列表：原文 + 该句当前缓存译文。"""
        tree = self.conflict_sent_tree
        for iid in tree.get_children():
            tree.delete(iid)
        self.conflict_sent_iids = {}

        row = None
        if idx is not None and 0 <= idx < len(self.conflict_rows):
            row = self.conflict_rows[idx]
        if row is None:
            self.conflict_sent_title.config(text="产生冲突的句子")
            self.conflict_edit_btn.set_enabled(False)
            return

        self.conflict_sent_title.config(
            text=f"产生冲突的句子 · {row.get('term', '')}")
        for s in row.get("sents", []):
            iid = tree.insert("", "end", values=(
                (s.get("src") or "")[:300], (s.get("dst") or "")[:300]))
            self.conflict_sent_iids[iid] = s
        if not row.get("sents"):
            tree.insert("", "end", values=("（这条冲突没有记录到具体句子）", ""))
        self.conflict_edit_btn.set_enabled(bool(row.get("sents")))

    def _toggle_conflict_view(self):
        """「解决术语冲突」/「返回报告」：在报告与冲突视图之间切换。"""
        if getattr(self, "report_mode", "report") == "conflict":
            self._show_report_view()
            self._render_report_rows()
            self._refresh_conflict_btn()
            return

        srcs = self._conflict_source_paths()
        if not srcs:
            messagebox.showinfo(
                "提示", "请先在右侧选择检查报告（*_translated_report.txt）")
            return
        rows = commands.load_conflict_rows(srcs)
        if not rows:
            messagebox.showinfo(
                "提示", "这些文件里没有术语冲突记录。\n\n"
                        "术语冲突是翻译时记录下来的：模型给某个术语的译法与"
                        "术语表不一致时才会产生。")
            return
        self._show_conflict_view(rows)
        self.conflict_btn.set_enabled(False)

    def _refresh_conflict_btn(self):
        n = sum(1 for _p, h in getattr(self, "report_hits", [])
                if h.get("kind") == "术语冲突")
        try:
            self.conflict_btn.set_enabled(
                n > 0 and self.report_mode != "conflict")
        except Exception:
            pass

    def _conflict_edit_selected(self):
        """「编辑译文」：编辑下方选中那句的译文。"""
        if getattr(self, "report_mode", "report") != "conflict":
            return
        sel = self.conflict_sent_tree.selection()
        info = self.conflict_sent_iids.get(sel[0]) if sel else None
        if info is None:
            messagebox.showinfo("提示", "请先在下方列表里选中要编辑的句子")
            return
        row = None
        if self.conflict_sel is not None \
                and 0 <= self.conflict_sel < len(self.conflict_rows):
            row = self.conflict_rows[self.conflict_sel]
        if row is None:
            return
        self._open_conflict_edit(row, info)

    def _open_conflict_edit(self, row, info):
        """
        术语冲突里改一句译文：
        上方原文（只读，供对照）、下方译文（可编辑）。
        保存后写入该句所属文件的翻译缓存，并把这条术语冲突标记为「已编辑」。
        """
        src = info.get("src") or ""
        dst = info.get("dst") or ""
        src_path = info.get("path") or ""
        term = row.get("term") or ""
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

        tk.Label(body, text=f"编辑译文 · 术语冲突「{term}」", bg=CARD,
                 fg=C_TITLE, font=FONT_TITLE).pack(anchor="w")
        tk.Label(body,
                 text=(f"术语「{term}」：已有译文「{row.get('old', '')}」，"
                       f"模型返回「{row.get('new', '')}」。\n"
                       "保存后：这一句的译文写入翻译缓存，该术语标记为"
                       "「已编辑」并排到列表最后。"),
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=600).pack(anchor="w", pady=(4, 10))

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
                res = commands.save_report_edit(src, new, src_path or None)
            except Exception as e:
                messagebox.showerror("保存失败", str(e))
                return
            # 标记「已编辑」：该术语可能记在多个文件的冲突记录里
            srcs = row.get("sources") or ([src_path] if src_path else [])
            commands.set_term_conflicts_edited(term, srcs, True)
            info["dst"] = new
            row["edited"] = True
            win.destroy()
            self._after_conflict_saved(row)
            self._append_log(
                f"[术语冲突] 已编辑译文并写入缓存：{os.path.basename(res['cache'])}"
                f"（术语「{term}」标记为已编辑）\n")

        def cancel():
            win.destroy()

        bar = tk.Frame(body, bg=CARD)
        bar.pack(fill="x")
        GlassButton(bar, "取消", width=92, height=40, bg=CARD,
                    font=FONT_SMALL, command=cancel).pack(side="right")
        GlassButton(bar, "确定并保存", width=150, height=40, primary=True,
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

    def _resort_conflict_rows(self, keep_row):
        """
        重排上方列表：待解决在前，已编辑在后，并让 keep_row 保持选中。

        ★ 已编辑的按「本次标记的先后」排在后面 —— 刚处理的那条一定落到
          最底部（旧记录可能本来就多，只按术语名排就可能把它顶到中间）。
        """
        self.conflict_rows.sort(key=lambda r: (
            bool(r.get("edited")),
            r.get("_edited_seq", 0),
            (r.get("term") or "").lower(),
        ))
        try:
            self.conflict_sel = self.conflict_rows.index(keep_row)
        except ValueError:
            self.conflict_sel = None
        self._render_conflict_terms()
        self._render_conflict_sents(self.conflict_sel)

    def _after_conflict_saved(self, row):
        """保存译文后：该术语置为已编辑 → 排到最后，并保持它仍被选中。"""
        self._conflict_seq = getattr(self, "_conflict_seq", 0) + 1
        row["_edited_seq"] = self._conflict_seq
        self._resort_conflict_rows(row)
        n_open = sum(1 for r in self.conflict_rows if not r.get("edited"))
        self.status_var.set(
            f"已保存译文并写入缓存：术语「{row.get('term', '')}」标记为已编辑"
            f"（剩余待解决 {n_open} 条）")

    def _apply_conflict_edits(self):
        """
        冲突视图的「应用已编辑」：把手工译文写进缓存与译文文件，
        同时把**已编辑**的术语冲突从 <名>_conflicts.json 里删掉。
        """
        paths = self._report_sources()
        if not paths:
            messagebox.showwarning(
                "提示", "请先在右侧选择检查报告（*_translated_report.txt）")
            return
        try:
            n_files, n_edit = commands.count_manual_edits(paths)
        except Exception:
            n_files, n_edit = 0, 0
        n_done = sum(1 for r in self.conflict_rows if r.get("edited"))
        if not n_edit and not n_done:
            messagebox.showinfo(
                "没有可应用的内容",
                "这些文件还没有手工编辑记录，也没有已编辑的术语冲突。\n\n"
                "先在下方列表选中句子、点「编辑译文」改好并保存，"
                "或者直接点上方「状态」列把冲突标成「已编辑」，"
                "再回来点这个按钮。")
            return

        msg = (f"将把 {n_files} 个文件里的 {n_edit} 条手工编辑译文写入：\n"
               f"· 翻译缓存（<主名>_cache.json）\n"
               f"· 已生成的译文文件（<主名>_translated.txt）\n\n")
        if n_done:
            msg += (f"并把 {n_done} 条**已编辑**的术语冲突从\n"
                    f"<主名>_conflicts.json 里删除。\n\n")
        msg += "译文文件里其它行不会被改动。\n继续吗？"
        if not messagebox.askyesno("应用已编辑", msg):
            return

        def work():
            res = commands.apply_manual_edits(paths)
            removed, cfiles = commands.drop_edited_term_conflicts(paths)
            self.q.put(("conflict_applied", (res, removed, cfiles)))
            return res

        self.run_async(work, label="应用已编辑…", done_label="已应用手工编辑")

    def _after_conflict_applied(self, payload):
        """应用已编辑完成：提示结果，并刷新冲突列表（已编辑的已从记录删除）。"""
        res, removed, cfiles = (payload if isinstance(payload, tuple)
                                else (payload, 0, 0))
        r = res or {}
        messagebox.showinfo(
            "应用已编辑",
            f"写入缓存与译文文件：{r.get('files', 0)} 个文件 / "
            f"{r.get('applied', 0)} 句\n"
            + (f"缺少译文文件：{r.get('missing', 0)} 个\n"
               if r.get("missing") else "")
            + (f"已编辑的术语冲突：{removed} 条已从 "
               f"{cfiles} 个 <主名>_conflicts.json 里删除\n"
               if removed else
               "没有已编辑的术语冲突需要清理（待解决的仍留在列表里）\n")
            + "\n点「刷新报告」可让报告里的术语冲突一起消失。")
        if getattr(self, "report_mode", "report") == "conflict":
            self._load_conflict_view()
            if not self.conflict_rows:
                self._show_report_view()
                self._render_report_rows()
                self._refresh_conflict_btn()
        else:
            self._refresh_conflict_btn()

    def _on_report_dblclick(self, event):
        """报告列表双击 → 弹窗编辑这一句的译文。"""
        tree = self.report_tree
        iid = tree.identify_row(event.y)
        if not iid:
            return
        hit = getattr(self, "report_iid_map", {}).get(iid)
        if hit is None:
            return
        # hit = (源文件路径, hit dict)
        if isinstance(hit, tuple):
            src_path, hit = hit
        else:
            src_path = None
        self._open_report_edit(iid, hit, src_path=src_path)

    def _open_report_edit(self, iid, hit, src_path=None):
        """
        编辑单句译文：上方原文（只读，用来对照）、下方译文（可编辑）。
        保存后写入翻译缓存，并把这句归入「已编辑」类型。
        src_path: 该行属于哪个源文件（多文件报告时精确锁定对应缓存）。
        """
        src = hit.get("src") or ""
        dst = hit.get("dst") or ""
        # ★ 原类型是「需手动」（不自动重翻）时：保存后立即写缓存+译文文件，
        #   不再等「应用已编辑」。先记下原类型（保存后 hit 会被改成「已编辑」）。
        orig_kind = hit.get("kind") or ""
        manual_kind = orig_kind in commands.NEVER_RETRANSLATE_KINDS
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
                 text=("保存后：写入翻译缓存**并直接更新译文文件**，"
                       "并把这一句归入「已编辑」类型"
                       "（默认不勾选，也不会被重翻覆盖）。"
                       if manual_kind else
                       "保存后：写入翻译缓存，并把这一句归入「已编辑」类型"
                       "（默认不勾选，也不会被重翻覆盖）。"),
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
                if manual_kind:
                    res = commands.save_report_edit_and_apply(src, new,
                                                              src_path=src_path)
                else:
                    res = commands.save_report_edit(src, new,
                                                    src_path=src_path)
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
            if manual_kind and res.get("file_written"):
                self.status_var.set("已保存：译文写入缓存与译文文件，该句归入「已编辑」")
                self._append_log(f"[编辑] 已写入缓存与译文文件："
                                 f"{os.path.basename(res['cache'])}"
                                 f"（{len(new)} 字）\n")
            else:
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

    def _report_sources(self):
        """重翻检查报告页选的是检查报告，这里换回真正的源文件。"""
        paths = self.fp_report.ensure()
        srcs = []
        for p in paths:
            s = commands.source_path_for_report(p)
            if s:
                srcs.append(s)
            else:
                self._append_log(f"[跳过] 找不到报告对应的源文件：{p}\n")
        return self._drop_names_files(srcs, "检查报告 / 重翻")

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

        fp_holder = RoundCard(page, radius=16, pad=8, width=272,
                                scrollable=True)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "cache")
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
            # ★ manual=True：用户手工敲的术语写进「手工区」（AUTO 块之外），
            #   这样它不会被「一键删除自动提取术语」误删，
            #   也才算得上「手工术语」——整句术语直译只认这类词条。
            ok, msg, key = TS.add_term(src, dst, manual=True)
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

        fp_holder = RoundCard(page, radius=16, pad=8, width=272,
                                scrollable=True)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "cache")
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
            messagebox.showwarning("提示", "请先选择翻译缓存（*_cache.json）")
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

        # 勾选了缓存就顺带把前缀重新拼回译文，没有就只更新字典
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
               "· 保留全部控制码；控制码不一致的条目保留原译文\n"
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

        fp_holder = RoundCard(page, radius=16, pad=8, width=272,
                                scrollable=True)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        fp = self._make_file_panel(fp_holder, "cache")
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
        fp_holder = RoundCard(page, radius=16, pad=8, width=272,
                                scrollable=True)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        self.fp_reflow = self._make_file_panel(fp_holder, "translated",
                                               allow_game_root=True)

    def _build_reflow_panel(self, body):
        self.reflow_cfgs = {}
        self._reflow_cfg_frames = {}
        self._reflow_mode = "newline"
        self._reflow_data = {"newline": [], "space": []}
        # ★ 选中的区块（存 id，按模式分开）；刷新列表 / 切页签后仍能恢复
        self._reflow_sel_ids = {"newline": set(), "space": set()}
        self._reflow_restoring = False

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
                 text="只重排换行方式，不改动译文文字；两种重排各用一套参数"
                      "（会保存到设置）；在左边列表里选中区块后，"
                      "重排只对选中的区块生效",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=560).pack(anchor="w", pady=(4, 0))

        # ★ 区块选择：勾选「仅重排选中的区块」后，未选中的区块原样保留
        selrow = tk.Frame(body, bg=CARD)
        selrow.pack(fill="x", pady=(6, 0))
        self.reflow_only_sel = tk.BooleanVar(value=True)
        tk.Checkbutton(selrow, text="仅重排选中的区块",
                       variable=self.reflow_only_sel, bg=CARD, fg=C_KEY,
                       activebackground=CARD, activeforeground=TEXT,
                       selectcolor="#FFFFFF", font=FONT_SMALL,
                       cursor="hand2",
                       command=self._update_reflow_sel_label).pack(side="left")
        for text, val in (("全选", True), ("全不选", False)):
            lbl = tk.Label(selrow, text=f"[{text}]", bg=CARD, fg=ACCENT,
                           font=FONT_SMALL, cursor="hand2")
            lbl.pack(side="left", padx=(10, 0))
            lbl.bind("<Button-1>",
                     lambda _e, v=val: self._reflow_select_all(v))
        self.reflow_sel_lbl = tk.Label(selrow, text="", bg=CARD, fg=C_HINT,
                                       font=FONT_SMALL)
        self.reflow_sel_lbl.pack(side="left", padx=10)

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
                            show="headings", height=3,
                            selectmode="extended")     # ★ 可多选（Ctrl/Shift）
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
        tree.bind("<<TreeviewSelect>>", self._on_reflow_select)
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
                f"· Scripts.rxdata 里本工具插进去的那条脚本（如果是塞脚本的方式，"
                f"它在 Main 前面）\n"
                f"· Fonts 里当初复制进去的字体（游戏自带字体不动）\n"
                f"· 引擎脚本里被改过的字体定义（还原成游戏原来的字体）\n\n"
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
        self._reflow_restoring = True
        try:
            for iid in tree.get_children():
                tree.delete(iid)
            blocks = self._reflow_data.get(mode, [])
            saved = getattr(self, "_reflow_sel_ids", {}).get(mode, set())
            total = 0
            sel_ids = []
            for pos, b in enumerate(blocks):
                tree.insert("", "end", iid=str(pos),
                            values=(f"{b['file']} · {b['block']}", b["total"]))
                total += b["total"]
                if b.get("id") in saved:
                    sel_ids.append(str(pos))
            if sel_ids:
                tree.selection_set(sel_ids)
        finally:
            self._reflow_restoring = False
        self.reflow_stat.config(
            text=f"{len(blocks)} 个区块 / {total} 条译文")
        self._update_reflow_sel_label()

    # ---------- 区块选择 ----------
    def _on_reflow_select(self, _e=None):
        """列表选择变化 → 记下选中的区块 id，并刷新右侧预览。"""
        if getattr(self, "_reflow_restoring", False):
            return
        mode = getattr(self, "_reflow_mode", "newline")
        tree = getattr(self, "reflow_tree", None)
        if tree is None or not tree.winfo_exists():
            return
        blocks = self._reflow_data.get(mode, [])
        ids = set()
        for iid in tree.selection():
            try:
                pos = tree.index(iid)
            except Exception:
                continue
            if 0 <= pos < len(blocks):
                ids.add(blocks[pos]["id"])
        self._reflow_sel_ids[mode] = ids
        self._update_reflow_sel_label()
        self._render_reflow_block()

    def _reflow_select_all(self, value):
        """全选 / 全不选当前页签里的区块。"""
        mode = getattr(self, "_reflow_mode", "newline")
        tree = getattr(self, "reflow_tree", None)
        if tree is None or not tree.winfo_exists():
            return
        kids = tree.get_children()
        self._reflow_restoring = True
        try:
            if value:
                tree.selection_set(kids)
            else:
                tree.selection_remove(kids)
        finally:
            self._reflow_restoring = False
        blocks = self._reflow_data.get(mode, [])
        self._reflow_sel_ids[mode] = ({b["id"] for b in blocks} if value
                                     else set())
        self._update_reflow_sel_label()
        self._render_reflow_block()

    def _reflow_sel_label_text(self):
        """选中区块的统计文字（跨两个页签一起算）。"""
        sel = getattr(self, "_reflow_sel_ids", {}) or {}
        n_blocks = n_rows = 0
        for mode in ("newline", "space"):
            ids = sel.get(mode) or set()
            if not ids:
                continue
            for b in self._reflow_data.get(mode, []):
                if b.get("id") in ids:
                    n_blocks += 1
                    n_rows += b.get("total", 0)
        return n_blocks, n_rows

    def _update_reflow_sel_label(self):
        lbl = getattr(self, "reflow_sel_lbl", None)
        if lbl is None or not lbl.winfo_exists():
            return
        try:
            on = bool(self.reflow_only_sel.get())
        except Exception:
            on = True
        n_blocks, n_rows = self._reflow_sel_label_text()
        mode = getattr(self, "_reflow_mode", "newline")
        cur = len((getattr(self, "_reflow_sel_ids", {}) or {}).get(mode) or ())
        if n_blocks:
            txt = f"已选 {n_blocks} 个区块 / {n_rows} 条（本页 {cur} 个）"
        else:
            txt = "未选区块" if on else "重排全部区块"
        lbl.config(text=txt, fg=C_KEY if on else C_HINT)

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
                if len(sel) > 1:
                    lines.append(f"（另外还选中了 {len(sel) - 1} 个区块）")
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
            messagebox.showwarning("提示", "请先在右侧选择要重排的文件")
            return
        paths = self._drop_names_files(paths, "换行重排")
        if not paths:
            return

        # ★ 重排范围：勾了「仅重排选中的区块」就只动选中的那些
        #   （先定范围再写设置：用户中途取消时不该动配置文件）
        try:
            only_sel = bool(self.reflow_only_sel.get())
        except Exception:
            only_sel = True
        sel = set()
        for ids in (getattr(self, "_reflow_sel_ids", {}) or {}).values():
            sel |= (ids or set())
        if only_sel and not sel:
            if not messagebox.askyesno(
                    "没有选中区块",
                    "现在勾着「仅重排选中的区块」，但列表里一个区块都没选。\n\n"
                    "要改成重排**全部区块**吗？\n"
                    "（想只重排一部分，请先在左边列表里点选区块，"
                    "按住 Ctrl / Shift 可多选，也可以点 [全选]）"):
                return
            only_sel = False

        # 把两套参数写回设置（同时校验格式）
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
        blocks = sorted(sel) if only_sel else None

        self.show("log")
        self.run_async(
            lambda: commands.reflow_paths(paths, newline_cfg, space_cfg,
                                          blocks=blocks),
            label=(f"换行重排（选中 {len(blocks)} 个区块）…" if blocks
                   else "换行重排（全部区块）…"),
            done_label="换行重排完成")

    # ================================================================
    # 页面 7：术语字典（Excel 转术语表 + 查看 / 编辑术语字典）
    # ================================================================
    def _page_excel(self):
        page = self.pages["excel"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        # ★ 同一页两个视图：Excel 转换 / 术语字典，卡片上的按钮互相切换
        self.excel_view = tk.Frame(page, bg=BG_BASE)
        self.excel_view.grid(row=0, column=0, sticky="nsew")
        self.excel_view.grid_columnconfigure(0, weight=1)
        self.excel_view.grid_rowconfigure(0, weight=1)

        left = tk.Frame(self.excel_view, bg=BG_BASE)
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
        # ★ 「全选」右侧：切到术语字典列表（查看 / 修改 / 删除术语）
        GlassButton(head, "术语字典", width=92, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._show_termdict_view).pack(side="left",
                                                           padx=(8, 0))
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

        right = tk.Frame(self.excel_view, bg=BG_BASE, width=330)
        right.grid(row=0, column=1, sticky="nsew")
        right.pack_propagate(False)
        card = RoundCard(right, radius=16, pad=14, scrollable=True)
        card.pack(fill="both", expand=True)
        tk.Label(card.body, text="提示", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(card.body,
                 text="表头要同时含所选的两种语言列名，多个工作表会跨表去重，"
                      "默认「已有术语只加不覆盖」，新译法与旧译法不同会提示冲突。",
                 bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(10, 0))

        self._build_termdict_view(page)

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
                    f"内容（在「术语字典」里校对过的译法也会丢）。\n\n确定要覆盖吗？"):
                return

        def work():
            res = commands.build_terms_from_excel(path, sheets or None, src,
                                                  tgt, mode=mode)
            self.q.put(("excel_done", res))
            return res

        self.show("log")
        self.run_async(work, label="Excel 转换中…", done_label="转换完成")

    # ----------------------------------------------------------------
    # 术语字典视图（Excel 转换页的第二个视图）
    # ----------------------------------------------------------------
    def _build_termdict_view(self, page):
        """构建「术语字典」列表视图：查看 / 修改 / 新增 / 删除 / 撤回。"""
        view = tk.Frame(page, bg=BG_BASE)
        view.grid(row=0, column=0, sticky="nsew")
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(0, weight=1)
        self.termdict_view = view
        view.grid_remove()          # 默认显示 Excel 转换视图

        left = tk.Frame(view, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # 顶部：标题 + 搜索 / 来源过滤 + 返回
        c1 = RoundCard(left, radius=16, pad=14, auto_height=True)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        head = tk.Frame(c1.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="术语字典", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")
        GlassButton(head, "返回 Excel 转换", width=150, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._show_excel_view).pack(side="right")
        self.dict_stat = tk.Label(head, text="", bg=CARD, fg=C_KEY,
                                  font=FONT_BIG)
        self.dict_stat.pack(side="right", padx=12)
        attach_label_copy(self.dict_stat, self, "统计")

        bar = tk.Frame(c1.body, bg=CARD)
        bar.pack(fill="x", pady=(8, 0))
        tk.Label(bar, text="搜索", bg=CARD, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")
        self.dict_search = tk.StringVar()
        dent = ttk.Entry(bar, textvariable=self.dict_search, width=14,
                         font=FONT)
        dent.pack(side="left", padx=8)
        dent.bind("<KeyRelease>", lambda e: self._filter_dict_rows())
        dent.bind("<Escape>", lambda e: self._clear_dict_search())
        clr = tk.Label(bar, text="[清除]", bg=CARD, fg=ACCENT,
                       font=FONT_SMALL, cursor="hand2")
        clr.pack(side="left")
        clr.bind("<Button-1>", lambda e: self._clear_dict_search())

        self.dict_origin = tk.StringVar(value=DE.ORIGIN_ALL)
        for lab, val in ((DE.ORIGIN_ALL, DE.ORIGIN_ALL),
                         ("自动提取", DE.ORIGIN_AUTO),
                         ("手动录入", DE.ORIGIN_MANUAL)):
            tk.Radiobutton(bar, text=lab, value=val,
                           variable=self.dict_origin, bg=CARD, fg=TEXT,
                           activebackground=CARD, selectcolor="#FFFFFF",
                           font=FONT_SMALL,
                           command=self._filter_dict_rows).pack(side="left",
                                                                padx=4)
        GlassButton(bar, "重新载入", width=92, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._reload_dict_rows).pack(side="left", padx=8)

        # 中部：列表
        c2 = RoundCard(left, radius=16, pad=14)
        c2.grid(row=1, column=0, sticky="nsew")
        selbar = tk.Frame(c2.body, bg=CARD)
        selbar.pack(fill="x")
        self.dict_all_var = tk.IntVar(value=0)
        self.dict_all_chk = tk.Checkbutton(
            selbar, text="全选", variable=self.dict_all_var,
            onvalue=1, offvalue=0, tristatevalue=-1,
            bg=CARD, fg=TEXT, activebackground=CARD,
            selectcolor="#FFFFFF", font=FONT_SMALL,
            command=self._on_dict_toggle_all)
        self.dict_all_chk.pack(side="left")
        self.dict_check_stat = tk.Label(selbar, text="已选 0 条", bg=CARD,
                                        fg=C_KEY, font=FONT_BIG)
        self.dict_check_stat.pack(side="left", padx=10)
        self.dict_pending_lbl = tk.Label(selbar, text="", bg=CARD,
                                         fg=C_HINT, font=FONT_SMALL)
        self.dict_pending_lbl.pack(side="right")

        wrap = tk.Frame(c2.body, bg=CARD)
        wrap.pack(fill="both", expand=True, pady=(6, 0))
        cols = ("sel", "origin", "src", "dst")
        tree = ttk.Treeview(wrap, columns=cols, show="headings",
                            height=4, selectmode="extended")
        for c, w, t in (("sel", 34, "✓"), ("origin", 92, "来源"),
                        ("src", 250, "原文（可编辑）"),
                        ("dst", 250, "译文（可编辑）")):
            tree.heading(c, text=t)
            tree.column(c, width=w,
                        anchor="center" if c == "sel" else "w")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        # ★ 原文 / 译文都能双击直接改（#1 是复选框列）
        bind_tree_edit(tree, {"#3": True, "#4": True},
                       on_commit=self._on_dict_edit)
        bind_tree_wheel(tree)
        attach_tree_copy(tree, self)
        tree.bind("<Button-1>", self._on_dict_tree_click, add="+")
        tree.bind("<Double-1>", self._on_dict_tree_dblclick, add="+")
        self.dict_tree = tree

        hint_row = tk.Frame(c2.body, bg=CARD)
        hint_row.pack(fill="x", pady=(10, 0))
        self.dict_hint = tk.Label(
            hint_row,
            text="改动先记在内存里，点「保存」才写入 term_dict.py（可「撤回」）",
            bg=CARD, fg=C_HINT, font=FONT_SMALL)
        self.dict_hint.pack(side="left")

        bottom = tk.Frame(c2.body, bg=CARD)
        bottom.pack(fill="x", pady=(6, 0))
        btns = tk.Frame(bottom, bg=CARD)
        btns.pack(side="right")
        GlassButton(btns, "新增术语", width=96, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_dict_add).pack(side="left", padx=3)
        GlassButton(btns, "修改选中", width=96, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_dict_edit_selected).pack(side="left",
                                                              padx=3)
        GlassButton(btns, "删除选中", width=96, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_dict_delete_selected).pack(side="left",
                                                                padx=3)
        self.dict_auto_btn = GlassButton(
            btns, "一键删除自动术语", width=148, height=40, bg=CARD,
            font=FONT_SMALL, command=self._on_dict_delete_auto)
        self.dict_auto_btn.pack(side="left", padx=3)
        GlassButton(btns, "撤回", width=68, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._on_dict_undo).pack(side="left", padx=3)
        self.dict_save_btn = GlassButton(
            btns, "保存", width=104, height=44, primary=True, bg=CARD,
            command=self._on_dict_save)
        self.dict_save_btn.pack(side="left", padx=(8, 0))

        # 右列提示
        right = tk.Frame(view, bg=BG_BASE, width=316)
        right.grid(row=0, column=1, sticky="nsew")
        right.pack_propagate(False)
        card = RoundCard(right, radius=16, pad=14, scrollable=True)
        card.pack(fill="both", expand=True)
        tk.Label(card.body, text="术语字典", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(card.body,
                 text="双击改原文/译文，点「保存」写进 term_dict.py、"
                      "点「撤回」可逐步回退；「一键删除自动术语」只清自动提取的词。",
                 bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                 justify="left").pack(anchor="w", pady=(10, 0))
        self.dict_file_lbl = tk.Label(
            card.body, text="", bg=CARD, fg=C_HINT, font=FONT_SMALL,
            justify="left", wraplength=268)
        self.dict_file_lbl.pack(anchor="w", pady=(12, 0))
        attach_label_copy(self.dict_file_lbl, self, "术语字典")

    # ---------- 视图切换 ----------
    def _show_termdict_view(self):
        """Excel 转换 → 术语字典列表。"""
        if self.dict_editor is None:
            try:
                self.dict_editor = DE.TermDictEditor()
            except Exception as e:
                messagebox.showerror(
                    "读取失败", f"读取术语字典失败：\n{e}\n\n{config.TERM_FILE}")
                return
            self.dict_checks = set()
        elif not self.dict_editor.is_dirty():
            # 术语重翻 / Excel 转换可能刚改过 term_dict.py：没有未保存改动时
            # 悄悄重读一遍；有改动就原样留着（要重读请点「重新载入」）
            try:
                self.dict_editor.reload()
            except Exception as e:
                self.q.put(("log", f"术语字典重读失败：{e}\n"))
        self.excel_view.grid_remove()
        self.termdict_view.grid()
        self._load_dict_rows()

    def _show_excel_view(self):
        """术语字典列表 → Excel 转换（有未保存改动先问一句）。"""
        if not self._confirm_dict_leaving():
            return
        self.termdict_view.grid_remove()
        self.excel_view.grid()

    def _confirm_dict_leaving(self):
        ed = self.dict_editor
        if ed is None or not ed.is_dirty():
            return True
        ans = messagebox.askyesnocancel(
            "术语字典有未保存的改动",
            f"{ed.pending_text()}\n\n现在保存吗？\n"
            "· 是：保存后离开\n"
            "· 否：先留着（还在内存里，回到这个列表就能接着改）\n"
            "· 取消：留在当前列表")
        if ans is None:
            return False
        if ans:
            return self._save_dict()
        return True

    # ---------- 载入 / 过滤 ----------
    def _load_dict_rows(self):
        ed = self.dict_editor
        if ed is None:
            return
        self.dict_loaded = True
        if hasattr(self, "dict_file_lbl"):
            self.dict_file_lbl.config(text=f"字典文件：\n{config.TERM_FILE}")
        self._filter_dict_rows()

    def _reload_dict_rows(self):
        """丢弃内存里的改动，重新从 term_dict.py 读一遍。"""
        ed = self.dict_editor
        if ed is None:
            return
        if ed.is_dirty() and not messagebox.askyesno(
                "重新载入",
                f"{ed.pending_text()}\n\n重新载入会丢掉这些改动，继续吗？"):
            return
        try:
            ed.reload()
        except Exception as e:
            messagebox.showerror(
                "读取失败", f"读取术语字典失败：\n{e}\n\n{config.TERM_FILE}")
            return
        self.dict_checks = set()
        self._load_dict_rows()

    def _clear_dict_search(self):
        try:
            self.dict_search.set("")
        except Exception:
            pass
        self._filter_dict_rows()

    def _filter_dict_rows(self):
        """按搜索词 / 来源过滤，重建字典列表。"""
        ed = self.dict_editor
        if ed is None or not hasattr(self, "dict_tree"):
            return
        tree = self.dict_tree
        for iid in tree.get_children():
            tree.delete(iid)
        self.dict_row_orig = {}
        self.dict_visible = []
        kw = (self.dict_search.get() or "").strip()
        origin = self.dict_origin.get()
        rows, matched = ed.rows(query=kw, origin=origin,
                                limit=self.dict_show_limit)
        # 有未保存改动的行打个「·改」标记（新增的单独标「新增」）
        dirty = set(ed.changed) | set(ed.renamed)

        for orig, src, dst, org in rows:
            mark = (TERM_CHECK_ON if orig in self.dict_checks
                    else TERM_CHECK_OFF)
            if orig in ed.added:
                label = "新增"
            else:
                label = org + ("·改" if orig in dirty else "")
            iid = tree.insert("", "end", values=(mark, label, src, dst))
            self.dict_row_orig[iid] = orig
            self.dict_visible.append(orig)

        total, pending, auto_n = ed.stats()
        shown = len(self.dict_visible)
        parts = [f"显示 {shown} / 共 {total} 条"]
        if matched > shown:
            parts.append(f"搜索命中 {matched} 条（超出上限未显示）")
        parts.append(f"自动提取 {auto_n} 条")
        self.dict_stat.config(text="，".join(parts))
        self.dict_pending_lbl.config(
            text=ed.pending_text(), fg=(C_WARN if pending else C_HINT))
        self.dict_hint.config(
            text=(f"有 {pending} 处未保存改动，点「保存」写入 term_dict.py"
                  if pending else
                  "改动先记在内存里，点「保存」才写入 term_dict.py（可「撤回」）"),
            fg=(C_WARN if pending else C_HINT))
        self._sync_dict_all_state()

    # ---------- 勾选：行复选框 / 表头全选 ----------
    def _toggle_dict_row(self, iid):
        """切换一行的勾选状态，返回是否切换成功。"""
        orig = self.dict_row_orig.get(iid)
        if not orig:
            return False
        if orig in self.dict_checks:
            self.dict_checks.discard(orig)
        else:
            self.dict_checks.add(orig)
        self.dict_tree.set(
            iid, "sel",
            TERM_CHECK_ON if orig in self.dict_checks else TERM_CHECK_OFF)
        self._sync_dict_all_state()
        return True

    def _on_dict_tree_click(self, event):
        tree = self.dict_tree
        if tree.identify_column(event.x) != "#1":
            return
        if self._toggle_dict_row(tree.identify_row(event.y)):
            return "break"

    def _on_dict_tree_dblclick(self, event):
        """双击复选框列也算一次勾选（Tk 只派发更具体的 <Double-1>）。"""
        tree = self.dict_tree
        if tree.identify_column(event.x) != "#1":
            return
        if self._toggle_dict_row(tree.identify_row(event.y)):
            return "break"

    def _on_dict_toggle_all(self):
        vis = list(self.dict_visible or [])
        if not vis:
            self._sync_dict_all_state()
            return
        if self.dict_all_var.get() == 0:
            self.dict_checks.difference_update(vis)
        else:
            self.dict_checks.update(vis)
        self._refresh_dict_checks()

    def _refresh_dict_checks(self):
        tree = self.dict_tree
        for iid in tree.get_children():
            orig = self.dict_row_orig.get(iid)
            if not orig:
                continue
            tree.set(iid, "sel",
                     TERM_CHECK_ON if orig in self.dict_checks
                     else TERM_CHECK_OFF)
        self._sync_dict_all_state()

    def _sync_dict_all_state(self):
        vis = list(self.dict_visible or [])
        n = sum(1 for k in vis if k in self.dict_checks)
        if vis and n >= len(vis):
            state = 1
        elif n == 0 or not vis:
            state = 0
        else:
            state = -1
        if hasattr(self, "dict_all_var"):
            self.dict_all_var.set(state)
        if hasattr(self, "dict_check_stat"):
            self.dict_check_stat.config(
                text=(f"已选 {n} / {len(vis)} 条" if vis else "已选 0 条"))

    # ---------- 修改 / 新增 / 删除 / 撤回 / 保存 ----------
    def _dict_row_values(self, iid):
        try:
            vals = self.dict_tree.item(iid)["values"]
            return str(vals[2]), str(vals[3])
        except Exception:
            return "", ""

    def _dict_selected_rows(self):
        """选中的行 → [(原始原文, 当前原文, 当前译文), ...]。"""
        out = []
        for iid in self.dict_tree.selection():
            orig = self.dict_row_orig.get(iid)
            if not orig:
                continue
            src, dst = self._dict_row_values(iid)
            out.append((orig, src, dst))
        return out

    def _on_dict_edit(self, row, col, value):
        """双击原文 / 译文 → 先记进内存（点「保存」才落盘）。"""
        ed = self.dict_editor
        orig = self.dict_row_orig.get(row)
        if ed is None or not orig:
            self._filter_dict_rows()
            return
        try:
            vals = self.dict_tree.item(row)["values"]
            cur_src, cur_dst = str(vals[2]), str(vals[3])
        except Exception:
            self._filter_dict_rows()
            return
        new_src = value if col == "#3" else cur_src
        new_dst = value if col == "#4" else cur_dst
        ok, msg = ed.update(orig, new_src, new_dst)
        if not ok:
            messagebox.showwarning("不能这样改", msg)
        elif msg != "没有变化":
            self.q.put(("log", f"术语字典：{msg}\n"))
        self._filter_dict_rows()      # 重建列表，把非法输入还原成真实值

    def _on_dict_edit_selected(self):
        """弹窗修改选中的那一行（预填当前原文 / 译文）。"""
        ed = self.dict_editor
        if ed is None:
            return
        rows = self._dict_selected_rows()
        if not rows:
            messagebox.showinfo("提示", "请先选中要修改的术语（双击可直接改）")
            return
        if len(rows) > 1:
            messagebox.showinfo("提示", "一次只改一条，请只选一行（双击也能直接改）")
            return
        orig, cur_src, cur_dst = rows[0]
        got = TermDialog.ask(
            self.root, self.src_var.get(), self.tgt_var.get(),
            init_src=cur_src, init_dst=cur_dst,
            title="修改术语", ok_text="确定修改",
            note="改动先记在内存里，点「保存」后才写入 term_dict.py。")
        if not got:
            return
        ok, msg = ed.update(orig, got[0], got[1])
        if not ok:
            messagebox.showwarning("不能这样改", msg)
        elif msg != "没有变化":
            self.q.put(("log", f"术语字典：{msg}\n"))
        self._filter_dict_rows()

    def _on_dict_add(self):
        ed = self.dict_editor
        if ed is None:
            return
        got = TermDialog.ask(
            self.root, self.src_var.get(), self.tgt_var.get(),
            title="新增术语", ok_text="确定新增",
            note="新术语先记在内存里，点「保存」后才写入 term_dict.py。")
        if not got:
            return
        ok, msg = ed.add(got[0], got[1])
        if not ok:
            messagebox.showwarning("没有添加", msg)
        else:
            self.q.put(("log", f"术语字典：{msg}\n"))
        self._filter_dict_rows()

    def _on_dict_delete_selected(self):
        ed = self.dict_editor
        if ed is None:
            return
        picks = [k for k in list(self.dict_visible or [])
                 if k in self.dict_checks]
        if not picks:
            picks = [orig for orig, _s, _d in self._dict_selected_rows()]
        if not picks:
            messagebox.showinfo(
                "提示", "请先勾选（或选中）要删除的术语，再点「删除选中」")
            return
        if not messagebox.askyesno(
                "确认删除",
                f"确定删除这 {len(picks)} 条术语？\n"
                "（点「保存」前都能用「撤回」恢复）"):
            return
        ok, msg = ed.delete(picks)
        if not ok:
            messagebox.showwarning("没有删除", msg)
        else:
            self.q.put(("log", f"术语字典：{msg}\n"))
            self.dict_checks.difference_update(picks)
        self._filter_dict_rows()

    def _on_dict_delete_auto(self):
        """一键删除 AUTO 块里所有自动提取的术语。"""
        ed = self.dict_editor
        if ed is None:
            return
        try:
            auto_n = ed.stats()[2]
        except Exception:
            auto_n = 0
        if not auto_n:
            messagebox.showinfo("提示", "当前字典里没有自动提取的术语")
            return
        if not messagebox.askyesno(
                "确认一键删除",
                f"确定删除全部 {auto_n} 条自动提取的术语？\n"
                "（即 term_dict.py 里 AUTO 块内的词，"
                "不含手工新增的；\n"
                "点「保存」前都能用「撤回」恢复）"):
            return
        ok, msg = ed.delete_all_auto()
        if not ok:
            messagebox.showinfo("提示", msg)
            return
        self.q.put(("log", f"术语字典：{msg}\n"))
        self._filter_dict_rows()

    def _on_dict_undo(self):
        ed = self.dict_editor
        if ed is None:
            return
        if not ed.can_undo():
            messagebox.showinfo("提示", "没有可撤回的操作")
            return
        ok, msg = ed.undo()
        if ok:
            self.q.put(("log", f"术语字典：{msg}\n"))
        self._filter_dict_rows()

    def _save_dict(self):
        """把内存里的改动写进 term_dict.py。返回是否成功。"""
        ed = self.dict_editor
        if ed is None:
            return True
        if not ed.is_dirty():
            self._filter_dict_rows()
            return True
        try:
            rep = ed.save()
        except Exception as e:
            messagebox.showerror(
                "保存失败", f"{e}\n\n{config.TERM_FILE}")
            self.q.put(("log", f"术语字典保存失败：{e}\n"))
            return False
        # 让翻译端立刻用上新字典（★ 不写 snapshot，好让「术语更新后重翻」识别改动）
        try:
            PR.load_terms(force=True)
        except Exception:
            pass
        summary = (f"术语字典已保存：删除 {rep['deleted']} / 改名 "
                   f"{rep['renamed']} / 改译文 {rep['changed']} / 新增 "
                   f"{rep['added']}")
        self.q.put(("log", summary + "\n"))
        if rep.get("errors"):
            messagebox.showwarning(
                "部分条目没写进去",
                summary + "\n\n" + "\n".join(rep["errors"][:8]))
        self.dict_checks = set()
        self._filter_dict_rows()
        return True

    def _on_dict_save(self):
        self._save_dict()

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
        Avatar(head, size=64, path=config.AVATAR_FILE,
               on_click=lambda: self.show("home")).pack(side="left")
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
        right = RoundCard(page, radius=16, pad=12, width=272,
                          scrollable=True)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        tk.Label(right.body, text="切换适配", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        # ★ 侧栏只有 242px 宽，长标题必须允许换行，否则会被裁掉
        self.pv_from_to = tk.Label(right.body, text="", bg=CARD, fg=C_KEY,
                                   font=FONT_SMALL, anchor="w",
                                   justify="left", wraplength=238)
        self.pv_from_to.pack(fill="x", pady=(4, 6))

        # ★ 右栏卡片自己会滚了，这里再套一层 make_scroll_area 会变成
        #   「滚动套滚动」，画布 height=10 在无固定高的父容器里塌成 0 高 →
        #   适配清单整个看不见。Text 不给 height（默认 24 行）即可自然撑开。
        self.pv_adapt_text = tk.Text(right.body, wrap="word",
                                     font=FONT_SMALL,
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

        # 同步翻译页 / 设置页上的模式与模型显示
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
    # 页面 11：开启 DEBUG
    # ================================================================
    def _page_debug(self):
        self.debug_folder = None
        self.debug_exe = None       # ★ 用户手选的游戏启动程序（exe）
        self.debug_has_data = True  # ★ 选中的目录里有没有 Data
        self.debug_modes_locked = False  # ★ 无 Data 时锁成「调试启动器」
        # ★ 用户要求：引擎被改过也**默认继续写入**，所以默认勾上。
        self.debug_force = tk.BooleanVar(value=True)
        # ★ 自动关闭全量编译：默认勾上（给 Compiler 装编译闸门）。
        self.debug_guard = tk.BooleanVar(value=True)
        page = self.pages["debug"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        outer, inner = make_scroll_area(left, bg=BG_BASE)
        outer.pack(fill="both", expand=True)

        # ---- 上层：官方引擎覆盖 ----
        c1 = RoundCard(inner, radius=16, pad=16, auto_height=True)
        c1.pack(fill="x", pady=(0, 10))
        head1 = tk.Frame(c1.body, bg=CARD)
        head1.pack(fill="x")
        tk.Label(head1, text="官方引擎覆盖", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")

        row1 = tk.Frame(c1.body, bg=CARD)
        row1.pack(fill="x", pady=(8, 0))
        # ★ 用官方同版本基准覆盖 debug 菜单脚本
        GlassButton(row1, "用基准覆盖 debug 菜单", width=196, height=46,
                    primary=True, bg=CARD,
                    command=self._do_overwrite_menus).pack(side="left")
        # ★ 用官方同版本基准覆盖「地图更新」（Scene_Map）
        GlassButton(row1, "用基准覆盖地图更新", width=178, height=46,
                    bg=CARD,
                    command=self._do_overwrite_scene_map).pack(side="left",
                                                               padx=(10, 0))
        tk.Label(c1.body,
                 text="用官方同版本引擎的脚本整份盖回游戏（覆盖前先备份，"
                      "可随时用「还原覆盖」恢复）：\n"
                      "· debug 菜单：调试菜单的那几个脚本，覆盖时把菜单文字"
                      "换成中文；\n"
                      "· 地图更新：只替换 Scene_Map 一个脚本、不做翻译 —— "
                      "方式②③④ 找不到落点时先盖回官方版。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=560).pack(anchor="w", pady=(6, 0))
        row1b = tk.Frame(c1.body, bg=CARD)
        row1b.pack(fill="x", pady=(6, 0))
        GlassButton(row1b, "还原覆盖", width=108, height=38, bg=CARD,
                    font=FONT_SMALL,
                    command=self._do_overwrite_restore).pack(side="left")
        self.dbg_ow_lbl = tk.Label(c1.body, text="", bg=CARD, fg=C_KEY,
                                   font=FONT_SMALL, justify="left",
                                   wraplength=560)
        self.dbg_ow_lbl.pack(anchor="w", pady=(6, 0))
        attach_label_copy(self.dbg_ow_lbl, self, "覆盖结果")

        # ---- 中层：开启 DEBUG ----
        c2 = RoundCard(inner, radius=16, pad=16, auto_height=True)
        c2.pack(fill="x", pady=(0, 10))
        head2 = tk.Frame(c2.body, bg=CARD)
        head2.pack(fill="x")
        tk.Label(head2, text="开启 DEBUG", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(side="left")

        row2 = tk.Frame(c2.body, bg=CARD)
        row2.pack(fill="x", pady=(8, 0))
        self.dbg_do_btn = GlassButton(
            row2, "开启 DEBUG", width=140, height=46, primary=True,
            bg=CARD, command=self._do_debug_enable)
        self.dbg_do_btn.pack(side="left")
        GlassButton(row2, "还原", width=88, height=40, bg=CARD,
                    font=FONT_SMALL,
                    command=self._do_debug_restore).pack(side="right")
        # ★ 方式⑧：生成调试启动器（选中方式⑧时可用）
        self.dbg_launcher_btn = GlassButton(
            row2, "生成调试启动器", width=136, height=40, bg=CARD,
            font=FONT_SMALL, command=self._do_make_launcher)
        self.dbg_launcher_btn.pack(side="right", padx=8)

        # ★ 选项单独一行（跟按钮挤一行会把右边的按钮压扁）
        row2c = tk.Frame(c2.body, bg=CARD)
        row2c.pack(fill="x", pady=(6, 0))
        tk.Checkbutton(
            row2c, text="引擎被改过也继续写入（默认）",
            variable=self.debug_force, bg=CARD, fg=TEXT,
            activebackground=CARD, activeforeground=TEXT,
            selectcolor="#FFFFFF", font=FONT_SMALL,
            cursor="hand2").pack(side="left")
        # ★ 自动关闭全量编译（默认勾上）：给 Compiler 的 main 装一道闸，
        #   数据已编译好就直接 return（不删 Data/*.dat、不全量重编译）；
        #   取消勾选就保持引擎原样（调试启动时会真的全量编译一次）。
        tk.Checkbutton(
            row2c, text="自动关闭全量编译（默认）",
            variable=self.debug_guard, bg=CARD, fg=TEXT,
            activebackground=CARD, activeforeground=TEXT,
            selectcolor="#FFFFFF", font=FONT_SMALL,
            cursor="hand2").pack(side="left", padx=(18, 0))

        # ★ 任务5/任务2：开启方式改下拉框（容纳六种方式）
        row2b = tk.Frame(c2.body, bg=CARD)
        row2b.pack(fill="x", pady=(8, 0))
        tk.Label(row2b, text="开启方式：", bg=CARD, fg=C_TITLE,
                 font=FONT_SMALL).pack(side="left")
        self.debug_mode = tk.StringVar(value="main")
        self._debug_mode_labels = [
            ("main", "① 通用（写 Main，启动即调试）"),
            ("keys", "② 删条件（F9/队伍/穿墙 免 $DEBUG 可用）"),
            ("special", "③ F6 键（按 F6 直接开调试 + 提示）"),
            ("special_menu", "④ F6 键（按 F6 直接开调试菜单）"),
            ("repel", "⑤ 除虫喷雾（用喷雾即设 $DEBUG）"),
            ("repel_menu", "⑥ 除虫喷雾（用喷雾即开调试菜单）"),
            ("rewrite", "⑦ 改名调试函数（顶掉原函数，按 T 开菜单）"),
            ("launcher", "⑧ 调试启动器（生成 exe，双击进调试）"),
        ]
        self._debug_mode_cb = ttk.Combobox(
            row2b, textvariable=self.debug_mode, width=42, state="readonly",
            font=FONT_SMALL,
            values=[lab for _k, lab in self._debug_mode_labels])
        self._debug_mode_cb.pack(side="left", padx=8)
        self._debug_mode_cb.bind("<<ComboboxSelected>>",
                                 self._on_debug_mode_change)
        self._set_debug_mode_value("main")
        self.dbg_mode_desc = tk.Label(c2.body, text="", bg=CARD, fg=C_HINT,
                                      font=FONT_SMALL, justify="left",
                                      wraplength=560)
        self.dbg_mode_desc.pack(anchor="w", pady=(4, 0))
        self._on_debug_mode_change()
        self.dbg_do_lbl = tk.Label(c2.body, text="", bg=CARD, fg=C_KEY,
                                   font=FONT_SMALL, justify="left",
                                   wraplength=560)
        self.dbg_do_lbl.pack(anchor="w", pady=(6, 0))
        attach_label_copy(self.dbg_do_lbl, self, "开启结果")
        tk.Label(c2.body,
                 text="另外会自动清掉脚本里的反调试代码（含插件脚本 "
                      "Data/PluginScripts.rxdata）、给 Compiler 装一道编译闸门"
                      "（不想装就取消勾选「自动关闭全量编译」）；改动前先备份成 "
                      ".bak（可随时「还原」）；方式②一个 $DEBUG "
                      "条件都没认出来时，会问你要不要按官方基准补行。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=560).pack(anchor="w", pady=(6, 0))

        # ---- 下层：使用提示 ----
        c3 = RoundCard(inner, radius=16, pad=16, auto_height=True)
        c3.pack(fill="x")
        self.dbg_hint_lbl = tk.Label(
            c3.body,
            text="· 没有 Data 文件夹的游戏只能用「方式⑧ 调试启动器」\n"
                 "· 改完 PBS 想重新编译时，按住 Ctrl 启动游戏即可\n"
                 "· 只动 Main / Compiler / 反调试三处脚本（不勾「自动关闭全量编译」"
                 "就不动 Compiler），改动前各备份一份 .bak",
            bg=CARD, fg=C_HINT, font=FONT_SMALL,
            justify="left", wraplength=560)
        self.dbg_hint_lbl.pack(anchor="w", pady=(6, 0))

        # ---- 右侧：游戏启动程序（exe）----
        fp_holder = RoundCard(page, radius=16, pad=8, width=272,
                                scrollable=True)
        fp_holder.grid(row=0, column=1, sticky="nsew")
        fp_holder.grid_propagate(False)
        body = fp_holder.body
        tk.Label(body, text="游戏启动程序", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=10, pady=(8, 4))
        GlassButton(body, "选择游戏启动程序 (exe)", width=196, height=36,
                    bg=CARD, font=FONT_SMALL,
                    command=self._dbg_pick_exe).pack(anchor="w", padx=10)
        self.dbg_folder_lbl = tk.Label(body, text="未选择", bg=CARD,
                                       fg=C_KEY, font=FONT_SMALL,
                                       wraplength=200, justify="left")
        self.dbg_folder_lbl.pack(anchor="w", padx=10, pady=(6, 0))
        attach_copy(self.dbg_folder_lbl, [
            ("复制 exe 路径", lambda: getattr(self, "debug_exe", "") or ""),
            ("复制游戏目录",
             lambda: getattr(self, "debug_folder", "") or ""),
        ], app=self, hotkey=False)
        self.dbg_info_lbl = tk.Label(body, text="", bg=CARD, fg=C_KEY,
                                     font=FONT_SMALL, wraplength=200,
                                     justify="left")
        self.dbg_info_lbl.pack(anchor="w", padx=10, pady=(4, 0))
        attach_label_copy(self.dbg_info_lbl, self, "游戏信息")
        tk.Label(body,
                 text="提示：\n"
                      "选游戏的启动程序（exe）即可 —— 你选的这个就是主程序，"
                      "工具用它所在的文件夹当游戏目录。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=200).pack(anchor="w", padx=10,
                                                      pady=(10, 0))

        # ---- 右侧最下：插件解包 / 编译回容器 ----
        tk.Label(body, text="插件解包", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=10, pady=(14, 4))
        GlassButton(body, "插件解包", width=196, height=36,
                    bg=CARD, font=FONT_SMALL,
                    command=self._do_unpack_plugins).pack(anchor="w", padx=10)
        self.dbg_unpack_lbl = tk.Label(body, text="", bg=CARD, fg=C_KEY,
                                       font=FONT_SMALL, wraplength=200,
                                       justify="left")
        self.dbg_unpack_lbl.pack(anchor="w", padx=10, pady=(6, 0))
        attach_label_copy(self.dbg_unpack_lbl, self, "插件解包结果")
        tk.Label(body,
                 text="把 Data/PluginScripts.rxdata 解包到游戏目录的 "
                      "Plugins-p 文件夹（每个插件一个子目录，"
                      "插件里原有的子目录结构照原样保留）。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=200).pack(anchor="w", padx=10,
                                                      pady=(6, 0))
        GlassButton(body, "编译回容器", width=196, height=36,
                    bg=CARD, font=FONT_SMALL,
                    command=self._do_compile_back).pack(anchor="w", padx=10,
                                                        pady=(10, 0))
        # 单独一个标签：编译回容器的结果（更新了几个 / 备份名）和解包结果
        # 是两件事，共用一个标签会让上一次的结果被覆盖掉，看着像丢了。
        self.dbg_compile_lbl = tk.Label(body, text="", bg=CARD, fg=C_KEY,
                                        font=FONT_SMALL, wraplength=200,
                                        justify="left")
        self.dbg_compile_lbl.pack(anchor="w", padx=10, pady=(6, 0))
        attach_label_copy(self.dbg_compile_lbl, self, "编译回容器结果")
        tk.Label(body,
                 text="改完 Plugins-p 里的 .rb 后，点「编译回容器」才会生效"
                      "—— 游戏运行时读的是 Data/PluginScripts.rxdata，"
                      "不会自己去读 Plugins-p。写回前会先把原容器备份成 "
                      "PluginScripts.rxdata.<时间戳>.bak。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 justify="left", wraplength=200).pack(anchor="w", padx=10,
                                                      pady=(6, 0))

    # ---------- 菜单 5（开启DEBUG）：小工具 ----------
    _DEBUG_MODE_DESC = {
        "main": "方式①（通用）：在 Main 的 mainFunction 里写 $DEBUG=true，"
                "启动即调试模式（标题界面会变，F9 开调试菜单）。"
                "★ 这是**唯一**会开 $DEBUG 的方式；方式②–⑦ 都不会写"
                "（还会把以前留下的清掉）—— 需要 $DEBUG 时用本方式。",
        "keys": "方式②：删掉各处「需要 $DEBUG 才生效」的条件，让它们无条件可用。"
                "穿墙（Game_Player）、F9 调试菜单（Scene_Map）、"
                "队伍/暂停/背包里的 Debug 项（PScreen_Party / UI_Party / "
                "UI_PauseMenu / UI_Bag / UI_PokemonStorage）。"
                "**自动认版本**：v16/v17 的 `if $DEBUG and Input.press?(…)`、"
                "v18 起的 `return true if $DEBUG and|&& Input.press?(…)`、"
                "`… if $DEBUG`、`\"condition\" => proc { … $DEBUG }` 全都认，"
                "混着写也能正确处理，且只删修饰词、不会产生语法错误。\n"
                "★ 如果一个都认不出来（作者把这段改没了 / 结构完全不同），"
                "会弹窗问你要不要**按游戏版本的官方基准**，在对应位置补上"
                "「去掉 debug 条件」的代码。",
        "special": "方式③：照着 F9 的样子，在 Scene_Map#update 里加一个 "
                   "**F6 键**分支 —— 按下 F6 **直接** `$DEBUG = true` 并弹窗提示"
                   "（不再判断 `!$DEBUG`，按下去就提示）。"
                   "v16/v17 加独立 if 块，v18 起加 elsif 分支，各版本都认。",
        "special_menu": "方式④：位置同方式③（Scene_Map#update 里的 F6 键），"
                        "但**直接打开调试菜单**"
                        "（`pbFadeOutIn { pbDebugMenu }`，"
                        "即方式⑥ 的 F6 版）—— 按 F6 不再只是设 $DEBUG，"
                        "而是立刻把调试菜单弹出来。"
                        "v16/v17 独立 if 块，v18 起 elsif 分支。",
        "repel": "方式⑤：除虫喷雾 `pbRepel` 开头注入 —— $DEBUG 不为真就设为真"
                 "并提示（用一次除虫喷雾即开调试）。",
        "repel_menu": "方式⑥：同方式⑤的位置（除虫喷雾的 `pbRepel` 开头，"
                      "v16–v18 在 PItem_ItemEffects、v19+ 在 Item_Effects），"
                      "但**直接打开调试菜单**（`pbFadeOutIn { pbDebugMenu }`，"
                      "即 Scene_Map#call_debug 的等效写法），不再等 F9。",
        "rewrite": "方式⑦（改名调试函数 · 规避反调试）：给那些**把调试功能做掉**的"
                   "同人作准备 —— 作者的汉化/防改脚本会重定义 `pbDebugMenu` 为 "
                   "`exit`、清空 `MenuHandlers` 的 `:debug_menu` 注册项、"
                   "屏蔽含 debug 的注册、并把 `Scene_Map#update` 改成 "
                   "`exit if $DEBUG`，还屏蔽 F4–F12。本方式**整套改名**：\n"
                   "  · 从**官方基准**（Essentials 16–21.1 原版）里抠出每个版本的 "
                   "debug 菜单函数，**函数名全部改掉**（`pbDebugMenu`→`pbAideWindow`、"
                   "`pbPokemonDebug`→`pbAidePokemon`、`pbDebugMenuCommands`→"
                   "`pbAideWindowCommands` … `call_debug`→`call_aide`），"
                   "**函数体逐字保留官方实现**（菜单项齐全），直接顶掉游戏里的原函数；\n"
                   "  · 把游戏脚本里所有**旧函数调用点**（含 `alias`、注册表 key "
                   "`:debug_menu`/`:pokemon_debug_menu`/`:debug` → "
                   "`:aide_menu`/`:aide_pokemon_menu`/`:aide`）全部改道到新名字；\n"
                   "    ★ 符号改名带**词边界**：`:debug_calling` 这种「只是以 "
                   "`:debug` 开头」的符号不会被误改（`attr_accessor "
                   ":debug_calling` 被改掉的话，游戏一跑图就 "
                   "`NoMethodError: undefined method 'debug_calling'`）；"
                   "第 ⓪ 步还会**自动修回**早期版本误改的符号。\n"
                   "  · UI 里显示的 `\"Debug\"` 选项名统一改成 `\"助手\"`；\n"
                   "  · ★ **保留原函数名**：改名只发生在定义点，但别的插件/脚本可能"
                   "还在按旧名调用（`pbDebugMenu`、`pbPokemonDebug`…），旧名消失就是 "
                   "`NameError`。所以每个改名后的函数**同一作用域**里都补一个同名"
                   "转发壳（`def pbDebugMenu(*args, &blk) → pbAideWindow(...)`），"
                   "连 `PokemonDebugMixin.instance_method(:pbPokemonDebug)` 这类"
                   "反射访问也照旧可用；`call_debug` 同样保留；\n"
                   "  · **按版本正式注册 T 键**：v16–18 改 `PSystem_Controls.rb`"
                   "（加 `T = 24` 常量 + `buttonToKey` 里 `when Input::T` → "
                   "Win32 虚拟键码 `0x54`），v19+ 改 `004_Input.rb`"
                   "（加 `T = :T`，走 mkxp-z 的 `triggerex?(:T)`）；"
                   "另在插件里挂 T 键开菜单（T 不在被屏蔽的 F4–F12 里）。\n"
                   "★ 全程**不设 $DEBUG** —— 反调试有 `exit if $DEBUG`，一设就退游戏。\n"
                   "★ 重新定义的函数**名字不含 d-e-b-u-g**，不在反调试检测范围内。\n"
                   "★ 改动**多处都写**：① 独立插件 `Plugins/zzz_pkmn_aide/`；"
                   "② 游戏脚本 `Scene_Map` 末尾（双保险）；"
                   "③ **直接编进 `Data/PluginScripts.rxdata`**"
                   "（v19+ 插件机制真正 eval 的就是它，不依赖目录）；"
                   "④ **关掉 `PluginManager.needCompiling?`**"
                   "（rxdata 固定，不再被 `Plugins/` 目录重编译覆盖）。\n"
                   "★ 顺带修两类「开 $DEBUG 才暴露」的插件坑："
                   "① 给**依赖别的插件**的调用加 `defined?` 保护"
                   "（如 `MidbattleHandlers.add` 在 DBK 未加载时会 NameError）；"
                   "② 把 rxdata 里的**加载顺序摆正**"
                   "（使用方插件挪到提供方之后）。\n"
                   "★ 适配 v16–v21.1 全部九版；不改存档、可还原。",
        "launcher": "方式⑧（调试启动器）：生成 **宝可梦调试启动器.exe**（自带 "
                    "Python，玩家电脑**不用装 Python**）+ 一份 "
                    "`_pkmn_debug_launcher.json` 配置，双击 exe 即以调试模式"
                    "进游戏 —— **不改游戏本体、不动存档**。"
                    "★ exe 是**所有游戏共用同一份固定文件**，各游戏的差异"
                    "（游戏 exe 名 / 运行库 / 注入钩子）全写在那个 json 里。"
                    "适配 v16–v21.1：启动时**运行时看进程实际加载了哪个 dll**，"
                    "RGSS*.dll（v16–v18）→ 内存补丁；"
                    "msvcrt-ruby*.dll（mkxp-z，v19–v21.1）→ 原生命令行 "
                    "`debug` 参数。"
                    "会自动补齐最小可用 Data/*.dat 与 pbs/*.txt（真数据，"
                    "不是空文件），避免开调试后触发全量重编译报错。"
                    "适合脚本被加密打包（单 exe）的游戏；"
                    "**也是唯一不需要 Data 文件夹的方式**。",
    }

    def _set_debug_mode_value(self, key):
        """把内部 key 换算成下拉框显示的文字。"""
        for k, lab in self._debug_mode_labels:
            if k == key:
                self.debug_mode.set(lab)
                return
        self.debug_mode.set(self._debug_mode_labels[0][1])

    def _debug_mode_key(self):
        """下拉框当前选择 → 内部 key。"""
        lab = self.debug_mode.get()
        for k, l in self._debug_mode_labels:
            if l == lab:
                return k
        return "main"

    def _on_debug_mode_change(self, _e=None):
        # 没有 Data 时被锁成 launcher，描述文字由 _dbg_lock_modes 负责，
        # 这里不要覆盖掉它的警告。
        if getattr(self, "debug_modes_locked", False):
            if hasattr(self, "dbg_launcher_btn"):
                self.dbg_launcher_btn.set_enabled(True)
            return
        key = self._debug_mode_key()
        self.dbg_mode_desc.config(text=self._DEBUG_MODE_DESC.get(key, ""))
        # 方式⑧是独立按钮，提示去点它
        if hasattr(self, "dbg_launcher_btn"):
            on = (key == "launcher")
            self.dbg_launcher_btn.set_enabled(on)

    def _dbg_pick_exe(self):
        """选游戏启动程序（exe）；游戏目录由它推出。"""
        initial = (getattr(self, "debug_folder", None)
                   or config.Runtime.last_dir
                   or config.BASE_DIR)
        if not os.path.isdir(initial):
            initial = config.BASE_DIR
        p = filedialog.askopenfilename(
            title="选择游戏启动程序（Game.exe 之类，只要是 exe 就行）",
            initialdir=initial,
            filetypes=[("游戏启动程序", "*.exe"), ("所有文件", "*.*")])
        if not p:
            return
        if not p.lower().endswith(".exe"):
            if not messagebox.askyesno(
                    "这不是 exe",
                    f"你选的是：\n{os.path.basename(p)}\n\n"
                    "它不是 .exe 文件，一般不是游戏主程序。\n"
                    "仍要用它所在的目录吗？"):
                return
        import game_scripts as GS
        root, exe_name = GS.exe_root(p)
        self._dbg_apply_selection(root, exe_path=p, exe_name=exe_name)

    def _dbg_apply_selection(self, root, exe_path=None, exe_name=None):
        """
        统一处理「选好游戏了」：校验 → 记状态 → 刷新右侧信息。
        root 为游戏根目录；exe_path 为选中的启动程序（可为 None，走自动挑）。

        ★ 没有 Data 文件夹也允许选 —— 但那样**只能走「调试启动器」方式**
          （它不改游戏本体、不读 Data，脚本打包进 exe 的游戏也适用）。
        """
        import game_scripts as GS
        # need_data=False：先放行，拿到 has_data 再决定能用哪些方式
        ok, why, root, exe_path, has_data = GS.verify_game(
            root, exe=exe_path, need_data=False)
        if not ok:
            self.debug_folder = None
            self.debug_exe = None
            self.debug_has_data = False
            self.dbg_folder_lbl.config(text="未选择")
            self.dbg_info_lbl.config(text=f"⚠ {why}", fg=C_WARN)
            messagebox.showwarning("这个选择不太对", why)
            return
        self.debug_folder = root
        self.debug_exe = exe_path
        self.debug_has_data = has_data
        config.Runtime.set_dir(root)
        # 展示：先给启动程序名（主角），再给目录
        show = []
        if exe_name:
            show.append(f"启动程序：{exe_name}")
        elif exe_path:
            show.append(f"启动程序：{os.path.basename(exe_path)}")
        else:
            show.append("启动程序：（自动识别）")
        show.append(f"游戏目录：{root}")
        show.append("Data 文件夹：" + ("有" if has_data else "没有"))
        # ★ 选到形如 ...\Data\Game.exe 的内层目录时给一句提醒（根目录在上面）
        payload_hint = ""
        if GS.looks_like_payload_folder(root):
            payload_hint = (
                "\n\n⚠ 这个目录看着是游戏的**内层**目录（没有 Data 子文件夹）。"
                "真正的游戏根目录很可能是它的**上一层**：\n"
                f"  {os.path.dirname(os.path.abspath(root))}\n"
                "建议改选上一层里的游戏启动程序再试。")
        self.dbg_folder_lbl.config(text="\n".join(show) + payload_hint)
        if payload_hint:
            self.dbg_info_lbl.config(
                text=payload_hint.strip(), fg=C_WARN)
        # ★ 换了游戏目录 → 清掉上一次的开启结果与覆盖结果文字
        self.dbg_do_lbl.config(text="")
        if hasattr(self, "dbg_ow_lbl"):
            self.dbg_ow_lbl.config(text="")
        # ★ 没有 Data：强制切到「调试启动器」，其它方式全部禁用
        if not has_data:
            self._set_debug_mode_value("launcher")
        elif getattr(self, "debug_modes_locked", False):
            # ★ 上一次选的是「没有 Data」的游戏 → 方式被锁在⑧；这次有 Data，
            #   要把下拉框复位回默认，否则「解锁了但值还停在⑧」→ 用户点
            #   「开启 DEBUG」跑的其实是启动器，而不是他选的脚本改写方式。
            self._set_debug_mode_value("main")
        self._dbg_lock_modes(not has_data)
        self._dbg_refresh_folder_info()

    def _dbg_lock_modes(self, locked):
        """
        locked=True（没有 Data）时：把开启方式锁成「调试启动器」，
        下拉框禁用，并给一句醒目提示。
        """
        self.debug_modes_locked = bool(locked)
        cb = getattr(self, "_debug_mode_cb", None)
        if cb is not None:
            try:
                cb.config(state="disabled" if locked else "readonly")
            except Exception:
                pass
        if hasattr(self, "dbg_mode_desc"):
            if locked:
                self.dbg_mode_desc.config(
                    text="⚠ 这个游戏目录里没有 Data 文件夹 —— 只能用"
                         "「方式⑧ 调试启动器」开调试（它不改游戏本体、"
                         "不依赖 Data，脚本打包进 exe 的游戏也适用）。"
                         "其它方式需要改 Data 里的脚本，已禁用。",
                    fg=C_WARN)
            else:
                self.dbg_mode_desc.config(fg=C_HINT)
                self._on_debug_mode_change()
        if hasattr(self, "dbg_launcher_btn"):
            self.dbg_launcher_btn.set_enabled(
                locked or self._debug_mode_key() == "launcher")
        # 没 Data 时「开启 DEBUG」主按钮也可以点（它内部会走 launcher），
        # 但把「还原」留着（万一之前改过 Data）。主按钮始终可用，
        # 因为 _do_debug_enable 会按当前方式走；这里只保证方式被锁住。
        if hasattr(self, "dbg_do_btn"):
            try:
                self.dbg_do_btn.set_enabled(True)
            except Exception:
                pass



    def _dbg_refresh_folder_info(self):
        """重新显示右侧的「运行库 / $DEBUG / 编译闸门」状态。"""
        d = getattr(self, "debug_folder", None)
        if not d:
            return
        exe = getattr(self, "debug_exe", None)
        try:
            import engine_tools as ET
            kind = ET.detect_runtime(d, exe=exe)
            rl = ET.RUNTIME_LABEL.get(kind, "未知运行库")
        except Exception:
            kind, rl = "", "运行库未知"
        import game_scripts as GS
        has_data = os.path.isdir(GS.data_dir(d))
        # ★ 选到内层目录（...\Data\Game.exe）时补一句「根目录在上面」
        payload = ""
        if GS.looks_like_payload_folder(d):
            payload = ("\n⚠ 这像是游戏的**内层**目录，根目录很可能是上一层：\n"
                       f"  {os.path.dirname(os.path.abspath(d))}")
        if not has_data:
            # 没有 Data：谈不上「$DEBUG 写没写 / 编译闸门」，只报运行库
            self.dbg_info_lbl.config(
                text=f"⚠ 无 Data 文件夹 → 只能用调试启动器\n"
                     f"运行库：{rl}\n"
                     f"（启动器会生成到游戏目录，点它即以调试模式进游戏）"
                     f"{payload}",
                fg=C_WARN)
            return
        try:
            import debug_tool as DT
            st = DT.status(d)
            dbg_w = ("已写" if st["debug_on"]
                     else ("只写了一半" if st.get("debug_partial") else "未写"))
            gd_w = ("已装" if st["guarded"]
                    else ("只装了一半" if st.get("guarded_partial") else "未装"))
            ad_w = ("已清除" if st.get("antidebug_fixed")
                    else ("⚠ 待处理" if st.get("antidebug") else "无"))
            self.dbg_info_lbl.config(
                text=f"✔ Essentials {st['version'] or '（读不到）'}\n"
                     f"运行库：{rl}\n"
                     f"$DEBUG=true：{dbg_w}\n"
                     f"编译闸门：{gd_w}\n"
                     f"反调试代码：{ad_w}",
                fg=C_KEY)
        except Exception:
            self.dbg_info_lbl.config(text=f"运行库：{rl}", fg=C_KEY)

    def _dbg_folder(self, need_data=True):
        """
        取当前选中的游戏目录。
        need_data=True（默认）要求有 Data 文件夹；False 时允许没有
        （给「调试启动器」用 —— 它不读 Data）。
        """
        d = getattr(self, "debug_folder", None)
        exe = getattr(self, "debug_exe", None)
        if not d or not os.path.isdir(d):
            messagebox.showwarning("提示", "请先在右侧选择游戏启动程序（exe）")
            return None
        import game_scripts as GS
        ok, why, _root, _exe, has_data = GS.verify_game(
            d, exe=exe, need_data=need_data)
        if not ok:
            messagebox.showwarning("这个选择不太对", why)
            return None
        if not has_data:
            self.debug_has_data = False        # 顺手同步一下状态
        return d

    def _dbg_folder_data(self):
        """
        「要改脚本」的操作（基准覆盖 / 非 launcher 的开启方式）
        统一走这里：没 Data 就提示只能用调试启动器。
        """
        import game_scripts as GS
        d = getattr(self, "debug_folder", None)
        if d and not os.path.isdir(GS.data_dir(d)):
            messagebox.showwarning(
                "这个游戏没有 Data 文件夹",
                "当前选的游戏目录里没有 Data 文件夹，无法改动脚本。\n\n"
                "这类游戏只能用「方式⑧ 调试启动器」开调试 —— "
                "请把「开启方式」选成 ⑥ 调试启动器，再点「开启 DEBUG」"
                "或「生成调试启动器」。")
            self._set_debug_mode_value("launcher")
            self._dbg_lock_modes(True)
            return None
        return self._dbg_folder(need_data=True)

    def _do_overwrite_menus(self):
        """用基准覆盖 debug 菜单脚本（覆盖前提醒风险）。"""
        d = self._dbg_folder_data()
        if not d:
            return
        import essentials_base as EB
        try:
            ver = EB.detect_version(d)
        except Exception:
            ver = ""
        if not ver:
            # ★ 脚本里读不出版本号（v16 就没有这个常量）→ 跑一次检测，
            #   用「按函数指纹认出来」的那份基准。
            self.show("log")
            self._emit_log(
                "[覆盖] 脚本里读不出版本号，正在按函数指纹识别引擎版本…\n")

            def work_ver():
                try:
                    chk = EB.compare(d, emit=lambda s: self._emit_log(s))
                except Exception as e:      # noqa: BLE001
                    chk = None
                    self._emit_log(f"[覆盖] ✘ 识别失败：{e}\n")
                self.q.put(("dbg_overwrite_ver", (d, chk, "menus")))
                return chk

            self.run_async(work_ver, label="识别引擎版本中…",
                           done_label="识别完成")
            return
        self._do_overwrite_menus_ask(d, ver, "")

    def _do_overwrite_scene_map(self):
        """任务3：用基准的 Scene_Map 覆盖游戏的「地图更新」。"""
        d = self._dbg_folder_data()
        if not d:
            return
        import essentials_base as EB
        try:
            ver = EB.detect_version(d)
        except Exception:
            ver = ""
        if not ver:
            self.show("log")
            self._emit_log(
                "[覆盖] 脚本里读不出版本号，正在按函数指纹识别引擎版本…\n")

            def work_ver():
                try:
                    chk = EB.compare(d, emit=lambda s: self._emit_log(s))
                except Exception as e:      # noqa: BLE001
                    chk = None
                    self._emit_log(f"[覆盖] ✘ 识别失败：{e}\n")
                self.q.put(("dbg_overwrite_ver", (d, chk, "scene_map")))
                return chk

            self.run_async(work_ver, label="识别引擎版本中…",
                           done_label="识别完成")
            return
        self._do_overwrite_scene_map_ask(d, ver, "")

    def _do_overwrite_scene_map_ask(self, d, ver, guessed_by):
        """版本号定了之后：说明 → 提醒风险 → 覆盖 Scene_Map。"""
        import engine_tools as ET
        if not ver:
            messagebox.showwarning(
                "读不到版本号",
                "从游戏脚本里读不出 Essentials 版本号，也没能按函数指纹认出"
                "是哪一版，无法确定用哪份基准覆盖。")
            return
        item = ET.scene_map_plan(d, ver)
        if not item:
            messagebox.showwarning(
                "没有对应基准",
                f"工具里没有内置 v{ver} 的 Scene_Map 脚本，无法覆盖。")
            return
        tgt = item.get("target")
        if tgt:
            where = ("解包文件 %s" % tgt["key"] if tgt.get("mode") == "file"
                     else "Scripts.rxdata 第 %s 条（脚本名 Scene_Map）"
                          % tgt["key"])
        else:
            where = "游戏里没找到 Scene_Map（会按基准新建一个）"
        lines = [
            f"即将用官方 v{ver} 的 **Scene_Map**（地图场景）整份覆盖游戏里的"
            "那一份：",
            f"  · 目标：{where}",
            f"  · 基准：{os.path.basename(item['src'])}",
        ]
        if guessed_by:
            lines.append(f"（版本号是检测时按指纹认出来的：{guessed_by}）")
        lines += [
            "",
            "它管的是地图上的按键与流程：F9 调试菜单、菜单/战斗/商店的呼出、"
            "地图转场等。",
            "",
            "⚠ 风险提示：",
            "· 作者对 Scene_Map 做的改动会**全部丢失**（整份替换）；",
            "· 覆盖前会自动把原文件备份成 .pkmn-overwrite-*.bak，"
            "出问题可用「还原覆盖」恢复；",
            "· 这份**不做中文翻译**（Scene_Map 不是菜单文本）；",
            "· 覆盖后建议再开一次「方式②③④」，那时 $DEBUG 条件就是官方写法，"
            "一定能认出来。",
        ]
        if not messagebox.askyesno("确认覆盖「地图更新」（Scene_Map）？",
                                   "\n".join(lines)):
            self._emit_log("[覆盖] 已取消（地图更新）\n")
            return
        self.show("log")

        def work():
            import engine_tools as ET
            res = ET.overwrite_scene_map(
                d, ver, emit=lambda s: self._emit_log(s))
            res["game_dir"] = d
            self.q.put(("dbg_scene_overwrite_done", res))
            return res

        self.run_async(work, label="覆盖地图更新（Scene_Map）中…",
                       done_label="覆盖完成")

    def _ask_baseline_strip(self, r):
        """
        任务2：方式②「一个 $DEBUG 条件都没认出来」时的兜底询问。

        「认不出来」= 游戏里那几处「需要 $DEBUG 才生效」的代码被作者改掉 /
        写法跟官方完全不一样，光靠文本模式匹配定位不到。这时问用户要不要
        **按游戏版本对应的官方基准**，在读到的那几处**对应位置**补一行
        「去掉 debug 条件」的代码。
        """
        d = r.get("mode_game_dir") or getattr(self, "debug_folder", None)
        if not d:
            return
        ver = (r.get("baseline")
               or (r.get("check") or {}).get("baseline")
               or r.get("version") or "")
        import engine_tools as ET
        names = "、".join(ET._KEYS_SCRIPTS)
        if not ver:
            self._emit_log(
                "[方式二·兜底] 读不到版本号、也没识别出基准，跳过基准补行\n")
            return
        if not messagebox.askyesno(
                "方式②一处都没认出来",
                "方式②（删 $DEBUG 条件）在游戏脚本里**一处都没认出来** ——\n"
                "多半是作者把「… if $DEBUG」那段改掉 / 删掉了，"
                "光靠文本匹配定位不到位置。\n\n"
                "要不要**按游戏版本（v%s）对应的官方基准**，在**对应位置**"
                "补一行「去掉 debug 条件」的代码？\n\n"
                "· 做法：在官方基准里带 $DEBUG 的那几行所在的**同一个函数、"
                "同一个位置**（用它后面那行代码当锚点）补进去；\n"
                "· **只加不删**，游戏里已经有同一句的就跳过；\n"
                "· 改动前照样自动备份，可以「还原」。\n\n"
                "涉及脚本：%s" % (ver, names)):
            self._emit_log("[方式二·兜底] 已取消（不按基准补行）\n")
            return
        self.show("log")

        def work():
            import engine_tools as ET
            res = ET.add_debug_strip_from_baseline(
                d, ver, emit=lambda s: self._emit_log(s))
            res["game_dir"] = d
            self.q.put(("dbg_strip_baseline_done", res))
            return res

        self.run_async(work, label="按基准补行中…", done_label="补行完成")

    def _do_overwrite_menus_ask(self, d, ver, guessed_by):
        """版本号定了之后：列计划 → 提醒风险 → 覆盖。"""
        import engine_tools as ET
        if not ver:
            messagebox.showwarning(
                "读不到版本号",
                "从游戏脚本里读不出 Essentials 版本号，也没能按函数指纹认出"
                "是哪一版，无法确定用哪份基准覆盖。")
            return
        plan = ET.overwrite_plan(d, ver)
        if not plan:
            messagebox.showwarning(
                "没有对应基准",
                f"工具里没有内置 v{ver} 的引擎脚本，无法覆盖。")
            return

        def _label(p):
            return f"{p['name']}#{p['func']}" if p.get("func") else p["name"]

        missing = [_label(p) for p in plan if not p["target"]]
        lines = [f"即将用官方 v{ver} 引擎脚本覆盖游戏里的 "
                 f"{len(plan)} 处调试相关代码："]
        if guessed_by:
            lines.append(f"（版本号是检测时按指纹认出来的：{guessed_by}）")
        for p in plan:
            if p.get("kind") == "func":
                tail = "（只替换该函数）"
            elif p["target"]:
                tail = "（整份替换）"
            elif p.get("create"):
                tail = ("（游戏里没有 → **按基准新建**，"
                        "追加进 Scripts.rxdata，排在 Main 之前）")
            else:
                tail = "（游戏里没有，也无处可新建，将跳过）"
            lines.append(f"  · {_label(p)} {tail}")
        lines.append("")
        lines.append("⚠ 风险提示：")
        lines.append("· 标「整份替换」的会把游戏里那份调试脚本换成官方原版，"
                     "作者对它的改动会丢失；")
        lines.append("· 标「只替换该函数」的只动那一个函数，脚本其余部分原样保留；")
        lines.append("· 覆盖前会自动把原文件备份成 .pkmn-overwrite-*.bak，"
                     "出问题可用「还原覆盖」恢复；")
        lines.append("· 覆盖时会把菜单名、功能说明等**全部翻译成中文**再写入。")
        if missing:
            lines.append(f"· 其中 {len(missing)} 个游戏里找不到："
                         + "、".join(missing))
        if not messagebox.askyesno("确认覆盖调试菜单脚本？",
                                   "\n".join(lines)):
            self._emit_log("[覆盖] 已取消\n")
            return
        self.show("log")

        def work():
            res = ET.overwrite_engine_scripts(
                d, ver, translate=True,
                emit=lambda s: self._emit_log(s), allow_missing=True)
            self.q.put(("dbg_overwrite_done", res))
            return res

        self.run_async(work, label="覆盖调试菜单脚本中…", done_label="覆盖完成")

    def _do_overwrite_restore(self):
        d = self._dbg_folder_data()
        if not d:
            return
        import engine_tools as ET
        if not messagebox.askyesno(
                "还原覆盖",
                "把本工具「覆盖」过的脚本（调试菜单 / 地图更新）还原回"
                "覆盖前的样子？"):
            return
        self.show("log")

        def work():
            res = ET.restore_overwrite(d, emit=lambda s: self._emit_log(s))
            self.q.put(("dbg_overwrite_restore_done", res))
            return res

        self.run_async(work, label="还原覆盖中…", done_label="还原完成")

    def _do_debug_enable(self):
        mode = self._debug_mode_key()
        exe = getattr(self, "debug_exe", None)
        # ★ 没有 Data 文件夹时：只允许「调试启动器」，其它方式一律拦下
        import game_scripts as GS
        root_now = getattr(self, "debug_folder", None)
        if not root_now:
            # ★ 还没选游戏：原因要说准。以前这里 `bool(root_now) and …` 直接
            #   算成「没有 Data」，用户会以为是游戏缺 Data，其实是没选游戏，
            #   而且还会顺手把方式永久锁成⑧。
            messagebox.showwarning(
                "请先选择游戏",
                "请先在右侧选择**游戏启动程序（exe）**（或用「选游戏…」按钮）。\n\n"
                "工具要用它所在文件夹当游戏目录。")
            return
        has_data = os.path.isdir(GS.data_dir(root_now))
        if not has_data and mode != "launcher":
            self._set_debug_mode_value("launcher")
            self._dbg_lock_modes(True)
            messagebox.showwarning(
                "这个游戏没有 Data 文件夹",
                "当前游戏目录里没有 Data 文件夹，无法改动脚本。\n\n"
                "已自动切到「方式⑧ 调试启动器」，再点一次「开启 DEBUG」"
                "即可（它会生成一个启动文件，点它即以调试模式进游戏）。")
            return
        d = self._dbg_folder(need_data=(mode != "launcher"))
        if not d:
            return
        self.show("log")
        force = bool(self.debug_force.get())
        guard = bool(getattr(self, "debug_guard", tk.BooleanVar(value=True)).get())

        # ---------- 反调试复核：注释之前先把代码摆给用户看 ----------
        ad_plan = {}
        if mode != "launcher":
            import debug_tool as DT
            try:
                ad_srcs = DT.find_antidebug_sources(d)
            except Exception as e:
                ad_srcs = []
                self._emit_log(f"[开启] ⚠ 扫描反调试代码失败：{e}\n")
            n = len(ad_srcs)
            for i, src in enumerate(ad_srcs, 1):
                r = AntiDebugDialog.review(self.root, src, i, n)
                act = r.get("action")
                if act == "cancel":
                    self._emit_log(
                        "[开启] 已取消（反调试复核窗口里点了「取消」）\n")
                    return
                if act == "skip":
                    ad_plan[DT.src_key(src)] = {"action": "skip"}
                    self._emit_log(
                        "[开启] · 第 %d/%d 处按你的选择跳过\n" % (i, n))
                else:
                    dec = DT.antidebug_decision(
                        src["text"], src["blocks"], AntiDebugDialog.CTX,
                        edited=r.get("edited"))
                    dec["action"] = act
                    ad_plan[DT.src_key(src)] = dec
                    self._emit_log(
                        "[开启] · 第 %d/%d 处：%s\n"
                        % (i, n, "自动注释" if act == "comment"
                           else "按你手改的版本"))

        def work():
            import debug_tool as DT
            import engine_tools as ET
            if mode == "launcher":
                # ★ 方式⑧：生成调试启动器（不改游戏本体）
                res = ET.make_debug_launcher(
                    d, version=None, emit=lambda s: self._emit_log(s),
                    exe=exe)
                # 启动器成功=真的干了活（生成/更新了文件）；它自己没有
                # `changed` 字段 → 汇总会误判成「没有需要改动的地方」。
                res["changed"] = bool(res.get("ok"))
            else:
                res = DT.enable_debug(
                    d, emit=lambda s: self._emit_log(s), force=force,
                    antidebug_plan=ad_plan,
                    # ★ 「自动关闭全量编译」的勾选：不勾就不装编译闸门
                    guard=guard,
                    # ★ 只有方式①（通用）才往 mainFunction 写 `$DEBUG=true`
                    #   —— 那本来就是方式① 的功能。
                    #   方式②（删条件）的做法本来就是把「需要 $DEBUG 才生效」
                    #   的判定**删掉**，再写一个 $DEBUG=true 属于画蛇添足；
                    #   方式⑦ 更不能设 —— 反调试里有 `exit if $DEBUG`。
                    #   以前这里是「所有非⑧方式一律写」，换方式后 Main 里
                    #   总会冒出 $DEBUG=true，让人以为「还原没生效」。
                    write_debug=(mode == "main"))
            # ★ 按选择的方式追加对应改动
            res["mode"] = mode
            try:
                if mode == "keys":
                    res["mode_res"] = ET.patch_remove_debug_conditions(
                        d, emit=lambda s: self._emit_log(s))
                elif mode == "special":
                    res["mode_res"] = ET.patch_special_key(
                        d, "special", emit=lambda s: self._emit_log(s))
                elif mode == "special_menu":
                    res["mode_res"] = ET.patch_special_key(
                        d, "special_menu", emit=lambda s: self._emit_log(s))
                elif mode == "repel":
                    res["mode_res"] = ET.patch_repel(
                        d, "repel", version=res.get("version"),
                        emit=lambda s: self._emit_log(s))
                elif mode == "repel_menu":
                    res["mode_res"] = ET.patch_repel(
                        d, "repel_menu", version=res.get("version"),
                        emit=lambda s: self._emit_log(s))
                elif mode == "rewrite":
                    # ★ 方式⑦：改名调试函数（基准函数改名后顶掉原函数）
                    #   + 全库调用点改名 + 按版本注册 T 键（规避反调试；不设 $DEBUG）
                    res["mode_res"] = ET.patch_rewrite_debug_func(
                        d, version=res.get("version"),
                        emit=lambda s: self._emit_log(s))
            except Exception as e:
                res["mode_error"] = str(e)
                self._emit_log(f"[开启] ⚠ 方式执行失败：{e}\n")
            # ★ 任务2：方式②「一个 $DEBUG 条件都没认出来」→ 交给主线程弹窗
            #   问用户要不要按版本基准在对应位置补行（见 dbg_enable_done）。
            if mode == "keys":
                try:
                    res["mode_none"] = not bool(
                        (res.get("mode_res") or {}).get("changed"))
                except Exception:
                    res["mode_none"] = False
                res["mode_game_dir"] = d
            self.q.put(("dbg_enable_done", res))
            return res

        self.run_async(work, label="开启 DEBUG 中…", done_label="开启完成")

    def _do_make_launcher(self):
        """方式⑧(测试)：在游戏目录生成调试启动器（点它即以调试模式进游戏）。"""
        # ★ 启动器不读 Data，没有 Data 也能用
        d = self._dbg_folder(need_data=False)
        if not d:
            return
        import engine_tools as ET
        exe = getattr(self, "debug_exe", None)
        try:
            kind = ET.detect_runtime(d, exe=exe)
        except Exception:
            kind = ""
        exe_txt = os.path.basename(exe) if exe else "（自动识别）"
        has_data = os.path.isdir(os.path.join(d, "Data"))
        has_pbs = os.path.isdir(os.path.join(d, "pbs"))
        miss = []
        if not has_data:
            miss.append("Data 文件夹")
        if not has_pbs:
            miss.append("pbs 文件夹")
        warned = ("\n⚠ 本目录缺少：" + "、".join(miss)
                  + "，工具会新建，并补一套空占位文件，\n"
                    "  让调试模式下不触发全量重编译报错。\n") if miss else ""
        if not messagebox.askyesno(
                "生成调试启动器（测试功能）？",
                "在游戏目录生成一个「调试启动器」，点击它即以调试模式进游戏。\n\n"
                f"· 启动程序：{exe_txt}\n"
                f"· 游戏目录：{d}\n"
                f"· 检测到的运行库：{ ET.RUNTIME_LABEL.get(kind, '未知') }\n"
                "· 不改游戏本体、不动存档，随时可删；\n"
                "· 生成：调试模式启动.py / 调试模式启动.bat\n"
                "  （mkxp-z 另有 _pkmn_debug_preload.rb）\n"
                "· 启动器会运行时看进程加载的 dll 决定打补丁方式：\n"
                "  · RGSS*.dll        → 内存补丁（v16–v18）\n"
                "  · msvcrt-ruby*.dll → mkxp-z，改用命令行 `debug` 参数（v19+）\n"
                "· 会补齐 Data/*.dat 与 pbs/*.txt 空占位文件（不覆盖已有文件）；\n"
                "· RGSS 引擎需先关掉正在运行的游戏。\n"
                f"{warned}\n"
                "继续吗？"):
            return
        self.show("log")

        def work():
            res = ET.make_debug_launcher(
                d, emit=lambda s: self._emit_log(s), exe=exe)
            self.q.put(("dbg_launcher_done", res))
            return res

        self.run_async(work, label="生成调试启动器中…", done_label="生成完成")

    # ================================================================
    # 菜单 3：PBS编辑
    # ================================================================
    def _page_pbsedit(self):
        """
        PBS 编辑入口页：右侧选游戏，中间三个模块
        （提取 PBS 文件 / 编辑 PBS 文件 / 编译 PBS 文件）。
        """
        page = self.pages["pbsedit"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=0)
        page.grid_rowconfigure(0, weight=1)

        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        holder = tk.Frame(page, bg=BG_BASE, width=340)
        holder.grid(row=0, column=1, sticky="nsew")
        holder.pack_propagate(False)
        card = RoundCard(holder, radius=16, pad=12, scrollable=True)
        card.pack(fill="both", expand=True)
        self.pbs_panel = PbsGamePanel(card.body, bg=CARD, app=self)
        self.pbs_panel.pack(fill="both", expand=True)

        outer, inner = make_scroll_area(left, bg=BG_BASE)
        outer.pack(fill="both", expand=True)

        c0 = RoundCard(inner, radius=18, pad=18, auto_height=True)
        c0.pack(fill="x")
        tk.Label(c0.body, text="PBS编辑", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        hint = tk.Label(c0.body,
                        text="右侧先选好游戏主程序，再从下面点一个动作。\n"
                             "只处理 4 个文件：宝可梦（pokemon）、宝可梦形态"
                             "（pokemon_forms）、道具（items）、招式（moves）。\n"
                             "提取和编译都按该游戏版本的官方引擎脚本走"
                             "（v19 / v19.1 / v20 / v20.1 / v21 / v21.1 各自不同），"
                             "产出与官方一致。",
                        bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                        wraplength=620)
        hint.pack(fill="x", pady=(4, 8))
        bind_autowrap(hint, pad=4)

        grid = tk.Frame(c0.body, bg=CARD)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)
        mods = [
            ("1. 提取PBS文件", self._pbs_extract,
             "把 Data 里的 .dat 还原成 txt，写到游戏根目录的 PBS 文件夹"
             "（没有就新建）。"),
            ("2. 编辑PBS文件", self._pbs_open_editor,
             "打开 PBS 窗口：左边挑一个 txt，右边按它自己的类型显示编辑界面，"
             "列表上方可以搜索条目。"),
            ("3. 编译PBS文件", self._pbs_compile,
             "把 PBS 文件夹里的 txt 编译回 Data/*.dat（第一次编译会留 .orig）。"),
        ]
        for i, (name, cmd, desc) in enumerate(mods):
            GlassButton(grid, name, width=210, height=46, bg=CARD,
                        primary=(i == 0), font=FONT_B,
                        command=cmd).grid(row=i, column=0, sticky="w", pady=5)
            lb = tk.Label(grid, text=desc, bg=CARD, fg=C_HINT,
                          font=FONT_SMALL, justify="left", wraplength=430)
            lb.grid(row=i, column=1, sticky="w", padx=(14, 0))
            bind_autowrap(lb, pad=4)

        warn = tk.Label(c0.body,
                        text="★ 编译会改游戏的 Data 目录（原文件留成 .dat.orig），"
                             "改内部名／顺序还可能让旧存档对不上 —— 动手前建议先备份。",
                        bg=CARD, fg=C_WARN, font=FONT_SMALL, justify="left",
                        wraplength=620)
        warn.pack(fill="x", pady=(12, 0))
        bind_autowrap(warn, pad=4)

        old = tk.Label(c0.body,
                       text="★ v16 / v17 / v18 的老游戏（.dat 是数组/二进制、"
                            "一半数据是衍生缓存）不建议使用此功能 "
                            "会出现未知BUG \n"
                            "★ 老版本的 .dat 里不存名字/描述， "
                            "所以会出现字段错位等问题",
                       bg=CARD, fg=C_KEY, font=FONT_SMALL, justify="left",
                       wraplength=620)
        old.pack(fill="x", pady=(6, 0))
        bind_autowrap(old, pad=4)

        # 结果区
        c1 = RoundCard(inner, radius=18, pad=18, auto_height=True)
        c1.pack(fill="x", pady=(10, 0))
        tk.Label(c1.body, text="上一次操作", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        self.pbs_result = tk.Text(c1.body, height=10, wrap="word",
                                  font=FONT_MONO, bg="#FFFFFF", fg=TEXT_DIM,
                                  relief="flat", borderwidth=0)
        self.pbs_result.pack(fill="x", pady=(6, 0))
        self.pbs_result.insert("1.0", "（还没有操作）")
        self.pbs_result.config(state="disabled")

    def _pbs_game(self):
        """当前选中的游戏根目录（没选或认不出版本就提示）。"""
        root = getattr(self, "pbs_panel", None)
        root = root.root_dir if root else config.Runtime.game_root
        if not root or not os.path.isdir(root):
            messagebox.showinfo("提示", "请先在右侧「选择游戏主程序」。")
            return None, "", ""
        fam, why = pbs_edit.detect_family(root)
        if not fam:
            messagebox.showwarning(
                "认不出版本",
                "这个游戏识别为：%s\n\nPBS 提取／编译支持 Essentials "
                "v16 ~ v21.1 的游戏。" % (why or "未知"))
            return None, "", ""
        return root, fam, why

    def _pbs_show(self, lines):
        try:
            self.pbs_result.config(state="normal")
            self.pbs_result.delete("1.0", "end")
            self.pbs_result.insert("1.0", "\n".join(lines))
            self.pbs_result.config(state="disabled")
        except Exception:
            pass

    def _pbs_extract(self):
        root, fam, _why = self._pbs_game()
        if not root:
            return
        if os.path.isdir(pbs_edit.pbs_dir(root)):
            n = len(pbs_edit.list_pbs_txt(root, fam))
            if n and not messagebox.askyesno(
                    "覆盖确认",
                    "PBS 文件夹里已经有 %d 个 txt 了。\n\n"
                    "提取会用 .dat 的内容重新生成同名文件（覆盖）。继续吗？" % n):
                return
        self.show("log")
        if log:
            log.info("PBS 提取：%s（%s）", root, fam)

        def work():
            out = []
            res = pbs_edit.extract_all(root, fam,
                                       emit=lambda r: out.append(r))
            self.q.put(("pbs_extract_done", (out, res)))
            return res

        self.run_async(work, label="提取 PBS 文件中…", done_label="提取完成")

    def _pbs_compile(self):
        root, fam, _why = self._pbs_game()
        if not root:
            return
        pbs = pbs_edit.pbs_dir(root)
        if not os.path.isdir(pbs):
            messagebox.showinfo("提示", "PBS 文件夹还没有，请先「提取PBS文件」。")
            return
        if pbs_edit.is_legacy(fam):
            # ★ 老版本（v16/v17/v18）：不硬写 .dat，改成「标记待重编译」
            if not messagebox.askyesno(
                    "确认编译（%s 老版本）" % fam,
                    "v16 / v17 / v18 的 .dat 里有一半是官方编译器的衍生缓存"
                    "（种族表、进化表、招式机表…），拆开单个写容易造成"
                    "「一半新一半旧」。\n\n"
                    "本工具的做法：把 Data 里的 .dat 标记成「比 PBS 旧」，"
                    "游戏下次启动时用它自己的编译器一次性重建全部 .dat。\n"
                    "（只改时间戳、不删文件，随时可以重来）\n\n"
                    "现在就把 %s 里的 txt 标记为待编译吗？" % pbs):
                return
            self.show("log")
            if log:
                log.info("PBS 标记待重编译：%s（%s）", root, fam)

            def work():
                import pbs_legacy
                n, msg = pbs_legacy.mark_for_recompile(root, fam)
                out = [("标记待重编译", "_mark", True, "", msg)]
                self.q.put(("pbs_compile_done", out))
                return out

            self.run_async(work, label="标记待重编译…", done_label="标记完成")
            return
        if not messagebox.askyesno(
                "确认编译",
                "要把 %s 里的 txt 编译回 Data/*.dat 吗？\n\n"
                "· 原 .dat 会备份成 .dat.orig（只留第一版）\n"
                "· 改过内部名/顺序的话，旧存档可能识别不了" % pbs):
            return
        self.show("log")
        if log:
            log.info("PBS 编译：%s（%s）", root, fam)

        def work():
            out = []
            for spec in pbs_edit.list_specs(fam):
                ok, msg, stat = pbs_edit.compile_spec(spec, fam, root)
                out.append((spec["name"], spec["key"], ok, msg, stat))
            self.q.put(("pbs_compile_done", out))
            return out

        self.run_async(work, label="编译 PBS 文件中…", done_label="编译完成")

    def _pbs_open_editor(self):
        root, fam, _why = self._pbs_game()
        if not root:
            return
        if not os.path.isdir(pbs_edit.pbs_dir(root)):
            messagebox.showinfo("提示",
                                "PBS 文件夹还没有。\n先「提取PBS文件」再来编辑。")
            return
        self.show("pbs_editor")

    def on_pbs_root_changed(self):
        """侧边栏换游戏后：清掉编辑窗口里的旧文档。"""
        self.pbs_doc = None
        self.pbs_doc_path = ""
        if getattr(self, "pbs_file_list", None) is not None:
            try:
                self._pbs_reload_file_list()
            except Exception:
                pass

    # ---- 提取 / 编译的结果 ----
    def _pbs_after_extract(self, results):
        lines = []
        ok_n = 0
        for r in results:
            if r.get("ok"):
                ok_n += 1
                lines.append("✔ %-10s %-26s %s" % (
                    r["name"], r["file"], r.get("stat") or ""))
            else:
                lines.append("· %-10s 跳过（%s）" % (
                    r["name"], (r.get("stat") or "没有这个 .dat")[:40]))
        self._pbs_show(lines or ["（没有可提取的文件）"])
        self.status_var.set("PBS 提取完成：%d 个文件" % ok_n)
        if getattr(self, "pbs_panel", None):
            self.pbs_panel._sync()
        self._pbs_reload_file_list()

    def _pbs_after_compile(self, results):
        lines = []
        ok_n = 0
        for name, _key, ok, msg, stat in results:
            if ok:
                ok_n += 1
                lines.append("✔ %-10s %s" % (name, stat))
            else:
                txt = (msg or "").strip()
                if "找不到" in txt and txt.endswith(".txt"):
                    lines.append("· %-10s 跳过（PBS 里没有这个 txt）" % name)
                elif "找不到" in txt:
                    lines.append("· %-10s 跳过（%s）" % (name, txt))
                else:
                    lines.append("✘ %-10s %s" % (name, txt))
        self._pbs_show(lines or ["（没有可编译的文件）"])
        self.status_var.set("PBS 编译完成：%d 个" % ok_n)

    # ================================================================
    # 子页面：PBS 编辑窗口
    #   左边是游戏 PBS 文件夹里的 txt（显示中文名），
    #   右边按这个 txt 的类型显示对应的编辑界面。
    # ================================================================
    def _page_pbs_editor(self):
        page = self.pages["pbs_editor"]
        page.grid_columnconfigure(0, weight=0)
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(0, weight=1)

        # ---- 左：文件列表 ----
        lcol = tk.Frame(page, bg=BG_BASE, width=320)
        lcol.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        lcol.pack_propagate(False)
        lcard = RoundCard(lcol, radius=16, pad=12)
        lcard.pack(fill="both", expand=True)
        tk.Label(lcard.body, text="PBS 文件", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", padx=8, pady=(2, 4))
        tk.Label(lcard.body, text="点一个文件，右边就是它自己的编辑界面：",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                 wraplength=280).pack(anchor="w", padx=8, pady=(0, 6))

        # ★ 底部按钮先按 side="bottom" 钉住，再让列表 expand（否则被挤出卡片）
        row = tk.Frame(lcard.body, bg=CARD)
        row.pack(side="bottom", fill="x", pady=(6, 0))
        GlassButton(row, "刷新", width=76, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pbs_reload_file_list).pack(side="left")
        GlassButton(row, "打开文件夹", width=110, height=34, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pbs_open_dir).pack(side="left", padx=(6, 0))

        fouter, finner = make_scroll_area(lcard.body, bg=CARD)
        fouter.pack(fill="both", expand=True, pady=(4, 0))
        self.pbs_file_box = finner
        self.pbs_file_list = []

        # ---- 右：条目 + 表单 ----
        right = tk.Frame(page, bg=BG_BASE)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=0)
        right.grid_columnconfigure(1, weight=1)
        right.grid_rowconfigure(0, weight=1)

        # 条目列表
        ecol = tk.Frame(right, bg=BG_BASE, width=300)
        ecol.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ecol.pack_propagate(False)
        ecard = RoundCard(ecol, radius=16, pad=12, scrollable=True)
        ecard.pack(fill="both", expand=True)
        self.pbs_entry_title = tk.Label(ecard.body, text="（选一个文件）",
                                        bg=CARD, fg=C_TITLE,
                                        font=FONT_B, anchor="w")
        self.pbs_entry_title.pack(fill="x", padx=6, pady=(2, 4))
        # ★ 搜索框：按 中文名 / 内部名 / 字段内容 过滤当前文件的条目
        srow = tk.Frame(ecard.body, bg=CARD)
        srow.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(srow, text="搜索", bg=CARD, fg=TEXT,
                 font=FONT_SMALL).pack(side="left")
        self.pbs_search_var = tk.StringVar(value="")
        sent = tk.Entry(srow, textvariable=self.pbs_search_var,
                        font=FONT_SMALL, bg="#FFFFFF", relief="flat",
                        highlightthickness=2,
                        highlightbackground=FIELD_BORDER,
                        highlightcolor=FIELD_BORDER_FOCUS)
        sent.pack(side="left", fill="x", expand=True, padx=(6, 4))
        self.pbs_search_var.trace_add("write", self._pbs_on_search_change)
        GlassButton(srow, "清空", width=52, height=26, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pbs_clear_search).pack(side="left")
        self.pbs_search_info = tk.Label(ecard.body, text="", bg=CARD,
                                        fg=C_HINT, font=FONT_SMALL,
                                        anchor="w")
        self.pbs_search_info.pack(fill="x", padx=6)
        # ★ 增删按钮先按 side="bottom" 钉在底部，再让表格 expand —— 否则表格
        #   会把空间吃光，把按钮挤出卡片下沿（用户截图里按钮被切了一半）。
        erow = tk.Frame(ecard.body, bg=CARD)
        erow.pack(side="bottom", fill="x", pady=(6, 0))
        GlassButton(erow, "新增", width=64, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pbs_add_entry).pack(side="left")
        GlassButton(erow, "复制", width=64, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pbs_dup_entry).pack(side="left", padx=(4, 0))
        GlassButton(erow, "删除", width=64, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pbs_del_entry).pack(side="left", padx=(4, 0))

        tree_holder = tk.Frame(ecard.body, bg=CARD)
        tree_holder.pack(fill="both", expand=True)
        self.pbs_entry_tree = ttk.Treeview(
            tree_holder, columns=("name",), show="headings", height=12)
        self.pbs_entry_tree.heading("name", text="条目")
        self.pbs_entry_tree.column("name", width=250, anchor="w",
                                   stretch=True)
        sb = ttk.Scrollbar(tree_holder, orient="vertical",
                           command=self.pbs_entry_tree.yview)
        self.pbs_entry_tree.configure(yscrollcommand=sb.set)
        self.pbs_entry_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        bind_tree_wheel(self.pbs_entry_tree)
        self.pbs_entry_tree.bind("<<TreeviewSelect>>",
                                 self._pbs_on_entry_select)

        # 表单区
        fcol = tk.Frame(right, bg=BG_BASE)
        fcol.grid(row=0, column=1, sticky="nsew")
        fcard = RoundCard(fcol, radius=16, pad=12)
        fcard.pack(fill="both", expand=True)
        bar = tk.Frame(fcard.body, bg=CARD)
        bar.pack(fill="x")
        self.pbs_form_title = tk.Label(bar, text="", bg=CARD, fg=C_TITLE,
                                       font=FONT_TITLE, anchor="w")
        self.pbs_form_title.pack(side="left")
        GlassButton(bar, "保存到 txt", width=118, height=36, primary=True,
                    bg=CARD, font=FONT_SMALL,
                    command=self._pbs_save_doc).pack(side="right")
        GlassButton(bar, "编译到 .dat", width=118, height=36, bg=CARD,
                    font=FONT_SMALL,
                    command=self._pbs_compile_current).pack(side="right",
                                                            padx=(0, 6))
        self.pbs_hint = tk.Label(fcard.body, text="", bg=CARD, fg=C_HINT,
                                 font=FONT_SMALL, justify="left",
                                 wraplength=520, anchor="w")
        self.pbs_hint.pack(fill="x", pady=(4, 0))
        outer, inner = make_scroll_area(fcard.body, bg=CARD)
        outer.pack(fill="both", expand=True, pady=(4, 0))
        self.pbs_form_box = inner
        self.pbs_form_getters = []

    # ---- 左侧文件列表 ----
    def _pbs_open_dir(self):
        root = getattr(self, "pbs_panel", None)
        root = root.root_dir if root else config.Runtime.game_root
        if not root:
            return
        try:
            d = pbs_edit.pbs_dir(root)
            os.makedirs(d, exist_ok=True)
            os.startfile(d) if hasattr(os, "startfile") else None
        except Exception as e:                                  # noqa: BLE001
            messagebox.showwarning("打开失败", str(e))

    def _pbs_reload_file_list(self):
        box = getattr(self, "pbs_file_box", None)
        if box is None:
            return
        for w in box.winfo_children():
            w.destroy()
        self.pbs_file_list = []
        root = getattr(self, "pbs_panel", None)
        root = root.root_dir if root else config.Runtime.game_root
        if not root:
            tk.Label(box, text="（还没选游戏）", bg=CARD, fg=C_HINT,
                     font=FONT_SMALL).pack(anchor="w", padx=6, pady=8)
            return
        fam, _why = pbs_edit.detect_family(root)
        files = pbs_edit.list_pbs_txt(root, fam)
        if not files:
            tk.Label(box, text="PBS 文件夹是空的，\n先回上一页「提取PBS文件」。",
                     bg=CARD, fg=C_HINT, font=FONT_SMALL,
                     justify="left").pack(anchor="w", padx=6, pady=8)
            return
        self.pbs_file_list = files
        for i, f in enumerate(files):
            btn = GlassButton(box, f["name"], width=270, height=38,
                              bg=CARD, font=FONT_SMALL,
                              command=lambda idx=i: self._pbs_open_file(idx))
            btn.pack(fill="x", pady=2)

    def _pbs_open_file(self, idx):
        if idx >= len(self.pbs_file_list):
            return
        f = self.pbs_file_list[idx]
        root = self.pbs_panel.root_dir if getattr(self, "pbs_panel", None) \
            else config.Runtime.game_root
        fam, _why = pbs_edit.detect_family(root)
        spec = pbs_edit.spec_for(f["key"], fam) if f["key"] else None
        doc = pbs_edit.Doc.load(spec, fam, f["path"])
        if spec is None:
            # 没登记的类型（对战设施引用的文件等）用最简单的段式界面打开
            doc.style = "section"
            doc.editor = "generic"
        self.pbs_doc = doc
        self.pbs_doc_path = f["path"]
        self._pbs_clear_search_quiet()
        self._pbs_refresh_entries(keep_sel=0)

    def _pbs_entry_matches(self, entry, query):
        """条目是否命中搜索词（中文名 / 内部名 / 任意字段内容）。"""
        if not query:
            return True
        q = query.lower()
        if q in (entry.label() or "").lower() or q in (entry.sid or "").lower():
            return True
        for k, v in entry.fields:
            if q in k.lower() or q in str(v).lower():
                return True
        return False

    def _pbs_clear_search(self):
        self.pbs_search_var.set("")

    def _pbs_clear_search_quiet(self):
        """清空搜索框但不触发刷新（调用方自己接着刷新条目表）。"""
        var = getattr(self, "pbs_search_var", None)
        if var is None:
            return
        self._pbs_suppress_search = True
        try:
            var.set("")
        finally:
            self._pbs_suppress_search = False

    def _pbs_on_search_change(self, *_a):
        if getattr(self, "_pbs_suppress_search", False):
            return
        doc = getattr(self, "pbs_doc", None)
        if doc is None:
            return
        self._pbs_refresh_entries(keep_sel=None)

    def _pbs_refresh_entries(self, keep_sel=None):
        doc = getattr(self, "pbs_doc", None)
        tree = self.pbs_entry_tree
        for iid in tree.get_children():
            tree.delete(iid)
        if doc is None:
            self.pbs_entry_title.config(text="（选一个文件）")
            self.pbs_form_title.config(text="")
            if getattr(self, "pbs_search_info", None) is not None:
                self.pbs_search_info.config(text="")
            for w in self.pbs_form_box.winfo_children():
                w.destroy()
            return
        query = ""
        var = getattr(self, "pbs_search_var", None)
        if var is not None:
            try:
                query = var.get().strip()
            except tk.TclError:
                query = ""
        hit = 0
        first = None
        for i, e in enumerate(doc.entries):
            if not self._pbs_entry_matches(e, query):
                continue
            tree.insert("", "end", iid="e%d" % i,
                        values=(e.label() or "(空)",))
            hit += 1
            if first is None:
                first = i
        self.pbs_entry_title.config(
            text="%s：%d 条（%s）" % (doc.name, len(doc.entries),
                                     os.path.basename(doc.path)))
        if getattr(self, "pbs_search_info", None) is not None:
            if query:
                self.pbs_search_info.config(
                    text="搜索「%s」：命中 %d / %d 条" % (query, hit,
                                                         len(doc.entries)))
            else:
                self.pbs_search_info.config(
                    text="共 %d 条" % len(doc.entries))
        if hit:
            if keep_sel is not None and ("e%d" % keep_sel) in tree.get_children():
                sel = "e%d" % keep_sel
            else:
                sel = "e%d" % (first if first is not None else 0)
            tree.selection_set(sel)
            tree.focus(sel)
            tree.see(sel)
            self._pbs_on_entry_select()
        else:
            self.pbs_form_title.config(text="没有匹配的条目")
            self.pbs_form_getters = []
            for w in self.pbs_form_box.winfo_children():
                w.destroy()

    def _pbs_on_entry_select(self, _e=None):
        self._pbs_apply_form()          # 先把当前表单写回内存
        doc = getattr(self, "pbs_doc", None)
        if doc is None:
            return
        sel = self.pbs_entry_tree.selection()
        if not sel:
            return
        idx = int(sel[0][1:])
        if idx >= len(doc.entries):
            return
        self.pbs_cur_idx = idx
        self._pbs_build_form(doc.entries[idx])

    # ---- 表单：按文件类型造界面 ----
    def _pbs_build_form(self, entry):
        doc = self.pbs_doc
        for w in self.pbs_form_box.winfo_children():
            w.destroy()
        self.pbs_form_getters = []
        self.pbs_form_title.config(text=entry.label() or entry.sid)
        kind = doc.editor
        if kind == "trainers":
            self._pbs_form_trainer(entry)
        elif kind == "encounters":
            self._pbs_form_encounter(entry)
        elif kind == "townmap":
            self._pbs_form_townmap(entry)
        elif kind == "connections":
            self._pbs_form_connections(entry)
        elif kind == "regional":
            self._pbs_form_regional(entry)
        elif kind == "phone":
            self._pbs_form_phone(entry)
        else:
            self._pbs_form_generic(entry)
        self.pbs_hint.config(text=PBS_FORM_HINTS.get(kind, PBS_FORM_HINTS["generic"]))

    # ---- 通用字段控件 ----
    #   ★ 输入框统一用醒目的宝可蓝描边（2px），鼠标不用找；每个字段下面
    #     再跟一行灰色中文说明，讲这个字段是干什么的。
    def _row(self, parent, label, desc=""):
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=(4, 0))
        tk.Label(r, text=label, bg=CARD, fg=TEXT, font=FONT_SMALL,
                 width=16, anchor="w").pack(side="left")
        return r

    def _desc(self, parent, text):
        if not text:
            return
        lb = tk.Label(parent, text="　　" + text, bg=CARD, fg=C_HINT,
                      font=FONT_SMALL, justify="left", anchor="w")
        lb.pack(fill="x", padx=(0, 4))
        bind_autowrap(lb, pad=4)

    def _f_entry(self, parent, label, value, width=28, desc=""):
        r = self._row(parent, label)
        var = tk.StringVar(value=value)
        ent = tk.Entry(r, textvariable=var, width=width, font=FONT_SMALL,
                       bg="#FFFFFF", relief="flat",
                       highlightthickness=2,
                       highlightbackground=FIELD_BORDER,
                       highlightcolor=FIELD_BORDER_FOCUS)
        ent.pack(side="left", fill="x", expand=True)
        self.pbs_form_getters.append((label, var.get))
        self._desc(parent, desc)
        return ent

    def _f_combo(self, parent, label, value, options, width=26, desc=""):
        r = self._row(parent, label)
        var = tk.StringVar(value=value)
        box = tk.Frame(r, bg=FIELD_BORDER, padx=1, pady=1)
        box.pack(side="left")
        cb = ttk.Combobox(box, textvariable=var, width=width,
                          font=FONT_SMALL, values=list(options))
        cb.pack(side="left")
        self.pbs_form_getters.append((label, var.get))
        self._desc(parent, desc)
        return cb

    def _f_bool(self, parent, label, value, desc=""):
        r = self._row(parent, label)
        var = tk.BooleanVar(value=str(value).strip().lower() in
                            ("1", "true", "yes", "y"))
        tk.Checkbutton(r, variable=var, bg=CARD, activebackground=CARD,
                       selectcolor="#FFFFFF").pack(side="left")
        self.pbs_form_getters.append(
            (label, lambda: "true" if var.get() else "false"))
        self._desc(parent, desc)
        return r

    def _f_text(self, parent, label, value, height=3, desc=""):
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=(4, 0))
        tk.Label(r, text=label, bg=CARD, fg=TEXT, font=FONT_SMALL,
                 anchor="w").pack(anchor="w")
        txt = tk.Text(r, height=height, wrap="word", font=FONT_SMALL,
                      bg="#FFFFFF", relief="flat", highlightthickness=2,
                      highlightbackground=FIELD_BORDER,
                      highlightcolor=FIELD_BORDER_FOCUS)
        txt.insert("1.0", value)
        txt.pack(fill="x")
        self.pbs_form_getters.append(
            (label, lambda: txt.get("1.0", "end").strip()))
        self._desc(parent, desc)
        return txt

    def _f_lines(self, parent, label, value, height=5, desc=""):
        """多值字段：一行一个（写回时用逗号连接）。"""
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=(4, 0))
        tk.Label(r, text=label + "（一行一个）", bg=CARD, fg=TEXT,
                 font=FONT_SMALL, anchor="w").pack(anchor="w")
        txt = tk.Text(r, height=height, wrap="none", font=FONT_SMALL,
                      bg="#FFFFFF", relief="flat", highlightthickness=2,
                      highlightbackground=FIELD_BORDER,
                      highlightcolor=FIELD_BORDER_FOCUS)
        txt.insert("1.0", "\n".join(
            x.strip() for x in value.split(",") if x.strip()))
        txt.pack(fill="x")
        self.pbs_form_getters.append(
            (label, lambda: ",".join(
                ln.strip() for ln in txt.get("1.0", "end").splitlines()
                if ln.strip())))
        self._desc(parent, desc)
        return txt

    def _f_stats(self, parent, label, value, order, desc=""):
        """六项能力值 / 努力值。"""
        r = self._row(parent, label)
        parts = [x.strip() for x in value.split(",")]
        vars_ = []
        for st in order:
            sub = tk.Frame(r, bg=CARD)
            sub.pack(side="left", padx=(0, 6))
            tk.Label(sub, text=pbs_edit.STAT_LABELS.get(st, st), bg=CARD,
                     fg=C_HINT, font=FONT_SMALL).pack(side="left")
            v = tk.StringVar(value=parts[len(vars_)] if len(parts) >
                             len(vars_) else "0")
            tk.Entry(sub, textvariable=v, width=4, font=FONT_SMALL,
                     bg="#FFFFFF", relief="flat", highlightthickness=2,
                     highlightbackground=FIELD_BORDER,
                     highlightcolor=FIELD_BORDER_FOCUS).pack(side="left")
            vars_.append((st, v))
        self.pbs_form_getters.append(
            (label, lambda: ",".join(v.get() or "0" for _s, v in vars_)))
        self._desc(parent, desc)
        return r

    def _f_evs(self, parent, label, value, order, desc=""):
        """努力值：PBS 里写成 属性,值 一对一对。"""
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=(4, 0))
        tk.Label(r, text=label + "（只写不为 0 的）", bg=CARD, fg=TEXT,
                 font=FONT_SMALL, anchor="w").pack(anchor="w")
        row = tk.Frame(r, bg=CARD)
        row.pack(fill="x")
        vals = [x.strip() for x in value.split(",") if x.strip()]
        pairs = {}
        for i in range(0, len(vals) - 1, 2):
            pairs[vals[i]] = vals[i + 1]
        vars_ = []
        for st in order:
            sub = tk.Frame(row, bg=CARD)
            sub.pack(side="left", padx=(0, 8))
            tk.Label(sub, text=pbs_edit.STAT_LABELS.get(st, st), bg=CARD,
                     fg=C_HINT, font=FONT_SMALL).pack(side="left")
            v = tk.StringVar(value=pairs.get(st, "0"))
            tk.Entry(sub, textvariable=v, width=4, font=FONT_SMALL,
                     bg="#FFFFFF", relief="flat", highlightthickness=2,
                     highlightbackground=FIELD_BORDER,
                     highlightcolor=FIELD_BORDER_FOCUS).pack(side="left")
            vars_.append((st, v))

        def get():
            out = []
            for st, v in vars_:
                n = (v.get() or "").strip()
                if n and n != "0":
                    out.append("%s,%s" % (st, n))
            return ",".join(out)
        self.pbs_form_getters.append((label, get))
        self._desc(parent, desc)
        return r

    def _f_pairs(self, parent, label, value, n, sub_labels=None, desc=""):
        """定长数组（ii / uuu / vuuu …）：一格一个值。"""
        r = self._row(parent, label)
        parts = [x.strip() for x in value.split(",")]
        vars_ = []
        for i in range(n):
            sub = tk.Frame(r, bg=CARD)
            sub.pack(side="left", padx=(0, 6))
            if sub_labels and i < len(sub_labels):
                tk.Label(sub, text=sub_labels[i], bg=CARD, fg=C_HINT,
                         font=FONT_SMALL).pack(side="left")
            v = tk.StringVar(value=parts[i] if i < len(parts) else "")
            tk.Entry(sub, textvariable=v, width=10, font=FONT_SMALL,
                     bg="#FFFFFF", relief="flat", highlightthickness=2,
                     highlightbackground=FIELD_BORDER,
                     highlightcolor=FIELD_BORDER_FOCUS).pack(side="left")
            vars_.append(v)
        self.pbs_form_getters.append(
            (label, lambda: ",".join(v.get() for v in vars_)))
        self._desc(parent, desc)
        return r

    def _f_table(self, parent, label, value, cols, per_row, desc=""):
        """表格型字段（升级招式 / 进化）：一行一条，逗号分隔。"""
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=(4, 0))
        tk.Label(r, text="%s（一行一条：%s）" % (label, ",".join(cols)),
                 bg=CARD, fg=TEXT, font=FONT_SMALL,
                 anchor="w").pack(anchor="w")
        txt = tk.Text(r, height=6, wrap="none", font=FONT_SMALL,
                      bg="#FFFFFF", relief="flat", highlightthickness=2,
                      highlightbackground=FIELD_BORDER,
                      highlightcolor=FIELD_BORDER_FOCUS)
        vals = [x.strip() for x in value.split(",") if x.strip()]
        lines = []
        for i in range(0, len(vals) - per_row + 1, per_row):
            lines.append(",".join(vals[i:i + per_row]))
        txt.insert("1.0", "\n".join(lines))
        txt.pack(fill="x")
        self.pbs_form_getters.append(
            (label, lambda: ",".join(
                x.strip() for x in
                txt.get("1.0", "end").replace("\n", ",").split(",")
                if x.strip())))
        self._desc(parent, desc)
        return txt


    @staticmethod
    def _field_desc(key: str, doc) -> str:
        """这个字段的中文说明（按文件覆盖优先）。"""
        fk = getattr(doc, "key", "") or ""
        hit = pbs_edit.FIELD_DESC_BY_FILE.get((fk, key))
        return hit or pbs_edit.field_desc(key)

    def _pbs_form_generic(self, entry):
        doc = self.pbs_doc
        schema = pbs_edit.schema_of(doc.spec, doc.family) if doc.spec else []
        box = self.pbs_form_box
        # 段名（内部名 / 编号 / 形态）
        if doc.style == "kv":
            self._f_entry(box, "键名", entry.sid)
        elif doc.style == "line":
            pass                      # 行式文件的段名就是整行，下面按字段改
        else:
            self._f_entry(box, "段名", entry.sid, width=34)
        known = set()
        for key, _ivar, ctype, enum in schema:
            known.add(key)
            val = entry.get(key, "")
            base = ctype[1:] if ctype[0] in "*^" else ctype
            desc = self._field_desc(key, doc)
            if ctype[0] == "^" or base in ("ue", "ses", "ees"):
                cols = {"ue": ("等级", "招式"),
                        "ses": ("目标", "方式", "参数"),
                        "ees": ("目标", "方式", "参数")}.get(base, ("值",))
                self._f_table(box, key, val, cols,
                              2 if base == "ue" else 3, desc=desc)
            elif base in ("uuuuuu", "vvvvvv"):
                self._f_stats(box, key, val, pbs_edit.stat_order(doc.family),
                              desc=desc)
            elif base == "ev":
                self._f_evs(box, key, val, pbs_edit.stat_order(doc.family),
                            desc=desc)
            elif base in ("player", "ball"):
                self._f_entry(box, key, val, desc=desc)
            elif re.fullmatch(r"[a-zA-Z]{2,}", base) and \
                    base[0] not in ("s", "q", "n", "m"):
                self._f_pairs(box, key, val, len(base), desc=desc)
            elif ctype[0] in "*^":
                self._f_lines(box, key, val, desc=desc)
            elif base == "b":
                self._f_bool(box, key, val, desc=desc)
            elif base == "q":
                self._f_text(box, key, val, height=4, desc=desc)
            elif enum:
                self._f_combo(box, key, val,
                              [""] + sorted(enum.keys()), desc=desc)
            else:
                self._f_entry(box, key, val, desc=desc)
        # 文件里有但表里没有的键也列出来，别丢
        for k, v in entry.fields:
            if k in known:
                continue
            self._f_entry(box, k + "（未登记）", v,
                          desc=pbs_edit.field_desc(k))

    def _pbs_form_trainer(self, entry):
        box = self.pbs_form_box
        self._f_entry(box, "段名（类型,名字,版本）", entry.sid, width=34,
                      desc="这段的标识：训练家类型内部名,名字[,版本号]。"
                           "版本号用于同一训练家的多套队伍（0 可省略）")
        schema = pbs_edit.schema_of(self.pbs_doc.spec, self.pbs_doc.family)
        for key, _i, ctype, _e in schema:
            d = self._field_desc(key, self.pbs_doc)
            if ctype == "q":
                self._f_text(box, key, entry.get(key, ""), height=3, desc=d)
            else:
                self._f_lines(box, key, entry.get(key, ""), height=2, desc=d)
        sub = self.pbs_doc.spec.get("sub_schema", {}).get(
            self.pbs_doc.family) or []
        tk.Label(box, text="队伍（每只一块；改完点右上角保存）", bg=CARD,
                 fg=C_TITLE, font=FONT_B).pack(anchor="w", pady=(10, 2))
        self.pbs_pkmn_rows = []
        for i, p in enumerate(entry.data.get("pokemon", [])):
            self._pbs_pkmn_block(box, i, p, sub)
        self._desc(box, "整行的书写格式（看懂这个就不用怕）：段名开头的"
                        "方括号里是「类型,名字,版本」，Items/LoseText 属于训练家本人；"
                        "下面每条 Pokemon = 种族,等级 是一只，缩进的键属于那一只。")

    def _pbs_pkmn_block(self, box, idx, p, sub):
        f = tk.LabelFrame(box, text="#%d" % (idx + 1), bg=CARD, fg=TEXT,
                          font=FONT_SMALL)
        f.pack(fill="x", pady=4)
        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x")
        sp = tk.StringVar(value=p.get("species", ""))
        lv = tk.StringVar(value=p.get("level", "1"))
        tk.Label(row, text="种族", bg=CARD, fg=C_HINT,
                 font=FONT_SMALL).pack(side="left")
        tk.Entry(row, textvariable=sp, width=18, font=FONT_SMALL,
                 bg="#FFFFFF", relief="flat", highlightthickness=2,
                 highlightbackground=FIELD_BORDER,
                 highlightcolor=FIELD_BORDER_FOCUS).pack(side="left", padx=4)
        tk.Label(row, text="等级", bg=CARD, fg=C_HINT,
                 font=FONT_SMALL).pack(side="left", padx=(8, 0))
        tk.Entry(row, textvariable=lv, width=5, font=FONT_SMALL,
                 bg="#FFFFFF", relief="flat", highlightthickness=2,
                 highlightbackground=FIELD_BORDER,
                 highlightcolor=FIELD_BORDER_FOCUS).pack(side="left", padx=4)
        rest = {}
        for key, _i, ctype, _e in sub:
            if key in ("species", "level"):
                continue
            r = tk.Frame(f, bg=CARD)
            r.pack(fill="x", pady=(3, 0))
            tk.Label(r, text=key, bg=CARD, fg=TEXT, font=FONT_SMALL,
                     width=16, anchor="w").pack(side="left")
            if ctype == "b":
                v = tk.BooleanVar(value=p.get(key, "").lower() in
                                  ("1", "true", "yes", "y"))
                tk.Checkbutton(r, variable=v, bg=CARD,
                               activebackground=CARD,
                               selectcolor="#FFFFFF").pack(side="left")
                rest[key] = v
            elif ctype == "uuuuuu":
                parts = [x.strip() for x in p.get(key, "").split(",")]
                vs = []
                for i2, st in enumerate(pbs_edit.stat_order(
                        self.pbs_doc.family)):
                    vv = tk.StringVar(value=parts[i2] if i2 < len(parts)
                                      else "0")
                    tk.Entry(r, textvariable=vv, width=4, font=FONT_SMALL,
                             bg="#FFFFFF", relief="flat",
                             highlightthickness=2,
                             highlightbackground=FIELD_BORDER,
                             highlightcolor=FIELD_BORDER_FOCUS).pack(
                                 side="left")
                    vs.append(vv)
                rest[key] = vs
            elif ctype == "*e":
                v = tk.StringVar(value=p.get(key, ""))
                tk.Entry(r, textvariable=v, width=40, font=FONT_SMALL,
                         bg="#FFFFFF", relief="flat", highlightthickness=2,
                         highlightbackground=FIELD_BORDER,
                         highlightcolor=FIELD_BORDER_FOCUS).pack(side="left")
                rest[key] = v
            else:
                v = tk.StringVar(value=p.get(key, ""))
                tk.Entry(r, textvariable=v, width=22, font=FONT_SMALL,
                         bg="#FFFFFF", relief="flat", highlightthickness=2,
                         highlightbackground=FIELD_BORDER,
                         highlightcolor=FIELD_BORDER_FOCUS).pack(side="left")
                rest[key] = v
            self._desc(f, pbs_edit.FIELD_DESC_SUB.get(key, ""))

        def apply_(_p=p, _sp=sp, _lv=lv, _rest=rest, _sub=sub):
            _p["species"] = _sp.get()
            _p["level"] = _lv.get()
            for key, _i, ctype, _e in _sub:
                if key in ("species", "level") or key not in _rest:
                    continue
                w = _rest[key]
                if isinstance(w, list):
                    _p[key] = ",".join(x.get() or "0" for x in w)
                elif isinstance(w, tk.BooleanVar):
                    _p[key] = "yes" if w.get() else ""
                else:
                    _p[key] = w.get()
        self.pbs_form_getters.append(("队伍#%d" % (idx + 1), apply_))

    def _pbs_form_encounter(self, entry):
        box = self.pbs_form_box
        m = tk.StringVar(value=entry.data.get("map", "0"))
        v = tk.StringVar(value=entry.data.get("version", "0"))
        r = tk.Frame(box, bg=CARD)
        r.pack(fill="x", pady=(4, 0))
        tk.Label(r, text="地图编号", bg=CARD, fg=TEXT, font=FONT_SMALL,
                 width=16, anchor="w").pack(side="left")
        tk.Entry(r, textvariable=m, width=8, font=FONT_SMALL, bg="#FFFFFF",
                 relief="flat", highlightthickness=2,
                 highlightbackground=FIELD_BORDER,
                 highlightcolor=FIELD_BORDER_FOCUS).pack(side="left")
        tk.Label(r, text="版本", bg=CARD, fg=TEXT, font=FONT_SMALL,
                 anchor="w").pack(side="left", padx=(10, 0))
        tk.Entry(r, textvariable=v, width=6, font=FONT_SMALL, bg="#FFFFFF",
                 relief="flat", highlightthickness=2,
                 highlightbackground=FIELD_BORDER,
                 highlightcolor=FIELD_BORDER_FOCUS).pack(side="left")
        self._desc(box, "地图编号 = 游戏里那张地图的编号（和 RPG Maker 里一致）；"
                        "版本用于同一张地图的多套遇敌表，没有就填 0")
        self.pbs_form_getters.append(("地图", m.get))
        self.pbs_form_getters.append(("版本", v.get))

        tk.Label(box, text="遭遇类型", bg=CARD,
                 fg=C_TITLE, font=FONT_B).pack(anchor="w", pady=(10, 2))
        self._desc(box, "每种遭遇一块：Land 草丛、Water 水面、OldRod 旧钓竿…；"
                        "「步数概率」是踩一步遇到它的概率（0 = 只靠钓竿/道具触发）。"
                        "槽位一行一条：概率,种族,最低等级,最高等级")
        self.pbs_enc_types = []
        for i, (tname, chance, slots) in enumerate(
                entry.data.get("types", [])):
            f = tk.LabelFrame(box, text=tname, bg=CARD, fg=TEXT,
                              font=FONT_SMALL)
            f.pack(fill="x", pady=4)
            row = tk.Frame(f, bg=CARD)
            row.pack(fill="x")
            tv = tk.StringVar(value=tname)
            cv = tk.StringVar(value=chance)
            tk.Label(row, text="类型", bg=CARD, fg=C_HINT,
                     font=FONT_SMALL).pack(side="left")
            tk.Entry(row, textvariable=tv, width=16, font=FONT_SMALL,
                     bg="#FFFFFF", relief="flat", highlightthickness=2,
                     highlightbackground=FIELD_BORDER,
                     highlightcolor=FIELD_BORDER_FOCUS).pack(side="left")
            tk.Label(row, text="步数概率", bg=CARD, fg=C_HINT,
                     font=FONT_SMALL).pack(side="left", padx=(8, 0))
            tk.Entry(row, textvariable=cv, width=6, font=FONT_SMALL,
                     bg="#FFFFFF", relief="flat", highlightthickness=2,
                     highlightbackground=FIELD_BORDER,
                     highlightcolor=FIELD_BORDER_FOCUS).pack(side="left")
            tk.Label(f, text="槽位：概率,种族,最低级,最高级（一行一条）",
                     bg=CARD, fg=C_HINT, font=FONT_SMALL,
                     anchor="w").pack(anchor="w")
            st = tk.Text(f, height=max(2, len(slots) + 1), wrap="none",
                         font=FONT_SMALL, bg="#FFFFFF", relief="flat",
                         highlightthickness=2,
                         highlightbackground=FIELD_BORDER,
                         highlightcolor=FIELD_BORDER_FOCUS)
            st.insert("1.0", "\n".join(",".join(s) for s in slots))
            st.pack(fill="x")
            self.pbs_enc_types.append((tv, cv, st))

            def apply(_tv=tv, _cv=cv, _st=st, _slots=slots):
                _slots[:] = [
                    [x.strip() for x in ln.split(",") if x.strip() != ""]
                    for ln in _st.get("1.0", "end").splitlines()
                    if ln.strip()]
                return _tv.get(), _cv.get()
            self.pbs_form_getters.append(("遭遇%s" % tname, apply))

    def _pbs_form_townmap(self, entry):
        box = self.pbs_form_box
        self._f_entry(box, "区域编号", entry.sid, width=10,
                      desc="这块区域地图的编号（0 = 第一张区域地图）")
        for k, v in entry.fields:
            self._f_entry(box, k, v, desc=self._field_desc(k, self.pbs_doc))
        tk.Label(box, text="地点", bg=CARD,
                 fg=C_TITLE, font=FONT_B).pack(anchor="w", pady=(10, 2))
        self._desc(box, "一行一个地点：x,y,地点名,说明文字"
                        "（说明可以不写；再往后还能接 跳转地图,地图x,地图y）")
        txt = tk.Text(box, height=12, wrap="none", font=FONT_SMALL,
                      bg="#FFFFFF", relief="flat", highlightthickness=2,
                      highlightbackground=FIELD_BORDER,
                      highlightcolor=FIELD_BORDER_FOCUS)
        txt.insert("1.0", "\n".join(
            ",".join(p) for p in entry.data.get("points", [])))
        txt.pack(fill="x")

        def get():
            entry.data["points"] = [
                [x.strip() for x in ln.split(",")]
                for ln in txt.get("1.0", "end").splitlines() if ln.strip()]
            return ""
        self.pbs_form_getters.append(("地点", get))

    def _pbs_form_connections(self, entry):
        box = self.pbs_form_box
        labels = ("地图A", "边A(N/S/E/W)", "坐标A", "地图B", "边B", "坐标B")
        vals = [v for _k, v in entry.fields]
        self._f_pairs(box, "连接", ",".join(vals), 6, labels,
                      desc="一张地图连接：地图A,从哪条边出去,在那条边上的坐标,"
                           "地图B,接到它的哪条边,坐标")
        self._desc(box, "方向写法：N 北 / S 南 / E 东 / W 西；"
                        "A 的边和 B 的边必须相对（北对南、东对西）")

    def _pbs_form_regional(self, entry):
        box = self.pbs_form_box
        self._f_entry(box, "图鉴编号", entry.sid, width=10,
                      desc="第几本地区图鉴（0 = 第一本，和 metadata 里的"
                           "MapPosition 第一个数字对应）")
        self._desc(box, "按图鉴顺序写宝可梦的内部名（或编号），一行若干只、"
                        "逗号分隔；顺序就是图鉴里的排列顺序")
        txt = tk.Text(box, height=14, wrap="word", font=FONT_SMALL,
                      bg="#FFFFFF", relief="flat", highlightthickness=2,
                      highlightbackground=FIELD_BORDER,
                      highlightcolor=FIELD_BORDER_FOCUS)
        txt.insert("1.0", "\n".join(entry.data.get("species", [])))
        txt.pack(fill="x")

        def get():
            entry.data["species"] = [
                x.strip() for x in
                txt.get("1.0", "end").replace("\n", ",").split(",")
                if x.strip()]
            return ""
        self.pbs_form_getters.append(("名单", get))

    def _pbs_form_phone(self, entry):
        box = self.pbs_form_box
        self._f_entry(box, "段名", entry.sid, width=34,
                      desc="Default = 所有训练家通用的来电；"
                           "也可以写「训练家类型,名字,版本」给某个训练家专属")
        msgs = entry.data.get("msgs", {})
        if isinstance(msgs, dict):
            for k, lst in msgs.items():
                self._f_text(box, k + "（一行一条）", "\n".join(lst),
                             height=max(2, len(lst)),
                             desc=pbs_edit.field_desc(k))
        else:
            self._f_text(box, "消息（一行一条）", "\n".join(msgs), height=14)
        self._desc(box, "台词里的转义：\\PN 玩家名、\\TN 训练家名、"
                        "\\TP 玩家首发宝可梦、\\TE 对手宝可梦、\\m 换行")

    # ---- 应用 / 保存 / 编译 ----
    def _pbs_apply_form(self):
        """把表单里的内容写回内存里的条目。"""
        doc = getattr(self, "pbs_doc", None)
        if doc is None or not self.pbs_form_getters:
            return
        idx = getattr(self, "pbs_cur_idx", None)
        if idx is None or idx >= len(doc.entries):
            return
        entry = doc.entries[idx]
        for label, getter in self.pbs_form_getters:
            try:
                val = getter()
            except Exception:
                continue
            if val is None:
                continue
            if label == "段名" or label == "键名" or label == "图鉴编号" \
                    or label == "区域编号":
                entry.sid = val
            elif label == "段名（类型,名字,版本）":
                entry.sid = val
            elif label == "地图":
                entry.data["map"] = val
            elif label == "版本":
                entry.data["version"] = val
            elif label == "地图写入":
                pass
            elif label == "地点" or label == "名单":
                pass                     # 回调内部已经写进 data
            elif label.startswith("遭遇"):
                tname, chance = val
                for i, blk in enumerate(entry.data.get("types", [])):
                    if i == int(label[2:]) if label[2:].isdigit() else False:
                        blk[0] = tname
                        blk[1] = chance
                        break
            elif label.startswith("队伍"):
                pass                     # 回调内部已经写进 data
            else:
                entry.set(label, val)
        doc.dirty = True

    def _pbs_save_doc(self):
        self._pbs_apply_form()
        doc = getattr(self, "pbs_doc", None)
        if doc is None:
            return
        try:
            doc.save()
            self.status_var.set("已保存 %s" % os.path.basename(doc.path))
            if log:
                log.info("PBS 保存：%s", doc.path)
        except Exception as e:                                  # noqa: BLE001
            messagebox.showerror("保存失败", str(e))

    def _pbs_compile_current(self):
        self._pbs_apply_form()
        doc = getattr(self, "pbs_doc", None)
        if doc is None:
            return
        try:
            doc.save()
        except Exception as e:                                  # noqa: BLE001
            messagebox.showerror("保存失败", str(e))
            return
        root = self.pbs_panel.root_dir if getattr(self, "pbs_panel", None) \
            else config.Runtime.game_root
        fam = doc.family
        if pbs_edit.is_legacy(fam):
            # 老版本：只标记，让游戏自己编译（避免写坏 .dat）
            import pbs_legacy
            n, msg = pbs_legacy.mark_for_recompile(root, fam)
            self.status_var.set("已标记待重编译")
            messagebox.showinfo(
                "已标记（%s 老版本）" % fam,
                "txt 已保存。\n\n" + msg + "\n\n"
                "（v16/v17/v18 的 .dat 由官方编译器在游戏启动时一次性重建，"
                "这样不会出现「一半新一半旧」）")
            return
        if not doc.spec:
            messagebox.showinfo("提示", "这个文件没有对应的 .dat，不用编译。")
            return
        ok, msg, stat = pbs_edit.compile_spec(doc.spec, fam, root)
        if ok:
            self.status_var.set("已编译 %s（%s）" % (doc.name, stat))
            messagebox.showinfo("编译完成",
                                "%s 已写回游戏的 Data（%s）" % (doc.name, stat))
        else:
            messagebox.showerror("编译失败", msg or "未知错误")

    # ---- 条目的增删改 ----
    def _pbs_add_entry(self):
        doc = getattr(self, "pbs_doc", None)
        if doc is None:
            return
        self._pbs_apply_form()
        sid = _AskText.ask(self.root, "新增条目",
                           "新的段名（内部名 / 编号）：", "NEWSPECIES")
        if not sid:
            return
        e = pbs_edit.DocEntry(sid)
        if doc.spec:
            for key, _i, _c, _e in pbs_edit.schema_of(doc.spec, doc.family):
                e.fields.append([key, ""])
        doc.entries.append(e)
        self._pbs_clear_search_quiet()
        self._pbs_refresh_entries(keep_sel=len(doc.entries) - 1)

    def _pbs_dup_entry(self):
        doc = getattr(self, "pbs_doc", None)
        if doc is None:
            return
        idx = getattr(self, "pbs_cur_idx", None)
        if idx is None or idx >= len(doc.entries):
            return
        self._pbs_apply_form()
        src = doc.entries[idx]
        new = pbs_edit.DocEntry(src.sid + "_COPY")
        new.fields = [list(x) for x in src.fields]
        new.data = {}
        for k, v in src.data.items():
            if isinstance(v, list):
                new.data[k] = [list(x) if isinstance(x, (list, tuple))
                               else x for x in v]
            else:
                new.data[k] = v
        doc.entries.insert(idx + 1, new)
        self._pbs_clear_search_quiet()
        self._pbs_refresh_entries(keep_sel=idx + 1)

    def _pbs_del_entry(self):
        doc = getattr(self, "pbs_doc", None)
        if doc is None:
            return
        idx = getattr(self, "pbs_cur_idx", None)
        if idx is None or idx >= len(doc.entries):
            return
        name = doc.entries[idx].label()
        if not messagebox.askyesno("删除", "确定删掉「%s」吗？" % name):
            return
        doc.entries.pop(idx)
        self._pbs_clear_search_quiet()
        self._pbs_refresh_entries(keep_sel=min(idx, len(doc.entries) - 1)
                                  if doc.entries else None)

    def _do_debug_restore(self):
        d = self._dbg_folder_data()
        if not d:
            return
        self.show("log")

        def work():
            import debug_tool as DT
            res = DT.restore(d, emit=lambda s: self._emit_log(s))
            self.q.put(("dbg_restore_done", res))
            return res

        self.run_async(work, label="还原中…", done_label="还原完成")

    def _do_unpack_plugins(self):
        """把 Data/PluginScripts.rxdata 解包成松散 .rb → <游戏目录>/Plugins-p。"""
        d = self._dbg_folder_data()
        if not d:
            return
        self.show("log")
        out = os.path.join(d, "Plugins-p")

        def work():
            import game_scripts as GS
            res = GS.unpack_plugin_scripts(d, out, emit=self._emit_log)
            self.q.put(("dbg_unpack_done", res))
            return res

        self.run_async(work, label="插件解包中…", done_label="插件解包完成")

    def _do_compile_back(self):
        """把 Plugins-p 里改过的 .rb 就地写回 Data/PluginScripts.rxdata。"""
        d = self._dbg_folder_data()
        if not d:
            return
        self.show("log")
        src = os.path.join(d, "Plugins-p")

        def work():
            import game_scripts as GS
            res = GS.compile_back_plugin_scripts(d, src, emit=self._emit_log)
            self.q.put(("dbg_compile_done", res))
            return res

        self.run_async(work, label="编译回容器中…", done_label="编译回容器完成")

    def _emit_log(self, text):
        """把命令行的输出同步到日志页。"""
        self.q.put(("log", f"{text}\n"))

    # ================================================================
    # 页面 12：日志
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
    # 存档编辑（菜单 6）
    #   一个入口页 + 5 个编辑子页面；右侧统一是「选择游戏存档」侧边栏。
    #   全局共用一份 SaveFile（self.save_obj），改完点「保存到存档」写回。
    # ================================================================
    # ================================================================
    # 存档编辑：校验 / 差异 / 提示条 / 快捷键 的公共部件
    #   ★ 内核（save_tools）里的 validate / warnings / diff_against_disk /
    #     encoding_report 是后加的，可能还没落地：**一律 getattr 判空**，
    #     拿不到就跳过对应功能，绝不因此抛 AttributeError。
    # ================================================================
    def _save_call(self, sv, name, default=None):
        """安全调用内核的新方法：不存在 / 抛异常都退回 default。"""
        fn = getattr(sv, name, None)
        if not callable(fn):
            return default
        try:
            return fn()
        except Exception as e:                                  # noqa: BLE001
            if log:
                log.warning("存档接口 %s 调用失败：%s", name, e)
            return default

    def _save_issues_of(self, sv):
        """sv.validate()（写回前校验）；拿不到返回 None 表示「这项没法做」。"""
        if sv is None:
            return None
        items = self._save_call(sv, "validate", default=None)
        return items if isinstance(items, list) else None

    def _save_warnings_of(self, sv):
        """sv.warnings（读取阶段的问题）；属性不存在返回 None。"""
        if sv is None:
            return None
        items = getattr(sv, "warnings", None)
        return items if isinstance(items, list) else None

    def _save_diff_of(self, sv):
        if sv is None:
            return None
        items = self._save_call(sv, "diff_against_disk", default=None)
        return items if isinstance(items, list) else None

    def _save_roundtrip(self, sv):
        """roundtrip_ok()；拿不到返回 None（=未知，不硬下结论）。"""
        if sv is None:
            return None
        fn = getattr(sv, "roundtrip_ok", None)
        if not callable(fn):
            return None
        try:
            return bool(fn())
        except Exception:                                        # noqa: BLE001
            return None

    def _save_encoding_report(self, sv):
        rep = self._save_call(sv, "encoding_report", default=None)
        return rep if isinstance(rep, dict) else None

    # ---------------- 页面顶部「读取提示」条 ----------------
    def _make_save_bar(self, parent, key, pady=(0, 8)):
        """在页面顶部预留一条提示位（没内容时高度为 0，不造成布局跳动）。"""
        bar = tk.Frame(parent, bg=BG_BASE)
        bar.pack(fill="x", pady=pady)
        self._save_bars[key] = bar
        return bar

    def _render_save_bar(self, key):
        """按当前存档重画提示条：有读取问题 / 编码提示才显示，否则收成 0 高。"""
        bar = self._save_bars.get(key)
        if bar is None:
            return
        try:
            if not bar.winfo_exists():
                return
        except Exception:
            return
        for w in bar.winfo_children():
            w.destroy()
        sv = self.save_obj
        if sv is None:
            return
        items = self._save_warnings_of(sv) or []
        note = _save_encoding_note(self._save_encoding_report(sv))
        if not items and not note:
            return
        errs = [it for it in items
                if isinstance(it, dict) and str(it.get("等级")) == "错误"]
        color = ERR_COLOR if errs else WARN_COLOR
        inner = tk.Frame(bar, bg=CARD_ALT, highlightthickness=1,
                         highlightbackground=color)
        inner.pack(fill="x")
        head = tk.Frame(inner, bg=CARD_ALT)
        head.pack(fill="x", padx=10, pady=(6, 2))
        title = "⚠ 存档读取提示"
        if items:
            title += f"（{len(items)}）"
            if errs:
                title += f"　其中错误 {len(errs)} 条"
        lbl = tk.Label(head, text=title, bg=CARD_ALT, fg=color, font=FONT_B,
                       anchor="w", justify="left")
        lbl.pack(side="left")
        if items:
            GlassButton(head, "查看详情", width=96, height=30, bg=CARD_ALT,
                        font=FONT_SMALL,
                        command=lambda its=list(items), nt=note:
                        SaveIssuesDialog(self, "存档读取提示", its,
                                         allow_write=False,
                                         encoding_note=nt)
                        ).pack(side="right")
        if note:
            nl = tk.Label(inner, text=note, bg=CARD_ALT, fg=C_HINT,
                          font=FONT_SMALL, anchor="w", justify="left")
            nl.pack(fill="x", padx=10, pady=(0, 6))
            bind_autowrap(nl, pad=12, minimum=160)

    def _refresh_save_bars(self):
        for key in list(self._save_bars):
            self._render_save_bar(key)

    # ---------------- 校验标红 ----------------
    def _iter_widgets(self, root):
        """递归遍历控件树（找输入框用）。"""
        stack = [root]
        while stack:
            w = stack.pop()
            yield w
            try:
                stack.extend(w.winfo_children())
            except Exception:
                continue

    # 页面键 → 字段来源（标红时按「位置」限定来源，避免同名键跨页误标）
    _SAVE_PAGE_SOURCE = {"save_trainer": "tr", "save_party": "party",
                         "save_box": "box"}
    # 「位置」文案里的关键词 → 字段来源（内核的 validate 用中文短名指位置）
    _SAVE_SOURCE_WORDS = (("电脑", "box"), ("箱子", "box"),
                          ("队伍", "party"), ("主角", "tr"),
                          ("训练家", "tr"))

    def _save_form_of(self, source):
        if source == "party":
            return getattr(self, "party_form", None)
        if source == "box":
            return getattr(self, "box_form", None)
        return None

    def _save_var_field_map(self):
        """
        字段来源（tr / party / box）→ {StringVar 的 Tcl 名: 字段名}。

        ★ 必须按来源分开建表：party_form 与 box_form 是同一个 PokemonForm
          类，两边都有 "level" / "nick" 这类键，混成一张表会互相覆盖，
          结果是「电脑箱子里的等级坏了」把「队伍页的等级框」也标红。
        """
        mp = {"tr": {}, "party": {}, "box": {}}
        for key, var in (getattr(self, "tr_vars", None) or {}).items():
            mp["tr"][str(var)] = key
        for src in ("party", "box"):
            form = self._save_form_of(src)
            for key, var in (getattr(form, "vars", None) or {}).items():
                mp[src][str(var)] = key
        return mp

    def _save_entry_index(self):
        """字段来源 → {字段名（归一化）: 输入框列表} —— 校验标红的目标。"""
        vmaps = self._save_var_field_map()
        index = {"tr": {}, "party": {}, "box": {}}
        for page_key, left in list(self._save_left.items()):
            src = self._SAVE_PAGE_SOURCE.get(page_key)
            if not src:
                continue
            try:
                if not left.winfo_exists():
                    continue
            except Exception:
                continue
            vmap = vmaps.get(src) or {}
            for w in self._iter_widgets(left):
                if not isinstance(w, ttk.Entry):
                    continue
                try:
                    tcl = str(w.cget("textvariable"))
                except Exception:
                    continue
                fname = vmap.get(tcl)
                if not fname:
                    continue
                index[src].setdefault(_save_norm_field(fname), []).append(w)
        return index

    def _save_source_hint(self, where):
        """从「位置」文案猜这条问题属于哪一块（tr / party / box）；猜不出返回空串。"""
        text = str(where or "")
        for word, src in self._SAVE_SOURCE_WORDS:
            if word in text:
                return src
        return ""

    def _clear_save_highlights(self):
        """把标红的输入框恢复原样（改回原来的 style）。"""
        for w, style in self._save_highlights:
            try:
                if w.winfo_exists():
                    w.configure(style=style)
            except Exception:
                pass
        self._save_highlights = []

    def _highlight_save_issues(self, issues):
        """
        把「错误」级的字段输入框底色标红；认不出的字段安静跳过。

        ★ 命中范围要按「位置」限定来源：party_form 与 box_form 都有 level
          键，不限来源的话箱子里的等级坏了会把队伍页的等级框一起标红。
        """
        self._clear_save_highlights()
        bad = [it for it in (issues or [])
               if isinstance(it, dict) and str(it.get("等级")) == "错误"]
        if not bad:
            return 0
        index = self._save_entry_index()
        if not any(index.values()):
            return 0
        hit = 0
        for it in bad:
            want = _save_norm_field(it.get("字段"))
            where = _save_norm_field(it.get("位置"))
            # 位置能定位到哪一块就只标那一块；定位不到才退化成全表匹配
            src = self._save_source_hint(it.get("位置"))
            scopes = [src] if src else [s for s in ("tr", "party", "box")]
            # ★ 内核给了「字段键」（稳定英文键：money / level / iv0 / box_name…）
            #   就直接用它精确匹配，一次到位；只有旧版内核没有这个键时，才退回
            #   中文别名表（SAVE_FIELD_ALIASES 只兜旧版内核，别指望它覆盖新项）
            fkey = _save_norm_field(it.get("字段键"))
            # ★ 旧版内核给的是中文名（金钱 / 等级 / 个体值），表单变量是英文键，
            #   先过一遍别名表；位置里也可能写成 "存档.player.@money" 这种
            keys = set() if fkey else _save_highlight_keys(
                it.get("字段"), it.get("位置"))
            for scope in scopes:
                for fname, widgets in (index.get(scope) or {}).items():
                    if not fname:
                        continue
                    if fkey:
                        matched = (fname == fkey)
                    else:
                        # ★ 字段可能是 "@party[0]/@exp" 这种路径：字段名或位置里
                        #   出现表单字段名就认为命中，命不中就当没这回事
                        matched = (fname in keys or fname == want
                                   or fname in want or fname in where)
                    if not matched:
                        continue
                    for w in widgets:
                        if any(w is h[0] for h in self._save_highlights):
                            continue
                        try:
                            old = w.cget("style")
                        except Exception:
                            continue
                        try:
                            w.configure(style="SaveErr.TEntry")
                        except Exception:
                            continue
                        self._save_highlights.append((w, old))
                        hit += 1
        return hit

    # ---------------- 页面顶部常驻状态文字 ----------------
    _SAVE_TOOL_ATTR = {"save_trainer": "tr_tool", "save_party": "party_tool",
                       "save_bag": "bag_tool", "save_box": "box_tool",
                       "save_switch": "sw_tool"}

    def _set_save_status(self, key, text, level="info"):
        """在编辑页顶部那行常驻状态文字里写一句话（成功绿 / 失败红 / 普通灰）。"""
        if key is None:
            key = self.current
        attr = self._SAVE_TOOL_ATTR.get(key)
        lbl = getattr(self, attr, None) if attr else None
        if lbl is None:
            try:
                if self.status_var is not None:
                    self.status_var.set(text)
            except Exception:
                pass
            return
        color = {"ok": OK_COLOR, "err": ERR_COLOR}.get(level, C_HINT)
        try:
            lbl.config(text=text, fg=color)
        except Exception:
            pass

    # ---------------- 快捷键（只在该页面可见时生效） ----------------
    def _bind_save_hotkeys(self):
        """
        Ctrl+S 保存到存档 / F5 重新载入当前页 / Ctrl+F 聚焦搜索框。

        ★ 绑定挂在 root 上、靠 self.current 判断当前页 —— 不要 bind_all，
          也不要无条件响应：否则在别的菜单页也会抢键（Ctrl+S 本来该无操作）。
        """
        def _bind(seq, fn):
            try:
                self.root.bind(seq, fn, add="+")
            except Exception:
                pass
        for seq in ("<Control-s>", "<Control-S>"):
            _bind(seq, self._hotkey_save)
        _bind("<F5>", self._hotkey_reload)
        for seq in ("<Control-f>", "<Control-F>"):
            _bind(seq, self._hotkey_search)

    def _hotkey_save(self, _e=None):
        if self.current in SAVE_SUBMENUS_KEYS or self.current == "saveedit":
            self.write_save()
            return "break"
        return None

    def _hotkey_reload(self, _e=None):
        if self.current in SAVE_SUBMENUS_KEYS:
            self._refresh_save_page(self.current)
            self._set_save_status(self.current, "已重新载入当前页。", "info")
            return "break"
        if self.current == "saveedit":
            self._refresh_save_overview()
            return "break"
        return None

    def _hotkey_search(self, _e=None):
        ent = self._save_search.get(self.current)
        if ent is None:
            return None
        try:
            if not ent[1].winfo_exists():
                return None
            ent[1].focus_set()
            ent[1].select_range(0, "end")
        except Exception:
            return None
        return "break"

    def current_save(self):
        return self.save_obj

    def select_save(self, path, force=False, root=None):
        """选中一份存档（各页面共用同一个内存对象）。"""
        try:
            sv = ST.open_save(path, game_root=root or None, force=force)
        except Exception as e:
            messagebox.showerror("打开存档失败", f"{path}\n\n{e}")
            return
        self.save_path = path
        self.save_obj = sv
        self.save_dirty = False
        self._clear_save_highlights()   # ★ 换存档就清掉上一份的标红
        for p in list(self.save_panels):
            try:
                if p.winfo_exists():
                    p.sync_selection(path)
                    p.set_info(sv, self.save_dirty)
            except Exception:
                pass
        self._refresh_save_bars()       # 读取提示条跟着换
        self._reload_save_views()
        try:
            self.status_var.set(
                f"已选择存档：{os.path.basename(path)}"
                f"（{len(sv.objects)} 个数据块，名称来源 {sv.data.source}）")
        except Exception:
            pass

    def mark_dirty(self):
        self.save_dirty = True
        for p in list(self.save_panels):
            try:
                p.set_dirty(True)
            except Exception:
                pass

    def write_save(self, skip_check=False):
        """
        保存到存档：先做字段级校验 + 差异预览，再走确认。

        ★ 顺序不能反：校验（validate）发现「错误」级问题时优先拦下来，让
          用户回对应页面改；差异预览里的 roundtrip 结论则在写之前就摆出来。
        ★ 内核那几个方法可能还没落地（getattr 判空），拿不到就退回原来的
          纯 messagebox 确认流程，行为不变。
        """
        sv = self.save_obj
        if sv is None:
            messagebox.showinfo("还没有选择存档", "先在右侧选一份游戏存档。")
            self._set_save_status(None, "还没有选择存档。", "err")
            return
        if not skip_check:
            issues = self._save_issues_of(sv) or []
            errs = [it for it in issues
                    if isinstance(it, dict) and str(it.get("等级")) == "错误"]
            # 标红只针对「错误」级（函数内部自己筛），警告级不动输入框
            hit = self._highlight_save_issues(issues) if errs else 0
            if errs:
                # ★ 只有「错误」级才拦下来问用户：真实存档的 validate() 里
                #   通常只有「警告」（没选游戏根目录之类），那些留在顶部
                #   常驻提示条就够，每存一次都弹窗纯属添堵。
                note = _save_encoding_note(self._save_encoding_report(sv))
                dlg = SaveIssuesDialog(
                    self, "写入前校验发现问题", issues,
                    allow_write=True, encoding_note=note)
                # ★ App 不是控件（self.root 才是窗口），等弹窗得走 root
                self.root.wait_window(dlg)
                if dlg.result != "write":
                    # 返回修改：标红留着，等用户改完再点保存
                    self._set_save_status(
                        None,
                        (f"校验未通过：{len(errs)} 条错误、"
                         f"{len(issues) - len(errs)} 条警告，已取消写入。"),
                        "err")
                    return
                if hit:
                    self._set_save_status(
                        None, f"仍有 {len(errs)} 条错误，按用户选择继续写入。",
                        "err")
            else:
                self._clear_save_highlights()
        changes = self._save_diff_of(sv)
        roundtrip = self._save_roundtrip(sv)
        if changes is not None or roundtrip is not None:
            dlg = SaveWriteDialog(self, sv, changes or [], roundtrip)
            self.root.wait_window(dlg)
            if not dlg.result:
                self._set_save_status(None, "已取消写入。", "info")
                return
        else:
            # 降级：内核没有 diff/roundtrip，沿用原来的确认框
            bak = sv.path + ".bak"
            tip = "" if os.path.exists(bak) else \
                f"\n\n（第一次保存会先生成备份 {os.path.basename(bak)}）"
            if not messagebox.askyesno(
                    "保存到存档",
                    f"写入这个文件：\n{sv.path}{tip}\n\n要在游戏里看到效果，"
                    "需要回游戏重新「读档」（继续游戏不会重读）。确定写入吗？"):
                return
        try:
            sv.write()
        except Exception as e:
            messagebox.showerror("写入失败", f"{e}")
            self._set_save_status(None, f"写入失败：{e}", "err")
            return
        self.save_dirty = False
        self._clear_save_highlights()
        for p in list(self.save_panels):
            try:
                p.set_info(sv, False)
            except Exception:
                pass
        self._refresh_save_bars()
        self._set_save_status(
            None, f"已写入 {os.path.basename(sv.path)}（回游戏重新读档才生效）。",
            "ok")
        messagebox.showinfo("已保存", f"已写入 {os.path.basename(sv.path)}。")

    def _reload_save_views(self):
        if self.current == "saveedit":
            self._refresh_save_overview()
        elif self.current in SAVE_SUBMENUS_KEYS:
            self._refresh_save_page(self.current)

    def refresh_save_lists(self):
        """改完数据后刷新当前页（列表 + 表单都按新值重读，选中行保持）。"""
        if self.current == "save_party":
            self._refresh_save_party()
        elif self.current == "save_box":
            self._refresh_save_box()
        elif self.current == "save_bag":
            self._refresh_save_bag()
        elif self.current == "save_trainer":
            self._refresh_save_trainer()
        elif self.current == "save_switch":
            self._refresh_save_switch()

    def _refresh_save_page(self, key, force=False):
        """切到/刷新某个编辑子页面。"""
        fn = getattr(self, f"_refresh_{key}", None)
        if fn:
            try:
                fn()
            except Exception as e:
                messagebox.showerror("读取存档失败", f"{e}")

    # ---------- 页面骨架 ----------
    def _save_page_shell(self, key, panel_width=340):
        """「内容 + 右侧存档侧边栏」的页面骨架。"""
        page = self.pages[key]
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=0)
        page.grid_rowconfigure(0, weight=1)
        left = tk.Frame(page, bg=BG_BASE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        holder = tk.Frame(page, bg=BG_BASE, width=panel_width)
        holder.grid(row=0, column=1, sticky="nsew")
        holder.pack_propagate(False)
        card = RoundCard(holder, radius=16, pad=12, scrollable=True)
        card.pack(fill="both", expand=True)
        panel = SavePanel(card.body, bg=CARD, app=self)
        panel.pack(fill="both", expand=True)
        self.save_panels.append(panel)
        # 记住左半区：字段级校验标红时要在里面按字段名找回输入框
        self._save_left[key] = left
        return left, panel

    def _save_toolbar(self, parent, key):
        """编辑页顶部：读取提示条 / 重新载入 / 保存 + 常驻状态文字。"""
        # ★ 提示条先 pack，才会落在工具条上方；没内容时它自己保持 0 高，
        #   不会把下面的内容顶下去（避免切换存档时布局跳动）
        self._make_save_bar(parent, key)
        row = tk.Frame(parent, bg=BG_BASE)
        row.pack(fill="x", pady=(0, 8))
        GlassButton(row, "重新载入", width=104, height=38, bg=BG_BASE,
                    font=FONT_SMALL,
                    command=lambda k=key: self._refresh_save_page(k)).pack(
            side="left")
        GlassButton(row, "保存到存档", width=124, height=38, primary=True,
                    bg=BG_BASE, font=FONT_B,
                    command=self.write_save).pack(side="left", padx=6)
        lbl = tk.Label(row, text="", bg=BG_BASE, fg=C_HINT, font=FONT_SMALL,
                       anchor="w", justify="left")
        lbl.pack(side="left", padx=10)
        # ★ 右上角再给一个返回入口（左上角的返回条离得远，容易找不到）
        GlassButton(row, "返回存档编辑", width=136, height=38, bg=BG_BASE,
                    font=FONT_SMALL,
                    command=lambda: self.show("saveedit")).pack(side="right")
        return lbl


    def _make_tree(self, parent, columns, widths=None, height=12,
                   stretch_all=False):
        """带滚动条的表格。columns = [(键, 标题), ...]

        stretch_all=True：所有列都参与伸缩。左侧卡片宽度是固定的，
        只让一列 stretch 的话，卡片一窄下来这一列会被压到只剩几个像素
        （踩过：队伍树「昵称」列被压成 20px、HP 列整列消失）。

        ★ 斑马纹 / 数字列右对齐 / 列宽自适应都在 _tree_reload 里按**实际
          数据**决定（建表时还没有数据，量不出来），这里只把初始宽度记下来
          当「最小宽度地板」，避免自适应把列压得比设计值还窄。
        """
        holder = tk.Frame(parent, bg=CARD)
        tree = ttk.Treeview(holder, columns=[c[0] for c in columns],
                            show="headings", height=height)
        for i, (ck, title) in enumerate(columns):
            tree.heading(ck, text=title)
            tree.column(ck, width=(widths[i] if widths else 90), anchor="w",
                        stretch=True if stretch_all else (i == 1))
        # ★ 斑马纹：用 tag 上色，交替行底色区分；选中行由 ttk 的 map 覆盖
        try:
            tree.tag_configure("row_odd", background="#FFFFFF")
            tree.tag_configure("row_even", background=CARD_ALT)
        except Exception:
            pass
        tree._col_floors = list(widths) if widths else None
        sb = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        bind_tree_wheel(tree)
        try:
            attach_tree_copy(tree, app=self)
        except Exception:
            pass
        return holder, tree

    @staticmethod
    def _tree_fit_columns(tree, values_rows):
        """数字列右对齐 + 列宽按内容撑开（不超过地板值 2.4 倍）。"""
        cols = list(tree["columns"])
        if not cols:
            return
        floors = getattr(tree, "_col_floors", None) or [90] * len(cols)
        kinds = _save_tree_col_kinds(values_rows, len(cols))
        try:
            import tkinter.font as tkfont
            fnt = tkfont.Font(font=tree.cget("font") or FONT)
            measure = fnt.measure
        except Exception:                                        # noqa: BLE001
            measure = lambda s: len(str(s)) * 9                  # noqa: E731
        for i, ck in enumerate(cols):
            anchor = "e" if kinds[i] else "w"
            try:
                tree.heading(ck, anchor=anchor)
                tree.column(ck, anchor=anchor)
            except Exception:
                pass
            widest = 0
            for row in values_rows:
                if i < len(row):
                    widest = max(widest, measure(str(row[i])))
            floor = floors[i] if i < len(floors) else 90
            want = max(floor, min(int(widest) + 22, int(floor * 2.4)))
            try:
                tree.column(ck, width=want, minwidth=min(floor, 90))
            except Exception:
                pass

    # ================================================================
    # 搜索过滤（队伍 / 箱子 / 背包）
    # ================================================================
    def _save_search_row(self, parent, key, on_change):
        """
        搜索过滤输入框（按名字 / ID / 位置实时过滤，清空恢复）。

        ★ 变量记进 self._save_search：Ctrl+F 靠它找到当前页的搜索框。
        """
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=(0, 6))
        tk.Label(row, text="搜索", bg=CARD, fg=C_HINT, font=FONT_SMALL,
                 anchor="w").pack(side="left")
        var = tk.StringVar(value="")
        ent = ttk.Entry(row, textvariable=var, width=12, font=FONT_SMALL)
        ent.pack(side="left", fill="x", expand=True, padx=(6, 6))
        var.trace_add("write", lambda *_a: on_change())
        self._save_search[key] = (var, ent)
        GlassButton(row, "清空", width=64, height=28, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda v=var: v.set("")).pack(side="left")
        return var

    def _save_filter_keyword(self, key):
        ent = self._save_search.get(key)
        return ent[0].get() if ent else ""

    @staticmethod
    def _tree_reload(tree, rows):
        """
        重填表格并**保住原来的选中行**。

        rows = [(iid, values), ...]；重填会清掉选中状态，不保的话
        「改一次值就要重新点一遍」。

        ★ 顺带做两件「按数据决定」的排版：奇偶行斑马纹、纯数字列右对齐，
          再按内容把列宽顶到够用（不超过地板值的 2.4 倍，长昵称不会把
          旁边的列挤没）。
        """
        rows = list(rows or [])
        wanted = list(tree.selection())
        tree.delete(*tree.get_children())
        for i, (iid, values) in enumerate(rows):
            tree.insert("", "end", iid=str(iid), values=values,
                        tags=("row_even" if i % 2 else "row_odd",))
        have = set(tree.get_children())
        keep = [i for i in wanted if i in have]
        if keep:
            tree.selection_set(keep)
            try:
                tree.see(keep[0])
            except Exception:
                pass
        App._tree_fit_columns(tree, [v for _i, v in rows])

    # ================================================================
    # 入口页：中间列编辑选项，右侧选存档
    # ================================================================
    def _page_saveedit(self):
        left, panel = self._save_page_shell("saveedit")

        # ★ 入口页也要有读取提示条：用户是在这一页选存档的，读取出问题时
        #   第一个看到的就是这里（子页面各有自己的条，靠页面键分开记）
        self._make_save_bar(left, "saveedit")

        outer, inner = make_scroll_area(left, bg=BG_BASE)
        outer.pack(fill="both", expand=True)

        card = RoundCard(inner, radius=18, pad=18, auto_height=True)
        card.pack(fill="x")
        body = card.body
        tk.Label(body, text="存档编辑", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        # ★ 说明文字 fill="x" + wraplength 跟实际宽度走：固定 620 在窄窗里
        #   会被卡片右边缘裁掉一截
        hint1 = tk.Label(body,
                         text="右侧先选好游戏目录与存档，再从下面点进要改的部分。"
                              "所有修改都先放在内存里，改完点右侧「保存到存档」才写进文件"
                              "（第一次保存会自动生成 .bak 备份）。",
                         bg=CARD, fg=C_HINT, font=FONT_SMALL, justify="left",
                         wraplength=620)
        hint1.pack(fill="x", pady=(4, 10))
        bind_autowrap(hint1, pad=4)

        grid = tk.Frame(body, bg=CARD)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)
        for i, (key, name, desc) in enumerate(SAVE_SUBMENUS):
            GlassButton(grid, f"{i + 1}. {name}", width=210, height=46,
                        primary=(i == 0), bg=CARD, font=FONT_B,
                        command=lambda k=key: self.show(k)).grid(
                row=i, column=0, sticky="w", pady=5)
            tk.Label(grid, text=desc, bg=CARD, fg=C_HINT, font=FONT_SMALL,
                     justify="left", wraplength=430).grid(
                row=i, column=1, sticky="w", padx=(14, 0))

        hint2 = tk.Label(body,
                         text="★ 数据来源：优先读游戏 Data 目录里的 .dat，"
                              "读不到才退回 PBS。宝可梦／道具／招式名按游戏的语言包显示。",
                         bg=CARD, fg=C_WARN, font=FONT_SMALL, justify="left",
                         wraplength=620)
        hint2.pack(fill="x", pady=(12, 0))
        bind_autowrap(hint2, pad=4)

        # 概览卡（跟着选中的存档变）
        self.overview_card = RoundCard(inner, radius=18, pad=18,
                                       auto_height=True)
        self.overview_card.pack(fill="x", pady=(10, 0))
        self.overview_body = tk.Frame(self.overview_card.body, bg=CARD)
        self.overview_body.pack(fill="x")
        self._refresh_save_overview()

    def _refresh_save_overview(self):
        body = getattr(self, "overview_body", None)
        if body is None:
            return
        for w in body.winfo_children():
            w.destroy()
        sv = self.save_obj
        tk.Label(body, text="当前存档概览", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        if sv is None:
            tk.Label(body, text="（右侧选中存档后这里会显示概览）", bg=CARD,
                     fg=C_HINT, font=FONT_SMALL).pack(anchor="w", pady=(4, 0))
            self._fit_overview_card()
            return
        tr = sv.g("$Trainer").ivars
        party = [p for p in (tr.get("@party") or []) if not sv.empty_slot(p)]
        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x", pady=(4, 2))
        tk.Label(head, text=os.path.basename(sv.path), bg=CARD, fg=C_KEY,
                 font=FONT_BIG).pack(side="left")
        tk.Label(head, text=f"    游戏目录：{os.path.basename(sv.game_root)}"
                            f"    名称来源：{sv.data.source}"
                            f"    语言包：{sv.data.lang_dat or '（无）'}",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL).pack(side="left")
        badges = sum(1 for b in (tr.get("@badges") or []) if b)
        # ★ 徽章数不一定是 8（有些作品更多），按实际长度显示
        badges_all = len(tr.get("@badges") or [])
        bag = sv.g("$PokemonBag").ivars.get("@pockets") or []
        # 用 pocket_entries() 统计，Hash 式口袋也算得进去
        items = sum(len(sv.pocket_entries(i)) for i in range(len(bag)))
        boxes = list(sv.boxes())
        in_box = sum(len([p for p in (b.ivars.get("@pokemon") or [])
                          if not sv.empty_slot(p)]) for b in boxes)
        lines = [
            f"主角：{sfmt(tr.get('@name'))}（ID {sfmt(tr.get('@id'))}）    "
            f"金钱 {sfmt(tr.get('@money'))}    徽章 {badges}/{badges_all}",
            f"同行宝可梦：{len(party)} 只    PC 箱子：{in_box} 只 / {len(boxes)} 箱    "
            f"背包：{items} 种道具",
            f"开关 {len(sv.switch_peek())} 个    变量 {len(sv.variable_peek())} 个    "
            f"图鉴已捕获 {sum(1 for x in sv.dex_flags('owned') if x)} / "
            f"已见 {sum(1 for x in sv.dex_flags('seen') if x)}",
            self._save_format_line(sv),
        ]
        for ln in lines:
            tk.Label(body, text=ln, bg=CARD, fg=TEXT_DIM, font=FONT_SMALL,
                     anchor="w").pack(anchor="w")
        self._fit_overview_card()

    def _save_format_line(self, sv):
        """
        概览里那行「格式 / 外层封装 / 编码标记健康度」摘要。

        ★ 读不到的东西一律降级成「—」：encoding_report 现在还只是契约里
          的名字，内核没落地时这行也要能正常显示。
        """
        fmts = {"hash": "hash（单流）", "legacy": "legacy（多流 / 15 流）"}
        try:
            raw_fmt = getattr(sv, "fmt", None)
            fmt = fmts.get(str(raw_fmt), str(raw_fmt or "未知"))
        except Exception:                                        # noqa: BLE001
            fmt = "未知"
        try:
            # ★ encoding_label 是 @property，取属性而不是调用；没有封装时是
            #   空串，这里补一句「无（明文）」免得概览上留个空档
            enc = sv.encoding_label or "无（明文）"
        except Exception:                                        # noqa: BLE001
            enc = "—"
        health = ""
        rep = self._save_encoding_report(sv)
        if rep:
            health = _save_encoding_health(rep)
        return (f"格式：{fmt}    外层封装：{enc}"
                + (f"    编码标记健康度：{health}" if health else ""))

    def _fit_overview_card(self):
        """概览卡高度兜底。

        auto_height 靠 body 的 <Configure> 驱动（_body_resize）。body 因故
        没被 map 过时这条链一次都不触发，卡片会保持 RoundCard 默认的 10px
        请求高度 → 整张卡看不见。这里按 body 的请求高度补一次（与
        _body_resize 同公式），正常链生效时值相同、不会打架。
        """
        card = getattr(self, "overview_card", None)
        body = getattr(self, "overview_body", None)
        if card is None or body is None:
            return
        try:
            card.configure(height=body.winfo_reqheight() + card.pad * 2 + 8)
        except Exception:
            pass

    # ================================================================
    # 子页面 1：主角编辑
    # ================================================================
    def _page_save_trainer(self):
        left, panel = self._save_page_shell("save_trainer")
        self.tr_tool = self._save_toolbar(left, "save_trainer")

        outer, inner = make_scroll_area(left, bg=BG_BASE)
        outer.pack(fill="both", expand=True)
        card = RoundCard(inner, radius=18, pad=18, auto_height=True)
        card.pack(fill="x")
        body = card.body
        tk.Label(body, text="主角编辑", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(body, text="这些是游戏通用字段（PokeBattle_Trainer）。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL).pack(anchor="w",
                                                           pady=(2, 8))

        self.tr_vars = {}
        for k, d in (("name", ""), ("money", ""), ("id", ""),
                     ("outfit", ""), ("language", "")):
            self.tr_vars[k] = tk.StringVar(value=d)

        r = tk.Frame(body, bg=CARD)
        r.pack(fill="x", pady=3)
        _lbl(r, "名字", width=10).pack(side="left")
        _entry(r, self.tr_vars["name"], 16).pack(side="left")
        _lbl(r, "金钱", width=8).pack(side="left", padx=(14, 0))
        _entry(r, self.tr_vars["money"], 12).pack(side="left")
        GlassButton(r, "金钱拉满", width=96, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self.tr_vars["money"].set("999999")
                    ).pack(side="left", padx=8)

        r = tk.Frame(body, bg=CARD)
        r.pack(fill="x", pady=3)
        _lbl(r, "训练家 ID", width=10).pack(side="left")
        _entry(r, self.tr_vars["id"], 12).pack(side="left")
        _lbl(r, "服装编号", width=8).pack(side="left", padx=(14, 0))
        _entry(r, self.tr_vars["outfit"], 8).pack(side="left")
        _lbl(r, "语种", width=8).pack(side="left", padx=(14, 0))
        _entry(r, self.tr_vars["language"], 8).pack(side="left")

        r = tk.Frame(body, bg=CARD)
        r.pack(fill="x", pady=3)
        ttcol = tk.Frame(r, bg=CARD)
        ttcol.pack(side="left")
        ttrow = tk.Frame(ttcol, bg=CARD)
        ttrow.pack(fill="x")
        _lbl(ttrow, "训练家类型", width=10).pack(side="left")
        # ★ 这里在 App 类里（不是宝可梦编辑器），用模块级工厂：
        #   _manual_resolver 是编辑器实例的方法，App 上没有，会 AttributeError。
        self.tr_type_combo = SearchCombo(ttrow, [], width=22,
                                         resolver=make_manual_resolver(
                                             lambda: self.save_obj,
                                             "trainer_type"))
        self.tr_type_combo.pack(side="left")
        # ★ 框下只读译文行：有游戏数据（如 pbs/trainertypes.txt）时按原始
        #   数据翻出来；没有就留空。框里显示的始终是存档原始数据。
        self.tr_type_trans = _hint(ttcol, "", fg=C_KEY)
        self.tr_type_trans.pack(fill="x")
        self.tr_dex_var = tk.BooleanVar(value=False)
        tk.Checkbutton(r, text="已获得图鉴", variable=self.tr_dex_var, bg=CARD,
                       activebackground=CARD, selectcolor="#FFFFFF",
                       font=FONT_SMALL, fg=TEXT).pack(side="left", padx=(14, 0))
        self.tr_dex_lbl = _hint(r, "")
        self.tr_dex_lbl.pack(side="left", padx=(8, 0))

        # 徽章
        tk.Label(body, text="徽章", bg=CARD, fg=C_TITLE,
                 font=FONT_B).pack(anchor="w", pady=(10, 2))
        self.tr_badges = []
        brow = tk.Frame(body, bg=CARD)
        brow.pack(fill="x")
        for i in range(8):
            v = tk.BooleanVar(value=False)
            self.tr_badges.append(v)
            tk.Checkbutton(brow, text=f"{i + 1}", variable=v, bg=CARD,
                           activebackground=CARD, selectcolor="#FFFFFF",
                           font=FONT_SMALL, fg=TEXT).pack(side="left",
                                                          padx=(0, 6))
        GlassButton(brow, "全给", width=76, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: [v.set(True) for v in self.tr_badges]
                    ).pack(side="left", padx=6)
        GlassButton(brow, "全清", width=76, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: [v.set(False) for v in self.tr_badges]
                    ).pack(side="left")

        # 图鉴 / 形态图鉴
        tk.Label(body, text="图鉴与形态图鉴", bg=CARD, fg=C_TITLE,
                 font=FONT_B).pack(anchor="w", pady=(12, 2))
        da = tk.Frame(body, bg=CARD)
        da.pack(fill="x", pady=2)
        # ★ 5 个按钮一行约 590px，比最小窗口（1240）下的卡片还宽，
        #   最后一个会被裁掉 —— 统一收窄按钮宽度留出余量
        GlassButton(da, "全部已见", width=96, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self._dex_all("seen", True)).pack(side="left")
        GlassButton(da, "清空已见", width=96, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self._dex_all("seen", False)).pack(
            side="left", padx=6)
        GlassButton(da, "全部已捕获", width=100, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self._dex_all("owned", True)).pack(side="left")
        GlassButton(da, "清空已捕获", width=100, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self._dex_all("owned", False)).pack(
            side="left", padx=6)
        GlassButton(da, "形态图鉴全开", width=108, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._dex_forms).pack(side="left")
        self.tr_dex_info = _hint(body, "")
        self.tr_dex_info.pack(fill="x", pady=(4, 0))
        bind_autowrap(self.tr_dex_info, pad=4)

        save_row = tk.Frame(body, bg=CARD)
        save_row.pack(fill="x", pady=(12, 0))
        GlassButton(save_row, "应用主角修改", width=148, height=40,
                    primary=True, bg=CARD, font=FONT_B,
                    command=self._apply_trainer).pack(side="left")
        tk.Label(save_row,
                 text="图鉴那四个按钮是立刻生效的；上方字段要再点这个按钮。",
                 bg=CARD, fg=C_HINT, font=FONT_SMALL).pack(side="left",
                                                           padx=(12, 0))

    def _dex_all(self, which, value):
        sv = self.save_obj
        if sv is None:
            return
        name = "已见" if which == "seen" else "已捕获"
        if not messagebox.askyesno(
                "图鉴", f"把图鉴的「{name}」{'全部勾上' if value else '全部清空'}吗？"):
            return
        sv.set_dex(which, None, value)
        self.mark_dirty()
        self._refresh_save_trainer()

    def _dex_forms(self):
        """形态图鉴全开（两种存档格式的细节都交给 save_tools）。"""
        sv = self.save_obj
        if sv is None:
            return
        n = sv.unlock_all_forms()
        if n:
            self.mark_dirty()
            messagebox.showinfo("形态图鉴", f"已把 {n} 条形态记录标记为已见。")
        else:
            messagebox.showinfo("形态图鉴",
                                "这份存档里没有形态图鉴字段（不同作品不一样），"
                                "跳过。")
        self._refresh_save_trainer()

    def _apply_trainer(self):
        sv = self.save_obj
        if sv is None:
            messagebox.showinfo("提示", "先在右侧选一份存档。")
            return
        # ★ 逐字段解析：**填错只警告、不阻止** —— 写得动的字段照常写入，
        #   写不动的（认不出 / 不是整数）收集起来，最后一次性提示。
        #   空字段 = 「这一项不修改」（避免清空输入框时误把金钱写成 0）。
        problems = []
        fields = {"name": self.tr_vars["name"].get(),
                  "pokedex": bool(self.tr_dex_var.get())}
        for key, label in (("money", "金钱"), ("id", "训练家 ID"),
                           ("outfit", "服装编号"), ("language", "语种")):
            txt = self.tr_vars[key].get().strip()
            if not txt:
                continue
            try:
                fields[key] = int(txt)
            except ValueError:
                problems.append(f"{label}要填整数（收到「{txt}」），该字段未修改")
        try:
            sv.set_trainer(**fields)
        except Exception as e:                                  # noqa: BLE001
            problems.append(f"通用字段写入失败：{e}")
        tt = self.tr_type_combo.value_or_text()
        # ★ 没选游戏数据时下拉是空的，别拿「当前编号」去写 ——
        #   那样只会写成一个错的类型；这时保持原样。
        if tt is not None and (self.tr_type_combo.pairs
                               or not isinstance(tt, int)):
            try:
                sv.set_trainer(trainertype=tt)
            except Exception as e:                              # noqa: BLE001
                problems.append(str(e))
        try:
            sv.set_trainer(badges=[v.get() for v in self.tr_badges])
        except Exception as e:                                  # noqa: BLE001
            problems.append(f"徽章写入失败：{e}")
        self.mark_dirty()
        self._refresh_save_trainer()
        if problems:
            messagebox.showwarning(
                "部分字段没写进去",
                "以下字段填写有误，已跳过（其他字段照常改好）：\n\n"
                + "\n".join(f"· {p}" for p in problems),
                parent=self)
            self._set_save_status(
                "save_trainer",
                f"有 {len(problems)} 个字段填错了，已跳过（其余已改好）。", "err")
        else:
            messagebox.showinfo("已应用",
                                "主角字段已改好（记得点「保存到存档」写入文件）。")
            self._set_save_status(
                "save_trainer", "主角字段已改好（记得点「保存到存档」写入文件）。",
                "ok")

    def _refresh_save_trainer(self):
        sv = self.save_obj
        if sv is None:
            return
        t = sv.trainer()
        self.tr_vars["name"].set(str(t["名字"] or ""))
        self.tr_vars["money"].set(str(t["持有金钱"] or 0))
        self.tr_vars["id"].set(str(t["训练家ID"] or 0))
        self.tr_vars["outfit"].set(str(t["服装编号"] or 0))
        self.tr_vars["language"].set(str(t["语种"] or 0))
        self.tr_dex_var.set(bool(t["已获得图鉴"]))
        self.tr_type_combo.set_pairs(
            [(f"{n}（#{i}）", i) for n, i in sv.data.trainer_type_list()],
            keep=False)
        # ★ 框里显示存档原始数据（内部名 / 编号）；译文在框下一行只读展示
        tt_raw = t.get("训练家类型原始")
        if tt_raw is not None:
            self.tr_type_combo.set(str(tt_raw))
        elif t["训练家类型ID"] is not None:
            self.tr_type_combo.set(str(t["训练家类型ID"]))
        else:
            self.tr_type_combo.set("")
        if t["训练家类型ID"] is not None and t["训练家类型"]:
            self.tr_type_trans.config(text=f"译文：{t['训练家类型']}")
        else:
            self.tr_type_trans.config(text="")
        for i, v in enumerate(self.tr_badges):
            v.set(i < len(t["徽章明细"] or []) and bool(t["徽章明细"][i]))
        seen = sum(1 for x in sv.dex_flags("seen") if x)
        owned = sum(1 for x in sv.dex_flags("owned") if x)
        self.tr_dex_lbl.config(text=f"图鉴：已见 {seen} / 已捕获 {owned}")
        self.tr_dex_info.config(
            text=f"存档格式：{t.get('存档格式', sv.fmt)}    "
                 f"训练家类型 {t['训练家类型'] or '—'}"
                 f"（ID {sfmt(t['训练家类型ID'])}）    "
                 f"徽章 {sum(1 for v in self.tr_badges if v.get())}"
                 f"/{len(self.tr_badges)}    "
                 f"存档：{os.path.basename(sv.path)}")

    # ================================================================
    # 子页面 2：同行宝可梦编辑
    # ================================================================
    def _page_save_party(self):
        left, panel = self._save_page_shell("save_party")
        self.party_tool = self._save_toolbar(left, "save_party")

        wrap = tk.Frame(left, bg=BG_BASE)
        wrap.pack(fill="both", expand=True)
        # ★ 左卡定宽 322：5 列表格（40+74+78+32+56=280）+ 滚动条 13 + 卡片
        #   内边距 24 刚好放下。原来是 250，表格被压得「昵称」只剩 20px、
        #   HP 列整列看不见（用户截图反馈过）。
        wrap.grid_columnconfigure(0, weight=0, minsize=322)
        wrap.grid_columnconfigure(1, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        lcard = RoundCard(wrap, radius=16, pad=12)
        lcard.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(lcard.body, text="同行队伍（最多 6 只）", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w", pady=(0, 6))
        self._save_search_row(lcard.body, "save_party",
                              lambda: self._refresh_save_party())
        holder, self.party_tree = self._make_tree(
            lcard.body,
            [("pos", "位置"), ("nick", "昵称"), ("sp", "种族"),
             ("lv", "Lv"), ("hp", "HP")],
            [40, 74, 78, 32, 56], height=10, stretch_all=True)
        self.party_tree.bind("<<TreeviewSelect>>", self._on_party_select)

        # ★ 底部按钮钉在卡片底边（side="bottom"），树自动让位
        btn_grid(lcard.body, [
            ("复制一只", self._party_duplicate),
            ("移入 PC", self._party_to_box),
            ("移出队伍", self._party_remove),
        ]).pack(side="bottom", fill="x", pady=(8, 0))

        holder.pack(fill="both", expand=True)

        rcard = RoundCard(wrap, radius=16, pad=12, scrollable=True)
        rcard.grid(row=0, column=1, sticky="nsew")
        self.party_form = PokemonForm(rcard.body, self)
        self.party_form.frame.pack(fill="both", expand=True)

    def _on_party_select(self, _e=None):
        sv = self.save_obj
        if sv is None:
            return
        sel = self.party_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        party = sv.party()
        if 0 <= idx < len(party):
            self.party_form.load(party[idx], f"队伍第 {idx + 1} 位")

    def _refresh_save_party(self):
        sv = self.save_obj
        if sv is None:
            return
        rows = []
        party = sv.party()
        for i, pm in enumerate(party):
            if sv.empty_slot(pm):
                continue
            r = sv.read_pokemon(pm)
            rows.append((i, (i + 1, r.get("name") or "",
                             sv.data.species_label(r["species"],
                                                   r.get("species_raw")),
                             r["level"],
                             f"{r.get('hp')}/{r.get('totalhp')}")))
        # ★ 过滤只影响显示：行 iid 仍是队伍下标，选中行照样对得上
        shown = _save_filter_rows(rows, self._save_filter_keyword("save_party"))
        self._tree_reload(self.party_tree, shown)
        if not self.party_tree.selection() and shown:
            self.party_tree.selection_set(str(shown[0][0]))
        if self.party_tree.selection():
            self._on_party_select()       # 表单跟着新值重读
        else:
            self.party_form.clear()
        self.party_tool.config(
            text=f"共 {len(rows)} 只"
                 + (f"（筛出 {len(shown)} 只）" if len(shown) != len(rows) else "")
                 + f"   存档：{os.path.basename(sv.path)}")

    def _party_index(self):
        sel = self.party_tree.selection()
        return int(sel[0]) if sel else None

    def _party_duplicate(self):
        sv = self.save_obj
        i = self._party_index()
        if sv is None or i is None:
            messagebox.showinfo("提示", "先在左边选一只宝可梦。")
            return
        pm = sv.clone_pokemon(sv.party()[i])
        if pm is None:
            return
        if not sv.add_to_party(pm):
            messagebox.showwarning("队伍满了", "同行队伍最多 6 只，先移走一只。")
            self._set_save_status("save_party", "队伍已满（6 只），没能复制。",
                                  "err")
            return
        self.mark_dirty()
        self._refresh_save_party()
        self._set_save_status("save_party", "已复制一只到队伍末尾。", "ok")

    def _party_to_box(self):
        sv = self.save_obj
        i = self._party_index()
        if sv is None or i is None:
            return
        # ★ 先看有没有空位再动队伍 —— 之前是先 pop 再放，放不下那只就没了（丢档）
        pm = sv.party()[i] if 0 <= i < len(sv.party()) else None
        if sv.empty_slot(pm):
            return
        if sv.add_to_box(pm, 0)[0] < 0:
            messagebox.showwarning("箱子满了", "所有箱子都满了，先腾一格。")
            self._set_save_status("save_party", "箱子都满了，没移动。", "err")
            return
        sv.remove_from_party(i)
        self.mark_dirty()
        self._refresh_save_party()
        self._set_save_status("save_party", "已把这一只放进箱子。", "ok")

    def _party_remove(self):
        sv = self.save_obj
        i = self._party_index()
        if sv is None or i is None:
            return
        if not messagebox.askyesno("移出队伍", "把这只从队伍里删掉吗？"
                                              "（不会放进箱子，直接消失）"):
            return
        sv.remove_from_party(i)
        self.mark_dirty()
        self._refresh_save_party()
        self._set_save_status("save_party", "已把这一只移出队伍。", "ok")

    # ================================================================
    # 子页面 3：背包编辑
    # ================================================================
    def _page_save_bag(self):
        left, panel = self._save_page_shell("save_bag")
        self.bag_tool = self._save_toolbar(left, "save_bag")

        card = RoundCard(left, radius=16, pad=14)
        card.pack(fill="both", expand=True)
        body = card.body

        top = tk.Frame(body, bg=CARD)
        top.pack(fill="x", pady=(0, 6))
        _lbl(top, "口袋", width=8).pack(side="left")
        self.bag_pocket_combo = SearchCombo(top, [], width=18)
        self.bag_pocket_combo.pack(side="left")
        self.bag_pocket_combo.bind("<<ComboboxSelected>>",
                                   lambda e: self._load_bag_items())
        _lbl(top, "登记道具", width=10).pack(side="left", padx=(16, 0))
        self.bag_reg_combo = SearchCombo(
            top, [], width=20,
            resolver=make_manual_resolver(lambda: self.save_obj, "item"))
        self.bag_reg_combo.pack(side="left")
        GlassButton(top, "设为登记道具", width=128, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._bag_set_registered).pack(side="left", padx=8)
        self.bag_reg_lbl = _hint(top, "")
        self.bag_reg_lbl.pack(side="left")

        self.bag_search_var = self._save_search_row(
            body, "save_bag", lambda: self._load_bag_items())

        holder, self.bag_tree = self._make_tree(
            body, [("name", "道具"), ("trans", "译文"), ("id", "#"),
                   ("count", "数量")],
            [190, 150, 70, 70], height=14)
        self.bag_tree.bind("<<TreeviewSelect>>", self._on_bag_select)

        # ★ 底部两行（改数量 / 添加道具）单独一帧、side="bottom" 钉在卡片
        #   底边，树自动让位。原来按顺序 pack，窗口一矮「添加道具」整行被
        #   挤出卡片看不见（1366×768 屏幕上尤其明显）。
        foot = tk.Frame(body, bg=CARD)
        foot.pack(side="bottom", fill="x")

        edit = tk.Frame(foot, bg=CARD)
        edit.pack(fill="x", pady=2)
        _lbl(edit, "数量", width=8).pack(side="left")
        self.bag_count_var = tk.StringVar(value="")
        _entry(edit, self.bag_count_var, 10).pack(side="left")
        GlassButton(edit, "改数量", width=96, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._bag_edit_count).pack(side="left", padx=6)
        GlassButton(edit, "删除这条", width=104, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._bag_delete).pack(side="left")

        add = tk.Frame(foot, bg=CARD)
        add.pack(fill="x", pady=(8, 0))
        _lbl(add, "添加道具", width=10).pack(side="left")
        self.bag_add_combo = SearchCombo(
            add, [], width=30,
            resolver=make_manual_resolver(lambda: self.save_obj, "item"))
        self.bag_add_combo.pack(side="left")
        _lbl(add, "数量", width=6).pack(side="left", padx=(10, 0))
        self.bag_add_var = tk.StringVar(value="99")
        _entry(add, self.bag_add_var, 8).pack(side="left")
        GlassButton(add, "加入本口袋", width=116, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._bag_add).pack(side="left", padx=6)
        GlassButton(add, "本口袋补满 999", width=140, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=lambda: self._bag_bulk(999)).pack(side="left")

        holder.pack(fill="both", expand=True, pady=(4, 6))

    def _bag_pocket_options(self, sv):
        opts = []
        for idx in range(len(sv.g("$PokemonBag").ivars.get("@pockets") or [])):
            opts.append((f"{sv.data.pocket_name(idx)}（{idx}）", idx))
        return opts

    def _refresh_save_bag(self):
        sv = self.save_obj
        if sv is None:
            return
        # ★ keep=True：保留玩家当前正在看的口袋，别每次刷新都跳回第 2 个
        self.bag_pocket_combo.set_pairs(self._bag_pocket_options(sv), keep=True)
        cur = self.bag_pocket_combo.value_of()
        if cur is None:
            cur = 1 if len(self.bag_pocket_combo.pairs) > 1 else 0
            self.bag_pocket_combo.set_value(cur)
        items = [(f"{n}（#{i}）", i) for n, i in sv.data.item_list()]
        self.bag_add_combo.set_pairs(items, keep=True)
        self.bag_reg_combo.set_pairs([("（无）", 0)] + items, keep=False)
        bag_info = sv.bag()
        reg_id = bag_info.get("登记道具ID") or 0
        reg_raw = bag_info.get("登记道具原始名")
        # ★ 登记道具框显示存档原始数据（内部名 / 编号），译文在右侧标签
        if reg_raw:
            self.bag_reg_combo.set(str(reg_raw))
        elif reg_id:
            self.bag_reg_combo.set(str(reg_id))
        else:
            self.bag_reg_combo.set("（无）")
        self.bag_reg_lbl.config(
            text=(f"当前登记：{bag_info.get('登记道具', '')}"
                  if reg_id or reg_raw else "当前登记：（无）"))
        self._load_bag_items()
        self.bag_tool.config(text=f"存档：{os.path.basename(sv.path)}")

    def _load_bag_items(self):
        sv = self.save_obj
        if sv is None:
            return
        idx = self.bag_pocket_combo.value_of() or 0
        rows = []
        # ★ 用 pocket_entries_ex()：框里显示**存档原始数据**（内部名 / 编号），
        #   「译文」列显示按游戏数据翻出来的名字（翻不出就留空）
        for i, (iid, raw, cnt) in enumerate(sv.pocket_entries_ex(idx)):
            if raw:
                name = str(raw)
            elif iid:
                name = str(iid)
            else:
                name = "（无）"
            trans = f"译文：{sv.data.item(iid)}" if iid else ""
            rows.append((i, (name, trans, iid, cnt)))
        # ★ 过滤只影响显示：行 iid 仍是口袋内下标，改数量/删除都还按它定位
        shown = _save_filter_rows(rows, self._save_filter_keyword("save_bag"))
        self._tree_reload(self.bag_tree, shown)
        self.bag_count_var.set("")
        if len(shown) != len(rows):
            self.bag_tool.config(
                text=f"本口袋 {len(rows)} 种，筛出 {len(shown)} 种    "
                     f"存档：{os.path.basename(sv.path)}")

    def _bag_selected(self):
        sel = self.bag_tree.selection()
        return int(sel[0]) if sel else None

    def _on_bag_select(self, _e=None):
        sv = self.save_obj
        i = self._bag_selected()
        if sv is None or i is None:
            return
        idx = self.bag_pocket_combo.value_of() or 0
        entries = sv.pocket_entries(idx)
        if 0 <= i < len(entries):
            self.bag_count_var.set(str(entries[i][1]))

    def _bag_edit_count(self):
        sv = self.save_obj
        i = self._bag_selected()
        if sv is None or i is None:
            messagebox.showinfo("提示", "先在表里选一条道具。")
            return
        idx = self.bag_pocket_combo.value_of() or 0
        entries = sv.pocket_entries(idx)
        if not (0 <= i < len(entries)):
            return
        try:
            n = int(self.bag_count_var.get().strip())
        except ValueError:
            messagebox.showwarning("数量不对", "数量要填整数。")
            return
        sv.set_pocket_count_by_index(idx, i, n)
        self.mark_dirty()
        self._load_bag_items()
        self._set_save_status("save_bag", f"数量已改成 {n} 个。", "ok")

    def _bag_delete(self):
        sv = self.save_obj
        i = self._bag_selected()
        if sv is None or i is None:
            return
        idx = self.bag_pocket_combo.value_of() or 0
        sv.remove_bag_index(idx, i)
        self.mark_dirty()
        self._load_bag_items()
        self._set_save_status("save_bag", "已从口袋里删掉这一种道具。", "ok")

    def _bag_add(self):
        sv = self.save_obj
        if sv is None:
            return
        iid = self.bag_add_combo.value_or_text()
        if iid is None:
            messagebox.showinfo(
                "提示", "先在下拉里选一个道具（可打字搜索），"
                        "或直接填**英文内部名 / 编号**（如 POKEBALL、410）。")
            return
        # ★ 数量填错只警告、不阻止：按 1 个加入
        n = 1
        try:
            n = int(self.bag_add_var.get().strip() or 1)
        except ValueError:
            messagebox.showwarning(
                "数量不对", "数量要填整数，已按 1 个加入。", parent=self)
        idx = self.bag_pocket_combo.value_of() or 0
        try:
            sv.set_bag_item(idx, iid, n)
        except Exception as e:                                  # noqa: BLE001
            messagebox.showwarning("加不进去", str(e), parent=self)
            return
        self.mark_dirty()
        self._load_bag_items()
        self._set_save_status("save_bag", f"已加入 {n} 个。", "ok")

    def _bag_bulk(self, n):
        sv = self.save_obj
        if sv is None:
            return
        idx = self.bag_pocket_combo.value_of() or 0
        entries = sv.pocket_entries(idx)
        if not entries:
            messagebox.showinfo("提示", "这个口袋是空的。")
            return
        if not messagebox.askyesno("批量改数量",
                                   f"把「{sv.data.pocket_name(idx)}」里 "
                                   f"{len(entries)} 种道具都改成 {n} 个？"):
            return
        sv.fill_pocket(idx, n)
        self.mark_dirty()
        self._load_bag_items()
        self._set_save_status("save_bag", f"整个口袋的道具都改成了 {n} 个。",
                              "ok")

    def _bag_set_registered(self):
        sv = self.save_obj
        if sv is None:
            return
        v = self.bag_reg_combo.value_or_text()
        if v is None:
            return
        try:
            sv.set_registered_item(v)
        except Exception as e:                                  # noqa: BLE001
            messagebox.showwarning("设置失败", str(e), parent=self)
            return
        self.mark_dirty()
        self.bag_reg_lbl.config(text=f"当前登记：{sv.data.item(v)}"
                                     if isinstance(v, int) else f"当前登记：{v}")
        self._set_save_status("save_bag", "登记道具已更新。", "ok")

    # ================================================================
    # 子页面 4：PC 盒子编辑
    # ================================================================
    def _page_save_box(self):
        left, panel = self._save_page_shell("save_box")
        self.box_tool = self._save_toolbar(left, "save_box")

        wrap = tk.Frame(left, bg=BG_BASE)
        wrap.pack(fill="both", expand=True)
        # ★ 左卡定宽 320：4 列表格（40+90+96+38=264）+ 滚动条 13 + 内边距 24。
        #   原来 290 偏窄，树列全挤在一起，顶行「改名」按钮还被裁成「箱」。
        wrap.grid_columnconfigure(0, weight=0, minsize=320)
        wrap.grid_columnconfigure(1, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        lcard = RoundCard(wrap, radius=16, pad=12)
        lcard.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        top = tk.Frame(lcard.body, bg=CARD)
        top.pack(fill="x")
        _lbl(top, "箱子", width=4).pack(side="left")
        # ★ 箱子选择 + 改名分成两行：原来一行硬塞（标签+下拉+输入框+按钮），
        #   卡片一窄「改名」按钮就被压成 35px（用户截图里只剩个「箱」字）
        self.box_combo = SearchCombo(top, [], width=14)
        self.box_combo.pack(side="left", fill="x", expand=True)
        self.box_combo.bind("<<ComboboxSelected>>",
                            lambda e: self._load_box_slots())
        top2 = tk.Frame(lcard.body, bg=CARD)
        top2.pack(fill="x", pady=(2, 0))
        self.box_name_var = tk.StringVar(value="")
        _entry(top2, self.box_name_var, 12).pack(side="left", fill="x",
                                                 expand=True)
        GlassButton(top2, "改名", width=72, height=30, bg=CARD,
                    font=FONT_SMALL,
                    command=self._box_rename).pack(side="left", padx=(6, 0))
        self._save_search_row(lcard.body, "save_box",
                              lambda: self._load_box_slots())

        holder, self.box_tree = self._make_tree(
            lcard.body,
            [("slot", "格"), ("nick", "昵称"), ("sp", "种族"), ("lv", "Lv")],
            [40, 90, 96, 38], height=13, stretch_all=True)
        self.box_tree.bind("<<TreeviewSelect>>", self._on_box_select)

        # ★ 底部按钮钉在卡片底边（side="bottom"），树自动让位 ——
        #   按顺序 pack 时窗口一矮这排按钮就被挤扁（踩过：1366×768）
        btn_grid(lcard.body, [
            ("移入队伍", self._box_to_party),
            ("复制到空位", self._box_duplicate),
            ("清空该格", self._box_clear),
        ]).pack(side="bottom", fill="x", pady=(6, 0))

        holder.pack(fill="both", expand=True, pady=(6, 4))

        rcard = RoundCard(wrap, radius=16, pad=12, scrollable=True)
        rcard.grid(row=0, column=1, sticky="nsew")
        self.box_form = PokemonForm(rcard.body, self)
        self.box_form.frame.pack(fill="both", expand=True)

    def _refresh_save_box(self):
        sv = self.save_obj
        if sv is None:
            return
        opts = []
        for i, b in enumerate(sv.boxes()):
            n = len([p for p in (b.ivars.get("@pokemon") or [])
                     if not sv.empty_slot(p)])
            opts.append((f"{i + 1}. {b.ivars.get('@name') or '箱子'}（{n}）", i))
        self.box_combo.set_pairs(opts, keep=True)
        if self.box_combo.value_of() is None:
            self.box_combo.set_value(
                sv.g("$PokemonStorage").ivars.get("@currentBox") or 0)
        self._load_box_slots()
        self.box_tool.config(
            text=f"共 {len(sv.boxes())} 箱    存档：{os.path.basename(sv.path)}")

    def _load_box_slots(self):
        sv = self.save_obj
        if sv is None:
            return
        bi = self.box_combo.value_of() or 0
        slots = sv.box_slots(bi)
        rows = []
        for i in range(30):
            pm = slots[i] if i < len(slots) else None
            if sv.empty_slot(pm):
                rows.append((i, (i + 1, "（空）", "", "")))
                continue
            r = sv.read_pokemon(pm)
            rows.append((i, (i + 1, r.get("name") or "",
                             sv.data.species_label(r["species"],
                                                   r.get("species_raw")),
                             r["level"])))
        shown = _save_filter_rows(rows, self._save_filter_keyword("save_box"))
        self._tree_reload(self.box_tree, shown)
        boxes = sv.boxes()
        if 0 <= bi < len(boxes):
            self.box_name_var.set(str(boxes[bi].ivars.get("@name") or ""))
        # 表单跟着选中格重读（没选中就清空）
        self._on_box_select()
        if len(shown) != len(rows):
            self.box_tool.config(
                text=f"本箱 {len(rows)} 格，筛出 {len(shown)} 格    "
                     f"存档：{os.path.basename(sv.path)}")

    def _box_selected(self):
        sel = self.box_tree.selection()
        return int(sel[0]) if sel else None

    def _on_box_select(self, _e=None):
        sv = self.save_obj
        i = self._box_selected()
        bi = self.box_combo.value_of() or 0
        if sv is None or i is None:
            self.box_form.clear()
            return
        slots = sv.box_slots(bi)
        pm = slots[i] if i < len(slots) else None
        if sv.empty_slot(pm):
            self.box_form.clear()
            self.box_form.title_lbl.config(
                text=f"第 {bi + 1} 箱 · 第 {i + 1} 格（空）")
            return
        self.box_form.load(pm, f"第 {bi + 1} 箱 · 第 {i + 1} 格")

    def _box_rename(self):
        sv = self.save_obj
        if sv is None:
            return
        bi = self.box_combo.value_of() or 0
        sv.rename_box(bi, self.box_name_var.get())
        self.mark_dirty()
        self._refresh_save_box()
        self._set_save_status("save_box", f"第 {bi + 1} 箱已改名。", "ok")

    def _box_to_party(self):
        sv = self.save_obj
        i, bi = self._box_selected(), self.box_combo.value_of() or 0
        if sv is None or i is None:
            return
        if not sv.move_box_to_party(bi, i):
            messagebox.showwarning("放不进去", "同行队伍满了，或者这一格是空的。")
            self._set_save_status("save_box", "没放进去：队伍满了或这一格是空的。",
                                  "err")
            return
        self.mark_dirty()
        self._load_box_slots()
        self._set_save_status("save_box", "已把这一格放进同行队伍。", "ok")

    def _box_duplicate(self):
        sv = self.save_obj
        i, bi = self._box_selected(), self.box_combo.value_of() or 0
        if sv is None or i is None:
            return
        slots = sv.box_slots(bi)
        if not (0 <= i < len(slots)) or sv.empty_slot(slots[i]):
            messagebox.showinfo("提示", "这一格是空的。")
            return
        pm = sv.clone_pokemon(slots[i])
        if pm is None:
            return
        b2, s2 = sv.add_to_box(pm, bi)
        if b2 < 0:
            messagebox.showwarning("放不下", "所有箱子都满了。")
            return
        self.mark_dirty()
        self._load_box_slots()
        messagebox.showinfo("已复制", f"复制到了第 {b2 + 1} 箱第 {s2 + 1} 格。")
        self._set_save_status(
            "save_box", f"已复制到第 {b2 + 1} 箱第 {s2 + 1} 格。", "ok")

    def _box_clear(self):
        sv = self.save_obj
        i, bi = self._box_selected(), self.box_combo.value_of() or 0
        if sv is None or i is None:
            return
        if not messagebox.askyesno("清空该格", "把这一格的宝可梦删掉吗？"):
            return
        sv.remove_from_box(bi, i)
        self.mark_dirty()
        self._load_box_slots()
        self.box_form.clear()
        self._set_save_status("save_box", "这一格已清空。", "ok")

    # ================================================================
    # 子页面 5：开关与变量
    # ================================================================
    # ★ 编号规则与游戏里一致：**从 1 开始**（@data[0] 是占位）。
    #   列表默认只列「已开的开关 / 非 0 的变量」—— 动辄上千条全列出来反而
    #   找不到东西；任意编号可以用下面的输入框直接改。
    # ★ 所有输入框都允许手填：填错只弹警告，能写的照样写，不阻止。
    _SWITCH_ROW_CAP = 2000

    def _page_save_switch(self):
        left, panel = self._save_page_shell("save_switch")
        self.sw_tool = self._save_toolbar(left, "save_switch")

        wrap = tk.Frame(left, bg=BG_BASE)
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        # ---- 左卡：全局开关 ----
        lcard = RoundCard(wrap, radius=16, pad=12)
        lcard.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(lcard.body, text="全局开关", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        self.sw_lbl = _hint(lcard.body, "")
        self.sw_lbl.pack(fill="x", pady=(2, 6))
        bind_autowrap(self.sw_lbl, pad=4, minimum=120)
        holder, self.switch_tree = self._make_tree(
            lcard.body, [("idx", "编号"), ("state", "状态")],
            [90, 80], height=16)
        holder.pack(fill="both", expand=True)
        self.switch_tree.bind("<<TreeviewSelect>>", self._on_switch_select)

        foot = tk.Frame(lcard.body, bg=CARD)
        foot.pack(fill="x", pady=(8, 0))
        _lbl(foot, "编号", width=4).pack(side="left")
        self.sw_idx_var = tk.StringVar(value="")
        _entry(foot, self.sw_idx_var, 8).pack(side="left")
        _lbl(foot, "状态", width=4).pack(side="left", padx=(10, 0))
        self.sw_on_combo = SearchCombo(foot, [("开", True), ("关", False)],
                                       width=8)
        self.sw_on_combo.pack(side="left")
        GlassButton(foot, "应用", width=72, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._switch_apply).pack(side="left", padx=8)
        GlassButton(foot, "全部关闭", width=96, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._switch_all_off).pack(side="left")

        # ---- 右卡：全局变量 ----
        rcard = RoundCard(wrap, radius=16, pad=12, scrollable=True)
        rcard.grid(row=0, column=1, sticky="nsew")
        tk.Label(rcard.body, text="全局变量", bg=CARD, fg=C_TITLE,
                 font=FONT_TITLE).pack(anchor="w")
        self.var_lbl = _hint(rcard.body, "")
        self.var_lbl.pack(fill="x", pady=(2, 6))
        bind_autowrap(self.var_lbl, pad=4, minimum=120)
        vholder, self.var_tree = self._make_tree(
            rcard.body, [("idx", "编号"), ("val", "值")],
            [90, 140], height=16)
        vholder.pack(fill="both", expand=True)
        self.var_tree.bind("<<TreeviewSelect>>", self._on_variable_select)

        vfoot = tk.Frame(rcard.body, bg=CARD)
        vfoot.pack(fill="x", pady=(8, 0))
        _lbl(vfoot, "编号", width=4).pack(side="left")
        self.var_idx_var = tk.StringVar(value="")
        _entry(vfoot, self.var_idx_var, 8).pack(side="left")
        _lbl(vfoot, "值", width=3).pack(side="left", padx=(10, 0))
        self.var_val_var = tk.StringVar(value="")
        _entry(vfoot, self.var_val_var, 12).pack(side="left")
        GlassButton(vfoot, "应用", width=72, height=32, bg=CARD,
                    font=FONT_SMALL,
                    command=self._variable_apply).pack(side="left", padx=8)

    def _refresh_save_switch(self):
        sv = self.save_obj
        if sv is None:
            return
        # -- 开关：只列「已开」的 --
        try:
            data = sv.switch_peek()
        except Exception as e:                                  # noqa: BLE001
            self.switch_tree.delete(*self.switch_tree.get_children())
            self.sw_lbl.config(text=f"读不到开关数据：{e}", fg=ERR_COLOR)
            data = None
        if data is not None:
            rows = []
            for i, v in enumerate(data):
                if i < 1 or not v:
                    continue
                rows.append((i, (i, "开")))
            self._tree_reload(self.switch_tree, rows[:self._SWITCH_ROW_CAP])
            self.sw_lbl.config(
                text=f"已开 {len(rows)} 个 / 共 {len(data)} 个"
                     + (f"（列表只显示前 {self._SWITCH_ROW_CAP} 个，"
                        f"更多请用下方编号直接改）"
                        if len(rows) > self._SWITCH_ROW_CAP else "")
                     + "。编号从 1 开始，与游戏里一致。",
                fg=C_HINT)
        # -- 变量：只列「非 0」的 --
        try:
            vdata = sv.variable_peek()
        except Exception as e:                                  # noqa: BLE001
            self.var_tree.delete(*self.var_tree.get_children())
            self.var_lbl.config(text=f"读不到变量数据：{e}", fg=ERR_COLOR)
            vdata = None
        if vdata is not None:
            vrows = []
            for i, v in enumerate(vdata):
                if i < 1 or v in (None, 0, False):
                    continue
                vrows.append((i, (i, str(v))))
            self._tree_reload(self.var_tree, vrows[:self._SWITCH_ROW_CAP])
            self.var_lbl.config(
                text=f"非 0 变量 {len(vrows)} 个 / 共 {len(vdata)} 个"
                     + (f"（列表只显示前 {self._SWITCH_ROW_CAP} 个，"
                        f"更多请用下方编号直接改）"
                        if len(vrows) > self._SWITCH_ROW_CAP else "")
                     + "。填 0 等于清掉该变量。",
                fg=C_HINT)
        self.sw_tool.config(text=f"存档：{os.path.basename(sv.path)}")

    def _on_switch_select(self, _e=None):
        sel = self.switch_tree.selection()
        if sel:
            self.sw_idx_var.set(sel[0])
            self.sw_on_combo.set_value(True)

    def _on_variable_select(self, _e=None):
        sel = self.var_tree.selection()
        if not sel:
            return
        i = int(sel[0])
        self.var_idx_var.set(str(i))
        vals = self.var_tree.item(sel[0], "values")
        self.var_val_var.set(str(vals[1]) if vals and len(vals) > 1 else "")

    def _switch_apply(self):
        sv = self.save_obj
        if sv is None:
            messagebox.showinfo("提示", "先在右侧选一份存档。", parent=self)
            return
        txt = self.sw_idx_var.get().strip()
        if not txt:
            messagebox.showwarning("编号为空", "先填开关编号（从 1 开始的整数）。",
                                   parent=self)
            return
        try:
            idx = int(txt)
        except ValueError:
            messagebox.showwarning(
                "编号不对", f"开关编号要填整数（收到「{txt}」）。", parent=self)
            return
        on_txt = self.sw_on_combo.get().strip().lower()
        if on_txt in ("开", "1", "true", "on", "是"):
            on = True
        elif on_txt in ("关", "0", "false", "off", "否"):
            on = False
        else:
            messagebox.showwarning(
                "状态不对", f"状态要填「开」或「关」（收到「{on_txt}」）。",
                parent=self)
            return
        try:
            sv.set_switch(idx, on)
        except Exception as e:                                  # noqa: BLE001
            messagebox.showwarning("写入失败", str(e), parent=self)
            self._set_save_status("save_switch", f"开关写入失败：{e}", "err")
            return
        self.mark_dirty()
        self._refresh_save_switch()
        self._set_save_status("save_switch",
                              f"开关 {idx} 已设为「{'开' if on else '关'}」。", "ok")

    def _switch_all_off(self):
        sv = self.save_obj
        if sv is None:
            return
        data = sv.switch_peek()
        on = [i for i, v in enumerate(data) if i >= 1 and v]
        if not on:
            messagebox.showinfo("提示", "已经没有开着的开关了。", parent=self)
            return
        if not messagebox.askyesno(
                "全部关闭", f"把已开的 {len(on)} 个开关全部关掉吗？",
                parent=self):
            return
        for i in on:
            sv.set_switch(i, False)
        self.mark_dirty()
        self._refresh_save_switch()
        self._set_save_status("save_switch", f"已关掉 {len(on)} 个开关。", "ok")

    def _variable_apply(self):
        sv = self.save_obj
        if sv is None:
            messagebox.showinfo("提示", "先在右侧选一份存档。", parent=self)
            return
        itxt = self.var_idx_var.get().strip()
        vtxt = self.var_val_var.get().strip()
        if not itxt:
            messagebox.showwarning("编号为空", "先填变量编号（从 1 开始的整数）。",
                                   parent=self)
            return
        try:
            idx = int(itxt)
        except ValueError:
            messagebox.showwarning(
                "编号不对", f"变量编号要填整数（收到「{itxt}」）。", parent=self)
            return
        if not vtxt:
            messagebox.showwarning(
                "值为空", "变量值要填整数；想清掉这个变量就填 0。", parent=self)
            return
        try:
            val = int(vtxt)
        except ValueError:
            messagebox.showwarning(
                "值不对", f"变量值要填整数（收到「{vtxt}」）。", parent=self)
            return
        try:
            sv.set_variable(idx, val)
        except Exception as e:                                  # noqa: BLE001
            messagebox.showwarning("写入失败", str(e), parent=self)
            self._set_save_status("save_switch", f"变量写入失败：{e}", "err")
            return
        self.mark_dirty()
        self._refresh_save_switch()
        self._set_save_status("save_switch", f"变量 {idx} 已设为 {val}。", "ok")


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
