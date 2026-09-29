# -*- coding: utf-8 -*-
"""
本地模型服务提供商（菜单 9）。

统一管理 Ollama / llama.cpp / LM Studio / 自定义 OpenAI 兼容服务：
  · 协议差异：Ollama 走 /api/chat + /api/tags；其余走 OpenAI 兼容 /v1
  · 一键切换：切换后自动改写 TRANSLATE_MODE、服务地址与推荐参数
  · 模型目录：参数量 / 上下文 / 体积 / 量化 / 跨提供商模型名映射
  · 一键部署：调用各提供商自己的拉取命令，输出实时打进日志
  · 切换适配：列出「同一模型换提供商后要改什么」，能自动改的一键改掉

★ 本模块只改配置与执行本地命令，不碰翻译核心逻辑。
"""
import os
import re
import shutil
import subprocess
import urllib.parse

import config

try:
    import requests
except Exception:      # 缺 requests 时本模块仍可被导入，只是探测/部署不可用
    requests = None


# ================================================================
# 提供商注册表
# ================================================================
# protocol:
#   "ollama"  —— Ollama 原生协议（/api/chat、/api/tags），支持 think / keep_alive / num_ctx
#   "openai"  —— OpenAI 兼容（/v1/chat/completions、/v1/models），本地服务一般不校验密钥
#
# url_config: 该提供商服务地址落在 config 里的哪个键上。
#             Ollama 存的是完整的 chat 端点，其余存的是 /v1 根地址。
PROVIDERS = {
    "ollama": {
        "key":         "ollama",
        "label":       "Ollama",
        "protocol":    "ollama",
        "url_config":  "OLLAMA_URL",
        "default_url": "http://localhost:11434/api/chat",
        "model_config": "MODEL",
        "default_model": "qwen2.5:14b",
        "think":       False,     # 支持 think=false 关掉思考过程
        "keep_alive":  False,     # 支持模型驻留显存
        "num_ctx":     True,     # 上下文由请求参数决定
        "install_url": "https://ollama.com/download",
        "home":        "https://ollama.com",
        "summary":     "最省事，模型一条命令拉取，参数每次请求都能带。",
        # ★ 关掉推理/思考的办法（每条请求都带 think=false 就够）
        "nothink":     "菜单 10 取消勾选「推理模式 think」，请求里会带 think=false。",
        "pull":        "ollama pull {model}",
    },
    "llamacpp": {
        "key":         "llamacpp",
        "label":       "llama.cpp",
        "protocol":    "openai",
        "url_config":  "LLAMACPP_URL",
        "default_url": "http://127.0.0.1:8080/v1",
        "model_config": "API_MODEL",
        "default_model": "qwen3.5-4b",
        "think":       False,
        "keep_alive":  False,
        "num_ctx":     False,    # 上下文在启动时用 -c/--ctx-size 定死
        "install_url": "https://github.com/ggml-org/llama.cpp/releases",
        "home":        "https://github.com/ggml-org/llama.cpp",
        "summary":     "官方 llama-server：一个进程一个 GGUF，参数全在启动命令里。",
        # ★ 实测：--reasoning off 会直接让 chat template 不启用思考
        #   （启动日志出现 "chat template, thinking = 0"）。
        "nothink":     ("启动时加 --reasoning off（等价 --reasoning-budget 0）。"),
        # llama.cpp 没有模型仓库，必须自己指定 GGUF 文件路径
        "pull":        None,
    },
    "lmstudio": {
        "key":         "lmstudio",
        "label":       "LM Studio",
        "protocol":    "openai",
        "url_config":  "LMSTUDIO_URL",
        "default_url": "http://localhost:1234/v1",
        "model_config": "API_MODEL",
        "default_model": "qwen2.5-14b-instruct",
        "think":       False,
        "keep_alive":  False,
        "num_ctx":     False,    # 上下文在 LM Studio 界面里加载模型时设置
        "install_url": "https://lmstudio.ai/download",
        "home":        "https://lmstudio.ai",
        "summary":     "图形界面管模型，改上下文/卸载模型都要在界面里点。",
        "nothink":     "加载模型时把 Reasoning 设为 Off（不是 Auto）。",
        "pull":        "lms get {model}",
    },
    "custom": {
        "key":         "custom",
        "label":       "自定义 OpenAI 兼容",
        "protocol":    "openai",
        "url_config":  "CUSTOM_OPENAI_URL",
        "default_url": "http://localhost:8080/v1",
        "model_config": "API_MODEL",
        "default_model": "",
        "think":       False,
        "keep_alive":  False,
        "num_ctx":     False,
        "install_url": "",
        "home":        "",
        "summary":     "指向任意 OpenAI 兼容服务（llama.cpp server / vLLM / 本地网关）。",
        "nothink":     ("看服务端支不支持 reasoning_effort / "
                        "chat_template_kwargs，或直接在服务端关掉。"),
        "pull":        None,
    },
}

# 侧边栏 / 下拉框里的显示顺序
ORDER = ["ollama", "llamacpp", "lmstudio", "custom"]

# 每个提供商的推荐参数（与 settings.MODE_PRESETS 同思路，但按本地服务器特点细分）
PRESETS = {
    "ollama": {
        "TIMEOUT":             600,
        "NUM_CTX":             8192,
        "NUM_PREDICT":         2048,
        "BATCH_SIZE":          15,
        "MAX_BATCH_CHARS":     2048,
        "MAX_TERMS_IN_PROMPT": 80,
        "KEEP_ALIVE":          "30m",
    },
    "llamacpp": {
        # llama-server 一次只服务一个模型、上下文固定，批次给小一点更稳
        "TIMEOUT":             600,
        "NUM_CTX":             8192,
        "NUM_PREDICT":         2048,
        "BATCH_SIZE":          15,
        "MAX_BATCH_CHARS":     2048,
        "MAX_TERMS_IN_PROMPT": 80,
        "API_TIMEOUT":         600,
    },
    "lmstudio": {
        "TIMEOUT":             600,
        "NUM_CTX":             8192,
        "NUM_PREDICT":         2048,
        "BATCH_SIZE":          15,
        "MAX_BATCH_CHARS":     2048,
        "MAX_TERMS_IN_PROMPT": 80,
        "API_TIMEOUT":         600,
    },
    "custom": {
        "TIMEOUT":             600,
        "NUM_CTX":             8192,
        "NUM_PREDICT":         2048,
        "BATCH_SIZE":          10,
        "MAX_BATCH_CHARS":     1800,
        "MAX_TERMS_IN_PROMPT": 70,
        "API_TIMEOUT":         600,
    },
}

PRESET_LABELS = {
    "TIMEOUT":             "请求超时（秒）",
    "API_TIMEOUT":         "API 超时（秒）",
    "NUM_CTX":             "上下文长度",
    "NUM_PREDICT":         "最大生成长度",
    "BATCH_SIZE":          "每批条数",
    "MAX_BATCH_CHARS":     "单批字符上限",
    "MAX_TERMS_IN_PROMPT": "术语上限（条）",
    "KEEP_ALIVE":          "模型驻留时长",
    "TRANSLATE_MODE":      "翻译模式",
    "PROVIDER":            "服务提供商",
    "MODEL":               "Ollama 模型名",
    "API_MODEL":           "API 模型名",
    "API_BASE_URL":        "API 服务地址",
    "THINK":               "推理模式",
}


# ================================================================
# 模型目录（跨提供商共用一套「模型族」，各提供商用自己的标识）
# ================================================================
# size    —— 该量化下大致的磁盘占用（GB）
# ctx     —— 该模型常见可用上下文
# think   —— 模型本身会不会输出思考过程
MODEL_FAMILIES = [
    {
        "family": "qwen3.5-4b", "display": "Qwen3.5 4B",
        "params": "4B", "ctx": 262144, "size": 2.4, "quant": "Q3_K_S",
        "think": True, "level": "推荐",
        "note": ("实测最好用的一档：译文自然、控制码保留、术语命中。"
                 "默认会输出思考过程，务必关掉推理模式（详见切换适配栏）。"),
        "ids": {"ollama": "qwen3.5:4b",
                "lmstudio": "qwen_qwen3.5-4b",
                "llamacpp": "Qwen_Qwen3.5-4B-Q3_K_S.gguf",
                "custom": "qwen3.5-4b"},
    },
    {
        "family": "qwen2.5-7b", "display": "Qwen2.5 7B",
        "params": "7B", "ctx": 32768, "size": 4.7, "quant": "Q4_K_M",
        "think": False, "level": "轻量",
        "note": "西语→中文的主力小模型，8G 显存就能跑，术语稳定。",
        "ids": {"ollama": "qwen2.5:7b",
                "lmstudio": "qwen2.5-7b-instruct",
                "llamacpp": "qwen2.5-7b-instruct-q5_k_m.gguf",
                "custom": "qwen2.5-7b-instruct"},
    },
    {
        "family": "qwen2.5-14b", "display": "Qwen2.5 14B",
        "params": "14B", "ctx": 32768, "size": 9.0, "quant": "Q4_K_M",
        "think": False, "level": "推荐",
        "note": "翻译质量与速度的平衡点，12G 显存可跑，本项目默认档。",
        "ids": {"ollama": "qwen2.5:14b",
                "lmstudio": "qwen2.5-14b-instruct",
                "llamacpp": "qwen2.5-14b-instruct-q5_k_m.gguf",
                "custom": "qwen2.5-14b-instruct"},
    },
    {
        "family": "qwen2.5-32b", "display": "Qwen2.5 32B",
        "params": "32B", "ctx": 32768, "size": 20.0, "quant": "Q4_K_M",
        "think": False, "level": "高质",
        "note": "长句与俚语处理更稳，需要 24G 以上显存或大内存卸载。",
        "ids": {"ollama": "qwen2.5:32b",
                "lmstudio": "qwen2.5-32b-instruct",
                "llamacpp": "qwen2.5-32b-instruct-q4_k_m.gguf",
                "custom": "qwen2.5-32b-instruct"},
    },
    {
        "family": "qwen3-8b", "display": "Qwen3 8B",
        "params": "8B", "ctx": 40960, "size": 5.2, "quant": "Q4_K_M",
        "think": True, "level": "轻量",
        "note": "会思考。Ollama 下用 think=False 关掉，否则译文前带推理内容且变慢。",
        "ids": {"ollama": "qwen3:8b",
                "lmstudio": "qwen3-8b",
                "llamacpp": "qwen3-8b-q5_k_m.gguf",
                "custom": "qwen3-8b"},
    },
    {
        "family": "qwen3-14b", "display": "Qwen3 14B",
        "params": "14B", "ctx": 40960, "size": 9.3, "quant": "Q4_K_M",
        "think": True, "level": "推荐",
        "note": "翻译质量好。务必关掉思考模式，否则每批耗时翻倍。",
        "ids": {"ollama": "qwen3:14b",
                "lmstudio": "qwen3-14b",
                "llamacpp": "qwen3-14b-q5_k_m.gguf",
                "custom": "qwen3-14b"},
    },
    {
        "family": "qwen3-30b", "display": "Qwen3 30B",
        "params": "30B", "ctx": 40960, "size": 18.0, "quant": "Q4_K_M",
        "think": True, "level": "高质",
        "note": "MoE 架构，速度接近 14B 但质量更高，需要 24G 显存。",
        "ids": {"ollama": "qwen3:30b",
                "lmstudio": "qwen3-30b-a3b",
                "llamacpp": "qwen3-30b-a3b-q4_k_m.gguf",
                "custom": "qwen3-30b-a3b"},
    },
    {
        "family": "llama3.1-8b", "display": "Llama 3.1 8B",
        "params": "8B", "ctx": 131072, "size": 4.9, "quant": "Q4_K_M",
        "think": False, "level": "备选",
        "note": "中文不如 Qwen 系，但胜在上下文长、社区模板多。",
        "ids": {"ollama": "llama3.1:8b",
                "lmstudio": "llama-3.1-8b-instruct",
                "llamacpp": "llama-3.1-8b-instruct-q5_k_m.gguf",
                "custom": "llama-3.1-8b-instruct"},
    },
    {
        "family": "gemma3-12b", "display": "Gemma 3 12B",
        "params": "12B", "ctx": 131072, "size": 8.9, "quant": "Q4_K_M",
        "think": False, "level": "备选",
        "note": "多语种表现均衡，长句不易漏翻，显存占用略高于同参数量。",
        "ids": {"ollama": "gemma3:12b",
                "lmstudio": "gemma-3-12b-it",
                "llamacpp": "gemma-3-12b-it-q5_k_m.gguf",
                "custom": "gemma-3-12b-it"},
    },
    {
        "family": "deepseek-r1-14b", "display": "DeepSeek-R1 14B",
        "params": "14B", "ctx": 131072, "size": 9.0, "quant": "Q4_K_M",
        "think": True, "level": "备选",
        "note": "强推理但翻译偏慢，且必须处理思考内容，一般不推荐做批量翻译。",
        "ids": {"ollama": "deepseek-r1:14b",
                "lmstudio": "deepseek-r1-distill-qwen-14b",
                "llamacpp": "deepseek-r1-distill-qwen-14b-q5_k_m.gguf",
                "custom": "deepseek-r1-distill-qwen-14b"},
    },
    {
        "family": "glm4-9b", "display": "GLM-4 9B",
        "params": "9B", "ctx": 131072, "size": 5.5, "quant": "Q4_K_M",
        "think": False, "level": "备选",
        "note": "中文语感好，西语理解略弱于 Qwen，可作对照。",
        "ids": {"ollama": "glm4:9b",
                "lmstudio": "glm-4-9b-chat",
                "llamacpp": "glm-4-9b-chat-q5_k_m.gguf",
                "custom": "glm-4-9b-chat"},
    },
    {
        "family": "mistral-nemo-12b", "display": "Mistral-Nemo 12B",
        "params": "12B", "ctx": 131072, "size": 7.1, "quant": "Q4_K_M",
        "think": False, "level": "备选",
        "note": "上下文长、授权宽松（Apache 2.0），适合商用项目。",
        "ids": {"ollama": "mistral-nemo:12b",
                "lmstudio": "mistral-nemo-instruct-2407",
                "llamacpp": "mistral-nemo-instruct-2407-q5_k_m.gguf",
                "custom": "mistral-nemo-instruct-2407"},
    },
]


# 量化后缀：-q4-k-m / .Q4_K_S / -iq4-xs / -f16 / .bf16 ...
# （分隔符既可能是横线也可能是点，GGUF 文件名两种都常见）
_QUANT_SUFFIX_RE = re.compile(
    r'(?:-|\.)(?:i?q\d+(?:-k)?(?:-[smlx]+)?|f16|bf16|f32|q8-0)$',
    re.IGNORECASE)


def norm_model(name):
    """
    归一化模型标识，好让不同服务端的叫法能对上。

    实测各家的叫法：
      llama.cpp  → qwen3.5-4b（或 -a 指定的别名；不带别名时是模型文件路径）
      LM Studio  → qwen_qwen3.5-4b （全小写、下划线）
      Ollama     → qwen3.5:4b
    这里统一成小写、去服务名前缀、去 .gguf、下划线转横线。
    """
    s = str(name or "").strip().lower()
    if "/" in s:
        head, _, tail = s.partition("/")
        if head in ("llamacpp", "llama.cpp", "llama-server", "ollama",
                    "lmstudio", "lm-studio", "local", "openai",
                    # 历史遗留：旧版用过 KoboldCpp，老配置里的前缀也认
                    "koboldcpp", "kobold"):
            s = tail
    if s.endswith(".gguf"):
        s = s[:-5]
    s = s.replace("_", "-")

    # 去掉量化后缀：qwen2.5-7b-instruct-q5-k-m → qwen2.5-7b-instruct
    # （GGUF 文件名一般带量化，而接口里的别名不带）
    while True:
        new = _QUANT_SUFFIX_RE.sub("", s)
        if new == s:
            break
        s = new

    # 去掉重复的厂商前缀：qwen-qwen3.5-4b → qwen3.5-4b
    for vendor in ("qwen", "llama", "google", "meta", "mistral",
                   "deepseek", "microsoft", "gemma"):
        if s.startswith(vendor + "-") and s[len(vendor) + 1:].startswith(vendor):
            s = s[len(vendor) + 1:]
            break
    return s


def family_by_id(name, provider_key=None):
    """按任一提供商下的模型标识反查模型族（做归一化后再比）。"""
    if not name:
        return None
    low = norm_model(name)
    for fam in MODEL_FAMILIES:
        ids = fam.get("ids", {})
        if provider_key:
            cand = ids.get(provider_key)
            if cand and norm_model(cand) == low:
                return fam
            continue
        for cand in ids.values():
            if cand and norm_model(cand) == low:
                return fam
    return None


def map_model_name(name, from_key, to_key):
    """
    把模型名从一个提供商映射到另一个提供商。
    映射不到时原样返回（自定义提供商通常就是原样）。
    """
    if not name or from_key == to_key:
        return name or ""
    fam = family_by_id(name, from_key) or family_by_id(name)
    if not fam:
        return name
    return fam.get("ids", {}).get(to_key) or name


# ================================================================
# 读写
# ================================================================
def normalize(key):
    key = str(key or "").strip().lower()
    return key if key in PROVIDERS else "ollama"


def get(key=None):
    return PROVIDERS[normalize(key)]


def keys():
    return list(ORDER)


def current():
    return normalize(getattr(config, "PROVIDER", "ollama"))


def label_of(key):
    return get(key)["label"]


def _cfg_url(key):
    p = get(key)
    return str(getattr(config, p["url_config"], "") or p["default_url"])


def stored_url(key=None):
    """config 里存的原始地址：Ollama 是 /api/chat，其余是 /v1 根地址。"""
    return _cfg_url(key)


def endpoints_text(key=None):
    """给用户看的实际调用端点。"""
    p = get(key)
    if p["protocol"] == "ollama":
        return f"对话 {chat_url(p['key'])}   列表 {models_url(p['key'])}"
    return (f"对话 {chat_url(p['key'])}   列表 {models_url(p['key'])}"
            f"（OpenAI 兼容）")


def base_url(key=None):
    """
    OpenAI 兼容根地址（末尾不带 /）。
    Ollama 存的是 /api/chat，这里剥掉路径只留 http://host:port。
    """
    p = get(key)
    raw = _cfg_url(p["key"])
    u = urllib.parse.urlparse(raw)
    if p["protocol"] == "ollama":
        return f"{u.scheme}://{u.netloc}"
    return raw.rstrip("/")


def models_url(key=None):
    p = get(key)
    if p["protocol"] == "ollama":
        return base_url(p["key"]) + "/api/tags"
    return base_url(p["key"]) + "/models"


def chat_url(key=None):
    p = get(key)
    if p["protocol"] == "ollama":
        return _cfg_url(p["key"])
    return base_url(p["key"]) + "/chat/completions"


def host_port(key=None):
    u = urllib.parse.urlparse(base_url(key))
    return u.hostname or "localhost", u.port or 80


def model_config_key(key=None):
    return get(key)["model_config"]


def current_model(key=None):
    return str(getattr(config, model_config_key(key), "") or "")


def set_current_model(value, key=None):
    import settings
    ok, _msg, _v = settings.set_value(model_config_key(key), value)
    return ok


def set_url(url, key=None):
    """写回该提供商的服务地址。"""
    import settings
    p = get(key)
    ok, msg, _v = settings.set_value(p["url_config"], url)
    return ok, msg


# ================================================================
# 服务探测
# ================================================================
# 有的本地服务在「没加载模型」时会返回一个占位名，别把它当成真模型
PLACEHOLDER_IDS = {"inactive", "none", "null", "no-model", "no_model",
                   "unknown", "undefined", "n/a", ""}


def _is_placeholder(name):
    return str(name or "").strip().lower() in PLACEHOLDER_IDS


def _raw_model_names(data, protocol):
    """从 /api/tags 或 /v1/models 的返回里取出模型名列表。"""
    names = []
    if protocol == "ollama":
        for m in (data or {}).get("models", []) or []:
            if isinstance(m, dict):
                n = m.get("name") or m.get("model") or ""
                if n:
                    names.append(n)
    else:
        for m in (data or {}).get("data", []) or []:
            n = (m.get("id") or m.get("name") or "") if isinstance(m, dict) \
                else str(m)
            if n:
                names.append(n)
    return names


def probe(key=None, timeout=3):
    """
    探测服务是否在线。返回 (ok, msg)。
      · 先看端口通不通
      · 再取模型列表：有真模型 → 报「已加载 N 个」；
        只有占位名（如某些服务没加载模型时回的 inactive）→ 报「还没加载模型」
    """
    import socket
    p = get(key)
    host, port = host_port(p["key"])
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except Exception as e:
        return False, f"{p['label']} 未响应 {host}:{port}（{e.__class__.__name__}）"

    if requests is None:
        return True, f"{p['label']} 端口已通（缺少 requests，未校验接口）"

    try:
        r = requests.get(models_url(p["key"]), timeout=timeout + 2)
        if r.status_code >= 400:
            return False, f"{p['label']} 接口返回 HTTP {r.status_code}"
        try:
            data = r.json()
        except Exception:
            return True, f"{p['label']} 在线（{host}:{port}）"
    except Exception as e:
        return False, f"{p['label']} 端口已通，但接口不可用（{e.__class__.__name__}）"

    real = [n for n in _raw_model_names(data, p["protocol"])
            if not _is_placeholder(n)]
    if real:
        return True, (f"{p['label']} 在线（{host}:{port}），"
                      f"已加载 {len(real)} 个模型")
    if p["protocol"] == "ollama":
        return True, f"{p['label']} 在线（{host}:{port}），但还没有安装模型"
    return True, (f"{p['label']} 在线（{host}:{port}），但还没有加载模型；"
                  + _load_hint(p["key"]))


# ================================================================
# 模型列表
# ================================================================
def _fmt_gb(n):
    try:
        n = float(n)
    except Exception:
        return ""
    if n <= 0:
        return ""
    return f"{n / (1024 ** 3):.1f} GB" if n > 10 ** 6 else f"{n:.1f} GB"


def local_models(key=None, timeout=5):
    """
    查询该提供商下本机已有的模型。返回 [{name, params, ctx, size, quant, ...}]。
    服务不可用时返回空列表，不抛异常。
    """
    if requests is None:
        return []
    p = get(key)
    try:
        r = requests.get(models_url(p["key"]), timeout=timeout)
        r.raise_for_status()
        data = r.json() or {}
    except Exception:
        return []

    out = []
    if p["protocol"] == "ollama":
        for m in data.get("models", []) or []:
            if not isinstance(m, dict):
                continue
            name = m.get("name") or m.get("model") or ""
            if not name:
                continue
            det = m.get("details") or {}
            out.append({
                "name":        name,
                "params":      det.get("parameter_size", "") or "",
                "ctx":         _ollama_ctx(m),
                "size":        _fmt_gb(m.get("size", 0)),
                "quant":       det.get("quantization_level", "") or "",
                "family":      det.get("family", "") or "",
                "installed":   True,
                "source":      "本机已安装",
            })
    else:
        # ★ 没加载模型时服务可能回一个占位名（旧版 KoboldCpp 是 "inactive"），
        #   那不是真模型，不能列出来也不能让它参与模型名匹配。
        for name in _raw_model_names(data, p["protocol"]):
            if _is_placeholder(name):
                continue
            out.append({
                "name":      name,
                "params":    "",
                "ctx":       "",
                "size":      "",
                "quant":     "",
                "family":    "",
                "installed": True,
                "source":    "本机已加载",
            })
    out.sort(key=lambda d: str(d["name"]).lower())
    return out


def _ollama_ctx(m):
    """Ollama /api/tags 里没有直接的 num_ctx，从 model_info 里取。"""
    info = m.get("model_info") or {}
    for k in ("general.context_length", "qwen3.context_length",
              "llama.context_length", "bert.context_length"):
        if k in info:
            return info[k]
    return ""


def catalog(key=None):
    """该提供商下推荐（可拉取）的模型目录。"""
    p = get(key)
    out = []
    for fam in MODEL_FAMILIES:
        mid = fam.get("ids", {}).get(p["key"])
        if not mid:
            continue
        out.append({
            "name":      mid,
            "display":   fam["display"],
            "params":    fam["params"],
            "ctx":       fam["ctx"],
            "size":      f"{fam['size']:.1f} GB",
            "quant":     fam["quant"],
            "family":    fam["family"],
            "installed": False,
            "source":    "可拉取",
            "note":      fam["note"],
            "level":     fam.get("level", ""),
            "think":     fam.get("think", False),
        })
    return out


def all_models(key=None, timeout=5):
    """本机已有 + 推荐目录（本机已有的排前面，并标注来源）。"""
    p = get(key)
    installed = local_models(p["key"], timeout=timeout)
    # ★ 用归一化名去重：本机别名「qwen3.5-4b」和目录里的
    #   「Qwen_Qwen3.5-4B-Q3_K_S.gguf」其实是同一个模型，别列两遍。
    names = {norm_model(d["name"]) for d in installed}

    out = []
    for d in installed:
        fam = family_by_id(d["name"], p["key"]) or family_by_id(d["name"])
        row = dict(d)
        row["display"] = fam["display"] if fam else d["name"]
        row["note"] = fam["note"] if fam else "本机已有模型，目录中无对应条目。"
        row["level"] = fam.get("level", "") if fam else ""
        row["think"] = fam.get("think", False) if fam else False
        if not row.get("ctx") and fam:
            row["ctx"] = fam["ctx"]
        if not row.get("size") and fam:
            row["size"] = f"{fam['size']:.1f} GB"
        out.append(row)

    for d in catalog(p["key"]):
        if norm_model(d["name"]) in names:
            continue
        out.append(d)
    return out


def info_from_row(row, key=None):
    """
    把 `all_models()` 返回的一行补全成展示用的完整信息（不再联网）。
    列表里已经有数据时用这个，避免每点一次模型就打一次服务。
    """
    p = get(key)
    name = str((row or {}).get("name", ""))
    fam = family_by_id(name, p["key"]) or family_by_id(name)

    out = dict(row or {})
    if fam:
        out["display"] = fam["display"]
        out["params"] = out.get("params") or fam["params"]
        out["ctx"] = out.get("ctx") or fam["ctx"]
        out["size"] = out.get("size") or f"{fam['size']:.1f} GB"
        out["quant"] = out.get("quant") or fam["quant"]
        out["note"] = out.get("note") or fam["note"]
        out["level"] = out.get("level") or fam.get("level", "")
        out["think"] = out.get("think", fam.get("think", False))
    out.setdefault("display", name)
    for k in ("params", "ctx", "size", "quant", "note", "level"):
        out.setdefault(k, "")
    out.setdefault("think", False)
    out.setdefault("installed", False)
    return out


def model_info(name, key=None, timeout=5):
    """
    单个模型的完整参数：优先用本机返回的真实数据，缺失部分用目录补全。
    """
    p = get(key)
    row = None
    for d in local_models(p["key"], timeout=timeout):
        if str(d["name"]).lower() == str(name).lower():
            row = dict(d)
            break
    fam = family_by_id(name, p["key"]) or family_by_id(name)
    if row is None:
        row = {"name": name, "installed": False, "source": "可拉取"}
    if fam:
        row.setdefault("display", fam["display"])
        row["display"] = fam["display"]
        row.setdefault("params", fam["params"]) or None
        if not row.get("params"):
            row["params"] = fam["params"]
        if not row.get("ctx"):
            row["ctx"] = fam["ctx"]
        if not row.get("size"):
            row["size"] = f"{fam['size']:.1f} GB"
        if not row.get("quant"):
            row["quant"] = fam["quant"]
        row.setdefault("note", fam["note"])
        row.setdefault("level", fam.get("level", ""))
        row.setdefault("think", fam.get("think", False))
    row.setdefault("display", name)
    row.setdefault("params", "")
    row.setdefault("ctx", "")
    row.setdefault("size", "")
    row.setdefault("quant", "")
    row.setdefault("note", "")
    row.setdefault("level", "")
    row.setdefault("think", False)
    return row


# ================================================================
# 一键部署（拉取 / 加载模型）
# ================================================================
def _find_ollama_exe():
    try:
        import env_check
        return env_check._find_ollama_exe()
    except Exception:
        return shutil.which("ollama")


def _find_lms_exe():
    """
    LM Studio 的 lms 命令行。

    实测（0.4.25）：装在 `%LOCALAPPDATA%\\Programs\\LM Studio\\`，
    真正的 CLI 是 `resources\\app\\.webpack\\lms.exe`（120MB 那个）。
    `~/.lmstudio/bin/lms.exe` 是首次启动 GUI 后生成的转发器，可能不存在，
    所以两边都要找；最后再在常见安装目录下浅层递归兜底。
    """
    exe = shutil.which("lms")
    if exe:
        return exe

    home = os.path.expanduser("~")
    local = (os.environ.get("LOCALAPPDATA")
             or os.path.join(home, "AppData", "Local"))

    roots = [os.path.join(local, "Programs", "LM Studio"),
             os.path.join(local, "LM Studio")]
    cands = [
        os.path.join(home, ".lmstudio", "bin", "lms.exe"),
        os.path.join(home, ".cache", "lm-studio", "bin", "lms.exe"),
    ]
    for r in roots:
        cands.append(os.path.join(r, "resources", "app", ".webpack",
                                  "lms.exe"))
        cands.append(os.path.join(r, "resources", "app", "bin", "lms.exe"))
        cands.append(os.path.join(r, "lms.exe"))

    for c in cands:
        if os.path.exists(c):
            return c

    # 兜底 ①：已知安装目录里浅层递归找一次（Electron 打包路径各版本不一样）
    for r in roots:
        if not os.path.isdir(r):
            continue
        for dirpath, _dn, files in os.walk(r):
            if dirpath[len(r):].count(os.sep) > 4:
                continue
            if "lms.exe" in files:
                return os.path.join(dirpath, "lms.exe")

    # 兜底 ②：LM Studio 允许装到任意盘（实测有装 E:\LM Studio\ 的），
    #        在各盘根目录找一层同名文件夹。
    import string
    for letter in string.ascii_uppercase:
        rt = letter + ":\\"
        if not os.path.isdir(rt):
            continue
        try:
            names = os.listdir(rt)
        except OSError:
            continue
        for name in names:
            low = name.lower()
            if low not in ("lm studio", "lmstudio", "lm-studio"):
                continue
            d = os.path.join(rt, name)
            cand = os.path.join(d, "resources", "app", ".webpack", "lms.exe")
            if os.path.exists(cand):
                return cand
            cand2 = os.path.join(d, "LM Studio.exe")
            if os.path.exists(cand2):
                return cand2
    return None


def deploy_command(model, key=None):
    """
    生成部署命令。返回 (argv, note)；本提供商不支持时返回 (None, reason)。
    """
    p = get(key)
    if p["key"] == "ollama":
        exe = _find_ollama_exe()
        if not exe:
            return None, ("未找到 ollama 命令。请先安装 Ollama："
                          f"{p['install_url']}，或把 ollama.exe 加进 PATH。")
        return [exe, "pull", model], "正在用 ollama pull 拉取模型，输出见下方日志。"

    if p["key"] == "lmstudio":
        exe = _find_lms_exe()
        if not exe:
            return None, ("未找到 LM Studio 的 lms 命令行。\n"
                          "请在 LM Studio 里手动搜索并下载该模型，"
                          "或在 LM Studio 的终端里执行："
                          f"lms get {model}")
        return [exe, "get", model], (
            "正在用 lms get 拉取模型，输出见下方日志。\n"
            "注意：lms 需要 LM Studio 的守护进程在跑；\n"
            "没反应的话先手动打开一次 LM Studio（或执行 "
            "lms server start）再重试。")

    if p["key"] == "llamacpp":
        return None, ("llama.cpp 没有模型仓库，一次只加载一个 GGUF 文件。\n"
                      "做法：启动 llama-server.exe 时用 -m 指定 GGUF 路径。\n"
                      "示例（按你本机路径改）：\n"
                      f"  llama-server.exe -m \"...\\{model}.gguf\" -c 8192 "
                      "--port 8080 --reasoning off -a " + (model or "my-model"))

    return None, "自定义服务请在你自己的服务端准备模型，这里无法代劳。"


def run_deploy(model, key=None, emit=None, timeout=7200):
    """
    执行部署命令，逐行把输出交给 emit（GUI 里就是运行日志）。
    返回 (ok, msg)。
    """
    emit = emit or (lambda s: None)
    p = get(key)
    argv, note = deploy_command(model, p["key"])
    if not argv:
        emit(note or "该提供商不支持一键部署。")
        return False, note or "该提供商不支持一键部署。"

    emit(f"$ {' '.join(argv)}")
    emit(note or "")

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=config.BASE_DIR, env=env,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1,
        )
    except Exception as e:
        msg = f"启动命令失败：{e}"
        emit(msg)
        return False, msg

    try:
        for line in proc.stdout:
            emit(line.rstrip("\n"))
    except Exception as e:
        emit(f"读取输出失败：{e}")
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        msg = f"部署超时（{timeout} 秒），已终止。"
        emit(msg)
        return False, msg

    ok = (proc.returncode == 0)
    msg = ("部署完成。回到菜单 2 选好文件即可翻译。"
           if ok else f"命令退出码 {proc.returncode}，部署未成功。")
    emit(msg)
    return ok, msg


# ================================================================
# llama.cpp 专用：找程序 / 扫模型 / 拼启动命令
# ================================================================
def _fmt_bytes(n):
    try:
        n = float(n)
    except Exception:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return ("%.0f %s" if unit in ("B", "KB") else "%.1f %s") % (n, unit)
        n /= 1024.0
    return ""


def find_llama_server(folder=None):
    """定位 llama-server.exe。folder 为空时用 config.LLAMACPP_DIR。"""
    folder = folder if folder is not None else \
        getattr(config, "LLAMACPP_DIR", "")
    cands = []
    if folder:
        cands.append(os.path.join(folder, "llama-server.exe"))
        cands.append(os.path.join(folder, "llama-server"))
    exe = shutil.which("llama-server")
    if exe:
        cands.append(exe)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def autodetect_llama_dir():
    """在各固定磁盘根目录找 llama*/llama-server.exe（只看一层，很快）。"""
    import string
    for letter in string.ascii_uppercase:
        root = letter + ":\\"
        if not os.path.isdir(root):
            continue
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            if not name.lower().startswith("llama"):
                continue
            d = os.path.join(root, name)
            if os.path.isdir(d) and os.path.exists(
                    os.path.join(d, "llama-server.exe")):
                return d
    return ""


def autodetect_model_dir(max_depth=3, limit=60):
    """找一个放着 .gguf 的目录：先挑名字像模型库的目录再浅扫。"""
    import string
    seeds = []
    for letter in string.ascii_uppercase:
        root = letter + ":\\"
        if not os.path.isdir(root):
            continue
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            d = os.path.join(root, name)
            if not os.path.isdir(d):
                continue
            low = name.lower()
            if any(k in low for k in ("model", "gguf", "lm studio", "llm")):
                seeds.append(d)
    for d in seeds[:limit]:
        for dirpath, dirs, files in os.walk(d):
            if dirpath[len(d):].count(os.sep) >= max_depth:
                dirs[:] = []          # 到深度就不再往下走
            if any(f.lower().endswith(".gguf") for f in files):
                return d
    return ""


def scan_gguf(model_dir=None, max_items=300):
    """
    扫描目录下已安装的 GGUF 模型。
    跳过 mmproj（视觉投影）和分片文件，只留能直接 -m 加载的主模型。
    """
    model_dir = model_dir if model_dir is not None else \
        getattr(config, "LLAMACPP_MODEL_DIR", "")
    out = []
    if not model_dir or not os.path.isdir(model_dir):
        return out
    for dirpath, _dirs, files in os.walk(model_dir):
        for fn in files:
            low = fn.lower()
            if not low.endswith(".gguf"):
                continue
            if "mmproj" in low or "projector" in low or "mmproj-" in low:
                continue
            if re.search(r'-\d{5}-of-\d{5}\.gguf$', low):
                continue
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            # 相对模型目录的展示名（层级太深时只留最后两段）
            try:
                rel = os.path.relpath(full, model_dir)
            except ValueError:
                rel = fn
            if rel.count(os.sep) > 1:
                rel = os.sep.join(rel.split(os.sep)[-2:])
            out.append({
                "path": full, "name": fn, "rel": rel,
                "size": size, "size_text": _fmt_bytes(size),
            })
    out.sort(key=lambda d: d["rel"].lower())
    return out[:max_items]


def llamacpp_args(model_path=None, exe=None):
    """
    拼 llama-server 的启动参数（已包含关推理与单槽）。
    返回 (argv, msg)；argv=None 表示缺东西跑不起来。
    """
    exe = exe or find_llama_server()
    if not exe:
        return None, ("未找到 llama-server.exe。\n"
                      "请在菜单 10 中层把「llama.cpp 目录」指到解压出来的那个文件夹。")
    model = (model_path or getattr(config, "LLAMACPP_MODEL_PATH", "") or "").strip()
    if not model:
        return None, ("还没选模型。\n"
                      "请在菜单 10 中层的「已安装模型」里选一个 GGUF。")
    if not os.path.exists(model):
        return None, f"模型文件不存在：{model}"

    port = 8080
    try:
        u = urllib.parse.urlparse(base_url("llamacpp"))
        port = u.port or 8080
    except Exception:
        pass
    ctx = int(getattr(config, "NUM_CTX", 8192) or 8192)
    alias = os.path.splitext(os.path.basename(model))[0]
    alias = alias[:40]

    argv = [
        exe,
        "-m", model,
        "-c", str(ctx),
        "-np", "1",                     # 翻译是单并发，别开多槽白占 KV 缓存
        "--port", str(port),
        "-ngl", "99",                   # 尽量全量上 GPU；没 CUDA 时 llama.cpp 会自己退 CPU
        "--reasoning", "off",           # ★ 关推理模式
        "--no-ui",
        "-a", alias,
    ]
    return argv, "将启动 llama-server（自动加载该模型并关闭推理模式）"


def _find_lmstudio_app():
    """
    找 LM Studio 主程序。顺序：
      ① 读它自己记录的安装位置（~/.lmstudio/.internal/app-install-location.json，最准）
      ② 从 lms.exe 所在目录往上翻（支持装在任意盘）
      ③ 各盘根目录下的同名文件夹
    """
    # ① LM Studio 自己写的安装位置
    try:
        import json
        info = os.path.join(os.path.expanduser("~"), ".lmstudio",
                            ".internal", "app-install-location.json")
        if os.path.exists(info):
            with open(info, "r", encoding="utf-8") as f:
                p = (json.load(f) or {}).get("path") or ""
            if p and os.path.exists(p):
                return p
    except Exception as e:
        try:
            from logger import get_logger
            get_logger("providers").debug("读 LM Studio 安装位置失败：%s", e)
        except Exception:
            pass

    # ② 从 lms.exe 往上翻（lms 在 <root>\resources\app\.webpack\ 或 ~/.lmstudio/bin/）
    lms = _find_lms_exe()
    if lms:
        d = os.path.dirname(os.path.abspath(lms))
        for _ in range(4):
            cand = os.path.join(d, "LM Studio.exe")
            if os.path.exists(cand):
                return cand
            d = os.path.dirname(d)

    # ③ 各盘根目录下的同名文件夹
    import string
    for letter in string.ascii_uppercase:
        rt = letter + ":\\"
        if not os.path.isdir(rt):
            continue
        for name in ("LM Studio", "LMStudio", "LM-Studio"):
            cand = os.path.join(rt, name, "LM Studio.exe")
            if os.path.exists(cand):
                return cand
    return None


def launch_command(key=None):
    """
    「尝试启动服务」要执行的命令。返回 (argv, msg)；argv=None 表示做不到。
    """
    p = get(key)
    k = p["key"]
    if k == "ollama":
        exe = _find_ollama_exe()
        if not exe:
            return None, ("未找到 ollama.exe。请先安装 Ollama：\n"
                          f"{p['install_url']}")
        return [exe, "serve"], "将启动 ollama serve（服务在 11434 端口）"
    if k == "llamacpp":
        return llamacpp_args()
    if k == "lmstudio":
        app = _find_lmstudio_app()
        if not app:
            return None, ("未找到 LM Studio.exe。\n"
                          "装好后请先手动打开一次（它会同时初始化 lms 命令行）。")
        return [app], ("将启动 LM Studio。\n"
                       "启动后请在左侧 Local Server 页把模型载入，"
                       "并点 Start Server（默认 1234 端口），再回来点「检测连接」。")
    return None, ("自定义服务没法替你启动。\n"
                  "请在你自己那边把服务跑起来，然后点「检测连接」。")


def launch_app(key=None):
    """真正去启动。返回 (ok, msg)。"""
    key = normalize(key)
    argv, msg = launch_command(key)
    if not argv:
        return False, msg
    try:
        cwd = os.path.dirname(argv[0]) or config.BASE_DIR
        subprocess.Popen(argv, cwd=cwd, close_fds=True)
    except Exception as e:
        return False, f"启动失败：{e}"
    try:
        from logger import get_logger
        get_logger("providers").info("已启动 %s：%s",
                                     get(key)["label"], " ".join(argv))
    except Exception:
        pass
    return True, msg


# ================================================================
# 切换提供商
# ================================================================
def _set(key, value, changes=None, label=None):
    import settings
    old = getattr(config, key, None)
    if old == value:
        return False
    ok, _msg, _v = settings.set_value(key, value)
    if ok:
        if changes is not None:
            changes.append((label or PRESET_LABELS.get(key, key), old, value))
        return True
    return False


def apply_provider(key, model=None, map_model=True):
    """
    切换到某个提供商：改协议、改地址、套用推荐参数，并按需要映射模型名。
    返回 [(显示名, 旧值, 新值), ...]。
    """
    key = normalize(key)
    p = get(key)
    old_key = current()
    # ★ 旧模型要从「切换前那个提供商」对应的配置键上读，
    #   否则 ollama→lmstudio 会拿 API_MODEL 当旧模型名去映射。
    old_model = current_model(old_key)
    changes = []

    # ---------- 协议 / 地址 ----------
    if p["protocol"] == "ollama":
        _set("TRANSLATE_MODE", "ollama", changes)
        if not getattr(config, "OLLAMA_URL", ""):
            _set("OLLAMA_URL", p["default_url"], changes)
    else:
        _set("TRANSLATE_MODE", "api", changes)
        url = _cfg_url(key) or p["default_url"]
        _set("API_BASE_URL", url, changes)

    # ---------- 推荐参数 ----------
    for k, v in PRESETS.get(key, {}).items():
        _set(k, v, changes)

    # ---------- 模型名 ----------
    target_model = model
    if not target_model and map_model:
        target_model = map_model_name(old_model, old_key, key)
    if not target_model:
        target_model = old_model or p.get("default_model", "")
    if target_model:
        _set(model_config_key(key), target_model, changes)

    # ---------- 提供商本身 ----------
    _set("PROVIDER", key, changes, label="服务提供商")

    try:
        from logger import get_logger
        get_logger("providers").info(
            "切换服务提供商：%s → %s（同步 %d 项）",
            label_of(old_key), p["label"], len(changes))
    except Exception:
        pass

    return changes


def sync_with_mode(mode):
    """
    菜单 1 / 菜单 8 上的「本地 Ollama ↔ API 服务」切换后同步 PROVIDER，
    避免那里与菜单 9 的状态打架。
      · 切到 ollama → PROVIDER 归位成 ollama
      · 切到 api    → 若原来在 ollama，PROVIDER 记为 custom（地址沿用现有设置）
    """
    import settings

    mode = str(mode).strip().lower()
    cur = current()
    if mode == "ollama":
        if cur != "ollama":
            apply_provider("ollama", map_model=True)
    else:
        if cur == "ollama":
            settings.set_value("PROVIDER", "custom")


def set_prev_provider(key):
    """记住上一个提供商，供右侧「切换适配」栏计算 from → to。"""
    import settings
    return settings.set_internal("PROVIDER_PREV", normalize(key))


def prev_provider():
    return normalize(getattr(config, "PROVIDER_PREV", "") or current())


# ================================================================
# 切换适配清单
# ================================================================
def adaptation(from_key, to_key):
    """
    从一个提供商换到另一个，需要做什么。
    返回 (auto, manual)，每项 dict：{"title", "detail"}。
      auto   —— 切换时已经自动改掉的
      manual —— 需要人工在服务端 / 界面上处理的
    """
    from_key, to_key = normalize(from_key), normalize(to_key)
    fp, tp = get(from_key), get(to_key)
    auto, manual = [], []

    if fp["protocol"] != tp["protocol"]:
        auto.append({
            "title": "接口协议",
            "detail": (f"{fp['label']} 用 {_proto_desc(fp)}，"
                       f"{tp['label']} 用 {_proto_desc(tp)}；"
                       "已改写 TRANSLATE_MODE 与服务地址。"),
        })
    else:
        auto.append({
            "title": "接口协议",
            "detail": f"两边都是 {_proto_desc(tp)}，只改了服务地址。",
        })

    auto.append({
        "title": "模型名映射",
        "detail": _model_map_desc(from_key, to_key),
    })

    preset_desc = "、".join(
        f"{PRESET_LABELS.get(k, k)}={v}"
        for k, v in PRESETS.get(to_key, {}).items()
        if k not in ("API_TIMEOUT",))
    auto.append({
        "title": "推荐参数",
        "detail": f"已套用 {tp['label']} 的推荐值：{preset_desc}。",
    })

    # ---------- 需要人工处理的 ----------
    if tp["protocol"] == "openai":
        manual.append({
            "title": "上下文长度要在服务端设",
            "detail": (f"{tp['label']} 不认请求里的 num_ctx，"
                       f"NUM_CTX 只是本项目的分批依据。\n"
                       + _ctx_hint(to_key)),
        })

    if tp["think"] is False and fp["think"] is True:
        manual.append({
            "title": "思考模式没法用参数关了",
            "detail": ("Ollama 的 think=false 在 OpenAI 兼容端无效。"
                       "若模型会输出思考过程（Qwen3 / DeepSeek-R1），"
                       "要么换 Qwen2.5 这类不带思考的模型，"
                       "要么接受它多花时间。"),
        })

    if tp["keep_alive"] is False:
        manual.append({
            "title": "模型驻留策略变了",
            "detail": (f"{tp['label']} 没有 keep_alive；模型常驻还是用完即卸，"
                       "由服务端界面/启动参数决定。频繁翻译建议让它常驻，"
                       "否则每批都要重新加载模型。"),
        })

    if to_key == "llamacpp":
        manual.append({
            "title": "一次只加载一个模型",
            "detail": ("llama-server 启动时就绑定了那一个 GGUF，"
                       "换模型要重启服务并重新指定 -m；\n"
                       "启动命令形如：llama-server.exe -m 你的.gguf -c 8192 "
                       "--port 8080 --reasoning off -a 别名。\n"
                       "建议加 -a 起个短别名，接口里的模型名就是它。"),
        })
    elif to_key == "lmstudio":
        manual.append({
            "title": "模型要在界面里加载",
            "detail": ("LM Studio 需在「Local Server」页把模型加进 "
                       "「Loaded Models」，且开启 Server 后才有 /v1 接口。"),
        })
    elif to_key == "custom":
        manual.append({
            "title": "确认接口路径",
            "detail": ("自定义地址请填到 OpenAI 兼容根路径（一般 /v1 结尾）。"
                       "若服务端是 Anthropic 协议，请到「设置」里改填 "
                       "/anthropic 结尾的地址。"),
        })

    # ★ 推理模式：Ollama 能用参数关，其余都得在服务端关，
    #   不关的话模型会把预算花在 <think> 上，译文被截断甚至直接没返回。
    if not tp["think"]:
        manual.append({
            "title": "推理（思考）模式要在服务端关",
            "detail": (f"{tp['label']} 不认请求里的 think 参数。\n"
                       f"关闭办法：{tp.get('nothink', '见官方文档')}\n"
                       "不关的后果：模型把生成预算耗在思考过程上，"
                       "译文被截断、或直接「模型无返回」。"),
        })

    if tp["protocol"] == "openai":
        manual.append({
            "title": "首次加载会慢",
            "detail": ("本地服务第一次收到请求才把模型读进显存，"
                       "首批可能等几十秒到几分钟；TIMEOUT 已设成 600 秒。"),
        })

    return auto, manual


def _proto_desc(p):
    return "/api/chat（Ollama 原生）" if p["protocol"] == "ollama" \
        else "/v1/chat/completions（OpenAI 兼容）"


def _ctx_hint(key):
    if key == "llamacpp":
        return "llama.cpp：启动时用 -c 指定上下文，例如 -c 8192。"
    if key == "lmstudio":
        return "LM Studio：加载模型时把 Context Length 调到 8192 以上。"
    return "请在服务端把上下文调到 8192 以上，否则长批会截断。"


def nothink_hint(key=None):
    """当前提供商关掉推理（思考）模式的办法。"""
    return get(key).get("nothink", "")


def _load_hint(key):
    """「服务在线但没模型」时告诉用户下一步怎么做。"""
    return {
        "llamacpp": ("用 -m 指定一个 GGUF 重启 llama-server"
                     "（服务起来但没模型时，生成会直接报错）。"),
        "lmstudio": "在 LM Studio 的 Local Server 页把模型加进 Loaded Models。",
        "custom": "请在你的服务端先加载模型。",
        "ollama": "先 ollama pull 一个模型。",
    }.get(key, "先在服务端加载一个模型。")


def _model_map_desc(from_key, to_key):
    cur = current_model(to_key) or current_model(from_key)
    fam = family_by_id(cur, to_key) or family_by_id(cur)
    if not fam:
        return (f"当前模型名「{cur or '（空）'}」在两个提供商里标识一致，"
                "已原样保留。若实际不存在，请在下方模型列表里选一个。")
    src = fam.get("ids", {}).get(from_key) or cur
    dst = fam.get("ids", {}).get(to_key) or cur
    if src == dst:
        return f"「{dst}」两边同名，沿用即可。"
    return f"同一个模型：{from_key} 里叫 {src} → {to_key} 里叫 {dst}，已自动改写。"


def apply_adaptation(from_key, to_key):
    """
    一键适配：把能自动改的都改掉（含模型名映射与推荐参数）。
    返回 [(显示名, 旧值, 新值), ...]。
    """
    return apply_provider(to_key, map_model=True)
