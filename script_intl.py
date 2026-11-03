# -*- coding: utf-8 -*-
"""
"""
import io
import json
import os
import re
import shutil
import time

import config
import game_scripts as GS
import intl_text as IT
import logger
import rmarshal

log = logger.get_logger(__name__)

SCRIPT_TEXTS_SECTION = 24

# `_INTL("...")` / `_ISPRINTF("...")` —— 前面不能紧跟标识符字符（防 pb_INTL）
_LIT_RE = re.compile(r'(?<![A-Za-z0-9_])(?:_INTL|_ISPRINTF)\s*\(\s*"((?:[^"\\]|\\.)*)"')

# ★ 粗略判断（用户指定）：`_INTL` 所在**行**里出现下面任一记号，整行都不替换。
#   宁可不翻，也不把资源名写坏。例：
#     @sprites["memo"].bitmap =
#         RPG::Cache.load_bitmap(@directory, _INTL("memo"))
#   代价：同一行里的真界面文案也会被跳过（如
#   `pbMessageDisplay(@sprites["msgwindow"], _INTL("What?"))`）。
SKIP_LINE_TOKENS = (
    "@sprites[",
    "RPG::Cache.load_bitmap",
    "AnimatedBitmap.new",
    "pbBitmap",
)


def should_skip_line(line, col=None):
    """
    `_INTL` 所在行出现 SKIP_LINE_TOKENS 里任一记号 → 不替换。

    ★ 只按行判断，不看 `_INTL` 在行内的位置（粗略判断，宁可少翻）。
    col 参数保留给调用方，当前不使用。
    """
    return bool(line) and any(t in line for t in SKIP_LINE_TOKENS)

# ★ 判「是不是中文」要连**全角标点**一起认：`{1}（PP：---）` 整串只有
#   U+FF08 / U+FF1A 这类全角符号，只查 \u4e00-\u9fff 会把它当成没翻。
_CJK_RE = re.compile(u"[\u2e80-\u9fff\uf900-\ufaff\uff01-\uff60]")


def has_cjk(text):
    return bool(text and _CJK_RE.search(text))


def line_of(text, pos):
    """pos 所在的那一整行（不含换行符）。"""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end < 0:
        end = len(text)
    return text[start:end]


# ================================================================
# 与游戏那套一模一样的转义 / 归一化
# ================================================================
def string_to_key(text):
    """同 `Translation.stringToKey`：去首尾空白、连续空白压一个空格。"""
    if not text:
        return text
    if re.search(r"[\r\n\t\1]|^\s+|\s+$|\s{2,}", text):
        key = re.sub(r"^\s+", "", text)
        key = re.sub(r"\s+$", "", key)
        return re.sub(r"\s{2,}", " ", key)
    return text


def unescape(body):
    """
    源码里双引号字符串的**字面内容** → 真实字符串。

    顺序照抄 `Translator.find_translatable_text_from_RGSS_script` 的 5 个 gsub：
    `\\r` `\\n` `\\1` `\\"` 先，`\\\\` 最后。
    """
    s = body.replace("\\r", "\r")
    s = s.replace("\\n", "\n")
    s = s.replace("\\1", "\x01")
    s = s.replace('\\"', '"')
    s = s.replace("\\\\", "\\")
    return s


def escape(value):
    """真实字符串 → 能安全放进双引号字面量的内容（`unescape` 的逆）。"""
    s = str(value).replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\r", "\\r").replace("\n", "\\n")
    s = s.replace("\t", "\\t").replace("\x01", "\\1")
    return s


# ================================================================
# 词表：从编译好的中文语言文件第 24 段取
# ================================================================
def _pairs(section):
    if section is None:
        return []
    if isinstance(section, list):
        return [(None, v) for v in section]
    pr = getattr(section, "pairs", None)      # ★ 是属性不是方法，见 MEMORY
    return list(pr) if isinstance(pr, list) else []


def _collect(path, table, note):
    """
    读一个 .dat 的第 24 段 → 词表，返回**新增**条数。

    ★ 0 条时必须说清原因（用户最容易卡在这）：
        · 文件没有第 24 段 → 「没有第 24 段」；
        · 有第 24 段但一条中文都没有 → 「共 N 条，一条都没翻译」。
      以前两种都只说「0 条」，看不出是「表是空的」还是「压根没翻」。
    """
    name = os.path.basename(path)
    try:
        messages = IT.read_messages(path)
    except Exception as e:                    # noqa: BLE001
        note.append("读不了 %s：%s" % (name, e))
        return 0
    if len(messages) <= SCRIPT_TEXTS_SECTION:
        note.append("%s 没有第 %d 段（脚本内文本）"
                    % (name, SCRIPT_TEXTS_SECTION))
        return 0

    pairs = _pairs(messages[SCRIPT_TEXTS_SECTION])
    n = total = 0
    for key, value in pairs:
        if not key or not isinstance(key, str):
            continue
        total += 1
        if not isinstance(value, str) or value == key or not has_cjk(value):
            continue
        if table.get(key) == value:
            continue
        table[key] = value
        n += 1
    if not n:
        if total and not any(has_cjk(v) for _k, v in pairs
                             if isinstance(v, str)):
            note.append("%s 第 %d 段（脚本内文本）共 %d 条，"
                        "**一条都没翻译**（值全等于原文）"
                        % (name, SCRIPT_TEXTS_SECTION, total))
        else:
            note.append("%s 第 %d 段没有可用的中文译文"
                        % (name, SCRIPT_TEXTS_SECTION))
    return n


def _text_folders(game_dir):
    """游戏目录下所有 Text_* 文本文件夹（提取出来的那些）。"""
    out = []
    try:
        names = sorted(os.listdir(str(game_dir or "")))
    except OSError:
        return out
    for n in names:
        p = os.path.join(str(game_dir), n)
        if os.path.isdir(p) and n.lower().startswith("text_"):
            out.append(p)
    return out


def _collect_folder(folder, table, note, emit=None):
    """
    从提取出来的文本文件夹里读第 24 段译文（不依赖 .dat）。

    来源两个，**译文文件最后读**（同一句在两边不同时以译文文件为准，
    因为「编译文本」吃的就是它）：
      · `SCRIPT_TEXTS_cache.json`（翻译缓存，中间文件夹里那份优先）
      · `SCRIPT_TEXTS_translated.txt`（翻完的译文文件）
    ★ 有了这一层，「翻完但还没编译」也能直接写回脚本 —— 以前必须先
      「编译文本」，而编译还要选对文件、选对输出，绕。
    """
    def _take(key, value):
        if not key or not isinstance(key, str):
            return 0
        if not isinstance(value, str) or value == key or not has_cjk(value):
            return 0
        key = string_to_key(key)
        if table.get(key) == value:
            return 0
        table[key] = value
        return 1

    n = 0
    for cp in (os.path.join(folder, config.WORK_DIR_NAME,
                            "SCRIPT_TEXTS_cache.json"),
               os.path.join(folder, "SCRIPT_TEXTS_cache.json")):
        if not os.path.isfile(cp):
            continue
        try:
            with io.open(cp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:                # noqa: BLE001
            note.append("读不了 %s：%s" % (os.path.basename(cp), e))
            continue
        if not isinstance(data, dict):
            continue
        got = sum(_take(k, v) for k, v in data.items())
        n += got
        if emit:
            emit("  词表 ← %s：%d 条"
                 % (os.path.join(os.path.basename(folder),
                                 os.path.basename(cp)), got))

    p = os.path.join(folder, "SCRIPT_TEXTS_translated.txt")
    if os.path.isfile(p):
        got = sum(_take(k, v) for k, v in _parse_pairs(p))
        n += got
        if emit:
            emit("  词表 ← %s：%d 条"
                 % (os.path.join(os.path.basename(folder),
                                 "SCRIPT_TEXTS_translated.txt"), got))
    return n


def translation_map(game_dir, emit=None, extra_paths=None):
    """
    读「已编译的中文语言文件」第 24 段 → (词表 dict, 说明 list)。

    split 方案：`messages_<片段>_core.dat` + `…_game.dat`（game 覆盖 core，
    跟游戏 `getFromHash` 先查 game 再查 core 的顺序一致）。
    旧方案：`Data/<语言>.dat`，没有就退回 `Data/messages.dat`。
    额外的补译稿（`Script_texts_missing_translated.txt`）最后叠加，优先级最高。
    """
    note = []
    data = GS.data_dir(game_dir)
    table = {}
    total = 0

    frag = None
    try:
        frag = GS.language_fragment(game_dir)
    except Exception:                         # noqa: BLE001
        frag = None

    paths = []
    if frag:
        for part in ("core", "game"):         # core 先读，game 后读覆盖
            p = os.path.join(data, "messages_%s_%s.dat" % (frag, part))
            if os.path.isfile(p):
                paths.append(p)
    if not paths:
        legacy = GS.default_language_file(game_dir)
        if legacy and os.path.isfile(legacy):
            paths.append(legacy)
        elif os.path.isfile(os.path.join(data, "messages.dat")):
            paths.append(os.path.join(data, "messages.dat"))

    for p in paths:
        n = _collect(p, table, note)
        total += n
        if emit:
            emit("  词表 ← %s：%d 条" % (os.path.basename(p), n))

    # ★ 再读提取出来的文本文件夹：翻完没编译也能写回（后读的覆盖先读的）
    for folder in _text_folders(game_dir):
        total += _collect_folder(folder, table, note, emit=emit)

    # 补译稿（导出缺口 → 翻译 → 存成 *_translated.txt）
    extra = list(extra_paths or [])
    extra.append(os.path.join(game_dir,
                              MISSING_TODO_NAME[:-4] + MISSING_DONE_SUFFIX))
    for p in extra:
        got = load_extra(p)
        if got:
            table.update(got)
            if emit:
                emit("  补译稿 ← %s：%d 条" % (os.path.basename(p), len(got)))

    if not table:
        scheme = {}
        try:
            scheme = IT.detect_scheme(game_dir)
        except Exception:                     # noqa: BLE001
            scheme = {}
        if scheme.get("scheme") == IT.SCHEME_SPLIT:
            target = "messages_%s_core.dat / _game.dat" % (frag or "chinese")
        else:
            target = os.path.basename(
                GS.default_language_file(game_dir) or "Chinese.dat")
        note.append(
            "没读到中文词表：%s 里没有「脚本内文本」（第 %d 段）的译文。"
            % (target, SCRIPT_TEXTS_SECTION))
        note.append(
            "办法二选一：① 去「文本提取与编译」先提取文本，把 Text_<语言>/"
            "SCRIPT_TEXTS.txt 翻完（或整份跑一遍翻译），再回来写回脚本"
            "（不用先编译）；② 「导出待补文案」→ 翻完存成 "
            "%s，再回来写回脚本。" % (MISSING_TODO_NAME[:-4]
                                      + MISSING_DONE_SUFFIX))
    return table, note


MISSING_TODO_NAME = "Script_texts_missing.txt"
MISSING_DONE_SUFFIX = "_translated.txt"


def _parse_pairs(path):
    """读一份 intl 格式 txt 的第 24 段 → [(原文, 译文), ...]。"""
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace",
                     newline="") as f:
            text = f.read()
    except OSError:
        return []
    try:
        secs = IT.parse_intl_text(text, os.path.basename(path),
                                  allow_constants=True,
                                  normalize_keys=True, trim="strip")
    except Exception as e:                    # noqa: BLE001
        log.warning("解析 %s 失败：%s", path, e)
        return []
    sec = secs.get((None, SCRIPT_TEXTS_SECTION)) or \
        secs.get(("map", SCRIPT_TEXTS_SECTION))
    if sec is None:
        return []
    return _pairs(sec)


def load_extra(*paths):
    """
    额外词表：用户翻好的 `Script_texts_missing_translated.txt`。

    格式与游戏导出文本一致（`[24]` + 每段两行），只收「译文含中文且不等于原文」。
    """
    table = {}
    for p in paths:
        if not p or not os.path.isfile(p):
            continue
        for key, value in _parse_pairs(p):
            if not key or not isinstance(key, str):
                continue
            if not isinstance(value, str) or value == key or not has_cjk(value):
                continue
            table[string_to_key(key)] = value
    return table


def is_translatable(key):
    """
    待补清单里只留「真的需要翻」的：图片路径、单个字母、纯格式串一律剔掉。

    （实测登神 v0.1.1.3 的 165 条缺口里，140 多条是 `Graphics/UI/...`、
     图鉴字母索引 `A`~`Z`、`{1}/{2}` 这种，喂给翻译只会浪费钱。）
    """
    if not key or len(key.strip()) < 2:
        return False
    if re.match(r"^\s*(?:Graphics|Audio|Data|Fonts|PBS)/", key):
        return False
    if not re.search(r"[A-Za-z]{2,}", key):        # 至少两个连续字母
        return False
    stripped = re.sub(r"\{[^}]*\}|<[^>]*>|\\\\[A-Za-z]+(?:\[[^\]]*\])?|\s", "",
                      key)
    return bool(stripped)


def export_missing(game_dir, out_path=None, include_main=True,
                   include_plugins=True, include_maps=True, emit=None):
    """
    把「脚本里有、词表里没有」的 `_INTL` 文案导出成 intl 格式 txt（每行两遍），
    拿去「翻译」翻完（生成 `Script_texts_missing_translated.txt`），
    再回来点「写回脚本」就会用上。

    返回 {"ok", "out", "count", "skipped"}。
    """
    def say(msg):
        if emit:
            emit(msg)

    table, notes = translation_map(game_dir)
    if not table:
        # ★ 词表为空也能导出：这正是「一条都没翻」时要走的路
        #   （列出来的就是全部待翻文案），以前这里直接 return，等于把唯一
        #   可行的补救路径也堵死了。
        for n in notes:
            say("  ⚠ %s" % n)
        say("  ⚠ 词表是空的，这次会把所有能翻的 _INTL 文案都列出来")

    seen = {}
    skipped = 0
    for target in ([] if not table else
                   iter_targets(game_dir, include_main, include_plugins,
                                emit=say)):
        stats = {}
        rewrite_text(target["text"], table, stats)
        for s in stats.get("miss_samples", []):
            if not s or s in seen:
                continue
            if not is_translatable(s):
                skipped += 1
                continue
            seen[s] = 1

    # 地图事件（Data/Map*.rxdata）里的缺口一视同仁
    if include_maps:
        _samples, mrep = map_miss_samples(game_dir, table)
        for s in _samples:
            if not s or s in seen:
                continue
            if not is_translatable(s):
                skipped += 1
                continue
            seen[s] = 1
        if mrep.get("files"):
            say("  地图事件：%d 个文件有可写回文案"
                % len(mrep["files"]))

    out = out_path or os.path.join(game_dir, MISSING_TODO_NAME)
    lines = ["# 脚本里有、词表里没有的 _INTL 文案（%d 条）。" % len(seen),
             "# 每段两行：第一行原文，把第二行改成译文即可（别改第一行）。",
             "# 翻完存成同名 + _translated.txt，再回「文本提取与编译」点「写回脚本」。",
             "[%d]" % SCRIPT_TEXTS_SECTION]
    for key in sorted(seen):
        lines.append(key)
        lines.append(key)
    try:
        with io.open(out, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as e:
        say("  ✘ 写不了 %s：%s" % (out, e))
        return {"ok": False, "error": str(e), "count": len(seen)}
    say("  已导出 %d 条待补文案 → %s" % (len(seen), out))
    if skipped:
        say("  （另有 %d 条非文本项已跳过：图片路径 / 单个字母 / 纯格式串）"
            % skipped)
    return {"ok": True, "out": out, "count": len(seen), "skipped": skipped}


# ================================================================
# 改写
# ================================================================
def rewrite_text(text, table, stats=None):
    """
    把一个脚本的源码里所有 `_INTL("英文")` 换成中文 → (新源码, 命中数)。

    stats（可选 dict）会被累加：hit / already / dynamic / miss / skip_line，
    并收集 miss 样例。

    ★ 所在行出现 SKIP_LINE_TOKENS 里任一记号（`@sprites[` / `RPG::Cache.load_bitmap`
      / `AnimatedBitmap.new` / `pbBitmap`）→ 整行不动，例如：
        @sprites["memo"].bitmap =
            RPG::Cache.load_bitmap(@directory, _INTL("memo"))
      这类文本是**资源名 / 索引键**，不是给人看的界面文案。
    """
    if stats is None:
        stats = {}
    for k in ("hit", "already", "dynamic", "miss", "skip_line"):
        stats.setdefault(k, 0)
    stats.setdefault("miss_samples", [])
    stats.setdefault("miss_set", set())

    def rep(m):
        body = m.group(1)
        if should_skip_line(line_of(text, m.start())):
            stats["skip_line"] += 1
            return m.group(0)
        if "#{" in body:                      # 动态串，换掉会丢插值
            stats["dynamic"] += 1
            return m.group(0)
        if has_cjk(body):                     # 已经是中文
            stats["already"] += 1
            return m.group(0)
        key = string_to_key(unescape(body))
        value = table.get(key)
        if not value:
            stats["miss"] += 1
            if key not in stats["miss_set"] and len(stats["miss_samples"]) < 400:
                stats["miss_set"].add(key)
                stats["miss_samples"].append(key)
            return m.group(0)
        stats["hit"] += 1
        prefix = m.group(0)[:m.start(1) - m.start(0)]     # 到开引号为止
        return prefix + escape(value) + '"'

    return _LIT_RE.sub(rep, text), stats["hit"]


def count_text(text, table):
    """只数不改（预览用）。"""
    stats = {}
    rewrite_text(text, table, stats)
    return stats


# ================================================================
# 地图事件（Data/Map*.rxdata）
#   事件指令里的 `_INTL("…")`（脚本行 code 355/655 的 @parameters[0]）
#   同样写回中文：整份 MapXXX.rxdata 读 → 改字符串 → 原样 dump 回去。
#   ★ rmarshal 对地图文件的「读 → 写」是逐字节一致的，所以没改到的地方
#     一个字节都不会动。
# ================================================================
_MAP_FILE_RE = re.compile(r'^Map\d{3,4}\.rxdata$', re.I)
# 只对「看起来真的含 _INTL 调用」的字符串走正则（省时间也少误伤）
_INTL_HINT_RE = re.compile(r'(?<![A-Za-z0-9_])(?:_INTL|_ISPRINTF)\s*\(')


def map_files(game_dir):
    """Data 下所有 MapXXX.rxdata（不含 MapInfos.rxdata）。"""
    d = GS.data_dir(str(game_dir or ""))
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if not _MAP_FILE_RE.match(name):
            continue
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            out.append(p)
    return out


def _rewrite_tree(obj, fn, seen=None):
    """
    递归把容器里的字符串过一遍 fn（返回新串时替换）。

    ★ 只动**普通字符串**；符号（RSymbol）/ 二进制负载（u / U 类型）一律不碰。
    ★ RObject / RHash / RStruct / RIVar / list 都是原地改，返回同一个对象。
    """
    if isinstance(obj, rmarshal.RStr):
        new = fn(str(obj))
        return obj if new == str(obj) else rmarshal.RStr.smart(new, obj)
    if isinstance(obj, str):
        new = fn(obj)
        return obj if new == obj else new
    if not isinstance(obj, (list, dict, rmarshal.RHash, rmarshal.RObject,
                            rmarshal.RStruct, rmarshal.RIVar)):
        return obj

    if seen is None:
        seen = set()
    key = id(obj)
    if key in seen:
        return obj
    seen.add(key)

    if isinstance(obj, list):
        for i, v in enumerate(obj):
            obj[i] = _rewrite_tree(v, fn, seen)
        return obj
    if isinstance(obj, rmarshal.RHash):
        for i, (k, v) in enumerate(list(obj.pairs)):
            obj.pairs[i] = (_rewrite_tree(k, fn, seen),
                            _rewrite_tree(v, fn, seen))
        return obj
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            obj[k] = _rewrite_tree(obj[k], fn, seen)
        return obj
    if isinstance(obj, rmarshal.RObject):
        for k in list(obj.ivars.keys()):
            obj.ivars[k] = _rewrite_tree(obj.ivars[k], fn, seen)
        return obj
    if isinstance(obj, rmarshal.RStruct):
        obj.members = [(k, _rewrite_tree(v, fn, seen)) for k, v in obj.members]
        return obj
    if isinstance(obj, rmarshal.RIVar):
        obj.base = _rewrite_tree(obj.base, fn, seen)
        if isinstance(obj.ivars, dict):
            for k in list(obj.ivars.keys()):
                obj.ivars[k] = _rewrite_tree(obj.ivars[k], fn, seen)
        return obj
    return obj


def _load_rxdata(path):
    with open(path, "rb") as f:
        return rmarshal.loads_all(f.read())


def process_maps(game_dir, table, write=False, emit=None):
    """
    地图事件里的 `_INTL` 文案写回（write=False 只统计）。

    返回 {"files": [{label,changed,bytes}], "changed", "miss", "already",
          "dynamic", "skip_line", "miss_samples", "backups", "errors"}
    """
    def say(msg):
        if emit:
            emit(msg)

    rep = {"files": [], "changed": 0, "miss": 0, "already": 0,
           "dynamic": 0, "skip_line": 0, "miss_samples": [],
           "backups": [], "errors": []}

    for path in map_files(game_dir):
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            rep["errors"].append("%s：%s" % (os.path.basename(path), e))
            continue
        if not _INTL_HINT_RE.search(raw.decode("latin1")):
            continue                      # 整份文件里没有 _INTL，跳过

        try:
            objs = _load_rxdata(path)
        except Exception as e:            # noqa: BLE001
            rep["errors"].append("%s：读不出来（%s）"
                                 % (os.path.basename(path), e))
            say("  ⚠ 读不了 %s：%s" % (os.path.basename(path), e))
            continue

        stats = {}

        def fn(text):
            if not _INTL_HINT_RE.search(text):
                return text
            return rewrite_text(text, table, stats)[0]

        for o in objs:
            _rewrite_tree(o, fn)

        rep["miss"] += stats.get("miss", 0)
        rep["dynamic"] += stats.get("dynamic", 0)
        rep["already"] += stats.get("already", 0)
        rep["skip_line"] += stats.get("skip_line", 0)
        for s in stats.get("miss_samples", []):
            if s and s not in rep["miss_samples"]:
                rep["miss_samples"].append(s)

        hits = stats.get("hit", 0)
        if not hits:
            continue

        label = "地图事件 %s" % os.path.basename(path)
        row = {"label": label, "changed": hits,
               "kind": "map", "bytes": (len(raw), 0)}
        if write:
            try:
                data = rmarshal.dumps_all(objs)
                # ★ 复查：dump 出来的东西必须还能读回来（读得回 = 结构没坏）
                rmarshal.loads_all(data)
            except Exception as e:        # noqa: BLE001
                rep["errors"].append("%s：写回失败（%s）" % (label, e))
                say("  ✘ %s：%s" % (label, e))
                continue
            try:
                made = []
                _backup(path, made, stamp=True)
                for b in made:
                    rep["backups"].append(b)
                tmp = path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
            except Exception as e:        # noqa: BLE001
                rep["errors"].append("%s：写文件失败（%s）" % (label, e))
                say("  ✘ %s：%s" % (label, e))
                continue
            row["bytes"] = (len(raw), len(data))

        rep["files"].append(row)
        rep["changed"] += hits
        say("  %s %-46s %d 处" % ("✔" if write else "·", label[:46], hits))

    return rep


def map_miss_samples(game_dir, table):
    """地图事件里「有 _INTL 但词表里没有」的原文（导出待补清单用）。"""
    seen = []
    rep = process_maps(game_dir, table, write=False)
    for s in rep.get("miss_samples", []):
        if s and s not in seen:
            seen.append(s)
    return seen, rep


# ================================================================
# 地图对话（101 / 401 / 102）→ 直接写回 Map*.rxdata / CommonEvents.rxdata
#
#   和上面的 process_maps 是两件事：
#     · process_maps      改 355/655 脚本行里的 `_INTL("…")`（引擎抽不到的死文本）
#     · process_event_texts 改 101/401/102 的对话文本（引擎把它们抽进 .dat 第 0 段）
#   本函数把语言文件第 0 段的译文**按原文文本**钉回地图文件，不看地图编号：
#   `[map1]` 里的某句只要在 Map012.rxdata 里出现，也一起替换。
# ================================================================
_COMMON_EVENTS_NAME = "CommonEvents.rxdata"

# 折行时的「安全切点」：优先在这些字符之后断行
_SPLIT_PUNCT = set("，。！？、；：,.!?;:…")

# 对话类事件指令
_CODE_TEXT = 101        # 显示文字（params[0] 第一行）
_CODE_TEXT_CONT = 401   # 续行（params[0] 是下一行）
_CODE_CHOICES = 102     # 显示选项（params[1] 是选项文本数组）


def event_files(game_dir):
    """地图对话要改的文件：Data/Map*.rxdata + Data/CommonEvents.rxdata。"""
    out = list(map_files(game_dir))
    p = os.path.join(GS.data_dir(str(game_dir or "")), _COMMON_EVENTS_NAME)
    if os.path.isfile(p) and os.path.getsize(p) > 0:
        out.append(p)
    return out


def _cmd_of(obj, attr, default=None):
    try:
        v = obj.get(attr) if hasattr(obj, "get") else None
    except Exception:                          # noqa: BLE001
        return default
    return default if v is None else v


def _event_pair(key, value):
    """(原文, 译文) → (归一化原文, 译文)；不合格返回 ("", "")。"""
    if not isinstance(key, str) or not isinstance(value, str):
        return "", ""
    k = string_to_key(key)
    v = value
    if not k or not v.strip() or v == k or not has_cjk(v):
        return "", ""
    return k, v


def event_text_table(game_dir, emit=None):
    """
    读语言文件第 0 段（地图/公共事件文本）→ {归一化原文: 译文}。

    ★ **忽略地图编号**：第 0 段是「下标=地图号」的一堆哈希，这里全部拍平成一个
      原文→译文的大表。同一句在不同地图里出现、或出现在别的地图里，都能命中。
    ★ 来源按「后读覆盖先读」：
        ① 语言 .dat 第 0 段（split: messages_<片段>_core/_game；旧版: Chinese.dat）
        ② Text_*/EVENT_TEXTS_cache.json（翻译缓存）
        ③ Text_*/EVENT_TEXTS_translated.txt（译文文件，最接近最终产物）
      文本文件夹那两样能让「翻完还没编译」也直接写回。
    返回 (table, notes)
    """
    def say(msg):
        if emit:
            emit(msg)

    note = []
    table = {}
    data = GS.data_dir(str(game_dir or ""))

    frag = None
    try:
        frag = GS.language_fragment(game_dir)
    except Exception:                          # noqa: BLE001
        frag = None

    paths = []
    if frag:
        for part in ("core", "game"):
            p = os.path.join(data, "messages_%s_%s.dat" % (frag, part))
            if os.path.isfile(p):
                paths.append(p)
    if not paths:
        legacy = GS.default_language_file(game_dir)
        if legacy and os.path.isfile(legacy):
            paths.append(legacy)
        elif os.path.isfile(os.path.join(data, "messages.dat")):
            paths.append(os.path.join(data, "messages.dat"))

    for p in paths:
        try:
            messages = IT.read_messages(p)
        except Exception as e:                 # noqa: BLE001
            note.append("读不了 %s：%s" % (os.path.basename(p), e))
            continue
        n = _collect_map_texts(messages, table)
        if emit:
            say("  对话词表 ← %s：%d 条" % (os.path.basename(p), n))

    for folder in _text_folders(game_dir):
        n = _collect_folder_events(folder, table, note, emit=emit)
        if emit:
            say("  对话词表 ← %s\\EVENT_TEXTS*：%d 条"
                % (os.path.basename(folder), n))

    if not table:
        note.append("没读到地图对话译文：语言文件第 0 段（EVENT_TEXTS）是空的。"
                    "先「提取文本 → 翻译 → 编译文本」，或用已有的 "
                    "EVENT_TEXTS_translated.txt。")
    say_count = len(table)
    log.info("地图对话词表：%d 条（%s）", say_count, game_dir)
    return table, note


def _collect_map_texts(messages, table):
    """第 0 段（list，下标=地图号）→ 拍平进 table，返回新增条数。"""
    if not messages:
        return 0
    sec = messages[0] if len(messages) > 0 else None
    if sec is None:
        return 0
    subs = sec if isinstance(sec, list) else [sec]
    n = 0
    for sub in subs:
        if sub is None:
            continue
        for key, value in _pairs(sub):
            k, v = _event_pair(key, value)
            if not k:
                continue
            if table.get(k) == v:
                continue
            table[k] = v
            n += 1
    return n


def _collect_folder_events(folder, table, note, emit=None):
    """Text_* 文件夹里的 EVENT_TEXTS 缓存 / 译文 → table，返回新增条数。"""
    n = 0

    def _take(k, v):
        nonlocal n
        kk, vv = _event_pair(k, v)
        if not kk or table.get(kk) == vv:
            return
        table[kk] = vv
        n += 1

    for cp in (os.path.join(folder, config.WORK_DIR_NAME,
                            "EVENT_TEXTS_cache.json"),
               os.path.join(folder, "EVENT_TEXTS_cache.json")):
        if not os.path.isfile(cp):
            continue
        try:
            with io.open(cp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:                 # noqa: BLE001
            note.append("读不了 %s：%s" % (os.path.basename(cp), e))
            continue
        if isinstance(data, dict):
            for k, v in data.items():
                _take(k, v)

    p = os.path.join(folder, "EVENT_TEXTS_translated.txt")
    if os.path.isfile(p):
        try:
            with io.open(p, "r", encoding="utf-8", errors="replace",
                         newline="") as f:
                text = f.read()
            secs = IT.parse_intl_text(text, os.path.basename(p),
                                      allow_constants=True,
                                      normalize_keys=True, trim="strip")
        except Exception as e:                 # noqa: BLE001
            note.append("解析 %s 失败：%s" % (os.path.basename(p), e))
            secs = {}
        for _key, sec in (secs or {}).items():
            for k, v in _pairs(sec):
                if isinstance(k, str):
                    k = IT.denormalize_value(k)
                _take(k, v)
    return n


def split_width(text, n):
    """
    把一段文本按「可见字数」均匀切成 n 段，尽量在标点 / 空格后断开。

    ★ 控制码（`\\PN` / `\\c[8]` / `<<n>>` …）整段跳过：既不计字宽，也绝不切断。
    ★ 切点取「第 round(total*i/n) 个可见字符」附近最近的标点/空格；
      找不到就硬切。纯本地规则，断得不满意还可以再用「换行重排」修。
    """
    text = str(text or "")
    n = int(n or 1)
    if n <= 1:
        return [text]
    if not text:
        return [""] * n

    try:
        import processor as _PR
        ctrl = _PR.ALL_CTRL_RE
    except Exception:                          # noqa: BLE001
        ctrl = None

    units = []                                 # [(片段, 可见宽度 0/1)]
    i = 0
    while i < len(text):
        m = ctrl.match(text, i) if ctrl is not None else None
        if m:
            units.append((m.group(0), 0))
            i = m.end()
            continue
        ch = text[i]
        units.append((ch, 0 if ch in "\n\r" else 1))
        i += 1

    vis_idx = [k for k, (_p, w) in enumerate(units) if w]
    total = len(vis_idx)
    if total <= 1:
        return ["".join(p for p, _w in units)] + [""] * (n - 1)

    def _is_break(k):
        piece = units[k][0]
        return piece in _SPLIT_PUNCT or piece.isspace()

    cuts = []
    prev = 0
    for i in range(1, n):
        k = int(round(total * i / n))
        k = min(max(k, 1), total - 1)
        limit = len(units) - (n - i)           # 后面每段至少还要留 1 个单元
        base = min(max(vis_idx[k], prev + 1), limit)
        best = base
        for off in range(0, 3):                # 附近 ±2 个单元找标点
            hit = None
            for cand in (base + off, base - off):
                if prev < cand <= limit and _is_break(cand):
                    hit = cand
                    break
            if hit is not None:
                best = hit
                break
        if best <= prev:
            best = min(prev + 1, limit)
        prev = best
        cuts.append(best)

    bounds = [0]
    for c in cuts:
        cut = c + 1
        if bounds[-1] < cut < len(units):      # 切在末尾等于没切，直接跳过
            bounds.append(cut)
    bounds.append(len(units))

    parts = ["".join(p for p, _w in units[a:b])
             for a, b in zip(bounds, bounds[1:])]
    while len(parts) < n:
        parts.append("")
    return parts[:n]


# 有「实际内容」的字符：字母 / 数字 / 汉字（只有标点或空白的段算孤儿段）
_CONTENT_RE = re.compile(r"[\w\u3400-\u9fff\uf900-\ufaff]")


def _join_soft(a, b):
    """把两段译文接起来：中文之间不加空格，西文之间补一个空格。"""
    if not a:
        return b
    if not b:
        return a
    if has_cjk(a[-1:]) or has_cjk(b[:1]):
        return a + b
    return a + " " + b


def _join_soft_all(segs):
    """把多段软接回一段（中文之间不加空格）。"""
    out = ""
    for seg in segs:
        out = _join_soft(out, seg)
    return out


def _tidy_segs(segs):
    """把空段和「只有标点」的孤儿段并到相邻段上（避免出现单一个句号的行）。"""
    out = []
    for seg in segs:
        if not seg or not seg.strip():
            continue
        if out and not _CONTENT_RE.search(seg):
            out[-1] = _join_soft(out[-1], seg)
            continue
        out.append(seg)
    return out or [""]


def fit_lines(text, slots):
    """
    把一条译文摆到 `slots` 个行槽里（101 + 各 401），返回恰好 slots 段。

    ★ 译文里的换行是**真实换行符**（`0x0A`，不是字面 `\\n`）—— 第 0 段里的
      译文就是这样存换行的，它正好对应原文的换行位置，直接拿来做分段边界。
    · 段数与槽位相等 → 一一对应（最理想，尊重译者的断行）；
    · 段数多于槽位 → 前 n-1 段照填，剩下的软接到最后一槽（不留空行）；
    · 段数少于槽位 → 去掉换行后按可见字数折行填满。
    """
    slots = max(1, int(slots or 1))
    text = str(text or "")
    if slots == 1:
        # 只有一行时把断行留成字面 `\n`（游戏的消息窗口认它）：既保住译者要的
        # 断行，又不会在 rxdata 的字符串里塞真实换行。
        return [text.replace("\r\n", "\n").replace("\r", "\n")
                .replace("\n", "\\n")]

    # 两种换行都当分段边界：真实换行（0x0A，来自原文的多行结构）
    # 与字面 `\n`（译者/流水线写进同一行的断行控制码）
    norm = text.replace("\r\n", "\n").replace("\r", "\n").replace("\\n", "\n")
    norm = re.sub(r"[ \t]*\n[ \t]*", "\n", norm)       # 行尾空白去掉
    segs = _tidy_segs(norm.split("\n"))
    if len(segs) == slots:
        return segs
    if len(segs) > slots:
        # 段数比槽位多：按比例并成 slots 组，别把余下的全塞进最后一行
        per = len(segs) / float(slots)
        groups, start = [], 0
        for i in range(slots):
            end = int(round((i + 1) * per))
            end = max(end, start + 1) if i < slots - 1 else len(segs)
            groups.append(_join_soft_all(segs[start:end]))
            start = end
        while len(groups) < slots:
            groups.append("")
        return groups[:slots]
    return split_width(_join_soft_all(segs), slots)


def _walk_lists(obj, fn, seen=None):
    """递归找出所有 `@list`（事件指令数组），交给 fn 原地处理。"""
    if seen is None:
        seen = set()
    if isinstance(obj, (list, dict, rmarshal.RHash, rmarshal.RObject,
                        rmarshal.RStruct, rmarshal.RIVar)):
        key = id(obj)
        if key in seen:
            return
        seen.add(key)

    if isinstance(obj, rmarshal.RObject):
        for k, v in obj.ivars.items():
            if k == "@list" and isinstance(v, list):
                fn(v)
            else:
                _walk_lists(v, fn, seen)
    elif isinstance(obj, list):
        for v in obj:
            _walk_lists(v, fn, seen)
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_lists(v, fn, seen)
    elif isinstance(obj, rmarshal.RHash):
        for k, v in obj.pairs:
            _walk_lists(k, fn, seen)
            _walk_lists(v, fn, seen)
    elif isinstance(obj, rmarshal.RStruct):
        for _k, v in obj.members:
            _walk_lists(v, fn, seen)
    elif isinstance(obj, rmarshal.RIVar):
        _walk_lists(obj.base, fn, seen)
        for v in (obj.ivars or {}).values():
            _walk_lists(v, fn, seen)


def _translate_single(text, table, stats):
    """单句查表（选项文本用）；命中返回译文，否则 None。"""
    if not isinstance(text, str) or not text.strip():
        return None
    if has_cjk(text):
        stats["already"] += 1
        return None
    key = string_to_key(text)
    val = table.get(key)
    if not val or val == key:
        stats["miss"] += 1
        return None
    return val


def _rewrite_dialog_list(lst, table, stats):
    """在一个事件指令数组里就地改写 101/401/102 的文本。"""
    n = len(lst)
    i = 0
    while i < n:
        cmd = lst[i]
        code = _cmd_of(cmd, "@code")
        if code == _CODE_TEXT:
            params = _cmd_of(cmd, "@parameters") or []
            idxs = [i]
            lines = [params[0] if params and isinstance(params[0], str) else ""]
            j = i + 1
            while j < n and _cmd_of(lst[j], "@code") == _CODE_TEXT_CONT:
                p2 = _cmd_of(lst[j], "@parameters") or []
                lines.append(p2[0] if p2 and isinstance(p2[0], str) else "")
                idxs.append(j)
                j += 1
            _rewrite_message(lst, idxs, lines, table, stats)
            i = j
            continue
        if code == _CODE_CHOICES:
            params = _cmd_of(cmd, "@parameters") or []
            if len(params) > 1 and isinstance(params[1], list):
                for k, ch in enumerate(params[1]):
                    new = _translate_single(ch, table, stats)
                    if new is not None:
                        params[1][k] = new
                        stats["choices"] += 1
            i += 1
            continue
        i += 1


def _rewrite_message(lst, idxs, lines, table, stats):
    """把一整条对话（101 + 各 401）按原文查表后写回。"""
    if not any((ln or "").strip() for ln in lines):
        return
    if any(has_cjk(ln) for ln in lines):
        stats["already"] += 1
        return
    key = string_to_key(" ".join(lines))
    val = table.get(key)
    if not val or val == key:
        stats["miss"] += 1
        return
    segs = fit_lines(val, len(lines))
    for pos, text in zip(idxs, segs):
        params = _cmd_of(lst[pos], "@parameters") or []
        if params:
            params[0] = text
    stats["changed"] += 1


def process_event_texts(game_dir, table, write=False, emit=None):
    """
    把地图对话的译文写回 Data/Map*.rxdata 与 Data/CommonEvents.rxdata。

    · 只动 101（首行）/ 401（续行）/ 102（选项文本），**不增删指令**，
      所以 119 跳转的下标不会错位；
    · 按原文匹配，忽略地图编号（`[map1]` 的句子出现在 Map012 里也照写）；
    · 已经含中文的整条跳过（幂等）；没译文的计 miss，不动原文；
    · 写盘前做字节级预检（未改动时 dump 必须与原文件逐字节一致），
      不等价就记 errors 并跳过该文件；每个文件双备份。

    write=False 只统计、不落盘。
    """
    def say(msg):
        if emit:
            emit(msg)

    rep = {"files": [], "changed": 0, "miss": 0, "already": 0, "choices": 0,
           "errors": [], "backups": [], "scanned": 0, "cancelled": False}

    files = event_files(game_dir)
    rep["scanned"] = len(files)
    if not files:
        return rep
    if not table:
        say("  ⚠ 没有地图对话译文（第 0 段 EVENT_TEXTS 是空的），跳过")
        return rep

    import bridge

    for i, path in enumerate(files, 1):
        if i % 20 == 0 and bridge.cancelled():
            rep["cancelled"] = True
            say("  ⚠ 已取消（处理到 %d/%d 个文件）" % (i - 1, len(files)))
            break
        if write and i % 50 == 0:
            say("    … %d/%d" % (i, len(files)))
        try:
            with open(path, "rb") as f:
                raw = f.read()
            objs = rmarshal.loads_all(raw)
        except Exception as e:                 # noqa: BLE001
            rep["errors"].append("%s：读不出来（%s）"
                                 % (os.path.basename(path), e))
            continue

        # ★ 预检：没有改动时必须逐字节还原，否则这份文件不碰
        try:
            if rmarshal.dumps_all(objs) != raw:
                rep["errors"].append("%s：读→写不是逐字节一致，已跳过"
                                     % os.path.basename(path))
                continue
        except Exception as e:                 # noqa: BLE001
            rep["errors"].append("%s：预检失败（%s）"
                                 % (os.path.basename(path), e))
            continue

        stats = {"changed": 0, "miss": 0, "already": 0, "choices": 0}
        try:
            for o in objs:
                _walk_lists(o, lambda lst: _rewrite_dialog_list(lst, table, stats))
        except Exception as e:                 # noqa: BLE001
            rep["errors"].append("%s：改写失败（%s）"
                                 % (os.path.basename(path), e))
            continue

        rep["miss"] += stats["miss"]
        rep["already"] += stats["already"]
        rep["choices"] += stats["choices"]
        if not stats["changed"]:
            continue

        label = ("公共事件 %s" % os.path.basename(path)
                 if os.path.basename(path).lower() == _COMMON_EVENTS_NAME.lower()
                 else "地图 %s" % os.path.basename(path))
        row = {"label": label, "changed": stats["changed"],
               "kind": "dialog", "bytes": (len(raw), 0),
               "choices": stats["choices"]}
        if write:
            try:
                data = rmarshal.dumps_all(objs)
                rmarshal.loads_all(data)       # 能读回才算数
            except Exception as e:             # noqa: BLE001
                rep["errors"].append("%s：写回失败（%s）" % (label, e))
                say("  ✘ %s：%s" % (label, e))
                continue
            try:
                made = []
                _backup(path, made, stamp=True)
                rep["backups"].extend(made)
                tmp = path + ".tmp"
                try:
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, path)
                finally:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
            except Exception as e:             # noqa: BLE001
                rep["errors"].append("%s：写文件失败（%s）" % (label, e))
                say("  ✘ %s：%s" % (label, e))
                continue
            row["bytes"] = (len(raw), len(data))

        rep["files"].append(row)
        rep["changed"] += stats["changed"]
        say("  %s %-46s %d 条对话"
            % ("✔" if write else "·", label[:46], stats["changed"]))

    return rep


# ================================================================
# 目标遍历（主脚本 + 插件）
# ================================================================
def _read_raw(path):
    with io.open(path, "r", encoding="utf-8", errors="replace",
                 newline="") as f:            # newline="" 保住原来的 CRLF
        return f.read()


def _write_raw(path, text):
    with io.open(path, "w", encoding="utf-8", errors="replace",
                 newline="") as f:
        f.write(text)


def _backup(path, made, stamp=False):
    """
    备份一次。

    stamp=False → 固定名 `<文件>.bak`，已存在就不覆盖（留住最初那份原版）；
    stamp=True  → 再加一份带时间戳的 `<文件>.YYYYmmdd-HHMMSS.bak`，
                  容器这种「一改全改」的文件必须能退回改动前那一刻。
    """
    out = []
    dst = path + ".bak"
    if not os.path.exists(dst):
        try:
            shutil.copyfile(path, dst)
            out.append(dst)
        except OSError as e:
            raise RuntimeError("备份 %s 失败：%s" % (os.path.basename(path), e))
    if stamp:
        ts = path + "." + time.strftime("%Y%m%d-%H%M%S") + ".bak"
        try:
            if not os.path.exists(ts):
                shutil.copyfile(path, ts)
                out.append(ts)
        except OSError as e:
            raise RuntimeError("备份 %s 失败：%s" % (os.path.basename(path), e))
    made.extend(out)
    return out[0] if out else None


def _unpack_siblings(game_dir):
    """
    Plugins-p 里「文件名 → 路径」的索引（插件容器改完后顺手同步松散副本用）。
    """
    idx = {}
    root = os.path.join(game_dir, "Plugins-p")
    if not os.path.isdir(root):
        return idx
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".rb"):
                idx.setdefault(f, []).append(os.path.join(dirpath, f))
    return idx


def iter_targets(game_dir, include_main=True, include_plugins=True, emit=None):
    """
    逐个给出可改写的脚本 → dict(kind/label/text/write)。

    write(new_text) 真正落盘；dry_run 时不会被调用。
    """
    if include_main:
        try:
            sources = GS.collect_scripts(game_dir, both=True)
        except Exception as e:                # noqa: BLE001
            sources = []
            if emit:
                emit("  ⚠ 读主脚本失败：%s" % e)
        for mode, key, path, title, text in sources:
            name = GS.script_name(key, title) or str(key)
            if mode == "file":
                label = "主脚本 %s" % name
                try:
                    text = _read_raw(path)
                except OSError as e:
                    if emit:
                        emit("  ⚠ 读不了 %s：%s" % (label, e))
                    continue

                def make(path=path, text=text):
                    def write(new, _old=text):
                        if _read_raw(path) != _old:
                            raise RuntimeError("文件内容变了，拒绝写入")
                        _backup(path, [])
                        _write_raw(path, new)
                    return write
                yield {"kind": "main", "label": label, "text": text,
                       "write": make()}
            else:
                label = "主脚本 #%s %s" % (key, name)

                def make(rx=path, key=key, text=text):
                    def write(new, _old=text):
                        GS.write_rxdata_entry(rx, key, new, expect=_old)
                    return write
                yield {"kind": "main", "label": label, "text": text,
                       "write": make()}

    if include_plugins:
        siblings = _unpack_siblings(game_dir)
        try:
            entries = GS.iter_plugin_scripts(game_dir)
        except Exception as e:                # noqa: BLE001
            entries = []
            if emit:
                emit("  ⚠ 读插件脚本失败：%s" % e)
        for _mode, key, path, name, text in entries:
            base = re.sub(r"^\[[^\]]*\]\s*", "", name or "")

            def make(path=path, key=key, text=text, name=name, base=base):
                def write(new, _old=text):
                    GS.write_plugin_entry(path, key, new, expect=_old)
                    # 松散副本内容一致才跟着改（不一致说明它本来就是旧的，
                    # 硬写会把它当权威版本反打回容器）
                    for p in siblings.get(base, []):
                        try:
                            if _read_raw(p) == _old:
                                _backup(p, [])
                                _write_raw(p, new)
                        except OSError:
                            pass
                return write
            yield {"kind": "plugin", "label": "插件 %s" % name,
                   "text": text, "write": make()}


# ================================================================
# 对外：预览 / 写回
# ================================================================
def run(game_dir, write=False, include_main=True, include_plugins=True,
        include_maps=True, include_dialog=False, emit=None):
    """
    预览（write=False）或写回（write=True）。返回报告 dict。

    include_maps  ：连 Data/Map*.rxdata 里事件脚本的 `_INTL("…")` 一起写回
                    （地图名 MapInfos.rxdata 不在此列，它归「地图名文本」管）。
    include_dialog：把语言文件第 0 段（地图对话）的译文直接钉进
                    Data/Map*.rxdata / CommonEvents.rxdata 的 101/401/102。
                    ★ 按原文匹配、忽略地图编号；会改 700+ 个地图文件，先备份再写。
    """
    def say(msg):
        if emit:
            emit(msg)

    game_dir = str(game_dir or "")

    say("\n" + "=" * 55)
    say("  脚本内文本汉化（写回 _INTL 源码）%s" % ("" if write else "［预览］"))
    say("=" * 55)

    table, notes = translation_map(game_dir, emit=say)
    for n in notes:
        say("  ⚠ %s" % n)
    if not table:
        if not include_dialog:
            return {"ok": False, "error": "没有可用的中文词表", "notes": notes}
        # ★ 只写地图对话时，脚本文本没有词表也不算错：对话词表来自第 0 段
        say("  ⚠ 脚本文本（第 24 段）没有中文词表，这次只处理地图对话")
    else:
        say("  词表共 %d 条（英文原文 → 中文）" % len(table))

    rep = {"ok": True, "write": bool(write), "dict": len(table),
           "files": [], "changed": 0, "miss": 0, "dynamic": 0,
           "already": 0, "skip_line": 0, "backups": [], "errors": [],
           "miss_samples": [], "notes": notes,
           "dialog_changed": 0, "dialog_miss": 0, "dialog_already": 0,
           "dialog_choices": 0, "dialog_files": 0}

    # 容器文件先备份（整份容器一改就是全量重写，必须能退回改动前那一刻）
    containers = [p for p in (GS.rxdata_path(game_dir),
                              GS.plugin_rxdata_path(game_dir))
                  if os.path.isfile(p)]
    before = {}
    if write:
        for p in containers:
            made = []
            try:
                _backup(p, made, stamp=True)
            except RuntimeError as e:
                say("  ✘ %s" % e)
                return {"ok": False, "error": str(e)}
            for b in made:
                rep["backups"].append(b)
                say("  已备份 %s" % os.path.basename(b))
            try:
                before[p] = len(GS.read_rxdata_entries(p)[0])
            except Exception:                 # noqa: BLE001
                before[p] = None

    for target in iter_targets(game_dir, include_main, include_plugins,
                               emit=say):
        stats = {}
        new, hits = rewrite_text(target["text"], table, stats)
        rep["miss"] += stats.get("miss", 0)
        rep["dynamic"] += stats.get("dynamic", 0)
        rep["already"] += stats.get("already", 0)
        rep["skip_line"] += stats.get("skip_line", 0)
        for s in stats.get("miss_samples", []):
            if s not in rep["miss_samples"]:
                rep["miss_samples"].append(s)
        if not hits:
            continue
        row = {"label": target["label"], "changed": hits,
               "kind": target["kind"],
               "bytes": (len(target["text"]), len(new))}
        if write:
            try:
                target["write"](new)
            except Exception as e:            # noqa: BLE001
                log.error("写回 %s 失败：%s", target["label"], e)
                rep["errors"].append("%s：%s" % (target["label"], e))
                say("  ✘ %s：%s" % (target["label"], e))
                continue
        rep["files"].append(row)
        rep["changed"] += hits
        say("  %s %-46s %d 处" % ("✔" if write else "·",
                                  row["label"][:46], hits))

    say("-" * 55)
    # ★ 地图事件（Data/Map*.rxdata）：事件指令里的 _INTL 也一起写回
    mchanged = 0
    if include_maps and table:
        say("  地图事件（Map*.rxdata）：")
        mrep = process_maps(game_dir, table, write=write, emit=say)
        for k in ("miss", "dynamic", "already", "skip_line"):
            rep[k] += mrep.get(k, 0)
        for s in mrep.get("miss_samples", []):
            if s not in rep["miss_samples"]:
                rep["miss_samples"].append(s)
        rep["backups"].extend(mrep.get("backups", []))
        rep["errors"].extend(mrep.get("errors", []))
        for row in mrep.get("files", []):
            rep["files"].append(row)
        mchanged = mrep.get("changed", 0)
        rep["changed"] += mchanged
        if not mrep.get("files"):
            say("    （没有需要改的地图事件文案）")
        rep["map_files"] = mrep.get("files", [])
        rep["map_changed"] = mchanged

    # ★ 地图对话（101/401/102）：把语言文件第 0 段的译文直接钉进地图文件
    if include_dialog:
        say("  地图对话（101/401/102 → Map*.rxdata / CommonEvents.rxdata）：")
        dtable, dnote = event_text_table(game_dir, emit=say)
        for n in dnote:
            say("  ⚠ %s" % n)
        if dtable:
            say("  对话词表 %d 条（按原文匹配，不看地图编号）" % len(dtable))
            drep = process_event_texts(game_dir, dtable, write=write, emit=say)
            for k in ("miss", "already", "choices"):
                rep["dialog_" + ("miss" if k == "miss" else k)] = \
                    drep.get(k, 0)
            rep["dialog_changed"] = drep.get("changed", 0)
            rep["dialog_files"] = len(drep.get("files") or [])
            rep["backups"].extend(drep.get("backups", []))
            rep["errors"].extend(drep.get("errors", []))
            for row in drep.get("files", []):
                rep["files"].append(row)
            if not drep.get("files"):
                say("    （没有需要改的地图对话）")

    say("-" * 55)
    say("  改写 %d 个文件、共 %d 处；已中文跳过 %d，动态串跳过 %d，"
        "加载资源的行跳过 %d"
        % (len(rep["files"]), rep["changed"], rep["already"],
           rep["dynamic"], rep["skip_line"]))
    if include_maps:
        say("  其中地图事件 %d 处（%d 个 Map 文件）"
            % (mchanged, len(rep.get("map_files") or [])))
    if include_dialog:
        say("  其中地图对话 %d 条（%d 个文件）；已是中文 %d 条，"
            "仍缺译文 %d 条%s"
            % (rep["dialog_changed"], rep["dialog_files"],
               rep["dialog_already"], rep["dialog_miss"],
               "（选项 %d 处）" % rep["dialog_choices"]
               if rep["dialog_choices"] else ""))
    if rep["miss"]:
        say("  仍有 %d 处查不到译文（脚本里有、词表里没有）" % rep["miss"])
    if rep["errors"]:
        say("  ✘ %d 个文件写失败，见日志" % len(rep["errors"]))
        rep["ok"] = False

    # ★ 写完复查：容器条目数必须和改之前一致（少一条游戏就缺脚本）
    if write:
        for p in containers:
            n0 = before.get(p)
            try:
                n1 = len(GS.read_rxdata_entries(p)[0])
            except Exception as e:            # noqa: BLE001
                n1 = None
                say("  ✘ %s 写完后读不回来：%s"
                    % (os.path.basename(p), e))
                rep["ok"] = False
            if n0 is not None and n1 is not None and n0 != n1:
                say("  ✘ %s 条目数变了：%d → %d"
                    % (os.path.basename(p), n0, n1))
                rep["ok"] = False
            elif n0 is not None:
                say("  ✔ %s 复查通过（%d 条脚本，未增减）"
                    % (os.path.basename(p), n1))

    if not write and rep["files"]:
        say("  这是预览，没有写任何文件。")
    return rep


def plan(game_dir, include_main=True, include_plugins=True, include_maps=True,
         include_dialog=False, emit=None):
    """只预览不改。"""
    return run(game_dir, write=False, include_main=include_main,
               include_plugins=include_plugins, include_maps=include_maps,
               include_dialog=include_dialog, emit=emit)


def apply(game_dir, include_main=True, include_plugins=True, include_maps=True,
          include_dialog=False, emit=None):
    """真写回。"""
    return run(game_dir, write=True, include_main=include_main,
               include_plugins=include_plugins, include_maps=include_maps,
               include_dialog=include_dialog, emit=emit)
