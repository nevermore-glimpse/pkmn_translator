# -*- coding: utf-8 -*-
"""四个核心功能的实现：翻译 / 检查 / Excel 转术语表 / 术语更新后重翻。"""
import os
import re
import time

import config
import parser as P
import processor as PR
import checker
from cache import Cache
from logger import get_logger
from translator import OllamaClient, translate_with_retry

log = get_logger("commands")


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
def _force_restore(raw, maps):
    """
    兜底补回丢失的占位符。
    """
    if not maps:
        return raw

    missing = [item["token"] for item in maps if item["token"] not in raw]
    if not missing:
        return PR.restore(raw, maps)

    missing_set = set(missing)
    result = raw

    for m_idx, item in enumerate(maps):
        token = item["token"]
        if token not in missing_set:
            continue
        original = item.get("original", "")

        new_result = _insert_token_by_hint(
            result, token, original, maps, m_idx, missing_set
        )
        if new_result is not None:
            result = new_result
        else:
            result = result.rstrip() + " " + token
        missing_set.discard(token)

    return PR.restore(result, maps)


def _insert_token_by_hint(text, token, original, maps, m_idx, missing_set):
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

    return None


# ================================================================
# 内部：翻译一批
# ================================================================
def _translate_batch(client, batch_texts, cache,
                     unknown_ctrl_hits, failed, extra_hits,
                     mode_of_entry=None, bi=1):
    """
    翻译一批文本，写入缓存。
    返回成功条数。
    """
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
        log.debug("[批 %d][%d] 原文=%r", bi, k, txt)

        # 前缀提取
        if getattr(config, "PREFIX_DICT_ENABLE", True):
            prefix, body = PR.split_prefix(txt)
            prefix_list[k] = prefix
            if prefix:
                if PFD.register_prefix(prefix):
                    new_prefixes += 1
                    log.debug("[批 %d][%d] 新前缀=%r", bi, k, prefix)
                else:
                    log.debug("[批 %d][%d] 前缀=%r（已注册）", bi, k, prefix)
                log.debug("[批 %d][%d] 剥离前缀后 body=%r", bi, k, body)
            else:
                log.debug("[批 %d][%d] 无前缀", bi, k)
        else:
            prefix_list[k] = ""
            body = txt

        # 玩家名替换
        if getattr(config, "PLAYER_TOKEN", None):
            new_body = body.replace(config.PLAYER_TOKEN,
                                    config.PLAYER_PLACEHOLDER)
            if new_body != body:
                log.debug("[批 %d][%d] 玩家名替换：%r → %r",
                          bi, k, body, new_body)
            body = new_body

        # 保护 + 术语查找
        safe, maps, breaks, hit_terms = PR.prepare(body)
        batch.append((k, safe))
        maps_dict[k] = maps
        breaks_dict[k] = breaks

        log.debug("[批 %d][%d] 送模型=%r", bi, k, safe)
        log.debug("[批 %d][%d] 占位符数=%d  换行断点=%d",
                  bi, k, len(maps), sum(1 for b in breaks if b))

        if hit_terms:
            log.debug("[批 %d][%d] 术语命中 %d 条：%s",
                      bi, k, len(hit_terms),
                      ", ".join(f"{a}={b}" for a, b in hit_terms[:5])
                      + (" …" if len(hit_terms) > 5 else ""))

        for src_term, dst_term in hit_terms:
            if src_term not in hit_terms_all:
                hit_terms_all[src_term] = dst_term

        for token, ctx in PR.detect_unknown_ctrl(safe):
            unknown_ctrl_hits.append((token, txt, ctx))
            log.debug("[批 %d][%d] 未识别控制码：%r  上下文=%r",
                      bi, k, token, ctx)

    if new_prefixes:
        PFD.save()
        print(f"  [前缀] 发现 {new_prefixes} 个新前缀，已加入 prefix_dict.json")
        log.info("[批 %d] 新增前缀 %d 个", bi, new_prefixes)

    term_pairs_list = list(hit_terms_all.items())
    if term_pairs_list:
        log.info("[批 %d] 命中术语 %d 条，随 prompt 发送",
                 bi, len(term_pairs_list))
        log.debug("[批 %d] 术语表内容：%s", bi,
                  ", ".join(f"{a}={b}" for a, b in term_pairs_list[:10])
                  + (" …" if len(term_pairs_list) > 10 else ""))

    # ---------- 请求模型 ----------
    log.info("[批 %d] 请求模型（%d 条）…", bi, len(batch))
    t_req = time.time()
    result = translate_with_retry(client, batch,
                                  terms_out=batch_terms,
                                  term_pairs=term_pairs_list)
    t_req_elapsed = time.time() - t_req
    log.info("[批 %d] 模型返回 %d 条，耗时 %.1fs",
             bi, len(result), t_req_elapsed)

    # 单条重试
    missing = [(k, t) for k, t in batch
               if k not in result or not result[k].strip()]
    if missing:
        log.warning("[批 %d] 缺失 %d 条，单条重试", bi, len(missing))
    for k, safe in missing:
        for attempt in range(config.SINGLE_RETRIES):
            try:
                log.debug("[批 %d][%d] 单条重试 %d/%d",
                          bi, k, attempt + 1, config.SINGLE_RETRIES)
                r = translate_with_retry(client, [(k, safe)],
                                         terms_out=batch_terms,
                                         term_pairs=term_pairs_list)
                if k in r and r[k].strip():
                    result[k] = r[k]
                    log.debug("[批 %d][%d] 单条重试成功", bi, k)
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

        log.debug("[批 %d][%d] 模型原始返回=%r", bi, k, raw)

        maps = maps_dict[k]

        # 占位符校验
        ok_ph, missing_ph = PR.verify(raw, maps)
        if not ok_ph:
            log.warning("[批 %d][%d] 占位符丢失 %s",
                        bi, k, missing_ph)
            retried = False
            for attempt in range(config.SINGLE_RETRIES):
                try:
                    log.debug("[批 %d][%d] 占位符重试 %d/%d",
                              bi, k, attempt + 1, config.SINGLE_RETRIES)
                    r = translate_with_retry(client, [(k, batch[k][1])],
                                             term_pairs=term_pairs_list)
                    if k in r and r[k].strip():
                        ok3, _ = PR.verify(r[k], maps)
                        if ok3:
                            raw = r[k]
                            retried = True
                            log.debug("[批 %d][%d] 占位符重试成功", bi, k)
                            break
                except Exception:
                    time.sleep(1.0)
            if not retried:
                raw = _force_restore(raw, maps)
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
        log.debug("[批 %d][%d] 换行模式=%s", bi, k, mode)

        body_final = PR.finalize(raw, maps, breaks_dict.get(k), mode=mode)
        log.debug("[批 %d][%d] body译文=%r", bi, k, body_final)

        if getattr(config, "PLAYER_TOKEN", None):
            new_body_final = body_final.replace(config.PLAYER_PLACEHOLDER,
                                                config.PLAYER_TOKEN)
            if new_body_final != body_final:
                log.debug("[批 %d][%d] 玩家名还原：%r → %r",
                          bi, k, body_final, new_body_final)
            body_final = new_body_final

        prefix = prefix_list.get(k, "")
        if prefix:
            applied = PFD.apply_prefix(prefix)
            final = applied + body_final
            if applied != prefix:
                log.debug("[批 %d][%d] 前缀应用字典：%r → %r",
                          bi, k, prefix, applied)
            else:
                log.debug("[批 %d][%d] 前缀未翻译，原样保留：%r",
                          bi, k, prefix)
        else:
            final = body_final

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
                print(f"  [术语] 新增 {added} 条，已应用到后续批次")
                log.info("[批 %d] 术语新增 %d 条", bi, added)

            if conflicts:
                log.warning("[批 %d] 术语冲突 %d 条", bi, len(conflicts))
                conflict_keys = {c['src'].lower() for c in conflicts}
                for idx, terms in batch_terms.items():
                    if not any(k.lower() in conflict_keys
                               for k in terms.keys()):
                        continue
                    if 0 <= idx < len(batch_texts):
                        src_text = batch_texts[idx]
                        conflict_info = next(
                            (c for c in conflicts
                             if c['src'].lower() in
                             {k.lower() for k in terms.keys()}),
                            None,
                        )
                        detail = (
                            f"术语冲突：{conflict_info['src']} "
                            f"已有 {conflict_info['old']}，"
                            f"模型返回 {conflict_info['new']}"
                            if conflict_info else "术语冲突"
                        )
                        extra_hits.append({
                            'src': src_text,
                            'kind': '术语冲突',
                            'dst': cache.get(src_text, ''),
                            'detail': detail,
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
                log.debug("[批 %d][%d] 术语兜底：%r → %r",
                          bi, k, old_final, new_final)
        if fix_count:
            print(f"  [术语] 兜底替换 {fix_count} 条")
            log.info("[批 %d] 术语兜底替换 %d 条", bi, fix_count)

    return ok


# ================================================================
# 内部：翻译单个文件（核心流程）
# ================================================================
def _translate_core(src_path, newline, show_header=True):
    """
    对单个文件执行完整翻译流程。
    src_path 已在 Runtime 里设置好 input/output/cache。
    """
    out_path = config.Runtime.output_file
    cache_path = config.Runtime.cache_file

    if show_header:
        print(f"\n{'=' * 55}")
        print(f"  翻译：{src_path}")
        print(f"  输出：{out_path}")
        print(f"{'=' * 55}")

    # 加载术语表
    PR.load_terms()

    # 解析
    lines, _ = P.read_file(src_path, config.INPUT_ENCODING)
    entries, special = P.extract_entries(lines)

    # ★ 计算每行所属区块的换行模式
    line_modes = P.get_block_modes(lines)
    mode_of_entry = {}
    for ln, src_text in entries:
        if src_text not in mode_of_entry and 0 <= ln < len(line_modes):
            mode_of_entry[src_text] = line_modes[ln]
    log.info("文件 %d 行  待翻 %d  特殊 %d",
             len(lines), len(entries), len(special))
    print(f"[解析] 总行数 {len(lines)}  待翻 {len(entries)}  特殊 {len(special)}")

    if not entries:
        print("没有可翻译的内容")
        return

    # 缓存
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
        print(f"[过滤] 跳过 {skipped_pure} 条纯控制符句子（不送模型）")

    log.info("唯一 %d  需翻 %d  缓存命中 %d",
             len(seen), len(todo), len(seen) - len(todo))
    print(f"[待翻] 唯一 {len(seen)}  需翻 {len(todo)}  缓存命中 {len(seen) - len(todo)}")

    # ---------- 批量翻译 ----------
    unknown_ctrl_hits = []
    failed = []
    extra_hits = []

    if todo:
        client = OllamaClient()
        done = 0
        t0 = time.time()
        total = len(todo)

        for start in range(0, total, config.BATCH_SIZE):
            bi = start // config.BATCH_SIZE + 1
            batch_texts = todo[start:start + config.BATCH_SIZE]

            log.info("[批 %d] 开始  %d 条", bi, len(batch_texts))
            for k, txt in enumerate(batch_texts):
                log.debug("[批 %d][%d] 原文=%r", bi, k, txt)

            ok = _translate_batch(client, batch_texts, cache,
                                  unknown_ctrl_hits, failed, extra_hits,
                                  mode_of_entry=mode_of_entry,
                                  bi=bi)

            cache.save()
            done += len(batch_texts)
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate / 60 if rate > 0 else 0
            log.info("[批 %d] 成功 %d/%d  累计 %d/%d  %.2f条/秒  ETA %.1f分",
                     bi, ok, len(batch_texts), done, total, rate, eta)

        if failed:
            log.warning("失败 %d 条", len(failed))
            print(f"\n[失败] {len(failed)} 条未翻译：")
            for t in failed[:10]:
                print(f"    {t['src'][:70]}   （{t['reason']}）")
            if len(failed) > 10:
                print(f"    … 其余 {len(failed) - 10} 条省略")

    # ---------- 回写 ----------
    translations = {txt: cache.get(txt) for _, txt in entries if cache.get(txt)}
    replaced = P.write_output(
        lines, entries, translations,
        out_path, newline, config.OUTPUT_ENCODING,
    )
    log.info("回写：%d/%d → %s", replaced, len(entries), out_path)
    print(f"\n✔ 输出：{out_path}")
    print(f"  替换 {replaced}/{len(entries)} 条")

    # ---------- 自动检查 ----------
    print("\n[检查] 生成检查报告…")
    try:
        out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
        report_path = _report_path()
        all_extra = failed + extra_hits
        hits = checker.check(lines, out_lines, entries, special, report_path,
                             extra_hits=all_extra)
        _print_summary(hits, report_path)
    except Exception as e:
        log.error("自动检查失败：%s", e)
        print(f"  自动检查失败（不影响翻译结果）：{e}")

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


# ================================================================
# 功能 1：翻译
# ================================================================
def cmd_translate(skip_picker=False):
    import filepicker
    import settings

    log.info("=" * 50)
    log.info("开始翻译")

    # ---------- 选源语言 / 目标语言 ----------
    if not skip_picker and getattr(config, "ASK_LANG_EACH_TIME", True):
        src_lang = _pick_language("请选择【源语言】：", config.SOURCE_LANG)
        if not src_lang:
            print("已取消")
            return

        tgt_lang = _pick_language("请选择【目标语言】：",
                                  config.TARGET_LANG, exclude=src_lang)
        if not tgt_lang:
            print("已取消")
            return

        if src_lang == tgt_lang:
            print(f"\n⚠ 源语言和目标语言相同（{src_lang}）")
            if input("继续？(y/N): ").strip().lower() != "y":
                return

        settings.set_value("SOURCE_LANG", src_lang)
        settings.set_value("TARGET_LANG", tgt_lang)

        log.info("翻译方向：%s → %s", src_lang, tgt_lang)
        print(f"\n  翻译方向：{src_lang} → {tgt_lang}")
    else:
        print(f"\n  翻译方向：{config.SOURCE_LANG} → {config.TARGET_LANG}")

    # ---------- 选文件 / 文件夹 ----------
    if skip_picker:
        src_paths = [config.Runtime.input_file]
    else:
        default_dir = (os.path.dirname(config.Runtime.input_file)
                       or config.BASE_DIR)
        picked, is_dir = filepicker.pick_path(
            initial_dir=default_dir,
            title="选择要翻译的 .txt 文件或文件夹",
        )
        if not picked:
            print("已取消")
            return

        if is_dir:
            files = sorted([
                os.path.join(picked, f)
                for f in os.listdir(picked)
                if f.lower().endswith(".txt")
            ])
            if not files:
                print(f"文件夹里没有 .txt 文件：{picked}")
                return
            print(f"\n文件夹：{picked}")
            print(f"共 {len(files)} 个 .txt 文件：")
            for f in files:
                print(f"  - {os.path.basename(f)}")
            if input("\n开始批量翻译？(Y/n): ").strip().lower() == "n":
                return
            src_paths = files
        else:
            src_paths = [picked]

    # ---------- 逐个翻译 ----------
    total_files = len(src_paths)
    processed = 0

    for i, path in enumerate(src_paths, 1):
        if not os.path.exists(path):
            print(f"[跳过] 文件不存在：{path}")
            continue

        config.Runtime.set_input(path)

        try:
            _, newline = P.read_file(path, config.INPUT_ENCODING)
        except Exception as e:
            print(f"[跳过] 读取失败：{e}")
            continue

        if total_files > 1:
            print(f"\n[{i}/{total_files}] {os.path.basename(path)}")

        try:
            _translate_core(path, newline, show_header=(total_files == 1))
            processed += 1
        except KeyboardInterrupt:
            print("\n[中断] 用户中止")
            raise

    if total_files > 1:
        print(f"\n{'=' * 55}")
        print(f"  批量翻译完成，共处理 {processed}/{total_files} 个文件")
        print(f"{'=' * 55}")


# ================================================================
# 内部：运行检查
# ================================================================
def _run_check():
    """跑一次检查，返回 hits 列表；失败返回 None。"""
    log.info("=" * 50)
    log.info("检查  %s", config.Runtime.output_file)

    if not os.path.exists(config.Runtime.input_file):
        print(f"缺少输入文件：{config.Runtime.input_file}")
        return None
    if not os.path.exists(config.Runtime.output_file):
        print(f"缺少输出文件：{config.Runtime.output_file}（先跑一次翻译）")
        return None

    src_lines, _ = P.read_file(config.Runtime.input_file, config.INPUT_ENCODING)
    out_lines, _ = P.read_file(config.Runtime.output_file, config.OUTPUT_ENCODING)
    entries, special = P.extract_entries(src_lines)
    log.info("待检查 %d 条  特殊 %d 条", len(entries), len(special))

    report_path = _report_path()
    hits = checker.check(src_lines, out_lines, entries, special, report_path)
    _print_summary(hits, report_path)
    return hits


# ================================================================
# 功能 3：重翻检查报告内容
# ================================================================
def cmd_retranslate_failed():
    """扫描输出文件，找出所有未翻译 / 疑似未翻译的句子，重翻。"""
    log.info("=" * 50)
    log.info("重翻检查报告内容")

    print("\n[重翻检查报告内容]")
    print("-" * 55)

    # 1. 先检查
    hits = _run_check()
    if hits is None:
        return

    if not hits:
        print("\n✔ 没有发现问题，无需重翻")
        return

    # 2. 按类型分组
    kinds_count = {}
    for h in hits:
        kinds_count[h['kind']] = kinds_count.get(h['kind'], 0) + 1
    print("\n问题分布：")
    for k, n in kinds_count.items():
        print(f"  {k}: {n}")

    target_kinds = {"疑似未翻译", "译文残留控制码",
                    "译文残留占位符", "翻译失败", "占位符兜底", "术语冲突"}
    to_retranslate = [h for h in hits if h['kind'] in target_kinds]
    symbol_issues = [h for h in hits if h['kind'] == '符号不匹配']
    special_issues = [h for h in hits if h['kind'] == '特殊行']

    # 3. 检查是否可重翻
    if not to_retranslate:
        print("\n没有【未翻译 / 疑似未翻译】的句子")
        if symbol_issues:
            print(f"  符号不匹配 {len(symbol_issues)} 处 —— 属于模型没保留控制码，")
            print(f"    重翻大概率仍会失败，建议看报告手动修正")
        if special_issues:
            print(f"  特殊行 {len(special_issues)} 处 —— 属于未配对的文本行，")
            print(f"    需要手动处理，请查看报告")
        return

    # 4. 列出待重翻
    print(f"\n待重翻：{len(to_retranslate)} 条")
    for h in to_retranslate[:10]:
        print(f"  [{h['kind']}] 行 {h['line_no']}  {h['src'][:60]}")
    if len(to_retranslate) > 10:
        print(f"  … 其余 {len(to_retranslate) - 10} 条")

    # 5. 确认
    print(f"\n将从缓存中删除这 {len(to_retranslate)} 条原文，然后重新翻译。")
    if input("确认？(Y/n): ").strip().lower() == "n":
        print("已取消")
        return

    # 6. 清缓存
    cache = Cache(config.Runtime.cache_file)
    keys = {h['src'] for h in to_retranslate}

    before = len(cache)
    removed = cache.remove_many(keys)
    cache.save(force=True)
    log.info("缓存：%d → %d（删除 %d）", before, len(cache), removed)
    print(f"✔ 已删除 {removed} 条缓存（原缓存 {before} 条）")

    # 7. 重翻
    if removed == 0:
        print("\n⚠ 缓存里没有这些条目（可能上次翻译失败未入库）")
        print("  直接重翻…")

    print()
    cmd_translate(skip_picker=True)


def _print_summary(hits, report_path):
    from collections import Counter
    c = Counter(h['kind'] for h in hits)
    print(f"  共 {len(hits)} 处问题：")
    for k in ('翻译失败', '占位符兜底', '术语冲突',
              '疑似未翻译',
              '符号不匹配', '译文残留控制码', '译文残留占位符', '特殊行'):
        if c.get(k):
            print(f"    {k}: {c[k]}")
    print(f"  报告：{report_path}")


# ================================================================
# 功能 6：Excel 转术语表
# ================================================================
def _choose_language(prompt, default_key, exclude=None):
    import build_terms as BT
    keys = list(BT.LANG_ALIASES.keys())
    print(f"\n{prompt}")
    for i, k in enumerate(keys, 1):
        mark = ""
        if k == default_key:
            mark = "   ← 默认"
        if exclude and k == exclude:
            mark = "   (已被选为另一种语言)"
        print(f"  {i:>2}. {k}{mark}")
    print(f"   0. 自定义")

    raw = input(f"请选择 [{default_key}]: ").strip()
    if not raw:
        return default_key
    if raw == "0":
        return input("请输入列名（Excel 表头文字）：").strip() or None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(keys):
            return keys[idx]
    print("无效输入")
    return None


def cmd_build_terms():
    import importlib
    import filepicker
    import build_terms as BT

    log.info("Excel 转术语表")
    print(f"\n[术语表] 从 Excel 提取")

    # 选 Excel 文件
    excel_path = config.EXCEL_FILE

    if not os.path.exists(excel_path):
        print(f"默认文件不存在：{excel_path}")
        picked = filepicker.pick_excel_file(initial_dir=config.BASE_DIR)
        if not picked:
            print("已取消")
            return
        excel_path = picked
    else:
        print(f"默认 Excel：{excel_path}")
        if input("是否另选？(y/N): ").strip().lower() == "y":
            picked = filepicker.pick_excel_file(
                initial_dir=os.path.dirname(excel_path))
            if picked:
                excel_path = picked

    if not os.path.exists(excel_path):
        print(f"文件不存在：{excel_path}")
        return

    print(f"Excel：{excel_path}")
    log.info("Excel 路径：%s", excel_path)

    try:
        sheets = BT.list_sheets(excel_path)
    except Exception as e:
        log.error("打开 Excel 失败：%s", e)
        print(f"打开 Excel 失败：{e}")
        return

    print(f"\n共 {len(sheets)} 个工作表：")
    for i, (name, r, c) in enumerate(sheets, 1):
        print(f"  {i:>2}. {name}   ({r} 行 × {c} 列)")

    # 选语言
    src = _choose_language("请选择【源语言】：", config.EXCEL_SOURCE_LANG)
    if not src:
        print("已取消")
        return

    tgt = _choose_language("请选择【目标语言】：",
                           config.EXCEL_TARGET_LANG, exclude=src)
    if not tgt:
        print("已取消")
        return

    if src == tgt:
        print(f"\n⚠ 源语言和目标语言相同（{src}）")
        if input("继续？(y/N): ").strip().lower() != "y":
            return

    # 选工作表
    sheet_filter = input(
        "\n只处理哪些工作表？（序号，逗号分隔；回车=全部）："
    ).strip()
    chosen = None
    if sheet_filter:
        chosen = []
        for tok in re.split(r"[,，\s]+", sheet_filter):
            if tok.isdigit():
                idx = int(tok) - 1
                if 0 <= idx < len(sheets):
                    chosen.append(sheets[idx][0])
        if not chosen:
            print("未识别到有效序号，改为处理全部")

    # 输出路径
    out_path = input(f"\n输出文件 [{config.TERM_FILE}]: ").strip().strip('"')
    out_path = out_path or config.TERM_FILE

    print("\n" + "-" * 50)
    print(f"  源语言：{src}")
    print(f"  目标语言：{tgt}")
    print(f"  工作表：{'全部' if not chosen else ', '.join(chosen)}")
    print(f"  输出到：{out_path}")
    print("-" * 50)
    if input("确认提取？(Y/n): ").strip().lower() == "n":
        return

    result = BT.build_terms(excel_path, out_path, src, tgt,
                            sheets=chosen, dedup=True, verbose=True)
    for e in result["errors"]:
        print(f"  [err] {e}")

    if not result["ok"]:
        print("\n提取失败")
        return

    print(f"\n✔ 共 {result['total']} 条 → {result['out_path']}")
    if input("立即重新加载术语表？(Y/n): ").strip().lower() != "n":
        import processor
        importlib.reload(processor)
        processor.load_terms()
        print("术语表已重新加载。")


# ================================================================
# 功能 2：术语更新后重翻
# ================================================================
def cmd_retranslate_terms():
    """对比术语表快照，找出新增/修改的术语并重翻相关句子。"""
    import term_sync as TS

    log.info("=" * 50)
    log.info("术语更新后重翻")

    print("\n[术语更新后重翻]")
    print("-" * 55)

    # 1. 加载当前术语
    current_terms = TS.load_current_terms()
    log.info("当前术语表：%d 条", len(current_terms))
    print(f"当前术语表：{len(current_terms)} 条")

    if not current_terms:
        print("术语表为空或不存在，请先运行菜单 6 生成")
        return

    # 2. 首次使用：只记录基准
    if not TS.snapshot_exists():
        print(f"\n未找到快照文件：{TS.SNAPSHOT_FILE}")
        print("首次使用本功能，需要先把当前术语表记录为基准。")
        print(f"\n当前术语表：{len(current_terms)} 条")
        ans = input("是否将当前术语表记录为基准？(Y/n): ").strip().lower()
        if ans == "n":
            print("已取消")
            return
        TS.save_snapshot(current_terms)
        print(f"✔ 已保存基准（{len(current_terms)} 条）")
        return

    # 3. 对比
    added, removed, modified, old_was_keyonly = TS.diff_terms()

    if added is None:
        print("快照读取失败，无法对比")
        return

    log.info("对比快照：新增 %d  删除 %d  修改 %d",
             len(added), len(removed), len(modified))
    print(f"\n对比快照：")
    print(f"  当前术语：{len(current_terms)} 条")
    print(f"  新增：    {len(added)} 条")
    print(f"  删除：    {len(removed)} 条")
    if old_was_keyonly:
        print(f"  修改：    （旧快照无 value，无法判断）")
    else:
        print(f"  修改：    {len(modified)} 条")

    if old_was_keyonly:
        print("\n⚠ 检测到旧版快照（只存了 key 没存 value），")
        print("  无法识别译文修改。本次运行后会自动升级快照格式。")

    if not added and not removed and not modified:
        print("\n术语表没有变化，无需重翻")
        return

    # 4. 展示变化
    if added:
        print(f"\n【新增术语】（前 20 条）：")
        for t in added[:20]:
            print(f"  + {t}  →  {current_terms.get(t, '')}")
        if len(added) > 20:
            print(f"  … 其余 {len(added) - 20} 条")

    if modified and not old_was_keyonly:
        print(f"\n【译文修改】（前 20 条）：")
        old_snapshot = TS.load_snapshot() or {}
        old_index = {k.strip().lower(): v for k, v in old_snapshot.items()}
        for t in modified[:20]:
            old_v = old_index.get(t.strip().lower(), "?")
            new_v = current_terms.get(t, "?")
            print(f"  ~ {t}")
            print(f"      旧：{old_v}")
            print(f"      新：{new_v}")
        if len(modified) > 20:
            print(f"  … 其余 {len(modified) - 20} 条")

    if removed:
        print(f"\n【删除的术语】（前 10 条）：")
        for t in removed[:10]:
            print(f"  - {t}")
        if len(removed) > 10:
            print(f"  … 其余 {len(removed) - 10} 条")
        print("  （删除的术语不影响已有译文，只更新快照）")

    # 5. 找命中的缓存
    affected_terms = list(added) + list(modified)
    if not affected_terms:
        print("\n没有需要重翻的内容（只有删除），直接更新快照")
        TS.save_snapshot(current_terms)
        return

    cache = Cache(config.Runtime.cache_file)
    print(f"\n当前缓存：{len(cache)} 条")

    hits = TS.find_affected_cache(cache.data, affected_terms)
    log.info("命中缓存：%d 条", len(hits))

    if not hits:
        print("没有缓存中的句子包含这些术语，无需重翻")
        TS.save_snapshot(current_terms)
        return

    from collections import Counter
    by_term = Counter(term for _, term in hits)
    print(f"\n命中缓存：{len(hits)} 条")
    print("命中分布（前 10 个术语）：")
    for term, n in by_term.most_common(10):
        print(f"  {term}: {n} 条")

    print("\n命中示例（前 10 条）：")
    for key, term in hits[:10]:
        print(f"  [{term}]  {key[:65]}")
    if len(hits) > 10:
        print(f"  … 其余 {len(hits) - 10} 条")

    # 6. 确认
    print(f"\n将删除这 {len(hits)} 条缓存，然后重新翻译。")
    if input("确认？(Y/n): ").strip().lower() == "n":
        print("已取消（快照未更新）")
        return

    # 7. 清缓存
    keys_to_remove = [k for k, _ in hits]
    removed_n = cache.remove_many(keys_to_remove)
    cache.save(force=True)
    log.info("已删除缓存：%d 条", removed_n)
    print(f"✔ 已删除 {removed_n} 条缓存")

    # 8. 更新快照
    TS.save_snapshot(current_terms)

    # 9. 开始重翻
    print("\n开始重翻…")
    cmd_translate(skip_picker=True)


# ================================================================
# 功能 5：应用前缀字典
# ================================================================
def cmd_apply_prefix_dict():
    """
    不调用模型，只重新拼接缓存里的译文 + 前缀字典里的前缀。
    用于用户翻译完前缀后立即生效。
    """
    import prefix_dict as PFD

    log.info("=" * 50)
    log.info("应用前缀字典")

    print("\n[应用前缀字典]")
    print("-" * 55)

    PFD.reload_dict()
    s = PFD.stats()
    print(f"当前字典：共 {s['total']} 条，"
          f"已翻译 {s['done']} 条，待翻译 {s['pending']} 条")

    if not os.path.exists(config.Runtime.input_file):
        print(f"缺少输入文件：{config.Runtime.input_file}")
        return
    if not os.path.exists(config.Runtime.cache_file):
        print(f"缺少缓存：{config.Runtime.cache_file}（先跑一次翻译）")
        return

    lines, newline = P.read_file(config.Runtime.input_file,
                                 config.INPUT_ENCODING)
    entries, special = P.extract_entries(lines)
    cache = Cache(config.Runtime.cache_file)

    translations = {}
    hit_prefix = 0
    miss_prefix = 0
    no_prefix = 0

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
            # 精确剔除旧前缀
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

    print(f"\n✔ 输出：{config.Runtime.output_file}")
    print(f"  替换 {replaced}/{len(entries)} 条")
    print(f"  前缀替换生效：{hit_prefix} 条；"
          f"未翻译前缀：{miss_prefix} 条；无前缀：{no_prefix} 条")
    log.info("应用前缀字典完成：%d/%d", replaced, len(entries))


# ================================================================
# 功能 4：翻译前缀字典
# ================================================================
def cmd_review_prefix_dict():
    """列出前缀字典，方便用户翻译。"""
    import prefix_dict as PFD

    PFD.reload_dict()
    s = PFD.stats()

    print("\n[前缀字典]")
    print("-" * 55)
    print(f"文件：{PFD.DICT_FILE}")
    print(f"统计：共 {s['total']} 条，"
          f"已翻译 {s['done']} 条，待翻译 {s['pending']} 条")

    pending = PFD.list_pending()
    if not pending:
        print("\n✔ 没有待翻译的前缀")
        return

    print(f"\n待翻译前缀（前 30 条）：")
    for i, (k, _) in enumerate(pending[:30], 1):
        print(f"  {i:>3}. {k}")

    if len(pending) > 30:
        print(f"  … 其余 {len(pending) - 30} 条")

    print(f"\n请编辑：{PFD.DICT_FILE}")
    print("把每个前缀的 \"\" 换成你的译文，例如：")
    print('  "\\\\w[speech hgss 3]\\\\tg[???]": '
          '"\\\\w[speech hgss 3]\\\\tg[欧文]"')

    if input("\n是否现在打开文件？(y/N): ").strip().lower() == "y":
        try:
            if os.name == "nt":
                os.startfile(PFD.DICT_FILE)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", PFD.DICT_FILE])
        except Exception as e:
            print(f"打开失败：{e}，请手动打开：{PFD.DICT_FILE}")
