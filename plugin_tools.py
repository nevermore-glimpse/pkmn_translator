# -*- coding: utf-8 -*-
"""
中文文本处理插件的植入，以及**离线复现** PluginManager 的插件编译。

游戏那边的流程（001_Technical/005_PluginManager.rb）：

    getPluginOrder   读 Plugins/<每个插件>/meta.txt，按依赖关系排出加载顺序
    needCompiling?   只在 $DEBUG 为真时才编译 —— 所以平时得开着调试进一次游戏
    compilePlugins   把每个插件的脚本 zlib 压缩后 Marshal 写进
                     Data/PluginScripts.rxdata，游戏启动时再从它加载

本模块把最后一步搬到工具里做：不用进游戏、不用 debug 模式，直接算出同样的
结果写进 Data/PluginScripts.rxdata（写之前自动备份）。meta.txt 的解析规则、
依赖排序（sortLoadOrder + reverse）、脚本清单（meta 里列出的优先，其余按
目录里名字顺序补上）都照抄游戏实现。
"""
import io
import os
import re
import shutil
import struct
import time
import zlib

from rubymarshal.writer import write as _rb_write
from rubymarshal.reader import load as _rb_load
from rubymarshal.classes import Symbol

import config
import game_scripts as GS
from logger import get_logger

log = get_logger("plugin_tools")

# 插件本体（工作区里的）。★ 游戏里的目录名固定是 PLUGIN_DIR_NAME（还原靠它），
# 但工作区里按 Essentials 版本备了三份：21.1 / 20.1 / 19.1。
# 版本不同，引擎的 DrawText 实现与可用助手函数不同（v20.1/19.1 没有
# Color.new_from_rgb，v21.1 没有 rgbToColor / Rgb16ToColor），所以必须分版本。
PLUGIN_DIR_NAME = "chinese text manager"
PLUGIN_SRC_DIRS = (
    ("21.1", os.path.join("scripts", "chinese text manager")),
    ("20.1", os.path.join("scripts", "chinese text manager 20.1")),
    ("19.1", os.path.join("scripts", "chinese text manager 19.1")),
    # ★ 旧版（19.1 之前 / Ruby 1.8 / 没有插件系统）：塞进脚本的最后一个
    ("legacy", os.path.join("scripts", "chinese text manager legacy")),
)
PLUGIN_SRC_DIR = PLUGIN_SRC_DIRS[0][1]        # 默认（21.1），兼容旧调用
PLUGIN_META_FILE = "meta.txt"
PLUGIN_SETTINGS_FILE = "Settings.rb"
PLUGIN_TOOLS_FILE = "Tools.rb"
PLUGIN_FONT_ATTR = "GLOBAL_FONT_NAME"
PLUGIN_INJECT_MARK = "[pkmn] injected by the Pokemon translation tool"

PLUGIN_SCRIPTS_NAME = "PluginScripts.rxdata"

# ---- 没有插件目录时：插件会被拼成一个脚本，插到 Main **之前** ----
# ★ 必须排在 Main 之前：RGSS 是「从上往下依次执行脚本，读到 Main 就开始跑游戏」，
#   所以写在 Main 后面的脚本永远不会执行（这就是最早「塞进脚本却没生效」的原因）。
SCRIPT_TITLE = "[pkmn] chinese text manager"
SCRIPT_FILE_STEM = "pkmn_chinese_text"          # 解包游戏：<Main 的编号-1>_pkmn_chinese_text.rb
SCRIPT_FILE_NAME = "zzz_pkmn_chinese_text.rb"   # 旧版本用过的名字，还原时一并清掉
SCRIPT_HEAD_MARK = "[pkmn] 中文文本处理"
# 脚本标题/文件名里像 Main 的：Main / main / 999_Main / [Main] …
_MAIN_TITLE_RE = re.compile(r"^\s*\[?\s*\d*\s*_?\s*main\s*\]?\s*$", re.I)


# ================================================================
# 路径
# ================================================================
def plugins_dir(game_dir):
    return os.path.join(game_dir, "Plugins")


def plugin_dir(game_dir):
    """工具植入的那个插件在游戏里的位置。"""
    return os.path.join(plugins_dir(game_dir), PLUGIN_DIR_NAME)


def plugin_src_dir(ver=None):
    """工作区里的插件本体：scripts/chinese text manager[- 版本]/"""
    key = ver or "21.1"
    for k, rel in PLUGIN_SRC_DIRS:
        if k == key:
            return config.resource_path(rel)
    log.warning("未知的插件变体「%s」，按 21.1 处理", key)
    return config.resource_path(PLUGIN_SRC_DIRS[0][1])


def pick_plugin_version(game_dir):
    """
    按游戏的 Essentials 版本挑插件变体 → (变体, 游戏里读到的版本字符串)。

      主版本 ≥ 21 → 21.1 ；== 20 → 20.1 ；== 19 → 19.1 ；
      其余（18.x 及更早、纯 RMXP 游戏）→ legacy（Ruby 1.8 兼容版）
    ★ 没有插件系统（没有 PluginManager）的也一律用 legacy ——
      它不依赖插件系统，是直接塞进脚本里的。
    """
    ver = essentials_version(game_dir)
    tup = _version_tuple(ver)
    if not has_plugin_manager(game_dir):
        return "legacy", ver
    if tup is None:
        return "21.1", ver                  # 有插件系统但读不出型号：用最新版
    if tup[0] >= 21:
        return "21.1", ver
    if tup[0] == 20:
        return "20.1", ver
    if tup[0] == 19:
        return "19.1", ver
    return "legacy", ver


def install_mode(game_dir):
    """
    插件怎么装：

      "plugins" —— 游戏有插件系统、也有 Plugins 目录 → 老办法
                   （复制到 Plugins/ 并编译进 PluginScripts.rxdata）
      "scripts" —— 没有插件系统，**或者没有 Plugins 目录** →
                   把插件拼成一个脚本，追加到 Scripts.rxdata 的最后一个
                   （解包成 Data/Scripts/ 的游戏就放一个排最后的 .rb）
    """
    if not has_plugin_manager(game_dir):
        return "scripts"
    if not os.path.isdir(plugins_dir(game_dir)):
        return "scripts"
    return "plugins"


def plugin_scripts_path(game_dir):
    return os.path.join(GS.data_dir(game_dir), PLUGIN_SCRIPTS_NAME)


# ================================================================
# 字体
# ================================================================
def ttf_family_name(path):
    """从 TTF/OTF 的 name 表读字族名（优先 ID 16，其次 ID 1）；读不到返回 None。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if data[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
            return None
        num_tables = struct.unpack(">H", data[4:6])[0]
        name_off = None
        for i in range(num_tables):
            rec = data[12 + i * 16: 12 + i * 16 + 16]
            if rec[:4] == b"name":
                name_off = struct.unpack(">I", rec[8:12])[0]
                break
        if name_off is None:
            return None
        count = struct.unpack(">H", data[name_off + 2:name_off + 4])[0]
        str_off = name_off + struct.unpack(
            ">H", data[name_off + 4:name_off + 6])[0]
        found = {}
        for i in range(count):
            rec = data[name_off + 6 + i * 12: name_off + 6 + i * 12 + 12]
            platform, _enc, _lang, name_id = struct.unpack(">HHHH", rec[:8])
            length, offset = struct.unpack(">HH", rec[8:12])
            if name_id in (1, 16) and name_id not in found:
                raw = data[str_off + offset: str_off + offset + length]
                try:
                    val = (raw.decode("utf-16-be") if platform in (0, 3)
                           else raw.decode("latin-1"))
                except Exception:
                    continue
                if val.strip():
                    found[name_id] = val.strip()
        return found.get(16) or found.get(1)
    except Exception as e:
        log.debug("读取字体族名失败：%s", e)
        return None


def resolve_font(font_file=None):
    """
    确定要用的字体 → (字体文件路径, 字族名, 提示行列表)。
    font_file 留空时用随程序分发的萝莉体。
    """
    notes = []
    path = font_file or config.FONT_FILE
    if not os.path.isfile(path):
        raise FileNotFoundError(f"字体文件不存在：{path}")
    family = ttf_family_name(path) or config.FONT_NAME or "Lolita"
    notes.append(f"[插件] 字体：{os.path.basename(path)}（族名「{family}」）")
    return path, family, notes


# ================================================================
# meta.txt 解析（照抄 PluginManager.readMeta）
# ================================================================
_META_LINE = re.compile(r"^\s*(\w+)\s*=\s*(.*)$")


def read_meta(plugin_dir_path, emit=None):
    """
    解析某个插件的 meta.txt → dict（键与游戏一致：name/version/link/
    credits/dependencies/incompatibilities/scripts/…）。

    ★ 规则的几点照抄游戏：
      · 值按逗号拆开、各自去空白；
      · REQUIRES 一行是「名字」、两列是「名字,版本」、三列是「类型,名字,版本」；
      · SCRIPTS 可以写多行、每行可带多个文件；
      · 其余属性一律「属性名小写 = 第一个值」（Name→name、Essentials→essentials）；
      · 最后把目录里**所有 .rb**（递归、按名字顺序）补进 scripts，去重。
        meta 里显式写过的文件排前面。
    """
    def say(msg):
        if emit:
            emit(msg)

    path = os.path.join(plugin_dir_path, PLUGIN_META_FILE)
    meta = {}
    # ★ utf-8-sig：Essentials 自带的 meta.txt（v19.1 Hotfixes 就是）带 BOM，
    #   不剥掉的话第一行 `Name=...` 匹配不上 → 插件会被当成「没有 Name」跳过。
    with io.open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.rstrip("\r\n").lstrip("﻿")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = _META_LINE.match(line)
            if not m:
                say(f"[插件] ⚠ {path} 第 {line_no} 行格式不对（应为 XXX=YYY），已跳过")
                continue
            prop = m.group(1).upper()
            data = [x.strip() for x in m.group(2).split(",")]
            if prop == "REQUIRES":
                meta.setdefault("dependencies", [])
                if len(data) < 2:
                    meta["dependencies"].append(data[0])
                elif len(data) == 2:
                    meta["dependencies"].append([data[0], data[1]])
                else:
                    meta["dependencies"].append([Symbol(data[2].lower()),
                                                 data[0], data[1]])
            elif prop in ("EXACT", "OPTIONAL"):
                if len(data) < 2:
                    continue
                meta.setdefault("dependencies", [])
                meta["dependencies"].append([Symbol(prop.lower()),
                                             data[0], data[1]])
            elif prop == "CONFLICTS":
                meta.setdefault("incompatibilities", [])
                for v in data:
                    if v:
                        meta["incompatibilities"].append(v)
            elif prop == "SCRIPTS":
                meta.setdefault("scripts", [])
                for v in data:
                    if v:
                        meta["scripts"].append(v)
            elif prop == "CREDITS":
                meta["credits"] = data
            elif prop in ("LINK", "WEBSITE"):
                meta["link"] = data[0]
            else:
                meta[prop.lower()] = data[0]
    meta.setdefault("scripts", [])
    for rel in _all_rb_files(plugin_dir_path):
        if rel not in meta["scripts"]:
            meta["scripts"].append(rel)
    return meta


def _all_rb_files(plugin_dir_path):
    """
    目录里所有脚本的相对路径（递归）——严格照抄 Dir.all：

        Dir.get     = Dir.glob 的结果 **排序**后返回完整路径
        Dir.all     = 本层的**文件**先全部收完（按名排序），再依次递归**子目录**

    所以子目录的内容一定排在本层所有文件**之后**，而不是按名字混排。
    另外游戏判据是 `fl.include?(".rb")`（名字里含 .rb 即可），不是 endswith。
    路径分隔符是 `/`（Ruby 那边直接 gsub 掉 "目录/" 前缀）。
    """
    out = []

    def walk(path, rel):
        try:
            names = sorted(os.listdir(path))
        except OSError:
            return
        dirs = []
        for name in names:
            p = os.path.join(path, name)
            r = f"{rel}/{name}" if rel else name
            if os.path.isdir(p):
                dirs.append((p, r))
            elif ".rb" in name:
                out.append(r)
        for p, r in dirs:                 # 子目录排在本层文件之后
            walk(p, r)

    walk(plugin_dir_path, "")
    return out


# ================================================================
# 加载顺序（照抄 getPluginOrder / sortLoadOrder）
# ================================================================
def _dep_name(dep):
    """依赖项 → 纯名字（形状可能是 名字 / [名字,版本] / [类型,名字,版本]）。"""
    if isinstance(dep, list):
        if len(dep) == 2:
            return dep[0]
        if len(dep) == 3:
            return dep[1]
    return dep


def _sort_load_order(order, plugins, emit=None, laps=None):
    """
    照抄 sortLoadOrder：以「反转前」的顺序为准，依赖必须排在**后面**
    （游戏注释写着 this ends up in reverse order，最后整体 reverse 之后
    依赖就排到前面了）。发现依赖排在自己前面就交换两位并从头重排。

    ★ Ruby 那边 `for o in order` 是按下标遍历实时数组 —— 交换后继续往下走，
      不回头；这里也用下标循环，保持一致。
    """
    def say(msg):
        if emit:
            emit(msg)

    if laps is None:
        laps = [0]
    i = 0
    while i < len(order):
        o = order[i]
        info = plugins.get(o) or {}
        deps = info.get("dependencies") or []
        for dep in deps:
            dname = _dep_name(dep)
            if dname not in order:
                # ★ 只在最后统一报一次（这里每次交换都会重排，会刷屏）
                continue
            if order.index(dname) > order.index(o):
                continue                    # 依赖在自己后面 → 顺序正确
            laps[0] += 1
            if laps[0] > 500:               # 依赖成环时不要死循环
                say("[插件] ⚠ 插件依赖关系可能成环，已按当前顺序继续")
                return order
            ia, ib = order.index(o), order.index(dname)
            order[ia], order[ib] = order[ib], order[ia]
            _sort_load_order(order, plugins, emit=emit, laps=laps)
        i += 1
    return order


def scan_plugins(game_dir, emit=None):
    """
    扫 Plugins/ 下的所有插件 → (顺序列表, {名字: meta})。

    顺序 = 目录名顺序 → 依赖排序 → **整体反转**（游戏如此：先反转再依次加载，
    依赖才排在前面）。
    """
    def say(msg):
        if emit:
            emit(msg)

    root = plugins_dir(game_dir)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"找不到插件目录：{root}")

    plugins = {}
    order = []
    # ★ Dir.get 返回的是排序后的**完整路径**（Plugins/<文件夹名>）；
    #   插件的显示名（meta 里的 Name）可能与文件夹名不同（实测「Elite Battle: DX」
    #   的文件夹就叫 Elite Battle DX），所以「读文件用文件夹名、排序用 Name」两条
    #   必须分开存 —— 混用会读不到脚本。
    for folder in sorted(os.listdir(root)):
        d = os.path.join(root, folder)
        if not os.path.isdir(d):
            continue
        if not os.path.isfile(os.path.join(d, PLUGIN_META_FILE)):
            continue                       # 没有 meta.txt 的目录游戏会忽略
        meta = read_meta(d, emit=emit)
        pname = meta.get("name")
        if not pname:
            say(f"[插件] ⚠ {folder}/meta.txt 里没有 Name，游戏会报错，已跳过")
            continue
        if not meta.get("scripts"):
            say(f"[插件] ⚠ {folder} 里没有任何脚本，已跳过")
            continue
        if pname in plugins:
            say(f"[插件] ⚠ 有两个插件都叫「{pname}」，后者已跳过")
            continue
        meta["dir_path"] = d               # 真实目录（读脚本用）
        plugins[pname] = meta
        order.append(pname)

    _sort_load_order(order, plugins, emit=emit)
    order.reverse()
    # ★ 缺依赖在这里统一报一次，且每个插件最多一条
    for o in order:
        miss = [_dep_name(d) for d in plugins[o].get("dependencies") or []
                if _dep_name(d) not in plugins]
        if miss:
            uniq = []
            for m in miss:
                if m not in uniq:
                    uniq.append(m)
            say(f"[插件] ⚠ 插件「{o}」缺依赖：{'、'.join(uniq)} —— "
                f"游戏启动时可能报错")
    return order, plugins


# ================================================================
# 写 PluginScripts.rxdata（照抄 compilePlugins）
# ================================================================
def _to_bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, list):
        return [_to_bytes(x) for x in value]
    if isinstance(value, Symbol):
        return value
    return str(value).encode("utf-8")


def compile_plugins(game_dir, emit=None, backup=True, out_path=None):
    """
    重新编译 Data/PluginScripts.rxdata。返回报告 dict。

    ★ 写出来的是**全部**插件（不只中文插件）：这份文件是整包替换的，
      漏掉其它插件会让游戏丢掉它们。
    out_path 只给测试用（默认就写游戏里的那份）。
    """
    def say(msg):
        if emit:
            emit(msg)

    order, plugins = scan_plugins(game_dir, emit=emit)
    if not order:
        raise FileNotFoundError("Plugins/ 里没有找到任何带 meta.txt 的插件")

    scripts = []
    for name in order:
        meta = dict(plugins[name])
        files = meta.pop("scripts")
        base = meta.pop("dir_path", None) or os.path.join(
            plugins_dir(game_dir), name)
        entry = {}
        for k, v in meta.items():
            entry[Symbol(k)] = _to_bytes(v)
        dat = [_to_bytes(name), entry, []]
        for rel in files:
            p = os.path.join(base, rel.replace("/", os.sep))
            try:
                with open(p, "rb") as f:
                    body = f.read()
            except OSError as e:
                say(f"[插件] ⚠ 读不到 {os.path.basename(base)}/{rel}：{e}")
                continue
            dat[2].append([_to_bytes(rel), zlib.compress(body)])
        scripts.append(dat)

    out = out_path or plugin_scripts_path(game_dir)
    bak = None
    if out_path is None and os.path.isfile(out) and backup:
        bak = f"{out}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
        shutil.copyfile(out, bak)
        say(f"[插件] 原 PluginScripts.rxdata 已备份："
            f"{os.path.basename(bak)}")
    tmp = out + ".tmp"
    with open(tmp, "wb") as f:
        _rb_write(f, scripts)
    os.replace(tmp, out)

    total = sum(len(d[2]) for d in scripts)
    say(f"[插件] 已编译 {len(scripts)} 个插件、{total} 个脚本 → "
        f"Data/{PLUGIN_SCRIPTS_NAME}（{os.path.getsize(out):,} 字节）")
    for d in scripts:
        mark = "　←　本工具植入" if d[0] == _to_bytes(PLUGIN_DIR_NAME) else ""
        say(f"[插件]   · {d[0].decode('utf-8', 'replace')}"
            f"（{len(d[2])} 个脚本）{mark}")
    log.info("编译插件：%s → %d 个插件 / %d 个脚本",
             game_dir, len(scripts), total)
    return {"out": out, "backup": bak, "plugins": len(scripts),
            "scripts": total,
            "names": [d[0].decode("utf-8", "replace") for d in scripts]}


# ================================================================
# 植入插件
# ================================================================
def _copied_font(game_dir):
    """读插件 Settings.rb 里「# Copied font:」标记 → 当初复制进 Fonts 的文件名。"""
    p = os.path.join(plugin_dir(game_dir), PLUGIN_SETTINGS_FILE)
    if not os.path.isfile(p):
        return None
    try:
        with io.open(p, "r", encoding="utf-8", errors="replace") as f:
            return _copied_font_name(f.read())
    except Exception as e:
        log.warning("读取插件 Settings 失败：%s", e)
    return None


def _copied_font_name(text):
    """从文本里找 `# Copied font: xxx` 标记 → xxx（游戏自带字体写的是 Game font）。"""
    for line in (text or "").split("\n"):
        if line.startswith("# Copied font:"):
            return line.split(":", 1)[1].strip() or None
    return None


def essentials_version(game_dir):
    return GS.essentials_version(game_dir)


# ================================================================
# 兼容层（兜底用）
# ================================================================
# 现在 21.1 / 20.1 / 19.1 各有一份插件本体，正常情况下按版本植入即可。
# 但「型号读不出来」或「引擎里缺插件依赖的 API」时还是可能出错，
# 所以留一层「兼容外壳」兜底：插件自己的实现一旦抛异常，
# 就退回引擎原本的实现（原版换行逻辑），至少不会一进游戏就崩。
COMPAT_METHODS = ("getFormattedText", "getFormattedTextFast",
                  "pbDrawShadowText", "_MAPINTL")

# 这些是 RGSS / 引擎内建的，脚本里搜不到但一定存在
_BUILTIN_APIS = ("Font.default_color", "Bitmap#text_size")

# 插件用到的外部 API → 在脚本里的样子
_PLUGIN_APIS = {
    "MessageTypes.getFromMapHash": r"def self\.getFromMapHash",
    "MessageTypes.getFromHash": r"def self\.getFromHash",
    "getFormattedText": r"^def getFormattedText\b",
    "pbDrawShadowText": r"^def pbDrawShadowText\b",
    "MessageConfig": r"module MessageConfig",
    "Settings": r"module Settings\b",
}
_PLUGIN_API_FILE = os.path.join("scripts", PLUGIN_DIR_NAME, "Tools.rb")

COMPAT_PRE = '''# [pkmn] 兼容层（前）：先把引擎原本的实现存下来
#   型号读不出来 / 引擎缺 API 时用；插件实现一旦抛异常，
#   就退回这里存下来的原实现（见 zz_CNCompatPost.rb）。
module CNCompat
  ORIG = {}
end

%(methods)s.each do |name|
  sym = name.to_sym
  next if !Object.private_method_defined?(sym) && !Object.method_defined?(sym)
  begin
    CNCompat::ORIG[name] = Object.instance_method(sym)
  rescue Exception
    nil
  end
end
'''

COMPAT_POST = '''# [pkmn] 兼容层（后）：插件的实现出错 → 退回引擎原本的实现
#   这样即使插件与当前 Essentials 版本不合，游戏也不会一进来就崩溃，
#   最多是换行/排版沿用原版行为。
%(methods)s.each do |name|
  sym = name.to_sym
  next if !Object.private_method_defined?(sym) && !Object.method_defined?(sym)
  orig = CNCompat::ORIG[name]
  cn = Object.instance_method(sym)
  next if orig && cn == orig          # 插件没覆盖，不用包
  if orig
    Object.send(:define_method, sym) do |*args, &blk|
      begin
        cn.bind(self).call(*args, &blk)
      rescue Exception
        orig.bind(self).call(*args, &blk)
      end
    end
  else
    # 引擎里本来就没有这个方法（更老的版本）：出错就退回最朴素的取值
    Object.send(:define_method, sym) do |*args, &blk|
      begin
        cn.bind(self).call(*args, &blk)
      rescue Exception
        (args[1] || args[0] || "").to_s
      end
    end
  end
end
'''


def has_plugin_manager(game_dir):
    """
    这个游戏有没有插件系统（Essentials v19 起才有 PluginManager）。

    ★ 只看**脚本里有没有 PluginManager** —— 很多整合版压根没有 Plugins
      文件夹（我们到时候自己建），但插件系统是有的。
      脚本读不出来时才退回去看文件夹（这种情况下判不了，就当没有）。
    """
    readable = False
    for _name, text in GS.iter_script_texts(game_dir):
        readable = True
        if "module PluginManager" in text or "def self.compilePlugins" in text:
            return True
    if readable:
        return False
    return os.path.isdir(plugins_dir(game_dir))


def _version_tuple(text):
    m = re.search(r"(\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_compat(game_dir):
    """
    判断这个游戏该用哪个版本的插件、走哪条植入路径。返回 dict：

      version         —— 游戏里的 Essentials::VERSION
      variant         —— 要植入的插件变体（21.1 / 20.1 / 19.1 / legacy）
      mode            —— "plugins"（Plugins 目录）或 "scripts"（塞进脚本末尾）
      plugin_manager  —— 有没有插件系统（没有就只能塞脚本）
      missing_apis    —— 插件依赖、但脚本里找不到的引擎 API
      need_compat     —— 要不要加兼容层（只在 "plugins" 路径下才有意义）
      advice          —— 给人看的一句话说明

    ★ 版本对得上就用对应版本，不加兼容层；
      只有「有插件系统但型号读不出来」或「引擎里连插件依赖的 API 都找不到」
      时才兜底加兼容层。
    """
    ver = essentials_version(game_dir)
    variant, _v = pick_plugin_version(game_dir)
    mode = install_mode(game_dir)
    pm = has_plugin_manager(game_dir)
    texts = GS.iter_script_texts(game_dir)
    blob = "\n".join(t for _n, t in texts)
    readable = bool(texts)
    # ★ 脚本读不出来时没法判断 API 在不在，别拿「找不到」吓唬人
    missing = ([k for k, pat in _PLUGIN_APIS.items()
                if not re.search(pat, blob, re.M)] if readable else [])
    tup = _version_tuple(ver)
    unreadable = tup is None
    need = bool(missing) or (unreadable and variant != "legacy")
    if mode == "scripts":
        need = False            # 塞脚本不需要兼容外壳
    if not readable:
        mode_name = "脚本" if mode == "scripts" else "Plugins 目录"
        advice = (f"读不到游戏脚本，按 Essentials {variant} 版插件"
                  f"（{mode_name}方式）处理")
    elif mode == "scripts":
        why = ("这个游戏没有插件系统（Essentials v19 之前 / Ruby 1.8）"
               if not pm else "这个游戏没有 Plugins 目录")
        advice = (f"{why}：改用 Essentials {variant} 版插件，"
                  f"并把它插到脚本里 Main 的前面")
    elif missing:
        advice = ("脚本里找不到 " + "、".join(missing) +
                  f"，用 Essentials {variant} 版插件并加兼容层兜底")
    else:
        advice = (f"Essentials {ver} → 用 {variant} 版插件"
                  f"（Plugins 目录 + PluginScripts.rxdata）")
    if not readable:
        advice += "（脚本读不出来，判断可能不准）"
    return {"version": ver, "variant": variant, "mode": mode,
            "plugin_manager": pm, "missing_apis": missing,
            "need_compat": need, "old": unreadable,
            "readable": readable, "advice": advice}


def write_compat_layer(dst_dir, methods=None):
    """
    在插件目录里写入兼容层（前/后两个脚本）。返回写出的文件名列表。
    ★ 靠文件名排序保证顺序：000_CNCompatPre → Settings → Tools → zz_CNCompatPost
    """
    methods = list(methods or COMPAT_METHODS)
    body = "%w[" + " ".join(methods) + "]"
    written = []
    for name, tpl in (("000_CNCompatPre.rb", COMPAT_PRE),
                      ("zz_CNCompatPost.rb", COMPAT_POST)):
        p = os.path.join(dst_dir, name)
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(tpl % {"methods": body})
        written.append(name)
    return written


def plugin_needs_essentials(ver=None):
    """读插件 meta.txt 里声明的 Essentials 版本（读不到返回 ""）。
    ver 为空时读默认的 21.1 那份。"""
    p = os.path.join(plugin_src_dir(ver), PLUGIN_META_FILE)
    if not os.path.isfile(p):
        return ""
    try:
        with io.open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"\s*Essentials\s*=\s*(.+)", line)
                if m:
                    return m.group(1).strip().rstrip(",")
    except Exception as e:
        log.warning("读插件 meta.txt 失败：%s", e)
    return ""


def install_plugin(game_dir, font_file=None, emit=None, adaptive=True):
    """
    植入中文文本处理插件。两条路（按游戏自动选，见 install_mode）：

      ★ 「有插件系统 + 有 Plugins 目录」→ 老办法：
          1. 按 Essentials 版本挑插件本体（21.1 / 20.1 / 19.1），
             复制到 <游戏>/Plugins/chinese text manager/；
          2. 选定字体写进 Settings.rb，字体复制到 Fonts/；
          3. 型号读不出来 / 引擎缺 API 时加一层兼容外壳；
          4. 重新编译 Data/PluginScripts.rxdata（含游戏原有的其它插件）。

      ★ 「没有插件系统（v19 之前 / Ruby 1.8）」或「没有 Plugins 目录」→
         用 legacy / 对应版本的本体，把 Settings.rb + Tools.rb 拼成一个脚本，
         **追加到 Scripts.rxdata 的最后一个**（解包游戏则写
         Data/Scripts/zzz_pkmn_chinese_text.rb）。字体一样复制到 Fonts/。

    adaptive=False 时不做兼容层、也不按版本挑（一律用 21.1 那份、走插件系统）。
    返回报告 dict。
    """
    def say(msg):
        if emit:
            emit(msg)

    compat = check_compat(game_dir) if adaptive else None
    if compat:
        say(f"[插件] {compat['advice']}")
        variant = compat["variant"]
        mode = compat["mode"]
    else:
        variant, mode = "21.1", "plugins"

    src = plugin_src_dir(variant)
    if not os.path.isdir(src):
        raise FileNotFoundError(
            f"找不到 Essentials {variant} 版的插件本体：{src}")
    say(f"[插件] 插件本体：Essentials {variant} 版（{os.path.basename(src)}/）")

    font_file, family, notes = resolve_font(font_file)
    for n in notes:
        say(n)

    fonts_dir = os.path.join(game_dir, "Fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    font_dst = os.path.join(fonts_dir, os.path.basename(font_file))
    copied = os.path.abspath(font_dst) != os.path.abspath(font_file)
    if copied:
        shutil.copyfile(font_file, font_dst)
        say(f"[插件] 字体已复制：Fonts/{os.path.basename(font_file)}")

    # ---------- 路线 B：塞进脚本的最后一个 ----------
    if mode == "scripts":
        rep = inject_script_plugin(game_dir, src, font_file, family, copied,
                                   emit=emit)
        say("[插件] 完成：插件已插到游戏脚本里（Main 之前），"
            "**不需要**再进游戏编译一次")
        return {"font": family, "font_file": font_file, "copied": copied,
                "variant": variant, "mode": mode, "files": [],
                "script": rep, "compat": [], "compat_info": compat,
                "compile": None}

    # ---------- 路线 A：Plugins/ + PluginScripts.rxdata ----------
    dst = plugin_dir(game_dir)
    os.makedirs(dst, exist_ok=True)
    written = []
    for name in sorted(os.listdir(src)):
        s_path = os.path.join(src, name)
        if not os.path.isfile(s_path):
            continue
        with open(s_path, "rb") as f:
            data = f.read()
        with open(os.path.join(dst, name), "wb") as f:
            f.write(data)
        written.append(name)
    if not written:
        raise FileNotFoundError(f"{src} 里没有任何文件")
    say(f"[插件] 已复制插件到 Plugins/{PLUGIN_DIR_NAME}/（{len(written)} 个文件）")

    settings = os.path.join(dst, PLUGIN_SETTINGS_FILE)
    if os.path.isfile(settings):
        text, n = _settings_text(dst, font_file, family, copied)
        with open(settings, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        say(f"[插件] 字体名已写入 Settings.rb：{PLUGIN_FONT_ATTR} = \"{family}\""
            f"（{n} 处）")

    # ★ 旧版游戏：加兼容层（插件实现出错 → 退回引擎原本的实现）
    compat_files = []
    if compat and compat["need_compat"]:
        for old in ("000_CNCompatPre.rb", "zz_CNCompatPost.rb"):
            p = os.path.join(dst, old)
            if os.path.isfile(p):
                os.remove(p)
        compat_files = write_compat_layer(dst)
        say(f"[插件] 已加兼容层：{'、'.join(compat_files)}"
            f"（插件实现出错会退回引擎原本的实现，不会一进游戏就崩）")

    meta = os.path.join(dst, PLUGIN_META_FILE)
    if os.path.isfile(meta):
        with io.open(meta, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
        if PLUGIN_INJECT_MARK not in text:
            text = text.rstrip("\n") + "\n# " + PLUGIN_INJECT_MARK + "\n"
        # ★ 兼容层必须夹在中间：Pre → Settings → Tools → Post
        if compat_files:
            order = ["000_CNCompatPre.rb", PLUGIN_SETTINGS_FILE, "Tools.rb",
                     "zz_CNCompatPost.rb"]
            order += [f for f in sorted(os.listdir(dst))
                      if f.endswith(".rb") and f not in order]
            text = re.sub(r"(?im)^\s*Scripts\s*=.*\n", "", text)
            text = text.rstrip("\n") + "\nScripts   = " + ",".join(order) + "\n"
        with open(meta, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    need = plugin_needs_essentials(variant)
    have = essentials_version(game_dir)
    if need and have:
        if need not in have and have not in need:
            say(f"[插件] ⚠ 插件声明适用 Essentials {need}，本游戏是 {have}"
                + ("；已用兼容层兜底" if compat_files else
                   " —— 建议勾上兼容层，或在设置里手动处理"))
        else:
            say(f"[插件] Essentials 版本 {have}，与插件声明（{need}）匹配")

    rep = compile_plugins(game_dir, emit=emit)
    say("[插件] 完成：插件已放进 Plugins/ 并已编译进 PluginScripts.rxdata，"
        "**不需要**再进游戏编译一次")
    return {"font": family, "font_file": font_file, "copied": copied,
            "variant": variant, "mode": "plugins", "files": written,
            "compat": compat_files, "compat_info": compat, "compile": rep}


def restore_plugin(game_dir, emit=None):
    """
    还原插件植入：
      · Plugins/ 下**确认是本工具植入**的那个插件目录（meta.txt 里有标记）；
      · Scripts.rxdata 里本工具追加的那个脚本（或那个 .rb 文件）；
      · 当初复制进 Fonts 的那份字体（带 `# Copied font:` 标记）。
    """
    def say(msg):
        if emit:
            emit(msg)

    removed = []
    font_name = None
    # ★ 塞进脚本的那份要**先读出来**（里面有字体标记），再删
    bodies = _script_bodies(game_dir)

    d = plugin_dir(game_dir)
    if os.path.isdir(d):
        meta = os.path.join(d, PLUGIN_META_FILE)
        mine = False
        if os.path.isfile(meta):
            with io.open(meta, "r", encoding="utf-8",
                         errors="replace") as f:
                mine = PLUGIN_INJECT_MARK in f.read()
        if not mine:
            say(f"[还原] Plugins/{PLUGIN_DIR_NAME}/ 不是本工具植入的，保留不动")
        else:
            font_name = _copied_font(game_dir)
            shutil.rmtree(d, ignore_errors=True)
            removed.append(f"Plugins/{PLUGIN_DIR_NAME}/")
            say(f"[还原] 已删除 Plugins/{PLUGIN_DIR_NAME}/")
    else:
        say(f"[还原] 没有 Plugins/{PLUGIN_DIR_NAME}/")

    rep = remove_script_plugin(game_dir, emit=emit)
    removed.extend(rep.get("removed") or [])

    if not font_name:
        for b in bodies:
            font_name = _copied_font_name(b)
            if font_name:
                break
    if font_name:
        fp = os.path.join(game_dir, "Fonts", font_name)
        if os.path.isfile(fp):
            try:
                os.remove(fp)
                removed.append(f"Fonts/{font_name}")
                say(f"[还原] 已删除 Fonts/{font_name}")
            except OSError as e:
                say(f"[还原] 删除 Fonts/{font_name} 失败：{e}")

    if not removed:
        say("[还原] 没有找到本工具植入的插件")
    say("[还原] 插件已移除 —— 记得再点一次「加载插件并编译」或手动"
        "重编 PluginScripts.rxdata，否则游戏仍会加载已编译进去的那份")
    return {"removed": removed, "scripts": rep}


# ================================================================
# 没有插件目录的游戏：把插件拼成一个脚本，追加到脚本的最后
# ================================================================
def scripts_container(game_dir):
    """
    游戏脚本的落盘位置 → ("file", Data/Scripts 目录) / ("rxdata", 路径) /
    (None, None)。

    ★ 解包过（Data/Scripts 里有 .rb）就写文件；否则改 Scripts.rxdata；
      Scripts.rxdata 不在时退回 ScriptsBackup.rxdata。
    """
    sdir = GS.scripts_dir(game_dir)
    if os.path.isdir(sdir):
        for _dp, _dn, fs in os.walk(sdir):
            if any(str(f).endswith(".rb") for f in fs):
                return "file", sdir
    rx = GS.rxdata_path(game_dir)
    if os.path.isfile(rx):
        return "rxdata", rx
    bak = os.path.join(GS.data_dir(game_dir), GS.BACKUP_NAME)
    if os.path.isfile(bak):
        return "rxdata", bak
    return None, None


def _settings_text(src_dir, font_file, family, copied):
    """读插件 Settings.rb → 写入字体名与植入标记后的文本。"""
    p = os.path.join(src_dir, PLUGIN_SETTINGS_FILE)
    with io.open(p, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    text = re.sub(r"^# (Copied|Game) font:.*\n", "", text, flags=re.M)
    mark = (f"# Copied font: {os.path.basename(font_file)}\n" if copied
            else f"# Game font: {os.path.basename(font_file)}\n")
    text = "# " + PLUGIN_INJECT_MARK + "\n" + mark + text
    text, n = re.subn(
        r"^(\s*" + PLUGIN_FONT_ATTR + r"\s*=\s*)([\"'])([^\"']*)\2",
        lambda m: f"{m.group(1)}{m.group(2)}{family}{m.group(2)}",
        text, flags=re.M)
    return text, n


def build_script_body(src_dir, font_file, family, copied):
    """
    把插件的 Settings.rb + Tools.rb 拼成一个可以直接塞进脚本的 .rb。
    返回 (脚本文本, 字体替换处数)。
    """
    settings, n = _settings_text(src_dir, font_file, family, copied)
    with io.open(os.path.join(src_dir, PLUGIN_TOOLS_FILE), "r",
                 encoding="utf-8", errors="replace") as f:
        tools = f.read()
    head = (f"# {SCRIPT_HEAD_MARK}\n"
            f"# 由「宝可梦同人游戏翻译工具」自动插到本游戏 Main 之前，\n"
            f"# 想撤掉请用工具里的「还原」，不要手删。\n"
            f"# (RGSS 从上往下执行脚本、读到 Main 就进游戏主循环，\n"
            f"#  所以本脚本必须待在 Main 上面才有用。)\n")
    body = head + settings.rstrip("\n") + "\n\n" + tools.lstrip("\n")
    if not body.endswith("\n"):
        body += "\n"
    return body, n


def _title_bytes(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    text = getattr(value, "text", None)
    if text is not None:
        return str(text).encode("utf-8", "replace")
    return str(value).encode("utf-8", "replace")


def _is_our_script(entry):
    """Scripts.rxdata 里的这一条是不是本工具塞进去的脚本？"""
    try:
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            return False
        return SCRIPT_TITLE.encode("utf-8") in _title_bytes(entry[1])
    except Exception:
        return False


def _title_text(entry):
    """脚本条目的标题 → str（RubyString / bytes 都能吃）。"""
    try:
        return _title_bytes(entry[1]).decode("utf-8", "replace")
    except Exception:
        return ""


def _main_index(entries):
    """
    找「Main」那条脚本的下标（有多条就取最后一条；找不到返回 None）。

    ★ RGSS 读到 Main 就开始跑游戏，所以插件必须插在它**前面**。
    """
    found = None
    for i, e in enumerate(entries):
        if _MAIN_TITLE_RE.match(_title_text(e).strip()):
            found = i
    return found


def _next_script_id(entries):
    """
    给新脚本挑一个没被占用的正整数 id。

    ★ id 只是编辑器里的编号（这些游戏里的 id 本来就是随机大数），RGSS 按数组
      顺序加载；用小正整数可以躲开 Ruby 1.8 Marshal 写 4 字节整数时的坑。
    """
    used = set()
    for e in entries:
        try:
            v = e[0]
        except Exception:
            continue
        if isinstance(v, int) and 0 < v < 2 ** 30:
            used.add(v)
    n = 1
    while n in used:
        n += 1
    return n


def _script_file_name(scripts_dir):
    """
    解包游戏（Data/Scripts/ 目录）里给注入的脚本挑文件名 →
    (文件名, 是否保证排在 Main 之前)。

    加载顺序按文件名排序，所以要挑一个「排在最靠后的普通脚本之后、Main 之前」
    的名字：拿 Main 的编号前缀减一，例如 999_Main.rb → 998_pkmn_chinese_text.rb。
    """
    try:
        names = sorted(os.listdir(scripts_dir))
    except OSError:
        names = []
    mains = sorted(
        n for n in names
        if _MAIN_TITLE_RE.match(os.path.splitext(n)[0].strip() or n))
    for m_name in mains:
        m = re.match(r"^(\d+)", m_name)
        if m:
            n = max(0, int(m.group(1)) - 1)
            return (f"{n:0{len(m.group(1))}d}_{SCRIPT_FILE_STEM}.rb", True)
    return (SCRIPT_FILE_NAME, False)


def _our_files(scripts_dir):
    """目录里本工具写过的脚本文件（按正文里的标记认，只认名字不保险）。"""
    out = []
    try:
        names = sorted(os.listdir(scripts_dir))
    except OSError:
        return out
    for n in names:
        if not str(n).endswith(".rb"):
            continue
        p = os.path.join(scripts_dir, n)
        if not os.path.isfile(p):
            continue
        try:
            with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(600)
        except OSError:
            continue
        if PLUGIN_INJECT_MARK in head or SCRIPT_HEAD_MARK in head:
            out.append(p)
    return out


def inject_script_plugin(game_dir, src_dir, font_file, family, copied,
                         emit=None):
    """
    把插件拼成一个脚本写进游戏脚本里。

      · 没解包 → 插一条到 Scripts.rxdata 里 **Main 之前**（先备份；已经注入
        过的先移除，所以反复执行不会堆好几份）；
      · 解包成 Data/Scripts/ → 写一个「排在最靠后的普通脚本之后、Main 之前」
        的 .rb 文件。

    ★ 为什么一定要在 Main 之前：RGSS 从上往下依次执行脚本，读到 Main 就进
      游戏主循环 —— 挂在 Main 后面的脚本永远不会被执行。

    返回 {"mode", "where", "backup", "scripts", "bytes", "ordered"}。
    """
    def say(msg):
        if emit:
            emit(msg)

    body, _n = build_script_body(src_dir, font_file, family, copied)
    mode, path = scripts_container(game_dir)
    if mode is None:
        raise FileNotFoundError(
            "这个游戏里既没有 Data/Scripts 目录，也没有 Data/Scripts.rxdata "
            "—— 找不到可以写脚本的地方")

    if mode == "file":
        for old in _our_files(path):        # 幂等：先删上次注入的（含旧名字）
            try:
                os.remove(old)
                say(f"[插件] 先删掉上次注入的"
                    f" Data/Scripts/{os.path.basename(old)}")
            except OSError as e:
                say(f"[插件] 删不掉 {os.path.basename(old)}：{e}")
        name, ordered = _script_file_name(path)
        p = os.path.join(path, name)
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(body)
        if ordered:
            say(f"[插件] 已写出脚本 Data/Scripts/{name}"
                f"（{len(body.encode('utf-8')):,} 字节）"
                f"—— 名字排在 Main 之前，会被执行")
        else:
            say(f"[插件] ⚠ 已写出 Data/Scripts/{name}，但这个游戏的脚本名没有"
                f"编号前缀，**没法保证它排在 Main 之前**。RGSS 读到 Main 就开始"
                f"跑游戏，Main 后面的脚本不执行；万一没生效，请把它改名到 "
                f"Main 之前。")
        return {"mode": "file", "where": p, "backup": None,
                "ordered": ordered, "scripts": 0,
                "bytes": len(body.encode("utf-8"))}

    with open(path, "rb") as f:
        obj = _rb_load(f)
    if not isinstance(obj, list):
        raise ValueError(f"{path} 不是脚本数组，没法追加脚本")

    kept = [e for e in obj if not _is_our_script(e)]
    dropped = len(obj) - len(kept)
    if dropped:
        say(f"[插件] 先移除了之前注入的 {dropped} 个脚本（重复注入不会堆积）")

    entry = [_next_script_id(kept), _to_bytes(SCRIPT_TITLE),
             zlib.compress(body.encode("utf-8"))]
    at = _main_index(kept)
    has_main = at is not None
    if not has_main:
        at = len(kept)
        say("[插件] ⚠ 脚本列表里没找到 Main，只能放在最后 —— 万一游戏没生效，"
            "请手动把这条 [pkmn] 脚本移到 Main 上面")
    else:
        say(f"[插件] 插件脚本插在 Main 之前（第 {at + 1} 条 / 共 "
            f"{len(kept) + 1} 条）")
    kept.insert(at, entry)

    bak = f"{path}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
    shutil.copyfile(path, bak)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        _rb_write(f, kept)
    os.replace(tmp, path)
    say(f"[插件] 已写进 {os.path.basename(path)}（共 {len(kept)} 个脚本，"
        f"原文件已备份：{os.path.basename(bak)}）")
    log.info("脚本方式植入插件：%s → %s（%d 个脚本，本插件在第 %d 条，"
             "Main 在第 %s 条）", game_dir, path, len(kept), at,
             _main_index(kept))
    return {"mode": "rxdata", "where": path, "backup": bak,
            "scripts": len(kept), "dropped": dropped,
            "ordered": has_main, "index": at,
            "bytes": len(body.encode("utf-8"))}


def _script_bodies(game_dir):
    """读出本工具注入的那些脚本正文（还原时用来找 `# Copied font:` 标记）。"""
    mode, path = scripts_container(game_dir)
    if mode == "file":
        out = []
        for p in _our_files(path):
            try:
                out.append(io.open(p, "r", encoding="utf-8",
                                   errors="replace").read())
            except OSError:
                pass
        old = os.path.join(path, SCRIPT_FILE_NAME)   # 万一标记被改过
        if os.path.isfile(old):
            try:
                out.append(io.open(old, "r", encoding="utf-8",
                                   errors="replace").read())
            except OSError:
                pass
        return out
    if mode != "rxdata":
        return []
    try:
        with open(path, "rb") as f:
            obj = _rb_load(f)
    except Exception:
        return []
    out = []
    if isinstance(obj, list):
        for e in obj:
            if not _is_our_script(e):
                continue
            try:
                out.append(zlib.decompress(bytes(e[2])).decode("utf-8",
                                                               "replace"))
            except Exception:
                pass
    return out


def remove_script_plugin(game_dir, emit=None):
    """删掉本工具塞进脚本里的那份（rxdata 条目或那个 .rb 文件）。"""
    def say(msg):
        if emit:
            emit(msg)

    mode, path = scripts_container(game_dir)
    removed = []
    if mode is None:
        return {"removed": removed}
    if mode == "file":
        targets = list(_our_files(path))
        old = os.path.join(path, SCRIPT_FILE_NAME)
        if os.path.isfile(old) and old not in targets:
            targets.append(old)
        for p in targets:
            try:
                os.remove(p)
                removed.append(f"Data/Scripts/{os.path.basename(p)}")
                say(f"[还原] 已删除 Data/Scripts/{os.path.basename(p)}")
            except OSError as e:
                say(f"[还原] 删除 {os.path.basename(p)} 失败：{e}")
        return {"removed": removed}

    try:
        with open(path, "rb") as f:
            obj = _rb_load(f)
    except Exception as e:
        say(f"[还原] 读不了 {os.path.basename(path)}：{e}")
        return {"removed": removed}
    if not isinstance(obj, list):
        return {"removed": removed}
    kept = [e for e in obj if not _is_our_script(e)]
    n = len(obj) - len(kept)
    if not n:
        return {"removed": removed}
    bak = f"{path}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
    shutil.copyfile(path, bak)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        _rb_write(f, kept)
    os.replace(tmp, path)
    removed.append(f"{os.path.basename(path)} 里的 {n} 个脚本")
    say(f"[还原] 已从 {os.path.basename(path)} 里删掉 {n} 个注入的脚本"
        f"（原文件已备份：{os.path.basename(bak)}）")
    return {"removed": removed, "dropped": n, "backup": bak}
