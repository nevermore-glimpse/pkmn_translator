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

# ★ 区块符只有一种写法，三处（is_block / 区块模式判断）共用同一条正则，
#   免得以后改了一处忘了另一处。
BLOCK_RE = re.compile(r'^\s*\[[^\]]*\]\s*$')
NUM_RE   = re.compile(r'^\s*\d+\s*$')
BLOCK_MAP_RE = re.compile(r'^\s*\[map\d+\]\s*$', re.IGNORECASE)


def is_block(s):  return bool(BLOCK_RE.match(s))
def is_number(s): return bool(NUM_RE.match(s))


def pair_similarity(a, b, floor=0.0):
    """
    计算两行的相似度：**相同部分占整句的百分比**。

    做法：找出两行所有公共片段，把它们的长度加起来，再除以较长那一行的长度。
    差异出现在句子的哪个位置都不影响结果。

    与旧算法（只管最长公共前缀 + 最长公共后缀）的区别：
      旧算法一旦中间有一处不同，前后就接不上，长句极易被算低。
      例如这种模板句：
        Max. HP<r>+{1}<<n>>Attack<r>+{2}<<n>>Defense<r>+{3}<<n>>...
      两行明明绝大部分相同，只因差异不在头尾，旧算法只给出 25%，
      于是被误判成「特殊行」而不参与翻译。
      新算法统计的是"整句里有多少字是一样的"，这类行能正确配对。

    floor：只关心「够不够得着这个阈值」时传它 —— 两行长度差得太多时
           相同部分最多也就是短的那行全长，直接判 0，
           省掉一次 difflib（它是 O(n·m)，整文件跑下来不便宜）。
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    if floor > 0:
        lo, hi = (len(a), len(b)) if len(a) <= len(b) else (len(b), len(a))
        if hi == 0 or lo / hi < floor:
            return 0.0

    import difflib
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    matched = sum(bl.size for bl in sm.get_matching_blocks())
    return matched / max(len(a), len(b))



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
        if BLOCK_MAP_RE.match(s):
            current = "newline"
        elif is_block(s):
            current = "space"
        modes.append(current)
    return modes

def read_file(path, encoding="utf-8-sig", max_lines=None):
    """
    读文件，返回 (lines, newline)。保留原始换行风格。

    ★ max_lines：最多返回前 N 行（N <= 0 表示不限）。
      默认取 config.MAX_INPUT_LINES —— 真实翻译与模拟/测试用的
      翻译文件都受同一个上限约束，避免一次吃进整个大文件。
    """
    if max_lines is None:
        max_lines = getattr(config, "MAX_INPUT_LINES", 0)

    # ★ newline="" 关掉 Python 的「通用换行」：否则 CRLF 在读取时就被归一成
    #   LF，`"\r\n" in raw` 永远为假 → 写回时整个文件被悄悄改成 LF 行尾。
    with open(path, "r", encoding=encoding, newline="") as f:
        raw = f.read()
    crlf = raw.count("\r\n")
    lf = raw.count("\n") - crlf          # 单独的 LF（不算 CRLF 里那个）
    newline = "\r\n" if crlf >= lf else "\n"
    # 内部一律按 LF 切，返回的每一行都不带行尾符（与调用方约定一致）
    lines = raw.replace("\r\n", "\n").split("\n")

    try:
        max_lines = int(max_lines)
    except (TypeError, ValueError):
        max_lines = 0
    if max_lines > 0 and len(lines) > max_lines:
        log_lines_trimmed(path, len(lines), max_lines)
        lines = lines[:max_lines]

    return lines, newline


def log_lines_trimmed(path, total, kept):
    """（可被上层替换的）截断提示钩子，默认写日志。"""
    try:
        from logger import get_logger
        get_logger("parser").info(
            "读取 %s：共 %d 行，按 MAX_INPUT_LINES 只取前 %d 行",
            path, total, kept)
    except Exception:
        pass


def detect_newline(path, default="\n"):
    """
    按**原始字节**判断文件用的是 CRLF 还是 LF。

    ★ read_file 是用文本模式打开的，Python 的通用换行在读取时就把 "\\r\\n"
      归一成 "\\n" 了，所以它返回的 newline 永远是 "\\n"。
      要「原样写回、不改动行尾」的场合（应用已编辑 / 换行重排）用这个函数。
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(65536)
    except OSError:
        return default
    return "\r\n" if b"\r\n" in chunk else "\n"


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

        # ★ # 开头的行视为注释 / 标记行：不翻译、不进入检查报告
        if s.startswith('#'):
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

        # 情况 3：下一行不同 → 先看「相同部分占比」够不够高（近似配对）
        sim = 0.0
        pairable = bool(next_s) and not is_block(next_s) and not is_number(next_s)
        if pairable:
            # ★ 把阈值传进去：长度差太多的直接判 0，不用跑 difflib
            need = getattr(config, "PAIR_SIMILARITY_MIN", 0.8)
            sim = pair_similarity(s, next_s, floor=need)
            if sim >= need:
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
            reason = f'下一行文本不同（相同部分占比 {sim:.0%}）'

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