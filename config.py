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
    定位随程序分发的资源（文件或目录均可）。

    ★ name 传相对路径时用os.path.join 拼，如
      resource_path(os.path.join("scripts", "essentials_src"))

    查找顺序：
      ① 打包后：exe 所在目录（外置资源放这里 / 用户可直接放旁边替换）
      ② 打包后：PyInstaller 单文件解包目录 sys._MEIPASS（--add-data 内置的资源）
      ③ 源码目录（开发时）
    都不存在时返回 ①，方便上层给出准确报错。

    ★ 打包策略：体积小的资源（字体/图片/图标/指南）用 --add-data 内置；
      体积大的scripts/ 不内置，改由打包脚本拷到 dist 与 exe 同级，
      走① 命中即可。这样 exe 启动时不必解压几十 MB 到 %TEMP%。
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


def resource_dir(name):
    """定位随程序分发的**目录**。找不到时返回 None（区别于 resource_path 会兜底返回）。"""
    for c in (os.path.join(BASE_DIR, name),
              os.path.join(getattr(sys, '_MEIPASS', '') or '', name) if getattr(sys, 'frozen', False) else '',
              os.path.join(SRC_DIR, name)):
        if c and os.path.isdir(c):
            return c
    return None


# ================================================================
# 应用信息
# ================================================================
VERSION     = "1.8.8"
APP_NAME    = "宝可梦同人工具"
APP_TITLE   = f"{APP_NAME} v{VERSION}"

AUTHOR_NAME     = "玛俐大小姐想让我告白"
AUTHOR_GITHUB   = "https://github.com/nevermore-glimpse"
AUTHOR_BILIBILI = ("https://space.bilibili.com/3546602748775226"
                   "?spm_id_from=333.1007.0.0")
# ★ 主页大图 + 全局头像。必须走 resource_path：打包时用
#   --add-data "玛俐大小姐.jpg;." 打进 exe，运行时会解包到 sys._MEIPASS。
#   直接拼 BASE_DIR 的话，onefile 模式下 exe 旁边没有这张图就永远读不到。
#   查找顺序仍是「exe 同目录 → _MEIPASS 解包目录 → 源码目录」，
#   所以玩家想换图，把 jpg 丢到 exe 旁边就能覆盖。
AVATAR_FILE     = resource_path("玛俐大小姐.jpg")

# ---------- 字体 ----------
# 随程序分发的字体文件。打包后会被解包到 sys._MEIPASS；
# 也可直接放在 exe 同目录覆盖。运行时会用 GDI 私有加载，
# 无需在目标机器上安装字体。
FONT_FILE       = resource_path("萝莉体.ttf")
FONT_NAME       = "Lolita"      # TTF 内读不到族名时的兜底

# ---------- LM Studio 操作指南（LM1/LM2/LM3 截图） ----------
# 打包时用 --add-data "LM操作指南;LM操作指南" 打进 exe；
# resource_path 会依次找 exe 同目录 → _MEIPASS 解包目录 → 源码目录，
# 所以也支持把文件夹放在 exe 旁边随时替换。
GUIDE_DIR       = resource_path("LM操作指南")


# ---------- 文件（默认，可在运行时覆盖） ----------
INPUT_FILE   = os.path.join(BASE_DIR, "intl.txt")
OUTPUT_FILE  = os.path.join(BASE_DIR, "intl_translated.txt")
CACHE_FILE   = os.path.join(BASE_DIR, "intl_cache.json")
TERM_FILE    = os.path.join(BASE_DIR, "term_dict.py")
CONFLICT_FILE = os.path.join(BASE_DIR, "term_conflicts.json")
REPORT_DIR   = os.path.join(BASE_DIR, "reports")
EXCEL_FILE   = os.path.join(BASE_DIR, "术语表（Glossary）.xlsx")
# ★ 窗口标题栏图标。--icon=start.ico 只是把图标烧进 exe 文件头，
#   运行时 self.root.iconbitmap() 仍要读真实文件，所以也要 resource_path。
ICON_FILE    = resource_path("start.ico")

# ★ 输入文件最多读多少行（含模拟/测试用的翻译文件）。
#   0 或负数 = 不限制。
MAX_INPUT_LINES = 0


# ================================================================
# 翻译中间文件目录
# ================================================================
# 一次翻译会产生不少「中间文件」：缓存、术语冲突、检查报告……
# 编译文本时其实**只看 `*_translated.txt`**，
# 这些中间文件堆在源文件夹里既乱又容易被误当成源文本。
#
# 所以「翻译整个文件夹」时，工具会在该文件夹下建这么一个子目录，
# 把上面这些中间文件全放进去；源文件夹里只剩「源文件 + 译文」。
# 单文件翻译不建（保持老行为：中间文件跟源文件同目录）。
WORK_DIR_NAME = "翻译中间文件"


def work_dir_for(directory) -> str:
    """给定目录，返回其下**已存在**的「翻译中间文件」夹路径（没有 → ""）。"""
    if not directory:
        return ""
    wd = os.path.join(directory, WORK_DIR_NAME)
    return wd if os.path.isdir(wd) else ""


def aux_dir(file_path, create: bool = False) -> str:
    """
    「中间文件」（缓存 / 冲突 / 占位符 / 报告）该放哪个目录。

      ① file_path 所在目录下已经有「翻译中间文件」夹 → 用它；
      ② create=True → 直接建一个再用；
      ③ 都没有 → 就放 file_path 所在目录（单文件翻译的老行为）。

    ★ 用「目录是否存在」来判断，而不是靠运行时状态 —— 这样菜单 2/4/6/7
      事后单独选一个译文 / 缓存来跑时，也能自己找到那个中间文件夹。
    """
    if not file_path:
        return ""
    d = os.path.dirname(os.path.abspath(file_path))
    wd = work_dir_for(d)
    if wd:
        return wd
    if create and d:
        wd = os.path.join(d, WORK_DIR_NAME)
        try:
            os.makedirs(wd, exist_ok=True)
            return wd
        except OSError:
            pass
    return d


# ================================================================
# 运行时上下文
# ================================================================
class Runtime:
    input_file  = INPUT_FILE
    output_file = OUTPUT_FILE
    cache_file  = CACHE_FILE
    conflict_file = CONFLICT_FILE   # ★ 术语冲突记录（与缓存同源）
    last_dir    = BASE_DIR      # ★ 最近一次浏览的目录（GUI 用）
    plugin_font = ""            # ★ 植入中文插件时用户自选的字体（空=内置萝莉体）
    # ★ 存档编辑（菜单 6）：这两项**分开**记 ——
    #   多数汉化版/移植版的存档不在游戏目录里（常见于 AppData），
    #   所以「读 .dat / PBS 的游戏根目录」和「存档所在文件夹」要能各自选。
    game_root   = ""            # 游戏根目录（读 .dat / PBS 用）
    save_files  = []            # 已选存档文件列表（用户手选，可跨会话记住）

    @classmethod
    def reset(cls):
        cls.input_file  = INPUT_FILE
        cls.output_file = OUTPUT_FILE
        cls.cache_file  = CACHE_FILE
        cls.conflict_file = CONFLICT_FILE
        cls.last_dir    = BASE_DIR
        cls.plugin_font = ""
        cls.game_root   = ""
        cls.save_files  = []

    @classmethod
    def set_input(cls, path):
        cls.input_file = path
        stem = os.path.splitext(os.path.basename(path))[0]
        parent = os.path.dirname(os.path.abspath(path))
        # ★ 译文（编译要用的那份）始终留在源文件夹；中间文件去「翻译中间文件」夹
        cls.output_file = os.path.join(parent, f"{stem}_translated.txt")
        aux = aux_dir(path)
        cls.cache_file  = os.path.join(aux, f"{stem}_cache.json")
        cls.conflict_file = os.path.join(aux, f"{stem}_conflicts.json")
        cls.last_dir    = parent

    @classmethod
    def set_dir(cls, path):
        if path and os.path.isdir(path):
            cls.last_dir = path

    @classmethod
    def set_game_root(cls, path):
        cls.game_root = path if (path and os.path.isdir(path)) else ""
        cls.save()

    @classmethod
    def set_save_files(cls, paths):
        cls.save_files = [p for p in (paths or []) if p and os.path.isfile(p)]
        cls.save()

    @classmethod
    def save(cls):
        """把当前输入路径 / 最近目录持久化到 .runtime.json"""
        import json
        try:
            with open(os.path.join(BASE_DIR, ".runtime.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"input_file": cls.input_file,
                           "last_dir":   cls.last_dir,
                           "plugin_font": cls.plugin_font,
                           "game_root":  cls.game_root,
                           "save_files": cls.save_files}, f,
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
            pf = d.get("plugin_font")
            if pf and os.path.isfile(pf):
                cls.plugin_font = pf
            gr = d.get("game_root")
            if gr and os.path.isdir(gr):
                cls.game_root = gr
            sfl = d.get("save_files")
            if isinstance(sfl, list):
                cls.save_files = [p for p in sfl if isinstance(p, str)
                                  and os.path.isfile(p)]
        except Exception:
            pass


Runtime.reset()


# ---------- 编码 ----------
INPUT_ENCODING  = "utf-8-sig"
OUTPUT_ENCODING = "utf-8-sig"

# ---------- 翻译模式 ----------
# "ollama" = 本地服务 / "api" = 云端服务（协议由 PROVIDER 决定）
TRANSLATE_MODE = "ollama"
API_BASE_URL   = "http://localhost:8080/v1"
# ★ 不要把密钥写在这里（config.py 会提交到仓库）！
#   请在「设置」里填写，它会写入 user_config.json（已在 .gitignore 中）。
API_KEY        = ""
API_MODEL      = "qwen3.5-4b"
API_TIMEOUT    = 600.0

# ---------- 本地服务提供商（菜单 10 用） ----------
# ollama / llamacpp / lmstudio / custom
# 三档本地服务共用一套本地通用配置，切换只换地址与各自的模型名
PROVIDER         = "llamacpp"
# 设置页显示哪一侧参数："local" = 本地服务 / "cloud" = 云端服务
UI_MODE          = "local"
LLAMACPP_URL     = "http://127.0.0.1:8080/v1"
LLAMACPP_MODEL   = ""    # llama.cpp 上次用的模型名（llama-server 的 -a 别名）
LMSTUDIO_URL     = "http://localhost:1234/v1"
LMSTUDIO_MODEL   = ""    # LM Studio 上次用的模型名
CUSTOM_OPENAI_URL = "http://localhost:8080/v1"
CUSTOM_MODEL     = ""    # 自定义 OpenAI 兼容端上次用的模型名

# ---------- llama.cpp（菜单 10 中层用） ----------
# ★ 保持空值：由用户在界面里选自己的目录，不把个人路径写进仓库
LLAMACPP_DIR        = ""    # llama-server.exe 所在文件夹
LLAMACPP_MODEL_DIR  = ""    # 存放 GGUF 的文件夹（会自动扫描）
LLAMACPP_MODEL_PATH = ""    # 选中要加载的那个 GGUF 文件

# ★ 上一个使用的提供商（内部状态位，只写 user_config.json）
PROVIDER_PREV    = "ollama"

# ---------- Ollama ----------
OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "qwen3.5:4b"
TIMEOUT     = 600.0
NUM_CTX     = 8192
NUM_PREDICT = 4096
TEMPERATURE = 0.4
TOP_P       = 0.8
KEEP_ALIVE  = "30m"
THINK       = False
# ★ OpenAI 兼容端（llama.cpp / LM Studio / 自定义）怎么关推理模式：
#   本地服务不认 Ollama 的 think 参数，改为在请求里带 reasoning_effort=none。
#   实测 LM Studio：不关时 token 全被思考过程吃掉，译文直接是空的。
#   极少数云端服务不接受这个字段时，把它改成 False 即可。
NO_REASONING = True

# ---------- 本地模型的内存占用（长跑越用越多的问题） ----------
# LM Studio 请求里带的 ttl（秒）：模型空闲这么久就自动从内存卸载。
#   · LM Studio 的 JIT 加载默认 TTL 是 60 分钟，模型与它的缓存会一直占着
#     内存不放；每跑完一轮翻译能自己还回去，才不至于越积越多。
#   · 每次请求都会重置计时，翻译进行中不会卸载。
#   · 设 0 = 不带这个字段（保持 LM Studio 自己的默认行为）。
LMSTUDIO_TTL = 600

# ---------- 翻译策略 ----------
SOURCE_LANG      = "西班牙文"
TARGET_LANG      = "简体中文"
# 每批条数上限；实际批大小由下面的上下文预算决定
BATCH_SIZE       = 200
BATCH_RETRIES    = 2
SINGLE_RETRIES   = 0
CACHE_SAVE_EVERY = 1

# ---------- 自适应分批（按上下文预算切批）----------
# 每批占用 = system + 术语块 + 正文 + 预留输出，按 token 估算求和
# CTX_LIMIT：模型上下文窗口，0 = 自动（按服务提供商预设 → NUM_CTX）
# CTX_BUDGET_RATIO：预算占窗口比例，0.9 = 占到 90% 就切批
CTX_LIMIT        = 0
CTX_BUDGET_RATIO = 0.9
# 预留输出 = 原文 token × 倍数 + 每条固定开销
CTX_OUTPUT_RATIO = 1.5
CTX_OUTPUT_OVERHEAD = 8
# 缺失 / 回显的单句是否记为失败（保留原文 + 进检查报告）
TREAT_ECHO_AS_FAIL = True
# ---------- 缺失 / 回显汇总与自动重翻 ----------
# 翻译时「缺失 / 回显」不再逐条打日志，只汇总成一条；超过这个条数则
# 把这些句子一起（删缓存后）重翻一次。0 = 关闭自动重翻。
ECHO_RETRANSLATE_OVER = 10
# ---------- 每个文件翻完立刻自动刷新报告 + 重翻 ----------
# 翻完一个文件就对本文件跑一次检查（等同「刷新报告」），再按报告里
# 所有可重翻的问题类型各重翻一遍。
AUTO_CHECK_AFTER_FILE = True
# 自动重翻的轮数（2 = 每类问题句子各重翻两次）
AUTO_CHECK_ROUNDS = 2
# 已废弃：自适应分批后不参与切批，仅保留读取
MAX_BATCH_CHARS  = 4096
MAX_BATCH_TOKENS = 2048
# 单批注入 prompt 的术语上限
MAX_TERMS_IN_PROMPT = 1000

# ---------- 并发与多 API Key（借鉴 LinguaGacha 自适应调度） ----------
# 翻译并发批数。0 = 自动（云端服务 4，本地服务 1）
TRANSLATE_CONCURRENCY = 1
# 并发自适应：请求成功逐步 +1、遇到 429 减半（在 CONCURRENCY_MIN~MAX 之间）。
AUTO_CONCURRENCY = True
CONCURRENCY_MIN = 1
# 云端服务最高并发：自适应 +1 的上限，也钳制手动设置的值
CONCURRENCY_MAX = 300
# 本地服务最高并发：钳制手动设置的值；自动模式下本地默认串行
LOCAL_CONCURRENCY_MAX = 16
# 多 API Key：每行一个，轮询使用；某个 Key 连续失败按阶梯冷却，
# 冷却中的 Key 不占并发槽。留空则只用 API_KEY 单 key。
API_KEYS = ""
# 单个 Key 连续失败后的冷却阶梯（秒）：第 1 次失败冷却 15s，第 2 次 30s…
KEY_COOLDOWN_STEPS = [15, 30, 60]

# ---------- 提示词 ----------
# 输出格式固定为 jsonline：每行 {"id":N,"text":"译文","terms":{...}}。
#   · 逐行 JSON 比两行制 <编号> 格式好解析、模型也更少漏行；
#   · 术语内联提取放进 terms 字段（原 tag 格式的 @@T: 行已废弃）。
# 提示词模板目录（相对 resource_path）。按目标语言分子目录覆盖：
#   prompts/{zh,en,ja,...}/xxx.txt 优先于 prompts/xxx.txt
# 文件缺失时用 translator.py 里的内置默认模板，行为不变。
PROMPT_DIR = "prompts"
# True 时在 system prompt 末尾追加 <why> 结构化思考块（语境/决策），
# 让模型翻译前先想清楚指代和难点；会略增输出 token。
THINKING_BLOCK = False

# ---------- 译前 / 译后替换（借鉴 LinguaGacha Replacement） ----------
# 规则文件：JSON 数组，每项 {"src","dst","regex","info"}。
# 译前替换发生在「保护控制码之前」，译后替换发生在「还原占位符之后」。
# 留空 = 用内置 replacements/{pre,post}_default.json。
PRE_REPLACEMENT_FILE  = ""
POST_REPLACEMENT_FILE = ""
# ★ 预设（replacements/pre、replacements/post 下**一个文件一个预设**）：
#   留空 = 目录下全部启用；填 "01_中文排版,02_别的" = 只启用这几个（按填写顺序）。
#   文件名前缀（01_、02_…）决定执行顺序。
PRE_REPLACEMENT_PRESETS  = ""
POST_REPLACEMENT_PRESETS = ""
PRE_REPLACEMENT_ENABLE  = False
POST_REPLACEMENT_ENABLE = True

# ---------- 术语命中统计 ----------
# 翻译时累计每条术语被命中多少次，结束写 terms_stats.json（aux 目录），
# 用来发现「提取了但游戏里根本没出现」的废术语和真正高频的核心术语。
TERM_STATS_ENABLE = False

# ---------- 预过滤（借鉴 LinguaGacha prefilter） ----------
# 剥离控制码后**不含源语言字符**的行不送模型（数字串、纯符号行、
# 他国语言残留行），直接按原文缓存——省 token 也省报告噪音。
PREFILTER_ENABLE = True

# ---------- 换行重排 ----------
REWRAP_ENABLE  = True
WRAP_CHARS_MIN = 15
WRAP_CHARS_MAX = 18
WRAP_MIN_GAP   = 10    # ★ 新增：换行后至少 N 个字才能再次换行

# 空格模式（非 [map*] 区块）：每 8~10 个字符插一个空格
WRAP_SPACE_MIN = 8
WRAP_SPACE_MAX = 10
WRAP_SPACE_MIN_GAP = 5   # ★ 空格重排：插空格后至少 N 字才能再次插

# 特殊行配对：两行的「相同部分占整句的百分比」达到该值即视为同一组
# （差异出现在句子哪个位置都算），按"保留第一行、替换第二行"处理。
# 例：只差一个 <<r>> 控制码的两行、或模板句里只改了中间一项的两行。
PAIR_SIMILARITY_MIN = 0.70

# ---------- 术语 ----------
APPLY_TERMS        = True
# ★ 整句术语直译（默认开）：整句就是一条**手工维护**的术语时（只忽略首尾
#   标点），翻译前直接把术语译文写进缓存，不送模型。
#   例：原文 "Defensa X" / "¡Defensa X!" → 直接用术语表里的「防御强化」。
#   自动提取（AUTO 块）的术语不参与，避免模型瞎提取的词条被当成整句译文。
WHOLE_TERM_MATCH   = True
# ★ 词根派生匹配（默认开）：整词查不到时按「词根 + 常见后缀」再试一次，
#   例如 Altaria=七夕青鸟 也能覆盖 Altarianite / Altarianites 这类派生词。
#   命中的术语只注入 prompt（不改译文），词根与后缀白名单见 processor.py。
TERM_DERIVED_MATCH = True
ASK_LANG_EACH_TIME = True

# ---------- 自动术语提取 ----------
# ★ 翻译时**不再**由模型内联提取术语（v1.6.7 起）：改用「游戏汉化 → 术语提取」
#   页从游戏导出的文本文件（*_NAMES / *_NAME）抽名字再翻 ——
#   来源确定、覆盖完整、不干扰翻译 prompt。
#   ★ v1.7.4 起术语提取**就是正常翻译流水线**，分批按 BATCH_SIZE，
#     温度也用正常翻译的 TRANSLATE_TEMPERATURE，故这里不再单列。
AUTO_EXTRACT_MIN_LEN  = 3       # 术语最短长度（过滤单字母/双字母）
TERM_EXTRACT_BATCH    = 40      # 术语提取页「预览」用的显示值（分批按 BATCH_SIZE）

# ---------- 云端服务保护 ----------
# 单次请求的 max_tokens 上限（防止把 NumPredict 直接透传给云端导致 400）
API_MAX_TOKENS =393216

# ---------- Excel ----------
EXCEL_SOURCE_LANG = "西班牙文"
EXCEL_TARGET_LANG = "简体中文"
# 已有 term_dict.py 时：True = 把新术语接在末尾（原有译法不动），
#                     False = 整份覆盖，只留本次 Excel 的内容
EXCEL_APPEND      = True
# ---------- 句首控制码字典 ----------
PREFIX_DICT_ENABLE = True    # 启用句首控制码前缀字典
# ---------- 控制码回退 ----------
# True  = 译文缺失控制码时按原文补回
# False = 不补回，缺失清单原样进检查报告（kind: 控制码回退）
REPAIR_MISSING_CONTROLS = False
# ---------- 文本保护规则（text_preserve） ----------
# 目录名（与 config.py 同级）。规则文件格式与用法见该目录下 README.md。
TEXT_PRESERVE_DIR = "text_preserve"
# 三档模式：
#   off    只用 processor 内置的识别规则（\命令[参数]、单字母、\$ \. \| 等符号码、%1）
#   smart  内置 + 项目自带规则集（text_preserve/base.json、rpgmaker.json）
#   custom smart + 用户自己的 text_preserve/custom.json（同人游戏自定义控制码写这里）
TEXT_PRESERVE_MODE = "smart"

# ---------- 纯控制符过滤 ----------
SKIP_PURE_CONTROL = True    # 剥离控制码后无有效内容的句子跳过翻译
SKIP_SINGLE_LETTER = True   # 整句只有一个字母（A / ñ）的句子原文即译文，不送模型
PURE_CONTROL_MIN_LEN = 2    # 剥离后至少保留多少个字母/汉字才算有内容
# ---------- 资源路径 ----------
# 形如 Graphics/Pictures/battleCommandButtons 的行不翻译（翻了引擎找不到资源）
SKIP_PATH_LINES = True
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