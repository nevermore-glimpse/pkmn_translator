# -*- coding: utf-8 -*-
"""
翻译结果检查：
  1. 疑似未翻译（译文剥离控制码后仍含英文）
  2. 特殊符号不匹配（控制码 / 标签 / 数字占位符）
  3. 特殊情况行（未配对文本）
  4. 译文残留控制码（名单外的 \\字母）
  5. 译文残留占位符（@0@ / ⟦0⟧）
  6. 额外命中（翻译失败 / 占位符兜底 / 术语冲突）

输出：与输出文件同目录的 <名>_report.txt
"""
import os
import re

from logger import get_logger

from processor import (
    CTRL_RE, TAG_RE, BRACE_RE,
    ANGLE_CMD_RE, HTML_TAG_RE, ALL_CTRL_RE,
    _HTML_ENTITY_PAT,
)

log = get_logger("checker")


# ================================================================
# 常量
# ================================================================
_CTRL_IGNORE = {r'\n'}

# 英文单词（含西语重音字符）
_ENGLISH_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{3,}")

# 白名单：这些英文不算"未翻译"
# ★ 比对的是 _ENGLISH_RE 抽出的纯字母词，所以 &quot 要写 "quot" 才命中；
#   两个都放进去，兼容后续若改用整串匹配的情况。
WHITELIST = {
    "Pokémon", "Pokemon", "Pokédex", "Pokedex",
    "Twitter", "Discord", "YouTube", "Facebook",
    "Android", "Windows", "Linux", "Nintendo", "Switch",
    "AMD", "NVIDIA", "Intel", "Haya",
    "quot", "&quot",          # HTML 实体 &quot; / &quot
    "amp", "&amp", "nbsp", "&nbsp",
}

# 占位符匹配
PLACEHOLDER_RE = re.compile(r'@\s*\d+\s*@|⟦\s*\d+\s*⟧')

# 异常 @ 符号：连续 2 个以上
_ABNORMAL_AT_RE = re.compile(r'@{2,}')
# ================================================================
# 工具：剥离所有控制码
# ================================================================
def _strip_all_ctrl(text):
    """剥离所有已识别的控制码/标签/占位符，返回纯文本。"""
    if not text:
        return ""
    t = text
    t = ANGLE_CMD_RE.sub('', t)
    t = HTML_TAG_RE.sub('', t)
    t = re.sub(_HTML_ENTITY_PAT, '', t)     # ★ 加 HTML 实体
    t = CTRL_RE.sub('', t)
    t = TAG_RE.sub('', t)
    t = BRACE_RE.sub('', t)
    return t


# ================================================================
# 符号提取
# ================================================================
def _extract_symbols(text):
    """返回 (控制码列表, 标签列表, 花括号占位符列表)。"""
    ctrls = [c for c in CTRL_RE.findall(text) if c not in _CTRL_IGNORE]
    ctrls += ANGLE_CMD_RE.findall(text)
    ctrls += HTML_TAG_RE.findall(text)
    ctrls += re.findall(_HTML_ENTITY_PAT, text)   # ★ HTML 实体
    return ctrls, TAG_RE.findall(text), BRACE_RE.findall(text)


def _find_unprotected_ctrl(text):
    """
    找出 text 中真正未被识别的 \\字母 形式。
    逐位置尝试 ALL_CTRL_RE.match，匹配不上才算残留。
    """
    if not text:
        return []
    results = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == '\\':
            m = ALL_CTRL_RE.match(text, i)
            if m:
                i = m.end()
                continue
            # 未识别：收集 \ 后面的连续字母
            j = i + 1
            while j < n and text[j].isascii() and text[j].isalpha():
                j += 1
            if j > i + 1:
                results.append(text[i:j])
                i = j
                continue
        i += 1
    return results


def _find_leftover_placeholder(text):
    """找出残留的 @N@ / ⟦N⟧ 占位符。"""
    if not text:
        return []
    return [m.group(0) for m in PLACEHOLDER_RE.finditer(text)]

def _find_abnormal_at(text):
    """
    检测译文里是否有异常的 @@ / @@@ 符号。
    先剔除合法占位符 @数字@，再看剩余是否还有连续 @。
    """
    if not text:
        return []
    # 剔除合法占位符
    t = PLACEHOLDER_RE.sub('', text)
    # 剩余的 @ 里面，连续 2 个以上视为异常
    return [m.group(0) for m in _ABNORMAL_AT_RE.finditer(t)]
# ================================================================
# 主检查
# ================================================================
def check(src_lines, out_lines, entries, special, report_path,
          extra_hits=None):
    """返回 hits 列表并写入报告。"""
    hits = []

    # 从 src 反查行号
    src_to_line = {}
    for ln, src in entries:
        key = src.strip()
        if key and key not in src_to_line:
            src_to_line[key] = ln

    # 已单独报告过的 src
    failed_srcs = set()
    if extra_hits:
        for item in extra_hits:
            # ★ 术语冲突只是「术语译法不一致」，句子本身的翻译没问题，
            #   不该因为它就跳过其它检查（未翻译 / 符号不匹配等）
            if (item.get('kind') or '') == '术语冲突':
                continue
            s = (item.get('src') or '').strip()
            if s:
                failed_srcs.add(s)

    # ---------- 遍历正常条目 ----------
    for line_no, src in entries:
        if line_no >= len(out_lines):
            continue
        dst = out_lines[line_no].strip()
        src_strip = src.strip()

        if src_strip in failed_srcs:
            continue

        # ★① 疑似未翻译：剥离控制码后仍含英文
        dst_clean = _strip_all_ctrl(dst)
        english_words = [
            w for w in _ENGLISH_RE.findall(dst_clean)
            if w not in WHITELIST
        ]
        if english_words:
            hits.append({
                'line_no': line_no, 'kind': '疑似未翻译',
                'src': src, 'dst': dst,
                'detail': f'译文残留英文：{", ".join(english_words[:8])}',
            })

        # ② 特殊符号不匹配
        s_ctrl, s_tag, s_brace = _extract_symbols(src)
        d_ctrl, d_tag, d_brace = _extract_symbols(dst)

        problems = []
        if len(s_ctrl) != len(d_ctrl):
            problems.append(
                f'控制码 原{len(s_ctrl)}/译{len(d_ctrl)}  '
                f'原={s_ctrl}  译={d_ctrl}'
            )
        if len(s_tag) != len(d_tag):
            problems.append(
                f'标签 原{len(s_tag)}/译{len(d_tag)}  '
                f'原={s_tag}  译={d_tag}'
            )
        if len(s_brace) != len(d_brace):
            problems.append(
                f'数字占位符 原{len(s_brace)}/译{len(d_brace)}'
            )

        if problems:
            hits.append({
                'line_no': line_no, 'kind': '符号不匹配',
                'src': src, 'dst': dst,
                'detail': ' | '.join(problems),
            })

        # ③ 译文残留控制码
        dst_unprotected = _find_unprotected_ctrl(dst)
        if dst_unprotected:
            hits.append({
                'line_no': line_no, 'kind': '译文残留控制码',
                'src': src, 'dst': dst,
                'detail': f'译文中存在未被保护的控制码：'
                          f'{", ".join(dst_unprotected[:5])}',
            })

        # ④ 译文残留占位符
        dst_ph = _find_leftover_placeholder(dst)
        if dst_ph:
            hits.append({
                'line_no': line_no, 'kind': '译文残留占位符',
                'src': src, 'dst': dst,
                'detail': f'译文中存在未还原的占位符：'
                          f'{", ".join(dst_ph[:5])}',
            })
        # ★⑤ 疑似异常句：连续 @ 符号
        abnormal_at = _find_abnormal_at(dst)
        if abnormal_at:
            hits.append({
                'line_no': line_no, 'kind': '疑似异常句',
                'src': src, 'dst': dst,
                'detail': f'译文含异常符号：{", ".join(abnormal_at[:5])}',
            })

    # ---------- 特殊行 ----------
    for sc in special:
        ln = sc['line_no']
        if ln >= len(out_lines):
            continue
        dst = out_lines[ln].strip()
        if dst == sc['text'].strip():
            hits.append({
                'line_no': ln, 'kind': '特殊行',
                'src': sc['text'], 'dst': dst,
                'detail': sc['reason'],
            })

    # ---------- 额外 hits ----------
    if extra_hits:
        for item in extra_hits:
            src = (item.get('src') or '').strip()
            kind = item.get('kind') or '翻译失败'
            detail = (item.get('detail') or item.get('reason')
                      or '翻译过程中问题')
            dst = item.get('dst', '') or ''
            line_no = item.get('line_no', src_to_line.get(src, -1))
            hit = {
                'line_no': line_no, 'kind': kind,
                'src': src, 'dst': dst,
                'detail': detail,
            }
            # ★ 透传调用方附加的结构化字段
            #   （术语冲突的 term_src / term_old / term_new 等）
            for k, v in item.items():
                if k not in hit:
                    hit[k] = v
            hits.append(hit)

    # ---------- 写报告 ----------
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# 翻译检查报告\n")
        f.write(f"# 共 {len(hits)} 处问题\n")
        f.write("=" * 70 + "\n\n")
        for h in hits:
            f.write(f"行 {h['line_no']}   [{h['kind']}]\n")
            f.write(f"  说明：{h['detail']}\n")
            f.write(f"  原文：{h['src']}\n")
            f.write(f"  译文：{h['dst']}\n\n")

    log.info("检查完成：%d 处问题 → %s", len(hits), report_path)
    return hits