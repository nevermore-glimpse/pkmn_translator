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
    speaker_ranges = []

    # 说话人标签：\tg[Alba] → 拆成三段 \tg[ / Alba / ]
    for m in SPEAKER_TAG_RE.finditer(text):
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

    # 其它控制码
    for m in CTRL_RE.finditer(text):
        if _in_speaker(m.start(), m.end()):
            continue
        regions.append({
            "start": m.start(),
            "end":   m.end(),
            "segments": [
                {"protect": True, "content": m.group(0), "no_pad": False},
            ],
        })

    # 方括号标签
    for m in TAG_RE.finditer(text):
        if _in_speaker(m.start(), m.end()):
            continue
        regions.append({
            "start": m.start(),
            "end":   m.end(),
            "segments": [
                {"protect": True, "content": m.group(0), "no_pad": False},
            ],
        })

    # 花括号占位符
    for m in BRACE_RE.finditer(text):
        if _in_speaker(m.start(), m.end()):
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
    #   重叠场景：CTRL_RE 的 \w[speech hgss 3] 与 TAG_RE 的 [speech hgss 3]
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
_TERM_MAP_LOWER = {}
_COMBINED_RE = None

def _check_case_conflicts(terms):
    """
    检测术语表里是否有大小写不同但译文不同的词。
    例如：
        "Owen": "欧文"
        "OWEN": "OWEN"
    这种会导致小写索引冲突，取后者。此时输出警告。
    """
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
    _TERM_MAP_LOWER = {}          # ★ 加这个
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

    # ★ 关键优化：把 N 个词合并成一个正则，大小写不敏感
    if good:
        word_chars = r'\w\u00C0-\u024F'
        alternation = '|'.join(re.escape(k) for k, _ in good)
        pattern = (r'(?<![' + word_chars + r'])('
                   + alternation +
                   r')(?![' + word_chars + r'])')
        try:
            # ★ re.IGNORECASE：Pokérus / PokéRus / POKÉRUS 都能匹配
            _COMBINED_RE = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            log.error("术语表合并正则失败：%s（将退化为逐条匹配）", e)
            _COMBINED_RE = None

    # ★ 小写索引，供 IGNORECASE 匹配后查表用
    _TERM_MAP_LOWER = {k.lower(): v for k, v in good}

    # ★ 检测大小写冲突（同一个词有多种大小写但译文不同）
    _check_case_conflicts(good)

    log.info("术语表加载：%d 条（跳过短词 %d 条，大小写不敏感）",
             len(_TERMS), skipped_short)


def find_terms(text):
    """
    找出 text 中命中的术语，返回 [(原文, 译文), ...]（去重，保持出现顺序）。
    大小写不敏感。
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
    """
    术语兜底替换：把 text 里命中的术语原文替换为术语表译文。
    大小写不敏感。用于每批翻译后的兜底修正。
    """
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
    分析原文，返回 [bool, ...]：
      每个"标点单元"后是否紧跟 \\n。

    标点单元定义：
      · 单个 . ! ? 。 ！ ？         → 一次
      · 连续 2 个以上半角点（.. ... ......） → 整体算一次
    """
    if not text:
        return []
    result = []
    n = len(text)
    i = 0
    while i < n:
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
            # 单个点 → 落到下面按普通标点处理

        # 单个标点
        if ch in _PUNCT_SET:
            has_break = (i + 2 < n and
                         text[i + 1] == '\\' and
                         text[i + 2] == 'n')
            result.append(has_break)
        i += 1
    return result


def apply_breaks(text, breaks):
    """
    按 breaks 列表，在译文对应位置的标点后补加 \\n。

    连续点处理方式与 analyze_breaks 保持一致：
      · 译文里的连续 2+ 个点 → 作为一个单元
      · 若对应原文位置有换行 → 加 \\n
    """
    if not text or not breaks:
        return text

    result = []
    idx = 0
    n = len(text)
    i = 0
    while i < n:
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
                        result.append('\\n')
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
                    result.append('\\n')
            idx += 1
        i += 1
    return ''.join(result)

# ================================================================
# 换行重排
# ================================================================
# 复用 CTRL_RE 的已知名单，避免贪婪匹配 \NABC 之类
_CTRL_FOR_REWRAP = re.compile(
    r'(?:' + CTRL_RE.pattern + r')'
    r'|@\d+@|⟦\d+⟧'
)


def rewrap(text, min_chars=None, max_chars=None, punct=None, min_gap=None):
    """
    翻译后重新分行：

      · 累计 max_chars 个字符 → 强制换行
      · 累计 ≥ min_chars → 往后看 1 个字符，是软断点就换行
      · 控制码原样输出，不计入、不触发换行
      · 遇到 \\n 视为换行边界，重置计数
      · 文本末尾不追加 \\n
       若需要按原文换行位置对齐，由 apply_breaks 处理。
    """
    if not text:
        return text
    min_chars = min_chars if min_chars is not None else config.WRAP_CHARS_MIN
    max_chars = max_chars if max_chars is not None else config.WRAP_CHARS_MAX
    min_gap   = min_gap   if min_gap   is not None else getattr(config, "WRAP_MIN_GAP", 10)

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

        # 连续点：作为一个整体加入，只累计字数，不主动换行
        if text[i] == '.':
            j = i
            while j < n and text[j] == '.':
                j += 1
            dots = text[i:j]
            parts.append(dots)
            count += (j - i)
            i = j
            # 若累计超过 max_chars，在此处强制换行
            if count >= max_chars:
                parts.append("\\n")
                count = 0
            continue

        ch = text[i]
        parts.append(ch)
        count += 1
        i += 1

        if count >= max_chars:
            parts.append("\\n")
            count = 0
            continue

        if count >= soft_threshold and i < n:
            next_ch = text[i]
            if next_ch in soft_punct:
                parts.append("\\n")
                count = 0

    s = "".join(parts)
    while s.endswith("\\n"):
        s = s[:-2]
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

def finalize(text, maps, breaks=None):
    """
    还原占位符 → 按原文换行位置补 \\n → 字数重排。
    breaks 来自 prepare() 的第三个返回值。
    """
    text = restore(text, maps)
    if breaks:
        text = apply_breaks(text, breaks)
    if config.REWRAP_ENABLE:
        text = rewrap(text)
    return text