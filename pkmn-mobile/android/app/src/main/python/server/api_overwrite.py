# -*- coding: utf-8 -*-
"""
基准覆盖：用官方同版本脚本盖掉游戏里被改过的部分。

为什么需要它
------------
同人游戏常把引擎改得面目全非。最典型的两处：

  · **debug 函数** —— 把 F9 调试菜单的 `$DEBUG` 条件删了、或整份重写。
    于是「方式二：删 $DEBUG 条件」一条都认不出来。
  · **地图更新（Scene_Map）** —— 同人游戏几乎必改这个（自己的地图机制、
    天气、NPC 逻辑），改完之后 `if $DEBUG … end` 被拆散、变形，反调试清理
    也认不准。

把官方那份原封不动盖回去，就有了一个干净的落点。这两件事电脑版已经实现
（`engine_tools.overwrite_engine_scripts` / `overwrite_scene_map`），这里
只是把它们接到手机上，并把长任务的日志推到 SSE。

安全设计
--------
覆盖**先备份**（`.pkmn-overwrite-*.bak`），并且 `restore_overwrite` 能整体
还原。代价是：原作者对这些脚本的改动会被替换掉 —— 所以 UI 上必须让用户
明确知情，默认不勾。
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
        import engine_tools as ET
        import essentials_base as EB
        import game_scripts as GS
        return ET, EB, GS
    except Exception as e:
        raise RuntimeError(f"核心模块加载失败：{type(e).__name__}: {e}") from e


def _dir(src, key="dir"):
    d = JU.normalize_path(src.get(key))
    if not d:
        raise ValueError("缺少参数 dir（游戏根目录）")
    return d


def resolve_version(ET, EB, GS, game_dir, manual=""):
    """
    决定「用哪一版基准」—— 返回 (版本, 来源说明)；定不下来返回 ("", 原因)。

    优先级（对应 UI 上那个「版本」下拉）：
      ① **手动指定**：用户在下拉里选了具体版本 → 直接用，不猜；
      ② 游戏自报版本：读 `Essentials::VERSION`（`detect_version`）再映射到基准；
      ③ **指纹识别**：② 读不到（老游戏 / 魔改版常把版本号删了）时，
         拿游戏里的「脚本名 → 函数指纹」和每份基准逐一对，挑重合度最高的
         （`best_baseline`，要求 ≥50%）；
      ④ 都不行 → 返回空，调用方报错让用户手选。
    """
    manual = (manual or "").strip()
    if manual:
        return manual, f"手动指定 v{manual}"
    v = (EB.detect_version(game_dir) or "").strip()
    if v:
        base, exact = EB.pick_baseline_version(v)
        if base:
            return base, (f"游戏自报 v{v}"
                          + ("（与基准一致）" if exact else f" → 取基准 v{base}"))
    try:
        scripts = GS.collect_scripts(game_dir)
    except Exception:                                  # noqa: BLE001
        scripts = []
    ver, ratio = EB.best_baseline(scripts) if scripts else (None, 0.0)
    if ver:
        return ver, f"按脚本指纹识别 v{ver}（重合度 {ratio:.0%}）"
    if v:
        return "", f"游戏自报 v{v}，但工具里没有对应基准，请手动选一个版本"
    return "", "读不到版本号，指纹也认不出（引擎可能改得太狠），请手动选一个版本"


# ------------------------------------------------------------------
# 同步接口
# ------------------------------------------------------------------
def api_detect(ctx):
    """
    探测「该用哪版基准」，不写任何文件 —— 前端用它把下拉预选到识别出来的版本。
    """
    ET, EB, GS = _load()
    q = ctx["query"]
    d = _dir(q)
    valid, why = GS.check_game_root(d)
    if not valid:
        return JU.err(why)
    ver, why2 = resolve_version(ET, EB, GS, d, q.get("version") or "")
    return JU.ok({
        "detected": EB.detect_version(d) or "",
        "version": ver,
        "source": why2,
        "ok": bool(ver),
    })


def api_versions(ctx):
    """
    列出内置基准：哪些版本、每个版本能覆盖哪些脚本。

    前端用它决定「能不能覆盖」—— 版本不在表里就直接禁用按钮，
    别让用户点了才失败。
    """
    ET, EB, GS = _load()
    import engine_src as ES

    out = []
    for v in ES.list_versions():
        try:
            files = ES.engine_files(v)
            sm = ET.scene_map_rel_file(v)
        except Exception as e:
            continue
        out.append({
            "version": v,
            "debug_files": [os.path.basename(f) for f in files],
            "debug_count": len(files),
            "has_scene_map": bool(sm),
            "scene_map": [os.path.basename(x) for x in (sm or [])],
        })
    return JU.ok({
        "versions": out,
        "baselines": EB.list_baselines(),
    })


def api_plan(ctx):
    """
    预览覆盖计划（不写盘）：会动哪些脚本、目标在哪、有没有备份。

    UI 在执行前把这个表原样展示给用户看 —— 覆盖是不可逆操作（虽然有备份），
    必须让人知道将要发生什么。
    """
    ET, EB, GS = _load()
    q = ctx["query"]
    d = _dir(q)
    valid, why = GS.check_game_root(d)
    if not valid:
        return JU.err(why)

    ver = (q.get("version") or "").strip()
    kind = (q.get("kind") or "debug").strip()      # debug | scene_map

    if not ver:
        ver, why2 = resolve_version(ET, EB, GS, d)
        if not ver:
            return JU.err(why2)

    try:
        plan = ET.overwrite_plan(d, ver,
                                 files=ET.scene_map_rel_file(ver)
                                 if kind == "scene_map" else None)
    except Exception as e:
        return JU.err(f"生成计划失败：{e}")

    items = []
    for it in plan:
        tgt = it.get("target") or {}
        items.append({
            "kind": it.get("kind"),
            "name": it.get("name"),
            "has_target": bool(tgt),
            "where": str(tgt.get("path") or tgt.get("key") or ""),
            "mode": tgt.get("mode") or "",
            "will_create": not tgt and bool(it.get("create")),
        })
    return JU.ok({"dir": d, "version": ver, "kind": kind,
                  "items": items, "count": len(items)})


def api_backups(ctx):
    """列出本工具做过的覆盖备份。"""
    ET, _, _ = _load()
    d = _dir(ctx["query"])
    found = []
    mark = getattr(ET, "BAK_MARK", ".pkmn-overwrite-")
    for root, dirs, files in os.walk(d):
        # 别把整个游戏目录都翻一遍
        depth = os.path.relpath(root, d).count(os.sep)
        if depth > 3:
            dirs[:] = []
            continue
        for f in files:
            if mark in f and f.endswith(".bak"):
                found.append(os.path.join(root, f))
    found.sort()
    return JU.ok({"backups": found})


# ------------------------------------------------------------------
# 异步接口
# ------------------------------------------------------------------
def _run_overwrite(ctx, kind, title):
    body = ctx["body"]
    d = _dir(body)
    ET, EB, GS = _load()

    ver = (body.get("version") or "").strip()
    allow_missing = bool(body.get("allow_missing", False))

    def job(emit, progress, cancelled):
        if not ver:
            emit("[覆盖] 没指定版本 → 先读游戏自报版本，读不到就按脚本指纹识别…")
        use = ver
        if not use:
            use, why2 = resolve_version(ET, EB, GS, d)
            if not use:
                return JU.err(why2)
            emit(f"[覆盖] {why2}")
        emit(f"[覆盖] 使用官方 v{use} 基准")

        if kind == "scene_map":
            res = ET.overwrite_scene_map(d, use, emit=emit,
                                         allow_missing=allow_missing)
        else:
            res = ET.overwrite_engine_scripts(d, use, translate=True,
                                              emit=emit,
                                              allow_missing=allow_missing)
        return JU.clean(res)

    t = tasks.create(title, job)
    return JU.ok({"task_id": t.id})


def api_overwrite_debug(ctx):
    """用基准覆盖 debug 相关脚本（含中文菜单名）。"""
    return _run_overwrite(ctx, "debug", "覆盖debug函数")


def api_overwrite_scene_map(ctx):
    """用基准覆盖地图更新（Scene_Map）。"""
    return _run_overwrite(ctx, "scene_map", "覆盖地图更新")


def api_restore(ctx):
    """还原所有被覆盖的脚本。"""
    ET, _, _ = _load()
    d = _dir(ctx["body"])

    def job(emit, progress, cancelled):
        return JU.clean(ET.restore_overwrite(d, emit=emit))

    t = tasks.create("还原覆盖", job)
    return JU.ok({"task_id": t.id})


def dispatch(ctx, action):
    table = {
        "versions": api_versions,
        "detect": api_detect,
        "plan": api_plan,
        "overwrite_debug": api_overwrite_debug,
        "overwrite_scene_map": api_overwrite_scene_map,
        "restore": api_restore,
        "backups": api_backups,
    }
    fn = table.get(action)
    if not fn:
        return JU.err(f"未知的覆盖操作：{action}")
    try:
        return fn(ctx)
    except ValueError as e:
        return JU.err(str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JU.err(f"{type(e).__name__}: {e}")