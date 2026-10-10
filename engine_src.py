# -*- coding: utf-8 -*-
"""
读取随工具分发的官方引擎脚本（scripts/essentials_src/<ver>/）。

提供：
  · list_versions()            内置了哪些版本
  · debug_menu_files(ver)      debug 菜单脚本的相对路径列表
  · engine_files(ver, ...)     某版本的官方脚本绝对路径
  · load_translations()        英→中对照表
  · apply_translation(text,tr) 把 _INTL("英文") 换成 _INTL("中文")
  · func_source(ver, script, func)  取官方某函数的源码
  · extract_func(text, func)        从脚本文本里抠出某函数
  · replace_func(text, func, new)   把脚本文本里的某函数替换掉
"""
import io
import json
import os
import re

import config

SRC_DIR_NAME = os.path.join("scripts", "essentials_src")
DEBUG_MENU_SUBDIR = os.path.join("020_Debug", "003_Debug menus")

# ----------------------------------------------------------------
# ★ 覆盖清单（用户指定，按引擎版本各不相同）
#
#   v16 / v16.1  Debug                                  （+ PScreen_Party 的 pbPokemonDebug）
#   v17 / v17.1  Debug_Menu / Debug_Actions / Debug_Pokemon
#   v18 / v18.1  同上
#   v19          Debug_Menus / Debug_MenuCommands / Debug_MenuExtraCode / Debug_PokemonCommands
#   v19.1        同上 + Debug_MenuSpriteRenamer
#   v20 / v20.1 / v21 / v21.1
#                Debug_Menus / Debug_MenuCommands / Debug_MenuExtraCode /
#                Debug_BattleCommands / Debug_BattlePkmnCommands /
#                Debug_BattleExtraCode / Debug_PokemonCommands / Debug_FilenameUpdater
#
#   ★ 只覆盖游戏内的 debug —— 不碰 DebugConsole / PBDebug / PokeBattle_DebugScene
#     （那些是控制台和作者自己的调试残留，覆盖了反而会出事）。
# ----------------------------------------------------------------
_V20_DEBUG_SET = (
    "Debug_Menus", "Debug_MenuCommands", "Debug_MenuExtraCode",
    "Debug_BattleCommands", "Debug_BattlePkmnCommands",
    "Debug_BattleExtraCode", "Debug_PokemonCommands",
    "Debug_FilenameUpdater",
)
_V19_DEBUG_SET = (
    "Debug_Menus", "Debug_MenuCommands", "Debug_MenuExtraCode",
    "Debug_PokemonCommands",
)
_OVERWRITE_SCRIPTS = {
    "16": ("Debug",),
    "17": ("Debug_Menu", "Debug_Actions", "Debug_Pokemon"),
    "18": ("Debug_Menu", "Debug_Actions", "Debug_Pokemon"),
    "19": _V19_DEBUG_SET,
    "19.1": _V19_DEBUG_SET + ("Debug_MenuSpriteRenamer",),
    "20": _V20_DEBUG_SET,
    "20.1": _V20_DEBUG_SET,
    "21": _V20_DEBUG_SET,
    "21.1": _V20_DEBUG_SET,
}

# 函数级覆盖：v16 的「宝可梦 debug 菜单」不在独立脚本里，
# 而是 PScreen_Party 的 pbPokemonDebug 函数 → 只换这个函数，别整份替换。
_OVERWRITE_FUNCS = {
    "16": (("PScreen_Party", "pbPokemonDebug"),),
}

# ★ 旧版（v16/v17/v18）的脚本是从 Scripts.rxdata 解出来的平铺文件
#   `NNNNN_<脚本名>.rb`，没有 `020_Debug/003_Debug menus` 子目录。
#   同名文件可能不止一份（v18 既有 Debug_Menu 也有别的），按脚本名取第一个。
_LEGACY_FLAT = ("16", "17", "18")


def norm_ver(version):
    """
    把版本号归到「有内置基准」的那一档：16.1→16、17.1→17、18.1→18，
    其余原样返回（认不出来就按最新那档）。
    """
    v = str(version or "").strip()
    if v in _OVERWRITE_SCRIPTS:
        return v
    try:
        maj, minor = (int(x) for x in v.split(".")[:2])
    except (ValueError, AttributeError):
        return "21.1" if v else "21.1"
    if maj <= 18:
        return str(maj)
    if maj == 19:
        return "19.1" if minor >= 1 else "19"
    return v if v in _OVERWRITE_SCRIPTS else f"{maj}.{minor}" \
        if f"{maj}.{minor}" in _OVERWRITE_SCRIPTS else str(maj)


def overwrite_script_names(version):
    """该版本要**整份覆盖**的脚本名列表。"""
    return list(_OVERWRITE_SCRIPTS.get(norm_ver(version), ()))


def overwrite_func_items(version):
    """该版本要**函数级覆盖**的 (脚本名, 函数名) 列表。"""
    return list(_OVERWRITE_FUNCS.get(norm_ver(version), ()))


def _flat_src_file(version, script):
    """在扁平版本目录里按脚本名找文件 → 绝对路径（找不到 ""）。"""
    d = _ver_dir(version)
    stem = re.sub(r"^\d+_", "", str(script))
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not f.endswith(".rb"):
            continue
        if re.sub(r"^\d+_", "", f[:-3]) == stem:
            return os.path.join(d, f)
    return ""


def script_src_path(version, script):
    """某版本里某个官方脚本的绝对路径（v19+ 走索引，v16–v18 走平铺目录）。"""
    if str(version) in _LEGACY_FLAT:
        p = _flat_src_file(version, script)
        if p:
            return p
    return _script_path(version, script)


def script_rel_path(version, script):
    """
    某版本里某个官方脚本**相对于版本目录**的路径（引擎没有它 → ""）。

    ★ `engine_files(version, files=[...])` 收的就是这种相对路径，
      所以要「只覆盖某一个脚本」时先拿这个函数取路径。
    """
    p = script_src_path(version, script)
    if not p:
        return ""
    root = _ver_dir(version)
    try:
        rel = os.path.relpath(p, root)
    except ValueError:                 # 跨盘（基本不会）
        return ""
    if rel.startswith(".."):
        return ""
    return rel.replace("/", os.sep)


def legacy_abs_files(version):
    """（兼容旧调用）该版本 debug 菜单脚本的绝对路径列表。"""
    return [p for p in (script_src_path(version, n)
                        for n in overwrite_script_names(version)) if p]



def src_root():
    return config.resource_path(SRC_DIR_NAME)


def list_versions():
    d = src_root()
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if os.path.isdir(os.path.join(d, f)):
            out.append(f)
    return sorted(out, key=_vkey)


def _vkey(t):
    try:
        return tuple(int(x) for x in str(t).split("."))
    except ValueError:
        return (999,)


def _ver_dir(version):
    return os.path.join(src_root(), str(version))


def debug_menu_files(version):
    """
    debug 菜单脚本的相对路径列表（相对于版本目录）。

    ★ 走的是**版本化覆盖清单** `overwrite_script_names()`，
      不再是「目录里有什么就覆盖什么」——只覆盖游戏内的 debug。
    """
    names = overwrite_script_names(version)
    if not names:
        return []
    sub = os.path.join(_ver_dir(version), DEBUG_MENU_SUBDIR)
    if os.path.isdir(sub):
        have = {re.sub(r"^\d+_", "", f[:-3]): os.path.join(DEBUG_MENU_SUBDIR, f)
                for f in os.listdir(sub) if f.endswith(".rb")}
        return [have[n] for n in names if n in have]
    # ★ v16 / v17 / v18：扁平布局，没有子目录 —— 取实际文件名
    out = []
    for n in names:
        p = _flat_src_file(version, n)
        if p:
            out.append(os.path.basename(p))
    return out


def engine_files(version, files=None):
    """
    某版本官方脚本的绝对路径列表。

    files=None → 用 debug 菜单脚本；否则用给定的相对路径列表。
    """
    rels = files if files is not None else debug_menu_files(version)
    out = []
    for rel in rels:
        p = os.path.join(_ver_dir(version), rel)
        if os.path.isfile(p):
            out.append(p)
    return out


def load_translations():
    """读英→中对照表 → {英文: 中文}。找不到返回 {}。"""
    p = os.path.join(src_root(), "debug_menu_zh.json")
    if not os.path.isfile(p):
        return {}
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data.get("translations") or {}


_TR_RE = re.compile(r'_INTL\(\s*"((?:[^"\\]|\\.)*)"\s*\)')


def apply_translation(text, tr):
    """
    把 `_INTL("英文")` 换成 `_INTL("中文")`（只换对照表里有的）。
    返回 (新文本, 替换条数)。
    """
    if not tr:
        return text, 0
    n = 0

    def rep(m):
        nonlocal n
        s = m.group(1)
        zh = tr.get(s)
        if zh is None:
            return m.group(0)
        n += 1
        return f'_INTL("{zh}")'
    return _TR_RE.sub(rep, text), n


# ================================================================
# 函数级源码定位（报告页对比 / 回写用）
# ================================================================
_DEF_LINE_RE = re.compile(r"^([ \t]*)def\b")


def extract_func(text, func):
    """
    从脚本文本里抠出某个函数（def … end，含嵌套）的源码。

    func 是限定名，可能形如 `ClassName.method` / `self.method` / `method`。
    只用最后一段（方法名）来匹配 `def name`。
    找不到返回 ""。
    """
    name = str(func).split(".")[-1].strip()
    if not name:
        return ""
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        m = re.match(r"^([ \t]*)def\s+" + re.escape(name) + r"\b", ln)
        if not m:
            continue
        base = len(m.group(1))
        j = i + 1
        while j < len(lines):
            s = lines[j]
            st = s.strip()
            if st == "" or st.startswith("#"):
                j += 1
                continue
            if re.match(r"^[ \t]*end[ \t]*\r?$", s):
                cur = len(s) - len(s.lstrip(" \t"))
                if cur <= base:
                    break
            j += 1
        if j >= len(lines):
            j = len(lines) - 1
        return "\n".join(lines[i:j + 1])
    return ""


def replace_func(text, func, new_src):
    """
    把脚本文本里的某函数替换成 new_src。返回新文本；没找到返回 None。
    """
    old = extract_func(text, func)
    if not old:
        return None
    return text.replace(old, new_src, 1)


def func_source(version, script, func):
    """取官方某版本某脚本里某函数的源码。找不到返回 ""。"""
    path = _script_path(version, script)
    if not path:
        return ""
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except OSError:
        return ""
    return extract_func(txt, func)


_index_cache = {}


def _script_index(version):
    """某版本的 {归一化脚本名: [文件路径, ...]}（带缓存，避免每次 walk）。"""
    key = str(version)
    if key in _index_cache:
        return _index_cache[key]
    idx = {}
    for p in _all_engine_scripts(version):
        name = os.path.splitext(os.path.basename(p))[0]
        name = re.sub(r"^\d+_", "", name)
        idx.setdefault(_norm(name), []).append(p)
    _index_cache[key] = idx
    return idx


def _script_path(version, script):
    """按脚本名找官方源文件路径（取第一个）。找不到返回 ""。"""
    hits = _script_index(version).get(_norm(script))
    if not hits:
        return ""
    # 优先取路径更短（更靠顶层）的那份
    hits = sorted(hits, key=lambda p: (len(p), p))
    return hits[0]


def _all_engine_scripts(version):
    d = _ver_dir(version)
    if not os.path.isdir(d):
        return []
    out = []
    for dp, _dn, fs in os.walk(d):
        for f in fs:
            if f.endswith(".rb"):
                out.append(os.path.join(dp, f))
    return out


def _norm(s):
    return re.sub(r"[^0-9a-z]+", "", str(s).lower())
