# -*- coding: utf-8 -*-
"""
移动端 config 替身。

电脑版的 config.py 有大量桌面相关的东西（sys._MEIPASS 打包资源、GDI 私有字体、
.exe 同目录查找……），手机上这些统统不存在。与其改原文件，不如在这里做个替身 ——
让 core/ 里的模块 `import config` 时拿到的是这份，**core/ 因此保持零改动**。

替换 móstoles 后的两个入口：

    BASE_DIR        工作目录，日志文件落在它下面
    resource_path() 定位随 App 分发的数据，主要是引擎版本比对基准 JSON

验证依据（改动前请重新确认）：整条核心链路上，config 只被用到这两处
    logger.py:22        os.path.join(config.BASE_DIR, "logs")
    essentials_base.py:233  config.resource_path(BASE_DIR_NAME)
                            （BASE_DIR_NAME = "scripts/essentials_base"）
下面多导出的那些常量是防御性的 —— 免得电脑版哪天新增 config.X 就让手机版炸掉。
"""

import os
import sys

_SHIM_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_SHIM_DIR)          # pkmn-mobile/（安卓上是 App files 目录）

# ================================================================
# 目录
# ================================================================
# 安卓上 App 私有目录由 MainActivity 通过环境变量注入；电脑调试时落到项目里的 home/。
_HOME_DIR = os.path.join(ROOT, "home")
_BASE_DIR = os.path.join(_HOME_DIR, "data")

# 安卓上这两个值由 MainActivity 通过环境变量注入 —— APK 里 __file__ 指向的是
# 打包后的虚拟路径，靠它推目录不可靠，必须以环境变量为准。
BASE_DIR = os.environ.get("PKMN_HOME") or _BASE_DIR
HOME_DIR = os.environ.get("PKMN_HOME_DIR") or _HOME_DIR

# core_data/ 由人工从电脑版拷贝进来（不再有自动同步脚本）
DATA_DIR = os.environ.get("PKMN_DATA_DIR") or os.path.join(ROOT, "core_data")

REPORT_DIR = os.path.join(BASE_DIR, "reports")
TMP_DIR = os.path.join(BASE_DIR, "tmp")
LOG_DIR = os.path.join(BASE_DIR, "logs")

for _d in (BASE_DIR, REPORT_DIR, TMP_DIR, LOG_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        # 只读环境（例如纯 Web 预览）下不致命，日志相关功能退化即可
        pass


# ================================================================
# 资源定位
# ================================================================
# 电脑版这里有一大坨 sys._MEIPASS / exe 同目录的查找逻辑，手机版只需要做一件事：
# 把 "scripts/essentials_base" 指到同步过来的 core_data/essentials_base。
_RESOURCE_MAP = {
    "scripts/essentials_base": os.path.join(DATA_DIR, "essentials_base"),
    "scripts/essentials_src": os.path.join(DATA_DIR, "essentials_src"),
    # 插件源码的目录名带空格（"scripts/chinese text manager 21.1"），
    # 手机上改用无空格的短名，这里按 basename 兜底匹配。
    "scripts/essentials_src": os.path.join(DATA_DIR, "essentials_src"),
}

# 插件源码变体 → core_data/plugins/ 下的短名目录。
# 电脑版用 "scripts/chinese text manager 21.1" 这种带空格的路径，
# 安卓打包与路径拼接都容易出问题，所以映射到 ctm-21.1。
_PLUGIN_DIRS = {
    "scripts/chinese text manager":           "ctm-21.1",
    "scripts/chinese text manager 21.1":      "ctm-21.1",
    "scripts/chinese text manager 20.1":      "ctm-20.1",
    "scripts/chinese text manager 19.1":      "ctm-19.1",
    "scripts/chinese text manager 18.1":      "ctm-18.1",
    "scripts/chinese text manager 17.2":      "ctm-17.2",
    "scripts/chinese text manager 16":        "ctm-16",
}

# 内置字体（萝莉体）—— 手机版自带的默认中文字体
FONT_FILE = os.path.join(DATA_DIR, "fonts", "萝莉体.ttf")
FONT_NAME = "Lolita"


def _norm(path):
    """把 "scripts\\essentials_base" / "scripts/essentials_base" 统一成后者。"""
    return str(path).replace("\\", "/").strip("/")


def resource_path(name):
    """
    定位随 App 分发的资源。

    查找顺序：
      ① 资源映射表（core_data/ 下人工拷贝进来的数据）
      ② 插件源码映射（带空格的目录名 → ctm-XX.X）
      ③ App 工作目录下的同名资源（用户可放进去覆盖）
      ④ core_data/ 根目录同级同名
    都不存在时返回 ①/③ 的候选路径，让上层给出准确报错。
    """
    key = _norm(name)
    mapped = _RESOURCE_MAP.get(key)
    if mapped:
        return mapped

    # 插件源码：名字带空格/版本号后缀的都在这张表里
    base = os.path.basename(key)
    if key.startswith("scripts/chinese text manager"):
        folder = _PLUGIN_DIRS.get(key) or _PLUGIN_DIRS.get("scripts/" + base)
        if folder:
            p = os.path.join(DATA_DIR, "plugins", folder)
            if os.path.isdir(p):
                return p
            return p

    candidate = os.path.join(BASE_DIR, name)
    if os.path.exists(candidate):
        return candidate

    alt = os.path.join(DATA_DIR, os.path.normpath(name))
    if os.path.exists(alt):
        return alt

    return mapped or candidate


def resource_dir(name):
    """同 resource_path，但要求必须是**目录**，找不到返回 None。"""
    p = resource_path(name)
    if os.path.isdir(p):
        return p
    alt = os.path.join(DATA_DIR, os.path.basename(_norm(name)))
    return alt if os.path.isdir(alt) else None


# ================================================================
# 应用信息（防御性导出，保持与电脑版同名）
# ================================================================
APP_NAME = "宝可梦同人工具"
VERSION = os.environ.get("PKMN_VERSION", "1.0.0")
APP_TITLE = f"{APP_NAME} v{VERSION}"

# ★ 电脑版「翻译中间文件」目录名（桌面批量翻译把缓存/报告/润色稿放这里）。
#   手机不跑这条链路，导出同名常量只为让 core/ 里 `import config` 的模块
#   （如 intl_text.collect_text_files）拿到一致的名字 —— core/ 保持零改动。
WORK_DIR_NAME = "翻译中间文件"

PLATFORM = "android" if "ANDROID_ARGUMENT" in os.environ or hasattr(sys, "getandroidapilevel") else "desktop"
