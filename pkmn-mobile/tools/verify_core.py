# -*- coding: utf-8 -*-
"""
手机版核心自检。

    python tools/verify_core.py

用途：
  ① 每次 sync_core.py 之后跑一遍，确认电脑版的改动没有把手机版带崩；
  ② 排查问题时先跑它 —— 它会把失败点精确到具体的函数和异常。

★ 它只依赖 tools/sync_core.py 同步出来的 core/，**不依赖任何 GUI / 网络**。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bootstrap  # noqa: E402  必须先引导路径

PASS, FAIL, WARN = "✔", "✘", "⚠"
_results = []


def report(ok, name, detail=""):
    _results.append((ok, name))
    print(f"  {PASS if ok is True else (WARN if ok is None else FAIL)} {name}"
          + (f"  — {detail}" if detail else ""))


def try_call(name, fn, expect_exc=False):
    """跑一个调用，返回结果或 None。"""
    try:
        val = fn()
        report(True, name, str(val)[:110] if val is not None else "")
        return val
    except Exception as e:
        report(False if not expect_exc else None, name,
               f"{type(e).__name__}: {e}")
        if not expect_exc:
            print(traceback.format_exc(limit=2))
        return None


def make_fake_game_dir():
    """造一个能通过 check_game_root 的最小目录。"""
    d = tempfile.mkdtemp(prefix="pkmn_fake_", dir=os.path.join(ROOT, "tmp"))
    os.makedirs(os.path.join(d, "Data"), exist_ok=True)
    with open(os.path.join(d, "Game.exe"), "wb") as f:
        f.write(b"fake")
    return d


def part1_modules():
    print("\n[1] 模块加载")
    st = bootstrap.status()
    for m, v in st["modules"].items():
        report(v == "ok", f"import {m}", "" if v == "ok" else v)
    report(st["data_exists"], "core_data/ 存在（引擎版本基准 JSON）")
    return st["missing"] == []


def part2_pure_functions():
    print("\n[2] 存档数值纯函数（不依赖存档文件）")
    try:
        import save_tools as ST
    except Exception as e:
        report(False, "import save_tools", str(e))
        return False

    # 50 级、种族值 60、个体 31、努力 252、无性格修正 → 应为某个确定值
    v = try_call("calc_stat(成长/HP)", lambda: ST.calc_stat(60, 50, 31, 252, 0, 0))
    try_call("calc_stat(攻击·固执加成)", lambda: ST.calc_stat(80, 50, 31, 252, 4, 1))
    try_call("growth_exp(50, medium)", lambda: ST.growth_exp(50, "Medium"))
    try_call("level_from_exp(反推等级)", lambda: ST.level_from_exp(125000, "Medium"))
    try_call("nature_boost(性格修正)", lambda: ST.nature_boost(4, 1))
    try_call("gender_of(性别判定)", lambda: ST.gender_of(123456, "AlwaysMale"))
    try_call("is_shiny(异色判定)", lambda: ST.is_shiny(1, 1))
    return v is not None


def part3_save_file():
    print("\n[3] 存档文件读取（喂坏数据，看能不能优雅报错而不是崩）")
    try:
        import save_tools as ST
    except Exception:
        return False
    bad = os.path.join(ROOT, "tmp", "bad.rxdata")
    os.makedirs(os.path.dirname(bad), exist_ok=True)
    with open(bad, "wb") as f:
        f.write(b"this is not marshal data at all")
    ok = False
    try:
        ST.open_save(bad)
        report(True, "open_save(坏数据)")
        ok = True
    except Exception as e:
        # 能抛出带说明的异常 = 正常；关键是异常类型可控、不炸到解释器
        report(None, "open_save(坏数据) 抛出可识别异常",
               f"{type(e).__name__}: {e}"[:110])
        ok = True
    return ok


def part4_debug_chain():
    print("\n[4] 开启 DEBUG 链路")
    try:
        import debug_tool as DT
        import game_scripts as GS
        import essentials_base as EB
    except Exception as e:
        report(False, "import debug 链路", str(e))
        return False

    d = make_fake_game_dir()
    out = []

    def emit(msg):
        out.append(msg)

    try_call("GS.check_game_root(假游戏目录)",
             lambda: GS.check_game_root(d))
    try_call("EB.detect_version(假游戏目录)",
             lambda: EB.detect_version(d))
    try_call("EB.compare(版本比对)",
             lambda: EB.compare(d, emit=emit))

    rep = try_call("DT.status(查询 DEBUG 状态)",
                   lambda: DT.status(d))

    # 真跑一次 enable_debug：假目录里没有 mainFunction，预期是「干净地失败」
    try:
        r = DT.enable_debug(d, emit=emit)
        detail = f"ok={r.get('ok')} changed={r.get('changed')} reason={r.get('reason')!r}"
        report(r.get("ok") in (True, False), "DT.enable_debug(假目录)", detail[:110])
    except Exception as e:
        report(False, "DT.enable_debug 抛出未捕获异常",
               f"{type(e).__name__}: {e}"[:110])
        return False

    try_call("DT.list_backups(备份列表)", lambda: DT.list_backups(d))

    # DT.status 的报告字段是 version/has_main/debug_on/...，不含 ok
    if isinstance(rep, dict):
        report("has_main" in rep and "debug_on" in rep,
               "status() 返回结构化报告",
               f"字段: {', '.join(list(rep)[:8])}")
    else:
        report(False, "status() 返回结构化报告", f"返回值类型异常: {type(rep)}")

    shutil.rmtree(d, ignore_errors=True)
    return True


def main():
    os.makedirs(os.path.join(ROOT, "tmp"), exist_ok=True)
    print("=" * 62)
    print("手机版核心自检")
    print("=" * 62)

    part1_modules()
    part2_pure_functions()
    part3_save_file()
    part4_debug_chain()

    bad = [n for ok, n in _results if ok is False]
    warn = [n for ok, n in _results if ok is None]
    print("\n" + "=" * 62)
    print(f"通过 {sum(1 for ok,_ in _results if ok is True)} 项"
          f" / 警告 {len(warn)} 项 / 失败 {len(bad)} 项")
    if bad:
        print("\n失败项：")
        for n in bad:
            print(f"   {FAIL} {n}")
    print("=" * 62)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
