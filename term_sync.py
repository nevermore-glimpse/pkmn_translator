# -*- coding: utf-8 -*-
"""
术语更新后重翻：
  1. 维护一份"上次重翻时的术语基准"快照
  2. 对比当前 term_dict.py，找出新增 / 删除的术语
  3. 在缓存里找出包含新增术语的句子
  4. 让上层删除这些缓存并重翻
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


# ================================================================
# 快照
# ================================================================
def load_snapshot():
    """返回上次快照的术语集合；不存在则返回 None。"""
    if not os.path.exists(SNAPSHOT_FILE):
        return None
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("terms", []))
    except Exception as e:
        log.warning("快照读取失败：%s", e)
        return None


def save_snapshot(term_keys):
    """写入快照。term_keys 是术语 key 的集合。"""
    data = {
        "saved_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "count":    len(term_keys),
        "terms":    sorted(term_keys),
    }
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("快照已保存：%d 条 → %s", len(term_keys), SNAPSHOT_FILE)


# ================================================================
# 对比
# ================================================================
def diff_terms():
    """返回 (added, removed)，都是排序后的列表。"""
    current_terms = load_current_terms()
    current_keys = set(current_terms.keys())

    old_keys = load_snapshot()
    if old_keys is None:
        return None, None      # 首次使用

    added   = sorted(current_keys - old_keys)
    removed = sorted(old_keys - current_keys)
    return added, removed


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
                r'(?![' + word_chars + r'])'
            )))
        except re.error:
            continue
    return pats


def find_affected_cache(cache_data, added_terms):
    """
    在缓存的所有 key（原文）里，找出包含任一新术语的句子。
    返回 [(key, 命中的术语), ...]
    """
    if not added_terms:
        return []

    pats = _build_patterns(added_terms)
    hits = []
    for key in cache_data:
        for term, pat in pats:
            if pat.search(key):
                hits.append((key, term))
                break
    return hits