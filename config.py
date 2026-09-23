# -*- coding: utf-8 -*-
"""全局配置。"""
import os
import sys


# ================================================================
# 路径自适应：
#   打包成 exe → BASE_DIR = exe 所在目录
#   普通 py    → BASE_DIR = 本文件（config.py）所在目录
# ================================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------- 文件（默认，可在运行时覆盖） ----------
INPUT_FILE   = os.path.join(BASE_DIR, "intl.txt")
OUTPUT_FILE  = os.path.join(BASE_DIR, "intl_translated.txt")
CACHE_FILE   = os.path.join(BASE_DIR, "intl_cache.json")
TERM_FILE    = os.path.join(BASE_DIR, "term_dict.py")
REPORT_DIR   = os.path.join(BASE_DIR, "reports")
EXCEL_FILE   = os.path.join(BASE_DIR, "术语表（Glossary）.xlsx")
CHECK_REPORT = os.path.join(REPORT_DIR, "check_report.txt")
ICON_FILE    = os.path.join(BASE_DIR, "start.ico")


# ================================================================
# 运行时上下文
# ================================================================
class Runtime:
    input_file  = INPUT_FILE
    output_file = OUTPUT_FILE
    cache_file  = CACHE_FILE

    @classmethod
    def reset(cls):
        cls.input_file  = INPUT_FILE
        cls.output_file = OUTPUT_FILE
        cls.cache_file  = CACHE_FILE

    @classmethod
    def set_input(cls, path):
        cls.input_file = path
        stem = os.path.splitext(os.path.basename(path))[0]
        parent = os.path.dirname(os.path.abspath(path))
        cls.output_file = os.path.join(parent, f"{stem}_translated.txt")
        cls.cache_file  = os.path.join(parent, f"{stem}_cache.json")

    @classmethod
    def save(cls):
        """可选：把当前输入路径持久化到 .runtime.json"""
        import json
        try:
            with open(os.path.join(BASE_DIR, ".runtime.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"input_file": cls.input_file}, f,
                          ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def load(cls):
        import json
        p = os.path.join(BASE_DIR, ".runtime.json")
        if not os.path.exists(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            ip = d.get("input_file")
            if ip and os.path.exists(ip):
                cls.set_input(ip)
        except Exception:
            pass


Runtime.reset()


# ---------- 编码 ----------
INPUT_ENCODING  = "utf-8-sig"
OUTPUT_ENCODING = "utf-8-sig"

# ---------- Ollama ----------
OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "qwen3.5:4b"
TIMEOUT     = 600
NUM_CTX     = 4096
NUM_PREDICT = 1024
TEMPERATURE = 0.25
THINK       = False

# ---------- 翻译策略 ----------
SOURCE_LANG      = "西班牙文"
TARGET_LANG      = "简体中文"
BATCH_SIZE       = 10
BATCH_RETRIES    = 2
SINGLE_RETRIES   = 3
CACHE_SAVE_EVERY = 1

# ---------- 换行重排 ----------
REWRAP_ENABLE  = True
WRAP_CHARS_MIN = 15
WRAP_CHARS_MAX = 18
WRAP_PUNCT     = "。！？!?"
WRAP_DOTS      = 3
WRAP_MIN_GAP   = 10    # ★ 新增：换行后至少 N 个字才能再次换行

# ---------- 术语 ----------
APPLY_TERMS        = True
ASK_LANG_EACH_TIME = True
# ---------- 玩家名替换 ----------
PLAYER_TOKEN = r"\PN"              # 游戏脚本里的玩家名控制码
PLAYER_PLACEHOLDER = "玛俐大小姐"  # 送模型时的替换文本（含罕见括号，防误伤）

# ---------- 自动术语提取 ----------
AUTO_EXTRACT_TERMS    = True    # 翻译时自动提取专有名词
AUTO_EXTRACT_MIN_LEN  = 3       # 术语最短长度（过滤单字母/双字母）
# ---------- Excel ----------
EXCEL_SOURCE_LANG = "西班牙文"
EXCEL_TARGET_LANG = "简体中文"
# ---------- 句首控制码字典 ----------
PREFIX_DICT_ENABLE = True    # 启用句首控制码前缀字典
# ---------- 纯控制符过滤 ----------
SKIP_PURE_CONTROL = True    # 剥离控制码后无有效内容的句子跳过翻译
PURE_CONTROL_MIN_LEN = 2    # 剥离后至少保留多少个字母/汉字才算有内容
# ================================================================
# 用户配置覆盖
#   源码运行：settings.py 直接改 config.py
#   exe 运行：settings.py 写 user_config.json，这里读它覆盖默认值
# ================================================================
USER_CONFIG_FILE = os.path.join(BASE_DIR, "user_config.json")
SNAPSHOT_INITIALIZED = True

if os.path.exists(USER_CONFIG_FILE):
    try:
        import json as _json
        with open(USER_CONFIG_FILE, "r", encoding="utf-8") as _f:
            _overrides = _json.load(_f)
        for _k, _v in _overrides.items():
            if _k in globals():
                globals()[_k] = _v
    except Exception as _e:
        # 用户配置损坏时忽略，用默认值
        pass