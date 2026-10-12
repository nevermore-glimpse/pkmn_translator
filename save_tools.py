# -*- coding: utf-8 -*-
"""
save_tools —— Pokémon Essentials 存档读取 / 解码 / 写回。

给「存档修改」菜单打底：先能把 savestateN.rxdata 里的东西**完整、可读地**
摊开来（宝可梦 / 背包 / 主角 / 图鉴 / 开关变量 …），后续再在这个对象上做修改
并原样写回。

## 存档的样子

一份存档不是「一个 Marshal 对象」，而是**多个 Marshal 流首尾相接**——
Essentials 的 ``pbSave`` 逐个 ``Marshal.dump`` 全局变量：

    #0  PokeBattle_Trainer       $Trainer          主角 + 同行队伍
    #1  Integer                  Graphics.frame_count
    #2  Game_System              $game_system      系统设定
    #3  PokemonSystem            $PokemonSystem    游戏选项
    #4  Integer                  $game_map.map_id  (shallow dump?)
    #5  Game_Switches            $game_switches    开关
    #6  Game_Variables           $game_variables   变量
    #7  Game_SelfSwitches        $game_self_switches 独立开关
    #8  Game_Screen              $game_screen      画面/天气
    #9  PokemonMapFactory        $MapFactory       地图链
    #10 Game_Player              $game_player      主角位置
    #11 PokemonGlobalMetadata    $PokemonGlobal    全局数据（时间/位置/记录…）
    #12 PokemonMapMetadata       当前地图事件状态
    #13 PokemonBag               $PokemonBag       背包
    #14 PokemonStorage           $PokemonStorage   电脑箱子

## 用法

    import save_tools as ST
    sv = ST.open_save(r".../Data/Savestates/savestate1.rxdata",
                      game_root=r".../游戏根目录")
    sv.set_trainer(money=999999)               # 改字段
    sv.write()                                 # 原样写回（未改动则字节完全一致）

依赖：rmarshal（本项目自研，纯标准库）、os、re、zlib。
数据名称（宝可梦/道具/招式名）取自游戏自己的 Data/*.dat、PBS 目录与
Scripts.rxdata。
"""

from __future__ import annotations

import os
import re
import time
import zlib
from typing import Any, Dict, List, Optional, Tuple

import rmarshal


# ---------------------------------------------------------------------------
# 常量表
# ---------------------------------------------------------------------------
# Essentials v16 的 PBStatuses
STATUS_NAMES = {0: "正常", 1: "睡眠", 2: "中毒", 3: "灼伤",
                4: "冰冻", 5: "麻痹", 6: "濒死"}

# 25 种性格（index = @natureflag）；索引用法见 NatBoost()
NATURES = [
    "勤奋", "怕寂寞", "勇敢", "固执", "调皮",
    "大胆", "坦率", "悠闲", "淘气", "乐天",
    "胆小", "急躁", "认真", "爽朗", "天真",
    "内敛", "慢吞吞", "冷静", "害羞", "马虎",
    "温顺", "温和", "狂妄", "慎重", "浮躁",
]

NATURES_EN = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]

# IV/EV 与能力值的顺序：[HP, 攻击, 防御, 速度, 特攻, 特防]
STAT_KEYS = ["HP", "攻击", "防御", "速度", "特攻", "特防"]
STAT_IVARS = ["@totalhp", "@attack", "@defense", "@speed", "@spatk", "@spdef"]

# 性别率阈值（PB Species GenderRate）
GENDER_THRESHOLD = {
    "AlwaysMale": None, "AlwaysFemale": None, "Genderless": None,
    "FemaleOneEighth": 30, "Female25Percent": 63,
    "Female50Percent": 126, "Female75Percent": 190,
}

DEFAULT_POCKETS = ["", "物品", "药品", "精灵球", "技能机/秘传机",
                   "树果", "书籍/其他", "战斗道具", "关键道具"]

# Essentials 官方属性内部名顺序（PBTypes::NORMAL = 0 …）。
# ★ 只在「.dat 没给内部名」且总数对得上（18/19 个）时用来把 PBS 里的
#   Type1=GHOST 这种内部名换算成显示名；改过属性顺序的作品会换不准，
#   那种情况靠 Data/types.dat 的 @id（v19+）来定位。
ESSENTIALS_TYPE_ORDER = [
    "NORMAL", "FIGHTING", "FLYING", "POISON", "GROUND", "ROCK", "BUG",
    "GHOST", "STEEL", "QMARKS", "FIRE", "WATER", "GRASS", "ELECTRIC",
    "PSYCHIC", "ICE", "DRAGON", "DARK", "FAIRY",
]


# ---------------------------------------------------------------------------
# 游戏资料库（PBS + 脚本常量）
# ---------------------------------------------------------------------------
class GameData:
    """
    从游戏目录读取名对照表。读不到不报错，退化成「#编号」。

    ★ 数据来源有两条，**优先编译好的 .dat**，PBS 只做兜底：

      ① ``Data/*.dat``（v19+ 的 ``GameData::Species`` / ``Move`` / ``Item`` /
         ``Ability`` / ``Type`` / ``TrainerType`` 对象；v17/v18 的数组式
         ``pokemon.dat`` / ``moves.dat`` …）
         —— 汉化版游戏常把 PBS 删掉只留 .dat，只认 PBS 会一个字都读不出来。
      ② ``PBS/*.txt``（v16 及保留 PBS 的游戏）

    归一化后统一用 PBS 的字段名（Name / BaseStats / GrowthRate / Abilities /
    GenderRate / Types / HatchSteps），好处是上层（宝可梦解码、编辑界面）
    完全不用关心数据到底来自 .dat 还是 PBS。
    """

    def __init__(self, game_root: str):
        self.root = game_root
        self.pbs = os.path.join(game_root, "PBS")
        self.source = "none"          # "dat" / "pbs" / "none"
        self.dat_files: List[str] = []  # 实际读到的 .dat 文件名（排错用）
        self._species: Dict[int, dict] = {}
        self._items: Dict[int, Tuple[str, int]] = {}     # id -> (名称, 口袋)
        self._moves: Dict[int, str] = {}
        self._move_pp: Dict[int, int] = {}      # 招式编号 → 初始 PP
        self._abilities: Dict[int, str] = {}
        self._ability_by_internal: Dict[str, str] = {}        # 内部名 → 显示名
        self._ability_index: Dict[str, int] = {}              # 内部名 → 编号
        self.lang_dat: Optional[str] = None                   # 实际使用的语言包
        self._types: Dict[int, str] = {}
        self._type_by_internal: Dict[str, int] = {}      # 属性内部名 → 编号
        self._trainer_types: Dict[int, str] = {}
        self._pockets: List[str] = list(DEFAULT_POCKETS)
        # 内部名 → 编号（.dat 里 key 是 Symbol，用它才能和语言包对上号）
        self._species_by_internal: Dict[str, int] = {}
        self._item_by_internal: Dict[str, int] = {}
        self._move_by_internal: Dict[str, int] = {}
        self._forms: Dict[int, List[int]] = {}          # 物种 → 可用形态号
        # 形态自己的数据（.dat 的 form>0 条目）与内部名
        self._form_info: Dict[Tuple[int, int], dict] = {}
        self._form_internal: Dict[Tuple[int, int], str] = {}
        # ★ 现代存档（v19+）里 物种/道具/招式/特性 都是用 Symbol（内部名）存的，
        #   所以除了「编号 → 名字」，还得有「编号 → 内部名」的反查
        self._terms: Dict[str, str] = {}      # 术语字典（小写原文 → 译文）
        self._species_internal: Dict[int, str] = {}
        self._item_internal: Dict[int, str] = {}
        self._move_internal: Dict[int, str] = {}
        self._trainer_type_by_internal: Dict[str, int] = {}
        self._trainer_type_internal: Dict[int, str] = {}
        self.loaded = False

    # -- PBS ---------------------------------------------------------------
    @staticmethod
    def _read(name_dirfile: str) -> Optional[str]:
        try:
            with open(name_dirfile, "r", encoding="utf-8-sig", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def _pbs_file(self, *names: str) -> Optional[str]:
        for n in names:
            p = os.path.join(self.pbs, n)
            if os.path.isfile(p):
                txt = self._read(p)
                if txt:
                    return txt
        return None

    @staticmethod
    def _csv_rows(txt: str):
        for line in txt.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            yield line.split(",")

    # -- 入口 --------------------------------------------------------------
    def load(self) -> "GameData":
        if self.loaded:
            return self
        self.loaded = True
        try:
            self._load_compiled()          # ① Data/*.dat（编译好的数据）
        except Exception:
            self.dat_files.append("（.dat 读取失败，已跳过）")
        self._load_pbs()                   # ② PBS/*.txt（只补 .dat 没有的）
        self._load_language_pack()         # ③ 语言包（v16 的 <语言>.dat）
        self._load_pocket_names()          # ④ 口袋名（脚本里的 pbPocketNames）
        return self

    # ------------------------------------------------------------------
    # ① 编译好的 .dat
    #   v19+ ：Hash{ Symbol(内部名) => GameData::Species 等 Ruby 对象 }
    #           字段名取自 010_Data/002_PBS data/*.rb 的 attr_reader
    #   v17/18：Hash{ 编号 => 数组 }，布局见各自源码（此处按常见布局解析）
    # ------------------------------------------------------------------
    # 能力值的 Hash 键顺序 → PBS 的顺序（HP, 攻击, 防御, 速度, 特攻, 特防）
    DAT_STAT_ORDER = ["HP", "ATTACK", "DEFENSE", "SPEED",
                      "SPECIAL_ATTACK", "SPECIAL_DEFENSE"]

    def _dat_path(self, *names: str) -> Optional[str]:
        """找一个非空的 Data/<name>（空文件是「占位」，不能当数据源）。"""
        for n in names:
            p = os.path.join(self.root, "Data", n)
            if os.path.isfile(p) and os.path.getsize(p) > 8:
                return p
        return None

    @staticmethod
    def _ivars(obj: Any) -> dict:
        """Ruby 对象的 ivar 表；不是对象就返回空。"""
        return obj.ivars if isinstance(obj, rmarshal.RObject) else {}

    @staticmethod
    def _num(v: Any) -> Optional[int]:
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def _dat_pairs(self, path: str) -> List[tuple]:
        """把 .dat 读成 [(key, value)]。读不出来就返回空列表。"""
        try:
            obj = rmarshal.load(path)
        except Exception:
            return []
        if isinstance(obj, rmarshal.RHash):
            return list(obj.pairs)
        if isinstance(obj, dict):
            return list(obj.items())
        return []

    def _load_compiled(self) -> None:
        """读 Data/*.dat。.dat 优先 —— 汉化版常把 PBS 删掉只留 .dat。"""
        def each(*names):
            p = self._dat_path(*names)
            if p:
                self.dat_files.append(os.path.basename(p))
            return self._dat_pairs(p) if p else []

        # --- 特性 ---
        for key, val in each("abilities.dat"):
            ivs = self._ivars(val)
            num = self._num(ivs.get("@id_number"))
            name = ivs.get("@real_name") or ivs.get("@name")
            if isinstance(val, list) and len(val) >= 3:
                num, name = self._num(val[0]), val[2]          # v17/18 数组式
            if not isinstance(name, str) or not name:
                continue
            idx = num if num is not None else len(self._abilities)
            self._abilities.setdefault(idx, name)
            self._ability_by_internal.setdefault(_sym(key).upper(), name)
            self._ability_index.setdefault(_sym(key).upper(), idx)

        # --- 属性 ---
        for key, val in each("types.dat"):
            ivs = self._ivars(val)
            num = self._num(ivs.get("@id_number"))
            name = ivs.get("@real_name") or ivs.get("@name")
            if isinstance(val, list) and len(val) >= 3:
                num, name = self._num(val[0]), val[2]
            if not isinstance(name, str) or not name:
                continue
            idx = num if num is not None else len(self._types)
            self._types.setdefault(idx, name)
            if ivs:
                # v19+ 的 GameData::Type 带 @id（内部名），拿它就能把
                # PBS 里的 Type1=GHOST 换算成显示名
                self._type_by_internal.setdefault(_sym(key).upper(), idx)

        # --- 训练家类型 ---
        for key, val in each("trainer_types.dat", "trainertypes.dat"):
            ivs = self._ivars(val)
            num = self._num(ivs.get("@id_number"))
            name = ivs.get("@real_name") or ivs.get("@name")
            if isinstance(val, list) and len(val) >= 3:
                num, name = self._num(val[0]), val[2]
            if not isinstance(name, str) or not name:
                continue
            idx = num if num is not None else len(self._trainer_types)
            self._trainer_types.setdefault(idx, name)
            self._trainer_type_by_internal.setdefault(_sym(key).upper(), idx)
            self._trainer_type_internal.setdefault(idx, _sym(key))

        # --- 招式 ---
        for key, val in each("moves.dat"):
            ivs = self._ivars(val)
            num = self._num(ivs.get("@id_number"))
            name = ivs.get("@real_name") or ivs.get("@name")
            pp = self._num(ivs.get("@total_pp"))
            if isinstance(val, list) and len(val) >= 3:
                num, name = self._num(val[0]), val[2]
                pp = self._num(val[5]) if len(val) > 5 else pp
            if not isinstance(name, str) or not name:
                continue
            idx = num if num is not None else (max(self._moves) + 1
                                               if self._moves else 1)
            self._moves.setdefault(idx, name)
            if pp:
                self._move_pp.setdefault(idx, pp)
            self._move_by_internal.setdefault(_sym(key).upper(), idx)
            self._move_internal.setdefault(idx, _sym(key))

        # --- 道具 ---
        for key, val in each("items.dat"):
            ivs = self._ivars(val)
            num = self._num(ivs.get("@id_number"))
            name = ivs.get("@real_name") or ivs.get("@name")
            pocket = self._num(ivs.get("@pocket")) or 0
            if isinstance(val, list) and len(val) >= 5:
                num, name = self._num(val[0]), val[2]
                pocket = self._num(val[4]) or 0
            if not isinstance(name, str) or not name:
                continue
            idx = num if num is not None else (max(self._items) + 1
                                               if self._items else 1)
            self._items.setdefault(idx, (name, pocket))
            self._item_by_internal.setdefault(_sym(key).upper(), idx)
            self._item_internal.setdefault(idx, _sym(key))

        # --- 物种 ---
        for key, val in each("species.dat", "pokemon.dat"):
            self._add_species_dat(key, val)

        if self._species:
            self.source = "dat"

    def _add_species_dat(self, key: Any, val: Any) -> None:
        """把一条 .dat 物种记录归一化成 PBS 字段名。"""
        ivs = self._ivars(val)
        name = stats = rate = abil_s = hidden = gender = types_s = hatch = None
        form = None
        if ivs:
            name = ivs.get("@real_name") or ivs.get("@name")
            bs = ivs.get("@base_stats")
            if isinstance(bs, rmarshal.RHash):
                d = {_sym(k).upper(): self._num(v) for k, v in bs.pairs}
                stats = [d.get(k) or 0 for k in self.DAT_STAT_ORDER]
            elif isinstance(bs, (list, tuple)) and len(bs) >= 6:
                stats = [self._num(x) or 0 for x in bs[:6]]
            t = ivs.get("@types")
            if isinstance(t, (list, tuple)) and t:
                types_s = ",".join(_sym(x) for x in t)
            else:
                types_s = ",".join(x for x in (_sym(ivs.get("@type1")),
                                               _sym(ivs.get("@type2"))) if x)
            rate = _sym(ivs.get("@growth_rate"))
            abil_s = ",".join(_sym(a) for a in (ivs.get("@abilities") or []) if a)
            h = [_sym(a) for a in (ivs.get("@hidden_abilities") or []) if a]
            hidden = h[0] if h else None
            gender = _sym(ivs.get("@gender_ratio"))
            hatch = self._num(ivs.get("@hatch_steps"))
            form = self._num(ivs.get("@form"))
            sid = self._num(ivs.get("@id_number"))
        elif isinstance(val, list) and len(val) >= 12:
            # v17/v18 的 pokemon.dat：数组式；能力值顺序是
            # HP / 攻击 / 防御 / 速度 / 特攻 / 特防（PBStats 顺序）
            name = val[0]
            stats = [self._num(x) or 0 for x in val[3:9]]
            types_s = ",".join(_sym(x) for x in val[1:3] if x)
            gender = _sym(val[9]) if len(val) > 9 else None
            rate = _sym(val[11]) if len(val) > 11 else None
            abil_s = _sym(val[15]) if len(val) > 15 else None
            hidden = _sym(val[17]) if len(val) > 17 and val[17] is not None else None
            sid = self._num(val[0]) if isinstance(val[0], int) else None
        else:
            return

        # ★ 形态（form）在 species.dat 里是**独立条目**：VULPIX / VULPIX_1 /
        #   VULPIX_2，@species 都指向 :VULPIX，@form 分别是 0/1/2，
        #   而且这批文件的 @id_number 是空的。所以：
        #     · form 0 → 定编号（@id_number 优先，没有就按出场顺序编号）
        #     · form > 0 → 挂到它所属物种上，别新占一个物种
        base_sym = _sym(ivs.get("@species")) if ivs else None
        if not base_sym:
            base_sym = _sym(key)
        form = form or 0
        if form <= 0:
            if sid is None:
                sid = self._species_by_internal.get(base_sym.upper())
            if sid is None:
                sid = (max(self._species) + 1) if self._species else 1
        else:
            sid = self._species_by_internal.get(base_sym.upper())
            if sid is None:
                return          # 基础形态还没出现（文件顺序异常），跳过

        fields = {"Name": name,
                  "BaseStats": ",".join(map(str, stats)) if stats else None,
                  "GrowthRate": rate, "Abilities": abil_s,
                  "HiddenAbility": hidden, "GenderRate": gender,
                  "Types": types_s, "HatchSteps": hatch}
        if form <= 0:
            info = self._species.setdefault(sid, {})
            for k, v in fields.items():
                if v not in (None, ""):
                    info.setdefault(k, v)
            self._species_internal.setdefault(sid, _sym(key))
        else:
            f = self._form_info.setdefault((sid, form), {})
            for k, v in fields.items():
                if v not in (None, ""):
                    f.setdefault(k, v)
            self._form_internal[(sid, form)] = _sym(key)
        self._species_by_internal.setdefault(_sym(key).upper(), sid)
        self._forms.setdefault(sid, [0])
        if form not in self._forms[sid]:
            self._forms[sid].append(form)

    # ------------------------------------------------------------------
    # ② PBS/*.txt —— 只补 .dat 里没有的（setdefault，不覆盖 .dat）
    # ------------------------------------------------------------------
    def _load_pbs(self) -> None:
        # --- 宝可梦：[ID] 小节体 ---
        txt = self._pbs_file("pokemon.txt")
        if txt:
            cur = None
            for line in txt.splitlines():
                line = line.strip()
                m = re.match(r"^\[(\d+)\]$", line)
                if m:
                    cur = int(m.group(1))
                    self._species.setdefault(cur, {})
                    continue
                if line.startswith("#") or cur is None or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                self._species[cur].setdefault(k, v)
                if k == "InternalName" and v:
                    self._species_by_internal.setdefault(v.upper(), cur)
                    self._species_internal.setdefault(cur, v)

        # --- 道具：id,内部名,名称,复数名,口袋,价格,... ---
        txt = self._pbs_file("items.txt")
        if txt:
            for row in self._csv_rows(txt):
                if len(row) < 3 or not row[0].isdigit():
                    continue
                pocket = int(row[4]) if len(row) > 4 and row[4].strip().isdigit() else 0
                iid = int(row[0])
                self._items.setdefault(iid, (row[2].strip(), pocket))
                self._item_by_internal.setdefault(row[1].strip().upper(), iid)
                self._item_internal.setdefault(iid, row[1].strip())

        # --- 招式：id,内部名,名称,作用码,威力,属性,类别,命中,总PP,... ---
        txt = self._pbs_file("moves.txt")
        if txt:
            for row in self._csv_rows(txt):
                if len(row) < 3 or not row[0].isdigit():
                    continue
                mid = int(row[0])
                self._moves.setdefault(mid, row[2].strip())
                self._move_by_internal.setdefault(row[1].strip().upper(), mid)
                self._move_internal.setdefault(mid, row[1].strip())
                if len(row) > 8 and row[8].strip().isdigit():
                    self._move_pp.setdefault(mid, int(row[8]))

        # --- 特性：id,内部名,名称,... ---
        txt = self._pbs_file("abilities.txt")
        if txt:
            for row in self._csv_rows(txt):
                if len(row) < 3 or not row[0].isdigit():
                    continue
                aid = int(row[0])
                self._abilities.setdefault(aid, row[2].strip())
                self._ability_by_internal.setdefault(row[1].strip().upper(),
                                                     row[2].strip())
                self._ability_index.setdefault(row[1].strip().upper(), aid)

        # --- 属性：[ID] Name=... ---
        txt = self._pbs_file("types.txt")
        if txt:
            cur = None
            for line in txt.splitlines():
                line = line.strip()
                m = re.match(r"^\[(\d+)\]$", line)
                if m:
                    cur = int(m.group(1))
                    self._types.setdefault(cur, "")
                    continue
                if line.startswith("Name=") and cur is not None:
                    if line[5:].strip():
                        self._types[cur] = line[5:].strip()

        # --- 训练家类型：id,内部名,名称,... ---
        txt = self._pbs_file("trainer_types.txt", "trainertypes.txt")
        if txt:
            for row in self._csv_rows(txt):
                if len(row) < 3 or not row[0].isdigit():
                    continue
                self._trainer_types.setdefault(int(row[0]), row[2].strip())
                self._trainer_type_by_internal.setdefault(
                    row[1].strip().upper(), int(row[0]))
                self._trainer_type_internal.setdefault(int(row[0]),
                                                       row[1].strip())

        if self._species and self.source == "none":
            self.source = "pbs"

    # 编译后的 <语言>.dat（v16 的 messages 布局）：
    #   1=宝可梦名 2=种类 3=图鉴说明 4=形态名 5=招式名 6=招式说明
    #   7=道具名 8=道具复数名 9=道具说明 10=特性名 11=特性说明 12=属性名 13=训练家类型
    LANG_COLS = {"species": 1, "kind": 2, "dex": 3, "form": 4,
                 "move": 5, "item": 7, "ability": 10, "type": 12, "trainer": 13}

    def _load_language_pack(self) -> None:
        """
        游戏里显示的其实是 <语言>.dat 里的译文（PBS / .dat 里可能是原文）。

        列布局在各版本里一致（都来自同一张 intl 段表）：
          1=宝可梦名 2=种类 3=图鉴说明 4=形态名 5=招式名 …
        这里做一次形状校验（物种名 ≥100 条、属性名 15~30 条）才采用，
        免得把别的表的列当名字用。
        """
        for name in ("ch.dat", "intl.dat", "English.dat", "messages.dat"):
            path = os.path.join(self.root, "Data", name)
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                continue
            try:
                cols = rmarshal.load(path)
            except Exception:
                continue
            if not isinstance(cols, list) or len(cols) < 14:
                continue
            sp_col = cols[self.LANG_COLS["species"]]
            ty_col = cols[self.LANG_COLS["type"]]
            if not isinstance(sp_col, list) or len(sp_col) < 100:
                continue
            if not isinstance(ty_col, list) or not (15 <= len(ty_col) <= 30):
                continue
            self.lang_dat = name
            C = self.LANG_COLS

            def col(i):
                v = cols[i] if i < len(cols) else None
                return v if isinstance(v, list) else []

            for sid, name_txt in enumerate(col(C["species"])):
                if isinstance(name_txt, str) and name_txt:
                    self._species.setdefault(sid, {})["Name"] = name_txt
            for mid, name_txt in enumerate(col(C["move"])):
                if isinstance(name_txt, str) and name_txt:
                    self._moves[mid] = name_txt
            for iid, name_txt in enumerate(col(C["item"])):
                if isinstance(name_txt, str) and name_txt:
                    prev = self._items.get(iid)
                    self._items[iid] = (name_txt, prev[1] if prev else self.item_pocket(iid))
            for tid, name_txt in enumerate(col(C["type"])):
                if isinstance(name_txt, str) and name_txt:
                    self._types[tid] = name_txt
            for tid, name_txt in enumerate(col(C["trainer"])):
                if isinstance(name_txt, str) and name_txt:
                    self._trainer_types[tid] = name_txt
            for aid, name_txt in enumerate(col(C["ability"])):
                if isinstance(name_txt, str) and name_txt:
                    self._abilities[aid] = name_txt
            break

    def ability_name(self, internal: str) -> str:
        """内部名 → 显示名（优先用语言包的译文）。"""
        key = (internal or "").upper()
        idx = self._ability_index.get(key)
        if idx is not None and self._abilities.get(idx):
            return self.tr(self._abilities[idx])
        return self.tr(self._ability_by_internal.get(key, internal or ""))

    def _load_pocket_names(self) -> None:
        """口袋名写在 Scripts.rxdata 的 Settings 脚本里，取不到就用默认值。"""
        path = os.path.join(self.root, "Data", "Scripts.rxdata")
        if not os.path.isfile(path):
            return
        try:
            entries = rmarshal.load(path)
        except Exception:
            return
        for entry in entries:
            if not (isinstance(entry, list) and len(entry) >= 3 and isinstance(entry[1], str)):
                continue
            if entry[1] != "Settings":
                continue
            try:
                raw = entry[2].encode("utf-8", errors="surrogateescape")
                src = zlib.decompress(raw).decode("utf-8", errors="replace")
            except Exception:
                continue
            m = re.search(r"def\s+pbPocketNames.*?\[(.*?)\]", src, re.S)
            if m:
                names = re.findall(r'_\w+\("([^"]*)"\)|"([^"]*)"', m.group(1))
                got = [a or b for a, b in names]
                if got:
                    self._pockets = got
            break

    # -- 术语字典 ----------------------------------------------------------
    def apply_terms(self, terms: Dict[str, str]) -> "GameData":
        r"""挂上术语字典（小写原文 → 译文），显示名一律先过它。"""
        self._terms = dict(terms or {})
        return self

    def tr(self, name: Any) -> Any:
        """术语字典查一遍（查不到原样返回）。"""
        if not self._terms or not isinstance(name, str) or not name:
            return name
        got = self._terms.get(name.strip().lower())
        return got if got else name

    # -- 查询 --------------------------------------------------------------
    def species(self, sid: Any) -> str:
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            return str(sid)
        info = self._species.get(sid)
        if not info:
            return f"#{sid}"
        return self.tr(info.get("Name") or f"#{sid}")

    def species_info(self, sid: Any, form: Any = 0) -> dict:
        """
        物种数据（PBS 字段名）。★ 带形态时优先用形态自己的那份
        （形态的种族值/属性/特性在 .dat 里就是独立条目，不这么做
          算出来的能力值会和游戏对不上 —— 踩过：空谷幽林的火狐狸形态 2）。
        """
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            return {}
        base = self._species.get(sid, {})
        try:
            form = int(form or 0)
        except (TypeError, ValueError):
            form = 0
        if form > 0:
            f = self._form_info.get((sid, form))
            if f:
                merged = dict(base)
                merged.update(f)
                return merged
        return base

    def item(self, iid: Any) -> str:
        try:
            iid = int(iid)
        except (TypeError, ValueError):
            return str(iid)
        hit = self._items.get(iid)
        if hit:
            return self.tr(hit[0])
        # ★ v16 的编号从 1 开始、0 表示「没有道具」；v19+ 的编号从 0 开始，
        #   所以只有 0 号确实不在表里时才当成「无」。
        return "（无）" if iid == 0 else f"#{iid}"

    def item_pocket(self, iid: Any) -> int:
        try:
            iid = int(iid)
        except (TypeError, ValueError):
            return 0
        return self._items.get(iid, (None, 0))[1]

    def move(self, mid: Any) -> str:
        try:
            mid = int(mid)
        except (TypeError, ValueError):
            return str(mid)
        if not mid:
            return "（无）"
        return self.tr(self._moves.get(mid, f"#{mid}"))

    def type_name(self, tid: Any) -> str:
        try:
            t = self._types.get(int(tid), str(tid))
        except (TypeError, ValueError):
            t = str(tid)
        return self.tr(t)

    def trainer_type(self, tid: Any) -> str:
        try:
            t = self._trainer_types.get(int(tid), str(tid))
        except (TypeError, ValueError):
            t = str(tid)
        return self.tr(t)

    def pocket_name(self, idx: int) -> str:
        if idx == 0:
            return "（未使用）"
        if 0 <= idx < len(self._pockets):
            return self._pockets[idx] or f"口袋{idx}"
        return f"口袋{idx}"

    # -- 编辑界面用的清单（(显示名, 编号) 列表，已按编号排序） ---------------
    @staticmethod
    def _listing(d: Dict[int, Any]) -> List[Tuple[str, int]]:
        def key(it):
            v = it[1]
            return (0, v) if isinstance(v, int) else (1, str(v))
        return sorted(((str(v), k) for k, v in d.items()), key=key)

    def species_list(self) -> List[Tuple[str, int]]:
        """[(显示名, 全国图鉴编号)]；显示名带编号，方便搜索。"""
        return self._listing({k: self.species(k) for k in self._species})

    def item_list(self) -> List[Tuple[str, int]]:
        # ★ 和 species_list() 一样过一遍术语字典：否则下拉里是 .dat 的英文
        #   原名（"Repel"），同页表格用 item() 却是中文（"除虫喷雾"），两边对不上
        return self._listing({k: self.tr(v[0]) for k, v in self._items.items()})

    def move_list(self) -> List[Tuple[str, int]]:
        return self._listing({k: self.tr(v) for k, v in self._moves.items()})

    def move_pp(self, mid: Any) -> int:
        """招式初始 PP（读不到就给 10，够用）。"""
        try:
            return self._move_pp.get(int(mid), 10) or 10
        except (TypeError, ValueError):
            return 10

    def trainer_type_list(self) -> List[Tuple[str, int]]:
        return self._listing(self._trainer_types)

    # -- 单只宝可梦要用到的原始数据 ----------------------------------------
    def base_stats(self, sid: Any, form: Any = 0) -> List[int]:
        """六项种族值，顺序 = [HP, 攻击, 防御, 速度, 特攻, 特防]。"""
        info = self.species_info(sid, form)
        txt = info.get("BaseStats") or ""
        try:
            vals = [int(float(x)) for x in txt.split(",") if x.strip() != ""]
        except (TypeError, ValueError):
            vals = []
        while len(vals) < 6:
            vals.append(1)
        return vals[:6]

    def growth_rate(self, sid: Any, form: Any = 0) -> str:
        return self.species_info(sid, form).get("GrowthRate") or "Medium"

    def abilities_of(self, sid: Any, form: Any = 0) -> List[str]:
        """可选特性内部名列表（含隐藏特性，顺序即 @abilityflag 的取值）。"""
        info = self.species_info(sid, form)
        out = [a.strip() for a in (info.get("Abilities") or "").split(",") if a.strip()]
        hid = (info.get("HiddenAbility") or "").strip()
        if hid:
            out.append(hid)
        return out

    def ability_options(self, sid: Any,
                        form: Any = 0) -> List[Tuple[str, int]]:
        """[(特性显示名, @abilityflag / @ability_index 取值)]，供编辑界面下拉。"""
        opts = []
        for i, internal in enumerate(self.abilities_of(sid, form)):
            opts.append((self.ability_name(internal) or internal, i))
        return opts

    def gender_rate(self, sid: Any, form: Any = 0) -> str:
        return self.species_info(sid, form).get("GenderRate") or "Genderless"

    def hatch_steps(self, sid: Any, form: Any = 0) -> Optional[int]:
        v = self.species_info(sid, form).get("HatchSteps")
        return v if isinstance(v, int) else None

    def type_index_of(self, name_or_id: Any) -> Optional[int]:
        """把「属性内部名 / 编号 / 显示名」换算成编号。认不出来返回 None。"""
        if name_or_id is None:
            return None
        s = str(name_or_id).strip()
        if not s:
            return None
        if s.lstrip("-").isdigit():
            i = int(s)
            return i if i in self._types else None
        key = s.upper()
        if key in self._type_by_internal:
            return self._type_by_internal[key]
        for i, v in self._types.items():
            if str(v).upper() == key:
                return i
        if len(self._types) in (18, 19) and key in ESSENTIALS_TYPE_ORDER:
            i = ESSENTIALS_TYPE_ORDER.index(key)
            if i in self._types:
                return i
        return None

    def type_names_of(self, sid: Any, form: Any = 0) -> str:
        info = self.species_info(sid, form)
        raw = info.get("Types") or ""
        if not raw:
            # PBS（v16~v18）用的是 Type1= / Type2= 两个字段
            raw = ",".join(x for x in (info.get("Type1"), info.get("Type2")) if x)
        out = []
        for t in raw.split(","):
            t = t.strip()
            if not t:
                continue
            idx = self.type_index_of(t)
            out.append(self.type_name(idx) if idx is not None else t)
        return "/".join(out)

    def forms_of(self, sid: Any) -> List[int]:
        """
        可用形态号。

        ★ 只有 .dat 里记过形态才准（一个物种会以多条 form 记录出现）；
          纯 PBS 的作品没有形态表，返回空列表让界面提示「按数字填」。
        """
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            return []
        if sid in self._forms:
            return sorted(set(self._forms[sid]))
        return []

    # =====================================================================
    # 内部名 ↔ 编号（现代存档 v19+ 用 Symbol 存 物种 / 道具 / 招式 / 特性）
    # =====================================================================
    @staticmethod
    def _norm_internal(name: Any) -> str:
        """内部名归一：去掉下划线等符号、统一大写（GIFT_LANTURN == giftlanturn）。"""
        return re.sub(r"[^0-9A-Za-z]+", "", str(name or "")).upper()

    def _lookup(self, table: Dict[str, int], internal: Any) -> Optional[int]:
        key = self._norm_internal(internal)
        if not key:
            return None
        if key in table:
            return table[key]
        for k, v in table.items():
            if self._norm_internal(k) == key:
                return v
        return None

    def species_id_of(self, internal: Any) -> Optional[int]:
        return self._lookup(self._species_by_internal, internal)

    def item_id_of(self, internal: Any) -> Optional[int]:
        return self._lookup(self._item_by_internal, internal)

    def move_id_of(self, internal: Any) -> Optional[int]:
        return self._lookup(self._move_by_internal, internal)

    def trainer_type_id_of(self, internal: Any) -> Optional[int]:
        return self._lookup(self._trainer_type_by_internal, internal)

    def trainer_type_internal(self, tid: Any) -> str:
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            return str(tid)
        return self._trainer_type_internal.get(tid) or "POKEMONTRAINER_Red"

    def trainer_type_name_of(self, internal: Any) -> str:
        """训练家类型 Symbol（:POKEMONTRAINER_Red）→ 显示名。"""
        idx = self.trainer_type_id_of(internal)
        if idx is not None and self._trainer_types.get(idx):
            return self._trainer_types[idx]
        return str(internal)

    def species_internal(self, sid: Any) -> str:
        """编号 → 内部名（写现代存档时要用 Symbol）。取不到就退回名字。"""
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            return str(sid)
        return self._species_internal.get(sid) or self.species(sid).replace(" ", "")

    def item_internal(self, iid: Any) -> str:
        try:
            iid = int(iid)
        except (TypeError, ValueError):
            return str(iid)
        return self._item_internal.get(iid) or self.item(iid).replace(" ", "")

    def move_internal(self, mid: Any) -> str:
        try:
            mid = int(mid)
        except (TypeError, ValueError):
            return str(mid)
        return self._move_internal.get(mid) or self.move(mid).replace(" ", "")

    # -- 性格 / 状态（现代存档也是 Symbol） --------------------------------
    NATURE_SYMBOLS = [n.upper() for n in NATURES_EN]

    def nature_index_of(self, symbol: Any) -> Optional[int]:
        """:MODEST → 15。认不出来返回 None。"""
        key = self._norm_internal(symbol)
        if not key:
            return None
        for i, n in enumerate(self.NATURE_SYMBOLS):
            if n == key:
                return i
        for i, n in enumerate(NATURES):
            if self._norm_internal(n) == key:
                return i
        return None

    def nature_name(self, index: Any) -> str:
        """性格显示名（术语表里有 "Adamant" → 就用它的译文，否则用内置中文）。"""
        try:
            i = int(index)
        except (TypeError, ValueError):
            return str(index)
        if 0 <= i < 25:
            return self.tr(NATURES_EN[i]) or NATURES[i]
        return str(index)

    def nature_options(self) -> List[Tuple[str, int]]:
        """性格下拉：[(显示名（英文）, 取值)]。"""
        return [(f"{self.nature_name(i)}（{NATURES_EN[i]}）", i)
                for i in range(25)]

    def nature_symbol(self, index: Any) -> str:
        try:
            i = int(index)
        except (TypeError, ValueError):
            return "HARDY"
        return self.NATURE_SYMBOLS[i] if 0 <= i < 25 else "HARDY"

    # :SLEEP / :POISON … → 与 v16 数字一致的状态码（0 正常 … 6 濒死）
    STATUS_SYMBOLS = {"NONE": 0, "SLEEP": 1, "POISON": 2, "BURN": 3,
                      "FROZEN": 4, "PARALYSIS": 5, "FAINT": 6}

    def status_code_of(self, symbol: Any) -> int:
        key = self._norm_internal(symbol)
        if not key:
            return 0
        if key in self.STATUS_SYMBOLS:
            return self.STATUS_SYMBOLS[key]
        for k, v in self.STATUS_SYMBOLS.items():
            if self._norm_internal(k) == key:
                return v
        return 0

    def status_symbol(self, code: Any) -> str:
        try:
            c = int(code)
        except (TypeError, ValueError):
            c = 0
        for k, v in self.STATUS_SYMBOLS.items():
            if v == c:
                return k
        return "NONE"


# ---------------------------------------------------------------------------
# 数值换算
# ---------------------------------------------------------------------------
def growth_exp(level: int, rate: str) -> int:
    """某种成长曲线升到 level 所需的累计经验。"""
    rate = (rate or "").upper()
    n = level
    if rate.startswith("FAST"):
        return int(4 * n ** 3 / 5)
    if rate.startswith("SLOW"):
        return int(5 * n ** 3 / 4)
    if rate.startswith("PARABOLIC") or rate.startswith("MEDIUMSLOW"):
        return int(1.25 * n ** 3 - 15 * n ** 2 + 100 * n - 140)
    if rate.startswith("ERRATIC"):
        if n <= 50:
            return int(n ** 3 * (100 - n) / 50)
        if n <= 68:
            return int(n ** 3 * (150 - n) / 100)
        if n <= 98:
            return int(n ** 3 * int((1911 - n * 10) / 3) / 500)
        return int(n ** 3 * (160 - n) / 100)
    if rate.startswith("FLUCTUATING"):
        if n <= 15:
            return int(n ** 3 * ((n + 1) // 3 + 24) / 50)
        if n <= 35:
            return int(n ** 3 * (n + 14) / 50)
        return int(n ** 3 * ((n // 2) + 32) / 50)
    return n ** 3        # Medium


def level_from_exp(exp: int, rate: str) -> int:
    lv = 1
    while lv < 100 and growth_exp(lv + 1, rate) <= exp:
        lv += 1
    return lv


def level_from_hp(totalhp: int, base_hp: int, iv_hp: int, ev_hp: int) -> Optional[int]:
    """
    形态宝可梦（如洛托姆形态 6）的基础数据在脚本里、不在 PBS 里，按经验反推等级
    会偏。用「HP 反推」更稳：所有形态的 HP 通常相同。
    """
    if not totalhp or not base_hp:
        return None
    for lv in range(1, 101):
        if (base_hp * 2 + iv_hp + ev_hp // 4) * lv // 100 + lv + 10 == totalhp:
            return lv
    return None


def nature_boost(nature: int, stat_index: int) -> Optional[str]:
    """返回 '↑' / '↓' / None。索引 0=HP，其余不吃加减。"""
    inc = nature // 5 + 1        # 提升的能力序列位 1..5
    dec = nature % 5 + 1         # 降低的能力序列位 1..5
    if inc == dec or stat_index == 0:
        return None
    if stat_index == inc:
        return "↑"
    if stat_index == dec:
        return "↓"
    return None


def calc_stat(base: int, level: int, iv: int, ev: int, nature: int, idx: int) -> int:
    if idx == 0:                                    # HP 不吃性格
        return (base * 2 + iv + ev // 4) * level // 100 + level + 10
    s = (base * 2 + iv + ev // 4) * level // 100 + 5
    boost = nature_boost(nature, idx)
    if boost == "↑":
        return int(s * 11 / 10)
    if boost == "↓":
        return int(s * 9 / 10)
    return s


def calc_stats(base_stats: List[int], level: int, ivs: List[int],
               evs: List[int], nature: int) -> List[int]:
    return [calc_stat(base_stats[i], level, ivs[i], evs[i], nature, i)
            for i in range(6)]


def gender_of(personal_id: int, gender_rate: str) -> str:
    rate = (gender_rate or "").strip()
    if rate == "AlwaysMale":
        return "♂"
    if rate == "AlwaysFemale":
        return "♀"
    if rate == "Genderless":
        return "—"
    th = GENDER_THRESHOLD.get(rate, 126)
    return "♀" if (personal_id & 0xFF) <= th else "♂"


def is_shiny(personal_id: int, trainer_id: int, shinyflag: Any = None) -> bool:
    if shinyflag is True:
        return True
    if shinyflag is False:
        return False
    try:
        a = int(personal_id) ^ ((int(trainer_id) & 0xFFFF) ^ (int(trainer_id) >> 16))
        return ((a & 0xFFFF) ^ (a >> 16)) < 8
    except (TypeError, ValueError):
        return False


def stamp_text(ts: Any) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
    except (TypeError, ValueError, OSError):
        return str(ts)


# ---------------------------------------------------------------------------
# 通用：把 Marshal 对象转成可 JSON 化的普通 Python 值
# ---------------------------------------------------------------------------
def to_plain(obj: Any, _seen: Optional[dict] = None, _path: str = "$") -> Any:
    """
    转成可 JSON 化的普通值。

    ★ 存档里的对象是**图**不是树：Game_Interpreter 会指回 $game_map，
      事件又指向 Interpreter…… 直接递归会 RecursionError。这里对「从根出发
      的当前路径」做记忆，遇到自己祖先就写成 {"$环": <路径>}。
    """
    if _seen is None:
        _seen = {}
    if isinstance(obj, (rmarshal.RObject, rmarshal.RHash, rmarshal.RIVar,
                        rmarshal.RStruct, rmarshal.RUserMarshal, list, dict)):
        key = id(obj)
        if key in _seen:
            return {"$环": _seen[key]}
        _seen[key] = _path

    try:
        if obj is None or isinstance(obj, (bool, int, float)):
            return obj
        if isinstance(obj, rmarshal.RStr):
            return str(obj)
        if isinstance(obj, rmarshal.RSymbol):
            return {":sym": obj.name}
        if isinstance(obj, rmarshal.RClass):
            return {":class": obj.name}
        if isinstance(obj, rmarshal.RHash):
            out: Dict[str, Any] = {
                ":hash": [[to_plain(k, _seen, _path + ".key"), to_plain(v, _seen, _path)]
                          for k, v in obj.pairs]}
            if obj.default is not None:
                out[":default"] = to_plain(obj.default, _seen, _path + ".default")
            return out
        if isinstance(obj, rmarshal.RObject):
            d = {":class": obj.ruby_class}
            for k, v in obj.ivars.items():
                d[k] = to_plain(v, _seen, _path + "." + k)
            return d
        if isinstance(obj, rmarshal.RIVar):
            d = {":ivar_on": to_plain(obj.base, _seen, _path + ".base")}
            if obj.uclass:
                d[":uclass"] = obj.uclass
            for k, v in obj.ivars.items():
                d[k] = to_plain(v, _seen, _path + "." + k)
            return d
        if isinstance(obj, rmarshal.RStruct):
            return {":struct": obj.ruby_class,
                    ":members": [[str(_sym(k)), to_plain(v, _seen, _path)]
                                 for k, v in obj.members]}
        if isinstance(obj, rmarshal.RUserDefined):
            return {":userdef": obj.ruby_class, ":payload": str(obj.payload)}
        if isinstance(obj, rmarshal.RUserMarshal):
            return {":marshal": obj.ruby_class,
                    ":data": to_plain(obj.data, _seen, _path + ".data")}
        if isinstance(obj, rmarshal.RRegexp):
            return {":regexp": obj.source}
        if isinstance(obj, list):
            return [to_plain(x, _seen, f"{_path}[{i}]") for i, x in enumerate(obj)]
        if isinstance(obj, dict):
            return {str(k): to_plain(v, _seen, _path + "." + str(k)) for k, v in obj.items()}
        return str(obj)
    finally:
        if isinstance(obj, (rmarshal.RObject, rmarshal.RHash, rmarshal.RIVar,
                            rmarshal.RStruct, rmarshal.RUserMarshal, list, dict)):
            _seen.pop(id(obj), None)


def _sym(v: Any) -> str:
    return v.name if isinstance(v, rmarshal.RSymbol) else str(v)


# ---------------------------------------------------------------------------
# 存档
# ---------------------------------------------------------------------------
# 按 pbSave 的 dump 顺序给每个流起名字
STREAM_LABELS = [
    ("$Trainer", "PokeBattle_Trainer", "主角与同行队伍"),
    ("Graphics.frame_count", "Integer", "游戏总帧数"),
    ("$game_system", "Game_System", "系统设定（BGM/、SE、菜单禁用等）"),
    ("$PokemonSystem", "PokemonSystem", "游戏选项（字体/速度/音量等）"),
    ("$game_map.map_id", "Integer", "当前地图 ID"),
    ("$game_switches", "Game_Switches", "全局开关"),
    ("$game_variables", "Game_Variables", "全局变量"),
    ("$game_self_switches", "Game_SelfSwitches", "事件独立开关"),
    ("$game_screen", "Game_Screen", "画面：天气、色调、贴图、摇晃"),
    ("$MapFactory", "PokemonMapFactory", "地图链（可能多张图）"),
    ("$game_player", "Game_Player", "主角：坐标、朝向、移动速度"),
    ("$PokemonGlobal", "PokemonGlobalMetadata", "全局数据：时间、飞点、上次治疗点…"),
    ("$game_map.metadata", "PokemonMapMetadata", "当前地图的事件状态"),
    ("$PokemonBag", "PokemonBag", "背包"),
    ("$PokemonStorage", "PokemonStorage", "电脑箱子"),
]


class SaveFile:
    """
    Essentials 存档。

    ★ 两种格式都要认（各代差异很大，字段名完全不一样）：

      **legacy**（v16 ~ v18，RGSS）
        15 个 Marshal 流首尾相接，每个全局变量一条：$Trainer / 开关 / 变量 …
        宝可梦字段：`@species` 是**数字**、`@iv`/`@ev` 是**长度 6 的数组**、
        性格是 `@natureflag`、特性是 `@abilityflag`、道具是数字编号。

      **hash**（v19+，含 v20 / v21）
        一条 Marshal 流，顶层是 `{ :player => Player, :bag => Bag, … }`。
        宝可梦字段：`@species` 是**Symbol（内部名）**、`@iv`/`@ev` 是
        **Hash{Symbol=>int}**、性格是 `@nature`（:MODEST）、特性是
        `@ability_index`、道具是 Symbol（:POTION）、状态是 Symbol（:NONE）。
        另外等级 `@level` 直接存在存档里，不用拿经验反推。

    对外统一：`sv.g("$Trainer")` 两种格式都能取到主角对象；`sv.pokemon(pm)`
    返回**同一种结构**，上层（导出 / 编辑界面）完全不用关心是哪一代。
    """

    # 现代格式：老的全局变量名 → Hash 里的键
    MODERN_KEYS = {
        "$Trainer": "player",
        "Graphics.frame_count": "frame_count",
        "$game_system": "game_system",
        "$PokemonSystem": "pokemon_system",
        "$game_map.map_id": "map_id",
        "$game_switches": "switches",
        "$game_variables": "variables",
        "$game_self_switches": "self_switches",
        "$game_screen": "game_screen",
        "$MapFactory": "map_factory",
        "$game_player": "game_player",
        "$PokemonGlobal": "global_metadata",
        "$game_map.metadata": "map_metadata",
        "$PokemonBag": "bag",
        "$PokemonStorage": "storage_system",
    }

    def __init__(self, path: str, game_root: Optional[str] = None):
        self.path = path
        with open(path, "rb") as f:
            self.raw = f.read()
        self.objects = rmarshal.loads_all(self.raw)
        self.fmt = "legacy"
        self.root = None
        first = self.objects[0] if self.objects else None
        if (len(self.objects) == 1 and isinstance(first, rmarshal.RHash)
                and self._modern_keys_of(first)):
            self.fmt = "hash"
            self.root = first
        self._data: Optional[GameData] = None
        self._game_root = game_root or self._guess_root()

    @staticmethod
    def _modern_keys_of(h: rmarshal.RHash) -> set:
        """顶层 Hash 的键里有没有现代格式那几个（用来判定格式）。"""
        names = set()
        for k, _v in h.pairs:
            if isinstance(k, rmarshal.RSymbol):
                names.add(k.name)
        return names & {"player", "bag", "storage_system"}

    # -- 路径 --------------------------------------------------------------
    def _guess_root(self) -> str:
        p = os.path.abspath(self.path)
        # <root>/Data/Savestates/xxx.rxdata —— 往上找带 Data 的那一层
        # （不要求有 PBS：汉化/编译过的游戏往往只有 Data）
        cur = os.path.dirname(p)
        fallback = None
        for _ in range(4):
            if os.path.isdir(os.path.join(cur, "Data")):
                if os.path.exists(os.path.join(cur, "Game.ini")):
                    return cur
                fallback = fallback or cur
            cur = os.path.dirname(cur)
        return fallback or os.path.dirname(p)

    @property
    def game_root(self) -> str:
        return self._game_root

    @property
    def data(self) -> GameData:
        # 走缓存（术语表改过会自动重读，不用重启工具）
        return load_game_data(self._game_root)

    # -- 索引 --------------------------------------------------------------
    def index(self) -> List[dict]:
        out = []
        if self.fmt == "hash":
            for i, (k, o) in enumerate(self.root.pairs):
                name = _sym(k)
                actual = o.ruby_class if isinstance(o, rmarshal.RObject) \
                    else type(o).__name__
                label = desc = ""
                for old, key in self.MODERN_KEYS.items():
                    if key == name:
                        label, desc = old, ""
                        break
                for lab, _cls, d in STREAM_LABELS:
                    if self.MODERN_KEYS.get(lab) == name:
                        desc = d
                        break
                out.append({
                    "index": i,
                    "全局变量": label or f":{name}",
                    "ruby类型": actual,
                    "说明": desc or "（v19+ 存档顶层对象）",
                    "字段数": len(o.ivars) if isinstance(o, rmarshal.RObject) else (
                        len(o) if isinstance(o, (list, rmarshal.RHash)) else None),
                })
            return out
        for i, o in enumerate(self.objects):
            label = cls = ""
            desc = ""
            if i < len(STREAM_LABELS):
                label, cls, desc = STREAM_LABELS[i]
            actual = o.ruby_class if isinstance(o, rmarshal.RObject) else type(o).__name__
            out.append({
                "index": i,
                "全局变量": label or f"?({actual})",
                "ruby类型": actual,
                "说明": desc,
                "字段数": len(o.ivars) if isinstance(o, rmarshal.RObject) else (
                    len(o) if isinstance(o, (list, rmarshal.RHash)) else None),
            })
        return out

    def g(self, key: str) -> Any:
        """
        按 '$Trainer' / '$PokemonBag' 之类的名字取到原始对象（两代格式都认）。
        也可以直接给现代格式的键名（"player" / ":bag"）或类名（"Player"）。
        """
        if self.fmt == "hash":
            want = self.MODERN_KEYS.get(key, key.lstrip("$").lstrip(":"))
            for k, v in self.root.pairs:
                if isinstance(k, rmarshal.RSymbol) and k.name == want:
                    return v
            for k, v in self.root.pairs:
                if isinstance(k, rmarshal.RSymbol) and \
                        k.name.lower() == str(want).lower():
                    return v
            for _k, v in self.root.pairs:
                if isinstance(v, rmarshal.RObject) and v.ruby_class == key:
                    return v
            raise KeyError(key)
        for i, (label, _, _) in enumerate(STREAM_LABELS):
            if label == key and i < len(self.objects):
                return self.objects[i]
        for o in self.objects:
            if isinstance(o, rmarshal.RObject) and o.ruby_class == key:
                return o
        raise KeyError(key)

    # -- 写回 --------------------------------------------------------------
    def dumps(self) -> bytes:
        if self.fmt == "hash":
            return rmarshal.dumps(self.root)
        return rmarshal.dumps_all(self.objects)

    def write(self, path: Optional[str] = None, backup: bool = True) -> str:
        target = path or self.path
        same = os.path.abspath(target) == os.path.abspath(self.path)
        if backup and same:
            bak = target + ".bak"
            if not os.path.exists(bak):
                try:
                    with open(bak, "wb") as f:
                        f.write(self.raw)
                except OSError:
                    pass
        blob = self.dumps()
        with open(target, "wb") as f:
            f.write(blob)
        if same:
            self.raw = blob            # 让 roundtrip_ok() 反映新的状态
        forget_save(target)            # ★ 刷新缓存 mtime，免得下次被当成「外部改过」
        return target

    def roundtrip_ok(self) -> bool:
        return self.dumps() == self.raw

    # =====================================================================
    # 解码
    # =====================================================================
    # -- 宝可梦 -----------------------------------------------------------
    # v19+ 的能力值 Hash 键顺序 → 我们内部顺序 [HP, 攻击, 防御, 速度, 特攻, 特防]
    MODERN_STAT_KEYS = ["HP", "ATTACK", "DEFENSE", "SPEED",
                        "SPECIAL_ATTACK", "SPECIAL_DEFENSE"]

    def _stat_hash(self, h: Any) -> List[int]:
        """把 @iv / @ev 的 Hash{Symbol=>int} 读成内部顺序的 6 个数。"""
        if isinstance(h, rmarshal.RHash):
            d = {GameData._norm_internal(_sym(k)): v for k, v in h.pairs}
        elif isinstance(h, list):
            d = {}
        else:
            d = {}
        out = []
        for key in self.MODERN_STAT_KEYS:
            v = d.get(GameData._norm_internal(key))
            out.append(int(v) if isinstance(v, int) else 0)
        return out

    def _set_stat_hash(self, h: Any, values: List[int]) -> None:
        """
        写回 @iv / @ev。

        ★ 尽量**复用原来的键对象**（RHash 是键值对列表，直接改 v 就不动顺序、
          也不会让 Symbol 在对象表里错位）；缺的键才补。
        """
        if not isinstance(h, rmarshal.RHash):
            return
        want = {GameData._norm_internal(k): (k, values[i])
                for i, k in enumerate(self.MODERN_STAT_KEYS)}
        for i in range(len(h.pairs)):
            k, v = h.pairs[i]
            key = GameData._norm_internal(_sym(k))
            if key in want:
                h.pairs[i] = (k, max(0, int(want[key][1])))
                want.pop(key)
        for key, (name, val) in want.items():
            h.pairs.append((rmarshal.RSymbol(name), max(0, int(val))))

    def _species_id(self, v: Any) -> Optional[int]:
        """物种（Symbol / 字符串 / 数字）→ 编号。"""
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, rmarshal.RSymbol):
            return self.data.species_id_of(v.name)
        i = self.data.species_id_of(v)
        if i is not None:
            return i
        return int(v) if str(v).lstrip("-").isdigit() else None

    def _move_id(self, v: Any) -> Optional[int]:
        """招式（Symbol / 字符串 / 数字）→ 编号。"""
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v or None
        if isinstance(v, rmarshal.RSymbol):
            return self.data.move_id_of(v.name)
        i = self.data.move_id_of(v)
        if i is not None:
            return i
        return int(v) if str(v).lstrip("-").isdigit() else None

    def _read_pokemon(self, pm: Any) -> dict:
        """把一只宝可梦读成**与格式无关**的中间结构（显示 / 编辑都用它）。"""
        iv = pm.ivars
        get = iv.get
        d = self.data
        if self.fmt == "hash":
            sid = self._species_id(get("@species"))
            exp = get("@exp") or 0
            level = get("@level")
            if not isinstance(level, int) or level < 1:
                level = level_from_exp(exp, d.growth_rate(sid))
            nature = None
            nature_src = "@nature"
            nat = get("@nature")
            if nat is not None:
                nature = d.nature_index_of(nat)
            if nature is None:
                nature = (get("@personalID") or 0) % 25
                nature_src = "personalID%25（缺省）"
            form = get("@form") or 0
            ab_sym = get("@ability")
            ab_flag = get("@ability_index")
            ab_txt = None
            if ab_sym is not None:
                # v19+ 的 @ability 是「显式指定」的特性（Symbol），它优先
                ab_txt = d.ability_name(_sym(ab_sym))
                for i, a in enumerate(d.abilities_of(sid, form)):
                    if GameData._norm_internal(a) == \
                            GameData._norm_internal(_sym(ab_sym)):
                        ab_flag = i
                        break
            ab_src = "@ability" if ab_sym is not None else (
                "@ability_index" if ab_flag is not None else "personalID%2（缺省）")
            if ab_flag is None:
                ab_flag = (get("@personalID") or 0) % 2
            moves = []
            for mv in get("@moves") or []:
                mi = getattr(mv, "ivars", None)
                if not isinstance(mi, dict):
                    continue
                moves.append((self._move_id(mi.get("@id")),
                              mi.get("@pp"), mi.get("@ppup")))
            nm = get("@name")
            if nm in (None, ""):
                # v19 里 @name = nil 表示「用种族名」显示
                nm = d.species(sid)
            owner = get("@owner")
            oi = owner.ivars if isinstance(owner, rmarshal.RObject) else {}
            ribbons = get("@ribbons") or []
            kind = {0: "♂", 1: "♀"}.get(get("@gender"), "—")
            return {
                "species": sid,
                "name": nm,
                "level": level,
                "exp": exp,
                "ivs": self._stat_hash(get("@iv")),
                "evs": self._stat_hash(get("@ev")),
                "nature": nature,
                "nature_src": nature_src,
                "ability_flag": ab_flag,
                "ability_name": ab_txt,
                "ability_src": ab_src,
                "moves": moves,
                "item": self._item_id(get("@item")),
                "ball": self._item_id(get("@poke_ball")),
                "status": d.status_code_of(get("@status")),
                "happiness": get("@happiness") or 0,
                "eggsteps": get("@steps_to_hatch") or 0,
                "shiny": get("@shiny"),
                "form": get("@form"),
                "ribbons": [ _sym(x) for x in ribbons ] if isinstance(ribbons, list)
                            else ribbons,
                "ot": oi.get("@name") if oi else None,
                "ot_id": oi.get("@id") if oi else None,
                "ot_gender": oi.get("@gender") if oi else None,
                "pid": get("@personalID") or 0,
                "gender": kind,
                "hp": get("@hp"),
                "totalhp": get("@totalhp"),
                "firstmoves": [_sym(x) for x in (get("@first_moves") or [])],
                "obtain": (get("@obtain_method"), get("@obtain_map"),
                           get("@obtain_level"), get("@obtain_text")),
                "hatched_map": get("@hatched_map"),
                "time": get("@timeReceived"),
                "mail": get("@mail"),
                "fused": get("@fused"),
                "markings": get("@markings"),
            }
        # ---- legacy（v16~v18）----
        sid = get("@species")
        exp = get("@exp") or 0
        level_by_exp = level_from_exp(exp, d.growth_rate(sid))
        base = d.base_stats(sid)
        ivs = list(get("@iv") or [0] * 6)
        evs = list(get("@ev") or [0] * 6)
        level_by_hp = level_from_hp(get("@totalhp") or 0, base[0], ivs[0], evs[0])
        level = level_by_hp if level_by_hp else level_by_exp
        nature = get("@natureflag")
        nature_src = "@natureflag"
        if nature is None:
            nature = (get("@personalID") or 0) % 25
            nature_src = "personalID%25（缺省）"
        ab_flag = get("@abilityflag")
        ab_src = "@abilityflag"
        if ab_flag is None:
            ab_flag = (get("@personalID") or 0) % 2
            ab_src = "personalID%2（缺省）"
        moves = []
        for mv in get("@moves") or []:
            mi = getattr(mv, "ivars", None)
            if not isinstance(mi, dict):
                continue
            mid = mi.get("@id")
            if mid in (0, None):
                continue
            moves.append((mid, mi.get("@pp"), mi.get("@ppup")))
        pid = get("@personalID") or 0
        return {
            "species": sid,
            "name": get("@name"),
            "level": level,
            "level_by_exp": level_by_exp,
            "level_by_hp": level_by_hp,
            "exp": exp,
            "ivs": ivs,
            "evs": evs,
            "nature": nature,
            "nature_src": nature_src,
            "ability_flag": ab_flag,
            "ability_src": ab_src,
            "moves": moves,
            "item": get("@item") or 0,
            "ball": get("@ballused") or 0,
            "status": get("@status") or 0,
            "happiness": get("@happiness") or 0,
            "eggsteps": get("@eggsteps") or 0,
            "shiny": get("@shinyflag"),
            "form": get("@form"),
            "ribbons": get("@ribbons"),
            "ot": get("@ot"),
            "ot_id": get("@trainerID"),
            "ot_gender": get("@otgender"),
            "pid": pid,
            "gender": gender_of(pid, d.gender_rate(sid)),
            "hp": get("@hp"),
            "totalhp": get("@totalhp"),
            "firstmoves": [d.move(x) for x in (get("@firstmoves") or [])],
            "obtain": (get("@obtainMode"), get("@obtainMap"),
                       get("@obtainLevel"), get("@obtainText")),
            "hatched_map": get("@hatchedMap"),
            "time": get("@timeReceived"),
            "mail": get("@mail"),
            "fused": get("@fused"),
            "markings": get("@markings"),
        }

    def read_pokemon(self, pm: Any) -> dict:
        """
        格式无关的宝可梦读取（界面用这个，别去直接翻 ivar）。

        legacy 的 `@species` 是数字、`@iv` 是数组；v19+ 的 `@species` 是 Symbol、
        `@iv` 是 Hash、`@item` 也是 Symbol —— 界面统一从这里的返回值里取，
        就不用管是哪一代了。
        """
        return self._read_pokemon(pm)

    def pokemon(self, pm: Any, slot: str = "") -> dict:
        """一只宝可梦的可读结构（两代存档共用同一套输出）。"""
        d = self.data
        iv = pm.ivars
        r = self._read_pokemon(pm)
        sp = r["species"]
        form = r.get("form") or 0
        info = d.species_info(sp, form) if sp is not None else {}
        base_stats = d.base_stats(sp, form) if sp is not None else [1] * 6
        rate = d.growth_rate(sp, form) if sp is not None else "Medium"
        level = r["level"]
        nature = r["nature"]
        ivs, evs = r["ivs"], r["evs"]
        nickname = r.get("name") or iv.get("@name")
        # ★ 走 d.tr()：术语字典里译过的名字要生效（info["Name"] 是 .dat 原文）
        sp_name = ("（未知）" if sp is None
                   else (d.tr(info.get("Name")) or d.species(sp)))
        stored = [iv.get(k) for k in STAT_IVARS]
        recomputed = calc_stats(base_stats, level, ivs, evs, nature)
        # 有些 v19+ 作品不缓存能力值（读档时现算）—— 那就直接显示算出来的
        stats_cached = not all(v is None for v in stored)
        if not stats_cached:
            stored = list(recomputed)
        lang = iv.get("@language")
        if self.fmt == "hash" and isinstance(iv.get("@owner"), rmarshal.RObject):
            lang = iv["@owner"].ivars.get("@language", lang)

        abilities = d.abilities_of(sp, form) if sp is not None else []
        ab_flag = r["ability_flag"]
        ab_internal = None
        if isinstance(ab_flag, int) and 0 <= ab_flag < len(abilities):
            ab_internal = abilities[ab_flag]
        elif isinstance(ab_flag, int) and abilities:
            ab_internal = abilities[-1]      # 越界（比如只有 1 个特性却要第 2 个）
        ab_name = r.get("ability_name") or (
            d.ability_name(ab_internal) if ab_internal
            else (f"第{(ab_flag or 0) + 1}特性" if isinstance(ab_flag, int)
                  else str(ab_flag)))

        shows = []
        for mid, pp, _up in r["moves"]:
            if mid in (None, 0):
                continue
            shows.append({"招式": d.move(mid), "招式ID": mid, "PP": pp,
                          "PPUP等级": _up})

        ribbons = r["ribbons"]
        if isinstance(ribbons, list):
            ribbons = [x for x in ribbons]

        shiny = is_shiny(r["pid"], r["ot_id"] or 0, r["shiny"]) \
            if r["shiny"] is None else bool(r["shiny"])

        return {
            "位置": slot,
            "全国图鉴编号": sp,
            "宝可梦": sp_name,
            "昵称": nickname,
            "相同与否": ("同名" if nickname in (None, "") or nickname == sp_name
                       else "已改名"),
            "等级": level,
            "等级来源": ("存档直接存的" if self.fmt == "hash" else
                       ("HP反推" if r.get("level_by_hp")
                        and r["level_by_hp"] != r.get("level_by_exp") else "经验值")),
            "等级_按经验": r.get("level_by_exp", level),
            "等级_按HP": r.get("level_by_hp"),
            "经验值": r["exp"],
            "距下一级经验": (growth_exp(min(level, 99) + 1, rate) - r["exp"])
                            if level < 100 else 0,
            "性格": d.nature_name(nature) if 0 <= nature < 25 else str(nature),
            "性格EN": NATURES_EN[nature] if 0 <= nature < 25 else str(nature),
            "性格取值来源": r["nature_src"],
            "特性": ab_name,
            "特性序号": ab_flag,
            "特性取值来源": r["ability_src"],
            "性别": r["gender"],
            "异色": shiny,
            "形态": r["form"],
            "HP": f"{r['hp']}/{r['totalhp']}",
            "能力值": {STAT_KEYS[i]: stored[i] for i in range(6)},
            "能力值_重算校验": {STAT_KEYS[i]: recomputed[i] for i in range(6)},
            "校验一致": (stored == recomputed) or not stats_cached,
            "能力值已缓存": stats_cached,
            "个体值IV": {STAT_KEYS[i]: ivs[i] for i in range(6)},
            "努力值EV": {STAT_KEYS[i]: evs[i] for i in range(6)},
            "性格加成": {STAT_KEYS[i]: nature_boost(nature, i) for i in range(1, 6)
                     if nature_boost(nature, i)},
            "携带道具": d.item(r["item"]),
            "携带道具ID": r["item"],
            "捕获用球": d.item(r["ball"]),
            "状态": STATUS_NAMES.get(r["status"], str(r["status"])),
            "状态回合": iv.get("@statusCount"),
            "亲密度": r["happiness"],
            "孵蛋步数": r["eggsteps"],
            "语种": lang,
            "初训家": r["ot"],
            "初训家性别": ("♀" if r["ot_gender"] == 1 else
                        "♂" if r["ot_gender"] == 0 else "—"),
            "训练家ID": r["ot_id"],
            "个体ID": r["pid"],
            "初训技能": r["firstmoves"],
            "获得方式": r["obtain"][0],
            "获得地图": r["obtain"][1],
            "获得等级": r["obtain"][2],
            "孵化地图": r["hatched_map"],
            "获得时间": stamp_text(r["time"]),
            "融合对象": r["fused"],
            "邮件": r["mail"],
            "标记": r["markings"],
            "勋章": ribbons,
            "其余字段": {k: to_plain(v) for k, v in iv.items()
                      if k not in {"@species", "@name", "@exp", "@ev", "@iv",
                                   "@moves", "@item", "@ballused", "@status",
                                   "@hp", "@personalID", "@trainerID", "@ot",
                                   "@firstmoves", "@level", "@nature",
                                   "@ability_index", "@ability", "@shiny",
                                   "@poke_ball", "@steps_to_hatch", "@owner",
                                   "@happiness", "@form", "@ribbons"}},
            "__对象": pm,          # ★ 保留引用，改的时候直接用它
        }

    # -- 主角 -------------------------------------------------------------
    def _dex_ids(self, h: Any) -> List[int]:
        """
        图鉴的「已见 / 已捕获」。

        legacy 是 `Array(true/false)`，下标就是全国编号；
        v19+ 是 `Hash{Symbol(物种) => true}` —— 得先换算成编号。
        """
        if isinstance(h, rmarshal.RHash):
            out = []
            for k, v in h.pairs:
                if not v:
                    continue
                sid = self.data.species_id_of(_sym(k))
                if sid is not None:
                    out.append(sid)
            return sorted(set(out))
        if isinstance(h, list):
            return [i for i, v in enumerate(h) if v]
        return []

    def dex_flags(self, which: str) -> List[bool]:
        """按编号排的布尔表（现代格式按最大编号铺开，够界面显示数量）。"""
        tr = self.g("$Trainer")
        iv = tr.ivars
        if self.fmt == "hash":
            dex = iv.get("@pokedex")
            di = dex.ivars if isinstance(dex, rmarshal.RObject) else {}
            ids = set(self._dex_ids(di.get("@seen" if which == "seen"
                                            else "@owned")))
            n = max(self.data._species) + 1 if self.data._species else 1000
            return [(i in ids) for i in range(n)]
        arr = iv.get("@seen" if which == "seen" else "@owned")
        return [bool(x) for x in arr] if isinstance(arr, list) else []

    def trainer(self) -> dict:
        tr = self.g("$Trainer")
        iv = tr.ivars
        if self.fmt == "hash":
            seen = self._dex_ids(
                (iv.get("@pokedex").ivars if isinstance(
                    iv.get("@pokedex"), rmarshal.RObject) else {}).get("@seen"))
            own = self._dex_ids(
                (iv.get("@pokedex").ivars if isinstance(
                    iv.get("@pokedex"), rmarshal.RObject) else {}).get("@owned"))
            ttype = iv.get("@trainer_type")
            tname = (self.data.trainer_type_name_of(ttype)
                     if ttype is not None else "")
            party = [self.pokemon(p, f"队伍第{idx + 1}位")
                     for idx, p in enumerate(iv.get("@party") or [])
                     if not self.empty_slot(p)]
            skip = {"@name", "@money", "@party", "@id", "@badges", "@pokedex",
                    "@trainer_type", "@outfit", "@language", "@coins"}
            return {
                "名字": iv.get("@name"),
                "训练家ID": iv.get("@id"),
                "训练家类型": tname,
                "训练家类型ID": self.data.trainer_type_id_of(ttype),
                "持有金钱": iv.get("@money"),
                "已获得图鉴": bool(iv.get("@has_pokedex")),
                "服装编号": iv.get("@outfit"),
                "语种": iv.get("@language"),
                "徽章数量": sum(1 for b in (iv.get("@badges") or []) if b),
                "徽章明细": iv.get("@badges"),
                "图鉴已见数": len(seen),
                "图鉴已捕获数": len(own),
                "图鉴已见清单": [{"编号": i, "名称": self.data.species(i)}
                             for i in seen],
                "图鉴已捕获清单": [{"编号": i, "名称": self.data.species(i)}
                              for i in own],
                "队伍": party,
                "其余字段": {k: to_plain(v) for k, v in iv.items()
                          if k not in skip},
                "存档格式": "hash（v19+）",
                "__对象": tr,
            }
        dex_seen = iv.get("@seen") or []
        dex_own = iv.get("@owned") or []
        seen = [i for i, v in enumerate(dex_seen) if v]
        own = [i for i, v in enumerate(dex_own) if v]
        party = [self.pokemon(p, f"队伍第{idx + 1}位")
                 for idx, p in enumerate(iv.get("@party") or [])]
        return {
            "名字": iv.get("@name"),
            "训练家ID": iv.get("@id"),
            "训练家类型": self.data.trainer_type(iv.get("@trainertype")),
            "训练家类型ID": iv.get("@trainertype"),
            "持有金钱": iv.get("@money"),
            "已获得图鉴": bool(iv.get("@pokedex")),
            "服装编号": iv.get("@outfit"),
            "语种": iv.get("@language"),
            "徽章数量": sum(1 for b in (iv.get("@badges") or []) if b),
            "徽章明细": iv.get("@badges"),
            "图鉴已见数": len(seen),
            "图鉴已捕获数": len(own),
            "图鉴已见清单": [{"编号": i, "名称": self.data.species(i)} for i in seen],
            "图鉴已捕获清单": [{"编号": i, "名称": self.data.species(i)} for i in own],
            "队伍": party,
            "其余字段": {k: to_plain(v) for k, v in iv.items()
                      if k not in {"@name", "@money", "@party", "@id", "@badges",
                                   "@seen", "@owned", "@pokedex", "@trainertype"}},
            "存档格式": "legacy（v16~v18，15 个流）",
            "__对象": tr,
        }

    # -- 背包 -------------------------------------------------------------
    # 现代存档里「道具」是 Symbol（:POTION），legacy 是数字编号 —— 统一成数字
    def _item_id(self, v: Any) -> int:
        if v is None or isinstance(v, bool):
            return 0
        if isinstance(v, int):
            return v
        if isinstance(v, rmarshal.RSymbol):
            return self.data.item_id_of(v.name) or 0
        if isinstance(v, str):
            i = self.data.item_id_of(v)
            if i is not None:
                return i
            return int(v) if v.lstrip("-").isdigit() else 0
        return 0

    def item_id_of(self, v: Any) -> int:
        """道具（Symbol / 字符串 / 数字）→ 编号。界面用这个，别直接翻 pair[0]。"""
        return self._item_id(v)

    def unlock_all_forms(self) -> int:
        """
        形态图鉴「全开」。返回动过的记录条数（0 表示这作品没有形态图鉴字段）。

        legacy：`@formseen` / `@formlastseen`（数组）
        v19+ ：Pokedex 的 `@seen_forms`（Hash{物种 => [[[...]], [[...]]]}）
        """
        tr = self.g("$Trainer")
        n = 0
        for key in ("@formseen", "@formlastseen"):
            arr = tr.ivars.get(key)
            if isinstance(arr, list):
                for i, v in enumerate(arr):
                    if isinstance(v, list):
                        for j in range(len(v)):
                            v[j] = True
                        n += 1
                    elif v is not None:
                        arr[i] = True
                        n += 1
        if self.fmt == "hash":
            dex = tr.ivars.get("@pokedex")
            if isinstance(dex, rmarshal.RObject):
                h = dex.ivars.get("@seen_forms")
                if isinstance(h, rmarshal.RHash):
                    for i in range(len(h.pairs)):
                        k, v = h.pairs[i]
                        if isinstance(v, list):
                            for part in v:
                                if isinstance(part, list):
                                    for sub in part:
                                        if isinstance(sub, list):
                                            for j in range(len(sub)):
                                                sub[j] = True
                                                n += 1
                                        else:
                                            n += 1
                            n += 1
        return n

    @staticmethod
    def _pocket_kind(poc: Any) -> str:
        """口袋的存法：数组式 [[道具, 数量], …] / Hash 式 {道具 => 数量}。"""
        if isinstance(poc, rmarshal.RHash):
            return "hash"
        if isinstance(poc, list):
            return "array"
        return "none"

    def pocket_entries(self, index: int) -> List[Tuple[int, int]]:
        """口袋内容 [(道具编号, 数量)] —— 两种存法都归一成这个，界面用。"""
        pockets = self.g("$PokemonBag").ivars.get("@pockets") or []
        if not (0 <= index < len(pockets)):
            return []
        poc = pockets[index]
        kind = self._pocket_kind(poc)
        out: List[Tuple[int, int]] = []
        if kind == "array":
            for pair in poc:
                if isinstance(pair, list) and len(pair) >= 2:
                    out.append((self._item_id(pair[0]), pair[1]))
        elif kind == "hash":
            for k, v in poc.pairs:
                out.append((self._item_id(k), v))
        return out

    def bag(self) -> dict:
        bg = self.g("$PokemonBag")
        iv = bg.ivars
        pockets = []
        for idx, poc in enumerate(iv.get("@pockets") or []):
            kind = self._pocket_kind(poc)
            if kind == "none":
                continue
            rows = [{"道具": self.data.item(iid), "道具ID": iid, "数量": cnt}
                    for iid, cnt in self.pocket_entries(idx)]
            if not rows:
                continue
            pockets.append({
                "口袋编号": idx,
                "口袋名称": self.data.pocket_name(idx),
                "物品数": len(rows),
                "物品": rows,
            })
        if self.fmt == "hash":
            reg = iv.get("@registered_items")
            reg_id = self._item_id(reg[0]) if isinstance(reg, list) and reg else 0
            return {
                "登记道具": self.data.item(reg_id),
                "登记道具ID": reg_id,
                "登记道具原始": to_plain(reg),
                "上次打开口袋": self.data.pocket_name(
                    iv.get("@last_viewed_pocket") or 0),
                "各口袋选择位置": iv.get("@last_pocket_selections"),
                "口袋": pockets,
                "__对象": bg,
            }
        return {
            "登记道具": self.data.item(iv.get("@registeredItem")),
            "登记道具ID": iv.get("@registeredItem"),
            "上次打开口袋": self.data.pocket_name(iv.get("@lastpocket") or 0),
            "各口袋选择位置": iv.get("@choices"),
            "口袋": pockets,
            "__对象": bg,
        }

    # =====================================================================
    # 编辑（写操作）
    #   ★ 一条铁律：改过 IV / EV / 性格 / 等级 / 种族 / 形态 之后，六项能力值
    #     必须重算 —— 游戏读档时**不会**重算（只有升级/进化才会），
    #     不重算就会出现「个体值 31 但面板还是老数值」。
    # =====================================================================
    # -- 主角 -------------------------------------------------------------
    TRAINER_FIELDS = {
        "name": "@name", "money": "@money", "id": "@id",
        "outfit": "@outfit", "language": "@language",
        "trainertype": "@trainertype",
    }

    def set_trainer(self, **fields) -> None:
        """
        改主角通用字段。可用键：
          name 名字 / money 金钱 / id 训练家ID / badges 徽章(list[bool])
          outfit 服装 / language 语种 / trainertype 训练家类型 / pokedex 是否已有图鉴
        """
        iv = self.g("$Trainer").ivars
        modern = self.fmt == "hash"
        for k, v in fields.items():
            if k == "badges":
                # ★ 有些作品徽章不止 8 个（也有少于 8 个的）：
                #   原样保留 @badges 的长度，只覆盖界面上能勾的那几个。
                cur = iv.get("@badges")
                flags = [bool(x) for x in v]
                n = len(cur) if isinstance(cur, list) and cur else 8
                if len(flags) < n:
                    flags = flags + [False] * (n - len(flags))
                iv["@badges"] = flags
            elif k == "name":
                iv["@name"] = rmarshal.RStr(str(v))
            elif k == "pokedex":
                # v19+ 名字变成 @has_pokedex
                iv["@has_pokedex" if modern else "@pokedex"] = bool(v)
            elif k == "trainertype":
                if modern:
                    iv["@trainer_type"] = rmarshal.RSymbol(
                        self.data.trainer_type_internal(v))
                else:
                    iv["@trainertype"] = int(v)
            elif k in ("money", "id", "outfit", "language"):
                iv["@" + k] = int(v)
            else:
                raise KeyError(f"不认识的字段：{k}")

    def badges(self) -> List[bool]:
        """8 个徽章（不足 8 个时补 False；多出来的（v19+ 有 8 个以上）保留）。"""
        arr = [bool(x) for x in (self.g("$Trainer").ivars.get("@badges") or [])]
        return arr if len(arr) > 8 else (arr + [False] * 8)[:8]

    def set_badge(self, index: int, on: bool) -> None:
        arr = self.badges()
        if index >= len(arr):
            arr.extend([False] * (index + 1 - len(arr)))
        if 0 <= index < len(arr):
            arr[index] = bool(on)
        self.g("$Trainer").ivars["@badges"] = arr

    def _dex_hash(self, create: bool = False) -> Any:
        """现代格式的 Player::Pokedex 对象（拿不到就返回 None）。"""
        dex = self.g("$Trainer").ivars.get("@pokedex")
        return dex if isinstance(dex, rmarshal.RObject) else None

    def set_dex(self, which: str, ids=None, value: bool = True) -> None:
        """
        图鉴勾选。which = "seen"（已见）/ "owned"（已捕获）。
        ids=None → 全选 / 全清。
        """
        iv = self.g("$Trainer").ivars
        key = "@seen" if which == "seen" else "@owned"

        if self.fmt == "hash":
            dex = self._dex_hash()
            if dex is None:
                return
            h = dex.ivars.get(key)
            if not isinstance(h, rmarshal.RHash):
                h = rmarshal.RHash()
                dex.ivars[key] = h
            if ids is None:
                if not value:
                    for i in range(len(h.pairs)):
                        k, _v = h.pairs[i]
                        h.pairs[i] = (k, False)
                    return
                # ★ 全部勾上：光翻现有的键不够 —— 图鉴是空的时候一条都没有，
                #   得按物种表把缺的补进去（这才是玩家点的「全勾」的意思）。
                have = {}
                for k, _v in h.pairs:
                    have[GameData._norm_internal(_sym(k))] = k
                for sid in sorted(self.data._species):
                    internal = self.data.species_internal(sid)
                    key_n = GameData._norm_internal(internal)
                    if key_n in have or not internal:
                        continue
                    h.pairs.append((rmarshal.RSymbol(internal), True))
                for i in range(len(h.pairs)):
                    k, _v = h.pairs[i]
                    h.pairs[i] = (k, True)
                return
            want = {}
            for sid in ids:
                internal = self.data.species_internal(sid)
                want[GameData._norm_internal(internal)] = (int(sid), internal)
            for i in range(len(h.pairs)):
                k, _v = h.pairs[i]
                key_n = GameData._norm_internal(_sym(k))
                if key_n in want:
                    h.pairs[i] = (k, bool(value))
                    want.pop(key_n)
            if value:
                for _n, (_sid, internal) in want.items():
                    h.pairs.append((rmarshal.RSymbol(internal), True))
            return

        arr = iv.get(key)
        if not isinstance(arr, list):
            n = (max(self.data._species) + 1) if self.data._species else 900
            arr = [False] * n
            iv[key] = arr
        if ids is None:
            for i in range(len(arr)):
                arr[i] = bool(value)
            return
        ids = [int(i) for i in ids]
        while len(arr) <= max(ids, default=0):
            arr.append(False)
        for i in ids:
            if 0 <= i < len(arr):
                arr[i] = bool(value)

    # -- 宝可梦 -----------------------------------------------------------
    def party(self) -> list:
        """★ 只读：不要用 setdefault，光是打开页面就把空 @party 写进存档了。"""
        return self.g("$Trainer").ivars.get("@party") or []

    def boxes(self) -> list:
        return self.g("$PokemonStorage").ivars.get("@boxes") or []

    def box_slots(self, box_index: int) -> list:
        boxes = self.boxes()
        if not (0 <= box_index < len(boxes)):
            return []
        return boxes[box_index].ivars.get("@pokemon") or []

    def _ensure_party(self) -> list:
        return self.g("$Trainer").ivars.setdefault("@party", [])

    def _ensure_boxes(self) -> list:
        return self.g("$PokemonStorage").ivars.setdefault("@boxes", [])

    def _ensure_box_slots(self, box_index: int) -> list:
        boxes = self._ensure_boxes()
        while len(boxes) <= box_index:
            boxes.append(rmarshal.RHash())
        return boxes[box_index].ivars.setdefault("@pokemon", [])

    @staticmethod
    def empty_slot(pm: Any) -> bool:
        """空格：nil / false / 数字（Essentials 的空格有时存成 false）。"""
        return pm is None or isinstance(pm, (bool, int, float))

    def clone_pokemon(self, src: Any = None) -> Any:
        """
        复制一只宝可梦（经 Marshal 往返做深拷贝）。

        找不到可参照的样本就返回 None —— 新建宝可梦必须有「模板」才能保证
        字段齐全，宁可不做，也不生成缺字段的对象（游戏读档会炸）。
        """
        if src is None:
            pool = [p for p in self.party() if not self.empty_slot(p)]
            if not pool:
                for bi in range(len(self.boxes())):
                    pool = [p for p in self.box_slots(bi) if not self.empty_slot(p)]
                    if pool:
                        break
            if not pool:
                return None
            src = pool[0]
        return rmarshal.loads(rmarshal.dumps(src))

    def recalc_pokemon(self, pm: Any,
                       base_override: Optional[List[int]] = None) -> List[int]:
        """
        按当前 IV / EV / 性格 / 经验（等级）重算六项能力值并写回。

        返回 [HP, 攻击, 防御, 速度, 特攻, 特防]。
        ★ 改完 IV/EV/性格/等级/种族/形态 都要调它。
        """
        ivs = pm.ivars
        modern = self.fmt == "hash"
        sid = self._species_id(ivs.get("@species")) if modern \
            else ivs.get("@species")
        form = ivs.get("@form") or 0
        base = list(base_override) if base_override else \
            self.data.base_stats(sid, form)
        rate = self.data.growth_rate(sid, form)
        if modern:
            ivs_list = self._stat_hash(ivs.get("@iv"))
            evs_list = self._stat_hash(ivs.get("@ev"))
            level = ivs.get("@level")
            if not isinstance(level, int) or level < 1:
                level = level_from_exp(ivs.get("@exp") or 0, rate)
                ivs["@level"] = level
            nature = self.data.nature_index_of(ivs.get("@nature"))
            if nature is None:
                nature = (ivs.get("@personalID") or 0) % 25
        else:
            ivs_list = list(ivs.get("@iv") or [0] * 6)
            evs_list = list(ivs.get("@ev") or [0] * 6)
            level = level_from_exp(ivs.get("@exp") or 0, rate)
            nature = ivs.get("@natureflag")
            if nature is None:
                nature = (ivs.get("@personalID") or 0) % 25
        stats = calc_stats(base, level, ivs_list, evs_list, nature)

        # ★ v19+ 有的作品不缓存能力值（读档现算）—— 那种就别硬塞进去，
        #   只更新本来就有缓存的那一份，免得凭白改写存档。
        cached = (not modern) or any(ivs.get(k) is not None for k in STAT_IVARS)
        if cached:
            for k, v in zip(STAT_IVARS, stats):
                ivs[k] = v
        hp = ivs.get("@hp")
        total = stats[0]
        if isinstance(hp, int):
            if hp > total:
                ivs["@hp"] = total
            elif hp < 0:
                ivs["@hp"] = 0
        elif cached:
            ivs["@hp"] = total
        return stats

    # 编辑界面上的字段名 → ivar（数值型；字符串型的在下面单独处理）
    POKEMON_FIELDS = {
        "种族": "@species", "经验": "@exp",
        "性格": "@natureflag", "特性": "@abilityflag", "携带道具": "@item",
        "状态": "@status", "亲密度": "@happiness", "捕获用球": "@ballused",
        "孵蛋步数": "@eggsteps", "形态": "@form",
        "训练家ID": "@trainerID", "个体ID": "@personalID",
    }
    RECALC_FIELDS = {"种族", "经验", "性格", "形态", "等级", "个体值", "努力值"}

    def set_pokemon(self, pm: Any, key: str, value: Any, recalc: bool = True) -> bool:
        """
        改单只宝可梦的一个字段（改完自动重算能力值）。返回是否重算了。

        key 就是编辑界面上的字段名：昵称 / 种族 / 等级 / 经验 / 个体值 / 努力值 /
        性格 / 特性 / 当前HP / 招式 / 携带道具 / 状态 / 亲密度 / 异色 /
        捕获用球 / 孵蛋步数 / 形态 / 勋章 / 初训家 / 训练家ID / 个体ID

        ★ 两代存档的字段名完全不一样（v19+ 的种族是 Symbol、IV/EV 是 Hash），
          所以这里只做分派，具体写法在下面两个方法里。
        """
        if self.fmt == "hash":
            need = self._set_pokemon_modern(pm, key, value)
        else:
            need = self._set_pokemon_legacy(pm, key, value)
        if need and recalc:
            self.recalc_pokemon(pm)
        return need

    def _set_pokemon_modern(self, pm: Any, key: str, value: Any) -> bool:
        """v19+ 的写法（Symbol / Hash）。"""
        ivs = pm.ivars
        d = self.data
        need = False
        if key == "昵称":
            nm = str(value).strip()
            # v19 里 @name = nil 表示「显示种族名」；空名字/同名都存回 nil
            sp_name = d.species(self._species_id(ivs.get("@species")))
            ivs["@name"] = None if nm in ("", sp_name) else rmarshal.RStr(nm)
        elif key == "初训家":
            owner = ivs.get("@owner")
            if isinstance(owner, rmarshal.RObject):
                owner.ivars["@name"] = rmarshal.RStr(str(value))
        elif key == "种族":
            ivs["@species"] = rmarshal.RSymbol(d.species_internal(int(value)))
            need = True
        elif key in ("等级", "经验"):
            sid = self._species_id(ivs.get("@species"))
            rate = d.growth_rate(sid, ivs.get("@form") or 0)
            if key == "等级":
                ivs["@level"] = max(1, min(100, int(value)))
                ivs["@exp"] = growth_exp(ivs["@level"], rate)
            else:
                ivs["@exp"] = max(0, int(value))
                ivs["@level"] = level_from_exp(ivs["@exp"], rate)
            need = True
        elif key == "个体值":
            v = [int(x) for x in list(value)[:6]]
            self._set_stat_hash(ivs.get("@iv"),
                                [max(0, min(31, x)) for x in v] + [0] * (6 - len(v)))
            need = True
        elif key == "努力值":
            v = [int(x) for x in list(value)[:6]]
            self._set_stat_hash(ivs.get("@ev"),
                                [max(0, min(255, x)) for x in v] + [0] * (6 - len(v)))
            need = True
        elif key == "性格":
            ivs["@nature"] = rmarshal.RSymbol(d.nature_symbol(int(value)))
            need = True
        elif key == "特性":
            # v19+ 用 @ability_index（@ability 非空时会盖过它，所以清掉）
            ivs["@ability_index"] = max(0, min(2, int(value)))
            ivs["@ability"] = None
        elif key == "当前HP":
            total = ivs.get("@totalhp")
            hp = int(value)
            ivs["@hp"] = max(0, min(hp, total)) \
                if isinstance(total, int) and total > 0 else max(0, hp)
        elif key == "招式":
            self.set_moves(pm, value)
        elif key == "携带道具":
            ivs["@item"] = rmarshal.RSymbol(d.item_internal(int(value))) \
                if int(value) else None
        elif key == "捕获用球":
            ivs["@poke_ball"] = rmarshal.RSymbol(d.item_internal(int(value))) \
                if int(value) else None
        elif key == "状态":
            st = int(value)
            ivs["@status"] = rmarshal.RSymbol(d.status_symbol(st))
            if st != 1:
                ivs["@statusCount"] = 0
            elif not ivs.get("@statusCount"):
                ivs["@statusCount"] = 1
        elif key == "亲密度":
            ivs["@happiness"] = max(0, min(255, int(value)))
        elif key == "异色":
            ivs["@shiny"] = bool(value)
        elif key == "孵蛋步数":
            ivs["@steps_to_hatch"] = max(0, int(value))
        elif key == "形态":
            ivs["@form"] = int(value)
            need = True
        elif key == "勋章":
            if isinstance(value, str):
                toks = [x.strip() for x in value.replace("，", ",").split(",")
                        if x.strip()]
            else:
                toks = [str(x) for x in value]
            ivs["@ribbons"] = [rmarshal.RSymbol(t.upper()) for t in toks]
        elif key == "训练家ID":
            owner = ivs.get("@owner")
            if isinstance(owner, rmarshal.RObject):
                owner.ivars["@id"] = int(value)
        elif key == "个体ID":
            ivs["@personalID"] = int(value)
        else:
            raise KeyError(f"不认识的字段：{key}")
        return need

    def _set_pokemon_legacy(self, pm: Any, key: str, value: Any) -> bool:
        """v16~v18 的写法（数字编号 / 数组）。"""
        ivs = pm.ivars
        need = False
        if key == "昵称":
            nm = str(value).strip()
            ivs["@name"] = rmarshal.RStr(
                nm or self.data.species(ivs.get("@species")))
        elif key == "初训家":
            ivs["@ot"] = rmarshal.RStr(str(value))
        elif key == "等级":
            rate = self.data.growth_rate(ivs.get("@species"))
            ivs["@exp"] = growth_exp(max(1, min(100, int(value))), rate)
            need = True
        elif key == "个体值":
            v = [int(x) for x in list(value)[:6]]
            ivs["@iv"] = [max(0, min(31, x)) for x in v] + [0] * (6 - len(v))
            need = True
        elif key == "努力值":
            v = [int(x) for x in list(value)[:6]]
            ivs["@ev"] = [max(0, min(255, x)) for x in v] + [0] * (6 - len(v))
            need = True
        elif key == "当前HP":
            total = ivs.get("@totalhp")
            hp = int(value)
            ivs["@hp"] = max(0, min(hp, total)) if isinstance(total, int) else max(0, hp)
        elif key == "招式":
            self.set_moves(pm, value)
        elif key == "状态":
            st = int(value)
            ivs["@status"] = st
            if st != 1:
                ivs["@statusCount"] = 0
            elif not ivs.get("@statusCount"):
                ivs["@statusCount"] = 1
        elif key == "异色":
            ivs["@shinyflag"] = None if value is None else bool(value)
        elif key == "勋章":
            if isinstance(value, str):
                value = [int(x) for x in re.findall(r"-?\d+", value)]
            ivs["@ribbons"] = [int(x) for x in value]
        elif key in self.POKEMON_FIELDS:
            try:
                ivs[self.POKEMON_FIELDS[key]] = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"「{key}」要填数字，收到的是 {value!r}")
            need = key in self.RECALC_FIELDS
        else:
            raise KeyError(f"不认识的字段：{key}")
        return need

    def set_moves(self, pm: Any, moves) -> None:
        """
        设置招式。moves = [(招式编号 or 0, 剩余PP or None), ...]（最多 4 个）。

        没有现成 PBMove 对象时，复制一个来改 `@id` —— 保留全部字段最稳。
        """
        cur = pm.ivars.get("@moves")
        if not isinstance(cur, list):
            cur = []
            pm.ivars["@moves"] = cur
        proto = next((m for m in cur if isinstance(m, rmarshal.RObject)), None)
        want = list(moves)[:4]
        # 招式个数：原样保留，但如果要往后面的空位写新招式就补齐到 4
        n = len(cur)
        if any(i >= n and (want[i][0] if i < len(want) else 0) not in (None, 0)
               for i in range(4)):
            n = 4
        n = max(1, n)
        modern = self.fmt == "hash"
        out = []
        for i in range(n):
            mid, pp = want[i] if i < len(want) else (None, None)
            mv = cur[i] if i < len(cur) and isinstance(cur[i], rmarshal.RObject) else None
            if mv is None and proto is not None:
                mv = rmarshal.loads(rmarshal.dumps(proto))
            if mv is None:
                continue
            if mid in (None, 0):
                # legacy 用 id=0 占位；v19+ 用 nil
                mv.ivars["@id"] = None if modern else 0
                mv.ivars["@pp"] = 0
            else:
                mv.ivars["@id"] = (rmarshal.RSymbol(self.data.move_internal(int(mid)))
                                   if modern else int(mid))
                mv.ivars["@pp"] = int(pp) if pp not in (None, "") \
                    else self.data.move_pp(mid)
            if mv.ivars.get("@ppup") is None:
                mv.ivars["@ppup"] = 0
            out.append(mv)
        pm.ivars["@moves"] = out
        if modern:
            pm.ivars["@first_moves"] = [m.ivars.get("@id") for m in out
                                        if isinstance(m, rmarshal.RObject)
                                        and m.ivars.get("@id") is not None]
        else:
            pm.ivars["@firstmoves"] = [m.ivars.get("@id") for m in out
                                       if isinstance(m, rmarshal.RObject)
                                       and m.ivars.get("@id")]

    # -- 队伍 / 箱子 ------------------------------------------------------
    def add_to_party(self, pm: Any) -> bool:
        party = self._ensure_party()
        if len([p for p in party if not self.empty_slot(p)]) >= 6:
            return False
        party.append(pm)
        return True

    def remove_from_party(self, index: int) -> Any:
        party = self._ensure_party()
        if 0 <= index < len(party):
            return party.pop(index)
        return None

    def add_to_box(self, pm: Any, box_index: int = 0) -> Tuple[int, int]:
        """放进箱子第一个空位。返回 (箱号, 格号)，放不下返回 (-1, -1)。"""
        nboxes = len(self.boxes())
        for bi in range(box_index, nboxes):
            slots = self._ensure_box_slots(bi)
            for i in range(len(slots)):
                if self.empty_slot(slots[i]):
                    slots[i] = pm
                    return bi, i
            if len(slots) < 30:
                slots.append(pm)
                return bi, len(slots) - 1
        return -1, -1

    def remove_from_box(self, box_index: int, slot: int) -> Any:
        slots = self._ensure_box_slots(box_index)
        if 0 <= slot < len(slots):
            pm = slots[slot]
            slots[slot] = None
            return pm
        return None

    def move_box_to_party(self, box_index: int, slot: int) -> bool:
        slots = self.box_slots(box_index)
        pm = slots[slot] if 0 <= slot < len(slots) else None
        if self.empty_slot(pm) or not self.add_to_party(pm):
            return False
        self.remove_from_box(box_index, slot)
        return True

    def rename_box(self, box_index: int, name: str) -> None:
        boxes = self._ensure_boxes()
        if 0 <= box_index < len(boxes):
            boxes[box_index].ivars["@name"] = rmarshal.RStr(str(name))

    # -- 背包 -------------------------------------------------------------
    def pocket(self, index: int) -> list:
        """
        某个口袋的原始条目列表 `[[道具, 数量], ...]`（数组式）。

        ★ Hash 式口袋（少数作品把口袋存成 `{道具 => 数量}`）不会返回列表，
          返回空表；读写都请走 `pocket_entries()` / `set_bag_item()` ——
          那两个两种存法都认。
        ★ 只读：不 setdefault、不补长，看一眼不会把存档改脏。
        """
        pockets = self.g("$PokemonBag").ivars.get("@pockets") or []
        if not (0 <= index < len(pockets)) or not isinstance(pockets[index], list):
            return []
        return pockets[index]

    def set_bag_item(self, pocket_index: int, item_id: int, count: int) -> None:
        """
        设置某口袋某道具的数量（不存在就添加；数量 ≤0 就删除）。

        存档里同一种道具可能被拆成多条（游戏自己的历史遗留），这里统一合并到
        第一条上，避免改完显示两行。
        """
        item_id = int(item_id)
        pockets = self.g("$PokemonBag").ivars.setdefault("@pockets", [])
        while len(pockets) <= pocket_index:
            pockets.append([])
        poc = pockets[pocket_index]
        kind = self._pocket_kind(poc)
        if kind == "none":
            poc = []
            pockets[pocket_index] = poc
            kind = "array"

        # 现代存档里道具是 Symbol（:POTION），比较得先换算成编号
        if kind == "hash":
            hit = [k for k, _v in poc.pairs if self._item_id(k) == item_id]
            if hit:
                if count <= 0:
                    poc.pairs = [(k, v) for k, v in poc.pairs
                                 if self._item_id(k) != item_id]
                else:
                    poc.pairs = [(k, int(count) if self._item_id(k) == item_id else v)
                                 for k, v in poc.pairs]
                return
            if count > 0:
                poc.pairs.append((self._item_key(item_id), int(count)))
            return

        hit = [p for p in poc
               if isinstance(p, list) and len(p) >= 2
               and self._item_id(p[0]) == item_id]
        if hit:
            if count <= 0:
                for p in hit:
                    poc.remove(p)
            else:
                hit[0][1] = int(count)
                for p in hit[1:]:
                    poc.remove(p)
            return
        if count > 0:
            poc.append([self._item_key(item_id), int(count)])

    def _item_key(self, item_id: int) -> Any:
        """编号 → 存档里该用的「道具键」：v19+ 是 Symbol，legacy 是数字。"""
        if self.fmt == "hash":
            return rmarshal.RSymbol(self.data.item_internal(item_id))
        return int(item_id)

    def remove_bag_index(self, pocket_index: int, i: int) -> None:
        """
        按 `pocket_entries()` 的序号删一条。

        ★ 序号要跟 `pocket_entries()` 严格对齐 —— 数组式口袋里可能有残缺条目，
          那些在 `pocket_entries()` 里被跳过，所以要把序号换算回原始下标。
        """
        pockets = self.g("$PokemonBag").ivars.get("@pockets") or []
        if not (0 <= pocket_index < len(pockets)):
            return
        poc = pockets[pocket_index]
        kind = self._pocket_kind(poc)
        if kind == "hash":
            # Hash 式每条都有效，序号即下标
            if 0 <= i < len(poc.pairs):
                del poc.pairs[i]
            return
        if kind != "array":
            return
        seen = 0
        for raw in range(len(poc)):
            pair = poc[raw]
            ok = isinstance(pair, list) and len(pair) >= 2
            if ok and seen == i:
                poc.pop(raw)
                return
            seen += 1 if ok else 0

    def set_pocket_count_by_index(self, pocket_index: int, i: int,
                                  count: int) -> None:
        """按 `pocket_entries()` 的序号改某条的数量（两种存法都支持）。"""
        entries = self.pocket_entries(pocket_index)
        if not (0 <= i < len(entries)):
            return
        self.set_bag_item(pocket_index, entries[i][0], int(count))

    def fill_pocket(self, pocket_index: int, count: int) -> int:
        """把某口袋里所有道具的数量统一设成 count，返回改动条数。"""
        n = 0
        for iid, _cnt in list(self.pocket_entries(pocket_index)):
            self.set_bag_item(pocket_index, iid, int(count))
            n += 1
        return n

    def set_registered_item(self, item_id: int) -> None:
        iv = self.g("$PokemonBag").ivars
        if self.fmt == "hash":
            # v20+ 是 @registered_items 数组（可以登记好几个）
            reg = iv.get("@registered_items")
            sym = rmarshal.RSymbol(self.data.item_internal(int(item_id)))
            if not isinstance(reg, list) or not reg:
                iv["@registered_items"] = [sym] if int(item_id) else []
            else:
                reg[0] = sym
            return
        iv["@registeredItem"] = int(item_id)

    # -- 开关 / 变量 ------------------------------------------------------
    # 「开关与变量」编辑页已删除，这里只保留概览页要用的只读计数。
    # ★ 必须用只读的（`.get`），不能用带 setdefault 的版本 —— 那会让「打开概览」
    #   往存档里塞一个空 @data，把没改动过的存档写脏。
    def switch_peek(self) -> list:
        return self.g("$game_switches").ivars.get("@data") or []

    def variable_peek(self) -> list:
        return self.g("$game_variables").ivars.get("@data") or []

# ===========================================================================
# 存档缓存 / 目录扫描（GUI 用）
# ===========================================================================
# 一次会话里可能有好几个页面同时读同一份存档（主角/队伍/背包…），
# 每次都解析一遍太慢，而且各页面改的是**同一个内存对象**才不会互相覆盖。
_SAVE_CACHE: Dict[str, tuple] = {}


def open_save(path: str, game_root: Optional[str] = None,
              force: bool = False) -> SaveFile:
    """打开存档（同一个文件共用一份内存对象；文件被外部改过会自动重开）。"""
    if not path:
        raise ValueError("没有指定存档文件")
    key = os.path.abspath(path)
    try:
        mtime = os.path.getmtime(key)
    except OSError:
        mtime = None
    hit = _SAVE_CACHE.get(key)
    if hit and not force and hit[0] == mtime and hit[1] is not None:
        return hit[1]
    sv = SaveFile(path, game_root=game_root)
    _SAVE_CACHE[key] = (mtime, sv)
    return sv


def forget_save(path: str) -> None:
    """写回之后刷新缓存里的 mtime（内存里那份仍是最新的）。"""
    key = os.path.abspath(path)
    hit = _SAVE_CACHE.get(key)
    if hit is None:
        return
    try:
        _SAVE_CACHE[key] = (os.path.getmtime(key), hit[1])
    except OSError:
        _SAVE_CACHE.pop(key, None)


# 游戏数据（.dat / PBS）按目录缓存：大作品（species.dat 1.4MB +
# messages.dat 4.7MB）解析一次要好几秒，换个存档不该重来一遍。
_DATA_CACHE: Dict[tuple, "GameData"] = {}
_TERM_CACHE: Dict[str, tuple] = {}          # 术语字典：mtime → {小写原文: 译文}


def term_file() -> str:
    try:
        import config as _cfg
        p = getattr(_cfg, "TERM_FILE", "")
        if p:
            return p
    except Exception:
        pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "term_dict.py")


def load_user_terms(force: bool = False) -> Dict[str, str]:
    r"""
    读「术语字典」里**用户维护的正文条目**，返回 ``{小写原文: 译文}``。

    ★ 用来当游戏数据的显示名 —— 有术语字典（比如 11705 条
      "Bulbasaur"→"妙蛙种子"）时，宝可梦 / 招式 / 道具 / 特性 / 属性 /
      训练家类型 / 性格 都按它显示，而不是 .dat 里的英文原名。

    `@@AUTO_TERMS_START@@` 块里是工具自动提取的，不算「用户手动添加」，
    读的时候会整段剔除。
    """
    path = term_file()
    if not path or not os.path.isfile(path):
        return {}
    try:
        key = (os.path.abspath(path), os.path.getmtime(path))
    except OSError:
        return {}
    hit = _TERM_CACHE.get("k")
    if hit is not None and hit[0] == key and not force:
        return hit[1]
    out: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        # ★ 注意这个尾逗号：少了它就成了「两个字符串」而不是「一个二元组」，
        #   迭代时拆包直接 ValueError（踩过：术语表整份读不出来）
        for start, end in (("@@AUTO_TERMS_START@@", "@@AUTO_TERMS_END@@"),):
            i, j = text.find(start), text.find(end)
            if i != -1 and j > i:
                head = text.rfind("\n", 0, i)
                tail = text.find("\n", j)
                if head != -1 and tail != -1:
                    text = text[:head] + text[tail:]
        ns: Dict[str, Any] = {}
        exec(text, ns)                       # 就是本项目的术语表文件
        for k, v in (ns.get("TERM_DICT") or {}).items():
            if isinstance(k, str) and isinstance(v, str):
                k, v = k.strip(), v.strip()
                if k and v:
                    out.setdefault(k.lower(), v)
    except Exception:
        return {}
    _TERM_CACHE["k"] = (key, out)
    return out


def load_game_data(game_root: str) -> "GameData":
    """游戏数据（按目录 + 术语表版本缓存；术语表改过会自动重读）。"""
    try:
        stamp = _TERM_CACHE.get("k", ((0, 0), None))[0]
    except Exception:
        stamp = 0
    key = (os.path.abspath(game_root or ""), stamp)
    hit = _DATA_CACHE.get(key)
    if hit is None:
        hit = GameData(game_root).load()
        hit.apply_terms(load_user_terms())
        _DATA_CACHE[key] = hit
    return hit


def savestate_dir(game_root: str) -> Optional[str]:
    """游戏的存档目录（Data/Savestates）。"""
    if not game_root:
        return None
    d = os.path.join(game_root, "Data", "Savestates")
    return d if os.path.isdir(d) else None


def savestate_files(game_root: str) -> List[str]:
    """列出游戏里所有 savestate*.rxdata（按名字排序）。"""
    d = savestate_dir(game_root)
    if not d:
        return []
    out = []
    try:
        for f in os.listdir(d):
            if f.lower().endswith(".rxdata") and not f.lower().endswith(".bak"):
                out.append(os.path.join(d, f))
    except OSError:
        return []
    return sorted(out)


def guess_game_root(path: str) -> str:
    """从任意文件/目录往上找游戏根目录（有 Data 目录就算）。"""
    cur = os.path.abspath(path)
    if os.path.isfile(cur):
        cur = os.path.dirname(cur)
    for _ in range(5):
        if os.path.isdir(os.path.join(cur, "Data")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return ""


def normalize_name(text: Any) -> str:
    """目录名比对用：去掉符号与空白、统一小写（中文原样保留）。"""
    s = str(text or "").lower()
    return re.sub(r"[^0-9a-z一-鿿]+", "", s)


def game_title(game_root: str) -> str:
    """
    读 ``Game.ini`` 的 ``[Game] Title=`` —— AppData 里的存档文件夹一般就叫这个。
    """
    if not game_root:
        return ""
    for name in ("Game.ini", "game.ini", "Game.rxproj"):
        p = os.path.join(game_root, name)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
                txt = f.read()
        except OSError:
            continue
        m = re.search(r"^\s*Title\s*=\s*(.+?)\s*$", txt, re.M | re.I)
        if m:
            return m.group(1)
    return ""

