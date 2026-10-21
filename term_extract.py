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

翻译走的是**正常翻译流水线**
--------------------------
  名字文件不另做一套提示词：直接调 commands._translate_core —— 与菜单 2
  「翻译」完全同一条流水线（同一套 user / system 模板、jsonline 输出格式、
  解析与缩块重试、`*_cache.json` 续翻、整句术语直译、术语注入 prompt），
  因此也会产出正常的 `*_translated.txt` 与检查报告。
  唯一的差别是翻完之后：把「原文 → 译文」当成术语，经
  auto_terms.merge_into_term_dict() 写进 term_dict.py 的 AUTO 块。

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
  `[编号]`、空行、纯数字（hash 型数据里的下标）、**文件开头最多 4 行**
  `#` 注释以及 `#-----` 分隔线会被跳过；文件中间以 `#` 开头的行是正常
  句子，照样提取。连续两行相同的取一条 —— 直接复用 parser.extract_entries。

写回
----
  每翻完一批就把这批的「原文 → 译文」经 auto_terms.merge_into_term_dict()
  写进 term_dict.py 的 **AUTO 块（自动提取区）**，随后调
  processor.load_terms(force=True) 让**同一文件的后续批次立刻用上新术语**；
  全部翻完之后再整体合并一次兜底（已并入的不会重复计数）。

  逐批提取由本模块的 make_batch_term_hook() 提供，经
  commands._translate_core(..., batch_term_hook=...) 挂进流水线；
  不传 hook 时流水线行为与以前完全一致（普通对话翻译不受影响）。

缓存、译文与断点续翻（完全复用正常翻译那一套）
----------------------------------------
   名字文件走的就是菜单 2「翻译」那条流水线（commands._translate_core），
   所以产出的一切也都是正常翻译那一套，本模块**不再自建**任何缓存：

   · **译文** `<名字文件>_translated.txt`（与源文件同目录）；
   · **缓存** `<中间文件夹>/<主名>_cache.json`（结构就是 {原文: 译文}，
     每条每批落盘、原子写 + Windows 占用重试）；
   · **检查报告** `<中间文件夹>/<主名>_report.txt`（checker 生成）。

   取消 / 崩溃后重跑，缓存里已有的条目不重新送模型，所以「取消」不再等于白干。

   ★ 本模块与 term_fix 都**不写术语专用报告**：不再产出
     `<目标名>_terms_report.txt`（提取汇总）与 `<目标名>_terms_check.txt`
     （问题清单）。提取结果只体现在术语表 AUTO 块、翻译缓存与日志里。

后续的配套功能
------------
   翻完之后还有两个配套功能，都在术语提取页「开始提取并翻译」右侧的
   「检查报告」按钮进入的那个页面（见 term_fix.py）：

   · **检查报告**（term_fix.check_terms / write_report）：只读缓存与
     术语表，按「译名为空 → 未翻（回显原文）→ 译文残留英文 →
     疑似机翻残留」四类互斥问题判定（另加可叠加的「同词不同译」）；
   · **改译名 / 应用修改**（term_fix.apply_fixes）：在报告里直接改译名，
     同时写回缓存、名字文件的译文文件（如有）与术语表 AUTO 块。

   这两项都不调用模型。另有 **术语重翻**（term_fix.retranslate）：删掉
   选中条目的缓存 key 后重走本模块这条流水线，**会调用模型**，并且同样
   逐批把新译名并入术语表。

名字文件的归属
------------
   名字文件只归本模块管：「游戏汉化」的翻译 / 检查报告 / 术语重翻 /
   中文润色 / 换行重排都会经 is_term_source_file() 把它们排除掉，
   避免同一批名词被两条流水线各翻一遍。

用法
----
    p = plan(path)                       # 只统计，不调模型
    stats = run_extract(path, progress=cb, cancel=cb)
"""
import json
import os
import re
import threading
import time

import config
from logger import get_logger

log = get_logger("term_extract")

# 逐批术语并入的串行锁：merge_into_term_dict 每次都重读 + 重写整个
# term_dict.py，并发批（ThreadPoolExecutor）必须串行化，否则互相覆盖。
_TERM_MERGE_LOCK = threading.Lock()

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
def is_term_source_file(path):
    """
    这个文件是不是「名字类文件」（术语提取要读的那批）。

    ★ 判定规则与 find_names_files 完全一致（resolve_names），只是不返回原因。
    ★ 供「游戏汉化」菜单 2–7 排除名字文件用：那批文件归「术语提取」管，
      翻译 / 重翻 / 润色 / 前缀字典都不该碰 —— 否则同一批名词会被
      翻译流水线和术语流水线各翻一遍，译法还可能不一致。
    ★ 名字刻意不与上面那个按文件名判据的 is_names_file 冲突：
       那个只看文件名，这个连 [编号] 区块一起看（更严，也更准）。
    """
    try:
        if not path or not os.path.isfile(path):
            return False
        return bool(resolve_names(path)[0])
    except Exception:
        return False


def split_out_names_files(paths):
    """
    把一批路径分成 (要处理的, 要跳过的名字文件)。

    ★ 「游戏汉化」菜单 2–7 的公共入口：调用方把用户选的文件列表交给它，
      拿回来的就是去掉名字文件后的清单，第二项用于提示用户跳过了什么。
    """
    keep, skipped = [], []
    for p in paths or []:
        if not p:
            continue
        if os.path.isfile(p) and is_term_source_file(p):
            skipped.append(p)
        else:
            keep.append(p)
    return keep, skipped


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


# ================================================================
# 路径：缓存 / 译文 / 检查报告全部复用正常翻译那一套
# ================================================================
# ★ 名字文件走的就是菜单 2「翻译」那条流水线，所以：
#     · 缓存 = <中间文件夹>/<主名>_cache.json（commands.cache_path_for）
#     · 译文 = 与源文件同目录的 <主名>_translated.txt（_translate_core 回写）
#     · 检查报告 = <中间文件夹>/<主名>_report.txt（checker 生成）
#   这里不再推导缓存路径，也不再产出 *_terms_cache.json；
#   ★ 也不再产出任何「术语专用报告」（_terms_report.txt / _terms_check.txt）——
#     术语的成果只落在术语表 AUTO 块与普通翻译缓存里，不额外写审计文件。


# ================================================================
# 名字文件 → 它的普通翻译缓存
# ================================================================
def read_name_cache(path):
    """读某个名字文件的**普通翻译缓存** → {原文: 译名}（读不到返回 {}）。"""
    import commands as C
    cp = C.cache_path_for(path) or ""
    if not cp or not os.path.isfile(cp):
        return {}
    try:
        with open(cp, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.warning("翻译缓存读取失败（忽略，按空缓存处理）：%s：%s", cp, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): ("" if v is None else str(v)) for k, v in data.items()}


def file_records(target, files=None):
    """
    解析名字文件，并把它的**普通翻译缓存**过滤到该文件的候选原文上。

    返回 [{"path","section","label","cache_path","names","present","cached"}, ...]
      · names   : 候选原文（parse_names_file 已按文件内去重，并去掉纯数字 /
                  已含中文 / 一个字母都没有的行）
      · present : {候选原文: 缓存里的原值}（含空串，用于「译名为空」检查）；
                  缓存里的非名字条目（同一文件里的对白等）**不会**混进来
      · cached  : {候选原文: 可用的译名}（有内容且不等于原文的那些）
    """
    import commands as C

    recs = []
    for p in (files if files is not None else find_names_files(target)):
        try:
            info = parse_names_file(p)
        except Exception as e:
            log.warning("读名字文件失败（跳过）：%s：%s", p, e)
            continue
        raw = read_name_cache(p)
        present, cached = {}, {}
        for n in info["names"]:
            if n not in raw:
                continue
            v = raw[n]
            present[n] = v
            sv = v.strip()
            if sv and sv != n:
                cached[n] = sv
        sec = info["section"] or "未命名"
        recs.append({"path": p, "section": sec, "label": label_of(sec),
                     "cache_path": C.cache_path_for(p) or "",
                     "names": info["names"], "present": present,
                     "cached": cached})
    return recs


def plan(target, use_cache=True):
    """
    算一遍「有哪些要翻」但不调用模型（界面用来先显示数量）。

    候选按三档分流（与正常翻译的「缓存命中」同一口径）：
      ① 术语表里已有译名（in_term）→ 不翻；
      ② **普通翻译缓存**里已有条目（in_cache）→ 不翻，_translate_core 会跳过；
      ③ 剩下的（todo）→ 这次真正送模型的。

    返回 {"found", "todo", "by_section", "files", "problems",
          "in_term", "in_cache", "cache_path"}
      · files      : 识别到的名字文件（含区块号 / 类别 / 条数）
      · by_section : {区块名(小写): [待翻, ...]}
      · problems   : [(路径, 原因), ...]
      · cache_path : 名字文件的**普通翻译缓存**路径（多个文件时给它们共用的
                     中间文件夹）
    """
    file_metas, all_names, problems = collect(target)
    files = [m["path"] for m in file_metas]

    # ★ 先按正常翻译的规矩把「翻译中间文件」夹建好（≥2 个文件同目录才建）：
    #   否则这里算出来的缓存路径与真正翻译时落盘的位置会不一致。
    #   旧版也是在这里就把中间文件夹建出来的（不然报告没处放）。
    import commands as C
    if files:
        C.enter_work_dir(files)

    recs = file_records(target, files)
    exist = existing_keys()

    by_section, todo = {}, 0
    n_term = n_cache = 0
    for r in recs:
        sec = r["section"].lower()
        in_cache = r["present"] if use_cache else {}
        rest = []
        for n in r["names"]:
            if n.strip().lower() in exist:
                n_term += 1
                continue
            if n in in_cache:
                n_cache += 1
                continue
            rest.append(n)
        if rest:
            by_section.setdefault(sec, []).extend(rest)
            todo += len(rest)

    if files:
        cp = C.cache_path_for(files[0]) or ""
        cache_path = cp if len(files) == 1 else os.path.dirname(cp)
    else:
        cache_path = ""

    return {"found": sum(len(v) for v in all_names.values()),
            "todo": todo,
            "by_section": by_section,
            "files": file_metas,
            "problems": problems,
            "in_term": n_term,
            "in_cache": n_cache,
            "cache_path": cache_path}


# ================================================================
# 逐批术语 hook：每批翻完立刻并进术语表，后续批次立刻用上
# ================================================================
def make_batch_term_hook(candidate_names=None):
    """
    造一个「本批翻完 → 立刻并入术语表」的回调，交给
    commands._translate_core(..., batch_term_hook=...)。

    参数
    ----
    candidate_names: 可选 set/list —— 只并进这些原文（就是本文件的候选名）；
                     None = 不过滤，pair 里的都收。

    返回 callable(pairs) -> int：pairs = [(原文, 译文), ...]，返回并入条数。

    ★ 只用传进来的 pairs，不重新读文件、不重新解析（开销与文件大小无关）。
    ★ 模块级锁串行化：并发批会在多个线程里调它，而 merge_into_term_dict
      每次都要重读 + 重写整个 term_dict.py。
    ★ 任何异常只记警告并返回 0，绝不中断翻译。
    """
    allowed = None if candidate_names is None else set(candidate_names)

    def hook(pairs):
        import auto_terms
        import processor as PR

        try:
            new_terms = {}
            for item in pairs or ():
                try:
                    src, dst = item
                except Exception:
                    continue
                if not isinstance(src, str) or not isinstance(dst, str):
                    continue
                if not dst.strip():
                    continue
                if dst.strip() == src.strip():
                    continue          # 原文回显，不是译名
                if allowed is not None and src not in allowed:
                    continue
                new_terms[src.strip()] = dst.strip()
            if not new_terms:
                return 0
            with _TERM_MERGE_LOCK:
                added = auto_terms.merge_into_term_dict(new_terms)
                PR.load_terms(force=True)   # 后续批次立刻用上新术语
            return int(added or 0)
        except Exception as e:
            log.warning("逐批术语并入失败（忽略，不影响翻译）：%s", e)
            return 0

    return hook


# ================================================================
# 提取 + 翻译（正常流水线）+ 写入术语表
# ================================================================
def run_extract(target, batch_size=None, progress=None, cancel=None,
                client=None):
    """
    完整流程：找出名字文件 → **逐个跑正常翻译流水线**（就是菜单 2「翻译」
    跑的那条）→ 全部跑完后把缓存里的「原文 → 译文」并入术语表 AUTO 块。

    ★ 与正常翻译只有两处不同：
       ① 名字类文件只在这里翻（别处已由 is_term_source_file 排除）；
       ② 翻完之后把缓存里的原文与译文并入术语表。
      中间的解析、分批、缓存续翻、整句术语直译、术语注入 prompt、
      `*_cache.json` / `*_translated.txt` / 检查报告，全部由
      commands._translate_core 原样产出，这里一处都不重写。

    参数
    ----
    batch_size: 兼容旧参数 —— 临时覆盖 config.BATCH_SIZE（正常翻译的分批口径）
    progress  : 可选 callable(done_files, total_files, 文件名)，界面进度条
    cancel    : 可选 callable() -> bool，返回 True 时尽快停下（已翻的已进缓存）
    client    : 可选，测试用假 client；正常翻译内部自建 OllamaClient，
                传了就临时顶替它（跑完还原）

    返回统计 dict：found / todo / translated / added / conflicts / empty /
    files / conflict_notes / in_term / in_cache / cancelled / cache_path
    """
    import bridge
    import commands as C
    import processor as PR
    import auto_terms

    p = plan(target)
    files = [m["path"] for m in p["files"]]
    stats = {"found": p["found"], "todo": p["todo"], "translated": 0,
             "added": 0, "conflicts": 0, "empty": 0, "files": len(files),
             "conflict_notes": [], "in_term": p["in_term"],
             "in_cache": p["in_cache"], "cancelled": False,
             "cache_path": p["cache_path"]}
    t0 = time.time()

    if not files:
        log.info("术语提取：没找到名字文件（%d 个读不了）", len(p["problems"]))
        return stats

    log.info("术语提取开始：%d 个名字文件、候选 %d 条、待翻 %d 条"
             "（术语表已有 %d、缓存已有 %d）",
             len(files), p["found"], p["todo"], p["in_term"], p["in_cache"])

    recs0 = file_records(target, files)
    names_of = {r["path"]: r["names"] for r in recs0}

    # ★ 兼容旧参数 batch_size：正常流水线按 config.BATCH_SIZE 分批，
    #   临时换一下，跑完还原。
    saved_batch = None
    has_batch = bool(batch_size)
    if has_batch:
        saved_batch = config.BATCH_SIZE
        config.BATCH_SIZE = int(batch_size)
    # ★ 测试注入假 client：正常翻译内部自建 OllamaClient，这里临时顶替。
    saved_client = None
    has_client = client is not None
    if has_client:
        saved_client = C.OllamaClient
        C.OllamaClient = lambda *a, **k: client
    # ★ 把调用方的 cancel 接到 bridge 上：正常翻译的批循环看的正是
    #   bridge.cancelled()，接上后中途取消也会「先把缓存落盘再退出」。
    #   ★ 还原必须用独立的标志位：saved 的值本来就是 None，不能拿它当判据，
    #     否则跑完会把调用方的 cancel 永久留在 bridge 上，后续翻译全被取消。
    saved_cancel = None
    has_cancel = cancel is not None
    if has_cancel:
        saved_cancel = bridge._cancel_fn
        bridge._cancel_fn = lambda: bool(cancel())

    translated = 0
    cancelled = False
    total = len(files)
    try:
        for i, path in enumerate(files, 1):
            if cancel and cancel():
                cancelled = True
                log.info("术语提取被取消（已完成 %d/%d 个文件，已翻的已进缓存）",
                         i - 1, total)
                break
            if not os.path.isfile(path):
                log.warning("名字文件不存在，跳过：%s", path)
                continue

            cp = C.cache_path_for(path) or ""
            before = _cache_snapshot(cp)
            config.Runtime.set_input(path)
            try:
                lines, newline = _read_lines(path)
            except Exception as e:
                log.warning("读取失败，跳过：%s：%s", path, e)
                continue

            log.info("[%d/%d] 翻译名字文件：%s", i, total, os.path.basename(path))
            try:
                # ★ 就是正常翻译那条流水线（与 commands.translate_paths 同写法）
                #   + 逐批 hook：本批翻完立刻并进术语表（候选集按**本文件**的
                #     候选原文构造），后续批次立刻用上新术语。
                C._translate_core(
                    path, lines, newline, show_header=(total == 1),
                    batch_term_hook=make_batch_term_hook(
                        set(names_of.get(path) or [])))
                # ★ 本文件翻完立刻刷新「术语检查报告」并重翻本文件的问题句
                #   （term_mode=True → term_fix.check_terms 那条路径）。
                #   只针对当前文件，不影响已经翻好的其它文件；内部包了
                #   try/except，报告失败不会打断整个提取流程。
                C._auto_check_file(path, term_mode=True)
            except Exception as e:
                log.error("翻译失败（继续下一个文件）：%s：%s", path, e)
                continue

            after = _cache_snapshot(cp)
            for n in names_of.get(path) or []:
                if n in before:
                    continue
                v = str(after.get(n) or "").strip()
                if v and v != n:
                    translated += 1
            if progress:
                progress(i, total, os.path.basename(path))

        # ---------- 全部翻完：缓存里的「原文 → 译文」并入术语表 ----------
        recs = file_records(target, files)
        pairs, notes = {}, []
        for r in recs:
            for n in r["names"]:
                v = r["cached"].get(n)
                if not v:
                    continue
                if n in pairs:
                    if pairs[n] != v:
                        # 同一个原文在不同类别里译法不同 → 保留先到的并报出来
                        notes.append((n, pairs[n], v))
                    continue
                pairs[n] = v

        stats["translated"] = translated
        stats["cancelled"] = cancelled
        stats["conflict_notes"] = notes
        if notes:
            log.warning("=" * 60)
            log.warning("检测到 %d 条术语「同词不同译」（保留先到的）：",
                        len(notes))
            for k, keep, drop in notes:
                log.warning("  原文：%s  保留：%s  忽略：%s", k, keep, drop)

        dict_conflicts = []
        if pairs:
            stats["added"] = auto_terms.merge_into_term_dict(
                pairs, conflicts_out=dict_conflicts)
            try:
                PR.load_terms(force=True)     # 让后续翻译立刻用上新术语
            except Exception as e:
                log.warning("术语表重载失败：%s", e)
        stats["conflicts"] = len(dict_conflicts) + len(notes)

        # ★ 仍缺译名：缓存里没有可用译名、术语表里也没有的候选（下次重跑会再送）
        exist = existing_keys()
        empty = 0
        for r in recs:
            for n in r["names"]:
                if r["cached"].get(n):
                    continue
                if n.strip().lower() in exist:
                    continue
                empty += 1
        stats["empty"] = empty

    finally:
        if has_batch:
            config.BATCH_SIZE = saved_batch
        if has_client:
            C.OllamaClient = saved_client
        if has_cancel:
            bridge._cancel_fn = saved_cancel

    elapsed = time.time() - t0
    log.info("术语提取%s：候选 %d，待翻 %d，新翻 %d，新增进术语表 %d，"
             "冲突 %d，仍缺译名 %d；总耗时 %.1f 秒",
             "（已取消）" if cancelled else "完成", stats["found"],
             stats["todo"], stats["translated"], stats["added"],
             stats["conflicts"], stats["empty"], elapsed)
    return stats


def _cache_snapshot(cache_path):
    """普通翻译缓存里的 {原文: 译文}（用来算「本次新翻了多少条」）。"""
    if not cache_path or not os.path.isfile(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
