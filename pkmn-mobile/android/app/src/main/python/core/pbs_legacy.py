# -*- coding: utf-8 -*-
r"""
PBS 编辑（老版本）—— Essentials **v16 / v17 / v18** 的 PBS 提取与编译。

## 和 v19+ 的区别

| | v19+ | v16 / v17 / v18 |
|---|---|---|
| 数据类 | ``GameData::X`` 对象，Hash{Symbol=>对象} | 普通 Array / Hash（数值型） |
| 招式 / 道具 / 特性 | 段式 ``[ID]`` + ``Key = Value`` | **一行一条 CSV** |
| 训练家（v16/v17） | ``[类型,名字]`` + ``Pokemon = X,Y`` | **名字一行、数量一行、每只一行** |
| 宝可梦 | ``species.dat`` 一个文件 | v16/v17 拆成 dexdata / attacksRS / eggEmerald / evolutions / regionals / metrics 六个；v18 是 species.dat + 几个衍生文件 |
| 名字 / 图鉴文字 | 也在 .dat 里 | **不在 .dat 里**（存在语言包/脚本常量里） |

## 我们怎么处理「编译」

老版本里有一半数据是**衍生缓存**（种族表 dexdata、招式机表 attacksRS、进化表
evolutions、蛋招式 eggEmerald、地区图鉴 regionals），它们是官方编译器一次性重建的，
拆开单个写容易造成「一半新一半旧」。

所以本模块的策略是：

* 能安全单独写的（类型、招式、道具、树果、地图、训练家类型……）**直接写回 .dat**；
* 其余（宝可梦 / 训练家名单 / 电话 / 遭遇 / 脚本常量）写完 txt 后把 Data 里的
  .dat 时间戳回拨 —— 游戏下次启动时官方编译器会**全量重编译**，
  生成的数据与官方完全一致（老版本游戏本来就是这个流程）。

这个「回拨时间戳」是只改 mtime、不删文件，编译失败也能随时重来。
"""
from __future__ import annotations

import os
import re
import struct
from typing import Any, Dict, List, Optional, Tuple

import rmarshal
from rmarshal import RHash

import pbs_edit as PE

FAMILIES = ("v16", "v17", "v18")

# 官方重编译判定：PBS 的 mtime 比 Data 新就算「需要重编译」
# 我们把 .dat 的时间戳挪到 txt 之前这么多秒，确保一定触发
_RECOMPILE_GAP = 120


# ---------------------------------------------------------------------------
# 版本识别
# ---------------------------------------------------------------------------

def detect(game_root: str) -> Tuple[str, str]:
    """返回 (family, 说明)；family ∈ {"v16","v17","v18",""}。"""
    data = os.path.join(game_root, "Data")
    try:
        names = {n.lower() for n in os.listdir(data)}
    except OSError:
        return "", "没有 Data 目录"
    has = lambda n: n in names                                   # noqa: E731
    # ① 脚本里的版本号（v17 起才有 ESSENTIALSVERSION）
    ver = ""
    try:
        import essentials_base as EB
        ver = (EB.detect_version(game_root) or "").strip()
    except Exception:
        ver = ""
    if ver:
        try:
            major = int(float(ver))
        except ValueError:
            major = 0
        if major == 16:
            return "v16", "Essentials %s" % ver
        if major == 17:
            return "v17", "Essentials %s" % ver
        if major == 18:
            return "v18", "Essentials %s" % ver
        if major >= 19:
            return "", "Essentials %s（v19+，请用新版 PBS 功能）" % ver
    # ② 没有版本号：看 Data 里的标志文件
    if has("dexdata.dat") or has("attacksRS.dat"):
        # v16 / v17 共用这套文件；没有 ESSENTIALSVERSION 就是 v16
        if has("berryplants.dat") and not has("tm.dat"):
            return "v16", "老版数据文件（无版本号）"
        if _has_version_script(game_root):
            return "v17", "老版数据文件 + 脚本无版本号（按 v17 处理）"
        return "v16", "老版数据文件、脚本里没有版本号（v16 起才有该常量）"
    if has("species_movesets.dat") or has("form2species.dat"):
        return "v18", "有 species_movesets/form2species（v18 起）"
    if has("berry_plants.dat") and has("species.dat"):
        return "", "看起来是 v19+（请用新版 PBS 功能）"
    return "", "认不出是哪个版本"


def _has_version_script(game_root: str) -> bool:
    """脚本里有没有 ESSENTIALSVERSION（有 = v17 起）。"""
    try:
        import game_scripts as GS
        for _k, title, src in GS.iter_named_scripts(game_root):
            if src and "ESSENTIALSVERSION" in src:
                return True
    except Exception:
        pass
    return False


def _family_of(family: str) -> str:
    return family if family in FAMILIES else "v17"


# ---------------------------------------------------------------------------
# 读「游戏自己」的脚本：字段布局 / 编号常量
# ---------------------------------------------------------------------------
# ★ 同人游戏常改过官方布局（多几个特性位、改字段顺序），硬编码参考版的偏移
#   对不上。这里直接解析游戏脚本里的 schema 表和常量，按它自己的布局来写。
_LAYOUT_CACHE: Dict[str, dict] = {}


_SCRIPTS_CACHE: Dict[str, list] = {}


def _source_cache(game_root: str) -> list:
    """把游戏脚本只读一次（Scripts.rxdata 很大，反复解码会卡成幻灯片）。"""
    if game_root in _SCRIPTS_CACHE:
        return _SCRIPTS_CACHE[game_root]
    out = []
    try:
        import game_scripts as GS
        out.extend(GS.iter_named_scripts(game_root))
    except Exception:
        pass
    try:
        out.extend(_constants_scripts(game_root))
    except Exception:
        pass
    _SCRIPTS_CACHE[game_root] = out
    return out


def _iter_scripts(game_root: str):
    yield from _source_cache(game_root)


def _constants_scripts(game_root: str):
    p = os.path.join(game_root, "Data", "Constants.rxdata")
    if not os.path.isfile(p):
        return
    import zlib
    try:
        obj = rmarshal.load(p)
    except Exception:
        return
    if not isinstance(obj, list):
        return
    for e in obj:
        if not isinstance(e, list) or len(e) < 3:
            continue
        name = e[1] if isinstance(e[1], str) else str(e[1])
        raw = e[2]
        if not isinstance(raw, str):
            continue
        try:
            data = zlib.decompress(raw.encode("utf-8", "surrogateescape"))
        except Exception:
            try:
                data = raw.encode("utf-8", "surrogateescape")
            except Exception:
                continue
        yield "constants", name, p, name, data.decode("utf-8",
                                                      errors="replace")


def global_consts(game_root: str, prefix: str) -> Dict[str, int]:
    """全脚本范围找 `PREFIXxxx = 数字` 常量（如 MetadataHome / ITEM_NAME）。"""
    out: Dict[str, int] = {}
    pat = re.compile(r"^\s*" + prefix + r"(\w+)\s*=\s*(\d+)\s*$")
    for _m, _k, _p, _name, src in _iter_scripts(game_root):
        if not src or prefix not in src:
            continue
        for ln in src.splitlines():
            m = pat.match(ln)
            if m:
                out.setdefault(m.group(1), int(m.group(2)))
    return out


def _byte_len(t: str) -> int:
    """schema 类型串占多少字节（e/g=1，E/G=2，u/v/i=1，w=2，f=2，其余不入库）。"""
    n = 0
    for ch in t:
        if ch in "*^":
            continue
        if ch in ("e", "g", "u", "v", "i", "b", "n", "m", "x"):
            n += 1
        elif ch in ("E", "G", "w", "f", "U", "V"):
            n += 2
    return n


def dex_layout(game_root: str) -> Dict[str, Tuple[int, int]]:
    """
    从游戏自己的 pbCompilePokemonData 里读宝可梦字段布局。
    返回 {字段名: (起始偏移, 字节数)}；读不到就用参考版的兜底表。
    """
    ck = game_root + "|dex"
    if ck in _LAYOUT_CACHE:
        return _LAYOUT_CACHE[ck]
    out: Dict[str, Tuple[int, int]] = {}
    pat = re.compile(r'"([A-Za-z_]+)"\s*=>\s*\[\s*(-?\d+)\s*,\s*"([^"]*)"')
    for _m, _k, _p, _name, src in _iter_scripts(game_root):
        if not src or "def pbCompilePokemonData" not in src:
            continue
        i = src.index("def pbCompilePokemonData")
        j = src.find("currentmap", i)
        block = src[i:j if j > i else i + 20000]
        for m in pat.finditer(block):
            key, pos, ftype = m.group(1), int(m.group(2)), m.group(3)
            n = _byte_len(ftype)
            if pos >= 0 and n > 0:
                out[key] = (pos, n)
        if out:
            break
    if not out:
        out = dict(DEX_OFFSETS)
    _LAYOUT_CACHE[ck] = out
    return out


def _parse_named_consts(game_root: str, marker: str, prefixes: Tuple[str, ...],
                        aliases: Dict[str, str]) -> Dict[str, int]:
    """
    在含 marker 的脚本里收集 `<前缀><名字> = 数字`，按别名表归一。

    ★ 老版本写 ITEMID/ITEMNAME，v18 起写 ITEM_ID/ITEM_NAME —— 按前缀 + 后缀认；
      多份脚本都有匹配时取「认出的字段最多」的那一份。
    """
    pat = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(\d+)\s*$")
    best: Dict[str, int] = {}
    for _m, _k, _p, _name, src in _iter_scripts(game_root):
        if not src or marker not in src:
            continue
        found: Dict[str, int] = {}
        for ln in src.splitlines():
            m = pat.match(ln)
            if not m:
                continue
            nm = m.group(1).upper().lstrip("_")
            for pre in prefixes:
                if not nm.startswith(pre):
                    continue
                rest = nm[len(pre):].lstrip("_")
                if rest in aliases and aliases[rest] not in found:
                    found[aliases[rest]] = int(m.group(2))
        if len(found) > len(best):
            best = found
    return best


def layout_consts(game_root: str) -> dict:
    """把游戏脚本里的各类字段常量一次性读出来（带缓存）。"""
    ck = game_root + "|consts"
    if ck in _LAYOUT_CACHE:
        return _LAYOUT_CACHE[ck]
    meta = global_consts(game_root, "Metadata")
    glob_keys = ("Home", "WildBattleBGM", "TrainerBattleBGM", "WildVictoryME",
                 "TrainerVictoryME", "WildCaptureME", "SurfBGM", "BicycleBGM",
                 "PlayerA", "PlayerB", "PlayerC", "PlayerD", "PlayerE",
                 "PlayerF", "PlayerG", "PlayerH", "StorageCreator",
                 "StartMoney", "PlayerA")
    d = {
        "meta_global": {k: v for k, v in meta.items() if k in glob_keys},
        "meta_map": {k: v for k, v in meta.items() if k not in glob_keys
                     and k not in ("Size", "Position")},
        "metric": _parse_named_consts(
            game_root, "", ("METRIC", "METRICS"),
            {"PLAYERX": "PlayerX", "PLAYERY": "PlayerY", "ENEMYX": "EnemyX",
             "ENEMYY": "EnemyY", "ALTITUDE": "Altitude", "SHADOWX": "ShadowX",
             "SHADOWSIZE": "ShadowSize",
             "BATTLERPLAYERX": "PlayerX", "BATTLERPLAYERY": "PlayerY",
             "BATTLERENEMYX": "EnemyX", "BATTLERENEMYY": "EnemyY",
             "BATTLERALTITUDE": "Altitude", "BATTLERSHADOWX": "ShadowX",
             "BATTLERSHADOWSIZE": "ShadowSize"}),
        "item": _parse_named_consts(
            game_root, "", ("ITEM",),
            {"ID": "ID", "NAME": "NAME", "PLURAL": "PLURAL",
             "POCKET": "POCKET", "PRICE": "PRICE", "DESCRIPTION": "DESC",
             "DESC": "DESC", "FIELDUSE": "USE", "BATTLEUSE": "BATTLEUSE",
             "TYPE": "TYPE", "MACHINE": "MACHINE"}),
        "move": _parse_named_consts(
            game_root, "", ("MOVE",),
            {"ID": "ID", "INTERNALNAME": "INTERNAL", "NAME": "NAME",
             "FUNCTIONCODE": "FUNC", "BASEDAMAGE": "DAMAGE",
             "TYPE": "TYPE", "CATEGORY": "CATEGORY", "ACCURACY": "ACCURACY",
             "TOTALPP": "PP", "EFFECTCHANCE": "EFFECT",
             "ADDLEFFECT": "EFFECT", "TARGET": "TARGET",
             "PRIORITY": "PRIORITY", "FLAGS": "FLAGS",
             "DESCRIPTION": "DESC"}),
        "tp": _parse_named_consts(
            game_root, "", ("TP",),
            {"SPECIES": "SPECIES", "LEVEL": "LEVEL", "ITEM": "ITEM",
             "MOVE1": "MOVE1", "MOVE2": "MOVE2", "MOVE3": "MOVE3",
             "MOVE4": "MOVE4", "ABILITY": "ABILITY", "GENDER": "GENDER",
             "FORM": "FORM", "SHINY": "SHINY", "NATURE": "NATURE",
             "IV": "IV", "HAPPINESS": "HAPPINESS", "NAME": "NAME",
             "SHADOW": "SHADOW", "BALL": "BALL"}),
    }
    _LAYOUT_CACHE[ck] = d
    return d


# ---------------------------------------------------------------------------
# 二进制小工具（照抄官方 Compiler 的读写原语）
# ---------------------------------------------------------------------------

class Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.d = data
        self.p = pos

    def byte(self) -> int:
        v = self.d[self.p]
        self.p += 1
        return v

    def sbyte(self) -> int:
        v = self.byte()
        return v - 0x100 if v >= 0x80 else v

    def word(self) -> int:
        v = struct.unpack_from("<H", self.d, self.p)[0]
        self.p += 2
        return v

    def sword(self) -> int:
        v = self.word()
        return v - 0x10000 if v >= 0x8000 else v

    def dword(self) -> int:
        v = struct.unpack_from("<I", self.d, self.p)[0]
        self.p += 4
        return v

    def varint(self) -> int:                       # decodeInt
        bits = 0
        ret = 0
        while True:
            b = self.byte()
            ret += (b & 0x7F) << bits
            bits += 7
            if not (b & 0x80) or bits >= 0x1D:
                return ret


class Writer:
    def __init__(self):
        self.b = bytearray()

    def byte(self, v: int) -> None:
        self.b.append(v & 0xFF)

    def sbyte(self, v: int) -> None:
        self.b.append(v & 0xFF)

    def word(self, v: int) -> None:
        self.b += struct.pack("<H", v & 0xFFFF)

    def sword(self, v: int) -> None:
        self.word(v & 0xFFFF)

    def dword(self, v: int) -> None:
        self.b += struct.pack("<I", v & 0xFFFFFFFF)

    def varint(self, v: int) -> None:              # encodeInt
        v = int(v)
        while True:
            if v < 0x80:
                self.byte(v)
                return
            self.byte(0x80 | (v & 0x7F))
            v >>= 7

    def bytes(self) -> bytes:
        return bytes(self.b)


def _enc_str(w: Writer, s: str) -> None:
    b = s.encode("utf-8")
    w.varint(len(b))
    w.b += b


def _dec_str(r: Reader) -> str:
    n = r.varint()
    s = r.d[r.p:r.p + n]
    r.p += n
    return s.decode("utf-8", errors="replace")


# ---- 序列化记录（v16/v17 的 items.dat） ------------------------------------

def read_serial_records(path: str) -> List[list]:
    if not os.path.isfile(path):
        return []
    raw = open(path, "rb").read()
    if len(raw) < 4:
        return []
    numrec = struct.unpack_from("<I", raw, 0)[0] >> 3
    out = []
    for i in range(numrec):
        off, length = struct.unpack_from("<II", raw, i * 8)
        r = Reader(raw, off)
        rec = []
        while r.p < off + length:
            t = chr(r.byte())
            if t == "0":
                rec.append(None)
            elif t == "T":
                rec.append(True)
            elif t == "F":
                rec.append(False)
            elif t == '"':
                rec.append(_dec_str(r))
            elif t == "i":
                rec.append(r.varint())
            else:
                break
        out.append(rec)
    return out


def write_serial_records(path: str, records: List[list]) -> None:
    body = bytearray()
    table = bytearray()
    offset = len(records) * 8
    for rec in records:
        w = Writer()
        for f in (rec or []):
            if f is None:
                w.byte(ord("0"))
            elif f is True:
                w.byte(ord("T"))
            elif f is False:
                w.byte(ord("F"))
            elif isinstance(f, str):
                w.byte(ord('"'))
                _enc_str(w, f)
            elif isinstance(f, (int, float)):
                w.byte(ord("i"))
                w.varint(int(f))
        chunk = w.bytes()
        table += struct.pack("<II", offset, len(chunk))
        body += chunk
        offset += len(chunk)
    with open(path, "wb") as f:
        f.write(bytes(table) + bytes(body))


def _dword_table_list(raw: bytes, count: int, rec_size: int) -> List[List[int]]:
    """「dword 表 + 定长记录」格式（attacksRS / evolutions / eggEmerald）。"""
    out: List[List[int]] = []
    for i in range(count):
        if (i + 1) * 8 + 4 > len(raw):
            out.append([])
            continue
        off, length = struct.unpack_from("<II", raw, i * 8)
        n = length // rec_size
        recs = []
        for j in range(n):
            p = off + j * rec_size
            recs.append(list(raw[p:p + rec_size]))
        out.append(recs)
    return out


def _write_dword_table_list(path: str, data: List[List[bytes]], count: int) -> None:
    table = bytearray()
    body = bytearray()
    offset = count * 8
    for i in range(count):
        recs = data[i] if i < len(data) else []
        table += struct.pack("<II", offset, sum(len(x) for x in recs))
        for x in recs:
            body += x
            offset += len(x)
    with open(path, "wb") as f:
        f.write(bytes(table) + bytes(body))


# ---------------------------------------------------------------------------
# 文件注册表
# ---------------------------------------------------------------------------

_TYPES_SCHEMA = [
    ("Name", "real_name", "s", None),
    ("InternalName", "id", "n", None),
    ("IsPseudoType", "pseudo_type", "b", None),
    ("IsSpecialType", "special_type", "b", None),
    ("Weaknesses", "weaknesses", "*s", None),
    ("Resistances", "resistances", "*s", None),
    ("Immunities", "immunities", "*s", None),
]

_ABIL_SCHEMA = [
    ("IdNumber", "id_number", "v", None),
    ("InternalName", "id", "n", None),
    ("Name", "real_name", "s", None),
    ("Description", "real_description", "q", None),
]

_ITEM_SCHEMA = [
    ("IdNumber", "id_number", "v", None),
    ("InternalName", "id", "n", None),
    ("Name", "real_name", "s", None),
    ("NamePlural", "real_name_plural", "s", None),
    ("Pocket", "pocket", "v", None),
    ("Price", "price", "u", None),
    ("Description", "real_description", "q", None),
    ("FieldUse", "field_use", "u", None),
    ("BattleUse", "battle_use", "u", None),
    ("Type", "type", "u", None),
    ("Move", "move", "e", None),
]

_MOVE_SCHEMA = [
    ("IdNumber", "id_number", "v", None),
    ("InternalName", "id", "n", None),
    ("Name", "real_name", "s", None),
    ("FunctionCode", "function_code", "x", None),
    ("BaseDamage", "base_damage", "u", None),
    ("Type", "type", "e", None),
    ("Category", "category", "e", PE.ENUM_CATEGORY),
    ("Accuracy", "accuracy", "u", None),
    ("TotalPP", "total_pp", "u", None),
    ("EffectChance", "effect_chance", "u", None),
    ("Target", "target", "y", None),
    ("Priority", "priority", "i", None),
    ("Flags", "flags", "s", None),
    ("Description", "real_description", "q", None),
]

# 宝可梦：v16/v17/v18 都用 [编号] 段 + 键值（键名基本一致）
_POKEMON_SCHEMA = {
    "v16": [
        ("InternalName", "id", "n", None),
        ("Name", "real_name", "s", None),
        ("Kind", "kind", "s", None),
        ("Pokedex", "pokedex", "q", None),
        ("Type1", "type1", "e", None),
        ("Type2", "type2", "e", None),
        ("BaseStats", "base_stats", "uuuuuu", None),
        ("EffortPoints", "evs", "uuuuuu", None),
        ("BaseEXP", "base_exp", "v", None),
        ("GrowthRate", "growth_rate", "e", None),
        ("GenderRate", "gender_rate", "e", None),
        ("Rareness", "rareness", "u", None),
        ("Happiness", "happiness", "u", None),
        ("Abilities", "abilities", "*e", None),
        ("HiddenAbility", "hidden_abilities", "*e", None),
        ("Moves", "moves", "*ue", None),
        ("EggMoves", "egg_moves", "*e", None),
        ("Compatibility", "compatibility", "*e", None),
        ("StepsToHatch", "steps_to_hatch", "v", None),
        ("WildItemCommon", "wild_item_common", "e", None),
        ("WildItemUncommon", "wild_item_uncommon", "e", None),
        ("WildItemRare", "wild_item_rare", "e", None),
        ("Incense", "incense", "e", None),
        ("Height", "height", "f", None),
        ("Weight", "weight", "f", None),
        ("Color", "color", "e", None),
        ("Shape", "shape", "u", None),
        ("Habitat", "habitat", "e", None),
        ("FormNames", "form_names", "q", None),
        ("RegionalNumbers", "regional_numbers", "*u", None),
        ("Evolutions", "evolutions", "*ses", None),
        ("BattlerPlayerY", "battler_player_y", "i", None),
        ("BattlerEnemyY", "battler_enemy_y", "i", None),
        ("BattlerAltitude", "battler_altitude", "i", None),
    ],
    "v17": [
        ("InternalName", "id", "n", None),
        ("Name", "real_name", "s", None),
        ("Kind", "kind", "s", None),
        ("Pokedex", "pokedex", "q", None),
        ("Type1", "type1", "e", None),
        ("Type2", "type2", "e", None),
        ("BaseStats", "base_stats", "uuuuuu", None),
        ("EffortPoints", "evs", "uuuuuu", None),
        ("BaseEXP", "base_exp", "v", None),
        ("GrowthRate", "growth_rate", "e", None),
        ("GenderRate", "gender_rate", "e", None),
        ("Rareness", "rareness", "u", None),
        ("Happiness", "happiness", "u", None),
        ("Abilities", "abilities", "*e", None),
        ("HiddenAbility", "hidden_abilities", "*e", None),
        ("Moves", "moves", "*ue", None),
        ("EggMoves", "egg_moves", "*e", None),
        ("Compatibility", "compatibility", "*e", None),
        ("StepsToHatch", "steps_to_hatch", "v", None),
        ("WildItemCommon", "wild_item_common", "e", None),
        ("WildItemUncommon", "wild_item_uncommon", "e", None),
        ("WildItemRare", "wild_item_rare", "e", None),
        ("Incense", "incense", "e", None),
        ("Height", "height", "f", None),
        ("Weight", "weight", "f", None),
        ("Color", "color", "e", None),
        ("Shape", "shape", "u", None),
        ("Habitat", "habitat", "e", None),
        ("FormName", "form_names", "q", None),
        ("RegionalNumbers", "regional_numbers", "*u", None),
        ("Evolutions", "evolutions", "*ses", None),
        ("BattlerPlayerY", "battler_player_y", "i", None),
        ("BattlerEnemyY", "battler_enemy_y", "i", None),
        ("BattlerAltitude", "battler_altitude", "i", None),
    ],
}
_POKEMON_SCHEMA["v18"] = list(_POKEMON_SCHEMA["v17"])

_META_GLOBAL_SCHEMA = [
    ("Home", "home", "uuuu", None),
    ("WildBattleBGM", "wild_battle_BGM", "s", None),
    ("TrainerBattleBGM", "trainer_battle_BGM", "s", None),
    ("WildVictoryME", "wild_victory_ME", "s", None),
    ("TrainerVictoryME", "trainer_victory_ME", "s", None),
    ("WildCaptureME", "wild_capture_ME", "s", None),
    ("SurfBGM", "surf_BGM", "s", None),
    ("BicycleBGM", "bicycle_BGM", "s", None),
    ("PlayerA", "player_A", "e8s", None),
    ("PlayerB", "player_B", "e8s", None),
    ("PlayerC", "player_C", "e8s", None),
    ("PlayerD", "player_D", "e8s", None),
    ("PlayerE", "player_E", "e8s", None),
    ("PlayerF", "player_F", "e8s", None),
    ("PlayerG", "player_G", "e8s", None),
    ("PlayerH", "player_H", "e8s", None),
]

_META_MAP_SCHEMA = [
    ("Outdoor", "outdoor", "b", None),
    ("ShowArea", "show_area", "b", None),
    ("Bicycle", "bicycle", "b", None),
    ("BicycleAlways", "bicycle_always", "b", None),
    ("HealingSpot", "healing_spot", "uuu", None),
    ("Weather", "weather", "e", None),
    ("MapPosition", "map_position", "uuu", None),
    ("DiveMap", "dive_map", "u", None),
    ("DarkMap", "dark_map", "b", None),
    ("SafariMap", "safari_map", "b", None),
    ("SnapEdges", "snap_edges", "b", None),
    ("Dungeon", "dungeon", "b", None),
    ("BattleBack", "battle_back", "s", None),
    ("WildBattleBGM", "wild_battle_BGM", "s", None),
    ("TrainerBattleBGM", "trainer_battle_BGM", "s", None),
    ("WildVictoryME", "wild_victory_ME", "s", None),
    ("TrainerVictoryME", "trainer_victory_ME", "s", None),
    ("WildCaptureME", "wild_capture_ME", "s", None),
    ("MapSize", "map_size", "us", None),
    ("Environment", "environment", "e", None),
]

_TOWNMAP_SCHEMA = [
    ("Name", "name", "s", None),
    ("Filename", "filename", "s", None),
    ("Point", "point", "uussUUUU", None),
]

_TRAINERTYPE_SCHEMA = [
    ("IdNumber", "id_number", "u", None),
    ("InternalName", "id", "n", None),
    ("Name", "real_name", "s", None),
    ("BaseMoney", "base_money", "u", None),
    ("BattleBGM", "battle_BGM", "s", None),
    ("VictoryME", "victory_ME", "s", None),
    ("IntroME", "intro_ME", "s", None),
    ("Gender", "gender", "e", PE.ENUM_GENDER),
    ("SkillLevel", "skill_level", "u", None),
    ("SkillCode", "skill_code", "s", None),
]

# v18 的训练家是段式（和 v19 很像），v16/v17 是「一行一条」的老格式
_TRAINER18_SCHEMA = [
    ("LoseText", "lose_text", "q", None),
    ("Items", "items", "*e", None),
]
_TRAINER18_SUB = [
    ("Name", "name", "s", None),
    ("Form", "form", "u", None),
    ("Gender", "gender", "s", None),
    ("Shiny", "shininess", "b", None),
    ("Shadow", "shadowness", "b", None),
    ("Moves", "moves", "*e", None),
    ("Ability", "ability_flag", "u", None),
    ("Item", "item", "e", None),
    ("Nature", "nature", "e", None),
    ("NatureBias", "nature_bias", "i", None),
    ("IV", "iv", "u", None),
    ("Happiness", "happiness", "u", None),
    ("Ball", "poke_ball", "u", None),
]

_TM_SCHEMA = [
    ("IdNumber", "id_number", "v", None),
    ("Moves", "moves", "*e", None),
]


def _spec(key: str, name: str, desc: str, dat: List[str], fname: Dict[str, str],
          schema: Dict[str, list], style: str = "line", editor: str = "generic",
          keymode: str = "array", sub: Optional[Dict[str, list]] = None) -> dict:
    return {
        "key": key, "name": name, "desc": desc, "dat": dat,
        "fname": fname, "schema": schema, "cls": None, "keymode": keymode,
        "editor": editor,
        "style": {f: style for f in FAMILIES},
        "sub_schema": sub or {},
        "legacy": True,
    }


_NAMES = {
    "types": "属性", "abilities": "特性", "moves": "招式", "items": "道具",
    "pokemon": "宝可梦", "trainer_types": "训练家类型", "trainers": "训练家",
    "metadata": "元数据", "town_map": "区域地图", "map_connections": "地图连接",
    "berry_plants": "树果", "phone": "电话消息", "encounters": "野生遭遇",
    "tm": "招式机", "shadow_movesets": "暗黑招式", "trainer_lists": "对战设施名单",
    "regional_dexes": "地区图鉴",
}
_DESCS = {
    "types": "属性的相克关系（这些版本没有图标位置）",
    "abilities": "特性的名字与描述（名字表由游戏重编译时写入脚本）",
    "moves": "招式的威力、命中、PP 与描述",
    "items": "道具的名字、口袋、价格与描述",
    "pokemon": "物种的种族值、特性、进化等主数据",
    "trainer_types": "训练家类别的名字与金钱",
    "trainers": "每个训练家的队伍与台词",
    "metadata": "全局设置与每张地图的元数据",
    "town_map": "城镇地图的区域与地点",
    "map_connections": "地图之间的出入口",
    "berry_plants": "树果的生长时间与产量",
    "phone": "训练师的来电问候与台词",
    "encounters": "每张地图的野生宝可梦与概率",
    "tm": "每个招式机能教的招式",
    "shadow_movesets": "暗黑宝可梦的专属招式",
    "trainer_lists": "对战塔／ cups 的训练家与宝可梦名单",
    "regional_dexes": "各地区图鉴的收录顺序",
}


def specs(family: str) -> List[dict]:
    fam = _family_of(family)
    out = []

    def add(key, dat, schema, style="line", editor="generic", keymode="array",
            sub=None):
        out.append(_spec(key, _NAMES[key], _DESCS[key], dat,
                         {f: _fname(key, f) for f in FAMILIES},
                         schema, style, editor, keymode, sub))

    add("types", ["types.dat"], {f: _TYPES_SCHEMA for f in FAMILIES},
        style="section")
    add("abilities", ["abilities.dat"], {f: _ABIL_SCHEMA for f in FAMILIES})
    add("moves", ["moves.dat"], {f: _MOVE_SCHEMA for f in FAMILIES})
    add("items", ["items.dat"], {f: _ITEM_SCHEMA for f in FAMILIES})
    add("pokemon", ["dexdata.dat"], {f: _POKEMON_SCHEMA[f] for f in FAMILIES},
        style="section")
    add("trainer_types", ["trainertypes.dat"],
        {f: _TRAINERTYPE_SCHEMA for f in FAMILIES})
    add("trainers", ["trainers.dat"], {f: _TRAINER18_SCHEMA for f in FAMILIES},
        style="section", editor="trainers18", keymode="array",
        sub={f: _TRAINER18_SUB for f in FAMILIES})
    add("metadata", ["metadata.dat"],
        {"v16": _META_GLOBAL_SCHEMA, "v17": _META_GLOBAL_SCHEMA,
         "v18": _META_GLOBAL_SCHEMA}, style="section", editor="legacy_meta")
    add("town_map", ["townmap.dat"], {f: _TOWNMAP_SCHEMA for f in FAMILIES},
        style="section")
    add("map_connections", ["connections.dat"], {f: [] for f in FAMILIES},
        editor="connections")
    add("berry_plants", ["berryplants.dat"], {f: [] for f in FAMILIES},
        style="kv", editor="legacy_berry")
    add("phone", ["phone.dat"], {f: [] for f in FAMILIES}, editor="legacy_phone")
    add("encounters", ["encounters.dat"], {f: [] for f in FAMILIES},
        editor="legacy_enc")
    add("tm", ["tm.dat"], {f: _TM_SCHEMA for f in FAMILIES}, style="section")
    add("shadow_movesets", ["shadowmoves.dat"], {f: [] for f in FAMILIES},
        style="kv", editor="legacy_shadow")
    add("trainer_lists", ["trainerlists.dat"], {f: [] for f in FAMILIES},
        editor="facility_legacy")
    add("regional_dexes", ["regionals.dat"], {f: [] for f in FAMILIES},
        editor="legacy_regional")
    # v18 的文件名有几处不同
    for s in out:
        if fam == "v18":
            if s["key"] == "town_map":
                s["dat"] = ["town_map.dat"]
            elif s["key"] == "map_connections":
                s["dat"] = ["map_connections.dat"]
            elif s["key"] == "berry_plants":
                s["dat"] = ["berry_plants.dat"]
            elif s["key"] == "shadow_movesets":
                s["dat"] = ["shadow_movesets.dat"]
            elif s["key"] == "trainer_lists":
                s["dat"] = ["trainer_lists.dat"]
            elif s["key"] == "regional_dexes":
                s["dat"] = ["regional_dexes.dat"]
            elif s["key"] == "pokemon":
                s["dat"] = ["species.dat"]
    return out


_LEGACY_FNAMES = {
    "v18": {
        "pokemon": "pokemon.txt", "town_map": "townmap.txt",
        "map_connections": "connections.txt", "berry_plants": "berryplants.txt",
        "shadow_movesets": "shadowmoves.txt", "trainer_lists": "trainerlists.txt",
        "regional_dexes": "regionaldexes.txt", "trainers": "trainers.txt",
        "metadata": "metadata.txt", "tm": "tm.txt",
        "trainer_types": "trainertypes.txt", "encounters": "encounters.txt",
        "phone": "phone.txt", "types": "types.txt", "moves": "moves.txt",
        "items": "items.txt", "abilities": "abilities.txt",
    },
}


def _fname(key: str, family: str) -> str:
    fam = _family_of(family)
    special = _LEGACY_FNAMES.get(fam, {})
    if key in special:
        return special[key]
    return {
        "types": "types.txt", "abilities": "abilities.txt", "moves": "moves.txt",
        "items": "items.txt", "pokemon": "pokemon.txt",
        "trainer_types": "trainertypes.txt", "trainers": "trainers.txt",
        "metadata": "metadata.txt", "town_map": "townmap.txt",
        "map_connections": "connections.txt", "berry_plants": "berryplants.txt",
        "phone": "phone.txt", "encounters": "encounters.txt", "tm": "tm.txt",
        "shadow_movesets": "shadowmoves.txt",
        "trainer_lists": "trainerlists.txt",
        "regional_dexes": "regionaldexes.txt",
    }[key]


def spec_for(key: str, family: str) -> Optional[dict]:
    for s in specs(family):
        if s["key"] == key:
            return s
    return None


# ---------------------------------------------------------------------------
# 宝可梦：v16/v17 的 dexdata（76 字节固定布局）
# ---------------------------------------------------------------------------
#   偏移来自官方 pbCompilePokemonData 的 requiredtypes/optionaltypes：
#   多字节字段按 schema 里的大小写（e=1 字节 / E=2 字节）累加 offset。
DEX_OFFSETS = {
    # 键       偏移   字节数
    "Color": (6, 1), "Habitat": (7, 1), "Type1": (8, 1), "Type2": (9, 1),
    "BaseStats": (10, 6), "Rareness": (16, 1), "Shape": (17, 1),
    "GenderRate": (18, 1), "Happiness": (19, 1), "GrowthRate": (20, 1),
    "StepsToHatch": (21, 2), "EffortPoints": (23, 6),
    "Compatibility": (31, 3), "Height": (33, 2), "Weight": (35, 2),
    "BaseEXP": (38, 2), "HiddenAbility": (40, 8),
    "WildItemCommon": (48, 2), "WildItemUncommon": (50, 2),
    "WildItemRare": (52, 2), "Incense": (54, 2), "Abilities": (2, 3),
}
DEX_SIZE = 76

_GENDER = {"AlwaysMale": 0, "FemaleOneEighth": 31, "Female25Percent": 63,
           "Female50Percent": 127, "Female75Percent": 191,
           "FemaleSevenEighths": 223, "AlwaysFemale": 254, "Genderless": 255}
_GROWTH = {"Medium": 0, "MediumFast": 0, "Erratic": 1, "Fluctuating": 2,
           "Parabolic": 3, "MediumSlow": 3, "Fast": 4, "Slow": 5}
_HABITAT = ["", "Grassland", "Forest", "WatersEdge", "Sea", "Cave",
            "Mountain", "RoughTerrain", "Urban", "Rare"]


def _dex_bytes(name: str, val: Any, layout: dict) -> Tuple[int, bytes]:
    """按字段名把值转成 (偏移, 字节串)；layout 来自游戏自己的 schema。"""
    off, size = layout.get(name, DEX_OFFSETS[name])
    if name == "BaseStats":
        b = bytes(int(x) & 0xFF for x in val)
        return off, b.ljust(6, b"\0")[:6]
    if name == "EffortPoints":
        b = bytes(int(x) & 0xFF for x in val)
        return off, b.ljust(6, b"\0")[:6]
    if name in ("Abilities", "HiddenAbility", "Compatibility"):
        ab = list(val)
        buf = bytearray()
        while len(buf) < size:
            v = ab.pop(0) if ab else 0
            left = size - len(buf)
            if left >= 2 and v > 0xFF:
                buf += struct.pack("<H", int(v) & 0xFFFF)
            elif left >= 2 and len(ab) and any(x > 0xFF for x in ab):
                buf += struct.pack("<H", int(v) & 0xFFFF)
            else:
                buf.append(int(v) & 0xFF)
        return off, bytes(buf[:size])
    if name == "Height" or name == "Weight":
        return off, struct.pack("<H", int(round(float(val) * 10)) & 0xFFFF)
    if size == 2:
        return off, struct.pack("<H", int(val) & 0xFFFF)
    return off, bytes([int(val) & 0xFF])


def _dex_get(blob: bytes, name: str, layout: Optional[dict] = None) -> Any:
    off, size = (layout or DEX_OFFSETS).get(name, DEX_OFFSETS[name])
    b = blob[off:off + size]
    if size == 1:
        return b[0] if b else 0
    return struct.unpack("<H", b)[0]


# ---------------------------------------------------------------------------
# 提取（.dat -> txt）
# ---------------------------------------------------------------------------

def _load(game_root: str, dat: str) -> Any:
    p = os.path.join(game_root, "Data", dat)
    if not os.path.isfile(p) or os.path.getsize(p) < 4:
        return None
    try:
        return rmarshal.load(p)
    except Exception:
        try:
            return open(p, "rb").read()
        except OSError:
            return None


def _txt(game_root: str, key: str, family: str) -> Optional[str]:
    p = os.path.join(PE.pbs_dir(game_root), _fname(key, family))
    if os.path.isfile(p):
        try:
            return open(p, "rb").read().decode("utf-8-sig", errors="replace")
        except OSError:
            return None
    return None


# ---------------------------------------------------------------------------
# 名字来源：v16-18 的 .dat 里**没有名字**（dexdata / moves 二进制只存数值），
# 名字存在 Data/messages.dat 的消息表里（按 MessageTypes 下标）：
#   1=Species  2=Kinds  3=Pokedex  5=Moves  7=Items  8=ItemPlurals  12=Types
# 游戏若是中文版，语言包（zh.dat / Chinese.dat / intl_chinese.dat）里有中文名，
# 优先用带中文的那份 —— 用户在 PBS 编辑里看到的才是游戏里真正的名字。
# ---------------------------------------------------------------------------
_MSG_FILES = ("messages.dat", "zh.dat", "Chinese.dat", "chinese.dat",
              "intl_chinese.dat", "intl_chinese_cn.dat")
_MSG_CACHE: Dict[Tuple[str, int], list] = {}


def _cjk_len(s: Any) -> int:
    return sum(1 for ch in str(s) if "\u4e00" <= ch <= "\u9fff")


def _msg_array(game_root: str, idx: int) -> list:
    """取消息表第 idx 段（species/moves/...）→ list；带缓存。"""
    ck = (game_root, idx)
    if ck in _MSG_CACHE:
        return _MSG_CACHE[ck]
    best, best_score = [], -1
    for fn in _MSG_FILES:
        p = os.path.join(game_root, "Data", fn)
        if not os.path.isfile(p):
            continue
        try:
            obj = _load(game_root, fn)
        except Exception:
            continue
        if not isinstance(obj, list) or len(obj) <= idx:
            continue
        arr = obj[idx]
        if not isinstance(arr, list):
            continue
        # 中文越多越优先（中文版直接给中文名）；messages.dat 是基表，平局优先
        score = sum(_cjk_len(x) for x in arr[:80])
        if fn == "messages.dat":
            score += 1
        if score > best_score:
            best_score, best = score, arr
    _MSG_CACHE[ck] = best
    return best


def _msg_name(game_root: str, idx: int, sid: int) -> str:
    arr = _msg_array(game_root, idx)
    if 0 <= sid < len(arr):
        v = arr[sid]
        return "" if v is None else str(v)
    return ""


def _rev_const(game_root: str, cls: str) -> Dict[int, str]:
    """编号 → 内部名（脚本常量表反过来）。"""
    return {v: k for k, v in const_map(game_root, cls).items()}


def extract_spec(spec: dict, family: str, game_root: str
                 ) -> Tuple[bool, str, str]:
    """
    提取一个文件。

    ★ 老版本游戏的 .dat 里**没有名字/描述**（那些存在语言包与脚本常量里），
      所以只要游戏自带 PBS 就直接用它的；只有 PBS 缺失时才从 .dat 还原，
      能还原多少算多少（还原不了的字段留空并在说明里讲清楚）。
    """
    key = spec["key"]
    txt = _txt(game_root, key, family)
    if txt and txt.strip():
        return True, txt, "用游戏自带的 txt"
    fn = getattr(_EXTRACT, "f_" + key, None)
    if fn is None:
        return False, ("这一版没有 PBS/%s，而 .dat 里不含名字信息，无法还原。"
                       "请把游戏自带的 PBS 目录放回去。" % _fname(key, family)), ""
    try:
        out = fn(game_root, family, spec)
    except Exception as e:                                       # noqa: BLE001
        return False, "从 .dat 还原 %s 失败：%s" % (_fname(key, family), e), ""
    if out is None:
        return False, "找不到 Data/%s" % (spec["dat"][0]), ""
    return True, out, "从 .dat 还原"


class _EXTRACT:
    """提取函数集合（按 key 挂上去，见文件末尾）。"""


def _hdr() -> List[str]:
    return ["# See the documentation on the wiki to learn how to edit this file."]


def _lines_to_text(lines: List[str]) -> str:
    return "﻿" + PE.CRLF.join(lines) + PE.CRLF


def x_types(game_root: str, family: str, spec: dict):
    data = _load(game_root, spec["dat"][0])
    if not isinstance(data, list) or len(data) < 3:
        return None
    pseudo, special, chart = data[0], data[1], data[2]
    count = 0
    if chart:
        count = int(len(chart) ** 0.5)
    if count == 0:
        return None
    names = _type_internal_names(game_root, count)
    lines = _hdr()
    for i in range(count):
        lines.append(PE._SEP)
        lines.append("[%d]" % i)
        lines.append("Name = %s" % (names[i] or "TYPE%d" % i))
        lines.append("InternalName = %s" % (names[i] or "TYPE%d" % i))
        if i in (pseudo or []):
            lines.append("IsPseudoType = true")
        if i in (special or []):
            lines.append("IsSpecialType = true")
        weak, res, imm = [], [], []
        for j in range(count):
            v = chart[i + j * count] if i + j * count < len(chart) else 2
            nm = names[j] or ("TYPE%d" % j)
            if v == 4:
                weak.append(nm)
            elif v == 1:
                res.append(nm)
            elif v == 0:
                imm.append(nm)
        if weak:
            lines.append("Weaknesses = %s" % ",".join(weak))
        if res:
            lines.append("Resistances = %s" % ",".join(res))
        if imm:
            lines.append("Immunities = %s" % ",".join(imm))
    return _lines_to_text(lines)


def _type_internal_names(game_root: str, count: int) -> List[str]:
    """从脚本常量（class PBTypes）里读属性的内部名。"""
    out = [""] * count
    try:
        import game_scripts as GS
        for _k, title, src in GS.iter_named_scripts(game_root):
            if not src or "class PBTypes" not in src:
                continue
            inside = False
            for ln in src.splitlines():
                t = ln.strip()
                if t.startswith("class PBTypes"):
                    inside = True
                    continue
                if inside:
                    if t.startswith("end"):
                        inside = False
                        continue
                    if re_m := __import__("re").match(
                            r"^([A-Za-z_]\w*)\s*=\s*(\d+)$", t):
                        idx = int(re_m.group(2))
                        if 0 <= idx < count:
                            out[idx] = re_m.group(1)
            break
    except Exception:
        pass
    return out


def x_moves(game_root: str, family: str, spec: dict):
    dat = spec["dat"][0]
    if _family_of(family) == "v18":
        data = _load(game_root, dat)
        if not isinstance(data, list):
            return None
        rows = data
    else:
        p = os.path.join(game_root, "Data", dat)
        if not os.path.isfile(p):
            return None
        raw = open(p, "rb").read()
        n = len(raw) // 14
        rows = []
        for i in range(n):
            b = raw[i * 14:(i + 1) * 14]
            if len(b) < 14:
                break
            rows.append([i, None, None, struct.unpack_from("<H", b, 0)[0],
                         b[2], b[3], b[4], b[5], b[6], b[7],
                         struct.unpack_from("<H", b, 8)[0], b[10],
                         struct.unpack_from("<H", b, 11)[0], None])
    # ★ 名字/内部名：v16/17 的 moves.dat 只存数值，名字在消息表(5)与常量表里
    names = _msg_array(game_root, 5)
    rev = _rev_const(game_root, "PBMoves")
    for rec in rows:
        if not isinstance(rec, list):        # v18 偶尔是元组，不可写就跳过
            continue
        try:
            sid = int(rec[0])
        except (TypeError, ValueError, IndexError):
            continue
        if len(rec) > 1 and not rec[1]:
            rec[1] = rev.get(sid, "")
        if len(rec) > 2 and not rec[2] and 0 <= sid < len(names):
            rec[2] = names[sid]
    lines = _hdr()
    schema = spec["schema"][_family_of(family)]
    for i, rec in enumerate(rows):
        if not rec or rec[0] is None:
            continue
        if rec[3] in (0, None) and (rec[4] or 0) == 0:
            continue
        lines.append(_csv_line(rec, schema, family))
    return _lines_to_text(lines)


def x_items(game_root: str, family: str, spec: dict):
    dat = spec["dat"][0]
    if _family_of(family) == "v18":
        data = _load(game_root, dat)
        if not isinstance(data, list):
            return None
        rows = [r for r in data if r]
    else:
        rows = [r for r in read_serial_records(
            os.path.join(game_root, "Data", dat)) if r and r[0]]
    schema = spec["schema"][_family_of(family)]
    lines = _hdr()
    for rec in rows:
        lines.append(_csv_line(rec, schema, family))
    return _lines_to_text(lines)


def x_trainer_types(game_root: str, family: str, spec: dict):
    data = _load(game_root, spec["dat"][0])
    if not isinstance(data, list):
        return None
    schema = spec["schema"][_family_of(family)]
    lines = _hdr()
    for rec in data:
        if not rec:
            continue
        lines.append(_csv_line(rec, schema, family))
    return _lines_to_text(lines)


def _csv_line(rec: list, schema: list, family: str) -> str:
    """按 schema 把记录写成一行 CSV。"""
    parts = []
    for i, (key, _ivar, ctype, enum) in enumerate(schema):
        if i >= len(rec):
            parts.append("")
            continue
        v = rec[i]
        if v is None:
            parts.append("")
        elif isinstance(v, (list, tuple)):
            parts.append(",".join(str(x) for x in v))
        elif ctype == "x":
            # 有些版本（v18）把招式效果码直接存成字符串 "16F"
            if isinstance(v, str):
                parts.append(v.strip() or "000")
            else:
                parts.append("%03X" % int(v))
        elif ctype[0] == "b":
            parts.append("true" if v else "false")
        elif ctype == "q" or key in ("Description", "Pokedex", "LoseText"):
            parts.append(PE.csv_quote(str(v), always=True))
        elif ctype == "f":
            parts.append(("%g" % float(v)))
        else:
            parts.append(str(v))
    return ",".join(parts)


def x_map_connections(game_root: str, family: str, spec: dict):
    data = _load(game_root, spec["dat"][0])
    if not isinstance(data, list):
        return None
    lines = _hdr()
    for rec in data:
        if rec:
            lines.append(",".join(str(x) for x in rec))
    return _lines_to_text(lines)


def x_tm(game_root: str, family: str, spec: dict):
    data = _load(game_root, spec["dat"][0])
    if not isinstance(data, list):
        return None
    lines = _hdr()
    for i, moves in enumerate(data):
        if not moves:
            continue
        lines.append(PE._SEP)
        lines.append("[%d]" % i)
        lines.append("Moves = %s" % ",".join(str(m) for m in moves))
    return _lines_to_text(lines)


def x_berry(game_root: str, family: str, spec: dict):
    data = _load(game_root, spec["dat"][0])
    if not isinstance(data, (dict, RHash)):
        return None
    items = list(data.items()) if isinstance(data, dict) else data.items()
    lines = _hdr()
    for k, v in items:
        v = list(v) if isinstance(v, (list, tuple)) else []
        lines.append("%s = %s" % (k, ",".join(str(x) for x in v)))
    return _lines_to_text(lines)


def x_shadow(game_root: str, family: str, spec: dict):
    data = _load(game_root, spec["dat"][0])
    if not isinstance(data, (dict, RHash)):
        return None
    items = list(data.items()) if isinstance(data, dict) else data.items()
    lines = _hdr()
    for k, v in items:
        v = list(v) if isinstance(v, (list, tuple)) else []
        lines.append("%s = %s" % (k, ",".join(str(x) for x in v)))
    return _lines_to_text(lines)


def x_trainer_lists(game_root: str, family: str, spec: dict):
    data = _load(game_root, spec["dat"][0])
    if not isinstance(data, list):
        return None
    lines = _hdr()
    for rec in data:
        if not isinstance(rec, (list, tuple)) or len(rec) < 5:
            continue
        lines.append(PE._SEP)
        lines.append("[%s]" % ("DefaultTrainerList" if
                               (len(rec) > 5 and rec[5]) else "TrainerList"))
        lines.append("Trainers = %s" % rec[3])
        lines.append("Pokemon = %s" % rec[4])
        if len(rec) > 2 and rec[2] and not (len(rec) > 5 and rec[5]):
            lines.append("Challenges = %s" % ",".join(str(x) for x in rec[2]))
    return _lines_to_text(lines)


def x_metadata(game_root: str, family: str, spec: dict):
    data = _load(game_root, spec["dat"][0])
    if not isinstance(data, list):
        return None
    lines = _hdr()
    for mid, rec in enumerate(data):
        if not rec:
            continue
        use = _META_GLOBAL_SCHEMA if mid == 0 else _META_MAP_SCHEMA
        lines.append(PE._SEP)
        lines.append("[%03d]" % mid)
        for i, (key, _iv, ctype, _e) in enumerate(use):
            if i >= len(rec) or rec[i] is None:
                continue
            v = rec[i]
            if isinstance(v, (list, tuple)):
                parts = []
                for x in v:
                    parts.append("" if x is None else str(x))
                txt = ",".join(parts)
            elif ctype[0] == "b":
                if not v:
                    continue
                txt = "true"
            else:
                txt = str(v)
            lines.append("%s = %s" % (key, txt))
    return _lines_to_text(lines)


def x_townmap(game_root: str, family: str, spec: dict):
    data = _load(game_root, spec["dat"][0])
    if not isinstance(data, list):
        return None
    lines = _hdr()
    for i, rec in enumerate(data):
        if not rec:
            continue
        lines.append(PE._SEP)
        lines.append("[%d]" % i)
        if len(rec) > 0 and rec[0]:
            lines.append("Name = %s" % rec[0])
        if len(rec) > 1 and rec[1]:
            lines.append("Filename = %s" % rec[1])
        for pt in (rec[2] if len(rec) > 2 and rec[2] else []):
            lines.append("Point = %s" % ",".join(
                "" if x is None else str(x) for x in pt))
    return _lines_to_text(lines)


def x_regional(game_root: str, family: str, spec: dict):
    if _family_of(family) == "v18":
        data = _load(game_root, spec["dat"][0])
        if not isinstance(data, list):
            return None
        lines = _hdr()
        for i, lst in enumerate(data):
            if not lst:
                continue
            lines.append(PE._SEP)
            lines.append("[%d]" % i)
            sp = [str(x) for x in lst if x]
            for j in range(0, len(sp), 12):
                lines.append(",".join(sp[j:j + 12]))
        return _lines_to_text(lines)
    p = os.path.join(game_root, "Data", spec["dat"][0])
    if not os.path.isfile(p):
        return None
    raw = open(p, "rb").read()
    if len(raw) < 8:
        return None
    n_dex, n_sp = struct.unpack_from("<II", raw, 0)
    lines = _hdr()
    for i in range(n_dex):
        lines.append(PE._SEP)
        lines.append("[%d]" % i)
        vals = []
        for j in range(n_sp):
            off = 8 + (i * n_sp + j) * 4
            if off + 4 > len(raw):
                break
            num = struct.unpack_from("<I", raw, off)[0]
            if num:
                vals.append(str(num))
        if vals:
            lines.append(",".join(vals))
    return _lines_to_text(lines)


def x_pokemon(game_root: str, family: str, spec: dict):
    """v16/v17：从 dexdata 还原；v18：从 species.dat 还原。"""
    fam = _family_of(family)
    if fam == "v18":
        data = _load(game_root, "species.dat")
        if not isinstance(data, list):
            return None
        lines = _hdr()
        rev = _rev_const(game_root, "PBSpecies")
        for sid, rec in enumerate(data):
            if not rec:
                continue
            lines.append(PE._SEP)
            lines.append("[%d]" % sid)
            iv = rev.get(sid, "")
            nm = _msg_name(game_root, 1, sid)
            if iv:
                lines.append("InternalName = %s" % iv)
            if nm:
                lines.append("Name = %s" % nm)
            if len(rec) > 0 and rec[0] is not None:
                lines.append("Type1 = %s" % rec[0])
            if len(rec) > 1 and rec[1] is not None:
                lines.append("Type2 = %s" % rec[1])
            bs = rec[2] if len(rec) > 2 and rec[2] else []
            if bs:
                lines.append("BaseStats = %s" % ",".join(str(x) for x in bs))
            evs = rec[6] if len(rec) > 6 and rec[6] else []
            if evs:
                lines.append("EffortPoints = %s" % ",".join(str(x)
                                                           for x in evs))
            for idx, key in ((3, "GenderRate"), (4, "GrowthRate"),
                             (5, "BaseExp"), (7, "CatchRate"),
                             (8, "Happiness"), (12, "HatchSteps")):
                if len(rec) > idx and rec[idx] is not None:
                    lines.append("%s = %s" % (key, rec[idx]))
            for idx, key in ((9, "Abilities"), (10, "HiddenAbilities"),
                             (18, "WildItemCommon"), (19, "WildItemUncommon"),
                             (20, "WildItemRare"), (22, "PokedexForm"),
                             (23, "MegaStone"), (24, "MegaMove"),
                             (25, "UnmegaForm"), (26, "MegaMessage"),
                             (11, "EggGroups"), (21, "Incense"),
                             (15, "Color"), (16, "Shape"), (17, "Habitat"),
                             (13, "Height"), (14, "Weight")):
                if len(rec) > idx and rec[idx] is not None:
                    v = rec[idx]
                    if isinstance(v, (list, tuple)):
                        if not v:
                            continue
                        v = ",".join(str(x) for x in v if x is not None)
                        if not v:
                            continue
                    lines.append("%s = %s" % (key, v))
        return _lines_to_text(lines)
    p = os.path.join(game_root, "Data", "dexdata.dat")
    if not os.path.isfile(p):
        return None
    raw = open(p, "rb").read()
    n = len(raw) // DEX_SIZE
    lines = _hdr()
    rev = _rev_const(game_root, "PBSpecies")
    for i in range(1, n):
        blob = raw[i * DEX_SIZE:(i + 1) * DEX_SIZE]
        if len(blob) < DEX_SIZE or not any(blob):
            continue
        lines.append(PE._SEP)
        lines.append("[%d]" % i)
        iv = rev.get(i, "")
        nm = _msg_name(game_root, 1, i)
        if iv:
            lines.append("InternalName = %s" % iv)
        if nm:
            lines.append("Name = %s" % nm)
        lines.append("Type1 = %d" % _dex_get(blob, "Type1"))
        lines.append("Type2 = %d" % _dex_get(blob, "Type2"))
        bs = list(blob[10:16])
        lines.append("BaseStats = %s" % ",".join(str(x) for x in bs))
        evs = list(blob[23:29])
        lines.append("EffortPoints = %s" % ",".join(str(x) for x in evs))
        lines.append("Rareness = %d" % blob[16])
        lines.append("GenderRate = %d" % blob[18])
        lines.append("GrowthRate = %d" % blob[20])
        lines.append("Happiness = %d" % blob[19])
        lines.append("StepsToHatch = %d" % _dex_get(blob, "StepsToHatch"))
        lines.append("BaseEXP = %d" % _dex_get(blob, "BaseEXP"))
        lines.append("Height = %s" % (_dex_get(blob, "Height") / 10.0))
        lines.append("Weight = %s" % (_dex_get(blob, "Weight") / 10.0))
        lines.append("Color = %d" % blob[6])
        lines.append("Habitat = %d" % blob[7])
        ab = [blob[2]] + list(struct.unpack_from("<H", blob, 3))
        lines.append("Abilities = %s" % ",".join(str(x) for x in ab if x))
        lines.append("Compatibility = %s,%d" % (
            blob[31], struct.unpack_from("<H", blob, 32)[0]))
    return _lines_to_text(lines)


for _name, _fn in (("f_types", x_types), ("f_moves", x_moves),
                   ("f_items", x_items), ("f_trainer_types", x_trainer_types),
                   ("f_map_connections", x_map_connections), ("f_tm", x_tm),
                   ("f_berry_plants", x_berry), ("f_shadow_movesets", x_shadow),
                   ("f_trainer_lists", x_trainer_lists),
                   ("f_metadata", x_metadata), ("f_town_map", x_townmap),
                   ("f_regional_dexes", x_regional), ("f_pokemon", x_pokemon)):
    setattr(_EXTRACT, _name, _fn)


# ---------------------------------------------------------------------------
# 脚本常量表（老版本的 id 对照表就在脚本里：PBMoves/PBItems/PBSpecies…）
# ---------------------------------------------------------------------------

_CONST_CACHE: Dict[Tuple[str, str], Dict[str, int]] = {}

_CONST_CLASSES = ("PBTypes", "PBAbilities", "PBMoves", "PBItems", "PBSpecies",
                  "PBTrainers", "PBColors", "PBHabitats", "PBEggGroups",
                  "PBEvolution", "PBNatures", "PBFieldWeather", "PBEnvironment",
                  "PBStats")


def const_map(game_root: str, cls: str) -> Dict[str, int]:
    """读脚本里的 `NAME=编号` 常量表（老版本的数据 id 就在这儿）。"""
    ck = (game_root, cls)
    if ck in _CONST_CACHE:
        return _CONST_CACHE[ck]
    out: Dict[str, int] = {}
    pat = re.compile(r"^(?:\s*)([A-Za-z_]\w*)\s*=\s*(\d+)\s*$")
    for _m, _k, _p, _name, src in _iter_scripts(game_root):
        if not src or (("class %s" % cls) not in src
                       and ("module %s" % cls) not in src):
            continue
        inside = False
        for ln in src.splitlines():
            t = ln.strip()
            if t.startswith("class %s" % cls) or t.startswith("module %s" % cls):
                inside = True
                continue
            if not inside:
                continue
            if (t == "end" or t.startswith("module ")
                    or t.startswith("class ")):
                inside = False
                continue
            m = pat.match(ln)
            if m and not m.group(1).isdigit():
                out.setdefault(m.group(1), int(m.group(2)))
        if out:
            break
    _CONST_CACHE[ck] = out
    return out



def _id_of(game_root: str, cls: str, name: str, default: int = 0) -> int:
    if name is None:
        return default
    s = str(name).strip()
    if s == "":
        return default
    if s.lstrip("-").isdigit():
        return int(s)
    return const_map(game_root, cls).get(s, default)


def _num(s: Any, default: int = 0) -> int:
    try:
        if s is None or str(s).strip() == "":
            return default
        return int(float(str(s)))
    except (TypeError, ValueError):
        return default


def _flt(s: Any, default: float = 0.0) -> float:
    try:
        if s is None or str(s).strip() == "":
            return default
        return float(str(s))
    except (TypeError, ValueError):
        return default


def _q(s: Any) -> str:
    """去掉 CSV 外层引号。"""
    if s is None:
        return ""
    return PE._unquote_csv(str(s))


def _backup(path: str) -> None:
    if os.path.isfile(path) and not os.path.isfile(path + ".orig"):
        import shutil
        shutil.copy2(path, path + ".orig")


def _save(path: str, obj: Any) -> None:
    _backup(path)
    with open(path, "wb") as f:
        f.write(rmarshal.dumps(obj))


# ---------------------------------------------------------------------------
# 编译（txt -> .dat）
# ---------------------------------------------------------------------------

def compile_spec(spec: dict, family: str, game_root: str,
                 txt_path: Optional[str] = None) -> Tuple[bool, str, str]:
    fam = _family_of(family)
    key = spec["key"]
    if txt_path is None:
        txt_path = os.path.join(PE.pbs_dir(game_root), _fname(key, family))
    if not os.path.isfile(txt_path):
        return False, "找不到 %s" % os.path.basename(txt_path), ""
    try:
        text = open(txt_path, "rb").read().decode("utf-8-sig",
                                                  errors="replace")
    except OSError as e:
        return False, "读取失败：%s" % e, ""
    fn = _COMPILE.get(key)
    if fn is None:
        # 脚本常量 / 语言包里才有的东西，交给官方编译器
        n, _msg = mark_for_recompile(game_root, family)
        return True, ("" if n else "没有可标记的 .dat"), \
            "已标记待重编译（游戏下次启动会重写 .dat）"
    try:
        return fn(spec, fam, game_root, text)
    except Exception as e:                                       # noqa: BLE001
        import traceback
        traceback.print_exc()
        return False, "编译失败：%s" % e, ""


def c_types(spec, fam, game_root, text):
    sections = PE.parse_sections(text)
    cmap = const_map(game_root, "PBTypes")
    rows = []
    for sec in sections:
        sid = _num(sec.name)
        rows.append((sid, sec))
    if not rows:
        return False, "没有解析出任何属性段", ""
    maxid = max(r[0] for r in rows)
    count = maxid + 1
    names = [None] * count
    pseudo, special = [], []
    weak = [set() for _ in range(count)]
    res = [set() for _ in range(count)]
    imm = [set() for _ in range(count)]
    for sid, sec in rows:
        if sid < 0 or sid >= count:
            continue
        for k, v in sec.fields:
            if k == "InternalName":
                names[sid] = _q(v)
            elif k == "IsPseudoType" and _q(v).lower() in ("true", "1", "yes"):
                pseudo.append(sid)
            elif k == "IsSpecialType" and _q(v).lower() in ("true", "1", "yes"):
                special.append(sid)
            elif k == "Weaknesses":
                weak[sid] = {_id_of(game_root, "PBTypes", x, -1)
                             for x in PE.split_csv(v) if x}
            elif k == "Resistances":
                res[sid] = {_id_of(game_root, "PBTypes", x, -1)
                            for x in PE.split_csv(v) if x}
            elif k == "Immunities":
                imm[sid] = {_id_of(game_root, "PBTypes", x, -1)
                            for x in PE.split_csv(v) if x}
    del cmap
    chart = [2] * (count * count)
    for i in range(count):
        for j in range(count):
            v = 2
            if i in weak and j in weak[i]:
                v = 4
            if i in res and j in res[i]:
                v = 1
            if i in imm and j in imm[i]:
                v = 0
            chart[i + j * count] = v
    pseudo = sorted(set(pseudo) | {i for i in range(count) if not names[i]})
    special = sorted(set(special))
    _save(os.path.join(game_root, "Data", spec["dat"][0]),
          [pseudo, special, chart])
    return True, "", "%d 种属性" % count


def _flag_bits(s: str) -> int:
    bits = 0
    for i, ch in enumerate("abcdefghijklmnop"):
        if ch in (s or ""):
            bits |= 1 << i
    return bits


def c_moves(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("﻿"):
            continue
        rows.append(PE.split_csv(line))
    if fam == "v18":
        arr: List[Any] = []
        for vals in rows:
            if not vals:
                continue
            mid = _num(vals[0])
            rec = [0] * 14
            rec[0] = mid
            rec[1] = _q(vals[1]) if len(vals) > 1 else ""
            rec[2] = _q(vals[2]) if len(vals) > 2 else ""
            rec[3] = _q(vals[3]) if len(vals) > 3 else "None"
            rec[4] = _num(vals[4]) if len(vals) > 4 else 0
            rec[5] = _id_of(game_root, "PBTypes", vals[5] if len(vals) > 5
                            else "", 0)
            cat = _q(vals[6]) if len(vals) > 6 else ""
            rec[6] = PE.ENUM_CATEGORY.get(cat, 2) if cat else 2
            rec[7] = _num(vals[7]) if len(vals) > 7 else 100
            rec[8] = _num(vals[8]) if len(vals) > 8 else 5
            rec[9] = _num(vals[9]) if len(vals) > 9 else 0
            rec[10] = _id_of(game_root, "PBTargets", vals[10]
                             if len(vals) > 10 else "", 0)
            rec[11] = _num(vals[11]) if len(vals) > 11 else 0
            rec[12] = _q(vals[12]) if len(vals) > 12 else ""
            rec[13] = _q(vals[13]) if len(vals) > 13 else ""
            while len(arr) <= mid:
                arr.append(None)
            arr[mid] = rec
        _save(path, arr)
        return True, "", "%d 个招式" % len(rows)
    maxid = 0
    recs = {}
    for vals in rows:
        if not vals:
            continue
        mid = _num(vals[0])
        fcode = int(str(vals[3]).strip(), 16) if len(vals) > 3 and \
            str(vals[3]).strip() else 0
        cat = _q(vals[6]) if len(vals) > 6 else ""
        rec = {
            "f": fcode,
            "dmg": _num(vals[4]) if len(vals) > 4 else 0,
            "type": _id_of(game_root, "PBTypes", vals[5] if len(vals) > 5
                           else "", 0),
            "cat": PE.ENUM_CATEGORY.get(cat, 2) if cat else 2,
            "acc": _num(vals[7]) if len(vals) > 7 else 100,
            "pp": _num(vals[8]) if len(vals) > 8 else 5,
            "eff": _num(vals[9]) if len(vals) > 9 else 0,
            "target": _id_of(game_root, "PBTargets",
                             _q(vals[10]) if len(vals) > 10 else "", 0),
            "pri": _num(vals[11]) if len(vals) > 11 else 0,
            "flags": _flag_bits(vals[12] if len(vals) > 12 else ""),
        }
        if rec["cat"] != 2 and rec["dmg"] == 0:
            rec["cat"] = 2
        recs[mid] = rec
        maxid = max(maxid, mid)
    _backup(path)
    with open(path, "wb") as f:
        for i in range(maxid + 1):
            r = recs.get(i)
            if not r:
                f.write(b"\0" * 14)
                continue
            f.write(struct.pack("<H", r["f"] & 0xFFFF))
            f.write(bytes([r["dmg"] & 0xFF, r["type"] & 0xFF,
                           r["cat"] & 0xFF, r["acc"] & 0xFF,
                           r["pp"] & 0xFF, r["eff"] & 0xFF]))
            f.write(struct.pack("<H", r["target"] & 0xFFFF))
            f.write(bytes([r["pri"] & 0xFF]))
            f.write(struct.pack("<H", r["flags"] & 0xFFFF))
            f.write(b"\0")
    return True, "", "%d 个招式" % len(recs)


def c_items(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    records = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("﻿"):
            continue
        v = PE.split_csv(line)
        iid = _num(v[0]) if v else 0
        rec = [iid,
               _q(v[1]) if len(v) > 1 else "",
               _q(v[2]) if len(v) > 2 else "",
               _q(v[3]) if len(v) > 3 else "",
               _num(v[4]) if len(v) > 4 else 1,
               _num(v[5]) if len(v) > 5 else 0,
               _q(v[6]) if len(v) > 6 else "",
               _num(v[7]) if len(v) > 7 else 0,
               _num(v[8]) if len(v) > 8 else 0,
               _num(v[9]) if len(v) > 9 else 0,
               _id_of(game_root, "PBMoves",
                      _q(v[10]) if len(v) > 10 else "", 0)]
        while len(records) <= iid:
            records.append([0, "????????", 0, 0, "????????"])
        records[iid] = rec
    if fam == "v18":
        _save(path, records)
    else:
        _backup(path)
        write_serial_records(path, records)
    return True, "", "%d 个道具" % len(records)


def c_trainer_types(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    records: List[Any] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("﻿"):
            continue
        v = PE.split_csv(line)
        tid = _num(v[0]) if v else 0
        gen = _q(v[7]) if len(v) > 7 else ""
        rec = [tid,
               _q(v[1]) if len(v) > 1 else "",
               _q(v[2]) if len(v) > 2 else "",
               _num(v[3]) if len(v) > 3 else 30,
               _q(v[4]) if len(v) > 4 else None,
               _q(v[5]) if len(v) > 5 else None,
               _q(v[6]) if len(v) > 6 else None,
               PE.ENUM_GENDER.get(gen, 2) if gen else 2,
               _num(v[8]) if len(v) > 8 else None,
               _q(v[9]) if len(v) > 9 else None]
        if rec[7] == 2 and gen == "":
            rec[7] = 2
        while len(records) <= tid:
            records.append(None)
        records[tid] = rec
    _save(path, records)
    return True, "", "%d 个训练家类型" % sum(1 for r in records if r)


def c_map_connections(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    records = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("﻿"):
            continue
        v = PE.split_csv(line)
        if len(v) < 6:
            continue
        rec = [_num(v[0]), str(v[1]).strip().upper()[:1], _num(v[2]),
               _num(v[3]), str(v[4]).strip().upper()[:1], _num(v[5])]
        records.append(rec)
    _save(path, records)
    return True, "", "%d 条连接" % len(records)


def c_tm(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    rows: List[Any] = []
    for sec in PE.parse_sections(text):
        tid = _num(sec.name)
        moves = []
        for k, v in sec.fields:
            if k == "Moves":
                moves = [_id_of(game_root, "PBMoves", x)
                         for x in PE.split_csv(v) if x]
        while len(rows) <= tid:
            rows.append(None)
        rows[tid] = moves
    _save(path, rows)
    return True, "", "%d 个招式机" % sum(1 for r in rows if r)


def c_berry(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    h = RHash()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("﻿"):
            continue
        m = PE._KV_RE.match(line)
        if not m:
            continue
        item = _id_of(game_root, "PBItems", m.group(1))
        h[item] = [_num(x) for x in PE.split_csv(m.group(2))]
    _save(path, h)
    return True, "", "%d 种树果" % len(h.pairs)


def c_shadow(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    h = RHash()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("﻿"):
            continue
        m = PE._KV_RE.match(line)
        if not m:
            continue
        sp = _id_of(game_root, "PBSpecies", m.group(1))
        h[sp] = [_id_of(game_root, "PBMoves", x)
                 for x in PE.split_csv(m.group(2)) if x]
    _save(path, h)
    return True, "", "%d 条" % len(h.pairs)


def c_metadata(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    rows: List[Any] = []
    for sec in PE.parse_sections(text):
        mid = _num(sec.name)
        use = _META_GLOBAL_SCHEMA if mid == 0 else _META_MAP_SCHEMA
        rec: List[Any] = [None] * (len(use) + 1)
        for i, (key, _iv, ctype, _e) in enumerate(use):
            val = None
            for k, v in sec.fields:
                if k == key:
                    val = v
                    break
            if val is None:
                continue
            if ctype == "b":
                rec[i + 1] = str(val).strip().lower() in ("true", "1", "yes")
            elif ctype[0] in "*":
                rec[i + 1] = [_num(x) for x in PE.split_csv(val) if x]
            elif ctype == "e8s":
                parts = [_q(x) for x in PE.split_csv(val)]
                rec[i + 1] = ([_id_of(game_root, "PBTrainers", parts[0])]
                              if parts else [0]) + parts[1:]
            elif re.fullmatch(r"[a-zA-Z]{2,}", ctype) and \
                    ctype[0] not in ("s", "q", "n", "m", "e"):
                rec[i + 1] = [_num(x) for x in PE.split_csv(val)]
            elif ctype[0] == "e":
                rec[i + 1] = _id_of(game_root, _enum_class(key), val)
            elif ctype[0] in ("u", "v", "i"):
                rec[i + 1] = _num(val)
            else:
                rec[i + 1] = _q(val)
        while len(rows) <= mid:
            rows.append(None)
        rows[mid] = rec
    _save(path, rows)
    return True, "", "%d 段" % sum(1 for r in rows if r)


_ENUM_KEYS = {
    "Weather": "PBFieldWeather", "Environment": "PBEnvironment",
    "Color": "PBColors", "Habitat": "PBHabitats",
    "GenderRate": "PBGenderRates", "GrowthRate": "PBGrowthRates",
    "Compatibility": "PBEggGroups", "Nature": "PBNatures",
    "Type1": "PBTypes", "Type2": "PBTypes", "Types": "PBTypes",
    "Ability": "PBAbilities", "Incense": "PBItems", "Item": "PBItems",
    "WildItemCommon": "PBItems", "WildItemUncommon": "PBItems",
    "WildItemRare": "PBItems", "MegaStone": "PBItems",
}


def _enum_class(key: str) -> str:
    return _ENUM_KEYS.get(key, "")


def c_townmap(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    rows: List[Any] = []
    for sec in PE.parse_sections(text):
        tid = _num(sec.name)
        rec: List[Any] = [[], None, []]
        for k, v in sec.fields:
            if k == "Name":
                rec[0] = _q(v)
            elif k == "Filename":
                rec[1] = _q(v)
            elif k == "Point":
                pts = []
                for x in PE.split_csv(v):
                    x = x.strip()
                    if x == "":
                        pts.append(None)
                    elif x.lstrip("-").isdigit():
                        pts.append(int(x))
                    else:
                        pts.append(_q(x))
                rec[2].append(pts)
        while len(rows) <= tid:
            rows.append(None)
        rows[tid] = rec
    _save(path, rows)
    return True, "", "%d 个区域" % sum(1 for r in rows if r)


def c_regional(spec, fam, game_root, text):
    path = os.path.join(game_root, "Data", spec["dat"][0])
    lists: List[List[int]] = []
    for sec in PE.parse_sections(text):
        idx = _num(sec.name)
        vals = []
        for _k, v in sec.fields:
            for x in PE.split_csv(v):
                if x:
                    vals.append(_id_of(game_root, "PBSpecies", x))
        while len(lists) <= idx:
            lists.append([])
        lists[idx] = vals
    if fam == "v18":
        _save(path, lists)
        return True, "", "%d 本图鉴" % len(lists)
    n_sp = 0
    try:
        n_sp = max((_id_of(game_root, "PBSpecies",
                          s) for s in const_map(game_root, "PBSpecies")
                    .values()), default=0) + 1
    except Exception:
        n_sp = max((max(l) if l else 0 for l in lists), default=0) + 1
    _backup(path)
    with open(path, "wb") as f:
        f.write(struct.pack("<II", len(lists), n_sp))
        for lst in lists:
            for j in range(n_sp):
                f.write(struct.pack("<I", lst[j] if j < len(lst) else 0))
    return True, "", "%d 本图鉴 × %d 只" % (len(lists), n_sp)


def c_pokemon(spec, fam, game_root, text):
    """v16/v17：dexdata + attacksRS + eggEmerald + evolutions + regionals + metrics。"""
    sections = PE.parse_sections(text)
    if not sections:
        return False, "没解析出任何宝可梦段", ""
    if fam == "v18":
        return _c_pokemon18(game_root, text, sections)
    dexdatas: Dict[int, bytes] = {}
    movesets: Dict[int, list] = {}
    eggmoves: Dict[int, list] = {}
    evolutions: Dict[int, list] = {}
    metrics = [[], [], []]
    meta_names = {}
    for sec in sections:
        sid = _num(sec.name)
        if sid <= 0:
            continue
        blob = bytearray(DEX_SIZE)
        moves = []
        egge = []
        evos = []
        fields = {}
        for k, v in sec.fields:
            fields.setdefault(k, v)
        # Moves：级别,招式 成对
        mv = [_q(x) for x in PE.split_csv(fields.get("Moves", "")) if x != ""]
        for i in range(0, len(mv) - 1, 2):
            moves.append([_num(mv[i]), _id_of(game_root, "PBMoves", mv[i + 1])])
        moves.sort(key=lambda x: x[0])
        for x in PE.split_csv(fields.get("EggMoves", "")):
            if x:
                egge.append(_id_of(game_root, "PBMoves", x))
        ev = [_q(x) for x in PE.split_csv(fields.get("Evolutions", ""))
              if x != ""]
        for i in range(0, len(ev) - 2, 3):
            method = _id_of(game_root, "PBEvolution", ev[i + 1])
            param = ev[i + 2]
            if param == "":
                p = 0
            elif param.lstrip("-").isdigit():
                p = int(param)
            else:
                p = _id_of(game_root, _evo_param_class(method), param)
            evos.append([_id_of(game_root, "PBSpecies", ev[i]), method, p])
        # dexdata 各字段（布局按游戏自己的 schema）
        layout = dex_layout(game_root)

        def put(name, val):
            off, b = _dex_bytes(name, val, layout)
            blob[off:off + len(b)] = b
        put("Color", _id_of(game_root, "PBColors",
                            fields.get("Color", "Red")))
        put("Habitat", _id_of(game_root, "PBHabitats",
                              fields.get("Habitat", "")))
        put("Type1", _id_of(game_root, "PBTypes", fields.get("Type1")))
        put("Type2", _id_of(game_root, "PBTypes",
                            fields.get("Type2") or fields.get("Type1")))
        bs = [_num(x) for x in PE.split_csv(fields.get("BaseStats", ""))]
        put("BaseStats", (bs + [0] * 6)[:6])
        put("Rareness", _num(fields.get("Rareness"), 255))
        if fam == "v17":
            put("Shape", _num(fields.get("Shape")))
        put("GenderRate", _GENDER.get(fields.get("GenderRate", ""),
                                      _num(fields.get("GenderRate"), 127)))
        put("Happiness", _num(fields.get("Happiness"), 70))
        put("GrowthRate", _GROWTH.get(fields.get("GrowthRate", ""),
                                      _num(fields.get("GrowthRate"))))
        put("StepsToHatch", _num(fields.get("StepsToHatch"), 1))
        evs = [_num(x) for x in PE.split_csv(fields.get("EffortPoints", ""))]
        put("EffortPoints", (evs + [0] * 6)[:6])
        comp = [_id_of(game_root, "PBEggGroups", x)
                for x in PE.split_csv(fields.get("Compatibility", "")) if x]
        put("Compatibility", (comp + [0, 0])[:2])
        put("Height", _flt(fields.get("Height"), 0.1))
        put("Weight", _flt(fields.get("Weight"), 0.1))
        put("BaseEXP", _num(fields.get("BaseExp") or
                            fields.get("BaseEXP"), 100))
        ab = [_id_of(game_root, "PBAbilities", x)
              for x in PE.split_csv(fields.get("Abilities", "")) if x]
        put("Abilities", (ab + [0, 0])[:2])
        ha = [_id_of(game_root, "PBAbilities", x)
              for x in PE.split_csv(fields.get("HiddenAbility", "")) if x]
        put("HiddenAbility", (ha + [0, 0, 0, 0])[:4])
        for k, off_key in (("WildItemCommon", "WildItemCommon"),
                           ("WildItemUncommon", "WildItemUncommon"),
                           ("WildItemRare", "WildItemRare"),
                           ("Incense", "Incense")):
            v = fields.get(k, "")
            put(off_key, _id_of(game_root, "PBItems", v) if v else 0)
        dexdatas[sid] = bytes(blob)
        movesets[sid] = moves
        eggmoves[sid] = egge
        evolutions[sid] = evos
        metrics[0].append((sid, _num(fields.get("BattlerPlayerY"), 0)))
        metrics[1].append((sid, _num(fields.get("BattlerEnemyY"), 0)))
        metrics[2].append((sid, _num(fields.get("BattlerAltitude"), 0)))
        meta_names[sid] = fields.get("InternalName", "")
    if not dexdatas:
        return False, "没有有效的宝可梦段", ""
    maxid = max(dexdatas)
    # 前置进化（官方会补 true 标记）
    for sid, evos in list(evolutions.items()):
        for evo in evos:
            tgt = evo[0]
            if tgt in evolutions and not any(e[1] == evo[1] and e[0] == sid
                                             and e[2] == evo[2]
                                             for e in evolutions[tgt]):
                evolutions[tgt] = [[sid, evo[1], evo[2], 0x80]] + \
                    evolutions[tgt]
    # dexdata.dat
    _backup(os.path.join(game_root, "Data", "dexdata.dat"))
    with open(os.path.join(game_root, "Data", "dexdata.dat"), "wb") as f:
        f.write(b"\0" * DEX_SIZE)
        for i in range(1, maxid + 1):
            f.write(dexdatas.get(i, b"\0" * DEX_SIZE))
    # metrics.dat（三个数组：玩家Y / 敌人Y / 高度）
    mrows = []
    for idx in range(3):
        arr: List[Any] = [0] * (maxid + 1)
        for sid, v in metrics[idx]:
            arr[sid] = v
        mrows.append(arr)
    _save(os.path.join(game_root, "Data", "metrics.dat"), mrows)
    # attacksRS.dat（招式机表）
    _write_dword_table_list(
        os.path.join(game_root, "Data", "attacksRS.dat"),
        [[struct.pack("<HH", m, lv) for m, lv in (movesets.get(i) or [])]
         for i in range(maxid + 1)], maxid + 1)
    # eggEmerald.dat（蛋招式）
    _write_dword_table_list(
        os.path.join(game_root, "Data", "eggEmerald.dat"),
        [[struct.pack("<H", m) for m in (eggmoves.get(i) or [])]
         for i in range(maxid + 1)], maxid + 1)
    # evolutions.dat
    _write_dword_table_list(
        os.path.join(game_root, "Data", "evolutions.dat"),
        [[bytes([(e[1] | (e[3] if len(e) > 3 else 0)) & 0xFF])
          + struct.pack("<HH", e[2] & 0xFFFF, e[0] & 0xFFFF)
          for e in (evolutions.get(i) or [])] for i in range(maxid + 1)],
        maxid + 1)
    return True, "", "%d 只宝可梦（dexdata/进化/招式机表已写回）" % len(dexdatas)


def _evo_param_class(method: int) -> str:
    # 参数是道具 / 招式 / 宝可梦名时按进化方式判断
    if method in (6, 7, 16, 17, 18, 19):
        return "PBItems"
    if method == 20:
        return "PBMoves"
    if method in (21, 25):
        return "PBSpecies"
    return ""


def _c_pokemon18(game_root, text, sections):
    """v18：species.dat + species_movesets/eggmoves/evolutions/metrics/regional_dexes。"""
    species: List[Any] = []
    movesets: List[Any] = []
    eggmoves: List[Any] = []
    evolutions: List[Any] = []
    maxid = 0
    for sec in sections:
        sid = _num(sec.name)
        if sid <= 0:
            continue
        fields = {}
        for k, v in sec.fields:
            fields.setdefault(k, v)
        rec: List[Any] = [None] * 27
        rec[0] = _id_of(game_root, "PBTypes", fields.get("Type1"))
        rec[1] = _id_of(game_root, "PBTypes",
                        fields.get("Type2") or fields.get("Type1"))
        rec[2] = [_num(x) for x in PE.split_csv(fields.get("BaseStats", ""))]
        rec[3] = _GENDER.get(fields.get("GenderRate", ""), 127)
        rec[4] = _GROWTH.get(fields.get("GrowthRate", ""), 0)
        rec[5] = _num(fields.get("BaseExp") or fields.get("BaseEXP"), 100)
        rec[6] = [_num(x) for x in PE.split_csv(fields.get("EffortPoints", ""))]
        rec[7] = _num(fields.get("Rareness") or fields.get("CatchRate"), 255)
        rec[8] = _num(fields.get("Happiness"), 70)
        rec[9] = [_id_of(game_root, "PBAbilities", x)
                  for x in PE.split_csv(fields.get("Abilities", "")) if x]
        rec[10] = [_id_of(game_root, "PBAbilities", x)
                   for x in PE.split_csv(fields.get("HiddenAbility", "")) if x]
        rec[11] = [_id_of(game_root, "PBEggGroups", x)
                   for x in PE.split_csv(fields.get("Compatibility", "")) if x]
        rec[12] = _num(fields.get("StepsToHatch"), 1)
        rec[13] = _flt(fields.get("Height"), 0.1)
        rec[14] = _flt(fields.get("Weight"), 0.1)
        rec[15] = _id_of(game_root, "PBColors", fields.get("Color", "Red"))
        rec[16] = _num(fields.get("Shape"))
        rec[17] = _id_of(game_root, "PBHabitats", fields.get("Habitat", ""))
        rec[18] = _id_of(game_root, "PBItems", fields.get("WildItemCommon", ""))
        rec[19] = _id_of(game_root, "PBItems",
                         fields.get("WildItemUncommon", ""))
        rec[20] = _id_of(game_root, "PBItems", fields.get("WildItemRare", ""))
        rec[21] = _id_of(game_root, "PBItems", fields.get("Incense", ""))
        while len(species) <= sid:
            species.append(None)
            movesets.append(None)
            eggmoves.append(None)
            evolutions.append(None)
        species[sid] = rec
        mv = [_q(x) for x in PE.split_csv(fields.get("Moves", "")) if x != ""]
        ms = []
        for i in range(0, len(mv) - 1, 2):
            ms.append([_num(mv[i]), _id_of(game_root, "PBMoves", mv[i + 1])])
        ms.sort(key=lambda x: x[0])
        movesets[sid] = ms
        eggmoves[sid] = [_id_of(game_root, "PBMoves", x)
                         for x in PE.split_csv(fields.get("EggMoves", ""))
                         if x]
        ev = [_q(x) for x in PE.split_csv(fields.get("Evolutions", ""))
              if x != ""]
        evos = []
        for i in range(0, len(ev) - 2, 3):
            method = _id_of(game_root, "PBEvolution", ev[i + 1])
            param = ev[i + 2]
            p = int(param) if param.lstrip("-").isdigit() else \
                _id_of(game_root, _evo_param_class(method), param)
            evos.append([_id_of(game_root, "PBSpecies", ev[i]), method, p])
        evolutions[sid] = evos
        maxid = max(maxid, sid)
    if not any(species):
        return False, "没有有效的宝可梦段", ""
    data = os.path.join(game_root, "Data")
    _save(os.path.join(data, "species.dat"), species)
    _save(os.path.join(data, "species_movesets.dat"), movesets)
    _save(os.path.join(data, "species_eggmoves.dat"), eggmoves)
    _save(os.path.join(data, "species_evolutions.dat"), evolutions)
    return True, "", "%d 只宝可梦" % sum(1 for s in species if s)


_COMPILE = {
    "types": c_types, "moves": c_moves, "items": c_items,
    "trainer_types": c_trainer_types, "map_connections": c_map_connections,
    "tm": c_tm, "berry_plants": c_berry, "shadow_movesets": c_shadow,
    "metadata": c_metadata, "town_map": c_townmap, "regional_dexes": c_regional,
    "pokemon": c_pokemon,
}


# ---------------------------------------------------------------------------
# 「标记待重编译」：让官方编译器接管
# ---------------------------------------------------------------------------

def newest_txt_time(game_root: str) -> float:
    pbs = PE.pbs_dir(game_root)
    newest = 0.0
    try:
        for fn in os.listdir(pbs):
            if fn.lower().endswith(".txt"):
                newest = max(newest, os.path.getmtime(os.path.join(pbs, fn)))
    except OSError:
        pass
    return newest


def sync_names(game_root: str, family: str,
               keys: Optional[List[str]] = None) -> dict:
    """
    把 PBS txt 里的**名字**写回 Data/messages.dat（以及中文语言包），不碰 .dat。

    ★ 为什么低版本「编译」只做这个：v16-18 直接重编 .dat 会丢招式表/进化表
      （c_pokemon 只能从 pokemon.txt 重建，而提取出的 txt 不含这些衍生表）。
      名字本来就不在 .dat 里，而在消息表里；改名字落到消息表即可立刻生效，
      也不会破坏任何衍生数据。
    """
    want = set(keys) if keys else {"pokemon", "moves"}

    # 载入所有消息表文件（messages.dat + 中文包）
    files = []
    for fn in _MSG_FILES:
        p = os.path.join(game_root, "Data", fn)
        if not os.path.isfile(p):
            continue
        try:
            obj = _load(game_root, fn)
        except Exception:
            continue
        if isinstance(obj, list) and len(obj) >= 13:
            files.append((fn, p, obj))
    if not files:
        return {"ok": False,
                "reason": "Data 里没有 messages.dat，改名字无处可写"}

    def _pairs_from_txt(key: str):
        txt = _txt(game_root, key, family)
        if txt is None:
            return []
        out = []
        if key == "pokemon":
            for sec in PE.parse_sections(txt):
                sid = _num(sec.name)
                if sid <= 0:
                    continue
                nm = ""
                for k, v in sec.fields:
                    if k == "Name":
                        nm = v
                        break
                if nm:
                    out.append((sid, nm))
        elif key == "moves":
            for line in txt.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                cols = PE.split_csv(line)
                if len(cols) < 3:
                    continue
                sid = _num(cols[0])
                nm = _q(cols[2])
                if sid > 0 and nm:
                    out.append((sid, nm))
        return out

    counts: Dict[str, int] = {}
    applied = set()
    for key, idx in (("pokemon", 1), ("moves", 5)):
        if key not in want:
            continue
        pairs = _pairs_from_txt(key)
        if not pairs:
            continue
        n = 0
        for _fn, _p, obj in files:
            arr = obj[idx] if idx < len(obj) and isinstance(obj[idx], list) \
                else None
            if arr is None:
                continue
            for sid, nm in pairs:
                if sid >= len(arr):
                    arr.extend([""] * (sid + 1 - len(arr)))
                if arr[sid] != nm:
                    arr[sid] = nm
                    n += 1
        if n:
            for _fn, p, obj in files:
                _save(p, obj)
                applied.add(p)
            counts[key] = n

    # 写回后清掉这个名字缓存，保证紧接着的「提取」看到的是新名字
    for _k in [k for k in list(_MSG_CACHE) if k[0] == game_root]:
        _MSG_CACHE.pop(_k, None)

    if not counts:
        return {"ok": True, "counts": {}, "files": [],
                "reason": "名字没有变化（或 PBS 里没有名字）"}
    return {"ok": True, "counts": counts,
            "files": sorted(applied), "reason": ""}


def mark_for_recompile(game_root: str, family: str) -> Tuple[int, str]:
    """
    把 Data 里的 .dat 时间戳挪到 PBS 之前 —— 游戏下次启动会全量重编译。

    ★ 只改 mtime，不删文件：万一编译失败，原来的 .dat 还在。
    """
    base = newest_txt_time(game_root)
    if base <= 0:
        return 0, "PBS 目录里没有 txt"
    target = base - _RECOMPILE_GAP
    data = os.path.join(game_root, "Data")
    n = 0
    try:
        for fn in os.listdir(data):
            if not fn.lower().endswith(".dat"):
                continue
            if fn.endswith(".orig"):
                continue
            p = os.path.join(data, fn)
            try:
                if os.path.getmtime(p) >= base:
                    os.utime(p, (target, target))
                    n += 1
            except OSError:
                pass
    except OSError:
        return 0, "读不到 Data 目录"
    return n, ("已把 %d 个 .dat 标记为「旧」—— 下次启动游戏时它自己会重新编译"
               % n)


def extract_all(game_root: str, family: str,
                keys: Optional[List[str]] = None,
                emit=None) -> List[dict]:
    """把 PBS 里的 txt 补齐（游戏自带的原样保留，缺的从 .dat 尽力还原）。"""
    out_dir = PE.pbs_dir(game_root)
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for spec in specs(family):
        if keys and spec["key"] not in keys:
            continue
        ok, text, stat = extract_spec(spec, family, game_root)
        rec = {"key": spec["key"], "name": spec["name"],
               "file": _fname(spec["key"], family), "ok": ok, "stat": stat}
        if ok:
            path = os.path.join(out_dir, rec["file"])
            old = None
            if os.path.isfile(path):
                old = open(path, "rb").read()
            if old != text.encode("utf-8"):
                try:
                    with open(path, "wb") as f:
                        f.write(text.encode("utf-8"))
                    rec["path"] = path
                except OSError as e:
                    rec["ok"] = False
                    rec["stat"] = "写入失败：%s" % e
        else:
            rec["stat"] = text
        results.append(rec)
        if emit:
            emit(rec)
    return results


def compile_all(game_root: str, family: str,
                keys: Optional[List[str]] = None,
                emit=None) -> List[dict]:
    """编译全部（或指定）txt；不能单独写的会提示「交给游戏重编译」。"""
    out = []
    need_game = False
    for spec in specs(family):
        if keys and spec["key"] not in keys:
            continue
        ok, msg, stat = compile_spec(spec, family, game_root)
        if ok and "标记待重编译" in stat:
            need_game = True
        rec = {"key": spec["key"], "name": spec["name"], "ok": ok,
               "stat": stat, "msg": msg}
        out.append(rec)
        if emit:
            emit(rec)
    if need_game:
        n, m = mark_for_recompile(game_root, family)
        out.append({"key": "_mark", "name": "标记待重编译", "ok": True,
                    "stat": m, "msg": ""})
        if emit:
            emit(out[-1])
        del n
    return out


