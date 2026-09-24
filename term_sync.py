# -*- coding: utf-8 -*-
"""
术语更新后重翻：
  1. 维护一份"上次重翻时的术语基准"快照（key:value）
  2. 对比当前 term_dict.py，找出：
       · 新增的术语
       · 删除的术语
       · 译文被修改的术语
  3. 在缓存里找出包含"新增"或"修改"术语的句子
  4. 让上层删除这些缓存并重翻

兼容性：
  · 旧版快照（terms 只是 key 列表）可读，但无法识别"译文修改"，
    首次运行本版本后会升级为 {key: value} 格式
"""
import json
import os
import re

import config
from logger import get_logger

log = get_logger("term_sync")

SNAPSHOT_FILE = os.path.join(config.BASE_DIR, "term_dict.snapshot.json")


# ================================================================
# 术语加载
# ================================================================
def load_current_terms():
    """读取 term_dict.py，返回 {源语言: 译文}。"""
    if not os.path.exists(config.TERM_FILE):
        return {}
    ns = {}
    with open(config.TERM_FILE, "r", encoding="utf-8") as f:
        exec(f.read(), ns)
    return ns.get("TERM_DICT", {})


def _normalize_key(k):
    """归一化原文 key（去空格 + 小写），用于存在性比较。"""
    return k.strip().lower()


# ================================================================
# 快照
# ================================================================
def snapshot_exists():
    return os.path.exists(SNAPSHOT_FILE)


def load_snapshot():
    """
    返回上次快照的 {key: value}；
    若不存在则返回 None；
    若为旧格式（terms 是 key 列表），value 用空串代替。
    """
    if not os.path.exists(SNAPSHOT_FILE):
        return None
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        terms = data.get("terms")

        # 新格式：dict
        if isinstance(terms, dict):
            return terms
        # 旧格式：list of keys
        if isinstance(terms, list):
            return {k: "" for k in terms}

        log.warning("快照格式无法识别：%r", type(terms).__name__)
        return None
    except Exception as e:
        log.warning("快照读取失败：%s", e)
        return None


def save_snapshot(terms):
    """
    写入快照。
    terms: {key: value} 字典（直接来自 load_current_terms()）。
    """
    data = {
        "saved_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "count":    len(terms),
        "terms":    {k: v for k, v in sorted(terms.items())},
    }
    tmp = SNAPSHOT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SNAPSHOT_FILE)
    log.info("快照已保存：%d 条 → %s", len(terms), SNAPSHOT_FILE)


# ================================================================
# 对比
# ================================================================
def diff_terms():
    """
    对比当前 term_dict.py 与上次快照。

    返回 (added, removed, modified, old_was_keyonly)：
      · added               : 新增术语 key 列表（排序）
      · removed             : 删除术语 key 列表（排序）
      · modified            : 译文变化的术语 key 列表（排序）
      · old_was_keyonly     : 上次快照是旧格式（只有 key），此时 modified 恒为空

    首次使用（无快照）→ 返回 (None, None, None, False)
    """
    current = load_current_terms()
    old = load_snapshot()

    if old is None:
        return None, None, None, False

    # 判断旧快照是否是"只有 key 没有 value"的旧格式
    old_was_keyonly = bool(old) and all(v == "" for v in old.values())

    # 归一化索引：{norm_key: (原始 key, value)}
    cur_index = {_normalize_key(k): (k, v) for k, v in current.items()}
    old_index = {_normalize_key(k): (k, v) for k, v in old.items()}

    cur_keys = set(cur_index.keys())
    old_keys = set(old_index.keys())

    added   = sorted(cur_index[n][0] for n in (cur_keys - old_keys))
    removed = sorted(old_index[n][0] for n in (old_keys - cur_keys))

    modified = []
    if not old_was_keyonly:
        for n in (cur_keys & old_keys):
            _, old_v = old_index[n]
            _, new_v = cur_index[n]
            # 只有新值非空、且真正不同才算修改
            if new_v and old_v != new_v:
                modified.append(cur_index[n][0])
        modified.sort()

    return added, removed, modified, old_was_keyonly


# ================================================================
# 命中的缓存
# ================================================================
def _build_patterns(terms):
    """为每个术语生成词边界正则。跳过含特殊字符的。"""
    word_chars = r'\w\u00C0-\u024F'
    pats = []
    for t in terms:
        if not t or '\\' in t or '[' in t or ']' in t:
            continue
        try:
            pats.append((t, re.compile(
                r'(?<![' + word_chars + r'])' +
                re.escape(t) +
                r'(?![' + word_chars + r'])')))
        except re.error:
            continue
    return pats


def find_affected_cache(cache_data, terms):
    """
    在缓存的所有 key（原文）里，找出包含任一给定术语的句子。
    terms: 术语列表（可以是 added、modified 或两者合并）
    返回 [(key, 命中的术语), ...]
    """
    if not terms:
        return []

    pats = _build_patterns(terms)
    hits = []
    for key in cache_data:
        for term, pat in pats:
            if pat.search(key):
                hits.append((key, term))
                break
    return hits


# ================================================================
# 术语字典读写（GUI 术语表编辑用）
# ================================================================
# 匹配 "key": "value",  形式的一行（兼容末尾注释）
_PAIR_LINE_RE = re.compile(
    r'^(\s*)("(?:[^"\\]|\\.)*")(\s*:\s*)("(?:[^"\\]|\\.)*")(,?)(\s*(?:#.*)?)$'
)


def _split_lines_keepends(text):
    return text.splitlines()


def load_auto_block():
    """
    读取 term_dict.py 中 AUTO 块（自动提取术语）里的条目。
    返回 [(原文, 译文), ...]，按文件顺序。
    """
    try:
        import auto_terms
        start_mark, end_mark = auto_terms.AUTO_START, auto_terms.AUTO_END
    except Exception:
        return []

    if not os.path.exists(config.TERM_FILE):
        return []

    try:
        with open(config.TERM_FILE, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        log.warning("读取 term_dict.py 失败：%s", e)
        return []

    si = text.find(start_mark)
    ei = text.find(end_mark)
    if si == -1 or ei == -1 or ei < si:
        return []

    block = text[si + len(start_mark):ei]
    pairs = []
    for line in _split_lines_keepends(block):
        m = _PAIR_LINE_RE.match(line)
        if not m:
            continue
        try:
            k = json.loads(m.group(2))
            v = json.loads(m.group(4))
        except Exception:
            continue
        pairs.append((k, v))
    return pairs


def save_term_values(updates):
    """
    把 {原文: 新译文} 写回 term_dict.py（原地替换 value，保留格式与注释）。
    返回实际改动条数。
    """
    if not updates:
        return 0

    if not os.path.exists(config.TERM_FILE):
        log.warning("term_dict.py 不存在，无法写入")
        return 0

    with open(config.TERM_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    out = []
    changed = 0
    for line in text.splitlines():
        m = _PAIR_LINE_RE.match(line)
        if m:
            try:
                k = json.loads(m.group(2))
            except Exception:
                k = None
            if k in updates:
                new_v = json.dumps(updates[k], ensure_ascii=False)
                line = (f"{m.group(1)}{m.group(2)}{m.group(3)}"
                        f"{new_v}{m.group(5)}{m.group(6)}")
                changed += 1
        out.append(line)

    if not changed:
        return 0

    _atomic_write(config.TERM_FILE, "\n".join(out) + "\n")
    log.info("术语表写回 %d 条修改", changed)
    return changed


def delete_term_keys(keys):
    """
    从 term_dict.py 中删除指定原文 key 对应的条目（整行移除）。
    返回实际删除条数。

    删除仅在「应用术语」时落到文件；GUI 里先进入待删除集合，可撤回。
    """
    if not keys:
        return 0
    if not os.path.exists(config.TERM_FILE):
        log.warning("term_dict.py 不存在，无法删除")
        return 0

    keyset = set(keys)
    with open(config.TERM_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    out = []
    deleted = 0
    for line in text.splitlines():
        m = _PAIR_LINE_RE.match(line)
        if m:
            try:
                k = json.loads(m.group(2))
            except Exception:
                k = None
            if k in keyset:
                deleted += 1
                continue  # 跳过该行 = 删除
        out.append(line)

    if not deleted:
        return 0

    _atomic_write(config.TERM_FILE, "\n".join(out) + "\n")
    log.info("术语表删除 %d 条", deleted)
    return deleted


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)