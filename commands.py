# -*- coding: utf-8 -*-
"""
核心功能实现。

设计约定：
  · 所有 xxx_paths(...) 为「无交互核心」，只通过 bridge 输出/上报进度，
    供命令行与 GUI 共用；
  · 所有 cmd_xxx(...) 为命令行外壳，负责询问语言、选择文件范围等。
"""
import os
import re
import time
from collections import Counter, defaultdict

import bridge
import checker
import config
import parser as P
import processor as PR
import settings
from cache import Cache
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

# 重翻检查报告时，需要处理的问题类型
RETRANSLATE_KINDS = {
    "疑似未翻译", "疑似异常句", "译文残留控制码",
    "译文残留占位符", "翻译失败", "占位符兜底", "术语冲突",
}


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


# 生成物后缀（选文件时要跳过 / 报告模式下要识别）
TRANSLATED_SUFFIX = "_translated.txt"
REPORT_SUFFIX     = "_translated_report.txt"


def report_path_for(src_path):
    """源文件 → 对应检查报告路径。"""
    if not src_path:
        return None
    stem = os.path.splitext(os.path.basename(src_path))[0]
    parent = os.path.dirname(os.path.abspath(src_path))
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
    emit(f"   0. 自定义（手动输入）")

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
# 常用语言列表（序号选择用）
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


# ================================================================
# 报告路径
# ================================================================
def _report_path():
    """返回检查报告路径：与输出文件同目录。"""
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


def _write_unknown_ctrl_report(hits, report_path):
    """hits: [(token, original, context), ...]"""
    from collections import defaultdict

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
# 语言选择
# ================================================================
def _pick_language(prompt, default_key, exclude=None):
    """交互式语言选择。返回选中的语言字符串，或 None 表示取消。"""
    print(f"\n{prompt}")
    for i, lang in enumerate(LANG_OPTIONS, 1):
        mark = ""
        if lang == default_key:
            mark = "   ← 上次使用"
        if exclude and lang == exclude:
            mark = "   (已被选为另一种语言)"
        print(f"  {i:>2}. {lang}{mark}")
    print(f"   0. 自定义（手动输入）")

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
    print("无效输入")
    return None


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

    missing = [item["token"] for item in maps if item["token"] not in raw]
    if not missing:
        return raw

    missing_set = set(missing)
    result = raw

    for m_idx, item in enumerate(maps):
        token = item["token"]
        if token not in missing_set:
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
                     mode_of_entry=None, bi=1):
    """翻译一批文本，写入缓存。返回成功条数。"""
    if not batch_texts:
        return 0

    import prefix_dict as PFD

    batch, maps_dict, breaks_dict = [], {}, {}
    batch_terms = {}
    hit_terms_all = {}
    prefix_list = {}
    new_prefixes = 0

    log.info("[批 %d] 开始  %d 条", bi, len(batch_texts))

    for k, txt in enumerate(batch_texts):
        # 前缀提取
        if getattr(config, "PREFIX_DICT_ENABLE", True):
            prefix, body = PR.split_prefix(txt)
            prefix_list[k] = prefix
            if prefix and PFD.register_prefix(prefix):
                new_prefixes += 1
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
        emit(f"  [前缀] 发现 {new_prefixes} 个新前缀，已加入 prefix_dict.json")
        log.info("[批 %d] 新增前缀 %d 个", bi, new_prefixes)

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

        prefix = prefix_list.get(k, "")
        if prefix:
            final = PFD.apply_prefix(prefix) + body_final
        else:
            final = body_final

        # ★ 控制码回退：译文里缺失/未原样保留的控制码，一律回退为原文控制符
        final, fixed_ctrl = PR.repair_missing_controls(src, final)
        if fixed_ctrl:
            log.warning("[批 %d][%d] 译文缺失控制码 %s，已按原文回退",
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
                for idx, terms in batch_terms.items():
                    if not (0 <= idx < len(batch_texts)):
                        continue
                    info = _match_conflict(terms, conflicts)
                    if not info:
                        continue
                    src_text = batch_texts[idx]
                    extra_hits.append({
                        'src': src_text,
                        'kind': '术语冲突',
                        'dst': cache.get(src_text, ''),
                        'detail': (f"术语冲突：{info['src']} "
                                   f"已有 {info['old']}，"
                                   f"模型返回 {info['new']}"),
                    })
        except Exception as e:
            log.warning("术语合并失败：%s", e)

    # ---------- 术语兜底替换 ----------
    if term_pairs_list:
        fix_count = 0
        for k, src in enumerate(batch_texts):
            old_final = cache.get(src)
            if not old_final:
                continue
            new_final = PR.apply_terms(old_final)
            if new_final != old_final:
                cache.put(src, new_final)
                fix_count += 1
        if fix_count:
            emit(f"  [术语] 兜底替换 {fix_count} 条")

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
        todo.append(txt)

    if skipped_pure:
        cache.save()
        log.info("跳过纯控制符句子 %d 条（已缓存原文）", skipped_pure)
        emit(f"[过滤] 跳过 {skipped_pure} 条纯控制符句子（不送模型）")

    emit(f"[待翻] 唯一 {len(seen)}  需翻 {len(todo)}  "
         f"缓存命中 {len(seen) - len(todo)}")

    # ---------- 批量翻译 ----------
    unknown_ctrl_hits = []
    failed = []
    extra_hits = []

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
                                  bi=bi)

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
                emit(f"  请到菜单 4「前缀字典」补全译文后应用")
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

    # ---------- 未识别控制码报告 ----------
    if unknown_ctrl_hits:
        try:
            uc_path = _unknown_ctrl_report_path()
            _write_unknown_ctrl_report(unknown_ctrl_hits, uc_path)

            from collections import Counter
            kinds = Counter(t for t, _, _ in unknown_ctrl_hits)

            print(f"\n⚠ 检测到未识别控制码：")
            for tok, n in kinds.most_common(10):
                print(f"    {tok}  × {n}")
            if len(kinds) > 10:
                print(f"    … 其余 {len(kinds) - 10} 种省略")
            print(f"  报告：{uc_path}")

            log.warning("未识别控制码 %d 种 / %d 次 → %s",
                        len(kinds), len(unknown_ctrl_hits), uc_path)
        except Exception as e:
            log.error("写未识别控制码报告失败：%s", e)

    # ---------- 前缀字典统计 ----------
    if getattr(config, "PREFIX_DICT_ENABLE", True):
        try:
            import prefix_dict as PFD
            s = PFD.stats()
            if s["pending"]:
                print(f"\n[前缀字典] 共 {s['total']} 条，"
                      f"已翻译 {s['done']} 条，待翻译 {s['pending']} 条")
                print(f"  请编辑：{PFD.DICT_FILE}")
                print(f"  翻译完成后选菜单 4 或 5 应用前缀字典")
        except Exception as e:
            log.debug("前缀字典统计失败：%s", e)

    # ---------- 自动建立术语表快照 ----------
    try:
        import term_sync as TS
        current_terms = TS.load_current_terms()
        if current_terms:
            TS.save_snapshot(current_terms)
            log.info("术语表快照已更新：%d 条", len(current_terms))
    except Exception as e:
        log.warning("建立术语表快照失败：%s", e)


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
    hits = checker.check(src_lines, out_lines, entries, special, report_path)
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
def retranslate_report_paths(paths, src_lang=None, tgt_lang=None, model=None):
    """扫描输出文件，找出问题句，删缓存后重翻。"""
    _apply_lang_model(src_lang, tgt_lang, model)

    log.info("=" * 50)
    log.info("重翻检查报告内容  共 %d 个文件", len(paths))

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

        kinds = Counter(h['kind'] for h in hits)
        emit("  问题分布：" + "  ".join(f"{k}:{n}" for k, n in kinds.items()))

        to_re = [h for h in hits if h['kind'] in RETRANSLATE_KINDS]
        if not to_re:
            emit("  没有需要重翻的句子（仅符号不匹配 / 特殊行，需手动处理）")
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
        emit("术语表为空或不存在，请先运行菜单 6 生成")
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

        config.Runtime.set_input(path)
        bridge.progress(i - 1, len(paths), os.path.basename(path))

        if not os.path.exists(config.Runtime.cache_file):
            emit(f"  缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
            continue

        cache = Cache(config.Runtime.cache_file)
        hits = TS.find_affected_cache(cache.data, affected)
        if not hits:
            emit(f"  [{os.path.basename(path)}] 没有句子命中这些术语")
            continue

        emit(f"  [{os.path.basename(path)}] 命中缓存 {len(hits)} 条")
        by_term = Counter(term for _, term in hits)
        for term, n in by_term.most_common(8):
            emit(f"      {term}: {n} 条")

        removed_n = cache.remove_many([k for k, _ in hits])
        cache.save(force=True)
        total_removed += removed_n
        emit(f"  ✔ 已删除 {removed_n} 条缓存")

        lines, newline = P.read_file(path, config.INPUT_ENCODING)
        _translate_core(path, lines, newline, show_header=False)
        files_done += 1

    TS.save_snapshot(current)
    bridge.progress(len(paths), len(paths), "完成")
    return {"files": files_done, "removed": total_removed}


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

        config.Runtime.set_input(path)
        bridge.progress(i - 1, len(paths), os.path.basename(path))

        if not os.path.exists(config.Runtime.cache_file):
            emit(f"  缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
            continue

        try:
            lines, newline = P.read_file(path, config.INPUT_ENCODING)
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
            if new_prefix and new_prefix != prefix:
                if cached_final.startswith(prefix):
                    body_final = cached_final[len(prefix):]
                elif cached_final.startswith(new_prefix):
                    body_final = cached_final[len(new_prefix):]
                else:
                    body_final = cached_final
                translations[src] = new_prefix + body_final
                hit_prefix += 1
            else:
                translations[src] = cached_final
                miss_prefix += 1

        replaced = P.write_output(
            lines, entries, translations,
            config.Runtime.output_file, newline, config.OUTPUT_ENCODING,
        )
        emit(f"  [{os.path.basename(path)}] 替换 {replaced}/{len(entries)} 条"
             f"  前缀生效 {hit_prefix}  未译 {miss_prefix}  无前缀 {no_prefix}")
        done += 1

    bridge.progress(len(paths), len(paths), "完成")
    log.info("应用前缀字典完成：%d 个文件", done)
    return {"files": done}


# ================================================================
# 核心 5：中文润色重翻
# ================================================================
def _polish_core(path, lines=None, newline=None, show_header=True):
    """
    对单个文件：把缓存里的中文译文再润色一遍，覆盖回缓存并重写输出文件。
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
        todo.append(txt)

    emit(f"[润色] 缓存 {len(cache)} 条  待润色 {len(todo)} 条")
    if not todo:
        emit("没有需要润色的译文（先运行一次翻译）")
        return {"changed": 0, "todo": 0}

    client = OllamaClient()
    batch_size = getattr(config, "POLISH_BATCH_SIZE", 8) or 8
    changed = 0
    kept = 0
    total = len(todo)

    for bi, batch_texts in enumerate(_make_batches(todo, batch_size,
                                                   getattr(config,
                                                           "MAX_BATCH_CHARS",
                                                           1400)), 1):
        if bridge.cancelled():
            emit("\n[中断] 用户取消")
            break

        items, maps_dict = [], {}
        for k, txt in enumerate(batch_texts):
            safe, maps = PR.protect(cache.get(txt), drop_newline=False)
            items.append((k, safe))
            maps_dict[k] = maps

        result = polish_with_retry(client, items)

        # 单条补全
        for k, safe in items:
            if result.get(k, "").strip():
                continue
            for attempt in range(getattr(config, "SINGLE_RETRIES", 3)):
                try:
                    r = polish_with_retry(client, [(k, safe)])
                    if r.get(k, "").strip():
                        result[k] = r[k]
                        break
                except Exception:
                    time.sleep(1.0)

        for k, txt in enumerate(batch_texts):
            raw = result.get(k)
            if not raw or not raw.strip():
                kept += 1
                continue

            maps = maps_dict[k]
            ok_ph, _ = PR.verify(raw, maps)
            if not ok_ph:
                # 润色绝不冒险：占位符不全就保留原译文
                log.warning("[润色 %d][%d] 占位符不全，保留原译文", bi, k)
                kept += 1
                continue

            new_text = PR.restore(raw, maps).strip()
            if not new_text:
                kept += 1
                continue
            if new_text == cache.get(txt):
                kept += 1
                continue

            cache.put(txt, new_text)
            changed += 1

        cache.tick()
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

    return {"changed": changed, "kept": kept, "todo": total}


def polish_paths(paths, model=None):
    """中文润色重翻（无交互核心）。"""
    _apply_lang_model(None, None, model)

    log.info("=" * 50)
    log.info("中文润色重翻  共 %d 个文件", len(paths))

    if not getattr(config, "POLISH_ENABLE", True):
        emit("中文润色功能已关闭（POLISH_ENABLE=False）")
        return {"files": 0, "changed": 0}

    total_changed = 0
    files_done = 0

    for i, path in enumerate(paths, 1):
        if bridge.cancelled():
            break
        if not os.path.exists(path):
            emit(f"[跳过] 文件不存在：{path}")
            continue

        config.Runtime.set_input(path)
        bridge.progress(i - 1, len(paths), os.path.basename(path))

        if not os.path.exists(config.Runtime.cache_file):
            emit(f"  缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
            continue

        try:
            lines, newline = P.read_file(path, config.INPUT_ENCODING)
        except Exception as e:
            emit(f"  读取失败：{e}")
            continue

        if len(paths) > 1:
            emit(f"\n[{i}/{len(paths)}] {os.path.basename(path)}")

        try:
            r = _polish_core(path, lines, newline,
                             show_header=(len(paths) == 1))
            total_changed += r.get("changed", 0)
            files_done += 1
        except bridge.CancelRequested:
            emit("\n[中断] 用户取消")
            break

    bridge.progress(len(paths), len(paths), "完成")
    return {"files": files_done, "changed": total_changed}


# ================================================================
# 核心 6：Excel 转术语表
# ================================================================
def build_terms_from_excel(excel_path, sheets=None, source_lang="英文",
                           target_lang="简体中文", out_path=None):
    """Excel → term_dict.py（无交互）。返回结果 dict。"""
    import importlib
    import build_terms as BT

    out_path = out_path or config.TERM_FILE
    log.info("Excel 转术语表：%s  %s → %s", excel_path, source_lang, target_lang)

    result = BT.build_terms(excel_path, out_path, source_lang, target_lang,
                            sheets=sheets, dedup=True, verbose=False)

    for e in result.get("errors", []):
        emit(f"  [err] {e}")

    if result.get("ok"):
        emit(f"✔ 共 {result['total']} 条 → {result['out_path']}")
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
    """菜单 1：翻译"""
    if not _ask_languages():
        return
    paths = _select_scope_interactive("选择要翻译的文件")
    if not paths:
        return
    translate_paths(paths)


def cmd_retranslate_report():
    """菜单 2：重翻检查报告"""
    if not _ask_languages():
        return
    paths = _select_scope_interactive("选择要重翻的文件")
    if not paths:
        return
    retranslate_report_paths(paths)


def cmd_retranslate_terms():
    """菜单 3：术语更新后重翻"""
    if not _ask_languages():
        return
    paths = _select_scope_interactive("选择要重翻的文件")
    if not paths:
        return
    retranslate_terms_paths(paths)


def cmd_review_prefix_dict():
    """菜单 4：前缀字典（查看 / 编辑）"""
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
    """菜单 5：中文润色重翻"""
    paths = _select_scope_interactive("选择要润色的文件")
    if not paths:
        return
    polish_paths(paths)


def cmd_apply_prefix_dict():
    """菜单 4 的下半段：只应用前缀字典"""
    paths = _select_scope_interactive("选择要应用前缀字典的文件")
    if not paths:
        return
    apply_prefix_dict_paths(paths)


def _open_path(path):
    try:
        if os.name == "nt":
            os.startfile(path)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        emit(f"打开失败：{e}，请手动打开：{path}")
        return False


def cmd_build_terms():
    """菜单 6：Excel 转术语表"""
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
    build_terms_from_excel(excel_path, chosen, src, tgt, out_path or None)


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


def cmd_show_logs():
    """菜单 8：日志 / 环境检查"""
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
