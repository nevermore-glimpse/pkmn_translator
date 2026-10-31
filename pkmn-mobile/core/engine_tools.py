# -*- coding: utf-8 -*-
"""
引擎级工具：基准脚本覆盖、多种「开启 DEBUG」方式。

面向同人游戏的日常需求，三块：

  ① 基准脚本覆盖
     把官方同版本引擎里某几个脚本（默认是 debug 菜单定义）**整份替换**掉
     游戏里对应的那份。改前提醒风险、先备份；支持把英文菜单名/说明替换成
     随工具内置的中文（见 scripts/essentials_src/debug_menu_zh.json）。
     ★ 另有 `overwrite_scene_map()`：「用基准覆盖地图更新」—— 只把
       **Scene_Map** 整份盖回官方版（不翻译），给下面方式②③④铺路。

  ③ 多种开启 DEBUG 方式
     ① 写 Main 的 $DEBUG=true；
     ② 删各处 $DEBUG 条件（认不出时 `add_debug_strip_from_baseline()`
        按版本基准在对应位置补「免条件」的代码）；
     ③ F6 键 → 直接设 $DEBUG + 提示（不再判断 !$DEBUG）；
     ④ F6 键 → 直接打开调试菜单；
     ⑤ 除虫喷雾 → 设 $DEBUG；
     ⑥ 除虫喷雾 → 直接打开调试菜单；
     ⑦ 调试启动器（见 launcher）。
     按引擎版本 / 代码形态自动适配注入位置。

依赖：game_scripts（脚本读）、essentials_base（基准比对）、engine_src。
"""
import io
import os
import re
import shutil
import time
import zlib

import engine_src
import game_scripts as GS
from rubymarshal.classes import Symbol
from logger import get_logger

log = get_logger("engine_tools")

# 基准脚本存放目录名（随工具分发）
SRC_DIR_NAME = os.path.join("scripts", "essentials_src")
# 覆盖时的备份标记
BAK_MARK = ".pkmn-overwrite-"


# ================================================================
# ① 基准脚本覆盖
# ================================================================
def debug_menu_rel_files(version):
    """某版本官方引擎里 debug 菜单定义脚本的**相对路径**列表。"""
    return engine_src.debug_menu_files(version)


def _norm_script_name(name):
    """脚本名归一化：只留小写字母数字（中文名会归一成空串，正好永不匹配）。"""
    return re.sub(r"[^0-9a-z]+", "", str(name).lower())


# ================================================================
# 换字体时同步改「引擎脚本里的字体定义」
# ================================================================
# 为什么光改插件不够：
#   · 插件的 Settings.rb 只换 MessageConfig 里的那几个常量，别的界面不跟着走；
#   · v19 的字体来自 `Settings::FONT_OPTIONS`，玩家在选项里一挑就回去了；
#   · 引擎脚本里的那几个常量才是「游戏默认字体」，改了之后各处一起生效。
#
#   各版本定义在哪（都取自 scripts/essentials_src/<版本>/ 的官方源码）：
#     16 / 17 / 17.2   SpriteWindow    FontName / SmallFontName / NarrowFontName
#     18 / 18.1        MessageConfig   同上
#     19               Settings        FONT_OPTIONS（选项里的字体列表，改第 1 条）
#     19.1 ~ 21.1      MessageConfig   FONT_NAME / SMALL_FONT_NAME / NARROW_FONT_NAME
FONT_BAK_MARK = ".pkmn-font-"
FONT_OLD_CONSTS = ("FontName", "SmallFontName", "NarrowFontName")
FONT_NEW_CONSTS = ("FONT_NAME", "SMALL_FONT_NAME", "NARROW_FONT_NAME")
FONT_RULES = (
    (("16", "17", "17.2"), "SpriteWindow", FONT_OLD_CONSTS, "MessageConfig"),
    (("18", "18.1"), "MessageConfig", FONT_OLD_CONSTS, "MessageConfig"),
    (("19",), "Settings", ("FONT_OPTIONS",), "Settings"),
    (("19.1", "20", "20.1", "21", "21.1"), "MessageConfig", FONT_NEW_CONSTS,
     "MessageConfig"),
)


def font_rule(version):
    """
    版本号 → (改哪个脚本, 改哪些常量, 该脚本里必须有的模块名)。
    认不出返回 None。
    """
    v = str(version or "").strip()
    if not v:
        return None
    for keys, sname, consts, module in FONT_RULES:
        if v in keys:
            return sname, consts, module
    m = re.match(r"^(\d+)", v)              # 17.0 / 18.2 这种只认主版本
    if m:
        for keys, sname, consts, module in FONT_RULES:
            if any(k.split(".")[0] == m.group(1) for k in keys):
                return sname, consts, module
    return None


def _font_pat(const):
    """某个字体常量的匹配式（FONT_OPTIONS 是列表，取第 1 个字符串）。"""
    if const == "FONT_OPTIONS":
        return re.compile(r"(FONT_OPTIONS\s*=\s*\[\s*)([\"'])([^\"']*)\2")
    return re.compile(r"^([ \t]*" + const + r"[ \t]*=[ \t]*)([\"'])([^\"']*)\2",
                      re.M)


def _font_found(text, consts):
    """这份脚本里定义了哪些字体常量 → [常量名, ...]。"""
    return [c for c in consts if _font_pat(c).search(text or "")]


def _font_sub(text, consts, family):
    """把字体常量换成 family → (新文本, [改到的常量名])。"""
    changed = []
    for c in consts:
        def _rep(m, _c=c):
            if m.group(3) == family:
                return m.group(0)
            changed.append(_c)
            return f"{m.group(1)}{m.group(2)}{family}{m.group(2)}"
        text = _font_pat(c).sub(_rep, text)
    return text, changed


# ---------------------------------------------------------------------------
# 全库字体替换：常量之外，老游戏还会把字体名硬编码在别处
#   pbSetSystemFontName("OPPOSans") / pbTryFonts(MessageConfig::FontName,
#   "OPPOSans", "OPPOSans") / Font.default_name = "Arial" /
#   bitmap.font.name = "Arial" / FONT_OPTIONS = ["Power Green", ...]
# 只改一个脚本的三/四个常量，这些地方仍会把界面拉回旧字体 —— 用户要的是
# 「所有和字体相关的脚本里的字体都换掉」，所以下面全库扫一遍。
_FONT_CONST_ALL = re.compile(
    r"(\b(?:SMALL_FONT_NAME|NARROW_FONT_NAME|FONT_NAME|SmallFontName"
    r"|NarrowFontName|FontName)[ \t]*=[ \t]*)([\"'])([^\"'\r\n]*)\2")
_FONT_SETCALL = re.compile(
    r"(\bpb(?:SetSystem|SetSmall|SetNarrow)FontName[ \t]*\([ \t]*)"
    r"([\"'])([^\"'\r\n]*)\2")
_FONT_DEFAULT_ONE = re.compile(
    r"(\bFont\.default_name[ \t]*=[ \t]*)([\"'])([^\"'\r\n]*)\2")
_FONT_BITMAP_ONE = re.compile(
    r"(\.font\.name[ \t]*=[ \t]*)([\"'])([^\"'\r\n]*)\2")
_FONT_TRY_CALL = re.compile(r"(\bpbTryFonts[ \t]*\()([^)]*)(\))")
_FONT_DEFAULT_ARR = re.compile(
    r"(\bFont\.default_name[ \t]*=[ \t]*\[)([^\]]*)(\])")
_FONT_OPTIONS_ARR = re.compile(
    r"(\bFONT_OPTIONS[ \t]*=[ \t]*\[)([^\]]*)(\])")


def _font_lit(m, family, changed):
    """单引号/双引号字面量：{prefix}{quote}{value}{quote}。"""
    old = m.group(3)
    if old == family:
        return m.group(0)
    changed.append(old)
    return f"{m.group(1)}{m.group(2)}{family}{m.group(2)}"


def _font_quoted_inner(block, family, changed):
    """把一个括号块里**所有**字符串字面量换成 family（保留常量引用）。"""
    def _rep(m):
        old = m.group(2)
        if old == family:
            return m.group(0)
        changed.append(old)
        return f"{m.group(1)}{family}{m.group(1)}"
    return re.sub(r"([\"'])([^\"'\r\n]*)\1", _rep, block)


def _font_sub_all(text, family):
    """把一份脚本里**所有**字体定义换成 family → (新文本, [旧值...])。"""
    changed = []
    text = _FONT_CONST_ALL.sub(lambda m: _font_lit(m, family, changed), text)
    text = _FONT_SETCALL.sub(lambda m: _font_lit(m, family, changed), text)
    text = _FONT_DEFAULT_ONE.sub(lambda m: _font_lit(m, family, changed), text)
    text = _FONT_BITMAP_ONE.sub(lambda m: _font_lit(m, family, changed), text)

    def _arr(m):
        return (m.group(1)
                + _font_quoted_inner(m.group(2), family, changed)
                + m.group(3))

    text = _FONT_TRY_CALL.sub(_arr, text)
    text = _FONT_DEFAULT_ARR.sub(_arr, text)
    text = _FONT_OPTIONS_ARR.sub(_arr, text)
    return text, changed


def _font_script(game_dir, sname, consts, module):
    """
    找「字体定义」在哪份脚本里 → (脚本 dict, 是否按脚本名找到的)：
      ① 先按脚本名找（v16/17.2 在 SpriteWindow、v18.1 在 MessageConfig…）；
      ② 找不到（同人作改了名 / 合并了脚本）就全库扫一遍，认「真的定义了这些
         常量、而且带对应 module」的那一份 —— 免得改到不相干的同名常量。
    """
    tgt = find_game_script(game_dir, sname)
    if tgt and _font_found(tgt["text"], consts):
        return tgt, True
    if module:
        for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                               both=True):
            if f"module {module}" not in text:
                continue
            if _font_found(text, consts):
                return {"mode": mode, "key": key, "path": path,
                        "name": name, "text": text}, False
    return tgt, True


def patch_engine_font(game_dir, family, version=None, emit=None):
    """
    把游戏引擎脚本里**所有**字体定义改成 family（改前先备份，可还原）。

    ★ 用户要求：不只改「那个脚本」的三四个常量，而是全库扫一遍 ——
      老游戏常把字体名写死在 pbSetSystemFontName("OPPOSans") /
      pbTryFonts(..., "OPPOSans", ...) / Font.default_name = "..." /
      bitmap.font.name = "..." / FONT_OPTIONS = [...] 里；
      只改常量的话，这些地方一跑就把界面拉回旧字体，现在一并换掉。

    返回 {"ok", "script", "scripts", "consts", "backup", "reason", "notes"}；
    没找到可改的地方时 ok=True + reason（不写盘），和旧行为一致。
    """
    def say(msg):
        if emit:
            emit(msg)

    if not family:
        return {"ok": False, "reason": "字体名为空", "notes": []}

    ver = version
    if ver is None:
        try:
            import essentials_base as EB
            ver = EB.detect_version(game_dir)
        except Exception:
            ver = ""
    rule = font_rule(ver)
    if not rule:
        # 版本认不出：两套常量名都试，按内容找
        rule = ("MessageConfig", FONT_OLD_CONSTS + FONT_NEW_CONSTS,
                "MessageConfig")
    sname, consts, module = rule

    # ★ 全库扫描：解包 .rb 与 Scripts.rxdata 两处都要改（见 game_scripts）。
    hits = []            # [(脚本名, [旧值...], 备份路径)]
    seen = set()
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                            both=True):
        sig = (mode, key)
        if sig in seen:
            continue
        seen.add(sig)
        if not text:
            continue
        new_text, changed = _font_sub_all(text, family)
        if not changed:
            continue
        rec = {"mode": mode, "key": key, "path": path,
               "name": name, "text": text}
        try:
            bak = _write_script(rec, new_text, emit=emit, mark=FONT_BAK_MARK)
        except Exception as e:                       # noqa: BLE001
            say(f"[字体] ⚠ 改「{name}」失败：{e}")
            continue
        hits.append((name, sorted(set(changed)), bak))

    if not hits:
        # 说明「为什么没改」：按脚本名找一下那个定义脚本，给出具体原因
        tgt, _by_name = _font_script(game_dir, sname, consts, module)
        where = f"「{tgt['name']}」" if tgt else f"（{sname}）"
        reason = f"{where}里没有可改的字体定义，或已经是「{family}」"
        say(f"[字体] {reason}（引擎脚本原样不动）")
        return {"ok": True, "script": tgt["name"] if tgt else "",
                "scripts": [], "consts": [], "backup": None,
                "reason": reason, "notes": []}

    names = [h[0] for h in hits]
    notes = [f"[字体] 「{n}」：{'、'.join(vals)} → 「{family}」"
             for n, vals, _b in hits]
    summary = (f"[字体] 已改 {len(hits)} 个脚本的字体定义"
               f"（{'、'.join(names[:4])}{'…' if len(names) > 4 else ''}）"
               f" → 「{family}」，原文件均已备份")
    say(summary)
    return {"ok": True, "script": "、".join(names), "scripts": names,
            "consts": sorted({v for _n, vals, _b in hits for v in vals}),
            "backup": hits[0][2], "reason": "",
            "notes": [summary] + notes}


def restore_engine_font(game_dir, emit=None):
    """把本工具改过的引擎字体定义还原回去（只认 .pkmn-font-*.bak）。"""
    def say(msg):
        if emit:
            emit(msg)
    done = []
    for bak in sorted(_list_backups(game_dir, mark=FONT_BAK_MARK)):
        target = bak.split(FONT_BAK_MARK)[0]
        if not os.path.exists(bak):
            continue                     # 已经还原过（同一备份只处理一次）
        try:
            if os.path.exists(target):
                os.remove(target)
            os.rename(bak, target)
            done.append(os.path.basename(target))
            say(f"[字体] 已还原 {os.path.basename(target)} 的字体定义")
        except OSError as e:
            say(f"[字体] ⚠ 还原 {os.path.basename(target)} 失败：{e}")
    return {"ok": True, "restored": done}


def find_game_script(game_dir, name):
    """
    在游戏脚本里按**脚本名**找一份 → {mode, key, path, name, text}。
    找不到返回 None。

    ★★ 匹配要**容忍编号 / 路径前缀**（这是以前的一个真 bug）：
      游戏里的脚本名很少是干净的 `Scene_Map`，常见形态有
        · v19+ 官方：`003 Game processing/002_Scene_Map`
        · 解包 .rb：`900_Scene_Map.rb`
        · 同人作：`003_Game processing__002_Scene_Map`
      以前只做**全等**比较（把数字和分隔符去掉后比）→ 这些形态一律匹配不上，
      于是「方式② 删条件」和「用基准覆盖」对它们**静默空转**（日志只有一句
      「没找到脚本」，用户完全看不出为什么没效果）。
      ⇒ 现在三级匹配：① 全等 ② 尾部对齐（`…endswith("scenemap")`）
        ③ 都不中才算没有。同级里取**归一化后最短**的那个（最贴近纯脚本名），
        再按「解包 .rb 优先」。
    """
    want = _norm_script_name(name)
    # ★ 查询名归一化成空串（纯中文名等）时**不做任何匹配** ——
    #   否则「游戏里的中文脚本名」和「中文查询词」会双双归一成 "" 而相等，
    #   凭空匹配上一个不相干的脚本。
    if not want:
        return None
    exact, tail = [], []
    for mode, key, path, sname, text in GS.iter_named_scripts(game_dir,
                                                             both=True):
        s = _norm_script_name(sname)
        if not s:
            continue
        rec = {"mode": mode, "key": key, "path": path,
               "name": sname, "text": text}
        if s == want:
            exact.append(rec)
        elif s.endswith(want):
            tail.append(rec)
    hits = exact or tail
    if not hits:
        return None
    hits.sort(key=lambda h: (len(_norm_script_name(h["name"])),
                              0 if h["mode"] == "file" else 1))
    return hits[0]


def _create_target_plan(game_dir, sname, index=1):
    """
    目标游戏里没有这个脚本 → 算「新建到哪儿」。

    · 有 `Data/Scripts.rxdata` → 追加一个条目（引擎真正读的就是它）；
    · 只有解包的 `Data/Scripts/` → 写一个 `.rb` 文件；
    · 两者都没有（压根没有脚本）→ None，建不了。

    ★ **loader 形态优先写 .rb 文件**：这类游戏的 `Scripts.rxdata` 只有一条
      `load_scripts_from_folder(...)`，往里面追加条目虽然也能被eval，
      但排在 loader 之后 —— 而 loader 一跑就把游戏整个 load 完了，
      新脚本既排不到 Main 前、文件名也过不了 loader 的四位数字前缀过滤。
      所以认得出 loader 目录时直接往那个目录里写文件。
    """
    loader_dir = GS.loader_scripts_dir(game_dir)
    if loader_dir and os.path.isdir(loader_dir):
        fn = GS.script_file_name(game_dir, sname, index=index)
        return {"mode": "file", "path": os.path.join(loader_dir, fn),
                "title": sname}
    rx = GS.rxdata_path(game_dir)
    if rx and os.path.isfile(rx):
        return {"mode": "rxdata", "path": rx, "title": sname}
    sdir = GS.scripts_dir(game_dir)
    if sdir and os.path.isdir(sdir):
        return {"mode": "file",
                "path": os.path.join(sdir, sname + ".rb"), "title": sname}
    return None


def _create_script_everywhere(game_dir, sname, text, index=1):
    """
    把「游戏里没有」的新脚本**建到所有脚本落盘处**。

    ★ 用户要求：游戏如果既有解包 `Data/Scripts/**.rb`、又有 `Data/Scripts.rxdata`，
      那么所有改动都要对**两处**生效（运行时读哪份取决于 Game.ini 的
      `Scripts=` 指向，只写一处会出现「改了没反应」）。新建脚本同理。

    · loader 形态（Scripts.rxdata 只是 `load_scripts_from_folder(...)`）：
      只往 loader 指的那个目录写 .rb —— 往 rxdata 追加既排不到 Main 前、
      文件名也过不了四位数字过滤。
    · 其余：rxdata 有就追加条目，解包 Data/Scripts 有就写 .rb，两个都做。

    返回 [{"mode","path"}, ...]；一处都建不了返回 []。
    """
    made = []
    loader_dir = GS.loader_scripts_dir(game_dir)
    if loader_dir and os.path.isdir(loader_dir):
        fn = GS.script_file_name(game_dir, sname, index=index)
        p = GS.add_script_file_at(os.path.join(loader_dir, fn), text)
        return [{"mode": "file", "path": p}]

    rx = GS.rxdata_path(game_dir)
    if rx and os.path.isfile(rx):
        _backup(rx)
        GS.add_rxdata_script(rx, sname, text)
        made.append({"mode": "rxdata", "path": rx})

    # 解包形态：真存在 .rb 才算（空目录 / 只有占位不算）
    if GS.script_dirs(game_dir):
        p = GS.add_script_file(game_dir, sname, text, index=index)
        if p:
            made.append({"mode": "file", "path": p})
    return made


def overwrite_plan(game_dir, version, files=None):
    """
    算「覆盖计划」→ [item, ...]，不写盘。

    两种 item：
      · 整份覆盖：{"kind":"script","src","name","target"}
      · 函数覆盖：{"kind":"func","src","name","func","target"}
        （v16 的「宝可梦 debug 菜单」是 PScreen_Party 里的 pbPokemonDebug，
          只换那个函数，不整份替换那个脚本）

    ★ 游戏里**没有**某个脚本时不算失败：item 里带 `create`（新建到哪儿），
      执行阶段会把基准里那一份**新增进去**（插在 Main 之前）。

    files=None 时用该版本内置的 debug 覆盖清单。
    """
    out = []
    for src in engine_src.engine_files(version, files=files):
        name = os.path.splitext(os.path.basename(src))[0]
        # 文件名形如 001_Debug_Menus → 脚本名 Debug_Menus（去编号前缀）
        sname = re.sub(r"^\d+_", "", name)
        tgt = find_game_script(game_dir, sname)
        item = {"kind": "script", "src": src, "name": sname, "target": tgt}
        if not tgt:
            item["create"] = _create_target_plan(game_dir, sname,
                                                 index=len(out) + 1)
            item["_idx"] = len(out) + 1
        out.append(item)
    for sname, fname in engine_src.overwrite_func_items(version):
        src = engine_src.script_src_path(version, sname)
        tgt = find_game_script(game_dir, sname)
        out.append({"kind": "func", "src": src, "name": sname,
                    "func": fname, "target": tgt})
    return out


def overwrite_engine_scripts(game_dir, version, translate=True, emit=None,
                             allow_missing=False, files=None):
    """
    用官方同版本脚本覆盖游戏里的对应脚本（默认 debug 菜单那 8 个）。

    translate=True 时，把英文菜单名 / 说明按内置对照表替换成中文。
    files 给定时只覆盖这几个（**相对版本目录**的路径，见
    `engine_src.script_rel_path`）—— 「用基准覆盖地图更新」就是这么用的。

    返回 dict：{"ok", "version", "written": [...], "skipped": [...],
                "backups": [...], "reason"}
    """
    def say(msg):
        if emit:
            emit(msg)

    rep = {"ok": False, "version": version, "written": [], "skipped": [],
           "backups": [], "created": 0, "reason": ""}
    plan = overwrite_plan(game_dir, version, files=files)
    if not plan:
        rep["reason"] = (f"没有内置 v{version} 的引擎脚本，无法覆盖。"
                         "（工具只内置了 debug 菜单相关脚本）")
        say(f"[覆盖] ✘ {rep['reason']}")
        return rep

    tr = engine_src.load_translations() if translate else {}
    n_tr = 0
    for item in plan:
        sname = item["name"]
        src = item["src"]
        fname = item.get("func")
        label = f"{sname}#{fname}" if fname else sname
        cp = None if item["target"] else item.get("create")
        if not item["target"] and not cp:
            if allow_missing:
                rep["skipped"].append((label, "游戏里没有这个脚本"))
                say(f"[覆盖] · 游戏里没有脚本「{label}」，也没有地方能新建，"
                    "跳过")
                continue
            rep["reason"] = (f"游戏里找不到脚本「{label}」，也没有地方能新建 ——"
                             f"这个游戏的脚本结构可能和官方 v{version} 不一样。")
            say(f"[覆盖] ✘ {rep['reason']}")
            return rep
        if not src or not os.path.isfile(src):
            if allow_missing:
                rep["skipped"].append((label, "工具里没有这个官方脚本"))
                say(f"[覆盖] · 工具里没有官方脚本「{label}」，跳过")
                continue
            rep["reason"] = f"工具里没有内置官方脚本「{label}」，无法覆盖。"
            say(f"[覆盖] ✘ {rep['reason']}")
            return rep
        try:
            with io.open(src, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            rep["reason"] = f"读官方脚本 {os.path.basename(src)} 失败：{e}"
            say(f"[覆盖] ✘ {rep['reason']}")
            return rep
        if translate and tr:
            text, k = engine_src.apply_translation(text, tr)
            n_tr += k
        if cp:
            # ★ 游戏里没有这个脚本 → 把基准里那一份**新增进去**
            #   （两处脚本落盘处都建：见 _create_script_everywhere）
            try:
                made = _create_script_everywhere(game_dir, sname, text,
                                                 index=item.get("_idx", 1))
            except (OSError, RuntimeError) as e:
                rep["reason"] = f"新建「{label}」失败：{e}"
                say(f"[覆盖] ✘ {rep['reason']}")
                return rep
            if not made:
                rep["reason"] = f"新建「{label}」失败：没有可写入的脚本位置"
                say(f"[覆盖] ✘ {rep['reason']}")
                return rep
            for m in made:
                if m["mode"] == "rxdata":
                    rep["backups"].append(m["path"])
            rep["written"].append(label)
            rep["created"] += 1
            where = "、".join(
                "追加进 Scripts.rxdata（排在 Main 之前）"
                if m["mode"] == "rxdata" else "写入 Data/Scripts"
                for m in made)
            say(f"[覆盖] ⊕ 游戏里没有「{label}」，已按基准**新建**"
                f"（{where}）")
            continue
        tgt = item["target"]
        if fname:
            # 函数级：只把那个函数抠出来换进游戏脚本，其余原样保留
            new_func = engine_src.extract_func(text, fname)
            if not new_func:
                rep["reason"] = f"官方脚本里没有 {fname} 函数，跳过。"
                say(f"[覆盖] · {rep['reason']}")
                rep["skipped"].append((label, rep["reason"]))
                continue
            merged = engine_src.replace_func(tgt["text"], fname, new_func)
            if merged is None:
                rep["reason"] = (f"游戏脚本「{sname}」里找不到 {fname} 函数，"
                                 "结构可能不一样。")
                say(f"[覆盖] ✘ {rep['reason']}")
                if not allow_missing:
                    return rep
                rep["skipped"].append((label, rep["reason"]))
                continue
            if merged == tgt["text"]:
                rep["skipped"].append((label, "函数内容一致，无需改写"))
                say(f"[覆盖] · {label} 和游戏里的一模一样，跳过")
                continue
            text = merged
        try:
            bak = _write_script(tgt, text, emit=emit)
        except (OSError, RuntimeError) as e:
            rep["reason"] = f"写入「{label}」失败：{e}"
            say(f"[覆盖] ✘ {rep['reason']}")
            return rep
        rep["written"].append(label)
        if bak:
            rep["backups"].append(bak)
        how = "函数级覆盖" if fname else "整份覆盖"
        say(f"[覆盖] ✔ 已用官方 v{version} 脚本{how}「{label}」"
            f"（{'解包文件' if tgt['mode'] == 'file' else 'rxdata 条目'}）")
    rep["ok"] = True
    extra = f"（其中 {rep['created']} 处是游戏里没有、按基准新建的）" \
        if rep.get("created") else ""
    if translate:
        say(f"[覆盖] 共替换 {len(rep['written'])} 处，"
            f"翻译 {n_tr} 条菜单文本{extra}")
    else:
        say(f"[覆盖] 共替换 {len(rep['written'])} 处{extra}")
    log.info("基准覆盖：%s v%s → %d 处", game_dir, version,
             len(rep["written"]))
    return rep


# ---- 任务3：用基准覆盖「地图更新」（Scene_Map） ----
def scene_map_rel_file(version):
    """官方基准里 Scene_Map 脚本的相对路径（这个版本没有 → ""）。"""
    rel = engine_src.script_rel_path(version, "Scene_Map")
    return [rel] if rel else []


def scene_map_plan(game_dir, version):
    """
    「用基准覆盖地图更新」的计划 → item（同 overwrite_plan 的 item 结构）。

    找不到官方 Scene_Map / 游戏里没有 Scene_Map 时返回 None。
    """
    files = scene_map_rel_file(version)
    if not files:
        return None
    plan = overwrite_plan(game_dir, version, files=files)
    return plan[0] if plan else None


def overwrite_scene_map(game_dir, version, emit=None, allow_missing=False):
    """
    任务3：用**官方同版本**的 Scene_Map 整份覆盖游戏里的 Scene_Map。

    为什么要单独做这一件事：同人游戏常把 Scene_Map#update 改得面目全非
    （把 F9 调试菜单的 `$DEBUG` 条件删掉、插一堆自己的判断），于是
    「方式二：删 $DEBUG 条件」一个都认不出来。这时把官方那份盖回去，
    再跑方式二/方式三/方式四就有干净的落点了。

    ★ 和 debug 菜单覆盖不同：**不做中文翻译**（Scene_Map 不是菜单文本），
      但**同样先备份**（`.pkmn-overwrite-*.bak`，可用「还原覆盖」恢复）。
    """
    files = scene_map_rel_file(version)
    if not files:
        if emit:
            emit(f"[覆盖] ✘ 工具里没有内置 v{version} 的 Scene_Map 脚本")
        return {"ok": False, "reason": f"没有内置 v{version} 的 Scene_Map",
                "written": [], "backups": []}
    if emit:
        emit("[覆盖] 用官方基准覆盖「地图更新」（Scene_Map）—— "
             "只替换这一个脚本，改动前自动备份")
    return overwrite_engine_scripts(game_dir, version, translate=False,
                                    emit=emit, allow_missing=allow_missing,
                                    files=files)


def _write_script(tgt, text, emit=None, mark=None):
    """把 text 写进目标脚本（.rb 文件或 rxdata 条目），先备份。"""
    path = tgt["path"]
    bak = _backup(path, emit=emit, mark=mark)
    if tgt["mode"] == "file":
        with open(path, "rb") as f:
            cur = f.read().decode("utf-8", "replace")
        if "\r\n" in cur and "\r\n" not in text:
            text = text.replace("\n", "\r\n")
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return bak
    GS.write_rxdata_entry(path, tgt["key"], text, expect=tgt["text"])
    return bak


_overwritten = {}


def _backup(path, emit=None, mark=None):
    """备份一次（跨运行复用），与 debug_tool 同风格。mark 决定备份标记。

    ★ 缓存里的那份备份要**确认还在**：`restore_overwrite` 会把 .bak 改名回原位，
      同一进程里再改同一个文件时，旧缓存指向的那份已经不存在，直接返回它就会
      「改了文件却没有备份」——那正是「还原之后又开启一次」的场景。
    """
    mark = mark or BAK_MARK
    ap = (os.path.abspath(path), mark)
    old = _overwritten.get(ap)
    if old and os.path.exists(old):
        return old
    old = _find_backup(path, mark=mark)
    if old:
        _overwritten[ap] = old
        return old
    bak = f"{path}{mark}{_stamp()}.bak"
    os.rename(path, bak)
    shutil.copyfile(bak, path)
    _overwritten[ap] = bak
    if emit:
        emit(f"[覆盖]   原文件已备份：{os.path.basename(bak)}")
    return bak


def _find_backup(path, mark=None):
    mark = mark or BAK_MARK
    d = os.path.dirname(os.path.abspath(path))
    pref = os.path.basename(path) + mark
    try:
        hits = [os.path.join(d, f) for f in os.listdir(d)
                if f.startswith(pref) and f.endswith(".bak")]
    except OSError:
        return None
    hits.sort()
    return hits[0] if hits else None


def _stamp():
    return (time.strftime("%Y%m%d-%H%M%S")
            + f"{int(time.time() * 1000) % 1000:03d}")


def restore_overwrite(game_dir, emit=None):
    """把本工具「覆盖」过的脚本还原回去。"""
    def say(msg):
        if emit:
            emit(msg)
    baks = _list_backups(game_dir)
    done = []
    for bak in sorted(baks):
        target = bak.split(BAK_MARK)[0]
        if not os.path.exists(bak):
            continue                     # 已经还原过（同一备份只处理一次）
        try:
            if os.path.exists(target):
                os.remove(target)
            os.rename(bak, target)
            done.append(os.path.basename(target))
            say(f"[覆盖] 已还原 {os.path.basename(target)}")
        except OSError as e:
            say(f"[覆盖] ⚠ 还原 {os.path.basename(target)} 失败：{e}")
    return {"ok": True, "restored": len(done), "files": done}


def _list_backups(game_dir, mark=None):
    """
    这个游戏里所有的「本工具备份」→ [路径, ...]。

    ★ 必须去重：`Data` 的递归里**已经包含** `Data/Scripts`，两个根各扫一遍会
      把同一个 .bak 收两次。还原逻辑是「删目标 → 把 .bak 改回原名」，同一个
      备份被处理两次的第二趟就会「删掉刚还原出来的文件、再改名失败」——
      也就是**把游戏脚本删掉**（解包成 Data/Scripts/*.rb 的游戏必中）。
    """
    mark = mark or BAK_MARK
    uniq = {}
    for base in (GS.data_dir(game_dir), GS.scripts_dir(game_dir)):
        if not os.path.isdir(base):
            continue
        for dp, _dn, fs in os.walk(base):
            for f in fs:
                if mark in f and f.endswith(".bak"):
                    p = os.path.join(dp, f)
                    uniq[os.path.abspath(p).lower()] = p
    return list(uniq.values())


# ---- 通用小工具 ----
def _norm_eol(text):
    """
    统一行尾为 LF。

    ★ 基准（官方源码）是 LF，游戏 Scripts.rxdata 里多为 CRLF —— 拿基准文本
      做逐行处理之前先归一化，免得每行末尾都差一个 `\\r`。
    """
    if not text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ================================================================
# ③ 多种开启 DEBUG 方式
# ================================================================
# ★ 各引擎版本的注入点都不一样，这里**不按版本号分流**，而是按「代码长什么样」
#   逐个模式去认 —— 所以跨版本混搭（v16 的游戏里出现 v18 的写法）也能正确处理，
#   而且所有替换都保证不破坏语法（只删掉一个修饰词 / 注释掉一整行）。
#
#   穿墙（Game_Player#passable?）
#     v16 / v17    if $DEBUG and Input.press?(Input::CTRL)   →  if Input.press?(…)
#     v18 起       return true if $DEBUG and|&& Input.press?(Input::CTRL)
#   debug 菜单（Scene_Map#update）
#     v16 / v17    if $DEBUG and Input.press?(Input::F9)
#     v18 起       … elsif Input.press?(Input::F9) / $game_temp.debug_calling = true if $DEBUG
#   宝可梦 debug 菜单（PScreen_Party#pbPokemonScreen）
#     v16–v21      commands[cmdDebug = commands.length] = _INTL("Debug") if $DEBUG
#   除虫喷雾：PItem_ItemEffects / Item_Effects 的 pbRepel 函数开头
#
# ★ 编号 = GUI 下拉框里的「方式N」，与 _debug_mode_labels 一一对应：
#     ① main          写 Main 的 $DEBUG=true
#     ② keys          删各处 $DEBUG 条件
#     ③ special       F6 键 → 设 $DEBUG（直接开，不再判断 !$DEBUG）
#     ④ special_menu  F6 键 → 直接打开调试菜单（新，= 方式⑤ 的 F6 版）
#     ⑤ repel         除虫喷雾 → 设 $DEBUG
#     ⑥ repel_menu    除虫喷雾 → 直接打开调试菜单
#     ⑦ launcher      调试启动器
DEBUG_MODES = (
    ("main", "通用方式：给 Main 的 mainFunction 写 $DEBUG=true"),
    ("keys", "方式二：删除 F9 调试菜单 / 队伍调试 / 穿墙 的 $DEBUG 条件"),
    ("special", "方式三：F6 键 —— Scene_Map 里按 F6 直接开启调试模式"),
    ("special_menu", "方式四：F6 键 —— Scene_Map 里按 F6 直接打开调试菜单"),
    ("repel", "方式五：除虫喷雾 —— 使用时写入 $DEBUG=true"),
    ("repel_menu", "方式六：除虫喷雾 —— 直接打开调试菜单"),
    ("rewrite", "方式七：改名调试函数 —— 用基准改名函数顶掉原函数，按 T 开助手菜单"),
    ("launcher", "方式八：调试启动器 —— 生成 exe，双击进调试"),
)

_MARK = "[pkmn-debug]"
# 「别的功能」留下的标记文案：判断某个带标记的行属不属于当前这一块时，
# 撞上这些就说明已经越界了（见 patch_special_key 的 _marked_run_end）。
_FOREIGN_MARKS = ("方式二", "方式四", "方式五", "方式六", "方式七", "方式八",
                  "已去掉 $DEBUG", "原条件", "按基准补行", "翻译工具注入",
                  "pkmn-aide", "pbAide")

# 方式二要扫的脚本（找不到就跳过）
_KEYS_SCRIPTS = (
    "Game_Player",            # 穿墙
    "Scene_Map",              # F9 debug 菜单
    "PScreen_Party",          # 队伍菜单的 Debug 项（v16–v18）
    "UI_Party",               # 队伍菜单的 Debug 项（v19+）
    "UI_PauseMenu",           # 暂停菜单的 Debug 项（v19 / v19.1）
    "UI_Bag",                 # 背包的 Debug 项（v20+）
    "UI_PokemonStorage",      # 仓库的 Debug 项（v20+）
)

# 方式五 / 六：除虫喷雾所在脚本。
#   v19+ 叫 Item_Effects、v16–v18 叫 PItem_ItemEffects，
#   更老 / 改名的同人游戏里还见过 PokemonItemEffects（实测「宝可梦叛乱」）。
_REPEL_SCRIPTS = ("Item_Effects", "PItem_ItemEffects", "PokemonItemEffects")


def find_first_game_script(game_dir, names):
    """按脚本名依次试，返回第一个找到的（都找不到返回 None）。"""
    for n in names:
        tgt = find_game_script(game_dir, n)
        if tgt:
            return tgt
    return None


def find_repel_script(game_dir):
    """
    找含 `def pbRepel` 的脚本：先按名字，认不到就**按内容扫一遍**。

    ★ 名字靠不住 —— 同一款脚本在不同年代 / 不同同人作里叫法不一样；
      按内容兜底才不会在改名游戏上直接罢工。
    """
    tgt = find_first_game_script(game_dir, _REPEL_SCRIPTS)
    if tgt:
        return tgt
    for m, k, path, name, text in GS.iter_named_scripts(game_dir, both=True):
        if re.search(r"^[ \t]*def\s+pbRepel\b", text, re.M):
            return {"mode": m, "key": k, "path": path, "text": text,
                    "name": name}
    return None


# ---- 方式二：删除各处 $DEBUG 条件 ----
def patch_remove_debug_conditions(game_dir, emit=None):
    """
    方式二：把「需要 $DEBUG 才生效」的条件去掉，让穿墙 / F9 调试菜单 /
    队伍里的 Debug 项**无条件可用**。

    ★ 不按版本分流 —— 每个模式都独立匹配，认到就改；
      所有改动都只删修饰词或整行注释，不会产生语法错误。
    """
    def say(msg):
        if emit:
            emit(msg)
    out = {"ok": True, "targets": [], "reason": "", "changed": 0}
    for sname in _KEYS_SCRIPTS:
        tgt = find_game_script(game_dir, sname)
        if not tgt:
            continue
        new_text, n = _strip_debug_conds(tgt["text"])
        if not n:
            continue
        rec = {"script": sname, "where": str(tgt["key"]), "changes": n,
               "written": False}
        out["targets"].append(rec)
        try:
            _write_script(tgt, new_text, emit=emit)
        except (OSError, RuntimeError) as e:
            out["ok"] = False
            out["reason"] = f"改「{sname}」失败：{e}"
            say(f"[方式二] ✘ {out['reason']}")
            return out
        rec["written"] = True
        out["changed"] += n
        say(f"[方式二] ✔ 已去掉「{sname}」里的 {n} 处 $DEBUG 条件")
    if not out["changed"]:
        say("[方式二] · 没找到可改的 $DEBUG 条件（游戏可能已经去掉了）")
    return out


# 每一项：(正则, 替换模板)；只删修饰词 / 整行注释，绝不破坏语法
# ★ 两个坑（实测踩过）：
#   ① `Scripts.rxdata` 里的源码常用 **CRLF**，行尾那个 `\r` 会让 `$` 锚不上
#      → 所有行尾都要留 `(?P<cr>\r?)$`，替换时原样写回，别把那一行变成 LF。
#   ② 替换文案里**不能出现字面量 ` if $DEBUG`**，否则这条注释自己又会被
#      本表里的规则命中，重复点「开启 DEBUG」会越改越乱 → 文案写成
#      「已去掉 $DEBUG 条件」。改完必须幂等：第二次跑命中数为 0。
#   ③ `[^{}]` 会跨行，别用它包 proc 体，否则会跨行误匹配 → 一律 `[^{}\n]`。
_STRIP_PATS = (
    # v16 / v17 Game_Player：`if $DEBUG and Input.press?(Input::CTRL)`
    (re.compile(r"^([ \t]*)if\s+\$DEBUG\s+and\s+(?=Input\.press\?\(Input::"
                r"CTRL\))", re.M),
     r"\1if "),
    # v18 起 Game_Player：`return true if $DEBUG and|&& Input.press?(Input::CTRL)`
    (re.compile(r"^([ \t]*return\s+true\s+if\s+)\$DEBUG\s*(?:&&|and)\s+", re.M),
     r"\1"),
    # v16 / v17 Scene_Map：`if $DEBUG and Input.press?(Input::F9)`
    (re.compile(r"^([ \t]*)if\s+\$DEBUG\s+and\s+(?=Input\.press\?\(Input::"
                r"F9\))", re.M),
     r"\1if "),
    # v18 起 Scene_Map：`$game_temp.debug_calling = true if $DEBUG`
    (re.compile(r"^([ \t]*\$game_temp\.debug_calling\s*=\s*true)\s+if\s+"
                r"\$DEBUG[ \t]*(?P<tail>#.*?)?(?P<cr>\r?)$", re.M),
     r"\1  # " + _MARK + r" 已去掉 $DEBUG 条件\t\c"),
    # PScreen_Party / UI_Party / UI_PauseMenu / UI_Bag / UI_PokemonStorage：
    # `commands[cmdDebug = commands.length] = _INTL("Debug") if $DEBUG`
    (re.compile(r"^([ \t]*commands\[cmdDebug[^\n]*?)\s+if\s+\$DEBUG[ \t]*"
                r"(?P<tail>#.*?)?(?P<cr>\r?)$", re.M),
     r"\1  # " + _MARK + r" 已去掉 $DEBUG 条件\t\c"),
    # v20+ UI_Party / UI_PauseMenu：`"condition" => proc { |…| next $DEBUG },`
    (re.compile(r'^([ \t]*)"condition"\s*=>\s*proc\s*\{[^{}\n]*\$DEBUG'
                r'[^{}\n]*\}[ \t]*,?[ \t]*(?P<tail>#.*?)?(?P<cr>\r?)$', re.M),
     r'\1# ' + _MARK + r' 原条件："condition" => proc { … $DEBUG }（已去掉条件）'
     r"\t\c"),
    # v20+ UI_Party：`insert_index = ($DEBUG) ? 2 : 1` —— debug 项排第 2 位，
    #   恒取 2（规则只认这个精确三元式，不会误伤别的 `? :`）。
    #   ★ 替换串只能用 `\1`：`_expand()` 自己实现模板展开（`re.sub` 的模板
    #   语法走不通），只认 `\1` `\t` `\c`，**不认 `\g<1>`** —— 写了会被当
    #   字面量插进脚本里（实测插出过字面 `\g<1>2`）。`\1` 后面的空格是刻意
    #   加的，避免和字面的 `2` 连成 `\12`（`_expand` 取单个数字字符，
    #   其实能正确解析，但源码上容易让人误会）。
    (re.compile(r"^([ \t]*insert_index\s*=\s*)\(\$DEBUG\)\s*\?\s*2\s*:\s*1"
                r"[ \t]*(?P<tail>#.*?)?(?P<cr>\r?)$", re.M),
     r"\1 2" + r"  # " + _MARK + r" 已去掉 $DEBUG 插位条件\t\c"),
    # ---- 复合写法：`($DEBUG && <游戏自己加的条件>)` ----
    # ★ 上面那批规则只认光秃秃的 `$DEBUG`。同人游戏常把 $DEBUG 再包一层自己
    #   的条件 —— 实测「宝可梦灵魂石2」全游戏写的是
    #   `($DEBUG && $game_map.map_id != 455)`（某个地图上不给开调试）。
    #   于是这批规则一处都认不出来，方式二 报「没找到可改的 $DEBUG 条件」，
    #   而 Game_Player / UI_Party / UI_Bag / UI_PokemonStorage 里的条件其实
    #   还挂着 —— 属于**漏改 + 误报**。方式二 的语义本来就是「无条件可用」，
    #   所以整个括号条件一并去掉（与光秃秃写法得到的结果完全一致）。
    # v16 / v17 Game_Player / Scene_Map：`if ($DEBUG && …) and Input.press?(…)`
    (re.compile(r"^([ \t]*)if\s+\(\$DEBUG\s*&&\s*[^()\n]*\)\s*"
                r"(?:and|&&)\s+(?=Input\.press?\()", re.M),
     r"\1if "),
    # v18 起 Game_Player：`return true if ($DEBUG && …) && Input.press?(…)`
    (re.compile(r"^([ \t]*return\s+true\s+if\s+)\(\$DEBUG\s*&&\s*[^()\n]*\)"
                r"\s*(?:&&|and)\s+", re.M),
     r"\1"),
    # v18 起 Scene_Map：`$game_temp.debug_calling = true if ($DEBUG && …)`
    (re.compile(r"^([ \t]*\$game_temp\.debug_calling\s*=\s*true)\s+if\s+"
                r"\(\$DEBUG\s*&&\s*[^()\n]*\)[ \t]*(?P<tail>#.*?)?(?P<cr>\r?)$",
                re.M),
     r"\1  # " + _MARK + r" 已去掉 $DEBUG 条件\t\c"),
    # 队伍 / 背包 / 仓库的 Debug 项：`commands[cmdDebug…] = … if ($DEBUG && …)`
    (re.compile(r"^([ \t]*commands\[cmdDebug[^\n]*?)\s+if\s+"
                r"\(\$DEBUG\s*&&\s*[^()\n]*\)[ \t]*(?P<tail>#.*?)?(?P<cr>\r?)$",
                re.M),
     r"\1  # " + _MARK + r" 已去掉 $DEBUG 条件\t\c"),
    # v20+ UI_Party：`insert_index = (($DEBUG && …)) ? 2 : 1`
    (re.compile(r"^([ \t]*insert_index\s*=\s*)\(\(\$DEBUG\s*&&\s*[^()\n]*\)\)"
                r"\s*\?\s*2\s*:\s*1[ \t]*(?P<tail>#.*?)?(?P<cr>\r?)$", re.M),
     r"\1 2" + r"  # " + _MARK + r" 已去掉 $DEBUG 插位条件\t\c"),
)


def _expand(rep, m):
    """
    替换模板里的 `\\1` `\\2` → 对应分组（分到 None 当空串）；
    `\\t` → 原行尾注释（没有就当空串）；`\\c` → 原行尾的 \\r（保住 CRLF）。
    """

    def named(pat):
        gi = m.re.groupindex
        if pat in gi:
            return m.group(pat) or ""
        return ""

    def sub(mo):
        key = mo.group(1)
        if key == "t":
            tail = named("tail")
            return f"（原注释：{tail}）" if tail else ""
        if key == "c":
            return named("cr")
        return m.group(int(key)) or ""
    return re.sub(r"\\([0-9]|t|c)", sub, rep)


def _strip_debug_conds(text):
    """删掉各处「需要 $DEBUG 才生效」的条件 → (新文本, 改了几处)。"""
    n = 0
    for pat, rep in _STRIP_PATS:
        text, k = pat.subn(lambda m: _expand(rep, m), text)
        n += k
    return text, n


# ================================================================
# 任务2：方式二「检测不到」时的基准兜底
# ================================================================
# 有些同人游戏把 Scene_Map#update / Game_Player#passable? 改得跟官方
# 完全不一样（或干脆把 `if $DEBUG` 条件整段删了），于是方式二一个都
# 认不出来。这时按**游戏版本对应的官方基准**去「对应位置」补一行
# 「去掉 debug 条件」的代码 —— 位置靠基准里同一个函数 / 同一个锚点行
# 反查出来，保证插在语义相同的地方。
#
# 每一项 = (命中基准里那一行的正则, 去掉条件后的写法)
# ★ 这里的替换文案里**不能出现字面量 ` if $DEBUG`**，否则第二次跑
#   方式二时会被 _STRIP_PATS 自己再命中一次（非幂等）。
_FREE_PATS = (
    # v16 / v17：Game_Player / Scene_Map 的 `if $DEBUG and Input.press?(…)`
    (re.compile(r"^([ \t]*)if\s+\$DEBUG\s+(?:and|&&)\s+"
                r"(Input\.press\?\(Input::(?:CTRL|F9)\))[ \t]*$"),
     r"\1if \2"),
    # v18 起 Game_Player：`return true if $DEBUG and|&& Input.press?(Input::CTRL)`
    (re.compile(r"^([ \t]*)return\s+true\s+if\s+\$DEBUG\s*(?:&&|and)\s+"
                r"(Input\.press\?\(Input::CTRL\))[ \t]*$"),
     r"\1return true if \2"),
    # v18 起 Scene_Map：`$game_temp.debug_calling = true if $DEBUG`
    (re.compile(r"^([ \t]*)(\$game_temp\.debug_calling\s*=\s*true)"
                r"\s+if\s+\$DEBUG[ \t]*$"),
     r"\1\2"),
    # v16–v21 队伍 / 背包 / 仓库的 Debug 项
    (re.compile(r"^([ \t]*)(commands\[cmdDebug[^#\n]*?)"
                r"\s+if\s+\$DEBUG[ \t]*$"),
     r"\1\2"),
    # v20+ `"condition" => proc { … $DEBUG },` → 条件恒真（等于去掉条件）
    (re.compile(r'^([ \t]*)"condition"\s*=>\s*proc\s*\{([^{}\n]*)\$DEBUG'
                r'([^{}\n]*)\}[ \t]*,?[ \t]*$'),
     r'\1"condition" => proc {\2true\3},'),
)


def _baseline_free_line(line):
    """基准里某一行「需要 $DEBUG 才生效」→ 去掉条件后的写法（不适用 → None）。"""
    for pat, rep in _FREE_PATS:
        if pat.match(line):
            return pat.sub(rep, line)
    return None


def _baseline_free_items(b_lines):
    """
    基准脚本 → [{"start","end","free":[去掉条件后的行, ...]}, ...]

    ★ `if $DEBUG … end` 这种块**整块**一起搬（只搬 if 那一行会漏掉
      `end`，插进游戏里就是语法错误）。
    """
    import debug_tool as DT
    blocks = {b["start"]: b for b in DT._find_if_debug_blocks(b_lines)}
    out = []
    i = 0
    while i < len(b_lines):
        b = blocks.get(i)
        if b is not None:
            head = _baseline_free_line(b_lines[i])
            if head is not None:
                out.append({"start": i, "end": b["end"],
                            "free": [head] + b_lines[i + 1:b["end"] + 1]})
                i = b["end"] + 1
                continue
        free = _baseline_free_line(b_lines[i])
        if free is not None:
            out.append({"start": i, "end": i, "free": [free]})
        i += 1
    return out


def _enclosing_def(lines, idx):
    """idx 这一行所在（最内层）的 def 名（找不到 → ""）。"""
    for j in range(min(idx, len(lines) - 1), -1, -1):
        m = re.match(r"^[ \t]*def\s+(?:self\.)?([A-Za-z_][\w]*[?!]?)",
                     lines[j])
        if m:
            return m.group(1)
    return ""


def _func_range(lines, func):
    """按函数名找 [def 行, 收尾 end 行] 的行号（找不到 → None）。"""
    for i, ln in enumerate(lines):
        m = re.match(r"^([ \t]*)def\s+(?:self\.)?%s(?![A-Za-z0-9_])"
                     % re.escape(func), ln)
        if not m:
            continue
        base = len(m.group(1))
        j = i + 1
        while j < len(lines):
            s = lines[j]
            st = s.strip()
            if st == "" or st.startswith("#"):
                j += 1
                continue
            if re.match(r"^[ \t]*end[ \t]*\r?$", s) and \
                    len(s) - len(s.lstrip(" \t")) <= base:
                break
            j += 1
        if j >= len(lines):
            j = len(lines) - 1
        return i, j
    return None


# 这些「行」满篇都是，不能当定位锚点 / 重不重复的判据
_KEY_STOP = frozenset(("end", "}", ")", "]", "else", "begin", "ensure",
                       "rescue", "do", "then", "next", "case", "when"))


def _code_key(line):
    """
    比较两行「是不是同一句代码」用的归一化键（去行尾注释、去所有空白）。

    ★ 纯注释行 / 空行 / `end` `else` 这类满篇都是的行 → ""（既不能当锚点，
      也不能拿它判断「这句已经有了」）。
    """
    s = re.sub(r"#.*$", "", line or "")
    s = re.sub(r"\s+", "", s)
    return "" if s in _KEY_STOP else s


def _read_baseline_script(version, sname):
    """读官方基准里某个脚本的全文（没有 → ""）。"""
    p = engine_src.script_src_path(version, sname)
    if not p or not os.path.isfile(p):
        return ""
    try:
        with io.open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _reindent(lines, delta, eol):
    """把一组行整体挪 delta 个空格（delta>0 缩进、<0 反缩进），并补行尾。"""
    out = []
    for ln in lines:
        if delta > 0:
            out.append(" " * delta + ln + eol)
        elif delta < 0:
            k = min(-delta, len(ln) - len(ln.lstrip(" ")))
            out.append(ln[k:] + eol)
        else:
            out.append(ln + eol)
    return out


def _pick_anchor(b_lines, it, fb):
    """
    给基准里的这段代码挑**定位锚点**：同函数内、紧邻它的一段「有内容」的
    代码行（前一行优先，因为它更接近语义位置）。

    返回 (行号, 是否插在它后面)；挑不到 → (None, True)。
    """
    cands = []
    for k in range(it["start"] - 1, fb[0] - 1, -1):
        if _code_key(b_lines[k]):
            cands.append((k, True))
            break
    for k in range(it["end"] + 1, fb[1] + 1):
        if _code_key(b_lines[k]):
            cands.append((k, False))
            break
    if not cands:
        return None, True
    # 更长的那一行更「具体」，定位更准；一样长时优先前一行
    cands.sort(key=lambda t: (-len(_code_key(b_lines[t[0]])), not t[1]))
    return cands[0]


def _top_ok(free_lines):
    """这段代码能不能直接放函数体最前面（放上去不会语法错/语义错）。"""
    first = (free_lines[0] or "").lstrip()
    if first.startswith("if "):
        return True
    if len(free_lines) == 1 and (first.startswith("return")
                                 or first.startswith("$")):
        return True
    return False


def _strip_add_into(tgt_text, b_lines, tag):
    """
    把基准里那些「带 $DEBUG 条件」的代码，按**对应位置**补进游戏脚本。

    返回 (新文本, 补了几处, [说明, ...])。找不到落点的一律跳过（宁可不动）。
    """
    items = _baseline_free_items(b_lines)
    if not items:
        return tgt_text, 0, []
    lines = tgt_text.split("\n")
    added, notes = 0, []
    for it in reversed(items):
        func = _enclosing_def(b_lines, it["start"])
        # 「这句已经有了」只拿**首行**判断：多行块的块体（`return true`
        # 之类）在别的函数里很常见，拿它当判据会把该补的地方误判成"已有"。
        key = _code_key(it["free"][0])
        file_keys = {_code_key(x) for x in lines if _code_key(x)}
        if key and key in file_keys:
            continue                       # 游戏里已经有这句 → 本来就没条件
        # 游戏里还留着「原来那行（带条件）」的话，方式二本该处理掉它 ——
        # 这里不重复插，免得插出两条一样的语句。
        orig_key = _code_key(b_lines[it["start"]])
        if orig_key and orig_key in file_keys:
            continue
        fb = _func_range(b_lines, func) if func else None
        ak, is_prev = _pick_anchor(b_lines, it, fb or (0, len(b_lines) - 1))
        # 先在同一函数里找落点；找不到再退到整份脚本（v20+ 的
        # `MenuHandlers.add(… "condition" => proc {…$DEBUG} …)` 就直接写在
        # 文件顶层，根本没有外层 def）。
        rng = _func_range(lines, func) if func else None
        scopes = ([rng] if rng else []) + [(0, len(lines) - 1)]
        at, pad = None, None
        for sc in scopes:
            if ak is None:
                break
            akey = _code_key(b_lines[ak])
            hits = [k for k in range(sc[0] + 1, sc[1] + 1)
                    if _code_key(lines[k]) == akey]
            if hits:
                at = (hits[-1] + 1) if is_prev else hits[0]
                pad = re.match(r"^([ \t]*)",
                               lines[hits[-1] if is_prev else hits[0]]).group(1)
                break
        if at is None:
            if not _top_ok(it["free"]) or not rng:
                notes.append("%s：游戏里找不到对应的插入位置，跳过"
                             % (f"{func}()" if func else "文件顶层"))
                continue
            at = rng[0] + 1
            pad = re.match(r"^([ \t]*)", lines[rng[0]]).group(1) + "  "
        base_ind = len(b_lines[it["start"]]) - len(
            b_lines[it["start"]].lstrip(" \t"))
        delta = len(pad) - base_ind
        eol = "\r" if "\r\n" in tgt_text else ""
        block = [f"{x}  # {_MARK} {tag}" for x in
                 _reindent(it["free"], delta, eol)]
        lines[at:at] = block
        added += 1
    return "\n".join(lines), added, notes


def add_debug_strip_from_baseline(game_dir, version, emit=None):
    """
    任务2 的兜底：方式二**一个 $DEBUG 条件都没认出来**时，按游戏版本对应的
    官方基准，在**对应位置**补一行「去掉 debug 条件」的代码。

    逐脚本（Scene_Map / Game_Player / PScreen_Party / UI_* …）来：
      ① 读官方基准里的同名脚本；
      ② 找出里面所有「需要 $DEBUG 才生效」的行（含 `if $DEBUG … end` 整块）；
      ③ 定位游戏里**同一个函数**里的**对应位置**（基准里紧跟其后那行代码
         作为锚点），把去掉条件的写法插进去；
      ④ 游戏里已经有这一句 → 跳过（不重复插）。
    ★ 幂等：再跑一次命中数为 0（插进去的行已经在了）。
    ★ 只补代码、不删代码，插的是语法完整的整行 / 整块。
    """
    def say(msg):
        if emit:
            emit(msg)
    out = {"ok": True, "version": version or "", "targets": [], "added": 0,
           "reason": ""}
    version = str(version or "").strip()
    if not version:
        out["ok"] = False
        out["reason"] = "读不到版本号，无法据基准定位"
        say("[方式二·兜底] ✘ 读不到版本号，没法按基准找对应位置")
        return out
    tag = "按基准补行：免 $DEBUG 条件"
    for sname in _KEYS_SCRIPTS:
        btxt = _read_baseline_script(version, sname)
        if not btxt:
            continue
        tgt = find_game_script(game_dir, sname)
        if not tgt:
            continue
        new_text, n, notes = _strip_add_into(tgt["text"], btxt.split("\n"),
                                             tag)
        for x in notes:
            say(f"[方式二·兜底] · {sname} — {x}")
        if not n:
            continue
        try:
            _write_script(tgt, new_text, emit=emit)
        except (OSError, RuntimeError) as e:
            out["ok"] = False
            out["reason"] = f"写「{sname}」失败：{e}"
            say(f"[方式二·兜底] ✘ {out['reason']}")
            return out
        out["targets"].append({"script": sname, "where": str(tgt["key"]),
                               "added": n})
        out["added"] += n
        say(f"[方式二·兜底] ✔ 已按官方 v{version} 基准，在「{sname}」的对应"
            f"位置补了 {n} 处「免 $DEBUG 条件」的代码")
    if not out["added"]:
        say("[方式二·兜底] · 官方基准里有条件的地方，游戏里要么已经有了、"
            "要么找不到对应函数 —— 没有需要补的")
    return out


# ---- 方式三 / 方式四：F6 键 ----
# 两个方式都往 Scene_Map#update 里塞一个 F6 分支，只是按下后干的事不同：
#   方式三 special       → $DEBUG = true + 提示（直接开，不判断 !$DEBUG）
#   方式四 special_menu  → $DEBUG = true 后**直接打开调试菜单**（方式⑥ 的 F6 版）
_F6_SIMPLE = (
    '$DEBUG = true',
    'pbMessage("调试模式已开启！")',
)
_F6_MENU = (
    '$DEBUG = true',
    '$game_temp.debug_calling = false',
    '$game_player.straighten',
    'pbPlayDecisionSE',
    'pbFadeOutIn { pbDebugMenu }',
    'pbMessage("已打开调试菜单")',
)


def patch_special_key(game_dir, mode="special", emit=None):
    """
    方式三 / 方式四：在 **Scene_Map#update** 里照着 `Input::F9` 的样子加一个
    F6 分支。

      mode="special"（方式三）     按下 F6 → `$DEBUG = true` 并弹提示。
                                   ★ 用户要求：**不再判断 `!$DEBUG`**，
                                     按下去就直接开、直接提示。
      mode="special_menu"（方式四）按下 F6 → 设 `$DEBUG` 后**直接打开调试菜单**
                                   （`pbFadeOutIn { pbDebugMenu }`，
                                    即原方式⑤ 的 F6 版）。

    ★ 各版本 F9 的写法不同，这里按「找到什么就仿什么」来：
      v16 / v17   `if $DEBUG and Input.press?(Input::F9)`     → 加一个独立 if 块
      v18 起      `elsif Input.press?(Input::F9)`            → 在它前面加一个 elsif 分支
      两种都认不准时，退到 `unless $game_player.moving?` 那一行前面插独立 if 块。

    ★ 幂等 + 可切换：**先抠掉本工具此前注入的所有 F6 块**（两种方式各算一块），
      再按当前方式插一份新的。以前是「另一种方式注过就只警告一句、照样往下插」，
      结果是同一处并排出现两个条件完全相同的 `elsif Input.press?(Input::F6)`，
      第二个永远不可达（实测：先方式三再方式四 → 双 F6 分支，方式四变死代码）。
    """
    def say(msg):
        if emit:
            emit(msg)
    menu = (mode == "special_menu")
    tag = "方式四：F6 键打开调试菜单" if menu else "方式三：F6 键开启调试模式"
    head = "[方式四]" if menu else "[方式三]"
    tgt = find_game_script(game_dir, "Scene_Map")
    if not tgt:
        say(f"{head} · 游戏里没找到「Scene_Map」脚本")
        return {"ok": False, "reason": "找不到 Scene_Map 脚本"}

    # ① 先清掉本工具以前注入的 F6 块（不管是方式三还是方式四、也不管
    #    是不是老版本那种包着 `if !$DEBUG` 的写法）→ 保证锚点处至多一个。
    lines, dropped = _f6_strip(tgt["text"].split("\n"))
    if dropped:
        say(f"{head} · 已先清除之前注入的 F6 分支（{dropped} 行）")

    # ② 再定位锚点（此时 F6 块已经不在了，不会自己撞自己）
    anchor = None
    for i, ln in enumerate(lines):
        if "Input::F9" not in ln:
            continue
        if re.match(r"^[ \t]*(elsif|if)\b", ln):
            anchor = i
            break
    is_elsif = bool(anchor is not None
                    and lines[anchor].lstrip().startswith("elsif"))
    if anchor is None:
        for i, ln in enumerate(lines):
            if re.match(r"^[ \t]*(unless\s+\$game_player\.moving\?|"
                        r"if\s+!\$game_player\.moving\?)", ln):
                anchor = i
                break
    if anchor is None:
        say(f"{head} · Scene_Map 里找不到 F9 分支 / moving? 判断，"
            "无法确定注入位置")
        return {"ok": False, "reason": "Scene_Map 里找不到注入锚点"}

    body = _f6_block(lines[anchor], menu, tag, is_elsif=is_elsif)
    new_text = "\n".join(lines[:anchor] + body + lines[anchor:])
    if new_text == tgt["text"]:
        # 已经是当前这一套（方式、位置、内容都对）→ 不写盘，hash 不变
        say(f"{head} · {tag}已经注入过了，跳过")
        return {"ok": True, "script": "Scene_Map", "added": False,
                "mode": mode, "changed": False}
    try:
        _write_script(tgt, new_text, emit=emit)
    except (OSError, RuntimeError) as e:
        say(f"{head} ✘ 写入失败：{e}")
        return {"ok": False, "reason": str(e)}
    what = "直接打开调试菜单" if menu else "直接开启 $DEBUG 并提示"
    say(f"{head} ✔ 已在 Scene_Map 注入 F6 键（{what}）"
        f"（{'elsif 分支' if is_elsif else '独立 if 块'}，在 F9 那段之前）")
    return {"ok": True, "script": "Scene_Map", "added": True, "mode": mode,
            "changed": True, "branch": "elsif" if is_elsif else "if",
            "replaced": bool(dropped)}


def _f6_strip(lines):
    """
    抠掉本工具注入的**所有** F6 块 → (新的行列表, 删掉了几行)。

    ★ 认块的方式：块首 = 同时含 `Input::F6` 和 `_MARK` 的行（`_f6_block`
      生成的两条路径都满足）；块体 = 紧跟着的、含 `_MARK` 且不含
      `_FOREIGN_MARKS` 里任何文案的连续行（`end  # [pkmn-debug]` 也算在内）。

    ★ 不用固定行数上限收尾 —— 方式四那种 `elsif` 块有 7 行、v16/v17 的
      独立 `if` 块有 8 行，写死上限会把尾巴（尤其是 `end`）留在原地，
      删完反而多出一个孤立的 `end`。
    """
    heads = [i for i, x in enumerate(lines)
             if "Input::F6" in x and _MARK in x]
    if not heads:
        return lines, 0
    drop = set()
    for h in heads:
        drop.add(h)
        j = h + 1
        while j < len(lines) and _MARK in lines[j] \
                and not any(m in lines[j] for m in _FOREIGN_MARKS):
            drop.add(j)
            j += 1
    return [x for i, x in enumerate(lines) if i not in drop], len(drop)


def _f6_block(ref_line, menu, tag, is_elsif):
    """
    照着 `ref_line` 的缩进 / 行尾，生成 F6 分支的代码行（已带行尾）。

    is_elsif=True → `elsif Input.press?(Input::F6) …`（插在 F9 的 elsif 前）
    is_elsif=False → 独立 `if … end` 块（v16/v17 那种写法）
    """
    indent = re.match(r"^([ \t]*)", ref_line).group(1)
    eol = "\r" if ref_line.endswith("\r") else ""
    pad = indent + "  "
    body_code = _F6_MENU if menu else _F6_SIMPLE
    body_body = [f"{pad}{x}  # {_MARK}" for x in body_code]
    if is_elsif:
        body = [f"{indent}elsif Input.press?(Input::F6)  # {_MARK} {tag}"] \
            + body_body
    else:
        body = ([f"{indent}if Input.press?(Input::F6)  # {_MARK} {tag}"]
                + body_body
                + [f"{indent}end  # {_MARK}"])
    return [b + eol for b in body]


# ---- 方式五 / 方式六：除虫喷雾 ----
def patch_repel(game_dir, mode="repel", version=None, emit=None):
    """
    方式五：pbRepel 开头写入 $DEBUG = true 并提示。
    方式六：pbRepel 开头直接打开调试菜单（= Scene_Map#call_debug 的等效写法，
            这里用 $game_temp.debug_calling = false + pbFadeOutIn { pbDebugMenu }）。

    ★ 脚本名 v16–v18 是 `PItem_ItemEffects`，v19+ 是 `Item_Effects` —— 两个都试。
    ★ 方式六要 `return` 一个「道具已用掉」的返回值，各版本不同：
        v19 / v19.1  → 3
        v20 及以上   → true
    """
    def say(msg):
        if emit:
            emit(msg)
    tgt = find_repel_script(game_dir)
    if not tgt:
        # ★ 松散脚本里没有 pbRepel 时，仍可能**只在容器里**有 → 试一下容器，
        #   别把这种游戏直接判成「找不到道具效果脚本」。
        plug = _inject_repel_into_plugins(game_dir, mode, version=version,
                                          say=say)
        if plug.get("written"):
            return {"ok": True, "script": plug.get("names", ["(插件容器)"]),
                    "mode": mode, "where": "plugin", "plugins": plug}
        say("[除虫喷雾] · 游戏里没找到带 pbRepel 的脚本"
            "（试过 Item_Effects / PItem_ItemEffects / PokemonItemEffects，"
            "以及插件容器）")
        return {"ok": False, "reason": "找不到道具效果脚本"}
    m = re.search(r"^([ \t]*)def\s+pbRepel\b.*$", tgt["text"], re.M)
    if not m:
        say("[除虫喷雾] · 道具效果脚本里没有 pbRepel（版本不符？）")
        return {"ok": False, "reason": "没找到 pbRepel 函数"}
    ok_val = _repel_ok_value(tgt["text"], version)
    new_text, dropped = _repel_inject(tgt["text"], mode, ok_val)
    changed = (new_text != tgt["text"])
    if changed:
        if dropped:
            say(f"[除虫喷雾] · 已抠掉 {dropped} 行上次注入的内容"
                f"（{'方式五' if mode == 'repel' else '方式六'}）")
        try:
            _write_script(tgt, new_text, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[除虫喷雾] ✘ 写入失败：{e}")
            return {"ok": False, "reason": str(e)}
        say(f"[除虫喷雾] ✔ 已在「{tgt['name']}」的 pbRepel 注入"
            f"（{'方式五' if mode == 'repel' else '方式六'}）")
    else:
        say(f"[除虫喷雾] · 「{tgt['name']}」的 pbRepel 已经是"
            f"（{'方式五' if mode == 'repel' else '方式六'}），无需改动")
    # ★ 只改松散脚本**不够**：加载顺序是「松散 Scripts/ 全部加载完 →
    #   再 eval Data/PluginScripts.rxdata」，容器里后定义的 `def pbRepel`
    #   会把上面这份整体覆盖掉（实测本作容器内的
    #   `[Soulstones 2 Specific Changes] Item_Effects.rb` 正是如此），
    #   于是方式五/六 的注入完全无效。同一份注入必须同时写进容器。
    plug = _inject_repel_into_plugins(game_dir, mode, say=say)
    return {"ok": True, "script": tgt["name"], "mode": mode,
            "changed": changed, "plugins": plug}


def _repel_body(mode, ok_val):
    """方式五 / 方式六 注入的块体（相对 def 行缩进 2 空格的写法）。"""
    if mode == "repel":
        return [
            f'if !$DEBUG  # {_MARK} 方式五：除虫喷雾开启调试模式',
            f'  $DEBUG = true  # {_MARK}',
            f'  pbMessage("调试模式已开启！")  # {_MARK}',
            f'end  # {_MARK}',
        ]
    return [
        f'if !$DEBUG  # {_MARK} 方式六：除虫喷雾直接开调试菜单',
        f'  $DEBUG = true  # {_MARK}',
        f'  $game_temp.debug_calling = false  # {_MARK}',
        f'  $game_player.straighten  # {_MARK}',
        f'  pbPlayDecisionSE  # {_MARK}',
        f'  pbFadeOutIn {{ pbDebugMenu }}  # {_MARK}',
        f'  pbMessage("已打开调试菜单")  # {_MARK}',
        f'  return {ok_val}  # {_MARK}',
        f'end  # {_MARK}',
    ]


def _repel_inject(text, mode, ok_val):
    """
    把方式五/六 的注入写到 `text` 里 `def pbRepel` 的**第一行之后**
    → (新文本, 抠掉了几行)。

    ★ 幂等：先抠掉本工具**之前**注入的整块（方式五 / 方式六都带 _MARK）。
      以前这里没有任何检查 → 重复点「开启 DEBUG」会一份份往下堆
      （实测 1→2→3），而且「先跑方式五再跑方式六」时方式五那块把
      `$DEBUG` 设成 true，方式六的 `if !$DEBUG` 就永远进不去。
    ★ 认不出 pbRepel / 没有变化 → 返回值与原文本相等，由调用方判断。
    """
    m = re.search(r"^([ \t]*)def\s+pbRepel\b.*$", text, re.M)
    if not m:
        return text, 0
    pad = m.group(1) + "  "
    lines = text.split("\n")
    i = text.count("\n", 0, m.start())
    eol = "\r" if lines[i].endswith("\r") else ""
    old_rows = []
    j = i + 1
    while j < len(lines) and _MARK in lines[j]:
        old_rows.append(j)
        j += 1
    if old_rows:
        del lines[old_rows[0]:old_rows[-1] + 1]
    # ↑ lines / i / eol 已在「剥离旧注入」时算好（删的是 i 之后的行，i 不变）
    new = (lines[:i + 1] + [pad + x + eol for x in _repel_body(mode, ok_val)]
           + lines[i + 1:])
    return "\n".join(new), len(old_rows)


def _inject_repel_into_plugins(game_dir, mode, ok_val=None, version=None,
                               say=None):
    """
    把**同一份** pbRepel 注入写进插件容器 `Data/PluginScripts.rxdata` 里
    每一条同名 `def pbRepel`（见 patch_repel 里的加载顺序说明）。

    · 没有容器 / 容器里没有同名定义 / 任何读写失败 → 只 `say("[除虫喷雾] ⚠ …")`，
      **绝不中止**整个方式（v16–v18 没有插件机制，行为与改动前一致）。
    · 容器写入**先备份**（`.pkmn-overwrite-<时间戳>.bak`，与 `_write_script`
      同一套 → 「还原覆盖」`_list_backups` / `restore_overwrite` 能认出来），
      再由 `GS.write_plugin_entry` 原子落盘（写 `.tmp` 后 os.replace）。
    · ok_val 缺省时按容器条目自己的 body 嗅探（容器与松散脚本的返回值写法
      可能不同，所以两条路径各自判一次）。
    · 返回 {"ok", "written", "skipped", "names", "reason"}。
    """
    def warn(msg):
        if say:
            say(msg)
    out = {"ok": False, "written": 0, "skipped": 0, "names": [],
           "reason": ""}
    path = GS.plugin_rxdata_path(game_dir)
    if not os.path.isfile(path):
        out["reason"] = "missing"
        return out
    try:
        entries = GS.read_plugin_entries(path)
    except Exception as e:                              # noqa: BLE001
        warn(f"[除虫喷雾] ⚠ 读 {os.path.basename(path)} 失败，跳过容器注入：{e}")
        out["reason"] = "read_error"
        return out
    hits = [(pi, fi, nm, tx) for pi, fi, nm, tx in entries
            if re.search(r"^[ \t]*def\s+pbRepel\b", tx, re.M)]
    if not hits:
        out["reason"] = "no_entry"
        return out
    if ok_val is None:
        ok_val = _repel_ok_value(hits[0][3], version)
    backed = False
    for pi, fi, nm, tx in hits:
        new_text, dropped = _repel_inject(tx, mode, ok_val)
        if new_text == tx:
            out["skipped"] += 1
            warn(f"[除虫喷雾] · 容器「{nm}」的 pbRepel 已经是"
                 f"（{'方式五' if mode == 'repel' else '方式六'}），无需改动")
            continue
        try:
            if not backed:
                # 整个 rxdata 做一次备份就够（一次运行里可能改多条）
                _backup(path, emit=say)
                backed = True
            GS.write_plugin_entry(path, (pi, fi), new_text, expect=tx)
        except Exception as e:                          # noqa: BLE001
            warn(f"[除虫喷雾] ⚠ 写入容器「{nm}」失败，已跳过：{e}")
            continue
        out["written"] += 1
        out["names"].append(nm)
        if dropped:
            warn(f"[除虫喷雾] · 容器「{nm}」已抠掉 {dropped} 行上次注入的内容")
        warn(f"[除虫喷雾] ✔ 已在插件容器「{nm}」的 pbRepel 注入"
             f"（{'方式五' if mode == 'repel' else '方式六'}）")
    out["ok"] = bool(out["written"] or out["skipped"])
    if not out["written"] and not out["skipped"]:
        out["reason"] = "write_error"
    return out


def _repel_ok_value(text, version=None):
    """
    判断某个 pbRepel 的「使用成功」返回值：v19/v19.1 是 3，v20+ 是 true。

    先按 version 判（主版本 >= 20 → true），缺 version 就从原文里嗅探。
    """
    if version:
        try:
            maj = int(str(version).split(".")[0])
            return "true" if maj >= 20 else "3"
        except ValueError:
            pass
    body = text[text.find("def pbRepel"):]
    body = body[:body.find("\nend")]
    if re.search(r"return\s+true\b", body):
        return "true"
    return "3"


def detect_runtime(game_dir, exe=None):
    """判断游戏运行库：'rgss' / 'mkxp' / 'unknown'。exe 可指定启动程序。"""
    import launcher
    return launcher.detect_runtime(game_dir, exe=exe)


def find_exe(game_dir):
    """找游戏主 exe（用户没手选时的兜底）。返回完整路径或 None。"""
    import launcher
    return launcher._find_exe(game_dir)


def make_debug_launcher(game_dir, version=None, emit=None, exe=None):
    """
    方式七：在游戏目录生成调试启动器。
    返回 {"ok", "runtime", "files", "main", "reason"}。
    """
    import launcher
    return launcher.make_debug_launcher(
        game_dir, version=version, emit=emit, exe=exe)


# 把 launcher 的标签同步到模块级（GUI 会读 ET.RUNTIME_LABEL）
try:
    import launcher as _launcher
    RUNTIME_LABEL = _launcher.RUNTIME_LABEL
except Exception:
    pass


# ---- 通用：往某个 elsif 分支里插代码 ----
def _inject_into_branch(game_dir, sname, branch_re, body, emit=None):
    def say(msg):
        if emit:
            emit(msg)
    tgt = find_game_script(game_dir, sname)
    if not tgt:
        say(f"[方式三] · 游戏里没找到「{sname}」脚本")
        return {"ok": False, "reason": f"找不到 {sname}"}
    m = re.search(branch_re, tgt["text"], re.M)
    if not m:
        say(f"[方式三] · 「{sname}」里没有匹配的分支（版本不符？）")
        return {"ok": False, "reason": "没匹配到 SPECIAL 分支"}
    indent = m.group(1)
    pad = indent + "  "
    lines = tgt["text"].split("\n")
    i = tgt["text"].count("\n", 0, m.start())
    eol = "\r" if lines[i].endswith("\r") else ""
    new = (lines[:i + 1] + [pad + x + eol for x in body] + lines[i + 1:])
    try:
        _write_script(tgt, "\n".join(new), emit=emit)
    except (OSError, RuntimeError) as e:
        say(f"[方式三] ✘ 写入失败：{e}")
        return {"ok": False, "reason": str(e)}
    say("[方式三] ✔ 已在 SPECIAL 分支注入开启调试模式的代码")
    return {"ok": True, "script": sname}


# ================================================================
# 方式七：改名调试函数（规避反调试脚本）
# ================================================================
# 反调试脚本（典型如汉化插件的 000_Config.rb）大致干了这些事：
#
#     def pbDebugMenu(show_all = true)      ← 把调试入口改成直接退出
#       exit
#     end
#
#     class Scene_Map
#       alias del_update update
#       def update
#         exit if $DEBUG                    ← 一设 $DEBUG 就退游戏
#         del_update
#       end
#     end
#
#     module Input                          ← 屏蔽 F4–F12 全部按键
#       class << self
#         def press?(key) … return false if [F9,F5,F6,F7,F8].include?(key) …
#       end
#     end
#
#     MenuHandlers.add 也被改过：凡是 option/menu 名里含 "debug" 的注册一律丢弃。
#
# ★ 本方式的核心思路（用户指定）：
#     ① **不设 `$DEBUG = true`** —— 反调试会 `exit if $DEBUG`，一设就退游戏；
#     ② **改的是官方基准函数**：从工具内置的官方引擎源码（scripts/essentials_src/
#        <ver>/）取 debug 相关函数，把函数名里含 "debug" 的全部换成中性名，
#        然后**用改名后的基准函数覆盖游戏里的原函数定义**；
#     ③ **所有调用点同步改名** —— 游戏脚本里 `pbDebugMenu` / `pbPokemonDebug` 等
#        的每一个调用都改成新名（`def` 定义点一并改名 + 换体）；
#     ④ **T 键正式注册** —— 不是只在 Scene_Map 里判一下，而是照各版本原生的
#        「按键注册方式」正式注册：v16/17/18 改 `PSystem_Controls.rb` 的
#        `module Input`（加常量 + `buttonToKey` 映射到 Win32 键码 0x54）；
#        v19+ 走 mkxp-z 引擎的 `Input.triggerex?(:T)`（SDL scancode 符号）。
#     ⑤ 新函数名一律**不含 debug 字样** → 反调试的字符串过滤抓不到。
#
# 改名映射（旧名 → 新名，均不含 "debug" 字样）
# ------------------------------------------------------------
#   pbDebugMenu            → pbAideWindow           （主菜单入口）
#   pbPokemonDebug         → pbAidePokemon          （宝可梦调试界面）
#   pbDebugMenuCommands    → pbAideWindowCommands   （v17/v18 命令表）
#   pbDebugMenuActions     → pbAideWindowActions    （v17/v18 动作表）
#   pbPokemonDebugCommands → pbAidePokemonCommands  （v17/v18 宝可梦命令表）
#   pbPokemonDebugActions  → pbAidePokemonActions   （v17/v18 宝可梦动作表）
#   call_debug             → call_aide              （Scene_Map 私有入口）
#
# v19+ 还会把菜单注册表的 key 一起改名（反调试按名字丢注册）：
#   :debug_menu            → :aide_menu
#   :pokemon_debug_menu    → :aide_pokemon_menu
#   MenuHandlers.add(:party_menu,  :debug, …) → :aide
#   MenuHandlers.add(:pause_menu,  :debug, …) → :aide

# ---- 新函数名（★ 绝不能含 "debug" 字样）----
XQK_MENU_FUNC = "pbAideWindow"
XQK_PKMN_FUNC = "pbAidePokemon"
XQK_MENU_CMD_FUNC = "pbAideWindowCommands"
XQK_MENU_ACT_FUNC = "pbAideWindowActions"
XQK_PKMN_CMD_FUNC = "pbAidePokemonCommands"
XQK_PKMN_ACT_FUNC = "pbAidePokemonActions"
XQK_CALL_FUNC = "call_aide"
XQK_TAG = "方式七：改名调试函数"
# 目录名排 ASCII 尾部（排序后 CJK 目录在其后）→ reverse 后「中文名的反调试插件
# 先加载、本插件后加载」。这样本插件对 Scene_Map / Input 的封装才在反调试之后生效。
XQK_PLUGIN_DIR = "zzz_pkmn_aide"
XQK_PLUGIN_FILE = "001_Aide.rb"
XQK_PLUGIN_NAME = "pkmn aide"        # 插件 meta 里的 Name
# 历史遗留的旧名字（上一轮「重写调试函数」方案写过的），重开方式⑦时清掉
XQK_OLD_PLUGIN_DIRS = ("zzz_pkmn_assist", "zzz_pkmn_xqk", "pkmn_assist")

# 旧名 → 新名（顺序即替换顺序；长名在前，避免 `pbXxx` 前缀互吃）
XQK_RENAMES = (
    ("pbPokemonDebugCommands", XQK_PKMN_CMD_FUNC),
    ("pbPokemonDebugActions", XQK_PKMN_ACT_FUNC),
    ("pbDebugMenuCommands", XQK_MENU_CMD_FUNC),
    ("pbDebugMenuActions", XQK_MENU_ACT_FUNC),
    ("pbPokemonDebug", XQK_PKMN_FUNC),
    ("pbDebugMenu", XQK_MENU_FUNC),
    ("call_debug", XQK_CALL_FUNC),
)

# v19+ 菜单注册表 key / 选项 key 改名（`MenuHandlers.add` 被反调试按名字过滤）
XQK_SYM_RENAMES = (
    (":pokemon_debug_menu", ":aide_pokemon_menu"),
    (":debug_menu", ":aide_menu"),
    # 单独出现的 `:debug`（party_menu / pause_menu 的选项 key）
    (":debug", ":aide"),
)

# ------------------------------------------------------------
# ★ 兼容层：保留「原函数名」的调用入口（v1.6.0）
# ------------------------------------------------------------
# 为什么需要：
#   方式七把 debug 函数**整套改名**（`pbDebugMenu` → `pbAideWindow` …），游戏脚本里
#   的旧名 def 被整段顶掉了。但**别的插件 / 脚本可能还在按旧名调用**
#   （`pbDebugMenu(show_all)`、`pbPokemonDebug(pkmn, id)` …），旧名一没就是
#   `NameError / NoMethodError` → 直接崩。
# ⇒ 在每个「改名后函数」的**同一作用域**补一个同名转发壳：
#       # >>> pkmn-aide compat begin >>>
#       def pbDebugMenu(*args, &blk)  # pkmn-aide compat
#         pbAideWindow(*args, &blk)
#       end
#       # <<< pkmn-aide compat end <<<
#   壳插在 `def <新名> … end` 紧后面 → 缩进与 `self.` 形态都跟着新函数走，
#   作用域与原定义完全一致（顶层 / `module PokemonDebugMixin` / 某个类里），
#   所以 `PokemonDebugMixin.instance_method(:pbPokemonDebug)` 这类反射访问也能用。
# ★ 壳**不参与改名** —— 行尾带 XQK_COMPAT_MARK，`_rewrite_calls` 见到就跳过
#   （否则 `call_debug` 会被改成 `def call_aide; call_aide; end` → 无限递归）。
# ★ `*args, &blk` 是**刻意**的：RGSS1（v16–v18）跑的是 Ruby 1.8，
#   用不了 `**kw`；这样写 9 个版本语法都合法。
XQK_COMPAT_BEGIN = "# >>> pkmn-aide compat begin >>>"
XQK_COMPAT_END = "# <<< pkmn-aide compat end <<<"
XQK_COMPAT_MARK = "# pkmn-aide compat"

# 可能承载「按键注册」的脚本名（按归一化名字匹配，认到什么改什么）
#   v16/17/18：PSystem_Controls
#   v19+：001_Technical/004_Input
XQK_INPUT_SCRIPTS = ("PSystem_Controls", "Input")

# ★★ `pbDebugMenu` 这个名字在官方基准里有**两处定义**：
#   ① `Debug_Menus.rb`（v19+）/ `Debug_Menu.rb`（v17/18）**顶层** —— 调试菜单入口
#      （函数体是 `commands = CommandMenuList.new…`，我们改的正是它）；
#   ② `Battle_CommandPhase.rb`（v19+）/ `Battle_Phase_Command.rb`（v18）的
#      `Battle::CommandPhase` **类内** —— 战斗指令菜单那一侧的调试入口
#      （函数体只有 `pbBattleDebug(self)`）。
#   替换是**只按函数名**做的（`_func_range_in` 认不出这个区别）→ 以前会把 ②
#   也换成 ①：战斗调试菜单整个报废、`pbBattleDebug` 变成死代码。
#   ⇒ 下面按「脚本名排除 + 顶格 def」双重判定把 ② 摘出去。
XQK_BATTLE_SCRIPTS = (
    "Battle_Phase_Command", "Battle_CommandPhase", "Battle_ActionRunning",
    "Scene_ChooseCommands",
)


def _xqk_def_toplevel(text, func):
    """文本里有没有**顶格**（无缩进）的 `def <func>` —— 用来区分同名不同义的 def。"""
    return bool(re.search(r"(?m)^def[ \t]+(?:self\.)?" + re.escape(func)
                          + r"(?![0-9A-Za-z_!?=])", text))


def _xqk_is_battle_script(short_name):
    """是不是「战斗指令菜单」脚本（里面的 `pbDebugMenu` 是战斗调试，不能碰）。"""
    return any(_xqk_name_is(short_name, s) for s in XQK_BATTLE_SCRIPTS)


# 调用点可能出现在这些脚本里（扫描时按「名字归一化」匹配，找不到就跳过）
# ★ v16–v18 是扁平命名（PScreen_*、Debug_*）；v19+ 是 UI_*、Debug_*。
XQK_CALL_SITES = (
    # scene / 全局入口
    "Scene_Map", "Scene_DebugIntro", "call_debug", "call_aide",
    # v16–v18
    "PScreen_PauseMenu", "PScreen_Party", "PScreen_Load",
    "PScreen_PokemonStorage", "PScreen_Bag",
    "Debug", "Debug_Menu", "Debug_Menus", "Debug_MenuCommands",
    "Debug_MenuExtraCode", "Debug_Pokemon", "Debug_PokemonCommands",
    "Debug_Actions", "Debug_BattleCommands", "Debug_BattlePkmnCommands",
    "Debug_BattleExtraCode", "Debug_FilenameUpdater",
    # v19+
    "UI_PauseMenu", "UI_Party", "UI_Load", "UI_PokemonStorage", "UI_Bag",
    # 战斗指令菜单
    "Battle_Phase_Command", "Battle_CommandPhase", "Scene_ChooseCommands",
    "Scene_Commands", "Battle_ActionRunning",
    # 本作实际存在的其他调用点
    "PokedexQuickAccess", "TradeFromPC", "Bag with interactuable party",
)

# 「UI 里显示 Debug 的选项名」→ 统一改成中性文案（防选项名过滤 + 顺手汉化）
# ★ 只改**字符串字面量**，不动变量名（`cmdDebug` / `cmd_debug` 保持原样）。
XQK_LABEL_OLD = '"Debug"'
XQK_LABEL_NEW = '"助手"'

# T 键的 Win32 虚拟键码（v16/17/18 的 `buttonToKey` 用）
XQK_T_VKEY = "0x54"                  # T 键
# T 常量在 `module Input` 里占用的编号（挑一个 9 个版本都没用过的值）
XQK_T_BTN = 24


def _xqk_script_match(short_name):
    """脚本名是否属于「方式七要扫的调用点脚本」。

    ★ 用**后缀匹配**：游戏脚本名可能是 `Scene_Map`、`970842_Scene_Map`、
      `003_Game processing__002_Scene_Map` 等形态，取归一化后「去掉前导数字/
      路径片段」的尾部对比。
    """
    norm = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(short_name).lower())
    for s in XQK_CALL_SITES:
        tgt = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s.lower())
        if not tgt:
            continue
        if norm == tgt or norm.endswith(tgt):
            return True
    return False


def _xqk_name_is(short_name, target):
    """脚本名是否「就是」target（后缀匹配，容忍前导编号/路径片段）。"""
    x = re.sub(r"^.*[/\\]", "", str(short_name))
    norm = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", x.lower())
    norm = re.sub(r"^\d+", "", norm)
    tgt = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(target).lower())
    return bool(tgt) and (norm == tgt or norm.endswith(tgt))


def _xqk_input_script(short_name):
    """脚本名是否是某版本的「按键注册脚本」（PSystem_Controls / Input）。

    ★ 后缀匹配：`004_Input` / `001_Technical__004_Input` / `Input` 都算。
    """
    for s in XQK_INPUT_SCRIPTS:
        if _xqk_name_is(short_name, s):
            return True
    return False


# ==================================================================
# ① 用「改名后的官方基准函数」覆盖游戏里的原函数
# ==================================================================
# 做法：从官方基准脚本里把某个 `def <old>(...)` … 对应的 `end` 整段抠出来，
#      把函数名换成新名（以及函数体里对兄弟函数的调用），再拿去替换游戏里
#      同名函数的整段。
# ★ 只替换**函数级**（`def … end`），脚本其余部分逐字保留。
_QXK_DEF_RE_CACHE = {}

# Ruby 字符串字面量（双引号 / 单引号，含转义）
_XQK_STR_RE = re.compile(r'"(?:[^"\\]|\\.)*"' + r"|'(?:[^'\\]|\\.)*'")


def _xqk_blind_strings(code):
    """把字符串字面量**内容涂掉**（只留等长的引号），再去做块配对。

    ★★ 踩过：`end_re` 认的是「独立成词的 end」，可汉化文案里出现它太常见了 ——
      `pbMessage("Safari Zone end")`、`_INTL("press end")`、`"结束 end"`…，
      那条字符串会让深度提前归零 → `def` 的区间被**截短** →
      `_xqk_replace_func` 只替换前半段、原地留下孤儿 `end` →
      游戏脚本语法错误、启动即崩。实测构造用例会返回 `(0, 1)`（应为 `(0, 6)`）。
    """
    return _XQK_STR_RE.sub(lambda m: m.group(0)[0] * len(m.group(0)), code)


def _func_range_in(text, func):
    """
    找 `def <func>` 到对应 `end` 的区间 → (start, end)（end 是 end 行的行首下标）。
    找不到 → None。用**行首**锚 `^\\s*def\\b` 避免误配 `cmdDebug` 之类。

    ★ 缩进感知：`def` 可能在 class/module 里（前面有空格），块配对按
      「def / do / if / case / begin … end」计数，`end` 数归零即结束。
    """
    lines = text.split("\n")
    # 先找 def 行：`def pbXxx` / `def pbXxx(...)` / `def pbXxx` / `def self.pbXxx`
    #   ★ 允许后面跟参数表（可能跨行，但本引擎都写在一行里）
    start = None
    for i, ln in enumerate(lines):
        m = re.match(r"^([ \t]*)def[ \t]+(?:self\.)?" + re.escape(func)
                     + r"(?![0-9A-Za-z_!?=])", ln)
        if m:
            start = i
            break
    if start is None:
        return None

    depth = 1
    # 逐行配对：`def` 行本身算 1 层。之后按 Ruby 关键字计数。
    #   ★ 只把「**语句开头**的 if/unless/while/until/case/begin/do/for/class/
    #     module/def」算作开块 —— 行中间的 `x if y`（修饰语）、`foo { |x| }`
    #     里的 do 都不开块，否则 end 永远配不平。
    open_re = re.compile(r"(?m)^[ \t]*(?:if|unless|while|until|case|begin|for|"
                         r"class|module|def)\b")
    inline_open_re = re.compile(r"(?<![A-Za-z0-9_])do(?![A-Za-z0-9_])\s*(?:\|[^|]*\|)?\s*$")
    end_re = re.compile(r"(?<![A-Za-z0-9_.])end(?![A-Za-z0-9_])")
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        code = re.sub(r"#.*$", "", ln) if "#" in ln else ln
        # ★ 先把字符串内容涂掉：文案里的独立 `end`（"press end" 之类）不算块结束
        code = _xqk_blind_strings(code)
        if not code.strip():
            continue
        # 该行开块数
        n_open = len(open_re.findall(code))
        # 行尾 do（`... do`），但排除 `{ ... }` 形式（那种没有 do）
        if inline_open_re.search(code):
            n_open += 1
        n_end = len(end_re.findall(code))
        depth += n_open
        depth -= n_end
        if depth <= 0:
            return (start, i)
    return None


def _extract_func(text, func):
    """把 `def <func> … end` 整段抠出来（含 def 行与 end 行）。找不到 → ""。"""
    rng = _func_range_in(text, func)
    if not rng:
        return ""
    lines = text.split("\n")
    return "\n".join(lines[rng[0]:rng[1] + 1])


def _xqk_sym_re(sym):
    """「符号改名」用的正则 —— ★★ **必须带词边界**。

    ★★ 踩过（真机 `NoMethodError: undefined method 'debug_calling' for
      #<Game_Temp>`）：原来是朴素的 `text.replace(":debug", ":aide")`，
      `:debug_calling` 这种**只是以 `:debug` 开头**的符号也会被一起改掉 ——
      `attr_accessor :debug_calling`（定义）变成 `:aide_calling`，而
      `$game_temp.debug_calling`（调用点，**没有冒号**）不受影响 →
      跑图时 `Scene_Map#update` 读到 `$game_temp.debug_calling` 就炸。
      连**官方基准**里都有 9 处 `:debug_calling`（Game_Temp + Scene_Map），
      所以这个坑对任何游戏都会踩。
    ⇒ 前后都不许接标识符字符：`[A-Za-z0-9_]`。
    """
    return re.compile(r"(?<![0-9A-Za-z_])" + re.escape(sym) + r"(?![0-9A-Za-z_])")


# 我们**有意**改成的新符号（修复历史误改时要排除这几条）
_XQK_SYM_NEW = tuple(new for _old, new in XQK_SYM_RENAMES)


def _rename_in_func_body(body):
    """把函数体里出现的旧函数名/旧注册 key 全换成新名。"""
    out = body
    for old, new in XQK_RENAMES:
        out = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?![A-Za-z0-9_])",
                     new, out)
    for old, new in XQK_SYM_RENAMES:
        out = _xqk_sym_re(old).sub(new, out)
    return out


def _baseline_func_renamed(version, script, func):
    """
    从官方基准取 `func` 的函数体，改名后返回。
    script=None → 在所有基准脚本里找第一个定义了 func 的。
    """
    cands = []
    if script:
        p = engine_src.script_src_path(version, script)
        if p:
            cands.append(p)
    else:
        cands = engine_src.engine_files(version)
    for p in cands:
        try:
            with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                text = _norm_eol(f.read())
        except OSError:
            continue
        src = _extract_func(text, func)
        if src:
            return _rename_in_func_body(src)
    return ""


# 每个版本的入口函数：func 旧名 → 承载它的基准脚本名（None=全库搜）
# ★ 各版本实际函数清单见调研结论：
#   v16    : pbDebugMenu(Debug.rb) / pbPokemonDebug(PScreen_Party.rb)
#   v17    : pbDebugMenuCommands+Actions(Debug_Menu.rb) / pbDebugMenu(Debug_Menu.rb)
#            pbPokemonDebugCommands+Actions+pbPokemonDebug(Debug_Pokemon.rb)
#   v18    : 同 v17（Debug_Menu.rb / Debug_Pokemon.rb）
#   v19+   : pbDebugMenu + pbPokemonDebug(Debug_Menus.rb)
def _xqk_entry_funcs(version):
    """
    返回 [(旧名, 基准脚本名 or None), ...]：该版本要用基准改名覆盖的函数。
    """
    v = engine_src.norm_ver(version)
    if v == "16":
        return [
            ("pbDebugMenu", "Debug"),
            ("pbPokemonDebug", "PScreen_Party"),
        ]
    if v in ("17", "18"):
        return [
            ("pbDebugMenuCommands", "Debug_Menu"),
            ("pbDebugMenuActions", "Debug_Menu"),
            ("pbDebugMenu", "Debug_Menu"),
            ("pbPokemonDebugCommands", "Debug_Pokemon"),
            ("pbPokemonDebugActions", "Debug_Pokemon"),
            ("pbPokemonDebug", "Debug_Pokemon"),
        ]
    # 19 / 19.1 / 20 / 20.1 / 21 / 21.1
    return [
        ("pbDebugMenu", "Debug_Menus"),
        ("pbPokemonDebug", "Debug_Menus"),
    ]


def _xqk_strip_defs(text, func):
    """把文本里**所有** `def <func> … end` 整段抠掉。返回 (新文本, 抠掉几段)。"""
    n = 0
    while True:
        rng = _func_range_in(text, func)
        if not rng:
            break
        lines = text.split("\n")
        # 连同紧随其后的空行一起去掉，避免留一堆空行
        hi = rng[1] + 1
        while hi < len(lines) and not lines[hi].strip():
            hi += 1
        del lines[rng[0]:hi]
        text = "\n".join(lines)
        n += 1
        if n > 50:                      # 保险丝
            break
    return text, n


def _xqk_replace_func(text, old_func, new_src):
    """
    把文本里 `def <old_func> … end` 整段替换成 `new_src`。返回 (新文本, 换了几段)。
    `new_src` 已含改好名的新 `def`。
    """
    n = 0
    while True:
        rng = _func_range_in(text, old_func)
        if not rng:
            break
        lines = text.split("\n")
        new_lines = new_src.split("\n")
        lines[rng[0]:rng[1] + 1] = new_lines
        text = "\n".join(lines)
        n += 1
        if n > 50:
            break
    return text, n


def replace_aide_functions(game_dir, version=None, emit=None):
    """
    用「改名后的官方基准函数」覆盖游戏里 debug 相关函数的定义。

    步骤（每个函数）：
      · 从基准取原函数体 → 改名（函数名 + 体内调用 + 注册 key）；
      · 把游戏脚本里同名 `def … end` 段整段替换成改名版；
      · 若游戏里**没有**这个函数（比如反调试干脆删了），则在第一个
        扫到的调用点脚本末尾追加一份（保证新名一定有定义）。

    返回 {"replaced": n, "added": n, "scripts": {名: 次数}}。
    """
    def say(msg):
        if emit:
            emit(msg)

    v = engine_src.norm_ver(version)
    entries = _xqk_entry_funcs(v)
    out = {"replaced": 0, "added": 0, "scripts": {}}
    seen = set()                        # 已经处理过 (旧名) 组合

    # 先备好所有「新函数源码」（旧名 → 新源码）
    new_srcs = {}
    for old, script in entries:
        src = _baseline_func_renamed(v, script, old)
        if not src:
            say(f"[方式七] ⚠ 基准里找不到 {old}（{script}），跳过")
            continue
        new_srcs[old] = src

    # 扫描一遍现有脚本：既统计「已定义新名」也算出「旧名定义」的脚本
    all_scripts = list(GS.iter_named_scripts(game_dir, both=True))
    # 1) 这一轮先抠掉上次注入的块（+ 兼容壳），避免「已定义」判据被自己的注入干扰
    #    ★ 兼容壳必须在「替换 def 段」之前抠：它的 def 行就是旧函数名，
    #      留着会被 _xqk_replace_func 当成原函数再顶一次。
    cleaned = []
    for mode, key, path, name, text in all_scripts:
        nt, k = _xqk_strip_inject(text)
        nt, k2 = _xqk_strip_compat(nt)
        if k or k2:
            cleaned.append((mode, key, path, name, nt, text))
        else:
            cleaned.append((mode, key, path, name, text, None))
    # 2) 记录哪些新名已经在游戏里定义
    already = set()
    for _m, _k, _p, _n, text, _o in cleaned:
        for old, src in new_srcs.items():
            newname = re.sub(r"^\s*def\s+", "", src.split("\n")[0])
            newname = re.split(r"[\(\s]", newname.strip())[0]
            if newname and _func_range_in(text, newname):
                already.add(old)

    # 逐脚本替换
    for mode, key, path, name, text, orig in cleaned:
        short = re.sub(r"^.*/", "", str(name))
        # ★★ 战斗指令菜单脚本要**整个跳过**：里面的 `def pbDebugMenu`（类内）
        #   是战斗调试入口，和我们要改的调试菜单只是**同名**。
        if _xqk_is_battle_script(short):
            if _func_range_in(text, "pbDebugMenu"):
                say(f"[方式七] · 「{short}」里的同名函数是战斗调试入口，跳过")
            continue
        new_text = text
        local = 0
        for old, src in new_srcs.items():
            # ★ 兜底：脚本名对不上战斗脚本名单时，靠「顶格 def」再挡一次 ——
            #   调试菜单入口在官方基准里永远是顶层 def，战斗那侧是类内方法。
            if old == "pbDebugMenu" and not _xqk_def_toplevel(new_text, old):
                continue
            nt, k = _xqk_replace_func(new_text, old, src)
            if k:
                new_text = nt
                local += k
                seen.add(old)
        # 若这次没换、但新名早就定义在别处 → 也算「已覆盖」
        for old in new_srcs:
            if old in already:
                seen.add(old)
        if new_text != (orig if orig is not None else text):
            try:
                _write_script({"mode": mode, "key": key, "path": path,
                               "name": name, "text": orig if orig is not None
                               else text},
                              new_text, emit=emit)
            except (OSError, RuntimeError) as e:
                say(f"[方式七] ⚠ 覆盖「{name}」失败：{e}")
                continue
            if local:
                out["replaced"] += local
                out["scripts"][short] = local
                say(f"[方式七] · 已用基准改名函数覆盖「{name}」里的 "
                    f"{local} 个函数")

    # 没找到定义的函数 → 补到 Scene_Map 末尾（保证调用点有定义）
    missing = [old for old in new_srcs if old not in seen]
    if missing:
        block = "\n\n".join(new_srcs[o] for o in missing)
        for mode, key, path, name, text, orig in cleaned:
            short = re.sub(r"^.*/", "", str(name))
            if not _xqk_name_is(short, "scene_map"):
                continue
            base = orig if orig is not None else text
            nt = base.rstrip("\n") + "\n\n" + block + "\n"
            try:
                _write_script({"mode": mode, "key": key, "path": path,
                               "name": name, "text": base}, nt, emit=emit)
            except (OSError, RuntimeError) as e:
                say(f"[方式七] ⚠ 补充函数到「{name}」失败：{e}")
                break
            out["added"] = len(missing)
            say(f"[方式七] · 游戏里缺 {len(missing)} 个函数定义，已补到「{name}」")
            break
    return out


# ==================================================================
# ★ 兼容层：给改名后的函数补「原函数名」转发壳
# ==================================================================
def _xqk_compat_block(def_line, old, new):
    """按找到的 `def <new>` 行生成转发壳（沿用同样的缩进 / `self.` 形态）。

    ★ 注释里**不要出现旧名/新名的字面量**：`replace_aide_call_sites` 是全库
      正则替换（只跳 def 行），注释里写了旧名也会被改掉。
    """
    ind = re.match(r"^[ \t]*", def_line).group(0)
    m = re.match(r"^[ \t]*def[ \t]+(self\.)?", def_line)
    recv = (m.group(1) or "") if m else ""
    return "\n".join([
        XQK_COMPAT_BEGIN,
        "# 兼容层：旧调试函数名 → 新名转发（有些插件/脚本仍按旧名调用，删了会报错）",
        f"{ind}def {recv}{old}(*args, &blk)  {XQK_COMPAT_MARK}",
        f"{ind}  {recv}{new}(*args, &blk)",
        f"{ind}end",
        XQK_COMPAT_END,
    ])


def add_aide_compat(game_dir, version=None, emit=None):
    """给每个「改名后的 debug 函数」补一个**原函数名**的转发壳。返回补了几处。

    只在「该脚本里确实定义了改名后的函数」的地方补 → 作用域与原定义一致；
    `call_debug`（改名点在调用点替换那一步）也算在内。

    ★ 幂等：调用前 `replace_aide_functions` 已经用 `_xqk_strip_compat`
      把旧壳抠干净了，这里按「def 新名存在」重新补，二跑内容完全一致。
    """
    def say(msg):
        if emit:
            emit(msg)

    added = 0
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                           both=True):
        # ★ 战斗指令菜单脚本跳过（同 `replace_aide_functions`：那边的同名
        #   `pbDebugMenu` 是战斗调试，不是我们要改名/加壳的调试菜单）
        if _xqk_is_battle_script(re.sub(r"^.*/", "", str(name))):
            continue
        new_text = text
        n = 0
        for old, new in XQK_RENAMES:
            rng = _func_range_in(new_text, new)
            if not rng:
                continue
            lines = new_text.split("\n")
            # 保险：同一处已经补过就不重复（正常到不了这，旧壳已被抠掉）
            rng_old = _func_range_in(new_text, old)
            if rng_old and XQK_COMPAT_MARK in lines[rng_old[0]]:
                continue
            block = _xqk_compat_block(lines[rng[0]], old, new).split("\n")
            lines[rng[1] + 1:rng[1] + 1] = block
            new_text = "\n".join(lines)
            n += 1
        if not n or new_text == text:
            continue
        try:
            _write_script({"mode": mode, "key": key, "path": path,
                           "name": name, "text": text}, new_text, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[方式七] ⚠ 补兼容函数到「{name}」失败：{e}")
            continue
        added += n
        say(f"[方式七] ✔ 「{name}」已补 {n} 个原函数名兼容入口"
            "（插件按旧名调用不会报错）")
    return added


# ==================================================================
# ② 注册 T 键（照各版本原生按键注册方式）
# ==================================================================
# ★ 用户明确要求：**不能只在 Scene_Map 里判一下 T**，要在「按键注册脚本」里
#   正式注册。
#   · v16 / v17 / v18：`module Input` 定义常量 + `buttonToKey` 映射键码 →
#       加 `T = <btn>` 常量，`buttonToKey` 的 case 里加
#       `when Input::T; return [0x54]`。
#   · v19+（mkxp-z）：按键表在引擎里，Ruby 侧只需 `triggerex?(:T)`
#       （SDL scancode 符号，官方自身也用 `Input.triggerex?(:A)`）；
#       为「正式注册」，再补一个 `Input::T = :T` 别名常量。
XQK_KEY_MARK_BEGIN = "# >>> pkmn-aide key begin >>>"
XQK_KEY_MARK_END = "# <<< pkmn-aide key end <<<"


def _xqk_eol(text):
    """探测文本的行尾风格 → '\\r\\n' 或 '\\n'。"""
    return "\r\n" if "\r\n" in text else "\n"


def _xqk_key_patch_legacy(text):
    """
    v16/17/18：在 `module Input` 里插 `T = <btn>`，并在 `buttonToKey` 的
    `else; return []` 之前插 `when Input::T; return [0x54]`。返回 (新文本, 处数)。

    ★ 幂等：常量/分支已存在时跳过。
    ★★ 行尾锚**必须容 `\\r`**：v16/v17/v18 的官方脚本 **100% 是 CRLF**
      （实测 16/17/18 的 `PSystem_Controls.rb` 全是 CRLF），而 rxdata 里的
      源码原样保留 `\\r`（`GS._decode_script_bytes` 只 decode、不归一行尾）。
      一旦 `$` 锚不上 → 常量 `T = 24` 没插、但下面那条无 `$` 锚的
      `when Input::T` 插进去了 → **运行期 `NameError: uninitialized
      constant Input::T`**。
    """
    n = 0
    eol = _xqk_eol(text)
    # ---- ① 常量：插在 `ALT = 23` 行之后（各版本都有 ALT）----
    if not re.search(r"(?m)^[ \t]*T[ \t]*=[ \t]*\d+\b", text):
        m = re.search(r"(?m)^([ \t]*)ALT[ \t]*=[ \t]*23[ \t]*\r?$", text)
        if not m:
            m = re.search(r"(?m)^([ \t]*)F9[ \t]*=[ \t]*\d+[ \t]*\r?$", text)
        if m:
            ind = m.group(1)
            ins = (eol + ind + f"T         = {XQK_T_BTN}"
                   + "   # T key (pkmn-aide)")
            text = text[:m.end()] + ins + text[m.end():]
            n += 1
    # ---- ② buttonToKey：在 `else; return []` / `else return []` 之前插 ----
    if not re.search(r"when[ \t]+Input::T\b", text):
        m = re.search(r"(?m)^([ \t]*)else;[ \t]*return \[\]", text)
        if not m:
            m = re.search(r"(?m)^([ \t]*)else\s+return\s+\[\]", text)
        if m:
            ind = m.group(1)
            line = (ind + f"when Input::T; return [{XQK_T_VKEY}]"
                    + "        # T (pkmn-aide)" + eol)
            text = text[:m.start()] + line + text[m.start():]
            n += 1
    return text, n


def _xqk_key_patch_mkxp(text):
    """
    v19+（mkxp-z）：补 `T = :T` 常量别名，方便 `Input.triggerex?(Input::T)`。
    返回 (新文本, 处数)。★ 幂等。
    """
    if re.search(r"(?m)^[ \t]*T[ \t]*=[ \t]*:T\b", text):
        return text, 0
    eol = _xqk_eol(text)
    # ★ 行尾锚容 `\r`（官方基准是 LF，但同人的 rxdata 里常是 CRLF）
    m = re.search(r"(?m)^([ \t]*)AUX2[ \t]*=[ \t]*R[ \t]*\r?$", text)
    if not m:
        m = re.search(r"(?m)^([ \t]*)USE[ \t]*=[ \t]*C[ \t]*\r?$", text)
    if not m:
        return text, 0
    ind = m.group(1)
    ins = eol + ind + "T        = :T     # T key (pkmn-aide)"
    text = text[:m.end()] + ins + text[m.end():]
    return text, 1


def register_aide_key(game_dir, version=None, emit=None):
    """
    在「按键注册脚本」里正式注册 T 键。返回改了几个脚本。

    ★ 幂等：同一脚本重复跑不会重复插。
    """
    def say(msg):
        if emit:
            emit(msg)

    v = engine_src.norm_ver(version)
    mkxp = v not in ("16", "17", "18")
    changed = 0
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                           both=True):
        short = re.sub(r"^.*/", "", str(name))
        if not _xqk_input_script(short):
            continue
        nt, k = (_xqk_key_patch_mkxp(text) if mkxp
                 else _xqk_key_patch_legacy(text))
        if not k or nt == text:
            continue
        try:
            _write_script({"mode": mode, "key": key, "path": path,
                           "name": name, "text": text}, nt, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[方式七] ⚠ 注册 T 键到「{name}」失败：{e}")
            continue
        changed += 1
        say(f"[方式七] ✔ 已在「{name}」里正式注册 T 键（'"
            + ("triggerex?(:T)" if mkxp else "buttonToKey → 0x54") + "）")
    return changed


# ==================================================================
# ③ 写独立插件 / 注入游戏脚本（Scene_Map 里挂 T 键）
# ==================================================================
_QXK_PLUGIN_TEMPLATE = r'''# ==================================================================
# %(tag)s（规避反调试脚本）
# ------------------------------------------------------------------
# 本文件由「宝可梦汉化翻译工具」生成 —— 请勿手改（重开一次会覆盖）。
#
# 作用：
#   · 把被反调试改坏的调试菜单函数，用**官方基准的改名版本**覆盖回来
#     （新函数名不含 d-e-b-u-g 字样，绕开反调试的字符串过滤）；
#   · 让 **T 键** 在 Scene_Map 里直接打开助手菜单。
#
# ★ 全程**不设 $D-E-B-U-G** —— 反调试里有退出游戏的守卫，一设就退。
#
# 还原：删掉 Plugins/%(dir)s/ 与 PluginScripts.rxdata 里对应那条。
# ==================================================================
$pkmn_aide_loaded = true

# ------------------------------------------------------------------
# ① 改名后的菜单函数（体来自官方基准，函数名已换）
# ------------------------------------------------------------------
%(impl)s

# ------------------------------------------------------------------
# ② T 键开菜单（Scene_Map 主循环里判 T）
# ------------------------------------------------------------------
# ★ 关键点：反调试脚本在**插件阶段**才执行，它会
#     alias del_update update
#     def update; exit if $D-E-B-U-G; del_update; end
#   把当前的 update 再包一层。所以这里**必须优先接回 del_update**。
class Scene_Map
  if method_defined?(:_pkmn_aide_ready)
    # 已经装过 → 不动（幂等）
  else
    if method_defined?(:del_update)
      alias pkmn_aide_update del_update
    else
      alias pkmn_aide_update update
    end
    define_method(:_pkmn_aide_ready) { true }

    def update
      pkmn_aide_update
      begin
        if %(tkey)s
          %(menu)s
        end
      rescue Exception
      end
    end
  end
end

# ------------------------------------------------------------------
# ③ 运行时保护（★ 靠「加载在最后」盖过反调试）
# ------------------------------------------------------------------
# 汉化/反调试插件（本作是 `汉化和其他自定义组件集合/000_Config.rb`）会做：
#   ① 把 `MenuHandlers.add` 重写成「菜单名或选项名含 debug 就丢弃」
#   ② `MenuHandlers.remove` 删掉所有 `:debug_menu` 注册项
#   ③ `def pbDebugMenu(show_all = true); exit; end` —— 直接顶掉
#   ④ `Scene_Map#update` 包一层 `exit if $DEBUG`
#   ⑤ 把 `Input` 的 press?/trigger?/repeat?/pressex?/triggerex?/repeatex?
#      各包一层，吞掉 F4–F12（必要时 `exit if $joiplay` 之类的防盗变量）
# 前四条方式① 已经用改名 / 不设 $DEBUG 绕开了，但还剩两个**实际损失**：
#   · ③ 之后，游戏脚本里那份「旧名兼容壳」会被**加载更晚的反调试**重新盖成
#     `exit`（游戏脚本比插件早加载）→ 旧名入口仍然不能用；
#   · ⑤ 之后 F9 等调试键彻底没反应（T 键不在黑名单里，所以菜单还能开）。
# 本插件排在 PluginScripts.rxdata **最后**一条加载，下面这些定义能反过来
# 盖住它们 —— 这就是「保护」的落点。
%(protect)s
'''

# T 键判据（v16–18 走 buttonToKey；v19+ 走 mkxp-z 的 scancode 符号）
XQK_TKEY_LEGACY = "Input.trigger?(Input::T)"
XQK_TKEY_MKXP = "Input.triggerex?(:T) || Input.triggerex?(Input::T)"


def _xqk_tkey(version=None):
    v = engine_src.norm_ver(version)
    return XQK_TKEY_MKXP if v not in ("16", "17", "18") else XQK_TKEY_LEGACY


# 反调试常包一层的按键方法（它会 alias 成 del_<名> 再重定义吞掉某些键）
_XQK_INPUT_PROTECT = ("press?", "trigger?", "repeat?",
                      "pressex?", "triggerex?", "repeatex?")


def _xqk_protect_block(version=None):
    """生成插件里的「运行时保护」代码段。

    两件事：
    ① **旧函数名入口**：把 `pbDebugMenu` / `call_debug` 等旧名重新定义成
       转调新名。因为反调试插件**加载更晚**，游戏脚本里那份兼容壳会被它的
       `def pbDebugMenu; exit; end` 盖掉；本插件在最后加载，这里再盖回来。
       ★ 只给「本版本真的会用到」的函数名生成，转发目标才存在。
    ② **Input 解封**：把六个按键方法换回**最底层**实现（`del_<名>`，
       即反调试包一层之前的那份），F4–F12 恢复可用。
       ★ 只解封按键，**不碰** `$joiplay` 这类防盗逻辑（那是反盗，不是反调试）。
       ★ `if method_defined?` 判据在 `class << self` 里查的是 Input 的单例
         方法 —— 游戏没被反调试包过层时整块跳过，绝不会 alias 出一个
         不存在的方法。
    """
    v = engine_src.norm_ver(version)
    names = [old for old, _s in _xqk_entry_funcs(v)] + ["call_debug"]
    lines = []
    for old in names:
        new = dict(XQK_RENAMES).get(old)
        if not new:
            continue
        lines.append(f"def {old}(*args, &blk)  # pkmn-aide protect")
        lines.append(f"  {new}(*args, &blk)")
        lines.append("end")
    body = "\n".join(lines)
    out = ["# ① 旧函数名入口 → 转调改名后的实现（盖过反调试的 `exit` 版）",
           body, "",
           "# ② Input 解封：换回最底层实现，F4–F12 恢复可用",
           "module Input",
           "  class << self"]
    for m in _XQK_INPUT_PROTECT:
        alias = "pkmn_aide_" + m.replace("?", "")
        out += [f"    if method_defined?(:del_{m})",
                f"      alias {alias} del_{m}",
                f"      def {m}(key)",
                f"        {alias}(key)",
                "      end",
                "    end"]
    out += ["  end", "end"]
    return "\n".join(out)


def _xqk_impl_block(version=None):
    """生成插件/注入里那份「改名后的基准函数」代码块。"""
    v = engine_src.norm_ver(version)
    parts = []
    for old, script in _xqk_entry_funcs(v):
        src = _baseline_func_renamed(v, script, old)
        if src:
            parts.append(src)
    return "\n\n".join(parts)


def _xqk_plugin_body(version=None):
    """生成「方式七」插件的完整 Ruby 源码。"""
    return _QXK_PLUGIN_TEMPLATE % {
        "dir": XQK_PLUGIN_DIR,
        "tag": XQK_TAG,
        "menu": XQK_MENU_FUNC,
        "impl": _xqk_impl_block(version),
        "tkey": _xqk_tkey(version),
        "protect": _xqk_protect_block(version),
    }


# 注入游戏脚本时打的标记
XQK_INJECT_MARK_BEGIN = "# >>> pkmn-aide begin >>>"
XQK_INJECT_MARK_END = "# <<< pkmn-aide end <<<"


def _xqk_inject_src(version=None):
    """写进游戏脚本那份的源码（与插件体同构，去掉注释块）。"""
    body = _xqk_plugin_body(version)
    lines = body.split("\n")
    out = [ln for ln in lines if not ln.startswith("#")]
    core = "\n".join(out).strip("\n")
    return "\n".join([
        XQK_INJECT_MARK_BEGIN,
        "# %s —— 由翻译工具生成，重开一次会覆盖" % XQK_TAG,
        "# （与 Plugins/%s/ 里的插件同内容，双保险）" % XQK_PLUGIN_DIR,
        core,
        XQK_INJECT_MARK_END,
    ])


def _xqk_strip_marked(text, begin, end):
    """按 BEGIN/END 标记抠掉整块。返回 (新文本, 抠掉几块)。

    ★ **保险：只有 BEGIN 没有 END 时整块「放弃剥离」**（返回原文、计数 0）。
      否则 `skip` 会一直是 True，把**文件剩下的全部内容**当成块吃掉 —— 实测
      `'def a\n  x=1\n# >>> pkmn-aide begin >>>\ndef b…\ntail = 3\n'` 会变成
      `'def a\n  x=1'`。标记被手工破坏 / 加载器截断时就是这个后果，
      宁可重复注入也不能把游戏脚本截断。
    """
    n = text.count(begin)
    if not n:
        return text, 0
    out = []
    lines = text.split("\n")
    skip = False
    for ln in lines:
        if begin in ln:
            skip = True
            continue
        if end in ln:
            skip = False
            continue
        if not skip:
            out.append(ln)
    if skip:                                   # 结尾还停在块里 → 标记不成对
        return text, 0
    return "\n".join(out), n


def _xqk_strip_inject(text):
    """把上次注入的那一整块抠掉（幂等用）。返回 (新文本, 抠掉几块)。"""
    return _xqk_strip_marked(text, XQK_INJECT_MARK_BEGIN, XQK_INJECT_MARK_END)


def _xqk_strip_compat(text):
    """把上次注入的「原函数名兼容壳」块抠掉（幂等用）。返回 (新文本, 抠掉几块)。

    ★ 必须在「替换 def 段」**之前**抠：兼容壳的 def 行就是旧函数名
      （`def pbDebugMenu(*args, &blk)`），不先抠掉会被 `_xqk_replace_func`
      当成原函数再顶一次 → 多出一份新名 def、壳反而没了。
    ★ 标记不成对（只有 BEGIN）时**放弃剥离**，理由见 `_xqk_strip_marked`。
    """
    return _xqk_strip_marked(text, XQK_COMPAT_BEGIN, XQK_COMPAT_END)


def install_aide_plugin(game_dir, version=None, emit=None):
    """把「方式七」的独立插件写进游戏（排最后加载）。返回信息 dict。"""
    import plugin_tools as PT

    def say(msg):
        if emit:
            emit(msg)

    root = PT.plugins_dir(game_dir)
    if not os.path.isdir(root):
        os.makedirs(root, exist_ok=True)
    # ★ 清掉历史遗留的旧插件目录（上一轮方案写过的），避免同时加载两份
    for old in XQK_OLD_PLUGIN_DIRS:
        od = os.path.join(root, old)
        if os.path.isdir(od) and os.path.abspath(od) != os.path.abspath(
                os.path.join(root, XQK_PLUGIN_DIR)):
            try:
                for fn in os.listdir(od):
                    fp = os.path.join(od, fn)
                    if os.path.isfile(fp):
                        os.remove(fp)
                os.rmdir(od)
                say(f"[方式七] · 已清掉旧插件目录 Plugins/{old}/")
            except OSError as e:
                say(f"[方式七] ⚠ 清旧插件 Plugins/{old}/ 失败：{e}")
    d = os.path.join(root, XQK_PLUGIN_DIR)
    os.makedirs(d, exist_ok=True)
    body = _xqk_plugin_body(version)
    rb = os.path.join(d, XQK_PLUGIN_FILE)
    with io.open(rb, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    with io.open(os.path.join(d, "meta.txt"), "w", encoding="utf-8",
                 newline="") as f:
        f.write(_xqk_meta_txt())
    say(f"[方式七] ✔ 已写入独立插件 Plugins/{XQK_PLUGIN_DIR}/"
        f"（元数据 {XQK_PLUGIN_NAME}，排在最后加载）")
    return {"dir": d, "file": rb}


def inject_aide_into_scripts(game_dir, version=None, emit=None):
    """把引导代码写进游戏脚本（`Scene_Map` 末尾）。返回改了几个脚本。"""
    def say(msg):
        if emit:
            emit(msg)

    src = _xqk_inject_src(version)
    if not src.strip():
        return 0
    changed = 0
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                           both=True):
        short = re.sub(r"^.*/", "", str(name))
        if not _xqk_name_is(short, "scene_map"):
            continue
        new, _ = _xqk_strip_inject(text)
        new = new.rstrip("\n") + "\n\n" + src + "\n"
        if new == text:
            continue
        try:
            _write_script({"mode": mode, "key": key, "path": path,
                           "name": name, "text": text}, new, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[方式七] ⚠ 往「{name}」注入失败：{e}")
            continue
        changed += 1
        say(f"[方式七] ✔ 已把引导代码写进「{name}」末尾（双保险）")
    return changed


def remove_aide_from_scripts(game_dir, emit=None):
    """把注入的引导块从游戏脚本里抠掉。返回还原了几个脚本。"""
    def say(msg):
        if emit:
            emit(msg)

    changed = 0
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                           both=True):
        if XQK_INJECT_MARK_BEGIN not in text:
            continue
        new, _ = _xqk_strip_inject(text)
        try:
            _write_script({"mode": mode, "key": key, "path": path,
                           "name": name, "text": text}, new, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[方式七] ⚠ 还原「{name}」失败：{e}")
            continue
        changed += 1
    return changed


# ==================================================================
# ④ 批量改调用点 + UI 选项名 + 注册表 key
# ==================================================================
def _rewrite_calls(text):
    """把调用点改名 → (新文本, 改了几处)。

    ★ `def` 行：pbXxx 系列的定义点由 `replace_aide_functions` 负责整段换，
      这里跳过；但 **`call_debug` 例外**（它不是 debug 菜单函数，只是个
      Scene_Map 私有入口 → 直接连 def 一起改名）。
    ★ **兼容壳整块跳过**（行尾 `# pkmn-aide compat`）：壳的 def 行写的就是旧名，
      被改掉会变成 `def call_aide; call_aide; end` → 无限递归。
    """
    n = 0
    guard = r"(?![^\n]*" + re.escape(XQK_COMPAT_MARK) + r")"
    for old, new in XQK_RENAMES:
        skip_def = (old != "call_debug")
        pat = re.compile(
            r"(?m)^" + guard
            + (r"(?![ \t]*(?:def\b|alias\b|def self\.))" if skip_def else "")
            + r"(?P<pre>[^\n]*?)"
            # ★ 旧名左边也不许接标识符字符：`my_pbDebugMenu(x)` 这种
            #   「以前缀方式包含旧名」的标识符以前会被一起改掉。
            + r"(?<![0-9A-Za-z_])"
            + re.escape(old)
            + r"(?P<post>\s*[\(\s]|\s*$)")
        def sub(m, _new=new):
            return m.group("pre") + _new + m.group("post")
        text, k = pat.subn(sub, text)
        n += k
    # 注册表 key 改名
    # ★ 必须带词边界：`text.replace(":debug", ":aide")` 会把 `:debug_calling`
    #   一起改掉（见 `_xqk_sym_re` 的说明），那是个真机踩过的坑。
    for old, new in XQK_SYM_RENAMES:
        text, k = _xqk_sym_re(old).subn(new, text)
        n += k
    return text, n


def _xqk_calls_interesting(text):
    """正文里是否有「方式七关心的调用/注册名」——用于按内容筛选脚本。

    ★ 不能只按**脚本名**筛：游戏里可能有任意名字的脚本（例如本作的
      `Marin's Map Exporter`）向 `:debug_menu` 注册条目、或调用 debug 函数。
      只按名字筛会漏掉它们，反调试的 `include?("debug")` 过滤照样能拦住。
    """
    if not text:
        return False
    for old, _ in XQK_RENAMES:
        if old in text:
            return True
    for old, _ in XQK_SYM_RENAMES:
        # ★ 同样必须带词边界：`":debug" in ":debug_calling"` 也是真 → 会把
        #   Game_Temp 这种「只是名字里带 :debug」的脚本拉进来白改一遍。
        if _xqk_sym_re(old).search(text):
            return True
    return False


def replace_aide_call_sites(game_dir, emit=None):
    """把游戏/插件脚本里所有 debug 函数调用点 + 注册 key 改名。返回几处。"""
    def say(msg):
        if emit:
            emit(msg)
    changed = 0
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                           both=True):
        short = re.sub(r"^.*/", "", str(name))
        # ★ 战斗指令菜单脚本整个跳过：那里的 `pbDebugMenu` 是战斗调试入口
        #   （类内方法，调用 `pbBattleDebug`），改了调用点会让战斗中打开的是
        #   完整调试菜单，语义就错了。
        if _xqk_is_battle_script(short):
            continue
        # ★ 名字匹配 **或** 正文含 debug 相关调用/注册名 → 都要处理
        if not _xqk_script_match(short) and not _xqk_calls_interesting(text):
            continue
        new, k = _rewrite_calls(text)
        if not k:
            continue
        try:
            _write_script({"mode": mode, "key": key, "path": path,
                           "name": name, "text": text}, new, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[方式七] ⚠ 改「{name}」调用失败：{e}")
            continue
        changed += k
        say(f"[方式七] · 已替换「{name}」里的 {k} 处调用/注册名")
    return changed


# 历史误改的符号：`:debug<X>` 被裸替换成 `:aide<X>`（X 非空且整条不是我们有意的）
_XQK_SYM_REPAIR_RE = re.compile(r"(?<![0-9A-Za-z_]):aide([0-9A-Za-z_]+)")


def repair_aide_syms(game_dir, emit=None):
    """修回**历史版本**误改的符号（`:debug<X>` → `:aide<X>`）。返回修了几处。

    ★ 为什么要有这一步：早期版本用 `text.replace(":debug", ":aide")` 改名，
      凡是**以 `:debug` 开头**的符号都被一起改了 —— 最典型的就是
      `attr_accessor :debug_calling`（`Game_Temp`）被改成 `:aide_calling`，
      而调用点 `$game_temp.debug_calling` 没有冒号、没被改 →
      游戏跑图时 `NoMethodError: undefined method 'debug_calling' for
      #<Game_Temp>`（`Scene_Map#update`）。
    ★ 规则：把「不是我们有意改的」`:aide<X>` 还原成 `:debug<X>`
      （有意改的只有 `_XQK_SYM_NEW` 里那几条：`:aide` / `:aide_menu` /
      `:aide_pokemon_menu`）。`aide*` 是本工具自己的命名空间，这样还原是安全的。
    ★ 幂等：修完这些符号就不存在了，二跑 0 处。
    """
    def say(msg):
        if emit:
            emit(msg)

    hit = {"n": 0}

    def sub(m):
        full = m.group(0)
        if full in _XQK_SYM_NEW:            # 我们有意的改名 → 原样留着
            return full
        hit["n"] += 1
        return ":debug" + m.group(1)

    changed = 0
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                           both=True):
        hit["n"] = 0
        new = _XQK_SYM_REPAIR_RE.sub(sub, text)
        # ★ 只按「真的改动了」算：`_XQK_SYM_NEW` 那几条会被匹配到但原样返回，
        #   按 subn 的匹配数算会误报、还会白写一次文件（不幂等）。
        if not hit["n"] or new == text:
            continue
        try:
            _write_script({"mode": mode, "key": key, "path": path,
                           "name": name, "text": text}, new, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[方式七] ⚠ 修回「{name}」的误改名失败：{e}")
            continue
        changed += hit["n"]
        say(f"[方式七] ✔ 已把「{name}」里 {hit['n']} 处误改的符号还原"
            "（:aide* → :debug*）")
    return changed


def _relabel_aide_strings(text):
    """把 `"Debug"` / `'Debug'` 字面量改成 «助手»。返回 (新文本, 处数)。"""
    out = []
    n = 0
    for ln in text.split("\n"):
        stripped = ln.lstrip()
        if stripped.startswith("#"):
            out.append(ln)
            continue
        for q in ('"', "'"):
            old = q + "Debug" + q
            if old in ln:
                n += ln.count(old)
                ln = ln.replace(old, q + "助手" + q)
        out.append(ln)
    return "\n".join(out), n


def relabel_aide_ui(game_dir, emit=None):
    """把 UI 里显示的 `"Debug"` 选项名改成 `"助手"`。返回几处。"""
    def say(msg):
        if emit:
            emit(msg)
    changed = 0
    extra = {"ui_bag", "pscreen_bag", "bagwithinteractuableparty",
             "tradefrompc", "pokedexquickaccess"}
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                           both=True):
        short = re.sub(r"^.*/", "", str(name))
        norm = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", short.lower())
        # ★ 名字在白名单里，或正文确实含 `"Debug"` 字面量 → 都要处理
        if not (_xqk_script_match(short) or norm in extra
                or XQK_LABEL_OLD in text):
            continue
        new, n = _relabel_aide_strings(text)
        if not n:
            continue
        try:
            _write_script({"mode": mode, "key": key, "path": path,
                           "name": name, "text": text}, new, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[方式七] ⚠ 改「{name}」选项名失败：{e}")
            continue
        changed += n
        say(f"[方式七] · 已把「{name}」里 {n} 处选项名改成「助手」")
    return changed


# ==================================================================
# ⑤ 插件脚本 rxdata：把 zzz_pkmn_aide 编进 PluginScripts.rxdata
#    + 关掉插件自动重编译（让 rxdata 固定，不再被 Plugins/ 目录覆盖）
# ==================================================================
# ★ 为什么要写进 rxdata：
#   `PluginManager.runPlugins` **实际加载的是 `Data/PluginScripts.rxdata`**，
#   `Plugins/` 目录只在「算加载顺序 + 判断是否要重编译」时被扫。
#   而 `needCompiling?` 开头就是 `return false if !$DEBUG` —— 普通启动根本
#   不读目录、不重编译；**只有 $DEBUG 启动**（方式①/⑦、调试启动器）才会扫
#   目录并可能重编译。
#   ⇒ 把插件直接编进 rxdata + 关掉重编译 → rxdata 固定，加载可控。
XQK_RXDATA_TAG = "[pkmn-aide] 编进 PluginScripts.rxdata"

# ------------------------------------------------------------
# ★★ 插件元数据：**一份定义，两处使用**（Plugins/<dir>/meta.txt + rxdata 条目）
# ------------------------------------------------------------
# 校验规则照抄游戏自己的 `PluginManager.register`（v18 起每版都有，只是文案被
# 各语言的汉化组翻译过）：
#     :name / :version / :link  **三条都必须是非空 String**，否则
#     `register` 直接 `Kernel.exit! true` —— **游戏在标题画面前就死掉**，
#     弹窗只有一句「Plugin Error: …」，连堆栈都没有。
# ★ 实测踩过：本字段原来写的 `"link": ""` → 在 Pokemon Revival（西语游戏）
#   上报「Error del plugin: El enlace del plugin debe ser una cadena no vacía.」
#   （= Plugin link must be a non-empty string.）→ 方式⑦ 一开游戏就崩。
#   ⇒ link 绝不能留空串 / nil；credits 给了就必须是字符串数组。
# ★ `runPlugins` 在**非 $DEBUG** 启动时也会 `load_data("Data/PluginScripts.rxdata")`
#   并逐条 `register`（`listAll` 开头就 `return [] if !$DEBUG`，所以普通启动
#   根本不读 Plugins/ 目录、不读 meta.txt）→ 出错的一定是 rxdata 里那条。
XQK_PLUGIN_LINK = "https://github.com/nevermore-glimpse/pkmn_translator"

_XQK_META = {
    "name": XQK_PLUGIN_NAME,
    "version": "1.0.0",
    "essentials": ["16", "16.1", "16.2", "17", "17.1", "17.2", "18", "18.1",
                   "19", "19.1", "20", "20.1", "21", "21.1"],
    "link": XQK_PLUGIN_LINK,
    "credits": ["pkmn_translator"],
}


def _xqk_meta_bad(meta):
    """按游戏的 register 规则自检：返回「不合法的字段名列表」（空 = 通过）。

    ★ 只查**会导致 Kernel.exit! 的硬性字段**（name / version / link）。
    """
    bad = []
    for k in ("name", "version", "link"):
        v = meta.get(k)
        if not v or not isinstance(v, str):
            bad.append(k)
    cr = meta.get("credits", [])
    if isinstance(cr, str):
        cr = [cr]
    if not isinstance(cr, list) or any(not isinstance(x, str) for x in cr):
        bad.append("credits")
    return bad


def _xqk_meta_txt():
    """`Plugins/<dir>/meta.txt` 的文本（属性行从 `_XQK_META` 生成，不会跑偏）。"""
    m = _XQK_META
    props = "\n".join([
        f"Name       = {m['name']}",
        f"Version    = {m['version']}",
        "Essentials = " + ",".join(m["essentials"]),
        f"Link       = {m['link']}",
        "Credits    = " + ",".join(m["credits"]),
    ])
    return props + "\n" + (
        f"\n# [pkmn-aide] {XQK_TAG}（规避反调试：基准改名函数 + 兼容壳 + T 键）\n"
        "#\n"
        "# ★ 本插件**故意不声明 Requires/Optional 依赖**：\n"
        "#   加载顺序本来就对 —— PluginManager 的 listAll 走 Dir.get（路径\n"
        "#   字符串排序），Plugins/zzz_pkmn_aide 排在中文名插件\n"
        "#   （汉化和其他自定义组件集合）之前；getPluginOrder 拿到 Name 列表后\n"
        "#   .reverse() → 中文名插件（反调试）先加载、本插件后加载，\n"
        "#   后定义覆盖先定义，正是我们要的顺序。\n"
        "#   meta 里的依赖行必须写真实插件名 + 版本号（Optional 行还强制要版本），\n"
        "#   写错了会在启动时弹出\n"
        "#   \"El plugin 'pkmn aide' requiere que el plugin '…' esté presente\"。\n"
        "#\n"
        "# ★★ Name / Version / Link 三条**都必须非空**（PluginManager.register\n"
        "#   的硬校验，缺一条游戏会在标题画面前 `Kernel.exit!`）。\n"
    )


def _xqk_rxdata_entry(version=None):
    """把 Plugins/zzz_pkmn_aide/ 的内容做成一条 rxdata 插件条目。

    结构：`[插件名, meta_hash, [[文件名, zlib(源码)], ...]]`

    ★ meta 的 key 必须是 **Symbol** —— `PluginManager.register(meta)` 读的是
      `meta[:name]` / `meta[:version]` / `meta[:essentials]`。用 Python str 写
      出来会变成 `RubyString`，`meta[:name]` 取到 nil → 插件名空 → 各种诡异
      报错。这里照 `plugin_tools.compile_plugins` 的做法，用 `Symbol(k)`。
    ★ meta 的取值统一走 `_XQK_META`（与 meta.txt 同源），并先过一遍
      `_xqk_meta_bad` 自检 —— 缺 name/version/link 会让游戏**直接退出**，
      宁可不写这份 rxdata，也不能把游戏搞崩。
    ★ 文件体也是 **bytes**（`Zlib::Deflate` 出来的二进制）—— `_to_bytes`
      会把 str 编码成 utf-8；这里我们直接给 bytes，保持一致。
    """
    bad = _xqk_meta_bad(_XQK_META)
    if bad:
        raise ValueError(f"插件元数据不合法（{', '.join(bad)}）—— "
                         "name/version/link 必须是非空字符串")
    body = _xqk_plugin_body(version)
    meta = {}
    for k, v in _XQK_META.items():
        meta[Symbol(k)] = v
    return [XQK_PLUGIN_NAME, meta,
            [[XQK_PLUGIN_FILE, zlib.compress(body.encode("utf-8"))]]]


def write_aide_to_rxdata(game_dir, version=None, emit=None):
    """把 zzz_pkmn_aide 编进 `Data/PluginScripts.rxdata`。

    · 找不到 rxdata → 跳过（v16–v18 没有插件机制）；
    · 已有同名条目 → **原位替换**（幂等，顺序不动）；
      ★ 同名条目**有多条**时只留第一条、其余删掉 —— 重复的插件名会让游戏
        在 `register` 里报「A plugin called '…' already exists.」后
        `Kernel.exit!`（历史版本万一追加过就会踩到）。
    · 没有 → 追加到**末尾**（rxdata 的顺序 = 加载顺序，追加=最后加载 ✅）。
    返回 {"ok","action","index","total","dup"}。
    """
    def say(msg):
        if emit:
            emit(msg)

    path = GS.plugin_rxdata_path(game_dir)
    if not os.path.isfile(path):
        return {"ok": False, "action": "missing", "index": -1, "total": 0}
    try:
        with io.open(path, "rb") as f:
            obj = GS._rb_load_bytesafe(f)
    except Exception as e:                              # noqa: BLE001
        say("[方式七] ⚠ " + GS.rxdata_error_text(path, e))
        return {"ok": False, "action": "read_error", "index": -1, "total": 0}
    if not isinstance(obj, list):
        return {"ok": False, "action": "bad_format", "index": -1, "total": 0}

    entry = _xqk_rxdata_entry(version)
    hits = []
    for i, ent in enumerate(obj):
        try:
            # ★ 容器是 `_rb_load_bytesafe` 读的（String 按 latin1 解），
            #   非 ASCII 名字用 str() 会得到乱码 → 必须走 _plugin_name_text。
            if ent and GS._plugin_name_text(ent[0]) == XQK_PLUGIN_NAME:
                hits.append(i)
        except (TypeError, IndexError):
            continue
    dup = 0
    if hits:
        idx = hits[0]
        obj[idx] = entry
        for i in reversed(hits[1:]):        # 倒序删，避免下标错位
            del obj[i]
            dup += 1
        action = "replaced"
    else:
        obj.append(entry)
        idx = len(obj) - 1
        action = "appended"
    try:
        # ★ 写之前先备份（`.pkmn-overwrite-<时间戳>.bak`，与 `_write_script`
        #   同一套做法、跨运行复用同一份备份）。这份 rxdata 是整个插件机制的
        #   命根子，方式⑦ 以前是唯一不产出备份的路径 → 出问题没法用
        #   「还原覆盖」回滚。句柄已在上一步用 with 关掉，Windows 下 rename
        #   才不会被占住。
        _backup(path, emit=emit)
        with io.open(path, "wb") as f:
            GS._rb_write_safe(f, obj)
    except Exception as e:                              # noqa: BLE001
        say(f"[方式七] ⚠ 写 PluginScripts.rxdata 失败：{e}")
        return {"ok": False, "action": "write_error", "index": -1,
                "total": len(obj)}
    say(f"[方式七] ✔ 已把 {XQK_PLUGIN_NAME!r} "
        + ("原位替换" if action == "replaced" else "追加到末尾")
        + f"（第 {idx} 条 / 共 {len(obj)} 条）→ PluginScripts.rxdata"
        + (f"｜顺带清掉 {dup} 条重复条目" if dup else ""))
    return {"ok": True, "action": action, "index": idx, "total": len(obj),
            "dup": dup}


# 「关掉插件自动重编译」的注入标记
XQK_NORECOMPILE_BEGIN = "# >>> pkmn-aide no-recompile begin >>>"
XQK_NORECOMPILE_END = "# <<< pkmn-aide no-recompile end <<<"

# ★ 让 `PluginManager.needCompiling?` 永远返回 false：
#   直接把它换成 `def self.needCompiling?(*); false; end`。
#   这样 runPlugins 永远走 `load_data("Data/PluginScripts.rxdata")`，
#   不再扫 `Plugins/` 目录、不再重编译 → rxdata 内容完全由我们控制。
XQK_NORECOMPILE_SRC = (
    "module PluginManager\n"
    "  class << self\n"
    "    def needCompiling?(*args)\n"
    "      return false\n"
    "    end\n"
    "  end\n"
    "end"
)


def disable_plugin_recompile(game_dir, emit=None):
    """在游戏脚本里关掉「插件自动重编译」（rxdata 固定）。返回改了几个脚本。"""
    def say(msg):
        if emit:
            emit(msg)

    changed = 0
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                           both=True):
        short = re.sub(r"^.*/", "", str(name))
        # 只在「PluginManager」脚本里注入（那里最后定义、一定能覆盖引擎原实现）
        if not _xqk_name_is(short, "pluginmanager"):
            continue
        block = "\n".join([
            XQK_NORECOMPILE_BEGIN,
            "# %s —— 由翻译工具生成，重开一次会覆盖" % XQK_RXDATA_TAG,
            XQK_NORECOMPILE_SRC,
            XQK_NORECOMPILE_END,
        ])
        # ★ 幂等：先把上次注入的块**真正抠掉**再拼新的。
        #   以前判据是「块必须在文件末尾」（`endswith`），一旦块后面还有任何内容
        #   （别的工具追加、手工编辑、抠除后残留空行）判据就失效 → 每跑一次
        #   多叠一份 `module PluginManager …`，越叠越厚。抠除结果还被后面
        #   无条件覆盖掉，等于「先抠后拼」写成了「直接拼」。
        new, _ = _xqk_strip_no_recompile(text)
        new = new.rstrip("\n") + ("\n\n" + block + "\n" if new.strip()
                                  else block + "\n")
        if new == text:
            continue
        try:
            _write_script({"mode": mode, "key": key, "path": path,
                           "name": name, "text": text}, new, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[方式七] ⚠ 关重编译：写「{name}」失败：{e}")
            continue
        changed += 1
        say(f"[方式七] ✔ 已在「{name}」里关掉插件自动重编译（rxdata 固定）")
    return changed


def _xqk_strip_no_recompile(text):
    """抠掉上次注入的「关重编译」块。返回 (新文本, 抠掉几块)。

    ★ 标记不成对时放弃剥离（同 `_xqk_strip_marked`：宁可重复注入也不能截断脚本）。
    """
    return _xqk_strip_marked(text, XQK_NORECOMPILE_BEGIN, XQK_NORECOMPILE_END)


def undo_disable_plugin_recompile(game_dir, emit=None):
    """还原「关重编译」注入。返回改了几个脚本。"""
    def say(msg):
        if emit:
            emit(msg)
    changed = 0
    for mode, key, path, name, text in GS.iter_named_scripts(game_dir,
                                                           both=True):
        if XQK_NORECOMPILE_BEGIN not in text:
            continue
        new, _ = _xqk_strip_no_recompile(text)
        try:
            _write_script({"mode": mode, "key": key, "path": path,
                           "name": name, "text": text}, new, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[方式七] ⚠ 还原「{name}」失败：{e}")
            continue
        changed += 1
    return changed


# ==================================================================
# ⑥ 给「依赖别的插件才能跑」的调用加 defined? 保护
# ==================================================================
# ★ 背景（真实踩过）：`【】汉化和其他自定义组件集合/002_GameBugFix.rb` 里
#   直接调 `MidbattleHandlers.add(...)`，但 `MidbattleHandlers` 由
#   `[DBK_000] Deluxe Battle Kit` 提供。插件加载顺序**纯靠目录名排序**
#   （这些插件 meta 里都没有依赖声明），中文名目录排在 DBK 之后 → reverse
#   后**最先加载** → 执行到那几行时 DBK 还没加载 → `NameError:
#   uninitialized constant MidbattleHandlers` → 游戏直接崩。
#   保护写法：把每个 `Xxx.add(...)` 调用包一层 `if defined?(Xxx)`。
_XQK_GUARD_MARK = "# pkmn-aide guard"


def _xqk_paren_end(lines, start):
    """从 lines[start] 起找**第一个 `(`** 的匹配 `)` 所在行（跳过字符串/注释）。

    用于把一个 `Foo.bar(args)` 调用的完整实参块切出来。
    """
    depth = 0
    seen_open = False
    in_str = None
    for i in range(start, len(lines)):
        ln = lines[i]
        j = 0
        while j < len(ln):
            c = ln[j]
            if in_str:
                if c == "\\":
                    j += 2
                    continue
                if c == in_str:
                    in_str = None
                j += 1
                continue
            if c in ('"', "'"):
                in_str = c
                j += 1
                continue
            if c == "#":
                break
            if c == "(":
                depth += 1
                seen_open = True
            elif c == ")":
                depth -= 1
                if seen_open and depth == 0:
                    return i
            j += 1
    return None


def guard_plugin_dependency(script_path, const_name, emit=None):
    """给脚本里所有 `const_name.add(...)` 调用包一层 `if defined?(const_name)`。

    · 幂等：已包过的（紧跟 `_XQK_GUARD_MARK` 注释）跳过；
    · 块内每行统一加 2 空格缩进（保持可读）；
    · 返回改了几处。
    """
    def say(msg):
        if emit:
            emit(msg)

    try:
        # ★ newline="" 保留原始行尾（本模块约定：行里留着 \r，拼回时用 \n）。
        #   用默认的通用换行读，CRLF 脚本会被静默改写成 LF。
        with io.open(script_path, encoding="utf-8", errors="replace",
                     newline="") as f:
            text = f.read()
    except OSError as e:
        say(f"[方式七] ⚠ 读「{os.path.basename(script_path)}」失败：{e}")
        return 0
    lines = text.split("\n")
    out = []
    i = 0
    changed = 0
    call_re = re.compile(r"^[ \t]*" + re.escape(const_name) + r"\.add\s*\(")
    while i < len(lines):
        ln = lines[i]
        # 已包过（上一行是 guard 标记）→ 原样拷贝，跳过整块
        if out and _XQK_GUARD_MARK in out[-1]:
            out.append(ln)
            i += 1
            continue
        if call_re.match(ln):
            end = _xqk_paren_end(lines, i)
            if end is None:
                out.append(ln)
                i += 1
                continue
            indent = re.match(r"^([ \t]*)", ln).group(1)
            cr = "\r" if ln.endswith("\r") else ""      # 保留 CRLF 行尾
            out.append(f"{indent}if defined?({const_name})  "
                       f"{_XQK_GUARD_MARK}{cr}")
            for k in range(i, end + 1):
                out.append(("  " + lines[k]) if lines[k].strip() else lines[k])
            out.append(f"{indent}end{cr}")
            changed += 1
            i = end + 1
            continue
        out.append(ln)
        i += 1
    if not changed:
        return 0
    new = "\n".join(out)
    try:
        with io.open(script_path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    except OSError as e:
        say(f"[方式七] ⚠ 写「{os.path.basename(script_path)}」失败：{e}")
        return 0
    say(f"[方式七] ✔ 已给「{os.path.basename(script_path)}」里 "
        f"{changed} 处 `{const_name}.add` 加 defined? 保护")
    return changed


# ★★ 只处理**已知会崩**的那一个文件，绝不扫全库！
#   教训：第一版 `guard_known_plugin_deps` 扫了所有插件目录，结果把
#   `[DBK_000] Deluxe Battle Kit` 自己的 `[002] Midbattle Triggers.rb`（49 处）、
#   `[004] MidbattleHandlers Scripts.rb`（10 处）、`[LBDSKY] …/009 Deluxe
#   Additions.rb`（4 处）也包了 `defined?` —— 那些文件本来就在 DBK 之后
#   加载、常量一定已定义，**根本不需要保护**，白改还容易出问题。
#   所以这里改成「白名单：只认这一个目录 + 这一个文件名」。
XQK_GUARD_TARGETS = (
    # (插件目录名, 相对该目录的文件名)
    ("【】汉化和其他自定义组件集合", "002_GameBugFix.rb"),
)
# 这些插件提供的常量可能被上面的目标文件提前引用
XQK_GUARD_CONSTS = ("MidbattleHandlers",)


def guard_known_plugin_deps(game_dir, emit=None):
    """给**已知会崩**的插件文件里的 `Xxx.add` 调用加 `defined?` 保护。

    ★ 只动 `XQK_GUARD_TARGETS` 白名单里的文件；提供方（DBK）一律不碰。
    返回总处数。
    """
    import plugin_tools as PT
    total = 0
    root = PT.plugins_dir(game_dir)
    if not os.path.isdir(root):
        return 0
    for pdir, fname in XQK_GUARD_TARGETS:
        p = os.path.join(root, pdir, fname)
        if not os.path.isfile(p):
            continue
        try:
            txt = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for const in XQK_GUARD_CONSTS:
            if (const + ".add") not in txt:
                continue
            total += guard_plugin_dependency(p, const, emit=emit)
    return total


# ==================================================================
# ⑦ 修 rxdata 里的插件加载顺序
# ==================================================================
# ★ 背景：`PluginManager.runPlugins` **就按 `PluginScripts.rxdata` 数组的顺序
#   逐个 `eval`**（`scripts.each { |name, meta, script| … eval(code) }`），
#   数组下标 = 加载顺序。真实游戏这份 rxdata 的顺序是「上一次 compilePlugins
#   从 `Plugins/` 目录算出来的」——而那套排序只看目录名字符串，**别人的依赖
#   声明一概不看**（这些插件 meta 里全都没有 dependencies）。结果
#   `【】汉化和其他自定义组件集合`（反调试整合包，`【` 码点大 → 排序最后 →
#   reverse 后**最先加载**）在 `Deluxe Battle Kit`（提供 `MidbattleHandlers`）
#   之前 eval → `NameError` → 崩。
#
#   修法（与 `defined?` 保护互补）：
#     · `defined?` 保护是**治本**——就算顺序不对也不会崩；
#     · 这里顺手把顺序也**摆正**：让「提供方」排在「使用方」前面。
#   做法不猜依赖图，只认 `XQK_ORDER_RULES` 里的**已知会崩**的组合。
XQK_ORDER_RULES = (
    # (使用方插件名, 必须排在它前面的提供方插件名)
    ("汉化和其他自定义组件集合", "Deluxe Battle Kit"),
)


def fix_plugin_load_order(game_dir, emit=None):
    """把 `Data/PluginScripts.rxdata` 里「使用方」挪到「提供方」之后。

    · 只认 `XQK_ORDER_RULES` 里的已知组合，别的条目位置一律不动；
    · 幂等：顺序本来就对 → 返回 0；
    · 返回调整了几条（写回成功才计数）。
    """
    def say(msg):
        if emit:
            emit(msg)

    path = GS.plugin_rxdata_path(game_dir)
    if not os.path.isfile(path):
        return 0
    try:
        with io.open(path, "rb") as f:
            obj = GS._rb_load_bytesafe(f)
    except Exception as e:                              # noqa: BLE001
        say("[方式七] ⚠ " + GS.rxdata_error_text(path, e))
        return 0
    if not isinstance(obj, list):
        return 0

    def _idx(name):
        for i, ent in enumerate(obj):
            try:
                if ent and GS._plugin_name_text(ent[0]) == name:
                    return i
            except (TypeError, IndexError):
                continue
        return -1

    moved = 0
    for user, provider in XQK_ORDER_RULES:
        ui, pi = _idx(user), _idx(provider)
        if ui < 0 or pi < 0:
            continue
        if ui > pi:
            continue                                    # 顺序本来就对 → 幂等
        ent = obj.pop(ui)
        pi = _idx(provider)                             # pop 后重新定位
        obj.insert(pi + 1, ent)
        moved += 1
        say(f"[方式七] ✔ 调整插件顺序：「{user}」移到「{provider}」之后"
            f"（{ui} → {pi + 1}）")
    if not moved:
        return 0
    try:
        with io.open(path, "wb") as f:
            GS._rb_write_safe(f, obj)
    except Exception as e:                              # noqa: BLE001
        say(f"[方式七] ⚠ 写 PluginScripts.rxdata 失败：{e}")
        return 0
    return moved


def undo_fix_plugin_load_order(game_dir, emit=None):
    """把 `fix_plugin_load_order` 挪走的条目挪回**最前面**（近似还原）。

    没有存原始下标（rxdata 是二进制、没法写注释），所以只能恢复到
    「使用方排最前」的初始状态 —— 正是崩之前的样子。
    """
    def say(msg):
        if emit:
            emit(msg)

    path = GS.plugin_rxdata_path(game_dir)
    if not os.path.isfile(path):
        return 0
    try:
        with io.open(path, "rb") as f:
            obj = GS._rb_load_bytesafe(f)
    except Exception:                                   # noqa: BLE001
        return 0
    if not isinstance(obj, list):
        return 0
    moved = 0
    for user, _provider in XQK_ORDER_RULES:
        for i, ent in enumerate(obj):
            try:
                if ent and GS._plugin_name_text(ent[0]) == user:
                    if i == 0:
                        break
                    obj.insert(0, obj.pop(i))
                    moved += 1
                    say(f"[方式七] ✔ 已把「{user}」挪回最前")
                    break
            except (TypeError, IndexError):
                continue
    if not moved:
        return 0
    try:
        with io.open(path, "wb") as f:
            GS._rb_write_safe(f, obj)
    except Exception:                                   # noqa: BLE001
        return 0
    return moved


# ==================================================================
# 方式七主入口
# ==================================================================
def patch_rewrite_debug_func(game_dir, version=None, emit=None):
    """
    方式七：改名调试函数（规避反调试脚本）。

    步骤：
      ⓪ 先**修回历史误改**（早期版把 `:debug<X>` 裸替换成 `:aide<X>`，
         例如 `attr_accessor :debug_calling` → 游戏一跑图就 NoMethodError）；
      ① 用**官方基准的改名函数**覆盖游戏里 debug 相关函数的定义；
      ② 在「按键注册脚本」里**正式注册 T 键**；
      ③ 批量改所有调用点 / 菜单注册 key；
      ④ UI 里显示的 `"Debug"` 选项名 → `"助手"`；
      ④.5 **保留原函数名**：给每个改名后的函数在同一作用域补一个转发壳
         （`def pbDebugMenu(*args, &blk) → pbAideWindow(*args, &blk)`），
         免得还在按旧名调用的插件 / 脚本 `NameError`；
      ④.6 **同步删掉「$DEBUG 才生效」的条件**（同方式②）：改名只换了入口，
         穿墙 / F9 判定 / 队伍·背包里的 Debug 项 / v20+ 的
         `"condition" => proc { next $DEBUG }` 那些判定还在的话就还是关着的。
         ★ 只删条件、绝不写 `$DEBUG`（写了就撞反调试的 `exit if $DEBUG`）；
      ⑤ 写独立插件 + 把同内容注入游戏 `Scene_Map` 末尾（双保险）；
      ⑥ 把插件编进 `Data/PluginScripts.rxdata`（v19+ 的插件机制，
         游戏真正 eval 的就是它）+ 关掉插件自动重编译（rxdata 固定，
         不再被 `Plugins/` 目录覆盖）；
      ⑦ 给「依赖别的插件才能跑」的调用加 `defined?` 保护（治本）；
      ⑧ 顺手把 rxdata 里的加载顺序摆正（把使用方挪到提供方之后）。

    返回 {"ok","plugin","replaced","added","keyed","renamed","relabeled",
          "compat","injected","rxdata","norecompile","guarded","reordered",
          "repaired","reason"}。
    """
    def say(msg):
        if emit:
            emit(msg)

    out = {"ok": True, "plugin": None, "replaced": 0, "added": 0, "keyed": 0,
           "renamed": 0, "relabeled": 0, "compat": 0, "stripped": 0,
           "injected": 0, "rxdata": None, "norecompile": 0, "guarded": 0,
           "reordered": 0, "repaired": 0, "reason": ""}

    # ---- ⓪ 修回历史误改的符号（早期版的裸替换把 :debug_calling 也改了） ----
    try:
        out["repaired"] = repair_aide_syms(game_dir, emit=emit)
    except (OSError, RuntimeError) as e:
        say(f"[方式七] ⚠ 修回误改名失败：{e}")

    # ---- ① 覆盖函数定义 ----
    try:
        r1 = replace_aide_functions(game_dir, version=version, emit=emit)
        out["replaced"] = r1["replaced"]
        out["added"] = r1["added"]
    except (OSError, RuntimeError, ValueError) as e:
        out["ok"] = False
        out["reason"] = f"覆盖函数失败：{e}"
        say(f"[方式七] ✘ {out['reason']}")
        return out

    # ---- ② 注册 T 键 ----
    try:
        out["keyed"] = register_aide_key(game_dir, version=version, emit=emit)
    except (OSError, RuntimeError) as e:
        say(f"[方式七] ⚠ 注册 T 键失败：{e}")

    # ---- ③ 改调用点 / 注册 key ----
    out["renamed"] = replace_aide_call_sites(game_dir, emit=emit)

    # ---- ④ UI 选项名 ----
    out["relabeled"] = relabel_aide_ui(game_dir, emit=emit)

    # ---- ④.5 补「原函数名」兼容层 ----
    # ★ 必须排在 ③（改调用点，`call_debug` 在这里才改完名）之后、
    #   ⑤（注入 Scene_Map）之前 —— 这样壳只落在游戏脚本里真正定义函数的地方，
    #   作用域与原定义一致；不会塞进注入块里变成重复定义。
    try:
        out["compat"] = add_aide_compat(game_dir, version=version, emit=emit)
    except (OSError, RuntimeError) as e:
        out["compat"] = 0
        say(f"[方式七] ⚠ 补原函数名兼容层失败：{e}")

    # ---- ④.6 同步删掉「$DEBUG 才生效」的条件（同方式②）----
    # 改名只是把**入口**换掉了名；游戏脚本里那些 `if $DEBUG …` 的判定还在，
    # 不删的话「助手菜单外的调试功能」（穿墙、F9 判定、队伍/背包里的 Debug 项、
    # v20+ 的 `"condition" => proc { next $DEBUG }`）依然是关着的。
    # ★ 只删条件、**绝不写 $DEBUG** —— 写了就撞反调试的 `exit if $DEBUG`。
    try:
        out["stripped"] = patch_remove_debug_conditions(
            game_dir, emit=emit).get("changed", 0)
    except (OSError, RuntimeError, ValueError) as e:
        out["stripped"] = 0
        say(f"[方式七] ⚠ 删 $DEBUG 条件失败：{e}")

    # ---- ⑤ 独立插件 + 注入 ----
    try:
        out["plugin"] = install_aide_plugin(game_dir, version=version,
                                            emit=emit)
    except (OSError, RuntimeError, ValueError) as e:
        say(f"[方式七] ⚠ 写独立插件失败：{e}")
    try:
        out["injected"] = inject_aide_into_scripts(game_dir, version=version,
                                                   emit=emit)
    except (OSError, RuntimeError) as e:
        say(f"[方式七] ⚠ 写进游戏脚本失败：{e}")

    # ---- ⑥ 编进 PluginScripts.rxdata + 关掉自动重编译 ----
    try:
        out["rxdata"] = write_aide_to_rxdata(game_dir, version=version,
                                             emit=emit)
    except Exception as e:                              # noqa: BLE001
        say(f"[方式七] ⚠ 写 PluginScripts.rxdata 失败：{e}")
    try:
        out["norecompile"] = disable_plugin_recompile(game_dir, emit=emit)
    except (OSError, RuntimeError) as e:
        say(f"[方式七] ⚠ 关插件重编译失败：{e}")

    # ---- ⑦ 给「依赖别的插件的调用」加 defined? 保护（防 $DEBUG 下崩） ----
    try:
        out["guarded"] = guard_known_plugin_deps(game_dir, emit=emit)
    except (OSError, RuntimeError) as e:
        out["guarded"] = 0
        say(f"[方式七] ⚠ 加依赖保护失败：{e}")

    # ---- ⑧ 顺手把 rxdata 里的加载顺序摆正（使用方挪到提供方之后） ----
    try:
        out["reordered"] = fix_plugin_load_order(game_dir, emit=emit)
    except Exception as e:                              # noqa: BLE001
        out["reordered"] = 0
        say(f"[方式七] ⚠ 调整插件顺序失败：{e}")

    say(f"[方式七] ✔ 改名覆盖 {out['replaced']} 个函数（补定义 {out['added']}）"
        f"｜注册 T 键 {out['keyed']} 处｜改调用 {out['renamed']} 处"
        f"｜改选项名 {out['relabeled']} 处｜保留旧名 {out['compat']} 处"
        f"｜删$DEBUG条件 {out['stripped']} 处｜注入脚本 {out['injected']} 个"
        + (f"｜修回误改名 {out['repaired']} 处" if out.get("repaired") else "")
        + (f"｜rxdata {'已写' if (out['rxdata'] or {}).get('ok') else '跳过'}"
           if out["rxdata"] else "")
        + (f"｜关重编译 {out['norecompile']} 处" if out["norecompile"] else "")
        + (f"｜依赖保护 {out['guarded']} 处" if out.get("guarded") else "")
        + (f"｜调顺序 {out['reordered']} 条" if out.get("reordered") else ""))
    return out
