# -*- coding: utf-8 -*-
r"""
名字 ↔ 描述配对（术语提取用）。

做两件事：

  ① 把名字类文件（ABILITY_NAMES / ITEM_NAMES / MOVE_NAMES /
     SPECIES_NAMES / SPECIES_FORM_NAMES）与对应的描述类文件配成一组；
  ② 从游戏 PBS/*.txt 或 Data/*.dat 里读出「Name ↔ Description/Pokedex」，
     供术语提取把条目拼成 `Name:Description`。

对应关系（与 Essentials 官方 PBS 一致）：

    ABILITY_NAMES        ↔ ABILITY_DESCRIPTIONS     abilities.txt
    ITEM_NAMES           ↔ ITEM_DESCRIPTIONS        items.txt
    MOVE_NAMES           ↔ MOVE_DESCRIPTIONS        moves.txt
    SPECIES_NAMES        ↔ POKEDEX_ENTRIES          pokemon.txt
    SPECIES_FORM_NAMES   ↔ POKEDEX_ENTRIES          pokemon_forms.txt

PBS 不存在时退回 Data/*.dat（Marshal），字段取 GameData::* 的
`@real_name` / `@real_form_name` / `@real_description` / `@real_pokedex_entry`。
"""
import os
import re

from logger import get_logger

log = get_logger("term_pairs")

# 名字类 section → (描述类 section, PBS 前缀)
PAIR_SECTIONS = {
    "ABILITY_NAMES": ("ABILITY_DESCRIPTIONS", "abilities"),
    "ITEM_NAMES": ("ITEM_DESCRIPTIONS", "items"),
    "MOVE_NAMES": ("MOVE_DESCRIPTIONS", "moves"),
    "SPECIES_NAMES": ("POKEDEX_ENTRIES", "pokemon"),
    "SPECIES_FORM_NAMES": ("POKEDEX_ENTRIES", "pokemon_forms"),
}

# 名字 / 描述两侧给人看的类别名（写进提取缓存的 note 与提示词）
PAIR_LABELS = {
    "ABILITY_NAMES": ("特性名", "特性说明"),
    "ITEM_NAMES": ("道具名", "道具说明"),
    "MOVE_NAMES": ("招式名", "招式说明"),
    "SPECIES_NAMES": ("宝可梦名", "图鉴说明"),
    "SPECIES_FORM_NAMES": ("宝可梦形态名", "图鉴说明"),
}


def pair_labels(name_section):
    """名字类 section → (左标签, 右标签)；不认识返回 (\"名字\", \"描述\")。"""
    return PAIR_LABELS.get(str(name_section or "").upper(), ("名字", "描述"))


# 这四类描述文件归术语提取管，游戏汉化的「翻译」等同名字类文件一样跳过
DESC_SECTIONS = ("ABILITY_DESCRIPTIONS", "ITEM_DESCRIPTIONS",
                 "MOVE_DESCRIPTIONS", "POKEDEX_ENTRIES")

# 各 section 对应的 .dat（dat 里字段名各不相同）
DAT_FILES = {
    "ABILITY_DESCRIPTIONS": ("abilities.dat",),
    "ITEM_DESCRIPTIONS": ("items.dat",),
    "MOVE_DESCRIPTIONS": ("moves.dat",),
    "POKEDEX_ENTRIES": ("species.dat",),
}

_FIELD_RE = re.compile(r"^([ \t]*)([A-Za-z][A-Za-z0-9_]*)([ \t]*=[ \t]*)(.*)$")
_SEC_RE = re.compile(r"^\[([^\]]+)\][ \t]*$")


def desc_section_of(section):
    """名字类 section → 描述类 section；不是配对里的名字类返回 None。"""
    return PAIR_SECTIONS.get(str(section or "").upper(), (None, ""))[0]


def is_desc_section(section):
    return str(section or "").upper() in DESC_SECTIONS


def is_desc_file(path, section=None):
    """这个文件是不是「随名字类一起提取」的四类描述文件之一。"""
    sec = str(section or "").upper()
    if not sec:
        stem = os.path.splitext(os.path.basename(str(path or "")))[0].upper()
        sec = stem
    return sec in DESC_SECTIONS


# ================================================================
# 位置：游戏根目录 / PBS / Data
# ================================================================
def game_root_of(path):
    """从名字文件 / 描述文件往上找游戏根目录（有 PBS 或 Data 的那层）。"""
    p = os.path.abspath(str(path or "."))
    if os.path.isfile(p):
        p = os.path.dirname(p)
    cur = p
    for _ in range(8):
        if os.path.isdir(os.path.join(cur, "PBS")) or \
                os.path.isdir(os.path.join(cur, "Data")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return p


def find_desc_file(name_path, desc_section):
    """
    在名字文件同一目录（及游戏根目录的 Text_* 目录）里找描述文件。
    找不到返回 ""。
    """
    d = os.path.dirname(os.path.abspath(name_path))
    want = str(desc_section or "").upper()
    if not want:
        return ""
    try:
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith(".txt") and \
                    os.path.splitext(fn)[0].upper() == want:
                return os.path.join(d, fn)
    except OSError:
        pass
    # 文本目录可能分成 Text_chinese_core / Text_english_core 等多份
    root = game_root_of(name_path)
    try:
        for sub in sorted(os.listdir(root)):
            sd = os.path.join(root, sub)
            if not os.path.isdir(sd) or not sub.lower().startswith("text_"):
                continue
            p = os.path.join(sd, want + ".txt")
            if os.path.isfile(p):
                return p
    except OSError:
        pass
    return ""


# ================================================================
# PBS
# ================================================================
def _read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", "replace")


def _pbs_files(pbs, prefix, skip=()):
    out = []
    try:
        names = sorted(os.listdir(pbs))
    except OSError:
        return out
    for fn in names:
        low = fn.lower()
        if not low.endswith(".txt") or not low.startswith(prefix):
            continue
        if any(low.startswith(s) for s in skip):
            continue
        out.append(os.path.join(pbs, fn))
    return out


def _parse_pbs(path, forms=False):
    """PBS 文件 → {名字: 描述}。"""
    out = {}
    cur_id = ""
    name = desc = None
    for line in _read_text(path).split("\n"):
        s = line.strip()
        if s.startswith("#"):
            continue
        m = _SEC_RE.match(s)
        if m:
            if name and desc:
                out[name] = desc
            cur_id = m.group(1).strip()
            name = desc = None
            continue
        m = _FIELD_RE.match(line.rstrip("\r"))
        if not m:
            continue
        field, value = m.group(2), m.group(4).strip()
        if forms:
            if field == "FormName":
                name = value
            elif field == "Pokedex":
                desc = value
        else:
            if field == "Name":
                name = value
            elif field == "Description":
                desc = value
            elif field == "Pokedex":
                desc = value
    if name and desc:
        out[name] = desc
    return out


def load_pbs_pairs(root, desc_section):
    """从 PBS/*.txt 读「名字 → 描述」；没有 PBS 或读不到返回 {}。"""
    pbs = os.path.join(root, "PBS")
    if not os.path.isdir(pbs):
        return {}
    pairs = {}
    if desc_section == "POKEDEX_ENTRIES":
        # 普通物种：pokemon*.txt（跳过 pokemon_forms / pokemon_metrics）
        skip = ("pokemon_forms", "pokemon_metrics")
        for p in _pbs_files(pbs, "pokemon", skip=skip):
            pairs.update(_parse_pbs(p, forms=False))
        # 形态：pokemon_forms*.txt（有的整合版也把形态写进 pokemon.txt）
        for p in _pbs_files(pbs, "pokemon_forms"):
            pairs.update(_parse_pbs(p, forms=True))
        return pairs
    prefix = {
        "ABILITY_DESCRIPTIONS": "abilities",
        "ITEM_DESCRIPTIONS": "items",
        "MOVE_DESCRIPTIONS": "moves",
    }.get(desc_section, "")
    if not prefix:
        return {}
    for p in _pbs_files(pbs, prefix):
        pairs.update(_parse_pbs(p))
    return pairs


# ================================================================
# Data/*.dat
# ================================================================
def _ivars(obj):
    return getattr(obj, "ivars", None) or {}


def _val(obj, *names):
    iv = _ivars(obj)
    for n in names:
        v = iv.get(n)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _symbol_text(v):
    try:
        return str(v)
    except Exception:                           # noqa: BLE001
        return ""


def _iter_values(obj, seen=None):
    """Marshal 读出来的 Hash/Array → 去重后的对象序列。"""
    seen = seen or set()
    if hasattr(obj, "values") and callable(obj.values):
        vals = obj.values()
    elif isinstance(obj, (list, tuple)):
        vals = obj
    else:
        vals = [obj]
    for v in vals:
        if id(v) in seen:
            continue
        seen.add(id(v))
        yield v


def _load_dat(path):
    import rmarshal
    return rmarshal.load(path)


def load_dat_pairs(root, desc_section):
    """从 Data/*.dat 读「名字 → 描述」；没有可读的 dat 返回 {}。"""
    out = {}
    for fn in DAT_FILES.get(desc_section, ()):
        p = os.path.join(root, "Data", fn)
        if not os.path.isfile(p):
            continue
        try:
            obj = _load_dat(p)
        except Exception as e:                   # noqa: BLE001
            log.warning("读 %s 失败（跳过）：%s", p, e)
            continue
        for v in _iter_values(obj):
            if desc_section == "POKEDEX_ENTRIES":
                form = getattr(v, "ivars", {}).get("@form") or 0
                name = _val(v, "@real_form_name") if form else ""
                if not name:
                    name = _val(v, "@real_name")
                desc = _val(v, "@real_pokedex_entry")
            else:
                name = _val(v, "@real_name")
                desc = _val(v, "@real_description")
            if name and desc:
                out[name] = desc
    return out


# ================================================================
# 对外
# ================================================================
_cache = {}


def name_desc_map(basis, desc_section):
    """
    某个描述类 section 的「名字 → 描述」表。

    basis 可以是名字文件 / 文本目录 / 游戏根目录；先 PBS，缺了再 dat。
    """
    sec = str(desc_section or "").upper()
    if not sec:
        return {}
    root = game_root_of(basis)
    key = (root, sec)
    if key in _cache:
        return _cache[key]
    pairs = load_pbs_pairs(root, sec)
    if not pairs:
        pairs = load_dat_pairs(root, sec)
        if pairs:
            log.info("PBS 里没有 %s，改用 Data/*.dat（%d 条）", sec, len(pairs))
    else:
        log.info("从 PBS 读到 %s（%d 条）", sec, len(pairs))
    _cache[key] = pairs
    return pairs


def combo_key(name, desc):
    return f"{name}:{desc}"


def combo_index(pairs):
    """{名字: 描述} → {「名字:描述」: (名字, 描述)}。"""
    return {combo_key(n, d): (n, d) for n, d in (pairs or {}).items()}


def split_combo(key, index=None):
    """
    把 `Name:Description` 拆回 (name, desc)。

    index（combo_index 的产物）命中时按已知配对拆，描述里再有冒号也不会拆错；
    认不出就退回第一个冒号。
    """
    s = str(key or "")
    if index and s in index:
        return index[s]
    pos = s.find(":")
    if pos <= 0:
        return None
    return s[:pos], s[pos + 1:]