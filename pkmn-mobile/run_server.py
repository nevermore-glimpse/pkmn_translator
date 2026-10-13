# -*- coding: utf-8 -*-
"""
本地启动器：在电脑上把手机版跑起来。

    python run_server.py

效果和安卓 App 里的一模一样（同一套 web/ 和 server/），
用来开发调试最方便 —— 改完 Ctrl+C 重开即可。
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import bootstrap  # noqa: E402,F401

# ★ 走**包形式**，和安卓入口（mobile_main._import_app）保持一致。
#   以前是 `sys.path.insert(0, ROOT/"server"); import app`（平铺形式）——
#   两条路各用一套写法，结果安卓那边漏了 sys.path 这一手，
#   在电脑上却一路正常，问题完全暴露不出来。
#   现在两边都走 `from server import app`，电脑上就能测出安卓的问题。
from server import app as APP  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="启动手机版本地服务")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="自动打开浏览器")
    args = ap.parse_args()

    st = bootstrap.status()
    miss = st["missing"]
    print("=" * 58)
    print("  宝可梦同人游戏工具 · 手机版")
    print("=" * 58)
    print(f"  Python      {st['python']}")
    print(f"  core/       {'就绪' if st['core_exists'] else '缺失 —— 先跑 tools/sync_core.py'}")
    print(f"  基准数据    {'就绪' if st['data_exists'] else '缺失'}")
    if miss:
        print(f"  ✘ 模块缺失：{', '.join(miss)}")
    print("=" * 58)

    if miss or not st["core_exists"]:
        print("\n核心代码没就绪，先执行：\n    python tools/sync_core.py\n")

    httpd, port = APP.start_server(args.host, args.port, quiet=True)
    url = f"http://{args.host}:{port}/"
    print(f"\n  服务已启动：{url}")
    print(f"  web 目录  ：{APP.WEB_DIR}")
    print("\n  手机同 WiFi 想连的话，用 --host 0.0.0.0 并确认防火墙")
    print("  Ctrl+C 停止\n")

    if args.open:
        import webbrowser
        webbrowser.open(url)

    try:
        while True:
            import time
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n已停止")
        httpd.shutdown()


if __name__ == "__main__":
    main()
