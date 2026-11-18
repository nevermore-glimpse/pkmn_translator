# -*- coding: utf-8 -*-
r"""
回写 PBS：把翻译缓存里的译文替换进游戏 PBS 文本文件。

为什么要有这个
--------------
    「回写已翻术语缓存 / 回写已翻句子缓存」只把译文倒回翻译缓存与
    `*_translated.txt`，那是给**编译 .dat** 那条路用的。但不少汉化流程是
    直接改 `PBS/*.txt` 再让游戏自己编译（v20+ 的 Essentials 就是这样），
    这时需要的是一份**已经翻好的 PBS 源文件**。

    本模块干的就是这一步：读翻译缓存（`<文本目录>/翻译中间文件/*_cache.json`），
    拿缓存里的**原文键**去 PBS 里逐字段对照，命中就把原文换成译文。

哪些文件、哪些字段
------------------
    | 类别    | PBS 文件（按文件名前缀认）        | 可翻译字段                       |
    |---------|-----------------------------------|----------------------------------|
    | 特性    | abilities*.txt                    | Name、Description                |
    | 道具    | items*.txt                        | Name、NamePlural、Description    |
    | 招式    | moves*.txt                        | Name、Description                |
    | 宝可梦  | pokemon*.txt（跳过 pokemon_metrics*）| Name、FormName、Pokedex       |
    | 属性    | types*.txt                        | Name                             |

    ★ 认前缀是为了把插件包（abilities_Gen_9_Pack.txt / pokemon_forms.txt …）
      一并算进来 —— 它们和主文件是同一批数据，只是分了文件。
    ★ 只替换 `字段 = 值` 里**整个值**能对上缓存键的那些行：
      值对不上就原样不动，所以同一份 PBS 里没翻过的条目不会被误伤。
    ★ 各类别各用自己那批缓存（特性不会拿招式名去套），避免跨类别串译。

安全措施
--------
    · 只处理 UTF-8（含 BOM）的 txt，遇到别的编码整份跳过并报告。
    · 文件的行尾风格、BOM、缩进、`=` 两侧空格、其余行顺序全部保持原样。
    · 第一次改动某个文件前，把**原文件**复制到 `<PBS>/.cn_backup/<相对路径>`；
      已有备份就不再覆盖，所以备份里始终是最初那份原文。
    · 支持 dry-run（write=False）：只统计不改盘，供界面先确认再动手。
"""
import json
import os
import re
import shutil

from logger import get_logger

log = get_logger("pbs_writeback")

# 备份目录（放在 PBS 里，点号开头：本模块与游戏都不会把它当 PBS 数据）
BAK_DIR = ".cn_backup"

# 扫缓存时不必进去的目录（大且不会有翻译缓存）
SKIP_DIRS = {"graphics", "audio", "data", "fonts", "plugins", "pbs",
             "problem", "temp", "__pycache__", ".git", ".venv"}

# 类别表：prefixes=文件名前缀；fields=可翻译字段；caches=取译文的缓存（按优先级）
CLASSES = (
    {"key": "ability", "label": "特性",
     "prefixes": ("abilities",), "skip_prefixes": (),
     "fields": ("Name", "Description"),
     "caches": ("ABILITY_NAMES", "ABILITY_DESCRIPTIONS")},
    {"key": "items", "label": "道具",
     "prefixes": ("items",), "skip_prefixes": (),
     "fields": ("Name", "NamePlural", "Description"),
     "caches": ("ITEM_NAMES", "ITEM_NAME_PLURALS", "ITEM_DESCRIPTIONS")},
    {"key": "moves", "label": "招式",
     "prefixes": ("moves",), "skip_prefixes": (),
     "fields": ("Name", "Description"),
     "caches": ("MOVE_NAMES", "MOVE_DESCRIPTIONS")},
    {"key": "pokemon", "label": "宝可梦",
     "prefixes": ("pokemon",), "skip_prefixes": ("pokemon_metrics",),
     "fields": ("Name", "Pokedex", "FormName"),
     "caches": ("SPECIES_NAMES", "POKEDEX_ENTRIES", "SPECIES_FORM_NAMES")},
    {"key": "types", "label": "属性",
     "prefixes": ("types",), "skip_prefixes": (),
     "fields": ("Name",),
     "caches": ("TYPE_NAMES",)},
)

# `字段 = 值`：缩进 + 标识符 + 等号（含两侧空格）+ 值
_FIELD_RE = re.compile(r"^([ \t]*)([A-Za-z][A-Za-z0-9_]*)([ \t]*=[ \t]*)(.*)$")


# ================================================================
# 路径
# ================================================================
def game_root_of(basis):
    """basis（路径 / 路径列表）→ 游戏根目录。"""
    p = basis
    if isinstance(p, (list, tuple)):
        p = next((x for x in p if x), "")
    p = str(p or "")
    if not p:
        return os.getcwd()
    try:
        import problem_io as PI
        return PI.game_root_of(p)
    except Exception as e:                       # noqa: BLE001
        log.debug("判定游戏根目录失败（退回所选目录）：%s", e)
        return os.path.abspath(p if os.path.isdir(p) else os.path.dirname(p))


def pbs_dir(root):
    return os.path.join(root, "PBS")


# ================================================================
# 读缓存
# ================================================================
def _load_map(path):
    """一份 `*_cache.json` → {原文: 译文}（空 / 与原文相同的视为没翻，丢掉）。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:                       # noqa: BLE001
        log.warning("翻译缓存读取失败（跳过该文件）：%s：%s", path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if not isinstance(v, str):
            continue
        src, dst = str(k), v.strip()
        if not src.strip() or not dst or dst == src:
            continue
        out[src] = dst
    return out


def _find_cache_files(root):
    """游戏根目录下所有 `*_cache.json` → {大写主干: [路径, ...]}（深度 ≤ 3）。"""
    found = {}
    root = os.path.abspath(root or ".")
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= 3:                           # 再往下不会有文本目录
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames
                       if d.lower() not in SKIP_DIRS
                       and not d.startswith(".")
                       and "backup" not in d.lower()]
        for fn in filenames:
            if not fn.lower().endswith("_cache.json"):
                continue
            stem = fn[:-len("_cache.json")].upper()
            found.setdefault(stem, []).append(os.path.join(dirpath, fn))
    for v in found.values():
        v.sort()
    return found


def build_maps(root):
    """
    每个类别各建一份 {原文: 译文}。

    返回 (maps, used)：maps = {类别 key: 字典}，used = {类别 key: [用到的缓存名]}
    ★ 先名字缓存后描述缓存、先找到先赢（setdefault）——
      同一条原文在两类缓存里都有译文时，以**名字**那份为准。
    """
    caches = _find_cache_files(root)
    maps, used = {}, {}
    for cls in CLASSES:
        merged, names = {}, []
        for stem in cls["caches"]:
            for path in caches.get(stem, []):
                data = _load_map(path)
                if not data:
                    continue
                names.append(os.path.basename(path))
                for k, v in data.items():
                    merged.setdefault(k, v)
        maps[cls["key"]] = merged
        used[cls["key"]] = sorted(set(names))
    return maps, used


# ================================================================
# 认文件 / 读写
# ================================================================
def class_of(path):
    """PBS 文件 → 所属类别（认不出来返回 None）。"""
    stem = os.path.splitext(os.path.basename(str(path or "")))[0].lower()
    if not stem:
        return None
    for cls in CLASSES:
        if any(stem.startswith(p) for p in cls["skip_prefixes"]):
            continue
        if any(stem.startswith(p) for p in cls["prefixes"]):
            return cls
    return None


def _read_text(path):
    """读 PBS 文本 → (文本, 行尾, 有无 BOM)；非 UTF-8 返回 None。"""
    with open(path, "rb") as f:
        raw = f.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if bom else raw
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        log.warning("PBS 文件不是 UTF-8（跳过）：%s：%s", path, e)
        return None
    # ★ 统一成 LF 处理，写回时按原来的行尾还原
    newline = "\r\n" if b"\r\n" in body else "\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, newline, bom


def _write_text(path, text, newline, bom):
    data = text.replace("\n", newline)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(("\ufeff" if bom else "") + data)


def _unquote(value):
    """`"a, b"` → (`a, b`, True)；没被引号包住就原样返回。"""
    v = value
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1].replace('\\"', '"'), True
    return v, False


def _format_value(value, quoted):
    """译文写回时的值：原来是引号包的就继续包；含逗号 / 引号的必须包。"""
    if quoted or "," in value or '"' in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _backup(path, pbs_root):
    """第一次改动某文件前留一份原文；已有备份就直接用旧的。"""
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(pbs_root))
    dst = os.path.join(pbs_root, BAK_DIR, rel)
    if os.path.isfile(dst):
        return dst
    try:
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copy2(path, dst)
        log.info("已备份 PBS 原文：%s ← %s", dst, path)
        return dst
    except OSError as e:
        log.warning("备份 PBS 失败（继续回写）：%s：%s", path, e)
        return ""


# ================================================================
# 主流程
# ================================================================
def _pbs_files(pbs):
    """PBS 里所有 .txt（含插件子目录；跳过点号目录与 *backup*）。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(pbs):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".")
                       and "backup" not in d.lower()]
        for fn in sorted(filenames):
            if fn.lower().endswith(".txt"):
                out.append(os.path.join(dirpath, fn))
    return out


def _process_file(path, cls, mapping, pbs_root, write):
    """
    处理一个 PBS 文件 → {"changed": n, "note": "…"}（note 为空表示正常）。

    ★ 只在 `字段 = 值` 的整行值能对上缓存键时替换，其余行逐字节原样保留。
    """
    got = _read_text(path)
    if got is None:
        return {"changed": 0, "note": "不是 UTF-8，已跳过"}
    text, newline, bom = got
    fields = set(cls["fields"])
    lines = text.split("\n")
    out, changed = [], 0
    for line in lines:
        m = _FIELD_RE.match(line)
        if not m:
            out.append(line)
            continue
        indent, field, sep, raw = m.group(1), m.group(2), m.group(3), m.group(4)
        if field not in fields:
            out.append(line)
            continue
        value = raw.rstrip()                     # 值的右空白单独留着重拼
        tail = raw[len(value):]
        src, quoted = _unquote(value)
        if not src:
            out.append(line)
            continue
        dst = mapping.get(src)
        if dst is None:
            dst = mapping.get(src.strip())
        if dst is None or dst == src or not dst.strip():
            out.append(line)
            continue
        out.append(f"{indent}{field}{sep}{_format_value(dst, quoted)}{tail}")
        changed += 1
    if changed and write:
        _backup(path, pbs_root)
        _write_text(path, "\n".join(out), newline, bom)
        log.info("回写 PBS：%s（%d 行）", os.path.basename(path), changed)
    return {"changed": changed, "note": ""}


def apply(basis, write=True):
    """
    把翻译缓存的译文回写进 PBS。

    write=False → 只统计（dry-run），不碰任何文件。

    返回：
      ok        是否找到可处理的 PBS（False 时看 reason）
      reason    "pbs_missing" / "pbs_empty" / "no_cache" / ""
      root/pbs  游戏根目录 / PBS 目录
      files     [{path, name, cls, lines, note}] 有改动的文件
      total     总替换行数
      scanned   扫过的 PBS txt 数
      caches    {类别 key: [用到的缓存文件名]}
      backup    备份目录（有改动时）
    """
    root = game_root_of(basis)
    pbs = pbs_dir(root)
    st = {"ok": False, "reason": "", "root": root, "pbs": pbs,
          "files": [], "total": 0, "scanned": 0, "skipped": [],
          "caches": {}, "backup": "", "written": bool(write)}
    if not os.path.isdir(pbs):
        st["reason"] = "pbs_missing"
        return st

    files = _pbs_files(pbs)
    st["scanned"] = len(files)
    if not files:
        st["reason"] = "pbs_empty"
        return st

    maps, used = build_maps(root)
    st["caches"] = {k: v for k, v in used.items() if v}
    if not any(maps.values()):
        st["reason"] = "no_cache"
        return st

    st["ok"] = True
    for path in files:
        cls = class_of(path)
        if not cls:
            continue
        mapping = maps.get(cls["key"]) or {}
        if not mapping:
            continue
        try:
            r = _process_file(path, cls, mapping, pbs, write)
        except Exception as e:                   # noqa: BLE001
            log.error("处理 PBS 失败（跳过 %s）：%s", path, e)
            st["skipped"].append((os.path.relpath(path, pbs), f"处理失败：{e}"))
            continue
        if r["note"]:
            st["skipped"].append((os.path.relpath(path, pbs), r["note"]))
            continue
        if r["changed"]:
            st["files"].append({
                "path": path,
                "name": os.path.relpath(path, pbs),
                "cls": cls["label"],
                "lines": r["changed"],
            })
            st["total"] += r["changed"]

    if write and st["total"]:
        st["backup"] = os.path.join(pbs, BAK_DIR)
    log.info("回写 PBS %s：%d 个类别缓存，%d 个文件、%d 行%s",
             "（预演）" if not write else "完成", len(st["caches"]),
             len(st["files"]), st["total"], "" if write else "（未改盘）")
    return st
