# -*- coding: utf-8 -*-
"""
8 项端到端测试：把**七种开启方式**逐个跑一遍，验证它们真的写进了脚本。

    python tools/test_debug_modes.py

为什么单独写一个
---------------
`test_debug_e2e.py` 只覆盖了方式①（写 $DEBUG=true）。
方式②–⑦ 是照电脑版 gui.py 的分支搬过来的，最容易出错的地方有两个：

  ① **接错函数**：方式② 该调 engine_tools.patch_remove_debug_conditions，
     却调成了 patch_repel —— 这种错不会报错，只会「点了没反应」。
  ② **只有方式① 该写 $DEBUG=true**。②–⑦ 一旦也写了，方式⑦（改名调试函数）
     会被反调试的 `exit if $DEBUG` 直接踢出游戏 —— 电脑版专门为这条打过补丁。

所以这里对**每一种方式**都单独造一个假游戏（避免互相污染），
再断言：
    · 任务跑完、返回 mode 正确、enable_debug 本身 ok
    · 方式① 写出了 $DEBUG=true
    · **方式②–⑦ 一律没有写出 $DEBUG=true**（关键回归）
    · 各方式真的改到了目标脚本（$DEBUG 条件被删 / F6 分支被加 / pbRepel 被注入）
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bootstrap  # noqa: E402,F401

from server import app as APP  # noqa: E402

_res = []


def report(ok, name, detail=""):
    _res.append(ok)
    print(f"  {'✔' if ok else '✘'} {name}" + (f"  — {detail}" if detail else ""))


# ----------------------------------------------------------------
# 造一个「像真的那样」的假游戏
# ----------------------------------------------------------------
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

# 故意同时混进 v16 与 v18 两种写法，让方式②③ 都有东西可认
SCENE_MAP_SRC = """class Scene_Map
  def update
    if $DEBUG and Input.press?(Input::F9)
      $game_temp.debug_calling = true
    end
    $game_temp.debug_calling = true if $DEBUG
    if Input.trigger?(Input::F6)
      pbDebugMenu
    end
  end

  def pbDebugMenu
  end
end
"""

GAME_PLAYER_SRC = """class Game_Player
  def can_walk_through?
    if $DEBUG and Input.press?(Input::CTRL)
      return true
    end
    return false
  end
end
"""

ITEM_EFFECTS_SRC = """def pbRepel(item, itemUseType)
  return 3
end
"""

FILLERS = [b"Settings", b"PBDebug", b"Pokemon_Sprites", b"PScreen_Party",
           b"PScreen_Bag", b"PBattle_Battler", b"UI_Timer", b"Strings"]


def build_game(tag):
    """造一个能通过 check_game_root、且带各方式所需落点的假游戏。"""
    from rubymarshal.writer import writes

    d = tempfile.mkdtemp(prefix=f"modes_{tag}_", dir=os.path.join(ROOT, "tmp"))
    os.makedirs(os.path.join(d, "Data"), exist_ok=True)
    with open(os.path.join(d, "Game.exe"), "wb") as f:
        f.write(b"fake executable")

    # ★ rxdata 少于 10 条会被当成「解包后留下的占位」而不予采用
    #   （见 game_scripts.collect_scripts），所以必须凑够。
    entries = [[100000, b"Ze_Marker", zlib.compress(b"\n")]]
    for i, nm in enumerate(FILLERS):
        entries.append([100001 + i, nm, zlib.compress(
            f"# filler {nm.decode()}\n".encode("utf-8"))])
    for eid, name, src in ((100900, b"Main", MAIN_SRC),
                           (100901, b"Scene_Map", SCENE_MAP_SRC),
                           (100902, b"Game_Player", GAME_PLAYER_SRC),
                           (100903, b"Item_Effects", ITEM_EFFECTS_SRC)):
        entries.append([eid, name, zlib.compress(src.encode("utf-8"))])

    with open(os.path.join(d, "Data", "Scripts.rxdata"), "wb") as f:
        f.write(writes(entries))
    return d


def read_script(game_dir, name):
    import game_scripts as GS
    entries, _total = GS.read_rxdata_entries(
        os.path.join(game_dir, "Data", "Scripts.rxdata"))
    for _idx, title, text in entries:
        if str(title).strip().lower() == name.lower():
            return text
    return None


# ----------------------------------------------------------------
# HTTP + SSE
# ----------------------------------------------------------------
def post(path, body, port):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def run_task(port, path, body):
    """起一个 SSE 任务并等它跑完，返回 (最终 payload, 日志行列表)。"""
    r = post(path, body, port)
    if not r.get("ok"):
        return None, [str(r.get("message"))]
    tid = r["data"]["task_id"]
    logs, final = [], None
    with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/task/{tid}/stream", timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:].strip())
            if ev["type"] == "log":
                logs.append(str(ev["payload"]))
            elif ev["type"] == "done":
                final = ev["payload"]
                break
            elif ev["type"] == "error":
                logs.append("ERR " + str(ev["payload"]))
    return final, logs


# ----------------------------------------------------------------
MODES = ["main", "keys", "special", "special_menu", "repel", "repel_menu",
         "rewrite"]


def main():
    os.makedirs(os.path.join(ROOT, "tmp"), exist_ok=True)
    tmp_home = tempfile.mkdtemp(prefix="modes_home_")
    os.environ["PKMN_HOME"] = os.path.join(tmp_home, "home", "data")
    os.makedirs(os.environ["PKMN_HOME"], exist_ok=True)

    httpd, port = APP.start_server("127.0.0.1", 0, quiet=True)
    print("=" * 66)
    print(f"开启方式①–⑦ 端到端测试（本地服务 127.0.0.1:{port}）")
    print("=" * 66)

    games = {}
    try:
        # 未知方式要被挡住（免得前端传错时静默按方式①执行）
        r = post("/api/debug/enable", {"dir": "/tmp", "mode": "nope"}, port)
        report(not r.get("ok") and "未知" in str(r.get("message")),
               "未知的开启方式被拒绝", str(r.get("message"))[:60])

        for mode in MODES:
            game = build_game(mode)
            games[mode] = game
            rep, logs = run_task(
                port, "/api/debug/enable",
                {"dir": game, "mode": mode, "force": True, "guard": True})

            if rep is None:
                report(False, f"方式 {mode}：任务未返回结果",
                       " / ".join(logs[-3:]))
                continue
            # ★ done 事件的 payload 形如 {"ok": True, "result": {...}}
            #   （见 server/tasks.py 的 _run）—— 报告在 result 里，不在外层。
            if not rep.get("ok"):
                report(False, f"方式 {mode}：任务内部报错",
                       " / ".join(logs[-3:]))
                continue
            rep = rep.get("result") or {}

            report(rep.get("mode") == mode, f"方式 {mode}：返回的 mode 正确",
                   str(rep.get("mode")))
            report(bool(rep.get("ok")), f"方式 {mode}：enable_debug 成功",
                   str(rep.get("reason") or "")[:70])
            report(not rep.get("mode_error"), f"方式 {mode}：方式分支没抛异常",
                   str(rep.get("mode_error") or ""))

            main_text = read_script(game, "Main") or ""
            has_debug = "$DEBUG" in main_text

            # ★★ 最关键的一条：只有方式① 才允许写 $DEBUG
            if mode == "main":
                report(has_debug, "★ 方式① 写出了 $DEBUG=true")
            else:
                report(not has_debug,
                       f"★ 方式 {mode} 没有写 $DEBUG=true（否则可能被反调试踢出）")

            # 各方式确实改到了目标
            scene = read_script(game, "Scene_Map") or ""
            item = read_script(game, "Item_Effects") or ""
            if mode == "keys":
                report("$DEBUG and Input.press?(Input::F9)" not in scene,
                       "方式② 真的删掉了 Scene_Map 里的 $DEBUG 条件",
                       f"changed={(rep.get('mode_res') or {}).get('changed')}")
            elif mode in ("special", "special_menu"):
                report("Input::F6" in scene,
                       f"方式 {mode} 在 Scene_Map 里加了 F6 分支")
            elif mode in ("repel", "repel_menu"):
                report("$DEBUG" in item or "debug_calling" in item,
                       f"方式 {mode} 把逻辑注入到了 pbRepel",
                       f"changed={(rep.get('mode_res') or {}).get('changed')}")
            elif mode == "rewrite":
                mr = rep.get("mode_res") or {}
                report(bool(mr), "方式⑦ 返回了结果",
                       json.dumps(mr, ensure_ascii=False)[:70])

        # ---------- 幂等：方式② 再跑一次不该重复改 ----------
        game = games.get("keys")
        if game:
            before = read_script(game, "Scene_Map") or ""
            rep, _ = run_task(port, "/api/debug/enable",
                              {"dir": game, "mode": "keys", "force": True})
            after = read_script(game, "Scene_Map") or ""
            report(before == after, "方式② 幂等（再跑一次不再改动）")

    except Exception as e:                                        # noqa: BLE001
        import traceback
        traceback.print_exc()
        report(False, f"抛出异常：{type(e).__name__}: {e}")
    finally:
        try:
            httpd.shutdown()
        except Exception:                                         # noqa: BLE001
            pass
        for g in games.values():
            shutil.rmtree(g, ignore_errors=True)
        shutil.rmtree(tmp_home, ignore_errors=True)

    bad = _res.count(False)
    print("\n" + "=" * 66)
    print(f"通过 {len(_res) - bad} 项 / 失败 {bad} 项")
    print("=" * 66)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
