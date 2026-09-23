# -*- coding: utf-8 -*-
"""
Ollama 客户端 + 批量翻译。
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


SYSTEM_PROMPT = r"""你是专业游戏本地化译者，把游戏文本翻译成中文。

【输出】
每条两行：
<编号>译文
<编号>@@T:原文术语=译文术语|...
不要解释，不要空行，不要markdown，不要注释；原文有引号才加引号。

【占位符】
@0@ @1@等占位符必须原样保留：数量、位置、数字不变，不翻译 @ 和数字，不新增。
每句话中的占位符都不能丢；不同句子的占位符重复出现也完整保留。

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
<编号>@@T:原文术语=译文术语|...
2. 无术语输出 <编号>@@T:
3. 原文中@0@ @1@ @2@ @3@等占位符在译文里必须原样保留，位置、数量不变。
4. 术语表必须遵守，表内词无论大小写都用表中中文。
5. 不加解释、不漏行、不多输出、不加注释，严格遵循全部规则。
{body}
"""


# ================================================================
# 术语行解析
# ================================================================
_TERMS_PREFIX = "@@T:"


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
        if k and v and k != v:
            result[k] = v
    return result

MAX_TERMS_IN_PROMPT = 80     # prompt 里最多注入多少条术语


def _format_terms_block(term_pairs):
    """
    term_pairs: [(原文, 译文), ...]
    返回格式化好的术语表块，或空串。
    """
    if not term_pairs:
        return ""

    # 按原文长度降序（长词优先展示，模型更容易记住）
    items = sorted(term_pairs, key=lambda x: -len(x[0]))
    items = items[:MAX_TERMS_IN_PROMPT]

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

        translations[idx] = content

    return translations, terms_map


# ================================================================
# Ollama 客户端
# ================================================================
class OllamaClient:
    def __init__(self):
        self.session = requests.Session()
        self.system_prompt = (SYSTEM_PROMPT
                              .replace("{src}", config.SOURCE_LANG)
                              .replace("{tgt}", config.TARGET_LANG))
        self._think_supported = True
        log.info("Ollama 客户端初始化  模型=%s  地址=%s",
                 config.MODEL, config.OLLAMA_URL)

    def _request(self, messages):
        payload = {
            "model": config.MODEL,
            "messages": messages,
            "stream": False,
            "keep_alive": getattr(config, "KEEP_ALIVE", "30m"),
            "options": {
                "temperature": config.TEMPERATURE,
                "top_p": getattr(config, "TOP_P", 0.9),
                "num_ctx": config.NUM_CTX,
                "num_predict": config.NUM_PREDICT,
            },
        }
        if config.THINK is False and self._think_supported:
            payload["think"] = False

        resp = self.session.post(config.OLLAMA_URL, json=payload,
                                 timeout=config.TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def translate_batch(self, items, terms_out=None, term_pairs=None):
        """
        items:      [(idx, safe_text), ...]
        terms_out:  可选 dict，被填充为 {idx: {src: dst}}
        term_pairs: 可选 [(原文, 译文), ...]，作为 prompt 里的术语表
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

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": user_msg},
        ]

        try:
            data = self._request(messages)
        except requests.HTTPError as e:
            body_text = e.response.text[:300] if e.response is not None else ""
            if self._think_supported and (
                "think" in body_text.lower() or "unknown field" in body_text.lower()
            ):
                log.warning("Ollama 不支持 think 字段，降级重试")
                self._think_supported = False
                data = self._request(messages)
            else:
                raise

        raw = (data.get("message") or {}).get("content", "")
        raw = re.sub(r" thinking.*?", "", raw, flags=re.DOTALL)

        translations, terms_map = _parse_model_output(raw)

        if terms_out is not None:
            for idx, terms in terms_map.items():
                if terms:
                    terms_out.setdefault(idx, {}).update(terms)

        return translations


# ================================================================
# 带重试的封装
# ================================================================
def translate_with_retry(client, batch, depth=0,
                         terms_out=None, term_pairs=None):
    """
    batch:      [(idx, safe_text), ...]
    terms_out:  可选 dict，被填充为 {idx: {src: dst}}
    term_pairs: 可选 [(原文, 译文), ...]，作为 prompt 里的术语表
    返回:       {idx: translation}
    """
    if not batch:
        return {}

    last_err = None
    for attempt in range(config.BATCH_RETRIES + 1):
        try:
            return client.translate_batch(
                batch, terms_out=terms_out, term_pairs=term_pairs
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
                                  terms_out, term_pairs)
        r2 = translate_with_retry(client, batch[mid:], depth + 1,
                                  terms_out, term_pairs)
        r1.update(r2)
        return r1

    log.error("单条也失败，放弃该批（最后错误：%s）", last_err)
    return {}