# -*- coding: utf-8 -*-
"""
「开启 DEBUG」—— 往游戏里写 $DEBUG=true，并把 debug 启动时会炸的那两件事关掉。

为什么需要
----------
Essentials 的调试模式（$DEBUG）才能用游戏里的「Extract Text / Compile Text」
等菜单。但一开 $DEBUG，启动时会走 `Compiler.main`：

      mustCompile = true（PBS 比 .dat 新 / 缺 .dat / 按住了 Ctrl …）
      → 把 Data/*.dat 全部删掉        ← ① 删 dat
      → compile_all(true) 全量重编译  ← ② 全量编译

编译一旦失败（PBS 有坑、插件打架，同人游戏里太常见），rescue 分支会**再删一遍
Data/*.dat**，游戏直接变砖。所以开 DEBUG 的同时必须把这两步关掉。

本模块做的事
------------
  ① 版本识别 + 基本函数比对（见 essentials_base）—— 作者改过引擎就先警告；
  ② Main 脚本的 `mainFunction` 里插一行 `$DEBUG=true`；
  ③ 清掉脚本里的「反调试」代码：有些同人游戏在 Scene_Map#update 里塞了
     `if $DEBUG → $scene=nil`、`$DEBUG = false`，每帧把 $DEBUG 摁回 false，
     我们写的 $DEBUG=true 活不过一帧 —— 不改掉它开 DEBUG 等于没开。这里把
     这些行**整段注释掉**（原文留着，随时能还原）；
  ④ Compiler 脚本的 `main` 开头插一道闸：数据已经编译好就**直接 return**
     （不删 dat、不全量编译）；按住 Ctrl 启动仍然走原逻辑，随时能真编译；
  ⑤ 改动前备份（**只在第一次改动前备份一次**，之后复用同一份 .bak），
     随时「还原」。

★ ②③④ 都是纯文本改，不解包 / 不进游戏。脚本有两种存放形态：
  「已解包」Data/Scripts/**.rb、「未解包」Data/Scripts.rxdata；
  **两处并存时两处都改**（Game.ini 的 Scripts= 指向哪份哪份才算数，
  只改一处就会出现「改了没效果」）。
★ ③「反调试」检测**额外**把插件脚本 `Data/PluginScripts.rxdata` 也算进来
  （v19+ 的插件机制；游戏真正 eval 的就是插件里那份）。按用户要求，
  其它检测（基准比对 / 方式二 / 版本识别）一律不看插件脚本。
"""
import io
import json
import os
import re
import shutil
import time

import config
import essentials_base as EB
import game_scripts as GS
from logger import get_logger

log = get_logger("debug_tool")

# 备份文件名里带的标记（还原时靠它认领）
BAK_MARK = ".pkmn-debug-"

# 插进 mainFunction 的那一行
DEBUG_LINE = "$DEBUG=true"
# 插进 Compiler.main 的闸门
# ★ 每一行都带上 [pkmn-debug] 标记 —— 包括真正执行的那两行：
#   它们会改变 Compiler.main 的函数体，只标注释行的话比对仍会报「改过」。
# ★ 标记要够独特：游戏代码里就有叫 pkmn 的变量（[pkmn] / newPokemon[pkmn]），
#   用 [pkmn] 当标记会把人家的正常代码整行删掉。
_GUARD_LINES = (
    f"# {EB.PATCH_MARK} 翻译工具注入：数据已编译好时不再删 Data/*.dat、"
    "不再全量重编译。",
    f"# {EB.PATCH_MARK} （按住 Ctrl 启动仍然会编译 —— 与原版行为一致；"
    "删掉这几行即可还原）",
    f"Input.update  # {EB.PATCH_MARK}",
    "return if !Input.press?(Input::CTRL) && FileTest.exist?(\"Data/species.dat\")"
    f" && FileTest.exist?(\"Data/moves.dat\")  # {EB.PATCH_MARK}",
)
GUARD_MARK = f"{EB.PATCH_MARK} 翻译工具注入"

_MAIN_FUNC_RE = re.compile(r"^([ \t]*)def\s+mainFunction\b", re.M)
_COMPILER_MAIN_RE = re.compile(r"^([ \t]*)def\s+main\s*(?:#.*)?$", re.M)
_NO_DEBUG_RE = re.compile(r"^([ \t]*)return\s+if\s+!\$DEBUG\s*(?:#.*)?$", re.M)
_MODULE_COMPILER_RE = re.compile(r"^module\s+Compiler\b", re.M)

# ★ 判断「$DEBUG=true 已经写过了」时，**只认一整行就只有 $DEBUG=true** ——
#   像 `if $DEBUG=true`（那是条件判断 / 误写成 = 的老代码）不算写过，
#   否则我们就不插那一行，DEBUG 永远开不起来。
_DEBUG_SET_RE = re.compile(r"^[ \t]*\$DEBUG\s*=\s*true\s*(?:#.*)?[ \t]*\r?$",
                           re.M)

# ------------------------------------------------------------------
# 「反调试」代码：有些同人游戏在 Scene_Map#update 里塞了这么一段 ——
#
#     if $DEBUG
#       $scene=nil
#     end
#     $DEBUG = false
#
# 每帧都把 $DEBUG 摁回 false（我们写的 $DEBUG=true 活不过一帧），
# 同时 $scene=nil 把地图场景踢掉。不改掉它，开 DEBUG 等于没开。
#
# 处理办法（见 patch_antidebug）：把这些行**整段注释掉** ——
# 加 `# [pkmn-debug] ` 前缀。原文留在文件里看得见、随时能还原；
# 比对时会被 essentials_base.strip_own_patch 抹掉，不会误报「被改」。
#
# ★ 触发规则（用户指定）：
#   ① 在 **Scene_Map** 里检测到 `if $DEBUG … end` → 直接触发；
#   ② 检测到 `$DEBUG = false` / `$DEBUG=false` → 直接注释掉（就这一行）。
# ------------------------------------------------------------------
ANTIDEBUG_MODE = "comment"          # "comment"（默认，注释掉）/ "delete"

# ------------------------------------------------------------------
# 反调试「白名单」
#   有些 `if $DEBUG … end` 其实是引擎自带的正常代码（最典型的就是下面这条
#   「按 F9 呼出调试菜单」），不该被当成反调试注释掉。命中的块直接跳过。
#   用户在复核窗口里点「加入白名单」会往同一个文件里追加，下次不再问。
# ------------------------------------------------------------------
ANTIDEBUG_WL_FILE = os.path.join(config.BASE_DIR, "antidebug_whitelist.json")
# ★ 内置白名单（用户指定）：Scene_Map 里这段不是反调试
ANTIDEBUG_WL_BUILTIN = (
    "if $DEBUG and Input.press?(Input::F9)\n"
    "$game_temp.debug_calling = true\n"
    "end",
)
_DEBUG_ASSIGN_RE = re.compile(r"^([ \t]*)\$DEBUG\s*=\s*false\b")
_IF_DEBUG_RE = re.compile(r"^([ \t]*)if\s+\$DEBUG\b")
_END_LINE_RE = re.compile(r"^([ \t]*)end[ \t]*\r?$")
_ANTIDEBUG_FIXED_RE = re.compile(
    r"^[ \t]*#[^\n]*" + re.escape(EB.PATCH_MARK) + r"[^\n]*\$DEBUG", re.M)


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"


# 本次运行里已经备份过的文件：绝对路径 → 备份文件路径
# ★ 同一个文件常常要改两处（Main 和 Compiler 都在 Scripts.rxdata 里），
#   第二次绝不能再备份一遍 —— 那时文件已经被改过，备份下来的是「改了一半
#   的中间状态」，既不是原始文件，还会把真正的第一份备份挤掉。
_backed_up = {}


def _reset_backups():
    """每次「开启 / 还原」前清一遍（同一进程里可能连做好几次）。"""
    _backed_up.clear()


def _norm_name(name):
    """脚本名归一化（比对用）：只留字母数字，忽略大小写。"""
    return re.sub(r"[^0-9A-Za-z]+", "", str(name or "")).lower()


def _where(src):
    """给日志用的一句话定位：脚本名（脚本编辑器那一栏）+ 具体文件 / 条目。"""
    name = src.get("name")
    mode = src.get("mode")
    if mode == "plugin":
        # 插件脚本的 name 本身就是 `[插件名] 文件名`
        return "插件「%s」（%s）" % (name, os.path.basename(str(src["path"])))
    if mode == "rxdata":
        spot = f"{os.path.basename(str(src['path']))} 第 {src['key']} 条"
    else:
        spot = str(src["key"])
    return f"「{name}」· {spot}" if name else spot


def _eol_of(line):
    return "\r" if line.endswith("\r") else ""


def _insert_after(lines, idx, new_lines, eol):
    return lines[:idx + 1] + [x + eol for x in new_lines] + lines[idx + 1:]


# ================================================================
# 主脚本：mainFunction 里写 $DEBUG=true
# ================================================================
def find_main_sources(game_dir):
    """
    找出**所有**要写 `$DEBUG=true` 的脚本 —— **按脚本名找 Main**
    （就是 RMXP 脚本编辑器左边那一栏的 Main）。

    ★ 返回列表：v21 起很多游戏「Data/Scripts/**.rb（解包源码）」和
      「Data/Scripts.rxdata（运行时读的那份）」并存，**两处都要写**，
      否则改了不生效的那份（Game.ini 的 Scripts= 指向哪份，哪份才算数）。

    Main 里没有 `def mainFunction` 时（极少见，作者可能改名了），
    退回「第一份带 mainFunction 的脚本」。
    """
    named, fallback = [], []
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                            both=True):
        m = _MAIN_FUNC_RE.search(text)
        if not m:
            continue
        src = {"mode": mode, "key": key, "path": path, "text": text,
               "name": name, "match": m}
        if _norm_name(name) == "main":
            named.append(src)
        else:
            fallback.append(src)
    if named:
        return named
    return fallback[:1]


def find_main_source(game_dir):
    """（兼容旧调用）第一份 Main。"""
    srcs = find_main_sources(game_dir)
    return srcs[0] if srcs else None


def patch_main_function(text):
    """
    在 `def mainFunction` 的下一行插入 `$DEBUG=true`。
    返回 (新文本, {"added": bool, "existed": bool})；找不到 mainFunction 抛 ValueError。
    """
    m = _MAIN_FUNC_RE.search(text)
    if not m:
        raise ValueError("脚本里没有 `def mainFunction`（Main 脚本不对？）")
    lines = text.split("\n")
    i = text.count("\n", 0, m.start())
    # 已经写过了 → 不动（幂等）
    for j in range(i, min(i + 4, len(lines))):
        if _DEBUG_SET_RE.search(lines[j]):
            return text, {"added": False, "existed": True}
    indent = m.group(1) or ""
    eol = _eol_of(lines[i])
    new_lines = _insert_after(lines, i, [indent + "  " + DEBUG_LINE], eol)
    return "\n".join(new_lines), {"added": True, "existed": False}


def remove_debug_from_main(game_dir, emit=None):
    """
    把 Main 的 `mainFunction` 里 `$DEBUG = true` 那行**删掉**。返回 {"removed", "targets"}。

    ★ 什么时候用：用户选了「不设 $DEBUG」的方式（②–⑦），但之前用方式① 写过，
      换方式后那行还留在 Main 里 —— 它和用户的选择直接矛盾，而且方式⑦ 会被
      反调试的 `exit if $DEBUG` 每帧踢出游戏。
    ★ 只删**紧跟 `def mainFunction` 的那几行内、且值为 true** 的一行：
      这正是 `patch_main_function` 插入的位置和内容 → 能精确对应「是我们插的」，
      不会碰到脚本里其它地方写 `$DEBUG` 的代码，也不会碰 `$DEBUG = false`。
    """
    def say(msg):
        if emit:
            emit(msg)

    rep = {"removed": 0, "targets": []}
    try:
        mains = find_main_sources(game_dir)
    except (OSError, RuntimeError) as e:
        say(f"[DEBUG] ⚠ 找 Main 脚本失败：{e}")
        return rep
    for src in mains:
        lines = src["text"].split("\n")
        m = _MAIN_FUNC_RE.search(src["text"])
        if not m:
            continue
        i = src["text"].count("\n", 0, m.start())
        hit = -1
        for j in range(i, min(i + 4, len(lines))):
            if _DEBUG_SET_RE.search(lines[j]):
                hit = j
                break
        if hit < 0:
            continue
        new_text = "\n".join(lines[:hit] + lines[hit + 1:])
        try:
            _write_text(src["mode"], src["path"], src["key"], new_text,
                        old_text=src["text"], emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[DEBUG] ⚠ 移除 {DEBUG_LINE} 失败（{_where(src)}）：{e}")
            continue
        rep["removed"] += 1
        rep["targets"].append({"mode": src["mode"], "where": str(src["key"])})
        say(f"[DEBUG] ✔ 已移除 {_where(src)} mainFunction 里残留的 "
            f"{DEBUG_LINE}（本方式不需要它）")
    if not rep["removed"]:
        say("[DEBUG] · Main 里本来就没有多余的 $DEBUG=true，不用清理")
    return rep


# ================================================================
# Compiler 脚本：去掉「删 dat + 全量编译」
# ================================================================
def find_compiler_sources(game_dir):
    """
    找出**所有**要装闸门的脚本 —— **按脚本名找 Compiler**，并且它得有
    `module Compiler` + `def main`（v19 起才有这一段）。

    ★ 返回列表：Data/Scripts/**.rb 与 Data/Scripts.rxdata 两处都要装。
    ★ 别认错：LUTS 也有个脚本文件叫 Compiler
      （`058_Utilities/…/002_Compiler.rb`），它没有 `module Compiler`，
      靠这个条件挡掉。

    脚本名对不上时退回「第一份含 module Compiler 的脚本」。
    """
    named, fallback = [], []
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                            both=True):
        if not _MODULE_COMPILER_RE.search(text):
            continue
        m = _COMPILER_MAIN_RE.search(text)
        if not m:
            continue
        src = {"mode": mode, "key": key, "path": path, "text": text,
               "name": name, "match": m}
        if _norm_name(name) == "compiler":
            named.append(src)
        elif not fallback:
            fallback.append(src)
    return named or fallback


def find_compiler_source(game_dir):
    """（兼容旧调用）第一份 Compiler。"""
    srcs = find_compiler_sources(game_dir)
    return srcs[0] if srcs else None


def patch_compiler_main(text):
    """
    在 Compiler.main 的开头插一道闸（数据已编译好就直接 return）。
    返回 (新文本, {"added": bool, "existed": bool})。
    """
    m = _COMPILER_MAIN_RE.search(text)
    if not m:
        raise ValueError("没找到 Compiler 的 `def main`")
    if GUARD_MARK in text:
        return text, {"added": False, "existed": True}
    lines = text.split("\n")
    i = text.count("\n", 0, m.start())
    # 有 `return if !$DEBUG` 就插在它后面，否则紧跟 def main
    j = i
    mm = _NO_DEBUG_RE.match(lines[i + 1]) if i + 1 < len(lines) else None
    if mm:
        j = i + 1
    indent = m.group(1) or ""
    body = [indent + "  " + x for x in _GUARD_LINES]
    new_lines = _insert_after(lines, j, body, _eol_of(lines[j]))
    return "\n".join(new_lines), {"added": True, "existed": False}


# ================================================================
# 反调试：Scene_Map 里那段「把 $DEBUG 摁死」的代码
# ================================================================
def _find_if_debug_blocks(lines):
    """
    找 `if $DEBUG … end` 块 → [{"start", "end"}]（用缩进 + `end` 配对）。

    ★ 只在 **Scene_Map** 里用（见 find_antidebug_sources）——用户指定：
      Scene_Map 里出现 `if $DEBUG` 就触发。
    ★ `#` 开头的行跳过（保证幂等）。
    """
    blocks = []
    for i, ln in enumerate(lines):
        m = _IF_DEBUG_RE.match(ln)
        if not m:
            continue
        base = len(m.group(1))
        j = i + 1
        end = None
        while j < len(lines):
            s = lines[j]
            st = s.strip()
            if st.startswith("#") or st == "":
                j += 1
                continue
            if _END_LINE_RE.match(s):
                end = j
                break
            cur = len(s) - len(s.lstrip(" \t"))
            if cur <= base:
                # 没等到 end 就退到同级了 —— 当作单行块，保守收 i..j-1
                end = j - 1
                break
            j += 1
        if end is None:
            end = j - 1
        if end < i:
            end = i
        blocks.append({"start": i, "end": end})
    return blocks


def _find_debug_false_lines(lines):
    """找光秃秃一行 `$DEBUG = false` → [{"start": i, "end": i}]。"""
    return [{"start": i, "end": i} for i, ln in enumerate(lines)
            if _DEBUG_ASSIGN_RE.match(ln)]


def patch_antidebug(text, blocks, mode=None):
    """
    把给定的「反调试」代码块注释掉（或删掉）。返回 (新文本, info)。

    blocks 由 _find_if_debug_blocks / _find_debug_false_lines 得到。
    info = {"added", "existed", "blocks", "mode"}。
    """
    mode = mode or ANTIDEBUG_MODE
    if not blocks:
        return text, {"added": False, "existed": False, "blocks": 0,
                      "mode": mode}
    lines = text.split("\n")
    if mode == "delete":
        drop = set()
        for b in blocks:
            drop.update(range(b["start"], b["end"] + 1))
        out = [ln for k, ln in enumerate(lines) if k not in drop]
        return "\n".join(out), {"added": True, "existed": False,
                                "blocks": len(blocks), "mode": mode}
    out = list(lines)
    for b in blocks:
        for k in range(b["start"], b["end"] + 1):
            # 保留原缩进，行首插入 `# [pkmn-debug] `（原文原样留着）
            out[k] = re.sub(r"^([ \t]*)", r"\1# " + EB.PATCH_MARK + " ", out[k])
    return "\n".join(out), {"added": True, "existed": False,
                            "blocks": len(blocks), "mode": mode}


def norm_code(text):
    """
    代码归一化（白名单比对用）：去注释行 / 空行，压掉所有空白，转小写，
    `&&` `||` 统一成 `and` `or` —— 让
    `if $DEBUG && Input.press?(Input::F9)` 和 `if $DEBUG and …` 算同一段。
    """
    out = []
    for ln in (text or "").split("\n"):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        s = s.replace("&&", "and").replace("||", "or")
        s = re.sub(r"\s+", "", s).lower()
        if s:
            out.append(s)
    return "\n".join(out)


def load_antidebug_whitelist():
    """内置 + 用户白名单 → 归一化后的 [set, 原始文本 list]。"""
    items = list(ANTIDEBUG_WL_BUILTIN)
    try:
        if os.path.isfile(ANTIDEBUG_WL_FILE):
            with io.open(ANTIDEBUG_WL_FILE, "r", encoding="utf-8") as f:
                d = json.load(f) or {}
            for s in (d.get("code") or []):
                s = str(s)
                if s.strip():
                    items.append(s)
    except Exception as e:      # noqa: BLE001
        log.warning("反调试白名单读取失败（只用内置那份）：%s", e)
    return {norm_code(x) for x in items if norm_code(x)}, items


def add_antidebug_whitelist(code):
    """把一段代码加进白名单（幂等）。返回 (是否新增, 全部条数)。"""
    _n, items = load_antidebug_whitelist()
    key = norm_code(code)
    if not key:
        return False, len(items)
    if key in {norm_code(x) for x in items}:
        return False, len(items)
    items.append(code)
    try:
        tmp = ANTIDEBUG_WL_FILE + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "code": items}, f,
                      ensure_ascii=False, indent=2)
        os.replace(tmp, ANTIDEBUG_WL_FILE)
    except OSError as e:
        log.warning("反调试白名单写入失败：%s", e)
        return False, len(items)
    return True, len(items)


def remove_antidebug_whitelist(code):
    """从用户白名单里删一段（内置的删不掉）。"""
    _n, items = load_antidebug_whitelist()
    builtin = {norm_code(x) for x in ANTIDEBUG_WL_BUILTIN}
    key = norm_code(code)
    rest = [x for x in items if norm_code(x) != key or norm_code(x) in builtin]
    try:
        tmp = ANTIDEBUG_WL_FILE + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "code": rest}, f,
                      ensure_ascii=False, indent=2)
        os.replace(tmp, ANTIDEBUG_WL_FILE)
    except OSError as e:
        log.warning("反调试白名单写入失败：%s", e)
        return False
    return True


def is_whitelisted(code):
    keys, _items = load_antidebug_whitelist()
    return norm_code(code) in keys


def src_key(src):
    """一个脚本的唯一键（复核窗口的「决定」按它认领）。"""
    return "%s|%s" % (src.get("mode"), src.get("key"))


def block_text(text, blocks):
    """把 blocks 覆盖到的原始代码行拼成文本（给用户看 / 进白名单用）。"""
    lines = text.split("\n")
    out = []
    for b in sorted(blocks, key=lambda x: x["start"]):
        out.extend(lines[b["start"]:b["end"] + 1])
    return "\n".join(out)


def region_of(text, blocks, ctx=3):
    """blocks 前后各带 ctx 行上下文 → (起始行, 结束行)（0 基，闭区间）。"""
    lines = text.split("\n")
    lo = max(0, min(b["start"] for b in blocks) - ctx)
    hi = min(len(lines) - 1, max(b["end"] for b in blocks) + ctx)
    return lo, hi


def region_text(text, blocks, ctx=3):
    lo, hi = region_of(text, blocks, ctx)
    return "\n".join(text.split("\n")[lo:hi + 1])


def antidebug_decision(text, blocks, ctx=3, edited=None):
    """
    复核窗口的一份「决定」：只记**那一段原文 + 块在这段里的相对行号**。

    ★ 不记绝对行号 —— 开启 DEBUG 时第②步会先往 Main 里插 `$DEBUG=true`，
      行号会整体后移；按原文定位才不会错行。
    edited 给了就是用户手改后的那段；没给表示「自动注释」。
    """
    lines = text.split("\n")
    lo, hi = region_of(text, blocks, ctx)
    return {"ctx": ctx,
            "orig": "\n".join(lines[lo:hi + 1]),
            "rel": [[b["start"] - lo, b["end"] - lo] for b in blocks],
            "edited": edited}


def apply_antidebug_decision(text, dec, auto_comment=False):
    """
    按复核窗口的决定改整份脚本 → 新文本；找不到那段 / 没变化返回 None。

    auto_comment=True（用户点的「自动注释」）时，把 dec["rel"] 那些行
    加上 `# [pkmn-debug] `。
    """
    lines = text.split("\n")
    orig = dec.get("orig") or ""
    o = orig.split("\n")
    lo = hi = None
    if o and len(o) <= len(lines):
        for k in range(0, len(lines) - len(o) + 1):
            if lines[k:k + len(o)] == o:
                lo, hi = k, k + len(o) - 1
                break
    if lo is None:
        return None
    edited = dec.get("edited")
    if edited is not None and edited != orig:
        rep = edited.split("\n")
    elif auto_comment:
        rel = [{"start": s, "end": e} for s, e in (dec.get("rel") or [])]
        reg, _info = patch_antidebug(orig, rel)
        if reg == orig:
            return None
        rep = reg.split("\n")
    else:
        return None
    return "\n".join(lines[:lo] + rep + lines[hi + 1:])


def find_antidebug_sources(game_dir, use_whitelist=True):
    """
    找出含「反调试」代码的脚本 → [src, ...]（src 里带挑好的 blocks）。

    ★ 用户指定规则：
      ① **Scene_Map** 里出现 `if $DEBUG … end` → 整个 if 块；
      ② 任何脚本里出现 `$DEBUG = false`（`$DEBUG = false` / `$DEBUG=false`）
         → 那一行。
      两者都注释掉。
    ★ both=True：解包 .rb 与 Scripts.rxdata 并存时两处都要清。
    ★ **插件脚本（Data/PluginScripts.rxdata）也算** —— 按用户要求，反调试
      检测是唯一把插件脚本算进来的检测；游戏真正 eval 的就是插件里那份，
      藏在那儿的 `$DEBUG = false` 照样能把调试模式摁死。
    ★ use_whitelist：命中白名单的块直接跳过（用户自己加的 + 内置那条
      「F9 呼出调试菜单」）。
    """
    out = []
    for mode, key, path, name, text in _all_antidebug_candidates(game_dir):
        lines = text.split("\n")
        keep = _find_debug_false_lines(lines)           # 规则②：任何脚本
        if _scenemap_like(mode, name, text):            # 规则①：仅 Scene_Map
            covered = {b["start"] for b in keep}
            for b in _find_if_debug_blocks(lines):
                if b["start"] not in covered and \
                        not any(b["start"] <= c <= b["end"] for c in covered):
                    keep.append(b)
        if not keep:
            continue
        keep.sort(key=lambda b: b["start"])
        if use_whitelist:
            keep = [b for b in keep
                    if not is_whitelisted("\n".join(
                        lines[b["start"]:b["end"] + 1]))]
            if not keep:
                continue
        out.append({"mode": mode, "key": key, "path": path, "text": text,
                    "name": name, "blocks": keep})
    return out


def _all_antidebug_candidates(game_dir):
    """
    「反调试」检测要扫的脚本：
      主脚本（解包 .rb + Scripts.rxdata，both=True）
      + 插件脚本（Data/PluginScripts.rxdata）。
    """
    for item in GS.iter_named_scripts(game_dir, both=True):
        yield item
    try:
        for item in GS.iter_plugin_scripts(game_dir):
            yield item
    except Exception as e:                            # noqa: BLE001
        log.warning("读插件脚本失败（反调试检测跳过插件部分）：%s", e)


_SCENEMAP_CLASS_RE = re.compile(r"^[ \t]*class\s+Scene_Map\b", re.M)


def _scenemap_like(mode, name, text):
    """
    这份脚本算不算「Scene_Map」（规则①只在 Scene_Map 里触发）。

      · 主脚本：脚本名里有 scenemap（`Scene_Map`、`Scene_Map_Fixes`…）；
      · 插件脚本：名字多半跟 Scene_Map 无关（`[插件名] Refresh.rb`），
        所以**再看内容** —— 里面重开了 `class Scene_Map` 就算。
    """
    if "scenemap" in _norm_name(name):
        return True
    if mode == "plugin":
        return bool(_SCENEMAP_CLASS_RE.search(text or ""))
    return False


def antidebug_fixed(game_dir):
    """游戏里是否已经被本工具注释过反调试代码（含插件脚本）。"""
    for _m, _k, _p, _n, text in _all_antidebug_candidates(game_dir):
        if _ANTIDEBUG_FIXED_RE.search(text):
            return True
    return False


# ================================================================
# 写回
# ================================================================
def _find_existing_backup(path):
    """
    找这个文件**之前**留下的本工具备份（`<文件名>.pkmn-debug-*.bak`）。

    找到返回**最早**那份（它才是原始文件），没有返回 None。
    """
    d = os.path.dirname(os.path.abspath(path))
    pref = os.path.basename(path) + BAK_MARK
    try:
        hits = [os.path.join(d, f) for f in os.listdir(d)
                if f.startswith(pref) and f.endswith(".bak")]
    except OSError:
        return None
    hits.sort()
    return hits[0] if hits else None


def _backup(path, emit=None):
    """
    备份：**把脚本源文件直接改名为 .bak，再复制一份回原位置**，
    接下来所有修改都作用在复制出来的那份上。

    ★ 这样 .bak 里是**改名那一刻的原文件**（绝对干净），
      原路径上的文件照旧存在、游戏/编辑器读得到，但它是用来改的副本。
    ★ 还原只要把改过的那份删掉、.bak 改回原名即可（见 restore）。

    ★ **只备份一次**：同一个文件在一次运行里只备份一次（见 _backed_up）；
      而且**跨运行**也复用旧的 —— 如果这个文件上次开 DEBUG 时已经留了
      本工具的 .bak，这次就直接用它，**不再新建**。这样反复开关/改动
      不会堆出一堆 .bak，.bak 里也始终是最初那份原始文件。
    """
    ap = os.path.abspath(path)
    done = _backed_up.get(ap)
    if done:
        return done
    old = _find_existing_backup(path)          # 上次留下的备份？
    if old:
        _backed_up[ap] = old
        if emit:
            emit(f"[DEBUG]   这个文件之前已备份过，直接复用、不再新建："
                 f"{os.path.basename(old)}")
        return old
    bak = f"{path}{BAK_MARK}{_stamp()}.bak"
    if os.path.exists(bak):
        os.remove(bak)
    os.rename(path, bak)              # ① 改名 → .bak 里是原始内容
    shutil.copyfile(bak, path)        # ② 复制回来 → 原位置继续存在，供修改
    _backed_up[ap] = bak
    if emit:
        emit(f"[DEBUG]   原文件已备份：{os.path.basename(bak)}")
    return bak


def _no_eol(text):
    """去掉换行的差异（比对「内容是不是同一份」时用）。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _note_backup(rep, bak):
    """记下用到的备份（同一个文件只记一次 —— Main 和 Compiler 常在同一份里）。"""
    if bak and bak not in rep["backups"]:
        rep["backups"].append(bak)


def _write_text(mode, path, key, new_text, old_text=None, emit=None):
    """
    把改动写回 .rb 文件 / Scripts.rxdata / PluginScripts.rxdata（先备份再改）。

    old_text 是「补丁所依据的原文」：写之前会核对目标现在的内容确实
    还是它 —— 对不上就报错收手。这是防「下标算错、把 A 脚本的代码
    写进 B 条目」的最后一道闸（rxdata 里空标记也占位置，最容易错位）。
    """
    bak = _backup(path, emit=emit)
    if mode == "file":
        # ★ 按二进制读：文本模式会把 \r\n 吞成 \n，既没法比对，写回去还会
        #   把整份文件的换行悄悄改成 LF。
        with open(path, "rb") as f:
            cur = f.read().decode("utf-8", "replace")
        if old_text is not None and _no_eol(cur) != _no_eol(old_text):
            raise RuntimeError(
                f"「{os.path.basename(path)}」的内容和检测时读到的不一致，"
                "已拒绝写入（文件被别的程序改过？）")
        if "\r\n" in cur and "\r\n" not in new_text:
            new_text = new_text.replace("\n", "\r\n")     # 原文 CRLF → 照旧
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        return bak
    if mode == "plugin":
        GS.write_plugin_entry(path, key, new_text, expect=old_text)
        return bak
    GS.write_rxdata_entry(path, key, new_text, expect=old_text)
    return bak


# ================================================================
# 状态
# ================================================================
def status(game_dir):
    """
    看看这个游戏现在什么状态 → dict：
      version / has_main / has_compiler / debug_on / guarded
      / debug_partial / guarded_partial / antidebug / antidebug_fixed
      / backups（本工具做的备份文件列表）

    ★ debug_on / guarded 是「**两处都**已处理」才算 True —— 解包 .rb 与
      Scripts.rxdata 并存时，只写了一处的话对应 partial 为 True。
    ★ antidebug：脚本里还残留着没处理的「反调试」代码（`$DEBUG = false`
      之类）；antidebug_fixed：已经被本工具注释掉了。
    """
    out = {"version": EB.detect_version(game_dir), "has_main": False,
           "has_compiler": False, "debug_on": False, "guarded": False,
           "debug_partial": False, "guarded_partial": False,
           "antidebug": False, "antidebug_fixed": False, "backups": []}
    mains = find_main_sources(game_dir)
    if mains:
        out["has_main"] = True
        flags = []
        for src in mains:
            st = src["match"].start()
            body = src["text"][st:st + 300]
            flags.append(bool(_DEBUG_SET_RE.search(body)))
        out["debug_on"] = all(flags)
        out["debug_partial"] = any(flags) and not all(flags)
    comps = find_compiler_sources(game_dir)
    if comps:
        out["has_compiler"] = True
        flags = [GUARD_MARK in src["text"] for src in comps]
        out["guarded"] = all(flags)
        out["guarded_partial"] = any(flags) and not all(flags)
    out["antidebug"] = bool(find_antidebug_sources(game_dir))
    out["antidebug_fixed"] = antidebug_fixed(game_dir)
    out["backups"] = list_backups(game_dir)
    return out


def list_backups(game_dir):
    """列出本工具做过的备份（可按名字认领）。"""
    out = []
    data = GS.data_dir(game_dir)
    if not os.path.isdir(data):
        return out
    for f in sorted(os.listdir(data)):
        if BAK_MARK in f and f.endswith(".bak"):
            out.append(os.path.join(data, f))
    # 解包成 .rb 的游戏：备份在 Data/Scripts 下面
    sdir = GS.scripts_dir(game_dir)
    if os.path.isdir(sdir):
        for dp, _dn, fs in os.walk(sdir):
            for f in sorted(fs):
                if BAK_MARK in f and f.endswith(".bak"):
                    out.append(os.path.join(dp, f))
    return out


def restore(game_dir, emit=None):
    """把本工具改过的脚本还原回去。返回报告 dict。"""
    def say(msg):
        if emit:
            emit(msg)

    baks = list_backups(game_dir)
    if not baks:
        say("[DEBUG] 没找到本工具做过的备份，无需还原")
        return {"ok": True, "restored": 0, "files": []}

    # ★ 同一个文件可能留下多份备份（不同时间跑的），名字里带时间戳 ——
    #   取**最早**那份，它才是这个文件被打补丁之前的样子；
    #   较新的那几份是「已经改过一半」的中间状态，还原时直接删掉。
    by_target = {}
    for bak in baks:
        by_target.setdefault(bak.split(BAK_MARK)[0], []).append(bak)

    done = []
    for target, group in by_target.items():
        group.sort()                       # 名字里的时间戳决定先后
        bak = group[0]
        try:
            # ★ 备份是「改名为 .bak」，还原就是反过来：
            #   删掉改过的那份，再把 .bak 改名回原样 —— .bak 里是原始内容。
            if os.path.exists(target):
                os.remove(target)
            os.rename(bak, target)
            done.append(os.path.basename(target))
            say(f"[DEBUG] 已还原 {os.path.basename(target)}")
        except OSError as e:
            log.warning("还原 %s 失败：%s", bak, e)
            say(f"[DEBUG] ⚠ 还原 {os.path.basename(target)} 失败：{e}")
            continue
        for extra in group[1:]:            # 多余的同名备份：删掉，别越积越多
            try:
                os.remove(extra)
            except OSError:
                pass
    say(f"[DEBUG] 共还原 {len(done)} 处改动")
    return {"ok": True, "restored": len(done), "files": done}


# ================================================================
# 一键开启
# ================================================================
def enable_debug(game_dir, emit=None, force=False, antidebug_plan=None,
                 write_debug=True, guard=True):
    """
    开启 DEBUG：比对 → 写 $DEBUG=true → 清反调试 → 关掉「删 dat + 全量编译」。

    force=True 时即使比对发现引擎被改过也照样写（界面上让用户确认过再用）。

    guard=False 时**不装编译闸门**（界面上「自动关闭全量编译」取消勾选）：
      调试模式启动会走 Compiler 的常规流程 —— 数据比 PBS 旧、或缺 dat 时
      会删 Data/*.dat 并全量重编译。默认 True（勾上）：装一道闸，
      数据已编译好就直接 return，按住 Ctrl 启动仍然会真编译一次。

    antidebug_plan：复核窗口给的决定 —— `{src_key: {"action", "text"}}`
      · action="comment" / "manual"，text 是**改好后的整份脚本文本** → 直接写；
      · action="skip" → 这一处不动（用户跳过了 / 加进白名单了）。
      没给（None）就按老规矩：发现即自动注释。

    ★★ write_debug=False：**不往 mainFunction 写 `$DEBUG=true`**。
      只有方式①（通用）需要这一步。方式②（删条件）本来就是把「需要 $DEBUG
      才生效」的判定删掉；方式⑦（改名调试函数）更不能设 —— 它的整套设计前提
      就是「全程不设 $DEBUG」（反调试里到处是 `exit if $DEBUG`，一设就退游戏）。
      ★ 以前 GUI 对所有非⑧方式都传 True，于是**换方式后 Main 里总会冒出
      `$DEBUG=true`**，很容易被误判成「还原没生效」。其余步骤（比对 /
      清反调试 / 关编译）照做。
    返回报告 dict：{"ok", "changed", "version", "baseline", "check", ...}
    """
    def say(msg):
        if emit:
            emit(msg)

    rep = {"ok": False, "changed": False, "version": "", "baseline": None,
           "debug": {}, "antidebug": {}, "guard": {}, "check": None,
           "backups": [], "reason": ""}
    _reset_backups()

    ok, why = GS.check_game_root(game_dir)
    if not ok:
        rep["reason"] = why
        say(f"[DEBUG] ✘ {why}")
        return rep

    ver = EB.detect_version(game_dir)
    rep["version"] = ver
    say(f"[DEBUG] 游戏根目录：{game_dir}")
    say(f"[DEBUG] Essentials 版本：{ver or '（脚本里读不到版本号）'}")

    # ---------- ① 基本函数比对 ----------
    check = EB.compare(game_dir, version=ver, emit=emit)
    rep["check"] = check
    rep["baseline"] = check.get("baseline")
    if check.get("reason"):
        # 基准都对不上（没有内置基准 / 改得太狠认不出）——也**不中止**，
        # 下面照样写 $DEBUG（写的是 Main 的 mainFunction，跟基准无关）。
        say(f"[DEBUG] ⚠ {check['reason']}；仍继续写入（只写 $DEBUG 开关，"
            "不依赖基准）")
    elif not check.get("ok"):
        # ★ 用户要求：引擎基本函数被改过 / 缺失时**默认继续写入**，不再中止。
        #   只是警告一下，方便排查「写了没生效」这类问题。
        say(f"[DEBUG] ⚠ 引擎基本函数与官方基准不一致（改 "
            f"{check.get('changed_n', 0)} / 缺 {check.get('missing_n', 0)}）"
            "—— 按默认继续写入")
        if force:
            say("[DEBUG] · 你已勾选「仍要继续」，照常执行")

    # ---------- ② mainFunction 里写 $DEBUG=true ----------
    if not write_debug:
        # ★ 只有方式①（通用）需要这一步。其余方式一律不写：
        #   · 方式② 删条件的做法本来就是把「需要 $DEBUG 才生效」的判定删掉；
        #   · 方式⑦ 的整套设计前提就是「不设 $DEBUG」（反调试 `exit if $DEBUG`）。
        #   比对 / 清反调试 / 关重编译照做。
        rep["debug"] = {"targets": [], "skipped": True}
        say("[DEBUG] · 本方式**不写 $DEBUG=true**（需要它请改用方式①「通用」）")
        # 顺手把以前用方式① 留下的那行清掉 —— 它和「不设 $DEBUG」直接矛盾，
        # 而且方式⑦ 会被反调试的 `exit if $DEBUG` 每帧踢出游戏。
        try:
            rep["debug"]["removed"] = remove_debug_from_main(
                game_dir, emit=emit)["removed"]
            if rep["debug"]["removed"]:
                rep["changed"] = True
        except (OSError, RuntimeError) as e:
            say(f"[DEBUG] ⚠ 清理残留 {DEBUG_LINE} 失败：{e}")
    else:
        mains = find_main_sources(game_dir)
        if not mains:
            rep["reason"] = "脚本里没找到 `def mainFunction`，没法写 $DEBUG=true"
            say(f"[DEBUG] ✘ {rep['reason']}")
            return rep
        rep["debug"] = {"targets": []}
        if len(mains) > 1:
            say(f"[DEBUG] Main 有 {len(mains)} 处（解包 .rb 与 Scripts.rxdata "
                "并存），两处都写，免得改了不生效的那份")
        for src in mains:
            new_text, info = patch_main_function(src["text"])
            where = _where(src)
            rec = {"mode": src["mode"], "where": str(src["key"]),
                   "added": info["added"], "existed": info["existed"],
                   "written": False}
            rep["debug"]["targets"].append(rec)
            if not info["added"]:
                say(f"[DEBUG] · {where} 的 mainFunction 里已经有 {DEBUG_LINE}，"
                    "跳过")
                continue
            try:
                bak = _write_text(src["mode"], src["path"], src["key"],
                                  new_text, old_text=src["text"], emit=emit)
            except (OSError, RuntimeError) as e:
                rep["reason"] = f"写入 {DEBUG_LINE} 失败（{where}）：{e}"
                say(f"[DEBUG] ✘ {rep['reason']}")
                return rep
            _note_backup(rep, bak)
            rep["changed"] = True
            rec["written"] = True
            say(f"[DEBUG] ✔ 已在 mainFunction 里写入 {DEBUG_LINE}（{where}）")

    # ---------- ③ 清掉「反调试」（Scene_Map 里把 $DEBUG 摁死那一段） ----------
    ad_srcs = find_antidebug_sources(game_dir)
    rep["antidebug"] = {"targets": [], "na": not bool(ad_srcs)}
    if not ad_srcs:
        say("[DEBUG] · 没发现「反调试」代码（Scene_Map 无 `if $DEBUG`，"
            "也没有 `$DEBUG = false`；容器含 Data/PluginScripts.rxdata）")
    else:
        if len(ad_srcs) > 1:
            say(f"[DEBUG] 发现 {len(ad_srcs)} 处「反调试」代码，逐处处理")
        else:
            say("[DEBUG] 发现「反调试」代码 —— 它每帧把 $DEBUG 摁回 false，"
                "还顺手把场景踢掉，正是「开了没效果」的原因")
        for src in ad_srcs:
            where = _where(src)
            dec = (antidebug_plan or {}).get(src_key(src)) or {}
            act = dec.get("action")
            if act == "skip":
                rec = {"mode": src["mode"], "where": str(src["key"]),
                       "added": False, "blocks": 0, "written": False,
                       "skipped": True}
                rep["antidebug"]["targets"].append(rec)
                say(f"[DEBUG] · {where} 按你的选择跳过（已加白名单 / 本次"
                    "不处理）")
                continue
            if act in ("comment", "manual"):
                # 复核窗口的决定：按「那一段原文」定位后再改（行号可能已变）
                new_text = apply_antidebug_decision(
                    src["text"], dec, auto_comment=(act == "comment"))
                info = {"added": bool(new_text),
                        "blocks": len(src["blocks"])}
                if not info["added"]:
                    rec = {"mode": src["mode"], "where": str(src["key"]),
                           "added": False, "blocks": 0, "written": False}
                    rep["antidebug"]["targets"].append(rec)
                    say(f"[DEBUG] · {where} 没有变化，跳过")
                    continue
                rec = {"mode": src["mode"], "where": str(src["key"]),
                       "added": True, "blocks": info["blocks"],
                       "written": False, "manual": (act == "manual")}
                rep["antidebug"]["targets"].append(rec)
                try:
                    bak = _write_text(src["mode"], src["path"], src["key"],
                                      new_text, old_text=src["text"],
                                      emit=emit)
                except (OSError, RuntimeError) as e:
                    rep["reason"] = f"清除反调试失败（{where}）：{e}"
                    say(f"[DEBUG] ✘ {rep['reason']}")
                    return rep
                _note_backup(rep, bak)
                rep["changed"] = True
                rec["written"] = True
                say(f"[DEBUG] ✔ 已改掉 {where} 里的反调试代码"
                    f"（{info['blocks']} 段"
                    + ("，按你手改的版本写入）" if act == "manual"
                       else "，自动注释）"))
                continue
            # 没给决定（脚本调用 / 老流程）→ 自动注释
            new_text, info = patch_antidebug(src["text"], src["blocks"])
            rec = {"mode": src["mode"], "where": str(src["key"]),
                   "added": info["added"], "blocks": info.get("blocks", 0),
                   "written": False}
            rep["antidebug"]["targets"].append(rec)
            if not info["added"]:
                say(f"[DEBUG] · {where} 里的反调试已经处理过了，跳过")
                continue
            try:
                bak = _write_text(src["mode"], src["path"], src["key"],
                                  new_text, old_text=src["text"], emit=emit)
            except (OSError, RuntimeError) as e:
                rep["reason"] = f"清除反调试失败（{where}）：{e}"
                say(f"[DEBUG] ✘ {rep['reason']}")
                return rep
            _note_backup(rep, bak)
            rep["changed"] = True
            rec["written"] = True
            say(f"[DEBUG] ✔ 已注释掉 {where} 里的反调试代码"
                f"（{info['blocks']} 段：`if $DEBUG … end` / `$DEBUG = false`）")

    # ---------- ④ 关掉「删 dat + 全量编译」 ----------
    comps = [] if not guard else find_compiler_sources(game_dir)
    if not guard:
        # ★ 界面上「自动关闭全量编译」没勾：一道闸都不装
        say("[DEBUG] · 按你的选择：**不装**编译闸门（「自动关闭全量编译」"
            "没勾）—— 启动时数据比 PBS 旧的话会全量重编译")
        rep["guard"] = {"added": False, "existed": False, "na": True,
                        "targets": [], "skipped": True}
    elif not comps:
        say("[DEBUG] · 这个版本启动时不会自动删 dat / 全量编译，不用处理")
        rep["guard"] = {"added": False, "existed": False, "na": True,
                        "targets": []}
    else:
        rep["guard"] = {"na": False, "targets": []}
        if len(comps) > 1:
            say(f"[DEBUG] Compiler 有 {len(comps)} 处，两处都装闸门")
        for src in comps:
            ctext, cinfo = patch_compiler_main(src["text"])
            cwhere = _where(src)
            rec = {"mode": src["mode"], "where": str(src["key"]),
                   "added": cinfo["added"], "existed": cinfo["existed"],
                   "written": False}
            rep["guard"]["targets"].append(rec)
            if not cinfo["added"]:
                say(f"[DEBUG] · {cwhere} 的这道闸已经装过了，跳过")
                continue
            try:
                bak = _write_text(src["mode"], src["path"], src["key"], ctext,
                                  old_text=src["text"], emit=emit)
            except (OSError, RuntimeError) as e:
                rep["reason"] = f"写入编译闸门失败（{cwhere}）：{e}"
                say(f"[DEBUG] ✘ {rep['reason']}")
                return rep
            _note_backup(rep, bak)
            rep["changed"] = True
            rec["written"] = True
            say("[DEBUG] ✔ 已关掉 debug 启动时的「删 Data/*.dat + 全量编译」"
                f"（{cwhere}）")
        say("[DEBUG]   按住 Ctrl 启动游戏仍然会真的编译一次")

    rep["ok"] = True
    if rep["changed"]:
        say("[DEBUG] 完成：现在启动游戏就是调试模式（标题界面会变，"
            "按 F9 / Esc 能开调试菜单）")
    else:
        say("[DEBUG] 没有需要改动的地方 —— 这个游戏已经是开启状态")
    log.info("开启 DEBUG：%s（版本 %s，改动 %s）", game_dir, ver,
             rep["changed"])
    return rep
