# -*- coding: utf-8 -*-
"""
按文本类别选用专用提示词（区块/文件名路由 + 提示词装配）。

★ 与「写提示词正文」的同事约定好的契约（机制侧，不要自行更改）：
  · 目录：prompts/categories/<SECTION>.txt，SECTION ∈ SECTIONS（共 31 类）；
  · 语言覆盖：prompts/<语言代码>/categories/<SECTION>.txt
    （语言代码沿用 translator._lang_code()，如 zh）；
  · 正文纯文本、无 front matter，依次含 【本文本类型】【翻译规则】
    【翻译方法】【示例】四段；控制码规则与 JSON 输出格式**不**写在这里
    —— 它们在共享 system 前缀里，写重了等于每批白烧 token。
  · 装配：通用规则在前（保持稳定前缀，利于 KV 缓存复用），类别段追加其后。

★ 本模块只管**机制与接线**。文件缺失 / 读失败 / 类别判不出，一律退回
  「只用共享 system」的旧行为（逐字节一致），绝不抛异常。

★ 路由规则（区块号权威优先，文件名兜底）：
  1. 区块标志：读文件开头若干行找 `[数字]` 或 `[MapNNN]`；
     · `[数字]`   → intl_text.SECTION_NAMES（0 号单独叫 EVENT_TEXTS）；
     · `[MapNNN]` → EVENT_TEXTS（实测 EVENT_TEXTS.txt 的 86 个块都是这个形式，
       编号范围 [Map000]–[Map104] 且**不连续**，区间内有 19 个缺号）。
     注意 term_extract._BLOCK_RE 只认纯数字，所以 `[MapNNN]` 是本模块另加的。
  2. 文件名兜底：主干去扩展名、去 _translated / _report 之类产物后缀后转大写，
     命中 31 类之一就用它。
  3. 都判不出 → None（用通用提示词）。
"""
import os
import re

import config
import translator as TR
from logger import get_logger

log = get_logger("cat_prompts")


# ================================================================
# 31 个文本类别（权威表：SECTION → 中文类别名）
# ================================================================
SECTIONS = (
    "EVENT_TEXTS",
    "SPECIES_NAMES",
    "SPECIES_CATEGORIES",
    "POKEDEX_ENTRIES",
    "SPECIES_FORM_NAMES",
    "MOVE_NAMES",
    "MOVE_DESCRIPTIONS",
    "ITEM_NAMES",
    "ITEM_NAME_PLURALS",
    "ITEM_DESCRIPTIONS",
    "ABILITY_NAMES",
    "ABILITY_DESCRIPTIONS",
    "TYPE_NAMES",
    "TRAINER_TYPE_NAMES",
    "TRAINER_NAMES",
    "FRONTIER_INTRO_SPEECHES",
    "FRONTIER_END_SPEECHES_WIN",
    "FRONTIER_END_SPEECHES_LOSE",
    "REGION_NAMES",
    "REGION_LOCATION_NAMES",
    "REGION_LOCATION_DESCRIPTIONS",
    "MAP_NAMES",
    "PHONE_MESSAGES",
    "TRAINER_SPEECHES_LOSE",
    "SCRIPT_TEXTS",
    "RIBBON_NAMES",
    "RIBBON_DESCRIPTIONS",
    "STORAGE_CREATOR_NAME",
    "ITEM_PORTION_NAMES",
    "ITEM_PORTION_NAME_PLURALS",
    "POKEMON_NICKNAMES",
)

CATEGORY_LABELS = {
    "EVENT_TEXTS":                 "地图/公共事件文本",
    "SPECIES_NAMES":               "宝可梦名",
    "SPECIES_CATEGORIES":          "分类名",
    "POKEDEX_ENTRIES":             "图鉴说明",
    "SPECIES_FORM_NAMES":          "形态名",
    "MOVE_NAMES":                  "招式名",
    "MOVE_DESCRIPTIONS":           "招式说明",
    "ITEM_NAMES":                  "道具名",
    "ITEM_NAME_PLURALS":           "道具复数",
    "ITEM_DESCRIPTIONS":           "道具说明",
    "ABILITY_NAMES":               "特性名",
    "ABILITY_DESCRIPTIONS":        "特性说明",
    "TYPE_NAMES":                  "属性名",
    "TRAINER_TYPE_NAMES":          "训练家类型",
    "TRAINER_NAMES":               "训练家名",
    "FRONTIER_INTRO_SPEECHES":     "开场白",
    "FRONTIER_END_SPEECHES_WIN":   "胜利台词",
    "FRONTIER_END_SPEECHES_LOSE":  "失败台词",
    "REGION_NAMES":                "地区名",
    "REGION_LOCATION_NAMES":       "地点名",
    "REGION_LOCATION_DESCRIPTIONS": "地点说明",
    "MAP_NAMES":                   "地图名",
    "PHONE_MESSAGES":              "电话文本",
    "TRAINER_SPEECHES_LOSE":       "训练家败北文本",
    "SCRIPT_TEXTS":                "脚本内文本",
    "RIBBON_NAMES":                "缎带名",
    "RIBBON_DESCRIPTIONS":         "缎带说明",
    "STORAGE_CREATOR_NAME":        "存储系统创建者",
    "ITEM_PORTION_NAMES":          "道具数量名",
    "ITEM_PORTION_NAME_PLURALS":   "道具数量名（复数）",
    "POKEMON_NICKNAMES":           "宝可梦昵称",
}

_SECTION_SET = frozenset(SECTIONS)


# ================================================================
# 区块标志 → section
# ================================================================
# 只认纯数字（与 term_extract._BLOCK_RE 同口径）
_BLOCK_NUM_RE = re.compile(r'^\s*\[(\d+)\]\s*$')
# ★ 另加：EVENT_TEXTS.txt 用的是 [Map000] … [Map104] 这种形式（86 个，
#   编号不连续：区间内缺 5, 21, 28, 38–41, 44, 45, 51, 52, 66, 68, 70,
#   73, 78, 83, 97, 100 共 19 个），所以这里只按 [map\d+] 匹配、不假设连续
_BLOCK_MAP_RE = re.compile(r'^\s*\[map\d+\]\s*$', re.IGNORECASE)

# 只读文件开头这么多行找块标志（与 term_extract.peek_block 一致）
_PEEK_LINES = 30

# 产物后缀（按 `_` 分词后整词匹配）：SPECIES_NAMES_translated.txt 之类
_STRIP_TOKENS = frozenset({"TRANSLATED", "REPORT"})

# 类别正文的四个固定小节标题（顺序即约定顺序）
_MARKERS = ("【本文本类型】", "【翻译规则】", "【翻译方法】", "【示例】")

_SECTION_CACHE = None


def _block_sections():
    """{区块号: 区块名}，复用 intl_text.SECTION_NAMES（避免两处各写一份）。"""
    global _SECTION_CACHE
    if _SECTION_CACHE is None:
        try:
            import intl_text as IT
            _SECTION_CACHE = dict(getattr(IT, "SECTION_NAMES", {}) or {})
        except Exception as e:                  # pragma: no cover
            log.warning("读 intl_text.SECTION_NAMES 失败（区块号将无法判定）：%s", e)
            _SECTION_CACHE = {}
    return _SECTION_CACHE


def _section_of_block(num):
    """区块号 → section；0 号是地图/公共事件文本（见 intl_text._section_file_name）。"""
    if num == 0:
        return "EVENT_TEXTS"
    return _block_sections().get(num)


def _peek_block_section(path):
    """读文件开头若干行，把块标志解析成 section；没有 / 认不出 → None。"""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for _ in range(_PEEK_LINES):
                line = f.readline()
                if line == "":
                    break
                m = _BLOCK_NUM_RE.match(line)
                if m:
                    sec = _section_of_block(int(m.group(1)))
                    if sec:
                        return sec
                    continue            # 认不出的编号：继续往下扫 / 交给文件名兜底
                if _BLOCK_MAP_RE.match(line):
                    return "EVENT_TEXTS"
    except OSError as e:
        log.debug("读块标志失败（%s）：%s", path, e)
    return None


def _stem_section(path):
    """文件名主干 → section（兜底用）；对不上 31 类 → None。"""
    stem = os.path.splitext(os.path.basename(path or ""))[0]
    if not stem:
        return None
    toks = [t for t in stem.upper().split("_") if t]
    while toks and toks[-1] in _STRIP_TOKENS:
        toks.pop()                      # _translated / _report 之类产物后缀
    cand = "_".join(toks)
    return cand if cand in _SECTION_SET else None


def section_for(path):
    """
    判定一个待翻译 .txt 属于哪个文本类别；判不出返回 None。

    区块标志**权威优先**，文件名兜底（详见模块 docstring）。整函数不抛异常：
    路径不存在 / 读不了 / 都对不上 → None（调用方据此用通用提示词）。
    """
    sec = _peek_block_section(path)
    if sec:
        return sec
    sec = _stem_section(path)
    if sec:
        log.debug("按文件名判定 section：%s → %s", path, sec)
    return sec


# ================================================================
# 类别提示词文件的读取（prompts/categories/，支持语言覆盖）
# ================================================================
_PROMPT_CACHE = {}        # (语言代码, 相对路径) → 文件正文
_VALIDATED = set()        # 已做过四段校验的 (语言代码, section)


def _read_prompt_file(rel):
    """
    读 prompts/<rel>；沿用 load_template 的查找顺序与缓存约定。

      · 查找顺序：prompts/<语言代码>/<rel> → prompts/<rel> → 空串；
      · 每次调用都做 os.path.isfile 探测（打包后 exe 旁放同名文件即可热替换，
        不该被缓存挡住），但读到的内容按 (语言代码, rel) 缓存。

    ★ load_template 只接受文件名、不认子目录，所以这里另写一个等价小函数，
      不改动 load_template 的现有语义。rel 形如 "categories/MOVE_NAMES.txt"。
    """
    code = TR._lang_code()
    ck = (code, rel)
    for r in (os.path.join(config.PROMPT_DIR, code, rel),
              os.path.join(config.PROMPT_DIR, rel)):
        p = config.resource_path(r)
        if p and os.path.isfile(p):
            hit = _PROMPT_CACHE.get(ck)
            if hit is not None:
                return hit
            try:
                with open(p, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                log.warning("类别提示词读取失败（按无类别段处理）：%s：%s", p, e)
                return ""
            _PROMPT_CACHE[ck] = text
            log.info("类别提示词模板：%s", p)
            return text
    return ""


def _check_markers(section, text):
    """四段标题是否齐全；缺了只警告一次，绝不阻断（正文由同事维护）。"""
    key = (TR._lang_code(), section)
    if key in _VALIDATED:
        return
    _VALIDATED.add(key)
    miss = [m for m in _MARKERS if m not in text]
    if miss:
        log.warning("类别提示词 %s 缺少小节标题：%s（约定是四段齐全）",
                    section, "、".join(miss))


def _section_text(section):
    """读类别文件正文；读不到 / 类别非法 → ""（并 debug 一行）。"""
    if section not in _SECTION_SET:
        log.debug("未知 section（%r），只用共享 system", section)
        return ""
    text = _read_prompt_file(os.path.join("categories", section + ".txt"))
    if not text.strip():
        log.debug("类别提示词缺失，只用共享 system：%s", section)
        return ""
    _check_markers(section, text)
    return text


def _segments(text):
    """把类别正文按四个固定小节标题切成 {标题: 正文}（不依赖顺序与完整性）。"""
    hits = []
    for mk in _MARKERS:
        i = text.find(mk)
        if i >= 0:
            hits.append((i, mk))
    if not hits:
        return {}
    hits.sort()
    out = {}
    for n, (i, mk) in enumerate(hits):
        start = i + len(mk)
        end = hits[n + 1][0] if n + 1 < len(hits) else len(text)
        out[mk] = text[start:end].strip()
    return out


def category_block(section):
    """
    翻译用类别段：`【本文本类型：<中文类别名>】` 标题行 + 类别文件**全文**。

    ★ 装配：与 style_block 同一口径 —— 用带中文类别名的标题
      `【本文本类型：<中文类别名>】` **替代**正文里那个裸标题 `【本文本类型】`，
      而不是再在前面接一行（否则同一标题会出现两次）。只替换**第一处**
      （即标题那一行）：正文若在别处提到这个记号属于内容，不该动。

    ★ 与 style_block 的关键差异：这里**全量保留**其余小节
      （`【翻译规则】`、`【翻译方法】`、`【示例】`）—— 翻译需要规则与示例；
      style_block 才做裁剪。

    与共享 system 的拼接由调用方（translator._system_prompt）负责，且必须
    **追加在最后**：通用规则是每个请求最前面那段逐字节稳定的前缀，KV 缓存
    靠它复用；类别段放末尾后，section 相同的批次前缀一致、section 不同只
    在前缀之后分叉。

    文件不存在 / 读失败 / section 非法 → ""（调用方退回只用共享 system）。
    """
    text = _section_text(section)
    if not text:
        return ""
    label = CATEGORY_LABELS.get(section) or section
    head = f"【本文本类型：{label}】"
    if "【本文本类型】" in text:
        return text.replace("【本文本类型】", head, 1)
    # 正文没写裸标题（正常交付的文件都有）：退化为「标题 + 全文」，
    # 保证输出一定以类别标题开头。
    log.debug("类别提示词 %s 缺裸标题，改为前置标题拼接", section)
    return head + "\n" + text


def style_block(section):
    """
    润色用类别段：只取类别文件里**风格/术语相关**的两段 ——
    `【本文本类型】` 与 `【翻译方法】`，不取 `【示例】`、不取 `【翻译规则】`。

    ★ 取舍与理由：
      · 【示例】一律不取：示例是完整的「原文→译文」对照，进 prompt 极易被
        小模型当成待改写/待输出的内容照抄进结果（润色是**改写已有译文**，
        多一段原文对照反而诱导它重译），且示例最长、token 成本最高。
      · 【翻译规则】不取：那一节面向「首次翻译」，写的是不增不删、
        控制码保留、输出 JSON 之类**翻译型**约束，与润色的任务目标不同；
        润色的约束（控制码必须原样、只改中文表达）由共享的
        system_polish.txt 负责，重复写只会互相干扰。
      · 【本文本类型】要取：润色必须知道这段文本是什么类别（宝可梦名不能
        被润成一句话、图鉴说明要保持叙述口吻），且它自带该类别的术语
        （招式名/属性名/道具名等的固定译法），润色时最容易改坏的就是术语。
      · 【翻译方法】要取：它写的是这一类文本「怎么处理才地道」（如名称类
        保持简短、台词类保留语气），正是润色要利用的风格信息。

    ★ 装配：用带中文类别名的标题 `【本文本类型：<中文类别名>】` **替代**正文里
      那个裸标题 `【本文本类型】`（避免同一标题出现两次），再接【翻译方法】段。

    文件不存在 / 读失败 / section 非法 → ""（调用方退回只用共享 system）。
    """
    text = _section_text(section)
    if not text:
        return ""
    segs = _segments(text)
    label = CATEGORY_LABELS.get(section) or section
    head = f"【本文本类型：{label}】"
    own = segs.get("【本文本类型】", "")
    if own:
        head += "\n" + own
    method = segs.get("【翻译方法】", "")
    if not own and not method:
        log.debug("类别提示词 %s 取不到风格段（风格块留空）：%s",
                  section, "、".join(_MARKERS))
        return ""
    parts = [head]
    if method:
        parts.append("【翻译方法】\n" + method)
    return "\n\n".join(parts)
