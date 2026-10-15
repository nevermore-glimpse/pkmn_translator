# -*- coding: utf-8 -*-
r"""
PBS 编辑 —— 把游戏 Data/*.dat 提取成 PBS/*.txt、编辑后再编译回 .dat。

## 支持的版本

* **v19 / v19.1**：``[编号]`` 段 + ``Key = Value``；abilities / moves / items /
  ribbons / trainertypes / berryplants / shadowmoves 还是「一行一条 CSV」的老格式。
* **v20 / v20.1 / v21 / v21.1**：全部 ``[内部名]`` 段 + ``Key = Value``。
* v16～v18 的老游戏（``berryplants.dat`` / ``attacksRS.dat`` 那套）**不在支持范围**——
  那些游戏自带 PBS 目录，交给游戏自己编译。

## .dat 结构（v19+）

* ClassMethods 系（v19）：``Hash{ Symbol(id) => 对象, Integer(id_number) => 对象 }``
  （同一个对象挂两个键）。
* ClassMethodsSymbols 系（v20/v21）：``Hash{ Symbol(id) => 对象 }``。
* ClassMethodsIDNumbers 系（metadata / player_metadata / map_metadata）：
  ``Hash{ Integer(id) => 对象 }``。
* 对象是 ``GameData::X`` 的普通 Ruby 对象，字段全在实例变量里（``@real_name`` …）。

## 目录约定

提取结果放 **游戏根目录下的 PBS 文件夹**（没有就新建）；编译写回 Data/ 同名
.dat，第一次编译前先把原文件复制成 ``.dat.orig`` 留底。

依赖：rmarshal（Ruby Marshal 读写）、essentials_base（版本识别，可选）。
"""
from __future__ import annotations

import os
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

import rmarshal
from rmarshal import RObject, RSymbol, RHash

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

FAMILIES = ("v19", "v20", "v21")

PBS_DIR_NAME = "PBS"

# 行尾：Essentials 的 write_* 一律写 \r\n
CRLF = "\r\n"

# 段分隔线（官方格式）
_SEP = "#-------------------------------"

# 文件头（官方那句）
_HEADER = "# See the documentation on the wiki to learn how to edit this file."

# 六项能力值的 PBS 书写顺序（v19 与 v20+ 不同）
STAT_ORDER_V19 = ("HP", "ATTACK", "DEFENSE", "SPEED",
                  "SPECIAL_ATTACK", "SPECIAL_DEFENSE")
STAT_ORDER_NEW = ("HP", "ATTACK", "DEFENSE",
                  "SPECIAL_ATTACK", "SPECIAL_DEFENSE", "SPEED")

STAT_LABELS = {
    "HP": "HP", "ATTACK": "攻击", "DEFENSE": "防御",
    "SPECIAL_ATTACK": "特攻", "SPECIAL_DEFENSE": "特防", "SPEED": "速度",
}

# 枚举表（PBS 文本 <-> .dat 里的整数值）
ENUM_CATEGORY = {"Physical": 0, "Special": 1, "Status": 2}
ENUM_GENDER = {"Male": 0, "Female": 1, "Mixed": 2}
ENUM_ITEM_FIELD_USE = {"OnPokemon": 1, "Direct": 2, "TM": 3, "HM": 4, "TR": 5}
ENUM_ITEM_BATTLE_USE = {"OnPokemon": 1, "OnMove": 2, "OnBattler": 3,
                        "OnFoe": 4, "Direct": 5}


def stat_order(family: str) -> Tuple[str, ...]:
    return STAT_ORDER_V19 if family == "v19" else STAT_ORDER_NEW


# ---------------------------------------------------------------------------
# CSV 工具（对应 Essentials 001_Compiler.rb 的 csvQuote / split_csv_line /
# cast_csv_value / pbWriteCsvRecord）
# ---------------------------------------------------------------------------

def csv_quote(s: str, always: bool = False) -> str:
    """Essentials csvQuote：含逗号/引号时加引号，引号转成 \\" 。"""
    if s is None:
        s = ""
    if always or ("," in s) or ('"' in s):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def split_csv(line: str) -> List[str]:
    """Essentials split_csv_line：按逗号切分，引号内的逗号算内容。"""
    values = line.split(",")
    i = 0
    while i < len(values):
        value = values[i]
        if value and value.count('"'):
            j = i
            while j < len(values) - 1:
                qc = values[i].count('"')
                if qc == 2 and values[i].startswith('\\"') and values[i].endswith('\\"'):
                    values[i] = values[i][2:-3]
                    break
                if qc % 2 == 0:
                    break
                values[i] += "," + values[j + 1]
                values[j + 1] = None
                j += 1
            else:
                if values[i].count('"') == 2 and values[i].startswith('\\"') \
                        and values[i].endswith('\\"'):
                    values[i] = values[i][2:-3]
        i += 1
    return [v.strip() for v in values if v is not None]


def cast_value(text: str, ctype: str, enum: Optional[dict] = None) -> Any:
    """Essentials cast_csv_value：把文本按类型码转成 Python 值。"""
    if text is None:
        return None
    t = ctype.lower()
    if t == "i":
        return int(text) if text.strip() else 0
    if t in ("u", "v"):
        return int(text) if text.strip() else 0
    if t == "x":
        return int(text, 16)
    if t == "f":
        # ★ 官方 validate_compiled_pokemon：身高/体重按「十分之一单位」存整数，
        #   hash[:height] = [(hash[:height] * 10).round, 1].max
        return max(int(round(float(text) * 10)), 1)
    if t == "b":
        low = text.strip().lower()
        if low in ("1", "true", "yes", "y"):
            return True
        if low in ("0", "false", "no", "n"):
            return False
        raise ValueError(f"不是布尔值：{text!r}")
    if t in ("n", "m", "e"):
        # 内部名 / 符号 / 枚举 -> RSymbol（.dat 里就是 Symbol）
        if enum is not None:
            if text in enum:
                return enum[text]
            # 也接受直接写数值
            if text.lstrip("-").isdigit():
                return int(text)
            raise ValueError(f"不在枚举表里：{text!r}")
        return RSymbol(text)
    if t == "y":
        if enum and text in enum:
            return enum[text]
        return int(text)
    # "s" / "q" / 其它：原样字符串
    return text


def ruby_float(v: float) -> str:
    """Ruby Float#to_s 的近似：1.0 -> "1.0"（Python 默认给 "1"）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != f or f in (float("inf"), float("-inf")):
        return str(f)
    if f == int(f) and abs(f) < 1e16:
        return "%.1f" % f
    s = repr(round(f, 6))
    if s.endswith(".0"):
        s = s[:-2] + ".0"
    return s



def fmt_value(val: Any, ctype: str, enum: Optional[dict] = None) -> str:
    """把 .dat 里的值写成 PBS 文本（pbWriteCsvRecord 的 Python 版）。"""
    if val is None:
        return ""
    c = ctype[0].lower()
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, RSymbol):
        return val.name
    if isinstance(val, str):
        # "q"（未格式化文本）官方是**原样写**（读取时取整行剩余部分，逗号不用逃）；
        # "s" 才在含逗号/引号时加引号
        return val if c == "q" else csv_quote(val, always=False)
    if isinstance(val, (int, float)):
        if c == "x":                       # 十六进制（招式效果码）
            return "%03X" % int(val)
        if c in ("e", "y") and enum:
            for k, v in enum.items():
                if v == val:
                    return k
        if isinstance(val, float):
            return ruby_float(val)
        return str(val)
    return str(val)


# ---------------------------------------------------------------------------
# 版本识别
# ---------------------------------------------------------------------------

def _dat_names(game_root: str) -> List[str]:
    d = os.path.join(game_root, "Data")
    try:
        return [n for n in os.listdir(d) if n.lower().endswith(".dat")]
    except OSError:
        return []


_FAM_WHY = {
    "v19": "物种用 Type1/Type2、EffortPoints 等 v19 字段名",
    "v20": "物种用 Types/EVs，招式用 BaseDamage",
    "v21": "物种用 Types/EVs，招式用 Power",
}


def detect_family(game_root: str) -> Tuple[str, str]:
    """
    判断游戏属于哪个 PBS 版本族。返回 (family, 说明)。
    family ∈ {"v16","v17","v18","v19","v20","v21",""}，"" = 不认识。

    ★ v16～v18 由 pbs_legacy 负责（那几版的 .dat 是数组/二进制，格式完全不同）。
    """
    names = set(_dat_names(game_root))
    if not names:
        return "", "Data 目录里没有 .dat 文件"
    # ① 老版本（v16/v17/v18）优先
    try:
        import pbs_legacy
        fam, why = pbs_legacy.detect(game_root)
        if fam:
            return fam, why
    except Exception:
        pass

    # ① 脚本里的版本号最可靠
    try:
        import essentials_base as EB
        ver = EB.detect_version(game_root) or ""
        m = re.match(r"\s*(\d+)", ver)
        if m:
            major = int(m.group(1))
            if major >= 21:
                return "v21", f"Essentials {ver}"
            if major == 20:
                return "v20", f"Essentials {ver}"
            if major == 19:
                return "v19", f"Essentials {ver}"
            return "", f"Essentials {ver}（过旧，不支持 PBS 提取）"
    except Exception:
        pass

    # ② 老版本的标志文件
    if names & {"berryplants.dat", "attacksRS.dat", "dexdata.dat",
                "eggEmerald.dat", "clasepersona.dat"}:
        return "", "检测到 v16～v18 的老数据文件（berryplants/attacksRS 等）"

    # ③ v21 独有
    if "dungeon_tilesets.dat" in names:
        return "v21", "有 dungeon_tilesets.dat（v21 起才有）"
    # ④ v19 遗留的衍生 .dat
    if names & {"tm.dat", "species_evolutions.dat", "species_movesets.dat",
                "form2species.dat"}:
        return "v19", "有 tm/species_evolutions 等 v19 衍生文件"
    # ⑤ v20 起有 player_metadata / shadow_pokemon
    if "player_metadata.dat" in names or "shadow_pokemon.dat" in names:
        # v20 / v21 二选一：看物种字段名
        fam = _family_from_species(game_root)
        if fam:
            return fam, _FAM_WHY.get(fam, "按物种字段识别")
        return "v20", "有 player_metadata/shadow_pokemon（v20 起）"
    # ⑥ 只剩 v19 / v20 可能：看物种字段
    fam = _family_from_species(game_root)
    if fam:
        return fam, _FAM_WHY.get(fam, "按物种字段识别")
    if "species_metrics.dat" in names:
        return "v19", "有 species_metrics.dat（按 v19 解析）"
    return "", "无法识别版本"


def _family_from_species(game_root: str) -> str:
    """看 species.dat / moves.dat 的实例变量名区分 v19 / v20 / v21。"""
    try:
        p = os.path.join(game_root, "Data", "species.dat")
        if os.path.isfile(p) and os.path.getsize(p) > 8:
            obj = rmarshal.load(p)
            for _k, v in _iter_objects(obj):
                iv = getattr(v, "ivars", {}) or {}
                keys = set(iv.keys())
                if "@type1" in keys or "@pokedex_entry" in keys:
                    return "v19"
                if "@types" in keys or "@real_category" in keys:
                    # v20 / v21：再看 moves.dat
                    mp = os.path.join(game_root, "Data", "moves.dat")
                    if os.path.isfile(mp) and os.path.getsize(mp) > 8:
                        mo = rmarshal.load(mp)
                        for _k2, v2 in _iter_objects(mo):
                            iv2 = getattr(v2, "ivars", {}) or {}
                            if "@power" in iv2:
                                return "v21"
                            if "@base_damage" in iv2:
                                return "v20"
                    return "v20"
                break
    except Exception:
        pass
    return ""


def _iter_objects(obj: Any):
    """遍历 .dat 顶层容器里的对象（跳过整数重复键，同一个对象只出一次）。"""
    seen = set()
    if isinstance(obj, RHash):
        items = obj.items()
    elif isinstance(obj, dict):
        items = list(obj.items())
    elif isinstance(obj, list):
        items = list(enumerate(obj))
    else:
        return
    for _k, v in items:
        if id(v) in seen:
            continue
        seen.add(id(v))
        yield _k, v


def _obj_ivars(v: Any) -> dict:
    return getattr(v, "ivars", None) or {}


def _sym(v: Any) -> str:
    """RSymbol / str -> 名字。"""
    if isinstance(v, RSymbol):
        return v.name
    if isinstance(v, str):
        return v
    return str(v)


# ---------------------------------------------------------------------------
# 文件注册表
# ---------------------------------------------------------------------------
# 每条：
#   key      内部键
#   name     中文名（左侧列表显示用）
#   desc     一句话说明
#   dat      主 .dat 文件名（list；v19 的 metadata 是两个）
#   fname    {family: txt 文件名}
#   style    "section"（[段]+Key=Value）/"line"（v19 行式）/"custom"
#   schema   {family: [(pbs_key, ivar, csvtype, enum), ...]}
#   cls      .dat 里的 Ruby 类名
#   keymode  "symbol"（段名=内部名）/ "number"（段名=编号，v19）/
#            "idnum"（整数键）/"array"
#   editor   GUI 编辑器：generic / line / trainers / encounters / townmap /
#            connections / regional / phone / facility / metadata

FILES: List[dict] = [
    {
        "key": "types", "name": "属性", "desc": "18 种属性的相克与图标位置",
        "dat": ["types.dat"], "cls": "GameData::Type", "keymode": "symbol",
        "editor": "generic",
        "fname": {"v19": "types.txt", "v20": "types.txt", "v21": "types.txt"},
        "schema": {
            "v19": [("Name", "real_name", "s", None),
                    ("InternalName", "id", "m", None),
                    ("IsPseudoType", "pseudo_type", "b", None),
                    ("IsSpecialType", "special_type", "b", None),
                    ("Weaknesses", "weaknesses", "*m", None),
                    ("Resistances", "resistances", "*m", None),
                    ("Immunities", "immunities", "*m", None)],
            "v20": [("Name", "real_name", "s", None),
                    ("IconPosition", "icon_position", "u", None),
                    ("IsPseudoType", "pseudo_type", "b", None),
                    ("IsSpecialType", "special_type", "b", None),
                    ("Weaknesses", "weaknesses", "*m", None),
                    ("Resistances", "resistances", "*m", None),
                    ("Immunities", "immunities", "*m", None),
                    ("Flags", "flags", "*s", None)],
            "v21": [("Name", "real_name", "s", None),
                    ("IconPosition", "icon_position", "u", None),
                    ("IsSpecialType", "special_type", "b", None),
                    ("IsPseudoType", "pseudo_type", "b", None),
                    ("Weaknesses", "weaknesses", "*m", None),
                    ("Resistances", "resistances", "*m", None),
                    ("Immunities", "immunities", "*m", None),
                    ("Flags", "flags", "*s", None)],
        },
    },
    {
        "key": "abilities", "name": "特性", "desc": "特性的名字与描述",
        "dat": ["abilities.dat"], "cls": "GameData::Ability", "keymode": "symbol",
        "editor": "generic",
        "fname": {"v19": "abilities.txt", "v20": "abilities.txt",
                  "v21": "abilities.txt"},
        "style": {"v19": "line"},
        "schema": {
            "v19": [("IdNumber", "id_number", "v", None),
                    ("InternalName", "id", "n", None),
                    ("Name", "real_name", "s", None),
                    ("Description", "real_description", "q", None)],
            "v20": [("Name", "real_name", "s", None),
                    ("Description", "real_description", "q", None),
                    ("Flags", "flags", "*s", None)],
            "v21": [("Name", "real_name", "s", None),
                    ("Description", "real_description", "q", None),
                    ("Flags", "flags", "*s", None)],
        },
    },
    {
        "key": "moves", "name": "招式", "desc": "招式的威力、命中、PP 与描述",
        "dat": ["moves.dat"], "cls": "GameData::Move", "keymode": "symbol",
        "editor": "generic",
        "fname": {"v19": "moves.txt", "v20": "moves.txt", "v21": "moves.txt"},
        "style": {"v19": "line"},
        "sep_on": {"v19": "type"},
        "schema": {
            "v19": [("IdNumber", "id_number", "v", None),
                    ("InternalName", "id", "n", None),
                    ("Name", "real_name", "s", None),
                    ("FunctionCode", "function_code", "s", None),
                    ("BaseDamage", "base_damage", "u", None),
                    ("Type", "type", "m", None),
                    ("Category", "category", "e", ENUM_CATEGORY),
                    ("Accuracy", "accuracy", "u", None),
                    ("TotalPP", "total_pp", "u", None),
                    ("EffectChance", "effect_chance", "u", None),
                    ("Target", "target", "m", None),
                    ("Priority", "priority", "i", None),
                    ("Flags", "flags", "*s", None),
                    ("Description", "real_description", "q", None)],
            "v20": [("Name", "real_name", "s", None),
                    ("Type", "type", "m", None),
                    ("Category", "category", "e", ENUM_CATEGORY),
                    ("BaseDamage", "base_damage", "u", None),
                    ("Accuracy", "accuracy", "u", None),
                    ("TotalPP", "total_pp", "u", None),
                    ("Target", "target", "m", None),
                    ("Priority", "priority", "i", None),
                    ("FunctionCode", "function_code", "s", None),
                    ("Flags", "flags", "*s", None),
                    ("EffectChance", "effect_chance", "u", None),
                    ("Description", "real_description", "q", None)],
            "v21": [("Name", "real_name", "s", None),
                    ("Type", "type", "m", None),
                    ("Category", "category", "e", ENUM_CATEGORY),
                    ("Power", "power", "u", None),
                    ("Accuracy", "accuracy", "u", None),
                    ("TotalPP", "total_pp", "u", None),
                    ("Target", "target", "m", None),
                    ("Priority", "priority", "i", None),
                    ("FunctionCode", "function_code", "s", None),
                    ("Flags", "flags", "*s", None),
                    ("EffectChance", "effect_chance", "u", None),
                    ("Description", "real_description", "q", None)],
        },
    },
    {
        "key": "items", "name": "道具", "desc": "道具的名字、口袋、价格与描述",
        "dat": ["items.dat"], "cls": "GameData::Item", "keymode": "symbol",
        "editor": "generic",
        "fname": {"v19": "items.txt", "v20": "items.txt", "v21": "items.txt"},
        "style": {"v19": "line"},
        "sep_on": {"v19": "pocket"},
        "schema": {
            "v19": [("IdNumber", "id_number", "v", None),
                    ("InternalName", "id", "n", None),
                    ("Name", "real_name", "s", None),
                    ("NamePlural", "real_name_plural", "s", None),
                    ("Pocket", "pocket", "v", None),
                    ("Price", "price", "u", None),
                    ("Description", "real_description", "q", None),
                    ("FieldUse", "field_use", "v", None),
                    ("BattleUse", "battle_use", "v", None),
                    ("Type", "type", "v", None),
                    ("Move", "move", "e", None)],
            "v20": [("Name", "real_name", "s", None),
                    ("NamePlural", "real_name_plural", "s", None),
                    ("Pocket", "pocket", "v", None),
                    ("Price", "price", "u", None),
                    ("SellPrice", "sell_price", "u", None),
                    ("FieldUse", "field_use", "e", ENUM_ITEM_FIELD_USE),
                    ("BattleUse", "battle_use", "e", ENUM_ITEM_BATTLE_USE),
                    ("Consumable", "consumable", "b", None),
                    ("Flags", "flags", "*s", None),
                    ("Move", "move", "e", None),
                    ("Description", "real_description", "q", None)],
            "v21": [("Name", "real_name", "s", None),
                    ("NamePlural", "real_name_plural", "s", None),
                    ("PortionName", "real_portion_name", "s", None),
                    ("PortionNamePlural", "real_portion_name_plural", "s", None),
                    ("Pocket", "pocket", "v", None),
                    ("Price", "price", "u", None),
                    ("SellPrice", "sell_price", "u", None),
                    ("BPPrice", "bp_price", "u", None),
                    ("FieldUse", "field_use", "e", ENUM_ITEM_FIELD_USE),
                    ("BattleUse", "battle_use", "e", ENUM_ITEM_BATTLE_USE),
                    ("Flags", "flags", "*s", None),
                    ("Consumable", "consumable", "b", None),
                    ("ShowQuantity", "show_quantity", "b", None),
                    ("Move", "move", "e", None),
                    ("Description", "real_description", "q", None)],
        },
    },
    {
        "key": "pokemon", "name": "宝可梦", "desc": "物种的种族值、特性、进化等主数据",
        "dat": ["species.dat"], "cls": "GameData::Species", "keymode": "symbol",
        "editor": "generic",
        "fname": {"v19": "pokemon.txt", "v20": "pokemon.txt",
                  "v21": "pokemon.txt"},
        "schema": {
            "v19": [("Name", "real_name", "s", None),
                    ("InternalName", "id", "n", None),
                    ("Type1", "type1", "e", None),
                    ("Type2", "type2", "e", None),
                    ("BaseStats", "base_stats", "uuuuuu", None),
                    ("GenderRate", "gender_ratio", "e", None),
                    ("GrowthRate", "growth_rate", "e", None),
                    ("BaseEXP", "base_exp", "v", None),
                    ("EffortPoints", "evs", "uuuuuu", None),
                    ("Rareness", "catch_rate", "u", None),
                    ("Happiness", "happiness", "u", None),
                    ("Abilities", "abilities", "*e", None),
                    ("HiddenAbility", "hidden_abilities", "*e", None),
                    ("Moves", "moves", "*ue", None),
                    ("TutorMoves", "tutor_moves", "*e", None),
                    ("EggMoves", "egg_moves", "*e", None),
                    ("Compatibility", "egg_groups", "*e", None),
                    ("StepsToHatch", "hatch_steps", "v", None),
                    ("Height", "height", "f", None),
                    ("Weight", "weight", "f", None),
                    ("Color", "color", "e", None),
                    ("Shape", "shape", "e", None),
                    ("Habitat", "habitat", "e", None),
                    ("Kind", "real_category", "s", None),
                    ("Pokedex", "real_pokedex_entry", "q", None),
                    ("FormName", "real_form_name", "q", None),
                    ("Generation", "generation", "i", None),
                    ("WildItemCommon", "wild_item_common", "e", None),
                    ("WildItemUncommon", "wild_item_uncommon", "e", None),
                    ("WildItemRare", "wild_item_rare", "e", None),
                    ("BattlerPlayerX", "back_sprite_x", "i", None),
                    ("BattlerPlayerY", "back_sprite_y", "i", None),
                    ("BattlerEnemyX", "front_sprite_x", "i", None),
                    ("BattlerEnemyY", "front_sprite_y", "i", None),
                    ("BattlerAltitude", "front_sprite_altitude", "i", None),
                    ("BattlerShadowX", "shadow_x", "i", None),
                    ("BattlerShadowSize", "shadow_size", "u", None),
                    ("Evolutions", "evolutions", "*ses", None),
                    ("Incense", "incense", "e", None)],
            "v20": [("Name", "real_name", "s", None),
                    ("Types", "types", "*e", None),
                    ("BaseStats", "base_stats", "vvvvvv", None),
                    ("GenderRatio", "gender_ratio", "e", None),
                    ("GrowthRate", "growth_rate", "e", None),
                    ("BaseExp", "base_exp", "v", None),
                    ("EVs", "evs", "*ev", None),
                    ("CatchRate", "catch_rate", "u", None),
                    ("Happiness", "happiness", "u", None),
                    ("Abilities", "abilities", "*e", None),
                    ("HiddenAbilities", "hidden_abilities", "*e", None),
                    ("Moves", "moves", "*ue", None),
                    ("TutorMoves", "tutor_moves", "*e", None),
                    ("EggMoves", "egg_moves", "*e", None),
                    ("EggGroups", "egg_groups", "*e", None),
                    ("HatchSteps", "hatch_steps", "v", None),
                    ("Incense", "incense", "e", None),
                    ("Offspring", "offspring", "*s", None),
                    ("Height", "height", "f", None),
                    ("Weight", "weight", "f", None),
                    ("Color", "color", "e", None),
                    ("Shape", "shape", "e", None),
                    ("Habitat", "habitat", "e", None),
                    ("Category", "real_category", "s", None),
                    ("Pokedex", "real_pokedex_entry", "q", None),
                    ("FormName", "real_form_name", "q", None),
                    ("Generation", "generation", "i", None),
                    ("Flags", "flags", "*s", None),
                    ("WildItemCommon", "wild_item_common", "*e", None),
                    ("WildItemUncommon", "wild_item_uncommon", "*e", None),
                    ("WildItemRare", "wild_item_rare", "*e", None),
                    ("Evolutions", "evolutions", "*ses", None)],
            "v21": [("Name", "real_name", "s", None),
                    ("FormName", "real_form_name", "q", None),
                    ("Types", "types", "*e", None),
                    ("BaseStats", "base_stats", "vvvvvv", None),
                    ("GenderRatio", "gender_ratio", "e", None),
                    ("GrowthRate", "growth_rate", "e", None),
                    ("BaseExp", "base_exp", "v", None),
                    ("EVs", "evs", "*ev", None),
                    ("CatchRate", "catch_rate", "u", None),
                    ("Happiness", "happiness", "u", None),
                    ("Abilities", "abilities", "*e", None),
                    ("HiddenAbilities", "hidden_abilities", "*e", None),
                    ("Moves", "moves", "*ue", None),
                    ("TutorMoves", "tutor_moves", "*e", None),
                    ("EggMoves", "egg_moves", "*e", None),
                    ("EggGroups", "egg_groups", "*e", None),
                    ("HatchSteps", "hatch_steps", "v", None),
                    ("Incense", "incense", "e", None),
                    ("Offspring", "offspring", "*s", None),
                    ("Height", "height", "f", None),
                    ("Weight", "weight", "f", None),
                    ("Color", "color", "e", None),
                    ("Shape", "shape", "e", None),
                    ("Habitat", "habitat", "e", None),
                    ("Category", "real_category", "s", None),
                    ("Pokedex", "real_pokedex_entry", "q", None),
                    ("Generation", "generation", "i", None),
                    ("Flags", "flags", "*s", None),
                    ("WildItemCommon", "wild_item_common", "*e", None),
                    ("WildItemUncommon", "wild_item_uncommon", "*e", None),
                    ("WildItemRare", "wild_item_rare", "*e", None),
                    ("Evolutions", "evolutions", "*ses", None)],
        },
    },
    {
        "key": "pokemon_forms", "name": "宝可梦形态", "desc": "地区形态、超进化等形态差异数据",
        "dat": ["species.dat"], "cls": "GameData::Species", "keymode": "symbol",
        "editor": "generic",
        "fname": {"v19": "pokemonforms.txt", "v20": "pokemon_forms.txt",
                  "v21": "pokemon_forms.txt"},
        "schema": {
            "v19": [("FormName", "real_form_name", "q", None),
                    ("PokedexForm", "pokedex_form", "u", None),
                    ("MegaStone", "mega_stone", "e", None),
                    ("MegaMove", "mega_move", "e", None),
                    ("UnmegaForm", "unmega_form", "u", None),
                    ("MegaMessage", "mega_message", "u", None),
                    ("Type1", "type1", "e", None),
                    ("Type2", "type2", "e", None),
                    ("BaseStats", "base_stats", "uuuuuu", None),
                    ("BaseEXP", "base_exp", "v", None),
                    ("EffortPoints", "evs", "uuuuuu", None),
                    ("Rareness", "catch_rate", "u", None),
                    ("Happiness", "happiness", "u", None),
                    ("Abilities", "abilities", "*e", None),
                    ("HiddenAbility", "hidden_abilities", "*e", None),
                    ("Moves", "moves", "*ue", None),
                    ("TutorMoves", "tutor_moves", "*e", None),
                    ("EggMoves", "egg_moves", "*e", None),
                    ("Compatibility", "egg_groups", "*e", None),
                    ("StepsToHatch", "hatch_steps", "v", None),
                    ("Height", "height", "f", None),
                    ("Weight", "weight", "f", None),
                    ("Color", "color", "e", None),
                    ("Shape", "shape", "e", None),
                    ("Habitat", "habitat", "e", None),
                    ("Kind", "real_category", "s", None),
                    ("Pokedex", "real_pokedex_entry", "q", None),
                    ("Generation", "generation", "i", None),
                    ("WildItemCommon", "wild_item_common", "e", None),
                    ("WildItemUncommon", "wild_item_uncommon", "e", None),
                    ("WildItemRare", "wild_item_rare", "e", None),
                    ("BattlerPlayerX", "back_sprite_x", "i", None),
                    ("BattlerPlayerY", "back_sprite_y", "i", None),
                    ("BattlerEnemyX", "front_sprite_x", "i", None),
                    ("BattlerEnemyY", "front_sprite_y", "i", None),
                    ("BattlerAltitude", "front_sprite_altitude", "i", None),
                    ("BattlerShadowX", "shadow_x", "i", None),
                    ("BattlerShadowSize", "shadow_size", "u", None),
                    ("Evolutions", "evolutions", "*ees", None)],
            "v20": [("FormName", "real_form_name", "q", None),
                    ("PokedexForm", "pokedex_form", "u", None),
                    ("MegaStone", "mega_stone", "e", None),
                    ("MegaMove", "mega_move", "e", None),
                    ("UnmegaForm", "unmega_form", "u", None),
                    ("MegaMessage", "mega_message", "u", None),
                    ("Types", "types", "*e", None),
                    ("BaseStats", "base_stats", "vvvvvv", None),
                    ("BaseExp", "base_exp", "v", None),
                    ("EVs", "evs", "*ev", None),
                    ("CatchRate", "catch_rate", "u", None),
                    ("Happiness", "happiness", "u", None),
                    ("Abilities", "abilities", "*e", None),
                    ("HiddenAbilities", "hidden_abilities", "*e", None),
                    ("Moves", "moves", "*ue", None),
                    ("TutorMoves", "tutor_moves", "*e", None),
                    ("EggMoves", "egg_moves", "*e", None),
                    ("EggGroups", "egg_groups", "*e", None),
                    ("HatchSteps", "hatch_steps", "v", None),
                    ("Offspring", "offspring", "*e", None),
                    ("Height", "height", "f", None),
                    ("Weight", "weight", "f", None),
                    ("Color", "color", "e", None),
                    ("Shape", "shape", "e", None),
                    ("Habitat", "habitat", "e", None),
                    ("Category", "real_category", "s", None),
                    ("Pokedex", "real_pokedex_entry", "q", None),
                    ("Generation", "generation", "i", None),
                    ("Flags", "flags", "*s", None),
                    ("WildItemCommon", "wild_item_common", "*e", None),
                    ("WildItemUncommon", "wild_item_uncommon", "*e", None),
                    ("WildItemRare", "wild_item_rare", "*e", None),
                    ("Evolutions", "evolutions", "*ees", None)],
            "v21": [("FormName", "real_form_name", "q", None),
                    ("PokedexForm", "pokedex_form", "u", None),
                    ("MegaStone", "mega_stone", "e", None),
                    ("MegaMove", "mega_move", "e", None),
                    ("UnmegaForm", "unmega_form", "u", None),
                    ("MegaMessage", "mega_message", "u", None),
                    ("Types", "types", "*e", None),
                    ("BaseStats", "base_stats", "vvvvvv", None),
                    ("BaseExp", "base_exp", "v", None),
                    ("EVs", "evs", "*ev", None),
                    ("CatchRate", "catch_rate", "u", None),
                    ("Happiness", "happiness", "u", None),
                    ("Abilities", "abilities", "*e", None),
                    ("HiddenAbilities", "hidden_abilities", "*e", None),
                    ("Moves", "moves", "*ue", None),
                    ("TutorMoves", "tutor_moves", "*e", None),
                    ("EggMoves", "egg_moves", "*e", None),
                    ("EggGroups", "egg_groups", "*e", None),
                    ("HatchSteps", "hatch_steps", "v", None),
                    ("Offspring", "offspring", "*e", None),
                    ("Height", "height", "f", None),
                    ("Weight", "weight", "f", None),
                    ("Color", "color", "e", None),
                    ("Shape", "shape", "e", None),
                    ("Habitat", "habitat", "e", None),
                    ("Category", "real_category", "s", None),
                    ("Pokedex", "real_pokedex_entry", "q", None),
                    ("Generation", "generation", "i", None),
                    ("Flags", "flags", "*s", None),
                    ("WildItemCommon", "wild_item_common", "*e", None),
                    ("WildItemUncommon", "wild_item_uncommon", "*e", None),
                    ("WildItemRare", "wild_item_rare", "*e", None),
                    ("Evolutions", "evolutions", "*ees", None)],
        },
    },
    {
        "key": "pokemon_metrics", "name": "宝可梦坐标", "desc": "战斗画面上的精灵图偏移与影子",
        "dat": ["species_metrics.dat"], "cls": "GameData::SpeciesMetrics",
        "keymode": "symbol", "editor": "generic", "families": ("v20", "v21"),
        "fname": {"v19": "pokemonmetrics.txt", "v20": "pokemon_metrics.txt",
                  "v21": "pokemon_metrics.txt"},
        "schema": {
            "v20": [("BackSprite", "back_sprite", "ii", None),
                    ("FrontSprite", "front_sprite", "ii", None),
                    ("FrontSpriteAltitude", "front_sprite_altitude", "i", None),
                    ("ShadowX", "shadow_x", "i", None),
                    ("ShadowSize", "shadow_size", "u", None)],
            "v21": [("BackSprite", "back_sprite", "ii", None),
                    ("FrontSprite", "front_sprite", "ii", None),
                    ("FrontSpriteAltitude", "front_sprite_altitude", "i", None),
                    ("ShadowX", "shadow_x", "i", None),
                    ("ShadowSize", "shadow_size", "u", None)],
        },
    },
    {
        "key": "berry_plants", "name": "树果", "desc": "树果的生长时间与产量",
        "dat": ["berry_plants.dat"], "cls": "GameData::BerryPlant",
        "keymode": "symbol", "editor": "generic",
        "fname": {"v19": "berryplants.txt", "v20": "berry_plants.txt",
                  "v21": "berry_plants.txt"},
        "style": {"v19": "kv"},
        "schema": {
            "v19": [("Yield", None, "kv", None)],
            "v20": [("HoursPerStage", "hours_per_stage", "v", None),
                    ("DryingPerHour", "drying_per_hour", "u", None),
                    ("Yield", "yield", "uv", None)],
            "v21": [("HoursPerStage", "hours_per_stage", "v", None),
                    ("DryingPerHour", "drying_per_hour", "u", None),
                    ("Yield", "yield", "uv", None)],
        },
        "v19kv": ["hours_per_stage", "drying_per_hour", "minimum_yield",
                  "maximum_yield"],
    },
    {
        "key": "ribbons", "name": "勋章", "desc": "勋章的名字与描述",
        "dat": ["ribbons.dat"], "cls": "GameData::Ribbon", "keymode": "symbol",
        "editor": "generic",
        "fname": {"v19": "ribbons.txt", "v20": "ribbons.txt",
                  "v21": "ribbons.txt"},
        "style": {"v19": "line"},
        "schema": {
            "v19": [("IdNumber", "id_number", "v", None),
                    ("InternalName", "id", "n", None),
                    ("Name", "real_name", "s", None),
                    ("Description", "real_description", "q", None)],
            "v20": [("Name", "real_name", "s", None),
                    ("IconPosition", "icon_position", "u", None),
                    ("Description", "real_description", "q", None),
                    ("Flags", "flags", "*s", None)],
            "v21": [("Name", "real_name", "s", None),
                    ("IconPosition", "icon_position", "u", None),
                    ("Description", "real_description", "q", None),
                    ("Flags", "flags", "*s", None)],
        },
    },
    {
        "key": "trainer_types", "name": "训练家类型", "desc": "训练家类别的名字与金钱",
        "dat": ["trainer_types.dat"], "cls": "GameData::TrainerType",
        "keymode": "symbol", "editor": "generic",
        "fname": {"v19": "trainertypes.txt", "v20": "trainer_types.txt",
                  "v21": "trainer_types.txt"},
        "style": {"v19": "line"},
        "schema": {
            "v19": [("IdNumber", "id_number", "v", None),
                    ("InternalName", "id", "n", None),
                    ("Name", "real_name", "s", None),
                    ("BaseMoney", "base_money", "u", None),
                    ("BattleBGM", "battle_BGM", "s", None),
                    ("VictoryME", "victory_ME", "s", None),
                    ("IntroME", "intro_ME", "s", None),
                    ("Gender", "gender", "e", ENUM_GENDER),
                    ("SkillLevel", "skill_level", "u", None),
                    ("SkillCode", "skill_code", "s", None)],
            "v20": [("Name", "real_name", "s", None),
                    ("BaseMoney", "base_money", "u", None),
                    ("SkillLevel", "skill_level", "u", None),
                    ("Flags", "flags", "*s", None),
                    ("IntroBGM", "intro_BGM", "s", None),
                    ("BattleBGM", "battle_BGM", "s", None),
                    ("VictoryBGM", "victory_BGM", "s", None)],
            "v21": [("Name", "real_name", "s", None),
                    ("BaseMoney", "base_money", "u", None),
                    ("SkillLevel", "skill_level", "u", None),
                    ("Flags", "flags", "*s", None),
                    ("IntroBGM", "intro_BGM", "s", None),
                    ("BattleBGM", "battle_BGM", "s", None),
                    ("VictoryBGM", "victory_BGM", "s", None)],
        },
    },
    {
        "key": "trainers", "name": "训练家", "desc": "每个训练家的队伍与台词",
        "dat": ["trainers.dat"], "cls": "GameData::Trainer", "keymode": "symbol",
        "editor": "trainers",
        "fname": {"v19": "trainers.txt", "v20": "trainers.txt",
                  "v21": "trainers.txt"},
        "schema": {
            "v19": [("Items", "items", "*e", None),
                    ("LoseText", "real_lose_text", "q", None)],
            "v20": [("Items", "items", "*e", None),
                    ("LoseText", "real_lose_text", "q", None)],
            "v21": [("Items", "items", "*e", None),
                    ("LoseText", "real_lose_text", "q", None)],
        },
        # 每只宝可梦的子字段（缩进四空格的那批）
        "sub_schema": {
            "v19": [("Name", "name", "s", None),
                    ("Form", "form", "u", None),
                    ("Gender", "gender", "s", None),
                    ("Shiny", "shininess", "b", None),
                    ("Shadow", "shadowness", "b", None),
                    ("Moves", "moves", "*e", None),
                    ("Ability", "ability_flag", "u", None),
                    ("AbilityIndex", "ability_index", "u", None),
                    ("Item", "item", "e", None),
                    ("Nature", "nature", "e", None),
                    ("IV", "iv", "uuuuuu", None),
                    ("EV", "ev", "uuuuuu", None),
                    ("Happiness", "happiness", "u", None),
                    ("Ball", "poke_ball", "ball", None)],
            "v20": [("Name", "name", "s", None),
                    ("Form", "form", "u", None),
                    ("Gender", "gender", "s", None),
                    ("Shiny", "shininess", "b", None),
                    ("SuperShiny", "super_shininess", "b", None),
                    ("Shadow", "shadowness", "b", None),
                    ("Moves", "moves", "*e", None),
                    ("Ability", "ability_index", "u", None),
                    ("Item", "item", "e", None),
                    ("Nature", "nature", "e", None),
                    ("IV", "iv", "uuuuuu", None),
                    ("EV", "ev", "uuuuuu", None),
                    ("Happiness", "happiness", "u", None),
                    ("Ball", "poke_ball", "ball", None)],
            "v21": [("Name", "name", "s", None),
                    ("Form", "form", "u", None),
                    ("Gender", "gender", "s", None),
                    ("Shiny", "shininess", "b", None),
                    ("SuperShiny", "super_shininess", "b", None),
                    ("Shadow", "shadowness", "b", None),
                    ("Moves", "moves", "*e", None),
                    ("Ability", "ability_index", "u", None),
                    ("Item", "item", "e", None),
                    ("Nature", "nature", "e", None),
                    ("IV", "iv", "uuuuuu", None),
                    ("EV", "ev", "uuuuuu", None),
                    ("Happiness", "happiness", "u", None),
                    ("Ball", "poke_ball", "ball", None)],
        },
    },
    {
        "key": "metadata", "name": "元数据", "desc": "全局设置与玩家角色（Home/金钱/BGM）",
        "dat": ["metadata.dat", "player_metadata.dat"],
        "cls": "GameData::Metadata", "keymode": "idnum", "editor": "metadata",
        "fname": {"v19": "metadata.txt", "v20": "metadata.txt",
                  "v21": "metadata.txt"},
        "schema": {
            "v19": [("Home", "home", "vuuu", None),
                    ("WildBattleBGM", "wild_battle_BGM", "s", None),
                    ("TrainerBattleBGM", "trainer_battle_BGM", "s", None),
                    ("WildVictoryME", "wild_victory_ME", "s", None),
                    ("TrainerVictoryME", "trainer_victory_ME", "s", None),
                    ("SurfBGM", "surf_BGM", "s", None),
                    ("BicycleBGM", "bicycle_BGM", "s", None),
                    ("PlayerA", "player_A", "player", None),
                    ("PlayerB", "player_B", "player", None),
                    ("PlayerC", "player_C", "player", None),
                    ("PlayerD", "player_D", "player", None),
                    ("PlayerE", "player_E", "player", None),
                    ("PlayerF", "player_F", "player", None),
                    ("PlayerG", "player_G", "player", None),
                    ("PlayerH", "player_H", "player", None)],
            "v20": [("StartMoney", "start_money", "u", None),
                    ("Home", "home", "vuuu", None),
                    ("StorageCreator", "real_storage_creator", "s", None),
                    ("WildBattleBGM", "wild_battle_BGM", "s", None),
                    ("TrainerBattleBGM", "trainer_battle_BGM", "s", None),
                    ("WildVictoryBGM", "wild_victory_BGM", "s", None),
                    ("TrainerVictoryBGM", "trainer_victory_BGM", "s", None),
                    ("SurfBGM", "surf_BGM", "s", None),
                    ("BicycleBGM", "bicycle_BGM", "s", None)],
            "v21": [("StartMoney", "start_money", "u", None),
                    ("StartItemStorage", "start_item_storage", "*e", None),
                    ("Home", "home", "vuuu", None),
                    ("StorageCreator", "real_storage_creator", "s", None),
                    ("WildBattleBGM", "wild_battle_BGM", "s", None),
                    ("TrainerBattleBGM", "trainer_battle_BGM", "s", None),
                    ("WildVictoryBGM", "wild_victory_BGM", "s", None),
                    ("TrainerVictoryBGM", "trainer_victory_BGM", "s", None),
                    ("SurfBGM", "surf_BGM", "s", None),
                    ("BicycleBGM", "bicycle_BGM", "s", None)],
        },
        # v20/v21：metadata.txt 里 >0 的段是玩家角色（player_metadata）
        "player_schema": {
            "v20": [("TrainerType", "trainer_type", "e", None),
                    ("WalkCharset", "walk_charset", "s", None),
                    ("RunCharset", "run_charset", "s", None),
                    ("CycleCharset", "cycle_charset", "s", None),
                    ("SurfCharset", "surf_charset", "s", None),
                    ("DiveCharset", "dive_charset", "s", None),
                    ("FishCharset", "fish_charset", "s", None),
                    ("SurfFishCharset", "surf_fish_charset", "s", None),
                    ("Home", "home", "vuuu", None)],
            "v21": [("TrainerType", "trainer_type", "e", None),
                    ("WalkCharset", "walk_charset", "s", None),
                    ("RunCharset", "run_charset", "s", None),
                    ("CycleCharset", "cycle_charset", "s", None),
                    ("SurfCharset", "surf_charset", "s", None),
                    ("DiveCharset", "dive_charset", "s", None),
                    ("FishCharset", "fish_charset", "s", None),
                    ("SurfFishCharset", "surf_fish_charset", "s", None),
                    ("Home", "home", "vuuu", None)],
        },
        # v19：metadata.txt 里 >0 的段是地图元数据（map_metadata）
        "v19map_schema": [
            ("Outdoor", "outdoor_map", "b", None),
            ("ShowArea", "announce_location", "b", None),
            ("Bicycle", "can_bicycle", "b", None),
            ("BicycleAlways", "always_bicycle", "b", None),
            ("HealingSpot", "teleport_destination", "vuu", None),
            ("MapPosition", "town_map_position", "uuu", None),
            ("DarkMap", "dark_map", "b", None),
            ("SafariMap", "safari_map", "b", None),
            ("SnapEdges", "snap_edges", "b", None),
            ("StillReflections", "still_reflections", "b", None),
            ("Dungeon", "random_dungeon", "b", None),
            ("BattleBack", "battle_background", "s", None),
            ("WildBattleBGM", "wild_battle_BGM", "s", None),
            ("TrainerBattleBGM", "trainer_battle_BGM", "s", None),
            ("WildVictoryME", "wild_victory_ME", "s", None),
            ("TrainerVictoryME", "trainer_victory_ME", "s", None),
            ("WildCaptureME", "wild_capture_ME", "s", None),
        ],
    },
    {
        "key": "map_metadata", "name": "地图元数据", "desc": "每张地图的名字、野外 BGM 等",
        "dat": ["map_metadata.dat"], "cls": "GameData::MapMetadata",
        "keymode": "idnum", "editor": "generic", "families": ("v20", "v21"),
        "fname": {"v19": "mapmetadata.txt", "v20": "map_metadata.txt",
                  "v21": "map_metadata.txt"},
        "schema": {
            "v20": [("Name", "real_name", "s", None),
                    ("Outdoor", "outdoor_map", "b", None),
                    ("ShowArea", "announce_location", "b", None),
                    ("Bicycle", "can_bicycle", "b", None),
                    ("BicycleAlways", "always_bicycle", "b", None),
                    ("HealingSpot", "teleport_destination", "vuu", None),
                    ("MapPosition", "town_map_position", "uuu", None),
                    ("DarkMap", "dark_map", "b", None),
                    ("SafariMap", "safari_map", "b", None),
                    ("SnapEdges", "snap_edges", "b", None),
                    ("StillReflections", "still_reflections", "b", None),
                    ("Dungeon", "random_dungeon", "b", None),
                    ("BattleBack", "battle_background", "s", None),
                    ("WildBattleBGM", "wild_battle_BGM", "s", None),
                    ("TrainerBattleBGM", "trainer_battle_BGM", "s", None),
                    ("WildVictoryBGM", "wild_victory_BGM", "s", None),
                    ("TrainerVictoryBGM", "trainer_victory_BGM", "s", None),
                    ("WildCaptureME", "wild_capture_ME", "s", None),
                    ("Flags", "flags", "*s", None)],
            "v21": [("Name", "real_name", "s", None),
                    ("Outdoor", "outdoor_map", "b", None),
                    ("ShowArea", "announce_location", "b", None),
                    ("Bicycle", "can_bicycle", "b", None),
                    ("BicycleAlways", "always_bicycle", "b", None),
                    ("HealingSpot", "teleport_destination", "vuu", None),
                    ("MapPosition", "town_map_position", "uuu", None),
                    ("DiveMap", "dive_map_id", "v", None),
                    ("DarkMap", "dark_map", "b", None),
                    ("SafariMap", "safari_map", "b", None),
                    ("SnapEdges", "snap_edges", "b", None),
                    ("StillReflections", "still_reflections", "b", None),
                    ("Dungeon", "random_dungeon", "b", None),
                    ("BattleBack", "battle_background", "s", None),
                    ("WildBattleBGM", "wild_battle_BGM", "s", None),
                    ("TrainerBattleBGM", "trainer_battle_BGM", "s", None),
                    ("WildVictoryBGM", "wild_victory_BGM", "s", None),
                    ("TrainerVictoryBGM", "trainer_victory_BGM", "s", None),
                    ("WildCaptureME", "wild_capture_ME", "s", None),
                    ("MapSize", "town_map_size", "us", None),
                    ("Flags", "flags", "*s", None)],
        },
    },
    {
        "key": "town_map", "name": "区域地图", "desc": "城镇地图的区域与地点",
        "dat": ["town_map.dat"], "cls": "GameData::TownMap", "keymode": "idnum",
        "editor": "townmap",
        "fname": {"v19": "townmap.txt", "v20": "town_map.txt",
                  "v21": "town_map.txt"},
    },
    {
        "key": "map_connections", "name": "地图连接", "desc": "地图之间的出入口",
        "dat": ["map_connections.dat"], "cls": None, "keymode": "array",
        "editor": "connections",
        "fname": {"v19": "connections.txt", "v20": "map_connections.txt",
                  "v21": "map_connections.txt"},
    },
    {
        "key": "regional_dexes", "name": "地区图鉴", "desc": "各地区图鉴的收录顺序",
        "dat": ["regional_dexes.dat"], "cls": None, "keymode": "array",
        "editor": "regional",
        "fname": {"v19": "regionaldexes.txt", "v20": "regional_dexes.txt",
                  "v21": "regional_dexes.txt"},
    },
    {
        "key": "encounters", "name": "野生遭遇", "desc": "每张地图的野生宝可梦与概率",
        "dat": ["encounters.dat"], "cls": "GameData::Encounter",
        "keymode": "symbol", "editor": "encounters",
        "fname": {"v19": "encounters.txt", "v20": "encounters.txt",
                  "v21": "encounters.txt"},
    },
    {
        "key": "shadow_pokemon", "name": "暗黑宝可梦", "desc": "暗黑宝可梦的计量槽与招式",
        "dat": ["shadow_pokemon.dat"], "cls": "GameData::ShadowPokemon",
        "keymode": "symbol", "editor": "generic", "families": ("v20", "v21"),
        "fname": {"v19": "shadowmoves.txt", "v20": "shadow_pokemon.txt",
                  "v21": "shadow_pokemon.txt"},
        "style": {"v19": "kv"},
        "schema": {
            "v20": [("GaugeSize", "gauge_size", "v", None),
                    ("Moves", "moves", "*e", None),
                    ("Flags", "flags", "*s", None)],
            "v21": [("GaugeSize", "gauge_size", "v", None),
                    ("Flags", "flags", "*s", None)],
        },
        "v19kv": ["moves"],
    },
    {
        "key": "dungeon_parameters", "name": "迷宫参数", "desc": "随机迷宫的生成参数",
        "dat": ["dungeon_parameters.dat"], "cls": "GameData::DungeonParameters",
        "keymode": "symbol", "editor": "generic", "families": ("v21",),
        "fname": {"v21": "dungeon_parameters.txt"},
        "schema": {
            "v21": [("DungeonSize", "dungeon_size", "vv", None),
                    ("CellSize", "cell_size", "vv", None),
                    ("MinRoomSize", "min_room_size", "vv", None),
                    ("MaxRoomSize", "max_room_size", "vv", None),
                    ("CorridorWidth", "corridor_width", "v", None),
                    ("ShiftCorridors", "random_corridor_shift", "b", None),
                    ("NodeLayout", "node_layout", "m", None),
                    ("RoomLayout", "room_layout", "m", None),
                    ("RoomChance", "room_chance", "v", None),
                    ("ExtraConnections", "extra_connections_count", "u", None),
                    ("FloorPatches", "floor_patches", "vvu", None),
                    ("FloorDecorations", "floor_decorations", "uu", None),
                    ("VoidDecorations", "void_decorations", "uu", None),
                    ("RNGSeed", "rng_seed", "u", None),
                    ("Flags", "flags", "*s", None)],
        },
    },
    {
        "key": "dungeon_tilesets", "name": "迷宫图块", "desc": "随机迷宫用的图块规则",
        "dat": ["dungeon_tilesets.dat"], "cls": "GameData::DungeonTileset",
        "keymode": "idnum", "editor": "generic", "families": ("v21",),
        "fname": {"v21": "dungeon_tilesets.txt"},
        "schema": {
            "v21": [("Autotile", "autotile", "^um", None),
                    ("Tile", "tile", "^um", None),
                    ("SnapToLargeGrid", "snap_to_large_grid", "b", None),
                    ("LargeVoidTiles", "large_void_tiles", "b", None),
                    ("LargeWallTiles", "large_wall_tiles", "b", None),
                    ("LargeFloorTiles", "large_floor_tiles", "b", None),
                    ("DoubleWalls", "double_walls", "b", None),
                    ("FloorPatchUnderWalls", "floor_patch_under_walls", "b", None),
                    ("ThinNorthWallOffset", "thin_north_wall_offset", "i", None),
                    ("Flags", "flags", "*s", None)],
        },
    },
    {
        "key": "phone", "name": "电话消息", "desc": "训练师的来电问候与台词",
        "dat": ["phone.dat"], "cls": "GameData::PhoneMessage",
        "keymode": "symbol", "editor": "phone",
        "fname": {"v19": "phone.txt", "v20": "phone.txt", "v21": "phone.txt"},
    },
    {
        "key": "battle_facility_lists", "name": "对战设施名单",
        "desc": "对战塔／ cups 的训练家与宝可梦名单文件",
        "dat": ["trainer_lists.dat"], "cls": None, "keymode": "array",
        "editor": "facility",
        "fname": {"v19": "trainerlists.txt", "v20": "battle_facility_lists.txt",
                  "v21": "battle_facility_lists.txt"},
    },
]

FILES_BY_KEY = {f["key"]: f for f in FILES}


def file_for(key: str) -> Optional[dict]:
    return FILES_BY_KEY.get(key)


def style_of(spec: dict, family: str) -> str:
    """section / line / kv / custom。"""
    return (spec.get("style") or {}).get(family, "section")


def supports(spec: dict, family: str) -> bool:
    fams = spec.get("families")
    if fams and family not in fams:
        return False
    return family in spec.get("fname", {})


def txt_name(spec: dict, family: str) -> str:
    return spec["fname"].get(family) or spec["fname"].get("v21") \
        or next(iter(spec["fname"].values()))


def schema_of(spec: dict, family: str) -> List[tuple]:
    return spec.get("schema", {}).get(family) or []


def pbs_dir(game_root: str) -> str:
    return os.path.join(game_root, PBS_DIR_NAME)


# ---------------------------------------------------------------------------
# 字段中文说明（编辑界面在每个输入框下面显示一行）
# ---------------------------------------------------------------------------
# 键 = schema 里的 PBS 字段名（各版本同名同义，写一份就够）
FIELD_DESC: Dict[str, str] = {
    # ---- 通用 ----
    "Name": "显示名（游戏里看到的文字）",
    "InternalName": "内部编号，程序用它认这项数据；改动要同步脚本/存档",
    "Description": "图鉴/说明文字里显示的描述",
    "Flags": "附加标记（逗号分隔），程序按名字判断特殊行为",
    "IdNumber": "内部数字编号（老版本用），改动要同步脚本/存档",
    "FunctionCode_hex": "战斗效果编号，写成十六进制（如 16F）；None/000 表示没有特殊效果",

    # ---- 属性 ----
    "IconPosition": "属性图标在图集里的位置（0 开始）",
    "IsSpecialType": "勾上算「特殊」属性（按特攻/特防结算），取消算物理",
    "IsPseudoType": "勾上表示这是伪属性（???、暗黑等，不进正常相克表）",
    "Weaknesses": "弱点属性（受这些属性攻击时伤害 ×2）",
    "Resistances": "抗性属性（受这些属性攻击时伤害 ×½）",
    "Immunities": "免疫属性（这些属性打不到，伤害 ×0）",

    # ---- 招式 ----
    "Type": "招式属性",
    "Category": "分类：Physical 物理 / Special 特殊 / Status 变化",
    "BaseDamage": "威力（变化招式填 0）",
    "Power": "威力（变化招式填 0）",
    "Accuracy": "命中率（1~100，填 0 表示必中）",
    "TotalPP": "初始 PP（使用次数）",
    "Target": "作用目标（NearOther 单体、AllNearFoes 全体对手…）",
    "FunctionCode": "战斗效果编号（十六进制；None 表示没有特殊效果）",
    "Priority": "优先度（正数先出手，负数后出手）",
    "EffectChance": "附加效果的触发概率（0 = 必定触发）",

    # ---- 道具 ----
    "NamePlural": "复数名（英文用，如 Potions）",
    "PortionName": "量词单位（如「一口药」），显示「一口药」时用",
    "PortionNamePlural": "量词单位复数",
    "Pocket": "所在背包口袋的编号（1 道具、2 精灵球、3 战斗道具…）",
    "Price": "商店售价（买价）",
    "SellPrice": "卖价（不填默认是买价的一半）",
    "BPPrice": "对战点数（BP）价格",
    "FieldUse": "在地图上的使用方式：Direct 直接使用 / TM-/HM 教学机 / OnPokemon 对宝可梦用",
    "BattleUse": "战斗中的使用方式：Direct 直接用 / OnPokemon 对自己宝可梦 / OnFoe 对对手",
    "Consumable": "勾上 = 用掉后消失（一般道具都勾）",
    "ShowQuantity": "勾上 = 背包里显示数量",
    "Move": "关联招式（教学机、某些道具要用）",

    # ---- 宝可梦 ----
    "FormName": "形态名（地区形态/超进化形态才有）",
    "Kind": "图鉴分类（如「种子宝可梦」）",
    "Pokedex": "图鉴说明文字",
    "Type1": "第一属性",
    "Type2": "第二属性（只有一个属性时和第一属性填一样）",
    "Types": "属性（最多两个，逗号分隔）",
    "BaseStats": "种族值：HP,攻击,防御,特攻,特防,速度（v19 是 HP,攻击,防御,速度,特攻,特防）",
    "EffortPoints": "打败它时给的努力值：HP,攻击,防御,速度,特攻,特防（一般给 1~3 点）",
    "EVs": "打败它时给的努力值（属性,点数，可写多对）",
    "BaseEXP": "基础经验值（打它拿到多少经验）",
    "BaseExp": "基础经验值（打它拿到多少经验）",
    "GrowthRate": "升级曲线：Fast/Medium/Slow/Parabolic 等",
    "GenderRate": "性别比例：Female50Percent 各半、FemaleOneEighth 母 1/8、Genderless 无性别",
    "GenderRate_old": "性别比例（旧版写法）",
    "Rareness": "捕获率（0~255，越大越好抓）",
    "CatchRate": "捕获率（0~255，越大越好抓）",
    "Happiness": "初始亲密度（0~255，一般 70）",
    "Abilities": "普通特性（最多两个，逗号分隔）",
    "HiddenAbility": "隐藏特性（俗称梦特）",
    "HiddenAbilities": "隐藏特性（俗称梦特）",
    "TutorMoves": "教学招式（招式教学屋 / 招式学习器能学到的招式）",
    "EggMoves": "蛋招式（孵蛋遗传能学到的招式）",
    "Compatibility": "蛋组（Monster/Water1/Ditto…，决定能和谁生蛋）",
    "EggGroups": "蛋组（Monster/Water1/Ditto…，决定能和谁生蛋）",
    "StepsToHatch": "孵蛋步数（越大越难孵）",
    "HatchSteps": "孵蛋步数（越大越难孵）",
    "Incense": "需要携带的熏香道具（某些幼体的父母必须带它才会生蛋）",
    "Offspring": "生蛋结果的物种（留空 = 生自己）",
    "WildItemCommon": "野生携带道具：常见（50%）",
    "WildItemUncommon": "野生携带道具：少见（5%）",
    "WildItemRare": "野生携带道具：罕见（1%）",
    "Height": "身高（米，如 0.7）",
    "Weight": "体重（千克，如 6.9）",
    "Color": "图鉴颜色（Red/Blue/Green…）",
    "Shape": "体型（Quadruped 四足、Bipedal 两足…，图鉴搜索用）",
    "Habitat": "栖息地（Grassland/Forest/Cave…）",
    "Generation": "初次登场的世代（1 = 第一世代）",
    "BattlerPlayerX": "战斗中我方精灵图的横向偏移",
    "BattlerPlayerY": "战斗中我方精灵图的纵向偏移",
    "BattlerEnemyX": "战斗中敌方精灵图的横向偏移",
    "BattlerEnemyY": "战斗中敌方精灵图的纵向偏移",
    "BattlerAltitude": "精灵图悬空高度（飞行的宝可梦调大）",
    "BattlerShadowX": "影子横向偏移",
    "BattlerShadowSize": "影子大小（1~3）",
    "Evolutions": "进化：目标,方式,参数（如 IVYSAUR,Level,16；一行一……逗号连写）",
    "PokedexForm": "图鉴里显示的形态编号（和实际形态不同时才填）",
    "MegaStone": "超进化需要的石头（内部名）",
    "MegaMove": "超进化后变化的招式",
    "UnmegaForm": "超进化解除后变回的形态编号",
    "MegaMessage": "超进化时的提示编号（0 = 不提示）",

    # ---- 战斗坐标 ----
    "BackSprite": "背面精灵图偏移：x,y",
    "FrontSprite": "正面精灵图偏移：x,y",
    "FrontSpriteAltitude": "正面精灵图悬空高度",
    "ShadowX": "影子横向偏移",
    "ShadowSize": "影子大小（1~3）",

    # ---- 树果 ----
    "HoursPerStage": "每个生长阶段要几小时",
    "DryingPerHour": "每小时流失多少水分（越大越快枯萎）",
    "Yield": "产量范围：最少,最多",

    # ---- 训练家类型 ----
    "BaseMoney": "打赢后给的基础奖金",
    "SkillLevel": "AI 水平（0~100，越大越会打）",
    "IntroBGM": "战斗开场音乐文件名（不含扩展名）",
    "BattleBGM": "战斗音乐文件名",
    "VictoryBGM": "胜利音乐文件名",
    "VictoryME": "胜利音效文件名（旧版写法）",
    "IntroME": "开场音效文件名（旧版写法）",
    "Gender": "训练家头像性别：Male / Female / Mixed",
    "SkillCode": "AI 技能编号（旧版用，可留空）",

    # ---- 训练家 ----
    "Items": "训练家身上带的道具（打赢后可能捡到）",
    "LoseText": "被打败时说的话（\\PN 会自动换成玩家名）",

    # ---- 元数据 ----
    "StartMoney": "新游戏开局给多少金钱",
    "StartItemStorage": "开局就放进电脑道具箱的道具",
    "Home": "出生点：地图编号,x,y,朝向",
    "StorageCreator": "电脑箱子的管理员名字",
    "WildBattleBGM": "野外战斗音乐",
    "TrainerBattleBGM": "训练家战斗音乐",
    "WildVictoryBGM": "打赢野生宝可梦的音乐",
    "TrainerVictoryBGM": "打赢训练家的音乐",
    "WildVictoryME": "打赢野生宝可梦的音效（旧版写法）",
    "TrainerVictoryME": "打赢训练家的音效（旧版写法）",
    "WildCaptureME": "抓到宝可梦的音效",
    "SurfBGM": "冲浪时的音乐",
    "BicycleBGM": "骑自行车时的音乐",
    "TrainerType": "该玩家角色用的训练家类型",
    "WalkCharset": "走路图（Graphics/Characters 下的文件名）",
    "RunCharset": "跑步图",
    "CycleCharset": "骑车图",
    "SurfCharset": "冲浪图",
    "DiveCharset": "潜水图",
    "FishCharset": "钓鱼图",
    "SurfFishCharset": "冲浪钓鱼图",

    # ---- 地图元数据 ----
    "Outdoor": "勾上 = 这是一张户外地图（影响天气、遇敌等）",
    "ShowArea": "勾上 = 进入地图时左上角显示地名",
    "Bicycle": "勾上 = 允许在这张地图骑车",
    "BicycleAlways": "勾上 = 进入这张地图自动上车",
    "HealingSpot": "昏迷后送回的复活点：地图编号,x,y",
    "MapPosition": "在区域地图上的位置：区域编号,x,y",
    "DiveMap": "潜下去会到达的地图编号",
    "DarkMap": "勾上 = 这张地图是黑的（需要闪光）",
    "SafariMap": "勾上 = 野生原野区（用原野球、有步数限制）",
    "SnapEdges": "勾上 = 地图边界可以贴边行走",
    "StillReflections": "勾上 = 水面倒影不动",
    "Dungeon": "勾上 = 随机迷宫地图",
    "BattleBack": "用的战斗背景（field/cave/sand…）",
    "MapSize": "在区域地图上的大小：宽,高",
    "Name_MapMeta": "地图名（显示在左上角和存档里）",

    # ---- 区域地图 ----
    "Filename": "区域地图图片文件名（Graphics/Pictures 下）",
    "Point": "地图上的一点：x,y,地点名,说明文字[,跳转地图,地图x,地图y]",

    # ---- 暗黑宝可梦 ----
    "GaugeSize": "暗黑计量槽大小（越大越难净化）",
    "Moves": "拥有的招式（逗号分隔）",

    # ---- 迷宫（v21）----
    "DungeonSize": "迷宫大小：宽,高（单位：房间数）",
    "CellSize": "单个房间的格子大小：宽,高",
    "MinRoomSize": "房间最小尺寸：宽,高",
    "MaxRoomSize": "房间最大尺寸：宽,高",
    "CorridorWidth": "走廊宽度（格）",
    "ShiftCorridors": "勾上 = 走廊会随机错位",
    "NodeLayout": "房间排布方式（full / ring / …）",
    "RoomLayout": "房间内部布局方式",
    "RoomChance": "随机生成房间的概率（0~100）",
    "ExtraConnections": "额外通道数量",
    "FloorPatches": "地面补丁：数量,概率,大小",
    "FloorDecorations": "地面装饰：概率,数量",
    "VoidDecorations": "空白处装饰：概率,数量",
    "RNGSeed": "随机种子（固定后每次生成结果一样）",
    "Autotile": "自动图块编号（一行一个，前缀 m 表示形状编号）",
    "Tile": "普通图块编号（一行一个）",
    "SnapToLargeGrid": "勾上 = 对齐到大格子",
    "LargeVoidTiles": "勾上 = 空白处也用大图块",
    "LargeWallTiles": "勾上 = 墙壁用大图块",
    "LargeFloorTiles": "勾上 = 地板用大图块",
    "DoubleWalls": "勾上 = 双层墙",
    "FloorPatchUnderWalls": "勾上 = 墙下也有地板补丁",
    "ThinNorthWallOffset": "北墙薄壁偏移量",

    # ---- 电话 ----
    "Intro": "来电开场白（可以写好几条，随机挑一条）",
    "IntroMorning": "早上的开场白",
    "IntroAfternoon": "下午的开场白",
    "IntroEvening": "晚上的开场白",
    "Body": "闲聊内容（好几条随机挑）",
    "Body1": "闲聊内容第一组",
    "Body2": "闲聊内容第二组",
    "BattleRequest": "约战台词",
    "BattleRemind": "提醒约战台词",
    "End": "挂断台词",

    # ---- 对战设施名单 ----
    "Trainers": "训练家数据文件名（PBS 目录下的 txt）",
    "Pokemon": "宝可梦数据文件名（PBS 目录下的 txt）",
    "Challenges": "可挑战的对战规则（逗号分隔）",
}

# 训练家队伍里每只宝可梦的子字段
FIELD_DESC_SUB = {
    "species": "宝可梦内部名或编号",
    "level": "等级",
    "Form": "形态编号（0 = 普通形态）",
    "Gender": "性别：male / female（不填 = 随机）",
    "Shiny": "勾上 = 这只一定是异色",
    "SuperShiny": "勾上 = 超闪光（方闪）",
    "Shadow": "勾上 = 暗黑宝可梦",
    "Ability": "用第几个特性（-1 = 随机，0/1/2 = 第 1/2/隐藏特性）",
    "AbilityIndex": "用第几个特性（-1 = 随机，0/1/2 = 第 1/2/隐藏特性）",
    "Nature": "性格（内部名，如 Adamant）",
    "IV": "个体值：HP,攻击,防御,特攻,特防,速度（31 满）",
    "EV": "努力值：HP,攻击,防御,特攻,特防,速度",
    "Happiness": "亲密度",
    "Ball": "装在什么球里（编号或内部名）",
    "Moves": "会的招式（逗号分隔，最多四个）",
}

# 对战设施的附属 txt 文件的中文名（这些文件本身没有对应的 PBS 主文件）
ATTACH_NAMES = {
    "battle_tower_trainers": "对战塔训练家",
    "battle_tower_pokemon": "对战塔宝可梦",
    "bttrainers": "对战塔训练家",
    "btpokemon": "对战塔宝可梦",
    "cup_poke_trainers": "宝可梦杯训练家",
    "cup_poke_pkmn": "宝可梦杯宝可梦",
    "cup_little_trainers": "小家伙杯训练家",
    "cup_little_pkmn": "小家伙杯宝可梦",
    "cup_fancy_trainers": "华丽杯训练家",
    "cup_fancy_pkmn": "华丽杯宝可梦",
    "cup_fancy_trainers_single": "华丽杯训练家（单打）",
    "cup_fancy_pkmn_single": "华丽杯宝可梦（单打）",
    "cup_pika_trainers": "皮卡丘杯训练家",
    "cup_pika_pkmn": "皮卡丘杯宝可梦",
}


# 同名但含义不同的字段，按文件覆盖
FIELD_DESC_BY_FILE = {
    ("map_metadata", "Name"): "地图名（显示在左上角、存档里）",
    ("wild_encounters", "Name"): "",
    ("metadata", "Name"): "",
    ("pokemon", "Name"): "物种名（游戏里显示的名字）",
    ("pokemon", "Category"): "图鉴分类（如「种子宝可梦」）",
    ("pokemon_forms", "Category"): "图鉴分类（如「种子宝可梦」）",
    ("pokemon_forms", "Kind"): "图鉴分类（如「种子宝可梦」）",
    ("pokemon_forms", "Name"): "物种名（和基础形态一致）",
    ("pokemon", "Type1"): "第一属性（v19 写法，只有一个属性时填同一属性）",
    ("pokemon", "Types"): "属性（最多两个；单属性也写在第一个）",
    ("pokemon", "BaseStats"): "种族值 6 项，顺序见右侧提示",
    ("items", "Type"): "道具大类编号（0 = 普通道具，非 0 表示招式机等特殊类）",
    ("phone", "Intro"): "打电话时的开场白（可多条，随机选一条）",
    ("berry_plants", "Yield"): "产量：最少,最多（单位：颗）",
    ("shadow_pokemon", "Moves"): "暗黑招式（暗黑宝可梦专用招式，逗号分隔）",
    ("trainers", "Name"): r"训练家名字（\\PN 会替换成玩家名）",
    ("town_map", "Point"): "地点：x,y,地点名,说明[,要去的地图,地图x,地图y]",
}


def field_desc(key: str) -> str:
    """字段的中文说明（没有就返回空）。"""
    if key in FIELD_DESC:
        return FIELD_DESC[key]
    k = re.sub(r"（.*?）$", "", key)      # 去掉「（未登记）」这类后缀
    return FIELD_DESC.get(k, "")


def attach_name(fname: str) -> str:
    """附带的 txt 文件 → 中文名（认不出就用文件名）。"""
    stem = fname[:-4] if fname.lower().endswith(".txt") else fname
    return ATTACH_NAMES.get(stem, stem)



def spec_for(key: str, family: str) -> Optional[dict]:
    """按 key + 版本族取文件描述（v16~v18 走 pbs_legacy）。"""
    if not key:
        return None
    if is_legacy(family):
        import pbs_legacy
        return pbs_legacy.spec_for(key, family)
    return file_for(key)


def is_legacy(family: str) -> bool:
    return family in ("v16", "v17", "v18")


# PBS编辑只开放这 4 类文件（宝可梦 / 宝可梦形态 / 道具 / 招式）。
# 其余类型（地图元数据、训练家、遭遇……）不再提供提取 / 编辑 / 编译入口。
EDITABLE_KEYS = ("pokemon", "pokemon_forms", "items", "moves")


def list_specs(family: str) -> List[dict]:
    """返回这个版本可编辑的 PBS 文件类型（只含 EDITABLE_KEYS）。"""
    if is_legacy(family):
        import pbs_legacy
        specs = pbs_legacy.specs(family)
    else:
        specs = [s for s in FILES if supports(s, family)]
    return [s for s in specs if s["key"] in EDITABLE_KEYS]


# ---------------------------------------------------------------------------
# .dat 读写
# ---------------------------------------------------------------------------

class DatInfo:
    """一个 .dat 文件的解析结果。"""

    def __init__(self, path: str):
        self.path = path
        self.raw = b""
        self.obj: Any = None
        self.dual = False          # v19：Symbol 键 + Integer 键并存
        self.has_id_number = False  # 对象里有没有 @id_number
        self.entries: List[Tuple[Any, Any]] = []   # [(键, 对象)] 去重保序

    @property
    def ok(self) -> bool:
        return self.obj is not None


def load_dat(path: str) -> Optional[DatInfo]:
    if not path or not os.path.isfile(path) or os.path.getsize(path) < 4:
        return None
    try:
        info = DatInfo(path)
        info.raw = open(path, "rb").read()
        info.obj = rmarshal.loads(info.raw)
    except Exception:
        return None
    if info.obj is None:
        return None
    seen = set()
    for k, v in _iter_objects(info.obj):
        if id(v) in seen:
            continue
        seen.add(id(v))
        info.entries.append((k, v))
        if isinstance(k, int):
            info.dual = True
    for _k, v in info.entries:
        iv = _obj_ivars(v)
        if "@id_number" in iv:
            info.has_id_number = True
            break
    return info


def _hget(h: Any, name: str, default: Any = None) -> Any:
    """取 RHash / dict 里 Symbol(name) 对应的值。"""
    if h is None:
        return default
    if isinstance(h, RHash):
        v = h.get(RSymbol(name), None)
        return default if v is None else v
    if isinstance(h, dict):
        for k, v in h.items():
            if _sym(k) == name:
                return v
        return default
    return default


def _as_list(v: Any) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def _int(v: Any, default: int = 0) -> int:
    try:
        if v is None or isinstance(v, bool):
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


# ---- 值 -> PBS 文本 -------------------------------------------------------

def _fmt_scalar(v: Any, c: str, enum: Optional[dict] = None) -> str:
    return fmt_value(v, c, enum)


def fmt_field(val: Any, ctype: str, family: str,
              enum: Optional[dict] = None) -> Optional[str]:
    """把一个 .dat 字段值格式化成 PBS 文本（不含 key）。None = 不写这一行。"""
    if val is None:
        return None
    # 官方行为：布尔 false 等价于「没填」，直接不写这一行
    if val is False:
        return None
    if isinstance(val, (list, tuple)) and len(val) == 0 and ctype[0] in "*^":
        return None
    multi = ctype[0] in "*^"
    base = ctype[1:] if multi else ctype
    # 身高 / 体重：.dat 里存「十分之一单位」的整数，官方写出去要 ÷10 并按
    # Ruby Float#to_s 格式（7 -> "0.7"，10 -> "1.0"）
    if base == "f" and not multi:
        try:
            return ruby_float(float(val) / 10.0)
        except (TypeError, ValueError):
            return fmt_value(val, "f", enum)
        return None
    # 六项能力值 / 努力值（.dat 里是 Hash{Symbol=>int}）
    if base in ("uuuuuu", "vvvvvv"):
        parts = []
        for st in stat_order(family):
            v = _hget(val, st)
            parts.append("0" if v is None else str(_int(v)))
        return ",".join(parts)
    # 升级招式 [[level, sym], ...]
    if base == "ue":
        parts = []
        for m in _as_list(val):
            if isinstance(m, (list, tuple)) and len(m) >= 2:
                parts.append(str(_int(m[0])))
                parts.append(_sym(m[1]))
        return ",".join(parts) if parts else None
    # 努力值 Hash -> "STAT,VAL"
    if base == "ev":
        parts = []
        for st in stat_order(family):
            v = _hget(val, st)
            if v:
                parts.append(st)
                parts.append(str(_int(v)))
        return ",".join(parts) if parts else None
    # 玩家角色（v19 的 PlayerA~H）：[训练家类型符号, 行走图, ...]
    if base == "player":
        if isinstance(val, (list, tuple)) and val:
            parts = [_sym(val[0])] + [str(x) for x in val[1:]]
            return ",".join(parts)
        return _sym(val) if val else None
    # 进化 [[species, method, param, is_prevo?], ...]
    if base in ("ses", "ees"):
        parts = []
        for evo in _as_list(val):
            if not isinstance(evo, (list, tuple)) or not evo:
                continue
            if len(evo) > 3 and evo[3]:      # 前置进化（反向条目）不写
                continue
            parts.append(_sym(evo[0]))
            parts.append(_sym(evo[1]) if len(evo) > 1 else "")
            p = evo[2] if len(evo) > 2 else None
            parts.append("" if p is None else _sym(p))
        return ",".join(parts) if parts else None
    # 定长数组（ii / uuu / vuuu / uv / vv / vvu / uu / us / mV …）
    if re.fullmatch(r"[a-zA-Z]{2,}", base) and base[0] not in ("s", "q", "n", "m"):
        if isinstance(val, (list, tuple)):
            parts = []
            for i, x in enumerate(val):
                parts.append(_fmt_scalar(
                    x, base[i] if i < len(base) else base[0], enum))
            return ",".join(parts)
    if multi:
        if isinstance(val, (list, tuple)):
            return ",".join(_fmt_scalar(x, base, enum) for x in val)
        return _fmt_scalar(val, base, enum)
    # 标量字段但数据里是数组（同人游戏常这么改）：逗号连接
    if isinstance(val, (list, tuple)):
        return ",".join(_fmt_scalar(x, base, enum) for x in val)
    return _fmt_scalar(val, base, enum)


# ---- 新建对象用的默认实例变量表 -------------------------------------------
# （Marshal.load 不调用 initialize，少一个 ivar 游戏就可能崩，所以新条目必须补全）

NEW_IVARS: Dict[Tuple[str, str], List[tuple]] = {
    ("GameData::Type", "v19"): [
        ("@id", None), ("@id_number", 0), ("@real_name", "Unnamed"),
        ("@pseudo_type", False), ("@special_type", False),
        ("@weaknesses", []), ("@resistances", []), ("@immunities", [])],
    ("GameData::Type", "v20"): [
        ("@id", None), ("@real_name", "Unnamed"), ("@special_type", False),
        ("@pseudo_type", False), ("@flags", []), ("@weaknesses", []),
        ("@resistances", []), ("@immunities", []), ("@icon_position", 0)],
    ("GameData::Type", "v21"): [
        ("@id", None), ("@real_name", "Unnamed"), ("@icon_position", 0),
        ("@special_type", False), ("@pseudo_type", False),
        ("@weaknesses", []), ("@resistances", []), ("@immunities", []),
        ("@flags", []), ("@pbs_file_suffix", "")],
    ("GameData::Ability", "v19"): [
        ("@id", None), ("@id_number", 0), ("@real_name", "Unnamed"),
        ("@real_description", "???")],
    ("GameData::Ability", "v20"): [
        ("@id", None), ("@real_name", "Unnamed"),
        ("@real_description", "???"), ("@flags", [])],
    ("GameData::Ability", "v21"): [
        ("@id", None), ("@real_name", "Unnamed"),
        ("@real_description", "???"), ("@flags", []),
        ("@pbs_file_suffix", "")],
    ("GameData::Move", "v19"): [
        ("@id", None), ("@id_number", 0), ("@real_name", "Unnamed"),
        ("@function_code", "None"), ("@base_damage", 0), ("@type", None),
        ("@category", 2), ("@accuracy", 100), ("@total_pp", 5),
        ("@effect_chance", 0), ("@target", None), ("@priority", 0),
        ("@flags", []), ("@real_description", "???")],
    ("GameData::Move", "v20"): [
        ("@id", None), ("@real_name", "Unnamed"), ("@type", None),
        ("@category", 2), ("@base_damage", 0), ("@accuracy", 100),
        ("@total_pp", 5), ("@target", None), ("@priority", 0),
        ("@function_code", "None"), ("@flags", []), ("@effect_chance", 0),
        ("@real_description", "???")],
    ("GameData::Move", "v21"): [
        ("@id", None), ("@real_name", "Unnamed"), ("@type", None),
        ("@category", 2), ("@power", 0), ("@accuracy", 100),
        ("@total_pp", 5), ("@target", None), ("@priority", 0),
        ("@function_code", "None"), ("@flags", []), ("@effect_chance", 0),
        ("@real_description", "???"), ("@pbs_file_suffix", "")],
    ("GameData::Item", "v19"): [
        ("@id", None), ("@id_number", 0), ("@real_name", "Unnamed"),
        ("@real_name_plural", "Unnamed"), ("@pocket", 1), ("@price", 0),
        ("@real_description", "???"), ("@field_use", 0), ("@battle_use", 0),
        ("@type", 0), ("@move", None), ("@flags", []),
        ("@consumable", True), ("@show_quantity", True)],
    ("GameData::Item", "v20"): [
        ("@id", None), ("@real_name", "Unnamed"),
        ("@real_name_plural", "Unnamed"), ("@pocket", 1), ("@price", 0),
        ("@sell_price", 0), ("@real_description", "???"),
        ("@field_use", 0), ("@battle_use", 0), ("@flags", []),
        ("@consumable", True), ("@move", None)],
    ("GameData::Item", "v21"): [
        ("@id", None), ("@real_name", "Unnamed"),
        ("@real_name_plural", "Unnamed"), ("@real_portion_name", None),
        ("@real_portion_name_plural", None), ("@pocket", 1), ("@price", 0),
        ("@sell_price", 0), ("@bp_price", 0), ("@field_use", 0),
        ("@battle_use", 0), ("@flags", []), ("@consumable", True),
        ("@show_quantity", None), ("@move", None),
        ("@real_description", "???"), ("@pbs_file_suffix", "")],
    ("GameData::BerryPlant", "v20"): [
        ("@id", None), ("@hours_per_stage", 3), ("@drying_per_hour", 15),
        ("@minimum_yield", 2), ("@maximum_yield", 5)],
    ("GameData::BerryPlant", "v21"): [
        ("@id", None), ("@hours_per_stage", 3), ("@drying_per_hour", 15),
        ("@minimum_yield", 2), ("@maximum_yield", 5),
        ("@pbs_file_suffix", "")],
    ("GameData::Ribbon", "v19"): [
        ("@id", None), ("@id_number", 0), ("@real_name", "Unnamed"),
        ("@real_description", "???")],
    ("GameData::Ribbon", "v20"): [
        ("@id", None), ("@real_name", "Unnamed"), ("@icon_position", 0),
        ("@real_description", "???"), ("@flags", [])],
    ("GameData::Ribbon", "v21"): [
        ("@id", None), ("@real_name", "Unnamed"), ("@icon_position", 0),
        ("@real_description", "???"), ("@flags", []),
        ("@pbs_file_suffix", "")],
    ("GameData::TrainerType", "v19"): [
        ("@id", None), ("@id_number", 0), ("@real_name", "Unnamed"),
        ("@base_money", 30), ("@battle_BGM", None), ("@victory_ME", None),
        ("@intro_ME", None), ("@gender", 2), ("@skill_level", 0),
        ("@skill_code", None)],
    ("GameData::TrainerType", "v20"): [
        ("@id", None), ("@real_name", "Unnamed"), ("@base_money", 30),
        ("@skill_level", 0), ("@flags", []), ("@intro_BGM", None),
        ("@battle_BGM", None), ("@victory_BGM", None)],
    ("GameData::TrainerType", "v21"): [
        ("@id", None), ("@real_name", "Unnamed"), ("@base_money", 30),
        ("@skill_level", 0), ("@flags", []), ("@intro_BGM", None),
        ("@battle_BGM", None), ("@victory_BGM", None),
        ("@pbs_file_suffix", "")],
    ("GameData::Species", "v19"): [
        ("@id", None), ("@id_number", 0), ("@species", None), ("@form", 0),
        ("@real_name", "Unnamed"), ("@real_form_name", None),
        ("@real_category", "???"), ("@real_pokedex_entry", "???"),
        ("@pokedex_form", 0), ("@type1", None), ("@type2", None),
        ("@base_stats", RHash([(RSymbol(k), 1) for k in STAT_ORDER_V19])),
        ("@evs", RHash([(RSymbol(k), 0) for k in STAT_ORDER_V19])),
        ("@base_exp", 100), ("@growth_rate", RSymbol("Medium")),
        ("@gender_ratio", RSymbol("Female50Percent")), ("@catch_rate", 255),
        ("@happiness", 70), ("@moves", []), ("@tutor_moves", []),
        ("@egg_moves", []), ("@abilities", []), ("@hidden_abilities", []),
        ("@wild_item_common", None), ("@wild_item_uncommon", None),
        ("@wild_item_rare", None), ("@egg_groups", [RSymbol("Undiscovered")]),
        ("@hatch_steps", 1), ("@incense", None), ("@offspring", []),
        ("@evolutions", []), ("@height", 1), ("@weight", 1),
        ("@color", RSymbol("Red")), ("@shape", RSymbol("Head")),
        ("@habitat", RSymbol("None")), ("@generation", 0),
        ("@back_sprite_x", 0), ("@back_sprite_y", 0),
        ("@front_sprite_x", 0), ("@front_sprite_y", 0),
        ("@front_sprite_altitude", 0), ("@shadow_x", 0), ("@shadow_size", 2),
        ("@pbs_file_suffix", "")],
    ("GameData::Species", "v20"): [
        ("@id", None), ("@species", None), ("@form", 0),
        ("@real_name", "Unnamed"), ("@real_form_name", None),
        ("@real_category", "???"), ("@real_pokedex_entry", "???"),
        ("@pokedex_form", 0), ("@types", [RSymbol("NORMAL")]),
        ("@base_stats", RHash([(RSymbol(k), 1) for k in STAT_ORDER_NEW])),
        ("@evs", RHash([(RSymbol(k), 0) for k in STAT_ORDER_NEW])),
        ("@base_exp", 100), ("@growth_rate", RSymbol("Medium")),
        ("@gender_ratio", RSymbol("Female50Percent")), ("@catch_rate", 255),
        ("@happiness", 70), ("@moves", []), ("@tutor_moves", []),
        ("@egg_moves", []), ("@abilities", []), ("@hidden_abilities", []),
        ("@wild_item_common", []), ("@wild_item_uncommon", []),
        ("@wild_item_rare", []), ("@egg_groups", [RSymbol("Undiscovered")]),
        ("@hatch_steps", 1), ("@incense", None), ("@offspring", []),
        ("@evolutions", []), ("@height", 1), ("@weight", 1),
        ("@color", RSymbol("Red")), ("@shape", RSymbol("Head")),
        ("@habitat", RSymbol("None")), ("@generation", 0), ("@flags", []),
        ("@back_sprite_x", 0), ("@back_sprite_y", 0),
        ("@front_sprite_x", 0), ("@front_sprite_y", 0),
        ("@front_sprite_altitude", 0), ("@shadow_x", 0), ("@shadow_size", 2),
        ("@pbs_file_suffix", "")],
    ("GameData::Species", "v21"): [
        ("@id", None), ("@species", None), ("@form", 0),
        ("@real_name", "Unnamed"), ("@real_form_name", None),
        ("@real_category", "???"), ("@real_pokedex_entry", "???"),
        ("@pokedex_form", 0), ("@types", [RSymbol("NORMAL")]),
        ("@base_stats", RHash([(RSymbol(k), 1) for k in STAT_ORDER_NEW])),
        ("@evs", RHash([(RSymbol(k), 0) for k in STAT_ORDER_NEW])),
        ("@base_exp", 100), ("@growth_rate", RSymbol("Medium")),
        ("@gender_ratio", RSymbol("Female50Percent")), ("@catch_rate", 255),
        ("@happiness", 70), ("@moves", []), ("@tutor_moves", []),
        ("@egg_moves", []), ("@abilities", []), ("@hidden_abilities", []),
        ("@wild_item_common", []), ("@wild_item_uncommon", []),
        ("@wild_item_rare", []), ("@egg_groups", [RSymbol("Undiscovered")]),
        ("@hatch_steps", 1), ("@incense", None), ("@offspring", []),
        ("@evolutions", []), ("@height", 1), ("@weight", 1),
        ("@color", RSymbol("Red")), ("@shape", RSymbol("Head")),
        ("@habitat", RSymbol("None")), ("@generation", 0), ("@flags", []),
        ("@mega_stone", None), ("@mega_move", None),
        ("@unmega_form", 0), ("@mega_message", 0),
        ("@pbs_file_suffix", "")],
    ("GameData::SpeciesMetrics", "v20"): [
        ("@id", None), ("@species", None), ("@form", 0),
        ("@back_sprite", [0, 0]), ("@front_sprite", [0, 0]),
        ("@front_sprite_altitude", 0), ("@shadow_x", 0),
        ("@shadow_size", 2), ("@pbs_file_suffix", "")],
    ("GameData::SpeciesMetrics", "v21"): [
        ("@id", None), ("@species", None), ("@form", 0),
        ("@back_sprite", [0, 0]), ("@front_sprite", [0, 0]),
        ("@front_sprite_altitude", 0), ("@shadow_x", 0),
        ("@shadow_size", 2), ("@pbs_file_suffix", "")],
    ("GameData::ShadowPokemon", "v20"): [
        ("@id", None), ("@gauge_size", 5), ("@moves", []), ("@flags", [])],
    ("GameData::ShadowPokemon", "v21"): [
        ("@id", None), ("@gauge_size", 5), ("@flags", []),
        ("@pbs_file_suffix", "")],
}


def _new_object(cls: str, family: str, ivars: Dict[str, Any],
                has_id_number: bool) -> RObject:
    """按默认表造一个新对象，再用 ivars 覆盖。"""
    obj = RObject(cls)
    attrs: Dict[str, Any] = {}
    for name, default in NEW_IVARS.get((cls, family), []):
        if name == "@id_number" and not has_id_number:
            continue
        attrs[name] = ivars[name] if name in ivars else default
    # 默认表里没有的（用户数据里多出来的）也带上
    for k, v in ivars.items():
        attrs.setdefault(k, v)
    if "@id" in ivars:
        attrs["@id"] = ivars["@id"]
    obj.ivars = attrs
    return obj


# ---------------------------------------------------------------------------
# 段式文本（[段] + Key = Value）解析
# ---------------------------------------------------------------------------

_SEC_RE = re.compile(r"^\s*\[\s*(.*?)\s*\]\s*(?:#.*)?$")
_KV_RE = re.compile(r"^\s*(\w+)\s*=\s*(.*?)\s*$")


class ParsedSection:
    __slots__ = ("name", "comment", "fields")

    def __init__(self, name: str, comment: str = ""):
        self.name = name            # 段名（[ ] 里的原文）
        self.comment = comment      # 段名后面 # 的注释
        self.fields: List[Tuple[str, str]] = []   # [(key, 原始文本)]


def parse_sections(text: str) -> List[ParsedSection]:
    """解析段式 PBS 文本（容忍 BOM / 注释 / 空行 / 段尾注释）。"""
    if text.startswith("﻿"):
        text = text[1:]
    sections: List[ParsedSection] = []
    cur: Optional[ParsedSection] = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _SEC_RE.match(line)
        if m:
            inside = m.group(1)
            comment = ""
            if "#" in inside:
                inside, comment = inside.split("#", 1)
                inside = inside.strip()
                comment = comment.strip()
            cur = ParsedSection(inside, comment)
            sections.append(cur)
            continue
        m = _KV_RE.match(line)
        if m and cur is not None:
            cur.fields.append((m.group(1), m.group(2)))
    return sections


def section_field(sec: ParsedSection, key: str) -> Optional[str]:
    for k, v in sec.fields:
        if k == key:
            return v
    return None


# ---------------------------------------------------------------------------
# 提取：.dat -> PBS 文本
# ---------------------------------------------------------------------------

def _bom_text(lines: List[str]) -> str:
    return "﻿" + CRLF.join(lines) + CRLF


def _file_header(spec: dict) -> List[str]:
    return [_HEADER]


def extract_gamedata(spec: dict, family: str, info: DatInfo,
                     only_forms: bool = False,
                     game_root: str = "") -> str:
    """段式 GameData 文件提取（types / abilities(v20+) / moves(v20+) …）。"""
    schema = schema_of(spec, family)
    lines = _file_header(spec)
    keymode = spec.get("keymode", "symbol")
    # 形态文件要跟基础形态对比，只写差异
    base_by_species: Dict[str, Any] = {}
    if only_forms:
        for _k, v in info.entries:
            iv = _obj_ivars(v)
            if _int(iv.get("@form", 0)) == 0:
                base_by_species[_sym(iv.get("@species") or iv.get("@id"))] = iv
    for _k, v in info.entries:
        iv = _obj_ivars(v)
        if only_forms and _int(iv.get("@form", 0)) == 0:
            continue
        if not only_forms and keymode != "idnum" \
                and _int(iv.get("@form", 0)) != 0 and spec["key"] == "pokemon":
            continue    # 形态在 pokemon_forms.txt 里
        # 段名
        if only_forms:
            sec_name = "%s,%d" % (_sym(iv.get("@species") or iv.get("@id")),
                                  _int(iv.get("@form", 0)))
        elif keymode == "idnum":
            sec_name = "%03d" % _int(iv.get("@id", 0))
        elif family == "v19":
            sec_name = str(_int(iv.get("@id_number", 0)))
        else:
            sec_name = _sym(iv.get("@id"))
        lines.append(_SEP)
        lines.append("[%s]" % sec_name)
        base_iv = base_by_species.get(
            _sym(iv.get("@species") or iv.get("@id"))) if only_forms else None
        for key, ivar, ctype, enum in schema:
            val = iv.get("@" + ivar)
            if ctype[0] == "^":     # 多行键：一行一个元素
                if val is None:
                    continue
                for sub in _as_list(val):
                    txt = fmt_field(sub, ctype[1:], family, enum)
                    if txt is not None:
                        lines.append("%s = %s" % (key, txt))
                continue
            key = _pbs_key_label(spec, key, family, game_root)
            # ★ 官方 Item 的 Consumable 只写 false（get_property_for_PBS 里
            #   直接返回 @consumable），而 fmt_field 默认把 false 当「没填」
            if key == "Consumable" and val is False:
                txt = "false"
            else:
                txt = fmt_field(val, ctype, family, enum)
            base_txt = None
            if base_iv is not None:
                base_txt = fmt_field(base_iv.get("@" + ivar), ctype, family,
                                     enum)
                if key == "Consumable" and base_iv.get("@" + ivar) is False:
                    base_txt = "false"
            if _off_skip(spec["key"], family, key, iv, val, base_iv):
                continue
            if txt is None:
                continue
            if only_forms and family == "v19" and key in ("Type1", "Type2"):
                # 官方 v19：Type1/Type2 只要有一个和基础形态不同就写 Type1；
                # Type2 只在它和 Type1 不同时才写（不跟基础形态比）
                t1 = fmt_field(iv.get("@type1"), "e", family)
                t2 = fmt_field(iv.get("@type2"), "e", family)
                b1 = fmt_field(base_iv.get("@type1"), "e", family)
                b2 = fmt_field(base_iv.get("@type2"), "e", family)
                if t1 == b1 and t2 == b2:
                    continue
                if key == "Type2" and t2 == t1:
                    continue
            elif base_iv is not None and key not in WILD_ITEM_KEYS \
                    and base_txt == txt:
                continue    # 与基础形态一致：官方不写这一行
            lines.append("%s = %s" % (key, txt))
    return _bom_text(lines)


# 官方 form 写出时「野生道具」三个键的特殊处理（整组一样才全部省略）
WILD_ITEM_KEYS = ("WildItemCommon", "WildItemUncommon", "WildItemRare")
_WILD_IVAR = {"WildItemCommon": "wild_item_common",
              "WildItemUncommon": "wild_item_uncommon",
              "WildItemRare": "wild_item_rare"}


def _item_important(iv: dict) -> bool:
    """官方 Item#is_important? —— 重要道具：KeyItem 旗标 / HM / TM。"""
    flags = [str(_sym(x)).lower() for x in _as_list(iv.get("@flags"))]
    if "keyitem" in flags:
        return True
    return _int(iv.get("@field_use", 0)) in (3, 4)


def _wild_trio_differs(iv: dict, base_iv: dict) -> bool:
    for key in WILD_ITEM_KEYS:
        a = fmt_field(base_iv.get("@" + _WILD_IVAR[key]), "*e", "v21")
        b = fmt_field(iv.get("@" + _WILD_IVAR[key]), "*e", "v21")
        if a != b:
            return True
    return False


def sub_version(game_root: str) -> str:
    """游戏实际的 Essentials 版本号（读不到返回 ""）。"""
    if not game_root:
        return ""
    try:
        import essentials_base as EB
        return (EB.detect_version(game_root) or "").strip()
    except Exception:
        return ""


def _pbs_key_label(spec: dict, key: str, family: str, game_root: str) -> str:
    """
    字段名在.小版本之间改过名的情况。

    ★ 官方 v20.1 的 write_moves 把 ``BaseDamage`` 改成了 ``Power``（同一个
      @base_damage 字段，只改标签）。
    """
    if spec.get("key") == "moves" and key == "BaseDamage" and family == "v20":
        m = re.match(r"20\.(\d+)", sub_version(game_root))
        if m and int(m.group(1)) >= 1:
            return "Power"
    return key


def _off_skip(fkey: str, family: str, pbs_key: str, iv: dict, val: Any,
              base_iv: Optional[dict] = None) -> bool:
    """官方 write_* / get_property_for_PBS 里「这一行不写」的判断。"""
    if val is None:
        return True
    if isinstance(val, (list, tuple)) and not val:
        return True
    # ---- 通用 ----
    if pbs_key == "FormName":
        return not str(val).strip()
    if pbs_key == "Habitat":
        return _sym(val) == "None"
    if pbs_key == "Generation":
        return _int(val) == 0
    # ---- 宝可梦 / 形态 ----
    if fkey in ("pokemon", "pokemon_forms"):
        if pbs_key == "Type2":
            return _sym(val) == _sym(iv.get("@type1"))
        if pbs_key == "BattlerAltitude":
            return _int(val) == 0
        if pbs_key == "PokedexForm":
            return _int(val) == _int(iv.get("@form", 0))
        if pbs_key in ("UnmegaForm", "MegaMessage"):
            return _int(val) == 0
        if pbs_key in WILD_ITEM_KEYS:
            if not _as_list(val):
                return True
            if base_iv is not None and not _wild_trio_differs(iv, base_iv):
                return True
    # ---- 道具 ----
    if fkey == "items":
        if pbs_key == "SellPrice":
            return _int(val) == _int(iv.get("@price", 0)) // 2
        if pbs_key == "BPPrice":
            return _int(val) == 1
        if pbs_key in ("FieldUse", "BattleUse"):
            return _int(val) == 0
        if pbs_key == "Consumable":
            # 官方只写 false，而且重要道具一律不写
            return bool(val) or _item_important(iv)
        if pbs_key == "ShowQuantity":
            return val is not True
    # ---- 招式 ----
    if fkey == "moves":
        # v21 写成 Power，v20 写成 BaseDamage，v20.1 起也改成 Power
        zeros = ("BaseDamage", "Power", "Priority", "EffectChance")
        if pbs_key in zeros and _int(val) == 0:
            return True
    return False



def _same(a: Any, b: Any) -> bool:
    """比较两个字段值是否等价（Symbol/数组/Hash）。"""
    if isinstance(a, RSymbol) or isinstance(b, RSymbol):
        return _sym(a) == _sym(b) and type(a) == type(b)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, RHash) and isinstance(b, RHash):
        return a.items() == b.items()
    return a == b


def extract_line(spec: dict, family: str, info: DatInfo) -> str:
    """v19 行式文件（abilities / moves / items / ribbons / trainertypes）。

    ★ 官方 v19 的 write_moves / write_items 会在**类型/口袋变化**处插一条
      ``#-------------------------------`` 分隔线（用户读起来成组），这里照做。
    """
    schema = schema_of(spec, family)
    lines = _file_header(spec)
    sep_on = (spec.get("sep_on") or {}).get(family)
    cur = object()
    for _k, v in info.entries:
        iv = _obj_ivars(v)
        if sep_on:
            now = iv.get("@" + sep_on)
            if not _same(now, cur):
                cur = now
                lines.append(_SEP)
        parts = []
        for key, ivar, ctype, enum in schema:
            val = iv.get("@" + ivar)
            if ctype == "q":
                parts.append(csv_quote("" if val is None else str(val),
                                       always=True))
            elif ctype == "n":
                parts.append(_sym(val))
            elif val is None:
                parts.append("")
            else:
                txt = fmt_field(val, ctype, family, enum)
                parts.append("" if txt is None else txt)
        lines.append(",".join(parts))
    return _bom_text(lines)


def extract_kv(spec: dict, family: str, info: DatInfo) -> str:
    """v19 的 berryplants / shadowmoves：``KEY = v1,v2,…``。"""
    order = spec.get("v19kv") or []
    lines = _file_header(spec)
    for _k, v in info.entries:
        iv = _obj_ivars(v)
        key = _sym(iv.get("@id"))
        parts = []
        for ivar in order:
            val = iv.get("@" + ivar)
            if isinstance(val, (list, tuple)):
                parts.extend(_sym(x) for x in val)
            elif val is None:
                parts.append("")
            else:
                parts.append(str(val))
        lines.append("%s = %s" % (key, ",".join(parts)))
    return _bom_text(lines)


# ---- 定制格式的提取 --------------------------------------------------------

def extract_encounters(spec: dict, family: str, info: DatInfo) -> str:
    lines = _file_header(spec)
    for _k, v in info.entries:
        iv = _obj_ivars(v)
        m = _int(iv.get("@map", 0))
        ver = _int(iv.get("@version", 0))
        head = "[%03d]" % m if ver <= 0 else "[%03d,%d]" % (m, ver)
        lines.append(_SEP)
        lines.append(head)
        types = iv.get("@types")
        chances = iv.get("@step_chances")
        pairs = types.items() if isinstance(types, RHash) else []
        for t, slots in pairs:
            slots = _as_list(slots)
            if not slots:
                continue
            chance = _hget(chances, _sym(t), 0) if chances else 0
            if chance:
                lines.append("%s,%d" % (_sym(t), _int(chance)))
            else:
                lines.append(_sym(t))
            for slot in slots:
                if not isinstance(slot, (list, tuple)) or len(slot) < 3:
                    continue
                lo, sp, mn = _int(slot[0]), _sym(slot[1]), _int(slot[2])
                mx = _int(slot[3]) if len(slot) > 3 else mn
                if mn == mx:
                    lines.append("    %d,%s,%d" % (lo, sp, mn))
                else:
                    lines.append("    %d,%s,%d,%d" % (lo, sp, mn, mx))
    return _bom_text(lines)


def extract_town_map(spec: dict, family: str, infos: List[DatInfo]) -> str:
    """v19：town_map.dat 是数组；v20+：GameData::TownMap。"""
    lines = _file_header(spec)
    if family == "v19":
        data = infos[0].obj if infos and infos[0].obj else []
        for i, sec in enumerate(_as_list(data)):
            lines.append(_SEP)
            lines.append("[%d]" % i)
            if not isinstance(sec, (list, tuple)):
                continue
            name = sec[0] if len(sec) > 0 else None
            fname = sec[1] if len(sec) > 1 else None
            if name:
                lines.append("Name = %s" % csv_quote(str(name)))
            if fname:
                lines.append("Filename = %s" % csv_quote(str(fname)))
            for pt in (_as_list(sec[2]) if len(sec) > 2 else []):
                if isinstance(pt, (list, tuple)) and len(pt) >= 3:
                    lines.append("Point = %s" % ",".join(
                        "" if x is None
                        else (csv_quote(x) if isinstance(x, str) else str(x))
                        for x in pt))
        return _bom_text(lines)
    for info in infos:
        if not info or not info.ok:
            continue
        for _k, v in info.entries:
            iv = _obj_ivars(v)
            lines.append(_SEP)
            lines.append("[%d]" % _int(iv.get("@id", 0)))
            if iv.get("@real_name"):
                lines.append("Name = %s" % csv_quote(str(iv["@real_name"])))
            if iv.get("@filename"):
                lines.append("Filename = %s" % csv_quote(str(iv["@filename"])))
            for pt in _as_list(iv.get("@point")):
                if isinstance(pt, (list, tuple)) and len(pt) >= 3:
                    lines.append("Point = %s" % ",".join(
                        "" if x is None
                        else (csv_quote(x) if isinstance(x, str) else str(x))
                        for x in pt))
    return _bom_text(lines)


def extract_connections(spec: dict, family: str, info: DatInfo) -> str:
    lines = _file_header(spec)
    for rec in _as_list(info.obj):
        if isinstance(rec, (list, tuple)) and len(rec) >= 6:
            lines.append(_SEP)
            lines.append(",".join(str(x) for x in rec[:6]))
    return _bom_text(lines)


def extract_regional(spec: dict, family: str, info: DatInfo) -> str:
    lines = _file_header(spec)
    for i, lst in enumerate(_as_list(info.obj)):
        lines.append(_SEP)
        lines.append("[%d]" % i)
        names = [_sym(x) for x in _as_list(lst)]
        # 官方按家庭断行，这里简单处理：每行若干只
        for j in range(0, len(names), 12):
            lines.append(",".join(names[j:j + 12]))
    return _bom_text(lines)


def extract_phone(spec: dict, family: str, info: DatInfo) -> str:
    lines = _file_header(spec)
    if family == "v19":
        iv = _obj_ivars(info.entries[0][1]) if info.entries else {}
        groups = [("@generics", "Generics"), ("@battleRequests", "BattleRequests"),
                  ("@greetingsMorning", "GreetingsMorning"),
                  ("@greetingsEvening", "GreetingsEvening"),
                  ("@greetings", "Greetings"), ("@bodies1", "Bodies1"),
                  ("@bodies2", "Bodies2")]
        for ivar, label in groups:
            msgs = _as_list(iv.get(ivar))
            if not msgs:
                continue
            lines.append(_SEP)
            lines.append("[<%s>]" % label)
            for m in msgs:
                lines.append(str(m))
        return _bom_text(lines)
    # v20/v21：GameData::PhoneMessage
    multi = ["Intro", "IntroMorning", "IntroAfternoon", "IntroEvening",
             "Body", "Body1", "Body2", "BattleRequest", "BattleRemind", "End"]
    ivar_of = {"Intro": "intro", "IntroMorning": "intro_morning",
               "IntroAfternoon": "intro_afternoon",
               "IntroEvening": "intro_evening", "Body": "body",
               "Body1": "body1", "Body2": "body2",
               "BattleRequest": "battle_request", "BattleRemind": "battle_remind",
               "End": "end"}
    for _k, v in info.entries:
        iv = _obj_ivars(v)
        lines.append(_SEP)
        name = iv.get("@id")
        if isinstance(name, RSymbol):
            lines.append("[%s]" % name.name)
        else:
            lines.append("[%s]" % name)
        for key in multi:
            for m in _as_list(iv.get("@" + ivar_of[key])):
                lines.append("%s = %s" % (key, str(m)))
    return _bom_text(lines)


def extract_facility(spec: dict, family: str, infos: List[DatInfo]) -> str:
    """battle_facility_lists / trainerlists + 关联的 battle tower 文件。"""
    lines = _file_header(spec)
    for info in infos:
        if not info or not info.ok:
            continue
        for rec in _as_list(info.obj):
            if not isinstance(rec, (list, tuple)) or len(rec) < 5:
                continue
            trainers_file = rec[3] if len(rec) > 3 else None
            pokemon_file = rec[4] if len(rec) > 4 else None
            is_default = bool(rec[5]) if len(rec) > 5 else False
            lines.append(_SEP)
            lines.append("[%s]" % ("DefaultTrainerList" if is_default
                                   else "TrainerList"))
            if trainers_file:
                lines.append("Trainers = %s" % trainers_file)
            if pokemon_file:
                lines.append("Pokemon = %s" % pokemon_file)
            challenges = _as_list(rec[2]) if len(rec) > 2 else []
            if challenges and not is_default:
                lines.append("Challenges = %s" % ",".join(
                    str(c) for c in challenges))
    return _bom_text(lines)


# ---- 提取入口 --------------------------------------------------------------

def extract_spec(spec: dict, family: str, game_root: str
                 ) -> Tuple[bool, str, str]:
    """提取一个文件类型。返回 (ok, 文本或错误信息, 统计)。"""
    editor = spec.get("editor")
    dat_names = spec["dat"]
    infos = [load_dat(os.path.join(game_root, "Data", n)) for n in dat_names]
    if editor in ("townmap", "facility"):
        infos = [i for i in infos if i and i.ok]
        if not infos:
            return False, "找不到 %s" % " / ".join(dat_names), ""
    else:
        infos = [i for i in infos if i and i.ok]
        if not infos:
            return False, "找不到 %s" % " / ".join(dat_names), ""
        info = infos[0]
    try:
        if editor == "encounters":
            text = extract_encounters(spec, family, info)
            n = len(info.entries)
        elif editor == "townmap":
            text = extract_town_map(spec, family, infos)
            n = sum(len(i.entries) for i in infos)
        elif editor == "connections":
            text = extract_connections(spec, family, info)
            n = len(_as_list(info.obj))
        elif editor == "regional":
            text = extract_regional(spec, family, info)
            n = len(_as_list(info.obj))
        elif editor == "phone":
            text = extract_phone(spec, family, info)
            n = len(info.entries) if family != "v19" else 1
        elif editor == "facility":
            text = extract_facility(spec, family, infos)
            n = sum(len(_as_list(i.obj)) for i in infos)
        elif editor == "metadata":
            text, n = _extract_metadata(spec, family, infos)
        elif editor == "trainers":
            text, n = _extract_trainers(spec, family, info)
        else:
            style = style_of(spec, family)
            only_forms = spec["key"] == "pokemon_forms"
            if style == "line":
                text = extract_line(spec, family, info)
            elif style == "kv":
                text = extract_kv(spec, family, info)
            else:
                text = extract_gamedata(spec, family, info,
                                        only_forms=only_forms,
                                        game_root=game_root)
            n = len(info.entries)
            if only_forms:
                n = sum(1 for _k, v in info.entries
                        if _int(_obj_ivars(v).get("@form", 0)) != 0)
            if spec["key"] == "pokemon":
                n = sum(1 for _k, v in info.entries
                        if _int(_obj_ivars(v).get("@form", 0)) == 0)
    except Exception as e:
        return False, "解析 %s 失败：%s" % (dat_names[0], e), ""
    return True, text, "%d 条" % n


def _extract_metadata(spec: dict, family: str,
                      infos: List[DatInfo]) -> Tuple[str, int]:
    """metadata.txt：v19 = 全局 + 地图元数据；v20+ = 全局 + 玩家角色。"""
    lines = _file_header(spec)
    n = 0
    if family == "v19":
        schema = schema_of(spec, "v19")
        map_schema = spec.get("v19map_schema") or []
        info = infos[0]
        for _k, v in info.entries:
            iv = _obj_ivars(v)
            mid = _int(iv.get("@id", 0))
            lines.append(_SEP)
            lines.append("[%03d]" % mid)
            use = schema if mid == 0 else map_schema
            for key, ivar, ctype, enum in use:
                val = iv.get("@" + ivar)
                if val is None:
                    continue
                if isinstance(val, (list, tuple)) and not val and ctype[0] in "*^":
                    continue
                txt = fmt_field(val, ctype, family, enum)
                if txt is None:
                    continue
                lines.append("%s = %s" % (key, txt))
            n += 1
        return _bom_text(lines), n
    # v20/v21：metadata.dat（段 0）+ player_metadata.dat（段 1+）
    gschema = schema_of(spec, family)
    pschema = spec.get("player_schema", {}).get(family) or []
    if infos and infos[0]:
        for _k, v in infos[0].entries:
            iv = _obj_ivars(v)
            lines.append(_SEP)
            lines.append("[%d]" % _int(iv.get("@id", 0)))
            for key, ivar, ctype, enum in gschema:
                val = iv.get("@" + ivar)
                if val is None:
                    continue
                if isinstance(val, (list, tuple)) and not val and ctype[0] in "*^":
                    continue
                txt = fmt_field(val, ctype, family, enum)
                if txt is None:
                    continue
                lines.append("%s = %s" % (key, txt))
            n += 1
    if len(infos) > 1 and infos[1]:
        for _k, v in infos[1].entries:
            iv = _obj_ivars(v)
            lines.append(_SEP)
            lines.append("[%d]" % _int(iv.get("@id", 0)))
            for key, ivar, ctype, enum in pschema:
                val = iv.get("@" + ivar)
                if val is None:
                    continue
                if isinstance(val, (list, tuple)) and not val and ctype[0] in "*^":
                    continue
                txt = fmt_field(val, ctype, family, enum)
                if txt is None:
                    continue
                lines.append("%s = %s" % (key, txt))
            n += 1
    return _bom_text(lines), n


def _extract_trainers(spec: dict, family: str, info: DatInfo) -> Tuple[str, int]:
    lines = _file_header(spec)
    schema = schema_of(spec, family)
    sub_schema = spec.get("sub_schema", {}).get(family) or []
    n = 0
    for _k, v in info.entries:
        iv = _obj_ivars(v)
        ttype = _sym(iv.get("@trainer_type"))
        name = iv.get("@real_name")
        name = str(name) if name is not None else ""
        ver = _int(iv.get("@version", 0))
        lines.append(_SEP)
        if ver > 0:
            lines.append("[%s,%s,%d]" % (ttype, name, ver))
        else:
            lines.append("[%s,%s]" % (ttype, name))
        for key, ivar, ctype, enum in schema:
            val = iv.get("@" + ivar)
            if val is None:
                continue
            if isinstance(val, (list, tuple)) and not val and ctype[0] in "*^":
                continue
            txt = fmt_field(val, ctype, family, enum)
            if txt is None:
                continue
            lines.append("%s = %s" % (key, txt))
        for pkmn in _as_list(iv.get("@pokemon")):
            if isinstance(pkmn, RHash):
                pv = {_sym(k): v2 for k, v2 in pkmn.items()}
            elif isinstance(pkmn, dict):
                pv = {_sym(k): v2 for k, v2 in pkmn.items()}
            else:
                continue
            lines.append("Pokemon = %s,%d" % (_sym(pv.get("species")),
                                              _int(pv.get("level", 1))))
            for key, ivar, ctype, enum in sub_schema:
                val = pv.get(ivar)
                if val is None:
                    continue
                if isinstance(val, (list, tuple)) and not val and ctype[0] in "*^":
                    continue
                if ctype == "b":
                    if not val:
                        continue
                    lines.append("    %s = yes" % key)
                    continue
                if ctype == "s" and ivar == "gender":
                    lines.append("    Gender = %s" % (
                        "female" if _int(val) == 1 else "male"))
                    continue
                txt = fmt_field(val, ctype, family, enum)
                if txt is None:
                    continue
                lines.append("    %s = %s" % (key, txt))
        n += 1
    return _bom_text(lines), n


def extract_all(game_root: str, family: str, keys: Optional[List[str]] = None,
                emit=None) -> List[dict]:
    """提取全部（或指定）文件到 PBS 目录。返回结果列表。"""
    if is_legacy(family):
        import pbs_legacy
        return pbs_legacy.extract_all(game_root, family, keys, emit)
    out_dir = pbs_dir(game_root)
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for spec in list_specs(family):
        if keys and spec["key"] not in keys:
            continue
        ok, text, stat = extract_spec(spec, family, game_root)
        rec = {"key": spec["key"], "name": spec["name"],
               "file": txt_name(spec, family), "ok": ok, "stat": stat}
        if ok:
            path = os.path.join(out_dir, txt_name(spec, family))
            try:
                with open(path, "wb") as f:
                    f.write(text.encode("utf-8"))
                rec["path"] = path
            except OSError as e:
                rec["ok"] = False
                rec["stat"] = "写入失败：%s" % e
        else:
            rec["stat"] = text
        # 对战设施：连带提取引用的 battle tower / cups 文件
        if ok and spec.get("editor") == "facility":
            try:
                extra = extract_facility_files(spec, family, game_root,
                                               out_dir)
                if extra:
                    rec["stat"] = (rec.get("stat") or "") + \
                        "（含 %d 个关联文件）" % len(extra)
            except Exception:
                pass
        results.append(rec)
        if emit:
            emit(rec)
    return results


# ---------------------------------------------------------------------------
# 编译：PBS 文本 -> .dat
# ---------------------------------------------------------------------------

def _unquote_csv(s: str) -> str:
    """去掉 CSV 值外层引号（split_csv_line 的行为）。"""
    s = s.strip()
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        inner = s[1:-1]
        if inner.endswith('\\"') and not inner.endswith('\\\\"'):
            inner = inner[:-2] + '"'
        return inner.replace('\\"', '"')
    return s


def _parse_field_text(text: str, ctype: str, family: str,
                      enum: Optional[dict] = None,
                      unquote: bool = True) -> Any:
    """把一个字段的原始文本按类型码解析成 .dat 里的值。

    unquote=False 用于段式格式的 "q"（未格式化文本）—— 官方读取时取整行
    剩余部分，不做去引号。
    """
    if text is None:
        return None
    t = text.strip()
    if t == "":
        return None
    multi = ctype[0] in "*^"
    base = ctype[1:] if multi else ctype
    if base in ("uuuuuu", "vvvvvv"):
        vals = [x.strip() for x in split_csv(t)]
        vals += ["0"] * (6 - len(vals))
        out = []
        for st, v in zip(stat_order(family), vals[:6]):
            out.append((RSymbol(st), _int(v)))
        return RHash(out)
    if base == "ue":
        vals = [x.strip() for x in split_csv(t)]
        out = []
        for i in range(0, len(vals) - 1, 2):
            out.append([_int(vals[i]), RSymbol(vals[i + 1])])
        return out
    if base == "ev":
        vals = [x.strip() for x in split_csv(t)]
        got = {}
        for i in range(0, len(vals) - 1, 2):
            got[vals[i]] = _int(vals[i + 1])
        # ★ .dat 里六项都在（没分配的努力值是 0），PBS 只写非 0 的那几项
        out = []
        for st in stat_order(family):
            out.append((RSymbol(st), got.get(st, 0)))
        return RHash(out)
    if base in ("ses", "ees"):
        vals = [x.strip() for x in split_csv(t)]
        out = []
        for i in range(0, len(vals) - 2, 3):
            sp, method, param = vals[i], vals[i + 1], vals[i + 2]
            p: Any
            param = param.lstrip(":")      # 有些工具会写成 :MOONSTONE
            if param == "":
                p = None
            elif param.lstrip("-").isdigit():
                p = int(param)
            else:
                p = RSymbol(param)
            out.append([RSymbol(sp), RSymbol(method), p, False])
        return out
    # 携带球：编号或内部名都收（同人游戏两种都写）
    if base == "ball":
        if t.lstrip("-").isdigit():
            return int(t)
        return RSymbol(t)
    # 玩家角色（v19 的 PlayerA~H）：第一个是训练家类型符号，其余是行走图名
    if base == "player":
        vals = [x.strip() for x in split_csv(t)]
        out2: List[Any] = [RSymbol(vals[0])] if vals else []
        out2.extend(vals[1:])
        return out2
    if (re.fullmatch(r"[a-zA-Z]{2,}", base)
            and base[0] not in ("s", "q", "n", "m")
            and base not in ("player", "ball")):
        vals = [x.strip() for x in split_csv(t)]
        out3 = []
        for i, v in enumerate(vals):
            if v == "":
                out3.append(None)          # 空位保持 nil，别写成 0
                continue
            out3.append(cast_value(v, base[i] if i < len(base) else base[0],
                                   enum))
        return out3
    if multi:
        vals = split_csv(t)
        return [cast_value(v, base, enum) for v in vals if v != ""]
    # 标量的符号/枚举字段里出现逗号 → 当成列表（同人游戏把 @item 存成数组）
    if base in ("e", "m") and "," in t:
        parts = [x for x in split_csv(t) if x != ""]
        if len(parts) >= 2:
            return [cast_value(x, base, enum) for x in parts]
    val = cast_value(t, base, enum)
    if unquote and isinstance(val, str):
        val = _unquote_csv(val)
    return val


def _default_for(cls: str, family: str, ivar: str) -> Any:
    for name, default in NEW_IVARS.get((cls, family), []):
        if name == ivar:
            return default
    return None


def _patch(obj: RObject, ivars: Dict[str, Any]) -> None:
    attrs = dict(obj.ivars or {})
    attrs.update(ivars)
    obj.ivars = attrs


def _split_line_values(schema: List[tuple],
                       values: List[str]) -> List[Tuple[str, str]]:
    """
    行式格式：把一行切出来的值按 schema 位置分配。

    ★ 坑：列表字段（如 v19 moves 的 Flags）写出去是逗号连接的多值，
      会把后面的字段挤位。官方 v19 的 Flags 是紧凑字符串所以没这事；
      同人游戏改成数组后得在这里把多出来的值并回列表字段
      （只处理「恰好一个列表字段」的情况，v19 行式文件都满足）。
    """
    n_list = sum(1 for _k, _i, c, _e in schema if c[0] in "*^")
    extra = len(values) - len(schema)
    out: List[Tuple[str, str]] = []
    i = 0
    for key, ivar, ctype, enum in schema:
        if ctype[0] in "*^" and extra > 0 and n_list == 1:
            take = 1 + extra
            chunk = values[i:i + take]
            i += take
            extra = 0
            out.append((key, ",".join(chunk)))
        else:
            out.append((key, values[i] if i < len(values) else ""))
            i += 1
    return out


def _coerce_like(new: Any, orig: Any) -> Any:
    """
    照原对象的类型修正解析结果。

    ★ 有些字段类型在 PBS 文本里分不出来（进化参数可以是数字 / 符号 / 字符串，
      Offspring 官方 schema 写字符串、同人游戏却存符号），克隆出来的对象
      这里统一按「原来是什么类型就还原成什么类型」处理，避免改一字段就
      把整条数据的类型改掉。
    """
    if orig is None or new is None:
        return new
    if isinstance(orig, RSymbol):
        if isinstance(new, (RSymbol, str)):
            return RSymbol(_sym(new))
        return new
    if isinstance(orig, str) and isinstance(new, RSymbol):
        return new.name
    if isinstance(orig, str) and isinstance(new, (list, tuple)):
        # ★ v19 的招式 Flags 在 .dat 里是紧凑字符串（"abef"），PBS 读出来
        #   是单元素列表；原对象是字符串就还原成字符串。
        if len(new) == 1 and isinstance(new[0], str):
            return new[0]
        return ",".join(str(_sym(x)) for x in new)
    if isinstance(orig, (list, tuple)) and isinstance(new, (str, RSymbol)):
        return [_sym(new)] if _sym(new) != "" else []
    if isinstance(orig, (list, tuple)) and isinstance(new, (list, tuple)):
        out = []
        for i, x in enumerate(new):
            out.append(_coerce_like(x, orig[i]) if i < len(orig) else x)
        return out
    return new


def _section_rows(spec: dict, family: str, text: str,
                  orig_by_id: Dict[str, RObject], has_id_number: bool,
                  only_forms: bool, start_idx: int = 0,
                  base_of: Optional[Dict[str, dict]] = None
                  ) -> List[Tuple[RObject, Any, Optional[int]]]:
    """段式文本 -> [(对象, 顶层键, 编号), ...]（pokemon / forms 共用）。"""
    schema = schema_of(spec, family)
    cls = spec.get("cls") or "GameData::Type"
    keymode = spec.get("keymode", "symbol")
    number_mode = family == "v19" and any(
        k == "InternalName" for k, _i, _c, _e in schema)
    rows: List[Tuple[RObject, Any, Optional[int]]] = []
    for idx, sec in enumerate(parse_sections(text)):
        fmap: Dict[str, str] = {}
        for k, v in sec.fields:
            fmap.setdefault(k, v)
        if spec.get("key") == "moves":
            # 官方 v20 / v20.1 之间把 BaseDamage 改名成 Power，两种标签都收
            if "Power" in fmap and "BaseDamage" not in fmap:
                fmap["BaseDamage"] = fmap["Power"]
            elif "BaseDamage" in fmap and "Power" not in fmap:
                fmap["Power"] = fmap["BaseDamage"]
        ivars: Dict[str, Any] = {}
        id_sym: Optional[str] = None
        id_num = start_idx + idx
        if keymode == "idnum":
            id_num = _int(sec.name)
            id_sym = str(id_num)      # _build_object 靠字符串查原对象
            ivars["@id"] = id_num
        elif number_mode:
            id_num = _int(sec.name)
            internal = fmap.get("InternalName", "")
            id_sym = internal
            ivars["@id"] = RSymbol(internal)
            if has_id_number or family == "v19":
                ivars["@id_number"] = id_num
        elif only_forms:
            parts = [p.strip() for p in sec.name.split(",")]
            sp = RSymbol(parts[0]) if parts else None
            form = _int(parts[1]) if len(parts) > 1 else 0
            id_sym = "%s_%d" % (parts[0], form) if parts else ""
            ivars["@id"] = RSymbol(id_sym) if id_sym else None
            ivars["@species"] = sp
            ivars["@form"] = form
        else:
            id_sym = sec.name
            ivars["@id"] = RSymbol(sec.name)
            if has_id_number or family == "v19":
                ivars["@id_number"] = id_num
        provided = set()
        for key, ivar, ctype, enum in schema:
            if key not in fmap:
                continue
            base = ctype[1:] if ctype[0] in "*^" else ctype
            val = _parse_field_text(fmap[key], ctype, family, enum,
                                    unquote=(base != "q"))
            if val is None:
                # ★ 形态文件里「写了但是空的」等价于没写 —— 交给基础形态继承
                if only_forms:
                    continue
                val = _default_for(cls, family, "@" + ivar)
            ivars["@" + ivar] = val
            provided.add("@" + ivar)
        _post_process_ivars(cls, family, ivars, provided)
        if only_forms and base_of is not None:
            _apply_form_inherit(ivars, base_of.get(
                _sym(ivars.get("@species"))), family, provided)
        orig_obj = orig_by_id.get(id_sym or "")
        if orig_obj is not None:
            oiv = _obj_ivars(orig_obj)
            for _k, ivar, _c, _e in schema:
                nm = "@" + ivar
                if nm in ivars and nm in oiv:
                    ivars[nm] = _coerce_like(ivars[nm], oiv[nm])
        obj = _build_object(cls, family, orig_by_id, id_sym or "", ivars,
                            has_id_number)
        rows.append((obj, RSymbol(id_sym) if id_sym else id_num, id_num))
    return rows


def compile_gamedata(spec: dict, family: str, game_root: str, text: str,
                     only_forms: bool = False) -> Tuple[bool, str, str]:
    """段式 / 行式 / kv 式文件编译。"""
    schema = schema_of(spec, family)
    cls = spec.get("cls") or "GameData::Type"
    keymode = spec.get("keymode", "symbol")
    style = style_of(spec, family)
    dat_path = os.path.join(game_root, "Data", spec["dat"][0])
    orig = load_dat(dat_path)
    has_id_number = bool(orig and orig.has_id_number)
    dual = bool(orig and orig.dual) if family == "v19" else False
    orig_by_id: Dict[str, RObject] = {}
    if orig:
        for _k, v in orig.entries:
            orig_by_id[_sym(_obj_ivars(v).get("@id"))] = v

    rows: List[Tuple[RObject, Any, Optional[int]]] = []
    n = 0
    if style == "line":
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("\ufeff"):
                continue
            vals = split_csv(line)
            ivars: Dict[str, Any] = {}
            id_sym = None
            id_num = 0
            for key, v in _split_line_values(schema, vals):
                ivar = next(i for k, i, _c, _e in schema if k == key)
                ctype = next(c for k, _i, c, _e in schema if k == key)
                enum = next(e for k, _i, _c, e in schema if k == key)
                if ivar == "id":
                    id_sym = _unquote_csv(v)
                    ivars["@id"] = RSymbol(id_sym)
                elif ivar == "id_number":
                    id_num = _int(v)
                    if has_id_number or family == "v19":
                        ivars["@id_number"] = id_num
                else:
                    val = _parse_field_text(v, ctype, family, enum)
                    if val is None:
                        val = _default_for(cls, family, "@" + ivar)
                    ivars["@" + ivar] = val
            obj = _build_object(cls, family, orig_by_id, id_sym or "", ivars,
                                has_id_number)
            rows.append((obj, RSymbol(id_sym) if id_sym else id_num, id_num))
            n += 1
    elif style == "kv":
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("\ufeff"):
                continue
            m = _KV_RE.match(line)
            if not m:
                continue
            key, value = m.group(1), m.group(2)
            vals = [x.strip() for x in split_csv(value)]
            order = spec.get("v19kv") or []
            ivars = {"@id": RSymbol(key)}
            for i, ivar in enumerate(order):
                v = vals[i] if i < len(vals) else ""
                if spec["key"] == "shadow_pokemon":
                    ivars["@" + ivar] = [RSymbol(x) for x in
                                         split_csv(v) if x]
                else:
                    ivars["@" + ivar] = _int(v)
            obj = _build_object(cls, family, orig_by_id, key, ivars,
                                has_id_number)
            rows.append((obj, RSymbol(key), None))
            n += 1
    else:
        rows = _section_rows(spec, family, text, orig_by_id, has_id_number,
                             only_forms)
        n = len(rows)
    ok, msg = _write_dat(dat_path, rows, keymode, dual, cls)
    return ok, msg, "%d 条" % n


def _clone_val(v: Any) -> Any:
    """浅层深拷贝：列表/哈希复制一份，标量原样（继承基础形态时用）。"""
    if isinstance(v, list):
        return [_clone_val(x) for x in v]
    if isinstance(v, tuple):
        return tuple(_clone_val(x) for x in v)
    if isinstance(v, RHash):
        return RHash([(k, _clone_val(x)) for k, x in v.pairs], v.default)
    return v


# 官方 validate_compiled_pokemon_form 里「没写就从基础形态继承」的字段
_FORM_INHERIT_ALWAYS = (
    "@real_name", "@real_category", "@real_pokedex_entry", "@base_exp",
    "@growth_rate", "@gender_ratio", "@catch_rate", "@happiness",
    "@hatch_steps", "@incense", "@height", "@weight", "@color", "@shape",
    "@habitat", "@generation",
    # v19 的形态会把战斗坐标也继承下来（v20+ 挪进 species_metrics.dat）
    "@back_sprite_x", "@back_sprite_y", "@front_sprite_x", "@front_sprite_y",
    "@front_sprite_altitude", "@shadow_x", "@shadow_size",
)
_FORM_INHERIT_LIST = (
    "@types", "@type1", "@type2", "@base_stats", "@evs", "@tutor_moves",
    "@egg_moves", "@abilities", "@hidden_abilities", "@egg_groups",
    "@offspring", "@flags", "@moves", "@evolutions",
)
_FORM_WILD = ("@wild_item_common", "@wild_item_uncommon", "@wild_item_rare")


def _apply_form_inherit(ivars: Dict[str, Any], base: Optional[dict],
                        family: str = "", provided: Optional[set] = None
                        ) -> None:
    """
    照官方 validate_compiled_pokemon_form：形态没写的属性从基础形态继承。

    ★ 不继承的话，提取时「与基础形态一致的字段不写」这条规则就失效，
      pokemon_forms.txt 会把所有默认值都吐出来（实测 2313 行变 6142 行）。
    """
    if base is None:
        return
    provided = provided or set()
    for name in _FORM_INHERIT_ALWAYS:
        if name in base and ivars.get(name) is None:
            ivars[name] = _clone_val(base[name])
    for name in _FORM_INHERIT_LIST:
        if name not in base:
            continue
        cur = ivars.get(name)
        if cur is None or (isinstance(cur, (list, tuple)) and not cur):
            ivars[name] = _clone_val(base[name])
    if all(ivars.get(name) is None for name in _FORM_WILD):
        for name in _FORM_WILD:
            if name in base:
                ivars[name] = _clone_val(base[name])
    if family == "v19":
        # 官方 v19：单属性形态只写了 Type1 时，Type2 跟着 Type1（不继承基础形态）
        if "@type1" in provided and "@type2" not in provided:
            ivars["@type2"] = ivars.get("@type1")
        # 官方 v19：形态只要写了任意一个野生道具，就不再继承其余的
        if any(name in provided for name in _FORM_WILD):
            for name in _FORM_WILD:
                if name not in provided:
                    ivars[name] = None


def _post_process_ivars(cls: str, family: str, ivars: Dict[str, Any],
                        provided: set) -> None:
    """
    官方 initialize 里「没写就按别的字段算出来」的那些派生值。

    ★ 必须在 ivars 里显式落下来：否则克隆旧 .dat 时会留着上一版的默认值
      （实测 SellPrice 多写 480 行、ShowQuantity 多写 693 行）。
    """
    if cls != "GameData::Item" or family not in ("v20", "v21"):
        return
    if "@sell_price" not in provided:
        ivars["@sell_price"] = _int(ivars.get("@price", 0)) // 2
    if family == "v21" and "@bp_price" not in provided:
        ivars["@bp_price"] = 1
    if "@consumable" not in provided:
        ivars["@consumable"] = not _item_important(ivars)
    if "@show_quantity" not in provided:
        ivars["@show_quantity"] = None


def compile_species(family: str, game_root: str) -> Tuple[bool, str, str]:
    """
    pokemon.txt + pokemon_forms.txt 一起编译回 species.dat。

    ★ 两个文件对应同一个 .dat（基础形态 + 形态都在里面），单独编译任何一个
      都会把另一半冲掉，所以必须合并后一次性写回。
    """
    pbs = pbs_dir(game_root)
    dat_path = os.path.join(game_root, "Data", "species.dat")
    orig = load_dat(dat_path)
    has_id_number = bool(orig and orig.has_id_number)
    dual = bool(orig and orig.dual) if family == "v19" else False
    orig_by_id: Dict[str, RObject] = {}
    if orig:
        for _k, v in orig.entries:
            orig_by_id[_sym(_obj_ivars(v).get("@id"))] = v
    rows: List[Tuple[RObject, Any, Optional[int]]] = []
    base_of: Dict[str, dict] = {}
    n_base = n_form = 0
    for key, only_forms in (("pokemon", False), ("pokemon_forms", True)):
        spec = file_for(key)
        path = os.path.join(pbs, txt_name(spec, family))
        if not os.path.isfile(path):
            continue
        text = open(path, "rb").read().decode("utf-8-sig", errors="replace")
        part = _section_rows(spec, family, text, orig_by_id, has_id_number,
                             only_forms, start_idx=len(rows),
                             base_of=base_of if only_forms else None)
        if only_forms:
            n_form = len(part)
        else:
            n_base = len(part)
            for obj, _k, _n in part:      # 基础形态：给形态继承用
                iv = _obj_ivars(obj)
                if _int(iv.get("@form", 0)) == 0:
                    base_of[_sym(iv.get("@species") or iv.get("@id"))] = iv
        rows.extend(part)
    if not rows:
        return False, "PBS 目录里没有 pokemon.txt / pokemon_forms.txt", ""
    _add_prevolutions(rows)
    if family == "v19":
        max_num = max((_int(_obj_ivars(o).get("@id_number", 0))
                       for o, _k, _n in rows), default=0)
        for obj, _k, _n in rows:
            iv = _obj_ivars(obj)
            if _int(iv.get("@form", 0)) != 0 and not iv.get("@id_number"):
                max_num += 1
                iv["@id_number"] = max_num
    ok, msg = _write_dat(dat_path, rows, "symbol", dual, "GameData::Species")
    return ok, msg, "%d 基础形态 + %d 形态" % (n_base, n_form)


def _add_prevolutions(rows: List[Tuple[RObject, Any, Optional[int]]]) -> None:
    """
    照官方 validate_all_compiled_pokemon 的做法，给每个「被进化方」补一条
    前置进化记录（evo[3] = true）。txt 里只写正向进化，不补的话
    pbGetBabySpecies / 蛋组判断会缺数据。

    键只看「进化目标物种」—— 前置进化对该物种的**所有形态**都要补
    （踩过：MRMIME_1、FLOETTE_5 的前置进化就是这么来的）。
    """
    all_evos: Dict[str, list] = {}
    for obj, _k, _n in rows:
        iv = _obj_ivars(obj)
        for evo in _as_list(iv.get("@evolutions")):
            if not isinstance(evo, (list, tuple)) or not evo:
                continue
            if len(evo) > 3 and evo[3]:
                continue
            target = _sym(evo[0])
            if not target:
                continue
            if target not in all_evos:
                all_evos[target] = [_sym(iv.get("@species") or iv.get("@id")),
                                    evo[1] if len(evo) > 1 else None,
                                    evo[2] if len(evo) > 2 else None, True]
    if not all_evos:
        return
    for obj, _k, _n in rows:
        iv = _obj_ivars(obj)
        prevo = all_evos.get(_sym(iv.get("@species") or iv.get("@id")))
        if not prevo:
            continue
        evos = _as_list(iv.get("@evolutions"))
        for e in evos:
            if len(e) > 3 and e[3] and _sym(e[0]) == prevo[0]:
                break
        else:
            orig_e = iv.get("@evolutions")
            if isinstance(orig_e, (list, tuple)) and orig_e:
                prevo = _coerce_like(list(prevo), orig_e[0])
            iv["@evolutions"] = evos + [list(prevo)]


def _build_object(cls: str, family: str, orig_by_id: Dict[str, RObject],
                  id_key: str, ivars: Dict[str, Any],
                  has_id_number: bool) -> RObject:
    """能克隆就克隆（保住自造 ivar），否则按默认表新建。"""
    orig = orig_by_id.get(id_key)
    if orig is not None:
        obj = RObject(cls)
        obj.ivars = dict(orig.ivars or {})
        _patch(obj, ivars)
        return obj
    return _new_object(cls, family, ivars, has_id_number)


def _write_dat(path: str, rows: List[Tuple[RObject, Any, Optional[int]]],
               keymode: str, dual: bool, cls: str) -> Tuple[bool, str]:
    """把编译结果写回 .dat（第一次编译前留 .orig）。

    rows = [(对象, 顶层键, 编号), ...]；顶层键可以是 Symbol / 整数 / 数组
    （v19+ 的 Trainer 就是用 [类型, 名字, 版本] 数组当键的）。
    """
    try:
        if os.path.isfile(path):
            orig = path + ".orig"
            if not os.path.isfile(orig):
                shutil.copy2(path, orig)
        pairs = []
        for i, (obj, key, num) in enumerate(rows):
            if keymode == "idnum":
                pairs.append((num if num is not None else i, obj))
                continue
            if key is None:
                key = RSymbol("ENTRY_%d" % i)
            pairs.append((key, obj))
            if dual:
                if num is None:
                    num = _int(_obj_ivars(obj).get("@id_number", i))
                pairs.append((num, obj))
        data = rmarshal.dumps(RHash(pairs))
        with open(path, "wb") as f:
            f.write(data)
        return True, ""
    except Exception as e:
        return False, "写入 %s 失败：%s" % (os.path.basename(path), e)


def compile_trainers(spec: dict, family: str, game_root: str,
                     text: str) -> Tuple[bool, str, str]:
    schema = schema_of(spec, family)
    sub_schema = spec.get("sub_schema", {}).get(family) or []
    cls = "GameData::Trainer"
    dat_path = os.path.join(game_root, "Data", "trainers.dat")
    orig = load_dat(dat_path)
    has_id_number = bool(orig and orig.has_id_number)
    orig_by_id: Dict[str, RObject] = {}
    if orig:
        for _k, v in orig.entries:
            iv = _obj_ivars(v)
            key = _trainer_key(iv)
            if key:
                orig_by_id[key] = v
    # 逐行扫，Pokemon = 开新宝可梦，缩进的键属于当前宝可梦
    rows: List[Tuple[RObject, Any, Optional[int]]] = []
    cur: Optional[dict] = None
    cur_pkmn: Optional[dict] = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = _SEC_RE.match(line)
        if m:
            if cur is not None:
                obj = _finish_trainer(cls, family, cur, orig_by_id,
                                      has_id_number)
                iv = _obj_ivars(obj)
                rows.append((obj, iv.get("@id"),
                             _int(iv.get("@id_number", len(rows)))))
            parts = [p.strip() for p in m.group(1).split(",")]
            ttype = RSymbol(parts[0]) if parts else None
            name = parts[1] if len(parts) > 1 else ""
            ver = _int(parts[2]) if len(parts) > 2 else 0
            cur = {"ttype": ttype, "name": name, "ver": ver,
                   "ivars": {}, "pokemon": []}
            cur_pkmn = None
            continue
        if cur is None:
            continue
        m = re.match(r"^(\s*)(\w+)\s*=\s*(.*?)\s*$", line)
        if not m:
            continue
        indent, key, value = len(m.group(1)), m.group(2), m.group(3)
        if key == "Pokemon" and not indent:
            vals = [x.strip() for x in split_csv(value)]
            cur_pkmn = {RSymbol("species"): RSymbol(vals[0]) if vals else None,
                        RSymbol("level"): _int(vals[1]) if len(vals) > 1 else 1}
            cur["pokemon"].append(cur_pkmn)
            continue
        if indent and cur_pkmn is not None:
            for k2, ivar, ctype, enum in sub_schema:
                if k2 != key:
                    continue
                if ctype == "b":
                    cur_pkmn[RSymbol(ivar)] = value.strip().lower() in (
                        "1", "true", "yes", "y")
                elif ctype == "s" and ivar == "gender":
                    cur_pkmn[RSymbol(ivar)] = 1 if value.strip().lower() == \
                        "female" else 0
                else:
                    val = _parse_field_text(value, ctype, family, enum)
                    if val is not None:
                        cur_pkmn[RSymbol(ivar)] = val
            continue
        for k2, ivar, ctype, enum in schema:
            if k2 != key:
                continue
            base = ctype[1:] if ctype[0] in "*^" else ctype
            val = _parse_field_text(value, ctype, family, enum,
                                    unquote=(base != "q"))
            if val is None:
                val = _default_for(cls, family, "@" + ivar)
            cur["ivars"]["@" + ivar] = val
    if cur is not None:
        obj = _finish_trainer(cls, family, cur, orig_by_id, has_id_number)
        iv = _obj_ivars(obj)
        rows.append((obj, iv.get("@id"),
                     _int(iv.get("@id_number", len(rows)))))
    ok, msg = _write_dat(dat_path, rows, "symbol", family == "v19", cls)
    return ok, msg, "%d 条" % len(rows)


def _trainer_key(iv: dict) -> str:
    ttype = _sym(iv.get("@trainer_type"))
    name = iv.get("@real_name")
    name = str(name) if name is not None else ""
    ver = _int(iv.get("@version", 0))
    return "%s|%s|%d" % (ttype, name, ver)


def _finish_trainer(cls: str, family: str, cur: dict,
                    orig_by_id: Dict[str, RObject],
                    has_id_number: bool) -> RObject:
    key = "%s|%s|%d" % (_sym(cur["ttype"]), cur["name"], cur["ver"])
    orig = orig_by_id.get(key)
    ivars = dict(cur["ivars"])
    ivars["@trainer_type"] = cur["ttype"]
    ivars["@real_name"] = cur["name"]
    ivars["@version"] = cur["ver"]
    # ★ 每只宝可梦也照「克隆 + 打补丁」来：同人游戏常往队伍里塞自造字段
    #   （assigned_position / extra_abilities 之类），重建就丢了。
    orig_pkmn = _as_list(_obj_ivars(orig).get("@pokemon")) if orig else []
    pkmn_rows = []
    for i, p in enumerate(cur["pokemon"]):
        pairs = [(RSymbol(k) if not isinstance(k, RSymbol) else k, v)
                 for k, v in p.items() if v not in (None, "")]
        if i < len(orig_pkmn) and isinstance(orig_pkmn[i], RHash):
            h = RHash(list(orig_pkmn[i].items()))
            for k, v in pairs:
                h[k] = v
        else:
            h = RHash(pairs)
        pkmn_rows.append(h)
    ivars["@pokemon"] = pkmn_rows
    if orig is not None:
        obj = RObject(cls)
        obj.ivars = dict(orig.ivars or {})
        _patch(obj, ivars)
        return obj
    # 新训练家：@id 用数组（官方格式）
    new_ivars = dict(ivars)
    new_ivars["@id"] = [cur["ttype"], cur["name"], cur["ver"]]
    if has_id_number or family == "v19":
        new_ivars["@id_number"] = 0
    return _new_object(cls, family, new_ivars, has_id_number)


def compile_encounters(spec: dict, family: str, game_root: str,
                       text: str) -> Tuple[bool, str, str]:
    cls = "GameData::Encounter"
    dat_path = os.path.join(game_root, "Data", "encounters.dat")
    orig = load_dat(dat_path)
    orig_by_id: Dict[str, RObject] = {}
    if orig:
        for _k, v in orig.entries:
            orig_by_id[_sym(_obj_ivars(v).get("@id"))] = v
    rows: List[Tuple[RObject, Optional[str], Optional[int]]] = []
    cur: Optional[dict] = None
    cur_type: Optional[RSymbol] = None
    n = 0
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = _SEC_RE.match(line)
        if m:
            if cur is not None:
                obj = _finish_encounter(cls, cur, orig_by_id)
                rows.append((obj, _obj_ivars(obj).get("@id"),
                             _int(_obj_ivars(obj).get("@map", 0))))
                n += 1
            inside = m.group(1)
            if "#" in inside:
                inside = inside.split("#", 1)[0].strip()
            parts = [p.strip() for p in inside.split(",")]
            mnum = _int(parts[0])
            mver = _int(parts[1]) if len(parts) > 1 else 0
            cur = {"map": mnum, "ver": mver, "types": RHash(),
                   "chances": RHash()}
            cur_type = None
            continue
        if cur is None:
            continue
        stripped = line.strip()
        if line.startswith("    ") or line.startswith("\t"):
            vals = [x.strip() for x in split_csv(stripped)]
            if len(vals) >= 3 and cur_type is not None:
                chance = _int(vals[0])
                sp = RSymbol(vals[1])
                mn = _int(vals[2])
                mx = _int(vals[3]) if len(vals) > 3 else mn
                slots = cur["types"][cur_type]
                if slots is None:
                    slots = []
                    cur["types"][cur_type] = slots
                slots.append([chance, sp, mn, mx])
            continue
        vals = [x.strip() for x in split_csv(stripped)]
        if vals and vals[0]:
            cur_type = RSymbol(vals[0])
            if len(vals) > 1 and vals[1]:
                cur["chances"][cur_type] = _int(vals[1])
            if cur["types"][cur_type] is None:
                cur["types"][cur_type] = []
    if cur is not None:
        obj = _finish_encounter(cls, cur, orig_by_id)
        rows.append((obj, _obj_ivars(obj).get("@id"),
                     _int(_obj_ivars(obj).get("@map", 0))))
        n += 1
    ok, msg = _write_dat(dat_path, rows, "symbol", False, cls)
    return ok, msg, "%d 条" % n


def _finish_encounter(cls: str, cur: dict,
                      orig_by_id: Dict[str, RObject]) -> RObject:
    eid = "%d_%d" % (cur["map"], cur["ver"])
    orig = orig_by_id.get(eid)
    # 概率表以 txt 写的为准，没写的沿用原来的（有的游戏给每种遭遇都留一条 0）
    chances = RHash()
    orig_ch = _obj_ivars(orig).get("@step_chances") if orig is not None else None
    for t, _v in cur["types"].items():
        got = cur["chances"][t]
        if got is None and orig_ch is not None:
            got = orig_ch.get(t)
        if got is not None:
            chances[t] = got
    ivars = {"@map": cur["map"], "@version": cur["ver"],
             "@types": cur["types"], "@step_chances": chances}
    if orig is not None:
        obj = RObject(cls)
        obj.ivars = dict(orig.ivars or {})
        _patch(obj, ivars)
        return obj
    ivars["@id"] = RSymbol(eid)
    return _new_object(cls, "v21", ivars, False)


def compile_town_map(spec: dict, family: str, game_root: str,
                     text: str) -> Tuple[bool, str, str]:
    dat_path = os.path.join(game_root, "Data", "town_map.dat")
    orig = load_dat(dat_path)
    sections = parse_sections(text)
    if family == "v19":
        data = []
        for i, sec in enumerate(sections):
            fmap = {}
            for k, v in sec.fields:
                fmap.setdefault(k, v)
            name = _unq(fmap.get("Name", ""))
            fname = _unq(fmap.get("Filename", ""))
            points = []
            for k, v in sec.fields:
                if k == "Point":
                    vals = split_csv(v)
                    pts = []
                    for x in vals:
                        if x.lstrip("-").isdigit():
                            pts.append(int(x))
                        else:
                            pts.append(_unq(x))
                    points.append(pts)
            while len(data) <= i:
                data.append([None, None, []])
            data[i] = [name, fname, points]
        try:
            if os.path.isfile(dat_path) and not os.path.isfile(dat_path + ".orig"):
                shutil.copy2(dat_path, dat_path + ".orig")
            with open(dat_path, "wb") as f:
                f.write(rmarshal.dumps(data))
            return True, "", "%d 个区域" % len(data)
        except Exception as e:
            return False, "写入 town_map.dat 失败：%s" % e, ""
    # v20/v21
    cls = "GameData::TownMap"
    orig_by_id: Dict[str, RObject] = {}
    if orig:
        for _k, v in orig.entries:
            orig_by_id[str(_int(_obj_ivars(v).get("@id", 0)))] = v
    rows: List[Tuple[RObject, Optional[str], Optional[int]]] = []
    for sec in sections:
        fmap = {}
        for k, v in sec.fields:
            fmap.setdefault(k, v)
        rid = _int(sec.name)
        points = []
        for k, v in sec.fields:
            if k == "Point":
                vals = split_csv(v)
                pts = []
                for x in vals:
                    if x == "":
                        pts.append(None)
                    elif x.lstrip("-").isdigit():
                        pts.append(int(x))
                    else:
                        pts.append(_unq(x))
                points.append(pts)
        ivars = {"@id": rid,
                 "@real_name": _unq(fmap.get("Name", "")) or "???",
                 "@filename": _unq(fmap.get("Filename", "")) or None,
                 "@point": points,
                 "@flags": [RSymbol(x) for x in
                            split_csv(fmap.get("Flags", "")) if x]}
        orig_obj = orig_by_id.get(str(rid))
        if orig_obj is not None:
            obj = RObject(cls)
            obj.ivars = dict(orig_obj.ivars or {})
            _patch(obj, ivars)
        else:
            obj = _new_object(cls, family, ivars, False)
        rows.append((obj, None, rid))
    ok, msg = _write_dat(dat_path, rows, "idnum", False, cls)
    return ok, msg, "%d 个区域" % len(rows)


def _unq(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"')
    return s


def compile_connections(spec: dict, family: str, game_root: str,
                        text: str) -> Tuple[bool, str, str]:
    dat_path = os.path.join(game_root, "Data", "map_connections.dat")
    records = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("﻿"):
            continue
        vals = [x.strip() for x in split_csv(line)]
        if len(vals) < 6:
            continue
        rec = []
        for i, x in enumerate(vals[:6]):
            if i in (1, 4) and not x.lstrip("-").isdigit():
                rec.append(RSymbol(x[0].upper() if x else "N"))
            else:
                rec.append(_int(x))
        records.append(rec)
    try:
        if os.path.isfile(dat_path) and not os.path.isfile(dat_path + ".orig"):
            shutil.copy2(dat_path, dat_path + ".orig")
        with open(dat_path, "wb") as f:
            f.write(rmarshal.dumps(records))
        return True, "", "%d 条" % len(records)
    except Exception as e:
        return False, "写入 map_connections.dat 失败：%s" % e, ""


def compile_regional(spec: dict, family: str, game_root: str,
                     text: str) -> Tuple[bool, str, str]:
    dat_path = os.path.join(game_root, "Data", "regional_dexes.dat")
    lists: List[List[RSymbol]] = []
    cur: Optional[List[RSymbol]] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("﻿"):
            continue
        m = _SEC_RE.match(line)
        if m:
            idx = _int(m.group(1))
            while len(lists) <= idx:
                lists.append([])
            cur = lists[idx]
            continue
        if cur is None:
            continue
        for x in split_csv(line):
            x = x.strip()
            if x:
                cur.append(RSymbol(x))
    try:
        if os.path.isfile(dat_path) and not os.path.isfile(dat_path + ".orig"):
            shutil.copy2(dat_path, dat_path + ".orig")
        with open(dat_path, "wb") as f:
            f.write(rmarshal.dumps(lists))
        return True, "", "%d 个图鉴" % len(lists)
    except Exception as e:
        return False, "写入 regional_dexes.dat 失败：%s" % e, ""


_PHONE_KEYS = [("Intro", "intro"), ("IntroMorning", "intro_morning"),
               ("IntroAfternoon", "intro_afternoon"),
               ("IntroEvening", "intro_evening"), ("Body", "body"),
               ("Body1", "body1"), ("Body2", "body2"),
               ("BattleRequest", "battle_request"),
               ("BattleRemind", "battle_remind"), ("End", "end")]


def compile_phone(spec: dict, family: str, game_root: str,
                  text: str) -> Tuple[bool, str, str]:
    dat_path = os.path.join(game_root, "Data", "phone.dat")
    sections = parse_sections(text)
    if family == "v19":
        groups = {"Generics": "@generics", "BattleRequests": "@battleRequests",
                  "GreetingsMorning": "@greetingsMorning",
                  "GreetingsEvening": "@greetingsEvening",
                  "Greetings": "@greetings", "Bodies1": "@bodies1",
                  "Bodies2": "@bodies2"}
        ivars = {}
        for sec in sections:
            ivar = groups.get(sec.name.strip("<>"))
            if not ivar:
                continue
            ivars[ivar] = [v for _k, v in sec.fields]
        obj = RObject("PhoneDatabase")
        obj.ivars = ivars
        try:
            if os.path.isfile(dat_path) and not os.path.isfile(dat_path + ".orig"):
                shutil.copy2(dat_path, dat_path + ".orig")
            with open(dat_path, "wb") as f:
                f.write(rmarshal.dumps(obj))
            return True, "", "%d 组" % len(ivars)
        except Exception as e:
            return False, "写入 phone.dat 失败：%s" % e, ""
    cls = "GameData::PhoneMessage"
    orig = load_dat(dat_path)
    orig_by_id: Dict[str, RObject] = {}
    if orig:
        for _k, v in orig.entries:
            orig_by_id[str(_obj_ivars(v).get("@id"))] = v
    rows: List[Tuple[RObject, Optional[str], Optional[int]]] = []
    for sec in sections:
        msgs: Dict[str, List[str]] = {k: [] for k, _ in _PHONE_KEYS}
        for k, v in sec.fields:
            for pk, _iv in _PHONE_KEYS:
                if k == pk:
                    msgs[pk].append(_unq(v))
        ivars: Dict[str, Any] = {}
        for pk, iv in _PHONE_KEYS:
            ivars["@" + iv] = msgs[pk] or None
        name = sec.name
        if name.strip().lower() == "default":
            ivars["@id"] = "default"
            ivars["@trainer_type"] = "default"
            key = "default"
        else:
            parts = [p.strip() for p in name.split(",")]
            ttype = RSymbol(parts[0]) if parts else None
            pname = parts[1] if len(parts) > 1 else ""
            ver = _int(parts[2]) if len(parts) > 2 else 0
            ivars["@id"] = [ttype, pname, ver]
            ivars["@trainer_type"] = ttype
            ivars["@real_name"] = pname
            ivars["@version"] = ver
            key = str([ttype, pname, ver])
        orig_obj = orig_by_id.get(key)
        if orig_obj is not None:
            obj = RObject(cls)
            obj.ivars = dict(orig_obj.ivars or {})
            _patch(obj, ivars)
        else:
            obj = _new_object(cls, family, ivars, False)
        rows.append((obj, None, None))
    ok, msg = _write_dat(dat_path, rows, "symbol", False, cls)
    return ok, msg, "%d 条" % len(rows)


def _meta_objects(dat_path: str, cls: str, family: str,
                  id_int: int, ivars: Dict[str, Any]) -> RObject:
    """metadata 系：优先克隆原对象（保住自定义 ivar），否则新建。"""
    orig = load_dat(dat_path)
    if orig:
        for _k, v in orig.entries:
            if _int(_obj_ivars(v).get("@id", -1)) == id_int:
                obj = RObject(cls)
                obj.ivars = dict(_obj_ivars(v))
                obj.ivars.update(ivars)
                return obj
    return _new_object(cls, family, ivars, False)


def compile_metadata(spec: dict, family: str, game_root: str,
                     text: str) -> Tuple[bool, str, str]:
    """metadata.txt -> metadata.dat（+ player_metadata.dat / map_metadata.dat）。"""
    sections = parse_sections(text)
    data_dir = os.path.join(game_root, "Data")
    if family == "v19":
        gschema = schema_of(spec, "v19")
        mschema = spec.get("v19map_schema") or []
        g_rows: List[Tuple[RObject, Any, Optional[int]]] = []
        m_rows: List[Tuple[RObject, Any, Optional[int]]] = []
        for sec in sections:
            mid = _int(sec.name)
            use = gschema if mid == 0 else mschema
            cls = ("GameData::Metadata" if mid == 0
                   else "GameData::MapMetadata")
            fmap = {}
            for k, v in sec.fields:
                fmap.setdefault(k, v)
            ivars = {"@id": mid}
            for key, ivar, ctype, enum in use:
                if key not in fmap:
                    continue
                base = ctype[1:] if ctype[0] in "*^" else ctype
                val = _parse_field_text(fmap[key], ctype, family, enum,
                                        unquote=(base != "q"))
                if val is None:
                    val = _default_for(cls, family, "@" + ivar)
                ivars["@" + ivar] = val
            if mid == 0:
                obj = _meta_objects(os.path.join(data_dir, "metadata.dat"),
                                    cls, family, mid, ivars)
                g_rows.append((obj, mid, mid))
            else:
                obj = _meta_objects(os.path.join(data_dir, "map_metadata.dat"),
                                    cls, family, mid, ivars)
                m_rows.append((obj, mid, mid))
        ok1, msg1 = _write_dat(os.path.join(data_dir, "metadata.dat"),
                               g_rows, "idnum", False, "GameData::Metadata")
        ok2, msg2 = _write_dat(os.path.join(data_dir, "map_metadata.dat"),
                               m_rows, "idnum", False, "GameData::MapMetadata")
        return (ok1 and ok2), (msg1 + msg2), \
            "%d 全局 + %d 地图" % (len(g_rows), len(m_rows))
    # v20/v21
    gschema = schema_of(spec, family)
    pschema = spec.get("player_schema", {}).get(family) or []
    g_rows, p_rows = [], []
    for sec in sections:
        sid = _int(sec.name)
        fmap = {}
        for k, v in sec.fields:
            fmap.setdefault(k, v)
        if sid == 0:
            cls, use, rows = "GameData::Metadata", gschema, g_rows
        else:
            cls, use, rows = "GameData::PlayerMetadata", pschema, p_rows
        ivars = {"@id": sid}
        for key, ivar, ctype, enum in use:
            if key not in fmap:
                continue
            base = ctype[1:] if ctype[0] in "*^" else ctype
            val = _parse_field_text(fmap[key], ctype, family, enum,
                                    unquote=(base != "q"))
            if val is None:
                val = _default_for(cls, family, "@" + ivar)
            ivars["@" + ivar] = val
        dat = ("metadata.dat" if sid == 0 else "player_metadata.dat")
        obj = _meta_objects(os.path.join(data_dir, dat), cls, family, sid,
                            ivars)
        rows.append((obj, sid, sid))
    ok1, msg1 = _write_dat(os.path.join(data_dir, "metadata.dat"),
                           g_rows, "idnum", False, "GameData::Metadata")
    ok2, msg2 = _write_dat(os.path.join(data_dir, "player_metadata.dat"),
                           p_rows, "idnum", False, "GameData::PlayerMetadata")
    return (ok1 and ok2), (msg1 + msg2), \
        "%d 全局 + %d 玩家" % (len(g_rows), len(p_rows))


def compile_spec(spec: dict, family: str, game_root: str,
                 txt_path: Optional[str] = None) -> Tuple[bool, str, str]:
    """编译一个文件类型。txt_path 默认取 PBS 目录里的对应文件。"""
    if is_legacy(family):
        import pbs_legacy
        return pbs_legacy.compile_spec(spec, family, game_root, txt_path)
    if txt_path is None:
        txt_path = os.path.join(pbs_dir(game_root), txt_name(spec, family))
    if not os.path.isfile(txt_path):
        return False, "找不到 %s" % os.path.basename(txt_path), ""
    try:
        text = open(txt_path, "rb").read().decode("utf-8-sig", errors="replace")
    except OSError as e:
        return False, "读取失败：%s" % e, ""
    editor = spec.get("editor")
    try:
        if editor == "trainers":
            return compile_trainers(spec, family, game_root, text)
        if editor == "encounters":
            return compile_encounters(spec, family, game_root, text)
        if editor == "townmap":
            return compile_town_map(spec, family, game_root, text)
        if editor == "connections":
            return compile_connections(spec, family, game_root, text)
        if editor == "regional":
            return compile_regional(spec, family, game_root, text)
        if editor == "phone":
            return compile_phone(spec, family, game_root, text)
        if editor == "metadata":
            return compile_metadata(spec, family, game_root, text)
        if editor == "facility":
            return compile_facility(spec, family, game_root, text)
        if spec["key"] in ("pokemon", "pokemon_forms"):
            return compile_species(family, game_root)
        only_forms = spec["key"] == "pokemon_forms"
        return compile_gamedata(spec, family, game_root, text,
                                only_forms=only_forms)
    except Exception as e:
        return False, "编译失败：%s" % e, ""


# ---- 对战设施（battle_facility_lists + 关联文件） --------------------------

_BT_TRAINER_FIELDS = [("Type", 0, "e", None), ("Name", 1, "s", None),
                      ("BeginSpeech", 2, "s", None),
                      ("EndSpeechWin", 3, "s", None),
                      ("EndSpeechLose", 4, "s", None),
                      ("PokemonNos", 5, "*u", None)]


def extract_facility_files(spec: dict, family: str, game_root: str,
                           out_dir: str) -> List[str]:
    """连带提取 battle tower / cups 的 txt（内容嵌在 trainer_lists.dat 里）。"""
    written = []
    dat_path = os.path.join(game_root, "Data", "trainer_lists.dat")
    info = load_dat(dat_path)
    if not info or not info.ok:
        return written
    files: Dict[str, list] = {}
    for rec in _as_list(info.obj):
        if not isinstance(rec, (list, tuple)) or len(rec) < 5:
            continue
        tfile = rec[3]
        pfile = rec[4]
        if tfile:
            files[str(tfile)] = _as_list(rec[0])
        if pfile:
            files[str(pfile)] = _as_list(rec[1])
    for fname, data in files.items():
        if "trainers" in fname or fname.startswith("cup") and "tr" in fname:
            text = _bt_trainers_text(data)
        else:
            text = _bt_pokemon_text(data)
        path = os.path.join(out_dir, fname)
        try:
            with open(path, "wb") as f:
                f.write(text.encode("utf-8"))
            written.append(fname)
        except OSError:
            pass
    return written


def _bt_trainers_text(data: list) -> str:
    lines = _file_header({"key": "btt"})
    for i, tr in enumerate(data):
        if not isinstance(tr, (list, tuple)):
            continue
        lines.append(_SEP)
        lines.append("[%03d]" % i)
        for key, pos, ctype, enum in _BT_TRAINER_FIELDS:
            val = tr[pos] if pos < len(tr) else None
            if val is None:
                continue
            txt = fmt_field(val, ctype, "v21", enum)
            if txt is None:
                continue
            lines.append("%s = %s" % (key, txt))
    return _bom_text(lines)


def _bt_pokemon_text(data: list) -> str:
    lines = _file_header({"key": "btp"})
    for pkmn in data:
        iv = _obj_ivars(pkmn)
        if not iv:
            continue
        sp = _sym(iv.get("@species"))
        item = _sym(iv.get("@item")) if iv.get("@item") else ""
        nature = _sym(iv.get("@nature"))
        evs = iv.get("@ev")
        ev_txt = ""
        if isinstance(evs, (list, tuple)):
            ev_txt = ",".join(_sym(x) for x in evs)
        moves = [_sym(m) for m in _as_list(
            [iv.get("@move1"), iv.get("@move2"), iv.get("@move3"),
             iv.get("@move4")]) if m]
        lines.append("%s;%s;%s;%s;%s" % (sp, item, nature, ev_txt,
                                         ",".join(moves)))
    return _bom_text(lines)


def compile_facility(spec: dict, family: str, game_root: str,
                     text: str) -> Tuple[bool, str, str]:
    """battle_facility_lists.txt + 关联 txt -> trainer_lists.dat。"""
    dat_path = os.path.join(game_root, "Data", "trainer_lists.dat")
    sections = parse_sections(text)
    pbs = pbs_dir(game_root)
    rows = []
    for sec in sections:
        fmap = {}
        for k, v in sec.fields:
            fmap.setdefault(k, v)
        tfile = _unq(fmap.get("Trainers", ""))
        pfile = _unq(fmap.get("Pokemon", ""))
        if not tfile or not pfile:
            continue
        challenges = [c.strip() for c in split_csv(fmap.get("Challenges", ""))
                      if c.strip()]
        btt = _read_bt_trainers(os.path.join(pbs, tfile))
        btp = _read_bt_pokemon(os.path.join(pbs, pfile))
        is_default = sec.name == "DefaultTrainerList"
        rows.append([btt, btp, challenges, tfile, pfile, is_default])
    try:
        if os.path.isfile(dat_path) and not os.path.isfile(dat_path + ".orig"):
            shutil.copy2(dat_path, dat_path + ".orig")
        with open(dat_path, "wb") as f:
            f.write(rmarshal.dumps(rows))
        return True, "", "%d 组" % len(rows)
    except Exception as e:
        return False, "写入 trainer_lists.dat 失败：%s" % e, ""


def _read_bt_trainers(path: str) -> list:
    if not os.path.isfile(path):
        return []
    out = []
    for sec in parse_sections(open(path, "rb").read().decode(
            "utf-8-sig", errors="replace")):
        rec: list = []
        for key, pos, ctype, enum in _BT_TRAINER_FIELDS:
            v = section_field(sec, key)
            rec.append(_parse_field_text(v, ctype, "v21", enum)
                       if v is not None else None)
        out.append(rec)
    return out


def _read_bt_pokemon(path: str) -> list:
    if not os.path.isfile(path):
        return []
    out = []
    for raw in open(path, "rb").read().decode("utf-8-sig",
                                              errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(";")
        while len(parts) < 5:
            parts.append("")
        sp, item, nature, evs, moves = parts[:5]
        obj = RObject("PBPokemon")
        obj.ivars = {
            "@species": RSymbol(sp) if sp else None,
            "@item": RSymbol(item) if item else None,
            "@nature": RSymbol(nature) if nature else None,
            "@ev": [RSymbol(x) for x in evs.split(",") if x] or None,
            "@move1": RSymbol(moves.split(",")[0]) if moves else None,
            "@move2": RSymbol(moves.split(",")[1]) if len(
                moves.split(",")) > 1 else None,
            "@move3": RSymbol(moves.split(",")[2]) if len(
                moves.split(",")) > 2 else None,
            "@move4": RSymbol(moves.split(",")[3]) if len(
                moves.split(",")) > 3 else None,
        }
        out.append(obj)
    return out


def facility_attachments(game_root: str, family: str) -> List[str]:
    """battle_facility_lists.txt 里引用的 txt 文件（已存在的）。"""
    pbs = pbs_dir(game_root)
    spec = file_for("battle_facility_lists")
    index = os.path.join(pbs, txt_name(spec, family)) if spec else ""
    out = []
    if not index or not os.path.isfile(index):
        return out
    for sec in parse_sections(open(index, "rb").read().decode(
            "utf-8-sig", errors="replace")):
        for k, v in sec.fields:
            if k in ("Trainers", "Pokemon"):
                name = _unq(v)
                if name and os.path.isfile(os.path.join(pbs, name)):
                    out.append(name)
    return out


# ---------------------------------------------------------------------------
# 编辑器用的文档模型
# ---------------------------------------------------------------------------

class DocEntry:
    """一个段 / 一条记录。fields = [[key, 原始文本], ...]（保序，含未知键）。"""

    __slots__ = ("sid", "note", "fields", "data")

    def __init__(self, sid: str, note: str = ""):
        self.sid = sid
        self.note = note
        self.fields: List[List[str]] = []
        self.data: Dict[str, Any] = {}

    def get(self, key: str, default: str = "") -> str:
        for k, v in self.fields:
            if k == key:
                return v
        return default

    def set(self, key: str, value: str) -> None:
        for kv in self.fields:
            if kv[0] == key:
                kv[1] = value
                return
        self.fields.append([key, value])

    def label(self) -> str:
        """列表里显示的文字。"""
        if self.data.get("_label"):
            return self.data["_label"]
        for k, v in self.fields:
            if k in ("Name", "InternalName"):
                return v or self.sid
        return self.sid


class Doc:
    """一个 PBS 文件的在内存文档。"""

    def __init__(self, spec: Optional[dict], family: str, path: str):
        self.spec = spec
        self.family = family
        self.path = path
        self.key = spec["key"] if spec else ""
        self.name = spec["name"] if spec else os.path.basename(path)
        self.style = style_of(spec, family) if spec else "section"
        self.editor = spec.get("editor", "generic") if spec else "text"
        self.entries: List[DocEntry] = []
        self.dirty = False

    # ---- 读 ----
    @staticmethod
    def load(spec: Optional[dict], family: str, path: str) -> "Doc":
        doc = Doc(spec, family, path)
        text = ""
        try:
            text = open(path, "rb").read().decode("utf-8-sig",
                                                  errors="replace")
        except OSError:
            pass
        editor = doc.editor
        if editor == "trainers":
            doc._load_trainers(text)
        elif editor == "encounters":
            doc._load_encounters(text)
        elif editor == "townmap":
            doc._load_townmap(text)
        elif editor == "connections":
            doc._load_connections(text)
        elif editor == "regional":
            doc._load_regional(text)
        elif editor == "phone":
            doc._load_phone(text)
        elif doc.style == "line":
            doc._load_line(text)
        elif doc.style == "kv":
            doc._load_kv(text)
        else:
            doc._load_sections(text)
        return doc

    def _load_sections(self, text: str) -> None:
        for sec in parse_sections(text):
            e = DocEntry(sec.name, sec.comment)
            for k, v in sec.fields:
                e.fields.append([k, v])
            self.entries.append(e)

    def _load_line(self, text: str) -> None:
        schema = schema_of(self.spec, self.family)
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("﻿"):
                continue
            vals = split_csv(line)
            e = DocEntry(line[:40])
            for key, v in _split_line_values(schema, vals):
                e.fields.append([key, _unquote_csv(v)])
            name = e.get("Name") or e.get("InternalName")
            e.data["_label"] = "%s %s" % (e.get("IdNumber", "").rjust(4),
                                          name)
            self.entries.append(e)

    def _load_kv(self, text: str) -> None:
        order = self.spec.get("v19kv") or []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("﻿"):
                continue
            m = _KV_RE.match(line)
            if not m:
                continue
            vals = [x.strip() for x in split_csv(m.group(2))]
            e = DocEntry(m.group(1))
            for i, ivar in enumerate(order):
                e.fields.append([ivar, vals[i] if i < len(vals) else ""])
            self.entries.append(e)

    def _load_trainers(self, text: str) -> None:
        sub_schema = self.spec.get("sub_schema", {}).get(self.family) or []
        cur: Optional[DocEntry] = None
        cur_pkmn: Optional[dict] = None
        for raw in text.splitlines():
            line = raw.rstrip("\r")
            if not line.strip() or line.strip().startswith("#"):
                continue
            m = _SEC_RE.match(line)
            if m:
                cur = DocEntry(m.group(1))
                cur.data["pokemon"] = []
                self.entries.append(cur)
                cur_pkmn = None
                continue
            if cur is None:
                continue
            m = re.match(r"^(\s*)(\w+)\s*=\s*(.*?)\s*$", line)
            if not m:
                continue
            indent, key, value = len(m.group(1)), m.group(2), m.group(3)
            if key == "Pokemon" and not indent:
                vals = [x.strip() for x in split_csv(value)]
                cur_pkmn = {"species": vals[0] if vals else "",
                            "level": vals[1] if len(vals) > 1 else "1"}
                for k2, _i, _c, _e in sub_schema:
                    cur_pkmn.setdefault(k2, "")
                cur.data["pokemon"].append(cur_pkmn)
                continue
            if indent and cur_pkmn is not None:
                cur_pkmn[key] = value
                continue
            cur.fields.append([key, value])
        for e in self.entries:
            e.data["_label"] = e.sid

    def _load_encounters(self, text: str) -> None:
        cur: Optional[DocEntry] = None
        cur_type: Optional[str] = None
        for raw in text.splitlines():
            line = raw.rstrip("\r")
            if not line.strip() or line.strip().startswith("#"):
                continue
            m = _SEC_RE.match(line)
            if m:
                inside = m.group(1)
                if "#" in inside:
                    inside = inside.split("#", 1)[0].strip()
                parts = [p.strip() for p in inside.split(",")]
                cur = DocEntry(inside)
                cur.data["map"] = parts[0] if parts else "0"
                cur.data["version"] = parts[1] if len(parts) > 1 else "0"
                cur.data["types"] = []
                self.entries.append(cur)
                cur_type = None
                continue
            if cur is None:
                continue
            stripped = line.strip()
            if line.startswith("    ") or line.startswith("\t"):
                vals = [x.strip() for x in split_csv(stripped)]
                if len(vals) >= 3 and cur_type is not None:
                    for blk in cur.data["types"]:
                        if blk[0] == cur_type:
                            blk[2].append(vals)
                            break
                continue
            vals = [x.strip() for x in split_csv(stripped)]
            if vals and vals[0]:
                cur_type = vals[0]
                chance = vals[1] if len(vals) > 1 else ""
                cur.data["types"].append([cur_type, chance, []])

    def _load_townmap(self, text: str) -> None:
        for sec in parse_sections(text):
            e = DocEntry(sec.name)
            points = []
            for k, v in sec.fields:
                if k == "Point":
                    points.append(split_csv(v))
                else:
                    e.fields.append([k, v])
            e.data["points"] = points
            e.data["_label"] = "%s %s" % (e.sid, e.get("Name"))
            self.entries.append(e)

    def _load_connections(self, text: str) -> None:
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("﻿"):
                continue
            vals = split_csv(line)
            if len(vals) < 6:
                continue
            e = DocEntry(line[:30])
            for i, v in enumerate(vals[:6]):
                e.fields.append(["f%d" % i, v])
            e.data["_label"] = "地图 %s → %s" % (vals[0], vals[3])
            self.entries.append(e)

    def _load_regional(self, text: str) -> None:
        cur: Optional[DocEntry] = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("﻿"):
                continue
            m = _SEC_RE.match(line)
            if m:
                cur = DocEntry(m.group(1))
                cur.data["species"] = []
                self.entries.append(cur)
                continue
            if cur is None:
                continue
            for x in split_csv(line):
                x = x.strip()
                if x:
                    cur.data["species"].append(x)

    def _load_phone(self, text: str) -> None:
        if self.family == "v19":
            groups = {"Generics", "BattleRequests", "GreetingsMorning",
                      "GreetingsEvening", "Greetings", "Bodies1", "Bodies2"}
            for sec in parse_sections(text):
                label = sec.name.strip("<>")
                if label not in groups:
                    continue
                e = DocEntry(label)
                e.data["msgs"] = [v for _k, v in sec.fields]
                self.entries.append(e)
            return
        for sec in parse_sections(text):
            e = DocEntry(sec.name)
            msgs: Dict[str, List[str]] = {}
            for k, v in sec.fields:
                msgs.setdefault(k, []).append(v)
            e.data["msgs"] = msgs
            self.entries.append(e)

    # ---- 写 ----
    def to_text(self) -> str:
        editor = self.editor
        if editor == "trainers":
            return self._save_trainers()
        if editor == "encounters":
            return self._save_encounters()
        if editor == "townmap":
            return self._save_townmap()
        if editor == "connections":
            return self._save_connections()
        if editor == "regional":
            return self._save_regional()
        if editor == "phone":
            return self._save_phone()
        if self.style == "line":
            return self._save_line()
        if self.style == "kv":
            return self._save_kv()
        return self._save_sections()

    def _save_sections(self) -> str:
        lines = _file_header(self.spec)
        for e in self.entries:
            lines.append(_SEP)
            head = "[%s]" % e.sid
            if e.note:
                head += "   # %s" % e.note
            lines.append(head)
            for k, v in e.fields:
                lines.append("%s = %s" % (k, v))
        return _bom_text(lines)

    def _save_line(self) -> str:
        lines = _file_header(self.spec)
        schema = schema_of(self.spec, self.family)
        for e in self.entries:
            parts = []
            for key, ivar, ctype, enum in schema:
                v = e.get(key, "")
                if ctype == "q":
                    parts.append(csv_quote(v, always=True))
                else:
                    parts.append(v)
            lines.append(",".join(parts))
        return _bom_text(lines)

    def _save_kv(self) -> str:
        lines = _file_header(self.spec)
        for e in self.entries:
            vals = [v for _k, v in e.fields]
            lines.append("%s = %s" % (e.sid, ",".join(vals)))
        return _bom_text(lines)

    def _save_trainers(self) -> str:
        lines = _file_header(self.spec)
        for e in self.entries:
            lines.append(_SEP)
            lines.append("[%s]" % e.sid)
            for k, v in e.fields:
                lines.append("%s = %s" % (k, v))
            for p in e.data.get("pokemon", []):
                lines.append("Pokemon = %s,%s" % (p.get("species", ""),
                                                  p.get("level", "1")))
                for k2, v2 in p.items():
                    if k2 in ("species", "level") or v2 == "":
                        continue
                    lines.append("    %s = %s" % (k2, v2))
        return _bom_text(lines)

    def _save_encounters(self) -> str:
        lines = _file_header(self.spec)
        for e in self.entries:
            lines.append(_SEP)
            mnum = _int(e.data.get("map", "0"))
            mver = _int(e.data.get("version", "0"))
            head = "[%03d]" % mnum if mver <= 0 else "[%03d,%d]" % (mnum, mver)
            lines.append(head)
            for tname, chance, slots in e.data.get("types", []):
                lines.append("%s,%s" % (tname, chance) if chance else tname)
                for s in slots:
                    lines.append("    %s" % ",".join(s))
        return _bom_text(lines)

    def _save_townmap(self) -> str:
        lines = _file_header(self.spec)
        for e in self.entries:
            lines.append(_SEP)
            lines.append("[%s]" % e.sid)
            for k, v in e.fields:
                lines.append("%s = %s" % (k, v))
            for pt in e.data.get("points", []):
                lines.append("Point = %s" % ",".join(pt))
        return _bom_text(lines)

    def _save_connections(self) -> str:
        lines = _file_header(self.spec)
        for e in self.entries:
            lines.append(_SEP)
            lines.append(",".join(v for _k, v in e.fields[:6]))
        return _bom_text(lines)

    def _save_regional(self) -> str:
        lines = _file_header(self.spec)
        for e in self.entries:
            lines.append(_SEP)
            lines.append("[%s]" % e.sid)
            sp = e.data.get("species", [])
            for j in range(0, len(sp), 12):
                lines.append(",".join(sp[j:j + 12]))
        return _bom_text(lines)

    def _save_phone(self) -> str:
        lines = _file_header(self.spec)
        for e in self.entries:
            lines.append(_SEP)
            if self.family == "v19":
                lines.append("[<%s>]" % e.sid)
                for m in e.data.get("msgs", []):
                    lines.append(m)
            else:
                lines.append("[%s]" % e.sid)
                for k, msgs in e.data.get("msgs", {}).items():
                    for m in msgs:
                        lines.append("%s = %s" % (k, m))
        return _bom_text(lines)

    def save(self) -> None:
        # ★ 安全闸：原文件有内容、这份文档却一条都没解析出来 —— 说明类型认错了，
        #   直接写会把用户的文件清空。宁可不写。
        text = self.to_text()
        if not self.entries and os.path.isfile(self.path):
            try:
                raw = open(self.path, "rb").read()
            except OSError:
                raw = b""
            body = [ln for ln in raw.decode("utf-8-sig", errors="replace")
                    .splitlines()
                    if ln.strip() and not ln.lstrip().startswith("#")]
            if body and len(body) > 2:
                raise RuntimeError(
                    "这个文件解析出 0 条（格式没认对），为安全起见不覆盖原文件")
        with open(self.path, "wb") as f:
            f.write(text.encode("utf-8"))
        self.dirty = False


def load_doc(game_root: str, spec: Optional[dict], family: str,
             txt_path: Optional[str] = None) -> Doc:
    if txt_path is None:
        txt_path = os.path.join(pbs_dir(game_root),
                                txt_name(spec, family) if spec else "")
    return Doc.load(spec, family, txt_path)


def list_pbs_txt(game_root: str, family: str) -> List[dict]:
    """
    PBS 目录下的 txt 列表（左侧文件列表用）。

    ★ 只列 PBS编辑 开放的 4 类文件（宝可梦 / 形态 / 道具 / 招式），
      其余 txt 一律不显示。
    """
    pbs = pbs_dir(game_root)
    out: List[dict] = []
    if not os.path.isdir(pbs):
        return out
    by_name = {txt_name(s, family): s for s in list_specs(family)}
    for fn in sorted(os.listdir(pbs)):
        if not fn.lower().endswith(".txt"):
            continue
        spec = by_name.get(fn)
        if not spec:
            continue
        path = os.path.join(pbs, fn)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        out.append({
            "file": fn, "name": spec["name"], "desc": spec["desc"],
            "key": spec["key"], "path": path, "size": size,
        })
    return out




