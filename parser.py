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

# ★ 分段分隔线（`#-------------------------------`，见 intl_text._SEP）：
#   它是导出时插入的排版线，不是正文，**任何位置**都要跳过。
#   以前所有 # 行都跳所以不用单独判；现在只跳文件头，
#   这条线若不单独处理就会被当成句子送去翻译、还会顶乱行数。
SEP_LINE_RE = re.compile(r'^\s*#[-=]{3,}\s*$')

# ★ 「一串 CR（后面可以再跟一个 LF）」→ 统一当成一个换行。
#   正常文件里它等价于 replace("\r\n", "\n")；
#   坏文件（\r\r\n 双 CR、或者整篇只有 \r\r 没有 \n）也能一并修好。
CR_RUN_RE = re.compile(r'\r+\n?')


def is_block(s):  return bool(BLOCK_RE.match(s))
def is_number(s): return bool(NUM_RE.match(s))
def is_sep_line(s): return bool(SEP_LINE_RE.match(s))


# ★ 文件开头最多跳过几行 # 注释。
#   导出文件的开头固定是 2 行 # 说明（见 intl_text._HEADER），这里留一点余量；
#   **之后的 # 开头行是正常句子**（同人游戏真有以 # 开头的文本，是要翻译的）。
#   ★ 改动这个值时必须同步 intl_text._HASH_HEADER_MAX（编译端要按同一规则解析）。
HASH_HEADER_MAX = 4


def hash_header_end(lines, limit=None):
    """
    返回「文件开头 # 注释区」的结束行号（不含）。

    只有 [0, 返回值) 范围内的 # 开头行才算注释、跳过；其余位置的 # 开头行
    一律当正常句子处理（翻译 + 检查 + 编译）。

    规则：
      · 注释区一直延续到**第一个分段区块名**（形如 [10] / [map1]）之前；
      · 区内的空行不算内容，也不打断扫描（译文文件里可能夹着空行，
        例如 \r\r\n 被通用换行读成两行）；
      · 连续遇到 # 开头行即计入注释区，最多 limit 行（默认 HASH_HEADER_MAX=4）；
      · 一旦遇到第一条既非空、也不以 # 开头的行，注释区立刻结束。
    """
    if limit is None:
        limit = HASH_HEADER_MAX
    n = len(lines)
    i = 0
    skipped = 0
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if is_block(s):
            break
        if s.startswith('#') and skipped < limit:
            skipped += 1
            i += 1
            continue
        break
    return i


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
    lone_cr = raw.count("\r") - crlf     # 不在 CRLF 里的 CR
    newline = "\r\n" if (crlf or lone_cr) >= lf else "\n"
    # 内部一律按 LF 切，返回的每一行都不带行尾符（与调用方约定一致）
    # ★ 用 CR_RUN_RE 统一行尾，而不是 replace("\r\n", "\n")：
    #   旧版本写译文时没有 newline=""，把 "\r\n" 写成了 "\r\r\n"；
    #   更早的版本在某些系统上还会写成整篇只有 "\r\r"、一个 "\n" 都没有。
    #   后者用 replace("\r\n","\n") 一刀切不动（根本没有 "\r\n" 子串），
    #   整篇 193KB 会被当成 1 行，编译时解析出 0 条、静默丢光内容。
    #   CR_RUN_RE 把「一串 CR（后面可跟一个 LF）」统一压成一个 "\n"，
    #   三种坏法（\r\r\n / \r\r / 孤立 \r）都能救回来。
    lines = CR_RUN_RE.sub("\n", raw).split("\n")

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

    ★ 不能用「文本模式读 → 看 raw 里有没有 \r\n」：那样通用换行会把
      "\r\n" 归一成 "\n"，判断永远为假。这里直接读字节。
    ★ 孤立 CR（\r\r 这种坏行尾）也算 CR 风格：这种文件是用 CR 当换行的，
      写成 LF 会把它变成「一整行」；沿用 CRLF 才能正常分行。
      要「原样写回、不改动行尾」的场合（应用已编辑 / 换行重排）用这个函数。
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(65536)
    except OSError:
        return default
    crlf = chunk.count(b"\r\n")
    lf = chunk.count(b"\n") - crlf
    lone_cr = chunk.count(b"\r") - crlf
    return "\r\n" if (crlf or lone_cr) >= lf else "\n"


def extract_entries(lines):
    """
    扫描全文件，返回 (entries, special_cases)。

    entries       : [(目标行号, 原文), ...]      正常配对 → 翻译第二行
    special_cases : [ {line_no, next_line_no, text, next_text, reason}, ... ]

    ★ # 开头的行只在**文件开头**算注释（见 hash_header_end，最多
      HASH_HEADER_MAX=4 行）；后面的 # 开头行是正常句子，照样翻译
      （同人游戏真有以 # 开头的文本，例如 #{count} 这类整句占位符）。
    """
    entries, special = [], []
    i, n = 0, len(lines)
    header_end = hash_header_end(lines)

    while i < n:
        s = lines[i].strip()
        if not s or is_block(s) or is_number(s) or is_sep_line(s):
            i += 1
            continue

        # ★ 只有文件头的 # 注释行跳过（翻译、检查、写回都不管它们）
        if i < header_end and s.startswith('#'):
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
        pairable = (bool(next_s) and not is_block(next_s)
                    and not is_number(next_s) and not is_sep_line(next_s))
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
        elif is_sep_line(next_s):
            reason = '下一行为分隔线'
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

    # ★ newline="" 关掉 Python 的换行翻译：否则 newline="\r\n" 时
    #   文本模式会把 "\n" 再翻成 "\r\n"，写出 "\r\r\n" 双 CR，
    #   读回时通用换行把它当成「换行 + 空行」，行数翻倍、解析错位。
    with open(out_path, "w", encoding=encoding, newline="") as f:
        f.write(newline.join(out))

    return replaced