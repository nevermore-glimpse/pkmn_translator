# -*- coding: utf-8 -*-
r"""
术语检查：术语提取的「检查报告」，**改译名不走模型**。

为什么单独做一套
---------------
   名字类文件（*_NAMES / [编号] 名字区块）归术语提取管，不再进翻译流水线
   （见 term_extract.is_term_source_file）。可译完之后总会有不满意的译名：
   模型把 `Psychic` 译成「精神强念」而你想要「超能」，或者同一批里两条译法
   不一致。为此单开这个功能，与「重翻检查报告 / 术语更新后重翻」同型：

   · **检查报告**（check_terms）：只读缓存与术语表，列出问题条目
     （没译出来的、同词不同译的、译名可疑的）；
     界面上双击「译名」列即可改，点「应用」把改动同时写进
       ① 名字文件的**普通翻译缓存**（`*_cache.json`，按 key 增量改）
       ② 名字文件对应的译文文件（`*_translated.txt`，有的话）
       ③ 术语表的 AUTO 块（`term_dict.py`）
   原文列只读；**检查与「应用修改」都不调用模型，也不写任何报告文件**。
   另有 `retranslate()`：把选中条目的缓存 key 删掉后重走翻译流水线，
   **这一步会调用模型**（见「术语重翻」按钮）。

数据来源（v1.6.x 起）
---------------
   名字文件现在走**正常翻译流水线**（见 term_extract.run_extract），所以术语的
   「原文 → 译名」就在每个名字文件的普通翻译缓存
   `commands.cache_path_for(<名字文件>)` 里：
     · 只取「属于该名字文件的候选原文」那些 key（parse_names_file 得到候选集），
       同一文件里的对白等非名字条目一律不混进来；
     · 类别标签用名字文件的 section 经 label_of() 转中文。
   **不再有** `<目标名>_terms_cache.json` 那套独立缓存。

用法
----
    p = term_fix.plan(target)                  # 统计：多少条、几类有问题
    hits = term_fix.check_terms(target)        # 问题条目（不写文件）
    n = term_fix.apply_fixes(target, fixes)    # fixes = {原文: 新译名}
    st = term_fix.retranslate(target, items)   # 删缓存 + 走流水线重翻（调模型）

★ 本模块不写任何报告文件（`_terms_check.txt` 已移除）；问题条目只展示在
  GUI 的「术语检查报告」页里，改译名用「应用修改」直接写回三处。
"""
import io
import json
import os
import re

import config
from logger import get_logger

log = get_logger("term_fix")

# 问题类型的固定顺序（与 commands.REPORT_KIND_ORDER 同风格）
KIND_ORDER = ["译名为空", "同词不同译", "未翻（回显原文）",
              "译文残留英文", "疑似机翻残留"]

# 控制码：\xxx[...] 与 \xx 两种形式（与 _looks_untranslated 同一套正则）
_CTRL_CODE_RE = re.compile(r'\\[A-Za-z]\[[^\]]*\]|\\[A-Za-z]')
# ≥2 个连续拉丁字母（带音标的也算）＝ 译文里残留的英文
_LATIN_RUN_RE = re.compile(r'[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{2,}')


# ================================================================
# 读缓存 / 术语表
# ================================================================
def _sections(target):
    """
    读名字文件，返回只含**术语**的界面数据：

      [{"path": 名字文件, "label": 类别中文名,
        "cache_path": 它的普通翻译缓存,
        "items": {原文: 缓存里的译名（可能为空串）}}, ...]

    ★ 过滤依据是 term_extract.file_records：候选原文来自 parse_names_file，
      所以同一文件里的对白等普通条目不会被当成术语列出来。
    ★ 「缓存里完全没有该原文」的候选不算一条（还没翻过）—— 与改动前一致：
      改动前缓存里有什么就列什么。
    """
    import term_extract as TE

    out = []
    for rec in TE.file_records(target):
        out.append({"path": rec["path"], "label": rec["label"],
                    "cache_path": rec["cache_path"],
                    "items": dict(rec["present"])})
    return out


def _term_dict_pairs():
    """读 term_dict.py 的 TERM_DICT → {原文: 译文}（读不到返回空表）。"""
    if not os.path.exists(config.TERM_FILE):
        return {}
    ns = {}
    try:
        with io.open(config.TERM_FILE, "r", encoding="utf-8") as f:
            exec(f.read(), ns)
    except Exception as e:
        log.warning("读 term_dict.py 失败（按空表处理）：%s", e)
        return {}
    data = ns.get("TERM_DICT", {})
    return {str(k): str(v) for k, v in data.items()
            if isinstance(k, str) and isinstance(v, str)}


# ================================================================
# 计划 / 检查
# ================================================================
def plan(target):
    """
    统计一遍缓存里的术语（不调模型、不写文件）。

    返回 {"total", "sections", "in_dict", "not_in_dict", "problems",
          "cache_path"}
      · cache_path：名字文件的普通翻译缓存（多个文件时给它们共用的中间文件夹）
    """
    secs = _sections(target)
    pairs = _term_dict_pairs()
    lower_dict = {k.strip().lower(): (k, v) for k, v in pairs.items()}

    sections, total, in_dict, not_in_dict = {}, 0, 0, 0
    for s in secs:
        items = s["items"]
        sections[s["label"]] = sections.get(s["label"], 0) + len(items)
        for src in items:
            total += 1
            if src.strip().lower() in lower_dict:
                in_dict += 1
            else:
                not_in_dict += 1

    caches = [s["cache_path"] for s in secs if s["cache_path"]]
    if len(caches) == 1:
        cache_path = caches[0]
    elif caches:
        cache_path = os.path.dirname(caches[0])
    else:
        cache_path = ""

    problems = check_terms(target)
    return {
        "total": total,
        "sections": sections,
        "in_dict": in_dict,
        "not_in_dict": not_in_dict,
        "problems": len(problems),
        "cache_path": cache_path,
    }


def check_terms(target):
    """
    只读缓存与术语表，找出有问题的条目。

    返回 [{kind, section, src, dst, detail, path}, ...]
      · kind   问题类型（见 KIND_ORDER）
      · section 类别名（中文）
      · src/dst 原文 / 缓存里的译名
      · detail  给人看的一句话说明
      · path    该条目所属的名字文件路径（界面「术语重翻」按它分组）

    ★ 一条条目按顺序判定：译名为空 → 未翻（回显原文）→ 译文残留英文 →
      疑似机翻残留，前四者**互斥**（命中即 continue）；「同词不同译」可叠加。
    """
    hits = []
    for s in _sections(target):
        label = s["label"]
        path = s["path"]
        # 同一类别内的同形异译先自己报
        by_lower = {}
        for src, dst in s["items"].items():
            dst = (dst or "").strip()
            if not dst:
                hits.append({"kind": "译名为空", "section": label,
                             "src": src, "dst": "", "path": path,
                             "detail": "缓存里没有译名（模型当时没返回）"})
                continue
            if dst == src.strip():
                hits.append({"kind": "未翻（回显原文）", "section": label,
                             "src": src, "dst": dst, "path": path,
                             "detail": "译名与原文相同，模型没翻"})
                continue
            resid = _english_residue(dst)
            if resid:
                hits.append({"kind": "译文残留英文", "section": label,
                             "src": src, "dst": dst, "path": path,
                             "detail": resid})
                continue
            if _looks_untranslated(dst):
                hits.append({"kind": "疑似机翻残留", "section": label,
                             "src": src, "dst": dst, "path": path,
                             "detail": "译名里几乎全是控制码 / 符号，不像译文"})
            key = src.strip().lower()
            if key in by_lower and by_lower[key] != dst:
                hits.append({
                    "kind": "同词不同译", "section": label,
                    "src": src, "dst": dst, "path": path,
                    "detail": f"同一类别里先记的是「{by_lower[key]}」"})
            else:
                by_lower[key] = dst
    return hits


def _english_residue(text):
    """
    译名里是否残留英文 / 控制码，是则返回一句说明，否则返回 ""。

      · 先剥掉控制码，剩下的文本里含 ≥2 个连续拉丁字母（带音标的也算）
        → 残留英文（单个字母如 X 不算，纯符号/数字也不算）；
      · 译名里**本身**就写着控制码（`\\xxx[...]` / `\\xx`）
        → 残留控制码（这种条目 _looks_untranslated 会放过去，
          因为它剥掉控制码后还剩中文，必须单独报出来）。
    """
    if not text:
        return ""
    left = _CTRL_CODE_RE.sub('', text)
    m = _LATIN_RUN_RE.search(left)
    if m:
        return f"译文里残留英文：{m.group(0)}"
    m = _CTRL_CODE_RE.search(text)
    if m:
        return f"译文里残留控制码：{m.group(0)}"
    return ""



def _looks_untranslated(text):
    """剥掉控制码 / 符号后不含任何中日常用文字 → 疑似没翻出来。"""
    if not text:
        return True
    t = re.sub(r'\\[A-Za-z]\[[^\]]*\]', '', text)     # \xxx[...]
    t = re.sub(r'\\[A-Za-z]', '', t)                  # \n \c 之类
    t = re.sub(r'[\[\]{}<>@#~%$^&*_=|/\\\'"“”‘’()（）…·・.,;:!?！？，。、；：\s]',
               '', t)
    return not t


# ================================================================
# 应用修正（不走模型）
# ================================================================
def apply_fixes(target, fixes):
    """
    把 {原文: 新译名} 同时写到三处，返回统计 dict。

      ① 名字文件的普通翻译缓存  *_cache.json（**按 key 增量改**）
      ② 名字文件的译文文件      *_translated.txt（存在才改）
      ③ 术语表 AUTO 块          term_dict.py

    ★ 全程不调用模型。
    ★ 原文列在界面上是只读的，所以这里只需要处理译文。
    """
    import auto_terms

    fixes = {str(k): str(v or "").strip()
             for k, v in (fixes or {}).items() if str(k).strip()}
    if not fixes:
        return {"cache": 0, "dict": 0, "files": 0, "file_list": [],
                "missing": 0}

    # ---- ① 缓存（按 key 增量改，其余条目原样保留）----
    n_cache = _apply_to_caches(target, fixes)

    # ---- ③ 术语表 ----
    # 只把「有译名」的写进 AUTO 块；原文已在 AUTO 块的原地改译文，
    # 不在 AUTO 块的按新术语追加。
    in_dict = set(_term_dict_pairs().keys())
    to_merge, to_update = {}, {}
    for src, new in fixes.items():
        if not new:
            continue
        if src in in_dict:
            to_update[src] = new
        else:
            to_merge[src] = new
    n_dict = 0
    if to_update:
        try:
            import term_sync as TS
            n_dict += TS.save_term_values(to_update)
        except Exception as e:
            log.warning("更新术语表已有条目失败：%s", e)
    if to_merge:
        conflicts = []
        try:
            n_dict += auto_terms.merge_into_term_dict(
                to_merge, conflicts_out=conflicts)
        except Exception as e:
            log.warning("合并新术语失败：%s", e)

    # ---- ② 译文文件 ----
    n_files, file_list, missing = _apply_to_translated(target, fixes)

    # 让后续翻译立刻用上新译名
    try:
        import processor as PR
        PR.load_terms(force=True)
    except Exception as e:
        log.warning("术语表重载失败：%s", e)

    return {"cache": n_cache, "dict": n_dict, "files": n_files,
            "file_list": file_list, "missing": missing}


def _apply_to_caches(target, fixes):
    """
    把新译名写回各名字文件的**普通翻译缓存**（返回改动条数）。

    ★ 只改 fixes 里那些 key 的值，**其余条目原样保留** —— 缓存里同时躺着
      这个文件的所有普通句子译文（名字文件里也可能有对白等行），整体重写会
      把它们整片抹掉。
    ★ 只改「缓存里已经有」且「属于该文件候选原文」的 key：不改写非名字条目，
      也不凭空新增条目。
    ★ 多个名字文件的缓存是分开的（各是各的 `_cache.json`），所以按文件逐个来。
    """
    import term_extract as TE

    n = 0
    for rec in TE.file_records(target):
        cp = rec["cache_path"]
        if not cp or not os.path.isfile(cp):
            continue
        try:
            with io.open(cp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log.warning("读翻译缓存失败（跳过 %s）：%s", cp, e)
            continue
        if not isinstance(data, dict):
            log.warning("翻译缓存结构异常（跳过 %s）", cp)
            continue

        names = set(rec["names"])
        changed = 0
        for src, new in fixes.items():
            if src not in names or src not in data:
                continue
            if not new:
                # 译名被清空：保留原值，避免把缓存写成空
                log.info("译名为空，跳过缓存更新：%s", src)
                continue
            if data[src] != new:
                data[src] = new
                changed += 1
        if changed:
            _save_json(cp, data)
            log.info("翻译缓存已更新：%s（%d 条，其余 %d 条原样保留）",
                     cp, changed, len(data) - changed)
            n += changed
    return n


def _save_json(path, data):
    """原子写回 json（复用 cache.atomic_replace：Windows 上带占用重试）。"""
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    from cache import atomic_replace
    atomic_replace(tmp, path)


def _apply_to_translated(target, fixes):
    """
    把新译名写进名字文件对应的 `*_translated.txt`（有才写）。

    返回 (改过的文件数, [文件路径], 缺译文的条目数)。

    ★ 行号必须按**源文件**算：译文文件里「原文行 / 译文行」已经不配对
      （第二行是中文），直接 extract_entries 会把它们全当成特殊情况，
      一条都匹配不上。所以先解析源文件拿到「译文行号 ← 原文」的映射，
      再拿这个映射去改译文文件的对应行。
    ★ 原文与第二行相同，所以译文行就是 entries 里的目标行；
      与 commands 里「应用已编辑」同一个写法。
    """
    import parser as P
    import term_extract as TE

    files = TE.find_names_files(target)
    n_files, file_list, missing = 0, [], 0

    for src_path in files:
        out_path = _translated_path_for(src_path)
        if not out_path or not os.path.isfile(out_path):
            continue

        # ① 源文件 → {原文: 译文行号}
        try:
            src_lines, _nl = P.read_file(src_path, config.INPUT_ENCODING)
        except Exception as e:
            log.warning("读源文件失败（跳过）：%s：%s", src_path, e)
            continue
        entries, _special = P.extract_entries(src_lines)
        line_of = {}
        for idx, src in entries:
            key = (src or "").strip()
            if key and key not in line_of:
                line_of[key] = idx

        # ② 译文文件 → 按同一批行号替换
        try:
            lines, newline = P.read_file(out_path, config.OUTPUT_ENCODING)
        except Exception as e:
            log.warning("读译文失败（跳过）：%s：%s", out_path, e)
            continue

        changed = 0
        for src, new in fixes.items():
            idx = line_of.get(src.strip())
            if idx is None:
                missing += 1
                continue
            if idx >= len(lines):
                missing += 1
                continue
            indent = re.match(r'^([ \t]*)', lines[idx]).group(1)
            new_line = indent + new
            if lines[idx] != new_line:
                lines[idx] = new_line
                changed += 1
        if changed:
            try:
                with io.open(out_path, "w", encoding=config.OUTPUT_ENCODING,
                             newline="") as f:
                    f.write(newline.join(lines))
                n_files += 1
                file_list.append(out_path)
                log.info("译文文件已更新：%s（%d 条）", out_path, changed)
            except Exception as e:
                log.warning("写译文失败：%s：%s", out_path, e)
    return n_files, file_list, missing


def _translated_path_for(src_path):
    """名字文件 → 对应译文文件路径（与源文件同目录）。"""
    stem, _ext = os.path.splitext(os.path.basename(src_path))
    return os.path.join(os.path.dirname(os.path.abspath(src_path)),
                        f"{stem}_translated.txt")


# ================================================================
# 术语重翻（删缓存 + 走正常翻译流水线 —— ★ 会调用模型）
# ================================================================
def retranslate(target, items, cancel=None, progress=None,
                batch_term_hook=None):
    """
    把选中的条目**重翻一遍**：先删掉它们在翻译缓存里的 key，再让它们走
    一遍正常翻译流水线（与菜单 2「翻译」同一条：重新解析、整句术语直译、
    术语注入 prompt、分批送模型、续翻）。

      items = [{"src": 原文, "path": 该条目所属的名字文件}, ...]

    · 按 path 分组；每个文件：set_input → 删这些 key → save → 读源文件 →
      commands._translate_core(path, lines, newline, show_header=False,
                               batch_term_hook=batch_term_hook)；
    · batch_term_hook 可选，由调用方传入（界面传
      term_extract.make_batch_term_hook(None)）：每批翻完立刻并进术语表并
      重载，同一文件后续批次立刻用上新译名。**这里不 import term_extract**，
      只把回调转发下去；传 None 时行为与不开逐批提取完全一致。
      重翻时缓存里只剩选中的这批 key，_translate_core 的 todo 就是它们，
      所以回调不需要再按候选原文过滤。
    · 每个文件独立 try/except：一个文件失败只 log.warning，继续下一个；
    · cancel() 在**每个文件**开始前问一次，返回真值就停下；
    · progress(done, total, path) 可选，只用来刷界面。

    ★ 与 apply_fixes 的区别就在这儿：apply_fixes 只写文件、不调模型，
      重翻要调模型。

    不 import term_extract：条目属于哪个文件由 items 的 path 直接给出。
    返回 {"files": 真正跑完的文件数, "removed": 删掉的缓存条数,
          "translated": 参与重翻的条目数}
    """
    from cache import Cache
    import parser as P
    import commands as C

    by_path = {}
    for it in (items or []):
        it = it or {}
        src = str(it.get("src") or "")
        path = str(it.get("path") or "")
        if not src or not path:
            continue
        by_path.setdefault(path, set()).add(src)

    paths = sorted(by_path)
    total = sum(len(v) for v in by_path.values())
    log.info("术语重翻开始：目标 %s，%d 条 / %d 个文件", target, total, len(paths))

    files, removed = 0, 0
    for i, path in enumerate(paths, 1):
        if cancel and cancel():
            log.info("术语重翻已取消（处理到 %d/%d 个文件）", i - 1, len(paths))
            break
        if progress:
            try:
                progress(i - 1, len(paths), path)
            except Exception:
                pass
        try:
            config.Runtime.set_input(path)
            cache = Cache(config.Runtime.cache_file)
            n = cache.remove_many(by_path[path])
            cache.save(force=True)
            removed += n

            lines, newline = P.read_file(path, config.INPUT_ENCODING)
            C._translate_core(path, lines, newline, show_header=False,
                              batch_term_hook=batch_term_hook)
            files += 1
            log.info("术语重翻：%s（删缓存 %d 条）", path, n)
        except Exception as e:
            log.warning("术语重翻失败（跳过 %s）：%s", path, e)

    return {"files": files, "removed": removed, "translated": total}
