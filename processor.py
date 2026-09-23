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
# 原子正则：所有可识别的控制码/标签/占位符
# ================================================================
# ① 尖括号命令：
#    · \wt<<[>>10<<]>>  \se<<[>>ItemGet<<]>>  （带反斜杠的命令）
#    · \<<n>>  <<n>>  <<1>>  （裸尖括号，含换行符 <<n>>）
#    用 (?!\[|\]) 排除 <<[>> 和 <<]>> 这两个成对标记
_ANGLE_CMD_PAT = (
    r'\\[A-Za-z]+<<\[>>.*?<<\]>>'      # 带参数：\命令<<[>>内容<<]>>
    r'|'
    r'\\?<<(?!\[|\])[^>]*>>'           # 裸尖括号：<<n>>  \<<n>>  <<1>>
)

# ② HTML 风格标签：<ar> </ar> <color=red>
_HTML_TAG_PAT = r'</?[a-zA-Z][^>]*>'

# ③ HTML 实体：&quot;  &amp;  &#39;  &#x27;
_HTML_ENTITY_PAT = r'&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);'

# ③ 命令式控制码：\tg[Owen]  \v[50]  \wt[10]  \PN  \N  \n  \b  \c  \se  ...
_CTRL_PAT = (
    r'\\'
    r'(?:'
      r'(?:wtnp|wt|tg|ts|v|c|w|se)(?=\[)(?:\[[^\]]*\])?'   # 带参数
      r'|'
      r'(?:wtnp|wt|tg|PN|wu|HM|TM|se)'                      # 无参数多字母（长的在前）
      r'|'
      r'[Nnbcgwlvi]'                                        # 单字母
    r')'
)

# ④ 方括号标签
_TAG_PAT   = r'\[[^\]]*\]'
# ⑤ 花括号占位符
_BRACE_PAT = r'\{[^}]*\}'

# 各自独立的 re 对象
ANGLE_CMD_RE = re.compile(_ANGLE_CMD_PAT)
HTML_TAG_RE  = re.compile(_HTML_TAG_PAT)
CTRL_RE      = re.compile(_CTRL_PAT)
TAG_RE       = re.compile(_TAG_PAT)
BRACE_RE     = re.compile(_BRACE_PAT)
SPEAKER_TAG_RE = re.compile(r'\\tg\[([^\]]*)\]')

# 未识别控制码检测（原始文本中残留的 \字母）
LEFTOVER_CTRL_RE = re.compile(r'\\[A-Za-z]+')

ALL_CTRL_RE = re.compile(
    r'(?:'
    + _ANGLE_CMD_PAT    + r'|'
    + _CTRL_PAT         + r'|'
    + _HTML_TAG_PAT     + r'|'
    + _HTML_ENTITY_PAT
    + r')'
)

_CTRL_FOR_REWRAP = re.compile(
    r'(?:'
    + _ANGLE_CMD_PAT    + r'|'
    + _CTRL_PAT         + r'|'
    + _HTML_TAG_PAT     + r'|'
    + _HTML_ENTITY_PAT
    + r')'
    r'|@\d+@|⟦\d+⟧'
)

# 占位符包裹符
_PH_L_DEFAULT = "@"
_PH_R_DEFAULT = "@"

# 冲突检测：原文含 @数字@ 时切换为 ⟦ ⟧
_PH_COLLISION_RE = re.compile(r'@\d+@')


# ================================================================
# 句首控制码前缀：提取 / 剥离
# ================================================================
def split_prefix(text):
    """
    提取句子开头的连续控制码串（含 <<[>>...<<]>> 和 HTML 标签）。
    返回 (prefix, body)：
      prefix: 句首控制码串（如 '\\w[speech hgss 3]\\tg[???]'）；无则为 ""
      body:   剩余正文
    """
    if not text:
        return "", text

    i, n = 0, len(text)
    while i < n:
        m = ALL_CTRL_RE.match(text, i)      # ★ 用统合正则
        if not m:
            break
        i = m.end()

    if i == 0:
        return "", text
    return text[:i], text[i:]


def strip_prefix(text):
    """剥离句首控制码，返回 body。"""
    return split_prefix(text)[1]


# ================================================================
# 保护 / 还原
# ================================================================
def protect(text):
    """
    保护控制码、标签、占位符。返回 (安全文本, maps)。

    ★ 占位符编号按文本从左到右的顺序分配，保证 @0@ @1@ @2@ ...
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

    def _new_token():
        tok = f"{left}{counter[0]}{right}"
        counter[0] += 1
        return tok

    # ③ 收集所有待保护区域
    #    每个 region 含 1..N 段，每段标记 protect=True 或 False
    regions = []

    # ---------- ③.1 尖括号命令（优先级最高） ----------
    angle_ranges = []
    for m in ANGLE_CMD_RE.finditer(text):
        regions.append({
            "start": m.start(),
            "end":   m.end(),
            "segments": [
                {"protect": True, "content": m.group(0), "no_pad": False},
            ],
        })
        angle_ranges.append((m.start(), m.end()))

    def _in_angle(s, e):
        return any(s < se and e > ss for ss, se in angle_ranges)

    # ---------- ③.2 HTML 风格标签 ----------
    html_ranges = []
    for m in HTML_TAG_RE.finditer(text):
        if _in_angle(m.start(), m.end()):
            continue
        regions.append({
            "start": m.start(),
            "end":   m.end(),
            "segments": [
                {"protect": True, "content": m.group(0), "no_pad": False},
            ],
        })
        html_ranges.append((m.start(), m.end()))

    def _in_html(s, e):
        return any(s < se and e > ss for ss, se in html_ranges)
    # ---------- ③.2.5 HTML 实体 ----------
    entity_ranges = []
    for m in re.finditer(_HTML_ENTITY_PAT, text):
        if _in_angle(m.start(), m.end()):
            continue
        if _in_html(m.start(), m.end()):
            continue
        regions.append({
            "start": m.start(),
            "end":   m.end(),
            "segments": [
                {"protect": True, "content": m.group(0), "no_pad": False},
            ],
        })
        entity_ranges.append((m.start(), m.end()))

    def _in_entity(s, e):
        return any(s < se and e > ss for ss, se in entity_ranges)
    # ---------- ③.3 说话人标签：\tg[Alba] → 三段 \tg[ / Alba / ] ----------
    speaker_ranges = []
    for m in SPEAKER_TAG_RE.finditer(text):
        if _in_angle(m.start(), m.end()) or _in_html(m.start(), m.end()):
            continue
        if _in_entity(m.start(), m.end()):
            continue
        name = m.group(1).strip()
        regions.append({
            "start": m.start(),
            "end":   m.end(),
            "segments": [
                {"protect": True,  "content": "\\tg[", "no_pad": True},
                {"protect": False, "content": name},
                {"protect": True,  "content": "]",    "no_pad": True},
            ],
        })
        speaker_ranges.append((m.start(), m.end()))

    def _in_speaker(s, e):
        return any(s < se and e > ss for ss, se in speaker_ranges)

    # ---------- ③.4 其它命令式控制码 ----------
    for m in CTRL_RE.finditer(text):
        if _in_speaker(m.start(), m.end()):
            continue
        if _in_angle(m.start(), m.end()):
            continue
        if _in_html(m.start(), m.end()):
            continue
        if _in_entity(m.start(), m.end()):
            continue
        regions.append({
            "start": m.start(),
            "end":   m.end(),
            "segments": [
                {"protect": True, "content": m.group(0), "no_pad": False},
            ],
        })

    # ---------- ③.5 方括号标签 ----------
    for m in TAG_RE.finditer(text):
        if _in_speaker(m.start(), m.end()):
            continue
        if _in_angle(m.start(), m.end()):
            continue
        if _in_html(m.start(), m.end()):
            continue
        if _in_entity(m.start(), m.end()):
            continue
        regions.append({
            "start": m.start(),
            "end":   m.end(),
            "segments": [
                {"protect": True, "content": m.group(0), "no_pad": False},
            ],
        })

    # ---------- ③.6 花括号占位符 ----------
    for m in BRACE_RE.finditer(text):
        if _in_speaker(m.start(), m.end()):
            continue
        if _in_angle(m.start(), m.end()):
            continue
        if _in_html(m.start(), m.end()):
            continue
        if _in_entity(m.start(), m.end()):
            continue
        regions.append({
            "start": m.start(),
            "end":   m.end(),
            "segments": [
                {"protect": True, "content": m.group(0), "no_pad": False},
            ],
        })

    # ④ 按位置排序（start 升序，同 start 时长者优先）
    regions.sort(key=lambda r: (r["start"], -(r["end"] - r["start"])))

    # ★ 去除重叠 region（保留先加入的、更长的）
    filtered = []
    for r in regions:
        overlaps = False
        for existing in filtered:
            if r["start"] < existing["end"] and r["end"] > existing["start"]:
                overlaps = True
                break
        if not overlaps:
            filtered.append(r)
    regions = filtered

    # ⑤ 从左到右依次分配 token
    for region in regions:
        s, e = region["start"], region["end"]
        prev_ch = text[s - 1] if s > 0 else ""
        next_ch = text[e] if e < len(text) else ""
        had_left  = (not prev_ch) or prev_ch.isspace()
        had_right = (not next_ch) or next_ch.isspace()

        new_segments = []
        for seg in region["segments"]:
            if not seg["protect"]:
                new_segments.append({"protect": False,
                                     "content": seg["content"]})
                continue

            tok = _new_token()
            if seg.get("no_pad"):
                added_left = False
                added_right = False
            else:
                added_left  = not had_left
                added_right = not had_right

            maps.append({
                "token":       tok,
                "original":    seg["content"],
                "added_left":  added_left,
                "added_right": added_right,
            })
            new_segments.append({
                "protect":     True,
                "token":       tok,
                "added_left":  added_left,
                "added_right": added_right,
            })
        region["new_segments"] = new_segments

    # ⑥ 从后往前替换，避免位置偏移
    result = text
    for region in reversed(regions):
        parts = []
        for seg in region["new_segments"]:
            if seg["protect"]:
                lpad = " " if seg["added_left"]  else ""
                rpad = " " if seg["added_right"] else ""
                parts.append(lpad + seg["token"] + rpad)
            else:
                parts.append(seg["content"])
        replacement = "".join(parts)
        result = (result[:region["start"]]
                  + replacement
                  + result[region["end"]:])

    return result, maps


def detect_unknown_ctrl(safe_text):
    """
    在 protect() 处理后的文本中，找出未被识别的控制码。

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


# ================================================================
# 纯控制符句子检测
# ================================================================
_PURE_TEXT_RE = re.compile(r'[\s\W\d_]+', re.UNICODE)


def is_pure_control(text, min_text_len=None):
    """
    判断文本是否"纯控制符"（剥离所有控制码后没有可翻译内容）。
    """
    if min_text_len is None:
        min_text_len = getattr(config, "PURE_CONTROL_MIN_LEN", 2)
    if not text:
        return True

    t = text
    t = ANGLE_CMD_RE.sub('', t)
    t = HTML_TAG_RE.sub('', t)
    t = re.sub(_HTML_ENTITY_PAT, '', t)   # ★ HTML 实体也剥离
    t = CTRL_RE.sub('', t)
    t = TAG_RE.sub('', t)
    t = BRACE_RE.sub('', t)
    effective = _PURE_TEXT_RE.sub('', t)
    return len(effective) < min_text_len


# ================================================================
# 占位符还原 / 校验
# ================================================================
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
_TERM_MAP = {}
_TERM_MAP_LOWER = {}
_COMBINED_RE = None


def _check_case_conflicts(terms):
    """检测术语表里是否有大小写不同但译文不同的词。"""
    lower_map = {}
    conflicts = []
    for k, v in terms:
        lk = k.lower()
        if lk in lower_map and lower_map[lk] != v:
            conflicts.append((k, lower_map[lk], v))
        lower_map[lk] = v

    if conflicts:
        log.warning("检测到 %d 组大小写冲突的术语：", len(conflicts))
        for k, v1, v2 in conflicts[:10]:
            log.warning("  %s  →  已有 %r，新值 %r（取新值）", k, v1, v2)
        if len(conflicts) > 10:
            log.warning("  … 其余 %d 组省略", len(conflicts) - 10)


def load_terms():
    global _TERMS, _TERM_MAP, _TERM_MAP_LOWER, _COMBINED_RE
    _TERMS = []
    _TERM_MAP = {}
    _TERM_MAP_LOWER = {}
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
    _TERM_MAP = dict(good)

    if good:
        word_chars = r'\w\u00C0-\u024F'
        alternation = '|'.join(re.escape(k) for k, _ in good)
        pattern = (r'(?<![' + word_chars + r'])('
                   + alternation +
                   r')(?![' + word_chars + r'])')
        try:
            _COMBINED_RE = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            log.error("术语表合并正则失败：%s（将退化为逐条匹配）", e)
            _COMBINED_RE = None

    _TERM_MAP_LOWER = {k.lower(): v for k, v in good}
    _check_case_conflicts(good)

    log.info("术语表加载：%d 条（跳过短词 %d 条，大小写不敏感）",
             len(_TERMS), skipped_short)


def find_terms(text):
    """
    找出 text 中命中的术语，返回 [(原文, 译文), ...]（去重，保持出现顺序）。
    """
    if not _COMBINED_RE or not text:
        return []

    seen = set()
    result = []
    for m in _COMBINED_RE.finditer(text):
        matched = m.group(1)
        dst = _TERM_MAP.get(matched)
        if dst is None:
            dst = _TERM_MAP_LOWER.get(matched.lower())
        if not dst:
            continue
        key = matched.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append((matched, dst))
    return result


def apply_terms(text):
    """术语兜底替换：把 text 里命中的术语原文替换为术语表译文。"""
    if not _COMBINED_RE or not text:
        return text

    def _replace(m):
        matched = m.group(1)
        dst = _TERM_MAP.get(matched)
        if dst is None:
            dst = _TERM_MAP_LOWER.get(matched.lower())
        return dst if dst else matched

    return _COMBINED_RE.sub(_replace, text)


# ================================================================
# 按原文换行位置对齐译文
# ================================================================
_PUNCT_SET = set(".!?。！？")


def analyze_breaks(text):
    """
    分析原文，返回 [bool, ...]：每个"标点单元"后是否紧跟 \\n。
    ★ 遍历时跳过所有控制码区域，避免控制码内部的标点被误判。
    """
    if not text:
        return []
    result = []
    n = len(text)
    i = 0
    while i < n:
        # ★ 先尝试匹配控制码整段并跳过
        m = ALL_CTRL_RE.match(text, i)
        if m:
            i = m.end()
            continue

        ch = text[i]

        # 连续点：2 个及以上作为一组
        if ch == '.':
            j = i
            while j < n and text[j] == '.':
                j += 1
            if j - i >= 2:
                has_break = (j + 1 < n and
                             text[j] == '\\' and
                             text[j + 1] == 'n')
                result.append(has_break)
                i = j
                continue

        # 单个标点
        if ch in _PUNCT_SET:
            has_break = (i + 2 < n and
                         text[i + 1] == '\\' and
                         text[i + 2] == 'n')
            result.append(has_break)
        i += 1
    return result


def apply_breaks(text, breaks, mode="newline"):
    """
    按 breaks 列表，在译文对应位置的标点后补加换行符。
    mode="newline" → 补 \\n
    mode="space"   → 补空格
    """
    if not text or not breaks:
        return text

    insert_char = '\\n' if mode == "newline" else ' '

    result = []
    idx = 0
    n = len(text)
    i = 0
    while i < n:
        m = ALL_CTRL_RE.match(text, i)
        if m:
            result.append(m.group(0))
            i = m.end()
            continue

        ch = text[i]

        # 连续点：2 个及以上作为一组
        if ch == '.':
            j = i
            while j < n and text[j] == '.':
                j += 1
            if j - i >= 2:
                result.append(text[i:j])
                if idx < len(breaks) and breaks[idx]:
                    already = (j + 1 < n and
                               text[j] == '\\' and
                               text[j + 1] == 'n')
                    if not already:
                        result.append(insert_char)
                idx += 1
                i = j
                continue

        # 单个标点
        result.append(ch)
        if ch in _PUNCT_SET:
            if idx < len(breaks) and breaks[idx]:
                already = (i + 2 < n and
                           text[i + 1] == '\\' and
                           text[i + 2] == 'n')
                if not already:
                    result.append(insert_char)
            idx += 1
        i += 1
    return ''.join(result)


# ================================================================
# 换行重排
# ================================================================
def rewrap(text, min_chars=None, max_chars=None, punct=None,
           min_gap=None, mode="newline"):
    """
    翻译后重新分行。
    mode="newline" → 用 \\n
    mode="space"   → 用空格
    """
    if not text:
        return text
    min_chars = min_chars if min_chars is not None else config.WRAP_CHARS_MIN
    max_chars = max_chars if max_chars is not None else config.WRAP_CHARS_MAX
    min_gap   = min_gap   if min_gap   is not None else getattr(config, "WRAP_MIN_GAP", 10)

    insert_char = '\\n' if mode == "newline" else ' '

    soft_punct = set("，、；：,;: 　")
    soft_threshold = max(min_chars, min_gap)

    parts = []
    count = 0
    i, n = 0, len(text)

    while i < n:
        # 控制码：原样输出，不计数、不触发换行
        m = _CTRL_FOR_REWRAP.match(text, i)
        if m:
            token = m.group(0)
            parts.append(token)
            i = m.end()
            if token == '\\n':
                count = 0
            continue

        # 连续点：作为一个整体加入，只累计字数
        if text[i] == '.':
            j = i
            while j < n and text[j] == '.':
                j += 1
            dots = text[i:j]
            parts.append(dots)
            count += (j - i)
            i = j
            if count >= max_chars:
                parts.append(insert_char)
                count = 0
            continue

        ch = text[i]
        parts.append(ch)
        count += 1
        i += 1

        if count >= max_chars:
            parts.append(insert_char)
            count = 0
            continue

        if count >= soft_threshold and i < n:
            next_ch = text[i]
            if next_ch in soft_punct:
                parts.append(insert_char)
                count = 0

    s = "".join(parts)

    # 末尾处理
    if mode == "newline":
        while s.endswith("\\n"):
            s = s[:-2]
    else:
        s = s.rstrip()      # 空格模式剥掉末尾空格

    return s

# ================================================================
# 一步到位
# ================================================================
def prepare(text):
    """
    返回 (safe_text, maps, breaks, hit_terms)。
      hit_terms: [(原文, 译文), ...]  文本中命中的术语，交由 prompt 参考
    """
    breaks = analyze_breaks(text)
    safe, maps = protect(text)
    hit_terms = find_terms(safe)
    return safe, maps, breaks, hit_terms


def finalize(text, maps, breaks=None, mode="newline"):
    """
    还原占位符 → 按原文换行位置补换行符 → 字数重排。
    mode="newline" → 用 \\n
    mode="space"   → 用空格
    """
    text = restore(text, maps)
    if breaks:
        text = apply_breaks(text, breaks, mode=mode)
    if config.REWRAP_ENABLE:
        text = rewrap(text, mode=mode)
    return text