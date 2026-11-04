# -*- coding: utf-8 -*-
r"""
问题条目导出 / 导入（术语检查报告 + 重翻检查报告）。

为什么要有这个
--------------
    检查报告里的问题条目有时很多，在表格里一条条双击改太慢。更省事的做法是：

      ① 点「导出问题术语 / 导出问题句子」→ 把问题条目写成
         `<游戏根目录>/problem/problem_term_<文件名>.json`（句子同理
         `problem_sentence_<文件名>.json`）；
      ② 用任何文本编辑器 / 交给别人批量翻，只改里面的**译文值**；
      ③ 点「导入已翻问题术语 / 导入已翻问题句子」→ 把译文写回

           · 名字文件的翻译缓存 `*_cache.json`（没有就新建条目）
           · 名字文件的译文文件 `*_translated.txt`（有就改对应行）
           · 句子还要记一条「已编辑」，刷新报告后归入「已编辑」类型

         最后界面自动刷新报告。

文件格式（就是一份缓存）
------------------------
    {
      "type": "term",
      "file": "…/Text_chinese_game/ITEM_NAMES.txt",   ← 属于哪个文件
      "cache": "…/翻译中间文件/ITEM_NAMES_cache.json", ← 写回哪份缓存
      "note": "改 items 里每条的值就是新译名……",
      "items": {"Eevee": "伊布", "Potion": ""}         ← 原文: 译文
    }

    ★ items 就是「原文 → 译文」的缓存形式，与 `*_cache.json` 同一个语义：
      改右边那一列即可，键（原文）别动。
    ★ 值留空 / 等于原文 = 这条没翻，导入时跳过（不会把缓存写成空）。

句子缓存多一个 hit_terms（参考，不参与导入）
--------------------------------------------
    problem_sentence_*.json 里除 items 外，还带每句**命中的术语**：

      "hit_terms": {
        "原文句子": {"Profesor Oak": "大木博士", "Pokedex": "图鉴"}
      }

    ★ 与翻译时注入 prompt 的术语表同一口径，外部批量翻这些句子时照它用译名。
    ★ 只是参考：导入时只读 items，hit_terms 原样忽略。
"""
import glob
import json
import os

from logger import get_logger

log = get_logger("problem_io")

PROBLEM_DIR_NAME = "problem"
TERM_PREFIX = "problem_term_"
SENTENCE_PREFIX = "problem_sentence_"

_NOTE_TERM = ("只改 items 里的**译文**（冒号右边），键（原文）别动。"
              "改完回程序点「导入已翻问题术语」，会写回翻译缓存与译文文件。"
              "留空或与原文相同 = 视为没翻，导入时跳过。")
_NOTE_SENTENCE = ("只改 items 里的**译文**（冒号右边），键（原文）别动。"
                  "hit_terms 是本句命中的「术语原文 → 术语译文」，翻的时候参考它，"
                  "不用改，导入时原样忽略。"
                  "改完回程序点「导入已翻问题句子」，会写回翻译缓存与译文文件，"
                  "并记为「已编辑」。留空或与原文相同 = 视为没翻，导入时跳过。")


# ================================================================
# 路径
# ================================================================
def game_root_of(path):
    """
    从任意路径往上找「游戏根目录」（含 Data/Scripts.rxdata 或 Game.exe 的那层）。

    找不到就退回 path 本身（文件夹）或它的父目录 —— 至少能落盘。
    """
    p = str(path or "")
    if not p:
        return os.getcwd()
    p = os.path.abspath(p if os.path.isdir(p) else os.path.dirname(p))
    cur = p
    while True:
        data = os.path.join(cur, "Data")
        if os.path.isdir(data) and (
                os.path.isfile(os.path.join(data, "Scripts.rxdata"))
                or os.path.isfile(os.path.join(data, "MapInfos.rxdata"))
                or os.path.isfile(os.path.join(cur, "Game.exe"))):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return p


def problem_dir(basis, create=True):
    """`<游戏根目录>/problem`（create=True 时顺手建出来）。"""
    root = game_root_of(basis)
    d = os.path.join(root, PROBLEM_DIR_NAME)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def _basis_path(basis):
    """basis 可以是路径、也可以是路径列表（检查报告页传的是报告列表）。"""
    if isinstance(basis, (list, tuple)):
        for p in basis:
            if p:
                return p
        return ""
    return str(basis or "")


def _stem(path):
    return os.path.splitext(os.path.basename(str(path or "")))[0]


# ================================================================
# ★ 已经手工编辑过的条目：不再当作「问题」导出
# ================================================================
def edited_keys_of(src_path):
    """
    该源文件**已手工编辑过**的原文集合（读 `<缓存>_cache_edited.json`）。

    ★ 来源：报告里双击改句（`Cache.save_edit`）、导入已翻问题句子、
      术语检查报告「应用修改」写进缓存的那些条目。
    ★ 这些是用户自己改好的，导出成「问题」再交给别人改等于让人白改一遍，
      所以导出时统一跳过。
    ★ 读不到（没编辑过 / 缓存搬走了）一律返回空集合，绝不让导出挂掉。
    """
    src = str(src_path or "").strip()
    if not src:
        return set()
    try:
        import commands as C
        from cache import load_edits
        data = load_edits(C._edited_path_for(src))
        return {str(k).strip() for k in data if str(k).strip()}
    except Exception as e:                  # noqa: BLE001
        log.debug("读手工编辑记录失败（按空处理）：%s：%s", src, e)
        return set()


# ================================================================
# ★ 命中术语（导出问题句子时附带，供人工/外部翻译参考）
# ================================================================
def hit_terms_for(src_text, section=None):
    """
    一句原文命中的术语 → {术语原文: 术语译文}（保序；没有命中返回 {}）。

    ★ 与翻译流水线同一口径（见 commands._translate_batch）：
      split_prefix → apply_pre → strip_newlines → find_terms，
      译文用 render_term_dst（多译文按 section 定向，与送模型的一致）。
      这样「导出问题句子」里给的参考，和模型当时看到的术语表是同一批词。

    全程兜异常：术语表读不了 / processor 缺函数 → 返回空，绝不让导出挂掉。
    """
    s = str(src_text or "").strip()
    if not s:
        return {}
    try:
        import config
        import processor as PR
        import replacement as REPL

        PR.load_terms()
        if getattr(config, "PREFIX_DICT_ENABLE", True):
            _prefix, body = PR.split_prefix(s)
        else:
            body = s
        body, _n = REPL.apply_pre(body)
        hits = PR.find_terms(PR.strip_newlines(body))
        if not hits:
            return {}
        out = {}
        for term_src, _term_dst in hits:
            if not term_src or term_src in out:
                continue
            try:
                dst = PR.render_term_dst(term_src, section=section)
            except Exception:               # noqa: BLE001
                dst = _term_dst
            if dst:
                out[term_src] = dst
        return out
    except Exception as e:                  # noqa: BLE001
        log.debug("命中术语查询失败（忽略，不影响导出）：%s", e)
        return {}


# ================================================================
# 读写 json
# ================================================================
def _write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    from cache import atomic_replace
    atomic_replace(tmp, path)
    return path


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning("读问题缓存失败（跳过 %s）：%s", path, e)
        return {}


def _items_of(data):
    """取 items（缓存形式的 {原文: 译文}），兼容被手改成 list 的情况。"""
    items = data.get("items")
    if isinstance(items, dict):
        return {str(k): ("" if v is None else str(v))
                for k, v in items.items() if str(k).strip()}
    if isinstance(items, list):
        out = {}
        for it in items:
            if isinstance(it, dict):
                k = str(it.get("src") or it.get("原文") or "")
                v = it.get("dst", it.get("译文", ""))
                if k.strip():
                    out[k] = "" if v is None else str(v)
        return out
    return {}


# ================================================================
# 术语：导出 / 导入
# ================================================================
def export_terms(target, hits):
    """
    把术语检查报告里的问题条目按**名字文件**分组导出。

      target：当前检查目标（文件 / 文件夹），用来定位游戏根目录
      hits  ：term_fix.check_terms 的结果（或界面筛选后显示的那批）

    返回 {"dir", "files": [路径], "count", "groups": N}
    """
    hits = [h for h in (hits or []) if isinstance(h, dict) and h.get("src")]
    if not hits:
        return {"dir": problem_dir(target), "files": [], "count": 0,
                "groups": 0}

    import commands as C

    groups = {}
    for h in hits:
        path = str(h.get("path") or "")
        if not path:
            continue
        groups.setdefault(path, []).append(h)

    out_dir = problem_dir(target)
    files = []
    count = 0
    skipped_edited = 0
    for path, hs in groups.items():
        skip = edited_keys_of(path)
        items = {}
        for h in hs:
            src = str(h.get("src") or "").strip()
            if not src:
                continue
            # ★ 已经手工改过的译名不再当问题导出
            if src in skip:
                skipped_edited += 1
                continue
            items.setdefault(src, str(h.get("dst") or ""))
        if not items:
            continue
        payload = {
            "type": "term",
            "file": os.path.abspath(path),
            "cache": C.cache_path_for(path) or "",
            "note": _NOTE_TERM,
            "items": items,
        }
        out = os.path.join(out_dir, f"{TERM_PREFIX}{_stem(path)}.json")
        _write_json(out, payload)
        files.append(out)
        count += len(items)

    log.info("导出问题术语：%d 条 / %d 个文件 → %s（跳过已编辑 %d 条）",
             count, len(files), out_dir, skipped_edited)
    return {"dir": out_dir, "files": files, "count": count,
            "groups": len(files), "edited": skipped_edited}


def import_terms(basis):
    """
    读 `problem/problem_term_*.json`，把译文写回各名字文件的缓存与译文文件。

    ★ 缓存里没有这条原文就**新增**（用户明确要求：没有就新增缓存）。
    ★ 只改缓存 + 译文文件，不动术语表（术语表由提取/应用修改维护）。

    返回 {"dir", "files", "applied", "added", "updated", "file_lines",
          "missing", "skipped"}
    """
    import commands as C
    import term_fix as TFX

    out_dir = problem_dir(basis, create=False)
    pats = os.path.join(out_dir, f"{TERM_PREFIX}*.json")
    paths = sorted(glob.glob(pats))
    st = {"dir": out_dir, "files": 0, "applied": 0, "added": 0,
          "updated": 0, "file_lines": 0, "missing": 0, "skipped": 0}
    if not paths:
        return st

    for p in paths:
        data = _read_json(p)
        items = _items_of(data)
        if not items:
            continue

        src_file = str(data.get("file") or "")
        if not (src_file and os.path.isfile(src_file)):
            found = _find_by_stem(_stem(src_file) or _stem_from_json_name(p),
                                  os.path.dirname(p))
            if found:
                src_file = found
        if not (src_file and os.path.isfile(src_file)):
            log.warning("问题术语缓存找不到对应文本（跳过）：%s", p)
            st["missing"] += 1
            continue

        # ★ 缓存路径优先用导出时记下的那份；它不存在（比如中间文件后来
        #   搬进了「翻译中间文件」夹）就退回当前的口径，别凭空另建一份。
        recorded = str(data.get("cache") or "")
        canonical = C.cache_path_for(src_file) or ""
        cache_path = recorded if (recorded and os.path.isfile(recorded)) \
            else (canonical or recorded)
        if not cache_path:
            st["missing"] += 1
            continue

        fixes, skipped = _fixes_from_items(items)
        st["skipped"] += skipped
        if not fixes:
            continue

        # ① 缓存：有就改，没有就新增
        from cache import Cache
        cache = Cache(cache_path)
        added = updated = 0
        for src, dst in fixes.items():
            old = cache.get(src)
            if old is None:
                added += 1
            elif str(old) != dst:
                updated += 1
            cache.put(src, dst)
        cache.save(force=True)

        # ② 译文文件（有就改对应行）
        n_lines, _ok = TFX.apply_to_translated_file(src_file, fixes)

        st["files"] += 1
        st["applied"] += len(fixes)
        st["added"] += added
        st["updated"] += updated
        st["file_lines"] += n_lines
        log.info("导入问题术语：%s ← %s（%d 条，新增缓存 %d / 改 %d）",
                 src_file, os.path.basename(p), len(fixes), added, updated)

    return st


# ================================================================
# 句子：导出 / 导入
# ================================================================
def export_sentences(basis, items):
    """
    把重翻检查报告里的问题句子按**源文件**分组导出。

      basis：检查报告路径或它们的列表（用来定位游戏根目录）
      items：[(报告路径, hit), ...]（GUI 的 report_hits 就是这形态）

    ★ 缓存里额外带一份 `hit_terms`：每句命中的「术语原文 → 术语译文」，
      与翻译时注入 prompt 的术语表同一口径，供外部/人工翻这些句子时参考。
      只作参考，导入时忽略（写回只看 items）。

    返回 {"dir", "files", "count", "groups", "terms", "edited"}
    """
    import commands as C

    groups = {}
    skipped_edited = 0
    for report_path, h in (items or []):
        if not isinstance(h, dict) or not h.get("src"):
            continue
        # ★ 「已编辑」本来就不是问题（手工改过的句子），不导出
        if str(h.get("kind") or "") in C.MANUAL_KINDS:
            skipped_edited += 1
            continue
        src = C.source_path_for_report(report_path) or ""
        key = src or str(report_path or "")
        groups.setdefault(key, {"report": str(report_path or ""),
                               "items": {}})
        groups[key]["items"].setdefault(str(h.get("src")).strip(),
                                        str(h.get("dst") or ""))

    out_dir = problem_dir(_basis_path(basis))
    files, count, n_terms = [], 0, 0
    for src, g in groups.items():
        skip = edited_keys_of(src)
        its = {k: v for k, v in g["items"].items() if k and k not in skip}
        skipped_edited += len(g["items"]) - len(its)
        if not its:
            continue
        # 命中术语按句子算（同一文件的 section 判一次就够）
        sec = _section_of(src)
        hit_terms = {}
        for k in its:
            t = hit_terms_for(k, section=sec)
            if t:
                hit_terms[k] = t
        n_terms += sum(len(v) for v in hit_terms.values())
        stem = _stem(src) or _stem(g.get("report")) or "unknown"
        payload = {
            "type": "sentence",
            "source": os.path.abspath(src) if src else "",
            "report": g.get("report") or "",
            "cache": C.cache_path_for(src) if src else "",
            "note": _NOTE_SENTENCE,
            "items": its,
            # ★ 参考用：{该句原文: {术语原文: 术语译文}}，导入时不读它
            "hit_terms": hit_terms,
        }
        out = os.path.join(out_dir, f"{SENTENCE_PREFIX}{stem}.json")
        _write_json(out, payload)
        files.append(out)
        count += len(its)

    log.info("导出问题句子：%d 条 / %d 个文件（附带命中术语 %d 条，"
             "跳过已编辑 %d 条）→ %s",
             count, len(files), n_terms, skipped_edited, out_dir)
    return {"dir": out_dir, "files": files, "count": count,
            "groups": len(files), "terms": n_terms,
            "edited": skipped_edited}


def _section_of(src_path):
    """源文件的文本类别（与 commands._file_section 同一判据）；判不出 → None。"""
    if not src_path:
        return None
    try:
        import cat_prompts as CP
        return CP.section_for(src_path)
    except Exception:                       # noqa: BLE001
        return None


def import_sentences(basis):
    """
    读 `problem/problem_sentence_*.json`，把译文写回缓存 + 译文文件，
    并记入「已编辑」（刷新报告后这些句子归入「已编辑」类型）。

    返回 {"dir", "files", "applied", "skipped", "missing", "failed"}
    """
    import commands as C

    out_dir = problem_dir(basis, create=False)
    paths = sorted(glob.glob(os.path.join(out_dir, f"{SENTENCE_PREFIX}*.json")))
    st = {"dir": out_dir, "files": 0, "applied": 0, "skipped": 0,
          "missing": 0, "failed": 0}
    if not paths:
        return st

    for p in paths:
        data = _read_json(p)
        items = _items_of(data)
        if not items:
            continue

        src_file = str(data.get("source") or "")
        if not (src_file and os.path.isfile(src_file)):
            src_file = C.source_path_for_report(str(data.get("report") or ""))
        if not (src_file and os.path.isfile(src_file)):
            src_file = _find_by_stem(_stem_from_json_name(p), os.path.dirname(p))
        if not (src_file and os.path.isfile(src_file)):
            log.warning("问题句子缓存找不到对应文本（跳过）：%s", p)
            st["missing"] += 1
            continue

        fixes, skipped = _fixes_from_items(items)
        st["skipped"] += skipped
        if not fixes:
            continue

        n = 0
        for src, dst in fixes.items():
            try:
                # 既写缓存 + 编辑记录，也顺手改译文文件里那一行
                C.save_report_edit_and_apply(src, dst, src_path=src_file)
                n += 1
            except Exception as e:               # noqa: BLE001
                log.warning("写入问题句子失败（跳过 %s）：%s", src[:30], e)
                st["failed"] += 1
        st["files"] += 1
        st["applied"] += n
        log.info("导入问题句子：%s ← %s（%d 条）",
                 src_file, os.path.basename(p), n)

    return st


# ================================================================
# 小工具
# ================================================================
def _fixes_from_items(items):
    """{原文: 译文} → 只留真的翻了的那几条（空 / 等于原文的跳过）。"""
    fixes, skipped = {}, 0
    for src, dst in items.items():
        s = str(src or "").strip()
        d = str(dst or "").strip()
        if not s:
            continue
        if not d or d == s:
            skipped += 1
            continue
        fixes[s] = d
    return fixes, skipped


def _stem_from_json_name(path):
    name = _stem(path)
    for pre in (TERM_PREFIX, SENTENCE_PREFIX):
        if name.startswith(pre):
            return name[len(pre):]
    return name


def _find_by_stem(stem, start_dir):
    """
    按文件名主干在「游戏根目录」里找文本文件（用户在别处打开过 problem 目录
    也不至于找不到原文）。只在游戏根目录下递归，最多扫 4000 个 .txt。
    """
    if not stem:
        return ""
    root = game_root_of(start_dir)
    want = f"{stem.lower()}.txt"
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__")]
        for f in filenames:
            low = f.lower()
            if not low.endswith(".txt"):
                continue
            seen += 1
            if seen > 4000:
                return ""
            if low == want:
                return os.path.join(dirpath, f)
    return ""


def known_problem_files(basis):
    """当前 problem 目录里已有的缓存（界面提示用）。"""
    d = problem_dir(basis, create=False)
    if not os.path.isdir(d):
        return []
    return sorted(glob.glob(os.path.join(d, "problem_*.json")))
