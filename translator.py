# -*- coding: utf-8 -*-
"""
Ollama 客户端 + 批量翻译。
   · 整批失败 → 重试 → 拆分两半 → 递归
   · 无推理模式（think=False），旧版 Ollama 自动降级
"""
import re
import time

import requests

import config
from logger import get_logger

log = get_logger("translator")


SYSTEM_PROMPT = r"""你是一个专业的游戏本地化译者，负责把{src}的宝可梦同人游戏文本翻译成{tgt}。

严格遵守以下规则：
1. 只输出译文。不要解释，不要加引号，不要加任何前缀。
2. 输入格式为 <编号>原文，你必须输出 <编号>译文，编号一一对应。
3. 绝对不要漏掉任何一行，也不要多输出任何一行。

【占位符 —— 最重要，必须原样保留】
4. 形如 @0@ @1@ @2@ 的符号是游戏控制码占位符（两个 @ 中间夹一个数字）。
5. 它们是游戏指令（如换行、等待、说话人）的替身，翻译后必须一个不少地保留。
6. 保留位置：如果原文是 "Hello, @0@! @1@How are you?"，
   译文必须是 "你好，@0@！@1@你好吗？" —— 占位符的数量和相对位置完全一致。
7. 不要翻译 @ 和数字本身，不要删，不要改数字，不要换成其它括号。

【翻译】
8. 必须完整翻译每一条，严禁跳过任何词汇。
9. 宝可梦、道具、技能、特性名称使用官方中文译名。
10. 保持原文语气。西语标点 ¡ ¿ 可省略。
11. 不要截断、不要省略、不要扩写。
"""

_USER_TEMPLATE = r"""请把下面每一行翻译成{tgt}。每行格式为 <编号>原文。
输出要求：
1. 每行输出 <编号>译文，一行一条，编号一一对应。
2. 不要输出任何解释，不要加多余空行。
3. @0@ @1@ 这类占位符（两个 @ 夹数字）必须原样保留，数量和位置与原文一致。
4. 不要漏行、不要多输出。

{body}
"""


class OllamaClient:
    def __init__(self):
        self.session = requests.Session()
        self.system_prompt = (SYSTEM_PROMPT
                              .replace("{src}", config.SOURCE_LANG)
                              .replace("{tgt}", config.TARGET_LANG))
        self._think_supported = True
        log.info("Ollama 客户端初始化  模型=%s  地址=%s", config.MODEL, config.OLLAMA_URL)

    def _request(self, messages):
        payload = {
            "model": config.MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": config.TEMPERATURE,
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

    def translate_batch(self, items):
        """
        items: [(idx, safe_text), ...]
        返回: {idx: translation}
        """
        if not items:
            return {}

        body = "\n".join(f"<{i}>{t}" for i, t in items)
        user_msg = (_USER_TEMPLATE
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

        result = {}
        for m in re.finditer(r"<\s*(\d+)\s*>(.*?)(?=<\s*\d+\s*>|$)",
                             raw, re.DOTALL):
            idx = int(m.group(1))
            txt = m.group(2).strip()
            for prefix in ("译文：", "翻译：", "Translation:", "译："):
                if txt.startswith(prefix):
                    txt = txt[len(prefix):].strip()
            result[idx] = txt
        return result


def translate_with_retry(client, batch, depth=0):
    """
    batch: [(idx, safe_text), ...]
    返回: {idx: translation}
    """
    if not batch:
        return {}

    last_err = None
    for attempt in range(config.BATCH_RETRIES + 1):
        try:
            result = client.translate_batch(batch)
            return result
        except Exception as e:
            last_err = e
            log.warning("整批请求失败（第 %d/%d 次）：%s",
                        attempt + 1, config.BATCH_RETRIES + 1, e)
            time.sleep(min(2.0 * (attempt + 1), 6.0))

    if len(batch) > 1 and depth < 4:
        mid = len(batch) // 2
        log.info("整批失败，拆分为 %d + %d 重试", mid, len(batch) - mid)
        r1 = translate_with_retry(client, batch[:mid], depth + 1)
        r2 = translate_with_retry(client, batch[mid:], depth + 1)
        r1.update(r2)
        return r1

    log.error("单条也失败，放弃该批（最后错误：%s）", last_err)
    return {}