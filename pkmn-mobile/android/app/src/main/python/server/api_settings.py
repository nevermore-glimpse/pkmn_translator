# -*- coding: utf-8 -*-
"""
外观偏好（目前只有夜间模式）的持久化。

★ 为什么要存后端而不是浏览器 localStorage：

    WebView 每次启动，MainActivity 都用**随机端口**起服务
    （`port=0` → 真实源是 http://127.0.0.1:<随机端口>），
    端口每次都变，于是浏览器的 localStorage 是按「源」隔离的，
    换个端口就等于换了个源，之前存的偏好读不到 —— 表现就是
    「退出工具再打开，夜间模式又变回白天」。

    所以偏好不能交给浏览器存，必须在**后端**落盘。后端跑在 App 私有目录
    （PKMN_HOME，路径一直稳定），用一个极小的 JSON 文件存：
        <PKMN_HOME>/settings.json
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bootstrap  # noqa: E402,F401

# 兄弟模块：按「自己是怎么被导入的」二选一（详见 server/app.py 的说明）
if __package__:
    from . import jsonutil as JU          # noqa: E402
else:
    import jsonutil as JU                 # E402


def _path():
    home = os.environ.get("PKMN_HOME")
    if not home:
        home = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "home", "data")
    return os.path.normpath(os.path.join(home, "settings.json"))


def _load():
    """读偏好文件；不存在 / 损坏都当空（白天模式）。"""
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(data):
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return True
    except OSError:
        return False


def api_get(ctx):
    """返回当前偏好。"""
    return JU.ok({"night": bool(_load().get("night", False))})


def api_set(ctx):
    """写入偏好。body: {"night": bool}"""
    body = ctx.get("body") or {}
    night = bool(body.get("night", False))
    data = _load()
    data["night"] = night
    if not _save(data):
        return JU.err("保存偏好失败（无法写入本机文件）")
    return JU.ok({"night": night})


def dispatch(ctx, action):
    table = {
        "get": api_get,
        "set": api_set,
    }
    fn = table.get(action)
    if not fn:
        return JU.err(f"未知的外观操作：{action}")
    try:
        return fn(ctx)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JU.err(f"{type(e).__name__}: {e}")
