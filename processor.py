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

# ================================================================
# 控制码匹配（已知名单优先，避免贪婪吃首字母）
#
#   优先级 1：带参数的控制码，要求紧跟 [（如 \tg[Owen] \v[50] \wt[10]）
#   优先级 2：无参数的多字母控制码（\PN \wu）
#   优先级 3：无参数的单字母控制码（\N \n \b \c \g \w \l \i \v）
#
# 关键点：\N 后面无论跟什么字母都只吃 \N 两个字符，
#         \NSigamos → 匹配 \N，保留 Sigamos
# ================================================================
CTRL_RE = re.compile(
    r'\\'
    r'(?:'
      # 优先级 1：带参数
      r'(?:wtnp|wt|tg|ts|v|c|w)(?=\[)(?:\[[^\]]*\])?'
      r'|'
      # 优先级 2：无参数多字母（长的在前）
      r'(?:PN|wu)'
      r'|'
      # 优先级 3：无参数单字母
      r'[Nnbcgwlvi]'
    r')'
)
# 用于检测 protect() 后残留的未识别控制码
LEFTOVER_CTRL_RE = re.compile(r'\\[A-Za-z]+')
# 方括号标签：[Haya] [Player] [Map155] 等
TAG_RE   = re.compile(r'\[[^\]]*\]')

# 花括号占位符：{1} {2} 等
BRACE_RE = re.compile(r'\{[^}]*\}')

# 占位符包裹符
_PH_L_DEFAULT = "@"
_PH_R_DEFAULT = "@"

# 冲突检测：原文含 @数字@ 时切换为 ⟦ ⟧
_PH_COLLISION_RE = re.compile(r'@\d+@')
# 说话人标签：\tg[Owen]  \tg[Fátima]  \tg[Lionel, el Campeón de Galar]
SPEAKER_TAG_RE = re.compile(r'\\tg\[([^\]]*)\]')

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
    def _p_speaker(m):
        """
        \tg[Owen] → @N@@M@Owen@K@ （三个占位符：\\tg[  /  ]）
        \tg[ 和 ] 被保护，Owen 保持明文送模型翻译。
        """
        name = m.group(1).strip()

        def _mk(orig):
            tok = f"{left}{counter[0]}{right}"
            counter[0] += 1
            maps.append({
                "token": tok,
                "original": orig,
                "added_left": False,
                "added_right": False,
            })
            return tok

        lb = _mk("\\tg[")     # 保护 \tg[
        rb = _mk("]")         # 保护 ]
        return lb + name + rb
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

    text = SPEAKER_TAG_RE.sub(_p_speaker, text)
    text = CTRL_RE.sub(_p, text)
    text = TAG_RE.sub(_p, text)
    text = BRACE_RE.sub(_p, text)
    return text, maps

def detect_unknown_ctrl(safe_text):
    """
    在 protect() 处理后的文本中，找出未被 CTRL_RE 识别的控制码。

    原理：protect() 会把已知控制码都替换成 @N@ 占位符，
    如果 safe_text 里还有 \\字母 残留，就是名单外的。

    返回 [(token, context), ...]
    """
    if not safe_text:
        return []
    results = []
    for m in LEFTOVER_CTRL_RE.finditer(safe_text):
        token = m.group(0)
        s = max(0, m.start() - 30)
        e = min(len(safe_text), m.end() + 30)
        ctx = safe_text[s:e]
        results.append((token, ctx))
    return results

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
# 术语表（优化版：合并成一次正则匹配）
#   _TERMS      : [(原文, 译文), ...] 按长度降序，保留给外部查询用
#   _TERM_MAP   : {原文: 译文} 用于 lambda 内查表
#   _COMBINED_RE: 4419 个词合并成的单个正则
# ================================================================
_TERMS = []
_TERM_MAP = {}
_COMBINED_RE = None


def load_terms():
    global _TERMS, _TERM_MAP, _COMBINED_RE

    _TERMS = []
    _TERM_MAP = {}
    _COMBINED_RE = None

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

    # ★ 按长度降序：长的在前，正则交替匹配时优先命中长词
    good.sort(key=lambda x: -len(x[0]))
    _TERMS = good
    _TERM_MAP = dict(good)

    # ★ 关键优化：把 N 个词合并成一个正则
    if good:
        word_chars = r'\w\u00C0-\u024F'
        alternation = '|'.join(re.escape(k) for k, _ in good)
        pattern = (r'(?<![' + word_chars + r'])('
                   + alternation +
                   r')(?![' + word_chars + r'])')
        try:
            _COMBINED_RE = re.compile(pattern)
        except re.error as e:
            log.error("术语表合并正则失败：%s（将退化为逐条匹配）", e)
            _COMBINED_RE = None

    log.info("术语表加载：%d 条（跳过短词 %d 条）",
             len(_TERMS), skipped_short)


def apply_terms(text):
    """一次扫描完成所有术语替换。"""
    if not _COMBINED_RE:
        # 兜底：正则编译失败时退化为逐条替换
        if not _TERMS:
            return text
        word_chars = r'\w\u00C0-\u024F'
        for en, zh in _TERMS:
            try:
                pat = re.compile(r'(?<![' + word_chars + r'])' +
                                 re.escape(en) +
                                 r'(?![' + word_chars + r'])')
                text = pat.sub(lambda m, z=zh: z, text)
            except re.error:
                text = text.replace(en, zh)
        return text

    # 主路径：一次 sub 完成全部替换
    return _COMBINED_RE.sub(
        lambda m: _TERM_MAP.get(m.group(1), m.group(1)),
        text,
    )


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
    max_width = max_width

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
    return text