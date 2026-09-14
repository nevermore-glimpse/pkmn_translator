# -*- coding: utf-8 -*-
"""
翻译结果检查：
  1. 未翻译（译文 = 原文）
  2. 疑似未翻译（译文出现原文没有的英文单词）
  3. 特殊符号不匹配（控制码 / 标签 / 数字占位符）
  4. 特殊情况行（未配对文本）
输出：reports/check_report.txt，定位到行号。

说明：
  · 从 processor 借正则，保证两边一致
  · \\n（脚本换行）不算特殊符号；\\N（分页符）仍参与对比
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


# ================================================================
# 符号提取
# ================================================================
def _extract_symbols(text):
    """返回 (控制码列表, 标签列表, 花括号占位符列表)。忽略 \\n。"""
    ctrls = [c for c in CTRL_RE.findall(text) if c not in _CTRL_IGNORE]
    return ctrls, TAG_RE.findall(text), BRACE_RE.findall(text)


# ================================================================
# 主检查
# ================================================================
def check(src_lines, out_lines, entries, special, report_path):
    """返回 hits 列表并写入报告。"""
    hits = []

    for line_no, src in entries:
        if line_no >= len(out_lines):
            continue
        dst = out_lines[line_no].strip()
        src_strip = src.strip()

        # ① 未翻译：译文完全等于原文
        if dst == src_strip:
            hits.append({
                'line_no': line_no, 'kind': '未翻译',
                'src': src, 'dst': dst,
                'detail': '译文与原文完全相同',
            })
            continue

        # ② 疑似未翻译：出现了原文里没有的英文单词
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

    # ④ 特殊行（译文 == 原文时才报，说明用户还没处理）
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

    # ---- 写报告 ----
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