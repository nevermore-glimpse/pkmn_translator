# -*- coding: utf-8 -*-
r"""
文本保护规则（text_preserve）：把「哪些写法必须原样保留」从硬编码升级成**数据**。

为什么要有这个
--------------
processor 内置的识别规则覆盖了 RPG Maker 的通用写法：

    \命令[参数]      \xn[Leticia]  \c[3]  \tg[Owen]  \w[speech hgss 3] …
    无参数命令        \PN  \pn  \se  \ff  \CN …
    单字母            \N  \n  \b  \c  \g  \i …
    符号型事件码       \$  \.  \|  \!  \>  \<  \^  \{  \}
    printf 占位符     %1  %2

但**每个同人游戏都可能加自己的控制码**（比如本工具最早漏掉的
``\xn[Leticia]``），硬编码改不过来。这里让用户放一份 JSON 规则按正则补充。

三档模式（config.TEXT_PRESERVE_MODE）
------------------------------------
    off     只用 processor 内置规则
    smart   内置规则 + 项目自带规则集（base.json / rpgmaker.json）   ← 默认
    custom  smart + 用户自己的 custom.json

规则文件格式（JSON 数组，每项一个对象）
--------------------------------------
    [{"src": "正则表达式", "info": "给人看的说明，不参与匹配"}]

★ 正则匹配到的整段会按「控制码」对待：原样送模型、翻完检查是否还在，
  丢了就按原文补回。写宽了会连正文一起保护，写窄了等于没写 ——
  所以 `info` 请写清楚它到底保护什么。
"""
import json
import os

import config
from logger import get_logger

log = get_logger("text_rules")

# 自带规则集文件名（随程序分发；用户不要改，改 custom.json）
BUILTIN_FILES = ("base.json", "rpgmaker.json")
# 用户自己的规则文件
CUSTOM_FILE = "custom.json"

_MODES = ("off", "smart", "custom")

# 上次装载的签名（模式 + 各文件 mtime），用于按需重载
_applied_sig = None


def rules_dir() -> str:
    """规则目录：与 config.py 同级的 text_preserve/。"""
    return os.path.join(config.BASE_DIR,
                        getattr(config, "TEXT_PRESERVE_DIR", "text_preserve"))


def mode() -> str:
    m = str(getattr(config, "TEXT_PRESERVE_MODE", "smart") or "smart").lower()
    return m if m in _MODES else "smart"


def _load_file(path):
    """读一个规则文件，返回 [{src, info}, ...]；读不了返回 []。"""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.warning("文本保护规则读取失败：%s：%s", path, e)
        return []
    if isinstance(data, dict):
        # 兼容 {"rules": [...]} 写法
        data = data.get("rules") or []
    if not isinstance(data, list):
        log.warning("文本保护规则格式不对（要 JSON 数组）：%s", path)
        return []
    out = []
    for item in data:
        if isinstance(item, str):
            out.append({"src": item, "info": ""})
            continue
        if not isinstance(item, dict):
            continue
        src = str(item.get("src") or "").strip()
        if not src:
            continue
        out.append({"src": src, "info": str(item.get("info") or "")})
    return out


def file_list(m=None):
    """当前模式要读的规则文件（相对 rules_dir 的文件名）。"""
    m = m or mode()
    if m == "off":
        return []
    if m == "smart":
        return list(BUILTIN_FILES)
    return list(BUILTIN_FILES) + [CUSTOM_FILE]


def active_rules(m=None):
    """返回当前生效的规则列表（带来源文件名）。"""
    d = rules_dir()
    out = []
    for name in file_list(m):
        for r in _load_file(os.path.join(d, name)):
            out.append(dict(r, file=name))
    return out


def active_patterns(m=None):
    """返回当前生效的正则字符串列表（去重保序）。"""
    seen, out = set(), []
    for r in active_rules(m):
        src = r["src"]
        if src in seen:
            continue
        seen.add(src)
        out.append(src)
    return out


def _signature():
    d = rules_dir()
    sig = [mode()]
    for name in file_list():
        p = os.path.join(d, name)
        try:
            sig.append((name, os.path.getmtime(p), os.path.getsize(p)))
        except OSError:
            sig.append((name, None, None))
    return tuple(sig)


def apply(m=None, force=True):
    """
    把当前规则的额外正则装进 processor（全局立即生效）。

    返回实际装上的正则条数。
    """
    import processor as PR          # 惰性导入：避免与 processor 形成循环依赖
    pats = active_patterns(m)
    PR.set_extra_ctrl_patterns(pats)
    if pats:
        log.info("文本保护规则：模式 %s，%d 条生效（%s）",
                 m or mode(), len(pats), "、".join(file_list(m)))
    else:
        log.info("文本保护规则：模式 %s，未启用额外规则", m or mode())
    return len(pats)


def ensure_applied():
    """
    按需装载：模式或规则文件变了才重新装载。

    翻译/润色每轮开头调一次即可（只是几个 stat 调用，很便宜）。
    返回 True 表示这次真的重新装载了。
    """
    global _applied_sig
    sig = _signature()
    if sig == _applied_sig:
        return False
    apply()
    _applied_sig = sig
    return True


def save_custom(rules):
    """写用户自定义规则文件（供界面/工具调用）。返回写入条数。"""
    d = rules_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError as e:
        log.warning("规则目录创建失败：%s", e)
        return 0
    clean = []
    for r in rules or []:
        src = str((r or {}).get("src") or "").strip()
        if not src:
            continue
        clean.append({"src": src, "info": str((r or {}).get("info") or "")})
    path = os.path.join(d, CUSTOM_FILE)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    log.info("文本保护自定义规则已写入 %d 条 → %s", len(clean), path)
    return len(clean)
