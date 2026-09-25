# -*- coding: utf-8 -*-
"""
intl.txt 专用解析器。

格式约定：
    [map1]                       ← 区块符，独占一行
    Text A                       ← 原文
    Text A                       ← 重复的第二行，翻译/替换它
    Text B
    Text B
    ...

规则：
    1. [xxx] 区块符 / 纯数字 / 空行 → 跳过
    2. 文本行 + 下一行完全相同     → entries（记录第二行，替换它）
    3. 文本行 + 下一行不同或没有    → special_cases（待手动精修）
"""
import re

import config

BLOCK_RE = re.compile(r'^\s*\[[^\]]*\]\s*$')
NUM_RE   = re.compile(r'^\s*\d+\s*$')


def is_block(s):  return bool(BLOCK_RE.match(s))
def is_number(s): return bool(NUM_RE.match(s))


def pair_similarity(a, b):
    """
    计算两行的「头尾匹配度」：
      最长公共前缀 + 最长公共后缀（两者不重叠、不重复计数），再按较长行长度归一。

    典型场景：两行只差一个控制码（例如多一个 <<r>>），
    前缀配到 <<r>> 之前、后缀从 <<n>> 配起，匹配度很高 ——
    应视为同一组，而不是「文本不同」的特殊行。
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    m = min(len(a), len(b))

    # 最长公共前缀
    p = 0
    while p < m and a[p] == b[p]:
        p += 1

    # 最长公共后缀：限制在剩余长度内，避免与前缀重叠
    s = 0
    limit = m - p
    while s < limit and a[len(a) - 1 - s] == b[len(b) - 1 - s]:
        s += 1

    return (p + s) / max(len(a), len(b))

# 区块符模式判断
_BLOCK_MAP_RE = re.compile(r'^\s*\[map\d+\]\s*$', re.IGNORECASE)
_BLOCK_ANY_RE = re.compile(r'^\s*\[[^\]]+\]\s*$')


def get_block_modes(lines):
    """
    遍历所有行，返回每行所属区块的换行模式。

    规则：
      · [map数字]      → "newline"（用 \\n 换行）
      · [其它方括号内容] → "space"（用空格换行）
      · 其它行          → 继承上一个区块模式
      · 文件最开头无区块 → 默认 "newline"

    返回 [mode_str, ...]，长度等于 len(lines)
    """
    modes = []
    current = "newline"
    for line in lines:
        s = line.strip()
        if _BLOCK_MAP_RE.match(s):
            current = "newline"
        elif _BLOCK_ANY_RE.match(s):
            current = "space"
        modes.append(current)
    return modes

def read_file(path, encoding="utf-8-sig"):
    """读文件，返回 (lines, newline)。保留原始换行风格。"""
    with open(path, "r", encoding=encoding) as f:
        raw = f.read()
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.split(newline), newline


def extract_entries(lines):
    """
    扫描全文件，返回 (entries, special_cases)。

    entries       : [(目标行号, 原文), ...]      正常配对 → 翻译第二行
    special_cases : [ {line_no, next_line_no, text, next_text, reason}, ... ]
    """
    entries, special = [], []
    i, n = 0, len(lines)

    while i < n:
        s = lines[i].strip()
        if not s or is_block(s) or is_number(s):
            i += 1
            continue

        # 情况 1：文件末尾孤立文本
        if i + 1 >= n:
            special.append({
                'line_no':      i,
                'next_line_no': None,
                'text':         s,
                'next_text':    None,
                'reason':       '文件末尾孤立文本行',
            })
            i += 1
            continue

        next_raw = lines[i + 1]
        next_s   = next_raw.strip()

        # 情况 2：下一行完全相同 → 正常配对
        if next_s == s:
            entries.append((i + 1, s))
            i += 2
            continue

        # 情况 3：下一行不同 → 先看头尾匹配度够不够高（近似配对）
        sim = 0.0
        pairable = bool(next_s) and not is_block(next_s) and not is_number(next_s)
        if pairable:
            sim = pair_similarity(s, next_s)
            if sim >= getattr(config, "PAIR_SIMILARITY_MIN", 0.8):
                # 视为同一组：保留第一行，把第二行替换为对应译文
                entries.append((i + 1, next_s))
                i += 2
                continue

        # 仍不能配对 → 特殊情况
        if not next_s:
            reason = '下一行为空行'
        elif is_block(next_s):
            reason = '下一行为区块符'
        elif is_number(next_s):
            reason = '下一行为纯数字'
        else:
            reason = f'下一行文本不同（头尾匹配度 {sim:.0%}）'

        special.append({
            'line_no':      i,
            'next_line_no': i + 1,
            'text':         s,
            'next_text':    next_s if next_s else None,
            'reason':       reason,
        })
        i += 1

    return entries, special


def write_output(lines, entries, translations, out_path, newline="\n",
                 encoding="utf-8-sig", manual_translations=None):
    """
    回写译文。
    translations        : {原文: 译文}   正常配对条目（走缓存）
    manual_translations : {行号: 译文}   精修结果（优先级更高）
    """
    out = list(lines)
    replaced = 0

    for line_idx, src in entries:
        dst = translations.get(src)
        if not dst:
            continue
        m = re.match(r'^([ \t]*)', lines[line_idx])
        indent = m.group(1) if m else ""
        out[line_idx] = indent + dst
        replaced += 1

    if manual_translations:
        for line_idx, dst in manual_translations.items():
            if not dst:
                continue
            if not (0 <= line_idx < len(out)):
                continue
            m = re.match(r'^([ \t]*)', lines[line_idx])
            indent = m.group(1) if m else ""
            out[line_idx] = indent + dst
            replaced += 1

    with open(out_path, "w", encoding=encoding) as f:
        f.write(newline.join(out))

    return replaced