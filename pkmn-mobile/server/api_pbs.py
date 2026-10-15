# -*- coding: utf-8 -*-
"""
PBS 编辑（手机版后端）。

    GET  /api/pbs/list?dir=<游戏根目录>
    GET  /api/pbs/read?dir=<游戏根目录>&path=<txt 绝对路径>
    GET  /api/pbs/fields
    POST /api/pbs/extract {"dir": "..."}
    POST /api/pbs/write   {"dir": "...", "path": "...", "rows": [...]}
    POST /api/pbs/compile {"dir": "..."}
    POST /api/pbs/compile_one {"dir": "...", "path": "..."}

★ 核心逻辑全在 core/ 的 pbs_edit.py / pbs_legacy.py 里（和电脑版同一份代码），
  这里只做「取参数 → 调用 → 转 JSON」。
  老版本（v16/v17/v18）的「编译」= 标记待重编译（游戏启动时自己重建 .dat）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bootstrap  # noqa: E402,F401

if __package__:
    from . import jsonutil as JU          # noqa: E402
else:
    import jsonutil as JU                 # noqa: E402

from core import pbs_edit as PE           # noqa: E402

# 一次最多传多少条（手机端不需要编辑上万条；截断并提示）
ROW_LIMIT = 3000


def _arg(ctx, name):
    q = ctx.get("query") or {}
    b = ctx.get("body") or {}
    return b.get(name) or q.get(name) or ""


def _family(dir_):
    if not dir_ or not os.path.isdir(dir_):
        return "", "还没选游戏主程序"
    try:
        return PE.detect_family(dir_)
    except Exception as e:                                        # noqa: BLE001
        return "", "%s: %s" % (type(e).__name__, e)


def _find_key(dir_, path, fam):
    name = os.path.basename(path).lower()
    try:
        for f in PE.list_pbs_txt(dir_, fam):
            if f["file"].lower() == name:
                return f["key"], f["name"]
    except Exception:                                              # noqa: BLE001
        pass
    return "", os.path.basename(path)[:-4]


def api_list(ctx):
    d = _arg(ctx, "dir")
    fam, why = _family(d)
    files = []
    if fam:
        try:
            files = [{"file": f["file"], "name": f["name"],
                      "desc": f["desc"], "key": f["key"], "size": f["size"]}
                     for f in PE.list_pbs_txt(d, fam)]
        except Exception as e:                                    # noqa: BLE001
            return JU.err("读 PBS 目录失败：%s" % e)
    return JU.ok({
        "dir": d, "family": fam, "why": why, "files": files,
        "legacy": bool(fam) and PE.is_legacy(fam),
        "pbs_exists": bool(d) and os.path.isdir(PE.pbs_dir(d)),
    })


def api_fields(ctx):
    return JU.ok({"desc": PE.FIELD_DESC, "sub": PE.FIELD_DESC_SUB})


def api_read(ctx):
    d = _arg(ctx, "dir")
    path = _arg(ctx, "path")
    if not path or not os.path.isfile(path):
        return JU.err("文件不存在")
    fam, why = _family(d)
    if not fam:
        return JU.err(why)
    key, disp = _find_key(d, path, fam)
    spec = PE.spec_for(key, fam) if key else None
    try:
        doc = PE.Doc.load(spec, fam, path)
    except Exception as e:                                        # noqa: BLE001
        return JU.err("读取失败：%s" % e)
    rows = []
    for e in doc.entries[:ROW_LIMIT]:
        rows.append({
            "sid": e.sid,
            "label": e.label(),
            "fields": [{"key": k, "value": v, "desc": PE.field_desc(k)}
                       for k, v in e.fields],
        })
    return JU.ok({
        "file": os.path.basename(path), "key": key, "name": doc.name or disp,
        "family": fam, "style": doc.style, "editor": doc.editor,
        "legacy": PE.is_legacy(fam), "rows": rows,
        "truncated": len(doc.entries) > ROW_LIMIT,
        "hint": _hint(spec, fam, doc),
    })


def _hint(spec, fam, doc) -> str:
    if spec is None:
        return "这个文件没登记类型（多半是对战设施引用的附属文件），按原样编辑即可。"
    if doc.style == "line":
        return "一行一条记录：左边是字段名，右边是这一行的值；改完点「保存到 txt」。"
    if doc.style == "kv":
        return "写法是「键 = 值」；改完点「保存到 txt」。"
    return "每段以方括号标题开头，下面是若干「字段 = 值」；改完点「保存到 txt」。"


def api_write(ctx):
    d = _arg(ctx, "dir")
    path = _arg(ctx, "path")
    rows = (ctx.get("body") or {}).get("rows") or []
    if not path or not os.path.isfile(path):
        return JU.err("文件不存在")
    fam, why = _family(d)
    if not fam:
        return JU.err(why)
    key, _disp = _find_key(d, path, fam)
    spec = PE.spec_for(key, fam) if key else None
    try:
        doc = PE.Doc.load(spec, fam, path)
    except Exception as e:                                        # noqa: BLE001
        return JU.err("读取失败：%s" % e)
    old = {e.sid: e for e in doc.entries}
    new_entries = []
    for r in rows:
        sid = r.get("sid", "")
        ent = old.get(sid)
        if ent is None:
            ent = PE.DocEntry(sid)
        ent.fields = [[f.get("key", ""), f.get("value", "")]
                      for f in (r.get("fields") or [])]
        new_entries.append(ent)
    doc.entries = new_entries
    try:
        doc.save()
    except Exception as e:                                        # noqa: BLE001
        return JU.err("保存失败：%s" % e)
    return JU.ok({"file": os.path.basename(path), "count": len(new_entries)})


def api_extract(ctx):
    d = _arg(ctx, "dir")
    fam, why = _family(d)
    if not fam:
        return JU.err(why)
    out = []
    try:
        for r in PE.extract_all(d, fam):
            out.append({"name": r.get("name"), "file": r.get("file"),
                        "ok": r.get("ok"),
                        "stat": (r.get("stat") or "")[:80]})
    except Exception as e:                                        # noqa: BLE001
        return JU.err("提取失败：%s" % e)
    return JU.ok({"results": out,
                  "ok_count": sum(1 for r in out if r["ok"])})


def api_compile(ctx):
    d = _arg(ctx, "dir")
    fam, why = _family(d)
    if not fam:
        return JU.err(why)
    if PE.is_legacy(fam):
        try:
            from core import pbs_legacy as PL
            n, msg = PL.mark_for_recompile(d, fam)
        except Exception as e:                                    # noqa: BLE001
            return JU.err("标记失败：%s" % e)
        return JU.ok({"legacy": True, "count": n, "message": msg})
    out = []
    for spec in PE.list_specs(fam):
        ok, msg, stat = PE.compile_spec(spec, fam, d)
        out.append({"name": spec["name"], "ok": ok, "stat": stat,
                    "msg": (msg or "")[:120]})
    return JU.ok({"legacy": False, "results": out,
                  "ok_count": sum(1 for r in out if r["ok"])})


def api_compile_one(ctx):
    d = _arg(ctx, "dir")
    path = _arg(ctx, "path")
    fam, why = _family(d)
    if not fam:
        return JU.err(why)
    if PE.is_legacy(fam):
        try:
            from core import pbs_legacy as PL
            n, msg = PL.mark_for_recompile(d, fam)
        except Exception as e:                                    # noqa: BLE001
            return JU.err("标记失败：%s" % e)
        return JU.ok({"legacy": True, "count": n, "message": msg})
    key, _disp = _find_key(d, path, fam)
    spec = PE.spec_for(key, fam) if key else None
    if spec is None:
        return JU.err("这个文件没有对应的 .dat，不用编译。")
    ok, msg, stat = PE.compile_spec(spec, fam, d, txt_path=path)
    if not ok:
        return JU.err(msg or "编译失败")
    return JU.ok({"legacy": False, "name": spec["name"], "stat": stat})


def dispatch(ctx, action):
    table = {
        "list": api_list, "fields": api_fields, "read": api_read,
        "write": api_write, "extract": api_extract,
        "compile": api_compile, "compile_one": api_compile_one,
    }
    fn = table.get(action)
    if not fn:
        return JU.err("未知的 PBS 操作：%s" % action)
    try:
        return fn(ctx)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JU.err("%s: %s" % (type(e).__name__, e))
