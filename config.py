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

SRC_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    """
    定位随程序分发的资源文件（字体 / 图标 / 头像）。

    查找顺序：
      ① 打包后：exe 所在目录（用户可直接放旁边替换）
      ② 打包后：PyInstaller 单文件解包目录 sys._MEIPASS
      ③ 源码目录（开发时）
    都不存在时返回 ①，方便上层给出准确报错。
    """
    cands = []
    if getattr(sys, 'frozen', False):
        cands.append(os.path.join(BASE_DIR, name))
        mei = getattr(sys, '_MEIPASS', None)
        if mei:
            cands.append(os.path.join(mei, name))
    cands.append(os.path.join(SRC_DIR, name))
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


# ================================================================
# 应用信息
# ================================================================
VERSION     = "1.2.1"
APP_NAME    = "宝可梦同人游戏翻译工具"
APP_TITLE   = f"{APP_NAME}v{VERSION}"

AUTHOR_NAME     = "玛俐大小姐想让我告白"
AUTHOR_GITHUB   = "https://github.com/nevermore-glimpse"
AUTHOR_BILIBILI = ("https://space.bilibili.com/3546602748775226"
                   "?spm_id_from=333.1007.0.0")
AVATAR_FILE     = os.path.join(BASE_DIR, "玛俐大小姐.jpg")

# ---------- 字体 ----------
# 随程序分发的字体文件。打包后会被解包到 sys._MEIPASS；
# 也可直接放在 exe 同目录覆盖。运行时会用 GDI 私有加载，
# 无需在目标机器上安装字体。
FONT_FILE       = resource_path("萝莉体.ttf")
FONT_NAME       = "Lolita"      # TTF 内读不到族名时的兜底


# ---------- 文件（默认，可在运行时覆盖） ----------
INPUT_FILE   = os.path.join(BASE_DIR, "intl.txt")
OUTPUT_FILE  = os.path.join(BASE_DIR, "intl_translated.txt")
CACHE_FILE   = os.path.join(BASE_DIR, "intl_cache.json")
TERM_FILE    = os.path.join(BASE_DIR, "term_dict.py")
CONFLICT_FILE = os.path.join(BASE_DIR, "term_conflicts.json")
REPORT_DIR   = os.path.join(BASE_DIR, "reports")
EXCEL_FILE   = os.path.join(BASE_DIR, "术语表（Glossary）.xlsx")
ICON_FILE    = os.path.join(BASE_DIR, "start.ico")

# ★ 输入文件最多读多少行（含模拟/测试用的翻译文件）。
#   0 或负数 = 不限制。
MAX_INPUT_LINES = 0


# ================================================================
# 运行时上下文
# ================================================================
class Runtime:
    input_file  = INPUT_FILE
    output_file = OUTPUT_FILE
    cache_file  = CACHE_FILE
    conflict_file = CONFLICT_FILE   # ★ 术语冲突记录（与缓存同源）
    last_dir    = BASE_DIR      # ★ 最近一次浏览的目录（GUI 用）

    @classmethod
    def reset(cls):
        cls.input_file  = INPUT_FILE
        cls.output_file = OUTPUT_FILE
        cls.cache_file  = CACHE_FILE
        cls.conflict_file = CONFLICT_FILE
        cls.last_dir    = BASE_DIR

    @classmethod
    def set_input(cls, path):
        cls.input_file = path
        stem = os.path.splitext(os.path.basename(path))[0]
        parent = os.path.dirname(os.path.abspath(path))
        cls.output_file = os.path.join(parent, f"{stem}_translated.txt")
        cls.cache_file  = os.path.join(parent, f"{stem}_cache.json")
        cls.conflict_file = os.path.join(parent, f"{stem}_conflicts.json")
        cls.last_dir    = parent

    @classmethod
    def set_dir(cls, path):
        if path and os.path.isdir(path):
            cls.last_dir = path

    @classmethod
    def save(cls):
        """把当前输入路径 / 最近目录持久化到 .runtime.json"""
        import json
        try:
            with open(os.path.join(BASE_DIR, ".runtime.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"input_file": cls.input_file,
                           "last_dir":   cls.last_dir}, f,
                          ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def load(cls):
        """启动时恢复上次使用的文件与目录（CLI 与 GUI 都会调用）。"""
        import json
        p = os.path.join(BASE_DIR, ".runtime.json")
        if not os.path.exists(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            ld = d.get("last_dir")
            if ld and os.path.isdir(ld):
                cls.last_dir = ld
            ip = d.get("input_file")
            if ip and os.path.exists(ip):
                cls.set_input(ip)
        except Exception:
            pass


Runtime.reset()


# ---------- 编码 ----------
INPUT_ENCODING  = "utf-8-sig"
OUTPUT_ENCODING = "utf-8-sig"

# ---------- 翻译模式 ----------
TRANSLATE_MODE = "ollama"    # "ollama" = 本地 Ollama；"api" = 云端 API（OpenAI 兼容）
API_BASE_URL   = "https://api.deepseek.com"
# ★ 不要把密钥写在这里（config.py 会提交到仓库）！
#   请在「设置」里填写，它会写入 user_config.json（已在 .gitignore 中）。
API_KEY        = ""
API_MODEL      = "deepseek-chat"
API_TIMEOUT    = 120.0

# ---------- Ollama ----------
OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "qwen3.5:4b"
TIMEOUT     = 600.0
NUM_CTX     = 8192
NUM_PREDICT = 2048
TEMPERATURE = 0.25
TOP_P       = 0.9
KEEP_ALIVE  = "30m"
THINK       = False

# ---------- 翻译策略 ----------
SOURCE_LANG      = "西班牙文"
TARGET_LANG      = "简体中文"
BATCH_SIZE       = 12
BATCH_RETRIES    = 2
SINGLE_RETRIES   = 3
CACHE_SAVE_EVERY = 1

# ★ 自适应分批：单批原文总字符超过该值就提前切批，避免超长句撑爆上下文
MAX_BATCH_CHARS  = 2048
# ★ 按长度排序后再分批：同批句子长度接近，输出更稳定、更少截断
SORT_TODO_BY_LEN = True
# ★ 单批注入 prompt 的术语上限
MAX_TERMS_IN_PROMPT = 80
# ★ 模型原样回显原文时视为失败，触发重试
TREAT_ECHO_AS_FAIL = True

# ---------- 换行重排 ----------
REWRAP_ENABLE  = True
WRAP_CHARS_MIN = 15
WRAP_CHARS_MAX = 18
WRAP_MIN_GAP   = 10    # ★ 新增：换行后至少 N 个字才能再次换行

# 空格模式（非 [map*] 区块）：每 8~10 个字符插一个空格
WRAP_SPACE_MIN = 8
WRAP_SPACE_MAX = 10
WRAP_SPACE_MIN_GAP = 5   # ★ 空格重排：插空格后至少 N 字才能再次插

# 特殊行配对：两行头尾匹配的相似度达到该值即视为同一组
# （例如只差一个 <<r>> 控制码的两行），按"保留第一行、替换第二行"处理
PAIR_SIMILARITY_MIN = 0.80

# ---------- 术语 ----------
APPLY_TERMS        = True
ASK_LANG_EACH_TIME = True
# ---------- 玩家名替换 ----------
PLAYER_TOKEN = r"\PN"              # 游戏脚本里的玩家名控制码
PLAYER_PLACEHOLDER = "玛俐大小姐"  # 送模型时的替换文本（含罕见括号，防误伤）

# ---------- 自动术语提取 ----------
AUTO_EXTRACT_TERMS    = True    # 翻译时自动提取专有名词
AUTO_EXTRACT_MIN_LEN  = 3       # 术语最短长度（过滤单字母/双字母）

# ---------- 云端 API 保护 ----------
# ★ 单次请求的 max_tokens 上限（防止把 NumPredict 直接透传给云端导致 400）
#   多数 OpenAI 兼容服务上限 4K~8K；DeepSeek：chat 8K / reasoner 64K
API_MAX_TOKENS = 8192

# ---------- 中文润色重翻 ----------
POLISH_ENABLE      = True    # 启用「中文润色重翻」
POLISH_BATCH_SIZE  = 8
POLISH_TEMPERATURE = 0.35    # 比翻译略高，给润色一点自由度
POLISH_MIN_LEN     = 4       # 短于该长度的译文不润色（多为控制码/拟声词）
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
SNAPSHOT_INITIALIZED = False

if os.path.exists(USER_CONFIG_FILE):
    try:
        import json as _json
        with open(USER_CONFIG_FILE, "r", encoding="utf-8") as _f:
            _overrides = _json.load(_f)
        for _k, _v in _overrides.items():
            if _k in globals():
                globals()[_k] = _v
    except Exception:
        # 用户配置损坏时忽略，用默认值
        pass