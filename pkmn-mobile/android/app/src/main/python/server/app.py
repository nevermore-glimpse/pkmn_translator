# -*- coding: utf-8 -*-
"""
嵌入式 HTTP 服务 —— WebView 的后端。

只用标准库，不引 Flask/Django：安卓上的 Python 是 Chaquopy 自带的精简环境，
少一个依赖就少一个打包雷。

路由约定：
    GET/POST  /api/{模块}/{动作}       模块 ∈ debug | save | fs
    GET       /api/task/{id}/stream   SSE，实时推任务的日志与进度
    GET       /api/health             环境体检
    GET       /*                      web/ 下的静态资源
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import urllib.parse

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ★ 只有它真的是个目录才加进 sys.path。
#   安卓上（Chaquopy）__file__ 指向 app.imy 里的虚拟路径，dirname 两次
#   拿到的可能是 app.imy **这个文件本身** —— 而它恰好是个 zip，
#   放进 sys.path 会让 zipimport 去尝试解析它（无害，但纯属误导）。
if os.path.isdir(ROOT) and ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bootstrap  # noqa: E402,F401

# ★ 兄弟模块用哪种写法导入，取决于**自己是怎么被导入的**：
#
#     作为包      （server.app）  → 相对导入，不依赖 sys.path 里有没有 server/
#     作为顶层模块（app）         → 只能平铺导入（电脑版的 tools/*.py 这样用）
#
# 用 `if __package__` 明确二选一。
#
# ★ 千万不要写成 `try: import jsonutil / except ImportError: from . import jsonutil`：
#   那样会把「布局不同」和「真的出错」混成一种情况，
#   报错信息会完全指错方向 —— v1.3 那次
#   "ModuleNotFoundError: No module named 'app'" 就是这么来的。
if __package__:
    from . import jsonutil as JU            # noqa: E402
    from . import tasks                     # noqa: E402
    from . import api_debug                 # noqa: E402
    from . import api_save                  # noqa: E402
    from . import api_fs                    # noqa: E402
    from . import api_overwrite             # noqa: E402
    from . import api_font                  # noqa: E402
    from . import api_settings              # noqa: E402
    from . import api_pbs                   # noqa: E402
else:
    import jsonutil as JU                   # noqa: E402
    import tasks                            # noqa: E402
    import api_debug                        # noqa: E402
    import api_save                         # noqa: E402
    import api_fs                           # noqa: E402
    import api_overwrite                    # noqa: E402
    import api_font                         # noqa: E402
    import api_settings                     # E402
    import api_pbs                          # E402

# 安卓上资源由 MainActivity 从 assets 解出来放到私有目录，路径通过环境变量给
WEB_DIR = os.environ.get("PKMN_WEB_DIR") or os.path.join(ROOT, "web")
MODULES = {
    "debug": api_debug,
    "save": api_save,
    "fs": api_fs,
    "ow": api_overwrite,     # 基准覆盖
    "font": api_font,        # 字体替换
    "settings": api_settings, # 外观偏好（夜间模式等）持久化
    "pbs": api_pbs,          # PBS 编辑（v16~v21 的 txt 读写 + 编译）
}

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "PkmnTools/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------- 工具 ----------------
    def log_message(self, fmt, *args):
        pass  # 不打访问日志，免得刷爆 Android logcat

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        raw = self.rfile.read(n) if n else b"{}"
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8", errors="replace"))
        except Exception:
            return {}

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ---------------- GET ----------------
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(p.path)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(p.query).items()}

        if path == "/api/health":
            self._json(JU.ok(bootstrap.status()))
            return

        # 字体：实体只在 core_data/fonts/ 里一份，这里挂出去给 @font-face 用。
        # 不复制到 web/assets —— 萝莉体 11MB，复制一份 APK 就白白胖一圈。
        #
        # ★ 路由用 ASCII 别名而不是中文文件名：Windows 控制台 / curl /
        #   某些 WebView 在中文 URL 上会编码不一致，而 @font-face 拿到的
        #   URL 又是浏览器自己拼的。固定成 lolita.ttf 一劳永逸。
        if path.startswith("/fonts/"):
            return self._font(path[len("/fonts/"):])

        if path.startswith("/api/task/") and path.endswith("/stream"):
            tid = path.split("/")[3]
            return self._sse(tid)

        if path.startswith("/api/task/"):
            t = tasks.get(path.split("/")[3])
            if not t:
                self._json(JU.err("任务不存在"), 404)
            else:
                self._json(JU.ok(t.snapshot()))
            return

        if path.startswith("/api/"):
            self._json(self._dispatch("GET", path[len("/api/"):], query, {}))
            return

        self._static(path)

    # 中文文件名 → ASCII 别名，见 do_GET 里的说明
    FONT_ALIAS = {
        "lolita.ttf": "萝莉体.ttf",
        "lolita": "萝莉体.ttf",
    }

    def _font(self, name):
        """只允许读 core_data/fonts/ 下的字体文件。"""
        import config
        name = os.path.basename(name or "")
        name = self.FONT_ALIAS.get(name.lower(), name)
        if not name:
            return self._json(JU.err("字体不存在"), 404)
        fdir = os.path.join(getattr(config, "DATA_DIR", ""), "fonts")
        full = os.path.normpath(os.path.join(fdir, name))
        if not full.startswith(os.path.normpath(fdir)) or not os.path.isfile(full):
            return self._json(JU.err("字体不存在"), 404)
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError as e:
            return self._json(JU.err(str(e)), 500)
        ext = os.path.splitext(full)[1].lower()
        ctype = {".ttf": "font/ttf", ".otf": "font/otf",
                 ".woff2": "font/woff2"}.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # 字体不变，带上强缓存省得每次开 App 都重新拉 11MB
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    # ---------------- POST ----------------
    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(p.path)

        if path.startswith("/api/task/") and path.endswith("/cancel"):
            tid = path.split("/")[3]
            self._json(JU.ok({"cancelled": tasks.cancel(tid)}))
            return

        if path.startswith("/api/"):
            self._json(self._dispatch("POST", path[len("/api/"):], {},
                                      self._read_body()))
            return
        self._json(JU.err("未知接口"), 404)

    # ---------------- 路由分发 ----------------
    def _dispatch(self, method, tail, query, body):
        parts = [x for x in tail.split("/") if x]
        if len(parts) < 2:
            return JU.err("路径格式应为 /api/{模块}/{动作}")
        mod, action = parts[0], parts[1]
        handler_mod = MODULES.get(mod)
        if not handler_mod:
            return JU.err(f"未知模块：{mod}")
        ctx = {"query": query, "body": body, "method": method,
               "path": tail}
        try:
            return handler_mod.dispatch(ctx, action)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JU.err(f"{type(e).__name__}: {e}")

    # ---------------- SSE ----------------
    def _sse(self, task_id):
        t = tasks.get(task_id)
        if not t:
            self._json(JU.err("任务不存在"), 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        try:
            while True:
                try:
                    kind, payload = t.q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                line = json.dumps({"type": kind,
                                   "payload": JU.clean(payload)},
                                  ensure_ascii=False)
                self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                self.wfile.flush()
                if kind == "done":
                    break
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    # ---------------- 夜间模式注入 ----------------
    def _inject_night(self, data):
        """
        把后端持久化的夜间模式偏好塞进首屏 HTML。

        WebView 每次启动用随机端口起服务，浏览器 localStorage 按「源」隔离，
        重启就丢；所以偏好只能存在后端。这里在 <body> 之后立刻注入一段脚本
        设置 window.__NIGHT__，index.html 的内联脚本据此挂 .night 类，
        既不会开屏白闪、也不会重启后丢失。
        """
        try:
            night = bool(api_settings._load().get("night", False))
        except Exception:
            night = False
        script = ("<script>window.__NIGHT__=%s;</script>"
                  % ("true" if night else "false")).encode("utf-8")
        marker = b"<body>"
        idx = data.find(marker)
        if idx == -1:
            return data
        cut = idx + len(marker)
        return data[:cut] + b"\n" + script + data[cut:]

    # ---------------- 静态文件 ----------------
    def _static(self, path):
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        # 防目录穿越
        if not full.startswith(os.path.normpath(WEB_DIR)):
            self._json(JU.err("非法路径"), 403)
            return
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            self._json(JU.err(f"找不到 {path}"), 404)
            return
        ctype = _MIME.get(os.path.splitext(full)[1].lower(),
                          "application/octet-stream")
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError as e:
            self._json(JU.err(str(e)), 500)
            return
        # 夜间模式偏好存在后端（WebView 随机端口导致 localStorage 按源隔离、
        # 重启即丢），这里把持久化的值注入首屏 HTML，避免「开屏白闪」和
        # 「重启后夜间模式丢失」。index.html 的内联脚本读 window.__NIGHT__。
        if rel == "index.html":
            data = self._inject_night(data)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


def start_server(host="127.0.0.1", port=0, quiet=True):
    """启动服务。port=0 让系统随机分配（安卓上推荐）。返回 (httpd, 实际端口)。"""
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    real = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if not quiet:
        print(f"服务已启动：http://{host}:{real}")
    return httpd, real


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    _, real = start_server(args.host, args.port, quiet=False)
    print(f"web 目录：{WEB_DIR}")
    try:
        while True:
            import time
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n已停止")
