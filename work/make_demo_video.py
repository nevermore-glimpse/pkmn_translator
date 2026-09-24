# -*- coding: utf-8 -*-
"""
生成「宝可梦同人游戏翻译工具 v1.2.0」完整使用流程演示视频。

完全离线、依赖可控：
  · Pillow 绘制每一帧（毛玻璃宝可梦主题、中文大字幕烧录进画面）
  · imageio-ffmpeg 捆绑的 ffmpeg 编码为 MP4
同时输出一份 .srt 字幕文件，逐段对应演示步骤。
"""
import os
import math
import numpy as np
import imageio.v2 as imageio
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "demo_output")
os.makedirs(OUT_DIR, exist_ok=True)

W, H = 1280, 720
FPS = 30
HOLD = 4.0  # 每页停留秒数

# ---- 配色（与 gui.py 主题一致）----
BG_BASE = (234, 243, 252)      # #EAF3FC
CARD = (255, 255, 255)
ACCENT = (227, 53, 57)        # #E33539 球红
BLUE = (42, 109, 176)         # #2A6DB0
YELLOW = (255, 203, 5)        # #FFCB05 Pikachu 黄
INK = (28, 40, 60)            # 深蓝黑文字
INK_DIM = (96, 112, 132)
WHITE = (255, 255, 255)

FONT_DIR = r"C:\Windows\Fonts"
F_REG = os.path.join(FONT_DIR, "msyh.ttc")     # 微软雅黑
F_BOLD = os.path.join(FONT_DIR, "msyhbd.ttc")  # 微软雅黑粗

def font(size, bold=False):
    path = F_BOLD if bold else F_REG
    return ImageFont.truetype(path, size)

# ---- 演示步骤（标题=大字幕，points=要点）----
STEPS = [
    {
        "tag": "封面",
        "title": "宝可梦同人游戏翻译工具 · 使用演示",
        "sub": "v1.2.0 · 完整使用流程",
        "points": ["本地 Ollama / 云端 API 双模式",
                   "毛玻璃宝可梦主题 GUI · 8 大功能页"],
    },
    {
        "tag": "01 · 启动与界面",
        "title": "毛玻璃宝可梦主题界面",
        "sub": "头像 + 标题栏 v1.2.0，左侧 8 个功能页，右侧文件侧边栏",
        "points": ["亚克力磨砂质感，宝可梦配色",
                   "菜单：翻译 / 重翻 / 术语 / 前缀 / 润色 / Excel / 环境 / 设置"],
    },
    {
        "tag": "02 · 选择文件",
        "title": "先选翻译范围",
        "sub": "菜单 1 执行前，先选「单个文件」或「整个文件夹」",
        "points": ["选文件夹时列出全部 .txt 并逐个翻译",
                   "所选文件自动同步到后续菜单，无需重复选择"],
    },
    {
        "tag": "03 · 开始翻译",
        "title": "控制码脱敏后整句翻译",
        "sub": "标签/控制码变成 @0@ 占位符，整句批量送模型，译后还原校验",
        "points": ["本地 Ollama 或云端 API 模式一键切换",
                   "术语表作为参考注入 prompt，译后兜底替换"],
    },
    {
        "tag": "04 · 占位符保护",
        "title": "占位符绝不丢失",
        "sub": "模型若漏翻 @0@，针对性重试 + 按源文位置回插兜底",
        "points": ["术语表已排除占位符型伪术语，杜绝反向教学",
                   "缺失控制码一律按原文原样补回"],
    },
    {
        "tag": "05 · 中文润色重翻",
        "title": "菜单 5：中文润色",
        "sub": "把缓存中的中文译文再润色一遍并覆盖，更自然通顺",
        "points": ["短于阈值的句子自动跳过",
                   "润色时严格校验占位符，不全则保留原译文"],
    },
    {
        "tag": "06 · 术语编辑 / 删除",
        "title": "术语可编辑、可删除、可撤回",
        "sub": "菜单 3：双击改译文；选中或批量删除术语，应用前可一键撤回",
        "points": ["删除选中 / 批量删除（按当前筛选）",
                   "撤回栈支持逐步恢复，安心整理术语表"],
    },
    {
        "tag": "07 · 前缀与 Excel",
        "title": "前缀字典 & Excel 术语表",
        "sub": "菜单 4 应用前缀字典；菜单 6 用 Excel 一键生成术语表",
        "points": ["句首控制码由前缀字典统一管理",
                   "报告中的问题句可一键重翻修正"],
    },
    {
        "tag": "08 · 云端与更新",
        "title": "云端 API 模式 & 检查更新",
        "sub": "设置页切换本地/云端（参数自动同步弹窗），菜单 8 检查 GitHub 更新",
        "points": ["切换模式自动调整术语上限/超时/上下文等",
                   "发现新版本弹出下载链接"],
    },
]

# ---- 绘制工具 ----
def round_rect(draw, box, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)

def pokeball(draw, cx, cy, r, alpha=255):
    # 上半红、下半白、中间黑线 + 中心按钮
    col_top = tuple(int(c * alpha / 255) for c in ACCENT) if alpha < 255 else ACCENT
    col_bot = WHITE
    draw.pieslice([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=col_top)
    draw.pieslice([cx - r, cy - r, cx + r, cy + r], 0, 180, fill=col_bot)
    draw.line([cx - r, cy, cx + r, cy], fill=INK, width=max(2, r // 12))
    draw.ellipse([cx - r // 3, cy - r // 3, cx + r // 3, cy + r // 3],
                 fill=WHITE, outline=INK, width=max(2, r // 14))

def soft_bg(base):
    img = Image.new("RGB", (W, H), base)
    draw = ImageDraw.Draw(img, "RGBA")
    # 光斑
    glow = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-160, -160, 360, 360], fill=(255, 255, 255, 90))
    gd.ellipse([W - 320, H - 300, W + 120, H + 140], fill=(BLUE[0], BLUE[1], BLUE[2], 50))
    gd.ellipse([W - 260, -180, W + 120, 260], fill=(YELLOW[0], YELLOW[1], YELLOW[2], 40))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, glow).convert("RGB")
    return img

def draw_slide(idx, p):
    """p: 0..1 进度，用于底部进度条与轻微入场动画"""
    s = STEPS[idx]
    img = soft_bg(BG_BASE)
    d = ImageDraw.Draw(img, "RGBA")

    # 右侧半透明精灵球装饰
    ball = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(ball)
    pokeball(bd, W - 150, H - 150, 110, alpha=26)
    img = Image.alpha_composite(img.convert("RGBA"), ball).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")

    # 顶部标题条
    round_rect(d, [40, 36, W - 40, 104], 18, fill=CARD)
    d.line([64, 70, 64, 70 + 0], fill=ACCENT)  # noop keep
    # 标题
    d.text((72, 52), "宝可梦同人游戏翻译工具", font=font(30, True), fill=INK)
    # 版本徽章
    badge_w = 120
    round_rect(d, [W - 40 - badge_w - 16, 52, W - 56, 88], 14, fill=ACCENT)
    d.text((W - 40 - badge_w - 16 + badge_w // 2, 70), "v1.2.0",
           font=font(22, True), fill=WHITE, anchor="mm")

    # 步骤标签（左侧竖条 + 文字）
    tag = s["tag"]
    d.text((72, 132), tag, font=font(20, True), fill=BLUE)

    # 步骤编号大圆（仅内容页）
    if idx >= 1:
        num = s["tag"].split("·")[0].strip()
        cxp, cyp = 120, 300
        r = 64
        # 入场缩放
        rr = int(r * (0.86 + 0.14 * min(1, p * 1.4)))
        round_rect(d, [cxp - rr, cyp - rr, cxp + rr, cyp + rr], rr, fill=ACCENT)
        d.text((cxp, cyp), num, font=font(54, True), fill=WHITE, anchor="mm")

    # 主标题（大字幕）
    title_y = 200
    d.text((72, title_y), s["title"], font=font(40, True), fill=INK)

    # 副标题（说明，作为字幕正文）
    sub_y = title_y + 64
    # 自动换行
    sub = s["sub"]
    fsub = font(24)
    # 简单按宽度折行
    lines = wrap_text(d, sub, fsub, W - 160)
    yy = sub_y
    for ln in lines:
        d.text((72, yy), ln, font=fsub, fill=INK_DIM)
        yy += 34

    # 要点
    py = max(yy + 18, 360)
    for pt in s["points"]:
        d.ellipse([80, py + 8, 92, py + 20], fill=YELLOW)
        d.text((104, py), pt, font=font(22), fill=INK)
        py += 40

    # 底部进度条
    bar_x0, bar_y, bar_x1 = 72, H - 56, W - 72
    round_rect(d, [bar_x0, bar_y, bar_x1, bar_y + 8], 4,
               fill=(210, 222, 235))
    pw = int((bar_x1 - bar_x0) * p)
    if pw > 0:
        round_rect(d, [bar_x0, bar_y, bar_x0 + pw, bar_y + 8], 4, fill=ACCENT)

    # 页码
    d.text((W - 90, H - 52), f"{idx + 1}/{len(STEPS)}",
           font=font(18), fill=INK_DIM)

    return img

def wrap_text(draw, text, fnt, max_w):
    """按像素宽度折行（中文按字符）。"""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        test = cur + ch
        if draw.textlength(test, font=fnt) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines or [""]

def main():
    frames = []
    total = len(STEPS)
    for i in range(total):
        n_frames = int(HOLD * FPS)
        for f in range(n_frames):
            p = (f + 1) / n_frames
            img = draw_slide(i, p)
            frames.append(img)
    # 片段间 0.4s 交叉淡入淡出
    fade = int(0.4 * FPS)
    seq = []
    prev = None
    for img in frames:
        if prev is None:
            for _ in range(1):
                seq.append(img)
            prev = img
            continue
        # 不做复杂淡入，直接追加（保持稳健）；用最后一帧做轻微过渡略过
        seq.append(img)
    # 末帧多停 0.5s
    for _ in range(int(0.5 * FPS)):
        seq.append(frames[-1])

    out_path = os.path.join(OUT_DIR, "pkmn_translator_demo.mp4")
    writer = imageio.get_writer(
        out_path, fps=FPS, codec="libx264",
        quality=8, macro_block_size=1,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )
    for fr in seq:
        writer.append_data(np.asarray(fr.convert("RGB")))
    writer.close()

    # 写 .srt 字幕
    srt_path = os.path.join(OUT_DIR, "pkmn_translator_demo.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, s in enumerate(STEPS):
            start = i * HOLD
            end = (i + 1) * HOLD
            f.write(f"{i + 1}\n")
            f.write(f"{fmt_ts(start)} --> {fmt_ts(end)}\n")
            f.write(s["title"] + "\n")
            f.write(s["sub"] + "\n\n")

    print("VIDEO:", out_path)
    print("SRT:", srt_path)
    print("FRAMES:", len(seq))

def fmt_ts(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

if __name__ == "__main__":
    main()
