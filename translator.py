# -*- coding: utf-8 -*-
"""
翻译客户端 + 批量翻译 / 中文润色。
  · 翻译：输出固定 JSON，每行 {"id":N,"text":"译文"}
  · 术语提取（term_extract.py）**就是这条翻译流水线**：名字文件直接走
    正常翻译，翻完由 term_extract 把「原文→译文」并进术语表
  · 整批失败 → 重试 → 拆分两半 → 递归
  · 无推理模式（think=False），旧版 Ollama 自动降级
  · 提示词模板外置到 prompts/ 目录（按目标语言覆盖），文件缺失用内置默认
  · 云端服务：多 Key 轮换 + 冷却阶梯 + 并发自适应（429 减半 / 成功 +1）
"""
import os
import re
import threading
import time

import requests

import config
from logger import get_logger

log = get_logger("translator")


# ================================================================
# 提示词模板（外置到 prompts/，内置常量是兜底默认）
# ================================================================
# ★ 模板设计原则（改之前先读一遍）：
#   1. 稳定规则全放 system：system 是每批都一模一样的前缀，
#      llama.cpp / Ollama 会复用它的 KV 缓存，前缀越长省得越多；
#      而 user 里每批都变（术语表 + 正文），放那里的规则等于每批重发。
#   2. 只在 system 里说一遍，user 里绝不重复规则（旧版两处都写，白烧 token）。
#   3. 术语行 @@T 改为「有专有名词才输出」，大部分台词没有专名，
#      省掉一半输出 token。
#   4. 优先级顺序要显式：先准确、再通顺、后生动 —— 小模型最容易为了
#      "生动" 添油加醋，明确写"不增不删"比抽象要求有效。
#   5. 模板文件在 prompts/ 下，按目标语言放 prompts/{zh,en,ja}/ 可覆盖
#      默认版本；改模板不用动代码，exe 旁放同名文件即可热替换。

# ---------------- 中文润色 ----------------
POLISH_SYSTEM_PROMPT = r"""你的任务是把已经译成中文的游戏台词润色成更地道的{tgt}。

【输出】
每条一行：
<编号>译文
不要解释、空行、markdown，不要输出【参考原文】。

【必须遵守】
1. 控制码（\n \c[3] \v[10] \tg[Owen] 等）原样保留，不翻译、不改写、不移动，
   数量、位置、大小写都不变。
2. 保留换行控制码 \n；不要在 \n 前后新增标点。
3. 不改变原意、事实、情绪方向、人物关系；不新增动作、心理活动或设定；
   不改变句子数量，不删减内容，可以适当调整句子长度和语序。
4. 输入里有多少个编号，就必须输出多少行，一个都不能少、不能合并；
   也不要输出输入里没有的编号。

【润色标准】
通顺：符合中文口语习惯，消除翻译腔、语序别扭、搭配不当、代词/量词误用、重复啰嗦。
生动：在原文信息范围内用更具体、有画面感的说法，让台词有代入感。
贴角色：按说话人身份、性格、情绪调整口吻，同一角色前后一致。
克制：生动不等于堆辞藻；不要网络梗、不要过度文艺。
"""

_POLISH_TEMPLATE = r"""{body}
"""

# 翻译用 system 提示词（输出格式固定 JSON）
SYSTEM_PROMPT_JSONLINE = r"""你是专业游戏本地化译者，负责把游戏文本翻译成{tgt}。

【控制码】
输入里的控制码必须原样保留、不翻译、不改写、不移动：
· 反斜杠命令：\n \N \PN \c[3] \v[10] \tg[Owen] \w[speech hgss 3] \xn[Leticia] 等
· 尖括号标签：<ar> </ar> <<n>> 等；HTML 实体：&quot; 等
数量、位置、大小写都不变，不新增也不删除。
例：\c[3]你好\n再见 → 译文里 \c[3] 与 \n 必须还在原来的位置。

【翻译】
准确第一：语义、语气、人物性格随人物变化
生动第二：对话、感叹、拟声词可有画面感，可用成语/口语，但不改原意。
通顺第三：语义连贯，语句通顺，可读性强，可以适当调整句子的长度、语序等

【术语表】
用户提供则必须遵守；遇到表内词，无论大小写/数量，都用表内中文。
表内词为词根的派生词、复合词（+s 复数，或 +ite/+ites/+nite/+ium/+Z 等道具、进化石命名）也用同一个译名，再按词义把后缀补成中文。
例：Altarianite=七夕青鸟进化石 → Altarianites 译作「七夕青鸟进化石」；不要音译成别的词。

【输出】
每行输出一条 JSON，编号与输入一一对应，一个都不能少、不能合并：
{"id":<编号>,"text":"<译文>"}
不要解释，不要空行，不要 markdown 代码围栏，不要注释。
JSON 字符串里的双引号必须转义成 \"；换行必须转义成 \n。
正文里若出现 <数字> 字样的游戏内容，那是台词本身，原样保留在译文里。
"""

_USER_TEMPLATE_JSONLINE = r"""把下面每条翻译成{tgt}，每行输出一条 JSON，格式：
{"id":<编号>,"text":"<译文>"}
{terms_block}输入：
{body}
"""

# <why> 结构化思考块（config.THINKING_BLOCK=True 时追加到 system 末尾）
THINKING_BLOCK = r"""输出结果前，在<why></why>块内按格式进行极简的**结构化思考**：
<why>
- 语境：影响理解的语境、指代、语气和主谓关系
- 决策：结合当前指令，明确关键约束、歧义或翻译难点的处理方式
</why>
"""

# 目标语言显示名 → prompts/ 子目录代码
_LANG_CODE_BY_NAME = (
    (("简体", "中文", "汉语"), "zh"),
    (("繁体",), "zh-Hant"),
    (("英文", "英语"), "en"),
    (("日文", "日语"), "ja"),
    (("韩文", "朝鲜"), "ko"),
)


def _lang_code():
    for names, code in _LANG_CODE_BY_NAME:
        if any(n in str(config.TARGET_LANG) for n in names):
            return code
    return "default"


_TEMPLATE_CACHE = {}      # (code, name) → 模板文本


def load_template(name, default):
    """
    读 prompts/ 下的模板文件；找不到用内置默认。

    查找顺序：prompts/<语言代码>/<name> → prompts/<name> → default。
    ★ 每次调用都做 os.path.isfile 探测（打包后 exe 旁边放同名文件
       即可热替换，不该被缓存挡住），但读到的内容按 (code, name) 缓存。
    """
    code = _lang_code()
    ck = (code, name)
    for rel in (os.path.join(config.PROMPT_DIR, code, name),
                os.path.join(config.PROMPT_DIR, name)):
        p = config.resource_path(rel)
        if p and os.path.isfile(p):
            hit = _TEMPLATE_CACHE.get(ck)
            if hit is not None:
                return hit
            try:
                with open(p, "r", encoding="utf-8") as f:
                    text = f.read()
                _TEMPLATE_CACHE[ck] = text
                log.info("提示词模板：%s", p)
                return text
            except Exception as e:
                log.warning("提示词模板读取失败（用内置默认）：%s：%s", p, e)
                break
    return default



# ================================================================
# 术语行解析
# ================================================================
_TERMS_PREFIX = "@@T:"

# 模型偶尔包一层 markdown 代码围栏
_FENCE_RE = re.compile(r'^\s*```[a-zA-Z]*\s*$')

# 思考块：**只在响应开头**剥离（借鉴 LinguaGacha 的 /^\s*<why>/i）。
#   ★ 不要写成全篇贪婪匹配（旧版 `.*?(?:</think>|<think>|$)`+DOTALL）：
#     · 模型漏写 </think> 时那个 `|$` 会把后面**整篇译文**当思考内容吃掉；
#     · 正文里本来就有 "<think>" 字样的台词也会被误删。
#     实测："正文里有 <think> 这个字样的台词。" → 旧版剥离后只剩 "正文里有 "。
_THINK_OPEN_RE = re.compile(r'^\s*<think\b[^>]*>', re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r'</think>', re.IGNORECASE)
_THINK_ALT_CLOSE_RE = re.compile(r'<think\b[^>]*>', re.IGNORECASE)


def _first_think_close(rest):
    """在 rest 里找最近的思考块收尾符（</think> 或下一个 <think>）。

    返回收尾符之后的偏移；一个都没有时返回 None。
    """
    close = _THINK_CLOSE_RE.search(rest)
    alt = _THINK_ALT_CLOSE_RE.search(rest)
    if close is None and alt is None:
        return None
    if close is None:
        return alt.end()
    if alt is None:
        return close.end()
    return min(close.end(), alt.end())


def split_leading_think(raw):
    """
    剥掉响应**开头**的思考块，返回 (正文, 出现过思考块没有)。

    · 只在开头循环剥：正文中间出现的 <think> 属于译文本身，一律不动；
    · 开头的块没有闭合 → 认为整篇都是思考内容，正文返回空串
      （随后会被判成「模型无返回」走重试，而不是悄悄截断译文）。
    """
    text = raw or ""
    seen = False
    while True:
        m = _THINK_OPEN_RE.match(text)
        if not m:
            break
        seen = True
        rest = text[m.end():]
        end = _first_think_close(rest)
        if end is None:
            return "", seen
        text = rest[end:]
    return text, seen


def _strip_noise(raw):
    """去掉**开头**的思考块、代码围栏、首尾空白。"""
    if not raw:
        return ""
    text, _had_think = split_leading_think(raw)
    lines = []
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _nothink_hint():
    """当前服务提供商关掉推理模式的办法（给日志提示用）。"""
    try:
        import providers as PV
        return PV.nothink_hint(PV.current())
    except Exception:
        return "Ollama 用 think=false，其余服务请在服务端关闭"


def _clean_terms(obj):
    """术语 dict 归一：丢掉空值 / 原文==译文 / 占位符型 key。"""
    out = {}
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        k, v = str(k).strip(), str(v).strip()
        if not k or not v or k == v:
            continue
        # 占位符 token（@0@ / ⟦0⟧）不是术语，丢弃，避免污染术语表与 prompt
        if re.fullmatch(r'[@\u27e6]\d+[@\u27e7]', k):
            continue
        out[k] = v
    return out


def _extract_terms_obj(line):
    """从一行（可能残缺的）JSON 文本里抠出 "terms" 对象；失败返回 {}。

    用括号配平扫描，避免正则被嵌套花括号带偏。
    """
    import json as _json
    i = line.find('"terms"')
    if i < 0:
        return {}
    j = line.find("{", i)
    if j < 0:
        return {}
    depth = 0
    for k in range(j, len(line)):
        c = line[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = _json.loads(line[j:k + 1])
                except Exception:
                    return {}
                return obj if isinstance(obj, dict) else {}
    return {}


def _parse_terms_line(content):
    """
    解析 '@@T:k1=v1|k2=v2' 格式。返回 dict（可能为空）。
    不是术语行时返回 None。
    """
    if not content.startswith(_TERMS_PREFIX):
        return None
    body = content[len(_TERMS_PREFIX):].strip()
    if not body:
        return {}
    result = {}
    for pair in body.split("|"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, _, v = pair.partition("=")
        k, v = k.strip(), v.strip()
        if not k or not v or k == v:
            continue
        # ★ 占位符 token（@0@ / ⟦0⟧）不是术语，丢弃，避免污染术语表与 prompt
        if re.fullmatch(r'[@\u27e6]\d+[@\u27e7]', k):
            continue
        result[k] = v
    return result


def build_terms_block_string(term_pairs, limit=None):
    """
    ★ 术语块的「唯一组装函数」——组装与算 token 在这里解耦。

    term_pairs: [(原文, 译文), ...]
    limit     : None 时取 config.MAX_TERMS_IN_PROMPT（受它截断）

    自适应分批要按「真实组装出来的字符串」算术语块 token，所以切批侧
    （commands）与请求侧（translate_batch）都调这一个函数，避免两处各拼
    一遍导致格式漂移、token 算错。
    """
    if not term_pairs:
        return ""

    if limit is None:
        limit = getattr(config, "MAX_TERMS_IN_PROMPT", 80)

    # 按原文长度降序（长词优先展示，模型更容易记住）
    items = sorted(term_pairs, key=lambda x: -len(x[0]))
    items = items[:limit]

    # 表头写短一点：这段每批都要发，长表头等于每批多烧一份 token
    lines = ["【术语表·必须使用】"]
    for src, dst in items:
        lines.append(f"{src}={dst}")
    # 结尾紧跟正文，注意力最集中，这里放硬约束，防止模型看到却忽略
    lines.append("以下词条必须原样出现在译文里，不得改写、不得近义替换、不得音译。")
    lines.append("")     # 尾空行，与下面 {body} 隔开
    return "\n".join(lines) + "\n"


def _format_terms_block(term_pairs, limit=None):
    """
    term_pairs: [(原文, 译文), ...]
    返回术语表块，或空串。兼容旧名的薄壳，本体见 build_terms_block_string。
    """
    return build_terms_block_string(term_pairs, limit)


# ================================================================
# 自适应分批：上下文预算
# ================================================================
def _preset_ctx_limit():
    """当前服务提供商预设里的 NUM_CTX；取不到返回 0。"""
    try:
        import providers as PV
        cur = PV.current()
        presets = getattr(PV, "PRESETS", {}) or {}
        return int((presets.get(cur) or {}).get("NUM_CTX", 0) or 0)
    except Exception:
        return 0


def resolve_ctx_limit():
    """模型上下文窗口（token）：CTX_LIMIT > 0 用它，否则预设 NUM_CTX → NUM_CTX → 8192。"""
    try:
        n = int(getattr(config, "CTX_LIMIT", 0) or 0)
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        return n
    n = _preset_ctx_limit()
    if n > 0:
        return n
    try:
        n = int(getattr(config, "NUM_CTX", 8192) or 8192)
    except (TypeError, ValueError):
        n = 8192
    return n if n > 0 else 8192


def resolve_ctx_budget(ctx_limit=None):
    """每批 token 预算 = 上下文窗口 × CTX_BUDGET_RATIO（钳在 (0, 1]）。"""
    if ctx_limit is None:
        ctx_limit = resolve_ctx_limit()
    try:
        ratio = float(getattr(config, "CTX_BUDGET_RATIO", 0.9) or 0)
    except (TypeError, ValueError):
        ratio = 0.9
    if ratio <= 0:
        ratio = 0.9
    if ratio > 1:
        ratio = 1.0
    return max(1, int(ctx_limit * ratio))


def estimate_output_tokens(src_tokens):
    """预留输出 token = 原文 token × CTX_OUTPUT_RATIO + 每条固定开销。"""
    try:
        ratio = float(getattr(config, "CTX_OUTPUT_RATIO", 1.5) or 0)
    except (TypeError, ValueError):
        ratio = 1.5
    if ratio < 0:
        ratio = 0.0
    try:
        overhead = int(getattr(config, "CTX_OUTPUT_OVERHEAD", 8) or 0)
    except (TypeError, ValueError):
        overhead = 8
    return int(src_tokens * ratio) + overhead


def _decode_by_line_count(raw, items):
    """
    按「每条源文本的行数」把响应切回条目（Sakura 式对齐）。

    很多小模型根本不理 <编号> / JSON，只是**照着输入的行数逐行输出译文**。
    这种情况下：

      · 逐行扫描：源码的每条 item 占 `len(src.splitlines())` 行，
        响应里对应位置的同样行数就是它的译文（空行也占位置）；
      · **整批行数必须正好对上**（消耗完的 == 总行数）；
      · 任何一条切出来是空的 → 整体不接受。

    只要对不上就返回 {}，让上层的缩块重试去处理 —— 位置猜错了比不翻更糟。

    items: [(idx, src_text), ...]
    返回 {idx: text}；对不上返回 {}。
    """
    if not raw or not items:
        return {}
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = {}
    offset = 0
    for idx, src in items:
        n = len(str(src).splitlines()) or 1
        chunk = lines[offset:offset + n]
        offset += n
        if offset > len(lines):
            return {}
        text = "\n".join(chunk).strip()
        if not text:
            return {}
        # 模型吐了编号格式（JSON 行 / <N> tag 行）：整体拒绝，交给上层重试
        if text.startswith('{"id"') or re.match(r"<\s*\d+\s*>", text):
            return {}
        out[idx] = text
    if offset != len(lines):
        return {}
    return out


def _parse_model_output(raw, expected=None):
    """
    逐行解析模型输出。
    返回 (translations, terms_map)：
      translations: {idx: text}
      terms_map:    {idx: {src: dst}}

    expected: 本批输入的编号集合；给了就**只收这些编号**——
      模型偶尔会把台词里的 <3> 之类的字样另起一行输出，或自己编造编号，
      不挡住的话会污染别的条目（先到的假行占坑，真译文反被丢掉 → 漏句）。

    ★ 同一编号重复出现时保留「第一条非空」结果：
      模型偶尔先输出草稿再输出终稿，取第一条更稳。

    ★ 翻译走 JSON（{"id":N,"text":"...","terms":{...}}）：逐行 json.loads，
      失败走逐字段抠取兜底（模型漏转义引号 / 多逗号都能救）。
    ★ 同时保留 tag 行（<N>译文 / <N>@@T:术语）的解析：润色流程用的就是
      <编号>译文，模型偶尔也会不听话输出这个格式。
    """
    translations = {}
    terms_map = {}

    if not raw:
        return translations, terms_map

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        # ---------- JSON（唯一输出格式） ----------
        if line.startswith("{"):
            idx, text, terms = _parse_json_line(line)
            if idx is None:
                continue          # 修不好的残行：丢弃，交给重试
            if expected is not None and idx not in expected:
                continue
            if terms:
                terms_map.setdefault(idx, {}).update(terms)
            if text:
                translations.setdefault(idx, text)
            continue

        # ---------- tag 格式 ----------
        m = re.match(r"<\s*(\d+)\s*>(.*)", line)
        if not m:
            continue
        idx = int(m.group(1))
        if expected is not None and idx not in expected:
            continue          # ★ 编号不在本批输入里：直接丢弃，防串行
        content = m.group(2).strip()

        parsed = _parse_terms_line(content)
        if parsed is not None:
            if parsed:
                bucket = terms_map.setdefault(idx, {})
                bucket.update(parsed)
            continue

        for prefix in ("译文：", "翻译：", "Translation:", "译："):
            if content.startswith(prefix):
                content = content[len(prefix):].strip()
                break

        if not content:
            continue
        if idx in translations:
            continue          # ★ 保留第一条非空结果
        translations[idx] = content

    # ---------- 兜底：整个响应就是一个 JSON 对象 ----------
    # 模型把**真换行**（而不是 \n 转义）写进 text 里时，逐行解析全废；
    # 这时把整段当一个 JSON 抠还能救回来。
    # 只在响应里只有一个 "id" 时才敢这么干，多条时抠出来必然张冠李戴。
    if not translations:
        stripped = raw.strip()
        if (stripped.startswith("{")
                and len(re.findall(r'"id"\s*:', stripped)) == 1):
            _idx, _text, _terms = _parse_json_line(stripped)
            if _idx is not None and (expected is None or _idx in expected):
                if _terms:
                    terms_map.setdefault(_idx, {}).update(_terms)
                if _text:
                    translations[_idx] = _text

    return translations, terms_map


def _json_str(s):
    """把文本安全地编码成 JSON 字符串字面量（含外层引号）。"""
    import json as _json
    return _json.dumps(str(s), ensure_ascii=False)


# jsonline 行的两个字段（兜底抽取用）
_JSON_ID_RE = re.compile(r'"id"\s*:\s*"?(\d+)"?')
_JSON_TEXT_START_RE = re.compile(r'"text"\s*:\s*"')


def _parse_json_line(line):
    """
    解析一条 {"id":N,"text":"...","terms":{...}}。
    返回 (idx, text, terms)；完全解析不出来时返回 (None, None, {})。

    先 json.loads；失败（常见原因：译文里的引号没转义、行尾多逗号）
    退回「逐字段抠取」：id 用正则，text 用引号扫描（认 \" 转义），
    terms 用括号配平扫描。
    """
    import json as _json
    try:
        obj = _json.loads(line)
        if isinstance(obj, dict) and "id" in obj:
            idx = int(obj["id"])
            text = obj.get("text")
            if text is None:
                text = obj.get("translation", "")
            return (idx, ("" if text is None else str(text)),
                    _clean_terms(obj.get("terms")))
    except Exception:
        pass

    m_id = _JSON_ID_RE.search(line)
    if not m_id:
        return None, None, {}
    try:
        idx = int(m_id.group(1))
    except ValueError:
        return None, None, {}
    text = _extract_text_field(line)
    if text is None:
        return None, None, {}
    return idx, text.strip(), _clean_terms(_extract_terms_obj(line))


def _extract_text_field(line):
    """从容错路径的 JSON 行里抠出 "text" 的字符串值；失败返回 None。

    ★ 有 terms 字段时：text 的结束引号 = terms 之前最后一个引号 ——
      这样 text 里带未转义的引号也能正确截断（旧版贪心匹配会把
      terms 一起吞进去）。
    ★ 没有 terms 时：退到行尾 } 之前的最后一个引号（旧版行为）。
    """
    m = _JSON_TEXT_START_RE.search(line)
    if not m:
        return None
    i = m.end()

    t = line.find('"terms"', i)
    if t >= 0:
        seg = line[i:t]
        j = len(seg) - 1
        while j >= 0 and seg[j] in " \t,":
            j -= 1
        if j >= 0 and seg[j] == '"':
            seg = seg[:j]
        else:
            seg = seg.rstrip().rstrip(",")
        return _unescape_json_str(seg)

    k = line.rfind('"')
    if k <= i:
        return None
    return _unescape_json_str(line[i:k])


def _unescape_json_str(raw):
    """JSON 字符串反转义（只处理常见几种，其余原样留下）。"""
    return (raw.replace('\\"', '"')
               .replace("\\n", "\n")
               .replace("\\t", "\t")
               .replace("\\\\", "\\"))


# ================================================================
# token 估算（分批用；借鉴 LinguaGacha 的 token 感知切块）
# ================================================================
_TIKTOKEN = None          # 延迟导入：装了 tiktoken 就用 o200k_base 精确计数
_TIKTOKEN_TRIED = False


def _get_tiktoken():
    global _TIKTOKEN, _TIKTOKEN_TRIED
    if _TIKTOKEN_TRIED:
        return _TIKTOKEN
    _TIKTOKEN_TRIED = True
    try:
        import tiktoken
        _TIKTOKEN = tiktoken.get_encoding("o200k_base")
    except Exception:
        _TIKTOKEN = None
    return _TIKTOKEN


def estimate_tokens(text):
    """
    估算一段文本的 token 数。

    · 装了 tiktoken → o200k_base 精确计数（与 LinguaGacha 同款）；
    · 没装 → 经验值：CJK 每字 1 token、其余每 4 字符 1 token
      （中英混排的台词误差在一两成以内，用来切批足够）。
    """
    if not text:
        return 0
    enc = _get_tiktoken()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    cjk = 0
    other = 0
    for ch in text:
        if '\u2e80' <= ch <= '\u9fff' or '\uac00' <= ch <= '\ud7af' \
                or '\uff00' <= ch <= '\uffef' or '\u3000' <= ch <= '\u303f':
            cjk += 1
        else:
            other += 1
    return cjk + (other + 3) // 4


# ================================================================
# Ollama 客户端
# ================================================================
def _is_api_mode():
    """TRANSLATE_MODE 是否为云端服务（"api"），与协议无关。"""
    return str(getattr(config, "TRANSLATE_MODE", "ollama")).lower() == "api"


def _request_target():
    """
    当前请求目标：协议 / 地址 / 模型 / 超时 / 要不要带 Key。
    取自 providers.request_target()。
    """
    try:
        import providers as PV
        return PV.request_target()
    except Exception:
        pass
    # providers 不可用时的兜底
    api = _is_api_mode()
    return {
        "protocol": "openai" if api else "ollama",
        "base_url": str(getattr(config,
                                "API_BASE_URL" if api else "OLLAMA_URL", "")
                        or ""),
        "model": config.API_MODEL if api else getattr(config, "MODEL", ""),
        "timeout": (getattr(config, "API_TIMEOUT", 120) or config.TIMEOUT
                    if api else getattr(config, "TIMEOUT", 600)),
        "use_key": api,
        "local": not api,
        "cloud": api,
        "key": "",
    }


def _is_anthropic_base(base):
    """是否 Anthropic Messages 协议地址（以 /anthropic 结尾）。"""
    return str(base or "").rstrip("/").lower().endswith("/anthropic")


def _api_max_tokens(want):
    """把 max_tokens 钳到 API_MAX_TOKENS 以内，避免服务端 400。"""
    limit = int(getattr(config, "API_MAX_TOKENS", 1048576) or 1048576)
    try:
        want = int(want or 0)
    except (TypeError, ValueError):
        want = 0
    return limit if want <= 0 else min(want, limit)


# ================================================================
# 云端服务调度器：多 Key 轮换 + 冷却 + 并发自适应
# ================================================================
def _split_api_keys():
    """
    收集可用 API Key：config.API_KEYS（每行一个）优先，
    为空则退回 config.API_KEY 单 key。去空行、去重、保序。
    """
    raw = str(getattr(config, "API_KEYS", "") or "")
    keys = [k.strip() for k in raw.splitlines() if k.strip()]
    single = str(getattr(config, "API_KEY", "") or "").strip()
    if single and single not in keys:
        keys.insert(0, single)
    return keys


def _parse_retry_after(resp):
    """从 429 响应头读 Retry-After（秒）；读不到返回 None。"""
    try:
        v = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        if v is None:
            return None
        return max(0.0, float(str(v).strip()))
    except Exception:
        return None


class ApiScheduler:
    """
    单客户端共用的 API 调度器（线程安全）。

    · 并发槽：acquire() 阻塞拿槽，release() 归还；
      AUTO_CONCURRENCY 开启时，429 → 并发减半，成功 → +1（限 min~max）；
    · Key 状态机：ready → cooling（失败进冷却）→ probing（冷却结束试探）。
      连续失败按 KEY_COOLDOWN_STEPS 阶梯 [15s, 30s, 60s] 加长冷却；
      429 额外尊重服务端 Retry-After。
    """

    def __init__(self, keys=None, concurrency=None, auto=None):
        self._keys = keys if keys is not None else _split_api_keys()
        if not self._keys:
            self._keys = [""]
        n = len(self._keys)
        self._key_state = [{"fail": 0, "until": 0.0} for _ in range(n)]
        self._rr = 0                     # 轮询游标
        c_min = max(1, int(getattr(config, "CONCURRENCY_MIN", 1) or 1))
        c_max = max(c_min, int(getattr(config, "CONCURRENCY_MAX", 300) or 300))
        explicit = concurrency is not None
        if not explicit:
            concurrency = resolve_concurrency()
        self._conc = max(c_min, min(c_max, int(concurrency or 1)))
        self._auto = (getattr(config, "AUTO_CONCURRENCY", True)
                      if auto is None else bool(auto))
        self._c_min, self._c_max = c_min, c_max
        # ★ 本地服务（Ollama / llama.cpp / LM Studio）恒串行：
        #   自适应会在请求成功后一路 +1（上限 CONCURRENCY_MAX），把「并发 1」
        #   悄悄顶上去。这里只在**自动解析**时压到 1、并关掉自适应；
        #   显式传了 concurrency / auto 的调用方按它给的来。
        if _is_local_provider():
            if auto is None:
                self._auto = False
            if not explicit:
                self._conc = 1
        self._active = 0
        self._cond = threading.Condition()

    # ---------- 查询 ----------
    @property
    def concurrency(self):
        with self._cond:
            return self._conc

    def stats(self):
        with self._cond:
            cooling = sum(1 for s in self._key_state
                          if s["until"] > time.time())
            return {"keys": len(self._keys), "cooling": cooling,
                    "concurrency": self._conc, "active": self._active}

    # ---------- 槽位 + Key ----------
    def acquire(self, timeout=None):
        """
        拿一个并发槽和一个可用 Key，返回 (key, index)。
        冷却中的 Key 不占槽；全部 Key 都在冷却时等到最早恢复的那个。
        """
        deadline = None if timeout is None else time.time() + timeout
        with self._cond:
            while True:
                now = time.time()
                # ① 有空闲槽 → 找一个 ready 的 Key
                if self._active < self._conc:
                    for _ in range(len(self._keys)):
                        i = self._rr % len(self._keys)
                        self._rr += 1
                        if self._key_state[i]["until"] <= now:
                            self._active += 1
                            return self._keys[i], i
                # ② 没有 ready 的 Key：等到最早恢复点（或空槽出现）
                waits = [s["until"] - now for s in self._key_state
                         if s["until"] > now]
                if deadline is None:
                    self._cond.wait(max(0.05, min(waits) if waits else 0.05))
                else:
                    left = deadline - time.time()
                    if left <= 0:
                        raise TimeoutError("等待 API 调度槽超时")
                    self._cond.wait(max(0.05, min(min(waits) if waits
                                                  else 0.05, left)))

    def release(self, index, ok=True, rate_limited=False, retry_after=None):
        """归还槽位并汇报结果（ok=False 时按情况冷却该 Key）。"""
        steps = list(getattr(config, "KEY_COOLDOWN_STEPS", None)
                     or [15, 30, 60])
        with self._cond:
            self._active = max(0, self._active - 1)
            st = self._key_state[index]

            if rate_limited:
                # 429：并发减半（在途请求不受影响，下一批才降档）
                if self._auto:
                    self._conc = max(self._c_min, self._conc // 2)
                st["fail"] += 1
                cool = steps[min(st["fail"] - 1, len(steps) - 1)]
                if retry_after:
                    cool = max(cool, min(retry_after, 300.0))
                st["until"] = time.time() + cool
                log.warning("API 429：并发降至 %d，Key#%d 冷却 %.0fs",
                            self._conc, index + 1, cool)
            elif not ok:
                st["fail"] += 1
                cool = steps[min(st["fail"] - 1, len(steps) - 1)]
                st["until"] = time.time() + cool
                log.warning("API 请求失败：Key#%d 冷却 %.0fs（第 %d 次）",
                            index + 1, cool, st["fail"])
            else:
                st["fail"] = 0
                st["until"] = 0.0
                if self._auto and self._conc < self._c_max:
                    self._conc += 1
            self._cond.notify()


def _is_local_provider():
    """
    当前是不是**本机**服务：Ollama / llama.cpp / LM Studio。

    ★ 这三个都是本机单卡（或 CPU）推理，请求并发发过去只是在服务端排队，
      既不会更快，还容易撑爆显存 / 上下文；所以本地一律串行。
      「custom」可能是本机也可能是远端，不在这里判定。
    """
    try:
        import providers as PV
        return PV.current() in ("ollama", "llamacpp", "lmstudio")
    except Exception:
        return not _is_api_mode()


def resolve_concurrency():
    """
    实际并发批数：TRANSLATE_CONCURRENCY > 0 就用它（按本地/云端钳到上限）；
    = 0（默认）→ 本地服务 1，云端服务 4。
    上限：云端 CONCURRENCY_MAX（300），本地 LOCAL_CONCURRENCY_MAX（16）。
    """
    n = int(getattr(config, "TRANSLATE_CONCURRENCY", 0) or 0)
    local = _is_local_provider()
    if local:
        cap = max(1, int(getattr(config, "LOCAL_CONCURRENCY_MAX", 16) or 16))
    else:
        cap = max(1, int(getattr(config, "CONCURRENCY_MAX", 300) or 300))
    if n > 0:
        return max(1, min(n, cap))
    if local:
        return 1
    return 4


class OllamaClient:
    """翻译客户端：本地服务与云端服务共用同一套接口。"""

    def __init__(self, model=None):
        self.session = requests.Session()
        # 协议由服务提供商决定，不看翻译模式
        self.target = _request_target()
        self.api_mode = self.target["protocol"] != "ollama"
        self.cloud_mode = bool(self.target.get("cloud"))
        if model:
            self.model = model
        elif self.target["model"]:
            self.model = self.target["model"]
        else:
            self.model = (config.API_MODEL if self.cloud_mode
                          else config.MODEL)
        self._think_supported = True
        # token 用量累计（含前缀缓存命中）
        self.usage = {"calls": 0, "hit": 0, "miss": 0, "out": 0}
        # 调度器（多 Key 轮换 + 并发自适应）只给云端用
        use_sched = self.api_mode and self.cloud_mode and self.target["use_key"]
        self._sched = ApiScheduler() if use_sched else None
        proto = ""
        if self.api_mode:
            base = self.target["base_url"]
            proto = ("，协议=Anthropic Messages"
                     if _is_anthropic_base(base) else "，协议=OpenAI 兼容")
            if self._sched is not None:
                n_keys = len(_split_api_keys())
                proto += f"，Key×{n_keys}，并发{self._sched.concurrency}"
            else:
                proto += f"，{base}"
        log.info("翻译客户端初始化  模式=%s%s  模型=%s",
                 "云端服务" if self.cloud_mode else "本地服务", proto, self.model)

    # ---------- 底层 ----------
    def _lmstudio_ttl(self):
        """LM Studio 的 ttl（秒）；其它服务或不启用时返回 0。"""
        try:
            n = int(getattr(config, "LMSTUDIO_TTL", 0) or 0)
        except (TypeError, ValueError):
            return 0
        if n <= 0:
            return 0
        try:
            import providers as PV
            return n if PV.current() == "lmstudio" else 0
        except Exception:
            return 0

    # ---------- token 用量 ----------
    def _record_usage(self, data):
        """把一次响应的 usage 累计到 self.usage。"""
        if not isinstance(data, dict):
            return
        u = data.get("usage") or {}
        self.usage["calls"] += 1

        hit = u.get("prompt_cache_hit_tokens")
        miss = u.get("prompt_cache_miss_tokens")
        if hit is None and miss is None:
            # 没有缓存字段按全文未命中计
            miss = (u.get("prompt_tokens")
                    or u.get("prompt_eval_count") or 0)
            hit = 0
        self.usage["hit"] += int(hit or 0)
        self.usage["miss"] += int(miss or 0)
        self.usage["out"] += int(u.get("completion_tokens")
                                 or u.get("eval_count") or 0)

    def usage_line(self):
        """一行用量小结；没有用量数据时返回空串。"""
        u = self.usage
        prompt = u["hit"] + u["miss"]
        if not prompt and not u["out"]:
            return ""
        rate = (100.0 * u["hit"] / prompt) if prompt else 0.0
        return (f"[用量] 请求 {u['calls']} 次  输出 {u['out']} token  "
                f"缓存命中 {u['hit']}/{prompt} ({rate:.1f}%)  "
                f"未命中 {u['miss']}")

    def close(self):
        """关掉 HTTP 连接池。"""
        try:
            self.session.close()
        except Exception:
            pass

    def _request(self, messages, temperature=None, num_predict=None):
        if self.api_mode:
            return self._request_api(messages, temperature, num_predict)
        return self._request_ollama(messages, temperature, num_predict)

    def _request_ollama(self, messages, temperature, num_predict):
        payload = {
            "model": self.model or config.MODEL,
            "messages": messages,
            "stream": False,
            "keep_alive": getattr(config, "KEEP_ALIVE", "30m"),
            "options": {
                "temperature": (config.TEMPERATURE
                                if temperature is None else temperature),
                "top_p": getattr(config, "TOP_P", 0.9),
                "num_ctx": config.NUM_CTX,
                "num_predict": (config.NUM_PREDICT
                                if num_predict is None else num_predict),
            },
        }
        if config.THINK is False and self._think_supported:
            payload["think"] = False

        resp = self.session.post(self.target["base_url"] or config.OLLAMA_URL,
                                 json=payload,
                                 timeout=self.target["timeout"] or config.TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _request_api(self, messages, temperature, num_predict):
        base = str(self.target["base_url"] or "").rstrip("/")
        if not base:
            raise RuntimeError(
                "未配置服务地址，请先到「设置」里填写（"
                f"当前服务：{self.target['key'] or '未选择'}）")

        if _is_anthropic_base(base):
            return self._request_anthropic(base, messages, temperature,
                                           num_predict)

        url = base + "/chat/completions"

        headers = {"Content-Type": "application/json"}
        # 只有云端 / 自定义服务才带 Key
        key = (getattr(config, "API_KEY", "") or "") \
            if self.target["use_key"] else ""
        if key:
            headers["Authorization"] = f"Bearer {key}"

        payload = {
            "model": (self.model or self.target["model"]
                      or getattr(config, "API_MODEL", "")),
            "messages": messages,
            "stream": False,
            "temperature": (config.TEMPERATURE
                            if temperature is None else temperature),
            "top_p": getattr(config, "TOP_P", 0.9),
            "max_tokens": _api_max_tokens(
                config.NUM_PREDICT if num_predict is None else num_predict),
        }
        # 关掉推理模式
        if getattr(config, "NO_REASONING", True):
            payload["reasoning_effort"] = "none"
        # LM Studio：带 ttl，空闲到点自动卸载模型
        ttl = self._lmstudio_ttl()
        if ttl:
            payload["ttl"] = ttl
        timeout = self.target["timeout"] or config.TIMEOUT

        if self._sched is None:
            resp = self.session.post(url, json=payload, headers=headers,
                                     timeout=timeout)
            if resp.status_code >= 400:
                raise requests.HTTPError(
                    self._http_hint(resp, url, "OpenAI 兼容"),
                    response=resp)
            return resp.json()

        # 调度器路径：拿槽 + 轮换 Key，按结果反馈（429 降并发 / 冷却 Key）
        key, idx = self._sched.acquire()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            resp = self.session.post(url, json=payload, headers=headers,
                                     timeout=timeout)
        except Exception:
            self._sched.release(idx, ok=False)
            raise
        if resp.status_code == 429:
            self._sched.release(idx, ok=False, rate_limited=True,
                                retry_after=_parse_retry_after(resp))
        elif resp.status_code >= 400:
            self._sched.release(idx, ok=False)
        else:
            self._sched.release(idx, ok=True)
        if resp.status_code >= 400:
            raise requests.HTTPError(
                self._http_hint(resp, url, "OpenAI 兼容"),
                response=resp)
        return resp.json()

    def _request_anthropic(self, base, messages, temperature, num_predict):
        """Anthropic Messages 协议：POST {base}/v1/messages。"""
        url = base + "/v1/messages"

        system = "\n".join(m.get("content", "") for m in messages
                           if m.get("role") == "system")
        conv = [m for m in messages if m.get("role") != "system"]

        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        key = (getattr(config, "API_KEY", "") or "") \
            if self.target["use_key"] else ""
        if key:
            headers["x-api-key"] = key

        payload = {
            "model": (self.model or self.target["model"]
                      or getattr(config, "API_MODEL", "")),
            # ★ 与 OpenAI 那条路保持一致：没显式给 num_predict 时用 config 的
            #   （原来直接传 None → _api_max_tokens 当成 0 → 直接取上限，
            #    用户调小的 NUM_PREDICT 在 Anthropic 协议下被无视了）
            "max_tokens": _api_max_tokens(
                config.NUM_PREDICT if num_predict is None else num_predict),
            "messages": conv,
        }
        if system:
            payload["system"] = system
        temp = config.TEMPERATURE if temperature is None else temperature
        if temp is not None:
            payload["temperature"] = temp
        if getattr(config, "NO_REASONING", True):
            payload["thinking"] = {"type": "disabled"}

        timeout = self.target["timeout"] or config.TIMEOUT

        if self._sched is None:
            resp = self.session.post(url, json=payload, headers=headers,
                                     timeout=timeout)
            if resp.status_code >= 400:
                raise requests.HTTPError(
                    self._http_hint(resp, url, "Anthropic 兼容"),
                    response=resp)
            return resp.json()

        key, idx = self._sched.acquire()
        if key:
            headers["x-api-key"] = key
        try:
            resp = self.session.post(url, json=payload, headers=headers,
                                     timeout=timeout)
        except Exception:
            self._sched.release(idx, ok=False)
            raise
        if resp.status_code == 429:
            self._sched.release(idx, ok=False, rate_limited=True,
                                retry_after=_parse_retry_after(resp))
        elif resp.status_code >= 400:
            self._sched.release(idx, ok=False)
        else:
            self._sched.release(idx, ok=True)
        if resp.status_code >= 400:
            raise requests.HTTPError(
                self._http_hint(resp, url, "Anthropic 兼容"),
                response=resp)
        return resp.json()

    @staticmethod
    def _http_hint(resp, url, proto):
        """把 HTTP 错误包装成带排查建议的一句话。"""
        body = (resp.text or "")[:300]
        tip = ""
        if resp.status_code == 404:
            tip = ("；接口路径不存在：请确认「设置 → API 服务地址」用的是"
                   "OpenAI 兼容地址（/v1 结尾亦可）还是 Anthropic 兼容地址"
                   "（/anthropic 结尾），协议不匹配会 404")
        elif resp.status_code == 400 and "max_tokens" in body.lower():
            tip = ("；max_tokens 超出该模型上限，请调小"
                   "「设置 → API 最大生成长度」")
        elif resp.status_code in (401, 403):
            tip = "；密钥无效或无权限，请检查「设置 → API 密钥」"
        return f"API {resp.status_code}（{proto} {url}）：{body}{tip}"

    @staticmethod
    def _content_of(data):
        """兼容 Ollama（message.content）、OpenAI（choices[0]）与 Anthropic（content[]）。"""
        if not isinstance(data, dict):
            return ""
        if data.get("choices"):
            msg = data["choices"][0].get("message") or {}
            return msg.get("content", "") or ""
        if isinstance(data.get("content"), list):        # Anthropic Messages
            return "".join(p.get("text", "") for p in data["content"]
                           if isinstance(p, dict))
        if isinstance(data.get("content"), str):
            return data["content"]
        return (data.get("message") or {}).get("content", "") or ""

    def chat(self, system, user, temperature=None, num_predict=None):
        """带降级重试的一次对话，返回清洗后的纯文本。"""
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
        try:
            data = self._request(messages, temperature, num_predict)
        except requests.HTTPError as e:
            body_text = e.response.text[:300] if e.response is not None else ""
            if (not self.api_mode and self._think_supported and (
                "think" in body_text.lower() or "unknown field" in body_text.lower()
            )):
                log.warning("Ollama 不支持 think 字段，降级重试")
                self._think_supported = False
                data = self._request(messages, temperature, num_predict)
            else:
                raise

        self._record_usage(data)

        # 部分版本把思考内容单独放在 thinking 字段，正文已分离，这里只清洗正文
        content = self._content_of(data)
        # ★ 本地服务（KoboldCpp / LM Studio / 自定义）不认 think 参数，
        #   思考输出会吃掉生成预算导致译文截断，这里提示一次怎么关。
        if "<think" in content:
            log.warning(
                "模型输出了思考内容（<think>）——生成预算被推理过程占用，"
                "译文容易被截断。请在服务端关闭推理模式：%s", _nothink_hint())
        return _strip_noise(content)

    # ---------- 翻译 ----------
    def _system_prompt(self, section=None):
        """system 提示词：模板外置（prompts/ 可覆盖）+ 可选 <why> 思考块。

        section: 可选，当前文件的文本类别（见 cat_prompts.section_for）。
            非空且 prompts/categories/<SECTION>.txt 存在时，把类别段**追加在
            末尾**；判不出 / 文件缺失 → 与改动前逐字节一致。

        ★ 共享前缀仍然稳定：通用规则永远在最前面且逐字节不变，类别段只加在
          它之后，所以 section 相同的批次前缀完全一致（KV 缓存照旧复用），
          section 不同也只是在这个稳定前缀之后分叉。注意本函数每批都重建，
          但重建出的字符串对同一 section 是同一个值。
        """
        text = load_template("system_translate_jsonline.txt",
                             SYSTEM_PROMPT_JSONLINE)
        text = (text.replace("{src}", config.SOURCE_LANG)
                    .replace("{tgt}", config.TARGET_LANG))
        if getattr(config, "THINKING_BLOCK", False):
            text = text.rstrip() + "\n\n" + load_template(
                "thinking.txt", THINKING_BLOCK).rstrip()
        if section:
            # ★ 反向 import 会成环（cat_prompts 依赖本模块），只能延迟导入
            try:
                import cat_prompts as CP
                block = CP.category_block(section)
            except Exception as e:
                log.debug("类别提示词装配失败（按无类别段处理）：%s", e)
                block = ""
            if block:
                text = text.rstrip() + "\n\n" + block.rstrip()
        return text

    def translate_batch(self, items, term_pairs=None, section=None):
        """
        items:      [(idx, safe_text), ...]
        term_pairs: 可选 [(原文, 译文), ...]，作为 prompt 里的术语表
        section:    可选，当前文件的文本类别名（如 "SPECIES_NAMES"）——
                   有 prompts/categories/<SECTION>.txt 就追加到 system 末尾
        返回:       {idx: translation}
        """
        if not items:
            return {}

        terms_block = _format_terms_block(term_pairs)

        # 输出固定 JSON：每行一条 {"id":N,"text":"..."}
        body = "\n".join(
            '{"id":%d,"text":%s}' % (i, _json_str(t))
            for i, t in items)
        template = load_template("user_translate_jsonline.txt",
                                 _USER_TEMPLATE_JSONLINE)

        user_msg = (template
                    .replace("{terms_block}", terms_block)
                    .replace("{tgt}", config.TARGET_LANG)
                    .replace("{body}", body))

        system = self._system_prompt(section)

        raw = self.chat(system, user_msg)

        translations, _ = _parse_model_output(
            raw, expected={i for i, _t in items})

        if not translations and len(items) == 1:
            # ★ 单条批次不按编号过滤重解一次：小模型单条重试时习惯性写死
            #   {"id":0,...}，真实编号会被 expected 过滤掉，译文被整条丢弃。
            #   批里只有一条时 id 写成什么都只可能是它，不存在串行风险；
            #   模型吐的 id 键重映射回本批条目的真实编号。
            translations, _ = _parse_model_output(raw, expected=None)
            translations = {items[0][0]: v for v in translations.values()}

        if not translations:
            # ★ 兜底：模型完全不吐编号时，按「每条源文本的行数」把响应切回来
            #   （Sakura 式对齐）。整批行数正好对得上才接受，否则交给上层
            #   缩块重试 —— 宁可靠重试，也不瞎猜哪一行属于哪一条。
            aligned = _decode_by_line_count(raw, items)
            if aligned:
                log.info("按行数对齐解码成功：%d 条", len(aligned))
                translations = aligned

        return translations

    # ---------- 中文润色 ----------
    def polish_batch(self, items, section=None):
        """
        items: [(idx, safe_text), ...]  safe_text 为已保护控制码的中文译文
               也接受 [(idx, safe_text, safe_src), ...]：
               第三项是原文（已保护），会作为末尾的【参考原文】交给模型比对。
        section: 可选，当前文件的文本类别名 —— 有类别提示词时，
               把它的**风格段**（【本文本类型】+【翻译方法】，见
               cat_prompts.style_block 的取舍说明）追加到 system 末尾。
        返回:  {idx: polished}
        """
        if not items:
            return {}

        body_lines, ref_lines = [], []
        for it in items:
            idx = it[0]
            text = it[1]
            src = it[2] if len(it) > 2 else None
            body_lines.append(f"<{idx}>{text}")
            if src:
                ref_lines.append(f"[{idx}]{src}")

        body = "\n".join(body_lines)
        if ref_lines:
            # ★ 原文放末尾当参考提示词：只用于比对原意，不参与输出
            body += ("\n\n【参考原文】编号与上面一一对应，仅供比对原意、检查漏译；"
                     "不要输出这一段，也不要照抄其中的控制码。\n"
                     + "\n".join(ref_lines))

        user_msg = load_template("user_polish.txt",
                                 _POLISH_TEMPLATE).replace("{body}", body)
        system = load_template("system_polish.txt", POLISH_SYSTEM_PROMPT)
        system = system.replace("{tgt}", config.TARGET_LANG)
        if section:
            # ★ 同 _system_prompt：类别段只追加在末尾，共享前缀保持稳定；
            #   反向 import 成环，故延迟导入。
            try:
                import cat_prompts as CP
                block = CP.style_block(section)
            except Exception as e:
                log.debug("润色类别段装配失败（按无类别段处理）：%s", e)
                block = ""
            if block:
                system = system.rstrip() + "\n\n" + block.rstrip()

        raw = self.chat(
            system, user_msg,
            temperature=getattr(config, "POLISH_TEMPERATURE", 0.35),
        )
        translations, _ = _parse_model_output(
            raw, expected={it[0] for it in items})
        return translations


# ================================================================
# 带重试的封装
# ================================================================
def translate_with_retry(client, batch, depth=0,
                         term_pairs=None, section=None):
    """
    batch:      [(idx, safe_text), ...]
    term_pairs: 可选 [(原文, 译文), ...]，作为 prompt 里的术语表
    section:    可选，当前文件的文本类别名（透传给 translate_batch）
    返回:       {idx: translation}

    ★ 重试策略（借鉴 LinguaGacha）：整批失败 → 原样重试 BATCH_RETRIES 次
      → 按 2^depth 几何缩块（2 → 4 → 8 → 16 块）逐级重试，
      比逐半拆更快触底、又比直接单条省请求；depth 到顶后逐条重试，
      单条也失败才放弃（调用方记「翻译失败」进报告）。
    """
    if not batch:
        return {}

    last_err = None
    for attempt in range(config.BATCH_RETRIES + 1):
        try:
            return client.translate_batch(
                batch, term_pairs=term_pairs, section=section,
            )
        except Exception as e:
            last_err = e
            log.warning("整批请求失败（第 %d/%d 次）：%s",
                        attempt + 1, config.BATCH_RETRIES + 1, e)
            time.sleep(min(2.0 * (attempt + 1), 6.0))

    if len(batch) > 1 and depth < 4:
        parts = 2 ** (depth + 1)          # 几何缩块：2 → 4 → 8 → 16
        size = max(1, -(-len(batch) // parts))   # 向上取整
        log.info("整批失败，按 %d 块（每块约 %d 条）缩块重试",
                 parts, size)
        result = {}
        for i in range(0, len(batch), size):
            chunk = batch[i:i + size]
            r = translate_with_retry(client, chunk, depth + 1,
                                     term_pairs, section)
            result.update(r)
        return result

    log.error("单条也失败，放弃该批（最后错误：%s）", last_err)
    return {}


def polish_with_retry(client, batch, depth=0, section=None):
    """润色的重试封装（逻辑与翻译一致，但不带术语表）。"""
    if not batch:
        return {}

    retries = int(getattr(config, "BATCH_RETRIES", 2) or 0)
    last_err = None
    for attempt in range(retries + 1):
        try:
            return client.polish_batch(batch, section=section)
        except Exception as e:
            last_err = e
            log.warning("润色整批失败（第 %d/%d 次）：%s",
                        attempt + 1, retries + 1, e)
            time.sleep(min(2.0 * (attempt + 1), 6.0))

    if len(batch) > 1 and depth < 4:
        parts = 2 ** (depth + 1)          # 几何缩块（同翻译）
        size = max(1, -(-len(batch) // parts))
        log.info("润色整批失败，按 %d 块（每块约 %d 条）缩块重试",
                 parts, size)
        result = {}
        for i in range(0, len(batch), size):
            chunk = batch[i:i + size]
            r = polish_with_retry(client, chunk, depth + 1, section)
            result.update(r)
        return result

    log.error("润色单条也失败，放弃该批（最后错误：%s）", last_err)
    return {}
