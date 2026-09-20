# -*- coding: utf-8 -*-
"""
翻译过程中自动提取专有名词，写入 term_dict.py 顶部。

用法（由 commands.cmd_translate 调用）：
    auto_terms.process_batch(client, pairs, processor_module)
       pairs = [(原文, 译文), ...]
"""
import json
import os
import re

import config
from logger import get_logger

log = get_logger("auto_terms")


# ================================================================
# 提取 prompt
# ================================================================
EXTRACT_SYSTEM = """你是宝可梦游戏术语提取助手。
从用户给出的「原文 / 译文」句子对中，判断句子各自使用的语言并识别出其中的专有名词，输出双语对照字典。

【必须提取的类型】
1. 训练家 / NPC 名字，包括方括号里的名字：
   - 输入 \\tg[Fátima] → 提取 Fátima
   - 输入 [Owen] → 提取 Owen
   - 输入 [Lionel, el Campeón de Galar] → 提取整段 "Lionel, el Campeón de Galar"
2. 宝可梦名称：Pikachu、Helioptile、Charizard、Elgyem
3. 地名 / 城镇 / 道路 / 地区：Pallet Town、Route 1、Galar
4. 道具名称：Poké Ball、Potion、Repartir Exp.
5. 招式名称：Thunderbolt、Fly
6. 组织 / 队伍：Team Rocket
7. 游戏机制 / 特殊名词：PokéRus

【绝对不要提取】
- 人称代词：I、you、he、she、it、we、they、me、him、her、us、them
- 指示代词：this、that、these、those
- 疑问代词：who、what、which
- 冠词、介词、连词、助动词
- 普通日常名词：pokemon、ball、house、town、man、woman、boy、girl、day、time
- 纯数字、时间、货币符号
- 已经是中文的内容

【输出格式】
只输出一个 JSON 对象，不要任何解释，不要 markdown 代码块：
{"原文1": "译文1", "原文2": "译文2"}

【严格要求】
- 译文必须是对应的中文翻译，绝对不能直接复制原文
- 如果某个专有名词在译文中**没有对应翻译**（仍是原样），**按照自己的理解翻译它**
- 如果没有找到任何专有名词，输出：{}

【示例】
输入：
<0>[Fátima]Unamos fuerzas, . ¡Iré curando a tus Pokémon sobre la marcha!
<0>[法蒂玛]与我联手。我将随行治疗你的宝可梦。
<1>Go to Pallet Town. Helioptile is waiting for you.
<1>前往真新镇。伞电蜥在等你。

输出：
{"Fátima": "法蒂玛", "Pallet Town": "真新镇", "Helioptile": "伞电蜥"}
"""


# ================================================================
# 文本清理
# ================================================================
# 清理：把控制码和方括号标签替换成可读形式
_CLEAN_CTRL = re.compile(r'\\[A-Za-z]+(?:\[[^\]]*\])?')
_CLEAN_TAG  = re.compile(r'\[([^\]]*)\]')


def _clean_for_extract(text):
    """
    把控制码转成可读形式，方便模型识别术语：
      \\tg[Fátima]  → [Fátima]
      \\n \\N        → 空格
      \\PN          → 删掉
    """
    if not text:
        return ""
    # \n \N → 空格
    text = re.sub(r'\\(?:n|N)', ' ', text)
    # \tg[Fátima] → [Fátima]
    text = re.sub(r'\\[A-Za-z]+\[([^\]]*)\]',
                  lambda m: f"[{m.group(1)}]", text)
    # 剩下的 \PN 之类直接删掉
    text = re.sub(r'\\[A-Za-z]+', '', text)
    return text


# ================================================================
# JSON 解析（容错）
# ================================================================
_FENCE_RE = re.compile(r'^```[\w-]*\s*$', re.MULTILINE)


def _parse_json(raw):
    """从模型输出里提取 JSON 对象，失败返回 {}。"""
    if not raw:
        return {}

    text = raw.strip()

    # 去掉 markdown 代码块
    text = _FENCE_RE.sub("", text).strip()

    # 尝试直接解析
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    # 兜底：抓第一个 { ... }
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    return {}


# ================================================================
# 从句子对提取
# ================================================================
def extract_from_pairs(client, pairs):
    """
    pairs: [(原文, 译文), ...]
    返回: {原文: 译文}；失败返回 {}
    """
    if not pairs:
        return {}

    clean_pairs = []
    for s, t in pairs:
        s = _clean_for_extract((s or "").strip())
        t = _clean_for_extract((t or "").strip())
        if s and t and s != t:
            clean_pairs.append((s, t))

    if not clean_pairs:
        return {}

    lines = []
    for i, (s, t) in enumerate(clean_pairs):
        lines.append(f"<{i}>{s}")
        lines.append(f"<{i}>{t}")
    body = "\n".join(lines)

    user_msg = f"""请从下面的句子对中提取专有名词，输出 JSON 字典。

{body}

只输出 JSON，不要其它内容。无术语时输出 {{}}。
"""

    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    try:
        raw = client.chat_raw(messages, temperature=0.05, num_predict=1200)
    except Exception as e:
        log.warning("术语提取请求失败：%s", e)
        return {}

    log.debug("术语提取原始返回：%s", raw[:300])
    return _parse_json(raw)


# ================================================================
# 写入 term_dict.py
# ================================================================
AUTO_START = "    # @@AUTO_TERMS_START@@"
AUTO_END   = "    # @@AUTO_TERMS_END@@"


def _normalize_key(s):
    """
    归一化原文 key，用于存在性比较。
    规则：去首尾空白 + 全部转小写。
    这样 Owen / owen / "  Owen " 会被视为同一个术语。
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
        # 译文必须含中文（过滤 "Owen": " Owen" 这种未翻译的情况）
        if not re.search(r'[\u4e00-\u9fff]', v):
            continue
        result[k] = v
    return result


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


def merge_into_term_dict(new_terms):
    """
    把新术语合并到 term_dict.py 顶部的 AUTO 块。

    判断规则（按需求定义）：
      · 只以「原文」作为判断条件
      · 原文归一化后（去空格 + 小写）在术语表中已存在 → 跳过
      · 译文（value）不影响判断，即使译文不同也不覆盖已有条目
      · 若译文存在差异 → 输出警告日志，但仍保留原有译文

    返回实际新增的条数。
    """
    if not new_terms:
        return 0

    min_len = getattr(config, "AUTO_EXTRACT_MIN_LEN", 3)
    new_terms = _validate(new_terms, min_len)
    if not new_terms:
        log.debug("候选术语未通过校验，全部丢弃")
        return 0

    # ---------- 加载已有术语，构建归一化索引 ----------
    existing = _load_existing_terms(config.TERM_FILE)
    # {归一化 key: (原始 key, 原始译文)}
    existing_index = {
        _normalize_key(k): (k, v) for k, v in existing.items()
    }

    log.debug("已有术语 %d 条（归一化后 %d 个 key）",
              len(existing), len(existing_index))

    # ---------- 按原文过滤 ----------
    to_add = {}
    skipped_same = []          # 完全一样，安静跳过
    skipped_diff = []          # 原文相同但译文不同，需要警告

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

    # ---------- 输出跳过日志 ----------
    if skipped_same:
        log.info("跳过已存在术语 %d 条：%s",
                 len(skipped_same),
                 ", ".join(skipped_same[:10])
                 + (f" …" if len(skipped_same) > 10 else ""))

    # ---------- 译文差异警告 ----------
    if skipped_diff:
        log.warning("=" * 60)
        log.warning("检测到 %d 条术语「原文相同但译文不同」：", len(skipped_diff))
        for k, old_v, new_v in skipped_diff:
            log.warning("  原文：%s", k)
            log.warning("    已有译文：%s  （保留）", old_v)
            log.warning("    本次译文：%s", new_v)
        log.warning("  如需更新译文，请手动编辑 term_dict.py")
        log.warning("=" * 60)

    if not to_add:
        log.debug("所有候选术语均已存在（按原文判断），未新增")
        return 0

    log.info("准备写入 %d 条新术语：%s",
             len(to_add),
             ", ".join(list(to_add.keys())[:10])
             + (" …" if len(to_add) > 10 else ""))

    # ---------- 写文件 ----------
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
        # 已有 AUTO 块 → 插到 END 之前
        idx = text.find(AUTO_END)
        new_text = text[:idx] + insert_lines + text[idx:]
    elif "TERM_DICT = {" in text:
        # 没有 AUTO 块 → 在 TERM_DICT = { 之后创建
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
# 对外一步到位
# ================================================================
def process_batch(client, pairs, processor_module):
    """
    提取 + 合并 + 重载术语表。
    pairs            : [(原文, 译文), ...]
    processor_module : processor 模块（用于 reload）
    返回: 实际新增的术语数
    """
    if not getattr(config, "AUTO_EXTRACT_TERMS", True):
        return 0
    if not pairs:
        return 0

    terms = extract_from_pairs(client, pairs)
    if not terms:
        log.debug("本批未提取到术语")
        return 0

    log.info("本批提取到候选术语 %d 条", len(terms))

    added = merge_into_term_dict(terms)
    if added:
        # 重载 processor 的术语表，让后续批次立即使用
        try:
            processor_module.load_terms()
        except Exception as e:
            log.warning("重载术语表失败：%s", e)
        log.info("术语表新增 %d 条（已生效于后续批次）", added)
    else:
        log.debug("候选术语均已存在，未新增")

    return added