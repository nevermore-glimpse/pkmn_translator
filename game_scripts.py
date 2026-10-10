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
from rubymarshal.writer import write as _rb_write

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


# ★ `scripts_dir` / `rxdata_path` / loader-form handling are all defined in
#   the "loader form" section further down (they need to reference each other).


# ================================================================
# 「loader 形态」：Scripts.rxdata 只放一条 load_scripts_from_folder(...)
# ================================================================
#  increasingly many fan games (and several decompiled ports) shrink
#  Scripts.rxdata down to a single bootstrap entry:
#
#      def load_scripts_from_folder(path)
#        Dir.foreach(path) { |f| ... eval(File.read(...)) }
#      end
#      load_scripts_from_folder("Data/export")     # or "Scripts"
#
#  The real scripts then live in a folder that Data/Scripts does not point
#  at — Data/export or <root>/Scripts — and because collect_scripts only
#  recognises Data/Scripts, the tool comes back with "0 scripts found" and
#  every subsequent step (methods 1-5, baseline overwrite) just quietly
#  does nothing.
#
#  The solution: read the top-level call's argument from the rxdata entry,
#  resolve it to an absolute path, and treat that folder as the
#  scripts directory.
_LOADER_CALL_RE = re.compile(r"^load_scripts_from_folder\(\s*(.+?)\s*\)\s*$",
                             re.M)
# Entries fewer than this → it's very likely a loader, not a real script table
_LOADER_MAX_ENTRIES = 10


def _resolve_loader_arg(arg, game_dir):
    """
    Resolve a top-level `load_scripts_from_folder(<arg>)` argument to an absolute path.

    Handles the common ways of writing it:
        "Data/export"  /  'Scripts'  /  "Data/Scripts"
        File.join(Dir.pwd, File.join('Scripts'))
        File.join(Dir.pwd, 'Data', 'export')
    Implementation: pull out all the string literals and join them —
    Dir.pwd has no quotes so it drops out on its own.
    Returns "" when it can't be resolved.
    """
    parts = re.findall(r"['\"]([^'\"]+)['\"]", str(arg or ""))
    # Exclude the recursion inside the function body (load_scripts_from_folder(path + ...))
    if not parts or "folder" in str(arg):
        return ""
    rel = os.path.join(*parts) if len(parts) > 1 else parts[0]
    p = rel if os.path.isabs(rel) else os.path.join(game_dir, rel)
    return os.path.normpath(p)


def _has_rb(d):
    """Does this directory contain a .rb file? (without walking the whole tree)"""
    try:
        for _dp, _dn, fs in os.walk(d):
            for f in fs:
                if f.lower().endswith(".rb"):
                    return True
    except OSError:
        return False
    return False


def loader_scripts_dir(game_dir):
    """
    Loader form: return the absolute path of the folder holding the real
    scripts (no match → "").

    ★ Only when Data/Scripts is absent/empty do we look at the loader —
      games that already have Data/Scripts (the loader points there too)
      keep using the old path, so this doesn't affect them at all.
    """
    rx = rxdata_path(game_dir)
    if not os.path.isfile(rx):
        return ""
    try:
        with open(rx, "rb") as f:
            obj = _rb_load(f)
    except Exception as e:                        # noqa: BLE001
        log.warning("识别 loader 形态时读 %s 失败：%s", rx, e)
        return ""
    if not isinstance(obj, list) or not obj or len(obj) > _LOADER_MAX_ENTRIES:
        return ""
    cands = []
    for e in obj:
        text = rxdata_source(e)
        if "load_scripts_from_folder" not in text:
            continue
        # ★ Only match calls starting at column 0 — the recursive calls
        #   inside the function body are indented.
        for m in _LOADER_CALL_RE.finditer(text):
            p = _resolve_loader_arg(m.group(1), game_dir)
            if p:
                cands.append(p)
    for p in cands:
        if os.path.isdir(p) and _has_rb(p):
            return p
    return ""


def script_dirs(game_dir):
    """
    Directories holding scripts → [absolute path, ...] (loader form aware).

    Normally just [Data/Scripts] (only if there really are .rb files in it);
    otherwise the loader form's target folder.
    """
    d = os.path.join(data_dir(game_dir), SCRIPTS_DIR_NAME)
    if os.path.isdir(d) and _has_rb(d):
        return [d]
    alt = loader_scripts_dir(game_dir)
    return [alt] if alt else []


def scripts_dir(game_dir):
    """
    The scripts directory ("where scripts live / where new ones should be
    written"), loader form aware.

    Most games: Data/Scripts. Loader-form games (recall / Soul Stone / Frost
    …): the folder the loader points at, so add_script_file also lands in
    the right place. Nothing found → still return Data/Scripts (let the
    caller decide whether it exists).
    """
    d = os.path.join(data_dir(game_dir), SCRIPTS_DIR_NAME)
    if os.path.isdir(d) and _has_rb(d):
        return d
    return loader_scripts_dir(game_dir) or d


def _script_file_prefix(game_dir):
    """
    The numeric prefix new script files need in this game's scripts folder.

    ★ The loader form sometimes carries a `next if … || !f[/^\\d{4}/]`
      filter — files whose names don't start with four digits simply
      aren't loaded, so a newly created `Debug_Menus.rb` would never take
      effect. Return that prefix ("4" digits / "") so the caller can
      stick it on when creating a file.

    Implementation: find the file containing Main and copy its prefix
    (new scripts then sort right next to Main).
    """
    dirs = script_dirs(game_dir)
    if not dirs:
        return ""
    rx = rxdata_path(game_dir)
    if not os.path.isfile(rx):
        return ""
    try:
        with open(rx, "rb") as f:
            obj = _rb_load(f)
    except Exception:                             # noqa: BLE001
        return ""
    if not isinstance(obj, list) or len(obj) > _LOADER_MAX_ENTRIES:
        return ""
    joined = "\n".join(rxdata_source(e) for e in obj)
    if not re.search(r"!\s*f\[\s*/\^\\d\{4\}/", joined):
        return ""                                 # no digit filter
    for root in dirs:
        for dp, _dn, fs in os.walk(root):
            for f in sorted(fs):
                m = re.match(r"^(\d{4})", f)
                if m and "main" in f.lower():
                    return m.group(1)
    return "9999"


def script_file_name(game_dir, name, index=1):
    """
    File name for a newly created script → complies with the loader's
    filtering rules and sorts right before Main.

    When Main is `2600 Main.rb`, the 8 debug scripts become
    `2599_01 Debug_Menus.rb` … `2599_08 Debug_FilenameUpdater.rb`
    — ahead of Main, and among themselves in the given order.
    """
    safe = re.sub(r"[^0-9A-Za-z_]", "", str(name)) or "Script"
    base = _script_file_prefix(game_dir)
    if not base:
        return safe + ".rb"
    num = int(base) - 1
    return "%04d_%02d %s.rb" % (max(num, 0), int(index), safe)


def rxdata_path(game_dir):
    return os.path.join(data_dir(game_dir), RXDATA_NAME)


def add_script_file_at(path, source):
    """Write a script file directly to the given absolute path (creating directories)."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(str(source))
    return path


def check_game_root(game_dir, exe=None):
    """
    校验「游戏根目录」：要有 Data 文件夹，还要有 .exe 启动程序。
    返回 (是否通过, 说明文字)。

    exe 传了就用它当「启动程序」（可以是完整路径或文件名），
    没传就在目录里随便找一个 .exe（老行为，保持兼容）。
    """
    if not game_dir or not os.path.isdir(game_dir):
        return False, "这个文件夹不存在"
    if not os.path.isdir(data_dir(game_dir)):
        return False, "这里没有 Data 文件夹 —— 请选游戏根目录（里面有 Game.exe 和 Data）"
    if exe:
        return True, f"已识别：{os.path.basename(exe)} + Data"
    exes = [f for f in os.listdir(game_dir)
            if f.lower().endswith(".exe")]
    if not exes:
        return False, "这里没有 .exe 游戏启动程序 —— 请选游戏根目录（里面有 Game.exe 和 Data）"
    return True, f"已识别：{exes[0]} + Data"


def exe_root(exe_path):
    """
    从「启动程序（exe）」路径推出游戏根目录。

    · 只给文件名 / 相对名 → 目录视为当前工作目录；
    · 给完整路径 → 返回它所在的文件夹（去掉末尾斜杠）。
    返回 (game_dir, exe_name)；无法判断时返回 (None, None)。
    """
    if not exe_path:
        return None, None
    p = os.path.abspath(exe_path)
    d = os.path.dirname(p)
    if not d:
        d = os.getcwd()
    return d, os.path.basename(p)


def verify_game(root, exe=None, need_data=True):
    """
    统一的「选好游戏了吗」校验（菜单 1 / 菜单 11 共用）。

    · root 必须是存在的文件夹（通常由 exe 路径推出）；
    · need_data=True 时 Data 文件夹必须有；False 时允许没有 ——
      **这是给「调试启动器」用的**：它不改游戏本体，脚本打包进 exe、
      或者游戏根本没用 Data 目录，也能开调试；
    · exe 指定时要真实存在，并把它当成启动程序记着。

    返回 (ok, why, root, exe_path, has_data)：
      · ok       —— 通过与否；
      · why      —— 不通过时的原因；
      · root     —— 归一化后的绝对根目录；
      · exe_path —— 归一化后的启动程序完整路径（没给就是 None）；
      · has_data —— 目录里有没有 Data 文件夹。
    """
    if not root:
        return False, "还没选游戏目录", "", None, False
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return False, f"这个文件夹不存在：{root}", root, None, False
    has_data = os.path.isdir(data_dir(root))
    if need_data and not has_data:
        return (False,
                "这里没有 Data 文件夹 —— 请选游戏启动程序（exe）或游戏根目录；"
                "（没有 Data 的话只能用「调试启动器」方式）",
                root, None, False)
    exe_path = None
    if exe:
        # ★ exe 完整路径可能指向 root 之外（tmp 里 os.makedirs 后 os.path.join
        #   在某些路径写法下 root 与 exe 的 dirname 字符串不一致）——以「
        #   exe 真实存在」为准，同时把 root 校准成 exe 所在目录。
        cands = []
        if os.path.isabs(exe):
            cands.append(exe)
            cands.append(os.path.join(root, os.path.basename(exe)))
        else:
            cands.append(os.path.join(root, exe))
            cands.append(exe)
            cands.append(os.path.join(root, os.path.basename(exe)))
        for c in cands:
            if c and os.path.isfile(c):
                exe_path = os.path.abspath(c)
                break
        if not exe_path:
            return (False,
                    f"找不到启动程序：{os.path.basename(exe)}"
                    f"（在 {os.path.basename(root)} 下没这个文件）",
                    root, None, has_data)
        # exe 所在目录才是真·游戏根目录
        root = os.path.dirname(exe_path)
        has_data = os.path.isdir(data_dir(root))
        if need_data and not has_data:
            return (False,
                    "启动程序旁边没有 Data 文件夹 —— 确认选对了吗？"
                    "（没有 Data 的话只能用「调试启动器」方式）",
                    root, exe_path, False)
    return True, "OK", root, exe_path, has_data


def looks_like_payload_folder(root):
    """
    判断 root 是不是「游戏本体的内层目录」（不是真正的游戏根目录）。

    典型症状：用户把 exe 选在了形如 `...\\<游戏名>\\Data\\Game.exe` 的位置，
    而真正的游戏根目录是它的**上一层**。这时：
      · root 自己叫 Data（或含 Audio / Movies / Graphics 这类素材目录）；
      · root 里没有 Data 子目录；
      · root 的上一层挂着启动器 .bat / 或也含 Game.exe。

    返回 True 表示「这看着是内层目录，根目录应该往上找一层」。
    """
    if not root or not os.path.isdir(root):
        return False
    name = os.path.basename(os.path.normpath(root)).lower()
    if name != "data":
        return False
    if os.path.isdir(data_dir(root)):       # 真有 Data 子目录 → 就是根目录
        return False
    parent = os.path.dirname(os.path.abspath(root))
    # 上一层有启动相关的东西，才敢说「根目录在上面」
    try:
        entries = [e.lower() for e in os.listdir(parent)]
    except OSError:
        return True
    if any(e.endswith(".bat") for e in entries):
        return True
    if any(e.endswith(".exe") for e in entries):
        return True
    return False


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


def _decode_script_bytes(raw):
    """
    脚本源码的原始字节 → 文本（zlib 解压 + 解码；空/读不出来返回 ""）。

    ★ Scripts.rxdata 与 PluginScripts.rxdata 里的源码都是
      `Zlib::Deflate.deflate(...)` 压过的，解压用同一个 zlib.decompress。
    """
    code = _string_bytes(raw)
    try:
        code = zlib.decompress(code)
    except zlib.error:
        pass                      # 没压缩就直接用
    if not code:
        return ""
    return code.decode("utf-8", "replace")


def rxdata_source(entry):
    """rxdata 的单个条目 → 源码文本（解压 + 解码；读不出来返回 ""）。"""
    if not isinstance(entry, (list, tuple)) or len(entry) < 3:
        return ""
    return _decode_script_bytes(entry[2])


def rxdata_title(entry):
    """rxdata 的单个条目 → 标题（脚本编辑器左边那一栏的名字）。"""
    if not isinstance(entry, (list, tuple)) or len(entry) < 2:
        return ""
    return _text(entry[1])


def read_rxdata_entries(path):
    """
    读 Scripts.rxdata → (非空条目, 总条目数)

      非空条目 = [(原始下标, 标题, 源码文本), ...]；读不出来时 ([], 0)。

    ★ 只取「有源码」的条目 —— `[[ 章节 ]]` / `======` / 空标题那类纯标记
      会被跳过（它们本来就没有函数）。
    ★ 但下标一律是**它在 rxdata 里的原始位置**，绝不重新编号 ——
      空标记也占位置，「跳空后再 enumerate」得到的小标会整体前移，
      写回时就落到别的条目头上了：POG v2.1.1 的 Main 是第 433 条，
      跳空后成了第 345 条，于是 Main 的代码被写进了空的 `[[ Utilities ]]`，
      表现为「原本没函数的括号脚本，写入后长出了函数」。
    """
    try:
        with open(path, "rb") as f:
            obj = _rb_load(f)
    except Exception as e:
        log.warning("读取 %s 失败：%s", path, e)
        return [], 0
    if not isinstance(obj, list):
        return [], 0
    out = []
    for i, e in enumerate(obj):
        text = rxdata_source(e)
        if not text:
            continue
        out.append((i, rxdata_title(e), text))
    return out, len(obj)



def write_rxdata_entry(path, index, new_text, expect=None):
    """
    把第 index 条脚本的源码换成 new_text（就地写回 Scripts.rxdata）。

    ★ expect 给定时先核对「这一条现在的内容」是否真的等于 expect，
      不等就抛 RuntimeError 拒绝写入。下标一旦算错（被重新编号、
      或读和写之间文件被换过），这道检查能挡住「把 A 脚本的代码
      写进 B 条目」这种会毁工程的损坏 —— 而不是默默写坏。
    备份由调用方负责（各自的备份命名规则不一样）。
    """
    with open(path, "rb") as f:
        obj = _rb_load(f)
    if not isinstance(obj, list) or not 0 <= index < len(obj):
        raise RuntimeError(
            f"脚本下标 {index} 越界（这个文件共 "
            f"{len(obj) if isinstance(obj, list) else 0} 条）")
    if expect is not None:
        cur = rxdata_source(obj[index])
        if cur != expect:
            raise RuntimeError(
                f"要写的是第 {index} 条「{rxdata_title(obj[index])}」，"
                f"但它现在的内容和预期不符（{len(cur)} 字节 ≠ "
                f"{len(expect)} 字节），已拒绝写入")
    obj[index][2] = zlib.compress(new_text.encode("utf-8"))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        _rb_write(f, obj)
    os.replace(tmp, path)


def add_rxdata_script(path, title, source, before_title="Main"):
    """
    往 `Scripts.rxdata` 里**新增**一个脚本条目，返回新条目的下标。

    ★ 条目结构 = `[编号, 标题, zlib 压缩源码]`（和 Essentials 自带的
      `scripts_extract.rb` 里 `_, title, script = e` 对得上）；编号只被
      解包脚本工具忽略，随便取一个没被占用的就行。
    ★ **插在 Main 之前**：`999_Main` 一加载就 `loop do … end` 自己把游戏跑起来了，
      追加到末尾的话新脚本还没定义完游戏就已经开跑 → 必须排在它前面。
      找不到 Main 就追加到末尾。
    """
    with open(path, "rb") as f:
        obj = _rb_load(f)
    if not isinstance(obj, list):
        raise RuntimeError(f"{os.path.basename(path)} 不是脚本列表，放弃新增")
    used = set()
    for e in obj:
        if isinstance(e, (list, tuple)) and e and isinstance(e[0], int):
            used.add(e[0])
    sid = (max(used) + 1) if used else 1
    while sid in used:
        sid += 1
    entry = [sid, str(title).encode("utf-8"),
             zlib.compress(str(source).encode("utf-8"))]
    at = len(obj)
    if before_title:
        want = re.sub(r"[^0-9a-z]+", "", str(before_title).lower())
        for i, e in enumerate(obj):
            if isinstance(e, (list, tuple)) and len(e) >= 2 and \
                    re.sub(r"[^0-9a-z]+", "", _text(e[1]).lower()) == want:
                at = i
                break
    obj.insert(at, entry)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        _rb_write(f, obj)
    os.replace(tmp, path)
    return at


def add_script_file(game_dir, name, source, folder="", index=1):
    """
    往脚本目录下**新增**一个 `.rb` 脚本（已解包 / loader 形态的游戏用）。
    返回文件路径；建不了返回 ""。

    ★ loader 形态（Data/export、根 Scripts）会自动落到 loader 指的那个目录，
      文件名也按 loader 的过滤规则加数字前缀（见 `script_file_name`）。
    """
    d = scripts_dir(game_dir)
    if not d or not os.path.isdir(d):
        return ""
    if folder:
        d = os.path.join(d, folder)
        os.makedirs(d, exist_ok=True)
    p = os.path.join(d, script_file_name(game_dir, name, index=index))
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(str(source))
    return p


# ================================================================
# 插件脚本：Data/PluginScripts.rxdata
# ================================================================
# v19 起 Essentials 用「插件」组织第三方脚本。PluginManager 把
# `Plugins/<插件>/Scripts/**.rb` 全部读出来、zlib 压好，按
#
#     [ [插件名, 元数据, [ [文件名, zlib压缩源码], ... ]], ... ]
#
# 存进 `Data/PluginScripts.rxdata`；游戏启动时是从**这个文件** eval 的
# （官方 `005_PluginManager#runPlugins`），eval 用的文件名是
# `[插件名] 文件名`。所以「反调试」也可能藏在插件里 ——
# 只扫 Scripts.rxdata 会漏掉。
#
# ★ 按用户要求：**只有「反调试检测」**把插件脚本算进来；
#   基准比对 / 方式二 / 版本识别等其它检测一律不看插件脚本。
PLUGIN_RXDATA_NAME = "PluginScripts.rxdata"


def plugin_rxdata_path(game_dir):
    return os.path.join(data_dir(game_dir), PLUGIN_RXDATA_NAME)


def plugin_script_label(plugin, filename):
    """插件脚本在游戏里的「名字」= eval 时那个文件名：`[插件名] 文件名`。"""
    fn = os.path.basename(str(filename).replace("\\", "/"))
    return "[%s] %s" % (plugin, fn)


def read_plugin_entries(path):
    """
    读 PluginScripts.rxdata → [(插件下标, 文件下标, 显示名, 源码文本), ...]

    ★ 读不出来 / 结构不符 → []。
    ★ 下标一律是**原始位置**（写回时直接按它落回去，不许重新编号）。
    """
    try:
        with open(path, "rb") as f:
            obj = _rb_load(f)
    except Exception as e:                        # noqa: BLE001
        log.warning("读取 %s 失败：%s", path, e)
        return []
    if not isinstance(obj, list):
        return []
    out = []
    for pi, entry in enumerate(obj):
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            continue
        plugin = _text(entry[0])
        files = entry[2]
        if not isinstance(files, (list, tuple)):
            continue
        for fi, scr in enumerate(files):
            if not isinstance(scr, (list, tuple)) or len(scr) < 2:
                continue
            text = _decode_script_bytes(scr[1])
            if not text:
                continue
            out.append((pi, fi, plugin_script_label(plugin, _text(scr[0])),
                        text))
    return out


def iter_plugin_scripts(game_dir):
    """
    遍历**插件脚本** → [(mode, key, path, name, text), ...]

      mode = "plugin"
      key  = (插件下标, 文件下标)
      path = Data/PluginScripts.rxdata
      name = `[插件名] 文件名`

    ★ 没有这个文件 / 是 v19 以前的引擎 → []（老版本没有插件机制）。
    """
    p = plugin_rxdata_path(game_dir)
    if not os.path.isfile(p):
        return []
    return [("plugin", (pi, fi), p, name, text)
            for pi, fi, name, text in read_plugin_entries(p)]


def write_plugin_entry(path, key, new_text, expect=None):
    """
    把 PluginScripts.rxdata 里 `(插件下标, 文件下标)` 那条脚本换成 new_text。

    ★ expect 给定时先核对「这一条现在的内容」是否真的等于 expect，不等
      就抛 RuntimeError 拒绝写入（同 write_rxdata_entry 的那道闸）。
      备份由调用方负责。
    """
    try:
        pi, fi = key
    except (TypeError, ValueError):
        raise RuntimeError("插件脚本下标不对：%r" % (key,))
    with open(path, "rb") as f:
        obj = _rb_load(f)
    if not isinstance(obj, list):
        raise RuntimeError(
            "%s 不是插件脚本表，放弃写入" % os.path.basename(path))
    if not 0 <= pi < len(obj):
        raise RuntimeError("插件下标 %s 越界（共 %s 个插件）" % (pi, len(obj)))
    files = obj[pi][2] if isinstance(obj[pi], (list, tuple)) else None
    if not isinstance(files, (list, tuple)) or not 0 <= fi < len(files):
        raise RuntimeError("插件文件下标 %s 越界" % (fi,))
    if expect is not None:
        cur = _decode_script_bytes(files[fi][1])
        if cur != expect:
            raise RuntimeError(
                "要写的是插件脚本 %s 第 %s 个文件，但它现在的内容和预期不符"
                "（%d 字节 ≠ %d 字节），已拒绝写入"
                % (pi, fi, len(cur), len(expect)))
    files[fi][1] = zlib.compress(new_text.encode("utf-8"))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        _rb_write(f, obj)
    os.replace(tmp, path)


def collect_scripts(game_dir, allow_backup=True, both=False):
    """
    收集游戏脚本 → [(mode, key, path, title, text), ...]

      mode="file"   key = 相对 Data/Scripts 的路径，path = 真实文件
                    title = None（名字从 key 推）
      mode="rxdata" key = **在 rxdata 里的原始条目下标**，path = Scripts.rxdata
                    title = 脚本编辑器里看到的那一栏名字（Settings / Main…）

    ★ 两种脚本形态统一在这里读：已解包（Data/Scripts 存在）就读目录；
      否则读 Scripts.rxdata。

    ★ both=False（默认，**只读**场合用）：只挑一处 —— Data/Scripts 存在就
      读目录，否则读 Scripts.rxdata。只看一处就够，还不会拿到重名。

    ★ both=True（**要改**脚本的场合用）：Data/Scripts 与 Scripts.rxdata
      两处都收 —— 同一个脚本会返回两条（一条 mode="file"、一条
      mode="rxdata"）。调用方按脚本名各自定位、各自改（见 debug_tool 与
      apply_languages_entry）。
      ── 为什么要两处都改：v21 起很多同人游戏「Data/Scripts/**.rb
      （解包源码）」和「Data/Scripts.rxdata（运行时读的那份）」并存，
      到底哪份生效取决于 Game.ini 里 `Scripts=` 指向哪一个；只改一处
      就会出现「改了没效果」或「两份内容越走越远」。

    ★ Scripts.rxdata 里少于 10 条时，那多半只是「脚本已解包」留下的占位
      （v21 就是这样），不认。
    ★ allow_backup=False 时不认备份 —— 备份是只读的兜底数据源，
      往里写脚本会写错地方（改脚本的场合用这个）。
    ★ key 必须是原始下标：写回时是拿它直接 `obj[key] = …` 的，
      一旦重新编号就会写错条目（详见 read_rxdata_entries 的说明）。
    """
    files = []
    for sdir in script_dirs(game_dir):
        for dirpath, dirnames, filenames in os.walk(sdir):
            dirnames.sort()                    # 固定遍历顺序（与 rxdata 对照用）
            for f in sorted(filenames):
                if not f.endswith(".rb"):
                    continue
                p = os.path.join(dirpath, f)
                rel = os.path.relpath(p, game_dir).replace("\\", "/")
                try:
                    with io.open(p, "r", encoding="utf-8",
                                 errors="replace") as fp:
                        files.append(("file", rel, p, None, fp.read()))
                except OSError as e:
                    log.warning("读 %s 失败：%s", p, e)

    ents = []
    rx = rxdata_path(game_dir)
    if os.path.isfile(rx):
        got, _total = read_rxdata_entries(rx)
        if len(got) >= 10:
            ents = [("rxdata", i, rx, title, text)
                    for i, title, text in got]

    if both:
        return files + ents
    if files:
        return files
    if ents:
        return ents
    if allow_backup:
        bak = os.path.join(data_dir(game_dir), BACKUP_NAME)
        if os.path.isfile(bak):
            got, _total = read_rxdata_entries(bak)
            return [("rxdata", i, bak, title, text)
                    for i, title, text in got]
    return []


def iter_script_texts(game_dir):
    """
    遍历游戏脚本 → [(相对路径或标题, 源码文本), ...]（只读场合用）。
    """
    return [(key, text) for _m, key, _p, _t, text in collect_scripts(game_dir)]


def script_sources(game_dir, both=False):
    """
    列出**可写回**的游戏脚本 → [(mode, key, path, text)]

      mode="file"   key = 相对 Data/Scripts 的路径，path = 真实文件
      mode="rxdata" key = 条目下标，          path = Scripts.rxdata

    ★ 与 collect_scripts 的差别只在不认 ScriptsBackup —— 备份不能当写入目标。
    ★ both=True 时把 Data/Scripts/*.rb 与 Scripts.rxdata 两处都列出来
      （改脚本要两处一起改）。
    """
    return [(m, k, p, text) for m, k, p, _t, text
            in collect_scripts(game_dir, allow_backup=False, both=both)]


# 脚本文件名里的编号前缀（001_Settings.rb → Settings）
_LEADING_INDEX_RE = re.compile(r"^\d+\s*[_\-\s]*")


def script_name(key, title=None):
    """
    脚本「名字」—— 就是 RMXP 脚本编辑器左边那一栏（Settings / Main / Compiler）。

      · rxdata 条目 → 直接用标题；
      · 解包的 .rb  → 取文件名，去掉 .rb 和编号前缀
                      （999_Main/999_Main.rb → Main、
                        021_Compiler/001_Compiler.rb → Compiler、
                        001_Technical/003_Intl_Messages.rb → Intl_Messages）
    """
    if title:
        t = str(title).strip()
        if t:
            return t
    base = os.path.basename(str(key or "").replace("\\", "/"))
    base = re.sub(r"\.rb$", "", base, flags=re.I)
    base = _LEADING_INDEX_RE.sub("", base)
    return base.strip() or base


def iter_named_scripts(game_dir, allow_backup=False, both=False):
    """
    遍历游戏脚本 → [(mode, key, path, name, text), ...]（带脚本名）。

    ★ allow_backup 默认 False：这是给「按脚本名定位 / 比对」用的，
      兜底的 ScriptsBackup 里名字可能对不上。
    ★ both=True 时同时给出 Data/Scripts/*.rb 与 Scripts.rxdata 两处的
      同名脚本（「两处都要改」用）。**比对要保持唯一，用默认 False。**
    """
    return [(m, k, p, script_name(k, t), text)
            for m, k, p, t, text
            in collect_scripts(game_dir, allow_backup=allow_backup,
                               both=both)]


# ================================================================
# 找常量
# ================================================================
# 版本号的三种写法（v19 起是 module Essentials 里的 VERSION，
# v17/v18 是 ESSENTIALSVERSION / ESSENTIALS_VERSION，v16 干脆没有）
_VERSION_RES = (
    re.compile(
        r"module\s+Essentials\b[\s\S]{0,4000}?\bVERSION\s*=\s*[\"']([^\"']+)"),
    re.compile(r"\bESSENTIALS_?VERSION\s*=\s*[\"']([^\"']+)"),
)


def essentials_version(game_dir):
    """读游戏里的 Essentials 版本号（读不到返回 ""）。"""
    for rx in _VERSION_RES:
        for _name, text in iter_script_texts(game_dir):
            m = rx.search(text)
            if m:
                return m.group(1).strip()
    return ""


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


def _loc(src):
    """日志用的一句话定位：`文件 → Data/Scripts/…/002_Settings.rb`。"""
    key = str(src.get("key"))
    how = "文件" if src.get("mode") == "file" else "条目"
    return f"{how} {key}" + ("（Scripts.rxdata）"
                            if src.get("mode") == "rxdata" else "")


def find_languages_sources(game_dir):
    """
    找到**所有**写着 `LANGUAGES = [` 的脚本 → [src, ...]（没找到返回 []）。

    ★ 返回列表而不是一份：Data/Scripts/*.rb 与 Scripts.rxdata 两处都要改。
    """
    out = []
    for mode, key, path, text in script_sources(game_dir, both=True):
        if "LANGUAGES" not in text:
            continue
        m = _LANG_ARRAY_RE.search(text)
        if m:
            out.append({"mode": mode, "key": key, "path": path, "text": text,
                        "match": m})
    return out


def find_languages_source(game_dir):
    """找到写着 `LANGUAGES = [` 的那份脚本（找不到返回 None）—— 取第一份。"""
    srcs = find_languages_sources(game_dir)
    return srcs[0] if srcs else None


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


def _zh_fragment(frag, first_display=""):
    """
    第一条语言的文件名片段 → 中文那条该用的片段（照第一条的写法适配）。

      "english.dat" → "Chinese.dat"
      "english"     → "Chinese"
      "English.dat" → "Chinese.dat"
      "deutsch.dat" → "Chinese.dat"（第一条不是英文时按「主干+后缀」套）
    """
    frag = frag or ""
    # ① 片段里含 english（不分大小写）→ 整词换成 Chinese，前后缀原样保留
    m = re.search(r"english", frag, re.I)
    if m:
        return frag[:m.start()] + "Chinese" + frag[m.end():]
    # ② 含第一条的显示名（例如 Deutsch / deutsch.dat）→ 同样换掉
    if first_display:
        m2 = re.search(re.escape(first_display), frag, re.I)
        if m2:
            return frag[:m2.start()] + "Chinese" + frag[m2.end():]
    # ③ 都没有：主干换成 Chinese，后缀（.dat 之类）保留
    stem, dot, ext = frag.rpartition(".")
    if dot and stem:
        return "Chinese" + dot + ext
    return "Chinese"


def _patch_languages(text, display=None, fragment=None):
    """
    在 LANGUAGES 数组里加一条中文语言。做法（按需求定的三步）：

      ① 数组里第一条语言如果被注释掉了（`#  ["English","english.dat"]`），
         先把 `#` 去掉；
      ② 把这一行**复制一份**插到它下面；
      ③ 复制出来的那一行里：
           · 第一个引号 → 语言显示名（默认「简体中文」）
           · 第二个引号 → 文件名片段，**照第一条的写法适配**
             （english.dat → Chinese.dat、english → Chinese）

    于是
        LANGUAGES = [
          ["English","english.dat"]
        ]
    变成
        LANGUAGES = [
          ["English","english.dat"],
          ["简体中文","Chinese.dat"]
        ]

    而
        LANGUAGES = [
          ["English","english"]
        ]
    变成
        LANGUAGES = [
          ["English","english"],
          ["简体中文","Chinese"]
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

    info = {"display": display or "简体中文", "fragment": fragment,
            "added": False, "uncommented": False}
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

    # ③ 复制一行：第一个引号 → 显示名，第二个引号 → 照第一条适配的文件名
    disp = display or "简体中文"
    frag_new = fragment or _zh_fragment(em0.group("frag"),
                                        em0.group("display"))
    em = _ENTRY_LINE_RE.match(body)
    if em:
        # 保留第一条的写法：缩进、引号种类、逗号后的空格、行尾逗号都照抄
        dup = (body[:em.start("display")] + disp
               + body[em.end("display"):em.start("frag")] + frag_new
               + body[em.end("frag"):])
    else:                                    # 理论上不会走到，兜底沿用旧做法
        dup = body.replace("English", "Chinese")
        if dup == body:
            dup = re.sub(r"([\"'])[^\"']*\1", r"\1%s\1" % disp, body, count=1)

    info["added"] = True
    info["display"] = disp
    info["fragment"] = frag_new
    info["template"] = body.strip()
    info["entry"] = dup.strip()
    new_lines = lines[:k0] + [body + cr, dup + cr] + lines[k0 + 1:]
    return "\n".join(new_lines), info


def apply_languages_entry(game_dir, display="简体中文", fragment=None,
                          emit=None):
    """
    把一条语言写进游戏 Settings 的 LANGUAGES。
    返回 {"ok", "changed", "mode", "where", "backup", "targets", ...}

    ★ Data/Scripts/*.rb 与 Data/Scripts.rxdata **两处都改**（哪份生效取决于
      Game.ini 的 Scripts= 指向，只改一处会出现「改了没反应」）。
      列表里的每一份各自定位 `LANGUAGES = [`、各自备份、各自校验后写入。
    ★ 已解包的改 .rb 文件；没解包的直接改 Scripts.rxdata（脚本源码在里面是
      zlib 压缩的，改完再压回去）。
    """
    def say(msg):
        if emit:
            emit(msg)

    srcs = find_languages_sources(game_dir)
    if not srcs:
        return {"ok": False, "reason": "在脚本里没找到 LANGUAGES（Settings）"}
    frag = fragment or language_fragment(game_dir)
    out = {"ok": True, "changed": False, "fragment": frag, "targets": [],
           "display": display}
    first = None
    for src in srcs:
        try:
            new_text, info = _patch_languages(src["text"], display, frag)
        except ValueError as e:
            say(f"[语言] ⚠ {_loc(src)} 里的 LANGUAGES 读不出来：{e}")
            continue
        if first is None:
            first = info
        item = {"mode": src["mode"], "where": str(src["key"]),
                "changed": False, "display": info.get("display") or display}
        if not info.get("added"):
            say(f"[语言] {_loc(src)} 的 LANGUAGES 里已经有「"
                f"{info.get('exists') or '中文'}」，跳过")
            out["targets"].append(item)
            continue

        path = src["path"]
        bak = f"{path}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
        item["backup"] = bak
        with open(path, "rb") as f:
            raw = f.read()
        with open(bak, "wb") as f:
            f.write(raw)
        if src["mode"] == "file":
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new_text)
        else:
            # ★ expect=原文：条目下标算错时宁可报错，也不要写错脚本
            write_rxdata_entry(path, src["key"], new_text, expect=src["text"])
        item["changed"] = True
        out["changed"] = True
        out["targets"].append(item)
        if info.get("uncommented"):
            say(f"[语言] {_loc(src)} 里那条语言原本被注释掉了，已去掉 `#`")
        say(f"[语言] {_loc(src)} 已加入 "
            f"{info.get('entry') or '[\"Chinese\", …]'}（复制第一条并改名）"
            f"；原文件已备份：{os.path.basename(bak)}")

    if first:
        for k in ("display", "fragment", "entry", "template", "exists",
                  "added", "uncommented"):
            if k in first:
                out.setdefault(k, first[k])
    # 兼容旧字段：取第一处当代表
    if out["targets"]:
        out["mode"] = out["targets"][0]["mode"]
        out["where"] = out["targets"][0]["where"]
        if out["targets"][0].get("backup"):
            out["backup"] = out["targets"][0]["backup"]
    if not out["changed"]:
        say(f"[语言] Settings 的 LANGUAGES 里已经有「"
            f"{out.get('exists') or '中文'}」，不用再改")
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
