# -*- coding: utf-8 -*-
"""
核心功能实现。

设计约定：
  · 所有 xxx_paths(...) 为「无交互核心」，只通过 bridge 输出/上报进度，
    供命令行与 GUI 共用；
  · 所有 cmd_xxx(...) 为命令行外壳，负责询问语言、选择文件范围等。
"""
import json
import os
import re
import threading
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import bridge
import checker
import config
import parser as P
import processor as PR
import replacement as REPL
import restoration as RESTORE
import settings
import translator as T
from cache import Cache, atomic_replace, load_edits
from logger import get_logger
from translator import (OllamaClient, estimate_tokens, polish_with_retry,
                        resolve_concurrency, translate_with_retry)

log = get_logger("commands")

# ★ 并发批翻译时的共享资源锁：
#   _PREFIX_LOCK    —— prefix_dict 的注册与落盘（读改写同一个 json）
#   _TERM_MERGE_LOCK —— auto_terms 合并内联术语（读改写 term_dict.py）
_PREFIX_LOCK = threading.Lock()
_TERM_MERGE_LOCK = threading.Lock()


def emit(*args, **kwargs):
    """统一输出：GUI 接管后写入日志页，命令行下就是 print。"""
    bridge.emit(*args, **kwargs)


# ================================================================
# 常用语言列表
# ================================================================
LANG_OPTIONS = [
    "英文",
    "简体中文",
    "繁体中文",
    "西班牙文",
]

# 重翻检查报告时，默认要处理的问题类型（GUI 里可逐项勾选）
RETRANSLATE_KINDS = {
    "疑似未翻译", "疑似异常句", "译文残留占位符",
    "翻译失败", "符号不匹配", "标点结构",
}

# ★ 永远不参与自动重翻的类型：
#   · 译文残留控制码 —— 重翻并不能保证修好，改由用户手工处理
#   · 符号不匹配 / 特殊行 —— 需要人工判断
NEVER_RETRANSLATE_KINDS = {
    "译文残留控制码", "特殊行", "控制码回退",
    # 模型输出了真实换行，写缓存时已被自动压成空格 —— 提示供人工核对
    "译文含真实换行",
}

# ★ 手工编辑产生的类型：报告里**默认不勾选**（所以不参与重翻），
#   但可以勾上查看 —— 用户改过的句子都归在这里，方便回头核对。
MANUAL_KINDS = {"已编辑"}

# ★ 「提示 / 抽查」类型：只是给你看一眼的线索，**不算问题** ——
#   「术语冲突」自 2026-10-14 起也归这里（术语译法不一致，与句子质量无关，只提示、不计入问题数）。
#   不计入「共 N 处问题」的汇总，界面上也不显示成红色。
ADVISORY_KINDS = {"术语冲突"}

# 报告里可能出现的问题类型（展示 / 排序用）
# ★ 「术语冲突」是「提示 / 抽查」类：默认不勾选（不显示、
#   默认不重翻），勾上才显示；它不会抑制该句的其它检查
#   （见 checker.check 的 info 标记）。
# ★ 「派生命中」「术语未应用」已停用：不再扫描、不再进报告。
REPORT_KIND_ORDER = [
    "翻译失败", "术语冲突", "控制码回退",
    "疑似未翻译", "疑似异常句",
    "译文残留占位符", "译文残留控制码",
    "译文含真实换行",
    "符号不匹配", "标点结构", "特殊行", "已编辑",
]

# ★ 「共 N 处问题」里的 N 只统计**要处理的问题**：
#   · 手工编辑类（已编辑）：你自己改好的句子，不是问题；
#   · 需手动类（译文残留控制码 / 特殊行 / 控制码回退）：报告里只有灰色
#     提示、连勾选框都没有，同样不算问题。
#   于是这个数正好等于「默认勾选的那几类」的条数 —— 报告标题上的
#   「显示 X / 共 Y」不会再被几百条提示撑大。
PROBLEM_KINDS = tuple(
    k for k in REPORT_KIND_ORDER
    if k not in NEVER_RETRANSLATE_KINDS
    and k not in MANUAL_KINDS
    and k not in ADVISORY_KINDS
)


def count_problems(hits):
    """
    数「问题」条数 —— 报告标题那行「共 N 处问题」用它。

    hits 可以传 [(源路径, hit), ...]（GUI 的 report_hits），
    也可以传 [hit, ...]；只数 PROBLEM_KINDS 里的类型，
    「术语冲突」这类提示**不计入**（758 条提示不该算成 758 处问题）。
    """
    n = 0
    for item in hits or []:
        h = item[-1] if isinstance(item, (tuple, list)) and item else item
        if isinstance(h, dict) and h.get("kind") in PROBLEM_KINDS:
            n += 1
    return n


# ================================================================
# 报告里手工编辑的译文
#   存储与读写都在 cache.py（checker 也要读，放这里会循环 import）
# ================================================================
def save_report_edit(src, dst, src_path=None):
    """
    在报告里手工改一句译文：
      ① 写进翻译缓存（原样覆盖，重翻时不会把它当成未翻）；
      ② 记进 <缓存>_edited.json，下次「刷新报告」时这一句归入「已编辑」类型。

    src_path: 这句属于哪个**源文件**（多文件报告时用它精确定位缓存；
              省略则沿用当前 Runtime 的缓存）。

    返回 {"cache": 缓存路径, "edited": 记录路径}。
    """
    cache_file = (cache_path_for(src_path) if src_path
                  else getattr(config.Runtime, "cache_file", "")
                  or config.CACHE_FILE)
    if not os.path.isfile(cache_file):
        raise FileNotFoundError(f"找不到翻译缓存：{cache_file}\n"
                                f"（先跑一次翻译才会生成）")
    cache = Cache(cache_file)
    return cache.save_edit(src, dst)


def save_report_edit_and_apply(src, dst, src_path=None):
    """
    在报告里手工改一句译文，**立即落盘**：

      ① 写进翻译缓存 + <缓存>_edited.json（同 save_report_edit）；
      ② 就地改写译文文件（*_translated.txt）里这一句所在的行，
         其余行一个字不动——「需手动」类型（译文残留控制码 / 特殊行 /
         控制码回退 / 译文含真实换行等）保存后立刻生效，不用再点「应用已编辑」。

    返回 save_report_edit 的结果 + {"file_written": True/False}。
    """
    res = save_report_edit(src, dst, src_path=src_path)

    # ---- 定位译文文件：优先用调用方给的源文件，否则用 Runtime 当前输入 ----
    path = (src_path or getattr(config.Runtime, "input_file", "") or "").strip()
    out_path = ""
    if path and os.path.isfile(path):
        config.Runtime.set_input(path)
        out_path = config.Runtime.output_file

    res["file_written"] = False
    if not (out_path and os.path.isfile(out_path)):
        emit("  ⚠ 找不到译文文件，只写入了缓存（先跑一次翻译）")
        return res

    try:
        src_lines, _ = P.read_file(path, config.INPUT_ENCODING)
        out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
        # ★ 行数哨兵：译文文件混入过真实换行会整体错位，此时按 idx 写行
        #   会写进错误的句子——宁可不写，让用户重翻该文件
        if len(out_lines) != len(src_lines):
            emit(f"  ⚠ 行数不一致（原文 {len(src_lines)} / 译文 "
                 f"{len(out_lines)}），译文文件没改——请重新翻译该文件"
                 f"（缓存已更新）")
            return res
        out_nl = P.detect_newline(out_path, default=os.linesep)

        entries, _ = P.extract_entries(src_lines)
        line_of = {}
        for idx, esrc in entries:
            key = (esrc or "").strip()
            if key and key not in line_of:
                line_of[key] = idx

        idx = line_of.get((src or "").strip())
        if idx is None or idx >= len(out_lines):
            emit("  ⚠ 在原文里没定位到这一句，只写入了缓存")
            return res

        m = re.match(r'^([ \t]*)', src_lines[idx])
        indent = m.group(1) if m else ""
        new_line = indent + (dst or "")
        if out_lines[idx] != new_line:
            out_lines[idx] = new_line
            tmp = out_path + ".tmp"
            with open(tmp, "w", encoding=config.OUTPUT_ENCODING,
                      newline="") as f:
                f.write(out_nl.join(out_lines))
            atomic_replace(tmp, out_path)
            res["file_written"] = True
            log.info("手工编辑已写入译文文件：%s 行 %d", out_path, idx + 1)
    except Exception as e:
        emit(f"  ⚠ 缓存已更新，但写译文文件失败：{e}")
    return res


# ================================================================
# 「应用已编辑」：把手工改过的译文真正落到缓存 + 译文文件
# ================================================================
def _edited_path_for(src_path):
    """
    源文件 → 手工编辑记录路径（与 cache.edited_path 的规则一致）：
        <中间文件目录>/<主名>_cache_edited.json
    ★ 中间文件目录 = 源目录下若有「翻译中间文件」夹就用它（见 config.aux_dir），
      与缓存落在同一处，两边的规则必须一致，否则统计会数不到。
    """
    src = source_of(src_path)
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(config.aux_dir(src), f"{stem}_cache_edited.json")


def count_manual_edits(paths):
    """统计这些源文件各自的手工编辑条数 → (有编辑的文件数, 总条数)。"""
    files = total = 0
    for path in paths or []:
        if not path:
            continue
        try:
            with open(_edited_path_for(path), "r", encoding="utf-8") as f:
                data = json.load(f)
            n = len(data) if isinstance(data, dict) else 0
        except Exception:
            n = 0
        if n:
            files += 1
            total += n
    return files, total


def apply_manual_edits(paths):
    """
    把报告里手工编辑过的译文（<缓存名>_edited.json）真正应用下去：

      ① 覆盖翻译缓存里的对应条目（以后重翻 / 换行重排拿到的都是手工译文）；
      ② 就地改写已生成的译文文件（*_translated.txt）：
         只替换编辑过的那些句子，其余行一个字都不动。

    返回 {"files", "applied", "missing", "no_edit"}。
    """
    log.info("=" * 50)
    log.info("应用手工编辑  共 %d 个文件", len(paths))
    emit("\n" + "=" * 55)
    emit("  应用已编辑（把手工改过的句子写进缓存与译文文件）")
    emit("=" * 55)

    files_done = applied = missing = no_edit = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            emit("\n[中断] 用户取消")
            break
        if not path or not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        config.Runtime.set_input(path)
        name = os.path.basename(path)
        bridge.progress(i - 1, len(paths), name)

        edits = load_edits()
        if not edits:
            emit(f"[{i}/{len(paths)}] {name}：没有手工编辑记录，跳过")
            no_edit += 1
            continue

        # ---- ① 写回翻译缓存 ----
        cpath = config.Runtime.cache_file
        n_cache = 0
        try:
            cache = Cache(cpath)
            for src, dst in edits.items():
                if cache.get(src) != dst:
                    cache.put(src, dst)
                    n_cache += 1
            cache.save(force=True)
        except Exception as e:
            emit(f"  写缓存失败：{e}")
            continue

        # ---- ② 写回译文文件 ----
        out_path = config.Runtime.output_file
        if not os.path.exists(out_path):
            emit(f"  ⚠ 找不到译文文件：{os.path.basename(out_path)}"
                 f"（缓存已更新 {n_cache} 条，译文文件没改；先跑一次翻译）")
            missing += 1
            continue

        try:
            src_lines, _ = P.read_file(path, config.INPUT_ENCODING)
            out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
        except Exception as e:
            emit(f"  读取失败：{e}")
            continue
        # ★ 行数哨兵：译文文件混入过真实换行会整体错位，此时按 idx 写行
        #   会把文字写进错误的句子——宁可不写，让用户重翻该文件
        if len(out_lines) != len(src_lines):
            emit(f"  ⚠ 行数不一致（原文 {len(src_lines)} / 译文 "
                 f"{len(out_lines)}），译文文件没改——请重新翻译该文件"
                 f"（缓存已更新 {n_cache} 条）")
            missing += 1
            continue
        # ★ 行尾按译文文件的原始字节定，别让 Windows 文本模式把 LF 变 CRLF
        out_nl = P.detect_newline(out_path, default=os.linesep)

        entries, _ = P.extract_entries(src_lines)
        line_of = {}
        for idx, src in entries:
            key = (src or "").strip()
            if key and key not in line_of:
                line_of[key] = idx

        n_file = 0
        for src, dst in edits.items():
            idx = line_of.get((src or "").strip())
            if idx is None or idx >= len(out_lines):
                continue
            m = re.match(r'^([ \t]*)', src_lines[idx])
            indent = m.group(1) if m else ""
            new_line = indent + (dst or "")
            if out_lines[idx] == new_line:
                continue
            out_lines[idx] = new_line
            n_file += 1

        if not n_file:
            emit(f"[{i}/{len(paths)}] {name}：译文文件已是最新"
                 f"（缓存更新 {n_cache} 条）")
            files_done += 1
            continue

        try:
            tmp = out_path + ".tmp"
            with open(tmp, "w", encoding=config.OUTPUT_ENCODING,
                      newline="") as f:
                f.write(out_nl.join(out_lines))
            atomic_replace(tmp, out_path)
        except Exception as e:
            emit(f"  写入失败：{e}")
            continue

        emit(f"[{i}/{len(paths)}] {name}：已应用 {n_file} 句"
             f"（缓存更新 {n_cache} 条）→ {os.path.basename(out_path)}")
        applied += n_file
        files_done += 1

    bridge.progress(len(paths), len(paths), "完成")
    emit(f"\n✔ 应用已编辑完成：{files_done} 个文件，改写 {applied} 句"
         + (f"，{missing} 个文件缺少译文文件" if missing else ""))
    log.info("应用手工编辑完成：%d 个文件 / 改写 %d 句", files_done, applied)
    return {"files": files_done, "applied": applied,
            "missing": missing, "no_edit": no_edit}


# ================================================================
# 路径
# ================================================================
def _report_path():
    """检查报告路径：中间文件 → 优先放「翻译中间文件」夹。"""
    out = config.Runtime.output_file
    d = config.aux_dir(out) or "."
    base = os.path.splitext(os.path.basename(out))[0]
    return os.path.join(d, f"{base}_report.txt")


def _unknown_ctrl_report_path():
    """未识别控制码报告：中间文件 → 优先放「翻译中间文件」夹。"""
    inp = config.Runtime.input_file
    d = config.aux_dir(inp) or "."
    base = os.path.splitext(os.path.basename(inp))[0]
    return os.path.join(d, f"{base}_unknown_ctrl.txt")


def _open_path(path):
    """用系统默认程序打开文件 / 目录（命令行版；失败返回 False）。"""
    try:
        if not os.path.exists(path):
            if os.path.splitext(path)[1]:        # 看起来是文件 → 建空文件
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                open(path, "a", encoding="utf-8").close()
            else:                                # 否则当目录
                os.makedirs(path, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        emit(f"打开失败：{e}，请手动打开：{path}")
        return False


# ================================================================
# 术语冲突记录（翻译时落盘，检查报告 / 冲突面板共用）
#   结构：{术语原文: {"old": 已有译文, "new": 模型返回的译文,
#                     "src": [命中该术语的句子, …]}}
# ================================================================
def _conflict_path():
    """术语冲突记录文件：与缓存文件同目录。"""
    cf = getattr(config.Runtime, "conflict_file", None)
    if cf:
        return cf
    cache = config.Runtime.cache_file
    d = os.path.dirname(cache) or "."
    base = os.path.splitext(os.path.basename(cache))[0]
    return os.path.join(d, f"{base}_conflicts.json")


def load_term_conflicts(path=None):
    """读取术语冲突记录，返回 dict；文件不存在 / 损坏时返回 {}。"""
    import json
    p = path or _conflict_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning("读取术语冲突记录失败：%s", e)
        return {}


def save_term_conflicts(data, path=None):
    """写入术语冲突记录（原子替换）。"""
    import json
    p = path or _conflict_path()
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data or {}, f, ensure_ascii=False, indent=2)
        atomic_replace(tmp, p)
        return True
    except Exception as e:
        log.warning("写入术语冲突记录失败：%s", e)
        return False


def _record_term_conflicts(records):
    """
    把本批次新发现的术语冲突并进记录文件。
    records: [{"src": 术语原文, "old": …, "new": …, "sentence": 句子}]
    """
    if not records:
        return
    data = load_term_conflicts()
    for r in records:
        key = r.get("src") or ""
        if not key:
            continue
        item = data.get(key)
        if not isinstance(item, dict):
            item = {"old": r.get("old", ""), "new": r.get("new", ""),
                    "src": []}
            data[key] = item
        # ★ 冲突内容变了（旧译法或模型新译法不同）→ 重新算「待解决」；
        #   一模一样的冲突再次出现时保留用户已标记的「已编辑」。
        if (item.get("old", "") != r.get("old", "")
                or item.get("new", "") != r.get("new", "")):
            item.pop("edited", None)
        item["old"] = r.get("old", item.get("old", ""))
        item["new"] = r.get("new", item.get("new", ""))
        sent = (r.get("sentence") or "").strip()
        if sent and sent not in item.setdefault("src", []):
            item["src"].append(sent)
    save_term_conflicts(data)


def drop_term_conflicts(terms):
    """冲突解决后，把这几个术语从记录里移除。"""
    data = load_term_conflicts()
    if not data:
        return 0
    n = 0
    for t in terms or []:
        if t in data:
            data.pop(t, None)
            n += 1
    if n:
        save_term_conflicts(data)
    return n


def set_term_conflicts_edited(term, src_paths=None, edited=True):
    """
    把某个术语的冲突在各源文件的记录里标成「已编辑 / 待解决」。

    状态有两种：
      · 待解决（记录里没有 edited 字段）
      · 已编辑（edited=True）—— 保存过这句的译文，或在列表里点「状态」列手动标记

    src_paths: 该术语可能出现在哪些源文件的 <名>_conflicts.json 里；
               None → 只动当前 Runtime 的那一份。
    返回实际改动的文件数。
    """
    term = (term or "").strip()
    if not term:
        return 0

    if src_paths:
        paths = [conflict_path_for(p) for p in src_paths]
    else:
        paths = [_conflict_path()]

    changed = 0
    for p in dict.fromkeys(x for x in paths if x):
        data = load_term_conflicts(p)
        item = data.get(term)
        if not isinstance(item, dict):
            continue
        if bool(item.get("edited")) == bool(edited):
            continue
        if edited:
            item["edited"] = True
        else:
            item.pop("edited", None)
        if save_term_conflicts(data, p):
            changed += 1
    if changed:
        log.info("术语冲突「%s」标记为%s（%d 个记录文件）",
                 term, "已编辑" if edited else "待解决", changed)
    return changed


def drop_edited_term_conflicts(src_paths):
    """
    把**已编辑**的术语冲突从这些源文件的 <名>_conflicts.json 里删掉。

    术语冲突界面点「应用已编辑」时调用：译文这时已经写进缓存与译文文件，
    这条冲突没必要再留在记录里（否则刷新报告还会看到它）。

    返回 (删除条数, 改动的文件数)。
    """
    total = files = 0
    for sp in dict.fromkeys(p for p in (src_paths or []) if p):
        p = conflict_path_for(sp)
        if not p:
            continue
        data = load_term_conflicts(p)
        if not data:
            continue
        drop = [t for t, item in data.items()
                if isinstance(item, dict) and item.get("edited")]
        if not drop:
            continue
        for t in drop:
            data.pop(t, None)
        if save_term_conflicts(data, p):
            total += len(drop)
            files += 1
            log.info("术语冲突记录已清理 %d 条（已编辑）：%s",
                     len(drop), os.path.basename(p))
    if total:
        log.info("术语冲突：已编辑的 %d 条已从记录里移除（%d 个文件）",
                 total, files)
    return total, files


def load_conflict_rows(src_paths):
    """
    汇总这些源文件的术语冲突记录 → 供「术语冲突列表」视图展示的行。

    返回 [{"term", "old", "new", "edited", "sources": [源文件…],
           "sents": [{"src": 句子, "dst": 当前缓存译文, "path": 源文件}…]}, …]

    · 同一个术语出现在多个文件里时合并成一行（只要有一处还是待解决就算待解决）；
    · edited=True 表示这条冲突已经被处理过（改过译文，或手动点了「状态」列）；
    · 译文取**翻译缓存**里的当前值（手工编辑写入的也是缓存）；
    · 待解决的排前面，已编辑的排最后；同组内按术语原文排序。
    """
    rows = {}
    file_state = {}          # 源文件 → (conflict dict, Cache)

    for sp in (src_paths or []):
        if not sp:
            continue
        cf = conflict_path_for(sp)
        cp = cache_path_for(sp)
        if sp in file_state:
            data, cache = file_state[sp]
        else:
            data = load_term_conflicts(cf) if cf else {}
            cache = Cache(cp) if (cp and os.path.isfile(cp)) else None
            file_state[sp] = (data, cache)

        for term, item in (data or {}).items():
            if not isinstance(item, dict):
                continue
            row = rows.get(term)
            if row is None:
                row = rows[term] = {
                    "term": term, "old": "", "new": "",
                    "edited": True, "sources": [], "sents": [],
                    "_seen": set(),
                }
            if sp not in row["sources"]:
                row["sources"].append(sp)
            if not item.get("edited"):
                row["edited"] = False
            if not row["old"] and item.get("old"):
                row["old"] = item.get("old") or ""
            if not row["new"] and item.get("new"):
                row["new"] = item.get("new") or ""

            for sent in (item.get("src") or []):
                sent = (sent or "").strip()
                if not sent:
                    continue
                key = (sp, sent)
                if key in row["_seen"]:
                    continue
                row["_seen"].add(key)
                row["sents"].append({
                    "src": sent,
                    "dst": (cache.get(sent, "") if cache else "") or "",
                    "path": sp,
                })

    out = list(rows.values())
    for r in out:
        r.pop("_seen", None)
    out.sort(key=lambda r: (bool(r["edited"]), r["term"].lower()))
    return out

# ================================================================
# 派生命中（方案 F）：已停用 —— 不再扫描、不再进检查报告。
# ================================================================
def _has_derived_candidate(line):
    """
    便宜的预筛：这行有没有「词根 + 后缀」形态的词。

    只分词 + 查表，不做 protect()，所以绝大多数行几乎零成本；
    预筛为真才走完整的 find_derived_terms（与翻译时同一套）。
    """
    if not line or not getattr(config, "TERM_DERIVED_MATCH", True):
        return False
    try:
        import processor as PR
        if not PR._TERM_SINGLE:
            return False
        lookup = PR._derived_lookup
        min_len = PR.TERM_DERIVED_MIN_ROOT
        for tok in PR._TOKEN_RE.findall(line):
            if len(tok) <= min_len:
                continue
            if lookup(tok.lower())[0]:
                return True
    except Exception:
        return False
    return False


def _derived_term_hits(entries=None, out_lines=None):
    """
    把「术语词根派生命中」列进报告（方案 F，只作提示）。

    例如术语表里有 Altaria=七夕青鸟，源文里的 Altarianites 就会在这里
    记一条：说明它命中了哪个词根、该用什么译名，方便你抽查模型有没有照做。
    """
    if not entries or not getattr(config, "TERM_DERIVED_MATCH", True):
        return []
    try:
        import processor as PR
        PR.load_terms()
        if not PR._TERM_SINGLE:
            return []
    except Exception as e:
        log.debug("派生命中扫描跳过（术语表不可用）：%s", e)
        return []

    hits = []
    for ln, src in entries:
        if not _has_derived_candidate(src):
            continue
        try:
            found = PR.find_derived_terms(src)
        except Exception as e:
            log.debug("派生命中扫描失败（跳过该行）：%s", e)
            continue
        if not found:
            continue
        dst = ""
        if out_lines is not None and 0 <= ln < len(out_lines):
            dst = out_lines[ln].strip()
        detail = "；".join(f'{d["word"]} → 词根 {d["root"]}={d["dst"]}'
                           for d in found[:5])
        if len(found) > 5:
            detail += f"；…另 {len(found) - 5} 处"
        hits.append({
            'line_no': ln,
            'kind': '派生命中',
            'src': src,
            'dst': dst,
            'detail': f"术语词根派生命中：{detail}",
            # ★ info=True：只提示，不跳过这句的其它检查（checker.check 里认这个标记）
            'info': True,
            'derived': found,
        })
    if hits:
        log.info("派生命中 %d 条（术语词根派生匹配）", len(hits))
    return hits

def _unapplied_term_hits(entries=None, out_lines=None, section=None):
    """
    「术语未应用」：已停用 —— 不再扫描、不再进检查报告。

    借鉴 LinguaGacha 的「术语未应用」校对警告 —— 只作提示：
    · 不计入「共 N 处问题」（ADVISORY_KINDS）；
    · 报告里默认不勾选，勾上才显示；
    · info=True，不抑制该句的其它检查。

    ★ section：当前文件的 section 名（term_extract.resolve_names 判定）。
      同原文多译文（term_sections.json 的 variants）投送后，译文里出现
      **任一**变体即算已应用 —— 否则「译文用了超能力却没精神强念」这类
      正确翻译会被误报。

    术语表不可用 / 没开术语替换时返回 []。
    """
    if not entries or not getattr(config, "APPLY_TERMS", True):
        return []
    try:
        PR.load_terms()
        if not PR._TERM_SINGLE and not PR._MULTI_RE:
            return []
    except Exception as e:
        log.debug("术语未应用扫描跳过（术语表不可用）：%s", e)
        return []

    hits = []
    for ln, src in entries:
        try:
            # 先 protect 再找：控制码 / 标签内部的词不算术语命中
            # （与翻译时的匹配同源，避免误报）
            safe, _maps = PR.protect(src)
            found = PR.find_terms(safe)
        except Exception as e:
            log.debug("术语未应用扫描失败（跳过该行）：%s", e)
            continue
        if not found:
            continue
        dst = ""
        if out_lines is not None and 0 <= ln < len(out_lines):
            dst = out_lines[ln]
        if not dst:
            continue
        # ★ 译文里出现该术语任一变体即算已应用；都不在才算漏
        missing = []
        for s, d in found:
            if not d:
                continue
            cands = PR.term_dst_variants(s, section=section)
            if any(c and c in dst for c in cands):
                continue
            missing.append((s, d))
        if not missing:
            continue
        detail = "；".join(f"{s} 应为 {d}" for s, d in missing[:5])
        if len(missing) > 5:
            detail += f"；…另 {len(missing) - 5} 处"
        hits.append({
            'line_no': ln,
            'kind': '术语未应用',
            'src': src,
            'dst': dst,
            'detail': f"术语未应用：{detail}",
            # ★ info=True：只提示，不跳过这句的其它检查（checker.check 里认这个标记）
            'info': True,
        })
    if hits:
        log.info("术语未应用 %d 条（原文命中术语、译文未用规范译名）",
                 len(hits))
    return hits


def _write_term_stats(src_path, stat_batches):
    """
    把各批的术语命中按句数合并，写 <aux 目录>/terms_stats.json。

    用途：发现「提取了但游戏里根本没出现」的废术语、以及真正高频的
    核心术语（后者值得在 prompt 里优先注入）。
    """
    counts = {}
    for d in stat_batches or []:
        for term, n in d.items():
            counts[term] = counts.get(term, 0) + n
    if not counts:
        return None

    total_terms = 0
    try:
        PR.load_terms()
        total_terms = len(PR._TERMS)
    except Exception as e:
        log.debug("术语总数统计失败：%s", e)

    data = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": os.path.basename(src_path or ""),
        "total_terms": total_terms,
        "hit_terms": len(counts),
        "unused_terms": max(0, total_terms - len(counts)),
        "counts": dict(sorted(counts.items(),
                              key=lambda kv: (-kv[1], kv[0]))),
    }
    aux = config.aux_dir(src_path, create=True)
    path = os.path.join(aux, "terms_stats.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    atomic_replace(tmp, path)

    top = list(data["counts"].items())[:5]
    emit("  [术语统计] 高频术语："
         + "，".join(f"{t}×{n}" for t, n in top))
    if data["unused_terms"]:
        emit(f"  [术语统计] 本次未命中 {data['unused_terms']} 条术语"
             f"（详见 {path}）")
    log.info("术语命中统计已写入：%s（命中 %d / 共 %d）",
             path, len(counts), total_terms)
    return path



# 生成物后缀（选文件时要跳过 / 报告模式下要识别）
TRANSLATED_SUFFIX = "_translated.txt"
REPORT_SUFFIX     = "_translated_report.txt"
CACHE_SUFFIX      = "_cache.json"
CONFLICT_SUFFIX   = "_conflicts.json"
POLISH_LOG_SUFFIX = "_polished.txt"

# 「缓存 / 译文 / 报告 / 润色」→ 源文件，按长到短匹配
# （_translated_report.txt 先于 _translated.txt；_polish_cache.json 先于
#   _cache.json，否则后者会把前者切错）
_GENERATED_SUFFIXES = (REPORT_SUFFIX, TRANSLATED_SUFFIX,
                       "_polish_cache.json", POLISH_LOG_SUFFIX, CACHE_SUFFIX)


def enter_work_dir(paths):
    """
    「翻译整个文件夹」时，在文件夹下建「翻译中间文件」夹，把中间文件放进去。

    条件：**≥2 个文件且都在同一个目录**（单文件 / 跨目录的一批不建，
    保持老行为：中间文件跟源文件同目录）。
    返回建好的目录；没建返回 ""。
    """
    items = [p for p in (paths or []) if p]
    dirs = {os.path.dirname(os.path.abspath(p)) for p in items}
    if len(items) < 2 or len(dirs) != 1:
        return ""
    d = next(iter(dirs))
    wd = os.path.join(d, config.WORK_DIR_NAME)
    try:
        os.makedirs(wd, exist_ok=True)
    except OSError as e:
        log.warning("建「%s」失败（中间文件仍放源目录）：%s",
                    config.WORK_DIR_NAME, e)
        return ""
    return wd


def _announce_work_dir(paths):
    """
    批量处理前先建好「翻译中间文件」夹并打一行日志。
    返回目录（没建 → ""，表示中间文件仍与源文件同目录）。
    """
    wd = enter_work_dir(paths)
    if wd:
        log.info("本次中间文件目录：%s", wd)
        emit(f"  · 缓存 / 冲突 / 报告 / 润色稿等中间文件都放进：{wd}")
    return wd


def source_of(path):
    """
    把「缓存文件 / 译文文件 / 检查报告 / 润色稿」换回它对应的**源文件**路径；
    本来就是源文件的原样返回。

    ★ 菜单 4（术语重翻）/ 6（中文润色）只允许选 `*_cache.json`、
      菜单 7（换行重排）只允许选 `*_translated.txt`，而后面的流程都是按
      **源文件**推导缓存与译文路径的（Runtime.set_input），所以要先换算一步，
      否则会拼出 `xxx_cache_cache.json` 这种鬼东西。
    ★ 中间文件若在「翻译中间文件」夹里，源文件在它的**上一层**。
    """
    if not path:
        return path
    text = str(path)
    low = text.lower()
    for suf in _GENERATED_SUFFIXES:
        if low.endswith(suf):
            base = os.path.basename(text)[: -len(suf)]
            d = os.path.dirname(text)
            if os.path.basename(os.path.abspath(d)) == config.WORK_DIR_NAME:
                d = os.path.dirname(d)
            return os.path.join(d, base + ".txt") if d else base + ".txt"
    return path


def cache_path_for(path):
    """源文件 / 译文 / 缓存 → 对应的翻译缓存路径（*_cache.json）。"""
    if not path:
        return None
    src = source_of(path)
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(config.aux_dir(src), f"{stem}{CACHE_SUFFIX}")


def translated_path_for(path):
    """源文件 / 译文 / 缓存 → 对应的译文文件路径（*_translated.txt）。"""
    if not path:
        return None
    src = source_of(path)
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(os.path.dirname(os.path.abspath(src)),
                        f"{stem}{TRANSLATED_SUFFIX}")


def report_path_for(src_path):
    """源文件 → 对应检查报告路径（中间文件，放「翻译中间文件」夹）。"""
    if not src_path:
        return None
    src = source_of(src_path)
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(config.aux_dir(src), f"{stem}{REPORT_SUFFIX}")


def conflict_path_for(src_path):
    """
    源文件 → 对应的术语冲突记录路径（*_conflicts.json）。
    规则与 config.Runtime.set_input 一致；不碰 Runtime，便于按文件精确读写。
    """
    if not src_path:
        return None
    src = source_of(src_path)
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(config.aux_dir(src), f"{stem}{CONFLICT_SUFFIX}")


def source_path_for_report(report_path):
    """
    检查报告 → 原始源文件路径。
    报告名为 <原名>_translated_report.txt，反推源文件时按常见扩展名试，
    找不到就在同目录里按前缀匹配。
    ★ 报告放在「翻译中间文件」夹里时，源文件在**上一层**，两处都找。
    """
    if not report_path:
        return None
    base = os.path.basename(report_path)
    d = os.path.dirname(os.path.abspath(report_path))
    if not base.lower().endswith(REPORT_SUFFIX):
        return report_path if os.path.exists(report_path) else None

    stem = base[: -len(REPORT_SUFFIX)]
    cand_dirs = [d]
    if os.path.basename(d) == config.WORK_DIR_NAME:
        cand_dirs.append(os.path.dirname(d))

    for cd in cand_dirs:
        for ext in (".txt", ".TXT", ".json", ".yml", ".yaml", ".csv", ""):
            p = os.path.join(cd, stem + ext)
            if os.path.isfile(p):
                return p
        try:
            for f in sorted(os.listdir(cd)):
                low = f.lower()
                if (low.startswith(stem.lower() + ".")
                        and not (low.endswith(TRANSLATED_SUFFIX)
                                 or low.endswith(REPORT_SUFFIX))):
                    return os.path.join(cd, f)
        except OSError:
            pass
    return None


def _write_unknown_ctrl_report(hits, report_path):
    """hits: [(token, original, context), ...]"""
    grouped = defaultdict(list)
    for token, orig, ctx in hits:
        grouped[token].append((orig, ctx))

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 未识别控制码报告\n")
        f.write(f"# 共 {len(grouped)} 种，{len(hits)} 次\n")
        f.write("#\n")
        f.write("# 这些控制码不在 processor.py 的名单中，\n")
        f.write("# 可能被模型误翻或丢失。请手工确认是否要加入名单。\n")
        f.write("=" * 70 + "\n\n")

        for token, items in sorted(grouped.items(),
                                   key=lambda x: (-len(x[1]), x[0])):
            f.write(f"[{token}]  出现 {len(items)} 次\n")
            for orig, ctx in items[:3]:
                f.write(f"  原文：  {orig[:100]}\n")
                f.write(f"  上下文：{ctx[:100]}\n")
            if len(items) > 3:
                f.write(f"  … 其余 {len(items) - 3} 次省略\n")
            f.write("\n")

    return report_path


# ================================================================
# 命令行：语言 / 文件范围选择
# ================================================================
def _pick_language(prompt, default_key, exclude=None):
    """交互式语言选择。返回选中的语言字符串，或 None 表示取消。"""
    emit(f"\n{prompt}")
    for i, lang in enumerate(LANG_OPTIONS, 1):
        mark = ""
        if lang == default_key:
            mark = "   ← 上次使用"
        if exclude and lang == exclude:
            mark = "   (已被选为另一种语言)"
        emit(f"  {i:>2}. {lang}{mark}")
    emit("   0. 自定义（手动输入）")

    hint = f"[{default_key}]" if default_key else "[回车跳过]"
    raw = input(f"请选择 {hint}: ").strip()

    if not raw:
        return default_key or None
    if raw == "0":
        custom = input("请输入语言名（如 English / 日本語）：").strip()
        return custom or None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(LANG_OPTIONS):
            return LANG_OPTIONS[idx]
    emit("无效输入")
    return None


def _ask_languages():
    """命令行翻译前询问语言方向，返回 False 表示取消。"""
    if not getattr(config, "ASK_LANG_EACH_TIME", True):
        emit(f"\n  翻译方向：{config.SOURCE_LANG} → {config.TARGET_LANG}")
        return True

    src_lang = _pick_language("请选择【源语言】：", config.SOURCE_LANG)
    if not src_lang:
        emit("已取消")
        return False

    tgt_lang = _pick_language("请选择【目标语言】：",
                              config.TARGET_LANG, exclude=src_lang)
    if not tgt_lang:
        emit("已取消")
        return False

    if src_lang == tgt_lang:
        emit(f"\n⚠ 源语言和目标语言相同（{src_lang}）")
        if input("继续？(y/N): ").strip().lower() != "y":
            return False

    settings.set_value("SOURCE_LANG", src_lang)
    settings.set_value("TARGET_LANG", tgt_lang)
    log.info("翻译方向：%s → %s", src_lang, tgt_lang)
    emit(f"\n  翻译方向：{src_lang} → {tgt_lang}")
    return True


def _select_scope_interactive(title="选择要处理的文件"):
    """
    命令行：单个文件 / 整个文件夹。
    返回路径列表，或 None 表示取消。
    """
    import filepicker

    emit("")
    emit(f"[{title}]")
    emit("  1. 单个文件")
    emit("  2. 整个文件夹（其中的 .txt）")
    raw = input("请选择 [1]: ").strip() or "1"

    default_dir = config.Runtime.last_dir or config.BASE_DIR

    if raw == "2":
        folder = filepicker.pick_dir(
            initial_dir=default_dir,
            title="选择包含 .txt 的文件夹",
        )
        if not folder:
            emit("已取消")
            return None
        files = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".txt")
            and not f.lower().endswith(("_translated.txt",))
        )
        if not files:
            emit(f"文件夹里没有 .txt 文件：{folder}")
            return None
        config.Runtime.set_dir(folder)
        emit(f"\n文件夹：{folder}")
        emit(f"共 {len(files)} 个 .txt 文件：")
        for f in files:
            emit(f"  - {os.path.basename(f)}")
        if input("\n开始处理？(Y/n): ").strip().lower() == "n":
            return None
        return files

    path = filepicker.pick_text_file(
        initial_dir=default_dir,
        title=title,
    )
    if not path:
        emit("已取消")
        return None
    return [path]


def _apply_lang_model(src_lang=None, tgt_lang=None, model=None):
    """把 GUI/命令行选定的语言与模型写进配置（当前会话立即生效）。"""
    if src_lang:
        settings.set_value("SOURCE_LANG", src_lang)
    if tgt_lang:
        settings.set_value("TARGET_LANG", tgt_lang)
    if model:
        # 模型名存到当前服务提供商自己的键
        try:
            import providers as PV
            key = PV.model_config_key(PV.current())
        except Exception:
            key = ("API_MODEL"
                   if str(getattr(config, "TRANSLATE_MODE", "ollama")).lower()
                   == "api" else "MODEL")
        settings.set_value(key, model)
    return True


# ================================================================
# 分批策略：自适应（按上下文预算切批）
# ================================================================
def _make_batches(todo, batch_size=None, max_chars=None, max_tokens=None,
                  budget=None, sys_tokens=0,
                  terms_provider=None,
                  ref_provider=None, body_provider=None):
    """
    自适应分批：单批占用不超过上下文预算就继续加条，超了就切批。

    占用 = system + 术语块 + 正文 + 参考原文块 + 预留输出
    预算 = 上下文窗口 × CTX_BUDGET_RATIO

    两阶段：① 用 system + 正文 + 预留输出粗切出候选批；
            ② 补算术语块 / 参考原文块，超预算从尾部逐条剔除并重算。

    sys_tokens    system 提示词的 token 数
    terms_provider  callable(batch_texts) -> [(原文, 译文), ...]
    ref_provider    callable(batch_texts) -> bool；参考原文块开关
    body_provider   callable(txt) -> 进正文的字符串
    max_chars / max_tokens 已废弃，仅为兼容旧签名保留，不参与切批
    """
    batch_size = batch_size or config.BATCH_SIZE
    if budget is None:
        budget = T.resolve_ctx_budget()
    terms_provider = terms_provider or (lambda b: None)
    ref_provider = ref_provider or (lambda b: False)
    body_provider = body_provider or (lambda t: t)

    # 每条先算一次正文 token 与预留输出 token，两阶段复用
    per = [(txt, T.estimate_tokens(body_provider(txt))) for txt in todo]

    batches = []
    i = 0
    n = len(per)
    while i < n:
        # ---------- ① 粗切：system + 正文 + 预留输出 ----------
        j = i
        cost = sys_tokens
        while j < n and (j - i) < batch_size:
            t = per[j][1] + T.estimate_output_tokens(per[j][1])
            if cost + t > budget and j > i:
                break
            cost += t
            j += 1
        # 单条自身超预算：单独成批
        if j == i:
            log.warning("单条文本超出上下文预算（%d > %d token），单独成批，"
                        "可能被截断：%s",
                        per[i][1] + T.estimate_output_tokens(per[i][1])
                        + sys_tokens, budget, (per[i][0] or "")[:60])
            batches.append([per[i][0]])
            log.info("[批 %d] %d 条  占用 %d/%d  (%.0f%%)  ← 超预算单条",
                     len(batches), 1,
                     per[i][1] + T.estimate_output_tokens(per[i][1])
                     + sys_tokens, budget,
                     100.0 * (per[i][1] + T.estimate_output_tokens(per[i][1])
                              + sys_tokens) / budget)
            i += 1
            continue

        cand = [t for t, _ in per[i:j]]

        # ---------- ② 补算术语块与参考块，超预算从尾部剔除 ----------
        base = sys_tokens

        def _total(keep):
            """保留前 keep 条时的全部占用。"""
            sub = [t for t, _ in per[i:i + keep]]
            body = sum(per[i + m][1] for m in range(keep))
            out = sum(T.estimate_output_tokens(per[i + m][1])
                      for m in range(keep))
            # 参考原文块也占输入 token
            ref = sum(T.estimate_tokens(t) for t in sub) if ref_provider(sub) \
                else 0
            pairs = terms_provider(sub)
            term = _tokens_of(
                T.build_terms_block_string(pairs) if pairs else "")
            return base + body + ref + out + term

        keep = len(cand)
        total = _total(keep)
        while keep > 1 and total > budget:
            keep -= 1                  # 减一条重算，直到低于预算
            total = _total(keep)
        if total > budget:
            # 单条也超预算：照发并点名
            log.warning("第 %d 条连同术语块就撑满预算（%d > %d），"
                        "单独成批", i + 1, total, budget)

        batches.append([t for t, _ in per[i:i + keep]])
        log.info("[批 %d] %d 条  占用 %d/%d  (%.0f%%)",
                 len(batches), keep, total, budget,
                 100.0 * total / budget)
        i += keep
    return batches


def _tokens_of(text):
    """估算 token 数；空串返回 0。"""
    return T.estimate_tokens(text) if text else 0

# ================================================================
# 内部：翻译一批
# ================================================================
def _translate_batch(client, batch_texts, cache,
                     unknown_ctrl_hits, failed, extra_hits,
                     mode_of_entry=None, bi=1, conflict_records=None,
                     term_stats=None, section=None,
                     batch_term_hook=None, miss_log=None):
    """
    翻译一批文本，写入缓存。返回成功条数。

    term_stats: 可选 list —— 本批的 {术语: 命中句数} 会 append 进去
              （list.append 原子，可在多批并发时安全汇总）
    section: 可选，当前文件的 section 名（cat_prompts.section_for 判定）——
              两个用途：① 同原文多译文按它定向投送（有 section 只投该
              section 的译文；无 section 把全部变体用 " / " 并列投送，
              见 processor.term_dst_variants）；② 透传给 translator，
              有 prompts/categories/<SECTION>.txt 时把它追加到 system 末尾。
    batch_term_hook: 可选 callable(pairs) -> int。本批**全部条目写进缓存之后**
              调用，pairs = [(原文, 该批最终译文), ...]。只有术语提取页
              流程会传它（见 term_extract.make_batch_term_hook）；hook 抛
              异常只记警告，绝不影响翻译结果。
    miss_log: 可选 list。传了就**不逐条打日志**，而是把「缺失 / 回显」的
              原文 append 进去，由调用方 _translate_core 汇总成一条日志
              （几千条缺失时逐条打印会把运行日志刷爆）。
              不传（None）时保持旧行为：每批一条 warning。
    """
    if not batch_texts:
        return 0

    import prefix_dict as PFD

    batch, breaks_dict = [], {}
    hit_terms_all = {}
    prefix_list = {}
    new_prefixes = 0
    new_prefix_keys = []
    term_counts = {}            # 本批术语命中句数（交给 term_stats 汇总）

    log.info("[批 %d] 开始  %d 条", bi, len(batch_texts))

    for k, txt in enumerate(batch_texts):
        # 前缀提取
        # ★ 并发批翻译时 register_prefix / save 会同时读写
        #   prefix_dict.json，用模块级锁串起来
        if getattr(config, "PREFIX_DICT_ENABLE", True):
            with _PREFIX_LOCK:
                prefix, body = PR.split_prefix(txt)
                prefix_list[k] = prefix
                if prefix and PFD.register_prefix(prefix):
                    new_prefixes += 1
                    new_prefix_keys.append(prefix)
        else:
            prefix_list[k] = ""
            body = txt

        # ★ 译前替换（归一化游戏里的特殊写法，默认关）
        body, n_pre = REPL.apply_pre(body)
        if n_pre:
            log.debug("[批 %d][%d] 译前替换命中 %d 条规则", bi, k, n_pre)

        # ★ 不做占位符脱敏：控制码 / 标签原样随正文交给模型，
        #   翻完由「控制码检测」兜底 —— repair_missing_controls 按原文
        #   把整个丢失的控制码补回，检查报告再列出符号不匹配的句。
        #   ★ 换行符 \n 是例外（v1.7.4 起）：它已不算控制码，且**送模型前
        #     必须从正文里剔除** —— 让模型把注意力放在文字上，不必猜哪里
        #     该断行；译文里的换行由 apply_breaks 按原文断点补回。
        #   ★ 顺序要紧：breaks 必须在**未剔除**的原文上分析，否则断点全丢。
        breaks = PR.analyze_breaks(body)
        safe = PR.strip_newlines(body)
        hit_terms = PR.find_terms(safe)
        batch.append((k, safe))
        breaks_dict[k] = breaks

        log.debug("[批 %d][%d] 送模型=%r", bi, k, safe)

        for src_term, dst_term in hit_terms:
            hit_terms_all.setdefault(src_term, dst_term)
            # 术语命中统计：按「句」计（一句里重复出现只算一次）
            term_counts[src_term] = term_counts.get(src_term, 0) + 1
        # ★ 控制码检测（源侧）：原文里出现「识别不出来的 \字母 命令」，
        #   说明它可能被模型改坏，收进「未识别控制码」报告提醒用户
        for token, ctx in PR.detect_unknown_ctrl(body):
            unknown_ctrl_hits.append((token, txt, ctx))

    if term_stats is not None and term_counts:
        term_stats.append(term_counts)     # list.append 原子，可并发汇总

    if new_prefixes:
        with _PREFIX_LOCK:
            PFD.save()
            filled = sum(1 for p in new_prefix_keys if PFD.get_translation(p))
        msg = (f"  [前缀] 发现 {new_prefixes} 个新前缀，已加入 prefix_dict.json")
        if filled:
            msg += f"（其中 {filled} 个命中术语，已自动填入译文）"
        emit(msg)
        log.info("[批 %d] 新增前缀 %d 个（术语自动填入 %d 个）",
                 bi, new_prefixes, filled)

    # ★ 多译文投送：每个 src 只出一行，dst 按 section 定向展开成
    #   一个字符串（单译文逐字不变；多译文 " / " 连接并带场景标签，
    #   见 processor.render_term_dst）。term_counts 按句计的语义不变。
    term_pairs_list = [(src, PR.render_term_dst(src, section=section))
                       for src in hit_terms_all]
    if term_pairs_list:
        log.info("[批 %d] 命中术语 %d 条，随 prompt 发送",
                 bi, len(term_pairs_list))

    # ---------- 请求模型 ----------
    t_req = time.time()
    result = translate_with_retry(client, batch,
                                  term_pairs=term_pairs_list,
                                  section=section)
    log.info("[批 %d] 模型返回 %d 条，耗时 %.1fs",
             bi, len(result), time.time() - t_req)

    # 缺失 / 回显：不重试，保留原文并进检查报告
    echo_check = getattr(config, "TREAT_ECHO_AS_FAIL", True)
    missing = []
    for k, safe in batch:
        v = result.get(k)
        if not v or not v.strip():
            missing.append((k, safe))
        elif echo_check and v.strip() == safe.strip():
            # 模型原样回显，多半没翻
            missing.append((k, safe))
    if missing:
        if miss_log is not None:
            # ★ 记**原文**（batch_texts[k]），不是送模型的 safe：
            #   后面要按原文去缓存里重翻，safe 已经剥掉了前缀/换行。
            miss_log.extend(batch_texts[k] for k, _s in missing)
        else:
            log.warning("[批 %d] 缺失/回显 %d 条，保留原文（不重试）",
                        bi, len(missing))
    for k, safe in missing:
        result.pop(k, None)

    # ---------- 写入缓存 ----------
    ok = 0
    for k, src in enumerate(batch_texts):
        raw = result.get(k)
        if not raw:
            # ★ 传了 miss_log 就只汇总、不逐条打；否则按老行为逐条 warning。
            if miss_log is None:
                log.warning("[批 %d][%d] 无返回：保留原文", bi, k)
            failed.append({'src': src, 'reason': '模型无返回'})
            cache.put(src, src)
            continue

        prefix = prefix_list.get(k, "")
        src_body = (src[len(prefix):]
                    if (prefix and src.startswith(prefix)) else src)

        # ★ 译后「安全恢复层」：反斜杠连写长度、圆圈数字、成对标点
        #   —— 能证明安全的才修，修不了的留给下面的控制码检测。
        raw, restore_notes = RESTORE.safe_restore(raw, src_body)
        for note in restore_notes:
            log.info("[批 %d][%d] 安全恢复：%s", bi, k, note)

        # ★ 译文里控制码是否齐全：由下面的 repair_missing_controls 按原文
        #   补回，并由检查报告的「符号不匹配 / 译文残留控制码」兜底。

        # 还原 + 拼回前缀
        mode = "newline"
        if mode_of_entry:
            mode = mode_of_entry.get(src, "newline")

        body_final = PR.finalize(raw, [], breaks_dict.get(k), mode=mode)

        # ★ 控制码回退：译文里缺失/未原样保留的控制码，一律按原文补回
        #   前缀是交给前缀字典单独处理的（可能已被用户或术语改写成另一套控制码），
        #   所以校验时把前缀从原文侧剔除，只比真正参与翻译的正文部分：
        #     · 避免把字典已处理的前缀误判成"译文缺失控制码"（否则会谎报并回退原文）
        #     · 正文里真正丢失的控制码照样会被检测并补回
        #   （prefix / src_body 已在校验前算好，见上面的安全恢复段）

        if prefix:
            # ★ 模型有时会把前缀原样回显；旧版缓存里也可能已经带过前缀。
            #   先剥掉再拼当前前缀，否则会出现 `\tg[新]\tg[旧]正文`。
            body_final = PFD.strip_prefix_echo(body_final, prefix, src_body)
            final = PFD.apply_prefix(prefix) + body_final
        else:
            final = body_final

        if getattr(config, "REPAIR_MISSING_CONTROLS", False):
            final, fixed_ctrl = PR.repair_missing_controls(src_body, final)
            if fixed_ctrl:
                log.warning("[批 %d][%d] 译文缺失控制码 %s，已按原文补回",
                            bi, k, fixed_ctrl)
                extra_hits.append({
                    'src': src,
                    'kind': '控制码回退',
                    'dst': final,
                    'detail': f'译文缺失控制码 {fixed_ctrl}，已按原文原样补回',
                })
        else:
            # 不补回：把缺失清单原样上报，由检查报告兜底
            # （借 repair_missing_controls 的检测逻辑，但丢弃补回后的译文）
            _final, _fixed = PR.repair_missing_controls(src_body, final)
            if _fixed:
                log.warning("[批 %d][%d] 译文缺失控制码 %s，不补回，进检查报告",
                            bi, k, _fixed)
                extra_hits.append({
                    'src': src,
                    'kind': '控制码回退',
                    'dst': final,
                    'detail': f'译文缺失控制码 {_fixed}，未补回（REPAIR_MISSING_CONTROLS=False）',
                })

        # ★ 译后替换（统一译文排版，默认开；发生在还原占位符之后）
        final, n_post = REPL.apply_post(final)
        if n_post:
            log.debug("[批 %d][%d] 译后替换命中 %d 条规则", bi, k, n_post)

        log.debug("[批 %d][%d] 最终译文=%r", bi, k, final)
        # ★ 写缓存前清洗真实换行（cache.put 内完成）；发生过清洗就上报，
        #   由检查报告兜底供人工核对（防止压行破坏了排版/语气）。
        if cache.put(src, final):
            log.warning("[批 %d][%d] 译文含真实换行，已压成空格后写入缓存", bi, k)
            extra_hits.append({
                'src': src,
                'kind': '译文含真实换行',
                'dst': cache.get(src),
                'detail': '模型输出含真实换行，已自动压成空格写入缓存（防止译文文件行数错位）',
            })
        ok += 1

    # ★ 本批全部写进缓存之后：交给 hook（术语提取页用它把本批术语立刻并进
    #   术语表，后续批次立刻用上）。hook 抛异常只记警告，绝不中断翻译。
    if batch_term_hook is not None:
        try:
            batch_term_hook([(t, cache.get(t)) for t in batch_texts
                             if cache.get(t)])
        except Exception as e:
            log.warning("[批 %d] 逐批术语并入失败（忽略）：%s", bi, e)

    return ok



# ================================================================
# 内部：翻译单个文件（核心流程）
# ================================================================
def _file_section(src_path):
    """
    判定文件所属 section（term_sections.json 分派表的 key），失败返回 None。

    ★ 权威入口是 cat_prompts.section_for：区块标志优先（`[数字]` 走
      intl_text.SECTION_NAMES，`[MapNNN]` 判 EVENT_TEXTS），文件名兜底，
      覆盖全部 31 类文本；这里 try/except 全包，任何异常（import 环 /
      文件读不了 / 都对不上）都退回 None，绝不让主流程挂掉。
    ★ 判定结果同时用于两处：术语定向投送（processor 的 section 参数）
      与类别提示词装配（translator 的 section 参数）。
    """
    try:
        import cat_prompts as CP
        return CP.section_for(src_path)
    except Exception as e:
        log.debug("文件 section 判定失败（按无 section 处理）：%s", e)
    return None


def _translate_core(src_path, lines=None, newline=None, show_header=True,
                    batch_term_hook=None, recover=True):
    """对单个文件执行完整翻译流程（Runtime 已设置好 input/output/cache）。

    batch_term_hook: 可选 callable(pairs) -> int，逐批术语回调；
        默认 None（translate_paths / 术语重翻 / 润色等一律不传，行为不变）。
        只有术语提取页流程会传它，见 term_extract.run_extract。
    recover: 内部用。缺失/回显超过阈值时的整批重翻会再调本函数，那一层
        必须传 False，否则「缺失 > 阈值 → 重翻 → 又缺失 > 阈值」会无限递归。

    ★ 「每个文件翻完立刻刷新报告 + 重翻」不在这里做，而在调用方
      （translate_paths / term_extract.run_extract）调 _auto_check_file：
      本函数会被重翻流程递归调用，放在这里会自我触发。
    """
    # ★ 文本保护规则：按需装载（模式或规则文件改过才重新装载）
    import text_rules
    text_rules.ensure_applied()
    out_path = config.Runtime.output_file
    cache_path = config.Runtime.cache_file

    # ★ 本文件的 section（名字类文件才有，如 MOVE_NAMES）：
    #   整句术语直译与多译文投送都按它定向
    sec = _file_section(src_path)
    if sec:
        log.info("文件 section：%s", sec)

    if show_header:
        emit(f"\n{'=' * 55}")
        emit(f"  翻译：{src_path}")
        emit(f"  输出：{out_path}")
        emit(f"{'=' * 55}")

    PR.load_terms()

    if lines is None:
        lines, newline = P.read_file(src_path, config.INPUT_ENCODING)
    newline = newline or "\n"

    entries, special = P.extract_entries(lines)

    line_modes = P.get_block_modes(lines)
    mode_of_entry = {}
    for ln, src_text in entries:
        if src_text not in mode_of_entry and 0 <= ln < len(line_modes):
            mode_of_entry[src_text] = line_modes[ln]

    log.info("文件 %d 行  待翻 %d  特殊 %d",
             len(lines), len(entries), len(special))
    emit(f"[解析] 总行数 {len(lines)}  待翻 {len(entries)}  特殊 {len(special)}")

    if not entries:
        emit("没有可翻译的内容")
        return {"entries": 0, "todo": 0, "done": 0, "failed": 0}

    cache = Cache(cache_path)

    seen, todo = set(), []
    skipped_pure = 0
    skipped_path = 0
    skipped_prefilter = 0
    skipped_hash_ph = 0        # ★ 整句只有 #{...}（如 #{count}）：原样写缓存
    skipped_letter = 0         # ★ 单个字母（如 A / ñ）：原文即译文，不送模型
    whole_hits = []           # ★ 整句命中手工术语：直接写缓存，不送模型
    for _, txt in entries:
        if txt in seen:
            continue
        seen.add(txt)
        if txt in cache:
            continue
        # ★ 整句只由 #{...} 占位符组成（如 "#{count}"）：这是游戏填值的模板，
        #   翻了反而破坏占位符 → 原文即译文，直接写缓存，不送模型。
        #   ★ 放在「纯控制符」之前：这类句子剥掉 #{} 后没内容，会被当成
        #     纯控制符，但用户明确要求按「#{...} 整句」这条规则处理。
        if PR.is_hash_placeholder_only(txt):
            cache.put(txt, txt)
            skipped_hash_ph += 1
            continue
        # ★ 整句术语直译：整句就是一条手工维护的术语（只忽略首尾标点）→
        #   把术语译文当作这句的译文写进缓存，不再送模型。
        #   ★ 放在「纯控制符 / 资源路径」之前：像 "(?)" 这种整句都是符号、
        #     但用户明确给了术语译文的句子，要按术语翻，而不是原样保留。
        if getattr(config, "WHOLE_TERM_MATCH", True):
            # ★ 按 section 定向：名字类文件优先用自己 section 的译文
            hit = PR.match_whole_term(txt, section=sec)
            if hit:
                cache.put(txt, hit[1])
                whole_hits.append((txt, hit[0], hit[1]))
                continue
        # ★ 整句只有一个字母（单个英文字母 / 单个西班牙文字母）：
        #   游戏里多是按键提示 / 图标代号，翻了没意义，
        #   直接原文写缓存不送模型。
        #   ★ 放在「纯控制符」之前：单字母本来也会被纯控制符规则捡掉，
        #     但那条规则可以关掉，而且两条规则的理由不同，所以单独计一条。
        if getattr(config, "SKIP_SINGLE_LETTER", True) and PR.is_single_letter(txt):
            cache.put(txt, txt)
            skipped_letter += 1
            continue
        if getattr(config, "SKIP_PURE_CONTROL", True) and PR.is_pure_control(txt):
            cache.put(txt, txt)
            skipped_pure += 1
            continue
        # ★ 资源路径（Graphics/Pictures/xxx）不翻译，原样保留
        if getattr(config, "SKIP_PATH_LINES", True) and PR.is_path_like(txt):
            cache.put(txt, txt)
            skipped_path += 1
            continue
        # ★ 预过滤（借鉴 LinguaGacha prefilter）：剥掉控制码/标签后
        #   **不含源语言字符**的行（纯数字串、纯符号行、别国语言残留）
        #   原文即译文，不送模型——省 token，也省报告噪音
        if getattr(config, "PREFILTER_ENABLE", True) \
                and not PR.has_translatable_text(txt):
            cache.put(txt, txt)
            skipped_prefilter += 1
            continue
        todo.append(txt)

    if whole_hits:
        cache.save()
        log.info("整句术语直译 %d 条（已写入缓存，不送模型）", len(whole_hits))
        for src, term, dst in whole_hits:
            log.debug("[整句术语] %r → %r（命中术语 %r）", src, dst, term)
        emit(f"[整句术语] {len(whole_hits)} 条整句命中手工术语，"
             f"已直接用术语译文写入缓存（不送模型）")
        for src, term, dst in whole_hits[:5]:
            emit(f"    {src[:40]}  →  {dst[:40]}   （术语 {term}）")
        if len(whole_hits) > 5:
            emit(f"    … 其余 {len(whole_hits) - 5} 条见日志")

    if skipped_pure:
        cache.save()
        log.info("跳过纯控制符句子 %d 条（已缓存原文）", skipped_pure)
        emit(f"[过滤] 跳过 {skipped_pure} 条纯控制符句子（不送模型）")

    if skipped_path:
        cache.save()
        log.info("跳过资源路径句子 %d 条（已缓存原文）", skipped_path)
        emit(f"[过滤] 跳过 {skipped_path} 条资源路径（形如 A/B/C，不翻译）")

    if skipped_letter:
        cache.save()
        log.info("跳过单个字母句子 %d 条（已缓存原文）", skipped_letter)
        emit(f"[过滤] 跳过 {skipped_letter} 条单个字母句子"
             f"（如 A / ñ，原文即译文，不送模型）")

    if skipped_prefilter:
        cache.save()
        log.info("预过滤跳过无可译文本 %d 条（已缓存原文）", skipped_prefilter)
        emit(f"[过滤] 预过滤跳过 {skipped_prefilter} 条"
             f"（纯数字/纯符号/非源语言残留，原文即译文）")

    if skipped_hash_ph:
        cache.save()
        log.info("整句 #{} 占位符 %d 条（已缓存原文，不翻译）", skipped_hash_ph)
        emit(f"[过滤] 整句 #{{}} 占位符 {skipped_hash_ph} 条"
             f"（如 #{{count}}，原文即译文，不送模型）")

    n_cache = (len(seen) - len(todo) - skipped_pure - skipped_path
               - skipped_prefilter - len(whole_hits) - skipped_hash_ph
               - skipped_letter)
    emit(f"[待翻] 唯一 {len(seen)}  需翻 {len(todo)}  缓存命中 {n_cache}")

    # ---------- 批量翻译 ----------
    unknown_ctrl_hits = []
    failed = []
    extra_hits = []
    conflict_records = []      # ★ 术语冲突：落盘后供检查报告 / 冲突面板复用
    term_stat_batches = []      # 每批一条 {术语: 命中句数}，跑完汇总落盘
    miss_log = []              # ★ 缺失 / 回显的原文（不逐条刷日志，跑完汇总）

    if todo:
        # 按原文顺序翻译

        client = OllamaClient()
        done = 0
        t0 = time.time()
        total = len(todo)

        # ---------- 自适应分批 ----------
        # 切批时要算术语块，这里复现送模型前的处理口径
        def _terms_for(batch_texts):
            pairs = {}
            for txt in batch_texts:
                prefix, body = (PR.split_prefix(txt)
                                if getattr(config, "PREFIX_DICT_ENABLE", True)
                                else ("", txt))
                body, _n = REPL.apply_pre(body)
                for src, dst in PR.find_terms(PR.strip_newlines(body)):
                    pairs.setdefault(src, dst)
            return [(s, PR.render_term_dst(s, section=sec))
                    for s in pairs]

        sys_tokens = _tokens_of(client._system_prompt(sec))
        budget = T.resolve_ctx_budget()
        ctx_limit = T.resolve_ctx_limit()
        emit(f"[分批] 自适应：预算 {budget}/{ctx_limit} token"
             f"（窗口×{getattr(config, 'CTX_BUDGET_RATIO', 0.9)}）")
        batches = _make_batches(
            todo, budget=budget, sys_tokens=sys_tokens,
            terms_provider=_terms_for)
        emit(f"[分批] 共 {len(batches)} 批（{total} 条）")

        # ★ 并发批翻译：resolve_concurrency() > 1 且批数 > 1 时开线程池。
        #   调度（并发槽 / Key 轮换 / 429 降档）由 translator.ApiScheduler
        #   负责，这里只管把批次丢进池子；cache / prefix_dict / auto_terms
        #   的写路径都已加锁。
        try:
            conc = max(1, int(resolve_concurrency()))
        except Exception:
            conc = 1

        if conc > 1 and len(batches) > 1:
            if getattr(config, "AUTO_CONCURRENCY", True):
                emit(f"[并发] 并发批数 {conc}（自适应：成功+1 / 429 减半）")
            else:
                emit(f"[并发] 并发批数 {conc}")
            log.info("并发批翻译：%d 批，并发 %d", len(batches), conc)

            def _run(bi, batch_texts):
                return _translate_batch(
                    client, batch_texts, cache,
                    unknown_ctrl_hits, failed, extra_hits,
                    mode_of_entry=mode_of_entry, bi=bi,
                    conflict_records=conflict_records,
                    term_stats=term_stat_batches, section=sec,
                    batch_term_hook=batch_term_hook, miss_log=miss_log)

            with ThreadPoolExecutor(max_workers=conc) as ex:
                futs = {}
                for bi, batch_texts in enumerate(batches, 1):
                    if bridge.cancelled():
                        emit("\n[中断] 用户取消（已提交的批次会跑完）")
                        cache.save(force=True)
                        break
                    futs[ex.submit(_run, bi, batch_texts)] = bi
                for fut in as_completed(futs):
                    bi = futs[fut]
                    try:
                        ok = fut.result()
                    except Exception as e:
                        log.error("[批 %d] 执行失败：%s", bi, e)
                        ok = 0
                    cache.tick()
                    done += len(batches[bi - 1])
                    elapsed = time.time() - t0
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (total - done) / rate / 60 if rate > 0 else 0
                    log.info("[批 %d] 成功 %d/%d  累计 %d/%d  "
                             "%.2f条/秒  ETA %.1f分",
                             bi, ok, len(batches[bi - 1]), done, total,
                             rate, eta)
                    bridge.progress(done, total, f"{done}/{total} 条")
        else:
            for bi, batch_texts in enumerate(batches, 1):
                if bridge.cancelled():
                    emit("\n[中断] 用户取消")
                    cache.save(force=True)
                    break

                ok = _translate_batch(client, batch_texts, cache,
                                      unknown_ctrl_hits, failed, extra_hits,
                                      mode_of_entry=mode_of_entry,
                                      bi=bi,
                                      conflict_records=conflict_records,
                                      term_stats=term_stat_batches,
                                      section=sec,
                                      batch_term_hook=batch_term_hook,
                                      miss_log=miss_log)

                cache.tick()
                done += len(batch_texts)
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate / 60 if rate > 0 else 0
                log.info("[批 %d] 成功 %d/%d  累计 %d/%d  %.2f条/秒  ETA %.1f分",
                         bi, ok, len(batch_texts), done, total, rate, eta)
                bridge.progress(done, total, f"{done}/{total} 条")

        # 用量小结
        line = client.usage_line()
        if line:
            log.info(line)
            emit(line)

        # ★ 跑完把 HTTP 连接池关掉：长跑翻译时别让长连接一直堆着
        client.close()
        cache.save(force=True)

        if failed:
            log.warning("失败 %d 条", len(failed))
            emit(f"\n[失败] {len(failed)} 条未翻译：")
            for t in failed[:10]:
                emit(f"    {t['src'][:70]}   （{t['reason']}）")
            if len(failed) > 10:
                emit(f"    … 其余 {len(failed) - 10} 条省略")
    else:
        cache.save(force=True)

    # ---------- 缺失 / 回显：只汇总一条，超阈值整批重翻 ----------
    # ★ 用户要求：不逐条刷屏，只显示「缺失/回显 X 条」；X > 阈值（默认 10）
    #   时把这些句子一起重翻一次（recover=False 防止无限套娃）。
    miss_uniq = []
    _seen_miss = set()
    for s in miss_log:
        if s and s not in _seen_miss:
            _seen_miss.add(s)
            miss_uniq.append(s)
    if miss_uniq:
        emit(f"\n[缺失/回显] {len(miss_uniq)} 条（保留原文，已进检查报告）")
        log.warning("缺失/回显 %d 条（保留原文，不重试单条）", len(miss_uniq))
        limit = int(getattr(config, "ECHO_RETRANSLATE_OVER", 10) or 0)
        if recover and limit > 0 and len(miss_uniq) > limit:
            emit(f"  {len(miss_uniq)} 条 > {limit} 条，开始一起重翻…")
            log.warning("缺失/回显 %d 条超过阈值 %d，整批重翻一次",
                        len(miss_uniq), limit)
            try:
                cache = Cache(cache_path)
                removed = cache.remove_many(_seen_miss)
                cache.save(force=True)
                emit(f"  ✔ 已删除 {removed} 条缓存，重新翻译")
                _translate_core(src_path, lines if lines is not None else None,
                                newline, show_header=False,
                                batch_term_hook=batch_term_hook,
                                recover=False)
            except Exception as e:
                log.error("缺失/回显整批重翻失败：%s", e)
                emit(f"  ⚠ 缺失/回显整批重翻失败：{e}")
            # ★ 重翻走的是另一个 Cache 实例，本函数手里的 cache 已经过期：
            #   它的内存里这些 key 还是「保留原文」的旧值，后面的回写会拿它
            #   盖掉刚重翻好的译文。必须从磁盘重新读一遍再回写。
            cache = Cache(cache_path)

    # ---------- 术语命中统计落盘（aux 目录） ----------
    if getattr(config, "TERM_STATS_ENABLE", True) and term_stat_batches:
        try:
            _write_term_stats(src_path, term_stat_batches)
        except Exception as e:
            log.warning("术语命中统计写入失败：%s", e)

    # ---------- 术语冲突记录落盘（供检查报告 / 冲突面板复用） ----------
    if conflict_records:
        _record_term_conflicts(conflict_records)
        emit(f"  [术语冲突] 记录 {len(conflict_records)} 条，"
             f"可在菜单 3 用「解决术语冲突」处理")

    # ---------- 回写 ----------
    translations = {txt: cache.get(txt) for _, txt in entries if cache.get(txt)}
    replaced = P.write_output(
        lines, entries, translations,
        out_path, newline, config.OUTPUT_ENCODING,
    )
    log.info("回写：%d/%d → %s", replaced, len(entries), out_path)
    emit(f"\n✔ 输出：{out_path}")
    emit(f"  替换 {replaced}/{len(entries)} 条")

    # ---------- 自动检查 ----------
    emit("\n[检查] 生成检查报告…")
    try:
        out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
        report_path = _report_path()
        # ★ 行数哨兵：译文文件物理行数必须与原文一致（parser.write_output
        #   按行 join）。行数对不上 = 有译文混进了真实换行，从出错处往后
        #   整份报告的行号全部错位（上一对的译文配到下一对上）——
        #   此时逐行检查只会产出「牛头不对马嘴」的假配对，直接拒绝出报告。
        if len(out_lines) != len(lines):
            warn = (f"行数不一致（原文 {len(lines)} / 译文 {len(out_lines)}），"
                    f"检查报告已跳过——译文可能混入真实换行，请重新翻译该文件")
            emit(f"⚠ {warn}")
            log.warning(warn)
            return
        hits = checker.check(out_lines, entries, special, report_path,
                             extra_hits=(failed + extra_hits))
        _print_summary(hits, report_path)
    except Exception as e:
        log.error("自动检查失败：%s", e)
        emit(f"  自动检查失败（不影响翻译结果）：{e}")

    # ---------- 未识别控制码报告 ----------
    if unknown_ctrl_hits:
        try:
            uc_path = _unknown_ctrl_report_path()
            _write_unknown_ctrl_report(unknown_ctrl_hits, uc_path)
            kinds = Counter(t for t, _, _ in unknown_ctrl_hits)
            emit("\n⚠ 检测到未识别控制码：")
            for tok, n in kinds.most_common(10):
                emit(f"    {tok}  × {n}")
            if len(kinds) > 10:
                emit(f"    … 其余 {len(kinds) - 10} 种省略")
            emit(f"  报告：{uc_path}")
        except Exception as e:
            log.error("写未识别控制码报告失败：%s", e)

    # ---------- 前缀字典统计 ----------
    if getattr(config, "PREFIX_DICT_ENABLE", True):
        try:
            import prefix_dict as PFD
            s = PFD.stats()
            if s["pending"]:
                emit(f"\n[前缀字典] 共 {s['total']} 条，"
                     f"已翻译 {s['done']} 条，待翻译 {s['pending']} 条")
                emit("  请到菜单 5「前缀字典」补全译文后应用")
        except Exception as e:
            log.debug("前缀字典统计失败：%s", e)

    # ---------- 更新术语快照 ----------
    _update_snapshot()

    return {
        "entries": len(entries),
        "todo": len(todo),
        "done": len(todo) - len(failed),
        "failed": len(failed),
        "whole": len(whole_hits),      # ★ 整句命中手工术语、直接写缓存的条数
    }


def _auto_check_file(src_path, term_mode=False):
    """
    单个文件翻完**立刻**做一次检查（等同界面上的「刷新报告」），并把报告里
    的问题句子按类型重翻 config.AUTO_CHECK_ROUNDS 轮（默认 2 轮）。

    term_mode=True  → 术语提取流程：用术语检查报告（term_fix.check_terms），
                      对报告里**所有类型**的问题句子重翻。
    term_mode=False → 正常翻译（菜单 3）：用重翻检查报告（check_file），
                      对报告里**所有类型**（PROBLEM_KINDS）的问题句子重翻。

    ★ 只针对**当前这个文件**：所有 hits 都按 path 过滤到 src_path，
      绝不碰别的文件。
    ★ 全程 try/except：报告刷不出来或重翻失败只记一笔，绝不影响已经
      翻好落盘的结果。
    """
    if not getattr(config, "AUTO_CHECK_AFTER_FILE", True):
        return
    rounds = int(getattr(config, "AUTO_CHECK_ROUNDS", 2) or 0)
    if rounds <= 0:
        return
    if bridge.cancelled():
        return

    src_abs = os.path.abspath(src_path)
    # ★ 正常翻译模式下报告读的是译文文件：文件不存在（本文件没抽出任何条目、
    #   或被行数哨兵拦下）就直接跳过，别刷一条「没有问题句子」的假结论。
    if not term_mode and not os.path.exists(config.Runtime.output_file):
        return
    try:
        if term_mode:
            import term_fix as TFX
            emit(f"\n[自动检查] 术语检查报告（{os.path.basename(src_path)}）…")
            hits = TFX.check_terms(src_path)
            hits = [h for h in hits
                    if os.path.abspath(str(h.get("path") or "")) == src_abs]
            kinds = [k for k in TFX.KIND_ORDER
                     if any(h.get("kind") == k for h in hits)]
        else:
            emit(f"\n[自动检查] 重翻检查报告（{os.path.basename(src_path)}）…")
            hits = check_file(src_path) or []
            # ★「所有类型」= PROBLEM_KINDS（报告里带勾选框、可重翻的全部类型；
            #   目前与 RETRANSLATE_KINDS 同一集合）。需手动类 / 提示类 / 已编辑
            #   本来就不该由模型重翻，重翻也修不好。
            hits = [h for h in hits if h.get("kind") in PROBLEM_KINDS]
            kinds = [k for k in REPORT_KIND_ORDER
                     if k in PROBLEM_KINDS
                     and any(h.get("kind") == k for h in hits)]
    except Exception as e:
        log.error("自动检查失败（%s）：%s", src_path, e)
        emit(f"  ⚠ 自动检查失败（不影响翻译结果）：{e}")
        return

    if not hits:
        emit("  ✔ 没有问题句子，跳过自动重翻")
        return

    emit(f"  问题 {len(hits)} 条，类型：" + "  ".join(
        f"{k}:{sum(1 for h in hits if h.get('kind') == k)}" for k in kinds))
    log.info("自动检查 %s：%d 条问题，类型=%s",
             src_path, len(hits), "、".join(kinds) or "（无）")

    wl_sent = checker.user_sentences()
    # ★ 「所有类型的问题句子各重翻两次」按字面执行：第 1 轮翻首次报告判出的
    #   全部问题句；第 2 轮把这些句子**再翻一遍**（顺带补上第 1 轮之后新冒出
    #   来的），不因为「上一轮看起来修好了」就少翻一次。
    seed = {h.get("src") for h in hits if (h.get("src") or "").strip()}
    for rd in range(1, rounds + 1):
        if bridge.cancelled():
            emit("  [中断] 用户取消，停止自动重翻")
            return
        # 每轮重查一遍报告：拿到当前还剩下的问题（第 2 轮还要并上首轮集合）
        try:
            if term_mode:
                import term_fix as TFX
                cur = [h for h in TFX.check_terms(src_path)
                       if os.path.abspath(str(h.get("path") or "")) == src_abs]
                # ★ 术语报告不做「检查白名单」过滤：白名单是 checker 的句子
                #   规则，与术语报告的判定无关；界面「术语重翻」也只按类型
                #   勾选过滤，不查白名单。
                now = {h.get("src") for h in cur
                       if (h.get("src") or "").strip()}
                wanted = (seed | now) if rd > 1 else now
                items = [{"src": s, "path": src_path} for s in wanted]
                if not items:
                    emit(f"  [第 {rd}/{rounds} 轮] 没有需要重翻的句子，提前结束")
                    break
                emit(f"  [第 {rd}/{rounds} 轮] 术语重翻 {len(items)} 条…")
                # 与界面「术语重翻」按钮同一口径：逐批把新译名并进术语表，
                # 后续批次立刻用上（term_extract 只在函数内 import，无环）。
                import term_extract as TE
                TFX.retranslate(
                    src_path, items,
                    cancel=lambda: bridge.cancelled(),
                    batch_term_hook=TE.make_batch_term_hook(None))
            else:
                cur = [h for h in (check_file(src_path) or [])
                       if h.get("kind") in PROBLEM_KINDS]
                to_re = [h for h in cur
                         if (h.get("src") or "").strip() not in wl_sent]
                now = {h.get("src") for h in to_re if h.get("src")}
                srcs = ((seed | now) - wl_sent) if rd > 1 else now
                if not srcs:
                    emit(f"  [第 {rd}/{rounds} 轮] 没有需要重翻的句子，提前结束")
                    break
                emit(f"  [第 {rd}/{rounds} 轮] 重翻 {len(srcs)} 条…")
                config.Runtime.set_input(src_path)
                cache = Cache(config.Runtime.cache_file)
                n = cache.remove_many(srcs)
                cache.save(force=True)
                emit(f"    已删除 {n} 条缓存")
                rl, rn = P.read_file(src_path, config.INPUT_ENCODING)
                _translate_core(src_path, rl, rn, show_header=False)
        except bridge.CancelRequested:
            raise
        except Exception as e:
            import traceback as _tb
            log.error("自动重翻第 %d 轮失败（%s）：%s\n%s",
                      rd, src_path, e, _tb.format_exc())
            emit(f"  ⚠ 第 {rd} 轮重翻失败：{e}")
            return
    emit("  ✔ 自动检查与重翻完成")


def _update_snapshot():
    try:
        import term_sync as TS
        current_terms = TS.load_current_terms()
        if current_terms:
            TS.save_snapshot(current_terms)
            log.info("术语表快照已更新：%d 条", len(current_terms))
    except Exception as e:
        log.warning("建立术语表快照失败：%s", e)


def _print_summary(hits, report_path):
    c = Counter(h['kind'] for h in hits)
    # ★ 「共 N 处问题」只数 PROBLEM_KINDS：提示类（术语冲突）
    #   与需手动类（译文残留控制码 / 特殊行 / 控制码回退）都不算
    emit(f"  共 {count_problems(hits)} 处问题：")
    shown = 0
    for k in REPORT_KIND_ORDER:
        if k in PROBLEM_KINDS and c.get(k):
            emit(f"    {k}: {c[k]}")
            shown += 1
    if not shown:
        emit("    （无）")
    manual = [f"{k}: {c[k]}" for k in REPORT_KIND_ORDER
              if k in NEVER_RETRANSLATE_KINDS and c.get(k)]
    if manual:
        emit("  需手工处理（不计入问题）：" + "  ".join(manual))
    adv = [f"{k}: {c[k]}" for k in REPORT_KIND_ORDER
           if k in ADVISORY_KINDS and c.get(k)]
    if adv:
        emit("  提示（不计入问题）：" + "  ".join(adv))
    emit(f"  报告：{report_path}")


# ================================================================
# 核心 1：翻译
# ================================================================
def _drop_names_files(paths, action="该操作"):
    """
    把**名字类文件**从待处理清单里剔除（返回 (保留, 跳过)）。

    ★ 名字文件（*_NAMES / 开头 [编号] 是名字区块的那批）归「术语提取」管，
      翻译 / 检查报告 / 重翻 / 润色 / 换行重排都不该碰 —— 否则同一批名词
      会被两条流水线各翻一遍，译法还可能不一致。
    ★ 判定规则与 term_extract.find_names_files 完全一致（resolve_names），
       这里只做「是不是」的判断，不重复实现一套。
    """
    keep, skipped = [], []
    try:
        import term_extract as TE
    except Exception as e:                       # 模块缺失时不阻断主流程
        log.warning("载入 term_extract 失败，跳过名字文件过滤：%s", e)
        return list(paths or []), []

    for p in paths or []:
        if p and os.path.isfile(p) and TE.is_term_source_file(p):
            skipped.append(p)
        elif p:
            keep.append(p)

    if skipped:
        emit(f"[跳过] {action}不处理名字类文本，已跳过 {len(skipped)} 个："
             + "、".join(os.path.basename(p) for p in skipped[:5])
             + (" 等" if len(skipped) > 5 else ""))
        emit("      名字类文件请到「术语提取」里处理。")
    return keep, skipped


def translate_paths(paths, src_lang=None, tgt_lang=None, model=None):
    """
    翻译一组文件（无交互）。返回统计 dict。
    """
    _apply_lang_model(src_lang, tgt_lang, model)
    _announce_work_dir(paths)          # 整个文件夹 → 中间文件另存

    paths, _skipped = _drop_names_files(paths, "翻译")

    log.info("=" * 50)
    log.info("开始翻译  共 %d 个文件  方向 %s → %s",
             len(paths), config.SOURCE_LANG, config.TARGET_LANG)

    total = len(paths)
    if not total:
        emit("没有需要翻译的文件（名字类文本已全部跳过）")
        return {"files": 0, "total": 0}

    processed = 0
    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        config.Runtime.set_input(path)
        bridge.progress(i - 1, total, os.path.basename(path))

        try:
            lines, newline = P.read_file(path, config.INPUT_ENCODING)
        except Exception as e:
            emit(f"[跳过] 读取失败：{e}")
            continue

        if total > 1:
            emit(f"\n[{i}/{total}] {os.path.basename(path)}")

        try:
            _translate_core(path, lines, newline,
                            show_header=(total == 1))
            # ★ 本文件翻完立刻检查本文件（刷新重翻检查报告）+ 按类型重翻
            _auto_check_file(path, term_mode=False)
            processed += 1
        except bridge.CancelRequested:
            emit("\n[中断] 用户取消")
            break

    bridge.progress(total, total, "完成")
    config.Runtime.save()

    if total > 1:
        emit(f"\n{'=' * 55}")
        emit(f"  批量翻译完成，共处理 {processed}/{total} 个文件")
        emit(f"{'=' * 55}")

    return {"files": processed, "total": total}


# ================================================================
# 核心：检查
# ================================================================
def check_file(path, write_report=True):
    """
    对单个文件跑一次检查，返回 hits 列表；文件缺失返回 None。
    """
    config.Runtime.set_input(path)
    inp = config.Runtime.input_file
    out = config.Runtime.output_file

    if not os.path.exists(inp):
        emit(f"缺少输入文件：{inp}")
        return None
    if not os.path.exists(out):
        emit(f"缺少输出文件：{out}（先跑一次翻译）")
        return None

    try:
        src_lines, _ = P.read_file(inp, config.INPUT_ENCODING)
        out_lines, _ = P.read_file(out, config.OUTPUT_ENCODING)
    except Exception as e:
        emit(f"读取失败：{e}")
        return None

    entries, special = P.extract_entries(src_lines)
    report_path = _report_path()
    # ★ 行数哨兵：行数不一致 = 有译文混进真实换行，从此行号全部错位，
    #   逐行检查只会产出「牛头不对马嘴」的假配对——拒绝出报告。
    if len(out_lines) != len(src_lines):
        warn = (f"行数不一致（原文 {len(src_lines)} / 译文 {len(out_lines)}），"
                f"检查报告已跳过——译文可能混入真实换行，请重新翻译该文件")
        emit(f"⚠ {warn}")
        log.warning(warn)
        return []
    hits = checker.check(out_lines, entries, special, report_path,
                         extra_hits=_conflicts_as_hits(entries, out_lines))
    return hits


def _conflicts_as_hits(entries=None, out_lines=None):
    """
    读取落盘的术语冲突记录，转成 checker 能吃的 extra_hits。
    这样菜单 2 单独刷新报告时也能看到（并处理）术语冲突。
    entries/out_lines 用来把冲突关联回具体句子，顺便补上译文。
    """
    data = load_term_conflicts()
    if not data:
        return []

    line_of = {}
    for ln, s in (entries or []):
        k = (s or "").strip()
        if k and k not in line_of:
            line_of[k] = ln

    def _dst_of(sent):
        if not sent:
            return ""
        ln = line_of.get(sent.strip())
        if ln is None or out_lines is None or ln >= len(out_lines):
            return ""
        return out_lines[ln].strip()

    hits = []
    for term, item in data.items():
        if not isinstance(item, dict):
            continue
        if item.get("edited"):
            # ★ 已经在「术语冲突」视图里标记为已编辑的，不再进检查报告
            #   （视图里仍能看到它，排在列表最后）
            continue
        old = item.get("old", "")
        new = item.get("new", "")
        detail = f"术语冲突：{term} 已有 {old}，模型返回 {new}"
        sents = item.get("src") or []
        if not sents:
            sents = [""]
        for s in sents:
            hits.append({
                'src': s, 'kind': '术语冲突', 'dst': _dst_of(s),
                'detail': detail,
                'term_src': term, 'term_old': old, 'term_new': new,
            })
    log.info("载入术语冲突记录 %d 条", len(hits))
    return hits


def check_paths(paths):
    """批量检查，返回 {path: hits}。"""
    paths, _skipped = _drop_names_files(paths, "检查报告")
    _announce_work_dir(paths)
    result = {}
    for i, path in enumerate(paths, 1):
        bridge.progress(i - 1, len(paths), os.path.basename(path))
        hits = check_file(path)
        if hits is not None:
            result[path] = hits
    bridge.progress(len(paths), len(paths), "检查完成")
    return result


# ================================================================
# 核心 2：重翻检查报告内容
# ================================================================
def retranslate_report_paths(paths, src_lang=None, tgt_lang=None, model=None,
                             kinds=None):
    """
    扫描输出文件，找出问题句，删缓存后重翻。

    kinds: 只重翻这些问题类型（None = 用默认的 RETRANSLATE_KINDS）。
           ★「译文残留控制码」等 NEVER_RETRANSLATE_KINDS 里的类型、
             以及手工编辑产生的 MANUAL_KINDS（「已编辑」）都不会参与重翻 ——
             手工改过的句子一旦被重翻就白改了。
    """
    _apply_lang_model(src_lang, tgt_lang, model)

    _announce_work_dir(paths)

    active = set(RETRANSLATE_KINDS) if kinds is None else set(kinds)
    active -= NEVER_RETRANSLATE_KINDS
    active -= MANUAL_KINDS
    active = {k for k in active if k}          # 去掉空类型

    log.info("=" * 50)
    log.info("重翻检查报告内容  共 %d 个文件  类型=%s",
             len(paths), "、".join(sorted(active)) or "（空）")
    emit(f"  重翻类型：{'、'.join(sorted(active)) if active else '（未选择）'}")
    emit(f"  跳过类型：{'、'.join(sorted(NEVER_RETRANSLATE_KINDS | MANUAL_KINDS))}")

    if not active:
        emit("  没有勾选任何可重翻的类型，已取消")
        return {"files": 0, "removed": 0, "skipped": True}

    total_removed = 0
    files_done = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        config.Runtime.set_input(path)
        bridge.progress(i - 1, len(paths), os.path.basename(path))
        emit(f"\n[{i}/{len(paths)}] {os.path.basename(path)}")

        hits = check_file(path)
        if hits is None:
            continue

        if not hits:
            emit("  ✔ 没有发现问题，无需重翻")
            continue

        kinds_cnt = Counter(h['kind'] for h in hits)
        emit("  问题分布：" + "  ".join(f"{k}:{n}"
                                       for k, n in kinds_cnt.items()))

        # ★ 句子白名单：加了白名单的句子不再重翻（用户手动确认过没问题）
        wl_sent = checker.user_sentences()
        picked = [h for h in hits if h['kind'] in active]
        to_re = [h for h in picked
                 if (h.get('src') or '').strip() not in wl_sent]

        wl_hit = len(picked) - len(to_re)
        if wl_hit:
            emit(f"  白名单跳过：{wl_hit} 条")

        if not to_re:
            emit(f"  勾选的类型（{'、'.join(sorted(active))}）里没有可重翻的句子"
                 f"，已跳过")
            continue

        emit(f"  待重翻：{len(to_re)} 条")
        for h in to_re[:8]:
            emit(f"    [{h['kind']}] 行 {h['line_no']}  {h['src'][:60]}")

        cache = Cache(config.Runtime.cache_file)
        before = len(cache)
        removed = cache.remove_many({h['src'] for h in to_re})
        cache.save(force=True)
        total_removed += removed
        emit(f"  ✔ 已删除 {removed} 条缓存（原 {before} 条）")

        lines, newline = P.read_file(path, config.INPUT_ENCODING)
        _translate_core(path, lines, newline, show_header=False)
        files_done += 1

    bridge.progress(len(paths), len(paths), "完成")
    return {"files": files_done, "removed": total_removed}


# ================================================================
# 核心 3：术语更新后重翻
# ================================================================
def analyze_terms():
    """
    对比快照，返回 (current, added, removed, modified, old_keyonly)。
    无快照时返回 (current, None, None, None, False)。
    """
    import term_sync as TS
    current = TS.load_current_terms()
    if not TS.snapshot_exists():
        return current, None, None, None, False
    # ★ 把刚读到的 current 传下去，diff_terms 不再 exec 一遍 term_dict.py
    added, removed, modified, old_keyonly = TS.diff_terms(current=current)
    return current, added, removed, modified, old_keyonly


def retranslate_terms_paths(paths, src_lang=None, tgt_lang=None, model=None,
                            extra_terms=None):
    """
    术语更新后重翻。
    extra_terms: GUI 刚编辑过的术语，会强制纳入「受影响术语」。
    """
    _apply_lang_model(src_lang, tgt_lang, model)

    _announce_work_dir(paths)

    import term_sync as TS

    log.info("=" * 50)
    log.info("术语更新后重翻")

    current = TS.load_current_terms()
    if not current:
        emit("术语表为空或不存在，请先运行菜单 8 生成")
        return {"files": 0, "removed": 0}

    if not TS.snapshot_exists():
        emit("未找到快照，已把当前术语表记录为基准，本次不重翻")
        TS.save_snapshot(current)
        return {"files": 0, "removed": 0, "baseline": True}

    added, removed, modified, old_keyonly = TS.diff_terms(current=current)
    added = list(added or [])
    modified = list(modified or [])

    for t in (extra_terms or []):
        if t not in added and t not in modified:
            modified.append(t)

    emit(f"  当前术语：{len(current)} 条")
    emit(f"  新增：{len(added)}  修改：{len(modified)}  删除：{len(removed or [])}")

    affected = list(added) + list(modified)
    if not affected:
        emit("术语表没有变化，无需重翻")
        TS.save_snapshot(current)
        return {"files": 0, "removed": 0}

    if added:
        emit("  新增示例：" + "、".join(
            f"{t}→{current.get(t, '')}" for t in added[:8]))

    total_removed = 0
    files_done = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        # ★ 本菜单只允许选缓存文件（*_cache.json），先换回源文件再交给
        #   Runtime.set_input 推导缓存 / 译文路径
        src_path = source_of(path)
        if not os.path.exists(src_path):
            emit(f"  找不到对应的源文件：{src_path}")
            continue

        config.Runtime.set_input(src_path)
        bridge.progress(i - 1, len(paths), os.path.basename(src_path))

        if not os.path.exists(config.Runtime.cache_file):
            emit(f"  缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
            continue

        cache = Cache(config.Runtime.cache_file)
        hits = TS.find_affected_cache(cache.data, affected)
        if not hits:
            emit(f"  [{os.path.basename(src_path)}] 没有句子命中这些术语")
            continue

        emit(f"  [{os.path.basename(src_path)}] 命中缓存 {len(hits)} 条")
        by_term = Counter(term for _, term in hits)
        for term, n in by_term.most_common(8):
            emit(f"      {term}: {n} 条")

        removed_n = cache.remove_many([k for k, _ in hits])
        cache.save(force=True)
        total_removed += removed_n
        emit(f"  ✔ 已删除 {removed_n} 条缓存")

        lines, newline = P.read_file(src_path, config.INPUT_ENCODING)
        _translate_core(src_path, lines, newline, show_header=False)
        files_done += 1

    TS.save_snapshot(current)
    bridge.progress(len(paths), len(paths), "完成")
    return {"files": files_done, "removed": total_removed}


# ================================================================
# 核心 3b：解决术语冲突
#   报告页把「同一原文、两种译文」的冲突列出来，用户挑一个（或自定义）
#   作为最终译文，这里负责写回术语字典、删掉相关缓存并重翻。
# ================================================================
def _rename_conflict_keys(renames):
    """冲突记录文件里的术语原文同步改名（{旧: 新}）。"""
    if not renames:
        return
    data = load_term_conflicts()
    if not data:
        return
    changed = False
    for old, new in renames.items():
        item = data.pop(old, None)
        if not isinstance(item, dict):
            continue
        exist = data.get(new)
        if isinstance(exist, dict):
            for s in item.get("src") or []:
                if s and s not in exist.setdefault("src", []):
                    exist["src"].append(s)
        else:
            data[new] = item
        changed = True
    if changed:
        save_term_conflicts(data)




# ================================================================
# 核心 4：应用前缀字典
# ================================================================
def apply_prefix_dict_paths(paths, entries_map=None):
    """
    不调用模型：用前缀字典重新拼接缓存译文并回写输出文件。
    entries_map: 可选的 {前缀: 译文}，先写入字典再应用。
    """
    import prefix_dict as PFD

    _announce_work_dir(paths)

    log.info("=" * 50)
    log.info("应用前缀字典  共 %d 个文件", len(paths))

    if entries_map:
        n = PFD.update_many(entries_map)
        PFD.save()
        emit(f"  前缀字典已写入 {n} 条修改")

    PFD.reload_dict()
    s = PFD.stats()
    emit(f"当前字典：共 {s['total']} 条，已翻译 {s['done']} 条，"
         f"待翻译 {s['pending']} 条")

    done = 0
    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        # ★ 菜单 5 现在只选缓存文件（*_cache.json），先换回源文件
        src_path = source_of(path)
        if not os.path.exists(src_path):
            emit(f"  找不到对应的源文件：{src_path}")
            continue

        config.Runtime.set_input(src_path)
        bridge.progress(i - 1, len(paths), os.path.basename(src_path))

        if not os.path.exists(config.Runtime.cache_file):
            emit(f"  缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
            continue

        try:
            lines, newline = P.read_file(src_path, config.INPUT_ENCODING)
        except Exception as e:
            emit(f"  读取失败：{e}")
            continue

        entries, special = P.extract_entries(lines)
        cache = Cache(config.Runtime.cache_file)

        translations = {}
        hit_prefix = miss_prefix = no_prefix = 0

        for _, src in entries:
            prefix, body = PR.split_prefix(src)
            if not prefix:
                no_prefix += 1
                translations[src] = cache.get(src)
                continue

            cached_final = cache.get(src)
            if not cached_final:
                continue

            new_prefix = PFD.apply_prefix(prefix)
            # ★ 缓存里存的是「已经拼过前缀的整行」，而那版前缀未必等于
            #   现在字典里的写法（用户改过前缀译法、或当时用的是术语替换版）。
            #   统一交给 strip_prefix_echo 按「当前前缀 / 原文前缀 / 术语替换版」
            #   逐个比对，并用「原文正文是否自带控制码」做安全兜底，
            #   避免出现 `\tg[新]\tg[旧]正文` 这种新旧并存。
            src_body = (src[len(prefix):]
                        if src.startswith(prefix) else src)
            body_final = PFD.strip_prefix_echo(cached_final, prefix, src_body)
            new_final = new_prefix + body_final
            if new_final != cached_final:
                translations[src] = new_final
                hit_prefix += 1
            else:
                translations[src] = cached_final
                miss_prefix += 1

        replaced = P.write_output(
            lines, entries, translations,
            config.Runtime.output_file, newline, config.OUTPUT_ENCODING,
        )
        emit(f"  [{os.path.basename(src_path)}] 替换 {replaced}/{len(entries)} 条"
             f"  前缀生效 {hit_prefix}  未译 {miss_prefix}  无前缀 {no_prefix}")
        done += 1

    bridge.progress(len(paths), len(paths), "完成")
    log.info("应用前缀字典完成：%d 个文件", done)
    return {"files": done}


# ================================================================
# 核心 4b：前缀字典「应用术语」
#   · 让前缀去匹配术语字典，命中则替换
#   · 当前只替换 \tg[...] 里的内容（角色名），控制码参数一律不动
# ================================================================
def scan_prefix_terms():
    """预演「应用术语」，返回 (changes, stats)，不写盘。"""
    import prefix_dict as PFD
    PFD.reload_dict()
    return PFD.scan_terms_for_tg()


def apply_prefix_terms_paths(paths=None):
    """
    把术语表套用到前缀字典（仅 \tg[...] 内容）并落盘；
    给了 paths 就顺带把前缀重新拼回译文文件。

    返回 {"changed": 命中条数, "files": 应用到的文件数, "samples": [...]}
    """
    import prefix_dict as PFD

    _announce_work_dir(paths)

    PFD.reload_dict()
    changes, stats = PFD.apply_terms_for_tg()

    emit("\n" + "=" * 55)
    emit("  前缀字典 · 应用术语（只替换 \\tg[...] 里的内容）")
    emit("=" * 55)
    emit(f"  字典共 {stats['total']} 条，命中术语 {stats['changed']} 条，"
         f"未命中 {stats['untouched']} 条")

    samples = []
    for c in changes[:10]:
        pairs = "、".join(f"{s}→{d}" for s, d in c["terms"][:3])
        emit(f"    {c['src']}  →  {c['new']}   （{pairs}）")
        samples.append({"src": c["src"], "new": c["new"],
                        "terms": c["terms"]})
    if len(changes) > 10:
        emit(f"    … 其余 {len(changes) - 10} 条省略")

    if not changes:
        emit("  没有前缀命中术语，无需改动")
        return {"changed": 0, "files": 0, "samples": []}

    files = 0
    if paths:
        r = apply_prefix_dict_paths(paths)
        files = (r or {}).get("files", 0)
    else:
        emit("  （未选择文件，只更新前缀字典；"
             "选好文件后再点一次即可写回译文）")

    log.info("前缀字典应用术语：命中 %d 条，应用文件 %d 个",
             len(changes), files)
    return {"changed": len(changes), "files": files, "samples": samples}


# ================================================================
# 核心 5：中文润色重翻
# ================================================================
# ================================================================
# 中文润色：断点续翻进度 + 润色报告
#   · 进度：<输入名>_polish_cache.json（与缓存同目录）
#     {"version":1,"round":N,"updated_at":"...",
#      "done":{原文: {"out": 润色后译文, "at": 时间}}, "stats":{...}}
#     以「原文」为身份、以「缓存里的值 == 上次润色结果」为完成判据：
#     用户中途改过译文 / 重翻过，那条会自动重新参与润色。
#   · 报告：<输出名>_polished.txt（与输出文件同目录），逐条列出改动。
# ================================================================
POLISH_STATE_SUFFIX = "_polish_cache.json"
POLISH_STATE_VERSION = 1


def _polish_state_path():
    """润色进度文件路径：与缓存同源，<输入名>_polish_cache.json"""
    cache = getattr(config.Runtime, "cache_file", "") or ""
    if cache:
        stem = os.path.splitext(os.path.basename(cache))[0]
        if stem.endswith("_cache"):
            stem = stem[:-len("_cache")]
        return os.path.join(os.path.dirname(cache) or ".",
                            f"{stem}{POLISH_STATE_SUFFIX}")
    d = os.path.dirname(config.Runtime.output_file) or "."
    return os.path.join(d, f"polish{POLISH_STATE_SUFFIX}")


def _load_polish_state(path):
    """读润色进度；不存在 / 损坏都当作「没有进度」，不影响正常润色。"""
    empty = {"version": POLISH_STATE_VERSION, "round": 0,
             "done": {}, "stats": {}}
    if not path or not os.path.exists(path):
        return empty
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("进度文件内容不是对象")
        data.setdefault("done", {})
        data.setdefault("round", 0)
        data.setdefault("stats", {})
        return data
    except Exception as e:
        log.warning("润色进度加载失败（当无进度处理）：%s", e)
        return empty


def _save_polish_state(path, state):
    """落盘润色进度（原子写，Windows 上的临时文件占用与缓存同样处理）。"""
    state["version"] = POLISH_STATE_VERSION
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        atomic_replace(tmp, path)
    except Exception as e:
        log.warning("润色进度保存失败（不影响本次润色）：%s", e)


def _polish_log_path():
    """润色报告路径：中间文件 → 优先放「翻译中间文件」夹，名 <输出名>_polished.txt"""
    out = config.Runtime.output_file
    d = config.aux_dir(out) or "."
    base = os.path.splitext(os.path.basename(out))[0]
    return os.path.join(d, f"{base}_polished.txt")


def _write_polish_report(path, records, stats, state_path, status="完成"):
    """
    records: [{"kind": "改动"/"未变"/"跳过", "src": 原文,
               "old": 润色前, "new": 润色后}, ...]
    写完后返回报告路径。
    """
    report_path = _polish_log_path()
    groups = {"改动": [], "未变": [], "跳过": []}
    for r in records:
        groups.setdefault(r.get("kind", "改动"), []).append(r)

    head = [
        "# 中文润色报告",
        f"# 状态：{status}",
        f"# 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"# 输入文件：{path}",
        f"# 译文缓存：{config.Runtime.cache_file}",
        f"# 输出文件：{config.Runtime.output_file}",
        f"# 进度文件：{state_path}",
        "#",
        f"# 本轮：改动 {stats.get('changed', 0)} 条，"
        f"未变 {stats.get('kept', 0)} 条，"
        f"跳过（已完成）{stats.get('skipped', 0)} 条；"
        f"累计已完成 {stats.get('done_total', 0)} 条"
        f"（第 {stats.get('round', 1)} 轮）",
        "=" * 70,
        "",
    ]

    body = []
    for kind in ("改动", "未变", "跳过"):
        items = groups.get(kind) or []
        if not items:
            continue
        body.append(f"## {kind}　{len(items)} 条")
        body.append("-" * 70)
        for i, r in enumerate(items, 1):
            body.append(f"[{i}]")
            body.append(f"  原文：{r.get('src', '')}")
            if kind == "改动":
                body.append(f"  润色前：{r.get('old', '')}")
            if kind == "改动":
                body.append(f"  润色后：{r.get('new', '')}")
            body.append("")
        body.append("")

    try:
        with open(report_path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(head + body))
    except Exception as e:
        log.warning("写润色报告失败：%s", e)
        return None
    return report_path


def _flush_polish_report(path, records, state_path, round_no,
                         changed=0, kept=0, skipped=0, done_total=None,
                         status="完成"):
    """收尾：刷新进度文件与统计，再写润色明细报告，返回报告路径。"""
    state = _load_polish_state(state_path)
    if done_total is None:
        done_total = len(state.get("done") or {})
    state["round"] = round_no
    state["input"] = path
    state["stats"] = {"round": round_no, "changed": changed, "kept": kept,
                      "skipped": skipped, "done_total": done_total,
                      "todo": changed + kept + skipped}
    _save_polish_state(state_path, state)
    return _write_polish_report(path, records, state["stats"], state_path,
                                status=status)


def _polish_core(path, lines=None, newline=None, show_header=True,
                 reset=False, state_path=None):
    """
    对单个文件：把缓存里的中文译文再润色一遍，覆盖回缓存并重写输出文件。

    reset=True 会清空本文件的润色进度（重新润色全部）。
    """
    out_path = config.Runtime.output_file
    cache_path = config.Runtime.cache_file

    # ★ 本文件的 section：润色时用它追加类别风格段（prompts/categories）
    sec = _file_section(path)
    if sec:
        log.info("润色文件 section：%s", sec)

    if show_header:
        emit(f"\n{'=' * 55}")
        emit(f"  中文润色：{path}")
        emit(f"  输出：{out_path}")
        emit(f"{'=' * 55}")

    if lines is None:
        lines, newline = P.read_file(path, config.INPUT_ENCODING)
    newline = newline or "\n"

    entries, _ = P.extract_entries(lines)
    cache = Cache(cache_path)

    # ---------- 断点续翻进度 ----------
    state_path = state_path or _polish_state_path()
    state = _load_polish_state(state_path)
    round_no = int(state.get("round") or 0) + (0 if reset else 1)
    done_map = {} if reset else (state.get("done") or {})
    if reset:
        state["done"] = {}

    records = []          # 润色报告明细：每条一个 dict
    min_len = getattr(config, "POLISH_MIN_LEN", 4)
    seen, todo = set(), []
    for _, txt in entries:
        if txt in seen:
            continue
        seen.add(txt)
        val = cache.get(txt)
        if not val or val == txt:
            continue                       # 没翻译过 / 纯控制符原样缓存
        if len(val.strip()) < min_len or PR.is_pure_control(val):
            continue
        # ★ 断点续翻：缓存里的值仍是上次润色的结果 → 这条已完成，跳过
        if done_map.get(txt, {}).get("out") == val:
            records.append({"kind": "跳过", "src": txt, "old": val,
                            "new": val})
            continue
        todo.append(txt)

    skipped = sum(1 for r in records if r["kind"] == "跳过")
    emit(f"[润色] 缓存 {len(cache)} 条  待润色 {len(todo)} 条"
         f"  跳过已完成 {skipped} 条")
    if not todo:
        emit("没有需要润色的译文"
             + (f"（已全部润色过，进度文件 {state_path}）" if skipped else
                "（先运行一次翻译）"))
        _flush_polish_report(path, records, state_path, round_no,
                             skipped=skipped)
        return {"changed": 0, "kept": 0, "todo": 0, "skipped": skipped}

    client = OllamaClient()
    batch_size = getattr(config, "POLISH_BATCH_SIZE", 8) or 8
    changed = 0
    kept = 0
    total = len(todo)
    done = 0
    t0 = time.time()

    def _mark_unchanged(t):
        """润色没拿到有效结果 → 保留原译文，并记进报告。"""
        nonlocal kept
        kept += 1
        old = cache.get(t)
        records.append({"kind": "未变", "src": t, "old": old, "new": old})

    # 润色同样按上下文预算分批：正文取译文，原文进参考块
    polish_sys_tokens = _tokens_of(
        T.load_template("system_polish.txt", T.POLISH_SYSTEM_PROMPT)
        .replace("{tgt}", config.TARGET_LANG))
    polish_batches = _make_batches(
        todo, batch_size, budget=T.resolve_ctx_budget(),
        sys_tokens=polish_sys_tokens,
        ref_provider=lambda b: True,
        body_provider=lambda t: cache.get(t) or "")

    for bi, batch_texts in enumerate(polish_batches, 1):
        if bridge.cancelled():
            emit("\n[中断] 用户取消")
            break

        items, orig_dict, src_safe_dict = [], {}, {}
        for k, txt in enumerate(batch_texts):
            cur = cache.get(txt) or ""
            items.append((k, cur, txt))
            orig_dict[k] = cur
            src_safe_dict[k] = txt

        result = polish_with_retry(client, items, section=sec)

        # 拿不到译文就保留原译文
        for k, txt in enumerate(batch_texts):
            raw = result.get(k)
            if not raw or not raw.strip():
                _mark_unchanged(txt)
                continue

            new_text = (raw or "").strip()
            # ★ 控制码检测：润色前后控制码（含 \n）必须完全一致，
            #   不一致说明模型改坏了 —— 一律保留原译文
            if (PR.control_symbols(orig_dict[k], ignore_newline=False)
                    != PR.control_symbols(new_text,
                                          ignore_newline=False)):
                log.warning("[润色 %d][%d] 控制码不一致，保留原译文",
                            bi, k)
                _mark_unchanged(txt)
                continue
            if not new_text:
                _mark_unchanged(txt)
                continue
            if new_text == cache.get(txt):
                _mark_unchanged(txt)
                continue

            cache.put(txt, new_text)
            changed += 1
            state["done"][txt] = {"out": new_text,
                                  "at": time.strftime("%H:%M:%S")}
            records.append({"kind": "改动", "src": txt,
                            "old": cache.get(txt, ""), "new": new_text})

        cache.tick()
        ok = sum(1 for k in range(len(batch_texts))
                 if (result.get(k) or "").strip())
        done += len(batch_texts)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate / 60 if rate > 0 else 0
        log.info("[批 %d] 成功 %d/%d  累计 %d/%d  %.2f条/秒  ETA %.1f分",
                 bi, ok, len(batch_texts), done, total, rate, eta)
        state["stats"] = {"round": round_no, "changed": changed,
                          "kept": kept, "skipped": skipped,
                          "done_total": len(state["done"])}
        _save_polish_state(state_path, state)
        bridge.progress(min(bi * batch_size, total), total,
                        f"润色 {min(bi * batch_size, total)}/{total}")

    # ★ 跑完把 HTTP 连接池关掉（同翻译：别让长连接一直堆着）
    client.close()
    cache.save(force=True)

    translations = {txt: cache.get(txt) for _, txt in entries if cache.get(txt)}
    replaced = P.write_output(
        lines, entries, translations,
        out_path, newline, config.OUTPUT_ENCODING,
    )
    emit(f"\n✔ 润色完成：改动 {changed} 条，保持不变 {kept} 条")
    emit(f"  回写 {replaced}/{len(entries)} 条 → {out_path}")

    report_path = _flush_polish_report(
        path, records, state_path, round_no,
        changed=changed, kept=kept, skipped=skipped,
        status="已中断" if bridge.cancelled() else "完成",
    )
    if report_path:
        emit(f"  润色明细：{report_path}")

    return {"changed": changed, "kept": kept, "todo": total,
            "skipped": skipped, "report": report_path}


def polish_paths(paths, model=None, reset=False):
    # ★ 文本保护规则：润色也要按当前规则处理控制码
    import text_rules
    text_rules.ensure_applied()
    _apply_lang_model(None, None, model)

    _announce_work_dir(paths)

    log.info("=" * 50)
    log.info("中文润色重翻  共 %d 个文件", len(paths))

    if not getattr(config, "POLISH_ENABLE", True):
        emit("中文润色功能已关闭（POLISH_ENABLE=False）")
        return {"files": 0, "changed": 0}

    total_changed = 0
    total_skipped = 0
    files_done = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        # ★ 本菜单只允许选缓存文件（*_cache.json），先换回源文件
        src_path = source_of(path)
        if not os.path.exists(src_path):
            emit(f"  找不到对应的源文件：{src_path}")
            continue

        config.Runtime.set_input(src_path)
        bridge.progress(i - 1, len(paths), os.path.basename(src_path))

        if not os.path.exists(config.Runtime.cache_file):
            emit(f"  缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
            continue

        try:
            lines, newline = P.read_file(src_path, config.INPUT_ENCODING)
        except Exception as e:
            emit(f"  读取失败：{e}")
            continue

        if len(paths) > 1:
            emit(f"\n[{i}/{len(paths)}] {os.path.basename(src_path)}")

        try:
            r = _polish_core(src_path, lines, newline,
                             show_header=(len(paths) == 1), reset=reset)
            total_changed += r.get("changed", 0)
            total_skipped += r.get("skipped", 0)
            files_done += 1
        except bridge.CancelRequested:
            emit("\n[中断] 用户取消")
            break

    bridge.progress(len(paths), len(paths), "完成")
    return {"files": files_done, "changed": total_changed,
            "skipped": total_skipped}


# ================================================================
# 核心 6：换行重排（纯本地，不调用模型）
# ================================================================
def _reflow_cfg(mode, cfg=None):
    """取某模式的重排参数 (min_chars, max_chars, min_gap)。"""
    if isinstance(cfg, dict):
        return (cfg.get("min"), cfg.get("max"), cfg.get("gap"))
    if mode == "space":
        return (getattr(config, "WRAP_SPACE_MIN", 8),
                getattr(config, "WRAP_SPACE_MAX", 10),
                getattr(config, "WRAP_SPACE_MIN_GAP", 5))
    return (config.WRAP_CHARS_MIN, config.WRAP_CHARS_MAX,
            getattr(config, "WRAP_MIN_GAP", 10))


def _output_lines_of(path, lines, cache):
    """
    返回与原文等长、已填入译文的输出行。
    优先读已有译文文件（保留人工/术语修改），缺失时用缓存重建。
    """
    out_path = config.Runtime.output_file
    if os.path.exists(out_path):
        try:
            out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
            if len(out_lines) == len(lines):
                return out_lines
        except Exception:
            pass

    out_lines = list(lines)
    entries, _ = P.extract_entries(lines)
    for idx, src in entries:
        dst = cache.get(src)
        if not dst:
            continue
        m = re.match(r'^([ \t]*)', lines[idx])
        out_lines[idx] = (m.group(1) if m else "") + dst
    return out_lines


def reflow_block_id(path, block, line=None):
    """
    区块的唯一标识（绝对路径 + 区块名 + 起始行）。

    ★ 换行重排页支持「只重排选中的区块」，扫描（scan_reflow_blocks）
      与执行（reflow_paths）两边都用这个 id 对齐。
    """
    return "{0}\x00{1}\x00{2}".format(os.path.abspath(path), block, line)


def _line_block_ids(lines, path):
    """每行所属区块的 id（规则与 scan_reflow_blocks 完全一致）。"""
    out = []
    cur_name, cur_line = "（文件开头）", 0
    for idx, raw in enumerate(lines):
        s = raw.strip()
        if P.is_block(s):
            cur_name, cur_line = s, idx
        out.append(reflow_block_id(path, cur_name, cur_line))
    return out


def scan_reflow_blocks(paths, preview=8):
    """
    扫描待重排文件，按「区块」归类，供换行重排页展示。

    返回 {"newline": [block, ...], "space": [block, ...]}
    block = {"file", "path", "block", "mode", "line", "id", "total",
             "pairs":[(原文,译文),...]}
    """
    result = {"newline": [], "space": []}

    _announce_work_dir(paths)

    for path in paths:
        if not os.path.exists(path):
            continue
        # ★ 菜单 7 只列译文文件，先换回源文件再读（译文与源文件行数一致，
        #   但缓存 / 块名都挂在源文件上）
        src_path = source_of(path)
        if not os.path.exists(src_path):
            log.warning("重排扫描：找不到对应的源文件 %s", src_path)
            continue
        try:
            lines, _nl = P.read_file(src_path, config.INPUT_ENCODING)
        except Exception as e:
            log.warning("重排扫描读取失败：%s（%s）", src_path, e)
            continue

        config.Runtime.set_input(src_path)
        cache = Cache(config.Runtime.cache_file)
        out_lines = _output_lines_of(src_path, lines, cache)

        modes = P.get_block_modes(lines)
        entries, _ = P.extract_entries(lines)
        trans_idx = {idx for idx, _ in entries}

        blocks = []
        cur_name, cur_mode, cur_pairs, cur_line = "（文件开头）", "newline", [], 0

        def _flush():
            if cur_pairs:
                blocks.append({
                    # ★ 用源文件：区块 id 在扫描与执行两边必须一致，
                    #   否则「只重排选中的区块」会一个都命中不了
                    "file":  os.path.basename(src_path),
                    "path":  src_path,
                    "block": cur_name,
                    "mode":  cur_mode,
                    "line":  cur_line,
                    "id":    reflow_block_id(src_path, cur_name, cur_line),
                    "total": len(cur_pairs),
                    "pairs": cur_pairs[:preview],
                })

        for idx, raw in enumerate(lines):
            s = raw.strip()
            if P.is_block(s):
                _flush()
                cur_name, cur_mode, cur_pairs, cur_line = s, modes[idx], [], idx
                continue
            if idx in trans_idx:
                src = lines[idx].strip()
                dst = out_lines[idx].strip() if idx < len(out_lines) else ""
                if dst and dst != src:
                    cur_pairs.append((src, dst))
        _flush()

        for b in blocks:
            result.setdefault(b["mode"], []).append(b)

    return result


def reflow_paths(paths, newline_cfg=None, space_cfg=None, blocks=None):
    """
    按区块类型重排译文里的换行 / 空格（纯本地操作，不调用模型）。

    newline_cfg / space_cfg: {"min","max","gap"} 或 None（用当前配置）
    blocks : 只重排这些区块（reflow_block_id 组成的列表 / 集合）；
             None 或空 = 文件里所有区块都重排。
    """
    _announce_work_dir(paths)

    paths, _skipped = _drop_names_files(paths, "换行重排")
    if not paths:
        emit("没有需要重排的文件（名字类文本已全部跳过）")
        return {"files": 0, "changed": 0}

    log.info("=" * 50)
    log.info("换行重排  共 %d 个文件", len(paths))

    nl = _reflow_cfg("newline", newline_cfg)
    sp = _reflow_cfg("space", space_cfg)
    sel_ids = set(blocks) if blocks else None
    emit("\n" + "=" * 55)
    emit("  换行重排（仅重排列，不改动译文文字）")
    emit("=" * 55)
    emit(f"  [map*] 换行  ：{nl[0]}~{nl[1]} 字，最小间隔 {nl[2]} 字")
    emit(f"  其它区块空格：{sp[0]}~{sp[1]} 字，最小间隔 {sp[2]} 字")
    if sel_ids is not None:
        emit(f"  只重排选中的 {len(sel_ids)} 个区块（其余区块原样保留）")
    else:
        emit("  重排范围：文件里的所有区块")

    if not getattr(config, "REWRAP_ENABLE", True):
        emit("\n⚠ 换行重排已关闭（REWRAP_ENABLE=False），请先到「设置」里打开")
        return {"files": 0, "changed": 0}

    files_done = changed = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            emit("\n[中断] 用户取消")
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        # ★ 本菜单只允许选译文文件（*_translated.txt），先换回源文件
        src_path = source_of(path)
        if not os.path.exists(src_path):
            emit(f"  找不到对应的源文件：{src_path}")
            continue

        config.Runtime.set_input(src_path)
        out_path = config.Runtime.output_file
        bridge.progress(i - 1, len(paths), os.path.basename(src_path))

        try:
            lines, _ = P.read_file(src_path, config.INPUT_ENCODING)
        except Exception as e:
            emit(f"  读取失败：{e}")
            continue

        if not os.path.exists(out_path):
            emit(f"  缺少译文：{out_path}（先跑一次翻译）")
            continue

        try:
            out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
        except Exception as e:
            emit(f"  译文读取失败：{e}")
            continue
        # ★ 行尾按译文文件的原始字节定（文本模式读会把 CRLF 归一成 LF）
        out_nl = P.detect_newline(out_path, default=os.linesep)

        if len(out_lines) != len(lines):
            emit(f"  行数不一致（原文 {len(lines)} / 译文 {len(out_lines)}），跳过")
            continue

        modes = P.get_block_modes(lines)
        entries, _ = P.extract_entries(lines)
        # ★ 每个条目属于哪个区块（用于「只重排选中区块」）
        block_of = _line_block_ids(lines, src_path) if sel_ids is not None else None
        sel_hit = 0                       # 本文件里命中「选中区块」的条目数

        n_changed = 0
        for idx, src_text in entries:
            if block_of is not None:
                bid = block_of[idx] if idx < len(block_of) else None
                if bid not in sel_ids:
                    continue
                sel_hit += 1
            dst = out_lines[idx]
            m = re.match(r'^([ \t]*)', dst)
            indent = m.group(1) if m else ""
            body = dst.strip()
            if not body or body == src_text.strip():
                continue

            mode = modes[idx] if idx < len(modes) else "newline"
            mn, mx, gap = (sp if mode == "space" else nl)
            new_body = PR.reflow(src_text.strip(), body, mode=mode,
                                 min_chars=mn, max_chars=mx, min_gap=gap)
            if not new_body or new_body == body:
                continue
            out_lines[idx] = indent + new_body
            n_changed += 1

        name = os.path.basename(path)
        if not n_changed:
            extra = ("（本文件没有选中区块，已跳过）"
                     if block_of is not None and not sel_hit else "")
            emit(f"[{i}/{len(paths)}] {name}：已符合当前配置，无需改动{extra}")
            files_done += 1
            continue

        try:
            # ★ newline=""：原样写回，别让 Windows 文本模式把 \n 变成 \r\n
            #   —— 否则「只重排选中区块」时未选中的行也会跟着变行尾。
            tmp = out_path + ".tmp"
            with open(tmp, "w", encoding=config.OUTPUT_ENCODING,
                      newline="") as f:
                f.write(out_nl.join(out_lines))
            atomic_replace(tmp, out_path)
        except Exception as e:
            emit(f"  写入失败：{e}")
            continue

        emit(f"[{i}/{len(paths)}] {name}：重排 {n_changed} 条 → {out_path}")
        changed += n_changed
        files_done += 1

    bridge.progress(len(paths), len(paths), "完成")
    emit(f"\n✔ 换行重排完成：{files_done} 个文件，改动 {changed} 条")
    log.info("换行重排完成：%d 个文件，改动 %d 条", files_done, changed)
    return {"files": files_done, "changed": changed}


# ================================================================
# 核心 1：文本提取与编译（菜单 1）
#   纯本地：读游戏编译好的文本表 / 写回语言 .dat / 编译插件。
# ================================================================
def intl_extract_paths(game_dirs, out_path=None):
    """
    提取文本：读游戏 Data 下的原文表（messages.dat / english.dat），
    按分段拆成多个 txt（每个分段一个文件）—— 等同于在游戏 debug 菜单里点
    「Extract Text」。返回 [{"game":…, "out":…, "sections":…, …}]。
    """
    import intl_text as IT
    out = []
    for gd in game_dirs or []:
        if bridge.cancelled():
            break
        emit("\n" + "=" * 55)
        emit(f"  提取文本：{gd}")
        emit("=" * 55)
        try:
            rep = IT.extract_text(gd, out_path=out_path, emit=emit)
            out.append({"game": gd, **rep})
        except Exception as e:
            log.error("提取文本失败：%s\n%s", e, traceback.format_exc())
            emit(f"  ✘ 提取失败：{e}")
            out.append({"game": gd, "ok": False, "error": str(e)})
    return out


def intl_compile_paths(game_dir, sources, out_path=None, apply_language=True,
                       lang_first=None):
    """
    编译文本：把 intl 格式的文本（单个文件、多个文件、或整个文件夹里的
    全部 .txt）编译成游戏语言文件 —— 等同于在游戏 debug 菜单里点
    「Compile Text」。返回报告 dict。

    out_path 留空时按游戏版本自动定：
      旧版 → Settings::LANGUAGES 里那条（一般是 Data/Chinese.dat）
      新版 → Data/messages_<语言>_core.dat 与 …_game.dat
    apply_language：编译完顺手把这条语言写进 Settings::LANGUAGES，省得自己改脚本。
    lang_first：把中文放到语言表第一条（游戏默认语言）。留空取 config。
    """
    import intl_text as IT
    emit("\n" + "=" * 55)
    emit(f"  编译文本：{game_dir}")
    emit("=" * 55)
    try:
        rep = IT.compile_text(game_dir, sources, out_path=out_path,
                              emit=emit)
    except Exception as e:
        log.error("编译文本失败：%s\n%s", e, traceback.format_exc())
        emit(f"  ✘ 编译失败：{e}")
        return {"ok": False, "error": str(e)}
    if apply_language:
        try:
            # ★ 旧版写的是单个语言 .dat（如 Data/Chinese.dat）：语言表里必须
            #   写**同一个文件名**。写成 `chinese`（没 .dat）游戏会去找
            #   Data/chinese，找不到就静默回退 messages.dat —— 界面毫无变化。
            #   新版（core / game 两份）语言表里存的是片段，沿用原逻辑。
            # ★ 旧方案：语言表那一格就是**文件名**（游戏拼 "Data/" + 它），
            #   必须带 .dat；写成片段（chinese）游戏会去找 Data/chinese，
            #   找不到就整份加载失败，界面毫无变化。
            # ★ 新方案：语言表存的是片段（对应 messages_<片段>_core.dat）。
            frag = None
            if rep.get("outs"):
                frag = rep["outs"][0].get("fragment")
            elif rep.get("out"):
                frag = os.path.basename(rep["out"])
            if lang_first is None:
                lang_first = bool(getattr(config, "LANG_ENTRY_FIRST", True))
            rep["language"] = intl_apply_language(game_dir, fragment=frag,
                                                  emit=emit,
                                                  first=lang_first)
        except Exception as e:
            log.error("写入语言表失败：%s\n%s", e, traceback.format_exc())
            emit(f"  ⚠ 语言表没写成：{e}")
    return rep


def intl_apply_language(game_dir, display="简体中文", fragment=None, emit=None,
                        first=False):
    """
    编译完文本后调用：把这条语言写进游戏 Settings 的 LANGUAGES ——
    复制第一条语言条目、把 `English` 改成 `Chinese`（被注释的先取消注释）。
    不翻译注释、也不添加注释。返回 GS.apply_languages_entry 的结果。
    """
    import game_scripts as GS
    return GS.apply_languages_entry(game_dir, display=display,
                                    fragment=fragment, emit=emit,
                                    first=first)


def script_intl_paths(game_dir, write=False, include_main=True,
                      include_plugins=True):
    """
    脚本内文本汉化（方案 B）：把 `_INTL("英文")` 直接换成 `_INTL("中文")`。

    为什么不靠编译文本：`_INTL` 按键查第 24 段，查不到就原样返回英文；
    而第 24 段只能由游戏自己编译数据生成，插件文案常常一条都没进表
    （实测登神 v0.1.1.3：3299 键里 99.2% 来自主脚本）。写回源码不查表。

    write=False → 只预览，不动任何文件。
    返回 script_intl.run 的报告 dict。
    """
    import script_intl as SI
    emit("\n" + "=" * 55)
    emit(f"  脚本内文本汉化：{game_dir}")
    emit("=" * 55)
    try:
        return SI.run(game_dir, write=write, include_main=include_main,
                      include_plugins=include_plugins, emit=emit)
    except Exception as e:
        log.error("脚本内文本汉化失败：%s\n%s", e, traceback.format_exc())
        emit(f"  ✘ 失败：{e}")
        return {"ok": False, "error": str(e)}


def script_intl_export(game_dir, include_main=True, include_plugins=True):
    """
    导出「脚本里有、词表里没有」的 `_INTL` 文案 → 游戏根目录
    `Script_texts_missing.txt`（intl 格式，每段两行）。

    翻完存成 `Script_texts_missing_translated.txt`，「写回脚本」会自动用上。
    """
    import script_intl as SI
    emit("\n" + "=" * 55)
    emit(f"  导出脚本待补文案：{game_dir}")
    emit("=" * 55)
    try:
        return SI.export_missing(game_dir, include_main=include_main,
                                 include_plugins=include_plugins, emit=emit)
    except Exception as e:
        log.error("导出待补文案失败：%s\n%s", e, traceback.format_exc())
        emit(f"  ✘ 失败：{e}")
        return {"ok": False, "error": str(e), "count": 0}


def plugin_inject_paths(game_dirs, font_file=None):
    """
    加载中文文本处理插件：复制进 <游戏>/Plugins/、写字体名，并把**全部**
    插件（含游戏原有的）编译进 Data/PluginScripts.rxdata。
    ★ 纯文件写入，不调用模型、不联网。
    """
    import plugin_tools as PT
    out = []
    for gd in game_dirs or []:
        if bridge.cancelled():
            break
        emit("\n" + "=" * 55)
        emit(f"  加载中文文本处理插件：{gd}")
        emit("=" * 55)
        try:
            rep = PT.install_plugin(gd, font_file=font_file, emit=emit)
            out.append({"game": gd, **rep})
        except Exception as e:
            log.error("插件植入失败：%s\n%s", e, traceback.format_exc())
            emit(f"  ✘ 失败：{e}")
            out.append({"game": gd, "ok": False, "error": str(e)})
    return out


def plugin_restore_paths(game_dirs):
    """
    还原「加载中文文本处理插件」：删掉 Plugins/ 下本工具植入的那个目录，
    以及当初复制进游戏 Fonts 的那份字体（游戏自带字体不动）。
    """
    import plugin_tools as PT
    out = []
    for gd in game_dirs or []:
        emit("\n" + "=" * 55)
        emit(f"  还原插件植入：{gd}")
        emit("=" * 55)
        try:
            out.append({**PT.restore_plugin(gd, emit=emit), "game": gd})
        except Exception as e:
            log.error("插件还原失败：%s\n%s", e, traceback.format_exc())
            emit(f"  ✘ 失败：{e}")
            out.append({"game": gd, "ok": False, "removed": []})
    return out


def cmd_intl():
    """菜单 1：文本提取与编译"""
    import filepicker
    import game_scripts as GS
    import intl_text as IT

    emit("\n[文本提取与编译]")
    emit("  适用于 Pokémon Essentials（mkxp / RMXP）游戏：")
    emit("  ① 提取文本 —— 同游戏 debug 的 Extract Text；")
    emit("  ② 编译文本 —— 同游戏 debug 的 Compile Text；")
    emit("  ③ 加载中文文本处理插件（并编译进 PluginScripts.rxdata）。")

    folder = filepicker.pick_dir(
        initial_dir=config.Runtime.last_dir or config.BASE_DIR,
        title="选择游戏根目录（里面有 Game.exe 和 Data）")
    if not folder:
        emit("已取消")
        return
    ok, why = GS.check_game_root(folder)
    if not ok:
        emit(f"✘ {why}：{folder}")
        return
    config.Runtime.set_dir(folder)

    raw = input("\n1=提取 / 2=编译 / 3=加载插件 / 4=还原插件 [1]: ").strip()
    if raw == "2":
        src = input("要编译的文本（文件或文件夹）[默认用刚提取的 Text_ 文件夹]: ").strip()
        intl_compile_paths(folder, src or IT.extract_target(folder))
        return
    if raw == "3":
        plugin_inject_paths([folder])
        return
    if raw == "4":
        plugin_restore_paths([folder])
        return
    intl_extract_paths([folder])


# ================================================================
# 核心 7：Excel 转术语表
# ================================================================
def build_terms_from_excel(excel_path, sheets=None, source_lang="英文",
                           target_lang="简体中文", out_path=None,
                           mode="append"):
    """
    Excel → term_dict.py（无交互）。返回结果 dict。

    mode="append"（默认）已有术语字典时把新术语接在末尾、保留原有译法；
    mode="overwrite" 整份重写。
    """
    import importlib
    import build_terms as BT

    out_path = out_path or config.TERM_FILE
    log.info("Excel 转术语表：%s  %s → %s（%s）",
             excel_path, source_lang, target_lang, mode)

    result = BT.build_terms(excel_path, out_path, source_lang, target_lang,
                            sheets=sheets, dedup=True, verbose=False,
                            mode=mode)

    for e in result.get("errors", []):
        emit(f"  [err] {e}")

    if result.get("ok"):
        if result.get("mode") == "append" and result.get("existing"):
            emit(f"原有 {result['existing']} 条 → 追加 {result['added']} 条、"
                 f"跳过已存在 {result['skipped_existing']} 条")
            cf = result.get("conflicts") or []
            if cf:
                emit(f"⚠ {len(cf)} 条术语的新旧译法不一致，"
                     f"已保留字典里的原译法（不改已有内容）：")
                for src, old, new in cf[:8]:
                    emit(f"    {src}：保留「{old}」，Excel 里是「{new}」")
                if len(cf) > 8:
                    emit(f"    …另有 {len(cf) - 8} 条，详见日志")
        elif result.get("mode") == "append":
            emit(f"没有可追加的旧字典，新建 {result['total']} 条")
        emit(f"✔ 合计 {result['total']} 条 → {result['out_path']}")
        try:
            import processor
            importlib.reload(processor)
            processor.load_terms()
            emit("术语表已重新加载")
        except Exception as e:
            log.warning("重载术语表失败：%s", e)
        _update_snapshot()

    return result


# ================================================================
# 命令行外壳
# ================================================================
def cmd_translate():
    """菜单 2：翻译"""
    if not _ask_languages():
        return
    paths = _select_scope_interactive("选择要翻译的文件")
    if not paths:
        return
    translate_paths(paths)


def cmd_retranslate_report():
    """菜单 3：重翻检查报告"""
    if not _ask_languages():
        return
    paths = _select_scope_interactive("选择要重翻的文件")
    if not paths:
        return
    retranslate_report_paths(paths)


def cmd_retranslate_terms():
    """菜单 4：术语更新后重翻"""
    if not _ask_languages():
        return
    paths = _select_scope_interactive("选择要重翻的文件")
    if not paths:
        return
    retranslate_terms_paths(paths)


def cmd_review_prefix_dict():
    """菜单 5：前缀字典（查看 / 编辑）"""
    import prefix_dict as PFD

    PFD.reload_dict()
    s = PFD.stats()

    emit("\n[前缀字典]")
    emit("-" * 55)
    emit(f"文件：{PFD.DICT_FILE}")
    emit(f"统计：共 {s['total']} 条，已翻译 {s['done']} 条，"
         f"待翻译 {s['pending']} 条")

    pending = PFD.list_pending()
    if not pending:
        emit("\n✔ 没有待翻译的前缀")
    else:
        emit("\n待翻译前缀（前 30 条）：")
        for i, (k, _) in enumerate(pending[:30], 1):
            emit(f"  {i:>3}. {k}")
        if len(pending) > 30:
            emit(f"  … 其余 {len(pending) - 30} 条")
        emit(f"\n请编辑：{PFD.DICT_FILE}")
        if input("\n是否现在打开文件？(y/N): ").strip().lower() == "y":
            _open_path(PFD.DICT_FILE)

    paths = _select_scope_interactive("选择要应用前缀字典的文件")
    if not paths:
        return
    apply_prefix_dict_paths(paths)


def cmd_polish():
    """菜单 6：中文润色重翻"""
    paths = _select_scope_interactive("选择要润色的文件")
    if not paths:
        return
    # 默认断点续翻（跳过上次已润色过的）；选 y 才清空进度整份重润
    reset = False
    try:
        reset = input("是否清空润色进度、重新润色全部？(y/N): ").strip().lower() == "y"
    except EOFError:
        reset = False
    polish_paths(paths, reset=reset)


def _ask_reflow_params():
    """交互式修改两套重排参数：写回设置并热更新（回车跳过）。"""
    fields = [
        ("WRAP_CHARS_MIN",     "换行下限(字)"),
        ("WRAP_CHARS_MAX",     "换行上限(字)"),
        ("WRAP_MIN_GAP",       "换行最小间隔(字)"),
        ("WRAP_SPACE_MIN",     "空格下限(字)"),
        ("WRAP_SPACE_MAX",     "空格上限(字)"),
        ("WRAP_SPACE_MIN_GAP", "空格最小间隔(字)"),
    ]
    for key, name in fields:
        cur = getattr(config, key, "")
        raw = input(f"  {name}（当前 {cur}，回车跳过）：").strip()
        if not raw:
            continue
        ok, msg, _ = settings.set_value(key, raw)
        emit(f"    {'✔' if ok else '✘'} {name} → {msg}")


def cmd_reflow():
    """菜单 7：换行重排"""
    emit("\n[换行重排] 当前配置")
    emit("-" * 55)
    emit(f"  [map*] 换行  ：{config.WRAP_CHARS_MIN}~{config.WRAP_CHARS_MAX} 字，"
         f"最小间隔 {getattr(config, 'WRAP_MIN_GAP', 10)} 字")
    emit(f"  其它区块空格：{getattr(config, 'WRAP_SPACE_MIN', 8)}"
         f"~{getattr(config, 'WRAP_SPACE_MAX', 10)} 字，"
         f"最小间隔 {getattr(config, 'WRAP_SPACE_MIN_GAP', 5)} 字")
    emit("  （两种重排各用一套参数，也可在「设置」里修改）")

    if input("\n是否修改本次参数？(y/N): ").strip().lower() == "y":
        _ask_reflow_params()

    paths = _select_scope_interactive("选择要重排的文件")
    if not paths:
        return
    reflow_paths(paths)


def cmd_build_terms():
    """菜单 8：术语字典 —— Excel 转术语表（右侧卡片可切到字典列表）"""
    import filepicker
    import build_terms as BT

    emit("\n[术语表] 从 Excel 提取")

    excel_path = config.EXCEL_FILE
    if os.path.exists(excel_path):
        emit(f"默认 Excel：{excel_path}")
        if input("是否另选？(y/N): ").strip().lower() == "y":
            picked = filepicker.pick_excel_file(
                initial_dir=os.path.dirname(excel_path))
            if picked:
                excel_path = picked
    else:
        picked = filepicker.pick_excel_file(initial_dir=config.BASE_DIR)
        if not picked:
            emit("已取消")
            return
        excel_path = picked

    if not os.path.exists(excel_path):
        emit(f"文件不存在：{excel_path}")
        return

    try:
        sheets = BT.list_sheets(excel_path)
    except Exception as e:
        emit(f"打开 Excel 失败：{e}")
        return

    emit(f"\n共 {len(sheets)} 个工作表：")
    for i, (name, r, c) in enumerate(sheets, 1):
        emit(f"  {i:>2}. {name}   ({r} 行 × {c} 列)")

    src = _choose_language("请选择【源语言列】：", config.EXCEL_SOURCE_LANG)
    if not src:
        emit("已取消")
        return
    tgt = _choose_language("请选择【目标语言列】：",
                           config.EXCEL_TARGET_LANG, exclude=src)
    if not tgt:
        emit("已取消")
        return

    raw = input("\n只处理哪些工作表？（序号，逗号分隔；回车=全部）：").strip()
    chosen = None
    if raw:
        chosen = []
        for tok in re.split(r"[,，\s]+", raw):
            if tok.isdigit():
                idx = int(tok) - 1
                if 0 <= idx < len(sheets):
                    chosen.append(sheets[idx][0])
        if not chosen:
            emit("未识别到有效序号，改为处理全部")
            chosen = None

    out_path = input(f"\n输出文件 [{config.TERM_FILE}]: ").strip().strip('"')
    out_path = out_path or config.TERM_FILE

    # ★ 已有术语字典时默认追加：新术语接在末尾，原有译法不动
    mode = "append" if getattr(config, "EXCEL_APPEND", True) else "overwrite"
    if os.path.exists(out_path):
        try:
            import build_terms as _BT
            old_n = len(_BT.read_existing_terms(out_path))
        except Exception:
            old_n = 0
        if old_n:
            emit(f"\n检测到已有术语字典：{out_path}（{old_n} 条）")
            raw2 = input("  回车 = 在末尾追加新术语 / 输入 o = 整份覆盖: ")
            mode = "overwrite" if raw2.strip().lower() in ("o", "over",
                                                          "overwrite") else "append"
        else:
            emit(f"\n{out_path} 已存在但读不到 TERM_DICT，将整份重写")

    emit(f"模式：{'追加到末尾' if mode == 'append' else '整份覆盖'}")
    build_terms_from_excel(excel_path, chosen, src, tgt, out_path, mode=mode)


# ================================================================
# 术语提取的检查报告（不走模型）
# ================================================================




def _choose_language(prompt, default_key, exclude=None):
    """Excel 列名选择（用 build_terms 的别名表）。"""
    import build_terms as BT
    keys = list(BT.LANG_ALIASES.keys())
    emit(f"\n{prompt}")
    for i, k in enumerate(keys, 1):
        mark = ""
        if k == default_key:
            mark = "   ← 默认"
        if exclude and k == exclude:
            mark = "   (已被选为另一种语言)"
        emit(f"  {i:>2}. {k}{mark}")
    emit("   0. 自定义")

    raw = input(f"请选择 [{default_key}]: ").strip()
    if not raw:
        return default_key
    if raw == "0":
        return input("请输入列名（Excel 表头文字）：").strip() or None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(keys):
            return keys[idx]
    emit("无效输入")
    return None


def cmd_provider():
    """菜单 10：本地模型服务（切换提供商 / 模型 / 部署）"""
    import providers as PV

    while True:
        key = PV.current()
        p = PV.get(key)
        emit("\n" + "=" * 62)
        emit(f"  本地模型服务   当前：{p['label']}")
        emit("=" * 62)
        emit(f"  服务地址：{PV.chat_url(key)}")
        emit(f"  模型：{PV.current_model(key) or '（未设置）'}")
        emit(f"  说明：{p['summary']}")
        emit("-" * 62)
        for i, k in enumerate(PV.keys(), 1):
            mark = " ← 当前" if k == key else ""
            emit(f"  {i}. 切换到 {PV.label_of(k)}{mark}")
        emit(f"  {len(PV.keys()) + 1}. 修改当前服务地址")
        emit(f"  {len(PV.keys()) + 2}. 检测服务是否在线")
        emit(f"  {len(PV.keys()) + 3}. 列出本机可用模型")
        emit(f"  {len(PV.keys()) + 4}. 一键部署模型（拉取 / 下载）")
        emit("  0. 返回主菜单")
        emit("=" * 62)

        raw = input("请选择：").strip()
        if raw in ("0", ""):
            return

        keys = PV.keys()
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            target = keys[int(raw) - 1]
            if target == key:
                emit("已经是当前提供商")
                continue
            PV.set_prev_provider(key)
            changes = PV.apply_provider(target)
            emit(f"\n已切换到 {PV.label_of(target)}")
            for name, old, new in changes:
                emit(f"  · {name}：{old}  →  {new}")
            auto, manual = PV.adaptation(key, target)
            emit("\n[已自动完成]")
            for it in auto:
                emit(f"  ✔ {it['title']}：{it['detail']}")
            if manual:
                emit("\n[还需要你手动处理]")
                for it in manual:
                    emit(f"  ⚠ {it['title']}：{it['detail']}")
            continue

        extra = len(keys)
        if raw == str(extra + 1):
            new_url = input(f"新的服务地址（当前 {PV.chat_url(key)}）：").strip()
            if not new_url:
                emit("已取消")
                continue
            ok, msg = PV.set_url(new_url, key)
            emit(f"{'✔ 已更新' if ok else '✘ 失败'}：{msg}")
            continue

        if raw == str(extra + 2):
            ok, msg = PV.probe(key)
            emit(f"  [{'✔' if ok else '✘'}] {msg}")
            continue

        if raw == str(extra + 3):
            rows = PV.all_models(key)
            if not rows:
                emit("  （没查到模型；服务可能没开，下面是推荐目录）")
                rows = PV.catalog(key)
            emit(f"  共 {len(rows)} 个：")
            for r in rows:
                tag = "已装" if r.get("installed") else "可拉取"
                emit(f"   [{tag}] {r['name']}  "
                     f"{r.get('params') or '?'}  "
                     f"ctx={r.get('ctx') or '?'}  "
                     f"{r.get('size') or '?'}")
            continue

        if raw == str(extra + 4):
            name = input("要部署的模型名（回车用当前）：").strip()
            if not name:
                name = PV.current_model(key)
            if not name:
                emit("没有指定模型")
                continue
            emit("开始部署，输出如下（可随时 Ctrl+C 中断）：\n")
            ok, msg = PV.run_deploy(name, key, emit=emit)
            emit(f"\n{'✔' if ok else '✘'} {msg}")
            continue

        emit("无效选项")


def cmd_debug():
    """菜单 11：开启 DEBUG（比对引擎 → 写 $DEBUG=true → 关掉启动时的全量编译）"""
    import filepicker
    import game_scripts as GS
    import debug_tool as DT

    emit("\n[开启 DEBUG]")
    emit("  ① 识别 Essentials 版本，比对引擎的基本函数有没有被改过；")
    emit("  ② 往 mainFunction 里写 $DEBUG=true（等价于用调试模式启动游戏）；")
    emit("  ③ 关掉 debug 启动时「删 Data/*.dat + 全量重编译」这两步。")

    folder = filepicker.pick_dir(
        initial_dir=config.Runtime.last_dir or config.BASE_DIR,
        title="选择游戏根目录（里面有 Game.exe 和 Data）")
    if not folder:
        emit("已取消")
        return
    ok, why = GS.check_game_root(folder)
    if not ok:
        emit(f"✘ {why}：{folder}")
        return
    config.Runtime.set_dir(folder)

    # ★ 「只检测」已去掉：检测报告功能已从工具里删除，这里只留开启 / 还原
    raw = input("\n1=开启 / 2=还原 [1]: ").strip()
    if raw == "2":
        DT.restore(folder, emit=emit)
        return
    DT.enable_debug(folder, emit=emit, force=False)


def cmd_show_logs():
    """菜单 12：日志 / 环境检查"""
    import env_check

    log_dir = os.path.join(config.BASE_DIR, "logs")
    emit("\n[日志目录] " + log_dir)
    if not os.path.isdir(log_dir):
        emit("（暂无日志）")
        return

    files = sorted(f for f in os.listdir(log_dir)
                  if f.endswith(".log"))
    if not files:
        emit("（暂无日志）")
        return

    for f in files:
        p = os.path.join(log_dir, f)
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        emit(f"  {f}   ({size / 1024:.1f} KB)")

    today = time.strftime("%Y%m%d")
    target = os.path.join(log_dir, f"translate_{today}.log")
    if not os.path.exists(target):
        target = os.path.join(log_dir, files[-1])

    emit(f"\n--- {os.path.basename(target)} 末尾 40 行 ---")
    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in lines[-40:]:
            emit(line.rstrip())
    except Exception as e:
        emit(f"读取失败：{e}")

    emit("\n[环境检查]")
    result = env_check.check_all(verbose=False)
    for k, (ok, msg) in result.items():
        emit(f"  [{'✔' if ok else '✘'}] {k}: {msg}")

    emit("\n[检查更新]")
    try:
        import updater
        has, info = updater.check_update()
        if info.get("error"):
            emit(f"  获取失败：{info['error']}")
        elif has:
            emit(f"  发现新版本：{info.get('tag')}（当前 v{config.VERSION}）")
            emit(f"  下载地址：{info.get('url')}")
        else:
            emit(f"  当前已是最新版本 v{config.VERSION}")
    except Exception as e:
        emit(f"  检查更新失败：{e}")
