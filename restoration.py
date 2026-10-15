# -*- coding: utf-8 -*-
"""
译后「安全恢复层」（借鉴 LinguaGacha translation-output-restoration）。

对模型输出先做几件**能证明安全**的修复，修不了的照旧走重试 / 保留原文：

  1. restore_escape_run_lengths —— 反斜杠连写长度按原文恢复
     （模型爱把 \\n 写成 \\\\n）；
  2. restore_circled_numbers    —— ①~⑳ 圆圈数字按原文数值对应恢复；
  3. stabilize_punctuation      —— 省略号形态跟随原文 + 成对标点
     只开不闭 / 只闭不开时按类别补齐。

★ 所有函数都只做「保守修复」：前提不满足就原样返回，
   绝不猜位置、绝不改自然语言内容。
"""
import re

import processor as PR


# 占位符 token：@0@ / ⟦0⟧（与 processor 的写法保持一致）
_TOKEN_RE = re.compile(r'@\s*(\d+)\s*@|⟦\s*(\d+)\s*⟧')
_ESCAPE_RUN_RE = re.compile(r'\\{2,}')

# ① ~ ⑳（1~20）
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_CIRCLED_SET = set(_CIRCLED)

# 成对标点类别（开, 闭；开==闭 表示无方向，如直引号）
_PAIR_CLASSES = (
    ("「", "」"), ("『", "』"),
    ('"', '"'), ("'", "'"),
    ("(", ")"), ("（", "）"),
    ("[", "]"), ("【", "】"),
    ("{", "}"), ("《", "》"),
)

# 独立数字（不属于更长数字、不在占位符里）
_STANDALONE_DIGIT_RE = re.compile(r'(?<!\d)(\d)(?!\d)')


def restore_escape_run_lengths(text, src):
    """
    反斜杠连写长度按原文恢复。

    · 原文根本没有 2 连写时，把输出里的 \\\\ 折叠成 \\（模型常见错误）；
    · 原文有连写时，按「同一个后继字符」对应恢复长度；
    · 对不上就原样保留。
    """
    if not text or "\\" not in text:
        return text, None
    runs = list(_ESCAPE_RUN_RE.finditer(text))
    if not runs:
        return text, None

    src_runs = {}
    for m in re.finditer(r'\\+', src or ""):
        nxt = (src or "")[m.end():m.end() + 1]
        src_runs.setdefault(nxt, m.end() - m.start())

    out = text
    changed = 0
    for m in reversed(runs):
        run = m.group(0)
        nxt = out[m.end():m.end() + 1]
        want = src_runs.get(nxt)
        if want is None:
            # 原文没有「这个后继字符」的连写：模型自己写出来的，折叠成 1 个
            want = 1
        if want != len(run):
            out = out[:m.start()] + "\\" * want + out[m.end():]
            changed += 1
    return out, (f"反斜杠连写恢复 {changed} 处" if changed else None)


def restore_circled_numbers(text, src):
    """
    ①~⑳ 按原文数值对应恢复：原文用了圆圈数字、译文一个都没有、
    且译文独立数字个数正好相等时，按出现顺序逐一换回。

    条件很严（个数必须一致），所以只修「模型把 ① 老实翻成 1」。
    """
    if not text or not src:
        return text, None
    src_clean = _strip_ctrl(src)
    src_circled = [c for c in src_clean if c in _CIRCLED_SET]
    if not src_circled:
        return text, None
    if any(c in _CIRCLED_SET for c in text):
        return text, None        # 译文已经在用圆圈数字，不动

    # 占位符 token 先遮掉，避免 token 里的数字被当成正文数字
    masked = _TOKEN_RE.sub(lambda m: "\x00" * (m.end() - m.start()), text)
    digits = list(_STANDALONE_DIGIT_RE.finditer(masked))
    if len(digits) != len(src_circled):
        return text, None

    out = text
    for m, circ in zip(reversed(digits), reversed(src_circled)):
        out = out[:m.start()] + circ + out[m.end():]
    return out, f"圆圈数字恢复 {len(digits)} 处"


def _strip_ctrl(text):
    """剥掉控制码 / 标签 / 占位符，只留自然语言与标点。"""
    t = text
    t = PR.ANGLE_CMD_RE.sub('', t)
    t = PR.HTML_TAG_RE.sub('', t)
    t = re.sub(PR._HTML_ENTITY_PAT, '', t)
    t = PR.CTRL_RE.sub('', t)
    t = PR.TAG_RE.sub('', t)
    t = PR.BRACE_RE.sub('', t)
    t = _TOKEN_RE.sub('', t)
    return t


def stabilize_punctuation(text, src):
    """
    标点结构稳定化（保守版）：

    ① 省略号形态跟随原文：原文用 "..." 译文就不能用 "…"（反之亦然），
       仅在译文完全没用原文形态时转换；
    ② 成对标点只开不闭 / 只闭不开：原文该类配平、译文不配平时，
       按类别把缺的闭合/开启符号补在末尾/开头（补哪个字形看译文里
       已出现的同类符号，译文一类都没有就放弃——位置无从判断）。
    """
    if not text or not src:
        return text, None
    fixes = []
    out = text

    # ---------- ① 省略号形态 ----------
    src_clean = _strip_ctrl(src)
    dst_clean = _strip_ctrl(out)
    src_ascii = "..." in src_clean
    src_uni = "\u2026" in src_clean
    if src_ascii and not src_uni and "..." not in dst_clean \
            and "\u2026" in dst_clean:
        out = out.replace("\u2026", "...")
        dst_clean = dst_clean.replace("\u2026", "...")
        fixes.append("省略号形态跟随原文（… → ...）")
    elif src_uni and not src_ascii and "\u2026" not in dst_clean \
            and "..." in dst_clean:
        out = out.replace("...", "\u2026")
        dst_clean = dst_clean.replace("...", "\u2026")
        fixes.append("省略号形态跟随原文（... → …）")

    # ---------- ② 成对标点补齐 ----------
    for opener, closer in _PAIR_CLASSES:
        s_o, s_c = src_clean.count(opener), src_clean.count(closer)
        d_o, d_c = dst_clean.count(opener), dst_clean.count(closer)
        if opener == closer:
            # 无方向（直引号）：原文成对、译文落单 → 末尾补一个
            if s_o >= 2 and s_o % 2 == 0 and d_o % 2 == 1 and d_o > 0:
                out = out + opener
                dst_clean = dst_clean + opener
                fixes.append(f"补缺失的闭合引号 {opener}")
            continue
        if s_o == s_c and s_o > 0:
            if d_o > d_c and d_c > 0:
                out = out + closer * (d_o - d_c)
                dst_clean = dst_clean + closer * (d_o - d_c)
                fixes.append(f"补缺失的闭合符号 {closer}×{d_o - d_c}")
            elif d_c > d_o and d_o > 0:
                out = opener * (d_c - d_o) + out
                dst_clean = dst_clean + opener * (d_c - d_o)
                fixes.append(f"补缺失的开启符号 {opener}×{d_c - d_o}")

    return out, ("；".join(fixes) if fixes else None)


def safe_restore(raw, src_body):
    """
    对模型原始输出依次执行上述保守修复。

    返回 (新文本, [修复说明, ...])；无修复返回 (raw, [])。
    """
    text = raw
    notes = []

    text, note = restore_escape_run_lengths(text, src_body)
    if note:
        notes.append(note)

    text, note = restore_circled_numbers(text, src_body)
    if note:
        notes.append(note)

    text, note = stabilize_punctuation(text, src_body)
    if note:
        notes.append(note)

    return text, notes
