# -*- coding: utf-8 -*-
"""
接口冒烟测试：真的把服务起起来，用 HTTP 打一遍。

    python tools/smoke_api.py

不看代码对不对，只看**接口真的能不能用** —— 这是排障的第一步。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 与安卓入口一致，走包形式（见 run_server.py 的说明）
from server import app as APP  # noqa: E402

_results = []


def report(ok, name, detail=""):
    _results.append(ok)
    print(f"  {'✔' if ok else '✘'} {name}" + (f"  — {detail}" if detail else ""))


def call(base, method, path, body=None):
    url = base + path
    data = json.dumps(body or {}).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code,
                "body": e.read().decode("utf-8", errors="replace")[:300]}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def main():
    os.makedirs(os.path.join(ROOT, "tmp"), exist_ok=True)
    httpd, port = APP.start_server()
    base = f"http://127.0.0.1:{port}"
    print("=" * 62)
    print(f"接口冒烟测试   {base}")
    print("=" * 62)

    # ---------- 1. 健康检查 ----------
    print("\n[1] 健康检查")
    r = call(base, "GET", "/api/health")
    ok = r.get("ok") and not r["data"]["missing"]
    report(ok, "GET /api/health",
           "全部模块就绪" if ok else json.dumps(r, ensure_ascii=False)[:200])

    # ---------- 2. 文件浏览 ----------
    print("\n[2] 文件浏览（手机上代替 tkinter 选文件夹）")
    tmpdir = tempfile.mkdtemp(prefix="smoke_", dir=os.path.join(ROOT, "tmp"))
    r = call(base, "GET", "/api/fs/list?dir=" + urllib.parse.quote(tmpdir))
    report(r.get("ok") is True, "GET /api/fs/list", r.get("message", "")[:120])
    report("dirs" in str(r) and "cwd" in str(r), "返回结构含 cwd/dirs/files")

    # ---------- 3. 假游戏目录 → DEBUG 链路 ----------
    print("\n[3] 开启 DEBUG 链路")
    game = tempfile.mkdtemp(prefix="fakegame_", dir=os.path.join(ROOT, "tmp"))
    os.makedirs(os.path.join(game, "Data"), exist_ok=True)
    with open(os.path.join(game, "Game.exe"), "wb") as f:
        f.write(b"fake")

    r = call(base, "GET", "/api/fs/check_game?dir=" + urllib.parse.quote(game))
    report(r.get("ok") and r["data"].get("valid"), "GET /api/fs/check_game",
           r.get("data", {}).get("reason", "")[:110])

    r = call(base, "GET", "/api/debug/status?dir=" + urllib.parse.quote(game))
    report(r.get("ok") is True, "GET /api/debug/status",
           f"debug_on={r.get('data', {}).get('debug_on')}"
           if r.get("ok") else r.get("message", "")[:110])

    r = call(base, "POST", "/api/debug/enable", {"dir": game})
    tid = (r.get("data") or {}).get("task_id")
    report(bool(tid), "POST /api/debug/enable 拿到 task_id", str(tid))

    import time
    if tid:
        # 用 HTTP 拉一次 SSE（只读几秒就够，确认管道是通的）
        logs = []
        try:
            req = urllib.request.Request(base + f"/api/task/{tid}/stream")
            with urllib.request.urlopen(req, timeout=25) as resp:
                deadline = time.time() + 15
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line.startswith("data:"):
                        d = json.loads(line[5:])
                        if d["type"] == "log":
                            logs.append(d["payload"])
                        if d["type"] == "done":
                            break
                    if time.time() > deadline:
                        break
        except Exception as e:
            report(False, "SSE 读取", f"{type(e).__name__}: {e}")
        report(len(logs) > 0, f"SSE 收到 {len(logs)} 条日志",
               (logs[0][:70] if logs else "没有收到任何日志"))

    r = call(base, "GET", "/api/debug/backups?dir=" + urllib.parse.quote(game))
    report(r.get("ok") is True, "GET /api/debug/backups")

    # ---------- 4. 存档接口（喂坏数据，看能不能优雅报错） ----------
    print("\n[4] 存档接口")
    bad = os.path.join(ROOT, "tmp", "bad.rxdata")
    with open(bad, "wb") as f:
        f.write(b"not a marshal file")
    r = call(base, "POST", "/api/save/open", {"path": bad})
    # 坏数据应该返回「ok=False + 明确错误」，而不是把服务打挂
    report(r.get("ok") is False and "message" in r,
           "POST /api/save/open（坏数据）返回明确错误",
           r.get("message", "")[:120])

    # ---------- 5. 静态资源 ----------
    print("\n[5] 静态资源")
    idx = os.path.join(APP.WEB_DIR, "index.html")
    report(os.path.isfile(idx), "web/index.html 存在",
           "" if os.path.isfile(idx) else f"缺失：{idx}")

    # ---------- 收尾 ----------
    shutil.rmtree(tmpdir, ignore_errors=True)
    shutil.rmtree(game, ignore_errors=True)
    httpd.shutdown()

    bad_n = _results.count(False)
    print("\n" + "=" * 62)
    print(f"通过 {len(_results) - bad_n} 项 / 失败 {bad_n} 项")
    print("=" * 62)
    return 1 if bad_n else 0


if __name__ == "__main__":
    sys.exit(main())
