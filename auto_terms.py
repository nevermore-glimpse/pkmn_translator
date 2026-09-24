# -*- coding: utf-8 -*-
"""
术语合并：把翻译过程中内联提取的术语写入 term_dict.py 顶部的 AUTO 块。

术语来源：translator.translate_batch 通过 terms_out 参数返回 {idx: {src: dst}}。
合并入口：merge_from_translation(terms_map, processor_module)
"""
import json
import os
import re

import config
from logger import get_logger

log = get_logger("auto_terms")


# ================================================================
# term_dict.py 写入标记
# ================================================================
AUTO_START = "    # @@AUTO_TERMS_START@@"
AUTO_END   = "    # @@AUTO_TERMS_END@@"


# ================================================================
# 校验与归一化
# ================================================================
def _normalize_key(s):
    """
    归一化原文 key，用于存在性比较。
    规则：去首尾空白 + 全部转小写。
    Owen / owen / "  Owen " 会被视为同一个术语。
    """
    return s.strip().lower()


def _validate(terms, min_len):
    """过滤掉不合格的术语。"""
    result = {}
    for k, v in terms.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        k = k.strip()
        v = v.strip()
        if len(k) < min_len:
            continue
        if not k or not v or k == v:
            continue
        if "\\" in k or "[" in k or "]" in k:
            continue
        # ★ 占位符 token（@0@ / ⟦0⟧）不是术语，严禁进入术语表
        #   否则会被 find_terms 当作命中术语注入 prompt，反向教模型翻译占位符
        if re.fullmatch(r'[@\u27e6]\d+[@\u27e7]', k):
            continue
        # 译文必须含中文（过滤未翻译项）
        if not re.search(r'[\u4e00-\u9fff]', v):
            continue
        result[k] = v
    return result


# ================================================================
# 读取现有术语
# ================================================================
def _load_existing_terms(path):
    """加载 term_dict.py 里已有的 TERM_DICT。"""
    if not os.path.exists(path):
        return {}
    try:
        ns = {}
        with open(path, "r", encoding="utf-8") as f:
            exec(f.read(), ns)
        return ns.get("TERM_DICT", {})
    except Exception as e:
        log.warning("读取 term_dict.py 失败：%s", e)
        return {}


# ================================================================
# 合并写文件
# ================================================================
def merge_into_term_dict(new_terms, conflicts_out=None):
    """
    把新术语合并到 term_dict.py 顶部的 AUTO 块。

    判断规则：
      · 只以「原文」作为判断条件
      · 原文归一化后（去空格 + 小写）已存在 → 跳过
      · 译文差异 → 输出警告，保留原有译文

    返回实际新增的条数。
    """
    if not new_terms:
        return 0

    min_len = getattr(config, "AUTO_EXTRACT_MIN_LEN", 3)
    new_terms = _validate(new_terms, min_len)
    if not new_terms:
        log.debug("候选术语未通过校验，全部丢弃")
        return 0

    existing = _load_existing_terms(config.TERM_FILE)
    existing_index = {
        _normalize_key(k): (k, v) for k, v in existing.items()
    }

    log.debug("已有术语 %d 条（归一化后 %d 个 key）",
              len(existing), len(existing_index))

    to_add = {}
    skipped_same = []
    skipped_diff = []

    for k, v in new_terms.items():
        norm = _normalize_key(k)
        if norm in existing_index:
            old_k, old_v = existing_index[norm]
            if old_v == v:
                skipped_same.append(k)
            else:
                skipped_diff.append((k, old_v, v))
            continue
        to_add[k] = v

    if skipped_same:
        log.debug("跳过已存在术语 %d 条：%s",
                  len(skipped_same),
                  ", ".join(skipped_same[:10])
                  + (f" …" if len(skipped_same) > 10 else ""))

    if skipped_diff:
        log.warning("=" * 60)
        log.warning("检测到 %d 条术语「原文相同但译文不同」：", len(skipped_diff))
        for k, old_v, new_v in skipped_diff:
            log.warning("  原文：%s", k)
            log.warning("    已有译文：%s  （保留）", old_v)
            log.warning("    本次译文：%s", new_v)
        log.warning("  如需更新译文，请手动编辑 term_dict.py")
        log.warning("=" * 60)

        # ★ 输出冲突列表，供上层加入 report
        if conflicts_out is not None:
            for k, old_v, new_v in skipped_diff:
                conflicts_out.append({
                    "src": k, "old": old_v, "new": new_v,
                })

    if not to_add:
        log.debug("所有候选术语均已存在，未新增")
        return 0

    log.debug("准备写入 %d 条新术语：%s",
              len(to_add),
              ", ".join(list(to_add.keys())[:10])
              + (" …" if len(to_add) > 10 else ""))

    path = config.TERM_FILE

    # 情况 A：文件不存在，从头创建
    if not os.path.exists(path):
        content = (
            "# -*- coding: utf-8 -*-\n"
            '"""术语表：由自动翻译工具维护"""\n\n'
            "TERM_DICT = {\n"
            f"{AUTO_START}\n"
            + "".join(
                f"    {json.dumps(k, ensure_ascii=False)}: "
                f"{json.dumps(v, ensure_ascii=False)},\n"
                for k, v in to_add.items()
            )
            + f"{AUTO_END}\n"
            "}\n"
        )
        _atomic_write(path, content)
        return len(to_add)

    # 情况 B：文件已存在，插入到 AUTO 块
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    insert_lines = "".join(
        f"    {json.dumps(k, ensure_ascii=False)}: "
        f"{json.dumps(v, ensure_ascii=False)},\n"
        for k, v in to_add.items()
    )

    if AUTO_END in text:
        idx = text.find(AUTO_END)
        new_text = text[:idx] + insert_lines + text[idx:]
    elif "TERM_DICT = {" in text:
        marker = "TERM_DICT = {"
        idx = text.find(marker) + len(marker)
        block = f"\n{AUTO_START}\n{insert_lines}{AUTO_END}\n"
        new_text = text[:idx] + block + text[idx:]
    else:
        log.warning("term_dict.py 格式异常，无法插入新术语")
        return 0

    _atomic_write(path, new_text)
    return len(to_add)


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ================================================================
# 对外唯一入口
# ================================================================
def merge_from_translation(terms_map, processor_module, conflicts_out=None):
    """
    把翻译过程中内联提取的术语合并到 term_dict.py。
    conflicts_out: 可选 list，收集"原文相同但译文不同"的冲突项。
    """
    if not terms_map:
        return 0

    all_terms = {}
    for idx, terms in terms_map.items():
        if not isinstance(terms, dict):
            continue
        for k, v in terms.items():
            if k not in all_terms:
                all_terms[k] = v

    if not all_terms:
        return 0

    log.debug("本批内联提取到术语 %d 条", len(all_terms))

    added = merge_into_term_dict(all_terms, conflicts_out=conflicts_out)
    if added:
        try:
            processor_module.load_terms()
        except Exception as e:
            log.warning("重载术语表失败：%s", e)
        log.info("术语表新增 %d 条（已生效于后续批次）", added)
    return added