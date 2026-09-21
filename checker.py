# -*- coding: utf-8 -*-
"""
翻译结果检查：
  1. 未翻译（译文 = 原文）
  2. 疑似未翻译（译文出现原文没有的英文单词）
  3. 特殊符号不匹配（控制码 / 标签 / 数字占位符）
  4. 特殊情况行（未配对文本）
  5. 译文残留控制码（CTRL_RE 名单外的 \\字母）
  6. ★ 译文残留占位符（@0@ 或 ⟦0⟧ 形式）
  7. 翻译失败（由 cmd_translate 传入）

输出：与输出文件同目录的 <名>_report.txt
"""
import os
import re

from logger import get_logger

# ★ 复用 processor 的正则，避免 \\bHey 之类被误吃
from processor import CTRL_RE, TAG_RE, BRACE_RE

log = get_logger("checker")


# ================================================================
# 常量
# ================================================================
# 检查时忽略的控制码（不算"特殊符号不匹配"）
#   \n 是脚本换行，由 processor.rewrap 重排，允许原文/译文数量不同
#   \N（大写，分页符）不在此列，仍参与对比
_CTRL_IGNORE = {r'\n'}

# 疑似未翻译：抓 4 个及以上字母的英文单词（含西语重音字符）
WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{4,}")

# 白名单：这些英文不视为"未翻译"
WHITELIST = {
    "Pokémon", "Pokemon", "Pokédex", "Pokedex",
    "Twitter", "Discord", "YouTube", "Facebook",
    "Android", "Windows", "Linux", "Nintendo", "Switch",
    "AMD", "NVIDIA", "Intel",
}

# 宽松匹配：抓 \\字母 形式（用于检测译文残留）
LEFTOVER_CTRL_RE = re.compile(r'\\[A-Za-z]+(?:\[[^\]]*\])?')

# ★ 占位符匹配：@0@ / @1@ / ⟦0⟧ / ⟦1⟧ / @ 0 @ 等变体
PLACEHOLDER_RE = re.compile(r'@\s*\d+\s*@|⟦\s*\d+\s*⟧')


# ================================================================
# 符号提取
# ================================================================
def _extract_symbols(text):
    """返回 (控制码列表, 标签列表, 花括号占位符列表)。忽略 \\n。"""
    ctrls = [c for c in CTRL_RE.findall(text) if c not in _CTRL_IGNORE]
    return ctrls, TAG_RE.findall(text), BRACE_RE.findall(text)


def _find_unprotected_ctrl(text):
    """
    找出 text 中 CTRL_RE **匹配不到**的 \\字母 形式。
    """
    if not text:
        return []

    recognized = [(m.start(), m.end()) for m in CTRL_RE.finditer(text)]

    results = []
    for m in LEFTOVER_CTRL_RE.finditer(text):
        s, e = m.start(), m.end()
        covered = any(rs <= s and e <= re_ for rs, re_ in recognized)
        if not covered:
            results.append(m.group(0))
    return results


def _find_leftover_placeholder(text):
    """
    找出译文中残留的 @N@ / ⟦N⟧ 占位符。
    返回匹配到的 token 列表（含原始形式，如 '@0@'、'⟦2⟧'）。
    """
    if not text:
        return []
    return [m.group(0) for m in PLACEHOLDER_RE.finditer(text)]


# ================================================================
# 主检查
# ================================================================
def check(src_lines, out_lines, entries, special, report_path,
          extra_hits=None):
    """
    返回 hits 列表并写入报告。

    translate_failed: list of dict
        [{'src': 原文, 'reason': '失败原因', 'dst': 可选}, ...]
    """
    hits = []

    # 用于从 src 反查行号
    src_to_line = {}
    for ln, src in entries:
        key = src.strip()
        if key and key not in src_to_line:
            src_to_line[key] = ln

    # 已单独报告过的 src，避免常规检查重复
    failed_srcs = set()
    if extra_hits:
        for item in extra_hits:
            s = (item.get('src') or '').strip()
            if s:
                failed_srcs.add(s)

    # ---------- 遍历所有正常条目 ----------
    for line_no, src in entries:
        if line_no >= len(out_lines):
            continue
        dst = out_lines[line_no].strip()
        src_strip = src.strip()

        if src_strip in failed_srcs:
            continue

        # ① 未翻译
        if dst == src_strip:
            hits.append({
                'line_no': line_no, 'kind': '未翻译',
                'src': src, 'dst': dst,
                'detail': '译文与原文完全相同',
            })
            continue

        # ② 疑似未翻译
        src_words = set(WORD_RE.findall(src))
        dst_words = set(WORD_RE.findall(dst))
        new_words = [w for w in (dst_words - src_words) if w not in WHITELIST]
        if new_words:
            hits.append({
                'line_no': line_no, 'kind': '疑似未翻译',
                'src': src, 'dst': dst,
                'detail': f'残留英文：{", ".join(new_words[:8])}',
            })

        # ③ 特殊符号不匹配
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

        # ④ 译文残留控制码
        dst_unprotected = _find_unprotected_ctrl(dst)
        if dst_unprotected:
            hits.append({
                'line_no': line_no, 'kind': '译文残留控制码',
                'src': src, 'dst': dst,
                'detail': f'译文中存在未被保护的控制码：'
                          f'{", ".join(dst_unprotected[:5])}',
            })

        # ★⑤ 译文残留占位符
        dst_ph = _find_leftover_placeholder(dst)
        if dst_ph:
            hits.append({
                'line_no': line_no, 'kind': '译文残留占位符',
                'src': src, 'dst': dst,
                'detail': f'译文中存在未还原的占位符：'
                          f'{", ".join(dst_ph[:5])}',
            })

    # ---------- ⑥ 特殊行 ----------
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

    # ---------- ⑦ 翻译失败 ----------
    if extra_hits:
        for item in extra_hits:
            src = (item.get('src') or '').strip()
            kind = item.get('kind') or '翻译失败'
            detail = item.get('detail') or item.get('reason') or '翻译过程中问题'
            dst = item.get('dst', '') or ''
            line_no = item.get('line_no', src_to_line.get(src, -1))
            hits.append({
                'line_no': line_no, 'kind': kind,
                'src': src, 'dst': dst,
                'detail': detail,
            })

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