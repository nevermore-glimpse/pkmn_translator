# -*- coding: utf-8 -*-
"""
引擎级工具：基准脚本覆盖、对比报告、多种「开启 DEBUG」方式。

面向同人游戏的日常需求，三块：

  ① 基准脚本覆盖
     把官方同版本引擎里某几个脚本（默认是 debug 菜单定义）**整份替换**掉
     游戏里对应的那份。改前提醒风险、先备份；支持把英文菜单名/说明替换成
     随工具内置的中文（见 scripts/essentials_src/debug_menu_zh.json）。
     ★ 另有 `overwrite_scene_map()`：「用基准覆盖地图更新」—— 只把
       **Scene_Map** 整份盖回官方版（不翻译），给下面方式②③④铺路。

  ② 对比报告 / 合并编辑
     体检结果落盘到 <工具目录>/comparation/<游戏名>.json；
     报告页按「脚本 → 函数」列出基准与目标的差异，可逐行编辑后应用。

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

依赖：game_scripts（脚本读）、essentials_base（体检基准）、engine_src、
      config。
"""
import io
import json
import os
import re
import shutil
import time

import config
import engine_src
import game_scripts as GS
from logger import get_logger

log = get_logger("engine_tools")

# 基准脚本存放目录名（随工具分发）
SRC_DIR_NAME = os.path.join("scripts", "essentials_src")
# 对比报告目录（工具目录下）
REPORT_DIR_NAME = "comparation"
# 覆盖时的备份标记
BAK_MARK = ".pkmn-overwrite-"


# ================================================================
# ① 基准脚本覆盖
# ================================================================
def debug_menu_rel_files(version):
    """某版本官方引擎里 debug 菜单定义脚本的**相对路径**列表。"""
    return engine_src.debug_menu_files(version)


def find_game_script(game_dir, name):
    """
    在游戏脚本里按**脚本名**找一份 → {mode, key, path, name, text}。

    ★ 优先解包 .rb（有的话），否则 Scripts.rxdata 条目；两者都有取 .rb。
    ★ 找不到返回 None。
    """
    want = re.sub(r"[^0-9a-z]+", "", str(name).lower())
    hits = []
    for mode, key, path, sname, text in GS.iter_named_scripts(game_dir,
                                                             both=True):
        if re.sub(r"[^0-9a-z]+", "", str(sname).lower()) == want:
            hits.append({"mode": mode, "key": key, "path": path,
                         "name": sname, "text": text})
    if not hits:
        return None
    hits.sort(key=lambda h: 0 if h["mode"] == "file" else 1)
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
            #   （引擎真正读的是 Scripts.rxdata；解包的游戏写 Data/Scripts/*.rb）
            try:
                if cp["mode"] == "rxdata":
                    _backup(cp["path"], emit=emit)
                    GS.add_rxdata_script(cp["path"], cp["title"], text)
                    rep["backups"].append(cp["path"])
                else:
                    # 解包形态：文件本来就不存在，没有「原文件」要备份
                    GS.add_script_file(game_dir, sname, text)
            except (OSError, RuntimeError) as e:
                rep["reason"] = f"新建「{label}」失败：{e}"
                say(f"[覆盖] ✘ {rep['reason']}")
                return rep
            rep["written"].append(label)
            rep["created"] += 1
            say(f"[覆盖] ⊕ 游戏里没有「{label}」，已按基准**新建**一个"
                f"（{'追加进 Scripts.rxdata（排在 Main 之前）'
                   if cp['mode'] == 'rxdata' else '写入 Data/Scripts'}）")
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


def _write_script(tgt, text, emit=None):
    """把 text 写进目标脚本（.rb 文件或 rxdata 条目），先备份。"""
    path = tgt["path"]
    bak = _backup(path, emit=emit)
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


def _backup(path, emit=None):
    """备份一次（跨运行复用），与 debug_tool 同风格。"""
    ap = os.path.abspath(path)
    if ap in _overwritten:
        return _overwritten[ap]
    old = _find_backup(path)
    if old:
        _overwritten[ap] = old
        return old
    bak = f"{path}{BAK_MARK}{_stamp()}.bak"
    os.rename(path, bak)
    shutil.copyfile(bak, path)
    _overwritten[ap] = bak
    if emit:
        emit(f"[覆盖]   原文件已备份：{os.path.basename(bak)}")
    return bak


def _find_backup(path):
    d = os.path.dirname(os.path.abspath(path))
    pref = os.path.basename(path) + BAK_MARK
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
        try:
            if os.path.exists(target):
                os.remove(target)
            os.rename(bak, target)
            done.append(os.path.basename(target))
            say(f"[覆盖] 已还原 {os.path.basename(target)}")
        except OSError as e:
            say(f"[覆盖] ⚠ 还原 {os.path.basename(target)} 失败：{e}")
    return {"ok": True, "restored": len(done), "files": done}


def _list_backups(game_dir):
    out = []
    for base in (GS.data_dir(game_dir), GS.scripts_dir(game_dir)):
        if not os.path.isdir(base):
            continue
        for dp, _dn, fs in os.walk(base):
            for f in fs:
                if BAK_MARK in f and f.endswith(".bak"):
                    out.append(os.path.join(dp, f))
    return out


# ================================================================
# ② 对比报告
# ================================================================
def report_dir():
    """报告目录（工具目录下 comparation/，没有则建）。"""
    d = os.path.join(config.BASE_DIR, REPORT_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def report_path(game_dir, version=None):
    """
    报告文件名 = **只有游戏名**（不带版本号）。

    ★ 版本号不进文件名：存盘时用的是「基准版本」，而打开时按「游戏自报版本」
      去拼路径，两者常常对不上（老游戏读不到版本号、近似匹配取的基准又不同），
      于是「刚生成完却说没有报告」。只留游戏名就永远不会错位。
    """
    name = os.path.basename(os.path.normpath(game_dir)) or "game"
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    return os.path.join(report_dir(), f"{name}.json")


def find_report(game_dir):
    """
    找这个游戏的报告文件 → 路径 or None。

    兼容旧的带版本名（`<游戏名>_v<版本>.json`）：没有正好同名的就退回
    「同游戏名的旧命名」，取最新改动的那个。
    """
    exact = report_path(game_dir)
    if os.path.isfile(exact):
        return exact
    name = os.path.basename(os.path.normpath(game_dir)) or "game"
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    d = report_dir()
    cands = []
    for f in os.listdir(d):
        if not f.lower().endswith(".json"):
            continue
        stem = f[:-5]
        # `<name>_v16` / `<name>_v21.1` / `<name>_unknown` 都算
        if stem == name or stem.startswith(name + "_v"):
            cands.append(os.path.join(d, f))
    if not cands:
        return None
    cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return cands[0]


def build_report(game_dir, version=None, emit=None, check=None):
    """
    跑体检并把结果落盘到 comparation/<游戏名>.json。
    返回 (报告 dict, 路径)。

    check：可选，已经有体检结果时直接复用（避免同一个检测在日志里报两遍
    总结）。
    """
    import essentials_base as EB
    def say(msg):
        if emit:
            emit(msg)
    ver = version or EB.detect_version(game_dir)
    if check is None:
        check = EB.compare(game_dir, version=ver, emit=emit)
    bver = check.get("baseline") or ver or "unknown"
    items = []
    # 被改 / 缺失 的每个「脚本 → 函数」一条记录（含两边的源码）
    for sname, fname, got, want in (check.get("changed") or []):
        items.append(_item(game_dir, bver, sname, fname, got, want,
                           status="changed"))
    for sname, fname in (check.get("missing") or []):
        items.append(_item(game_dir, bver, sname, fname, "", "",
                           status="missing"))
    rep = {
        "game": os.path.basename(os.path.normpath(game_dir)),
        "game_dir": game_dir,
        "version": ver,
        "baseline": bver,
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {k: check.get(k) for k in
                    ("total", "same", "changed_n", "missing_n", "moved_n",
                     "added_n", "scripts_total", "scripts_missing_n")},
        "items": items,
    }
    p = report_path(game_dir, bver)
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    # ★ 日志精简：只留一行「已写入报告」，明细进报告页逐行对比。
    say(f"[报告] 已写入检测报告 → {p}（{len(items)} 条差异，"
        f"点「检测报告」查看逐行对比）")
    return rep, p


def _norm_eol(text):
    """
    统一行尾为 LF。

    ★ 报告页「逐行对比」必须比内容、不能比行尾 —— 基准（官方源码，LF）
      与目标（游戏 Scripts.rxdata，多为 CRLF）行尾天然不同，不归一化就会
      「每一行都算改动」（红/绿/黄全亮），看着像整个函数被重写。
    """
    if not text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _item(game_dir, bver, sname, fname, got, want, status):
    """构造一条差异记录（含基准/目标源码，供报告页对比）。"""
    return {
        "script": sname, "func": fname, "status": status,
        "edited": False,
        # ★ 两边都归一化行尾，report 页才只标「真正不同的行」
        "base_text": _norm_eol(engine_src.func_source(bver, sname, fname) or ""),
        "goal_text": _norm_eol(_game_func_source(game_dir, sname, fname) or ""),
        "base_fp": want, "goal_fp": got,
    }


def _game_func_source(game_dir, sname, fname):
    import essentials_base as EB
    for _m, _k, _p, name, text in GS.iter_named_scripts(game_dir):
        if EB._norm(name) != EB._norm(sname):
            continue
        src = engine_src.extract_func(text, fname)
        if src:
            return src
    return ""


def load_report(path):
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning("读报告 %s 失败：%s", path, e)
        return None


def apply_report(game_dir, rep, emit=None):
    """
    把报告里「已编辑」的条目写回游戏脚本。
    返回 {"ok", "applied": [脚本→函数], "reason"}。
    """
    def say(msg):
        if emit:
            emit(msg)
    applied = []
    for it in rep.get("items", []):
        if not it.get("edited"):
            continue
        sname, fname = it["script"], it["func"]
        tgt = find_game_script(game_dir, sname)
        if not tgt:
            say(f"[报告] ⚠ 找不到脚本「{sname}」，跳过 {fname}")
            continue
        new_text = engine_src.replace_func(tgt["text"], fname,
                                           it.get("goal_text") or "")
        if new_text is None:
            say(f"[报告] ⚠ 在「{sname}」里没找到函数 {fname}，跳过")
            continue
        try:
            _write_script(tgt, new_text, emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"[报告] ✘ 写入「{sname}」.{fname} 失败：{e}")
            continue
        applied.append(f"{sname} → {fname}")
        say(f"[报告] ✔ 已应用「{sname} → {fname}」")
    return {"ok": True, "applied": applied}


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
)

_MARK = "[pkmn-debug]"
# 「别的功能」留下的标记文案：判断某个带标记的行属不属于当前这一块时，
# 撞上这些就说明已经越界了（见 patch_special_key 的 _marked_run_end）。
_FOREIGN_MARKS = ("方式二", "方式四", "方式五", "方式六", "方式七",
                  "已去掉 $DEBUG", "原条件", "按基准补行", "翻译工具注入")

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
    text = tgt["text"]
    lines = text.split("\n")

    def _marked_run_end(start):
        """
        从 start 起，连续的「带本工具标记」的行到哪儿结束。

        ★ 只收**自己这一块**：撞上别的功能的标记（方式二/四/五/六/七、
          按基准补行…）就停 —— 那些是别的改动留下的，不能被当成 F6 分支
          的一部分删掉。
        """
        if start is None or start < 0:
            return None
        j = start
        while j + 1 < len(lines) and _MARK in lines[j + 1] \
                and not any(m in lines[j + 1] for m in _FOREIGN_MARKS) \
                and j + 1 - start < 8:
            j += 1
        return j

    if f"{_MARK} {tag}" in text:
        # ★ 之前可能注的是**老版本的方式三**（里面还包着 `if !$DEBUG`）。
        #   用户要求现在「直接开启并提示」，所以发现是老的就在原地升级，
        #   而不是当成「已经注入过」直接跳过。
        i0 = next((k for k, x in enumerate(lines)
                   if "Input::F6" in x and _MARK in x), None)
        j0 = _marked_run_end(i0)
        old = lines[i0:j0 + 1] if i0 is not None and j0 is not None else []
        if not any("if !$DEBUG" in x for x in old):
            say(f"{head} · {tag}已经注入过了，跳过")
            return {"ok": True, "script": "Scene_Map", "added": False,
                    "mode": mode}
        lines[i0:j0 + 1] = _f6_block(
            lines[i0], menu, tag,
            is_elsif=lines[i0].lstrip().startswith("elsif"))
        try:
            _write_script(tgt, "\n".join(lines), emit=emit)
        except (OSError, RuntimeError) as e:
            say(f"{head} ✘ 升级老注入失败：{e}")
            return {"ok": False, "reason": str(e)}
        say(f"{head} ✔ 发现以前注入的 F6 分支里还包着 `if !$DEBUG`，"
            "已原地升级成「直接开启并提示」")
        return {"ok": True, "script": "Scene_Map", "added": True,
                "mode": mode, "upgraded": True}

    # 另一个 F6 方式已经注过的话提醒一下（两种方式都是按 F6，会互相遮住）
    other = "方式四：F6 键打开调试菜单" if not menu else "方式三：F6 键开启调试模式"
    if f"{_MARK} {other}" in text:
        say(f"{head} · ⚠ 脚本里已经有「{other}」了 —— 两个 F6 分支会同时存在，"
            "按 F6 只会命中前面那个。想换方式先用「还原」再重开。")

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
    new = "\n".join(lines[:anchor] + body + lines[anchor:])
    try:
        _write_script(tgt, new, emit=emit)
    except (OSError, RuntimeError) as e:
        say(f"{head} ✘ 写入失败：{e}")
        return {"ok": False, "reason": str(e)}
    what = "直接打开调试菜单" if menu else "直接开启 $DEBUG 并提示"
    say(f"{head} ✔ 已在 Scene_Map 注入 F6 键（{what}）"
        f"（{'elsif 分支' if is_elsif else '独立 if 块'}，在 F9 那段之前）")
    return {"ok": True, "script": "Scene_Map", "added": True, "mode": mode,
            "branch": "elsif" if is_elsif else "if"}


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
        say("[除虫喷雾] · 游戏里没找到带 pbRepel 的脚本"
            "（试过 Item_Effects / PItem_ItemEffects / PokemonItemEffects）")
        return {"ok": False, "reason": "找不到道具效果脚本"}
    m = re.search(r"^([ \t]*)def\s+pbRepel\b.*$", tgt["text"], re.M)
    if not m:
        say("[除虫喷雾] · 道具效果脚本里没有 pbRepel（版本不符？）")
        return {"ok": False, "reason": "没找到 pbRepel 函数"}
    indent = re.search(r"^([ \t]*)", m.group(0)).group(1)
    pad = indent + "  "
    ok_val = _repel_ok_value(tgt["text"], version)
    if mode == "repel":
        body = [
            f'if !$DEBUG  # {_MARK} 方式五：除虫喷雾开启调试模式',
            f'  $DEBUG = true  # {_MARK}',
            f'  pbMessage("调试模式已开启！")  # {_MARK}',
            f'end  # {_MARK}',
        ]
    else:
        body = [
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
    lines = tgt["text"].split("\n")
    i = tgt["text"].count("\n", 0, m.start())
    eol = "\r" if lines[i].endswith("\r") else ""
    new = (lines[:i + 1] + [pad + x + eol for x in body] + lines[i + 1:])
    new_text = "\n".join(new)
    try:
        _write_script(tgt, new_text, emit=emit)
    except (OSError, RuntimeError) as e:
        say(f"[除虫喷雾] ✘ 写入失败：{e}")
        return {"ok": False, "reason": str(e)}
    say(f"[除虫喷雾] ✔ 已在「{tgt['name']}」的 pbRepel 注入"
        f"（{'方式五' if mode == 'repel' else '方式六'}）")
    return {"ok": True, "script": tgt["name"], "mode": mode}


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
