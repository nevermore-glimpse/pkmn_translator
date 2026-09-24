# -*- coding: utf-8 -*-
"""
Ollama 客户端 + 批量翻译 / 中文润色。
  · 翻译与术语提取一次完成（术语以 @@T: 行内联返回）
  · 整批失败 → 重试 → 拆分两半 → 递归
  · 无推理模式（think=False），旧版 Ollama 自动降级
"""
import re
import time

import requests

import config
from logger import get_logger

log = get_logger("translator")


# ================================================================
# 提示词
# ================================================================
SYSTEM_PROMPT = r"""你是专业游戏本地化译者，把{src}游戏文本翻译成{tgt}。

【输出】
每条两行：
<编号>译文
<编号>@@T:原文术语=译文术语|...
不要解释，不要空行，不要markdown，不要注释；原文有引号才加引号。

【占位符】
@0@ @1@等占位符必须原样保留：数量、位置、数字不变，不翻译 @ 和数字，不新增。
每句话中的占位符都不能丢；不同句子的占位符重复出现也完整保留。
短句（只有几个字）也要保留占位符，绝不要把它当成可翻译的词翻掉。
输出前请先核对：译文里 @N@（或 ⟦N⟧）的数量与输入完全一致，再提交。

【翻译】
准确第一：语义、语气、人物性格随人物变化
生动第二：对话、感叹、拟声词可有画面感，可用成语/口语，但不改原意。
简洁第三：台词能短则短，但不失准确。

【术语表】
用户提供则必须遵守；遇到表内词，无论大小写/数量，都用表内中文。

【术语提取】
每条译文后紧跟一行：
<编号>@@T:原文术语1=译文术语1|原文术语2=译文术语2
无专有名词写：<编号>@@T:
只能提取以下名词：训练家/NPC、宝可梦、地名/城镇/道路/地区、道具、招式、特性、组织/队伍、建筑。
绝不能提取以下词：代词、冠词、介词、连词、助动词、纯数字、时间、货币、已是中文、整个句子等。
编号一致，每行只有一个 @@T: 前缀。

【示例】
输入：
<0>¡Hola!Enfermera\n¿Cómo estás?
输出：
<0>你好！护士\n你怎么样？
<0>@@T:Enfermera=护士
"""

_USER_TEMPLATE = r"""翻译下列每行，编号对应。每行格式：<编号>原文。
{terms_block}
要求：
1. 每条输出两行：
<编号>译文
<编号>@@T:原文术语1=译文术语1|原文术语2=译文术语2...
2. 无术语输出<编号>@@T:
3. 原文中@0@ @1@ @2@ @3@等占位符在译文里必须原样保留，位置、数量不变。
4. 术语表必须遵守，表内词无论大小写都用表中中文。
5. 不加解释、不漏行、不多输出、不加注释，严格遵循全部规则。
{body}
"""

# ---------------- 中文润色 ----------------
POLISH_SYSTEM_PROMPT = r"""你是资深中文游戏本地化润色编辑。
我会给你若干条已经翻成中文的游戏台词，请你逐条润色成{tgt}。

【输出】
每条一行：
<编号>润色后文本
不要解释、不要空行、不要 markdown、不要编号以外的任何内容。

【必须遵守】
1. 原样保留所有占位符（@0@ @1@ ⟦0⟧ 等）与控制码，数量、位置、顺序都不能变。
2. 原样保留标点与换行控制码，不要增删；\\n 前后不要新增逗号、句号等标点。
3. 不改变原意、不改变句子数量与语序，不新增剧情信息。
4. 长度与原文基本相当，不要扩写成长句，也不要删掉内容。
5. 只做语言层面的优化：让台词更自然、口语化、符合说话人身份与情绪；
   修正生硬直译、语序别扭、量词/代词误用、重复啰嗦。
6. 已经是自然流畅的中文时，原样输出即可。
"""

_POLISH_TEMPLATE = r"""润色下列每行，编号对应。每行格式：<编号>中文台词。
{body}
"""


# ================================================================
# 术语行解析
# ================================================================
_TERMS_PREFIX = "@@T:"

# 模型偶尔包一层 markdown 代码围栏
_FENCE_RE = re.compile(r'^\s*```[a-zA-Z]*\s*$')

# <think> ... <think> / <think> ... </think>
_THINK_RE = re.compile(r'<think\b[^>]*>.*?(?:</think>|<think>|$)', re.DOTALL)


def _strip_noise(raw):
    """去掉思考块、代码围栏、首尾空白。"""
    if not raw:
        return ""
    raw = _THINK_RE.sub("", raw)
    lines = []
    for line in raw.splitlines():
        if _FENCE_RE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


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


def _format_terms_block(term_pairs, limit=None):
    """
    term_pairs: [(原文, 译文), ...]
    返回格式化好的术语表块，或空串。
    """
    if not term_pairs:
        return ""

    if limit is None:
        limit = getattr(config, "MAX_TERMS_IN_PROMPT", 80)

    # 按原文长度降序（长词优先展示，模型更容易记住）
    items = sorted(term_pairs, key=lambda x: -len(x[0]))
    items = items[:limit]

    lines = ["【术语表 —— 遇到这些词无论大小写都必须使用以下译文】"]
    for src, dst in items:
        lines.append(f"{src} = {dst}")
    lines.append("")     # 尾空行，与下面 {body} 隔开
    return "\n".join(lines) + "\n"


def _parse_model_output(raw):
    """
    逐行解析模型输出。
    返回 (translations, terms_map)：
      translations: {idx: text}
      terms_map:    {idx: {src: dst}}

    ★ 同一编号重复出现时保留「第一条非空」结果：
      模型偶尔先输出草稿再输出终稿，取第一条更稳。
    """
    translations = {}
    terms_map = {}

    if not raw:
        return translations, terms_map

    for line in raw.splitlines():
        m = re.match(r"<\s*(\d+)\s*>(.*)", line)
        if not m:
            continue
        idx = int(m.group(1))
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

    return translations, terms_map


# ================================================================
# Ollama 客户端
# ================================================================
def _is_api_mode():
    return str(getattr(config, "TRANSLATE_MODE", "ollama")).lower() == "api"


class OllamaClient:
    """翻译客户端：本地 Ollama 与云端 OpenAI 兼容 API 共用同一套接口。"""

    def __init__(self, model=None):
        self.session = requests.Session()
        self.api_mode = _is_api_mode()
        if model:
            self.model = model
        else:
            self.model = (config.API_MODEL if self.api_mode
                          else config.MODEL)
        self._think_supported = True
        log.info("翻译客户端初始化  模式=%s  模型=%s",
                 "云端API" if self.api_mode else "本地Ollama", self.model)

    # ---------- 底层 ----------
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

        resp = self.session.post(config.OLLAMA_URL, json=payload,
                                 timeout=config.TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _request_api(self, messages, temperature, num_predict):
        base = str(getattr(config, "API_BASE_URL", "") or "").rstrip("/")
        if not base:
            raise RuntimeError("未配置 API_BASE_URL，请先到「设置」里填写")
        url = base + "/chat/completions"

        headers = {"Content-Type": "application/json"}
        key = getattr(config, "API_KEY", "") or ""
        if key:
            headers["Authorization"] = f"Bearer {key}"

        payload = {
            "model": self.model or getattr(config, "API_MODEL", ""),
            "messages": messages,
            "stream": False,
            "temperature": (config.TEMPERATURE
                            if temperature is None else temperature),
            "top_p": getattr(config, "TOP_P", 0.9),
            "max_tokens": (config.NUM_PREDICT
                           if num_predict is None else num_predict),
        }
        timeout = getattr(config, "API_TIMEOUT", 120) or config.TIMEOUT

        resp = self.session.post(url, json=payload, headers=headers,
                                 timeout=timeout)
        if resp.status_code >= 400:
            raise requests.HTTPError(
                f"API {resp.status_code}: {resp.text[:300]}", response=resp)
        return resp.json()

    @staticmethod
    def _content_of(data):
        """兼容 Ollama（message.content）与 OpenAI（choices[0].message）。"""
        if not isinstance(data, dict):
            return ""
        if data.get("choices"):
            msg = data["choices"][0].get("message") or {}
            return msg.get("content", "") or ""
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

        # 部分版本把思考内容单独放在 thinking 字段，正文已分离，这里只清洗正文
        return _strip_noise(self._content_of(data))

    # ---------- 翻译 ----------
    def _system_prompt(self):
        return (SYSTEM_PROMPT
                .replace("{src}", config.SOURCE_LANG)
                .replace("{tgt}", config.TARGET_LANG))

    def translate_batch(self, items, terms_out=None, term_pairs=None,
                        extra_instruction=None):
        """
        items:      [(idx, safe_text), ...]
        terms_out:  可选 dict，被填充为 {idx: {src: dst}}
        term_pairs: 可选 [(原文, 译文), ...]，作为 prompt 里的术语表
        extra_instruction: 可选，追加到用户消息末尾的強化指令
                           （如占位符丢失时提醒模型必须保留 @N@）
        返回:       {idx: translation}
        """
        if not items:
            return {}

        body = "\n".join(f"<{i}>{t}" for i, t in items)
        terms_block = _format_terms_block(term_pairs)
        user_msg = (_USER_TEMPLATE
                    .replace("{terms_block}", terms_block)
                    .replace("{tgt}", config.TARGET_LANG)
                    .replace("{body}", body))
        if extra_instruction:
            user_msg = user_msg.rstrip() + "\n\n" + extra_instruction

        raw = self.chat(self._system_prompt(), user_msg)

        translations, terms_map = _parse_model_output(raw)

        if terms_out is not None:
            for idx, terms in terms_map.items():
                if terms:
                    terms_out.setdefault(idx, {}).update(terms)

        return translations

    # ---------- 中文润色 ----------
    def polish_batch(self, items):
        """
        items: [(idx, safe_text), ...]  safe_text 为已保护控制码的中文译文
        返回:  {idx: polished}
        """
        if not items:
            return {}

        body = "\n".join(f"<{i}>{t}" for i, t in items)
        user_msg = _POLISH_TEMPLATE.replace("{body}", body)
        system = POLISH_SYSTEM_PROMPT.replace("{tgt}", config.TARGET_LANG)

        raw = self.chat(
            system, user_msg,
            temperature=getattr(config, "POLISH_TEMPERATURE", 0.35),
        )
        translations, _ = _parse_model_output(raw)
        return translations


# ================================================================
# 带重试的封装
# ================================================================
def translate_with_retry(client, batch, depth=0,
                         terms_out=None, term_pairs=None,
                         extra_instruction=None):
    """
    batch:      [(idx, safe_text), ...]
    terms_out:  可选 dict，被填充为 {idx: {src: dst}}
    term_pairs: 可选 [(原文, 译文), ...]，作为 prompt 里的术语表
    extra_instruction: 占位符丢失等场景下的強化指令（透传给模型）
    返回:       {idx: translation}
    """
    if not batch:
        return {}

    last_err = None
    for attempt in range(config.BATCH_RETRIES + 1):
        try:
            return client.translate_batch(
                batch, terms_out=terms_out, term_pairs=term_pairs,
                extra_instruction=extra_instruction,
            )
        except Exception as e:
            last_err = e
            log.warning("整批请求失败（第 %d/%d 次）：%s",
                        attempt + 1, config.BATCH_RETRIES + 1, e)
            time.sleep(min(2.0 * (attempt + 1), 6.0))

    if len(batch) > 1 and depth < 4:
        mid = len(batch) // 2
        log.info("整批失败，拆分为 %d + %d 重试", mid, len(batch) - mid)
        r1 = translate_with_retry(client, batch[:mid], depth + 1,
                                  terms_out, term_pairs, extra_instruction)
        r2 = translate_with_retry(client, batch[mid:], depth + 1,
                                  terms_out, term_pairs, extra_instruction)
        r1.update(r2)
        return r1

    log.error("单条也失败，放弃该批（最后错误：%s）", last_err)
    return {}


def polish_with_retry(client, batch, depth=0):
    """润色的重试封装（逻辑与翻译一致，但不带术语表）。"""
    if not batch:
        return {}

    last_err = None
    for attempt in range(getattr(config, "BATCH_RETRIES", 2) + 1):
        try:
            return client.polish_batch(batch)
        except Exception as e:
            last_err = e
            log.warning("润色整批失败（第 %d/%d 次）：%s",
                        attempt + 1, config.BATCH_RETRIES + 1, e)
            time.sleep(min(2.0 * (attempt + 1), 6.0))

    if len(batch) > 1 and depth < 4:
        mid = len(batch) // 2
        r1 = polish_with_retry(client, batch[:mid], depth + 1)
        r2 = polish_with_retry(client, batch[mid:], depth + 1)
        r1.update(r2)
        return r1

    log.error("润色单条也失败，放弃该批（最后错误：%s）", last_err)
    return {}
