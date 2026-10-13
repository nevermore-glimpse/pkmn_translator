# -*- coding: utf-8 -*-
"""
从电脑版的原始素材生成安卓 App 需要的图标与封面图。

素材来源（人工从 E:\\pkmn_translator 拿过来的）：
    start.ico          应用图标
    玛俐大小姐.jpg      封面图

产物：
    android/app/src/main/res/mipmap-*/ic_launcher.png
    web/assets/cover.jpg      封面页用的图（压到 1080px 宽，控制 APK 体积）

★ 这个脚本**只在需要换素材时手动跑一次**，不参与打包流程。
"""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICO_SRC = r"E:/pkmn_translator/start.ico"
COVER_SRC = r"E:/pkmn_translator/玛俐大小姐.jpg"
RES = os.path.join(ROOT, "android", "app", "src", "main", "res")
WEB_ASSETS = os.path.join(ROOT, "web", "assets")

# 安卓各密度启动图标的标准边长
DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}
# 自适应图标的前景层要更大（108dp 画布 + 33% 安全边距）
FG_DENSITIES = {
    "mipmap-mdpi": 108, "mipmap-hdpi": 162, "mipmap-xhdpi": 216,
    "mipmap-xxhdpi": 324, "mipmap-xxxhdpi": 432,
}


def make_icons():
    src = Image.open(ICO_SRC).convert("RGBA")
    for folder, px in DENSITIES.items():
        d = os.path.join(RES, folder)
        os.makedirs(d, exist_ok=True)
        img = src.resize((px, px), Image.LANCZOS)
        img.save(os.path.join(d, "ic_launcher.png"))
        img.save(os.path.join(d, "ic_launcher_round.png"))
    print(f"  图标 {len(DENSITIES) * 2} 个 → res/mipmap-*")

    # 自适应图标前景：原图缩到 72%（安卓裁切时四周会各留 18%）
    for folder, px in FG_DENSITIES.items():
        d = os.path.join(RES, folder)
        os.makedirs(d, exist_ok=True)
        inner = int(px * 0.72)
        fg = src.resize((inner, inner), Image.LANCZOS)
        canvas = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        canvas.paste(fg, ((px - inner) // 2, (px - inner) // 2), fg)
        canvas.save(os.path.join(d, "ic_launcher_fg.png"))
    print(f"  自适应前景 {len(FG_DENSITIES)} 个 → res/mipmap-*/ic_launcher_fg.png")


def make_splash_logo():
    """
    冷启动窗口中央的那张图。

    ★ 必须是一张**独立的普通 PNG**，不能复用 @mipmap/ic_launcher：
      那个名字在 Android 8.0+ 会解析到 mipmap-anydpi-v26 里的
      <adaptive-icon> XML，而 drawable/splash_window.xml 用的是
      <bitmap>，喂 XML 给它必然抛
          XmlPullParserException: <bitmap> requires a valid 'src' attribute
      —— 表现就是「点开即闪退、没有弹窗」（详见 splash_window.xml 注释）。

    放到 drawable-xxhdpi：384px ÷ 3 = 128dp，正好是启动页图标的常见尺寸。
    """
    src = Image.open(ICO_SRC).convert("RGBA")
    d = os.path.join(RES, "drawable-xxhdpi")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, "splash_logo.png")
    src.resize((384, 384), Image.LANCZOS).save(out)
    print(f"  启动图 → drawable-xxhdpi/splash_logo.png (384×384)")


def make_cover():
    os.makedirs(WEB_ASSETS, exist_ok=True)
    im = Image.open(COVER_SRC).convert("RGB")
    w, h = im.size
    # 封面页在竖屏上显示，压到 1080 宽足够；顺带按 4:5 裁一下更好看
    target_w = 1080
    if w > target_w:
        im = im.resize((target_w, int(h * target_w / w)), Image.LANCZOS)
    out = os.path.join(WEB_ASSETS, "cover.jpg")
    im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    print(f"  封面 → web/assets/cover.jpg  "
          f"({im.size[0]}×{im.size[1]}, {os.path.getsize(out) / 1024:.0f}KB)")


def make_web_icons():
    """PWA / 网页 favicon 用的小图。"""
    os.makedirs(WEB_ASSETS, exist_ok=True)
    src = Image.open(ICO_SRC).convert("RGBA")
    src.resize((192, 192), Image.LANCZOS).save(
        os.path.join(WEB_ASSETS, "icon-192.png"))
    src.resize((512, 512), Image.LANCZOS).save(
        os.path.join(WEB_ASSETS, "icon-512.png"))
    print("  网页图标 → web/assets/icon-{192,512}.png")


def make_font_subset_hint():
    """
    萝莉体.ttf 有 11MB，全量塞进 assets 太大。
    这里只做一件事：确认文件在位，真正的大小优化在 README 里说明。
    """
    p = os.path.join(ROOT, "core_data", "fonts", "萝莉体.ttf")
    if not os.path.isfile(p):
        print("  ⚠ 找不到 core_data/fonts/萝莉体.ttf —— 字体功能会退化")
        return
    print(f"  内置字体 {os.path.getsize(p) / 1024 / 1024:.1f}MB "
          f"→ core_data/fonts/萝莉体.ttf")


if __name__ == "__main__":
    for src, what in ((ICO_SRC, "start.ico"), (COVER_SRC, "玛俐大小姐.jpg")):
        if not os.path.isfile(src):
            sys.exit(f"✘ 找不到素材：{src}\n"
                     f"  请把 {what} 放到 {src}")
    print("生成图标与封面：")
    make_icons()
    make_splash_logo()
    make_cover()
    make_web_icons()
    make_font_subset_hint()
    print("完成。")