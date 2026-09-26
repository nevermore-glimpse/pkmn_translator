# -*- coding: utf-8 -*-
r"""
句首控制码字典：
  · 缓存句子开头的连续控制码串（如 \w[speech hgss 3]\tg[???]）
  · 用户手工翻译后复用
  · 翻译时剥离，回写时拼回
"""
import json
import os
import re

import config
from logger import get_logger

log = get_logger("prefix_dict")

# 存储位置：与 term_dict.py 同目录
DICT_FILE = os.path.join(config.BASE_DIR, "prefix_dict.json")

# ★「应用术语」目前只处理说话人标签 \tg[...] 里的内容
#   （三段：\tg[ / 内容 / ]），内容段才是可替换的角色名
TG_RE = re.compile(r'(\\tg\[)([^\]]*)(\])')

# 全局内存缓存
_entries = {}     # {前缀原文: 前缀译文}  空串表示待翻译
_loaded = False


# ================================================================
# 读写
# ================================================================
def _load():
    global _entries, _loaded
    if _loaded:
        return
    _loaded = True

    if not os.path.exists(DICT_FILE):
        _entries = {}
        return

    try:
        with open(DICT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "entries" in data:
            _entries = dict(data.get("entries") or {})
        elif isinstance(data, dict):
            # 兼容裸 dict 格式
            _entries = dict(data)
        else:
            _entries = {}
        log.info("前缀字典加载：%d 条（%s）", len(_entries), DICT_FILE)
    except Exception as e:
        log.warning("前缀字典加载失败：%s", e)
        _entries = {}


def _save():
    """原子写回。"""
    tmp = DICT_FILE + ".tmp"
    data = {
        "version": 1,
        "entries": _entries,
    }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DICT_FILE)


def reload_dict():
    """强制从磁盘重读。"""
    global _loaded
    _loaded = False
    _load()


# ================================================================
# 查询 / 注册
# ================================================================
def get_translation(prefix):
    """
    返回译后前缀；未注册或未翻译返回 None。
    """
    _load()
    if not prefix:
        return None
    v = _entries.get(prefix)
    if v is None:
        return None
    return v or None      # 空串视为未翻译


def register_prefix(prefix, fill_by_terms=True):
    """
    注册新前缀。已存在返回 False；新增返回 True。

    ★ fill_by_terms=True：若该前缀里命中术语字典，直接把「术语替换后的前缀」
      作为它的译文填进去（不用再手工翻一遍）。
      例：\\tg[Owen] 命中术语 Owen=欧文 → 译文直接写成 \\tg[欧文]。
      没命中任何术语时仍保持空值（= 待翻译）。
    """
    _load()
    if not prefix:
        return False
    if prefix in _entries:
        return False

    value = ""
    if fill_by_terms:
        sub = substitute_terms(prefix)
        if sub and sub != prefix:
            value = sub
            log.info("新前缀 %r 命中术语，已自动填入译文 %r", prefix, sub)

    _entries[prefix] = value
    return True


def substitute_terms(prefix):
    """
    前缀里命中术语字典的部分，替换为术语译文。
    典型场景：\\tg[Owen] 中的 Owen 命中术语 → \\tg[欧文]。

    术语表不可用、或替换过程中出错时原样返回，绝不让前缀处理拖垮主流程。
    """
    if not prefix:
        return prefix
    try:
        import processor as _PR          # 惰性导入，避免与 processor 形成循环依赖
        _PR.load_terms()
        out = _PR.apply_terms(prefix)
        return out if out else prefix
    except Exception as e:               # 术语表损坏/未配置都不影响翻译
        log.debug("前缀术语替换失败（已回退原前缀）：%s", e)
        return prefix


def _apply_terms_to_text(text):
    """对一段纯文本做术语替换；术语表不可用时原样返回。"""
    if not text:
        return text
    try:
        import processor as _PR
        _PR.load_terms()
        out = _PR.apply_terms(text)
        return out if out else text
    except Exception as e:
        log.debug("术语替换失败（已回退原文）：%s", e)
        return text


def _terms_hit_in(text):
    """返回 text 中命中的术语 [(原文, 译文), ...]；术语表不可用时返回 []。"""
    if not text:
        return []
    try:
        import processor as _PR
        _PR.load_terms()
        return _PR.find_terms(text) or []
    except Exception as e:
        log.debug("术语命中检测失败：%s", e)
        return []


def substitute_tg_terms(prefix):
    r"""
    只把前缀里 \tg[...] 的内部文字按术语表替换（其余部分原样保留）。

    例：\w[speech hgss 3]\tg[Owen] → \w[speech hgss 3]\tg[欧文]
    没命中任何术语时原样返回。

    ★ 目前「应用术语」的作用范围就限定在 \tg[]，避免误伤
      \w[speech hgss 3] 之类必须保持英文的控制码参数。
    """
    if not prefix or "\\tg[" not in prefix:
        return prefix
    try:
        def _repl(m):
            inner = m.group(2)
            if not inner.strip():
                return m.group(0)
            new_inner = _apply_terms_to_text(inner)
            return m.group(1) + new_inner + m.group(3)

        return TG_RE.sub(_repl, prefix)
    except Exception as e:
        log.warning("前缀 \\tg[] 术语替换失败（已回退）：%s", e)
        return prefix


def tg_terms_of(prefix):
    r"""列出前缀中 \tg[...] 内部命中的术语 [(原文, 译文), ...]（已去重）。"""
    if not prefix or "\\tg[" not in prefix:
        return []
    out, seen = [], set()
    for m in TG_RE.finditer(prefix):
        for src, dst in _terms_hit_in(m.group(2)):
            key = (src or "").lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((src, dst))
    return out


def scan_terms_for_tg():
    r"""
    扫描整本前缀字典，预演「应用术语」的结果（不写盘）。

    只对「当前生效文本」里 \tg[] 的内容做术语替换：
      · 已有译文 → 在译文基础上替换（保留用户其它手工改动）
      · 译文为空 → 在原文基础上替换

    返回 (changes, stats)
      changes: [{"src", "old", "new", "terms":[(原文, 译文), ...]}, ...]
      stats  : {"total", "changed", "untouched"}
    """
    _load()
    changes = []
    stats = {"total": len(_entries), "changed": 0, "untouched": 0}

    for src, dst in _entries.items():
        base = dst or src
        terms = tg_terms_of(base)
        if not terms:
            stats["untouched"] += 1
            continue
        new = substitute_tg_terms(base)
        if new == dst:
            stats["untouched"] += 1
            continue
        changes.append({"src": src, "old": dst, "new": new, "terms": terms})
        stats["changed"] += 1

    return changes, stats


def apply_terms_for_tg():
    r"""
    把术语表套用到前缀字典并落盘（只替换 \tg[...] 的内容）。
    返回 (changes, stats)，与 scan_terms_for_tg() 结构一致。
    """
    changes, stats = scan_terms_for_tg()
    if not changes:
        return changes, stats

    n = update_many({c["src"]: c["new"] for c in changes})
    _save()
    log.info("前缀字典「应用术语」：命中 %d 条，写入 %d 条",
             len(changes), n)
    return changes, stats


def apply_prefix(prefix):
    """
    返回应使用的译后前缀：
      · 已翻译 → 译后前缀
      · 未翻译 → 原前缀，但其中命中术语的部分先替换成术语译文
    """
    t = get_translation(prefix)
    if t:
        return t
    return substitute_terms(prefix)


def update_many(mapping):
    """批量写入 {前缀原文: 译文}，返回改动条数。"""
    _load()
    n = 0
    for k, v in (mapping or {}).items():
        if not k:
            continue
        if _entries.get(k) != v:
            _entries[k] = v or ""
            n += 1
    return n


def remove(prefix):
    """删除一条前缀。"""
    _load()
    return _entries.pop(prefix, None) is not None


def all_entries():
    """返回 {前缀原文: 译文} 的副本。"""
    _load()
    return dict(_entries)


def save():
    """外部修改后调用，落盘。"""
    _save()


# ================================================================
# 批量统计
# ================================================================
def stats():
    _load()
    total = len(_entries)
    done = sum(1 for v in _entries.values() if v)
    pending = total - done
    return {"total": total, "done": done, "pending": pending}


def list_pending():
    """返回 [(前缀原文, 前缀译文), ...]，只列未翻译的。"""
    _load()
    return [(k, v) for k, v in sorted(_entries.items()) if not v]