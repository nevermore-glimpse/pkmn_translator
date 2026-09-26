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


# ================================================================
# 保护 / 还原
# ================================================================
def protect(text, drop_newline=True):
    """
    保护控制码、标签、占位符。返回 (安全文本, maps)。

    ★ 占位符编号按文本从左到右的顺序分配，保证 @0@ @1@ @2@ ...
    ★ drop_newline=False 时保留 \\n（中文润色流程需要原样保住换行控制码）
    """
    maps = []
    counter = [0]

    # ① 先删 \n（小写），\N（大写）保留
    if drop_newline:
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


# ================================================================
# 控制码回退：译文里缺失 / 未原样保留的控制码，按原文补回
# ================================================================
def control_symbols(text, ignore_newline=True):
    """
    列出 text 里所有可识别的控制码（按出现顺序，可重复）。
    \\n（小写）是换行符，由重排逻辑另行处理，默认不计入。
    """
    if not text:
        return []
    out = []
    for c in CTRL_RE.findall(text):
        if ignore_newline and c == "\\n":
            continue
        out.append(c)
    out += ANGLE_CMD_RE.findall(text)
    out += HTML_TAG_RE.findall(text)
    out += re.findall(_HTML_ENTITY_PAT, text)
    return out


def _insert_ctrl_by_src(text, ctrl, src):
    """按原文里相邻控制码的位置，把缺失的控制码插回译文。"""
    src_list = control_symbols(src)
    try:
        i = src_list.index(ctrl)
    except ValueError:
        i = 0

    # ① 前一个控制码 → 插到它后面
    for j in range(i - 1, -1, -1):
        prev = src_list[j]
        pos = text.find(prev)
        if pos != -1:
            end = pos + len(prev)
            return text[:end] + ctrl + text[end:]

    # ② 后一个控制码 → 插到它前面
    for j in range(i + 1, len(src_list)):
        nxt = src_list[j]
        pos = text.find(nxt)
        if pos != -1:
            return text[:pos] + ctrl + text[pos:]

    # ③ 找不到锚点：按它在原文里的相对位置插回（比直接追加更贴近原句）
    idx = src.find(ctrl)
    ratio = idx / max(1, len(src))
    if ratio <= 0.02:
        return ctrl + text
    if ratio >= 0.98:
        return text + ctrl
    pos = int(round(len(text) * ratio))
    pos = max(0, min(len(text), pos))
    return text[:pos] + ctrl + text[pos:]


def repair_missing_controls(src, dst):
    """
    比对原文与译文的控制码，把译文中「整个丢失」的控制码按原文原样补回。
    返回 (新译文, 实际补回的控制码列表)。

    例：原文含 \\PN（玩家名），模型把它翻没了 / 翻成别的 →
        这里把 \\PN 原样插回译文，避免检查报告报「符号不匹配」。

    ★ 调用方注意：src 只应传「真正参与翻译的那部分原文」。
      句首前缀若已交给前缀字典单独处理（可能已被改写成另一套控制码），
      调用方必须先把前缀剔除，否则字典改写过的前缀会被误判成"译文缺失控制码"。

    ★ 只有译文中一次都没出现的控制码才算丢失并补回；
      出现次数变少但不为 0 的，保持现状、不重复插入，
      也不会被谎报成"已按原文补回"（旧实现会报，导致日志与结果对不上）。
    """
    if not src or not dst:
        return dst, []

    from collections import Counter
    src_cnt = Counter(control_symbols(src))
    dst_cnt = Counter(control_symbols(dst))
    missing = src_cnt - dst_cnt
    if not missing:
        return dst, []

    text = dst
    fixed = []
    for ctrl, need in missing.items():
        if dst_cnt.get(ctrl, 0) > 0:
            # 译文里还有，只是次数比原文少：不重复插入，避免错位或重复
            log.debug("控制码 %r 出现次数少于原文（差 %d 次），保持现状",
                      ctrl, need)
            continue
        for _ in range(need):
            text = _insert_ctrl_by_src(text, ctrl, src)
        fixed.extend([ctrl] * need)
    return text, fixed


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
#   ★ 性能：术语表动辄 4000+ 条，若整体拼成一个超长 alternation 正则，
#     每条句子做一次 finditer 都要试遍全部分支，慢且容易撞上正则规模上限。
#     这里拆成两条路：
#        · 单词类术语（不含空格/标点）→ 直接切词后查哈希表，O(n)
#        · 多词 / 含标点的术语     → 单独一个小正则
#     语义与原来的"词边界 + 大小写不敏感"完全一致，速度提升一个数量级。
# ================================================================
_TERMS = []

_TERM_SINGLE = {}            # {小写单词: (原文, 译文)}
_TERM_MULTI = []             # [(原文, 译文), ...]  多词 / 含标点
_MULTI_RE = None
_MULTI_MAP = {}
_MULTI_MAP_LOWER = {}

_WORD_CHARS = r'\w\u00C0-\u024F'
_TOKEN_RE = re.compile(r'[' + _WORD_CHARS + r']+')
_PLAIN_TERM_RE = re.compile(r'^[' + _WORD_CHARS + r']+$')

# ★ 占位符 token 正则：@0@ @1@ … 与 ⟦0⟧ ⟦1⟧ …
#   这些是被 protect() 生成的脱敏锚点，绝非可翻译词条。
#   若混入术语表，会被 find_terms 当作命中术语注入 prompt，反向教模型
#   把 @0@ 翻成中文（导致占位符丢失）。因此术语加载/匹配时一律排除。
_PH_TOKEN_RE = re.compile(r'^[@\u27e6]\d+[@\u27e7]$')


def _is_placeholder_token(s):
    """判断字符串是否为占位符 token（@N@ / ⟦N⟧）。"""
    return bool(isinstance(s, str) and _PH_TOKEN_RE.match(s))

_TERMS_LOADED_KEY = None     # (路径, mtime, size, APPLY_TERMS)


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


def _terms_file_key():
    try:
        st = os.stat(config.TERM_FILE)
        return (config.TERM_FILE, st.st_mtime, st.st_size,
                bool(config.APPLY_TERMS))
    except OSError:
        return (config.TERM_FILE, 0, 0, bool(config.APPLY_TERMS))


def load_terms(force=False):
    """
    加载术语表。
    文件未变化（路径 + mtime + 大小）时直接复用内存结果，避免反复 exec 大文件。
    """
    global _TERMS
    global _TERM_SINGLE, _TERM_MULTI, _MULTI_RE
    global _MULTI_MAP, _MULTI_MAP_LOWER, _TERMS_LOADED_KEY

    if not config.APPLY_TERMS:
        if _TERMS or _TERM_SINGLE:
            _TERMS = []
            _TERM_SINGLE, _TERM_MULTI = {}, []
            _MULTI_RE, _MULTI_MAP, _MULTI_MAP_LOWER = None, {}, {}
            _TERMS_LOADED_KEY = None
        log.info("术语替换已关闭（APPLY_TERMS=False）")
        return

    if not os.path.exists(config.TERM_FILE):
        log.warning("术语表 %s 不存在，跳过", config.TERM_FILE)
        return

    key = _terms_file_key()
    if not force and key == _TERMS_LOADED_KEY:
        return          # 文件没变，内存里已有

    ns = {}
    with open(config.TERM_FILE, "r", encoding="utf-8") as f:
        exec(f.read(), ns)
    td = ns.get("TERM_DICT", {})

    good = []
    skipped_short = 0
    skipped_ph = 0
    for k, v in td.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        if "\\" in k or "[" in k or "]" in k:
            continue
        # ★ 占位符 token（@0@ / ⟦0⟧）不是词条，混入会污染 prompt，直接排除
        if _is_placeholder_token(k):
            skipped_ph += 1
            continue
        if len(k) <= 3 and k.isascii() and k.isalpha():
            skipped_short += 1
            continue
        good.append((k, v))
    if skipped_ph:
        log.info("术语表跳过 %d 条占位符型伪术语（@0@ 等）", skipped_ph)

    good.sort(key=lambda x: -len(x[0]))

    _TERMS = good

    # ---- 拆分：单词类 / 多词类 ----
    _TERM_SINGLE = {}
    _TERM_MULTI = []
    seen_single = set()
    for k, v in good:
        if _PLAIN_TERM_RE.match(k):
            lk = k.lower()
            if lk in seen_single:
                continue
            seen_single.add(lk)
            _TERM_SINGLE[lk] = (k, v)
        else:
            _TERM_MULTI.append((k, v))

    _MULTI_MAP = dict(_TERM_MULTI)
    _MULTI_MAP_LOWER = {k.lower(): v for k, v in _TERM_MULTI}
    _MULTI_RE = None
    if _TERM_MULTI:
        alternation = '|'.join(re.escape(k) for k, _ in _TERM_MULTI)
        pattern = (r'(?<![' + _WORD_CHARS + r'])('
                   + alternation +
                   r')(?![' + _WORD_CHARS + r'])')
        try:
            _MULTI_RE = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            log.error("多词术语正则失败：%s（这部分术语将用逐条匹配）", e)
            _MULTI_RE = None

    _TERMS_LOADED_KEY = key

    _check_case_conflicts(good)
    log.info("术语表加载：%d 条（单词 %d / 多词 %d，跳过短词 %d 条）",
             len(_TERMS), len(_TERM_SINGLE), len(_TERM_MULTI), skipped_short)


def find_terms(text):
    """
    找出 text 中命中的术语，返回 [(原文, 译文), ...]（去重，保持出现顺序）。

    ★ 多词术语优先：命中 "Profesor Oak" 时不再单独报 "Profesor"。
    """
    if not text or (not _TERM_SINGLE and not _MULTI_RE):
        return []

    seen = set()
    result = []
    spans = []

    if _MULTI_RE:
        for m in _MULTI_RE.finditer(text):
            matched = m.group(1)
            dst = _MULTI_MAP.get(matched)
            if dst is None:
                dst = _MULTI_MAP_LOWER.get(matched.lower())
            if not dst:
                continue
            spans.append((m.start(1), m.end(1)))
            key = matched.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append((matched, dst))

    if _TERM_SINGLE:
        for m in _TOKEN_RE.finditer(text):
            s, e = m.start(), m.end()
            if any(a <= s and e <= b for a, b in spans):
                continue
            hit = _TERM_SINGLE.get(m.group(0).lower())
            if not hit:
                continue
            key = hit[0].lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(hit)

    return result


def apply_terms(text):
    """
    术语兜底替换：把 text 里命中的术语原文替换为术语表译文。

    ★ 多词术语优先：先用占位标记锁住多词结果，再跑单词替换，最后回填，
      避免 "Profesor Oak" 被拆成 "教授 Oak"。
    """
    if not text or (not _TERM_SINGLE and not _MULTI_RE):
        return text

    out = text
    marks = {}

    if _MULTI_RE:
        counter = [0]

        def _mark(m):
            matched = m.group(1)
            dst = _MULTI_MAP.get(matched)
            if dst is None:
                dst = _MULTI_MAP_LOWER.get(matched.lower())
            if not dst:
                return m.group(0)
            key = f"\x00{counter[0]}\x00"
            counter[0] += 1
            marks[key] = dst
            return key

        out = _MULTI_RE.sub(_mark, out)

    if _TERM_SINGLE and marks:
        # 只有存在被锁定的多词结果时才需要保护单词扫描
        def _repl(m):
            hit = _TERM_SINGLE.get(m.group(0).lower())
            return hit[1] if hit else m.group(0)
        out = _TOKEN_RE.sub(_repl, out)
        for k, v in marks.items():
            out = out.replace(k, v)
    elif _TERM_SINGLE:
        def _repl2(m):
            hit = _TERM_SINGLE.get(m.group(0).lower())
            return hit[1] if hit else m.group(0)
        out = _TOKEN_RE.sub(_repl2, out)
    elif marks:
        for k, v in marks.items():
            out = out.replace(k, v)

    return out


# ================================================================
# 按原文换行位置对齐译文
# ================================================================
_PUNCT_SET = set(".!?。！？")

# ★ 省略号单元：英文连续 2 个以上句点（...），或中文省略号 …（1 个即算）。
#   模型常把原文的 "..." 译成 "……"，若不统一识别，译文里就找不到对应的标点单元，
#   换行会退化成按字数硬换行（出现 「…你好\n，\PN！」 这类错位）。
_ELLIPSIS_EN_MIN = 2


def _ellipsis_len(text, i):
    """从 i 起读取一个省略号单元，返回其长度；不是省略号返回 0。"""
    n = len(text)
    ch = text[i]
    if ch == '\u2026':                      # …（中文省略号，1 个即算）
        j = i
        while j < n and text[j] == '\u2026':
            j += 1
        return j - i
    if ch == '.':                           # 英文句点需连续 2 个以上
        j = i
        while j < n and text[j] == '.':
            j += 1
        return (j - i) if (j - i) >= _ELLIPSIS_EN_MIN else 0
    return 0


def _has_break_at(text, pos, mode):
    """pos 处是否已经存在换行符（避免重复插入）。"""
    if mode == "newline":
        return (pos + 1 < len(text) and
                text[pos] == '\\' and text[pos + 1] == 'n')
    return pos < len(text) and text[pos] == ' '


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

        # 省略号（... / ……）整体作为一个标点单元
        el = _ellipsis_len(text, i)
        if el:
            j = i + el
            has_break = (j + 1 < n and
                         text[j] == '\\' and
                         text[j + 1] == 'n')
            result.append(has_break)
            i = j
            continue

        ch = text[i]

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

        # 省略号（... / ……）整体作为一个标点单元
        el = _ellipsis_len(text, i)
        if el:
            j = i + el
            result.append(text[i:j])
            if idx < len(breaks) and breaks[idx]:
                if not _has_break_at(text, j, mode):
                    result.append(insert_char)
            idx += 1
            i = j
            continue

        ch = text[i]

        # 单个标点
        result.append(ch)
        if ch in _PUNCT_SET:
            if idx < len(breaks) and breaks[idx]:
                if not _has_break_at(text, i + 1, mode):
                    result.append(insert_char)
            idx += 1
        i += 1
    return ''.join(result)


# ================================================================
# 换行重排
# ================================================================
def unwrap(text, mode="newline"):
    """
    撤销上一次重排插入的换行 / 空格，使「重排」可以反复执行（幂等）。

      · mode="newline" → 丢弃所有 \\n 控制码（断点稍后按原文重新补回）
      · mode="space"   → 丢弃控制码之外的空格 / 全角空格

    ★ 控制码内部一律不动（如 \\w[speech hgss 3] 里的空格必须保留）。
    """
    if not text:
        return text

    out = []
    i, n = 0, len(text)
    while i < n:
        m = ALL_CTRL_RE.match(text, i)
        if m:
            token = m.group(0)
            i = m.end()
            if mode == "newline" and token == '\\n':
                continue
            out.append(token)
            continue

        ch = text[i]
        i += 1
        if mode == "space" and ch in " \t\u3000":
            continue
        out.append(ch)

    return "".join(out)


def reflow(src, dst, mode="newline", min_chars=None, max_chars=None,
           min_gap=None, punct=None):
    """
    对一条已译好的译文做「换行重排」（不调用模型）：

        撤销旧换行/空格 → 按原文断点重补 → 按新配置重排

    因为起点总是「干净」的，同配置反复执行结果一致（幂等）。
    """
    if not dst:
        return dst

    base = unwrap(dst, mode=mode)
    breaks = analyze_breaks(src or "")
    if breaks:
        base = apply_breaks(base, breaks, mode=mode)
    if not config.REWRAP_ENABLE:
        return base
    return rewrap(base, min_chars=min_chars, max_chars=max_chars,
                  min_gap=min_gap, punct=punct, mode=mode)


def rewrap(text, min_chars=None, max_chars=None, punct=None,
           min_gap=None, mode="newline"):
    """
    翻译后重新分行。
    mode="newline" → 用 \\n
    mode="space"   → 用空格
    """
    if not text:
        return text

    # ★ 空格模式（非 [map*] 区块）用独立的、更短的阈值：每 8~10 个字符插一个空格
    if mode == "space":
        min_chars = (min_chars if min_chars is not None
                     else getattr(config, "WRAP_SPACE_MIN", 8))
        max_chars = (max_chars if max_chars is not None
                     else getattr(config, "WRAP_SPACE_MAX", 10))
        min_gap = (min_gap if min_gap is not None
                   else getattr(config, "WRAP_SPACE_MIN_GAP", 5))
    else:
        min_chars = min_chars if min_chars is not None else config.WRAP_CHARS_MIN
        max_chars = max_chars if max_chars is not None else config.WRAP_CHARS_MAX
        min_gap = (min_gap if min_gap is not None
                   else getattr(config, "WRAP_MIN_GAP", 10))

    insert_char = '\\n' if mode == "newline" else ' '

    soft_punct = set("，、；：,;: 　")
    soft_threshold = max(min_chars, min_gap)

    parts = []
    count = 0
    i, n = 0, len(text)

    def _break_at(pos):
        """
        在 pos 处补一个换行 / 空格；若该位置本来就有（例如 apply_breaks
        已按原文断点补过 \\n），就不再重复插入，避免出现空行。
        """
        if not _has_break_at(text, pos, mode):
            parts.append(insert_char)

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

        # ★ 省略号（... / … / ……）作为一个整体，绝不在中间断行
        el = _ellipsis_len(text, i)
        if el:
            parts.append(text[i:i + el])
            count += el
            i += el
            if count >= max_chars:
                _break_at(i)
                count = 0
            continue

        ch = text[i]
        parts.append(ch)
        count += 1
        i += 1

        if count >= max_chars:
            _break_at(i)
            count = 0
            continue

        if count >= soft_threshold and i < n:
            next_ch = text[i]
            if next_ch in soft_punct:
                _break_at(i)
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
def prepare(text, drop_newline=True):
    """
    返回 (safe_text, maps, breaks, hit_terms)。
      hit_terms: [(原文, 译文), ...]  文本中命中的术语，交由 prompt 参考
      drop_newline=False → 保留 \\n（润色流程用）
    """
    breaks = analyze_breaks(text)
    safe, maps = protect(text, drop_newline=drop_newline)
    hit_terms = find_terms(safe)
    return safe, maps, breaks, hit_terms


def finalize(text, maps, breaks=None, mode="newline"):
    """
    还原占位符 → 按原文换行位置补换行符。

    ★ 翻译（以及润色、术语重翻）之后**不再自动做「按字数重排」**：
      字数重排已独立成菜单 6「换行重排」，需要时手动执行。
      这样翻译输出只保留「原文标点处记录下来的换行」，不会被动改动原文节奏。

    mode="newline" → 补 \\n
    mode="space"   → 补空格（只在按原文断点补齐时用到）
    """
    text = restore(text, maps)
    if breaks:
        text = apply_breaks(text, breaks, mode=mode)
    return text