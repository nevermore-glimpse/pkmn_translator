# -*- coding: utf-8 -*-
"""
从 Excel 多语言表提取术语字典。

两种用法：
    · 命令行：python build_terms.py -i 术语表.xlsx -o term_dict.py
    · 被调用：from build_terms import build_terms
              build_terms("术语表.xlsx", "term_dict.py", "英文", "简体中文")

★ 默认是「追加」模式：输出文件已存在且能读出 TERM_DICT 时，
  只把新术语接在末尾，已有键保留原译文（不覆盖用户校对过的内容）。
  要整份重写请传 mode="overwrite"（命令行加 --overwrite）。
"""
import argparse
import ast
import json
import os
import sys

try:
    import openpyxl
except ImportError:
    openpyxl = None


# ============================================================
# 语言别名表
# ============================================================
LANG_ALIASES = {
    "简体中文": ["简体中文", "简中", "中文（简体）", "中文(简体)", "zh-CN", "zh_Hans"],
    "繁体中文": ["繁体中文", "繁中", "中文（繁体）", "中文(繁体)", "zh-TW", "zh_Hant"],
    "英文":   ["英文", "英语", "English", "EN", "Eng"],
    "日文":   ["日文", "日本语", "日语", "Japanese", "JP", "JPN"],
    "西班牙文": ["西班牙文", "西班牙语", "西班牙", "Spanish", "ES", "Español"],
    "德文":   ["德文", "德语", "German", "DE", "Deutsch"],
    "法文":   ["法文", "法语", "French", "FR", "Français"],
    "意大利文": ["意大利文", "意大利语", "Italian", "IT", "Italiano"],
    "韩文":   ["韩文", "韩语", "Korean", "KO", "한국어"],
}


def _log_info(msg, *args):
    try:
        from logger import get_logger
        get_logger("build_terms").info(msg, *args)
    except Exception:
        print(msg % args if args else msg)


def _log_warning(msg, *args):
    try:
        from logger import get_logger
        get_logger("build_terms").warning(msg, *args)
    except Exception:
        print(msg % args if args else msg)


def norm_header(v):
    return "" if v is None else str(v).strip()


def match_lang(header, lang_key):
    h = norm_header(header)
    if not h:
        return False
    aliases = LANG_ALIASES.get(lang_key, [lang_key])
    for a in aliases:
        if h == a:
            return True
    for a in aliases:
        if len(a) >= 3 and a in h:
            return True
    return False


def find_header_row(rows, source_lang, target_lang, max_scan=15):
    for ri, row in enumerate(rows[:max_scan]):
        src_col = tgt_col = None
        for ci, cell in enumerate(row):
            if src_col is None and match_lang(cell, source_lang):
                src_col = ci
            if tgt_col is None and match_lang(cell, target_lang):
                tgt_col = ci
        if src_col is not None and tgt_col is not None:
            return ri, src_col, tgt_col
    return None, None, None


def extract_from_sheet(ws, source_lang, target_lang):
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], None

    ri, sc, tc = find_header_row(rows, source_lang, target_lang)
    if ri is None:
        return [], f"未找到同时含「{source_lang}」和「{target_lang}」的表头行"

    pairs = []
    seen = set()
    sk_empty = sk_same = sk_short = 0

    for row in rows[ri + 1:]:
        if sc >= len(row) or tc >= len(row):
            continue
        s_raw, t_raw = row[sc], row[tc]
        if s_raw is None or t_raw is None:
            sk_empty += 1
            continue
        s, t = str(s_raw).strip(), str(t_raw).strip()
        if not s or not t:
            sk_empty += 1
            continue
        if s == t:
            sk_same += 1
            continue
        if len(s) < 2 or s.isdigit():
            sk_short += 1
            continue
        if s.lower() in seen:
            continue
        seen.add(s.lower())
        pairs.append((s, t))

    stats = {
        "header_row":    ri + 1,
        "src_col":       sc + 1,
        "tgt_col":       tc + 1,
        "total":         len(pairs),
        "skipped_empty": sk_empty,
        "skipped_same":  sk_same,
        "skipped_short": sk_short,
    }
    return pairs, stats


def write_term_dict(pairs, out_path, source_lang, target_lang, note=None):
    """把 (源, 译) 列表写成 term_dict.py。note 会补一行到文件头的说明里。"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write('"""\n')
        f.write("术语表：由 build_terms.py 自动生成\n")
        f.write(f"源语言：{source_lang}    目标语言：{target_lang}\n")
        f.write(f"共 {len(pairs)} 条{note or ''}\n")
        f.write('"""\n\n')
        f.write("TERM_DICT = {\n")
        for s, t in pairs:
            f.write(f"    {json.dumps(s, ensure_ascii=False)}: "
                    f"{json.dumps(t, ensure_ascii=False)},\n")
        f.write("}\n")


# ============================================================
# 追加模式：已有术语字典时，把新术语接在末尾
# ============================================================
def read_existing_terms(path):
    """
    读出已有术语字典，保持文件里的原始顺序。

    用 ast 解析而不是 import（import 会执行文件、留下 __pycache__，
    还可能被同名模块缓存干扰）。解析不了就返回空字典 —— 上层会当成
    「没有已有字典」，最坏情况是覆盖写入，不会把文件写坏。
    """
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            src = f.read()
    except Exception as e:
        _log_warning("读取已有术语字典失败（%s）：%s", path, e)
        return {}

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        _log_warning("已有术语字典语法有误，本次按覆盖处理：%s", e)
        return {}

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "TERM_DICT"
                   for t in node.targets):
            continue
        try:
            val = ast.literal_eval(node.value)
        except Exception as e:
            _log_warning("TERM_DICT 不是字面量字典，本次按覆盖处理：%s", e)
            return {}
        if isinstance(val, dict):
            return {str(k): str(v) for k, v in val.items()}
    return {}


def merge_terms(existing, new_pairs):
    """
    把新术语追加到已有字典末尾。

    ★ 已有键一律保留原译文，只追加不存在的键 ——
      用户可能已经在菜单 4 里逐条校对过、或在术语更新流程里改过译法，
      Excel 里的旧数据不该把它冲掉。
    ★ 大小写不同视为同一个词（跟 Excel 内部的去重口径一致）。

    返回 (merged_dict, stats)；stats 含 added / skipped / conflicts。
    conflicts 是「同一个原文术语、新旧译法不一致」的三元组列表，
    只是提示，不会改已有值。
    """
    merged = {str(k): str(v) for k, v in (existing or {}).items()}
    lower = {k.lower(): k for k in merged}
    added = skipped = 0
    conflicts = []

    for s, t in new_pairs:
        s, t = str(s), str(t)
        low = s.lower()
        if low in lower:
            skipped += 1
            keep = lower[low]
            old = merged[keep]
            # ★ 全半角 / 空白差异不算冲突（招式学习器１３ == 招式学习器13）
            if old != t and _norm_value(old) != _norm_value(t):
                conflicts.append((keep, old, t))
            continue
        merged[s] = t
        lower[low] = s
        added += 1

    return merged, {"added": added, "skipped": skipped,
                    "conflicts": conflicts}


def _norm_value(s):
    """译文案值归一化：NFKC（全角→半角）+ 去空白，用于冲突比较。"""
    import re as _re
    import unicodedata
    return _re.sub(r'\s+', '', unicodedata.normalize('NFKC', s or ''))


# ============================================================
# 供 commands.py 调用的核心函数
# ============================================================
def list_sheets(excel_path):
    """返回 [(sheet_name, rows, cols), ...]"""
    if openpyxl is None:
        raise RuntimeError("缺少 openpyxl，请执行：pip install openpyxl")
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    out = [(name, wb[name].max_row, wb[name].max_column)
           for name in wb.sheetnames]
    wb.close()
    return out


def build_terms(excel_path,
                out_path="term_dict.py",
                source_lang="英文",
                target_lang="简体中文",
                sheets=None,
                dedup=True,
                verbose=True,
                mode="append"):
    """
    从 Excel 提取术语字典并写入 out_path。

    mode="append"    （默认）已有 term_dict.py 时，把新术语接在末尾，
                      已有键保留原译文不覆盖；
    mode="overwrite" 整份重写，只留本次 Excel 的内容。

    返回 dict 结果，含 total / added / skipped_existing / conflicts 等。
    """
    mode = "overwrite" if str(mode).lower().startswith("over") else "append"
    base = {"ok": False, "total": 0, "out_path": out_path, "mode": mode,
            "existing": 0, "added": 0, "skipped_existing": 0,
            "conflicts": [], "sheet_stats": [], "errors": []}

    if openpyxl is None:
        return {**base, "errors": ["缺少 openpyxl"]}

    if not os.path.exists(excel_path):
        return {**base, "errors": [f"文件不存在：{excel_path}"]}

    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    targets = sheets or wb.sheetnames

    all_pairs = []
    seen_global = set()
    sheet_stats = []
    errors = []

    _log_info("Excel 提取开始：%s  源=%s  译=%s  模式=%s",
              excel_path, source_lang, target_lang, mode)

    for name in targets:
        if name not in wb.sheetnames:
            errors.append(f"工作表不存在：{name}")
            continue

        ws = wb[name]
        pairs, stats = extract_from_sheet(ws, source_lang, target_lang)

        if stats is None:
            _log_warning("[%s] %s", name, pairs)
            errors.append(f"[{name}] {pairs}")
            continue

        dup = 0
        if dedup:
            new_pairs = []
            for s, t in pairs:
                if s.lower() in seen_global:
                    continue
                seen_global.add(s.lower())
                new_pairs.append((s, t))
            dup = len(pairs) - len(new_pairs)
            pairs = new_pairs

        all_pairs.extend(pairs)
        stats["sheet"] = name
        stats["dup_across_sheets"] = dup
        sheet_stats.append(stats)

        _log_info("[%s] 表头第 %d 行 源列 %d 译列 %d → %d 条%s",
                  name, stats["header_row"], stats["src_col"],
                  stats["tgt_col"], len(pairs),
                  f"  (跨表去重 {dup})" if dup else "")

    wb.close()

    if not all_pairs:
        errors.append("未提取到任何术语对，请检查源/目标语言列名")
        return {**base, "sheet_stats": sheet_stats, "errors": errors}

    # ---------- 追加 / 覆盖 ----------
    existing = read_existing_terms(out_path) if mode == "append" else {}
    if existing:
        merged, mstat = merge_terms(existing, all_pairs)
        note = f"（本次追加 {mstat['added']} 条，已存在跳过 {mstat['skipped']} 条）"
        _log_info("追加模式：原有 %d 条 → 追加 %d 条、跳过已存在 %d 条 → 合计 %d 条",
                  len(existing), mstat["added"], mstat["skipped"], len(merged))
        if mstat["conflicts"]:
            _log_warning("有 %d 条术语的译法与已有字典不一致，已保留已有译法：",
                         len(mstat["conflicts"]))
            for src, old, new in mstat["conflicts"][:20]:
                _log_warning("    %s：保留「%s」，Excel 里是「%s」", src, old, new)
    else:
        merged = {}
        for s, t in all_pairs:
            merged.setdefault(str(s), str(t))
        mstat = {"added": len(merged), "skipped": 0, "conflicts": []}
        note = None
        if mode == "append" and os.path.exists(out_path):
            # 文件在但解析不出 TERM_DICT（被改坏 / 不是术语字典）→ 明确提示
            _log_warning("已有文件 %s 里读不到 TERM_DICT，本次整份重写。", out_path)

    write_term_dict(list(merged.items()), out_path, source_lang, target_lang,
                    note=note)
    _log_info("Excel 提取完成：合计 %d 条（本次新增 %d）→ %s",
              len(merged), mstat["added"], out_path)

    return {
        "ok": True, "out_path": out_path, "mode": mode,
        "total": len(merged), "added": mstat["added"],
        "existing": len(existing), "skipped_existing": mstat["skipped"],
        "conflicts": mstat["conflicts"],
        "sheet_stats": sheet_stats, "errors": errors,
    }


# ============================================================
# CLI 入口
# ============================================================
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="从 Excel 多语言表提取术语字典",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("-i", "--input", required=True, help="Excel 文件路径")
    ap.add_argument("-o", "--output", default="term_dict.py", help="输出路径")
    ap.add_argument("--source", default="英文", help="源语言列名")
    ap.add_argument("--target", default="简体中文", help="目标语言列名")
    ap.add_argument("--sheet", action="append", help="只处理指定工作表")
    ap.add_argument("--list-sheets", action="store_true", help="列出所有工作表")
    ap.add_argument("--no-dedup", action="store_true", help="跨表不去重")
    ap.add_argument("--overwrite", action="store_true",
                    help="整份重写（默认是：已有术语字典时在末尾追加新术语）")
    args = ap.parse_args(argv)

    if args.list_sheets:
        for name, r, c in list_sheets(args.input):
            print(f"  {name}  ({r} 行 × {c} 列)")
        return 0

    result = build_terms(
        args.input, args.output, args.source, args.target,
        sheets=args.sheet, dedup=not args.no_dedup,
        mode="overwrite" if args.overwrite else "append",
    )
    for e in result["errors"]:
        print(f"[err] {e}")
    if result["ok"]:
        if result["mode"] == "append" and result["existing"]:
            print(f"\n原有 {result['existing']} 条 → 追加 {result['added']} 条、"
                  f"跳过已存在 {result['skipped_existing']} 条")
            for src, old, new in result["conflicts"][:10]:
                print(f"  [冲突] {src}：保留「{old}」，Excel 里是「{new}」")
            if len(result["conflicts"]) > 10:
                print(f"  …另有 {len(result['conflicts']) - 10} 条冲突，见日志")
        print(f"\n✔ 合计 {result['total']} 条 → {result['out_path']}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())