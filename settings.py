# -*- coding: utf-8 -*-
"""
设置管理：读取 / 修改 config.py 里的可编辑项。
- 直接改 config.py 源文件（持久化）
- 改完 setattr 到 config 模块（当前会话立即生效，不需重启）
"""
import os
import re

import config
from logger import get_logger

log = get_logger("settings")

CONFIG_PATH = os.path.join(config.BASE_DIR, "config.py")


# key, 显示名, 类型, 说明
EDITABLE = [
    ("MODEL",             "Ollama 模型名",     "str",   "如 qwen2.5:14b"),
    ("OLLAMA_URL",        "Ollama 服务地址",   "str",   ""),
    ("BATCH_SIZE",        "每批条数",          "int",   "建议 10-30"),
    ("TEMPERATURE",       "采样温度",          "float", "0.0-1.0"),
    ("TIMEOUT",           "请求超时(秒)",      "float", ""),
    ("NUM_CTX",           "上下文长度",        "int",   ""),
    ("NUM_PREDICT",       "最大生成 token",    "int",   ""),
    ("THINK",             "无推理模式",        "bool",  "True/False"),
    ("BATCH_RETRIES",     "整批重试次数",      "int",   ""),
    ("SINGLE_RETRIES",    "单条重试次数",      "int",   ""),
    ("SOURCE_LANG",       "源语言",            "str",   "如 英文"),
    ("TARGET_LANG",       "目标语言",          "str",   "如 简体中文"),
    ("REWRAP_ENABLE",     "启用换行重排",      "bool",  ""),
    ("WRAP_CHARS_MIN",    "换行下限(字)",      "int",   ""),
    ("WRAP_CHARS_MAX",    "换行上限(字)",      "int",   ""),
    ("WRAP_PUNCT",        "句末标点",          "str",   "如 。！？!?"),
    ("WRAP_DOTS",         "连续点换行阈值",    "int",   "如 3"),
    ("APPLY_TERMS",       "启用术语替换",      "bool",  ""),
    ("ASK_LANG_EACH_TIME", "每次询问语言", "bool", "True/False"),
    ("EXCEL_SOURCE_LANG", "Excel 源语言列",    "str",   ""),
    ("EXCEL_TARGET_LANG", "Excel 目标语言列",  "str",   ""),
]


# ================================================================
# 读写 config.py
# ================================================================
def _read_source():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _write_source(text):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, CONFIG_PATH)


def _pattern(key):
    return re.compile(
        r'^(\s*' + re.escape(key) + r'\s*=\s*)(.+?)(\s*(?:#.*)?)$',
        re.MULTILINE,
    )


def _strip_quotes(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        return v[1:-1]
    return v


def get_all():
    """返回 {key: 显示值}（已去引号）。"""
    text = _read_source()
    out = {}
    for key, *_ in EDITABLE:
        m = _pattern(key).search(text)
        out[key] = _strip_quotes(m.group(2)) if m else "（未找到）"
    return out


def _format_value(typ, new_value):
    """把用户输入转成 Python 字面量文本 + 实际值对象。"""
    if typ == "int":
        v = int(new_value)
        return str(v), v
    if typ == "float":
        v = float(new_value)
        return str(v), v
    if typ == "bool":
        if isinstance(new_value, str):
            v = new_value.strip().lower() in ("1", "true", "yes", "y", "on")
        else:
            v = bool(new_value)
        return ("True" if v else "False"), v
    # str
    v = str(new_value)
    escaped = v.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"', v


def set_value(key, new_value):
    """
    修改 config.py 中 key 的值。
    返回 (ok, msg, value_obj)，value_obj 供调用方 setattr 热更新。
    """
    meta = next(((k, n, t, d) for k, n, t, d in EDITABLE if k == key), None)
    if not meta:
        return False, f"不支持的配置项：{key}", None

    _, name, typ, _ = meta

    try:
        literal, value_obj = _format_value(typ, new_value)
    except ValueError as e:
        return False, f"格式错误：{e}", None

    text = _read_source()
    pat = _pattern(key)
    if not pat.search(text):
        return False, f"未在 config.py 中找到 {key}", None

    new_text = pat.sub(lambda m: m.group(1) + literal + m.group(3),
                       text, count=1)
    _write_source(new_text)

    # 热更新当前会话
    try:
        setattr(config, key, value_obj)
    except Exception as e:
        log.warning("setattr 失败：%s", e)

    log.info("设置已更新：%s = %s", key, literal)
    return True, literal, value_obj


# ================================================================
# 交互式菜单
# ================================================================
def show_menu():
    while True:
        current = get_all()
        print()
        print("=" * 62)
        print("  设置（输入序号修改，0 返回主菜单）")
        print("=" * 62)
        for i, (key, name, typ, desc) in enumerate(EDITABLE, 1):
            val = current.get(key, "?")
            tip = f"   # {desc}" if desc else ""
            print(f"  {i:>2}. {name:<16} = {val}{tip}")
        print("=" * 62)

        raw = input("请选择：").strip()
        if raw == "0" or not raw:
            return
        if not raw.isdigit():
            print("无效输入")
            continue
        idx = int(raw) - 1
        if not (0 <= idx < len(EDITABLE)):
            print("无效序号")
            continue

        key, name, typ, _ = EDITABLE[idx]
        print(f"\n当前 {name} = {current.get(key)}")
        hint = ""
        if typ == "bool":
            hint = "（输入 y/n 或 true/false）"
        new_val = input(f"输入新值{hint}（回车取消）：").strip()
        if not new_val:
            print("已取消")
            continue

        ok, msg, _ = set_value(key, new_val)
        if not ok:
            print(f"✘ {msg}")
            continue
        print(f"✔ 已更新：{key} = {msg}  （已写回 config.py，当前会话立即生效）")