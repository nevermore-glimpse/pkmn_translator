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

    ★ 必须按括号配对取整段：`LANGUAGES = \\[(.*?)\\]` 是非贪婪的，多条时
      只会吃到第一条的右括号（Void / 蛋白石 / 绿铀 都是好几条），
      那样算出来的「该写哪个语言文件」会错。
    ★ 被 `#` 注释掉的条目不算 —— 游戏不会加载它。
    """
    for _name, text in iter_script_texts(game_dir):
        if "LANGUAGES" not in text:
            continue
        m = _LANG_ARRAY_RE.search(text)
        if not m:
            continue
        lb, rb = _array_block(text, m.end())
        if rb < 0:
            continue
        body = text[lb + 1:rb]
        clean = "\n".join(ln.split("#", 1)[0] for ln in body.split("\n"))
        items = _LANG_ITEM.findall(clean)
        if items:
            return items
    return []


# ================================================================
# 改 Settings 里的语言表（LANGUAGES = [...]）
# ================================================================
_LANG_ARRAY_RE = re.compile(r"^([ \t]*)LANGUAGES\s*=\s*\[", re.M)

# LANGUAGES 数组里的一条语言：["显示名", "文件名"]（允许被 # 注释掉）
# ★ 末尾的 `\r?` 不能少：老游戏的脚本存在 Scripts.rxdata 里，解出来的源码是
#   CRLF，按 "\n" 切开后每行都带 "\r"，不认它的话带逗号的行一条都匹配不上。
_ENTRY_LINE_RE = re.compile(
    r"^(?P<ind>[ \t]*)(?P<hash>\#\s*)?"
    r"\[\s*(?P<q>[\"'])(?P<display>[^\"']*)(?P=q)\s*,\s*"
    r"(?P<q2>[\"'])(?P<frag>[^\"']*)(?P=q2)\s*\]\s*"
    r"(?P<tail>,?)[ \t]*\r?$")


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


def _patch_languages(text, display=None, fragment=None):
    """
    在 LANGUAGES 数组里加一条中文语言。做法（按需求定的三步）：

      ① 数组里第一条语言如果被注释掉了（`#  ["English","english.dat"]`），
         先把 `#` 去掉；
      ② 把这一行**复制一份**插到它下面；
      ③ 复制出来的那一行里 `English` → `Chinese`。

    于是
        LANGUAGES = [
          ["English","english.dat"]
        ]
    变成
        LANGUAGES = [
          ["English","english.dat"],
          ["Chinese","english.dat"]
        ]

    ★ 数组里已经有中文条目（中文 / Chinese / 简中…）就直接跳过，不会重复加。
    返回 (新文本, info)。
    """
    m = _LANG_ARRAY_RE.search(text)
    if not m:
        raise ValueError("这份脚本里没有 `LANGUAGES = [`")
    lb, rb = _array_block(text, m.end())
    if rb < 0:
        raise ValueError("LANGUAGES 数组没有闭合的 `]`")

    info = {"display": "Chinese", "fragment": fragment, "added": False,
            "uncommented": False}
    lines = text.split("\n")
    start_line = text.count("\n", 0, lb)          # "LANGUAGES = [" 所在行
    end_line = text.count("\n", 0, rb)            # "]" 所在行

    entries = []
    for k in range(start_line, min(end_line + 1, len(lines))):
        em = _ENTRY_LINE_RE.match(lines[k])
        if em:
            entries.append((k, em))

    # ① 已经有中文条目 → 不动（幂等）
    for _k, em in entries:
        if _is_zh(em.group("display")):
            info["exists"] = em.group("display")
            return text, info

    if not entries:
        raise ValueError("LANGUAGES 数组里没有可识别的语言条目")

    k0, em0 = entries[0]
    line0 = lines[k0]
    cr = "\r" if line0.endswith("\r") else ""     # 保持原来的行尾风格
    # ② 取消注释：保留缩进，去掉 `#` 和它后面的空白
    if em0.group("hash"):
        body = (em0.group("ind") + line0[em0.end("hash"):]).rstrip()
        info["uncommented"] = True
    else:
        body = line0.rstrip()
    # 数组里每条后面都要有逗号（Ruby 允许最后一条也带逗号）
    if not body.endswith(","):
        body += ","

    # ③ 复制一行，English → Chinese
    dup = body.replace("English", "Chinese")
    if dup == body:
        # 第一条不叫 English（例如 Deutsch）就改第一个引号里的显示名
        dup = re.sub(r"([\"'])[^\"']*\1", r"\1Chinese\1", body, count=1)

    info["added"] = True
    info["template"] = body.strip()
    info["entry"] = dup.strip()
    new_lines = lines[:k0] + [body + cr, dup + cr] + lines[k0 + 1:]
    return "\n".join(new_lines), info


def apply_languages_entry(game_dir, display="简体中文", fragment=None,
                          emit=None):
    """
    把一条语言写进游戏 Settings 的 LANGUAGES。
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
        new_text, info = _patch_languages(src["text"], display, frag)
    except ValueError as e:
        return {"ok": False, "reason": str(e)}
    out = {"ok": True, "mode": src["mode"], "where": str(src["key"]),
           "display": "Chinese", "fragment": frag, **info}
    if not info.get("added"):
        say(f"[语言] Settings 的 LANGUAGES 里已经有「"
            f"{info.get('exists') or '中文'}」，不用再改")
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
    if info.get("uncommented"):
        say("[语言] Settings 里那条语言原本被注释掉了，已去掉 `#`")
    say(f"[语言] Settings 已加入 {info.get('entry') or '[\"Chinese\", …]'}"
        f"（复制第一条并改名）")
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
