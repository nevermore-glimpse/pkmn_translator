# -*- coding: utf-8 -*-
"""
游戏文本的「提取 / 编译」——对应 Essentials 本地化机制里的两步。

游戏 debug 菜单里的做法（代码见 001_Technical/003_Intl_Messages.rb 与
020_Debug/003_Debug menus/003_Debug_MenuExtraCode.rb）：

    提取  MessageTypes.extract("intl.txt")
          读 Data/messages.dat（游戏编译好的**原文**表），写出 intl.txt：
          BOM + 两行说明 + 若干 `[分段]`；
          数组分段每条 3 行（序号 / 原文 / 译文），哈希分段每条 2 行
          （原文 / 译文）。译文行一开始就是原文的副本，逐行替换即可。
    编译  pbCompileText → pbGetText("intl.txt") → Marshal.dump → intl.dat
          把译文表写成一个 .dat，放进 Data/ 并登记到 Settings::LANGUAGES
          就能被游戏读取。

本模块是这两步的 Python 复现（rubymarshal + 标准库），差别只在：
  · 编译可以一次吃多个文本 / 整个文件夹（合并成一份译文表）；
  · 覆盖已有文件前自动备份；
  · 全程离线，不需要进游戏、不需要 debug 模式。
"""
import io
import os
import re
import shutil
import time

from rubymarshal.reader import load as _rb_load
from rubymarshal.writer import write as _rb_write
from rubymarshal.classes import UserDef

import game_scripts as GS
from logger import get_logger

log = get_logger("intl_text")

# 游戏里 MessageTypes 的编号 → 名字（只用于报告，方便看出「哪一类文本」）
TYPE_NAMES = {
    0: "地图/公共事件文本", 1: "宝可梦名", 2: "分类名", 3: "图鉴说明",
    4: "形态名", 5: "招式名", 6: "招式说明", 7: "道具名", 8: "道具复数",
    9: "道具说明", 10: "特性名", 11: "特性说明", 12: "属性名",
    13: "训练家类型", 14: "训练家名", 15: "开场白", 16: "胜利台词",
    17: "失败台词", 18: "地区名", 19: "地点名", 20: "地点说明",
    21: "地图名", 22: "电话文本", 23: "训练家败北文本",
    24: "脚本内文本", 25: "缎带名", 26: "缎带说明",
}

# 游戏读文本表时认的消息文件（按优先级）
MESSAGES_CANDIDATES = ("messages.dat", "english.dat")

_HEADER = ("# To localize this text for a particular language, please\r\n"
           "# translate every second line of this file.\r\n")

# ================================================================
# 两种文本方案
#   legacy（v19/v20 及更早）：一份 Data/messages.dat ↔ 一个 intl.txt
#   split （v21 起）        ：Data/messages_core.dat + messages_game.dat
#                             ↔ Text_<语言>_core/ 与 Text_<语言>_game/
#                             两个文件夹，里面**每个分段一个 txt**
# ================================================================
SCHEME_LEGACY = "legacy"
SCHEME_SPLIT = "split"

# 分段编号 → 游戏里的常量名（新方案导出的文件名就按这个来）
SECTION_NAMES = {
    1: "SPECIES_NAMES", 2: "SPECIES_CATEGORIES", 3: "POKEDEX_ENTRIES",
    4: "SPECIES_FORM_NAMES", 5: "MOVE_NAMES", 6: "MOVE_DESCRIPTIONS",
    7: "ITEM_NAMES", 8: "ITEM_NAME_PLURALS", 9: "ITEM_DESCRIPTIONS",
    10: "ABILITY_NAMES", 11: "ABILITY_DESCRIPTIONS", 12: "TYPE_NAMES",
    13: "TRAINER_TYPE_NAMES", 14: "TRAINER_NAMES",
    15: "FRONTIER_INTRO_SPEECHES", 16: "FRONTIER_END_SPEECHES_WIN",
    17: "FRONTIER_END_SPEECHES_LOSE", 18: "REGION_NAMES",
    19: "REGION_LOCATION_NAMES", 20: "REGION_LOCATION_DESCRIPTIONS",
    21: "MAP_NAMES", 22: "PHONE_MESSAGES", 23: "TRAINER_SPEECHES_LOSE",
    24: "SCRIPT_TEXTS", 25: "RIBBON_NAMES", 26: "RIBBON_DESCRIPTIONS",
    27: "STORAGE_CREATOR_NAME", 28: "ITEM_PORTION_NAMES",
    29: "ITEM_PORTION_NAME_PLURALS", 30: "POKEMON_NICKNAMES",
}

# 新方案里分段之间的分隔线（游戏自己写的）
_SEP = "\r\n#-------------------------------\r\n"

# 语言「片段」（chinese / english …）→ 显示名的默认写法
_DEFAULT_FRAGMENT = "chinese"


def detect_scheme(game_dir):
    """
    判断这个游戏用哪套文本方案。返回 dict：

      scheme = "split"  → core/game 两份 dat，导出成两个 Text_xxx_*/ 文件夹
      scheme = "legacy" → 单份 messages.dat，导出成一个 intl.txt
    """
    data = GS.data_dir(game_dir)
    core = os.path.join(data, "messages_core.dat")
    game = os.path.join(data, "messages_game.dat")
    if os.path.isfile(core) or os.path.isfile(game):
        return {
            "scheme": SCHEME_SPLIT,
            "core": core if os.path.isfile(core) else None,
            "game": game if os.path.isfile(game) else None,
            "fragment": GS.language_fragment(game_dir),
            "essentials": GS.essentials_version(game_dir),
        }
    src = None
    try:
        src = find_source_messages(game_dir)
    except FileNotFoundError:
        src = None
    return {
        "scheme": SCHEME_LEGACY,
        "source": src,
        "fragment": GS.language_fragment(game_dir),
        "essentials": GS.essentials_version(game_dir),
    }


def _section_file_name(sid):
    """分段编号 → 导出文件名（0 号是地图/公共事件文本，单独叫 EVENT_TEXTS）。"""
    if sid == 0:
        return "EVENT_TEXTS"
    return SECTION_NAMES.get(sid, f"SECTION_{sid}")


def _shown(path, base):
    """给日志用的短路径：不在同一盘符时退回绝对路径。"""
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


# ================================================================
# 文本表的表示
#   游戏里：Array（数组分段）与 OrderedHash（哈希分段，Ruby 自定义类）
#   这里：list 与 OHash（保持插入顺序、允许重复键）
# ================================================================
class OHash:
    """对应游戏里的 OrderedHash（Marshal 里是 u 类型的自定义对象）。"""

    __slots__ = ("pairs",)

    def __init__(self, pairs=None):
        self.pairs = list(pairs or [])

    def __len__(self):
        return len(self.pairs)

    def __repr__(self):
        return f"OHash({len(self.pairs)} 条)"


def _to_python(obj):
    """
    读出来的 .dat 结构 → Python 结构（哈希统一成 OHash）。

    ★ 两种哈希都要认：
        UserDef —— 旧版的 OrderedHash（Marshal 里是 u 类型自定义对象）
        dict    —— 新版（v21）直接用 Ruby 原生 Hash，插入顺序即排列顺序
    """
    if isinstance(obj, dict):
        return OHash([(_as_text(k), None if v is None else _as_text(v))
                      for k, v in obj.items()])
    if isinstance(obj, UserDef):
        raw = _private(obj)
        pairs = []
        try:
            keys, values = _rb_load(io.BytesIO(raw))
            # ★ 键和值都要按文本取：payload 里是**字节串**，直接 str() 会变成
            #   "b'...'" 这样的 repr 文本（踩过）。
            pairs = [(_as_text(k),
                      None if v is None else _as_text(v))
                     for k, v in zip(keys, values)]
        except Exception as e:
            log.warning("解析 OrderedHash 失败：%s", e)
        return OHash(pairs)
    if isinstance(obj, list):
        return [_to_python(x) for x in obj]
    return obj


def _private(user_def):
    data = getattr(user_def, "_private_data", None)
    if data is None:
        data = user_def._dump()
    return data


def _make_ohash(pairs):
    """
    Python 的 [(键, 值), ...] → 游戏认得的 OrderedHash 对象。

    ★ 两个细节都照原版 .dat 的写法来（不然游戏虽然也能读，但文件形态不同）：
      · 键/值写 **UTF-8 字节串**（原文件里的字符串就是不带宽高音标记的字节串）；
      · 对象外面再挂一份 `@keys` ivar —— 原版文件里就是这样写的（Ruby 那份
        Marshal 把 Hash 子类的 @keys 一起写了出来），跟着写可以做到逐字节一致。
    """
    keys = []
    values = []
    for k, v in pairs:
        kb = _as_bytes(k)
        vb = _as_bytes(v)
        # ★ 键和值内容相同时共用同一个对象：游戏那边 stringToKey 没改动文本时
        #   返回的就是同一个串对象，Marshal 会把它写成链接（@ 引用）；
        #   共用对象才能写出与原版一致的字节。
        if kb == vb:
            vb = kb
        keys.append(kb)
        values.append(vb)
    buf = io.BytesIO()
    _rb_write(buf, [keys, values])
    ud = UserDef("OrderedHash")
    ud._load(buf.getvalue())
    ud.attributes = {"@keys": keys}
    return ud


def _as_bytes(value):
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


def _enc(value, with_encoding):
    """
    ★ 新旧两版字符串在 Marshal 里的形态**正好相反**：
        旧版（OrderedHash 那套）：不带宽高音标记的**字节串**（ASCII-8BIT）；
        新版（v21 原生 Hash）  ：带 `E => true`（UTF-8）编码标记的**字符串**。
      写错形态内容虽然一样，但文件会有几十万字节的差别。
    """
    return _as_text(value) if with_encoding else _as_bytes(value)


def _marshal_list(items, with_encoding=False):
    """数组分段：None 保持 None（Marshal 里就是 nil 占位）。"""
    return [None if x is None else _enc(x, with_encoding) for x in items]


def _as_text(value):
    """读出来的值 → 文本（可能是 bytes / RubyString，也可能已经是 str）。"""
    value = _plain(value)
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        for enc in ("utf-8", "cp1252", "latin1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "replace")
    return str(value)


# ================================================================
# 游戏那套转义 / 归一化（Messages.normalizeValue / stringToKey）
# ================================================================
_NORMALIZE_DETECT = re.compile(r"[\r\n\t\x01]|^[\[\]]")


def normalize_value(value):
    if _NORMALIZE_DETECT.search(value):
        out = value.replace("\r", "<<r>>").replace("\n", "<<n>>") \
                   .replace("\t", "<<t>>").replace("[", "<<[>>") \
                   .replace("]", "<<]>>").replace("\x01", "<<1>>")
        return out
    return value


_DENORMALIZE_DETECT = re.compile(r"<<[rnt1\[\]]>>")


def denormalize_value(value):
    if _DENORMALIZE_DETECT.search(value):
        return (value.replace("<<1>>", "\x01").replace("<<r>>", "\r")
                .replace("<<n>>", "\n").replace("<<[>>", "[")
                .replace("<<]>>", "]").replace("<<t>>", "\t"))
    return value


_KEY_PAT = re.compile(r"[\r\n\t\x01]|^\s+|\s+$|\s{2,}")


def string_to_key(value):
    """
    游戏 v21 编译时的 `Translation.stringToKey`：含换行/制表/首尾空白/
    连续空格的键会被归一化。**只有新版方案用**（旧版 pbGetText 不归一化）。
    """
    if value and _KEY_PAT.search(value):
        v = re.sub(r"\s{2,}", " ", value.strip())
        return v
    return value


def _plain(value):
    """
    rubymarshal 读出来的字符串有两种：bytes（无编码标记）与 RubyString
    （带编码标记的串）。统一去壳成文本，其它类型原样返回。
    """
    text = getattr(value, "text", None)
    return text if text is not None else value


def _is_empty(value):
    """对应游戏里的 nil_or_empty?：nil 与**空串**都算空。

    ★ 空串要连 bytes 一起认（读出来的值常常是 bytes）——漏了的话，
      空条目会被写成空行，而空行在解析时会被跳过 → 后面所有条目错位。
    """
    value = _plain(value)
    if value is None:
        return True
    if isinstance(value, (str, bytes, bytearray)):
        return len(value) == 0
    if isinstance(value, (list, OHash)):
        return len(value) == 0
    return False


# ================================================================
# 读文本表（messages.dat / 语言 .dat）
# ================================================================
def read_messages(path):
    """读 messages.dat / 语言 .dat → Python 结构（顶层是 list）。"""
    with open(path, "rb") as f:
        obj = _rb_load(f)
    if not isinstance(obj, list):
        raise ValueError(f"{os.path.basename(path)} 顶层不是数组，"
                         f"不像 Essentials 的文本表")
    return [_to_python(x) for x in obj]


def find_source_messages(game_dir, emit=None):
    """
    找「原文表」：优先 Data/messages.dat，其次语言表里的第一份
    （通常是 english.dat）。都找不到就报错说明原因。
    """
    data = GS.data_dir(game_dir)
    for name in MESSAGES_CANDIDATES:
        p = os.path.join(data, name)
        if os.path.isfile(p):
            if emit and name != MESSAGES_CANDIDATES[0]:
                emit(f"[提取] 没有 Data/messages.dat，改用 {name} 作为文本来源")
            return p
    raise FileNotFoundError(
        f"找不到文本来源：{os.path.join(data, 'messages.dat')} 不存在。\n"
        f"这个文件是游戏编译数据时生成的原文表（正式的整合版都会带），"
        f"请确认选的是完整的游戏目录。")


# ================================================================
# 提取：文本表 → intl.txt
# ================================================================
def messages_to_text(messages):
    """
    按游戏 Messages.extract 的规则把文本表写成 intl.txt 的内容。
    返回 (文本, 分段数, 条目数)。
    """
    out = [_HEADER]
    sections = 0
    entries = 0

    def write_section(secname, msgs):
        nonlocal sections, entries
        if msgs is None:
            return
        if isinstance(msgs, list):
            if not any(not _is_empty(x) for x in msgs):
                return
            out.append(f"[{secname}]\r\n")
            sections += 1
            for j, value in enumerate(msgs):
                if _is_empty(value):
                    continue
                text = normalize_value(_as_text(value))
                out.append(f"{j}\r\n{text}\r\n{text}\r\n")
                entries += 1
        elif isinstance(msgs, OHash):
            if not msgs.pairs:
                return
            out.append(f"[{secname}]\r\n")
            sections += 1
            for key, value in msgs.pairs:
                if _is_empty(value):
                    continue
                out.append(f"{normalize_value(_as_text(key))}\r\n"
                           f"{normalize_value(_as_text(value))}\r\n")
                entries += 1

    # 第 0 段：各地图/公共事件的文本（游戏里叫 Map0、Map1…）
    if len(messages) > 0 and messages[0] is not None:
        for i, msgs in enumerate(messages[0]):
            write_section(f"Map{i}", msgs)
    # 其余段：第 i 段的段名就是编号
    for i in range(1, len(messages)):
        write_section(str(i), messages[i])
    return "".join(out), sections, entries


def extract_target(game_dir, scheme=None):
    """
    提取文本的默认输出：
      legacy → <游戏根目录>/intl.txt（与游戏 debug 的 Extract Text 一致）
      split  → <游戏根目录>/Text_<语言>_core/ 与 …/Text_<语言>_game/
    """
    scheme = scheme or detect_scheme(game_dir)
    if scheme.get("scheme") == SCHEME_SPLIT:
        frag = scheme.get("fragment") or _DEFAULT_FRAGMENT
        return os.path.join(game_dir, f"Text_{frag}_core")
    return os.path.join(game_dir, "intl.txt")


# ================================================================
# 新方案（v21）：按分段拆成多个 txt
# ================================================================
def _write_section_file(path, items):
    """
    写一个 txt：BOM + 两行说明 +（多个分段之间用分隔线隔开）+ 条目。

    items = [(段名, 默认文本, 已有译文或 None), ...]
    —— EVENT_TEXTS 会把所有地图段写进同一个文件，所以是列表。
    返回条目数。
    """
    buf = [b"\xef\xbb\xbf",
           b"# To localize this text for a particular language, please\r\n",
           b"# translate every second line of this file.\r\n"]
    entries = 0
    for i, (secname, msgs, lang) in enumerate(items):
        if i > 0:
            buf.append(_SEP.encode("utf-8"))
        buf.append(f"[{secname}]\r\n".encode("utf-8"))
        if isinstance(msgs, list):
            for j, value in enumerate(msgs):
                if _is_empty(value):
                    continue
                cur = lang[j] if (isinstance(lang, list)
                                  and j < len(lang)) else value
                buf.append(f"{j}\r\n{normalize_value(_as_text(value))}\r\n"
                           f"{normalize_value(_as_text(cur))}\r\n"
                           .encode("utf-8"))
                entries += 1
        elif isinstance(msgs, OHash):
            for key, value in msgs.pairs:
                if _is_empty(value):
                    continue
                cur = _hash_lookup(lang, key, value)
                buf.append(f"{normalize_value(_as_text(key))}\r\n"
                           f"{normalize_value(_as_text(cur))}\r\n"
                           .encode("utf-8"))
                entries += 1
    with open(path, "wb") as f:
        f.write(b"".join(buf))
    return entries


def _hash_lookup(lang, key, fallback):
    """在「已有译文」这个 OHash 里按键找值（找不到就用原文）。"""
    if isinstance(lang, OHash):
        for k2, v2 in lang.pairs:
            if _as_text(k2) == _as_text(key):
                return v2
    return fallback


def extract_split(game_dir, fragment=None, out_root=None, emit=None,
                  parts=("core", "game")):
    """
    新方案导出：把 Data/messages_core.dat 与 messages_game.dat 分别导出成
    Text_<语言>_core/ 与 Text_<语言>_game/ 两个文件夹（里面每个分段一个 txt）。

    ★ 已经翻过的部分会带出来：如果 Data/messages_<语言>_core.dat 存在，
      就用它作为「已有译文」，导出的第二行是译文而不是原文。
    """
    def say(msg):
        if emit:
            emit(msg)

    data = GS.data_dir(game_dir)
    frag = fragment or GS.language_fragment(game_dir) or _DEFAULT_FRAGMENT
    root = out_root or game_dir
    report = {"scheme": SCHEME_SPLIT, "fragment": frag, "parts": {},
              "out": root, "sections": 0, "entries": 0, "files": 0}
    data_out = {}
    for part in parts:
        src = os.path.join(data, f"messages_{part}.dat")
        if not os.path.isfile(src):
            say(f"[提取] 跳过 {part}：没有 Data/messages_{part}.dat")
            continue
        lang_src = os.path.join(data, f"messages_{frag}_{part}.dat")
        default_msgs = read_messages(src)
        lang_msgs = (read_messages(lang_src)
                     if os.path.isfile(lang_src) else None)
        if lang_msgs:
            say(f"[提取] {part}：已有译文来自 Data/messages_{frag}_{part}.dat")

        out_dir = os.path.join(root, f"Text_{frag}_{part}")
        os.makedirs(out_dir, exist_ok=True)
        # ★ 只删这个文件夹里的 .txt（游戏也是这么干的），其它文件不动
        for f in sorted(os.listdir(out_dir)):
            if f.lower().endswith(".txt"):
                try:
                    os.remove(os.path.join(out_dir, f))
                except OSError as e:
                    log.warning("删除旧文本失败 %s：%s", f, e)

        files, entries, sections = 0, 0, 0
        for sid in range(len(default_msgs)):
            msgs = default_msgs[sid]
            lm = lang_msgs[sid] if (lang_msgs and sid < len(lang_msgs)) else None
            if sid == 0:
                # 事件文本：所有地图段按 Map000、Map001… 写进同一个文件
                items = []
                for map_id, m in enumerate(msgs or []):
                    if m is None or not len(m):
                        continue
                    mlm = lm[map_id] if (isinstance(lm, list)
                                         and map_id < len(lm)) else None
                    items.append((f"Map{map_id:03d}", m, mlm))
                if not items:
                    continue
                path = os.path.join(out_dir, "EVENT_TEXTS.txt")
                n = _write_section_file(path, items)
            else:
                if msgs is None or not len(msgs):
                    continue
                path = os.path.join(out_dir, _section_file_name(sid) + ".txt")
                n = _write_section_file(path, [(str(sid), msgs, lm)])
            if n:
                files += 1
                entries += n
                sections += max(1, len(items) if sid == 0 else 1)
        report["parts"][part] = {"dir": out_dir, "files": files,
                                "entries": entries}
        report["files"] += files
        report["entries"] += entries
        report["sections"] += sections
        say(f"[提取] {part}：{files} 个文件 / {entries} 条 → "
            f"{_shown(out_dir, game_dir)}")
        data_out[part] = out_dir
    report["dirs"] = data_out
    say(f"[提取] 共 {report['files']} 个文件、{report['entries']} 条；"
        f"翻译时**只改每个条目的最后一行**")
    return report


def extract_text(game_dir, out_path=None, emit=None, backup=True):
    """
    提取文本。返回报告 dict。

    ★ 自动按游戏版本选方案：
        legacy → 单个 intl.txt
        split  → Text_<语言>_core/ 与 Text_<语言>_game/ 两个文件夹
    ★ 已存在时（backup=True）先备份再写 ——
      「要不要覆盖」由调用方（界面/命令行）先问过用户。
    """
    def say(msg):
        if emit:
            emit(msg)

    scheme = detect_scheme(game_dir)
    if scheme["scheme"] == SCHEME_SPLIT:
        say(f"[提取] 这个游戏是新版方案（Essentials "
            f"{scheme.get('essentials') or '≥21'}）："
            f"文本分 core / game 两份，导出成两个文件夹")
        return extract_split(game_dir, out_root=out_path, emit=emit)

    src = find_source_messages(game_dir, emit=emit)
    say(f"[提取] 文本来源：{_shown(src, game_dir)}"
        f"（{os.path.getsize(src):,} 字节）")
    messages = read_messages(src)
    text, sections, entries = messages_to_text(messages)

    out = out_path or extract_target(game_dir)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    bak = None
    if os.path.isfile(out) and backup:
        bak = f"{out}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
        shutil.copyfile(out, bak)
        say(f"[提取] 原文件已备份：{os.path.basename(bak)}")
    with open(out, "wb") as f:
        f.write(b"\xef\xbb\xbf")                     # 与游戏一致：写 BOM
        f.write(text.encode("utf-8"))

    kinds = _section_summary(messages)
    say(f"[提取] 已写出 {sections} 个分段、{entries} 条文本 → "
        f"{_shown(out, game_dir)}")
    say(f"[提取] 分布：{kinds}")
    say("[提取] 翻译时**只改每个条目的最后一行**（原样留着上一行），"
        "之后用「编译文本」生成语言文件")
    log.info("提取文本：%s → %s（%d 段 / %d 条）",
             game_dir, out, sections, entries)
    return {"out": out, "backup": bak, "sections": sections,
            "entries": entries, "source": src, "kinds": kinds}


def _section_summary(messages):
    """给出一句「哪类文本各多少条」，让用户对内容有数。"""
    parts = []
    for i, msgs in enumerate(messages):
        if i == 0:
            n = sum(len(m) for m in (msgs or []) if m is not None)
        elif isinstance(msgs, (list, OHash)):
            n = len(msgs)
        else:
            continue
        if n:
            parts.append(f"{TYPE_NAMES.get(i, str(i))} {n}")
    return "、".join(parts[:8]) + ("…" if len(parts) > 8 else "")


# ================================================================
# 编译：intl.txt → 语言 .dat
# ================================================================
_SECTION_LINE = re.compile(r"^\s*\[\s*([^\]]+)\s*\]\s*$")
_SECTION_NAME = re.compile(r"^([Mm][Aa][Pp])?(\d+)$")
_NAME_TO_ID = {v: k for k, v in SECTION_NAMES.items()}
_TEXT_DIR_RE = re.compile(r"^Text_(.+)_(core|game)$", re.I)


def parse_intl_text(text, name="intl.txt", allow_constants=False,
                    normalize_keys=False):
    """
    按游戏的 pbEachIntlSection / pbGetText 规则解析文本 → 结构。

    返回 {段号: 内容}，段号形如 ("map", 12) / (None, 24)；
    内容是 list（数组分段）或 OHash（哈希分段）。

    allow_constants：新版方案的分段名是常量名（SPECIES_NAMES 等），
                     打开后会按 SECTION_NAMES 换算成编号。
    normalize_keys ：新版方案编译时会把哈希的键再过一遍 stringToKey
                     （旧版 pbGetText 不会），往返一致性要求必须跟着做。
    """
    lines = text.split("\n")
    sections = []
    current = None
    for idx, raw in enumerate(lines):
        line = raw.rstrip("\r")
        if idx == 0 and line.startswith("\ufeff"):
            line = line[1:]
        if idx == 0 and line[:3] == "\xef\xbb\xbf":
            line = line[3:]
        if line.startswith("#") or line.strip() == "":
            continue
        m = _SECTION_LINE.match(line)
        if m:
            if current is not None:
                sections.append(current)
            current = [m.group(1), []]
        else:
            if current is None:
                raise ValueError(
                    f"{name}：第 {idx + 1} 行出现在任何 [分段] 之前 —— "
                    f"文件开头必须先有一个 [分段名]")
            current[1].append(line.rstrip())
    if current is not None:
        sections.append(current)

    out = {}
    for secname, body in sections:
        is_map = False
        sid = None
        m = _SECTION_NAME.match(secname)
        if m:
            is_map = bool(m.group(1))
            sid = int(m.group(2))
        elif allow_constants:
            key = secname.strip().upper()
            if key == "EVENT_TEXTS":
                is_map, sid = False, 0
            elif key in _NAME_TO_ID:
                sid = _NAME_TO_ID[key]
        if sid is None:
            raise ValueError(
                f"{name}：分段名「{secname}」不合法 —— "
                f"只能是数字、Map+数字（如 Map12）"
                + ("或分段常量名（如 SPECIES_NAMES）" if allow_constants
                   else ""))
        if not body:
            continue
        if body[0].isdigit():
            if is_map:
                raise ValueError(f"{name}：Map 分段「{secname}」不能是有序列表"
                                 f"（它的第一行是数字，被当成了有序列表）")
            if len(body) % 3 != 0:
                raise ValueError(
                    f"{name}：分段「{secname}」的行数不是 3 的倍数"
                    f"（{len(body)} 行）—— 每个条目应为「序号/原文/译文」三行")
            items = []
            for i in range(0, len(body), 3):
                if not body[i].isdigit():
                    raise ValueError(
                        f"{name}：分段「{secname}」里第 {i + 1} 行应是序号，"
                        f"实际是「{body[i][:40]}」")
                j = int(body[i])
                while len(items) <= j:
                    items.append(None)
                items[j] = denormalize_value(body[i + 1])
        else:
            if len(body) % 2 != 0:
                raise ValueError(
                    f"{name}：分段「{secname}」条目数不成对（{len(body)} 行）"
                    f"—— 每个条目应为「原文/译文」两行")
            pairs = []
            for i in range(0, len(body), 2):
                k = denormalize_value(body[i])
                if normalize_keys:
                    k = string_to_key(k)
                pairs.append((k, denormalize_value(body[i + 1])))
            items = OHash(pairs)
        key = ("map", sid) if is_map else (None, sid)
        out[key] = items
    return out


def _merge(a, b):
    """把 b 合进 a（同类合并；不同类型用 b 覆盖）。返回冲突条数。"""
    conflicts = 0
    if isinstance(a, list) and isinstance(b, list):
        while len(a) < len(b):
            a.append(None)
        for i, v in enumerate(b):
            if v is None:
                continue
            if a[i] is not None and a[i] != v:
                conflicts += 1
            a[i] = v
        return conflicts
    if isinstance(a, OHash) and isinstance(b, OHash):
        index = {k: i for i, (k, _v) in enumerate(a.pairs)}
        for k, v in b.pairs:
            if k in index:
                if a.pairs[index[k]][1] != v:
                    conflicts += 1
                a.pairs[index[k]] = (k, v)
            else:
                index[k] = len(a.pairs)
                a.pairs.append((k, v))
        return conflicts
    return -1                                  # 类型不同，由调用方覆盖


def collect_text_files(path):
    """
    编译输入 → .txt 文件清单。

    可以是单个文件、一个文件夹（收集里面所有 .txt，按名排序），
    也可以是前面两者的**列表**（界面里多选时用）。
    """
    if isinstance(path, (list, tuple)):
        out = []
        for p in path:
            out.extend(collect_text_files(p))
        seen, uniq = set(), []
        for p in out:
            ap = os.path.abspath(p)
            if ap not in seen:
                seen.add(ap)
                uniq.append(p)
        return uniq
    if os.path.isfile(path):
        return [path]
    if os.path.isdir(path):
        out = []
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in sorted(filenames):
                if f.lower().endswith(".txt"):
                    out.append(os.path.join(dirpath, f))
        return sorted(out)
    raise FileNotFoundError(f"找不到：{path}")


def _default_out(game_dir):
    return GS.default_language_file(game_dir)


# ================================================================
# 新方案的编译：Text_<语言>_core/ → Data/messages_<语言>_core.dat
# ================================================================
def split_targets(game_dir, paths):
    """
    由输入路径推断要写哪几份 .dat → [("chinese", "core", 输出路径), ...]

    认的是文件夹名 `Text_<语言>_<core|game>`；直接选中里面的 txt 也认。
    """
    found = {}

    def add(folder):
        m = _TEXT_DIR_RE.match(os.path.basename(folder))
        if not m:
            return
        frag, part = m.group(1), m.group(2).lower()
        found[(frag, part)] = folder

    for p in paths:
        if os.path.isdir(p):
            if _TEXT_DIR_RE.match(os.path.basename(p)):
                add(p)
            else:                       # 父目录：去里面找 Text_*_core/game
                for sub in sorted(os.listdir(p)):
                    q = os.path.join(p, sub)
                    if os.path.isdir(q):
                        add(q)
        elif os.path.isfile(p):
            add(os.path.dirname(p))
    if not found:
        return []
    data = GS.data_dir(game_dir)
    return [(frag, part, os.path.join(data, f"messages_{frag}_{part}.dat"), d)
            for (frag, part), d in sorted(found.items())]


def compile_split(game_dir, paths, emit=None, backup=True, out_paths=None):
    """
    新方案编译：把 Text_<语言>_core / _game 里的 txt 分别编成
    Data/messages_<语言>_core.dat 与 …_game.dat。
    """
    def say(msg):
        if emit:
            emit(msg)

    targets = split_targets(game_dir, paths if isinstance(paths, (list, tuple))
                            else [paths])
    if not targets:
        raise ValueError(
            "没认出新方案的文本文件夹。\n\n"
            "新版游戏的文本文件夹必须叫 Text_<语言>_core / Text_<语言>_game\n"
            "（例如 Text_chinese_game），或者直接选里面的 txt 文件。")

    report = {"scheme": SCHEME_SPLIT, "outs": [], "files": 0,
              "entries": 0, "conflicts": 0}
    for frag, part, out, folder in targets:
        if out_paths and part in out_paths:
            out = out_paths[part]
        files = sorted(os.path.join(folder, f)
                       for f in os.listdir(folder)
                       if f.lower().endswith(".txt"))
        if not files:
            say(f"[编译] ⚠ {os.path.basename(folder)} 里没有 txt，跳过")
            continue
        say(f"[编译] {part}：{len(files)} 个文本文件")

        merged = {}
        conflicts = 0
        for p in files:
            with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            secs = parse_intl_text(text, os.path.basename(p),
                                   allow_constants=True, normalize_keys=True)
            for key, value in secs.items():
                if key not in merged:
                    merged[key] = value
                    continue
                c = _merge(merged[key], value)
                if c < 0:
                    merged[key] = value
                else:
                    conflicts += c
        if conflicts:
            say(f"[编译] ⚠ {part}：{conflicts} 条在两份文本里不同，"
                f"已按靠后的覆盖")

        max_map = max([k[1] for k in merged if k[0] == "map"], default=-1)
        max_id = max([k[1] for k in merged if k[0] is None], default=-1)
        table = [None] * max(max_id, 0) if (max_id >= 0 or max_map >= 0) else []
        if max_map >= 0:
            if not table:
                table.append(None)
            table[0] = [None] * (max_map + 1)
        for (kind, sid), value in merged.items():
            if kind == "map":
                if table[0] is None:
                    table[0] = [None] * (sid + 1)
                while len(table[0]) <= sid:
                    table[0].append(None)
                table[0][sid] = _marshal_value(value, plain_hash=True,
                                               with_encoding=True)
            else:
                while len(table) <= sid:
                    table.append(None)
                table[sid] = _marshal_value(value, plain_hash=True,
                                            with_encoding=True)

        bak = None
        if os.path.isfile(out) and backup:
            bak = f"{out}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
            shutil.copyfile(out, bak)
            say(f"[编译] 原文件已备份：{os.path.basename(bak)}")
        tmp = out + ".tmp"
        with open(tmp, "wb") as f:
            _rb_write(f, table)
        os.replace(tmp, out)

        entries = sum(len(v) for v in merged.values())
        report["outs"].append({"part": part, "fragment": frag, "out": out,
                               "backup": bak, "files": len(files),
                               "entries": entries})
        report["files"] += len(files)
        report["entries"] += entries
        report["conflicts"] += conflicts
        say(f"[编译] 已写出 {entries} 条 → messages_{frag}_{part}.dat"
            f"（{os.path.getsize(out):,} 字节）")
    return report


def compile_text(game_dir, input_path, out_path=None, emit=None, backup=True):
    """
    编译文本：把 intl 格式的文本（或整个文件夹里的 .txt 合并）写成语言 .dat。

    ★ 自动按游戏版本选方案：新版会按 Text_*_core / _game 分别编出两份 .dat。

    返回报告 dict：{"out", "backup", "files", "entries", "conflicts", ...}
    """
    def say(msg):
        if emit:
            emit(msg)

    paths = input_path if isinstance(input_path, (list, tuple)) else [input_path]
    if split_targets(game_dir, paths):
        say("[编译] 这个游戏是新版方案：按 core / game 分别编译")
        return compile_split(game_dir, paths, emit=emit, backup=backup)

    files = collect_text_files(input_path)
    if not files:
        raise FileNotFoundError(f"{input_path} 里没有 .txt 文本文件")
    if len(files) > 1:
        say(f"[编译] 共 {len(files)} 个文本文件，按文件名顺序合并")

    merged = {}          # (kind, id) → list/OHash
    per_file = []
    conflicts = 0
    for p in files:
        try:
            with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            raise IOError(f"读取 {p} 失败：{e}") from e
        secs = parse_intl_text(text, os.path.basename(p))
        n = sum(len(v) for v in secs.values())
        per_file.append((os.path.basename(p), len(secs), n))
        say(f"[编译] {os.path.basename(p)}：{len(secs)} 段 / {n} 条")
        for key, value in secs.items():
            if key not in merged:
                merged[key] = value
                continue
            c = _merge(merged[key], value)
            if c < 0:
                say(f"[编译] ⚠ 段 {key[1]} 在不同文件里类型不一致，"
                    f"以靠后的文件为准")
                merged[key] = value
            else:
                conflicts += c
    if conflicts:
        say(f"[编译] ⚠ 有 {conflicts} 条在两份文本里内容不同，"
            f"已按靠后的文件覆盖")

    # 组回「第 0 段是各地图」的结构
    #   ★ 顶层数组长度只看非 map 段（map 段都塞进第 0 段里），
    #     别被地图编号（可能到 288）撑大 —— 否则写出来和游戏自己那份不一样。
    max_map = max([k[1] for k in merged if k[0] == "map"], default=-1)
    max_id = max([k[1] for k in merged if k[0] is None], default=-1)
    table = [None] * (max_id + 1)
    if max_map >= 0:
        table[0] = [None] * (max_map + 1)
    for (kind, sid), value in merged.items():
        if kind == "map":
            if table[0] is None:
                table[0] = [None] * (sid + 1)
            while len(table[0]) <= sid:
                table[0].append(None)
            table[0][sid] = _marshal_value(value)
        else:
            table[sid] = _marshal_value(value)

    out = out_path or _default_out(game_dir)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    bak = None
    if os.path.isfile(out) and backup:
        bak = f"{out}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
        shutil.copyfile(out, bak)
        say(f"[编译] 原文件已备份：{os.path.basename(bak)}")
    tmp = out + ".tmp"
    with open(tmp, "wb") as f:
        _rb_write(f, table)
    os.replace(tmp, out)

    entries = sum(len(v) for v in merged.values())
    say(f"[编译] 已写出 {entries} 条文本 → {_shown(out, game_dir)}"
        f"（{os.path.getsize(out):,} 字节）")
    kinds = _merged_summary(merged)
    if kinds:
        say(f"[编译] 分布：{kinds}")
    log.info("编译文本：%s → %s（%d 段 / %d 条）",
             input_path, out, len(merged), entries)
    return {"out": out, "backup": bak, "files": [f for f, _s, _n in per_file],
            "sections": len(merged), "entries": entries,
            "conflicts": conflicts, "detail": per_file, "kinds": kinds}


def _make_plain_hash(pairs, with_encoding=True):
    """
    新版（v21）用的是 Ruby 原生 Hash —— 直接写 Python dict 即可。
    键/值按新版形态写（带 UTF-8 编码标记的 str）。
    """
    out = {}
    for k, v in pairs:
        kb = _enc(k, with_encoding)
        out[kb] = kb if _as_text(v) == _as_text(k) else _enc(v, with_encoding)
    return out


def _marshal_value(value, plain_hash=False, with_encoding=False):
    """
    plain_hash    ：True = 新版原生 Hash；False = 旧版 OrderedHash 对象
    with_encoding ：True = 字符串带 UTF-8 编码标记（新版）；False = 裸字节串
    """
    if isinstance(value, OHash):
        return _make_plain_hash(value.pairs, with_encoding) if plain_hash \
            else _make_ohash(value.pairs)
    if isinstance(value, list):
        return _marshal_list(value, with_encoding)
    return value


def _merged_summary(merged):
    parts = []
    for (kind, sid), value in sorted(merged.items(),
                                     key=lambda kv: (kv[0][0] or "", kv[0][1])):
        n = len(value)
        if not n:
            continue
        label = TYPE_NAMES.get(sid, str(sid)) if kind is None else "地图事件"
        parts.append(f"{label} {n}")
    return "、".join(parts[:8]) + ("…" if len(parts) > 8 else "")
