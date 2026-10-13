# -*- coding: utf-8 -*-
"""
引导：把 core/ 和 shim/ 拼成一个可用的 Python 环境。

任何要用核心代码的入口（server、自检脚本、安卓端）都先 import 它：

    import bootstrap            # 必须是第一条业务 import
    import save_tools as ST
    import debug_tool as DT

原理：
    sys.path = [core/, shim/, ...]，于是
        core/save_tools.py 里的 `import rmarshal`      → core/rmarshal.py
        core/logger.py 里的 `import config`            → shim/config.py
        core/game_scripts.py 里的 `import rubymarshal` → pip 装的第三方纯 Python 包

★ core/ 之所以能保持与电脑版逐字节一致，全靠这里把差异拦在了外面。
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(ROOT, "core")
SHIM_DIR = os.path.join(ROOT, "shim")

# ★ core_data/ 的位置必须以环境变量为准。
#
#   安卓上源码在 app.imy 里，`<ROOT>/core_data` **不存在** ——
#   core_data 是作为 asset 打包、由 MainActivity 解到 App 私有目录，
#   路径通过 PKMN_DATA_DIR 注入。以前这里写死成 os.path.join(ROOT, "core_data")，
#   于是 status() 里的 os.path.isdir 永远为 False，关于页一直显示
#   「基准数据：缺失」（实际数据是好的，只是报错了）。
#   电脑上不设这个变量，行为不变。
DATA_DIR = os.environ.get("PKMN_DATA_DIR") or os.path.join(ROOT, "core_data")

# 内置进来的第三方纯 Python 包（不用 pip 装，见 README「为什么不用 pip」）
VENDOR_DIR = os.path.join(ROOT, "vendor")

# 工作目录默认值：安卓上由 MainActivity 用 PKMN_HOME 注入
if not os.environ.get("PKMN_HOME"):
    os.environ.setdefault("PKMN_HOME", os.path.join(ROOT, "home", "data"))

# 注意顺序：sys.path.insert(0, p) 会把先插的挤到后面，所以这里**倒着写**。
# 想让优先级是 core > shim > vendor > 根，就得这样插入。
for p in (ROOT, VENDOR_DIR, SHIM_DIR, CORE_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


def baseline_versions():
    """
    内置基准数据里有哪些版本 —— 关于页要把它列出来，
    让用户一眼看出「工具能认出哪些版本的引擎」。

    数据在两处（都随 App 打包，见 README 的「资源体积取舍」）：
        core_data/essentials_base/*.json   引擎基本函数的官方基准
        core_data/essentials_src/<版本>/   官方 debug 脚本 / Scene_Map 源码
    """
    out = {"base": [], "src": []}
    for key, sub, strip_ext in (("base", "essentials_base", True),
                                ("src", "essentials_src", False)):
        d = os.path.join(DATA_DIR, sub)
        try:
            for n in sorted(os.listdir(d)):
                p = os.path.join(d, n)
                if key == "base":
                    if n.lower().endswith(".json"):
                        out[key].append(os.path.splitext(n)[0])
                elif os.path.isdir(p):
                    out[key].append(n)
        except OSError:
            pass
    return out


def status():
    """返回一张环境体检表，给 /api/health 用。"""
    base = baseline_versions()
    info = {
        "root": ROOT,
        "python": sys.version.split()[0],
        "core_dir": CORE_DIR,
        "core_exists": os.path.isdir(CORE_DIR),
        "data_dir": DATA_DIR,
        "data_exists": os.path.isdir(DATA_DIR),
        "baseline_versions": base["base"],
        "src_versions": base["src"],
        "modules": {},
        "missing": [],
    }
    for m in ("rmarshal", "save_tools", "game_scripts",
              "essentials_base", "debug_tool", "engine_tools",
              "plugin_tools", "intl_text", "engine_src",
              "logger", "config"):
        try:
            __import__(m)
            info["modules"][m] = "ok"
        except Exception as e:
            info["modules"][m] = f"{type(e).__name__}: {e}"
            info["missing"].append(m)
    return info


if __name__ == "__main__":
    import json
    print(json.dumps(status(), ensure_ascii=False, indent=2))
