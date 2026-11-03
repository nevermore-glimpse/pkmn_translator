# -*- coding: utf-8 -*-
r"""
地图名（Data/MapInfos.rxdata）的提取与写回。

为什么单独做
------------
    Essentials 的「文本提取」只导 `messages*.dat` 里的表；地图名不在那张表里，
    而是躺在 RPG Maker XP 的 `Data/MapInfos.rxdata` 里（每个地图一个
    `RPG::MapInfo` 对象，名字在 `@name`）。想翻地图名只能直接改这个文件。

    于是这里做两件事：

      提取  read_map_infos() → 写成 `MapInfos.txt`（intl 风格，放在提取出来的
            文本文件夹里），格式是「地图编号 / 原文 / 译文」三行一条，
            区块标志 `[21]`（= MAP_NAMES）。这样：
              · 术语提取按「名字类文件」处理它（区块 21 是名字区块）；
              · 普通翻译流水线会跳过它（is_term_source_file 认区块 21）；
              · 编译文本时**不写进 language .dat**，而是写回 MapInfos.rxdata。

      写回  compile_to_rxdata() → 只改 `@name`，其余字段（@order / @parent_id /
            @expanded / 全图数据）一个字不动。

格式（MapInfos.txt）
--------------------
    # To localize this text for a particular language, please
    # translate every second line of this file.
    [21]
    1                                 ← 地图编号（MapInfos 的键）
    Intro 1                           ← 原文
    Intro 1                           ← 译文（翻这一行）

    ★ 编号行是纯数字，`parser.extract_entries` 会跳过它，所以术语提取
      读到的仍然是「原文 / 译文」成对的条目，与其它名字文件完全一致。
    ★ 换行 / 制表符 / 首尾方括号用 intl_text.normalize_value 转义，
      与游戏导出的其它文本同一套规则（读回时 denormalize_value 还原）。

往返安全
--------
    `rmarshal` 对 MapInfos.rxdata 的读→写是**逐字节一致**的（实测 504 个
    地图 / MapInfos 文件，全部 round-trip 相同），所以写回只会在原文与译文
    真的不同时产生字节差异。写之前一律备份，写完复查对象数。
"""
import os
import re
import time

import config
import game_scripts as GS
import intl_text as IT
import rmarshal
from logger import get_logger

log = get_logger("map_infos")

# Data 下的文件 / 提取出来的文本文件名
RXDATA_NAME = "MapInfos.rxdata"
TXT_STEM = "MapInfos"
TXT_NAME = "MapInfos.txt"
TRANS_SUFFIX = "_translated.txt"

# 区块号：21 = MAP_NAMES（见 intl_text.SECTION_NAMES）
SECTION_ID = 21

_HEADER = ("# To localize this text for a particular language, please\r\n"
           "# translate every second line of this file.\r\n")

# `[...]` 区块行（与 parser.BLOCK_RE 同一套）
_BLOCK_RE = re.compile(r'^\s*\[[^\]]*\]\s*$')
_TXT_RE = re.compile(r'^mapinfos(_translated)?\.txt$', re.I)

# MapInfos 里可能出现「没有名字」的地图（编辑器里没填）→ 不导出
_EMPTY = ("",)


# ================================================================
# 路径 / 判定
# ================================================================
def rxdata_path(game_dir):
    return os.path.join(GS.data_dir(str(game_dir or "")), RXDATA_NAME)


def is_mapinfos_txt(name_or_path):
    """文件名是不是 MapInfos.txt / MapInfos_translated.txt。"""
    return bool(_TXT_RE.match(os.path.basename(str(name_or_path or ""))))


def is_translated(name_or_path):
    return os.path.basename(str(name_or_path or "")).lower().endswith(
        TRANS_SUFFIX.lower())


def txt_path(dir_path, translated=False):
    return os.path.join(dir_path, TXT_STEM
                        + (TRANS_SUFFIX if translated else ".txt"))


# ================================================================
# 中间文件目录：地图名文本和别的文本用同一个「翻译中间文件」夹
# ================================================================
# 可能落在源目录的那几个中间文件（搬家用；按长到短匹配不上也没关系，
# 这里逐个拼全名判断）
_MID_SUFFIXES = (
    "_cache.json",
    "_cache_edited.json",
    "_translated_report.txt",
    "_conflicts.json",
    "_unknown_ctrl.txt",
)


def intermediates_dir(path_or_dir, create=True):
    """
    地图名文本的中间文件（缓存 / 检查报告 / 冲突 / 手工编辑）该放哪。

    ★ **一律放「翻译中间文件」夹**，与同目录其它文本完全一样。
      `config.aux_dir()` 只在夹子**已经存在**时才会用它；单文件翻译时
      没人建这个夹（`commands.enter_work_dir` 要求同目录 ≥2 个文件），
      于是地图名的缓存 / 报告会孤零零地摆在 txt 旁边 —— 这就是要修的不一致。
    ★ 顺手把「以前落在源目录」的那几份 MapInfos 中间文件搬进夹子里：
      只动 MapInfos 这一份，且目标已存在就跳过，免得挪位置后缓存作废、
      整套地图名重新送一次模型。

    返回中间文件夹路径（建不出来时退回源目录）。
    """
    p = str(path_or_dir or "")
    if not p:
        return ""
    d = p if os.path.isdir(p) else os.path.dirname(os.path.abspath(p))
    wd = os.path.join(d, config.WORK_DIR_NAME)
    if not os.path.isdir(wd):
        if not create:
            return ""
        try:
            os.makedirs(wd, exist_ok=True)
        except OSError as e:
            log.warning("建「%s」失败（地图名中间文件仍放源目录）：%s：%s",
                        config.WORK_DIR_NAME, d, e)
            return d
    _migrate_loose(d, wd)
    return wd


def _migrate_loose(src_dir, wd):
    """把散在源目录的 MapInfos 中间文件搬进「翻译中间文件」。"""
    moved = []
    for suf in _MID_SUFFIXES:
        src = os.path.join(src_dir, TXT_STEM + suf)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(wd, TXT_STEM + suf)
        if os.path.exists(dst):
            continue          # 两边都有 → 留夹子里的那份，别覆盖
        try:
            os.replace(src, dst)
            moved.append(TXT_STEM + suf)
        except OSError as e:
            log.warning("移动地图名中间文件失败（跳过）：%s：%s", src, e)
    if moved:
        log.info("地图名中间文件已并入「%s」：%s",
                 config.WORK_DIR_NAME, "、".join(moved))
    return moved


# ================================================================
# 读 MapInfos.rxdata
# ================================================================
def _items(root):
    """MapInfos 的「键 → MapInfo 对象」迭代（RHash / dict 都认）。"""
    if isinstance(root, rmarshal.RHash):
        return list(root.items())
    if isinstance(root, dict):
        return list(root.items())
    return []


def read_map_infos(game_dir):
    """
    读 Data/MapInfos.rxdata → [(地图编号, 地图名), ...]（按编号升序）。

    · 没有这个文件 / 读不出来 → 空列表（调用方当「这个游戏没有地图名」处理）；
    · 名字为空的地图跳过；
    · 编号不是整数的条目跳过（不是 RMXP 的 MapInfos，不碰）。
    """
    path = rxdata_path(game_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as f:
            objs = rmarshal.loads_all(f.read())
    except Exception as e:                       # noqa: BLE001
        log.warning("读 MapInfos.rxdata 失败（跳过地图名）：%s：%s", path, e)
        return []
    if not objs:
        return []
    out = []
    for key, info in _items(objs[0]):
        try:
            mid = int(key)
        except (TypeError, ValueError):
            continue
        name = ""
        try:
            name = info.get("@name") if hasattr(info, "get") else None
        except Exception:                        # noqa: BLE001
            name = None
        name = "" if name is None else str(name)
        if name.strip() in _EMPTY:
            continue
        out.append((mid, name))
    out.sort(key=lambda kv: kv[0])
    return out


# ================================================================
# 写 MapInfos.txt
# ================================================================
def read_txt(path):
    """
    读 MapInfos.txt → [(编号, 原文, 译文), ...]（译文可能为空串）。

    ★ 只认「纯数字编号 + 后两行」这一种结构：编号行不是数字就跳过，
      两个文本行之间允许夹空行。
    """
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace",
                  newline="") as f:
            raw = f.read()
    except OSError as e:
        log.warning("读 %s 失败：%s", path, e)
        return []
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s or s.startswith("#") or _BLOCK_RE.match(s):
            i += 1
            continue
        if not s.isdigit():
            i += 1
            continue
        mid = int(s)
        got = []
        j = i + 1
        while j < n and len(got) < 2:
            if lines[j].strip() == "":
                j += 1
                continue
            got.append(lines[j].rstrip())
            j += 1
        if len(got) < 2:
            break
        out.append((mid,
                    IT.denormalize_value(got[0]),
                    IT.denormalize_value(got[1])))
        i = j
    return out


def extract(game_dir, out_dir, emit=None):
    """
    把 Data/MapInfos.rxdata 里的地图名写成 `<out_dir>/MapInfos.txt`。

    · 已经存在 `MapInfos_translated.txt`（上次翻好的）时，译文行用它 ——
      重新提取不会把翻好的地图名冲掉；
    · 文件不存在时什么也不做（返回 extracted=False）。

    返回 {"ok", "out", "count", "translated", "extracted"}
    """
    def say(msg):
        if emit:
            emit(msg)

    pairs = read_map_infos(game_dir)
    if not pairs:
        return {"ok": False, "extracted": False, "count": 0,
                "out": "", "reason": "没有 Data/MapInfos.rxdata 或里面没有地图名"}

    os.makedirs(out_dir, exist_ok=True)
    prev = {}
    tpath = txt_path(out_dir, translated=True)
    if os.path.isfile(tpath):
        for mid, _old, trans in read_txt(tpath):
            t = (trans or "").strip()
            if t:
                prev[mid] = trans

    buf = ["\ufeff", _HEADER, f"[{SECTION_ID}]\r\n"]
    for mid, name in pairs:
        text = IT.normalize_value(name)
        cur = IT.normalize_value(prev.get(mid) or name)
        buf.append(f"{mid}\r\n{text}\r\n{cur}\r\n")
    out = txt_path(out_dir, translated=False)
    with open(out, "wb") as f:
        f.write("".join(buf).encode("utf-8"))

    say(f"[提取] 地图名：{len(pairs)} 条 → {os.path.basename(out)}"
        + (f"（沿用上次译文 {len(prev)} 条）" if prev else ""))
    log.info("提取地图名：%s → %s（%d 条）", game_dir, out, len(pairs))
    return {"ok": True, "extracted": True, "out": out, "count": len(pairs),
            "translated": len(prev)}


# ================================================================
# 写回 MapInfos.rxdata
# ================================================================
def _backup(path, stamp=True):
    """备份 `MapInfos.rxdata`：固定 .bak 留最初那份，另加一份带时间戳的。"""
    made = []
    dst = path + ".bak"
    if not os.path.exists(dst):
        import shutil
        shutil.copyfile(path, dst)
        made.append(dst)
    if stamp:
        ts = path + "." + time.strftime("%Y%m%d-%H%M%S") + ".bak"
        if not os.path.exists(ts):
            import shutil
            shutil.copyfile(path, ts)
            made.append(ts)
    return made


def compile_to_rxdata(game_dir, txt_paths, emit=None, backup=True):
    """
    把 MapInfos.txt（或 `MapInfos_translated.txt`）里的译文写回
    Data/MapInfos.rxdata 的 `@name`，其余字段一个字不动。

    txt_paths：可以是一个文件、一个路径列表，或一个文件夹（自动找里面的
               MapInfos.txt / MapInfos_translated.txt，优先译文文件）。

    返回 {"ok", "changed", "total", "out", "backup", "reason"}
    """
    def say(msg):
        if emit:
            emit(msg)

    path = rxdata_path(game_dir)
    if not os.path.isfile(path):
        return {"ok": False, "changed": 0, "total": 0, "out": path,
                "reason": "没有 Data/MapInfos.rxdata"}

    src = _pick_txt(txt_paths)
    if not src:
        return {"ok": False, "changed": 0, "total": 0, "out": path,
                "reason": "没找到 MapInfos.txt"}

    entries = read_txt(src)
    if not entries:
        return {"ok": False, "changed": 0, "total": 0, "out": path,
                "reason": f"{os.path.basename(src)} 里没有可用的条目"}

    wanted = {}
    for mid, old, trans in entries:
        t = (trans or "").strip()
        if not t:
            continue
        if t == (old or "").strip():
            continue                       # 还是原文，说明没翻
        wanted[mid] = trans

    try:
        with open(path, "rb") as f:
            raw = f.read()
        objs = rmarshal.loads_all(raw)
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "changed": 0, "total": len(wanted), "out": path,
                "reason": f"读 {RXDATA_NAME} 失败：{e}"}
    if not objs:
        return {"ok": False, "changed": 0, "total": len(wanted), "out": path,
                "reason": f"{RXDATA_NAME} 是空的"}

    root = objs[0]
    changed = 0
    for key, info in _items(root):
        try:
            mid = int(key)
        except (TypeError, ValueError):
            continue
        new = wanted.get(mid)
        if not new:
            continue
        if not hasattr(info, "get"):
            continue
        old = info.get("@name")
        old_text = "" if old is None else str(old)
        if old_text == new:
            continue
        info["@name"] = _same_type(new, old)
        changed += 1

    if not changed:
        say(f"[编译] 地图名：没有需要改的条目（{len(wanted)} 条译文与原文相同）")
        return {"ok": True, "changed": 0, "total": len(wanted), "out": path,
                "backup": None, "reason": ""}

    bak = None
    if backup:
        try:
            made = _backup(path)
            bak = made[0] if made else None
            if bak:
                say(f"[编译] 原文件已备份：{os.path.basename(bak)}")
        except OSError as e:
            return {"ok": False, "changed": 0, "total": len(wanted),
                    "out": path, "reason": f"备份失败：{e}"}

    n_before = len(_items(root))
    data = rmarshal.dumps_all(objs)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)

    # 复查：读回来对象数必须不变（少一个就是写坏了）
    try:
        with open(path, "rb") as f:
            back = rmarshal.loads_all(f.read())
        n_after = len(_items(back[0])) if back else -1
    except Exception as e:                       # noqa: BLE001
        n_after = -1
        say(f"[编译] ⚠ {RXDATA_NAME} 写完后读不回来：{e}")
    if n_after >= 0 and n_before and n_after != n_before:
        say(f"[编译] ⚠ {RXDATA_NAME} 地图条数变了：{n_before} → {n_after}")

    say(f"[编译] 地图名：已写回 {changed} 条 → {RXDATA_NAME}"
        f"（{os.path.getsize(path):,} 字节）")
    log.info("写回地图名：%s ← %s（%d 条）", path, src, changed)
    return {"ok": True, "changed": changed, "total": len(wanted),
            "out": path, "backup": bak, "reason": ""}


def _same_type(new, old):
    """新名字按旧值的类型造（保住 Marshal 的编码标记，见 RStr.smart）。"""
    if isinstance(old, rmarshal.RStr):
        return rmarshal.RStr.smart(new, old)
    return new


def _pick_txt(paths):
    """从文件 / 列表 / 文件夹里挑出要读的那份 txt（优先 *_translated.txt）。"""
    items = paths if isinstance(paths, (list, tuple)) else [paths]
    found = []
    for p in items:
        p = str(p or "")
        if not p:
            continue
        if os.path.isdir(p):
            for name in (TXT_STEM + TRANS_SUFFIX, TXT_NAME):
                q = os.path.join(p, name)
                if os.path.isfile(q):
                    found.append(q)
        elif os.path.isfile(p) and is_mapinfos_txt(p):
            found.append(p)
    if not found:
        return ""
    trans = [p for p in found if is_translated(p)]
    return trans[0] if trans else found[0]


def collect_txt(paths):
    """这些输入里所有的 MapInfos 文本（去重保序），用于编译前挑目标。"""
    items = paths if isinstance(paths, (list, tuple)) else [paths]
    out, seen = [], set()
    for p in items:
        p = str(p or "")
        if not p:
            continue
        if os.path.isdir(p):
            for name in (TXT_STEM + TRANS_SUFFIX, TXT_NAME):
                q = os.path.join(p, name)
                if os.path.isfile(q) and q not in seen:
                    seen.add(q)
                    out.append(q)
        elif os.path.isfile(p) and is_mapinfos_txt(p):
            ap = os.path.abspath(p)
            if ap not in seen:
                seen.add(ap)
                out.append(p)
    return out
