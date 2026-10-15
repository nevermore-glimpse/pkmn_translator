# -*- coding: utf-8 -*-
r"""
术语提取：从「文本文件」里抽出专有名词，交给模型翻译，写进术语表。

为什么不用「翻译时由模型内联提取术语」
--------------------------------------
  · **来源确定**：名字来自游戏导出的文本本身，不会像内联提取那样漏掉、
    也不会被模型瞎编；
  · **覆盖完整**：一次把宝可梦 / 招式 / 道具 / 特性 / 属性 / 训练家 / 地图 /
    地区 / 缎带 … 等全提出来；
  · **不干扰翻译**：翻译 prompt 不再要求模型顺手吐术语 —— 省 token、也更稳。

数据来源（v1.6.8 起）
---------------------
不再读游戏的 Data/*.dat，改成读**用户选的文本文件**：

  · **选单个文件**：直接读它，并识别 `[7]` 这种**区块标志** ——
    区块号决定它是不是名字文件（见 intl_text.SECTION_NAMES）；
  · **选一整个文件夹**：递归扫 .txt，只留**名字区块**的文件
    （名里含独立的 NAME / NAMES 词，如 ABILITY_NAMES / ITEM_NAMES /
     ITEM_NAME_PLURALS / MAP_NAMES / MOVE_NAMES / REGION_NAMES /
     REGION_LOCATION_NAMES / RIBBON_NAMES / SPECIES_NAMES /
     SPECIES_FORM_NAMES / STORAGE_CREATOR_NAME / TRAINER_NAMES /
     TRAINER_TYPE_NAMES / TYPE_NAMES / ITEM_PORTION_NAMES /
     ITEM_PORTION_NAME_PLURALS），
    跳过「翻译中间文件」夹与 `*_translated` 译文文件。

文本格式（游戏导出的 intl 风格）
--------------------------------
    # To localize this text for a particular language, please
    # translate every second line of this file.
    [7]                       ← 区块标志，独占一行
    Repel                     ← 原文
    Repel                     ← 重复的第二行（翻译 / 替换它）
    ...
  `[编号]`、空行、纯数字（hash 型数据里的下标）、`#` 注释行都会被跳过，
  连续两行相同的取一条 —— 直接复用 parser.extract_entries。

写回
----
  翻好的术语经 auto_terms.merge_into_term_dict() 写进 term_dict.py 的
  **AUTO 块（自动提取区）**，随后调 processor.load_terms() 让翻译立刻用上。

用法
----
    p = plan(path)                       # 只统计，不调模型
    stats = run_extract(path, progress=cb, cancel=cb)
"""
import os
import re

import config
from logger import get_logger

log = get_logger("term_extract")

# 区块标志：[7] / [12] 这种（只认纯数字，避免把 [map1] 之类当成区块号）
_BLOCK_RE = re.compile(r'^\s*\[(\d+)\]\s*$')

# 名字文件名 / 名字区块名的判据：按 `_` 分词后含独立的 NAME / NAMES / NICKNAMES
#   —— 这样 ITEM_NAME_PLURALS（以 PLURALS 结尾）和 POKEMON_NICKNAMES
#      也能认出来。
_NAME_TOKENS = {"NAME", "NAMES", "NICKNAMES"}

# 明确不认的：译文文件（*_translated.txt / *_translated_report.txt）
_TRANSLATED_TOKENS = {"TRANSLATED"}

# 区块名 → 界面上显示的中文类别名（未知的用区块名兜底）
SECTION_LABEL = {
    "SPECIES_NAMES":              "宝可梦名",
    "SPECIES_FORM_NAMES":         "宝可梦形态名",
    "MOVE_NAMES":                 "招式名",
    "ITEM_NAMES":                 "道具名",
    "ITEM_NAME_PLURALS":          "道具名（复数）",
    "ITEM_PORTION_NAMES":         "道具数量名",
    "ITEM_PORTION_NAME_PLURALS":  "道具数量名（复数）",
    "ABILITY_NAMES":              "特性名",
    "TYPE_NAMES":                 "属性名",
    "TRAINER_TYPE_NAMES":         "训练家类型",
    "TRAINER_NAMES":              "训练家名",
    "REGION_NAMES":               "地区名",
    "REGION_LOCATION_NAMES":      "地区地点名",
    "MAP_NAMES":                  "地图名",
    "RIBBON_NAMES":               "缎带名",
    "STORAGE_CREATOR_NAME":       "存储系统创建者",
    "POKEMON_NICKNAMES":          "宝可梦昵称",
}

_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')
_LETTER_RE = re.compile(r'[A-Za-z\u00c0-\u024f]')

_SECTION_CACHE = None


def _tokens(text):
    """按 `_` 分词并大写（'item_name_plurals' → {'ITEM','NAME','PLURALS'}）。"""
    return set((text or "").upper().split("_"))


def _has_name_token(text):
    return bool(_tokens(text) & _NAME_TOKENS)


def _is_translated_name(text):
    """文件名是译文产物（*_translated / *_translated_report …）。"""
    return bool(_tokens(os.path.splitext(os.path.basename(text or ""))[0])
                & _TRANSLATED_TOKENS)


# ================================================================
# 区块号 ↔ 区块名（复用 intl_text.SECTION_NAMES，避免两处各写一份）
# ================================================================
def sections():
    """{区块号: 区块名}，如 {7: "ITEM_NAMES", 12: "TYPE_NAMES", ...}。"""
    global _SECTION_CACHE
    if _SECTION_CACHE is None:
        try:
            import intl_text as IT
            _SECTION_CACHE = dict(getattr(IT, "SECTION_NAMES", {}) or {})
        except Exception as e:              # pragma: no cover
            log.warning("读 intl_text.SECTION_NAMES 失败：%s", e)
            _SECTION_CACHE = {}
    return _SECTION_CACHE


def _is_names_section_name(name):
    return _has_name_token(name)


def names_section(block):
    """区块号 → 区块名；不是「名字区块」时返回 None。"""
    if block is None:
        return None
    name = sections().get(block)
    return name if _is_names_section_name(name) else None


def label_of(key):
    """
    「区块名 / 文件名主干」→ 中文类别名。

    key 优先当成区块名（大写），再退回家具名主干（小写）。
    """
    k = (key or "").strip()
    if not k:
        return "未命名"
    up = k.upper()
    if up in SECTION_LABEL:
        return SECTION_LABEL[up]
    return k


def is_names_file(path):
    """
    只按**文件名**判断算不算名字文件。

    判据：主干按 `_` 分词后含独立的 NAME / NAMES
          （ABILITY_NAMES / ITEM_NAME_PLURALS / STORAGE_CREATOR_NAME …）。
    `*_translated` 之类一律不算。
    """
    stem = os.path.splitext(os.path.basename(path or ""))[0]
    if not stem or _is_translated_name(stem):
        return False
    return _has_name_token(stem)


def peek_block(path):
    """只读文件开头几行，取出 `[编号]` 区块标志（没有 → None）。"""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for _ in range(30):
                line = f.readline()
                if line == "":
                    break
                m = _BLOCK_RE.match(line)
                if m:
                    try:
                        return int(m.group(1))
                    except ValueError:
                        return None
    except OSError:
        return None
    return None


def resolve_names(path):
    """
    判定一个文件算不算「要读的名字文件」。

    返回 (ok, section, block, reason)：
      · 译文文件（*_translated）一律不读；
      · 再看 `[编号]` 区块标志（权威）—— 是名字区块就收；
      · 区块认不出来时退回文件名判据（含独立 NAME / NAMES 词）；
      · 都不行 → ok=False + reason。
    """
    if not os.path.isfile(path):
        return False, None, None, "路径不存在"

    if _is_translated_name(path):
        return False, None, None, "译文文件（*_translated）不读"

    block = peek_block(path)
    sec = names_section(block)
    if sec:
        return True, sec, block, ""

    if is_names_file(path):
        stem = os.path.splitext(os.path.basename(path))[0]
        return True, stem.upper(), block, ""

    if block is not None:
        name = sections().get(block) or f"区块 {block}"
        return False, None, block, (
            f"区块 [{block}] = {name}，不是名字区块；"
            f"文件名也不含独立的 NAME / NAMES 词")
    return False, None, None, (
        "没有 [编号] 区块标志，文件名也不含独立的 NAME / NAMES 词")


# ================================================================
# 找文件
# ================================================================
def find_names_files(target, problems=None):
    """
    从「文件或文件夹」里找出所有要读的名字文件（已排序）。

    · target 是文件 → 只对它自己跑 resolve_names；
    · target 是文件夹 → 递归扫 .txt，逐个 resolve_names，跳过「翻译中间文件」夹。
    """
    if not target:
        return []

    if os.path.isfile(target):
        ok, sec, _blk, reason = resolve_names(target)
        if ok:
            return [target]
        if problems is not None:
            problems.append((target, reason))
        return []

    if not os.path.isdir(target):
        if problems is not None:
            problems.append((target, "路径不存在"))
        return []

    work_dir = getattr(config, "WORK_DIR_NAME", "翻译中间文件")
    found = []
    for root, dirs, files in os.walk(target):
        # 跳过我们自己的中间文件夹（缓存 / 报告 / 冲突 / 译文 …）
        dirs[:] = [d for d in dirs if d != work_dir and work_dir not in d]
        for fn in files:
            if not fn.lower().endswith(".txt"):
                continue
            p = os.path.join(root, fn)
            if resolve_names(p)[0]:
                found.append(p)
    found.sort()
    return found


# ================================================================
# 解析
# ================================================================
def _read_lines(path):
    """读文本，返回 (lines, newline)；不限行数（不受 MAX_INPUT_LINES 影响）。"""
    import parser as P
    return P.read_file(path, max_lines=0)


def _needs_translation(name):
    """
    这条名字还值不值得翻。

    · 纯数字 / 空 → 不值得；
    · 已经含中日韩文字 → 汉化版游戏的数据本来就是中文，跳过；
    · 一个拉丁字母都没有 → 多半是符号（???、--），跳过。
    """
    n = str(name or "").strip()
    if not n or n.isdigit():
        return False
    if _CJK_RE.search(n):
        return False
    return bool(_LETTER_RE.search(n))


def parse_names_file(path):
    """
    解析一个名字文件。

    返回 {"section": 区块名或 None, "block": 区块号或 None,
          "blocks": [区块号, ...], "names": [去重后的原文, ...],
          "raw": parser 认出的配对条目数}
    """
    import parser as P

    lines, _nl = _read_lines(path)
    blocks = []
    for ln in lines:
        m = _BLOCK_RE.match(ln)
        if m:
            try:
                blocks.append(int(m.group(1)))
            except ValueError:
                pass

    entries, _special = P.extract_entries(lines)

    names, seen = [], set()
    for _ln_no, txt in entries:
        n = str(txt or "").strip()
        if not n or n in seen or not _needs_translation(n):
            continue
        seen.add(n)
        names.append(n)

    block = blocks[0] if blocks else None
    section = names_section(block)
    if section is None and is_names_file(path):
        section = os.path.splitext(os.path.basename(path))[0].upper()

    return {"section": section, "block": block, "blocks": blocks,
            "names": names, "raw": len(entries)}


def collect(target):
    """
    读用户选的路径，返回 (file_metas, by_section, problems)：

      · file_metas : [{"path","section","label","block","count","raw"}, ...]
      · by_section : {区块名(小写): [原文, ...]}（**只在文件内去重**）
      · problems   : [(路径, 原因), ...]

    ★ 不跨文件去重：同一个英文词在不同类别里可能译法不同
      （招式 Psychic=精神强念，属性 Psychic=超能力）。给每条类别正确的
      「以下是【…】」上下文更准；真出现同词不同译，写回时由
      auto_terms 的「术语冲突」机制报出来，而不是被悄悄合并掉。
    """
    problems = []
    files = find_names_files(target, problems)

    file_metas, by_section = [], {}
    for p in files:
        try:
            info = parse_names_file(p)
        except Exception as e:
            log.warning("读名字文件失败（%s）：%s", p, e)
            problems.append((p, f"读取失败：{e}"))
            continue

        section = info["section"] or "未命名"
        key = section.lower()
        kept = list(info["names"])        # parse_names_file 已按文件内去重

        file_metas.append({"path": p, "section": section,
                           "label": label_of(section), "block": info["block"],
                           "count": len(kept), "raw": info["raw"]})
        if kept:
            by_section.setdefault(key, []).extend(kept)

    log.info("名字文件：%d 个，候选 %d 条", len(file_metas),
             sum(len(v) for v in by_section.values()))
    return file_metas, by_section, problems


def existing_keys():
    """术语表里已有的原文（归一化：去空白 + 小写）。"""
    import processor as PR
    try:
        PR.load_terms()
    except Exception as e:
        log.warning("术语表加载失败（按空表处理）：%s", e)
    keys = set()
    for k in (getattr(PR, "_TERM_SINGLE", None) or {}):
        keys.add(str(k).strip().lower())
    for t in (getattr(PR, "_TERMS", None) or []):
        try:
            keys.add(str(t[0]).strip().lower())
        except Exception:
            pass
    return keys


def plan(target):
    """
    算一遍「有哪些要翻」但不调用模型（界面用来先显示数量）。

    返回 {"found", "todo", "by_section", "files", "problems"}
      · files      : 识别到的名字文件（含区块号 / 类别 / 条数）
      · by_section : {区块名(小写): [待翻, ...]}
      · problems   : [(路径, 原因), ...]
    """
    file_metas, all_names, problems = collect(target)
    exist = existing_keys()

    by_section, todo = {}, 0
    for sec, names in all_names.items():
        rest = [n for n in names if n.strip().lower() not in exist]
        if rest:
            by_section[sec] = rest
            todo += len(rest)

    return {"found": sum(len(v) for v in all_names.values()),
            "todo": todo,
            "by_section": by_section,
            "files": file_metas,
            "problems": problems}


# ================================================================
# 提取 + 翻译 + 写入术语表
# ================================================================
def run_extract(target, batch_size=None, progress=None, cancel=None,
                client=None):
    """
    完整流程：读文本文件 → 去掉术语表里已有的 → 分批送模型翻 →
    合并进 term_dict.py 的 AUTO 块（自动提取区）。

    参数
    ----
    progress: 可选 callable(done, total, kind)，用于界面进度条
    cancel  : 可选 callable() -> bool，返回 True 时尽快停下
    client  : 可选，传入已建好的 OllamaClient（测试用；不传就自建并负责关闭）

    返回统计 dict：found / todo / translated / added / conflicts / empty / files
    """
    import translator as T
    import auto_terms
    import processor as PR

    step = int(batch_size or getattr(config, "TERM_EXTRACT_BATCH", 40) or 40)
    p = plan(target)
    stats = {"found": p["found"], "todo": p["todo"], "translated": 0,
             "added": 0, "conflicts": 0, "empty": 0,
             "files": len(p["files"]), "conflict_notes": []}
    if not p["todo"]:
        return stats

    own_client = client is None
    if own_client:
        client = T.OllamaClient()

    merged = {}
    run_conflicts = []          # [(原文, 先到的译文, 后到的译文), ...]
    done = 0
    total = p["todo"]
    try:
        for sec, names in p["by_section"].items():
            header = f"以下是【{label_of(sec)}】，"
            for i in range(0, len(names), step):
                if cancel and cancel():
                    log.info("术语提取被取消（已完成 %d/%d）", done, total)
                    break
                batch = names[i:i + step]
                try:
                    got = client.translate_terms(batch, header=header)
                except Exception as e:
                    log.warning("术语批翻译失败（%s 第 %d 批）：%s",
                                sec, i // step + 1, e)
                    got = {}
                if not got:
                    stats["empty"] += len(batch)
                # ★ 同一个原文在不同类别里译法不同（招式 Psychic / 属性 Psychic）：
                #   保留**先到的**（与 merge_into_term_dict「保留已有译文」一致），
                #   把差异记成「术语冲突」报出来，而不是让后到的悄悄覆盖。
                for k, v in got.items():
                    if k in merged:
                        if merged[k] != v:
                            run_conflicts.append((k, merged[k], v))
                        continue
                    merged[k] = v
                done += len(batch)
                if progress:
                    progress(done, total, label_of(sec))
    finally:
        if own_client:
            try:
                client.close()
            except Exception:
                pass

    if run_conflicts:
        log.warning("=" * 60)
        log.warning("本次提取里检测到 %d 条术语「同词不同译」（保留先到的）：",
                    len(run_conflicts))
        for k, keep, drop in run_conflicts:
            log.warning("  原文：%s  保留：%s  忽略：%s", k, keep, drop)

    stats["translated"] = len(merged)
    stats["conflict_notes"] = run_conflicts
    if merged:
        conflicts = []
        stats["added"] = auto_terms.merge_into_term_dict(
            merged, conflicts_out=conflicts)
        stats["conflicts"] = len(conflicts) + len(run_conflicts)
        try:
            PR.load_terms()          # 让后续翻译立刻用上新术语
        except Exception as e:
            log.warning("术语表重载失败：%s", e)
    log.info("术语提取完成：候选 %d，待翻 %d，翻出 %d，新增 %d，冲突 %d",
             stats["found"], stats["todo"], stats["translated"],
             stats["added"], stats["conflicts"])
    return stats
