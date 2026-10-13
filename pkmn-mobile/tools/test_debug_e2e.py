# -*- coding: utf-8 -*-
"""
DEBUG 端到端测试：造一个**像真的那样**的游戏目录，真的写进去，再读回来比对。

    python tools/test_debug_e2e.py

前面的 verify_core / smoke_api 只证明「接口能通」，这里证明「功能真的对」：
    $DEBUG=true 有没有真的写进 mainFunction
    幂不幂等（再点一次不会写两遍）
    关闭能不能干净地清掉
    备份有没有落下
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bootstrap  # noqa: E402,F401

_res = []


def report(ok, name, detail=""):
    _res.append(ok)
    print(f"  {'✔' if ok else '✘'} {name}" + (f"  — {detail}" if detail else ""))


MAIN_SRC = """def pbSetUpSystem
  Graphics.frame_rate = 40
end

def mainFunction
  begin
    pbSetUpSystem
    Graphics.update
  rescue Hangup
  end
end
"""


def build_game():
    """造一个能通过 check_game_root 且带 Data/Scripts.rxdata 的假游戏。"""
    # rubymarshal 的序列化入口是 writer.writes（顶层模块不导出 dumps）
    from rubymarshal.writer import writes

    d = tempfile.mkdtemp(prefix="e2e_game_", dir=os.path.join(ROOT, "tmp"))
    os.makedirs(os.path.join(d, "Data"), exist_ok=True)
    with open(os.path.join(d, "Game.exe"), "wb") as f:
        f.write(b"fake executable")

    # ★ 注意：core 里有条规则 —— rxdata 少于 10 条就当成「解包后留下的占位」，
    #   不予采用（见 game_scripts.collect_scripts 的说明）。所以这里必须补足 ≥10 条，
    #   否则 find_main_sources 会直接找不到 Main。
    filler_names = [b"Settings", b"PBDebug", b"Pokemon_Sprites",
                    b"PScreen_Party", b"PScreen_Bag", b"PBattle_Battler",
                    b"UI_Timer", b"Scene_Map", b"Strings"]
    entries = [[100000, b"Ze_Marker", zlib.compress(b"\n")]]   # 空标记，应被跳过
    for i, nm in enumerate(filler_names):
        entries.append([100001 + i, nm, zlib.compress(
            f"# filler {nm.decode()}\n".encode("utf-8"))])
    # Main 放最后
    entries.append([100900, b"Main", zlib.compress(MAIN_SRC.encode("utf-8"))])
    blob = writes(entries)
    with open(os.path.join(d, "Data", "Scripts.rxdata"), "wb") as f:
        f.write(blob)
    return d


def read_main_text(game_dir):
    """把 Scripts.rxdata 里 Main 那条的源文本读回来。"""
    import game_scripts as GS
    entries, total = GS.read_rxdata_entries(
        os.path.join(game_dir, "Data", "Scripts.rxdata"))
    for idx, title, text in entries:
        if str(title).strip().lower() == "main":
            return text
    return None


def main():
    os.makedirs(os.path.join(ROOT, "tmp"), exist_ok=True)
    import debug_tool as DT
    import game_scripts as GS

    game = build_game()
    print("=" * 62)
    print(f"DEBUG 端到端测试\n  假游戏目录 {game}")
    print("=" * 62)

    try:
        # ---------- 0. 前提 ----------
        ok_, why = GS.check_game_root(game)
        report(ok_, "假游戏目录通过 check_game_root", why)

        main_text = read_main_text(game)
        report(main_text is not None, "能从 Scripts.rxdata 读回 Main 脚本")
        if main_text is None:
            return 1
        report("def mainFunction" in main_text,
               "Main 脚本里含有 def mainFunction")
        report("$DEBUG" not in main_text, "初始状态没有 $DEBUG=true")

        # ---------- 1. 开启 ----------
        logs = []
        rep = DT.enable_debug(game, emit=logs.append)
        report(bool(rep.get("ok")), "enable_debug 返回 ok=True",
               rep.get("reason", "")[:90])
        print(f"     日志 {len(logs)} 行")

        after = read_main_text(game)
        report("$DEBUG=true" in (after or ""),
               "★ $DEBUG=true 真的写进了 mainFunction",
               f"写入后包含标记 = {'$DEBUG=true' in (after or '')}")
        report((after or "").count("$DEBUG") == 1,
               "只写了一行，没有重复插入")

        st = DT.status(game)
        report(st.get("debug_on") is True, "status() 显示 debug_on=True")

        # ---------- 2. 幂等 ----------
        rep2 = DT.enable_debug(game, emit=lambda m: None)
        after2 = read_main_text(game)
        report((after2 or "").count("$DEBUG") == 1,
               "★ 再点一次开启不会重复写入（幂等）")

        # ---------- 3. 备份 ----------
        baks = DT.list_backups(game)
        report(len(baks) > 0, f"留有备份（{len(baks)} 个）")

        # ---------- 4. 关闭 ----------
        DT.remove_debug_from_main(game, emit=lambda m: None)
        after3 = read_main_text(game)
        report("$DEBUG" not in (after3 or ""),
               "★ 关闭 DEBUG 后干净移除 $DEBUG=true")
        st3 = DT.status(game)
        report(not st3.get("debug_on"), "status() 显示 debug_on=False")

        # ---------- 5. 还原 ----------
        DT.restore(game, emit=lambda m: None)
        report(True, "restore() 未抛异常")

    except Exception as e:
        import traceback
        traceback.print_exc()
        report(False, f"抛出异常：{type(e).__name__}: {e}")
    finally:
        shutil.rmtree(game, ignore_errors=True)

    bad = _res.count(False)
    print("\n" + "=" * 62)
    print(f"通过 {len(_res) - bad} 项 / 失败 {bad} 项")
    print("=" * 62)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
