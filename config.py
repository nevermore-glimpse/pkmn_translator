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
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------- 文件（默认，可在运行时覆盖） ----------
INPUT_FILE   = os.path.join(BASE_DIR, "intl.txt")
OUTPUT_FILE  = os.path.join(BASE_DIR, "intl_translated.txt")
CACHE_FILE   = os.path.join(BASE_DIR, "intl_cache.json")
TERM_FILE    = os.path.join(BASE_DIR, "term_dict.py")
REPORT_DIR   = os.path.join(BASE_DIR, "reports")
EXCEL_FILE   = os.path.join(BASE_DIR, "术语表（Glossary）.xlsx")

# ---------- 检查报告 ----------
CHECK_REPORT = os.path.join(REPORT_DIR, "check_report.txt")


# ================================================================
# 运行时上下文：用户选了别的文件后，通过这里覆盖默认路径
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
        """选了新的输入文件 → 输出/缓存按输入文件名自动派生"""
        cls.input_file = path
        stem = os.path.splitext(os.path.basename(path))[0]
        parent = os.path.dirname(os.path.abspath(path))
        cls.output_file = os.path.join(parent, f"{stem}_translated.txt")
        cls.cache_file  = os.path.join(parent, f"{stem}_cache.json")


Runtime.reset()


# ---------- 其余配置不变 ----------
INPUT_ENCODING  = "utf-8-sig"
OUTPUT_ENCODING = "utf-8-sig"

OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "qwen2.5:7b"
TIMEOUT     = 600
NUM_CTX     = 8192
NUM_PREDICT = 4096
TEMPERATURE = 0.2
THINK       = True

SOURCE_LANG     = "西班牙文"
TARGET_LANG     = "简体中文"
BATCH_SIZE      = 20
BATCH_RETRIES   = 2
SINGLE_RETRIES  = 3
CACHE_SAVE_EVERY = 1

REWRAP_ENABLE  = True
WRAP_CHARS_MIN = 15
WRAP_CHARS_MAX = 17
WRAP_PUNCT     = "。！？!?"
WRAP_DOTS      = 3

APPLY_TERMS = True
ASK_LANG_EACH_TIME = False    # 每次翻译前询问语言；False 则直接用上次的

EXCEL_SOURCE_LANG = "西班牙文"
EXCEL_TARGET_LANG = "简体中文"

# 图标文件：始终指向 BASE_DIR 下的 start.ico
ICON_FILE = os.path.join(BASE_DIR, "start.ico")
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)   # exe 所在目录
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
