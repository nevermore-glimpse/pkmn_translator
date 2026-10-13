# -*- coding: utf-8 -*-
r"""
最小可用游戏数据（mini data）——取代「空占位文件」。

## 为什么要它

开 ``$DEBUG`` 后 Essentials 的 ``Compiler.main`` 先判断要不要全量重编译：

    mustCompile |= (latestTextTime >= latestDataTime)

* ``latestTextTime`` = ``PBS/*.txt`` 里最大的 mtime
* ``latestDataTime`` = ``Data/*.dat`` 里最大的 mtime
* **任何一个「必需」.dat 不存在 → 直接 ``mustCompile = true``**

所以只要「文件齐 + .dat 恒新于 .txt」就不会触发编译。但编译被跳过后，
紧接着 ``GameData.load_all`` 会 ``Marshal.load`` 每一个 .dat ——
**空文件会在这一步直接炸掉**（Marshal 读 0 字节报 ``ArgumentError``）。

因此本模块不再写空文件，而是写**结构正确、内容最少**的真数据：
用 rubymarshal 生成 Ruby Marshal 字节，字段取 v19–v21.1 各版
``GameData::*#initialize`` 的**并集**（多出来的 ivar Ruby 不校验，
缺了的才有默认值兜底），所以同一份结构能同时喂饱 v19 / v19.1 / v20 /
v20.1 / v21 / v21.1。同时补一份最小可编译的 PBS，万一真触发了编译也不报错。

## 参照

* 数据类字段：``010_Data/002_PBS data/*.rb`` 的 ``initialize``
* 文件清单：``021_Compiler/001_Compiler.rb`` 的 ``dataFiles`` / ``textFiles``
  （v19、v20）与 ``GameData.get_all_data_filenames``（v21+）
* 目录形态：赤途那种「Data 一套完整的 .dat/.rxdata + PBS 一套 .txt」，
  且 Data 恒新于 PBS

依赖：rubymarshal、logger。
"""
import json
import os
import time

from rubymarshal.classes import RubyObject, Symbol
from rubymarshal.writer import writes

from logger import get_logger

log = get_logger("mini_data")

# 生成清单（清理时用）
MANIFEST = "_pkmn_mini_data.json"

# .dat 比 .txt 晚这么多秒（确保「不触发编译」）
_SKEW_SEC = 365 * 24 * 3600

FAMILIES = ("v19", "v20", "v21")


# ================================================================
# 小工具
# ================================================================
def _s(name):
    """Ruby Symbol。"""
    return Symbol(name)


def _o(cls, attrs):
    """Ruby 普通对象（Marshal 的 `o:`），attrs 直接就是 ivar 表。"""
    obj = RubyObject(cls)
    obj.attributes = attrs
    return obj


def _symlist(names):
    return [_s(n) for n in names]


_STAT_KEYS = ("HP", "ATTACK", "DEFENSE", "SPECIAL_ATTACK", "SPECIAL_DEFENSE",
              "SPEED")


def _stats(vals):
    return dict(zip([_s(k) for k in _STAT_KEYS], vals))


# ================================================================
# 数据内容
# ================================================================
# 19 种属性（含 QMARKS），顺序/图标位/特殊与否与官方 types.txt 一致
_TYPES = (
    # (ID, 名字, 图标位, 特殊?, 弱点, 抗性, 免疫)
    ("NORMAL", "Normal", 0, False, ["FIGHTING"], [],
     ["GHOST"]),
    ("FIGHTING", "Fighting", 1, False, ["FLYING", "PSYCHIC", "FAIRY"],
     ["ROCK", "BUG", "DARK"], []),
    ("FLYING", "Flying", 2, False, ["ROCK", "ELECTRIC", "ICE"],
     ["FIGHTING", "BUG", "GRASS"], ["GROUND"]),
    ("POISON", "Poison", 3, False, ["GROUND", "PSYCHIC"],
     ["FIGHTING", "POISON", "BUG", "GRASS", "FAIRY"], []),
    ("GROUND", "Ground", 4, False, ["WATER", "GRASS", "ICE"],
     ["POISON", "ROCK"], ["ELECTRIC"]),
    ("ROCK", "Rock", 5, False,
     ["FIGHTING", "GROUND", "STEEL", "WATER", "GRASS"],
     ["NORMAL", "FLYING", "POISON", "FIRE"], []),
    ("BUG", "Bug", 6, False, ["FLYING", "ROCK", "FIRE"],
     ["FIGHTING", "GROUND", "GRASS"], []),
    ("GHOST", "Ghost", 7, False, ["GHOST", "DARK"], ["POISON", "BUG"],
     ["NORMAL", "FIGHTING"]),
    ("STEEL", "Steel", 8, False, ["FIGHTING", "GROUND", "FIRE"],
     ["NORMAL", "FLYING", "ROCK", "BUG", "STEEL", "GRASS", "PSYCHIC", "ICE",
      "DRAGON", "FAIRY"], ["POISON"]),
    ("QMARKS", "???", 9, True, [], [], []),
    ("FIRE", "Fire", 10, True, ["GROUND", "ROCK", "WATER"],
     ["BUG", "STEEL", "FIRE", "GRASS", "ICE", "FAIRY"], []),
    ("WATER", "Water", 11, True, ["GRASS", "ELECTRIC"],
     ["STEEL", "FIRE", "WATER", "ICE"], []),
    ("GRASS", "Grass", 12, True,
     ["FLYING", "POISON", "BUG", "FIRE", "ICE"],
     ["GROUND", "WATER", "GRASS", "ELECTRIC"], []),
    ("ELECTRIC", "Electric", 13, True, ["GROUND"],
     ["FLYING", "STEEL", "ELECTRIC"], []),
    ("PSYCHIC", "Psychic", 14, True, ["BUG", "GHOST", "DARK"],
     ["FIGHTING", "PSYCHIC"], []),
    ("ICE", "Ice", 15, True, ["FIGHTING", "ROCK", "STEEL", "FIRE"],
     ["ICE"], []),
    ("DRAGON", "Dragon", 16, True, ["ICE", "DRAGON", "FAIRY"],
     ["FIRE", "WATER", "GRASS", "ELECTRIC"], []),
    ("DARK", "Dark", 17, False, ["FIGHTING", "BUG", "FAIRY"],
     ["GHOST", "DARK"], ["PSYCHIC"]),
    ("FAIRY", "Fairy", 18, True, ["POISON", "STEEL"],
     ["FIGHTING", "BUG", "DARK"], ["DRAGON"]),
)

# 两个招式 + 一个道具 + 两个特性 + 三段进化链 —— 够跑起来就行
_MOVES = (
    # (ID, 名字, 属性, 分类, 威力, 命中, PP)  分类 0=物理 2=变化
    ("TACKLE", "Tackle", "NORMAL", 0, 40, 100, 35),
    ("GROWL", "Growl", "NORMAL", 2, 0, 100, 40),
)
# 种族值一律按 HP,攻击,防御,特攻,特防,速度 的顺序写（= v20+ 的 PBS 顺序）；
# 生成 v19 的 PBS 时再换成它自己的 HP,攻,防,速,特攻,特防。
_SPECIES = (
    # (ID, 名字, 类型, 种族值, 特性, 隐藏特性, 进化)
    ("BULBASAUR", "Bulbasaur", ("GRASS", "POISON"),
     (45, 49, 49, 65, 65, 45), ["OVERGROW"], ["CHLOROPHYLL"],
     ("IVYSAUR", "Level", 16)),
    ("IVYSAUR", "Ivysaur", ("GRASS", "POISON"),
     (60, 62, 63, 80, 80, 60), ["OVERGROW"], ["CHLOROPHYLL"],
     ("VENUSAUR", "Level", 32)),
    ("VENUSAUR", "Venusaur", ("GRASS", "POISON"),
     (80, 82, 83, 100, 100, 80), ["OVERGROW"], ["CHLOROPHYLL"], None),
)


# ----------------------------------------------------------------
# 各 .dat 的内容
# ----------------------------------------------------------------
def _types(dual):
    out = {}
    for i, (tid, name, icon, special, weak, res, imm) in enumerate(_TYPES):
        o = _o("GameData::Type", {
            "@id": _s(tid),
            "@id_number": i,
            "@real_name": name,
            "@icon_position": icon,
            "@special_type": special,
            "@pseudo_type": False,
            "@weaknesses": _symlist(weak),
            "@resistances": _symlist(res),
            "@immunities": _symlist(imm),
            "@flags": [],
            "@pbs_file_suffix": "",
        })
        out[_s(tid)] = o
        if dual:
            out[i] = o
    return out


def _abilities(dual):
    src = (("OVERGROW", "Overgrow",
            "Powers up Grass-type moves when the Pokémon is in trouble."),
           ("CHLOROPHYLL", "Chlorophyll",
            "Boosts the Pokémon's Speed stat in harsh sunlight."))
    out = {}
    for i, (aid, name, desc) in enumerate(src):
        o = _o("GameData::Ability", {
            "@id": _s(aid),
            "@id_number": i,
            "@real_name": name,
            "@real_description": desc,
            "@flags": [],
            "@pbs_file_suffix": "",
        })
        out[_s(aid)] = o
        if dual:
            out[i] = o
    return out


def _moves(dual):
    out = {}
    for i, (mid, name, typ, cat, power, acc, pp) in enumerate(_MOVES):
        o = _o("GameData::Move", {
            "@id": _s(mid),
            "@id_number": i,
            "@real_name": name,
            "@type": _s(typ),
            "@category": cat,
            "@base_damage": power,      # v19 / v20 用这个
            "@power": power,            # v21 改名叫 power，两个都写
            "@accuracy": acc,
            "@total_pp": pp,
            "@target": _s("NearOther"),
            "@priority": 0,
            "@function_code": "None",
            "@flags": ["Contact", "CanProtect", "CanMirrorMove"],
            "@effect_chance": 0,
            "@real_description": "No description.",
            "@pbs_file_suffix": "",
        })
        out[_s(mid)] = o
        if dual:
            out[i] = o
    return out


def _items(dual):
    out = {}
    o = _o("GameData::Item", {
        "@id": _s("POTION"),
        "@id_number": 0,
        "@real_name": "Potion",
        "@real_name_plural": "Potions",
        "@real_portion_name": "sip of Potion",
        "@real_portion_name_plural": "sips of Potion",
        "@pocket": 1,
        "@price": 300,
        "@sell_price": 150,
        "@bp_price": 1,
        "@field_use": 1,
        "@battle_use": 1,
        "@type": 0,
        "@move": None,
        "@flags": [],
        "@consumable": True,
        "@show_quantity": True,
        "@real_description": "Restores 20 HP.",
        "@pbs_file_suffix": "",
    })
    out[_s("POTION")] = o
    if dual:
        out[0] = o
    return out


def _species(dual):
    out = {}
    moves = [[1, _s("TACKLE")], [1, _s("GROWL")]]
    for i, (sid, name, types, stats, abil, hidden, evo) in enumerate(_SPECIES):
        evolutions = []
        if evo:
            evolutions.append([_s(evo[0]), _s(evo[1]), evo[2], None])
        o = _o("GameData::Species", {
            "@id": _s(sid),
            "@id_number": i,
            "@species": _s(sid),
            "@form": 0,
            "@real_name": name,
            "@real_form_name": None,
            "@real_category": "Seed",
            "@real_pokedex_entry": "No Pokédex entry.",
            "@pokedex_form": 0,
            "@type1": _s(types[0]),          # v19
            "@type2": _s(types[1]),          # v19
            "@types": _symlist(types),       # v20+
            "@base_stats": _stats(stats),
            "@evs": {_s("SPECIAL_ATTACK"): 1},
            "@base_exp": 64,
            "@growth_rate": _s("Parabolic"),
            "@gender_ratio": _s("FemaleOneEighth"),
            "@catch_rate": 45,
            "@happiness": 50,
            "@moves": moves,
            "@tutor_moves": [],
            "@egg_moves": [],
            "@abilities": _symlist(abil),
            "@hidden_abilities": _symlist(hidden),
            "@wild_item_common": [],
            "@wild_item_uncommon": [],
            "@wild_item_rare": [],
            "@egg_groups": [_s("Monster"), _s("Grass")],
            "@hatch_steps": 5120,
            "@incense": None,
            "@offspring": [],
            "@evolutions": evolutions,
            "@height": 0.7,
            "@weight": 6.9,
            "@color": _s("Green"),
            "@shape": _s("Quadruped"),
            "@habitat": _s("Grassland"),
            "@generation": 1,
            "@flags": [],
            "@mega_stone": None,
            "@mega_move": None,
            "@unmega_form": 0,
            "@mega_message": 0,
            "@back_sprite_x": 0,
            "@back_sprite_y": 0,
            "@front_sprite_x": 0,
            "@front_sprite_y": 0,
            "@front_sprite_altitude": 0,
            "@shadow_x": 0,
            "@shadow_size": 2,
            "@pbs_file_suffix": "",
        })
        out[_s(sid)] = o
        if dual:
            out[i] = o
    return out


def _species_metrics():
    return {_s("BULBASAUR"): _o("GameData::SpeciesMetrics", {
        "@id": _s("BULBASAUR"),
        "@species": _s("BULBASAUR"),
        "@form": 0,
        "@back_sprite": [0, 0],
        "@front_sprite": [0, 0],
        "@front_sprite_altitude": 0,
        "@shadow_x": 0,
        "@shadow_size": 2,
        "@pbs_file_suffix": "",
    })}


def _berry_plants(dual):
    o = _o("GameData::BerryPlant", {
        "@id": _s("CHERIBERRY"),
        "@id_number": 0,
        "@hours_per_stage": 3,
        "@drying_per_hour": 15,
        "@yield": [2, 5],
        "@pbs_file_suffix": "",
    })
    out = {_s("CHERIBERRY"): o}
    if dual:
        out[0] = o
    return out


def _ribbons(dual):
    o = _o("GameData::Ribbon", {
        "@id": _s("HOENNCOOL"),
        "@id_number": 0,
        "@real_name": "Cool Ribbon",
        "@icon_position": 0,
        "@real_description": "A ribbon for a Cool Contest winner.",
        "@flags": [],
        "@pbs_file_suffix": "",
    })
    out = {_s("HOENNCOOL"): o}
    if dual:
        out[0] = o
    return out


def _trainer_types(dual):
    o = _o("GameData::TrainerType", {
        "@id": _s("POKEMONTRAINER_Red"),
        "@id_number": 0,
        "@real_name": "Pokémon Trainer",
        "@gender": 0,
        "@base_money": 60,
        "@skill_level": 60,
        "@skill_code": None,
        "@flags": [],
        "@intro_BGM": None,
        "@battle_BGM": None,
        "@victory_BGM": None,
        "@intro_ME": None,      # v19
        "@victory_ME": None,    # v19
        "@pbs_file_suffix": "",
    })
    out = {_s("POKEMONTRAINER_Red"): o}
    if dual:
        out[0] = o
    return out


def _trainers(dual):
    o = _o("GameData::Trainer", {
        "@id": _s("POKEMONTRAINER_Red"),
        "@id_number": 0,
        "@trainer_type": _s("POKEMONTRAINER_Red"),
        "@real_name": "Red",
        "@version": 0,
        "@items": [],
        "@real_lose_text": "...",
        "@pokemon": [{_s("species"): _s("BULBASAUR"), _s("level"): 5}],
        "@pbs_file_suffix": "",
    })
    out = {_s("POKEMONTRAINER_Red"): o}
    if dual:
        out[0] = o
    return out


def _metadata():
    """metadata.dat：只有第 0 段（全局）；玩家段放 player_metadata.dat。"""
    return {0: _o("GameData::Metadata", {
        "@id": 0,
        "@start_money": 3000,
        "@start_item_storage": [],
        "@home": [1, 1, 1, 8],
        "@real_storage_creator": "Bill",
        "@wild_battle_BGM": None,
        "@trainer_battle_BGM": None,
        "@wild_victory_BGM": None,
        "@wild_victory_ME": None,
        "@trainer_victory_BGM": None,
        "@trainer_victory_ME": None,
        "@wild_capture_ME": None,
        "@surf_BGM": None,
        "@bicycle_BGM": None,
        "@player_A": None,
        "@player_B": None,
        "@player_C": None,
        "@player_D": None,
        "@player_E": None,
        "@player_F": None,
        "@player_G": None,
        "@player_H": None,
        "@pbs_file_suffix": "",
    })}


def _player_metadata():
    return {1: _o("GameData::PlayerMetadata", {
        "@id": 1,
        "@trainer_type": _s("POKEMONTRAINER_Red"),
        "@walk_charset": "trainer_POKEMONTRAINER_Red",
        "@run_charset": "boy_run",
        "@cycle_charset": "boy_bike",
        "@surf_charset": "boy_surf",
        "@dive_charset": "boy_surf",
        "@fish_charset": "boy_fish_offset",
        "@surf_fish_charset": "boy_surf_fish_offset",
        "@home": None,
        "@pbs_file_suffix": "",
    })}


def _map_metadata():
    return {1: _o("GameData::MapMetadata", {
        "@id": 1,
        "@real_name": "Map 1",
        "@outdoor_map": None,
        "@announce_location": None,
        "@can_bicycle": None,
        "@always_bicycle": None,
        "@teleport_destination": None,
        "@weather": None,
        "@town_map_position": None,
        "@dive_map_id": None,
        "@dark_map": None,
        "@safari_map": None,
        "@snap_edges": None,
        "@still_reflections": None,
        "@random_dungeon": None,
        "@battle_background": None,
        "@wild_battle_BGM": None,
        "@trainer_battle_BGM": None,
        "@wild_victory_BGM": None,
        "@trainer_victory_BGM": None,
        "@wild_capture_ME": None,
        "@town_map_size": None,
        "@battle_environment": None,
        "@flags": [],
        "@pbs_file_suffix": "",
    })}


def _encounters(family):
    """v19 的 Encounter.each 要按 id_number 排序，空表最安全；v20+ 放一条空的。"""
    if family == "v19":
        return {}
    return {_s("1_0"): _o("GameData::Encounter", {
        "@id": _s("1_0"),
        "@map": 1,
        "@version": 0,
        "@step_chances": {},
        "@types": {},
        "@pbs_file_suffix": "",
    })}


def _town_map(family):
    """v19/v20 是「区域数组」；v21 起才是 GameData::TownMap。"""
    if family == "v21":
        return {0: _o("GameData::TownMap", {
            "@id": 0,
            "@real_name": "Region",
            "@filename": "mapRegion0.png",
            "@point": [],
            "@flags": [],
            "@pbs_file_suffix": "",
        })}
    return [[None, "mapRegion0.png", []]]


def _phone(family):
    """v19/v20 是 PhoneDatabase 对象；v21 起是 GameData::PhoneMessage 表。"""
    if family == "v21":
        return {}
    return _o("PhoneDatabase", {
        "@generics": [],
        "@greetings": [],
        "@greetingsMorning": [],
        "@greetingsEvening": [],
        "@bodies1": [],
        "@bodies2": [],
        "@battleRequests": [],
        "@trainers": [],
    })


# ----------------------------------------------------------------
# 每个 .dat 怎么造：{文件名: 造内容的函数}（参数 family）
# ----------------------------------------------------------------
def _dat_builders(family):
    dual = (family == "v19")     # v19 的 ClassMethods 要把 id_number 也当键
    return {
        "abilities.dat": lambda: _abilities(dual),
        "berry_plants.dat": lambda: _berry_plants(dual),
        "dungeon_parameters.dat": lambda: {},
        "dungeon_tilesets.dat": lambda: {},
        "encounters.dat": lambda: _encounters(family),
        "form2species.dat": lambda: {},
        "items.dat": lambda: _items(dual),
        "map_connections.dat": lambda: [],
        "map_metadata.dat": _map_metadata,
        "metadata.dat": _metadata,
        "move2anim.dat": lambda: [[], []],
        "moves.dat": lambda: _moves(dual),
        "phone.dat": lambda: _phone(family),
        "player_metadata.dat": _player_metadata,
        "regional_dexes.dat": lambda: [],
        "ribbons.dat": lambda: _ribbons(dual),
        "shadow_movesets.dat": lambda: {},
        "shadow_pokemon.dat": lambda: {},
        "species.dat": lambda: _species(dual),
        "species_eggmoves.dat": lambda: {},
        "species_evolutions.dat": lambda: {},
        "species_metrics.dat": _species_metrics,
        "species_movesets.dat": lambda: {},
        "tm.dat": lambda: [],
        "town_map.dat": lambda: _town_map(family),
        "trainer_lists.dat": lambda: [],
        "trainer_types.dat": lambda: _trainer_types(dual),
        "trainers.dat": lambda: _trainers(dual),
        "types.dat": lambda: _types(dual),
    }


# RMXP 自家那几个「数组型」rxdata（第 0 位是 nil，RMXP 的老规矩）
_RXDATA_EMPTY = (
    "Actors.rxdata", "Animations.rxdata", "Armors.rxdata", "Classes.rxdata",
    "CommonEvents.rxdata", "Enemies.rxdata", "Items.rxdata", "MapInfos.rxdata",
    "PkmnAnimations.rxdata", "Skills.rxdata", "States.rxdata",
    "Tilesets.rxdata", "Troops.rxdata", "Weapons.rxdata",
)


# ================================================================
# PBS（最小可编译）
# ================================================================
# v19 / v19.1 还停在「一行一条 CSV」的老格式（moves / items / abilities /
# berryplants / trainertypes / ribbons / shadowmoves 都是），v20 起才全换成
# [段] + Key = Value。两种都照官方样本写 —— 万一真触发全量编译也不至于解析报错。
_BOM = "\ufeff"
_HDR = "# 由 pkmn_translator 生成的最小数据（只为让编译器 / 游戏跑通）\n" \
       "#-------------------------------\n"


def _sec(name):
    return "[%s]\n" % name


def _tail():
    return "#-------------------------------\n"


def _pbs_types(family):
    out = [_BOM, _HDR]
    for i, (tid, name, icon, special, weak, res, imm) in enumerate(_TYPES):
        out.append(_sec(i if family == "v19" else tid))
        out.append("Name = %s\n" % name)
        if family == "v19":
            out.append("InternalName = %s\n" % tid)
        else:
            out.append("IconPosition = %d\n" % icon)
        if special:
            out.append("IsSpecialType = true\n")
        if weak:
            out.append("Weaknesses = %s\n" % ",".join(weak))
        if res:
            out.append("Resistances = %s\n" % ",".join(res))
        if imm:
            out.append("Immunities = %s\n" % ",".join(imm))
        out.append(_tail())
    return "".join(out)


def _pbs_abilities(family):
    src = (("OVERGROW", "Overgrow", "Powers up Grass-type moves in a pinch."),
           ("CHLOROPHYLL", "Chlorophyll", "Boosts Speed in harsh sunlight."))
    out = [_BOM, _HDR]
    if family == "v19":
        for i, (aid, name, desc) in enumerate(src):
            # v19 的 CSV 第一列从 1 开始数（0 会被当成空条目丢掉）
            out.append('%d,%s,%s,"%s"\n' % (i + 1, aid, name, desc))
    else:
        for aid, name, desc in src:
            out.append(_sec(aid))
            out.append("Name = %s\n" % name)
            out.append("Description = %s\n" % desc)
            out.append(_tail())
    return "".join(out)


def _pbs_moves(family):
    out = [_BOM, _HDR]
    for i, (mid, name, typ, cat, power, acc, pp) in enumerate(_MOVES):
        kind = "Physical" if cat == 0 else "Status"
        if family == "v19":
            # 序号,ID,名字,函数码(16 进制),威力,属性,分类,命中,PP,追加效果,
            # 目标,优先度,标记,描述（序号从 1 开始）
            out.append('%d,%s,%s,000,%d,%s,%s,%d,%d,0,NearOther,0,abef,'
                       '"No description."\n'
                       % (i + 1, mid, name, power, typ, kind, acc, pp))
        else:
            out.append(_sec(mid))
            out.append("Name = %s\n" % name)
            out.append("Type = %s\n" % typ)
            out.append("Category = %s\n" % kind)
            # v20 叫 BaseDamage，v21 起改叫 Power
            out.append("%s = %d\n" % ("Power" if family == "v21"
                                      else "BaseDamage", power))
            out.append("Accuracy = %d\n" % acc)
            out.append("TotalPP = %d\n" % pp)
            out.append("Target = NearOther\n")
            out.append("FunctionCode = None\n")
            out.append("Flags = Contact,CanProtect,CanMirrorMove\n")
            out.append("Description = No description.\n")
            out.append(_tail())
    return "".join(out)


def _pbs_items(family):
    desc = "Restores 20 HP."
    out = [_BOM, _HDR]
    if family == "v19":
        # 序号,ID,单数名,复数名,口袋,价格,描述,场上用,战斗用,类型,招式
        out.append('1,POTION,Potion,Potions,1,300,"%s",1,1,0,\n' % desc)
    else:
        out.append(_sec("POTION"))
        out.append("Name = Potion\n")
        out.append("NamePlural = Potions\n")
        out.append("Pocket = 1\n")
        out.append("Price = 300\n")
        out.append("FieldUse = Direct\n")
        out.append("BattleUse = Direct\n")
        out.append("Flags = Consumable\n")
        out.append("Description = %s\n" % desc)
        out.append(_tail())
    return "".join(out)


def _pbs_berry_plants(family):
    out = [_BOM, _HDR]
    if family == "v19":
        out.append("CHERIBERRY = 3,15,2,5\n")
    else:
        out.append(_sec("CHERIBERRY"))
        out.append("HoursPerStage = 3\n")
        out.append("DryingPerHour = 15\n")
        out.append("Yield = 2,5\n")
        out.append(_tail())
    return "".join(out)


def _pbs_ribbons(family):
    desc = "A ribbon for a Cool Contest winner."
    out = [_BOM, _HDR]
    if family == "v19":
        out.append('1,HOENNCOOL,Cool Ribbon,"%s"\n' % desc)
    else:
        out.append(_sec("HOENNCOOL"))
        out.append("Name = Cool Ribbon\n")
        out.append("IconPosition = 0\n")
        out.append("Description = %s\n" % desc)
        out.append(_tail())
    return "".join(out)


def _pbs_trainer_types(family):
    out = [_BOM, _HDR]
    if family == "v19":
        # 序号,ID,名字,基础奖金,战斗BGM,胜利ME,登场ME,性别,技能等级,技能代码
        out.append("0,POKEMONTRAINER_Red,Pokémon Trainer,60,,,,Male,,\n")
    else:
        out.append(_sec("POKEMONTRAINER_Red"))
        out.append("Name = Pokémon Trainer\n")
        out.append("Gender = Male\n")
        out.append("BaseMoney = 60\n")
        out.append(_tail())
    return "".join(out)


def _pbs_trainers(family):
    out = [_BOM, _HDR]
    out.append("[POKEMONTRAINER_Red,Red]\n")
    # v19 的 LoseText 是带引号的
    out.append('LoseText = "..."\n' if family == "v19"
               else "LoseText = ...\n")
    out.append("Pokemon = BULBASAUR,5\n")
    out.append(_tail())
    return "".join(out)


def _pbs_species(family):
    """pokemon.txt（v21 另有 pokemon_forms.txt / pokemon_metrics.txt）。"""
    out = [_BOM, _HDR]
    for i, (sid, name, types, stats, abil, hidden, evo) in enumerate(_SPECIES):
        out.append(_sec(i + 1 if family == "v19" else sid))
        out.append("Name = %s\n" % name)
        if family == "v19":
            out.append("InternalName = %s\n" % sid)
            out.append("Type1 = %s\n" % types[0])
            out.append("Type2 = %s\n" % types[1])
            # v19 的种族值顺序是 HP,攻,防,速,特攻,特防
            out.append("BaseStats = %s\n"
                       % ",".join(str(x) for x in
                                  (stats[0], stats[1], stats[2], stats[5],
                                   stats[3], stats[4])))
            out.append("GenderRate = FemaleOneEighth\n")
            out.append("BaseEXP = 64\n")
            out.append("EffortPoints = 0,0,0,0,1,0\n")
            out.append("Rareness = 45\n")
            out.append("Happiness = 70\n")
            out.append("Compatibility = Monster,Grass\n")
            out.append("StepsToHatch = 5120\n")
            out.append("Kind = Seed\n")
            out.append("BattlerPlayerX = 0\n")
            out.append("BattlerPlayerY = 0\n")
            out.append("BattlerEnemyX = 0\n")
            out.append("BattlerEnemyY = 0\n")
            out.append("BattlerShadowX = 0\n")
            out.append("BattlerShadowSize = 2\n")
        else:
            out.append("Types = %s\n" % ",".join(types))
            out.append("BaseStats = %s\n" % ",".join(str(x) for x in stats))
            out.append("GenderRatio = FemaleOneEighth\n")
            out.append("BaseExp = 64\n")
            out.append("EVs = SPECIAL_ATTACK,1\n")
            out.append("CatchRate = 45\n")
            out.append("Happiness = 50\n")
            out.append("EggGroups = Monster,Grass\n")
            out.append("HatchSteps = 5120\n")
            out.append("Category = Seed\n")
        out.append("GrowthRate = Parabolic\n")
        out.append("Abilities = %s\n" % ",".join(abil))
        out.append("HiddenAbilities = %s\n" % ",".join(hidden))
        out.append("Moves = 1,TACKLE,1,GROWL\n")
        out.append("EggMoves =\n")
        out.append("Height = 0.7\n")
        out.append("Weight = 6.9\n")
        out.append("Color = Green\n")
        out.append("Shape = Quadruped\n")
        out.append("Habitat = Grassland\n")
        out.append("Pokedex = No Pokedex entry.\n")
        out.append("Generation = 1\n")
        if evo:
            out.append("Evolutions = %s,%s,%d\n" % evo)
        out.append(_tail())
    return "".join(out)


def _pbs_metadata(family):
    out = [_BOM, _HDR]
    out.append(_sec(0))
    out.append("StartMoney = 3000\n")
    out.append("Home = 1,1,1,8\n")
    if family == "v19":
        # v19 的玩家形象写在第 0 段的 PlayerA 里（必填项）
        out.append("PlayerA = trainer_POKEMONTRAINER_Red,boy_run,boy_bike,"
                   "boy_surf,boy_surf,boy_fish_offset\n")
    else:
        out.append(_tail())
        out.append(_sec(1))
        out.append("TrainerType = POKEMONTRAINER_Red\n")
        out.append("WalkCharset = trainer_POKEMONTRAINER_Red\n")
        out.append("RunCharset = boy_run\n")
        out.append("CycleCharset = boy_bike\n")
        out.append("SurfCharset = boy_surf\n")
        out.append("DiveCharset = boy_surf\n")
        out.append("FishCharset = boy_fish_offset\n")
    out.append(_tail())
    return "".join(out)


def _pbs_map_metadata():
    return "".join([_BOM, _HDR, _sec(1), "Name = Map 1\n", _tail()])


def _pbs_town_map():
    return "".join([_BOM, _HDR, _sec(0), "Name = Region\n",
                    "Filename = mapRegion0.png\n", _tail()])


def _pbs_phone(family):
    out = [_BOM, _HDR]
    if family == "v19":
        out.append("[<Generics>]\n")
        out.append("How are your Pokémon doing?\n")
        out.append(_tail())
        out.append("[<BattleRequests>]\n")
        out.append("Want to battle?\n")
    else:
        out.append(_sec("Default"))
        out.append("Intro = Hello.\n")
        out.append("Body = How are you doing?\n")
        out.append("BattleRequest = Want to battle?\n")
    out.append(_tail())
    return "".join(out)


def _pbs_connections():
    return "".join([_BOM, _HDR, "# 没有地图连接（本工具生成的）\n"])


def _pbs_regional_dexes():
    return "".join([_BOM, _HDR, _sec(0), "BULBASAUR,IVYSAUR,VENUSAUR\n",
                    _tail()])


def _pbs_dungeon_parameters():
    return "".join([_BOM, _HDR, _sec("cave"), "DungeonSize = 5,4\n",
                    "CellSize = 10,10\n", "MinRoomSize = 5,5\n",
                    "MaxRoomSize = 9,9\n", "CorridorWidth = 2\n", _tail()])


def _pbs_dungeon_tilesets():
    return "".join([_BOM, _HDR, _sec(1), "Tile = 0,walls\n",
                    "Tile = 42,floor\n", _tail()])


def _pbs_empty():
    return "".join([_BOM, _HDR])


def _pbs_files(family):
    """{PBS 文件名: 生成内容的函数}。"""
    d = {
        "abilities.txt": lambda: _pbs_abilities(family),
        "berry_plants.txt": lambda: _pbs_berry_plants(family),
        "berryplants.txt": lambda: _pbs_berry_plants(family),
        "connections.txt": _pbs_connections,
        "dungeon_parameters.txt": _pbs_dungeon_parameters,
        "dungeon_tilesets.txt": _pbs_dungeon_tilesets,
        "encounters.txt": _pbs_empty,
        "items.txt": lambda: _pbs_items(family),
        "map_connections.txt": _pbs_connections,
        "map_metadata.txt": _pbs_map_metadata,
        "metadata.txt": lambda: _pbs_metadata(family),
        "moves.txt": lambda: _pbs_moves(family),
        "phone.txt": lambda: _pbs_phone(family),
        "pokemon.txt": lambda: _pbs_species(family),
        "pokemon_forms.txt": _pbs_empty,
        "pokemon_metrics.txt": _pbs_empty,
        "pokemonforms.txt": _pbs_empty,
        "regional_dexes.txt": _pbs_regional_dexes,
        "regionaldexes.txt": _pbs_regional_dexes,
        "ribbons.txt": lambda: _pbs_ribbons(family),
        "shadow_pokemon.txt": _pbs_empty,
        "town_map.txt": _pbs_town_map,
        "townmap.txt": _pbs_town_map,
        "trainer_lists.txt": _pbs_empty,
        "trainerlists.txt": _pbs_empty,
        "trainer_types.txt": lambda: _pbs_trainer_types(family),
        "trainertypes.txt": lambda: _pbs_trainer_types(family),
        "trainers.txt": lambda: _pbs_trainers(family),
        "types.txt": lambda: _pbs_types(family),
    }
    if family == "v19":
        d["shadowmoves.txt"] = _pbs_empty
    return d


# ================================================================
# 版本判定
# ================================================================
def family_of(version, game_dir=None):
    """
    把版本号归到 v19 / v20 / v21 三档；认不出来时按目录里已有的 .dat 猜，
    再不行就按 v21（当前最常见）。
    """
    v = (version or "").strip()
    if v.startswith("19"):
        return "v19"
    if v.startswith("20"):
        return "v20"
    if v.startswith("21"):
        return "v21"
    if v[:2] in ("16", "17", "18"):
        return "legacy"
    # ① 先看 Data 目录里已有什么（最省事，也不读脚本）
    d = os.path.join(game_dir or "", "Data")
    try:
        names = set(n.lower() for n in os.listdir(d))
    except OSError:
        names = set()
    if "dungeon_parameters.dat" in names or "dungeon_tilesets.dat" in names:
        return "v21"
    if "player_metadata.dat" in names or "species_metrics.dat" in names:
        return "v20"
    if "tm.dat" in names or "dexdata.dat" in names or \
            "species_movesets.dat" in names or "attacksrs.dat" in names:
        return "v19"
    # ② 再读脚本里的版本号（Data 齐全时用得上）
    if game_dir:
        try:
            import essentials_base as EB
            v = EB.detect_version(game_dir) or ""
        except Exception:            # noqa: BLE001
            v = ""
        if v.startswith("19"):
            return "v19"
        if v.startswith("20"):
            return "v20"
        if v.startswith("21"):
            return "v21"
        if v[:2] in ("16", "17", "18"):
            return "legacy"
    return "v21"      # 认不出就按最新那档（写多不写少，多出来的文件没人读）


def _pbs_dir(game_dir):
    """PBS 目录：已有的优先（大小写都算），没有就建 `pbs`。"""
    for n in ("PBS", "pbs"):
        p = os.path.join(game_dir, n)
        if os.path.isdir(p):
            return p
    return os.path.join(game_dir, "pbs")


# ================================================================
# 主入口
# ================================================================
def ensure_minimal_data(game_dir, version=None, say=None):
    r"""
    补齐 `Data/` 与 `pbs/`：缺的文件写成**最小可用数据**，已有一律不动。

    · `.dat` / `.rxdata`：Ruby Marshal（rubymarshal 生成），结构照各版本
      ``GameData::*`` 的字段并集来写；
    · `.txt`：最小可编译的 PBS（真触发编译也不会报错）；
    · mtime：`.txt` 定在 2000-01-01，`.dat` 取「现有最新 .txt + 1 天」
      （至少 2001），保证 `latestDataTime > latestTextTime` → 跳过全量编译。

    返回统计 dict。
    """
    res = {"family": "", "dat_new": 0, "txt_new": 0, "rx_new": 0,
           "dat_fixed": 0, "created_dir": False}
    if not game_dir or not os.path.isdir(game_dir):
        return res

    def emit(msg):
        if say:
            say(msg)

    family = family_of(version, game_dir)
    res["family"] = family

    data_dir = os.path.join(game_dir, "Data")
    if not os.path.isdir(data_dir):
        try:
            os.makedirs(data_dir, exist_ok=True)
            res["created_dir"] = True
        except OSError as e:
            emit("[启动器] ⚠ 建 Data 目录失败：%s" % e)
            return res
    pbs_dir = _pbs_dir(game_dir)
    if not os.path.isdir(pbs_dir):
        try:
            os.makedirs(pbs_dir, exist_ok=True)
            res["created_dir"] = True
        except OSError as e:
            emit("[启动器] ⚠ 建 PBS 目录失败：%s" % e)

    # 时间基准
    t_txt = time.mktime((2000, 1, 1, 0, 0, 0, 0, 0, -1))
    latest_txt = t_txt
    for nm in os.listdir(pbs_dir):
        if nm.lower().endswith(".txt"):
            try:
                latest_txt = max(latest_txt,
                                 os.path.getmtime(os.path.join(pbs_dir, nm)))
            except OSError:
                pass
    t_dat = max(t_txt + _SKEW_SEC, latest_txt + 24 * 3600)

    made = []
    legacy = (family == "legacy")

    # ---- PBS ----
    if os.path.isdir(pbs_dir):
        for nm, fn in sorted(_pbs_files(family).items()):
            p = os.path.join(pbs_dir, nm)
            if os.path.isfile(p):
                continue
            try:
                with open(p, "wb") as f:
                    f.write(fn().encode("utf-8"))
                os.utime(p, (t_txt, t_txt))
                res["txt_new"] += 1
                made.append(os.path.join(os.path.basename(pbs_dir), nm))
            except OSError:
                pass

    # ---- Data/*.dat ----
    builders = _dat_builders(family)
    for nm, fn in sorted(builders.items()):
        p = os.path.join(data_dir, nm)
        if os.path.isfile(p):
            # 兜底：把「比 .txt 旧」的空 .dat 提到基准时间
            try:
                if os.path.getsize(p) == 0 and os.path.getmtime(p) < t_dat:
                    os.utime(p, (t_dat, t_dat))
                    res["dat_fixed"] += 1
            except OSError:
                pass
            continue
        try:
            content = fn()
            if legacy:
                # v16–v18 的 .dat 是另一套格式，不敢伪造：只写合法的空容器
                content = {} if nm in ("form2species.dat", "tm.dat") else []
            with open(p, "wb") as f:
                f.write(writes(content))
            os.utime(p, (t_dat, t_dat))
            res["dat_new"] += 1
            made.append(os.path.join("Data", nm))
        except Exception as e:      # noqa: BLE001
            log.debug("生成 %s 失败：%s", nm, e)

    # ---- Data/*.rxdata（RMXP 数组型的那几个）----
    for nm in _RXDATA_EMPTY:
        p = os.path.join(data_dir, nm)
        if os.path.isfile(p):
            continue
        try:
            with open(p, "wb") as f:
                f.write(writes([None]))
            os.utime(p, (t_dat, t_dat))
            res["rx_new"] += 1
            made.append(os.path.join("Data", nm))
        except Exception:          # noqa: BLE001
            pass

    # 生成清单（清理用）
    if made:
        _write_manifest(game_dir, made)
        emit("[启动器] ✔ 补齐最小数据：Data 新建 %d（含 rxdata %d）、"
             "PBS 新建 %d  ——已写入真数据（非占位），重编译检查会被跳过"
             % (res["dat_new"] + res["rx_new"], res["rx_new"],
                res["txt_new"]))
    elif res["dat_fixed"]:
        emit("[启动器] · 已把 %d 个空 .dat 的时间提到安全值" % res["dat_fixed"])
    return res


def _write_manifest(game_dir, made):
    p = os.path.join(game_dir, MANIFEST)
    try:
        old = []
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                old = json.load(f).get("files", [])
        allf = sorted(set(old) | set(made))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"files": allf}, f, ensure_ascii=False, indent=1)
    except Exception:              # noqa: BLE001
        pass


def cleanup_minimal_data(game_dir):
    """删掉本模块生成过的文件（只删清单里记下的那些）。返回删除数。"""
    p = os.path.join(game_dir, MANIFEST)
    files = []
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                files = json.load(f).get("files", [])
        except Exception:           # noqa: BLE001
            files = []
    n = 0
    for rel in files:
        try:
            fp = os.path.join(game_dir, rel)
            if os.path.isfile(fp):
                os.remove(fp)
                n += 1
        except OSError:
            pass
    try:
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass
    # 顺手清掉上一版留下的空占位
    try:
        import launcher
        n += launcher.cleanup_placeholders(game_dir)
    except Exception:               # noqa: BLE001
        pass
    return n
