# -*- coding: utf-8 -*-
"""
在本地**模拟 Chaquopy 的启动环境**，把手机版真的跑起来。

为什么需要它
-----------
手机上「启动失败」的反馈只有一句 Python 异常，而异常往往还指错方向：

    踩坑 1（v1.3）：真实原因是 `server/app.py` 里 `import jsonutil` 找不到，
                    外层 `except ImportError` 一兜，报出来变成
                    「No module named 'app'」。
    踩坑 2（v1.4）：修的时候加了 `os.path.isdir(server_dir)` 当门槛，
                    可是安卓上源码在 app.imy 里、**不是真实目录**，
                    那行判断永远为假，路径被悄悄吃掉，报错和没改一样。

两次的共同点是：**差别只在路径/导入环境上，而这在本地完全可以复刻。**
Chaquopy 会把 `android/app/src/main/python/` 整个平铺到 sys.path 根上，
除此之外什么都不加。所以这个脚本：

    ① 只把 python 根放进 sys.path（别的什么都不加，跟 Chaquopy 一样）
    ② 用临时目录当 PKMN_HOME，避免污染工程里的 home/
    ③ 真的调 mobile_main.start()，再打一遍 HTTP 接口

★ 每次改 core/ shim/ server/ mobile_main.py 之后都该先跑它。
  几秒钟跑完，比在手机上装包试错快得多。

用法：
    python tools/test_mobile_boot.py
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_ROOT = os.path.join(ROOT, "android", "app", "src", "main", "python")

passed = []
failed = []


def check(name, cond, detail=""):
    if cond:
        passed.append(name)
        print(f"  ✔ {name}" + (f"  — {detail}" if detail else ""))
    else:
        failed.append(name)
        print(f"  ✘ {name}" + (f"  — {detail}" if detail else ""))


def http(path, host_port):
    url = f"http://127.0.0.1:{host_port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    print("模拟 Chaquopy 环境启动手机版：")

    # 0. 打包目录必须是同步过的（否则测的是过期副本，结论没意义）
    need = ["core", "shim", "server", "vendor", "bootstrap.py", "mobile_main.py",
            os.path.join("server", "__init__.py")]
    missing = [s for s in need if not os.path.exists(os.path.join(PY_ROOT, s))]
    if missing:
        print(f"✘ {os.path.relpath(PY_ROOT, ROOT)} 里缺少 {missing}\n"
              f"  先跑：python tools/stage_assets.py")
        return 1
    check("打包目录已同步（core/shim/server/vendor 齐全）", True)

    tmp = tempfile.mkdtemp(prefix="pkmn_boot_")
    old_env = {k: os.environ.get(k) for k in
               ("PKMN_HOME", "PKMN_HOME_DIR", "PKMN_WEB_DIR", "PKMN_DATA_DIR")}
    old_path = list(sys.path)
    try:
        home = os.path.join(tmp, "home", "data")
        os.makedirs(home)
        os.environ["PKMN_HOME"] = home
        os.environ["PKMN_HOME_DIR"] = os.path.dirname(home)
        os.environ["PKMN_WEB_DIR"] = os.path.join(ROOT, "web")
        os.environ["PKMN_DATA_DIR"] = os.path.join(ROOT, "core_data")

        # ① 关键：只放 python 根。像 Chaquopy 一样，不加 server/、不加项目根。
        sys.path.insert(0, PY_ROOT)

        import mobile_main  # noqa: E402

        check("mobile_main 可导入", True,
              "root=" + os.path.basename(mobile_main._guess_root()))

        # ② 关键回归：_import_app 不能再用 `except ImportError` 掩盖真实错误。
        #    用 AST 看**代码**，不能用字符串搜索 —— 注释里就写着这句错写法。
        tree = ast.parse(open(os.path.join(PY_ROOT, "mobile_main.py"),
                              encoding="utf-8").read())
        bare = [n for n in ast.walk(tree)
                if isinstance(n, ast.ExceptHandler)
                and getattr(n.type, "id", None) == "ImportError"]
        check("_import_app 不再用 except ImportError 掩盖错误", not bare,
              f"发现 {len(bare)} 处" if bare else "无")

        # ③ 两条导入通路都要能用（任意一条坏掉都还有另一条）
        import importlib  # noqa: E402
        pkg_mod = importlib.import_module("server.app")
        check("通路①包形式 `server.app` 可用",
              getattr(pkg_mod, "__name__", "") == "server.app",
              str(getattr(pkg_mod, "__file__", "?")))

        mobile_main._ensure_server_dir(PY_ROOT)
        sys.modules.pop("app", None)
        flat_mod = importlib.import_module("app")
        check("通路②平铺形式 `app` 可用（server/ 在 sys.path 上）",
              os.path.basename(str(getattr(flat_mod, "__file__", ""))) == "app.py",
              str(getattr(flat_mod, "__file__", "?")))

        check("两个 app 模块都指向 server/app.py，没有走错文件",
              "/server/app" in str(getattr(pkg_mod, "__file__", "")).replace("\\", "/")
              and "/server/app" in str(getattr(flat_mod, "__file__", "")).replace("\\", "/"))

        # ④ 真的把服务起起来
        port = mobile_main.start(
            home, os.environ["PKMN_WEB_DIR"], os.environ["PKMN_DATA_DIR"])
        check("mobile_main.start() 返回端口", isinstance(port, int) and port > 0,
              f"port={port}")

        # ⑤ 接口真的能通
        st, body = http("/api/health", port)
        check("GET /api/health → 200", st == 200, str(st))
        try:
            data = json.loads(body.decode("utf-8"))
            info = data.get("data") or data
            check("health 报告 core 模块齐全",
                  not info.get("missing"),
                  "missing=" + str(info.get("missing")))
        except Exception as e:                                    # noqa: BLE001
            check("health 返回可解析 JSON", False, f"{type(e).__name__}: {e}")

        st, body = http("/", port)
        check("GET / 返回首页", st == 200 and b"<html" in body.lower(),
              f"{st}, {len(body)} 字节")

        st, body = http("/api/save/open", port)
        # 没有传存档路径 → 应该是「明确的业务错误」而不是 500 崩栈
        check("GET /api/save/open 有明确错误而不是崩栈",
              st in (200, 400, 404),
              f"{st}, {body[:50].decode('utf-8', 'replace')}")

        # ⑥ 字体路由（11MB，只验状态码与长度）
        st, body = http("/fonts/lolita.ttf", port)
        check("GET /fonts/lolita.ttf 可用", st == 200 and len(body) > 1_000_000,
              f"{st}, {len(body) / 1024 / 1024:.1f}MB")

        # ⑦ 内置基准数据必须被认出来
        #    （v1.6 修：bootstrap.DATA_DIR 以前写死成源码树下的 core_data，
        #      安卓上那是 app.imy 里的虚拟路径，永远不存在 →
        #      关于页一直显示「基准数据：缺失」）
        st, body = http("/api/health", port)
        info = (json.loads(body.decode("utf-8")).get("data") or {})
        check("health 报基准数据就位（PKMN_DATA_DIR 生效）",
              bool(info.get("data_exists")),
              "data_dir=" + str(info.get("data_dir")))
        base_vs = info.get("baseline_versions") or []
        check("health 列出了内置基准版本", len(base_vs) >= 9,
              "versions=" + ",".join(base_vs))

        # ⑧ 开启方式①–⑦ 齐全（与电脑版 gui.py 下拉框对齐）
        st, body = http("/api/debug/modes", port)
        modes = (json.loads(body.decode("utf-8")).get("data") or {}).get("modes") or []
        keys = [m.get("key") for m in modes]
        want = ["main", "keys", "special", "special_menu",
                "repel", "repel_menu", "rewrite"]
        check("开启方式①–⑦ 齐全", keys == want, "keys=" + ",".join(keys))
        check("每个方式都带说明文字", bool(modes) and all(m.get("desc") for m in modes))
        # 只有方式① 允许写 $DEBUG —— 这条规则两端口径必须一致
        src = open(os.path.join(PY_ROOT, "server", "api_debug.py"),
                   encoding="utf-8").read()
        check("只有方式① 会写 $DEBUG（write_debug=(mode == \"main\")）",
              'write_debug=(mode == "main")' in src)

        # ⑨ 安卓上空路径要返回「可用起点」，而不是去列 "/"
        #    （"/" 在 SELinux 下列不出来 → 前端只会弹「没有读取权限」，
        #      用户完全不知道该往哪走。这是 v1.5 的真实反馈。）
        os.environ["PKMN_FORCE_ANDROID"] = "1"
        try:
            st, body = http("/api/fs/list?dir=", port)
            d = json.loads(body.decode("utf-8"))
            check("安卓空路径返回起点列表（不再报没有读取权限）",
                  bool(d.get("ok")) and (d.get("data") or {}).get("roots") is True,
                  str(d.get("message") or "roots"))
            check("起点列表带使用说明", bool((d.get("data") or {}).get("hint")))
        finally:
            os.environ.pop("PKMN_FORCE_ANDROID", None)

        # ⑩ 真实目录仍然能正常列出来
        st, body = http("/api/fs/list?dir=" + urllib.parse.quote(ROOT), port)
        d = json.loads(body.decode("utf-8"))
        dnames = [x["name"] for x in ((d.get("data") or {}).get("dirs") or [])]
        check("能列出真实目录", bool(d.get("ok")) and "core" in dnames,
              f"{len(dnames)} 个子目录")

        mobile_main.stop()

    finally:
        sys.path[:] = old_path
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 58)
    print(f"通过 {len(passed)} 项 / 失败 {len(failed)} 项")
    print("=" * 58)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
