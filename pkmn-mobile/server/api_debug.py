# -*- coding: utf-8 -*-
"""
开启 DEBUG / 关闭还原 / 备份恢复。

全部直接调用 core/debug_tool.py 与 core/engine_tools.py 的原生 API ——
那些函数本来就把 emit 预留好了（`enable_debug(game_dir, emit=None, ...)`），
这里的活儿只是把它接到 SSE 队列上：

    DT.enable_debug(dir, emit=emit)      → emit 每次都往队列塞一行
    GET /api/task/{id}/stream            → 前端实时看到过程

★ 开启方式①–⑦ 与电脑版 gui.py 的下拉框**一一对应**（见下面的 MODES）。
  分支逻辑照抄 gui.py 里 `_do_debug_enable` 的 work()，包括
  「只有方式① 才写 $DEBUG=true」这条容易忽略的规则。
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


# ================================================================
# 开启方式（与电脑版 gui.py 的 _debug_mode_labels 对齐）
# ================================================================
# ★ 电脑版还有「⑧ 调试启动器」—— 那是生成 Windows 的 exe，手机上做不到，
#   所以这里不列。其余①–⑦ 全部实现。
MODES = [
    {
        "key": "main",
        "label": "① 通用（写 Main，启动即调试）",
        "desc": "在 Main 的 mainFunction 里写 $DEBUG=true —— 进游戏就是调试模式。\n"
                "★ 这是**唯一**会开 $DEBUG 的方式；②–⑦ 都不会写 $DEBUG，"
                "需要 $DEBUG 时请用本方式。",
    },
    {
        "key": "keys",
        "label": "② 删条件（F9/队伍/穿墙 免 $DEBUG 可用）",
        "desc": "把各处「需要 $DEBUG 才生效」的条件删掉，让这些功能无条件可用"
                "（F9 存档、队伍界面、穿墙等）。\n"
                "自动认版本：v16/v17 的 `if $DEBUG and Input.press?(…)`、"
                "v18 起的 `return true if $DEBUG && …`、`… if $DEBUG`、"
                "`\"condition\" => proc { … $DEBUG }` 都认。\n"
                "★ 本方式不设 $DEBUG，还会把以前留下的清掉。",
    },
    {
        "key": "special",
        "label": "③ F6 键（按 F6 直接开调试 + 提示）",
        "desc": "改写 F6 键分支：按下 F6 **直接** $DEBUG = true 并弹窗提示"
                "（不再判断 !$DEBUG，按下去就提示）。",
    },
    {
        "key": "special_menu",
        "label": "④ F6 键（按 F6 直接开调试菜单）",
        "desc": "③ 的菜单版 —— 按 F6 不只设 $DEBUG，还直接打开调试菜单。",
    },
    {
        "key": "repel",
        "label": "⑤ 除虫喷雾（用喷雾即设 $DEBUG）",
        "desc": "在除虫喷雾 pbRepel 开头注入：$DEBUG 不为真就设为真。",
    },
    {
        "key": "repel_menu",
        "label": "⑥ 除虫喷雾（用喷雾即开调试菜单）",
        "desc": "⑤ 的菜单版 —— 用一次除虫喷雾直接打开调试菜单。",
    },
    {
        "key": "rewrite",
        "label": "⑦ 改名调试函数（顶掉原函数，按 T 开菜单）",
        "desc": "把官方基准里的调试函数整套改名，顶掉游戏里的原函数，"
                "再把全库调用点一起改名，并按版本注册 T 键。\n"
                "★ 全程**不设 $DEBUG** —— 有些游戏的反调试里有 `exit if $DEBUG`，"
                "一设就退游戏。反调试特别狠时用这条。",
    },
]

MODE_KEYS = tuple(m["key"] for m in MODES)


def _load_core():
    try:
        import debug_tool as DT
        import engine_tools as ET
        import essentials_base as EB
        import game_scripts as GS
        return DT, ET, EB, GS
    except Exception as e:
        raise RuntimeError(f"核心模块加载失败：{type(e).__name__}: {e}") from e


def _dir(body_or_query, key="dir"):
    d = JU.normalize_path(body_or_query.get(key))
    if not d:
        raise ValueError("缺少参数 dir（游戏根目录）")
    return d


def _mode_label(key):
    for m in MODES:
        if m["key"] == key:
            return m["label"]
    return key


# ------------------------------------------------------------------
# 同步接口
# ------------------------------------------------------------------
def api_modes(ctx):
    """开启方式清单 —— 前端拿它填下拉框，避免前后端各维护一份。"""
    return JU.ok({"modes": MODES})


def api_status(ctx):
    """查询当前 DEBUG 状态，返回结构化报告。"""
    DT, _ET, _EB, GS = _load_core()
    d = _dir(ctx["query"])
    valid, why = GS.check_game_root(d)
    if not valid:
        return JU.err(why)
    rep = DT.status(d)
    return JU.ok({
        "dir": d.replace("\\", "/"),
        "version": rep.get("version") or "（读不到版本号）",
        "debug_on": rep.get("debug_on"),
        "has_main": rep.get("has_main"),
        "report": JU.clean(rep),
    })


def api_backups(ctx):
    DT, _ET, _EB, _GS = _load_core()
    d = _dir(ctx["query"])
    return JU.ok({"backups": JU.clean(DT.list_backups(d))})


def api_antidebug(ctx):
    """
    列出「疑似反调试」代码 —— **只看不改**。

    ★ 手机上不自动注释反调试：电脑版会弹一个复核窗口让用户看代码再决定，
      手机没有那个窗口，所以这里把可疑代码原样返回给前端，
      由前端弹窗让用户选「自动注释 / 跳过 / 取消」，选择再随
      `/api/debug/enable` 的 `antidebug` 参数传回来。
    """
    DT, _ET, _EB, GS = _load_core()
    d = _dir(ctx["query"])
    valid, why = GS.check_game_root(d)
    if not valid:
        return JU.err(why)
    try:
        srcs = DT.find_antidebug_sources(d)
    except Exception as e:                                  # noqa: BLE001
        return JU.err(f"扫描反调试代码失败：{type(e).__name__}: {e}")
    out = []
    for s in srcs:
        try:
            code = DT.block_text(s["text"], s["blocks"])
            preview = DT.region_text(s["text"], s["blocks"], 3)
        except Exception:                                   # noqa: BLE001
            code = preview = ""
        out.append({
            "key": DT.src_key(s),
            "name": s.get("name") or "",
            "mode": s.get("mode") or "",
            "where": str(s.get("key") or s.get("path") or ""),
            "blocks": len(s.get("blocks") or []),
            "code": code,
            "preview": preview,
        })
    return JU.ok({"sources": out, "count": len(out)})


# ------------------------------------------------------------------
# 异步接口（返回 task_id，前端连 SSE 看过程）
# ------------------------------------------------------------------
def api_enable(ctx):
    body = ctx["body"]
    d = _dir(body)
    DT, ET, _EB, _GS = _load_core()

    mode = (body.get("mode") or "main").strip()
    if mode not in MODE_KEYS:
        return JU.err(f"未知的开启方式：{mode}（可选：{', '.join(MODE_KEYS)}）")

    # 勾选项（默认值跟电脑版一致）；「自动关闭全量编译」已取消：不再传 guard
    force = bool(body.get("force", True))

    # ★ 反调试怎么处理，由用户在弹窗里选（见 api_antidebug）：
    #     body["antidebug"] = {src_key: "comment" | "skip", ...}
    #                       或 "cancel"（用户点了取消 → 整个操作中止）
    #   没传 / 传别的 → **默认不注释**（用户明确要求：不自动注释）。
    ad_decisions = body.get("antidebug")
    if ad_decisions == "cancel":
        return JU.ok({"task_id": None, "cancelled": True,
                      "message": "已取消（反调试复核里点了「取消」）"})

    def _build_antidebug_plan(DT, d, emit):
        """按用户的选择拼出 enable_debug 需要的 antidebug_plan。"""
        try:
            srcs = DT.find_antidebug_sources(d)
        except Exception as e:                              # noqa: BLE001
            emit(f"[DEBUG] ⚠ 扫描反调试代码失败（跳过反调试处理）：{e}")
            return None
        if not srcs:
            return None
        plan = {}
        chosen = ad_decisions if isinstance(ad_decisions, dict) else {}
        for s in srcs:
            k = DT.src_key(s)
            act = chosen.get(k)
            nm = s.get("name") or k
            if act == "comment":
                dec = DT.antidebug_decision(s["text"], s["blocks"], 3)
                dec["action"] = "comment"
                plan[k] = dec
                emit(f"[DEBUG] · 反调试「{nm}」：按你的选择**自动注释**"
                     f"（{len(s.get('blocks') or [])} 处）")
            else:
                plan[k] = {"action": "skip"}
                emit(f"[DEBUG] · 反调试「{nm}」："
                     + ("按你的选择**跳过**" if act == "skip"
                        else "未收到你的选择 → **不注释**（默认不改反调试）"))
        return plan

    def job(emit, progress, cancelled):
        emit(f"[DEBUG] 开始处理：{d}")
        emit(f"[DEBUG] 开启方式：{_mode_label(mode)}")
        emit(f"[DEBUG] 忽略引擎改动={force}（全量编译不再自动关闭）")

        ad_plan = _build_antidebug_plan(DT, d, emit)

        rep = DT.enable_debug(
            d, emit=emit, force=force,
            # ★ 只有方式①（通用）才往 pbCallTitle 第一行写 $DEBUG=true。
            #   方式② 的做法本来就是把「需要 $DEBUG 才生效」的判定删掉，
            #   再写一个 $DEBUG=true 是画蛇添足；方式⑦ 更不能设 ——
            #   反调试里有 `exit if $DEBUG`。
            #   电脑版 gui.py 也是这么判断的（write_debug=(mode == "main")）。
            write_debug=(mode == "main"),
            antidebug_plan=ad_plan,
        )
        rep["mode"] = mode
        rep["mode_label"] = _mode_label(mode)

        # ---------- 按方式追加对应改动（照抄 gui.py 的分支） ----------
        try:
            if mode == "keys":
                rep["mode_res"] = ET.patch_remove_debug_conditions(d, emit=emit)
            elif mode in ("special", "special_menu"):
                rep["mode_res"] = ET.patch_special_key(d, mode, emit=emit)
            elif mode in ("repel", "repel_menu"):
                rep["mode_res"] = ET.patch_repel(
                    d, mode, version=rep.get("version"), emit=emit)
            elif mode == "rewrite":
                rep["mode_res"] = ET.patch_rewrite_debug_func(
                    d, version=rep.get("version"), emit=emit)
        except Exception as e:                                    # noqa: BLE001
            rep["mode_error"] = f"{type(e).__name__}: {e}"
            emit(f"[DEBUG] ⚠ 方式执行失败：{e}")

        # 方式② 一个条件都没认出来时给出可操作的下一步。
        # 电脑版这时会弹窗问「要不要按官方基准补行」，手机上没有那套复核界面，
        # 就把建议直接写进日志。
        if mode == "keys" and not (rep.get("mode_res") or {}).get("changed"):
            emit("[DEBUG] ⚠ 方式②：一处「需要 $DEBUG 才生效」的条件都没认出来。")
            emit("[DEBUG]   多半是作者把那些判断改掉/删掉了 —— "
                 "可以先到「基准覆盖」页把 debug 函数覆盖回官方版，再回来试方式②。")

        return JU.clean(rep)

    t = tasks.create("开启DEBUG", job)
    return JU.ok({"task_id": t.id})


def api_disable(ctx):
    """关掉 DEBUG（移除写进 pbCallTitle / 旧版 mainFunction 的 $DEBUG=true），
    不动反调试。"""
    DT, _ET, _EB, _GS = _load_core()
    body = ctx["body"]
    d = _dir(body)

    def job(emit, progress, cancelled):
        rep = DT.remove_debug_from_main(d, emit=emit)
        return JU.clean(rep)

    t = tasks.create("关闭DEBUG", job)
    return JU.ok({"task_id": t.id})


def api_restore(ctx):
    """从自动备份整体还原。"""
    DT, _ET, _EB, _GS = _load_core()
    body = ctx["body"]
    d = _dir(body)

    def job(emit, progress, cancelled):
        rep = DT.restore(d, emit=emit)
        return JU.clean(rep)

    t = tasks.create("还原备份", job)
    return JU.ok({"task_id": t.id})


def dispatch(ctx, action):
    table = {
        "modes": api_modes,
        "status": api_status,
        "antidebug": api_antidebug,
        "enable": api_enable,
        "disable": api_disable,
        "restore": api_restore,
        "backups": api_backups,
    }
    fn = table.get(action)
    if not fn:
        return JU.err(f"未知的 debug 操作：{action}")
    try:
        return fn(ctx)
    except ValueError as e:
        return JU.err(str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JU.err(f"{type(e).__name__}: {e}")
