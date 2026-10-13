# -*- coding: utf-8 -*-
"""
字体替换：植入「中文文本处理」插件，并把游戏字体换成内置的萝莉体。

这一整套逻辑电脑版在 `plugin_tools.py` 里已经写透了，手机版直接复用 ——
本文件只做三件事：

    1. 把内置字体（萝莉体.ttf）作为默认值传进去
    2. 让用户也能从自己手机上挑一个 .ttf（走 /api/fs 里已有的文件选择）
    3. 把长任务的日志接到 SSE 上

为什么要装插件而不是只换字体
----------------------------
RPG Maker Essentials 用 RMVX 的 `Font.default_color` 那套位图字体渲染，
直接改引擎字体常量的话，很多对话框还是显示方块。插件的做法是把字体名写进
`Font.default_name`，让引擎走 TTF 字体渲染路径 —— 这是 Essentials 生态里
公认的解法，电脑版实测有效。

关键函数（core/plugin_tools.py，全部原生支持 emit 回调）：
    check_compat(game_dir)    → 认版本、挑插件变体、决定植入路径
    install_plugin(dir, font) → 植入插件 + 换字体 + 改引擎字体定义
    restore_plugin(dir)        → 完整还原（插件、字体、引擎改动）
    scan_plugins(dir)          → 看当前装了什么
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bootstrap  # noqa: E402,F401

# 兄弟模块：按「自己是怎么被导入的」二选一（详见 server/app.py 的说明）
if __package__:
    from . import jsonutil as JU     # noqa: E402
    from . import tasks              # noqa: E402
else:
    import jsonutil as JU            # noqa: E402
    import tasks                     # noqa: E402


def _load():
    try:
        import plugin_tools as PT
        import config
        return PT, config
    except Exception as e:
        raise RuntimeError(f"核心模块加载失败：{type(e).__name__}: {e}") from e


def _dir(src, key="dir"):
    d = JU.normalize_path(src.get(key))
    if not d:
        raise ValueError("缺少参数 dir（游戏根目录）")
    return d


# ------------------------------------------------------------------
# 同步接口
# ------------------------------------------------------------------
def api_fonts(ctx):
    """
    列出可用字体。

    内置字体永远排第一（萝莉体），后面跟用户自己放在工作目录 fonts/ 下的
    .ttf / .otf。这样用户在手机上装字体不用挑路径 —— 放进去就能看到。
    """
    PT, config = _load()
    out = []

    builtin = getattr(config, "FONT_FILE", "")
    if builtin and os.path.isfile(builtin):
        try:
            fam = PT.ttf_family_name(builtin)
        except Exception:
            fam = getattr(config, "FONT_NAME", "")
        out.append({
            "path": builtin,
            "name": os.path.splitext(os.path.basename(builtin))[0],
            "family": fam or "Lolita",
            "builtin": True,
            "size": os.path.getsize(builtin),
        })

    # 用户自备字体：<工作目录>/fonts/
    user_dir = os.path.join(getattr(config, "BASE_DIR", ""), "fonts")
    if os.path.isdir(user_dir):
        for fn in sorted(os.listdir(user_dir)):
            if not fn.lower().endswith((".ttf", ".otf", ".ttc")):
                continue
            p = os.path.join(user_dir, fn)
            try:
                fam = PT.ttf_family_name(p)
            except Exception:
                fam = None
            out.append({
                "path": p,
                "name": os.path.splitext(fn)[0],
                "family": fam or "",
                "builtin": False,
                "size": os.path.getsize(p),
            })

    return JU.ok({"fonts": out, "builtin": builtin,
                  "user_dir": user_dir})


def api_scan(ctx):
    """看当前游戏里装了什么插件、字体设成了什么。"""
    PT, _ = _load()
    d = _dir(ctx["query"])
    try:
        rep = PT.scan_plugins(d)
    except Exception as e:
        return JU.err(f"扫描失败：{e}")
    return JU.ok(JU.clean(rep))


def api_compat(ctx):
    """预检：这个游戏该用哪个插件版本、走哪条植入路径、缺不缺引擎 API。"""
    PT, _ = _load()
    d = _dir(ctx["query"])
    try:
        rep = PT.check_compat(d)
    except Exception as e:
        return JU.err(f"预检失败：{e}")
    return JU.ok(JU.clean(rep))


# ------------------------------------------------------------------
# 异步接口
# ------------------------------------------------------------------
def api_install(ctx):
    """
    植入插件并替换字体。

    body:
        dir     游戏根目录
        font    字体文件路径（.ttf）；不传就用内置萝莉体
        adaptive 是否按版本自适应（默认 true）
    """
    body = ctx["body"]
    d = _dir(body)
    PT, config = _load()

    font = (body.get("font") or "").strip()
    if not font:
        font = getattr(config, "FONT_FILE", "")
        if not font or not os.path.isfile(font):
            return JU.err("内置字体缺失，无法继续")
    font = JU.normalize_path(font)
    if not os.path.isfile(font):
        return JU.err(f"找不到字体文件：{font}")

    adaptive = bool(body.get("adaptive", True))

    def job(emit, progress, cancelled):
        emit(f"[字体] 使用字体：{os.path.basename(font)}")
        rep = PT.install_plugin(d, font_file=font, emit=emit,
                                adaptive=adaptive)
        return JU.clean(rep)

    t = tasks.create("替换字体", job)
    return JU.ok({"task_id": t.id, "font": font})


def api_restore(ctx):
    """还原：移除插件、恢复字体、撤销引擎改动。"""
    body = ctx["body"]
    d = _dir(body)
    PT, _ = _load()

    def job(emit, progress, cancelled):
        return JU.clean(PT.restore_plugin(d, emit=emit))

    t = tasks.create("还原字体", job)
    return JU.ok({"task_id": t.id})


def dispatch(ctx, action):
    table = {
        "fonts": api_fonts,
        "scan": api_scan,
        "compat": api_compat,
        "install": api_install,
        "restore": api_restore,
    }
    fn = table.get(action)
    if not fn:
        return JU.err(f"未知的字体操作：{action}")
    try:
        return fn(ctx)
    except ValueError as e:
        return JU.err(str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JU.err(f"{type(e).__name__}: {e}")