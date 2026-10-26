# -*- coding: utf-8 -*-
"""
"""
import io
import os
import re
import shutil
import time

import game_scripts as GS
import intl_text as IT
import logger

log = logger.get_logger(__name__)

SCRIPT_TEXTS_SECTION = 24

# `_INTL("...")` / `_ISPRINTF("...")` —— 前面不能紧跟标识符字符（防 pb_INTL）
_LIT_RE = re.compile(r'(?<![A-Za-z0-9_])(?:_INTL|_ISPRINTF)\s*\(\s*"((?:[^"\\]|\\.)*)"')

# ★ 判「是不是中文」要连**全角标点**一起认：`{1}（PP：---）` 整串只有
#   U+FF08 / U+FF1A 这类全角符号，只查 \u4e00-\u9fff 会把它当成没翻。
_CJK_RE = re.compile(u"[\u2e80-\u9fff\uf900-\ufaff\uff01-\uff60]")


def has_cjk(text):
    return bool(text and _CJK_RE.search(text))


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
    try:
        messages = IT.read_messages(path)
    except Exception as e:                    # noqa: BLE001
        note.append("读不了 %s：%s" % (os.path.basename(path), e))
        return 0
    if len(messages) <= SCRIPT_TEXTS_SECTION:
        note.append("%s 没有第 %d 段" % (os.path.basename(path),
                                        SCRIPT_TEXTS_SECTION))
        return 0
    n = 0
    for key, value in _pairs(messages[SCRIPT_TEXTS_SECTION]):
        if not key or not isinstance(key, str):
            continue
        if not isinstance(value, str) or value == key or not has_cjk(value):
            continue
        if table.get(key) == value:
            continue
        table[key] = value
        n += 1
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
        note.append("没读到中文词表。先「编译文本」把译文写进 %s 再回来。"
                    % ("messages_%s_*.dat" % frag if frag else "语言文件"))
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
                   include_plugins=True, emit=None):
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
        for n in notes:
            say("  ⚠ %s" % n)
        return {"ok": False, "error": "没有可用的中文词表", "count": 0}

    seen = {}
    skipped = 0
    for target in iter_targets(game_dir, include_main, include_plugins,
                               emit=say):
        stats = {}
        rewrite_text(target["text"], table, stats)
        for s in stats.get("miss_samples", []):
            if not s or s in seen:
                continue
            if not is_translatable(s):
                skipped += 1
                continue
            seen[s] = 1

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

    stats（可选 dict）会被累加：hit / already / dynamic / miss，并收集 miss 样例。
    """
    if stats is None:
        stats = {}
    for k in ("hit", "already", "dynamic", "miss"):
        stats.setdefault(k, 0)
    stats.setdefault("miss_samples", [])
    stats.setdefault("miss_set", set())

    def rep(m):
        body = m.group(1)
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
        emit=None):
    """
    预览（write=False）或写回（write=True）。返回报告 dict。
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
        return {"ok": False, "error": "没有可用的中文词表", "notes": notes}
    say("  词表共 %d 条（英文原文 → 中文）" % len(table))

    rep = {"ok": True, "write": bool(write), "dict": len(table),
           "files": [], "changed": 0, "miss": 0, "dynamic": 0,
           "already": 0, "backups": [], "errors": [],
           "miss_samples": [], "notes": notes}

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
    say("  改写 %d 个文件、共 %d 处；已中文跳过 %d，动态串跳过 %d"
        % (len(rep["files"]), rep["changed"], rep["already"], rep["dynamic"]))
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


def plan(game_dir, include_main=True, include_plugins=True, emit=None):
    """只预览不改。"""
    return run(game_dir, write=False, include_main=include_main,
               include_plugins=include_plugins, emit=emit)


def apply(game_dir, include_main=True, include_plugins=True, emit=None):
    """真写回。"""
    return run(game_dir, write=True, include_main=include_main,
               include_plugins=include_plugins, emit=emit)
