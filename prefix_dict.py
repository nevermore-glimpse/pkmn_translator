# -*- coding: utf-8 -*-
"""
句首控制码字典：
  · 缓存句子开头的连续控制码串（如 \w[speech hgss 3]\tg[???]）
  · 用户手工翻译后复用
  · 翻译时剥离，回写时拼回
"""
import json
import os

import config
from logger import get_logger

log = get_logger("prefix_dict")

# 存储位置：与 term_dict.py 同目录
DICT_FILE = os.path.join(config.BASE_DIR, "prefix_dict.json")

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


def register_prefix(prefix):
    """
    注册新前缀。已存在返回 False；新增返回 True。
    """
    _load()
    if not prefix:
        return False
    if prefix in _entries:
        return False
    _entries[prefix] = ""
    return True


def apply_prefix(prefix):
    """
    返回应使用的译后前缀：
      · 已翻译 → 译后前缀
      · 未翻译 → 原前缀
    """
    t = get_translation(prefix)
    return t if t else prefix


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


def list_all():
    """返回 [(前缀原文, 前缀译文), ...]，按是否翻译排序。"""
    _load()
    return sorted(_entries.items(), key=lambda x: (bool(x[1]), x[0]))