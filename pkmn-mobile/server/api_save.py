# -*- coding: utf-8 -*-
"""
存档编辑接口。

统一用 SaveFile 这一层，**不区分 v16~v18（15 条 Marshal 流）和 v19+/v20/v21
（单条 Hash）** —— 这层抽象 core/save_tools.py 已经做好了（见 SaveFile 类开头
的说明），所以这里只有一套实现。

定位一只宝可梦的方式（locator）：
    "party:3"        同行队伍第 4 只
    "box:2:5"        第 3 个箱子的第 6 格
读写单个字段都用 core 的 set_pokemon(pm, key, value)，它会自动重算六项能力值。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bootstrap  # noqa: E402,F401

# 兄弟模块：按「自己是怎么被导入的」二选一（详见 server/app.py 的说明）
if __package__:
    from . import jsonutil as JU     # noqa: E402
else:
    import jsonutil as JU            # noqa: E402

_POKE_STAT_KEYS = ("HP", "攻击", "防御", "特攻", "特防", "速度")


def _sv(ctx):
    """取出（必要的话先打开）存档对象。"""
    import save_tools as ST
    q = dict(ctx["query"])
    q.update(ctx["body"] or {})
    path = JU.normalize_path(q.get("path"))
    if not path:
        raise ValueError("缺少参数 path（存档文件路径）")
    game_root = JU.normalize_path(q.get("game_root")) or None
    force = bool(q.get("force", False))
    return ST.open_save(path, game_root=game_root, force=force)


def _resolve_pm(sv, where):
    """locator → 原始 ruby 对象。"""
    if not where:
        raise ValueError("缺少参数 where")
    kind, _, rest = str(where).partition(":")
    if kind == "party":
        lst = sv.party()
        i = int(rest)
        if not (0 <= i < len(lst)):
            raise IndexError(f"队伍下标越界：{i}（共 {len(lst)} 只）")
        return lst[i]
    if kind == "box":
        b, _, s = rest.partition(":")
        lst = sv.box_slots(int(b))
        i = int(s)
        if not (0 <= i < len(lst)):
            raise IndexError(f"箱子格位越界：{b}:{i}")
        return lst[i]
    raise ValueError(f"无法识别的位置：{where}")


def _poke_view(sv, pm, slot=""):
    d = sv.pokemon(pm, slot=slot)
    d.pop("__对象", None)          # 带不了借的 ruby 对象引用出去
    return JU.clean(d)


# ------------------------------------------------------------------
# 概要
# ------------------------------------------------------------------
def api_open(ctx):
    sv = _sv(ctx)
    try:
        idx = JU.clean(sv.index())
    except Exception as e:
        idx = {"error": str(e)}
    return JU.ok({
        "path": sv.path.replace("\\", "/"),
        "game_root": (sv.game_root or "").replace("\\", "/"),
        "fmt": getattr(sv, "fmt", "?"),
        "encoding_label": getattr(sv, "encoding_label", ""),
        "index": idx,
    })


def api_index(ctx):
    sv = _sv(ctx)
    return JU.ok({"index": JU.clean(sv.index())})


def api_roundtrip(ctx):
    sv = _sv(ctx)
    try:
        return JU.ok({"roundtrip_ok": bool(sv.roundtrip_ok())})
    except Exception as e:
        return JU.err(f"校验失败：{e}")


# ------------------------------------------------------------------
# 主角
# ------------------------------------------------------------------
def api_trainer(ctx):
    sv = _sv(ctx)
    return JU.ok({"trainer": JU.clean(sv.trainer())})


def api_set_trainer(ctx):
    sv = _sv(ctx)
    fields = dict(ctx["body"].get("fields") or {})
    if not fields:
        return JU.err("没有要改的字段")
    sv.set_trainer(**fields)
    return JU.ok({"changed": list(fields)})


def api_badges(ctx):
    sv = _sv(ctx)
    return JU.ok({"badges": JU.clean(sv.badges())})


def api_set_badge(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    sv.set_badge(int(body.get("index")), bool(body.get("on", True)))
    return JU.ok({"changed": True})


def api_set_dex(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    which = body.get("which", "seen")
    if body.get("all") is True:
        sv.set_dex(which, None, bool(body.get("value", True)))
    else:
        sv.set_dex(which, list(body.get("ids") or []),
                   bool(body.get("value", True)))
    return JU.ok({"changed": True})


# ------------------------------------------------------------------
# 宝可梦
# ------------------------------------------------------------------
def api_party(ctx):
    sv = _sv(ctx)
    out = []
    for i, pm in enumerate(sv.party()):
        if sv.empty_slot(pm):
            out.append({"slot": f"party:{i}", "empty": True})
        else:
            out.append({"slot": f"party:{i}", "empty": False,
                        **_poke_view(sv, pm, slot=f"队伍{i + 1}")})
    return JU.ok({"party": out})


def api_boxes(ctx):
    sv = _sv(ctx)
    q = dict(ctx["query"]); q.update(ctx["body"] or {})
    boxes = sv.boxes()
    want = q.get("box")
    try:
        want_i = int(want) if want is not None else None
    except ValueError:
        return JU.err(f"box 不是数字：{want}")

    def one(i):
        slots = []
        for j, pm in enumerate(sv.box_slots(i)):
            if sv.empty_slot(pm):
                slots.append({"slot": f"box:{i}:{j}", "empty": True})
            else:
                slots.append({"slot": f"box:{i}:{j}", "empty": False,
                              **_poke_view(sv, pm, slot=f"{i + 1}-{j + 1}")})
        return {"index": i, "slots": slots}

    if want_i is not None:
        return JU.ok({"box": one(want_i)})
    return JU.ok({"boxes": [{"index": i, "count": len(sv.box_slots(i))}
                            for i in range(len(boxes))]})


def api_set_pokemon(ctx):
    """改单个字段；改 种族/等级/个体值/努力值 会自动重算能力值。

    ★ 种族 / 携带道具 / 捕获用球 允许传**手输文本**（内部名或编号），
      这里先用 GameData 解析成编号 —— 和电脑版「下拉里找不到就自己填」一致。
      解析不了会报错并提示必须用英文内部名或编号。
    """
    sv = _sv(ctx)
    body = ctx["body"]
    pm = _resolve_pm(sv, body.get("where"))
    key = body.get("key")
    if not key:
        return JU.err("缺少参数 key")
    value = body.get("value")
    if isinstance(value, str):
        txt = value.strip()
        if txt in ("（无）", "（未知）", "无", ""):
            value = 0
        # ★ 其余一律交给 core 去认：编号 / 英文内部名 / 显示名都能认，
        #   认不出来 core 会给出「必须用内部名」的明确报错（见 save_tools）。
    try:
        # ★ set_pokemon 的返回值是「要不要重算能力值」，**不是**成功与否 ——
        #   昵称 / 携带道具 这类字段本来就返回 False。以前把它当失败判断，
        #   于是这些字段一改就报「字段不可改或不支持」。未知字段才抛 KeyError。
        sv.set_pokemon(pm, key, value,
                       recalc=bool(body.get("recalc", True)),
                       sync_nick=bool(body.get("sync_nick", True)))
    except KeyError as e:
        return JU.err(f"字段不可改或不支持：{key}（{e}）")
    except (TypeError, ValueError) as e:
        return JU.err(str(e))
    return JU.ok({"where": body.get("where"), "key": key,
                  "value": JU.clean(value)})


def api_pokemon(ctx):
    """读单只宝可梦（locator → 详情）—— 详情页用。"""
    sv = _sv(ctx)
    q = dict(ctx["query"]); q.update(ctx["body"] or {})
    pm = _resolve_pm(sv, q.get("where"))
    return JU.ok({"where": q.get("where"), "pokemon": _poke_view(sv, pm,
                                                                slot=q.get("where"))})


def api_abilities(ctx):
    """某只宝可梦可选的特性（编号 + 名字）—— 给移动端填「特性」用。"""
    sv = _sv(ctx)
    q = dict(ctx["query"]); q.update(ctx["body"] or {})
    pm = _resolve_pm(sv, q.get("where"))
    r = sv.read_pokemon(pm)
    sid, form = r.get("species"), r.get("form") or 0
    names = sv.data.abilities_of(sid, form) if sid is not None else []
    out = []
    for i, internal in enumerate(names):
        out.append({"index": i, "internal": str(internal),
                    "name": sv.data.ability_name(internal) or str(internal)})
    return JU.ok({"abilities": out, "current": r.get("ability_flag")})


def api_resolve(ctx):
    """把「手输文本」解析成取值（内部名 / 显示名 / 编号都认）。

    ★ 与电脑版同一套规则（save_tools.GameData.find_* / *_by_name）。
      没选游戏数据时这些解析器认不出来 —— 前端会提示「请填英文内部名」，
      而真正写入时 core 仍允许直接按内部名写（现代存档本来就是 Symbol）。
    """
    sv = _sv(ctx)
    q = dict(ctx["query"]); q.update(ctx["body"] or {})
    kind = q.get("kind") or "species"
    txt = (q.get("text") or "").strip()
    d = sv.data
    if not txt:
        return JU.err("没填内容")
    if kind in ("species", "item", "move"):
        f = {"species": d.find_species, "item": d.find_item,
             "move": d.find_move}[kind]
        got = f(txt)
    elif kind == "nature":
        got = d.nature_index_by_name(txt)
    elif kind == "status":
        got = d.status_code_by_name(txt)
    elif kind == "trainer_type":
        got = d.find_trainer_type(txt)
    elif kind == "ability":
        where = q.get("where")
        if where:
            pm = _resolve_pm(sv, where)
            got = sv._ability_index_for(pm, txt)
        else:
            got = d.find_ability(txt)
    else:
        return JU.err(f"未知的类型：{kind}")
    if got is None:
        # ★ 没选游戏数据时对照表读不到 —— 但现代存档（v19+）的物种/道具/
        #   招式/特性/训练家类型本来就是 Symbol，可以直接按**内部名**写。
        #   这里把原文原样返回，前端原样提交，core 会按内部名处理。
        import save_tools as ST
        if sv.fmt == "hash" and ST.looks_internal(txt):
            return JU.ok({"kind": kind, "text": txt, "id": txt.upper(),
                          "internal": True})
        return JU.err("认不出来。请填**英文内部名**或**编号**（不要填中文）。")
    return JU.ok({"kind": kind, "text": txt, "id": got})


def api_set_moves(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    pm = _resolve_pm(sv, body.get("where"))
    sv.set_moves(pm, list(body.get("moves") or []))
    return JU.ok({"changed": True})


def api_clone(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    pm = _resolve_pm(sv, body.get("where"))
    cp = sv.clone_pokemon(pm)
    if not cp:
        return JU.err("复制失败")
    dst = body.get("to")
    if dst == "party":
        return JU.ok({"added": sv.add_to_party(cp)})
    bi = int(body.get("box_index", 0))
    return JU.ok({"added": sv.add_to_box(cp, bi)})


def api_move(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    op = body.get("op")
    if op == "box_to_party":
        return JU.ok({"moved": sv.move_box_to_party(int(body.get("box_index")),
                                                    int(body.get("slot")))})
    if op == "party_to_box":
        pm = sv.remove_from_party(int(body.get("index")))
        box, slot = sv.add_to_box(pm, int(body.get("box_index", 0)))
        return JU.ok({"box": box, "slot": slot})
    if op == "remove_party":
        return JU.ok({"removed": bool(sv.remove_from_party(int(body.get("index"))))})
    if op == "remove_box":
        return JU.ok({"removed": bool(sv.remove_from_box(int(body.get("box_index")),
                                                         int(body.get("slot"))))})
    if op == "rename_box":
        sv.rename_box(int(body.get("box_index")), str(body.get("name") or ""))
        return JU.ok({"changed": True})
    return JU.err(f"未知操作：{op}")


def api_recalc(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    pm = _resolve_pm(sv, body.get("where"))
    sv.recalc_pokemon(pm)
    return JU.ok({"recalculated": True, **_poke_view(sv, pm)})


# ------------------------------------------------------------------
# 背包
# ------------------------------------------------------------------
def api_bag(ctx):
    sv = _sv(ctx)
    return JU.ok({"bag": JU.clean(sv.bag())})


def api_pocket(ctx):
    sv = _sv(ctx)
    q = dict(ctx["query"]); q.update(ctx["body"] or {})
    i = int(q.get("index", 0))
    # ★ 归一成 {item_id, count, name}：pocket() 原样返回的是 Ruby 对象
    #   （现代存档里道具键是 Symbol），前端要的是一个能直接显示的编号。
    #   认不出编号的道具回退存档原始内部名（TEALMASK 而不是「（无）」）。
    rows = [{"item_id": iid, "count": cnt,
             "name": sv.data.item_label(iid if iid else None, raw)}
            for iid, raw, cnt in sv.pocket_entries_ex(i)]
    return JU.ok({"index": i, "pocket": rows,
                  "pocket_name": sv.data.pocket_name(i)})


def api_set_bag_item(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    sv.set_bag_item(int(body.get("pocket_index")), int(body.get("item_id")),
                    int(body.get("count")))
    return JU.ok({"changed": True})


def api_remove_bag_index(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    sv.remove_bag_index(int(body.get("pocket_index")), int(body.get("i")))
    return JU.ok({"changed": True})


def api_fill_pocket(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    n = sv.fill_pocket(int(body.get("pocket_index")), int(body.get("count", 1)))
    return JU.ok({"filled": n})


# ------------------------------------------------------------------
# 开关 / 变量
# ------------------------------------------------------------------
def api_switches(ctx):
    sv = _sv(ctx)
    return JU.ok({"switches": JU.clean(sv.switch_peek())})


def api_variables(ctx):
    sv = _sv(ctx)
    return JU.ok({"variables": JU.clean(sv.variable_peek())})


def _flag_list(sv, gvar):
    """拿到 $game_switches / $game_variables 里真正存数据的容器。

    core 只提供了可读的 switch_peek() / variable_peek()，写入没有现成接口，
    所以这里自己进一层 —— 按 SaveFile.set_dex 的写法操作 ruby 对象。
    读出来可能是 Python list，也可能是 rmarshal 的 RHash，两种都处理。
    """
    obj = sv.g(gvar)
    if hasattr(obj, "ivars"):
        d = obj.ivars.get("@data")
        if d is None:
            d = []
            obj.ivars["@data"] = d
        return d
    return obj


def _write_flag(seq, index, value):
    """往容器第 index 位写 value，容量不够就补。"""
    if index < 0:
        raise ValueError("下标不能为负")
    pairs = getattr(seq, "pairs", None)
    if pairs is not None:                       # rmarshal.RHash
        key = index
        for i, (k, _v) in enumerate(pairs):
            if k == index or (hasattr(k, "name") and k.name == index):
                pairs[i] = (k, value)
                return True
        pairs.append((index, value))
        return True
    if isinstance(seq, dict):
        seq[index] = value
        return True
    if isinstance(seq, list):
        while len(seq) <= index:
            seq.append(False if index > 0 else False)
        seq[index] = value
        return True
    raise TypeError(f"不支持的容器类型：{type(seq).__name__}")


def api_set_switch(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    try:
        i = int(body.get("index"))
    except (TypeError, ValueError):
        return JU.err("index 必须是数字")
    _write_flag(_flag_list(sv, "$game_switches"), i, bool(body.get("value", True)))
    return JU.ok({"changed": True, "index": i})


def api_set_variable(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    try:
        i = int(body.get("index"))
    except (TypeError, ValueError):
        return JU.err("index 必须是数字")
    raw = body.get("value", 0)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = str(raw)          # 变量也可能存字符串
    _write_flag(_flag_list(sv, "$game_variables"), i, val)
    return JU.ok({"changed": True, "index": i, "value": val})


# ------------------------------------------------------------------
# 下拉选项（给移动端的单选 / 搜索列表用）
# ------------------------------------------------------------------
def api_options(ctx):
    sv = _sv(ctx)
    q = dict(ctx["query"]); q.update(ctx["body"] or {})
    kind = q.get("kind") or "species"
    d = sv.data
    if kind == "status":
        # 与 v16 数字状态码一致：0 正常 … 6 濒死
        return JU.ok({"kind": kind, "options": [
            ["正常", 0], ["睡眠", 1], ["中毒", 2], ["灼伤", 3],
            ["冰冻", 4], ["麻痹", 5], ["濒死", 6]]})
    if kind == "shiny":
        return JU.ok({"kind": kind, "options": [
            ["自动（按个体ID算）", "auto"], ["是", "yes"], ["否", "no"]]})
    if kind == "ability":
        # 特性选项依赖具体是哪只宝可梦 → 需要 where
        where = q.get("where")
        if not where:
            return JU.err("ability 选项需要 where（哪只宝可梦）")
        pm = _resolve_pm(sv, where)
        r = sv.read_pokemon(pm)
        sid, form = r.get("species"), r.get("form") or 0
        names = sv.data.abilities_of(sid, form) if sid is not None else []
        return JU.ok({"kind": kind, "options": [
            [sv.data.ability_name(a) or str(a), i]
            for i, a in enumerate(names)]})
    table = {
        "species": d.species_list,
        "item": d.item_list,
        "move": d.move_list,
        "nature": d.nature_options,
        "trainer_type": d.trainer_type_list,
    }
    fn = table.get(kind)
    if not fn:
        return JU.err(f"未知的选项类型：{kind}")
    return JU.ok({"kind": kind, "options": JU.clean(fn())})


# ------------------------------------------------------------------
# 背包 / 图鉴 的零散写操作
# ------------------------------------------------------------------
def api_set_registered_item(ctx):
    sv = _sv(ctx)
    body = ctx["body"]
    iid = body.get("item_id")
    if isinstance(iid, str):
        iid = sv.data.find_item(iid)
    sv.set_registered_item(int(iid or 0))
    return JU.ok({"changed": True})


def api_unlock_forms(ctx):
    """形态图鉴全开。返回开了多少条。"""
    sv = _sv(ctx)
    n = sv.unlock_all_forms()
    return JU.ok({"unlocked": n})


# ------------------------------------------------------------------
# 保存
# ------------------------------------------------------------------
def api_write(ctx):
    sv = _sv(ctx)
    body = ctx["body"] or {}
    dest = JU.normalize_path(body.get("dest")) or None
    backup = bool(body.get("backup", True))
    try:
        real = sv.write(dest, backup=backup)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JU.err(f"写入失败：{type(e).__name__}: {e}")
    return JU.ok({"written_to": real.replace("\\", "/")})


def dispatch(ctx, action):
    table = {
        "open": api_open,
        "index": api_index,
        "roundtrip": api_roundtrip,
        "trainer": api_trainer,
        "set_trainer": api_set_trainer,
        "badges": api_badges,
        "set_badge": api_set_badge,
        "set_dex": api_set_dex,
        "party": api_party,
        "boxes": api_boxes,
        "set_pokemon": api_set_pokemon,
        "abilities": api_abilities,
        "resolve": api_resolve,
        "pokemon": api_pokemon,
        "set_moves": api_set_moves,
        "clone": api_clone,
        "move": api_move,
        "recalc": api_recalc,
        "bag": api_bag,
        "pocket": api_pocket,
        "set_bag_item": api_set_bag_item,
        "remove_bag_index": api_remove_bag_index,
        "fill_pocket": api_fill_pocket,
        "set_registered_item": api_set_registered_item,
        "unlock_forms": api_unlock_forms,
        "switches": api_switches,
        "variables": api_variables,
        "set_switch": api_set_switch,
        "set_variable": api_set_variable,
        "options": api_options,
        "write": api_write,
    }
    fn = table.get(action)
    if not fn:
        return JU.err(f"未知的 save 操作：{action}")
    try:
        return fn(ctx)
    except ValueError as e:
        return JU.err(str(e))
    except IndexError as e:
        return JU.err(str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JU.err(f"{type(e).__name__}: {e}")
