# -*- coding: utf-8 -*-
"""
核心功能实现。

设计约定：
  · 所有 xxx_paths(...) 为「无交互核心」，只通过 bridge 输出/上报进度，
    供命令行与 GUI 共用；
  · 所有 cmd_xxx(...) 为命令行外壳，负责询问语言、选择文件范围等。
"""
import json
import os
import re
import time
import traceback
from collections import Counter, defaultdict

import bridge
import checker
import config
import parser as P
import processor as PR
import settings
from cache import Cache, atomic_replace, load_edits
from logger import get_logger
from translator import (OllamaClient, polish_with_retry,
                        translate_with_retry)

log = get_logger("commands")


def emit(*args, **kwargs):
    """统一输出：GUI 接管后写入日志页，命令行下就是 print。"""
    bridge.emit(*args, **kwargs)


# ================================================================
# 常用语言列表
# ================================================================
LANG_OPTIONS = [
    "英文",
    "简体中文",
    "繁体中文",
    "日文",
    "韩文",
    "西班牙文",
    "法文",
    "德文",
    "意大利文",
]

# 重翻检查报告时，默认要处理的问题类型（GUI 里可逐项勾选）
RETRANSLATE_KINDS = {
    "疑似未翻译", "疑似异常句", "译文残留占位符",
    "翻译失败", "占位符兜底", "术语冲突","符号不匹配",
}

# ★ 永远不参与自动重翻的类型：
#   · 译文残留控制码 —— 重翻并不能保证修好，改由用户手工处理
#   · 符号不匹配 / 特殊行 —— 需要人工判断
NEVER_RETRANSLATE_KINDS = {
    "译文残留控制码", "特殊行", "控制码回退",
}

# ★ 手工编辑产生的类型：报告里**默认不勾选**（所以不参与重翻），
#   但可以勾上查看 —— 用户改过的句子都归在这里，方便回头核对。
MANUAL_KINDS = {"已编辑"}

# 报告里可能出现的问题类型（展示 / 排序用）
REPORT_KIND_ORDER = [
    "翻译失败", "占位符兜底", "术语冲突", "控制码回退",
    "疑似未翻译", "疑似异常句",
    "译文残留占位符", "译文残留控制码",
    "符号不匹配", "特殊行", "已编辑",
]


# ================================================================
# 报告里手工编辑的译文
#   存储与读写都在 cache.py（checker 也要读，放这里会循环 import）
# ================================================================
def save_report_edit(src, dst):
    """
    在报告里手工改一句译文：
      ① 写进翻译缓存（原样覆盖，重翻时不会把它当成未翻）；
      ② 记进 <缓存>_edited.json，下次「刷新报告」时这一句归入「已编辑」类型。

    返回 {"cache": 缓存路径, "edited": 记录路径}。
    """
    cache_file = getattr(config.Runtime, "cache_file", "") or config.CACHE_FILE
    if not os.path.isfile(cache_file):
        raise FileNotFoundError(f"找不到翻译缓存：{cache_file}\n"
                                f"（先跑一次翻译才会生成）")
    cache = Cache(cache_file)
    return cache.save_edit(src, dst)


# ================================================================
# 「应用已编辑」：把手工改过的译文真正落到缓存 + 译文文件
# ================================================================
def _edited_path_for(src_path):
    """
    源文件 → 手工编辑记录路径（与 cache.edited_path 的规则一致）：
        <目录>/<主名>_cache_edited.json
    ★ 不碰 config.Runtime，纯算路径，GUI 里统计条数时用。
    """
    parent = os.path.dirname(os.path.abspath(src_path))
    stem = os.path.splitext(os.path.basename(src_path))[0]
    return os.path.join(parent, f"{stem}_cache_edited.json")


def count_manual_edits(paths):
    """统计这些源文件各自的手工编辑条数 → (有编辑的文件数, 总条数)。"""
    files = total = 0
    for path in paths or []:
        if not path:
            continue
        try:
            with open(_edited_path_for(path), "r", encoding="utf-8") as f:
                data = json.load(f)
            n = len(data) if isinstance(data, dict) else 0
        except Exception:
            n = 0
        if n:
            files += 1
            total += n
    return files, total


def apply_manual_edits(paths):
    """
    把报告里手工编辑过的译文（<缓存名>_edited.json）真正应用下去：

      ① 覆盖翻译缓存里的对应条目（以后重翻 / 换行重排拿到的都是手工译文）；
      ② 就地改写已生成的译文文件（*_translated.txt）：
         只替换编辑过的那些句子，其余行一个字都不动。

    返回 {"files", "applied", "missing", "no_edit"}。
    """
    log.info("=" * 50)
    log.info("应用手工编辑  共 %d 个文件", len(paths))
    emit("\n" + "=" * 55)
    emit("  应用已编辑（把手工改过的句子写进缓存与译文文件）")
    emit("=" * 55)

    files_done = applied = missing = no_edit = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            emit("\n[中断] 用户取消")
            break
        if not path or not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        config.Runtime.set_input(path)
        name = os.path.basename(path)
        bridge.progress(i - 1, len(paths), name)

        edits = load_edits()
        if not edits:
            emit(f"[{i}/{len(paths)}] {name}：没有手工编辑记录，跳过")
            no_edit += 1
            continue

        # ---- ① 写回翻译缓存 ----
        cpath = config.Runtime.cache_file
        n_cache = 0
        try:
            cache = Cache(cpath)
            for src, dst in edits.items():
                if cache.get(src) != dst:
                    cache.put(src, dst)
                    n_cache += 1
            cache.save(force=True)
        except Exception as e:
            emit(f"  写缓存失败：{e}")
            continue

        # ---- ② 写回译文文件 ----
        out_path = config.Runtime.output_file
        if not os.path.exists(out_path):
            emit(f"  ⚠ 找不到译文文件：{os.path.basename(out_path)}"
                 f"（缓存已更新 {n_cache} 条，译文文件没改；先跑一次翻译）")
            missing += 1
            continue

        try:
            src_lines, _ = P.read_file(path, config.INPUT_ENCODING)
            out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
        except Exception as e:
            emit(f"  读取失败：{e}")
            continue
        # ★ 行尾按译文文件的原始字节定，别让 Windows 文本模式把 LF 变 CRLF
        out_nl = P.detect_newline(out_path, default=os.linesep)

        entries, _ = P.extract_entries(src_lines)
        line_of = {}
        for idx, src in entries:
            key = (src or "").strip()
            if key and key not in line_of:
                line_of[key] = idx

        n_file = 0
        for src, dst in edits.items():
            idx = line_of.get((src or "").strip())
            if idx is None or idx >= len(out_lines):
                continue
            m = re.match(r'^([ \t]*)', src_lines[idx])
            indent = m.group(1) if m else ""
            new_line = indent + (dst or "")
            if out_lines[idx] == new_line:
                continue
            out_lines[idx] = new_line
            n_file += 1

        if not n_file:
            emit(f"[{i}/{len(paths)}] {name}：译文文件已是最新"
                 f"（缓存更新 {n_cache} 条）")
            files_done += 1
            continue

        try:
            tmp = out_path + ".tmp"
            with open(tmp, "w", encoding=config.OUTPUT_ENCODING,
                      newline="") as f:
                f.write(out_nl.join(out_lines))
            atomic_replace(tmp, out_path)
        except Exception as e:
            emit(f"  写入失败：{e}")
            continue

        emit(f"[{i}/{len(paths)}] {name}：已应用 {n_file} 句"
             f"（缓存更新 {n_cache} 条）→ {os.path.basename(out_path)}")
        applied += n_file
        files_done += 1

    bridge.progress(len(paths), len(paths), "完成")
    emit(f"\n✔ 应用已编辑完成：{files_done} 个文件，改写 {applied} 句"
         + (f"，{missing} 个文件缺少译文文件" if missing else ""))
    log.info("应用手工编辑完成：%d 个文件 / 改写 %d 句", files_done, applied)
    return {"files": files_done, "applied": applied,
            "missing": missing, "no_edit": no_edit}


# ================================================================
# 路径
# ================================================================
def _report_path():
    """检查报告路径：与输出文件同目录。"""
    out = config.Runtime.output_file
    d = os.path.dirname(out) or "."
    base = os.path.splitext(os.path.basename(out))[0]
    return os.path.join(d, f"{base}_report.txt")


def _unknown_ctrl_report_path():
    """与输入文件同目录，名为 <输入名>_unknown_ctrl.txt"""
    inp = config.Runtime.input_file
    d = os.path.dirname(inp) or "."
    base = os.path.splitext(os.path.basename(inp))[0]
    return os.path.join(d, f"{base}_unknown_ctrl.txt")


def _open_path(path):
    """用系统默认程序打开文件 / 目录（命令行版；失败返回 False）。"""
    try:
        if not os.path.exists(path):
            if os.path.splitext(path)[1]:        # 看起来是文件 → 建空文件
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                open(path, "a", encoding="utf-8").close()
            else:                                # 否则当目录
                os.makedirs(path, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        emit(f"打开失败：{e}，请手动打开：{path}")
        return False


# ================================================================
# 术语冲突记录（翻译时落盘，检查报告 / 冲突面板共用）
#   结构：{术语原文: {"old": 已有译文, "new": 模型返回的译文,
#                     "src": [命中该术语的句子, …]}}
# ================================================================
def _conflict_path():
    """术语冲突记录文件：与缓存文件同目录。"""
    cf = getattr(config.Runtime, "conflict_file", None)
    if cf:
        return cf
    cache = config.Runtime.cache_file
    d = os.path.dirname(cache) or "."
    base = os.path.splitext(os.path.basename(cache))[0]
    return os.path.join(d, f"{base}_conflicts.json")


def load_term_conflicts(path=None):
    """读取术语冲突记录，返回 dict；文件不存在 / 损坏时返回 {}。"""
    import json
    p = path or _conflict_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning("读取术语冲突记录失败：%s", e)
        return {}


def save_term_conflicts(data, path=None):
    """写入术语冲突记录（原子替换）。"""
    import json
    p = path or _conflict_path()
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data or {}, f, ensure_ascii=False, indent=2)
        atomic_replace(tmp, p)
        return True
    except Exception as e:
        log.warning("写入术语冲突记录失败：%s", e)
        return False


def _record_term_conflicts(records):
    """
    把本批次新发现的术语冲突并进记录文件。
    records: [{"src": 术语原文, "old": …, "new": …, "sentence": 句子}]
    """
    if not records:
        return
    data = load_term_conflicts()
    for r in records:
        key = r.get("src") or ""
        if not key:
            continue
        item = data.get(key)
        if not isinstance(item, dict):
            item = {"old": r.get("old", ""), "new": r.get("new", ""),
                    "src": []}
            data[key] = item
        item["old"] = r.get("old", item.get("old", ""))
        item["new"] = r.get("new", item.get("new", ""))
        sent = (r.get("sentence") or "").strip()
        if sent and sent not in item.setdefault("src", []):
            item["src"].append(sent)
    save_term_conflicts(data)


def drop_term_conflicts(terms):
    """冲突解决后，把这几个术语从记录里移除。"""
    data = load_term_conflicts()
    if not data:
        return 0
    n = 0
    for t in terms or []:
        if t in data:
            data.pop(t, None)
            n += 1
    if n:
        save_term_conflicts(data)
    return n


# 生成物后缀（选文件时要跳过 / 报告模式下要识别）
TRANSLATED_SUFFIX = "_translated.txt"
REPORT_SUFFIX     = "_translated_report.txt"
CACHE_SUFFIX      = "_cache.json"

# 「缓存 / 译文 / 报告」→ 源文件，按长到短匹配（_translated_report.txt 先于
# _translated.txt，否则会被切错）
_GENERATED_SUFFIXES = (REPORT_SUFFIX, TRANSLATED_SUFFIX, CACHE_SUFFIX)


def source_of(path):
    """
    把「缓存文件 / 译文文件 / 检查报告」换回它对应的**源文件**路径；
    本来就是源文件的原样返回。

    ★ 菜单 4（术语重翻）/ 6（中文润色）只允许选 `*_cache.json`、
      菜单 7（换行重排）只允许选 `*_translated.txt`，而后面的流程都是按
      **源文件**推导缓存与译文路径的（Runtime.set_input），所以要先换算一步，
      否则会拼出 `xxx_cache_cache.json` 这种鬼东西。
    """
    if not path:
        return path
    low = str(path).lower()
    for suf in _GENERATED_SUFFIXES:
        if low.endswith(suf):
            return path[: -len(suf)] + ".txt"
    return path


def cache_path_for(path):
    """源文件 / 译文 / 缓存 → 对应的翻译缓存路径（*_cache.json）。"""
    if not path:
        return None
    src = source_of(path)
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(os.path.dirname(os.path.abspath(src)),
                        f"{stem}{CACHE_SUFFIX}")


def translated_path_for(path):
    """源文件 / 译文 / 缓存 → 对应的译文文件路径（*_translated.txt）。"""
    if not path:
        return None
    src = source_of(path)
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(os.path.dirname(os.path.abspath(src)),
                        f"{stem}{TRANSLATED_SUFFIX}")


def report_path_for(src_path):
    """源文件 → 对应检查报告路径。"""
    if not src_path:
        return None
    src = source_of(src_path)
    stem = os.path.splitext(os.path.basename(src))[0]
    parent = os.path.dirname(os.path.abspath(src))
    return os.path.join(parent, f"{stem}{REPORT_SUFFIX}")


def source_path_for_report(report_path):
    """
    检查报告 → 原始源文件路径。
    报告名为 <原名>_translated_report.txt，反推源文件时按常见扩展名试，
    找不到就在同目录里按前缀匹配。
    """
    if not report_path:
        return None
    base = os.path.basename(report_path)
    d = os.path.dirname(os.path.abspath(report_path))
    if not base.lower().endswith(REPORT_SUFFIX):
        return report_path if os.path.exists(report_path) else None

    stem = base[: -len(REPORT_SUFFIX)]
    for ext in (".txt", ".TXT", ".json", ".yml", ".yaml", ".csv", ""):
        p = os.path.join(d, stem + ext)
        if os.path.isfile(p):
            return p

    try:
        for f in sorted(os.listdir(d)):
            low = f.lower()
            if (low.startswith(stem.lower() + ".")
                    and not (low.endswith(TRANSLATED_SUFFIX)
                             or low.endswith(REPORT_SUFFIX))):
                return os.path.join(d, f)
    except OSError:
        pass
    return None


def _write_unknown_ctrl_report(hits, report_path):
    """hits: [(token, original, context), ...]"""
    grouped = defaultdict(list)
    for token, orig, ctx in hits:
        grouped[token].append((orig, ctx))

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 未识别控制码报告\n")
        f.write(f"# 共 {len(grouped)} 种，{len(hits)} 次\n")
        f.write("#\n")
        f.write("# 这些控制码不在 processor.py 的名单中，\n")
        f.write("# 可能被模型误翻或丢失。请手工确认是否要加入名单。\n")
        f.write("=" * 70 + "\n\n")

        for token, items in sorted(grouped.items(),
                                   key=lambda x: (-len(x[1]), x[0])):
            f.write(f"[{token}]  出现 {len(items)} 次\n")
            for orig, ctx in items[:3]:
                f.write(f"  原文：  {orig[:100]}\n")
                f.write(f"  上下文：{ctx[:100]}\n")
            if len(items) > 3:
                f.write(f"  … 其余 {len(items) - 3} 次省略\n")
            f.write("\n")

    return report_path


# ================================================================
# 命令行：语言 / 文件范围选择
# ================================================================
def _pick_language(prompt, default_key, exclude=None):
    """交互式语言选择。返回选中的语言字符串，或 None 表示取消。"""
    emit(f"\n{prompt}")
    for i, lang in enumerate(LANG_OPTIONS, 1):
        mark = ""
        if lang == default_key:
            mark = "   ← 上次使用"
        if exclude and lang == exclude:
            mark = "   (已被选为另一种语言)"
        emit(f"  {i:>2}. {lang}{mark}")
    emit("   0. 自定义（手动输入）")

    hint = f"[{default_key}]" if default_key else "[回车跳过]"
    raw = input(f"请选择 {hint}: ").strip()

    if not raw:
        return default_key or None
    if raw == "0":
        custom = input("请输入语言名（如 English / 日本語）：").strip()
        return custom or None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(LANG_OPTIONS):
            return LANG_OPTIONS[idx]
    emit("无效输入")
    return None


def _ask_languages():
    """命令行翻译前询问语言方向，返回 False 表示取消。"""
    if not getattr(config, "ASK_LANG_EACH_TIME", True):
        emit(f"\n  翻译方向：{config.SOURCE_LANG} → {config.TARGET_LANG}")
        return True

    src_lang = _pick_language("请选择【源语言】：", config.SOURCE_LANG)
    if not src_lang:
        emit("已取消")
        return False

    tgt_lang = _pick_language("请选择【目标语言】：",
                              config.TARGET_LANG, exclude=src_lang)
    if not tgt_lang:
        emit("已取消")
        return False

    if src_lang == tgt_lang:
        emit(f"\n⚠ 源语言和目标语言相同（{src_lang}）")
        if input("继续？(y/N): ").strip().lower() != "y":
            return False

    settings.set_value("SOURCE_LANG", src_lang)
    settings.set_value("TARGET_LANG", tgt_lang)
    log.info("翻译方向：%s → %s", src_lang, tgt_lang)
    emit(f"\n  翻译方向：{src_lang} → {tgt_lang}")
    return True


def _select_scope_interactive(title="选择要处理的文件"):
    """
    命令行：单个文件 / 整个文件夹。
    返回路径列表，或 None 表示取消。
    """
    import filepicker

    emit("")
    emit(f"[{title}]")
    emit("  1. 单个文件")
    emit("  2. 整个文件夹（其中的 .txt）")
    raw = input("请选择 [1]: ").strip() or "1"

    default_dir = config.Runtime.last_dir or config.BASE_DIR

    if raw == "2":
        folder = filepicker.pick_dir(
            initial_dir=default_dir,
            title="选择包含 .txt 的文件夹",
        )
        if not folder:
            emit("已取消")
            return None
        files = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".txt")
            and not f.lower().endswith(("_translated.txt",))
        )
        if not files:
            emit(f"文件夹里没有 .txt 文件：{folder}")
            return None
        config.Runtime.set_dir(folder)
        emit(f"\n文件夹：{folder}")
        emit(f"共 {len(files)} 个 .txt 文件：")
        for f in files:
            emit(f"  - {os.path.basename(f)}")
        if input("\n开始处理？(Y/n): ").strip().lower() == "n":
            return None
        return files

    path = filepicker.pick_text_file(
        initial_dir=default_dir,
        title=title,
    )
    if not path:
        emit("已取消")
        return None
    return [path]


def _apply_lang_model(src_lang=None, tgt_lang=None, model=None):
    """把 GUI/命令行选定的语言与模型写进配置（当前会话立即生效）。"""
    if src_lang:
        settings.set_value("SOURCE_LANG", src_lang)
    if tgt_lang:
        settings.set_value("TARGET_LANG", tgt_lang)
    if model:
        key = ("API_MODEL"
               if str(getattr(config, "TRANSLATE_MODE", "ollama")).lower() == "api"
               else "MODEL")
        settings.set_value(key, model)
    return True


# ================================================================
# 占位符兜底
# ================================================================
def _force_restore(raw, maps, src=None):
    """
    兜底补回丢失的占位符。

    返回【token 形态】的文本（仍含 @N@ / ⟦N⟧），由调用方后续的
    PR.finalize()→restore() 统一还原为控制码。
    （此前返回已还原文本会导致 verify 再次判失败、整条被丢弃，已修正。）
    """
    if not maps:
        return raw

    # ★ 被合并进连续占位符的成员（consumed）由 merged 项代表，
    #   模型输出里本来就只有合并后的 @K@，不能当「缺失」处理
    missing = [item["token"] for item in maps
               if not item.get("consumed") and item["token"] not in raw]
    if not missing:
        return raw

    missing_set = set(missing)
    result = raw

    for m_idx, item in enumerate(maps):
        token = item["token"]
        if token not in missing_set or item.get("consumed"):
            continue
        original = item.get("original", "")

        new_result = _insert_token_by_hint(
            result, token, original, maps, m_idx, missing_set, src=src
        )
        if new_result is not None:
            result = new_result
        else:
            result = result.rstrip() + " " + token
        missing_set.discard(token)

    return result


def _insert_token_by_hint(text, token, original, maps, m_idx, missing_set,
                          src=None):
    """返回插入后的文本，或 None 表示无法判断。"""
    if not original:
        return None

    # ① 说话人/标签起始：\tg[... 或 [xxx... → 句首
    if original.startswith("\\tg["):
        return token + text

    # ② 说话人结束 ]
    if original == "]":
        for i in range(m_idx - 1, -1, -1):
            prev_item = maps[i]
            prev_orig = prev_item.get("original", "")
            prev_token = prev_item["token"]
            if prev_orig.startswith("\\tg[") and prev_token in text:
                pos = text.find(prev_token) + len(prev_token)
                return text[:pos] + token + text[pos:]
        for i, ch in enumerate(text):
            if ch.isspace() or ch in "，。！？、；：!?,.;:":
                return text[:i] + token + text[i:]
        return text + token

    # ③ 换行符 \n \N → 最后一个句末标点后
    if original in ("\\n", "\\N"):
        for i in range(len(text) - 1, -1, -1):
            if text[i] in "。！？!?.":
                return text[:i + 1] + token + text[i + 1:]
        return text + token

    # ④ 找后 anchor，插到它前面
    for i in range(m_idx + 1, len(maps)):
        next_token = maps[i]["token"]
        if next_token in text:
            pos = text.find(next_token)
            return text[:pos] + token + text[pos:]

    # ⑤ 找前 anchor，插到它后面
    for i in range(m_idx - 1, -1, -1):
        prev_token = maps[i]["token"]
        if prev_token in text:
            pos = text.find(prev_token) + len(prev_token)
            return text[:pos] + token + text[pos:]

    # ⑥ 有源文时按占位符原内容在源文中的相对位置插回
    #    （比单纯追加更贴近原句，尤其 @N@ 这类插值变量的位置）
    if src and original:
        idx = src.find(original)
        if idx >= 0:
            ratio = idx / max(1, len(src))
            pos = int(round(len(text) * ratio))
            pos = max(0, min(len(text), pos))
            return text[:pos] + token + text[pos:]

    return None


# ================================================================
# 分批策略：条数 + 总字符数双限制
# ================================================================
def _make_batches(todo, batch_size=None, max_chars=None):
    """
    batch_size: 单批最多条数
    max_chars : 单批原文总字符上限（防止超长句挤爆上下文）
    """
    batch_size = batch_size or config.BATCH_SIZE
    max_chars = max_chars or getattr(config, "MAX_BATCH_CHARS", 1400)

    batches, cur, cur_chars = [], [], 0
    for txt in todo:
        cur.append(txt)
        cur_chars += len(txt) + 8
        if len(cur) >= batch_size or cur_chars >= max_chars:
            batches.append(cur)
            cur, cur_chars = [], 0
    if cur:
        batches.append(cur)
    return batches


# ================================================================
# 内部：翻译一批
# ================================================================
def _translate_batch(client, batch_texts, cache,
                     unknown_ctrl_hits, failed, extra_hits,
                     mode_of_entry=None, bi=1, conflict_records=None):
    """翻译一批文本，写入缓存。返回成功条数。"""
    if not batch_texts:
        return 0

    import prefix_dict as PFD

    batch, maps_dict, breaks_dict = [], {}, {}
    batch_terms = {}
    hit_terms_all = {}
    prefix_list = {}
    new_prefixes = 0
    new_prefix_keys = []

    log.info("[批 %d] 开始  %d 条", bi, len(batch_texts))

    for k, txt in enumerate(batch_texts):
        # 前缀提取
        if getattr(config, "PREFIX_DICT_ENABLE", True):
            prefix, body = PR.split_prefix(txt)
            prefix_list[k] = prefix
            if prefix and PFD.register_prefix(prefix):
                new_prefixes += 1
                new_prefix_keys.append(prefix)
        else:
            prefix_list[k] = ""
            body = txt

        # 玩家名替换
        if getattr(config, "PLAYER_TOKEN", None):
            body = body.replace(config.PLAYER_TOKEN,
                                config.PLAYER_PLACEHOLDER)

        # 保护 + 术语查找
        safe, maps, breaks, hit_terms = PR.prepare(body)
        batch.append((k, safe))
        maps_dict[k] = maps
        breaks_dict[k] = breaks

        log.debug("[批 %d][%d] 送模型=%r", bi, k, safe)

        for src_term, dst_term in hit_terms:
            hit_terms_all.setdefault(src_term, dst_term)

        for token, ctx in PR.detect_unknown_ctrl(safe):
            unknown_ctrl_hits.append((token, txt, ctx))

    if new_prefixes:
        PFD.save()
        filled = sum(1 for p in new_prefix_keys if PFD.get_translation(p))
        msg = (f"  [前缀] 发现 {new_prefixes} 个新前缀，已加入 prefix_dict.json")
        if filled:
            msg += f"（其中 {filled} 个命中术语，已自动填入译文）"
        emit(msg)
        log.info("[批 %d] 新增前缀 %d 个（术语自动填入 %d 个）",
                 bi, new_prefixes, filled)

    term_pairs_list = list(hit_terms_all.items())
    if term_pairs_list:
        log.info("[批 %d] 命中术语 %d 条，随 prompt 发送",
                 bi, len(term_pairs_list))

    # ---------- 请求模型 ----------
    t_req = time.time()
    result = translate_with_retry(client, batch,
                                  terms_out=batch_terms,
                                  term_pairs=term_pairs_list)
    log.info("[批 %d] 模型返回 %d 条，耗时 %.1fs",
             bi, len(result), time.time() - t_req)

    # 缺失 / 回显原文 → 单条重试
    echo_check = getattr(config, "TREAT_ECHO_AS_FAIL", True)
    missing = []
    for k, safe in batch:
        v = result.get(k)
        if not v or not v.strip():
            missing.append((k, safe))
        elif echo_check and v.strip() == safe.strip():
            # 模型原样回显，多半没翻
            missing.append((k, safe))
    if missing:
        log.warning("[批 %d] 缺失/回显 %d 条，单条重试", bi, len(missing))

    for k, safe in missing:
        for attempt in range(config.SINGLE_RETRIES):
            try:
                r = translate_with_retry(client, [(k, safe)],
                                         terms_out=batch_terms,
                                         term_pairs=term_pairs_list)
                v = r.get(k)
                if v and v.strip() and v.strip() != safe.strip():
                    result[k] = v
                    break
            except Exception as e:
                log.debug("[批 %d][%d] 单条重试 %d 失败：%s",
                          bi, k, attempt + 1, e)
                time.sleep(1.5)

    # ---------- 写入缓存 ----------
    ok = 0
    for k, src in enumerate(batch_texts):
        raw = result.get(k)
        if not raw:
            log.warning("[批 %d][%d] 无返回", bi, k)
            failed.append({'src': src, 'reason': '模型无返回'})
            continue

        maps = maps_dict[k]

        # 占位符校验
        ok_ph, missing_ph = PR.verify(raw, maps)
        if not ok_ph:
            log.warning("[批 %d][%d] 占位符丢失 %s", bi, k, missing_ph)
            retried = False
            # ★ 针对性重试：明确告诉模型它丢了哪些占位符，必须原样保留
            ph_hint = ("注意：你上一版译文丢失了占位符 "
                       + "、".join(missing_ph)
                       + "。请重新翻译，并务必原样保留每一个 @N@ / ⟦N⟧"
                         "（数量、位置、数字都不变，不翻译 @ 和数字）。")
            for attempt in range(config.SINGLE_RETRIES):
                try:
                    r = translate_with_retry(client, [(k, batch[k][1])],
                                             terms_out=batch_terms,
                                             term_pairs=term_pairs_list,
                                             extra_instruction=ph_hint)
                    if k in r and r[k].strip():
                        ok3, _ = PR.verify(r[k], maps)
                        if ok3:
                            raw = r[k]
                            retried = True
                            break
                except Exception:
                    time.sleep(1.0)
            if not retried:
                raw = _force_restore(raw, maps, src=src)
                log.info("[批 %d][%d] 占位符兜底补回", bi, k)
                extra_hits.append({
                    'src': src,
                    'kind': '占位符兜底',
                    'dst': raw,
                    'detail': f'占位符 {missing_ph} 丢失，已按位置特征补回',
                })

            ok_final, _ = PR.verify(raw, maps)
            if not ok_final:
                log.error("[批 %d][%d] 占位符仍失败，保留原文", bi, k)
                failed.append({'src': src, 'reason': '占位符丢失无法恢复'})
                continue

        # 还原 + 拼回前缀
        mode = "newline"
        if mode_of_entry:
            mode = mode_of_entry.get(src, "newline")

        body_final = PR.finalize(raw, maps, breaks_dict.get(k), mode=mode)

        if getattr(config, "PLAYER_TOKEN", None):
            body_final = _restore_player_token(body_final)

        # ★ 控制码回退：译文里缺失/未原样保留的控制码，一律按原文补回
        #   前缀是交给前缀字典单独处理的（可能已被用户或术语改写成另一套控制码），
        #   所以校验时把前缀从原文侧剔除，只比真正参与翻译的正文部分：
        #     · 避免把字典已处理的前缀误判成"译文缺失控制码"（否则会谎报并回退原文）
        #     · 正文里真正丢失的控制码照样会被检测并补回
        prefix = prefix_list.get(k, "")
        src_body = (src[len(prefix):]
                    if (prefix and src.startswith(prefix)) else src)

        if prefix:
            # ★ 模型有时会把前缀原样回显；旧版缓存里也可能已经带过前缀。
            #   先剥掉再拼当前前缀，否则会出现 `\tg[新]\tg[旧]正文`。
            body_final = PFD.strip_prefix_echo(body_final, prefix, src_body)
            final = PFD.apply_prefix(prefix) + body_final
        else:
            final = body_final

        final, fixed_ctrl = PR.repair_missing_controls(src_body, final)
        if fixed_ctrl:
            log.warning("[批 %d][%d] 译文缺失控制码 %s，已按原文补回",
                        bi, k, fixed_ctrl)
            extra_hits.append({
                'src': src,
                'kind': '控制码回退',
                'dst': final,
                'detail': f'译文缺失控制码 {fixed_ctrl}，已按原文原样补回',
            })

        log.debug("[批 %d][%d] 最终译文=%r", bi, k, final)
        cache.put(src, final)
        ok += 1

    # ---------- 术语合并（内联提取） ----------
    if getattr(config, "AUTO_EXTRACT_TERMS", True) and batch_terms:
        try:
            import auto_terms
            conflicts = []
            added = auto_terms.merge_from_translation(
                batch_terms, PR, conflicts_out=conflicts
            )
            if added:
                emit(f"  [术语] 新增 {added} 条，已应用到后续批次")
                log.info("[批 %d] 术语新增 %d 条", bi, added)

            if conflicts:
                log.warning("[批 %d] 术语冲突 %d 条", bi, len(conflicts))
                matched = {}          # 术语原文 → 命中的句子
                for idx, terms in batch_terms.items():
                    if not (0 <= idx < len(batch_texts)):
                        continue
                    info = _match_conflict(terms, conflicts)
                    if not info:
                        continue
                    src_text = batch_texts[idx]
                    matched.setdefault(info['src'], src_text)
                    extra_hits.append({
                        'src': src_text,
                        'kind': '术语冲突',
                        'dst': cache.get(src_text, ''),
                        'detail': (f"术语冲突：{info['src']} "
                                   f"已有 {info['old']}，"
                                   f"模型返回 {info['new']}"),
                        # ★ 结构化字段，供「解决术语冲突」面板使用
                        'term_src': info['src'],
                        'term_old': info['old'],
                        'term_new': info['new'],
                    })
                if conflict_records is not None:
                    for c in conflicts:
                        conflict_records.append({
                            "src": c.get("src", ""),
                            "old": c.get("old", ""),
                            "new": c.get("new", ""),
                            "sentence": matched.get(c.get("src", ""), ""),
                        })
        except Exception as e:
            log.warning("术语合并失败：%s", e)

    return ok


def _restore_player_token(text):
    """
    把玩家名占位文本还原成控制码。
    模型可能把它拆开（"玛 俐 大 小 姐"）或改写，除精确匹配外再做一次宽松匹配。
    """
    token = getattr(config, "PLAYER_TOKEN", None)
    ph = getattr(config, "PLAYER_PLACEHOLDER", None)
    if not token or not ph:
        return text

    if ph in text:
        return text.replace(ph, token)

    loose = re.compile(r"\s*".join(re.escape(ch) for ch in ph))
    m = loose.search(text)
    if m:
        return text[:m.start()] + token + text[m.end():]
    return text


def _match_conflict(terms, conflicts):
    """在一批术语里找出与冲突列表相交的那一条。"""
    keys = {k.lower() for k in terms.keys()}
    for c in conflicts:
        if c['src'].lower() in keys:
            return c
    return None


# ================================================================
# 内部：翻译单个文件（核心流程）
# ================================================================
def _translate_core(src_path, lines=None, newline=None, show_header=True):
    """对单个文件执行完整翻译流程（Runtime 已设置好 input/output/cache）。"""
    out_path = config.Runtime.output_file
    cache_path = config.Runtime.cache_file

    if show_header:
        emit(f"\n{'=' * 55}")
        emit(f"  翻译：{src_path}")
        emit(f"  输出：{out_path}")
        emit(f"{'=' * 55}")

    PR.load_terms()

    if lines is None:
        lines, newline = P.read_file(src_path, config.INPUT_ENCODING)
    newline = newline or "\n"

    entries, special = P.extract_entries(lines)

    line_modes = P.get_block_modes(lines)
    mode_of_entry = {}
    for ln, src_text in entries:
        if src_text not in mode_of_entry and 0 <= ln < len(line_modes):
            mode_of_entry[src_text] = line_modes[ln]

    log.info("文件 %d 行  待翻 %d  特殊 %d",
             len(lines), len(entries), len(special))
    emit(f"[解析] 总行数 {len(lines)}  待翻 {len(entries)}  特殊 {len(special)}")

    if not entries:
        emit("没有可翻译的内容")
        return {"entries": 0, "todo": 0, "done": 0, "failed": 0}

    cache = Cache(cache_path)

    seen, todo = set(), []
    skipped_pure = 0
    skipped_path = 0
    for _, txt in entries:
        if txt in seen:
            continue
        seen.add(txt)
        if txt in cache:
            continue
        if getattr(config, "SKIP_PURE_CONTROL", True) and PR.is_pure_control(txt):
            cache.put(txt, txt)
            skipped_pure += 1
            continue
        # ★ 资源路径（Graphics/Pictures/xxx）不翻译，原样保留
        if getattr(config, "SKIP_PATH_LINES", True) and PR.is_path_like(txt):
            cache.put(txt, txt)
            skipped_path += 1
            continue
        todo.append(txt)

    if skipped_pure:
        cache.save()
        log.info("跳过纯控制符句子 %d 条（已缓存原文）", skipped_pure)
        emit(f"[过滤] 跳过 {skipped_pure} 条纯控制符句子（不送模型）")

    if skipped_path:
        cache.save()
        log.info("跳过资源路径句子 %d 条（已缓存原文）", skipped_path)
        emit(f"[过滤] 跳过 {skipped_path} 条资源路径（形如 A/B/C，不翻译）")

    emit(f"[待翻] 唯一 {len(seen)}  需翻 {len(todo)}  "
         f"缓存命中 {len(seen) - len(todo)}")

    # ---------- 批量翻译 ----------
    unknown_ctrl_hits = []
    failed = []
    extra_hits = []
    conflict_records = []      # ★ 术语冲突：落盘后供检查报告 / 冲突面板复用

    if todo:
        if getattr(config, "SORT_TODO_BY_LEN", True):
            todo.sort(key=len)

        client = OllamaClient()
        batches = _make_batches(todo)
        done = 0
        t0 = time.time()
        total = len(todo)

        for bi, batch_texts in enumerate(batches, 1):
            if bridge.cancelled():
                emit("\n[中断] 用户取消")
                cache.save(force=True)
                break

            ok = _translate_batch(client, batch_texts, cache,
                                  unknown_ctrl_hits, failed, extra_hits,
                                  mode_of_entry=mode_of_entry,
                                  bi=bi,
                                  conflict_records=conflict_records)

            cache.tick()
            done += len(batch_texts)
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate / 60 if rate > 0 else 0
            log.info("[批 %d] 成功 %d/%d  累计 %d/%d  %.2f条/秒  ETA %.1f分",
                     bi, ok, len(batch_texts), done, total, rate, eta)
            bridge.progress(done, total, f"{done}/{total} 条")

        cache.save(force=True)

        if failed:
            log.warning("失败 %d 条", len(failed))
            emit(f"\n[失败] {len(failed)} 条未翻译：")
            for t in failed[:10]:
                emit(f"    {t['src'][:70]}   （{t['reason']}）")
            if len(failed) > 10:
                emit(f"    … 其余 {len(failed) - 10} 条省略")
    else:
        cache.save(force=True)

    # ---------- 术语冲突记录落盘（供检查报告 / 冲突面板复用） ----------
    if conflict_records:
        _record_term_conflicts(conflict_records)
        emit(f"  [术语冲突] 记录 {len(conflict_records)} 条，"
             f"可在菜单 3 用「解决术语冲突」处理")

    # ---------- 回写 ----------
    translations = {txt: cache.get(txt) for _, txt in entries if cache.get(txt)}
    replaced = P.write_output(
        lines, entries, translations,
        out_path, newline, config.OUTPUT_ENCODING,
    )
    log.info("回写：%d/%d → %s", replaced, len(entries), out_path)
    emit(f"\n✔ 输出：{out_path}")
    emit(f"  替换 {replaced}/{len(entries)} 条")

    # ---------- 自动检查 ----------
    emit("\n[检查] 生成检查报告…")
    try:
        out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
        report_path = _report_path()
        hits = checker.check(lines, out_lines, entries, special, report_path,
                             extra_hits=failed + extra_hits)
        _print_summary(hits, report_path)
    except Exception as e:
        log.error("自动检查失败：%s", e)
        emit(f"  自动检查失败（不影响翻译结果）：{e}")

    # ---------- 未识别控制码报告 ----------
    if unknown_ctrl_hits:
        try:
            uc_path = _unknown_ctrl_report_path()
            _write_unknown_ctrl_report(unknown_ctrl_hits, uc_path)
            kinds = Counter(t for t, _, _ in unknown_ctrl_hits)
            emit("\n⚠ 检测到未识别控制码：")
            for tok, n in kinds.most_common(10):
                emit(f"    {tok}  × {n}")
            if len(kinds) > 10:
                emit(f"    … 其余 {len(kinds) - 10} 种省略")
            emit(f"  报告：{uc_path}")
        except Exception as e:
            log.error("写未识别控制码报告失败：%s", e)

    # ---------- 前缀字典统计 ----------
    if getattr(config, "PREFIX_DICT_ENABLE", True):
        try:
            import prefix_dict as PFD
            s = PFD.stats()
            if s["pending"]:
                emit(f"\n[前缀字典] 共 {s['total']} 条，"
                     f"已翻译 {s['done']} 条，待翻译 {s['pending']} 条")
                emit("  请到菜单 5「前缀字典」补全译文后应用")
        except Exception as e:
            log.debug("前缀字典统计失败：%s", e)

    # ---------- 更新术语快照 ----------
    _update_snapshot()

    return {
        "entries": len(entries),
        "todo": len(todo),
        "done": len(todo) - len(failed),
        "failed": len(failed),
    }


def _update_snapshot():
    try:
        import term_sync as TS
        current_terms = TS.load_current_terms()
        if current_terms:
            TS.save_snapshot(current_terms)
            log.info("术语表快照已更新：%d 条", len(current_terms))
    except Exception as e:
        log.warning("建立术语表快照失败：%s", e)


def _print_summary(hits, report_path):
    c = Counter(h['kind'] for h in hits)
    emit(f"  共 {len(hits)} 处问题：")
    for k in ('翻译失败', '占位符兜底', '术语冲突',
              '疑似未翻译', '疑似异常句',
              '符号不匹配', '译文残留控制码', '译文残留占位符', '特殊行'):
        if c.get(k):
            emit(f"    {k}: {c[k]}")
    emit(f"  报告：{report_path}")


# ================================================================
# 核心 1：翻译
# ================================================================
def translate_paths(paths, src_lang=None, tgt_lang=None, model=None):
    """
    翻译一组文件（无交互）。返回统计 dict。
    """
    _apply_lang_model(src_lang, tgt_lang, model)

    log.info("=" * 50)
    log.info("开始翻译  共 %d 个文件  方向 %s → %s",
             len(paths), config.SOURCE_LANG, config.TARGET_LANG)

    total = len(paths)
    processed = 0
    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        config.Runtime.set_input(path)
        bridge.progress(i - 1, total, os.path.basename(path))

        try:
            lines, newline = P.read_file(path, config.INPUT_ENCODING)
        except Exception as e:
            emit(f"[跳过] 读取失败：{e}")
            continue

        if total > 1:
            emit(f"\n[{i}/{total}] {os.path.basename(path)}")

        try:
            _translate_core(path, lines, newline,
                            show_header=(total == 1))
            processed += 1
        except bridge.CancelRequested:
            emit("\n[中断] 用户取消")
            break

    bridge.progress(total, total, "完成")
    config.Runtime.save()

    if total > 1:
        emit(f"\n{'=' * 55}")
        emit(f"  批量翻译完成，共处理 {processed}/{total} 个文件")
        emit(f"{'=' * 55}")

    return {"files": processed, "total": total}


# ================================================================
# 核心：检查
# ================================================================
def check_file(path, write_report=True):
    """
    对单个文件跑一次检查，返回 hits 列表；文件缺失返回 None。
    """
    config.Runtime.set_input(path)
    inp = config.Runtime.input_file
    out = config.Runtime.output_file

    if not os.path.exists(inp):
        emit(f"缺少输入文件：{inp}")
        return None
    if not os.path.exists(out):
        emit(f"缺少输出文件：{out}（先跑一次翻译）")
        return None

    try:
        src_lines, _ = P.read_file(inp, config.INPUT_ENCODING)
        out_lines, _ = P.read_file(out, config.OUTPUT_ENCODING)
    except Exception as e:
        emit(f"读取失败：{e}")
        return None

    entries, special = P.extract_entries(src_lines)
    report_path = _report_path()
    hits = checker.check(src_lines, out_lines, entries, special, report_path,
                         extra_hits=_conflicts_as_hits(entries, out_lines))
    return hits


def _conflicts_as_hits(entries=None, out_lines=None):
    """
    读取落盘的术语冲突记录，转成 checker 能吃的 extra_hits。
    这样菜单 2 单独刷新报告时也能看到（并处理）术语冲突。
    entries/out_lines 用来把冲突关联回具体句子，顺便补上译文。
    """
    data = load_term_conflicts()
    if not data:
        return []

    line_of = {}
    for ln, s in (entries or []):
        k = (s or "").strip()
        if k and k not in line_of:
            line_of[k] = ln

    def _dst_of(sent):
        if not sent:
            return ""
        ln = line_of.get(sent.strip())
        if ln is None or out_lines is None or ln >= len(out_lines):
            return ""
        return out_lines[ln].strip()

    hits = []
    for term, item in data.items():
        if not isinstance(item, dict):
            continue
        old = item.get("old", "")
        new = item.get("new", "")
        detail = f"术语冲突：{term} 已有 {old}，模型返回 {new}"
        sents = item.get("src") or []
        if not sents:
            sents = [""]
        for s in sents:
            hits.append({
                'src': s, 'kind': '术语冲突', 'dst': _dst_of(s),
                'detail': detail,
                'term_src': term, 'term_old': old, 'term_new': new,
            })
    log.info("载入术语冲突记录 %d 条", len(hits))
    return hits


def check_paths(paths):
    """批量检查，返回 {path: hits}。"""
    result = {}
    for i, path in enumerate(paths, 1):
        bridge.progress(i - 1, len(paths), os.path.basename(path))
        hits = check_file(path)
        if hits is not None:
            result[path] = hits
    bridge.progress(len(paths), len(paths), "检查完成")
    return result


# ================================================================
# 核心 2：重翻检查报告内容
# ================================================================
def retranslate_report_paths(paths, src_lang=None, tgt_lang=None, model=None,
                             kinds=None):
    """
    扫描输出文件，找出问题句，删缓存后重翻。

    kinds: 只重翻这些问题类型（None = 用默认的 RETRANSLATE_KINDS）。
           ★「译文残留控制码」等 NEVER_RETRANSLATE_KINDS 里的类型、
             以及手工编辑产生的 MANUAL_KINDS（「已编辑」）都不会参与重翻 ——
             手工改过的句子一旦被重翻就白改了。
    """
    _apply_lang_model(src_lang, tgt_lang, model)

    active = set(RETRANSLATE_KINDS) if kinds is None else set(kinds)
    active -= NEVER_RETRANSLATE_KINDS
    active -= MANUAL_KINDS
    active = {k for k in active if k}          # 去掉空类型

    log.info("=" * 50)
    log.info("重翻检查报告内容  共 %d 个文件  类型=%s",
             len(paths), "、".join(sorted(active)) or "（空）")
    emit(f"  重翻类型：{'、'.join(sorted(active)) if active else '（未选择）'}")
    emit(f"  跳过类型：{'、'.join(sorted(NEVER_RETRANSLATE_KINDS | MANUAL_KINDS))}")

    if not active:
        emit("  没有勾选任何可重翻的类型，已取消")
        return {"files": 0, "removed": 0, "skipped": True}

    total_removed = 0
    files_done = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        config.Runtime.set_input(path)
        bridge.progress(i - 1, len(paths), os.path.basename(path))
        emit(f"\n[{i}/{len(paths)}] {os.path.basename(path)}")

        hits = check_file(path)
        if hits is None:
            continue

        if not hits:
            emit("  ✔ 没有发现问题，无需重翻")
            continue

        kinds_cnt = Counter(h['kind'] for h in hits)
        emit("  问题分布：" + "  ".join(f"{k}:{n}"
                                       for k, n in kinds_cnt.items()))

        # ★ 句子白名单：加了白名单的句子不再重翻（用户手动确认过没问题）
        wl_sent = checker.user_sentences()
        picked = [h for h in hits if h['kind'] in active]
        to_re = [h for h in picked
                 if (h.get('src') or '').strip() not in wl_sent]

        wl_hit = len(picked) - len(to_re)
        if wl_hit:
            emit(f"  白名单跳过：{wl_hit} 条")

        if not to_re:
            emit(f"  勾选的类型（{'、'.join(sorted(active))}）里没有可重翻的句子"
                 f"，已跳过")
            continue

        emit(f"  待重翻：{len(to_re)} 条")
        for h in to_re[:8]:
            emit(f"    [{h['kind']}] 行 {h['line_no']}  {h['src'][:60]}")

        cache = Cache(config.Runtime.cache_file)
        before = len(cache)
        removed = cache.remove_many({h['src'] for h in to_re})
        cache.save(force=True)
        total_removed += removed
        emit(f"  ✔ 已删除 {removed} 条缓存（原 {before} 条）")

        lines, newline = P.read_file(path, config.INPUT_ENCODING)
        _translate_core(path, lines, newline, show_header=False)
        files_done += 1

    bridge.progress(len(paths), len(paths), "完成")
    return {"files": files_done, "removed": total_removed}


# ================================================================
# 核心 3：术语更新后重翻
# ================================================================
def analyze_terms():
    """
    对比快照，返回 (current, added, removed, modified, old_keyonly)。
    无快照时返回 (current, None, None, None, False)。
    """
    import term_sync as TS
    current = TS.load_current_terms()
    if not TS.snapshot_exists():
        return current, None, None, None, False
    added, removed, modified, old_keyonly = TS.diff_terms()
    return current, added, removed, modified, old_keyonly


def retranslate_terms_paths(paths, src_lang=None, tgt_lang=None, model=None,
                            extra_terms=None):
    """
    术语更新后重翻。
    extra_terms: GUI 刚编辑过的术语，会强制纳入「受影响术语」。
    """
    _apply_lang_model(src_lang, tgt_lang, model)

    import term_sync as TS

    log.info("=" * 50)
    log.info("术语更新后重翻")

    current = TS.load_current_terms()
    if not current:
        emit("术语表为空或不存在，请先运行菜单 8 生成")
        return {"files": 0, "removed": 0}

    if not TS.snapshot_exists():
        emit("未找到快照，已把当前术语表记录为基准，本次不重翻")
        TS.save_snapshot(current)
        return {"files": 0, "removed": 0, "baseline": True}

    added, removed, modified, old_keyonly = TS.diff_terms()
    added = list(added or [])
    modified = list(modified or [])

    for t in (extra_terms or []):
        if t not in added and t not in modified:
            modified.append(t)

    emit(f"  当前术语：{len(current)} 条")
    emit(f"  新增：{len(added)}  修改：{len(modified)}  删除：{len(removed or [])}")

    affected = list(added) + list(modified)
    if not affected:
        emit("术语表没有变化，无需重翻")
        TS.save_snapshot(current)
        return {"files": 0, "removed": 0}

    if added:
        emit("  新增示例：" + "、".join(
            f"{t}→{current.get(t, '')}" for t in added[:8]))

    total_removed = 0
    files_done = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        # ★ 本菜单只允许选缓存文件（*_cache.json），先换回源文件再交给
        #   Runtime.set_input 推导缓存 / 译文路径
        src_path = source_of(path)
        if not os.path.exists(src_path):
            emit(f"  找不到对应的源文件：{src_path}")
            continue

        config.Runtime.set_input(src_path)
        bridge.progress(i - 1, len(paths), os.path.basename(src_path))

        if not os.path.exists(config.Runtime.cache_file):
            emit(f"  缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
            continue

        cache = Cache(config.Runtime.cache_file)
        hits = TS.find_affected_cache(cache.data, affected)
        if not hits:
            emit(f"  [{os.path.basename(src_path)}] 没有句子命中这些术语")
            continue

        emit(f"  [{os.path.basename(src_path)}] 命中缓存 {len(hits)} 条")
        by_term = Counter(term for _, term in hits)
        for term, n in by_term.most_common(8):
            emit(f"      {term}: {n} 条")

        removed_n = cache.remove_many([k for k, _ in hits])
        cache.save(force=True)
        total_removed += removed_n
        emit(f"  ✔ 已删除 {removed_n} 条缓存")

        lines, newline = P.read_file(src_path, config.INPUT_ENCODING)
        _translate_core(src_path, lines, newline, show_header=False)
        files_done += 1

    TS.save_snapshot(current)
    bridge.progress(len(paths), len(paths), "完成")
    return {"files": files_done, "removed": total_removed}


# ================================================================
# 核心 3b：解决术语冲突
#   报告页把「同一原文、两种译文」的冲突列出来，用户挑一个（或自定义）
#   作为最终译文，这里负责写回术语字典、删掉相关缓存并重翻。
# ================================================================
def _rename_conflict_keys(renames):
    """冲突记录文件里的术语原文同步改名（{旧: 新}）。"""
    if not renames:
        return
    data = load_term_conflicts()
    if not data:
        return
    changed = False
    for old, new in renames.items():
        item = data.pop(old, None)
        if not isinstance(item, dict):
            continue
        exist = data.get(new)
        if isinstance(exist, dict):
            for s in item.get("src") or []:
                if s and s not in exist.setdefault("src", []):
                    exist["src"].append(s)
        else:
            data[new] = item
        changed = True
    if changed:
        save_term_conflicts(data)


def apply_term_conflicts(choices, paths=None, src_lang=None, tgt_lang=None,
                         model=None):
    """
    choices: [{"term": 原文, "value": 最终采用的译文,
               "new_term": 可选，修改后的术语原文}, ...]
             只处理 value 非空的项。
    paths:   要重翻的文件（None / 空 → 只写字典不重翻）。

    返回 {"saved": n, "renamed": n, "files": n, "removed": n}
    """
    import term_sync as TS

    mapping = {}
    renames = {}
    for c in (choices or []):
        term = (c.get("term") or "").strip()
        val = c.get("value")
        new_term = (c.get("new_term") or "").strip()
        if not term:
            continue
        if new_term and new_term != term:
            renames[term] = new_term
        if val is not None and str(val).strip():
            mapping[term] = str(val).strip()

    emit("\n" + "=" * 55)
    emit("  解决术语冲突")
    emit("=" * 55)

    if not mapping and not renames:
        emit("  没有选择任何要保留的译文，已取消")
        return {"saved": 0, "renamed": 0, "files": 0, "removed": 0}

    # ★ 修改术语原文：先改名（写回 term_dict.py），值再跟着新原文走
    renamed = 0
    if renames:
        renamed = TS.rename_term_keys(renames)
        if renamed:
            emit(f"  ✔ 术语原文已改名 {renamed} 条")
            for o, nv in list(renames.items())[:8]:
                emit(f"    {o}  →  {nv}")
            if len(renames) > 8:
                emit(f"    … 其余 {len(renames) - 8} 条省略")
            mapping = {renames.get(k, k): v for k, v in mapping.items()}
            _rename_conflict_keys(renames)
        else:
            emit("  ⚠ 术语原文改名没有生效（见日志），译文仍按原原文写入")

    if not mapping:
        try:
            TS.save_snapshot(TS.load_current_terms())
        except Exception:
            pass
        drop_term_conflicts(list(renames.keys()))
        log.info("解决术语冲突：改名 %d 条，无需重翻", renamed)
        return {"saved": 0, "renamed": renamed, "files": 0, "removed": 0}

    for t, v in list(mapping.items())[:10]:
        emit(f"    {t}  →  {v}")
    if len(mapping) > 10:
        emit(f"    … 其余 {len(mapping) - 10} 条省略")

    saved = TS.save_term_values(mapping)
    emit(f"  ✔ 术语字典已更新 {saved} 条")

    try:
        PR.load_terms(force=True)
    except Exception as e:
        log.warning("重新载入术语表失败：%s", e)

    files = removed = 0
    if paths:
        result = retranslate_terms_paths(
            list(paths), src_lang, tgt_lang, model,
            extra_terms=[renames.get(t, t) for t in mapping.keys()])
        files = (result or {}).get("files", 0)
        removed = (result or {}).get("removed", 0)
    else:
        emit("  （未选择文件，只更新术语字典；"
             "选好文件后再点一次即可重翻相关句子）")
        try:
            TS.save_snapshot(TS.load_current_terms())
        except Exception:
            pass

    # 已解决的冲突从记录里移除，避免报告一直报同一个
    n = drop_term_conflicts(list(mapping.keys()) + list(renames.keys()))
    if n:
        emit(f"  ✔ 已清理 {n} 条冲突记录")

    log.info("解决术语冲突：写入 %d 条，改名 %d 条，重翻 %d 个文件，删缓存 %d 条",
             saved, renamed, files, removed)
    return {"saved": saved, "renamed": renamed,
            "files": files, "removed": removed}


def scan_term_conflicts():
    """读取当前落盘的术语冲突，返回 [(原文, 已有译文, 新增译文, 命中句数)]。"""
    data = load_term_conflicts()
    out = []
    for term, item in data.items():
        if not isinstance(item, dict):
            continue
        out.append((
            term,
            item.get("old", "") or "",
            item.get("new", "") or "",
            len(item.get("src") or []),
        ))
    out.sort(key=lambda x: (-x[3], x[0]))
    return out


# ================================================================
# 核心 4：应用前缀字典
# ================================================================
def apply_prefix_dict_paths(paths, entries_map=None):
    """
    不调用模型：用前缀字典重新拼接缓存译文并回写输出文件。
    entries_map: 可选的 {前缀: 译文}，先写入字典再应用。
    """
    import prefix_dict as PFD

    log.info("=" * 50)
    log.info("应用前缀字典  共 %d 个文件", len(paths))

    if entries_map:
        n = PFD.update_many(entries_map)
        PFD.save()
        emit(f"  前缀字典已写入 {n} 条修改")

    PFD.reload_dict()
    s = PFD.stats()
    emit(f"当前字典：共 {s['total']} 条，已翻译 {s['done']} 条，"
         f"待翻译 {s['pending']} 条")

    done = 0
    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        # ★ 菜单 5 现在只选缓存文件（*_cache.json），先换回源文件
        src_path = source_of(path)
        if not os.path.exists(src_path):
            emit(f"  找不到对应的源文件：{src_path}")
            continue

        config.Runtime.set_input(src_path)
        bridge.progress(i - 1, len(paths), os.path.basename(src_path))

        if not os.path.exists(config.Runtime.cache_file):
            emit(f"  缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
            continue

        try:
            lines, newline = P.read_file(src_path, config.INPUT_ENCODING)
        except Exception as e:
            emit(f"  读取失败：{e}")
            continue

        entries, special = P.extract_entries(lines)
        cache = Cache(config.Runtime.cache_file)

        translations = {}
        hit_prefix = miss_prefix = no_prefix = 0

        for _, src in entries:
            prefix, body = PR.split_prefix(src)
            if not prefix:
                no_prefix += 1
                translations[src] = cache.get(src)
                continue

            cached_final = cache.get(src)
            if not cached_final:
                continue

            new_prefix = PFD.apply_prefix(prefix)
            # ★ 缓存里存的是「已经拼过前缀的整行」，而那版前缀未必等于
            #   现在字典里的写法（用户改过前缀译法、或当时用的是术语替换版）。
            #   统一交给 strip_prefix_echo 按「当前前缀 / 原文前缀 / 术语替换版」
            #   逐个比对，并用「原文正文是否自带控制码」做安全兜底，
            #   避免出现 `\tg[新]\tg[旧]正文` 这种新旧并存。
            src_body = (src[len(prefix):]
                        if src.startswith(prefix) else src)
            body_final = PFD.strip_prefix_echo(cached_final, prefix, src_body)
            new_final = new_prefix + body_final
            if new_final != cached_final:
                translations[src] = new_final
                hit_prefix += 1
            else:
                translations[src] = cached_final
                miss_prefix += 1

        replaced = P.write_output(
            lines, entries, translations,
            config.Runtime.output_file, newline, config.OUTPUT_ENCODING,
        )
        emit(f"  [{os.path.basename(src_path)}] 替换 {replaced}/{len(entries)} 条"
             f"  前缀生效 {hit_prefix}  未译 {miss_prefix}  无前缀 {no_prefix}")
        done += 1

    bridge.progress(len(paths), len(paths), "完成")
    log.info("应用前缀字典完成：%d 个文件", done)
    return {"files": done}


# ================================================================
# 核心 4b：前缀字典「应用术语」
#   · 让前缀去匹配术语字典，命中则替换
#   · 当前只替换 \tg[...] 里的内容（角色名），控制码参数一律不动
# ================================================================
def scan_prefix_terms():
    """预演「应用术语」，返回 (changes, stats)，不写盘。"""
    import prefix_dict as PFD
    PFD.reload_dict()
    return PFD.scan_terms_for_tg()


def apply_prefix_terms_paths(paths=None):
    """
    把术语表套用到前缀字典（仅 \tg[...] 内容）并落盘；
    给了 paths 就顺带把前缀重新拼回译文文件。

    返回 {"changed": 命中条数, "files": 应用到的文件数, "samples": [...]}
    """
    import prefix_dict as PFD

    PFD.reload_dict()
    changes, stats = PFD.apply_terms_for_tg()

    emit("\n" + "=" * 55)
    emit("  前缀字典 · 应用术语（只替换 \\tg[...] 里的内容）")
    emit("=" * 55)
    emit(f"  字典共 {stats['total']} 条，命中术语 {stats['changed']} 条，"
         f"未命中 {stats['untouched']} 条")

    samples = []
    for c in changes[:10]:
        pairs = "、".join(f"{s}→{d}" for s, d in c["terms"][:3])
        emit(f"    {c['src']}  →  {c['new']}   （{pairs}）")
        samples.append({"src": c["src"], "new": c["new"],
                        "terms": c["terms"]})
    if len(changes) > 10:
        emit(f"    … 其余 {len(changes) - 10} 条省略")

    if not changes:
        emit("  没有前缀命中术语，无需改动")
        return {"changed": 0, "files": 0, "samples": []}

    files = 0
    if paths:
        r = apply_prefix_dict_paths(paths)
        files = (r or {}).get("files", 0)
    else:
        emit("  （未选择文件，只更新前缀字典；"
             "选好文件后再点一次即可写回译文）")

    log.info("前缀字典应用术语：命中 %d 条，应用文件 %d 个",
             len(changes), files)
    return {"changed": len(changes), "files": files, "samples": samples}


# ================================================================
# 核心 5：中文润色重翻
# ================================================================
# ================================================================
# 中文润色：断点续翻进度 + 润色报告
#   · 进度：<输入名>_polish_cache.json（与缓存同目录）
#     {"version":1,"round":N,"updated_at":"...",
#      "done":{原文: {"out": 润色后译文, "at": 时间}}, "stats":{...}}
#     以「原文」为身份、以「缓存里的值 == 上次润色结果」为完成判据：
#     用户中途改过译文 / 重翻过，那条会自动重新参与润色。
#   · 报告：<输出名>_polished.txt（与输出文件同目录），逐条列出改动。
# ================================================================
POLISH_STATE_SUFFIX = "_polish_cache.json"
POLISH_STATE_VERSION = 1


def _polish_state_path():
    """润色进度文件路径：与缓存同源，<输入名>_polish_cache.json"""
    cache = getattr(config.Runtime, "cache_file", "") or ""
    if cache:
        stem = os.path.splitext(os.path.basename(cache))[0]
        if stem.endswith("_cache"):
            stem = stem[:-len("_cache")]
        return os.path.join(os.path.dirname(cache) or ".",
                            f"{stem}{POLISH_STATE_SUFFIX}")
    d = os.path.dirname(config.Runtime.output_file) or "."
    return os.path.join(d, f"polish{POLISH_STATE_SUFFIX}")


def _load_polish_state(path):
    """读润色进度；不存在 / 损坏都当作「没有进度」，不影响正常润色。"""
    empty = {"version": POLISH_STATE_VERSION, "round": 0,
             "done": {}, "stats": {}}
    if not path or not os.path.exists(path):
        return empty
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("进度文件内容不是对象")
        data.setdefault("done", {})
        data.setdefault("round", 0)
        data.setdefault("stats", {})
        return data
    except Exception as e:
        log.warning("润色进度加载失败（当无进度处理）：%s", e)
        return empty


def _save_polish_state(path, state):
    """落盘润色进度（原子写，Windows 上的临时文件占用与缓存同样处理）。"""
    state["version"] = POLISH_STATE_VERSION
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        atomic_replace(tmp, path)
    except Exception as e:
        log.warning("润色进度保存失败（不影响本次润色）：%s", e)


def _polish_log_path():
    """润色报告路径：与输出文件同目录，名为 <输出名>_polished.txt"""
    out = config.Runtime.output_file
    d = os.path.dirname(out) or "."
    base = os.path.splitext(os.path.basename(out))[0]
    return os.path.join(d, f"{base}_polished.txt")


def _write_polish_report(path, records, stats, state_path, status="完成"):
    """
    records: [{"kind": "改动"/"未变"/"跳过", "src": 原文,
               "old": 润色前, "new": 润色后}, ...]
    写完后返回报告路径。
    """
    report_path = _polish_log_path()
    groups = {"改动": [], "未变": [], "跳过": []}
    for r in records:
        groups.setdefault(r.get("kind", "改动"), []).append(r)

    head = [
        "# 中文润色报告",
        f"# 状态：{status}",
        f"# 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"# 输入文件：{path}",
        f"# 译文缓存：{config.Runtime.cache_file}",
        f"# 输出文件：{config.Runtime.output_file}",
        f"# 进度文件：{state_path}",
        "#",
        f"# 本轮：改动 {stats.get('changed', 0)} 条，"
        f"未变 {stats.get('kept', 0)} 条，"
        f"跳过（已完成）{stats.get('skipped', 0)} 条；"
        f"累计已完成 {stats.get('done_total', 0)} 条"
        f"（第 {stats.get('round', 1)} 轮）",
        "=" * 70,
        "",
    ]

    body = []
    for kind in ("改动", "未变", "跳过"):
        items = groups.get(kind) or []
        if not items:
            continue
        body.append(f"## {kind}　{len(items)} 条")
        body.append("-" * 70)
        for i, r in enumerate(items, 1):
            body.append(f"[{i}]")
            body.append(f"  原文：{r.get('src', '')}")
            if kind == "改动":
                body.append(f"  润色前：{r.get('old', '')}")
            if kind == "改动":
                body.append(f"  润色后：{r.get('new', '')}")
            body.append("")
        body.append("")

    try:
        with open(report_path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(head + body))
    except Exception as e:
        log.warning("写润色报告失败：%s", e)
        return None
    return report_path


def _flush_polish_report(path, records, state_path, round_no,
                         changed=0, kept=0, skipped=0, done_total=None,
                         status="完成"):
    """收尾：刷新进度文件与统计，再写润色明细报告，返回报告路径。"""
    state = _load_polish_state(state_path)
    if done_total is None:
        done_total = len(state.get("done") or {})
    state["round"] = round_no
    state["input"] = path
    state["stats"] = {"round": round_no, "changed": changed, "kept": kept,
                      "skipped": skipped, "done_total": done_total,
                      "todo": changed + kept + skipped}
    _save_polish_state(state_path, state)
    return _write_polish_report(path, records, state["stats"], state_path,
                                status=status)


def _polish_core(path, lines=None, newline=None, show_header=True,
                 reset=False, state_path=None):
    """
    对单个文件：把缓存里的中文译文再润色一遍，覆盖回缓存并重写输出文件。

    reset=True 会清空本文件的润色进度（重新润色全部）。
    """
    out_path = config.Runtime.output_file
    cache_path = config.Runtime.cache_file

    if show_header:
        emit(f"\n{'=' * 55}")
        emit(f"  中文润色：{path}")
        emit(f"  输出：{out_path}")
        emit(f"{'=' * 55}")

    if lines is None:
        lines, newline = P.read_file(path, config.INPUT_ENCODING)
    newline = newline or "\n"

    entries, _ = P.extract_entries(lines)
    cache = Cache(cache_path)

    # ---------- 断点续翻进度 ----------
    state_path = state_path or _polish_state_path()
    state = _load_polish_state(state_path)
    round_no = int(state.get("round") or 0) + (0 if reset else 1)
    done_map = {} if reset else (state.get("done") or {})
    if reset:
        state["done"] = {}

    records = []          # 润色报告明细：每条一个 dict
    min_len = getattr(config, "POLISH_MIN_LEN", 4)
    seen, todo = set(), []
    for _, txt in entries:
        if txt in seen:
            continue
        seen.add(txt)
        val = cache.get(txt)
        if not val or val == txt:
            continue                       # 没翻译过 / 纯控制符原样缓存
        if len(val.strip()) < min_len or PR.is_pure_control(val):
            continue
        # ★ 断点续翻：缓存里的值仍是上次润色的结果 → 这条已完成，跳过
        if done_map.get(txt, {}).get("out") == val:
            records.append({"kind": "跳过", "src": txt, "old": val,
                            "new": val})
            continue
        todo.append(txt)

    skipped = sum(1 for r in records if r["kind"] == "跳过")
    emit(f"[润色] 缓存 {len(cache)} 条  待润色 {len(todo)} 条"
         f"  跳过已完成 {skipped} 条")
    if not todo:
        emit("没有需要润色的译文"
             + (f"（已全部润色过，进度文件 {state_path}）" if skipped else
                "（先运行一次翻译）"))
        _flush_polish_report(path, records, state_path, round_no,
                             skipped=skipped)
        return {"changed": 0, "kept": 0, "todo": 0, "skipped": skipped}

    client = OllamaClient()
    batch_size = getattr(config, "POLISH_BATCH_SIZE", 8) or 8
    changed = 0
    kept = 0
    total = len(todo)
    done = 0
    t0 = time.time()

    def _mark_unchanged(t):
        """润色没拿到有效结果 → 保留原译文，并记进报告。"""
        nonlocal kept
        kept += 1
        old = cache.get(t)
        records.append({"kind": "未变", "src": t, "old": old, "new": old})

    for bi, batch_texts in enumerate(_make_batches(todo, batch_size,
                                                   getattr(config,
                                                           "MAX_BATCH_CHARS",
                                                           1400)), 1):
        if bridge.cancelled():
            emit("\n[中断] 用户取消")
            break

        items, maps_dict, src_safe_dict = [], {}, {}
        for k, txt in enumerate(batch_texts):
            safe, maps = PR.protect(cache.get(txt), drop_newline=False)
            # ★ 原文一并保护后作为末尾参考提示词，供模型比对、避免润色跑偏
            src_safe, _ = PR.protect(txt, drop_newline=False)
            items.append((k, safe, src_safe))
            maps_dict[k] = maps
            src_safe_dict[k] = src_safe

        result = polish_with_retry(client, items)

        # 单条补全
        for k, safe, _src in items:
            if result.get(k, "").strip():
                continue
            for attempt in range(getattr(config, "SINGLE_RETRIES", 3)):
                try:
                    r = polish_with_retry(client, [(k, safe, src_safe_dict[k])])
                    if r.get(k, "").strip():
                        result[k] = r[k]
                        break
                except Exception:
                    time.sleep(1.0)

        for k, txt in enumerate(batch_texts):
            raw = result.get(k)
            if not raw or not raw.strip():
                _mark_unchanged(txt)
                continue

            maps = maps_dict[k]
            ok_ph, _ = PR.verify(raw, maps)
            if not ok_ph:
                # 润色绝不冒险：占位符不全就保留原译文
                log.warning("[润色 %d][%d] 占位符不全，保留原译文", bi, k)
                _mark_unchanged(txt)
                continue

            new_text = PR.restore(raw, maps).strip()
            if not new_text:
                _mark_unchanged(txt)
                continue
            if new_text == cache.get(txt):
                _mark_unchanged(txt)
                continue

            cache.put(txt, new_text)
            changed += 1
            state["done"][txt] = {"out": new_text,
                                  "at": time.strftime("%H:%M:%S")}
            records.append({"kind": "改动", "src": txt,
                            "old": cache.get(txt, ""), "new": new_text})

        cache.tick()
        ok = sum(1 for k in range(len(batch_texts))
                 if (result.get(k) or "").strip())
        done += len(batch_texts)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate / 60 if rate > 0 else 0
        log.info("[批 %d] 成功 %d/%d  累计 %d/%d  %.2f条/秒  ETA %.1f分",
                 bi, ok, len(batch_texts), done, total, rate, eta)
        state["stats"] = {"round": round_no, "changed": changed,
                          "kept": kept, "skipped": skipped,
                          "done_total": len(state["done"])}
        _save_polish_state(state_path, state)
        bridge.progress(min(bi * batch_size, total), total,
                        f"润色 {min(bi * batch_size, total)}/{total}")

    cache.save(force=True)

    translations = {txt: cache.get(txt) for _, txt in entries if cache.get(txt)}
    replaced = P.write_output(
        lines, entries, translations,
        out_path, newline, config.OUTPUT_ENCODING,
    )
    emit(f"\n✔ 润色完成：改动 {changed} 条，保持不变 {kept} 条")
    emit(f"  回写 {replaced}/{len(entries)} 条 → {out_path}")

    report_path = _flush_polish_report(
        path, records, state_path, round_no,
        changed=changed, kept=kept, skipped=skipped,
        status="已中断" if bridge.cancelled() else "完成",
    )
    if report_path:
        emit(f"  润色明细：{report_path}")

    return {"changed": changed, "kept": kept, "todo": total,
            "skipped": skipped, "report": report_path}


def polish_paths(paths, model=None, reset=False):
    """中文润色重翻（无交互核心）。

    reset=True → 清空各文件的润色进度，重新润色全部（不续翻）。
    """
    _apply_lang_model(None, None, model)

    log.info("=" * 50)
    log.info("中文润色重翻  共 %d 个文件", len(paths))

    if not getattr(config, "POLISH_ENABLE", True):
        emit("中文润色功能已关闭（POLISH_ENABLE=False）")
        return {"files": 0, "changed": 0}

    total_changed = 0
    total_skipped = 0
    files_done = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        # ★ 本菜单只允许选缓存文件（*_cache.json），先换回源文件
        src_path = source_of(path)
        if not os.path.exists(src_path):
            emit(f"  找不到对应的源文件：{src_path}")
            continue

        config.Runtime.set_input(src_path)
        bridge.progress(i - 1, len(paths), os.path.basename(src_path))

        if not os.path.exists(config.Runtime.cache_file):
            emit(f"  缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
            continue

        try:
            lines, newline = P.read_file(src_path, config.INPUT_ENCODING)
        except Exception as e:
            emit(f"  读取失败：{e}")
            continue

        if len(paths) > 1:
            emit(f"\n[{i}/{len(paths)}] {os.path.basename(src_path)}")

        try:
            r = _polish_core(src_path, lines, newline,
                             show_header=(len(paths) == 1), reset=reset)
            total_changed += r.get("changed", 0)
            total_skipped += r.get("skipped", 0)
            files_done += 1
        except bridge.CancelRequested:
            emit("\n[中断] 用户取消")
            break

    bridge.progress(len(paths), len(paths), "完成")
    return {"files": files_done, "changed": total_changed,
            "skipped": total_skipped}


# ================================================================
# 核心 6：换行重排（纯本地，不调用模型）
# ================================================================
def _reflow_cfg(mode, cfg=None):
    """取某模式的重排参数 (min_chars, max_chars, min_gap)。"""
    if isinstance(cfg, dict):
        return (cfg.get("min"), cfg.get("max"), cfg.get("gap"))
    if mode == "space":
        return (getattr(config, "WRAP_SPACE_MIN", 8),
                getattr(config, "WRAP_SPACE_MAX", 10),
                getattr(config, "WRAP_SPACE_MIN_GAP", 5))
    return (config.WRAP_CHARS_MIN, config.WRAP_CHARS_MAX,
            getattr(config, "WRAP_MIN_GAP", 10))


def _output_lines_of(path, lines, cache):
    """
    返回与原文等长、已填入译文的输出行。
    优先读已有译文文件（保留人工/术语修改），缺失时用缓存重建。
    """
    out_path = config.Runtime.output_file
    if os.path.exists(out_path):
        try:
            out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
            if len(out_lines) == len(lines):
                return out_lines
        except Exception:
            pass

    out_lines = list(lines)
    entries, _ = P.extract_entries(lines)
    for idx, src in entries:
        dst = cache.get(src)
        if not dst:
            continue
        m = re.match(r'^([ \t]*)', lines[idx])
        out_lines[idx] = (m.group(1) if m else "") + dst
    return out_lines


def reflow_block_id(path, block, line=None):
    """
    区块的唯一标识（绝对路径 + 区块名 + 起始行）。

    ★ 换行重排页支持「只重排选中的区块」，扫描（scan_reflow_blocks）
      与执行（reflow_paths）两边都用这个 id 对齐。
    """
    return "{0}\x00{1}\x00{2}".format(os.path.abspath(path), block, line)


def _line_block_ids(lines, path):
    """每行所属区块的 id（规则与 scan_reflow_blocks 完全一致）。"""
    out = []
    cur_name, cur_line = "（文件开头）", 0
    for idx, raw in enumerate(lines):
        s = raw.strip()
        if P.is_block(s):
            cur_name, cur_line = s, idx
        out.append(reflow_block_id(path, cur_name, cur_line))
    return out


def scan_reflow_blocks(paths, preview=8):
    """
    扫描待重排文件，按「区块」归类，供换行重排页展示。

    返回 {"newline": [block, ...], "space": [block, ...]}
    block = {"file", "path", "block", "mode", "line", "id", "total",
             "pairs":[(原文,译文),...]}
    """
    result = {"newline": [], "space": []}

    for path in paths:
        if not os.path.exists(path):
            continue
        # ★ 菜单 7 只列译文文件，先换回源文件再读（译文与源文件行数一致，
        #   但缓存 / 块名都挂在源文件上）
        src_path = source_of(path)
        if not os.path.exists(src_path):
            log.warning("重排扫描：找不到对应的源文件 %s", src_path)
            continue
        try:
            lines, _nl = P.read_file(src_path, config.INPUT_ENCODING)
        except Exception as e:
            log.warning("重排扫描读取失败：%s（%s）", src_path, e)
            continue

        config.Runtime.set_input(src_path)
        cache = Cache(config.Runtime.cache_file)
        out_lines = _output_lines_of(src_path, lines, cache)

        modes = P.get_block_modes(lines)
        entries, _ = P.extract_entries(lines)
        trans_idx = {idx for idx, _ in entries}

        blocks = []
        cur_name, cur_mode, cur_pairs, cur_line = "（文件开头）", "newline", [], 0

        def _flush():
            if cur_pairs:
                blocks.append({
                    # ★ 用源文件：区块 id 在扫描与执行两边必须一致，
                    #   否则「只重排选中的区块」会一个都命中不了
                    "file":  os.path.basename(src_path),
                    "path":  src_path,
                    "block": cur_name,
                    "mode":  cur_mode,
                    "line":  cur_line,
                    "id":    reflow_block_id(src_path, cur_name, cur_line),
                    "total": len(cur_pairs),
                    "pairs": cur_pairs[:preview],
                })

        for idx, raw in enumerate(lines):
            s = raw.strip()
            if P.is_block(s):
                _flush()
                cur_name, cur_mode, cur_pairs, cur_line = s, modes[idx], [], idx
                continue
            if idx in trans_idx:
                src = lines[idx].strip()
                dst = out_lines[idx].strip() if idx < len(out_lines) else ""
                if dst and dst != src:
                    cur_pairs.append((src, dst))
        _flush()

        for b in blocks:
            result.setdefault(b["mode"], []).append(b)

    return result


def reflow_paths(paths, newline_cfg=None, space_cfg=None, blocks=None):
    """
    按区块类型重排译文里的换行 / 空格（纯本地操作，不调用模型）。

    newline_cfg / space_cfg: {"min","max","gap"} 或 None（用当前配置）
    blocks : 只重排这些区块（reflow_block_id 组成的列表 / 集合）；
             None 或空 = 文件里所有区块都重排。
    """
    log.info("=" * 50)
    log.info("换行重排  共 %d 个文件", len(paths))

    nl = _reflow_cfg("newline", newline_cfg)
    sp = _reflow_cfg("space", space_cfg)
    sel_ids = set(blocks) if blocks else None
    emit("\n" + "=" * 55)
    emit("  换行重排（仅重排列，不改动译文文字）")
    emit("=" * 55)
    emit(f"  [map*] 换行  ：{nl[0]}~{nl[1]} 字，最小间隔 {nl[2]} 字")
    emit(f"  其它区块空格：{sp[0]}~{sp[1]} 字，最小间隔 {sp[2]} 字")
    if sel_ids is not None:
        emit(f"  只重排选中的 {len(sel_ids)} 个区块（其余区块原样保留）")
    else:
        emit("  重排范围：文件里的所有区块")

    if not getattr(config, "REWRAP_ENABLE", True):
        emit("\n⚠ 换行重排已关闭（REWRAP_ENABLE=False），请先到「设置」里打开")
        return {"files": 0, "changed": 0}

    files_done = changed = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            emit("\n[中断] 用户取消")
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        # ★ 本菜单只允许选译文文件（*_translated.txt），先换回源文件
        src_path = source_of(path)
        if not os.path.exists(src_path):
            emit(f"  找不到对应的源文件：{src_path}")
            continue

        config.Runtime.set_input(src_path)
        out_path = config.Runtime.output_file
        bridge.progress(i - 1, len(paths), os.path.basename(src_path))

        try:
            lines, _ = P.read_file(src_path, config.INPUT_ENCODING)
        except Exception as e:
            emit(f"  读取失败：{e}")
            continue

        if not os.path.exists(out_path):
            emit(f"  缺少译文：{out_path}（先跑一次翻译）")
            continue

        try:
            out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
        except Exception as e:
            emit(f"  译文读取失败：{e}")
            continue
        # ★ 行尾按译文文件的原始字节定（文本模式读会把 CRLF 归一成 LF）
        out_nl = P.detect_newline(out_path, default=os.linesep)

        if len(out_lines) != len(lines):
            emit(f"  行数不一致（原文 {len(lines)} / 译文 {len(out_lines)}），跳过")
            continue

        modes = P.get_block_modes(lines)
        entries, _ = P.extract_entries(lines)
        # ★ 每个条目属于哪个区块（用于「只重排选中区块」）
        block_of = _line_block_ids(lines, src_path) if sel_ids is not None else None
        sel_hit = 0                       # 本文件里命中「选中区块」的条目数

        n_changed = 0
        for idx, src_text in entries:
            if block_of is not None:
                bid = block_of[idx] if idx < len(block_of) else None
                if bid not in sel_ids:
                    continue
                sel_hit += 1
            dst = out_lines[idx]
            m = re.match(r'^([ \t]*)', dst)
            indent = m.group(1) if m else ""
            body = dst.strip()
            if not body or body == src_text.strip():
                continue

            mode = modes[idx] if idx < len(modes) else "newline"
            mn, mx, gap = (sp if mode == "space" else nl)
            new_body = PR.reflow(src_text.strip(), body, mode=mode,
                                 min_chars=mn, max_chars=mx, min_gap=gap)
            if not new_body or new_body == body:
                continue
            out_lines[idx] = indent + new_body
            n_changed += 1

        name = os.path.basename(path)
        if not n_changed:
            extra = ("（本文件没有选中区块，已跳过）"
                     if block_of is not None and not sel_hit else "")
            emit(f"[{i}/{len(paths)}] {name}：已符合当前配置，无需改动{extra}")
            files_done += 1
            continue

        try:
            # ★ newline=""：原样写回，别让 Windows 文本模式把 \n 变成 \r\n
            #   —— 否则「只重排选中区块」时未选中的行也会跟着变行尾。
            tmp = out_path + ".tmp"
            with open(tmp, "w", encoding=config.OUTPUT_ENCODING,
                      newline="") as f:
                f.write(out_nl.join(out_lines))
            atomic_replace(tmp, out_path)
        except Exception as e:
            emit(f"  写入失败：{e}")
            continue

        emit(f"[{i}/{len(paths)}] {name}：重排 {n_changed} 条 → {out_path}")
        changed += n_changed
        files_done += 1

    bridge.progress(len(paths), len(paths), "完成")
    emit(f"\n✔ 换行重排完成：{files_done} 个文件，改动 {changed} 条")
    log.info("换行重排完成：%d 个文件，改动 %d 条", files_done, changed)
    return {"files": files_done, "changed": changed}


# ================================================================
# 核心 1：文本提取与编译（菜单 1）
#   纯本地：读游戏编译好的文本表 / 写回语言 .dat / 编译插件。
# ================================================================
def intl_extract_paths(game_dirs, out_path=None):
    """
    提取文本：读游戏 Data 下的原文表（messages.dat / english.dat），
    按分段拆成多个 txt（每个分段一个文件）—— 等同于在游戏 debug 菜单里点
    「Extract Text」。返回 [{"game":…, "out":…, "sections":…, …}]。
    """
    import intl_text as IT
    out = []
    for gd in game_dirs or []:
        if bridge.cancelled():
            break
        emit("\n" + "=" * 55)
        emit(f"  提取文本：{gd}")
        emit("=" * 55)
        try:
            rep = IT.extract_text(gd, out_path=out_path, emit=emit)
            out.append({"game": gd, **rep})
        except Exception as e:
            log.error("提取文本失败：%s\n%s", e, traceback.format_exc())
            emit(f"  ✘ 提取失败：{e}")
            out.append({"game": gd, "ok": False, "error": str(e)})
    return out


def intl_compile_paths(game_dir, sources, out_path=None, apply_language=True):
    """
    编译文本：把 intl 格式的文本（单个文件、多个文件、或整个文件夹里的
    全部 .txt）编译成游戏语言文件 —— 等同于在游戏 debug 菜单里点
    「Compile Text」。返回报告 dict。

    out_path 留空时按游戏版本自动定：
      旧版 → Settings::LANGUAGES 里那条（一般是 Data/Chinese.dat）
      新版 → Data/messages_<语言>_core.dat 与 …_game.dat
    apply_language：编译完顺手把这条语言写进 Settings::LANGUAGES
                    （复制第一条语言、把 English 改成 Chinese），省得自己改脚本。
    """
    import intl_text as IT
    emit("\n" + "=" * 55)
    emit(f"  编译文本：{game_dir}")
    emit("=" * 55)
    try:
        rep = IT.compile_text(game_dir, sources, out_path=out_path,
                              emit=emit)
    except Exception as e:
        log.error("编译文本失败：%s\n%s", e, traceback.format_exc())
        emit(f"  ✘ 编译失败：{e}")
        return {"ok": False, "error": str(e)}
    if apply_language:
        try:
            rep["language"] = intl_apply_language(game_dir, emit=emit)
        except Exception as e:
            log.error("写入语言表失败：%s\n%s", e, traceback.format_exc())
            emit(f"  ⚠ 语言表没写成：{e}")
    return rep


def intl_apply_language(game_dir, display="简体中文", fragment=None, emit=None):
    """
    编译完文本后调用：把这条语言写进游戏 Settings 的 LANGUAGES ——
    复制第一条语言条目、把 `English` 改成 `Chinese`（被注释的先取消注释）。
    不翻译注释、也不添加注释。返回 GS.apply_languages_entry 的结果。
    """
    import game_scripts as GS
    return GS.apply_languages_entry(game_dir, display=display,
                                    fragment=fragment, emit=emit)


def plugin_inject_paths(game_dirs, font_file=None):
    """
    加载中文文本处理插件：复制进 <游戏>/Plugins/、写字体名，并把**全部**
    插件（含游戏原有的）编译进 Data/PluginScripts.rxdata。
    ★ 纯文件写入，不调用模型、不联网。
    """
    import plugin_tools as PT
    out = []
    for gd in game_dirs or []:
        if bridge.cancelled():
            break
        emit("\n" + "=" * 55)
        emit(f"  加载中文文本处理插件：{gd}")
        emit("=" * 55)
        try:
            rep = PT.install_plugin(gd, font_file=font_file, emit=emit)
            out.append({"game": gd, **rep})
        except Exception as e:
            log.error("插件植入失败：%s\n%s", e, traceback.format_exc())
            emit(f"  ✘ 失败：{e}")
            out.append({"game": gd, "ok": False, "error": str(e)})
    return out


def plugin_restore_paths(game_dirs):
    """
    还原「加载中文文本处理插件」：删掉 Plugins/ 下本工具植入的那个目录，
    以及当初复制进游戏 Fonts 的那份字体（游戏自带字体不动）。
    """
    import plugin_tools as PT
    out = []
    for gd in game_dirs or []:
        emit("\n" + "=" * 55)
        emit(f"  还原插件植入：{gd}")
        emit("=" * 55)
        try:
            out.append({**PT.restore_plugin(gd, emit=emit), "game": gd})
        except Exception as e:
            log.error("插件还原失败：%s\n%s", e, traceback.format_exc())
            emit(f"  ✘ 失败：{e}")
            out.append({"game": gd, "ok": False, "removed": []})
    return out


def cmd_intl():
    """菜单 1：文本提取与编译"""
    import filepicker
    import game_scripts as GS
    import intl_text as IT

    emit("\n[文本提取与编译]")
    emit("  适用于 Pokémon Essentials（mkxp / RMXP）游戏：")
    emit("  ① 提取文本 —— 同游戏 debug 的 Extract Text；")
    emit("  ② 编译文本 —— 同游戏 debug 的 Compile Text；")
    emit("  ③ 加载中文文本处理插件（并编译进 PluginScripts.rxdata）。")

    folder = filepicker.pick_dir(
        initial_dir=config.Runtime.last_dir or config.BASE_DIR,
        title="选择游戏根目录（里面有 Game.exe 和 Data）")
    if not folder:
        emit("已取消")
        return
    ok, why = GS.check_game_root(folder)
    if not ok:
        emit(f"✘ {why}：{folder}")
        return
    config.Runtime.set_dir(folder)

    raw = input("\n1=提取 / 2=编译 / 3=加载插件 / 4=还原插件 [1]: ").strip()
    if raw == "2":
        src = input("要编译的文本（文件或文件夹）[默认用刚提取的 Text_ 文件夹]: ").strip()
        intl_compile_paths(folder, src or IT.extract_target(folder))
        return
    if raw == "3":
        plugin_inject_paths([folder])
        return
    if raw == "4":
        plugin_restore_paths([folder])
        return
    intl_extract_paths([folder])


# ================================================================
# 核心 7：Excel 转术语表
# ================================================================
def build_terms_from_excel(excel_path, sheets=None, source_lang="英文",
                           target_lang="简体中文", out_path=None,
                           mode="append"):
    """
    Excel → term_dict.py（无交互）。返回结果 dict。

    mode="append"（默认）已有术语字典时把新术语接在末尾、保留原有译法；
    mode="overwrite" 整份重写。
    """
    import importlib
    import build_terms as BT

    out_path = out_path or config.TERM_FILE
    log.info("Excel 转术语表：%s  %s → %s（%s）",
             excel_path, source_lang, target_lang, mode)

    result = BT.build_terms(excel_path, out_path, source_lang, target_lang,
                            sheets=sheets, dedup=True, verbose=False,
                            mode=mode)

    for e in result.get("errors", []):
        emit(f"  [err] {e}")

    if result.get("ok"):
        if result.get("mode") == "append" and result.get("existing"):
            emit(f"原有 {result['existing']} 条 → 追加 {result['added']} 条、"
                 f"跳过已存在 {result['skipped_existing']} 条")
            cf = result.get("conflicts") or []
            if cf:
                emit(f"⚠ {len(cf)} 条术语的新旧译法不一致，"
                     f"已保留字典里的原译法（不改已有内容）：")
                for src, old, new in cf[:8]:
                    emit(f"    {src}：保留「{old}」，Excel 里是「{new}」")
                if len(cf) > 8:
                    emit(f"    …另有 {len(cf) - 8} 条，详见日志")
        elif result.get("mode") == "append":
            emit(f"没有可追加的旧字典，新建 {result['total']} 条")
        emit(f"✔ 合计 {result['total']} 条 → {result['out_path']}")
        try:
            import processor
            importlib.reload(processor)
            processor.load_terms()
            emit("术语表已重新加载")
        except Exception as e:
            log.warning("重载术语表失败：%s", e)
        _update_snapshot()

    return result


# ================================================================
# 命令行外壳
# ================================================================
def cmd_translate():
    """菜单 2：翻译"""
    if not _ask_languages():
        return
    paths = _select_scope_interactive("选择要翻译的文件")
    if not paths:
        return
    translate_paths(paths)


def cmd_retranslate_report():
    """菜单 3：重翻检查报告"""
    if not _ask_languages():
        return
    paths = _select_scope_interactive("选择要重翻的文件")
    if not paths:
        return
    retranslate_report_paths(paths)


def cmd_retranslate_terms():
    """菜单 4：术语更新后重翻"""
    if not _ask_languages():
        return
    paths = _select_scope_interactive("选择要重翻的文件")
    if not paths:
        return
    retranslate_terms_paths(paths)


def cmd_review_prefix_dict():
    """菜单 5：前缀字典（查看 / 编辑）"""
    import prefix_dict as PFD

    PFD.reload_dict()
    s = PFD.stats()

    emit("\n[前缀字典]")
    emit("-" * 55)
    emit(f"文件：{PFD.DICT_FILE}")
    emit(f"统计：共 {s['total']} 条，已翻译 {s['done']} 条，"
         f"待翻译 {s['pending']} 条")

    pending = PFD.list_pending()
    if not pending:
        emit("\n✔ 没有待翻译的前缀")
    else:
        emit("\n待翻译前缀（前 30 条）：")
        for i, (k, _) in enumerate(pending[:30], 1):
            emit(f"  {i:>3}. {k}")
        if len(pending) > 30:
            emit(f"  … 其余 {len(pending) - 30} 条")
        emit(f"\n请编辑：{PFD.DICT_FILE}")
        if input("\n是否现在打开文件？(y/N): ").strip().lower() == "y":
            _open_path(PFD.DICT_FILE)

    paths = _select_scope_interactive("选择要应用前缀字典的文件")
    if not paths:
        return
    apply_prefix_dict_paths(paths)


def cmd_polish():
    """菜单 6：中文润色重翻"""
    paths = _select_scope_interactive("选择要润色的文件")
    if not paths:
        return
    # 默认断点续翻（跳过上次已润色过的）；选 y 才清空进度整份重润
    reset = False
    try:
        reset = input("是否清空润色进度、重新润色全部？(y/N): ").strip().lower() == "y"
    except EOFError:
        reset = False
    polish_paths(paths, reset=reset)


def _ask_reflow_params():
    """交互式修改两套重排参数：写回设置并热更新（回车跳过）。"""
    fields = [
        ("WRAP_CHARS_MIN",     "换行下限(字)"),
        ("WRAP_CHARS_MAX",     "换行上限(字)"),
        ("WRAP_MIN_GAP",       "换行最小间隔(字)"),
        ("WRAP_SPACE_MIN",     "空格下限(字)"),
        ("WRAP_SPACE_MAX",     "空格上限(字)"),
        ("WRAP_SPACE_MIN_GAP", "空格最小间隔(字)"),
    ]
    for key, name in fields:
        cur = getattr(config, key, "")
        raw = input(f"  {name}（当前 {cur}，回车跳过）：").strip()
        if not raw:
            continue
        ok, msg, _ = settings.set_value(key, raw)
        emit(f"    {'✔' if ok else '✘'} {name} → {msg}")


def cmd_reflow():
    """菜单 7：换行重排"""
    emit("\n[换行重排] 当前配置")
    emit("-" * 55)
    emit(f"  [map*] 换行  ：{config.WRAP_CHARS_MIN}~{config.WRAP_CHARS_MAX} 字，"
         f"最小间隔 {getattr(config, 'WRAP_MIN_GAP', 10)} 字")
    emit(f"  其它区块空格：{getattr(config, 'WRAP_SPACE_MIN', 8)}"
         f"~{getattr(config, 'WRAP_SPACE_MAX', 10)} 字，"
         f"最小间隔 {getattr(config, 'WRAP_SPACE_MIN_GAP', 5)} 字")
    emit("  （两种重排各用一套参数，也可在「设置」里修改）")

    if input("\n是否修改本次参数？(y/N): ").strip().lower() == "y":
        _ask_reflow_params()

    paths = _select_scope_interactive("选择要重排的文件")
    if not paths:
        return
    reflow_paths(paths)


def cmd_build_terms():
    """菜单 8：术语字典 —— Excel 转术语表（右侧卡片可切到字典列表）"""
    import filepicker
    import build_terms as BT

    emit("\n[术语表] 从 Excel 提取")

    excel_path = config.EXCEL_FILE
    if os.path.exists(excel_path):
        emit(f"默认 Excel：{excel_path}")
        if input("是否另选？(y/N): ").strip().lower() == "y":
            picked = filepicker.pick_excel_file(
                initial_dir=os.path.dirname(excel_path))
            if picked:
                excel_path = picked
    else:
        picked = filepicker.pick_excel_file(initial_dir=config.BASE_DIR)
        if not picked:
            emit("已取消")
            return
        excel_path = picked

    if not os.path.exists(excel_path):
        emit(f"文件不存在：{excel_path}")
        return

    try:
        sheets = BT.list_sheets(excel_path)
    except Exception as e:
        emit(f"打开 Excel 失败：{e}")
        return

    emit(f"\n共 {len(sheets)} 个工作表：")
    for i, (name, r, c) in enumerate(sheets, 1):
        emit(f"  {i:>2}. {name}   ({r} 行 × {c} 列)")

    src = _choose_language("请选择【源语言列】：", config.EXCEL_SOURCE_LANG)
    if not src:
        emit("已取消")
        return
    tgt = _choose_language("请选择【目标语言列】：",
                           config.EXCEL_TARGET_LANG, exclude=src)
    if not tgt:
        emit("已取消")
        return

    raw = input("\n只处理哪些工作表？（序号，逗号分隔；回车=全部）：").strip()
    chosen = None
    if raw:
        chosen = []
        for tok in re.split(r"[,，\s]+", raw):
            if tok.isdigit():
                idx = int(tok) - 1
                if 0 <= idx < len(sheets):
                    chosen.append(sheets[idx][0])
        if not chosen:
            emit("未识别到有效序号，改为处理全部")
            chosen = None

    out_path = input(f"\n输出文件 [{config.TERM_FILE}]: ").strip().strip('"')
    out_path = out_path or config.TERM_FILE

    # ★ 已有术语字典时默认追加：新术语接在末尾，原有译法不动
    mode = "append" if getattr(config, "EXCEL_APPEND", True) else "overwrite"
    if os.path.exists(out_path):
        try:
            import build_terms as _BT
            old_n = len(_BT.read_existing_terms(out_path))
        except Exception:
            old_n = 0
        if old_n:
            emit(f"\n检测到已有术语字典：{out_path}（{old_n} 条）")
            raw2 = input("  回车 = 在末尾追加新术语 / 输入 o = 整份覆盖: ")
            mode = "overwrite" if raw2.strip().lower() in ("o", "over",
                                                          "overwrite") else "append"
        else:
            emit(f"\n{out_path} 已存在但读不到 TERM_DICT，将整份重写")

    emit(f"模式：{'追加到末尾' if mode == 'append' else '整份覆盖'}")
    build_terms_from_excel(excel_path, chosen, src, tgt, out_path, mode=mode)


def _choose_language(prompt, default_key, exclude=None):
    """Excel 列名选择（用 build_terms 的别名表）。"""
    import build_terms as BT
    keys = list(BT.LANG_ALIASES.keys())
    emit(f"\n{prompt}")
    for i, k in enumerate(keys, 1):
        mark = ""
        if k == default_key:
            mark = "   ← 默认"
        if exclude and k == exclude:
            mark = "   (已被选为另一种语言)"
        emit(f"  {i:>2}. {k}{mark}")
    emit("   0. 自定义")

    raw = input(f"请选择 [{default_key}]: ").strip()
    if not raw:
        return default_key
    if raw == "0":
        return input("请输入列名（Excel 表头文字）：").strip() or None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(keys):
            return keys[idx]
    emit("无效输入")
    return None


def cmd_provider():
    """菜单 10：本地模型服务（切换提供商 / 模型 / 部署）"""
    import providers as PV

    while True:
        key = PV.current()
        p = PV.get(key)
        emit("\n" + "=" * 62)
        emit(f"  本地模型服务   当前：{p['label']}")
        emit("=" * 62)
        emit(f"  服务地址：{PV.chat_url(key)}")
        emit(f"  模型：{PV.current_model(key) or '（未设置）'}")
        emit(f"  说明：{p['summary']}")
        emit("-" * 62)
        for i, k in enumerate(PV.keys(), 1):
            mark = " ← 当前" if k == key else ""
            emit(f"  {i}. 切换到 {PV.label_of(k)}{mark}")
        emit(f"  {len(PV.keys()) + 1}. 修改当前服务地址")
        emit(f"  {len(PV.keys()) + 2}. 检测服务是否在线")
        emit(f"  {len(PV.keys()) + 3}. 列出本机可用模型")
        emit(f"  {len(PV.keys()) + 4}. 一键部署模型（拉取 / 下载）")
        emit("  0. 返回主菜单")
        emit("=" * 62)

        raw = input("请选择：").strip()
        if raw in ("0", ""):
            return

        keys = PV.keys()
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            target = keys[int(raw) - 1]
            if target == key:
                emit("已经是当前提供商")
                continue
            PV.set_prev_provider(key)
            changes = PV.apply_provider(target)
            emit(f"\n已切换到 {PV.label_of(target)}")
            for name, old, new in changes:
                emit(f"  · {name}：{old}  →  {new}")
            auto, manual = PV.adaptation(key, target)
            emit("\n[已自动完成]")
            for it in auto:
                emit(f"  ✔ {it['title']}：{it['detail']}")
            if manual:
                emit("\n[还需要你手动处理]")
                for it in manual:
                    emit(f"  ⚠ {it['title']}：{it['detail']}")
            continue

        extra = len(keys)
        if raw == str(extra + 1):
            new_url = input(f"新的服务地址（当前 {PV.chat_url(key)}）：").strip()
            if not new_url:
                emit("已取消")
                continue
            ok, msg = PV.set_url(new_url, key)
            emit(f"{'✔ 已更新' if ok else '✘ 失败'}：{msg}")
            continue

        if raw == str(extra + 2):
            ok, msg = PV.probe(key)
            emit(f"  [{'✔' if ok else '✘'}] {msg}")
            continue

        if raw == str(extra + 3):
            rows = PV.all_models(key)
            if not rows:
                emit("  （没查到模型；服务可能没开，下面是推荐目录）")
                rows = PV.catalog(key)
            emit(f"  共 {len(rows)} 个：")
            for r in rows:
                tag = "已装" if r.get("installed") else "可拉取"
                emit(f"   [{tag}] {r['name']}  "
                     f"{r.get('params') or '?'}  "
                     f"ctx={r.get('ctx') or '?'}  "
                     f"{r.get('size') or '?'}")
            continue

        if raw == str(extra + 4):
            name = input("要部署的模型名（回车用当前）：").strip()
            if not name:
                name = PV.current_model(key)
            if not name:
                emit("没有指定模型")
                continue
            emit("开始部署，输出如下（可随时 Ctrl+C 中断）：\n")
            ok, msg = PV.run_deploy(name, key, emit=emit)
            emit(f"\n{'✔' if ok else '✘'} {msg}")
            continue

        emit("无效选项")


def cmd_show_logs():
    """菜单 11：日志 / 环境检查"""
    import env_check

    log_dir = os.path.join(config.BASE_DIR, "logs")
    emit("\n[日志目录] " + log_dir)
    if not os.path.isdir(log_dir):
        emit("（暂无日志）")
        return

    files = sorted(f for f in os.listdir(log_dir)
                  if f.endswith(".log"))
    if not files:
        emit("（暂无日志）")
        return

    for f in files:
        p = os.path.join(log_dir, f)
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        emit(f"  {f}   ({size / 1024:.1f} KB)")

    today = time.strftime("%Y%m%d")
    target = os.path.join(log_dir, f"translate_{today}.log")
    if not os.path.exists(target):
        target = os.path.join(log_dir, files[-1])

    emit(f"\n--- {os.path.basename(target)} 末尾 40 行 ---")
    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in lines[-40:]:
            emit(line.rstrip())
    except Exception as e:
        emit(f"读取失败：{e}")

    emit("\n[环境检查]")
    result = env_check.check_all(verbose=False)
    for k, (ok, msg) in result.items():
        emit(f"  [{'✔' if ok else '✘'}] {k}: {msg}")

    emit("\n[检查更新]")
    try:
        import updater
        has, info = updater.check_update()
        if info.get("error"):
            emit(f"  获取失败：{info['error']}")
        elif has:
            emit(f"  发现新版本：{info.get('tag')}（当前 v{config.VERSION}）")
            emit(f"  下载地址：{info.get('url')}")
        else:
            emit(f"  当前已是最新版本 v{config.VERSION}")
    except Exception as e:
        emit(f"  检查更新失败：{e}")
