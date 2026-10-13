# -*- coding: utf-8 -*-
"""
调试启动器生成（生成「调试模式启动.py / .bat」，双击即以调试模式进游戏）。

不改游戏本体、不动存档，加密打包（单 exe）的游戏也能用。两种运行时：

  ① RGSS 引擎（v16–v18）—— 内存补丁：启动后定位进程内 RGSS 引导串
     `$RGSS_SCRIPTS = load_data`，替换成 `eval(File.read("hook.rb"))`，钩子设
     `$DEBUG = true`、复刻原引导逻辑、屏蔽 `pbCompiler`（打包版磁盘没有 PBS）。
     补丁只在内存，关游戏即失效。

  ② mkxp-z 引擎（v19–v21.1）—— 命令行参数 `Game.exe debug`（引擎原生把
     $DEBUG/$TEST 置真），再于游戏目录 mkxp.json 挂一个 preload 脚本兜底。

★ 补齐数据方案（应对 $DEBUG 触发的全量重编译）：
  开 $DEBUG 后 Essentials 的 `Compiler.main` 会全量重编译，需要 `PBS/*.txt`
  与 `Data/*.dat`；打包版两者都没有 → 满屏 `Errno::ENOENT`。本工具不屏蔽编译，
  而是把缺的文件补齐，并让 `Data/*.dat` 的 mtime 远晚于 `pbs/*.txt`，使
  `mustCompile` 判定不成立。
  补的不是空文件（`GameData.load_all` 会 Marshal.load 每一个 .dat，空文件会在
  那一步炸掉），而是 `mini_data` 生成的**最小可用真数据**——结构照各版本
  `GameData::*` 的字段来写，内容只放几条例项，整套不到 20KB。
  （此为**测试功能**，故菜单里该项带「(测试)」后缀。）

生成物（都在游戏目录）：
  · 调试模式启动.py        —— 核心启动器
  · 调试模式启动.bat       —— 双击用（自动找 python / py）
  · _pkmn_debug_preload.rb —— mkxp-z 的 preload 脚本（仅 mkxp-z）
  · _pkmn_debug_ok.txt     —— 运行时自检标记
  · _pkmn_mini_data.json   —— 本次补了哪些文件（清理时用）
  · Data/*.dat、*.rxdata   —— 最小可用数据（只补缺失项）
  · pbs/*.txt              —— 最小可编译 PBS（只补缺失项）

依赖：logger、mini_data。
"""
import io
import os
import re
import shutil
import time

import mini_data

from logger import get_logger

log = get_logger("launcher")

PY_NAME = "调试模式启动.py"
BAT_NAME = "调试模式启动.bat"
MKXP_PRELOAD = "_pkmn_debug_preload.rb"
RGSS_HOOK = "_pkmn_debug_hook.rb"       # 运行时写到临时目录

# ★ 独立 exe 版（推荐）：**一个固定的 exe**（自带Python，玩家机器不用装），
#   每个游戏的差异全写在游戏目录的 `_pkmn_debug_launcher.json` 里。
LAUNCHER_EXE = "宝可梦调试启动器.exe"
LAUNCHER_CFG = "_pkmn_debug_launcher.json"

RUNTIME_LABEL = {
    "rgss": "RGSS（v16–v18）",
    "mkxp": "mkxp-z（v19–v21.1）",
    "unknown": "未知",
}

MARKER_NAME = "_pkmn_debug_ok.txt"

# ================================================================
# Essentials 编译所需文件清单（占位文件）
# ================================================================
# 取自 Essentials 各版 `Compiler.main` 的 dataFiles / textFiles
# （v19 / v19.1 / v20 / v20.1 / v21 的并集，任一版本都能覆盖）。
PLACEHOLDER_DATS = (
    "abilities.dat", "berry_plants.dat", "encounters.dat", "form2species.dat",
    "items.dat", "map_connections.dat", "map_metadata.dat", "metadata.dat",
    "moves.dat", "phone.dat", "player_metadata.dat", "regional_dexes.dat",
    "ribbons.dat", "shadow_movesets.dat", "shadow_pokemon.dat", "species.dat",
    "species_eggmoves.dat", "species_evolutions.dat", "species_metrics.dat",
    "species_movesets.dat", "tm.dat", "town_map.dat", "trainer_lists.dat",
    "trainer_types.dat", "trainers.dat", "types.dat",
)
PLACEHOLDER_TXTS = (
    "abilities.txt", "battle_facility_lists.txt", "berry_plants.txt",
    "berryplants.txt", "connections.txt", "encounters.txt", "items.txt",
    "map_connections.txt", "map_metadata.txt", "metadata.txt", "moves.txt",
    "phone.txt", "pokemon.txt", "pokemon_forms.txt", "pokemonforms.txt",
    "pokemon_metrics.txt", "regional_dexes.txt", "regionaldexes.txt",
    "ribbons.txt", "shadow_moves.txt", "shadow_pokemon.txt", "shadowmoves.txt",
    "town_map.txt", "townmap.txt", "trainer_lists.txt", "trainerlists.txt",
    "trainer_types.txt", "trainertypes.txt", "trainers.txt", "types.txt",
)

# .dat 比 .txt 晚这么多秒（确保「不触发编译」）
_PLACEHOLDER_SKEW_SEC = 365 * 24 * 3600

# 明显不是主程序的 exe（编辑器 / 工具 / 备份）
_NOT_MAIN_EXE = ("editor", "animmaker", "extendtext", "townmapgen",
                 "旧", "old", "备份", "bak", "debug", "更新", "update")

# mkxp-z 随行运行库特征
_MKXP_DLL_RE = re.compile(r"^(?:x64-)?msvcrt-ruby\d*\w*\.dll$", re.I)
_MKXP_DLL_RE2 = re.compile(r"^(?:x64-|x86-)?(?:msvcrt|vcruntime)-ruby.*\.dll$", re.I)

# 超过此大小视为加密单文件壳：壳内字符串不可信，静态不下结论，改由运行时判定。
_BIG_EXE_BYTES = 256 * 1024 * 1024

# 小 exe 里 `mkxp` 至少出现这么多次才静态判 mkxp-z（避免偶发误判）。
_MKXP_MIN_HITS = 3


def detect_runtime(game_dir, exe=None):
    """
    判断运行时："mkxp" / "rgss" / "unknown"。

    exe 给了就用它，否则自动挑。判据由强到弱：
      ① 目录有 mkxp.json 或 msvcrt-ruby*.dll → mkxp；
      ② 主 exe 内含 `mkxp` 字样（够多）或 sdl2+ruby（超出 _BIG_EXE_BYTES 不算）；
      ③ 目录有 RGSSxxx.dll 或 Game.ini 的 Library= 指向 RGSS → rgss；
      ④ 主 exe 头部含 `rgss` 字样 → rgss。

    ★ 只按 Game.ini 判会翻车：移植/打包过的游戏常留旧 Game.ini；
      mkxp 证据一旦出现即优先。超大加密壳里的库名会让 `mkxp` 偶然命中，
      故 >_BIG_EXE_BYTES 时不据壳内字符串下结论，交运行时判定。
    """
    if not game_dir or not os.path.isdir(game_dir):
        return "unknown"
    low_names = [n.lower() for n in os.listdir(game_dir)]

    # ① mkxp-z 随行运行库
    if "mkxp.json" in low_names:
        return "mkxp"
    if any(_MKXP_DLL_RE.match(n) or _MKXP_DLL_RE2.match(n) for n in low_names):
        return "mkxp"

    # ② 主 exe 内含 mkxp 字样
    exe = exe if (exe and os.path.isfile(exe)) else _find_exe(game_dir)
    if exe:
        try:
            size = os.path.getsize(exe)
        except OSError:
            size = 0
        try:
            with open(exe, "rb") as f:
                low = f.read().lower()
            n_mkxp = low.count(b"mkxp")
            if (n_mkxp >= _MKXP_MIN_HITS or (b"sdl2" in low and b"ruby" in low)) \
                    and size < _BIG_EXE_BYTES:
                return "mkxp"
        except OSError:
            pass

    # ③ RGSS
    if any(n.startswith("rgss") and n.endswith(".dll") for n in low_names):
        return "rgss"
    ini = os.path.join(game_dir, "Game.ini")
    if os.path.isfile(ini):
        try:
            with io.open(ini, "r", encoding="latin-1", errors="replace") as f:
                if re.search(r"Library\s*=\s*RGSS", f.read(), re.I):
                    return "rgss"
        except OSError:
            pass

    # ④ 主 exe 头部含 rgss
    if exe:
        try:
            with open(exe, "rb") as f:
                if b"rgss" in f.read(4 << 20).lower():
                    return "rgss"
        except OSError:
            pass
    return "unknown"


def _find_exe(game_dir):
    """
    找游戏主 exe：优先 `Game.exe`；否则在所有 *.exe 里排除编辑器/工具/备份，
    取最大的那个。全被排除时退回最大的 exe。
    """
    cands = []
    try:
        for n in os.listdir(game_dir):
            if not n.lower().endswith(".exe"):
                continue
            p = os.path.join(game_dir, n)
            if n.lower() == "game.exe":
                return p
            if any(k in n.lower() for k in _NOT_MAIN_EXE):
                continue
            try:
                cands.append((os.path.getsize(p), p))
            except OSError:
                pass
    except OSError:
        return None
    if cands:
        cands.sort(reverse=True)
        return cands[0][1]
    try:
        allx = [(os.path.getsize(os.path.join(game_dir, n)),
                 os.path.join(game_dir, n))
                for n in os.listdir(game_dir) if n.lower().endswith(".exe")]
        if allx:
            allx.sort(reverse=True)
            return allx[0][1]
    except OSError:
        pass
    return None


# ================================================================
# 占位文件：补齐 Data/*.dat 与 pbs/*.txt（避免 $DEBUG 触发全量重编译）
# ================================================================
def ensure_placeholders(game_dir, say):
    r"""
    确保 `Data/`、`pbs/` 存在，并补齐全套空占位文件。

    ★ 原理：`Compiler.main` 在 $DEBUG 时全量重编译，判据
      `mustCompile |= (latestTextTime >= latestDataTime)`。只要 `Data/*.dat`
      比 `pbs/*.txt` 新，就不触发；补齐所有会被检查的文件，就不会 ENOENT。

    · 已存在的目录/文件**原样保留**，只补缺失项（不覆盖）；
    · 已存在的「空」`.dat` 会被提到安全的未来时间；
    · **关键**：基准时间取「现有全部 `.txt` 的最新 mtime」再加一天 ——
      否若有游戏只剩 `pbs/`（作者删了 `Data/`）且 `.txt` 是近期时间，
      我们只按固定 2000 年补 `.dat` 仍会比 `.txt` 旧 → 照样触发重编译。

    返回 {"data_created","pbs_created","dat_new","txt_new","dat_fixed","txt_fixed"}。
    """
    res = {"data_created": False, "pbs_created": False,
           "dat_new": 0, "txt_new": 0, "dat_fixed": 0, "txt_fixed": 0}
    data_dir = os.path.join(game_dir, "Data")
    pbs_dir = os.path.join(game_dir, "pbs")

    for d, flag in ((data_dir, "data_created"), (pbs_dir, "pbs_created")):
        if not os.path.isdir(d):
            try:
                os.makedirs(d, exist_ok=True)
                res[flag] = True
            except OSError as e:
                say("[启动器] ⚠ 建目录失败：%s" % e)
                return res

    # 基准：pbs 的 `.txt` 定在 2000-01-01；Data 的 `.dat` 取「最新 .txt + 1 天」，
    # 但至少不早于 2000-01-01 + 一年（确保恒新于我们自己写的 .txt）。
    t_txt = time.mktime((2000, 1, 1, 0, 0, 0, 0, 0, -1))
    latest_txt = t_txt
    for nm in os.listdir(pbs_dir):
        if nm.lower().endswith(".txt"):
            try:
                latest_txt = max(latest_txt, os.path.getmtime(
                    os.path.join(pbs_dir, nm)))
            except OSError:
                pass
    t_dat = max(t_txt + _PLACEHOLDER_SKEW_SEC, latest_txt + 24 * 3600)

    for nm in PLACEHOLDER_TXTS:
        p = os.path.join(pbs_dir, nm)
        if not os.path.isfile(p):
            try:
                open(p, "wb").close()
                os.utime(p, (t_txt, t_txt))
                res["txt_new"] += 1
            except OSError:
                pass
    for nm in PLACEHOLDER_DATS:
        p = os.path.join(data_dir, nm)
        if not os.path.isfile(p):
            try:
                open(p, "wb").close()
                os.utime(p, (t_dat, t_dat))
                res["dat_new"] += 1
            except OSError:
                pass
        else:
            # 兜底：把「比 .txt 旧」的空 .dat 提到基准时间（不碰有内容的数据）
            try:
                if os.path.getsize(p) == 0 and os.path.getmtime(p) < t_dat:
                    os.utime(p, (t_dat, t_dat))
                    res["dat_fixed"] += 1
            except OSError:
                pass

    if res["dat_new"] or res["txt_new"]:
        say("[启动器] ✔ 占位文件：Data/*.dat 新建 %d、pbs/*.txt 新建 %d"
            % (res["dat_new"], res["txt_new"]))
    return res


def cleanup_placeholders(game_dir):
    """
    删除本工具生成的占位文件与目录（只删「空文件」，不动用户数据）。

    · `.dat`：大小 0 且 mtime >= 2000-01-02 的删；有内容的一律保留。
    · `.txt`：大小 0 且 mtime <= 2000-01-01 的删。
    · `Data/`、`pbs/` 若删完为空则一并删掉。

    返回删除的文件数。
    """
    t_txt = time.mktime((2000, 1, 1, 0, 0, 0, 0, 0, -1))
    t_dat = t_txt + _PLACEHOLDER_SKEW_SEC
    removed = 0
    for sub, names, t_ref, older in (
            ("Data", PLACEHOLDER_DATS, t_dat, False),
            ("pbs", PLACEHOLDER_TXTS, t_txt, True)):
        d = os.path.join(game_dir, sub)
        if not os.path.isdir(d):
            continue
        for nm in names:
            p = os.path.join(d, nm)
            try:
                if os.path.getsize(p) == 0:
                    mt = os.path.getmtime(p)
                    if (mt <= t_ref) if older else (mt >= t_ref):
                        os.remove(p)
                        removed += 1
            except OSError:
                pass
        try:
            if not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass
    return removed


# ================================================================
# 生成启动器
# ================================================================
def make_debug_launcher(game_dir, version=None, emit=None, exe=None):
    """
    在 game_dir 生成调试启动器。

    exe 给了就用它当主程序（用户手选），否则自动挑。
    返回 {"ok","runtime","files","main","exe","reason","note","fallback"}。
    """
    def say(msg):
        if emit:
            emit(msg)

    if not game_dir or not os.path.isdir(game_dir):
        return {"ok": False, "reason": "游戏目录不存在", "files": []}

    exe_pick = exe if (exe and os.path.isfile(exe)) else None
    auto = _find_exe(game_dir)
    if exe_pick and not any(k in os.path.basename(exe_pick).lower()
                            for k in _NOT_MAIN_EXE):
        exe = exe_pick
    else:
        exe = auto or exe_pick
    if not exe:
        return {"ok": False, "reason": "游戏目录里找不到 *.exe", "files": []}

    kind = detect_runtime(game_dir, exe=exe)
    was_unknown = (kind == "unknown")
    if was_unknown:
        say("[启动器] 静态认不出运行库 → 运行时探测（默认按 RGSS）")
        kind = "rgss"
    say("[启动器] 运行库：%s" % RUNTIME_LABEL.get(kind, kind))
    say("[启动器] 主程序：%s" % os.path.basename(exe))

    # 补齐 Data / PBS：两种引擎都补（RGSS 用不到但无害）
    # ★ 写的是最小可用真数据，不是空占位（空 .dat 会在 GameData.load_all 炸掉）
    md = mini_data.ensure_minimal_data(game_dir, version=version, say=say)

    preload_used = False
    if kind == "mkxp":
        ok, why = _install_mkxp_preload(game_dir, say)
        if ok:
            preload_used = True
        else:
            say("[启动器] · 挂 preloadScript 失败：%s" % why)
            say("[启动器] · 改用运行时探测（启动后认出 mkxp-z 会用 debug 参数）")
            kind = "rgss"
    elif was_unknown:
        # 静态认不出 → 先试挂 preload（对非 mkxp 无害），再走运行时探测
        ok, _ = _install_mkxp_preload(game_dir, say, quiet=True)
        preload_used = ok

    # ---------- 独立 exe 版（首选）：固定 exe + 随游戏的 json 配置 ----------
    exe_ok, exe_why = _deploy_launcher_exe(game_dir, exe, kind, say)

    # ---------- Python 版（没打成 exe 时的兜底）----------
    py_src = _render_py(game_dir, exe, kind)
    py_path = os.path.join(game_dir, PY_NAME)
    with io.open(py_path, "w", encoding="utf-8", newline="") as f:
        f.write(py_src)
    say("[启动器] ✔ 已写 %s（需要电脑上有 Python 才能跑）" % PY_NAME)

    bat_path = os.path.join(game_dir, BAT_NAME)
    with io.open(bat_path, "w", encoding="ascii", newline=chr(13) + chr(10),
                 errors="replace") as f:
        f.write(_render_bat())
    say("[启动器] ✔ 已写 %s" % BAT_NAME)

    files = [LAUNCHER_CFG] if exe_ok else []
    files += [PY_NAME, BAT_NAME]
    if preload_used:
        files.append(MKXP_PRELOAD)
    n_new = md.get("dat_new", 0) + md.get("rx_new", 0) + md.get("txt_new", 0)
    if n_new:
        files.append("Data/*.dat + *.rxdata、pbs/*.txt（最小可用数据 ×%d）"
                     % n_new)

    note = ("已挂 preload 脚本并补齐最小数据（%s 档）；开调试不会触发全量重编译。"
            % (md.get("family") or "?") if preload_used else
            "已补齐最小数据（%s 档）；运行时按实际加载的 dll 打补丁。"
            % (md.get("family") or "?"))

    main_file = LAUNCHER_EXE if exe_ok else BAT_NAME
    if exe_ok:
        note = ("双击 **%s** 进游戏（自带 Python，**电脑上不用装 Python**）；"
                % LAUNCHER_EXE) + note
    else:
        note += "（没找到打包好的 %s，只能用 .py/.bat 启动，"                 "需要电脑上装有 Python）" % LAUNCHER_EXE

    log.info("调试启动器已生成：%s（%s，exe=%s）", game_dir, kind, exe_ok)
    return {"ok": True, "runtime": kind, "files": files, "main": main_file,
            "exe": os.path.basename(exe), "reason": "", "note": note,
            "has_exe": exe_ok, "fallback": (kind == "rgss")}


# ================================================================
# 独立 exe 版：把「固定 exe」部署到游戏目录 + 写该游戏的配置
# ================================================================
def launcher_exe_source():
    """工具目录里打包好的启动器 exe 路径（没打包返回 ""）。

    找的地方（按优先级）：
      ① 项目根 `宝可梦调试启动器.exe`（打包脚本的默认输出）；
      ② `dist/宝可梦调试启动器.exe`；
      ③ `launcher_exe/宝可梦调试启动器.exe`（PyInstaller 的 workpath 之外
         手动指定的位置）。
    ★ 打包成主程序后（--onefile），`sys.executable` 是主 exe，
      `config.BASE_DIR` 是解包出来的临时目录 —— 那种情况下 exe 作为
      `--add-data` 一起分发，用 `_frozen_exe_data()` 找。
    """
    import sys
    cands = []
    try:
        import config
        base = config.BASE_DIR
    except Exception:                                        # noqa: BLE001
        base = os.path.dirname(os.path.abspath(__file__))
    here = os.path.dirname(os.path.abspath(__file__))
    for b in {base, here, os.path.dirname(here)}:
        if not b:
            continue
        cands += [os.path.join(b, LAUNCHER_EXE),
                  os.path.join(b, "dist", LAUNCHER_EXE),
                  os.path.join(b, "launcher_exe", LAUNCHER_EXE)]
    # PyInstaller onefile：作为数据文件被打进去，解包目录里有
    try:
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            cands += [os.path.join(meipass, LAUNCHER_EXE),
                      os.path.join(meipass, "launcher", LAUNCHER_EXE)]
    except Exception:                                        # noqa: BLE001
        pass
    for c in cands:
        try:
            if os.path.isfile(c) and os.path.getsize(c) > 100_000:
                return c
        except OSError:
            continue
    return ""


def _deploy_launcher_exe(game_dir, exe, kind, say):
    """
    把固定启动器 exe 复制进游戏目录，并写该游戏专属的 json 配置。
    返回 (ok, why)。

    ★ exe 是**所有游戏共用同一份**；每个游戏的差异（游戏 exe 名、运行库、
      注入钩子…）全在 `_pkmn_debug_launcher.json` 里。用户换游戏只要重新
      生成一次配置，不用重新打包。
    """
    src = launcher_exe_source()
    if not src:
        say("[启动器] · 没找到打包好的 %s（先跑一次「打包调试启动器.bat」）"
            % LAUNCHER_EXE)
        return False, "没有打包好的启动器 exe"
    try:
        import launcher_exe as LE
    except Exception as e:                                   # noqa: BLE001
        return False, "launcher_exe 模块不可用：%s" % e

    cfg = LE.default_config(game_dir, os.path.basename(exe),
                            runtime=kind)
    cfg["marker"] = MARKER_NAME
    cfg["engine_src"] = kind
    cfg["generated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    # mkxp 走 preload 时，把 preload 文件名也记下来（便于排查）
    cfg["mkxp_preload"] = MKXP_PRELOAD if kind == "mkxp" else ""
    try:
        cfg_path = LE.write_config(game_dir, cfg)
    except OSError as e:
        say("[启动器] ⚠ 写配置失败：%s（改用 .py 启动器）" % e)
        return False, "写配置失败：%s" % e

    dst = os.path.join(game_dir, LAUNCHER_EXE)
    try:
        if os.path.isfile(dst):
            same = (os.path.getsize(dst) == os.path.getsize(src))
        else:
            same = False
        if not same:
            shutil.copyfile(src, dst)
    except OSError as e:
        say("[启动器] ⚠ 复制 exe 失败：%s（改用 .py 启动器）" % e)
        return False, "复制 exe 失败：%s" % e

    say("[启动器] ✔ 已部署 %s（自带 Python，电脑上不用装）" % LAUNCHER_EXE)
    say("[启动器] ✔ 已写 %s（这个游戏自己的设置）" % LAUNCHER_CFG)
    log.info("启动器 exe 已部署：%s ← %s", game_dir, src)
    _ = cfg_path
    return True, ""


def remove_debug_launcher(game_dir):
    """删除本工具生成的启动器文件。返回删除的文件名列表。"""
    out = []
    for n in (LAUNCHER_EXE, LAUNCHER_CFG, PY_NAME, BAT_NAME,
              MKXP_PRELOAD, MARKER_NAME):
        if _try_remove(os.path.join(game_dir, n)):
            out.append(n)
    return out


def _install_mkxp_preload(game_dir, say, quiet=False):
    """
    给 mkxp-z 写 preload 脚本并挂到**游戏目录** mkxp.json 的 preloadScript。

    mkxp-z 读的就是「当前工作目录（= 游戏目录）的 mkxp.json」，没有就新建。
    quiet=True：不输出日志。

    返回 (ok, why)。
    """
    def _say(msg):
        if not quiet:
            say(msg)

    jp = os.path.join(game_dir, "mkxp.json")
    rb_path = os.path.join(game_dir, MKXP_PRELOAD)
    try:
        with io.open(rb_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(_MKXP_PRELOAD_RB)
    except OSError as e:
        return False, "写 preload 脚本失败：%s" % e

    has_ext = os.path.isfile(jp)
    txt = ""
    if has_ext:
        try:
            with io.open(jp, "r", encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except OSError as e:
            return False, "读 mkxp.json 失败：%s" % e
    if _mkxp_has_preload(txt):
        _say("[启动器] · mkxp.json 已有 preloadScript，跳过")
        return True, ""

    if has_ext and txt.strip() and txt.strip() not in ("{}", "{ }"):
        try:
            shutil.copyfile(jp, jp + ".pkmn-debug-%s.bak" % _stamp())
        except OSError:
            pass

    fwd = MKXP_PRELOAD.replace("\\", "/")
    if not has_ext:
        body = ('{\n'
                '    // 由「宝可梦同人工具」创建：调试模式用，可随时删除。\n'
                '    "preloadScript": ["%s"]\n'
                '}\n' % fwd)
    else:
        body = _inject_mkxp_preload(txt, fwd)
    try:
        with io.open(jp, "w", encoding="utf-8", newline="") as f:
            f.write(body)
    except OSError as e:
        return False, "写 mkxp.json 失败：%s" % e
    _say("[启动器] ✔ 已挂 preloadScript（%s）"
         % ("新建 mkxp.json" if not has_ext else "合并进 mkxp.json"))
    return True, ""


def _mkxp_has_preload(txt):
    """mkxp.json 里有没有生效的 preloadScript（忽略 // 注释行）。"""
    for line in txt.split("\n"):
        s = line.strip()
        if s.startswith("//"):
            continue
        if "preloadScript" in s:
            return True
    return False


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"


def _try_remove(path):
    """安静地删一个文件（不存在/被占用都当没事）。"""
    try:
        if path and os.path.isfile(path):
            os.remove(path)
            return True
    except OSError:
        pass
    return False


def _inject_mkxp_preload(txt, rb_fwd):
    """
    把 preloadScript 插进一段 mkxp.json 文本，返回新文本。
    mkxp.json 走 JSON5（允许注释与尾随逗号），仍尽量产出干净 JSON。
    """
    if txt.strip() in ("", "{}"):
        txt = "{}"
    # 找第一个不在 // 注释行里的 `{`
    idx, off = -1, 0
    for line in txt.split("\n"):
        if not line.strip().startswith("//"):
            j = line.find("{")
            if j >= 0:
                idx = off + j
                break
        off += len(line) + 1
    if idx < 0:
        return '{\n    "preloadScript": ["%s"]\n}\n' % rb_fwd
    rest = txt[idx + 1:]
    tail = "," if rest.strip().rstrip().rstrip("}").strip() else ""
    return txt[:idx + 1] + '\n    "preloadScript": ["%s"]%s' % (rb_fwd, tail) + rest


# ================================================================
# mkxp-z preload 脚本内容
# ================================================================
# 作用：把 $DEBUG / $TEST 置真（+ 后台维持），配合 `Game.exe debug`。
# 不屏蔽 Compiler —— 改用「补齐占位文件」让编译不触发。
_MKXP_PRELOAD_RB = r'''# pkmn-debug preload（由「宝可梦同人工具」生成，可随时删除）
# 作用：确保 $DEBUG / $TEST 为真；后台线程防止被 Settings 覆盖回去。
begin
  $DEBUG = true
  $TEST  = true if defined?($TEST)
rescue Exception
end

if defined?(Thread)
  Thread.new do
    loop do
      begin
        $DEBUG = true if $DEBUG != true
        $TEST  = true if defined?($TEST) && $TEST != true
      rescue Exception
      end
      sleep 0.2
    end
  end
end
'''
# ================================================================
# 启动器模板
# ================================================================
def _render_bat():
    """
    双击用的 .bat：优先用 python / py 启动同目录的 .py。

    ★ 全 ASCII 内容。.bat 的编码很难两全（GBK 中文 + chcp 65001 会乱码），
      故一个中文都不放：用 `for %%F in ("*.py")` 找到同目录的 .py，
      完全绕开中文文件名的编码坑。
    """
    return (
        "@echo off\r\n"
        "setlocal enabledelayedexpansion\r\n"
        "cd /d \"%~dp0\"\r\n"
        "chcp 65001 >nul 2>nul\r\n"
        "\r\n"
        "rem Find the launcher .py in this folder (there should be exactly one).\r\n"
        "set \"PY=\"\r\n"
        "for %%F in (\"*.py\") do (\r\n"
        "    if not defined PY set \"PY=%%~fF\"\r\n"
        ")\r\n"
        "if not defined PY (\r\n"
        "    echo [ERROR] launcher .py not found in this folder.\r\n"
        "    echo         Keep this .bat next to the generated .py file.\r\n"
        "    pause\r\n"
        "    exit /b 1\r\n"
        ")\r\n"
        "\r\n"
        "where python >nul 2>nul\r\n"
        "if %errorlevel%==0 (\r\n"
        "    python \"!PY!\"\r\n"
        "    goto :end\r\n"
        ")\r\n"
        "where py >nul 2>nul\r\n"
        "if %errorlevel%==0 (\r\n"
        "    py \"!PY!\"\r\n"
        "    goto :end\r\n"
        ")\r\n"
        "\r\n"
        "echo [ERROR] Python 3 not found.\r\n"
        "echo         Install Python 3 (tick \"Add to PATH\") and try again,\r\n"
        "echo         or double-click the generated .py file directly.\r\n"
        "pause\r\n"
        ":end\r\n"
        "endlocal\r\n"
    )


def _render_py(game_dir, exe, kind):
    """
    核心启动器：
      · mkxp（有外部 mkxp.json）→ 直接启动，靠 preloadScript 注入；
      · 其它（RGSS / 认不准的大 exe）→ 运行时探测引擎再打补丁。
    """
    exe_name = os.path.basename(exe)
    body = _py_body_mkxp(exe_name) if kind == "mkxp" else _py_body_rgss(exe_name)
    header = (
        "# -*- coding: utf-8 -*-\n"
        "# 宝可梦同人工具 · 调试模式启动器（自动生成）\n"
        f"# 运行库：{RUNTIME_LABEL.get(kind, '未知')}\n"
        "# 双击本文件（或同目录的「调试模式启动.bat」）即以调试模式进入游戏。\n"
        "# 不改游戏本体、不动存档；不想用了直接删掉生成的文件即可。\n\n"
        "import os\n"
        "import sys\n"
        "import re\n"
        "import time\n"
        "import ctypes\n"
        "import subprocess\n"
        "import tempfile\n"
        "from ctypes import wintypes\n\n"
        f"GAME_DIR = r\"{game_dir}\"\n"
        f"GAME_EXE = r\"{exe_name}\"\n\n\n"
        "def _init_console():\n"
        "    # 控制台按 UTF-8 输出，中文提示不乱码\n"
        "    try:\n"
        "        ctypes.windll.kernel32.SetConsoleOutputCP(65001)\n"
        "    except Exception:\n"
        "        pass\n"
        "    for s in (sys.stdout, sys.stderr):\n"
        "        try:\n"
        "            s.reconfigure(encoding=\"utf-8\", errors=\"replace\")\n"
        "        except Exception:\n"
        "            pass\n\n\n"
        "def log(msg):\n"
        "    try:\n"
        "        print(msg)\n"
        "        sys.stdout.flush()\n"
        "    except Exception:\n"
        "        pass\n\n\n"
    )
    footer = (
        "if __name__ == \"__main__\":\n"
        "    _init_console()\n"
        "    try:\n"
        "        rc = main()\n"
        "    except Exception as e:\n"
        "        log(\"发生异常: %r\" % (e,))\n"
        "        rc = 1\n"
        "    if rc != 0:\n"
        "        try:\n"
        "            input(\"按回车键关闭 ...\")\n"
        "        except Exception:\n"
        "            pass\n"
        "    else:\n"
        "        try:\n"
        "            time.sleep(6)\n"
        "        except Exception:\n"
        "            pass\n"
        "    sys.exit(rc)\n"
    )
    return header + body + "\n" + footer


def _py_body_mkxp(exe_name):
    r"""
    mkxp-z：用**原生命令行参数 `debug`** 启动。

    ★ mkxp-z 的 `config.cpp` 里 `argv[1] == "debug"` → `editor.debug = true`，
      `binding-mri.cpp` 再把 `$DEBUG`（RGSS1）/`$TEST`（VX/VXA）置真。
      这是引擎自带、最稳的开关，不依赖任何配置文件。

    ★ 编译报错：不屏蔽编译，而是靠生成时补齐的 Data/*.dat、pbs/*.txt
      占位文件，使编译判定不触发。
    """
    return r'''
MARKER_NAME = """__MARKER__"""


def main():
    exe_path = os.path.join(GAME_DIR, GAME_EXE)
    if not os.path.isfile(exe_path):
        log("找不到游戏：%s" % exe_path)
        return 2
    marker = os.path.join(GAME_DIR, MARKER_NAME)
    try:
        os.remove(marker)
    except Exception:
        pass

    log("=" * 52)
    log("  调试模式启动器（mkxp-z）")
    log("=" * 52)
    log("启动命令：%s debug" % GAME_EXE)
    subprocess.Popen([exe_path, "debug"], cwd=GAME_DIR)

    for _ in range(40):
        time.sleep(0.5)
        if os.path.exists(marker):
            break
    if os.path.exists(marker):
        log("[OK] 已进入调试模式")
    else:
        log("[i] 未收到自检标记；进游戏后按 F9 验证。")
    log("地图上按 F9 打开调试菜单。")
    return 0
'''.replace("__MARKER__", MARKER_NAME)


def _py_body_rgss(exe_name):
    r"""
    RGSS / 认不准的大 exe：**运行时**看进程实际加载哪个 dll，再决定怎么打补丁。

    ★ 为什么不在生成时静态判引擎：超大 exe（加密单文件壳）里混进的
      `mkxp`/`sdl2` 字符串会让静态判定翻车（实测 2GB 的「极夜永昼」静态像
      mkxp、其实跑的是 RGSS104E.dll）。所以：
        · 轮询进程模块：出现 `rgss*.dll` → RGSS 内存补丁；
          出现 `msvcrt-ruby*.dll` → mkxp-z（改用它原生的 `debug` 参数重启）；
        · 一段时间都没认出来 → 默认按 RGSS 尽力打补丁；
        · 连引导串都找不到 → 再用 `Game.exe debug` 重启一试。
      全程不改游戏文件、不动存档，补丁只在内存、关游戏即失效。
    """
    return r'''
# RGSS 引导代码固定串（RGSS102E/103E/104E.dll 内）
BOOTSTRAP_NEEDLE = b"$RGSS_SCRIPTS = load_data"
# RGSS 运行库名（宽松匹配：rgss 开头 + .dll，兼容日/欧/美版）
RGSS_DLL_RE = re.compile(r"^rgss\d*\w*\.dll$", re.I)
# mkxp-z 的 Ruby 随行库（x64-msvcrt-ruby3xx.dll 之类）
RUBY_DLL_RE = re.compile(r"^(?:x64-|x86-)?(?:msvcrt|vcruntime)-ruby.*\.dll$", re.I)

MARKER_NAME = """__MARKER__"""

# 注入到游戏进程内存的钩子：设 $DEBUG、复刻 RGSS 引导逻辑、屏蔽编译入口。
# 不检查引擎指纹；找不到引导串时按正常模式放行。
HOOK_SOURCE = r"""
$DEBUG = true
begin
  fname = scripts_fname
rescue Exception
  fname = nil
end
if fname.nil? || fname.to_s.empty?
  begin
    ini = File.open("Game.ini", "rb") { |f| f.read }
    fname = ini.scan(/Scripts\s*=\s*(\S+)/).flatten.first.to_s.gsub("\\", "/")
  rescue Exception
    fname = nil
  end
end
fname = "Data/Scripts.rxdata" if fname.nil? || fname.empty?
$RGSS_SCRIPTS = load_data(fname)
$RGSS_SCRIPTS.each { |s| s[3, 0] = Zlib::Inflate.inflate(s[2]) }

patched = 0
$RGSS_SCRIPTS.each do |s|
  code = s[3].to_s
  orig = code.dup
  # (1) Settings 里 `$DEBUG = false` 会盖掉上面的值 -> 改 true
  code = code.sub(/\$DEBUG\s*=\s*false/, "$DEBUG = true")
  # (2) Main 里裸调 pbCompiler（打包版磁盘没有 PBS，会崩）-> 注释
  code = code.sub(/^pbCompiler\s*$/, "# pbCompiler (debug launcher: disabled)")
  # (3) 兜底：pbCompiler 方法体开局 return
  code = code.sub(/def pbCompiler[ \t]*\n/) { "def pbCompiler\n  return\n" }
  if code != orig
    s[3] = code
    patched += 1
  end
end

begin
  _mk = File.join(Dir.pwd, "__MARKER__")
  File.open(_mk, "wb") { |f| f.write("DEBUG=#{$DEBUG.inspect}\npatched=#{patched}\ncount=#{$RGSS_SCRIPTS.size}\n") }
rescue Exception
end
$RGSS_SCRIPTS.size
"""


class ME32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260),
    ]


def _scan_range(h, base, size, needle):
    off = 0
    buf = ctypes.create_string_buffer(1 << 20)
    while off < size:
        chunk = min(1 << 20, size - off)
        rd = ctypes.c_size_t(0)
        if ctypes.windll.kernel32.ReadProcessMemory(
                h, ctypes.c_void_p(base + off), buf, chunk, ctypes.byref(rd)):
            i = buf.raw[:rd.value].find(needle)
            if i != -1:
                return base + off + i
        off += chunk
    return None


def _mods(pid):
    """列出进程已加载模块 [(name, base, size), ...]。"""
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(0x08 | 0x10, pid)
    me = ME32()
    me.dwSize = ctypes.sizeof(ME32)
    out = []
    if k32.Module32First(snap, ctypes.byref(me)):
        while True:
            out.append((me.szModule.decode("mbcs", "replace"),
                        me.modBaseAddr or 0, me.modBaseSize))
            if not k32.Module32Next(snap, ctypes.byref(me)):
                break
    k32.CloseHandle(snap)
    return out


def _find_running(exe_name):
    """游戏是否已在运行（补丁必须在引导代码执行前打）。"""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq " + exe_name, "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL).decode("mbcs", "replace")
        return exe_name.lower() in out.lower()
    except Exception:
        return False


def _launch_debug(exe_path):
    """用 mkxp-z 原生 `debug` 参数重启游戏。"""
    subprocess.Popen([exe_path, "debug"], cwd=GAME_DIR)


def main():
    k32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll
    exe_path = os.path.join(GAME_DIR, GAME_EXE)
    if not os.path.isfile(exe_path):
        log("找不到游戏：%s" % exe_path)
        return 2

    if _find_running(GAME_EXE):
        log("游戏已在运行。请先关闭，再用本程序启动（补丁必须在启动前打）。")
        return 7

    marker = os.path.join(GAME_DIR, MARKER_NAME)
    try:
        os.remove(marker)
    except Exception:
        pass

    hook_path = os.path.join(tempfile.gettempdir(), "_pkmn_debug_hook.rb")
    with open(hook_path, "wb") as f:
        f.write(HOOK_SOURCE.replace("__MARKER__", MARKER_NAME)
                .strip().encode("utf-8") + b"\n")
    payload = ('eval(File.read("%s"))' % hook_path.replace("\\", "/")).encode("ascii")

    log("=" * 52)
    log("  调试模式启动器（运行时探测引擎）")
    log("=" * 52)
    log("正在启动游戏 ...")
    proc = subprocess.Popen([exe_path], cwd=GAME_DIR,
                            creationflags=0x00000008)
    h = k32.OpenProcess(0x001F0FFF, False, proc.pid)
    if not h:
        log("无法打开进程（权限不足）。请以普通用户方式运行。")
        return 3

    addr = None
    detected = None
    mkxp_seen = False
    scanned = set()
    t0 = time.time()
    log("等待运行库载入 ...")
    while time.time() - t0 < 90:
        if proc.poll() is not None:
            log("游戏进程已退出。")
            return 4
        hit = None
        for name, base, size in _mods(proc.pid):
            ln = name.lower()
            if RGSS_DLL_RE.match(ln):
                hit = ("rgss", base, size, name)
                break
            if RUBY_DLL_RE.match(ln):
                hit = hit or ("mkxp", base, size, name)
        if hit:
            kind, base, size, mname = hit
            if kind != detected:
                detected = kind
                log("识别到引擎：%s（%s，%.1fs）"
                    % ("RGSS" if kind == "rgss" else "mkxp-z",
                       mname, time.time() - t0))
            if base not in scanned:
                scanned.add(base)
                addr = _scan_range(h, base, size, BOOTSTRAP_NEEDLE)
                if addr:
                    log("已定位引导代码: 0x%X (%.1fs)" % (addr, time.time() - t0))
                    break
                if kind == "rgss":
                    log("· 该模块里没搜到引导串")
            if kind == "mkxp":
                mkxp_seen = True
                break
        if mkxp_seen:
            break
        time.sleep(0.15)

    # 认出 mkxp-z → 用原生命令行参数重启
    if detected == "mkxp":
        log("-" * 52)
        log("[i] mkxp-z：改用原生调试参数重启 ...")
        try:
            proc.terminate()
        except Exception:
            pass
        time.sleep(0.6)
        _launch_debug(exe_path)
        log("[OK] 已用 mkxp-z 原生调试模式启动。")
        log("进游戏后按 F9 打开调试菜单；按 F12 复位。")
        return 0

    # 运行时也没认出引擎 → 默认按 RGSS：在所有模块里找引导串
    if not addr:
        if detected is None:
            log("[i] 未认出引擎模块，按默认（RGSS）方式再试一次 ...")
        for name, base, size in _mods(proc.pid):
            if proc.poll() is not None:
                break
            if base in scanned:
                continue
            addr = _scan_range(h, base, size, BOOTSTRAP_NEEDLE)
            if addr:
                detected = detected or "rgss"
                log("在模块 %s 内定位到引导代码: 0x%X" % (name, addr))
                break

    # 连引导串都找不到 → 再用 mkxp-z 原生 debug 参数重启一试
    if not addr:
        log("[i] 没找到可替换的引导串 → 用 `%s debug` 再试一次 ..." % GAME_EXE)
        try:
            proc.terminate()
        except Exception:
            pass
        time.sleep(0.6)
        _launch_debug(exe_path)
        log("已用 `%s debug` 重启。" % GAME_EXE)
        log("mkxp-z 会置 $DEBUG/$TEST；RGSS 会忽略该参数、按正常模式运行。")
        return 0

    old = wintypes.DWORD()
    ntdll.NtSuspendProcess(h)
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), ctypes.c_size_t(256),
                         0x04, ctypes.byref(old))
    written = ctypes.c_size_t(0)
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr),
                                payload + b"\x00", len(payload) + 1,
                                ctypes.byref(written))
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), ctypes.c_size_t(256),
                         old.value or 0x02, ctypes.byref(old))
    ntdll.NtResumeProcess(h)
    if not ok:
        log("写入内存失败，补丁未生效。游戏按正常模式运行。")
        return 6
    log("补丁已写入 (%d 字节)。" % written.value)

    for _ in range(60):
        time.sleep(0.5)
        if os.path.exists(marker):
            break
    if os.path.exists(marker):
        try:
            info = open(marker, "r", encoding="utf-8",
                        errors="replace").read().strip()
        except Exception:
            info = ""
        log("-" * 52)
        log("[OK] 调试模式已开启")
        for line in info.splitlines():
            log("   " + line)
        log("地图上按 F9 开调试菜单；按住 Ctrl 移动 = 穿墙。")
    else:
        log("[!] 钩子未被执行（补丁可能晚了一步）。游戏仍在正常模式运行。")
    log("游戏已交由系统接管，本窗口可以关闭。")
    return 0
'''.replace("__MARKER__", MARKER_NAME)
