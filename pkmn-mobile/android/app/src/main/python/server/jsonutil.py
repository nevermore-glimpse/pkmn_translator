# -*- coding: utf-8 -*-
"""JSON 序列化兜底：核心代码返回的东西不一定都能直接 json.dumps。"""
from __future__ import annotations

import datetime
import json
import os


def clean(obj, _depth=0):
    """把 Python 对象转成 JSON 友好的形态。

    遇到认不出的类型（rmarshal.RSymbol 之类）就退化成它的字符串形式，
    宁可显示得不漂亮，也不要让整个接口 500。
    """
    if _depth > 12:
        return "<递归过深>"
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {_key(k): clean(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [clean(v, _depth + 1) for v in obj]
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return f"<{len(obj)} bytes>"
    if isinstance(obj, datetime.datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, (datetime.date, datetime.time)):
        return str(obj)
    return str(obj)


def _key(k):
    if isinstance(k, str):
        return k
    try:
        return str(k)
    except Exception:
        return "<不可序列化的键>"


def dumps(obj):
    return json.dumps(clean(obj), ensure_ascii=False)


def ok(data=None):
    return {"ok": True, "data": data}


def err(message, **extra):
    d = {"ok": False, "message": str(message)}
    d.update(extra)
    return d


def normalize_path(p):
    """统一斜杠 + 去掉末尾分隔符，顺便防止明显的越界写法。"""
    if p is None:
        return None
    p = str(p).replace("\\", "/").rstrip("/")
    return os.path.normpath(p)
