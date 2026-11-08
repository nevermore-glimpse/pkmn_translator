# -*- coding: utf-8 -*-
r"""
手工翻译缓存：把待翻条目导出成 JSON 交给人翻，翻完再回写。

为什么要有这个
--------------
    模型不可用 / 上下文太长 / 只想挑几条精修时，最省事的做法是：
    把「要翻的原文」整批拿出来，用任何编辑器（或别人）翻好，再倒回程序。

    本模块干两件事，每件事都由一个按钮驱动：

      ① **提取缓存**（术语页 = 提取术语缓存 / 翻译页 = 提取句子缓存）
         对每个文件先按正常翻译流水线的口径分流：

           · **不用送模型**的条目 → 直接写进该文件的翻译缓存
             `*_cache.json`：整句术语直译（命中术语表）、整句 `#{…}`
             占位符、单个字母、纯控制符、资源路径、预过滤（无可译文本）、
             参考译文命中（程序目录「翻译中间文件」夹里的对照 json）。
             这些和真正翻译时写进去的值逐字节一致，下次翻译直接命中缓存。
           · **要送模型**的条目 → 导出成
             `<游戏根目录>/Text_chinese_cache/<源文件名>.json`，一个源文件一份，
             里面带 `items`（原文 → 空译文）与 `prompt`（本次该用的提示词）。

      ② **回写**（回写已翻术语缓存 / 回写已翻句子缓存）
         读上面那批 JSON，把 `items` 里填好的译文写回：
           · 该文件的翻译缓存 `*_cache.json`（没有就新建条目）
           · 该文件的译文文件 `<源文件名>_translated.txt`
           · 术语模式下再把这批「原文 → 译文」并进术语表 AUTO 块

JSON 格式
---------
    {
      "type": "term" | "sentence",
      "file": "<源文件绝对路径>",
      "cache": "<该文件的翻译缓存路径>",
      "translated": "<该文件的译文文件路径>",
      "section": "ITEM_NAMES",
      "note": "用法说明（改哪一列、别动哪一列；翻译时看下方 prompt）",
      "prompt": {
        "system": "<完整 system 提示词（含类别段）>",
        "user_template": "<给模型的翻译指令：只改 items 右边的值，术语照 terms 块>",
        "output_format": "<输出成 items 同结构的 JSON>",
        "terms": {"原文术语": "术语译文"}      ← 本文件命中的术语，翻的时候照它用
      },
      "items": {"原文": ""}                    ← 只改右边的值
    }

    ★ items 的键（原文）别动；值留空或与原文相同 = 视为没翻，回写时跳过。
    ★ prompt 只作参考，回写时完全忽略。
    ★ 重复提取时，旧 JSON 里已经填好的译文会带过来，不会因为再点一次就丢。
"""
import glob
import json
import os
from types import SimpleNamespace

import config
from cache import Cache, atomic_replace, reference_translations
from logger import get_logger

log = get_logger("manual_cache")

# 导出目录（放游戏根目录下，与 problem/ 同级）
DIR_NAME = "Text_chinese_cache"

# prompt.terms 的体积上限：超过就截断（只影响参考信息，不影响 items）
MAX_PROMPT_TERMS = 2000

_NOTE_TERM = ("只改 items 里每条**右边的译文**（冒号右边），键（原文）别动。"
              "留空或与原文相同 = 视为没翻，回写时跳过。"
              "翻译时照下方 prompt 里的提示词来：system 说明文本类型与整体要求，"
              "user_template / output_format 说明怎么改、怎么输出，"
              "terms 是术语参考表。"
              "改完回程序点「回写已翻术语缓存」："
              "译文会写进该文件的翻译缓存、生成 *_translated.txt，"
              "并把「原文 → 译文」并进术语表自动提取区。")
_NOTE_SENTENCE = ("只改 items 里每条**右边的译文**（冒号右边），键（原文）别动。"
                  "留空或与原文相同 = 视为没翻，回写时跳过。"
                  "翻译时照下方 prompt 里的提示词来：system 说明文本类型与整体要求，"
                  "user_template / output_format 说明怎么改、怎么输出，"
                  "terms 是术语参考表。"
                  "改完回程序点「回写已翻句子缓存」："
                  "译文会写进该文件的翻译缓存并生成 *_translated.txt。")

# 给模型看的翻译指令（prompt.user_template）：
#   ★ 不再是与程序送模型时逐字一致的那份模板 —— 那份要求「每行一条
#     {"id":N,"text":"…"}」，人 / 外部模型拿到的是 items 字典，用不上。
#     这里改成「就地改 items 右边的值」，与这份 JSON 的结构对齐。
_HUMAN_USER_PROMPT = (
    "翻译 items 里的每一条：左边是原文（键），右边是要填的译文（值）。\n"
    "· 只改右边的译文，左边的原文键一个字符都不要动，条数与顺序保持不变。\n"
    "· 术语参考：下方的 terms 是「原文术语 → 译文术语」对照表，"
    "items 里出现了表里的词就照它的译名翻，不要另创新译名。\n"
    "· 控制码 / 标签 / 占位符（\\n、\\c[1]、#{…}、\\tg[…] 之类）原样保留，不要翻。\n"
    "· 按 output_format 的格式输出，结构与 items 完全一致。")

_HUMAN_OUTPUT = (
    '{\n  "原文1": "译文1",\n  "原文2": "译文2"\n}\n'
    "（键 = items 里的原文，原样不动；值 = 译文；条数与 items 相同）")


# ================================================================
# 路径
# ================================================================
def _basis_path(basis):
    """basis 可以是路径、也可以是路径列表。"""
    if isinstance(basis, (list, tuple)):
        for p in basis:
            if p:
                return p
        return ""
    return str(basis or "")


def game_root_of(path):
    """游戏根目录（复用 problem_io 的判定，含「往上找 Data/Scripts.rxdata」）。"""
    try:
        import problem_io as PI
        return PI.game_root_of(path)
    except Exception as e:                       # noqa: BLE001
        log.debug("判定游戏根目录失败（退回所选目录）：%s", e)
        p = _basis_path(path)
        if not p:
            return os.getcwd()
        p = os.path.abspath(p if os.path.isdir(p) else os.path.dirname(p))
        return p


def cache_dir(basis, create=True):
    """`<游戏根目录>/Text_chinese_cache`（create=True 时顺手建出来）。"""
    d = os.path.join(game_root_of(basis), DIR_NAME)
    if create:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            log.warning("建「%s」失败：%s", d, e)
    return d


def _stem(path):
    return os.path.splitext(os.path.basename(str(path or "")))[0]


# ================================================================
# 读写 json
# ================================================================
def _write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    atomic_replace(tmp, path)
    return path


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:                       # noqa: BLE001
        log.warning("读手工翻译缓存失败（跳过 %s）：%s", path, e)
        return {}


def _items_of(data):
    """取 items（{原文: 译文}），兼容被手改成 list 的情况。"""
    items = data.get("items")
    if isinstance(items, dict):
        return {str(k): ("" if v is None else str(v))
                for k, v in items.items() if str(k).strip()}
    if isinstance(items, list):
        out = {}
        for it in items:
            if isinstance(it, dict):
                k = str(it.get("src") or it.get("原文") or "")
                v = it.get("dst", it.get("译文", ""))
                if k.strip():
                    out[k] = "" if v is None else str(v)
        return out
    return {}


def _fixes_of(items):
    """只留真的翻了的条目（空 / 等于原文的算没翻）。"""
    fixes, skipped = {}, 0
    for src, dst in items.items():
        s, d = str(src or "").strip(), str(dst or "").strip()
        if not s:
            continue
        if not d or d == s:
            skipped += 1
            continue
        fixes[s] = d
    return fixes, skipped


def _read_cache_data(cache_path):
    if not cache_path or not os.path.isfile(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:                       # noqa: BLE001
        log.warning("翻译缓存读取失败（按空缓存处理）：%s：%s", cache_path, e)
        return {}
    return data if isinstance(data, dict) else {}


# ================================================================
# 分流：照 commands._translate_core 的预分流顺序逐条判定
# ================================================================
def split_file(path):
    """
    解析一个文本文件并按正常翻译的口径分流。

    返回 {"path","section","cache","translated","auto","todo","cached","entries","ref"}
      · auto   : {原文: 译文}，**不用送模型**的条目（整句术语直译 / 各类跳过
                 / 参考译文命中）
      · todo   : [原文, ...]，要送模型翻的（缓存里还没有的）
      · cached : 已经在翻译缓存里的条数（这次不再处理）
      · ref    : auto 里命中程序目录「翻译中间文件」夹参考译文的条数
    """
    import commands as C
    import parser as P
    import processor as PR

    sec = C._file_section(path)
    cache_path = C.cache_path_for(path) or ""
    out_path = C.translated_path_for(path) or ""
    lines, _nl = P.read_file(path, config.INPUT_ENCODING)
    entries, _special = P.extract_entries(lines)
    have = _read_cache_data(cache_path)
    ref_map = reference_translations()

    try:
        PR.load_terms()
    except Exception as e:                       # noqa: BLE001
        log.warning("术语表加载失败（按空表处理）：%s", e)

    auto, todo, seen = {}, [], set()
    cached = 0
    ref_hits = 0
    for _ln, txt in entries:
        if not txt or txt in seen:
            continue
        seen.add(txt)
        if txt in have:
            cached += 1
            continue
        # ★ 顺序与 commands._translate_core 完全一致，写进缓存的值才不会
        #   与真正翻译时算出来的不一样。
        if PR.is_hash_placeholder_only(txt):
            auto[txt] = txt
            continue
        if getattr(config, "WHOLE_TERM_MATCH", True):
            hit = PR.match_whole_term(txt, section=sec)
            if hit:
                auto[txt] = hit[1]
                continue
        if getattr(config, "SKIP_SINGLE_LETTER", True) and PR.is_single_letter(txt):
            auto[txt] = txt
            continue
        if getattr(config, "SKIP_PURE_CONTROL", True) and PR.is_pure_control(txt):
            auto[txt] = txt
            continue
        if getattr(config, "SKIP_PATH_LINES", True) and PR.is_path_like(txt):
            auto[txt] = txt
            continue
        if getattr(config, "PREFILTER_ENABLE", True) \
                and not PR.has_translatable_text(txt):
            auto[txt] = txt
            continue
        # ★ 参考译文：与 _translate_core 同口径，命中就直接写缓存、不导出
        ref = ref_map.get(txt)
        if ref is not None:
            auto[txt] = ref
            ref_hits += 1
            continue
        todo.append(txt)

    return {"path": path, "section": sec, "cache": cache_path,
            "translated": out_path, "auto": auto, "todo": todo,
            "cached": cached, "entries": len(entries), "ref": ref_hits}


# ================================================================
# 提示词：与真正翻译时送给模型的同一套
# ================================================================
def _terms_for(texts, section=None):
    """这批原文命中的术语 → {术语原文: 术语译文}（与流水线注入 prompt 同口径）。"""
    import processor as PR
    import replacement as REPL

    pairs = {}
    for txt in texts or ():
        try:
            if getattr(config, "PREFIX_DICT_ENABLE", True):
                _prefix, body = PR.split_prefix(txt)
            else:
                body = txt
            body, _n = REPL.apply_pre(body)
            for src, _dst in PR.find_terms(PR.strip_newlines(body)):
                pairs.setdefault(src, src)
        except Exception as e:                   # noqa: BLE001
            log.debug("术语命中查询失败（忽略）：%s", e)
    out = {}
    for src in list(pairs)[:MAX_PROMPT_TERMS]:
        try:
            out[src] = PR.render_term_dst(src, section=section)
        except Exception:                        # noqa: BLE001
            continue
    return out


def build_prompt(section, texts):
    """
    给模型的翻译指令 + 术语参考。

    · system       : 直接取 translator.OllamaClient._system_prompt 的产物 ——
                     类别段、思考块、语言替换全都在里面，与送模型的请求逐字节一致。
                     该函数不用实例状态，给个空对象就够，不建 HTTP 连接池。
    · user_template: 本模块自己的「改 items 右边的值」指令（见 _HUMAN_USER_PROMPT）。
    · output_format: 输出成 items 同结构的 JSON。
    · terms        : 本文件命中的术语表，翻的时候照它用。

    ★ 这里**不放** note —— 用法说明只在顶层 note 里写一次（它在 prompt 上方），
      prompt 内部保持「纯给模型看」的内容。
    """
    import translator as TR

    system = ""
    try:
        system = TR.OllamaClient._system_prompt(SimpleNamespace(), section)
    except Exception as e:                       # noqa: BLE001
        log.warning("生成 system 提示词失败（留空）：%s", e)
    return {
        "system": system,
        "user_template": _HUMAN_USER_PROMPT,
        "output_format": _HUMAN_OUTPUT,
        "terms": _terms_for(texts, section),
    }


# ================================================================
# ① 提取缓存
# ================================================================
def _json_name(stem, used):
    """给源文件挑一个不重名的 json 文件名主干。"""
    base = stem or "unknown"
    name = base
    i = 2
    while name.lower() in used:
        name = f"{base}_{i}"
        i += 1
    used.add(name.lower())
    return name


def _merge_old_items(items, old_path):
    """重复提取：旧 json 里已填的译文带过来，别让用户白翻一遍。"""
    old = _items_of(_read_json(old_path)) if os.path.isfile(old_path) else {}
    if not old:
        return items
    for k, v in items.items():
        if not v and old.get(k):
            items[k] = old[k]
    return items


def _extract(files, mode, basis, progress=None):
    """
    分流 + 写缓存 + 导出 json（mode = "term" / "sentence"）。

    返回 {"dir","type","files","auto","todo","cached","written",
          "skipped","problems","entries"}
    """
    import bridge

    out_dir = cache_dir(basis)
    st = {"dir": out_dir, "type": mode, "files": 0, "auto": 0, "todo": 0,
          "cached": 0, "ref": 0, "written": [], "skipped": 0, "problems": [],
          "entries": 0}
    used = set()
    total = len(files)

    for i, path in enumerate(files, 1):
        if bridge.cancelled():
            raise bridge.CancelRequested()
        if not os.path.isfile(path):
            st["problems"].append((path, "文件不存在"))
            continue
        try:
            r = split_file(path)
        except Exception as e:                   # noqa: BLE001
            log.error("分流失败（跳过 %s）：%s", path, e)
            st["problems"].append((path, f"读取失败：{e}"))
            continue

        # ---------- 不用送模型的：直接写进该文件的翻译缓存 ----------
        if r["auto"]:
            try:
                c = Cache(r["cache"])
                for k, v in r["auto"].items():
                    c.put(k, v)
                c.save(force=True)
            except Exception as e:               # noqa: BLE001
                log.error("写翻译缓存失败（%s）：%s", r["cache"], e)
                st["problems"].append((path, f"写缓存失败：{e}"))

        # ---------- 要送模型的：导出 json ----------
        try:
            items = {t: "" for t in r["todo"]}
            name = _json_name(_stem(path), used)
            out = os.path.join(out_dir, f"{name}.json")
            items = _merge_old_items(items, out)
            payload = {
                "type": mode,
                "file": os.path.abspath(path),
                "cache": r["cache"],
                "translated": r["translated"],
                "section": r["section"] or "",
                "note": _NOTE_TERM if mode == "term" else _NOTE_SENTENCE,
                "prompt": build_prompt(r["section"], list(items)),
                "items": items,
            }
            _write_json(out, payload)
            st["written"].append(out)
        except Exception as e:                   # noqa: BLE001
            log.error("导出 json 失败（%s）：%s", path, e)
            st["problems"].append((path, f"导出失败：{e}"))
            continue

        st["files"] += 1
        st["entries"] += r["entries"]
        st["auto"] += len(r["auto"])
        st["todo"] += len(items)
        st["cached"] += r["cached"]
        st["ref"] += r.get("ref", 0)
        log.info("[%d/%d] %s：跳过类 %d 条写缓存（参考译文命中 %d 条），"
                 "待翻 %d 条 → %s",
                 i, total, os.path.basename(path), len(r["auto"]),
                 r.get("ref", 0), len(items), os.path.basename(out))
        if progress:
            progress(i, total, os.path.basename(path))

    log.info("提取缓存完成：%d 个文件，写缓存 %d 条，导出待翻 %d 条 → %s",
             st["files"], st["auto"], st["todo"], out_dir)
    return st


def extract_terms(target, progress=None):
    """
    术语提取页「提取术语缓存」：只处理名字类文件（与术语提取同一批）。
    """
    import commands as C
    import term_extract as TE

    problems = []
    files = TE.find_names_files(target, problems)
    for f in files:
        TE.ensure_mapinfos_dir(f)
    if files:
        # ★ 与真正翻译一致：多文件同目录时中间文件进「翻译中间文件」夹，
        #   否则这里算出来的缓存路径会和翻译时落盘的位置对不上。
        C.enter_work_dir(files)
    st = _extract(files, "term", target, progress)
    st["problems"] = list(problems) + list(st["problems"])
    return st


def extract_sentences(paths, basis=None, progress=None):
    """
    翻译页「提取句子缓存」：处理用户选的非术语类文件。
    """
    import commands as C

    files = [p for p in (paths or []) if p and os.path.isfile(p)]
    if files:
        C.enter_work_dir(files)
    return _extract(files, "sentence", basis or (files[0] if files else ""),
                    progress)


# ================================================================
# ② 回写
# ================================================================
def known_files(basis, mode=None):
    """当前目录里已有的 json（界面提示用）。"""
    d = cache_dir(basis, create=False)
    if not os.path.isdir(d):
        return []
    out = []
    for p in sorted(glob.glob(os.path.join(d, "*.json"))):
        if mode:
            data = _read_json(p)
            if str(data.get("type") or "") not in (mode, ""):
                continue
        out.append(p)
    return out


def writeback(basis, mode=None):
    """
    读 `Text_chinese_cache/*.json`，把译文写回缓存 + 生成译文文件。

    mode: "term" / "sentence" / None（不过滤）

    返回 {"dir","files","applied","added","updated","file_lines",
          "missing","skipped","terms_added"}
    """
    import commands as C

    out_dir = cache_dir(basis, create=False)
    paths = known_files(basis, mode)
    st = {"dir": out_dir, "files": 0, "applied": 0, "added": 0,
          "updated": 0, "file_lines": 0, "missing": 0, "skipped": 0,
          "terms_added": 0}
    if not paths:
        return st

    for p in paths:
        data = _read_json(p)
        typ = str(data.get("type") or "sentence")
        if mode and typ not in (mode, ""):
            continue
        items = _items_of(data)
        if not items:
            continue

        src_file = str(data.get("file") or "")
        if not (src_file and os.path.isfile(src_file)):
            log.warning("手工翻译缓存找不到对应文本（跳过）：%s", p)
            st["missing"] += 1
            continue

        fixes, skipped = _fixes_of(items)
        st["skipped"] += skipped
        if not fixes:
            continue

        # ---------- ① 翻译缓存 ----------
        recorded = str(data.get("cache") or "")
        canonical = C.cache_path_for(src_file) or ""
        cache_path = recorded if (recorded and os.path.isfile(recorded)) \
            else (canonical or recorded)
        if not cache_path:
            st["missing"] += 1
            continue

        cache = Cache(cache_path)
        added = updated = 0
        for src, dst in fixes.items():
            old = cache.get(src)
            if old is None:
                added += 1
            elif str(old) != dst:
                updated += 1
            cache.put(src, dst)
        cache.save(force=True)

        # ---------- ② 译文文件 ----------
        n_lines = _write_translated(src_file, cache)

        # ---------- ③ 术语表（只有术语模式） ----------
        if typ == "term":
            try:
                import auto_terms
                import processor as PR
                st["terms_added"] += int(
                    auto_terms.merge_into_term_dict(fixes) or 0)
                PR.load_terms(force=True)
            except Exception as e:               # noqa: BLE001
                log.warning("并进术语表失败（不影响缓存与译文）：%s", e)

        st["files"] += 1
        st["applied"] += len(fixes)
        st["added"] += added
        st["updated"] += updated
        st["file_lines"] += n_lines
        log.info("回写手工翻译：%s ← %s（%d 条，缓存新增 %d / 改 %d，"
                 "译文 %d 行）", src_file, os.path.basename(p),
                 len(fixes), added, updated, n_lines)

    return st


def _write_translated(src_file, cache):
    """
    用**整份缓存**重写译文文件（与 _translate_core 的回写同口径）。

    ★ 用整份缓存而不是只写这次改的几条：`*_translated.txt` 是一份完整译文，
      只替换几条会把它写残。
    ★ 行数哨兵不在这里做（那是检查报告的事）；写坏也只会多出几行，
      重新翻一次即可恢复。
    """
    import parser as P

    try:
        import commands as C
        out_path = C.translated_path_for(src_file)
        lines, newline = P.read_file(src_file, config.INPUT_ENCODING)
        entries, _special = P.extract_entries(lines)
        translations = {txt: cache.get(txt) for _ln, txt in entries
                        if cache.get(txt)}
        return int(P.write_output(lines, entries, translations, out_path,
                                  newline or "\n", config.OUTPUT_ENCODING) or 0)
    except Exception as e:                       # noqa: BLE001
        log.error("生成译文文件失败（%s）：%s", src_file, e)
        return 0
