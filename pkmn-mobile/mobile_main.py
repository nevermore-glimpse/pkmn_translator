# -*- coding: utf-8 -*-
"""
安卓入口。

MainActivity 通过 Chaquopy 调用：

    Python.getInstance().getModule("mobile_main")
          .callAttr("start", homeDir, webDir, dataDir).toInt()   → 端口号

职责只有三件：撑好路径环境、引导 sys.path、把 HTTP 服务跑起来并返回端口。
业务逻辑全在 core/ 和 server/ 里，这里刻意保持很薄。

★ 改这个文件之前先跑 `python tools/test_mobile_boot.py`：
  它在本地**按 Chaquopy 的方式**摆好 sys.path（只把 python 根放上去），
  再真的把服务起起来。本地一遍几秒钟，比在手机上试错快得多。
"""

import os
import sys


def _log(msg):
    """
    把一行字打到手机启动遮罩的日志区。

    <p>为什么值得专门写这个：手机打不开时，用户能给的信息只有屏幕上
    那几行 + 诊断报告。Python 侧完全看不见，一旦出错就只剩一句异常摘要。
    有了它，Python 的每一步（路径怎么摆的、哪个导入成功了）都会直接
    显示在手机上，截图即可定位。

    失败就算了 —— 日志绝不能把启动流程带崩。
    """
    try:
        from java import jclass
        jclass("com.mali.pkmntools.Diagnostics").step("[Python] " + str(msg))
    except BaseException:
        # BaseException 而不是 Exception：Chaquopy 调 Java 方法失败时
        # 抛出来的可能是 Error 系的包装，用 Exception 接不住。
        pass


def _guess_root():
    """
    Python 源码根目录。

    <p>电脑上它是一个**真实目录**（能找到 core/ 子目录）；
    安卓上（Chaquopy）它可能是 `asset.app.zip` 这类**虚拟前缀** ——
    Chaquopy 把 app.imy 当成目录来用，`os.path.isdir` 对它是 False，
    所以这里**不能用 isdir 作为判据**（用过一次，把路径吃掉了）。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        if os.path.isdir(os.path.join(p, "core")):
            return p
    return here


def _prepare(home=None, web_dir=None, data_dir=None):
    root = _guess_root()

    if home:
        os.environ["PKMN_HOME"] = home
        os.environ["PKMN_HOME_DIR"] = os.path.dirname(home.rstrip("/"))
    if web_dir:
        os.environ["PKMN_WEB_DIR"] = web_dir
    if data_dir:
        os.environ["PKMN_DATA_DIR"] = data_dir

    os.environ.setdefault("PKMN_VERSION", "1.6.1-mobile")

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        os.makedirs(home or os.path.join(root, "home", "data"), exist_ok=True)
    except OSError:
        pass

    import bootstrap  # noqa: F401  建立 core/ + shim/ 的 sys.path
    _ensure_server_dir(root)

    _log("源码根 = " + root)
    _log("sys.path 前 5 项 = " + repr(sys.path[:5]))
    _verify_imports()
    return root


def _verify_imports():
    """
    立刻把三处「靠子目录 sys.path 条目才能导入」的代表模块试一遍，
    结果直接打到手机上。

    <p>为什么值得做：`bootstrap` 给 `<root>/core`、`<root>/shim`、
    `<root>/vendor` 挂了 sys.path，靠的是 Chaquopy 的 AssetFinder 支持
    「zip 内的子目录作为 path 条目」这个特性（它的 __init__ 里有专门
    处理 dirname(path) != ASSET_PREFIX 的分支）。这个特性如果哪天变了，
    表现会是「App 打开了，但某个功能一用就报 No module named 'save_tools'」——
    极难定位。

    <p>在这里试一遍，就等于**每次启动都自检一次**，屏幕上直接能看到
    ✔/✘，不用再靠猜。三个模块分别代表三条路径：

        config     → shim/
        save_tools → core/
        rubymarshal→ vendor/
    """
    for name in ("config", "save_tools", "rubymarshal"):
        try:
            __import__(name)
            _log("导入 %s ✔" % name)
        except Exception as e:                                    # noqa: BLE001
            _log("导入 %s ✘ %s: %s" % (name, type(e).__name__, e))


def _ensure_server_dir(root):
    """
    把 `<root>/server` 加进 sys.path，让 `server/app.py` 里的平铺导入
    （`import jsonutil` / `import tasks` / `import api_*`）能找到兄弟模块。

    <p>电脑版 `run_server.py` 一直是这么做的
    （`sys.path.insert(0, os.path.join(ROOT, "server"))`），安卓入口当初漏了。

    ★★ 两个坑都踩过，改这里之前请看完整：

    坑一（v1.3）：**根本没加**。
        于是 `app.py` 一执行就炸在 `import jsonutil`，
        而外层 `except ImportError` 把它替换成 "No module named 'app'" 报出来。

    坑二（v1.4）：加了，但被一道多余的门槛挡住。
        当时写成
            if not os.path.isdir(server_dir): return
        可是**安卓上 root 不是真实目录** —— Chaquopy 把 app.imy 当目录用，
        `os.path.isdir("<...>/app.imy/server")` 永远是 False，
        这一行就把路径悄悄吃掉了，报错和没改之前一模一样。

        → 所以这里**不判断存在性**，直接加。sys.path 里多一条无效路径
          没有任何副作用（Python 找不到就跳过）。

    <p>机制说明（Chaquopy 的 `java/android/importer.py`）：它的
    `AssetFinder.__init__` 里有一个专门分支处理 `dirname(path) != ASSET_PREFIX`
    的情况 —— 先取父 finder 的 extract_root，再把相对部分当成 prefix 去 zip 里找。
    也就是说**「zip 内的子目录」是可以作为 sys.path 条目的**；
    `bootstrap` 给 core/ shim/ vendor/ 加路径用的正是这个机制。
    """
    server_dir = os.path.join(root, "server")
    if server_dir in sys.path:
        _log("server 路径已在 sys.path")
        return
    try:
        at = sys.path.index(root) + 1     # 紧跟 root：core → shim → … → root → server
    except ValueError:
        at = len(sys.path)
    sys.path.insert(at, server_dir)
    _log("已加入 server 路径：" + server_dir)


def _import_app():
    """
    取到 server/app.py 这个模块对象。两条路都留着，因为两种布局都合理：

        ① 包形式（首选）   from server import app
           靠 `server/__init__.py`。**完全不依赖 sys.path 里有没有 server/**，
           走 Chaquopy 自己也在用的「常规包」分支，最稳。

        ② 平铺形式（退路） import app
           靠 `_ensure_server_dir` 把 `<root>/server` 挂上 sys.path。

    ★★★ 关键：**只在「包本身找不到」时才降级，其它错误原样抛。**

        以前写的是 `except ImportError: import app` —— 于是 app.py 内部
        任何 ImportError 都会被替换成 "No module named 'app'"。
        v1.3 那次用户看到的报错就是这么被带偏的，白白多花了一轮。

        现在用 `e.name` 精确区分：
            e.name == "server" / "server.app"  → 包形式不可用，降级
            其它（例如 "jsonutil"）            → app.py 内部真的有问题，抛出去
    """
    try:
        from server import app as APP
        _log("app 模块（包形式）已导入：" + str(getattr(APP, "__file__", "?")))
        return APP
    except ModuleNotFoundError as e:
        if e.name not in ("server", "server.app"):
            raise                      # 真实错误，绝不掩盖
        _log("包形式不可用（No module named %r），改用平铺形式" % (e.name,))

    import app as APP
    _log("app 模块（平铺形式）已导入：" + str(getattr(APP, "__file__", "?")))
    return APP


def start(home=None, web_dir=None, data_dir=None, host="127.0.0.1", port=0):
    """启动本地服务，返回端口号。"""
    _prepare(home, web_dir, data_dir)
    APP = _import_app()

    httpd, real = APP.start_server(host=host, port=port, quiet=True)
    globals()["_HTTPD"] = httpd
    _log("服务已监听 127.0.0.1:%d" % real)
    return real


def health():
    """体检信息，给 MainActivity 显示在「关于」页。"""
    _prepare()
    APP = _import_app()
    return APP.bootstrap.status()


def stop():
    httpd = globals().get("_HTTPD")
    if httpd:
        try:
            httpd.shutdown()
        except Exception:
            pass
    return True


if __name__ == "__main__":
    print("port =", start())
