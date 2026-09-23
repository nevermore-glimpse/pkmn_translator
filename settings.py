# -*- coding: utf-8 -*-
"""
设置管理：读取 / 修改配置。

  · 源码运行：直接读写 config.py
  · exe 运行：读写 user_config.json（config.py 已被编译进 exe）
两种情况都会 setattr 到 config 模块，实现当前会话立即生效。
"""
import json
import os
import re
import sys

import config
from logger import get_logger

log = get_logger("settings")

# 运行模式判断
IS_FROZEN = getattr(sys, "frozen", False)

# 源码模式下 config.py 的路径
CONFIG_PATH = os.path.join(config.BASE_DIR, "config.py")

# exe 模式下用户配置的路径
USER_CONFIG_PATH = config.USER_CONFIG_FILE


# key, 显示名, 类型, 说明
# 顺序对应菜单里显示的序号
EDITABLE = [
    # ---------- Ollama 连接 ----------
    ("MODEL",              "Ollama 模型名",     "str",   "如 qwen2.5:14b"),
    ("OLLAMA_URL",         "Ollama 服务地址",   "str",   "一般不动"),
    ("TIMEOUT",            "请求超时(秒)",      "float", "限制模型输出时间（超时直接断开）"),
    ("NUM_CTX",            "上下文长度",        "int",   "至少大于2000+每批条数x100"),
    ("NUM_PREDICT",        "最大生成 token",    "int",   "限制模型输出上限（超限直接断开）"),
    ("TEMPERATURE",        "采样温度",          "float", "0.0-1.0,越大模型自由度越高"),
    ("THINK",              "推理模式",        "bool",  "True/False"),

    # ---------- 翻译策略 ----------
    ("BATCH_SIZE",         "每批条数",          "int",   "建议 10-30"),
    ("BATCH_RETRIES",      "整批重试次数",      "int",   "失败时重试"),
    ("SINGLE_RETRIES",     "单条重试次数",      "int",   "失败时重试"),
    ("CACHE_SAVE_EVERY",   "缓存保存间隔",      "int",   "每 N 批保存一次"),
    ("SOURCE_LANG",        "源语言",            "str",   "如 英语 / 西班牙文"),
    ("TARGET_LANG",        "目标语言",          "str",   "如 简体中文"),
    ("ASK_LANG_EACH_TIME", "每次询问语言",      "bool",  "翻译前是否弹语言选择"),
    ("PREFIX_DICT_ENABLE", "启用前缀字典", "bool", "句首控制码由字典管理"),
    ("SKIP_PURE_CONTROL", "跳过纯控制符", "bool", "剥离后无内容的句子不翻译"),
    ("PURE_CONTROL_MIN_LEN", "纯控制符阈值", "int", "剥离后最少保留几个字"),

    # ---------- 换行重排 ----------
    ("REWRAP_ENABLE",      "启用换行重排",      "bool",  "只适用于[map*]下的翻译"),
    ("WRAP_CHARS_MIN",     "换行下限(字)",      "int",   ""),
    ("WRAP_CHARS_MAX",     "换行上限(字)",      "int",   ""),
    ("WRAP_MIN_GAP",       "换行最小间隔(字)",  "int",   "换行后至少 N 字才换"),

    # ---------- 术语与 Excel ----------
    ("APPLY_TERMS",        "启用术语替换",      "bool",  ""),
    ("EXCEL_SOURCE_LANG",  "Excel 源语言列",    "str",   ""),
    ("EXCEL_TARGET_LANG",  "Excel 目标语言列",  "str",   ""),
    ("AUTO_EXTRACT_TERMS", "自动提取术语", "bool", "翻译时提取专有名词"),
    ("AUTO_EXTRACT_MIN_LEN", "术语最短长度", "int", "")
]


# ================================================================
# 读
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


def _load_user_overrides():
    """exe 模式下读取 user_config.json。"""
    if not os.path.exists(USER_CONFIG_PATH):
        return {}
    try:
        with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning("user_config.json 读取失败：%s", e)
        return {}


def _save_user_overrides(data):
    tmp = USER_CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, USER_CONFIG_PATH)


def get_all():
    """返回 {key: 显示值}。"""
    out = {}

    if IS_FROZEN:
        # exe 模式：读 config 模块属性
        for key, *_ in EDITABLE:
            v = getattr(config, key, None)
            out[key] = str(v) if v is not None else "（未找到）"
    else:
        # 源码模式：解析 config.py 文本
        text = _read_source()
        for key, *_ in EDITABLE:
            m = _pattern(key).search(text)
            out[key] = _strip_quotes(m.group(2)) if m else "（未找到）"

    return out


# ================================================================
# 写
# ================================================================
def _format_value(typ, new_value):
    """把用户输入转成 (字面量文本, 实际值对象)。"""
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


def _set_in_source(key, literal):
    """源码模式：把值写进 config.py。"""
    text = _read_source()
    pat = _pattern(key)
    if not pat.search(text):
        return False
    new_text = pat.sub(lambda m: m.group(1) + literal + m.group(3),
                       text, count=1)
    _write_source(new_text)
    return True


def _set_in_user_config(key, value_obj):
    """exe 模式：把值写进 user_config.json。"""
    data = _load_user_overrides()
    data[key] = value_obj
    _save_user_overrides(data)


def set_value(key, new_value):
    """
    修改配置。
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

    try:
        if IS_FROZEN:
            _set_in_user_config(key, value_obj)
        else:
            if not _set_in_source(key, literal):
                return False, f"未在 config.py 中找到 {key}", None
    except Exception as e:
        log.error("写入配置失败：%s", e)
        return False, f"写入失败：{e}", None

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
    mode = "exe" if IS_FROZEN else "源码"
    while True:
        current = get_all()
        print()
        print("=" * 62)
        print(f"  设置（{mode} 模式）  输入序号修改，0 返回主菜单")
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

        where = "user_config.json" if IS_FROZEN else "config.py"
        print(f"✔ 已更新：{key} = {msg}  （已写回 {where}，当前会话立即生效）")

def set_internal(key, value):
    """
    写回配置项，但不暴露在菜单里。
    用于内部标志位（如 SNAPSHOT_INITIALIZED）。
    不做类型校验，直接按 Python 值写入。
    """
    try:
        if isinstance(value, bool):
            literal = "True" if value else "False"
            value_obj = value
        elif isinstance(value, int):
            literal = str(value)
            value_obj = value
        elif isinstance(value, float):
            literal = str(value)
            value_obj = value
        else:
            v = str(value)
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            literal = f'"{escaped}"'
            value_obj = v

        if IS_FROZEN:
            _set_in_user_config(key, value_obj)
        else:
            if not _set_in_source(key, literal):
                log.warning("set_internal：config.py 中未找到 %s", key)
                return False

        # 热更新当前会话
        try:
            setattr(config, key, value_obj)
        except Exception as e:
            log.warning("setattr(%s) 失败：%s", key, e)

        log.info("内部配置已更新：%s = %s", key, literal)
        return True
    except Exception as e:
        log.warning("set_internal(%s) 失败：%s", key, e)
        return False