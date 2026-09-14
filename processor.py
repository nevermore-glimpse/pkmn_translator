# -*- coding: utf-8 -*-
"""
文本处理：控制码/标签保护 · 术语替换 · 换行重排 · 占位符校验

占位符：@0@ @1@ @2@ ...（两侧自动补空格）
    · 若原文含 @数字@ 形式，自动升级为 ⟦0⟧ 避免冲突
    · maps 每项：{"token", "original", "added_left", "added_right"}
    · \\n（小写）直接删除；\\N（大写）照常保护
"""
import os
import re

import config
from logger import get_logger

log = get_logger("processor")

# ---------------- 匹配规则 ----------------
# 控制码：\b  \n  \N  \c  \v[1]  \wt[10]  \PN  \ts[3] 等
#   ① \ + 全大写字母（\PN \HM \TM）
#   ② \ + 小写字母 + 紧跟 [（\wt[ \v[ \ts[）
#   ③ \ + 单个字母（\b \n \c \i \l \g \w \v）
CTRL_RE = re.compile(
    r'\\'
    r'(?:'
      r'[A-Z]+'
      r'|[a-z]+(?=\[)'
      r'|[A-Za-z]'
    r')'
    r'(?:\[[^\]]*\])?'
)

# 方括号标签：[Haya] [Player] [Map155] 等
TAG_RE   = re.compile(r'\[[^\]]*\]')

# 花括号占位符：{1} {2} 等
BRACE_RE = re.compile(r'\{[^}]*\}')

# 占位符包裹符
_PH_L_DEFAULT = "@"
_PH_R_DEFAULT = "@"

# 冲突检测：原文含 @数字@ 时切换为 ⟦ ⟧
_PH_COLLISION_RE = re.compile(r'@\d+@')


# ================================================================
# 保护 / 还原
# ================================================================
def protect(text):
    """
    保护控制码、标签、占位符。返回 (安全文本, maps)。
    """
    maps = []
    counter = [0]

    # ① 先删 \n（小写），\N（大写）保留
    text = re.sub(r'\\n', '', text)

    # ② 冲突检测
    left, right = _PH_L_DEFAULT, _PH_R_DEFAULT
    if _PH_COLLISION_RE.search(text):
        left, right = "⟦", "⟧"
        log.debug("检测到原文含 @数字@，切换占位符为 ⟦ ⟧")

    def _p(m):
        token = f"{left}{counter[0]}{right}"
        counter[0] += 1

        s = m.string
        start, end = m.start(), m.end()
        prev_ch = s[start - 1] if start > 0 else ""
        next_ch = s[end] if end < len(s) else ""

        had_left  = (not prev_ch) or prev_ch.isspace()
        had_right = (not next_ch) or next_ch.isspace()

        maps.append({
            "token":       token,
            "original":    m.group(0),
            "added_left":  not had_left,
            "added_right": not had_right,
        })

        return ("" if had_left else " ") + token + ("" if had_right else " ")

    text = CTRL_RE.sub(_p, text)
    text = TAG_RE.sub(_p, text)
    text = BRACE_RE.sub(_p, text)
    return text, maps


def _left_right_of(maps):
    if not maps:
        return _PH_L_DEFAULT, _PH_R_DEFAULT
    return ("⟦", "⟧") if maps[0]["token"].startswith("⟦") else ("@", "@")


def _loose_pattern(idx, left, right):
    """宽松匹配 token 的各种变体。"""
    n = r'0*' + str(idx)
    if left == "@":
        return re.compile(
            r'(?:'
            r'@{1,2}\s*' + n + r'\s*@{1,2}|'
            r'\[\s*@\s*' + n + r'\s*@\s*\]'
            r')'
        )
    return re.compile(
        r'(?:'
        r'⟦\s*' + n + r'\s*⟧|'
        r'\[\[\s*' + n + r'\s*\]\]|'
        r'\[\s*' + n + r'\s*\]|'
        r'\(\s*' + n + r'\s*\)|'
        r'\{\s*' + n + r'\s*\}'
        r')'
    )


def restore(text, maps):
    """还原占位符，并按 added_left / added_right 删掉补出的空格。"""
    result = text
    left, right = _left_right_of(maps)

    for idx, item in enumerate(maps):
        token       = item["token"]
        original    = item["original"]
        added_left  = item["added_left"]
        added_right = item["added_right"]

        pos = result.find(token)
        if pos != -1:
            m_start, m_end = pos, pos + len(token)
        else:
            m = _loose_pattern(idx, left, right).search(result)
            if m is None:
                continue
            m_start, m_end = m.start(), m.end()

        left_cut = right_cut = 0
        if added_left and m_start > 0 and result[m_start - 1] == " ":
            left_cut = 1
        if added_right and m_end < len(result) and result[m_end] == " ":
            right_cut = 1

        # ★ lambda 防止 original 里的 \w \n 之类被当转义
        result = (result[:m_start - left_cut]
                  + original
                  + result[m_end + right_cut:])

    return result


def verify(text, maps):
    """校验译文占位符是否齐全（顺序 + 数量）。"""
    if not maps:
        return True, []

    left, right = _left_right_of(maps)
    missing, pos = [], 0

    for idx, item in enumerate(maps):
        token = item["token"]
        i = text.find(token, pos)
        if i != -1:
            pos = i + len(token)
            continue
        m = _loose_pattern(idx, left, right).search(text, pos)
        if not m:
            missing.append(token)
            continue
        pos = m.end()

    return (len(missing) == 0), missing


# ================================================================
# 术语表
# ================================================================
_TERMS = []


def load_terms():
    global _TERMS
    _TERMS = []
    if not config.APPLY_TERMS:
        log.info("术语替换已关闭（APPLY_TERMS=False）")
        return
    if not os.path.exists(config.TERM_FILE):
        log.warning("术语表 %s 不存在，跳过", config.TERM_FILE)
        return

    ns = {}
    with open(config.TERM_FILE, "r", encoding="utf-8") as f:
        exec(f.read(), ns)
    td = ns.get("TERM_DICT", {})

    # 过滤：含 \ 或 [] 的键跳过；长度 ≤ 3 的英文键跳过（防误伤 Don't / Won't）
    good = []
    skipped_short = 0
    for k, v in td.items():
        if "\\" in k or "[" in k or "]" in k:
            continue
        if len(k) <= 3 and k.isascii() and k.isalpha():
            skipped_short += 1
            continue
        good.append((k, v))
    good.sort(key=lambda x: -len(x[0]))
    _TERMS = good
    log.info("术语表加载：%d 条（跳过短词 %d 条）",
             len(_TERMS), skipped_short)


def apply_terms(text):
    if not _TERMS:
        return text
    word_chars = r'\w\u00C0-\u024F'
    for en, zh in _TERMS:
        try:
            pat = re.compile(r'(?<![' + word_chars + r'])' +
                             re.escape(en) +
                             r'(?![' + word_chars + r'])')
            text = pat.sub(lambda m, z=zh: z, text)   # ★ lambda 防转义
        except re.error:
            text = text.replace(en, zh)
    return text


# ================================================================
# 换行重排
# ================================================================
_CTRL_FOR_REWRAP = re.compile(r'\\[A-Za-z]+(?:\[[^\]]*\])?|@\d+@|⟦\d+⟧')


def rewrap(text, min_chars=None, max_chars=None, punct=None):
    """
    翻译后重新分行：
      · 累计 max_chars 个字符 → 强制换行
      · 累计 ≥ min_chars → 往后看 1 个字符，是软断点就换行
      · 遇到句末标点（。！？!?）→ 立即换行并清零
      · 遇到 ≥ WRAP_DOTS 个连续的点（如 ......）→ 整体输出后换行
      · 控制码（\\N \\wt[10] \\PN 等）原样输出，不计入、不触发换行
    """
    if not text:
        return text
    min_chars = min_chars if min_chars is not None else config.WRAP_CHARS_MIN
    max_chars = max_chars if max_chars is not None else config.WRAP_CHARS_MAX
    punct     = punct     if punct     is not None else config.WRAP_PUNCT
    punct_set = set(punct) if punct else set()
    dots_min  = getattr(config, "WRAP_DOTS", 3)

    soft_punct = set("，、；：,;: 　")

    parts = []
    count = 0
    i, n = 0, len(text)

    while i < n:
        # 控制码：原样输出
        m = _CTRL_FOR_REWRAP.match(text, i)
        if m:
            parts.append(m.group(0))
            i = m.end()
            continue

        # 连续点：... / ...... / ...... 等
        if text[i] == '.':
            j = i
            while j < n and text[j] == '.':
                j += 1
            if j - i >= dots_min:
                dots = text[i:j]
                parts.append(dots)
                parts.append("\\n")
                count = 0
                i = j
                continue
            # 少于 dots_min 的点，作为普通字符走下面的逻辑

        ch = text[i]
        parts.append(ch)
        count += 1
        i += 1

        # ① 句末标点：立即换行
        if ch in punct_set:
            parts.append("\\n")
            count = 0
            continue

        # ② 达到上限：强制换行
        if count >= max_chars:
            parts.append("\\n")
            count = 0
            continue

        # ③ 区间 [min_chars, max_chars)：看下一字符是否是软断点
        if count >= min_chars and i < n:
            next_ch = text[i]
            if next_ch in soft_punct:
                parts.append("\\n")
                count = 0

    s = "".join(parts)
    while s.endswith("\\n"):
        s = s[:-2]
    return s

# ================================================================
# 自动换行（旧版，按显示宽度，默认关闭）
# ================================================================
def char_width(c):
    o = ord(c)
    if 0x4E00 <= o <= 0x9FFF:  return 1.0
    if 0x3000 <= o <= 0x303F:  return 1.0
    if 0xFF00 <= o <= 0xFFEF:  return 1.0
    return 0.5


def auto_wrap(text, max_width=None):
    if not text:
        return text
    max_width = max_width or config.MAX_LINE_WIDTH

    tokens = []
    def _protect(m):
        tokens.append((f"\x00{len(tokens)}\x00", m.group(0)))
        return tokens[-1][0]

    protected = re.compile(r'@\d+@|⟦\d+⟧').sub(_protect, text)

    items = []
    i = 0
    while i < len(protected):
        if protected[i] == "\x00":
            j = protected.find("\x00", i + 1)
            if j == -1:
                items.append((protected[i], 0.0)); i += 1; continue
            items.append((protected[i:j + 1], 0.0)); i = j + 1
        else:
            items.append((protected[i], char_width(protected[i]))); i += 1

    break_chars = set("。！？，、；：!?.,;:）)】」』》”’")
    lines, cur, cur_w = [], [], 0.0
    for item, w in items:
        if cur_w + w > max_width and cur:
            bp = -1
            for k in range(len(cur) - 1, max(0, len(cur) - 15) - 1, -1):
                if cur[k][0] in break_chars:
                    bp = k + 1; break
            if bp > 0:
                lines.append("".join(x for x, _ in cur[:bp]).rstrip())
                cur = cur[bp:]
            else:
                lines.append("".join(x for x, _ in cur).rstrip())
                cur = []
            cur_w = sum(x[1] for x in cur)
        cur.append((item, w)); cur_w += w
    if cur:
        lines.append("".join(x for x, _ in cur).rstrip())

    result = "\\n".join(lines)
    for tok, orig in tokens:
        result = result.replace(tok, orig)
    return result


# ================================================================
# 一步到位
# ================================================================
def prepare(text):
    safe, maps = protect(text)
    safe = apply_terms(safe)
    return safe, maps


def finalize(text, maps):
    text = restore(text, maps)
    if config.REWRAP_ENABLE:
        text = rewrap(text)
    elif config.AUTO_WRAP:
        text = auto_wrap(text)
    return text