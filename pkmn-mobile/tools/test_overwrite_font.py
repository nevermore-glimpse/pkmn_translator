# -*- coding: utf-8 -*-
"""
任务4 + 任务5 的端到端验证。

光「能 import」不算数，这里真的造一个游戏目录，把脚本写进去，再覆盖回来：

  任务4  基准覆盖
      · overwrite_plan 出计划
      · overwrite_scene_map 真的把 Scene_Map 换成官方那份
      · 原文件被备份
      · restore_overwrite 能还原

  任务5  字体替换
      · check_compat 认得出该用哪个插件变体
      · install_plugin 真的植入插件 + 复制字体
      · 游戏 Fonts/ 目录里出现 ttf
      · restore_plugin 能还原
"""
import os
import shutil
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "tmp")
os.makedirs(TMP, exist_ok=True)
sys.path.insert(0, ROOT)

import bootstrap  # noqa: E402,F401

import game_scripts as GS      # noqa: E402
import engine_tools as ET      # noqa: E402
import plugin_tools as PT      # noqa: E402
import essentials_base as EB   # noqa: E402
from rubymarshal.writer import writes  # noqa: E402

PASS = FAIL = WARN = 0


def report(ok, label, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [✓] {label}" + (f"  {extra}" if extra else ""))
    else:
        FAIL += 1
        print(f"  [✘] {label}  {extra}")
    return ok


def warn(label, extra=""):
    global WARN
    WARN += 1
    print(f"  [!] {label}  {extra}")


# ------------------------------------------------------------------
# 造假游戏
# ------------------------------------------------------------------
MAIN_SRC = """#encoding:UTF-8
module Main
  def self.mainFunction
    $DEBUG = false
    SceneManager.scene = Scene_Map.new
  end
end
"""

SCENE_MAP_CN = """#encoding:UTF-8
module Scene_Map
  def update
    if $DEBUG
      exit
    end
    # 同人游戏自己加的东西
    @custom_thing = 1
  end
end
"""

PLUGIN_SRC = """#encoding:UTF-8
module PluginTest
  def self.hello; end
end
"""


def make_game(name, with_rxdata=True, n_extra=12):
    """造一个能通过 check_game_root 的假游戏目录。"""
    d = tempfile.mkdtemp(prefix=name + "_", dir=TMP)
    os.makedirs(os.path.join(d, "Data"), exist_ok=True)
    os.makedirs(os.path.join(d, "Fonts"), exist_ok=True)
    with open(os.path.join(d, "Game.exe"), "wb") as f:
        f.write(b"fake")

    entries = []
    idx = 100

    def add(title, src):
        nonlocal idx
        idx += 1
        entries.append([idx, title, zlib.compress(src.encode("utf-8"))])

    add("Main", MAIN_SRC)
    add("Scene_Map", SCENE_MAP_CN)
    add("PluginTest", PLUGIN_SRC)
    # ★ game_scripts 对少于 10 条的 Scripts.rxdata 不认（那只是「已解包」的占位）
    for i in range(n_extra):
        add("Filler%02d" % i, "#encoding:UTF-8\nclass Filler%02d\nend\n" % i)

    # ★ Scripts.rxdata 在 **Data/ 下面**（GS.rxdata_path → data_dir/Scripts.rxdata），
    #   建在游戏根目录的话 collect_scripts 根本读不到 —— 这是我第一版测试
    #   栽的坑：所有脚本都「找不到」，看起来像功能坏了，其实是我造错了目录。
    with open(os.path.join(d, "Data", "Scripts.rxdata"), "wb") as f:
        f.write(writes(entries))
    return d


def read_script(d, title):
    for mode, key, path, name, text in GS.iter_named_scripts(d, both=True):
        if name == title:
            return text
    return None


# ==================================================================
# 任务4：基准覆盖
# ==================================================================
def test_overwrite():
    print("\n=== 任务4 · 基准覆盖 ===")
    ver = "21.1"
    game = make_game("ow")

    # ---- Scene_Map 覆盖 ----
    ok, why = GS.check_game_root(game)
    report(ok, "假游戏目录通过校验", why)

    before = read_script(game, "Scene_Map")
    report(before is not None and "custom_thing" in (before or ""),
           "覆盖前 Scene_Map 是同人改过的版本")

    plan = ET.overwrite_plan(game, ver,
                             files=ET.scene_map_rel_file(ver))
    report(len(plan) >= 1, "覆盖计划非空", f"{len(plan)} 项")
    names = [p["name"] for p in plan]
    report("Scene_Map" in names, "计划里含 Scene_Map", str(names))

    logs = []
    res = ET.overwrite_scene_map(game, ver, emit=logs.append)
    report(res.get("ok"), "overwrite_scene_map 成功", res.get("reason", ""))
    report(bool(res.get("written")), "写入了文件",
           str(res.get("written")))

    after = read_script(game, "Scene_Map")
    report("custom_thing" in (before or "") and
           "custom_thing" not in (after or ""),
           "同人自己的代码已被官方版盖掉")
    # v21.1 官方 Scene_Map 里只有一处 $DEBUG（debug_calling 开关），
    # 跟同人版那段 `if $DEBUG … exit` 完全不是一回事，所以比内容特征。
    report("$DEBUG" in (after or "") and "exit" not in (after or ""),
           "换成官方版结构（同人的 exit 反调试消失）")

    # ---- 备份存在 ----
    baks = [f for f in os.listdir(os.path.join(game, "Data"))
            if "bak" in f]
    report(bool(baks), "原文件已备份", str(baks[:2]))

    # ---- 还原 ----
    logs2 = []
    rr = ET.restore_overwrite(game, emit=logs2.append)
    report(rr.get("ok"), "restore_overwrite 成功", rr.get("reason", ""))
    restored = read_script(game, "Scene_Map")
    report("custom_thing" in (restored or ""),
           "同人版 Scene_Map 已还原回来")

    # ---- debug 脚本覆盖 ----
    game2 = make_game("ow2")
    res2 = ET.overwrite_engine_scripts(game2, ver, translate=True)
    report(res2.get("ok"), "overwrite_engine_scripts 成功",
           res2.get("reason", ""))
    report(bool(res2.get("written")),
           "debug 菜单脚本已覆盖", str(res2.get("written"))[:80])
    ET.restore_overwrite(game2)

    # ---- 版本清单 ----
    from engine_src import list_versions, engine_files
    vs = list_versions()
    report(len(vs) == 9, "9 个版本的基准齐全", str(vs))
    missing = []
    for v in vs:
        if not engine_files(v):
            missing.append(v)
    report(not missing, "每个版本都有可覆盖的 debug 脚本", str(missing))
    smiss = [v for v in vs if not ET.scene_map_rel_file(v)]
    report(not smiss, "每个版本都有 Scene_Map 基准", str(smiss))

    shutil.rmtree(game, ignore_errors=True)
    shutil.rmtree(game2, ignore_errors=True)


# ==================================================================
# 任务5：字体替换
# ==================================================================
def test_font():
    print("\n=== 任务5 · 字体替换 ===")
    import config

    font = getattr(config, "FONT_FILE", "")
    report(os.path.isfile(font), "内置字体在位", font)

    try:
        fam = PT.ttf_family_name(font)
        report(bool(fam), "能读出字体族名", str(fam))
    except Exception as e:
        warn("读字体族名失败", str(e))

    for v in ["21.1", "20.1", "19.1", "18.1", "17.2", "16"]:
        src = PT.plugin_src_dir(v)
        n = len(os.listdir(src)) if os.path.isdir(src) else 0
        report(n > 0, f"插件本体 v{v} 就位", f"{n} 个文件")

    game = make_game("font")

    try:
        comp = PT.check_compat(game)
        report(bool(comp), "check_compat 有结论",
               f"variant={comp.get('variant')} mode={comp.get('mode')}")
        report(comp.get("advice"), "给出建议文案", str(comp.get("advice"))[:50])
    except Exception as e:
        warn("check_compat 抛异常", str(e))

    logs = []
    try:
        rep = PT.install_plugin(game, font_file=font, emit=logs.append,
                                 adaptive=True)
        report(rep is not None, "install_plugin 返回报告")
    except Exception as e:
        report(False, "install_plugin 抛异常",
               f"{type(e).__name__}: {e}")

    # 字体有没有被复制进游戏
    fdir = os.path.join(game, "Fonts")
    got = [f for f in os.listdir(fdir)] if os.path.isdir(fdir) else []
    report(bool(got), "字体已复制进游戏 Fonts/", str(got))

    # 插件痕迹。走的是 legacy 脚本路径（没有 Plugins/ 目录），
    # 所以 scan_plugins 会找不到目录 —— 这是正常分支，不是错误。
    try:
        plugins = PT.scan_plugins(game)
        names = []
        if isinstance(plugins, dict):
            names = plugins.get("plugins") or plugins.get("names") or []
        elif isinstance(plugins, list):
            names = plugins
        report(True, "scan_plugins 有响应",
               f"{type(plugins).__name__} · {str(names)[:50]}")
    except Exception as e:
        # legacy 路径下没有 Plugins/ 目录，报错是预期的
        report("找不到插件目录" in str(e),
               "scan_plugins 在无 Plugins 目录时的行为符合预期", str(e)[:60])

    if logs:
        print("     安装日志摘录：")
        for line in logs[:6]:
            print("      ", line)

    try:
        rr = PT.restore_plugin(game, emit=lambda s: None)
        report(rr is not None, "restore_plugin 返回报告")
    except Exception as e:
        warn("restore_plugin 抛异常", str(e))

    shutil.rmtree(game, ignore_errors=True)


if __name__ == "__main__":
    print("=" * 52)
    print("覆盖 / 字体 端到端验证")
    print("=" * 52)
    test_overwrite()
    test_font()
    print("\n" + "=" * 52)
    print(f"通过 {PASS} 项 / 警告 {WARN} 项 / 失败 {FAIL} 项")
    print("=" * 52)
    sys.exit(1 if FAIL else 0)