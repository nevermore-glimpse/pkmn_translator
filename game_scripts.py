# -*- coding: utf-8 -*-
"""
读游戏脚本的小工具（新菜单 1 用）。

游戏脚本有两种形态，这里都支持：

  · 已解包：``Data/Scripts/**.rb`` 直接读文件；
  · 未解包：``Data/Scripts.rxdata``（rubymarshal 读，脚本源码是 zlib 压缩的）。

只做「取文本 / 找常量」这类**只读**操作，不写任何文件。
"""
import io
import os
import re
import time
import zlib

from rubymarshal.reader import load as _rb_load

from logger import get_logger

log = get_logger("game_scripts")

RXDATA_NAME = "Scripts.rxdata"
BACKUP_NAME = "ScriptsBackup.rxdata"
SCRIPTS_DIR_NAME = "Scripts"


# ================================================================
# 路径
# ================================================================
def data_dir(game_dir):
    return os.path.join(game_dir, "Data")


def scripts_dir(game_dir):
    return os.path.join(data_dir(game_dir), SCRIPTS_DIR_NAME)


def rxdata_path(game_dir):
    return os.path.join(data_dir(game_dir), RXDATA_NAME)


def check_game_root(game_dir):
    """
    校验「游戏根目录」：要有 Data 文件夹，还要有 .exe 启动程序。
    返回 (是否通过, 说明文字)。
    """
    if not game_dir or not os.path.isdir(game_dir):
        return False, "这个文件夹不存在"
    if not os.path.isdir(data_dir(game_dir)):
        return False, "这里没有 Data 文件夹 —— 请选游戏根目录（里面有 Game.exe 和 Data）"
    exes = [f for f in os.listdir(game_dir)
            if f.lower().endswith(".exe")]
    if not exes:
        return False, "这里没有 .exe 游戏启动程序 —— 请选游戏根目录（里面有 Game.exe 和 Data）"
    return True, f"已识别：{exes[0]} + Data"


# ================================================================
# 读脚本源码
# ================================================================
def _string_bytes(value):
    """rubymarshal 读出来的串还原成原始字节（保留 rxdata 里的原始字节）。"""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    text = getattr(value, "text", None)
    if text is None:
        text = str(value)
    for enc in ("latin1", "utf-8"):
        try:
            return text.encode(enc)
        except (UnicodeEncodeError, LookupError):
            continue
    return text.encode("utf-8", "replace")


def _text(value):
    raw = _string_bytes(value)
    for enc in ("utf-8", "cp1252", "latin1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def read_rxdata_texts(path):
    """
    读 Scripts.rxdata → [(标题, 源码文本), ...]；读不了返回空列表。
    只返回「有源码」的条目（章节标记那类空条目会被跳过）。
    """
    try:
        with open(path, "rb") as f:
            obj = _rb_load(f)
    except Exception as e:
        log.warning("读取 %s 失败：%s", path, e)
        return []
    if not isinstance(obj, list):
        return []
    out = []
    for e in obj:
        if not isinstance(e, (list, tuple)) or len(e) < 3:
            continue
        code = _string_bytes(e[2])
        try:
            code = zlib.decompress(code)
        except zlib.error:
            pass
        if not code:
            continue
        out.append((_text(e[1]), code.decode("utf-8", "replace")))
    return out


def iter_script_texts(game_dir):
    """
    遍历游戏脚本 → [(相对路径或标题, 源码文本), ...]。

    ★ 已解包（Data/Scripts 存在）就读目录；否则读 Scripts.rxdata；
      两者都没有时，退回 ScriptsBackup.rxdata（数据源可能更旧，但能读就行）。
    """
    sdir = scripts_dir(game_dir)
    if os.path.isdir(sdir):
        out = []
        for dirpath, _dirnames, filenames in os.walk(sdir):
            for f in sorted(filenames):
                if not f.endswith(".rb"):
                    continue
                p = os.path.join(dirpath, f)
                rel = os.path.relpath(p, sdir).replace("\\", "/")
                try:
                    with io.open(p, "r", encoding="utf-8",
                                 errors="replace") as fp:
                        out.append((rel, fp.read()))
                except OSError as e:
                    log.warning("读 %s 失败：%s", p, e)
        if out:
            return out

    rx = rxdata_path(game_dir)
    if os.path.isfile(rx):
        ent = read_rxdata_texts(rx)
        if len(ent) >= 10:
            return ent
    bak = os.path.join(data_dir(game_dir), BACKUP_NAME)
    if os.path.isfile(bak):
        return read_rxdata_texts(bak)
    return []


# ================================================================
# 找常量
# ================================================================
def essentials_version(game_dir):
    """读游戏里的 Essentials::VERSION（读不到返回 ""）。"""
    rx = re.compile(
        r"module\s+Essentials\b[\s\S]{0,4000}?\bVERSION\s*=\s*[\"']([^\"']+)")
    for _name, text in iter_script_texts(game_dir):
        m = rx.search(text)
        if m:
            return m.group(1).strip()
    return ""


_LANG_BLOCK = re.compile(r"LANGUAGES\s*=\s*\[(.*?)\]", re.S)
_LANG_ITEM = re.compile(r"\[\s*[\"']([^\"']*)[\"']\s*,\s*[\"']([^\"']*)[\"']")


def language_files(game_dir):
    """
    读 Settings::LANGUAGES → [(显示名, 文件名), ...]（读不到返回 []）。

    游戏里长这样：
        LANGUAGES = [
          ["English", "english.dat"],
          ["中文",   "Chinese.dat"],
        ]
    """
    for _name, text in iter_script_texts(game_dir):
        if "LANGUAGES" not in text:
            continue
        m = _LANG_BLOCK.search(text)
        if not m:
            continue
        items = _LANG_ITEM.findall(m.group(1))
        if items:
            return items
    return []


# ================================================================
# 改 Settings 里的语言表（LANGUAGES = [...]）
# ================================================================
_LANG_ARRAY_RE = re.compile(r"^([ \t]*)LANGUAGES\s*=\s*\[", re.M)

# 游戏自带的 LANGUAGES 注释（英）→ 中文。模型没接上时用这份兜底。
_LANG_COMMENT_ZH = [
    "# 游戏里可用语言的列表。每一项是一个数组，包含该语言在游戏中显示的名字，",
    "# 以及这个语言的文件名片段。某个语言会去读取 Data 文件夹下名为",
    "# messages_片段_core.dat 和 messages_片段_game.dat 的语言数据文件",
    "#（如果这两个文件存在的话）。",
]


def script_sources(game_dir):
    """
    列出游戏脚本 → [(mode, key, path, text)]
      mode="file"   key = 相对 Data/Scripts 的路径，path = 真实文件
      mode="rxdata" key = 条目下标，          path = Scripts.rxdata
    ★ 已解包就读目录，否则读 rxdata（两种都能改，只是落盘方式不同）。
    """
    sdir = scripts_dir(game_dir)
    if os.path.isdir(sdir):
        out = []
        for dp, _dn, fs in os.walk(sdir):
            for f in sorted(fs):
                if not f.endswith(".rb"):
                    continue
                p = os.path.join(dp, f)
                try:
                    with io.open(p, "r", encoding="utf-8",
                                 errors="replace") as fp:
                        out.append(("file",
                                    os.path.relpath(p, sdir).replace("\\", "/"),
                                    p, fp.read()))
                except OSError as e:
                    log.warning("读 %s 失败：%s", p, e)
        if out:
            return out
    rx = rxdata_path(game_dir)
    if os.path.isfile(rx):
        ents = read_rxdata_texts(rx)
        return [("rxdata", i, rx, t) for i, (n, t) in enumerate(ents) for _ in [0]]
    return []


def find_languages_source(game_dir):
    """找到写着 `LANGUAGES = [` 的那份脚本（找不到返回 None）。"""
    for mode, key, path, text in script_sources(game_dir):
        if "LANGUAGES" not in text:
            continue
        m = _LANG_ARRAY_RE.search(text)
        if m:
            return {"mode": mode, "key": key, "path": path, "text": text,
                    "match": m}
    return None


def _array_block(text, start):
    """
    从 `LANGUAGES = [` 的左括号起，按括号配对取出整个数组的文本。
    返回 (左括号下标, 右括号下标)。
    """
    i = text.index("[", start - 1) if text[start - 1] != "[" else start - 1
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i, j
    return i, -1


def _indent_of(text, line_start):
    """某一行前面的缩进。"""
    bol = text.rfind("\n", 0, line_start) + 1
    return text[bol:line_start]


def _patch_languages(text, display, fragment, comment_zh=None):
    """
    在 LANGUAGES 数组里加一条，并在上方注释后面补一段中文说明。
    返回 (新文本, info)。已经存在同名的条目就不动。
    """
    m = _LANG_ARRAY_RE.search(text)
    if not m:
        raise ValueError("这份脚本里没有 `LANGUAGES = [`")
    lb, rb = _array_block(text, m.end())
    if rb < 0:
        raise ValueError("LANGUAGES 数组没有闭合的 `]`")
    body = text[lb + 1:rb]

    info = {"display": display, "fragment": fragment, "added": False,
            "comment": False}
    # ① 已经有这个语言片段就不重复加
    for item in re.finditer(
            r"\[\s*[\"']([^\"']*)[\"']\s*,\s*[\"']([^\"']*)[\"']\s*\]", body):
        if item.group(2).strip().lower() == (fragment or "").lower():
            info["exists"] = item.group(1)
            return text, info

    # ② 上方注释：在原英文注释**后面**补一段中文说明
    zh = list(comment_zh) if comment_zh else list(_LANG_COMMENT_ZH)
    lines = text.split("\n")
    li = text.count("\n", 0, m.start())          # LANGUAGES 所在行号
    k = li - 1
    while k >= 0 and lines[k].strip() == "":
        k -= 1
    if k >= 0 and lines[k].lstrip().startswith("#"):
        # 缩进跟英文注释保持一致
        cind = re.match(r"[ \t]*", lines[k]).group(0)
        lines[k + 1:k + 1] = ([f"{cind}# [pkmn] 中文说明："] +
                              [cind + "# " + l.lstrip("# ").rstrip()
                               for l in zh])
        info["comment"] = True
        text = "\n".join(lines)
        m = _LANG_ARRAY_RE.search(text)
        lb, rb = _array_block(text, m.end())
        body = text[lb + 1:rb]

    # ③ 照现有条目的写法插入（缩进 + 引号风格），并补好上一行的逗号
    sample = re.search(r"([ \t]*)\[\s*([\"'])", body)
    quote = sample.group(2) if sample else '"'
    body_lines = body.split("\n")
    last_i = max((i for i, l in enumerate(body_lines) if l.strip()),
                 default=len(body_lines) - 1)
    ind = re.match(r"[ \t]*", body_lines[last_i]).group(0) or "    "
    line = f"{ind}[{quote}{display}{quote}, {quote}{fragment}{quote}]"
    if not body_lines[last_i].rstrip().endswith(","):
        body_lines[last_i] = body_lines[last_i].rstrip() + ","
    body_lines.insert(last_i + 1, line)
    # 收尾：] 单独一行，缩进与 LANGUAGES 那行一致
    while body_lines and body_lines[-1].strip() == "":
        body_lines.pop()
    body_lines.append(re.match(r"[ \t]*", text[m.start():]).group(0))
    new_body = "\n".join(body_lines)
    if not new_body.startswith("\n"):
        new_body = "\n" + new_body
    info["added"] = True
    return text[:lb + 1] + new_body + text[rb:], info


def languages_comment(game_dir):
    """
    取 LANGUAGES 上方那段英文注释（用来交给模型翻成中文）。
    找不到返回 []。
    """
    src = find_languages_source(game_dir)
    if not src:
        return []
    m = src["match"]
    lines = src["text"].split("\n")
    li = src["text"].count("\n", 0, m.start())
    k = li - 1
    while k >= 0 and lines[k].strip() == "":
        k -= 1
    if k < 0 or not lines[k].lstrip().startswith("#"):
        return []
    end = k
    while end >= 0 and lines[end].lstrip().startswith("#"):
        end -= 1
    return [lines[i].strip() for i in range(end + 1, k + 1)]


def apply_languages_entry(game_dir, display="简体中文", fragment=None,
                          comment_zh=None, emit=None):
    """
    把一条语言写进游戏 Settings 的 LANGUAGES，并在上方注释后面补中文说明。
    返回 {"ok", "changed", "mode", "where", "backup", ...}

    ★ 两种脚本形态都能改：已解包的改 .rb 文件；没解包的直接改 Scripts.rxdata
      （脚本源码在里面是 zlib 压缩的，改完再压回去）。都先备份再写。
    """
    def say(msg):
        if emit:
            emit(msg)

    src = find_languages_source(game_dir)
    if not src:
        return {"ok": False, "reason": "在脚本里没找到 LANGUAGES（Settings）"}
    frag = fragment or language_fragment(game_dir)
    try:
        new_text, info = _patch_languages(src["text"], display, frag,
                                          comment_zh)
    except ValueError as e:
        return {"ok": False, "reason": str(e)}
    out = {"ok": True, "mode": src["mode"], "where": str(src["key"]),
           "display": display, "fragment": frag, **info}
    if not info.get("added"):
        say(f"[语言] Settings 里已经有「{info.get('exists') or display}」，"
            f"不用再改")
        out["changed"] = False
        return out

    path = src["path"]
    bak = f"{path}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
    out["backup"] = bak
    if src["mode"] == "file":
        with open(path, "rb") as f:
            raw = f.read()
        with open(bak, "wb") as f:
            f.write(raw)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
    else:
        with open(path, "rb") as f:
            obj = _rb_load(f)
        with open(bak, "wb") as f:
            f.write(open(path, "rb").read())
        idx = src["key"]
        entry = obj[idx]
        code = zlib.compress(new_text.encode("utf-8"))
        entry[2] = code
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            from rubymarshal.writer import write as _w
            _w(f, obj)
        os.replace(tmp, path)
    out["changed"] = True
    say(f"[语言] Settings 已加入 [\"{display}\", \"{frag}\"]"
        + ("，并补了一段中文注释" if info.get("comment") else ""))
    say(f"[语言] 改动位置：{src['mode']} → {src['key']}"
        f"（原文件已备份：{os.path.basename(bak)}）")
    return out


def _is_zh(display):
    low = (display or "").lower()
    return any(k in low for k in ("中文", "chinese", "汉化", "简中", "繁中",
                                  "zh", "cn"))


def language_fragment(game_dir):
    """
    语言「片段」：新方案里就是文件名中间那截（chinese / english …），
    对应 Data/messages_<片段>_core.dat / _game.dat。

    优先用语言表里那条中文的（已经汉化过就沿用原来的文件名），
    没有就按 "chinese"。旧方案把 .dat 后缀去掉后也是同一个词。
    """
    items = language_files(game_dir)
    for display, filename in items:
        if _is_zh(display):
            return _strip_dat(filename)
    for display, filename in items:
        if _is_zh(filename):
            return _strip_dat(filename)
    return "chinese"


def _strip_dat(name):
    low = (name or "").lower()
    return name[:-4] if low.endswith(".dat") else name


def default_language_file(game_dir):
    """
    猜「该写哪个语言文件」：优先显示名里带中文/汉化/Chinese 的那条，
    否则取列表最后一条（惯例上它是正在做的译文），都没有就 Data/Chinese.dat。
    返回绝对路径。
    """
    items = language_files(game_dir)
    pick = None
    for display, filename in items:
        if _is_zh(display):
            pick = filename
            break
    if not pick and len(items) >= 2:
        pick = items[-1][1]
    if not pick:
        pick = "Chinese.dat"
    return os.path.join(data_dir(game_dir), pick)
