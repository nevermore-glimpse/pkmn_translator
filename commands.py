# -*- coding: utf-8 -*-
"""三个核心功能的实现：翻译 / 检查 / Excel 转术语表。"""
import json
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
# 占位符兜底
# ================================================================
def _force_restore(raw, maps):
    result = PR.restore(raw, maps)
    _, missing = PR.verify(result, maps)
    for token in missing:
        result = result.rstrip() + " " + token
    return result


# ================================================================
# 功能 1：翻译
# ================================================================
def cmd_translate():
    import filepicker

    log.info("=" * 50)
    log.info("开始翻译")

    # ---------- 选定输入文件 ----------
    src_path = config.Runtime.input_file

    if not os.path.exists(src_path):
        print(f"\n默认输入文件不存在：{src_path}")
        picked = filepicker.pick_text_file(
            initial_dir=config.BASE_DIR,
            title="选择要翻译的文本文件",
        )
        if not picked:
            print("已取消")
            return
        config.Runtime.set_input(picked)
        src_path = config.Runtime.input_file

    print(f"\n输入文件：{src_path}")
    print(f"输出文件：{config.Runtime.output_file}")
    print(f"缓存文件：{config.Runtime.cache_file}")

    if input("是否另选文件？(y/N): ").strip().lower() == "y":
        picked = filepicker.pick_text_file(
            initial_dir=os.path.dirname(src_path),
            title="选择文本文件",
        )
        if picked:
            config.Runtime.set_input(picked)
            src_path = config.Runtime.input_file
            print(f"已切换 → {src_path}")
            print(f"   输出：{config.Runtime.output_file}")
            print(f"   缓存：{config.Runtime.cache_file}")

    if not os.path.exists(src_path):
        print(f"文件不存在：{src_path}")
        return

    log.info("输入=%s", src_path)
    log.info("输出=%s", config.Runtime.output_file)

    # ---------- 加载术语表 ----------
    PR.load_terms()

    # ---------- 解析 ----------
    lines, newline = P.read_file(src_path, config.INPUT_ENCODING)
    entries, special = P.extract_entries(lines)
    log.info("文件 %d 行  待翻 %d  特殊 %d",
             len(lines), len(entries), len(special))
    print(f"[解析] 总行数 {len(lines)}  待翻 {len(entries)}  特殊 {len(special)}")

    if not entries:
        print("没有可翻译的内容")
        return

    # ---------- 缓存 ----------
    cache = Cache(config.Runtime.cache_file)

    seen, todo = set(), []
    for _, txt in entries:
        if txt in seen:
            continue
        seen.add(txt)
        if txt in cache:
            continue
        todo.append(txt)

    log.info("唯一 %d  需翻 %d  缓存命中 %d",
             len(seen), len(todo), len(seen) - len(todo))
    print(f"[待翻] 唯一 {len(seen)}  需翻 {len(todo)}  缓存命中 {len(seen) - len(todo)}")

    # ---------- 批量翻译 ----------
    if todo:
        client = OllamaClient()
        done, failed = 0, []
        t0 = time.time()
        total = len(todo)

        for start in range(0, total, config.BATCH_SIZE):
            bi = start // config.BATCH_SIZE + 1
            batch_texts = todo[start:start + config.BATCH_SIZE]

            batch, maps_dict = [], {}
            for k, txt in enumerate(batch_texts):
                safe, maps = PR.prepare(txt)
                batch.append((k, safe))
                maps_dict[k] = maps

            log.info("[批 %d] 开始  %d 条", bi, len(batch))
            for k, txt in enumerate(batch_texts):
                log.debug("[批 %d][%d] 原文=%r", bi, k, txt)
                log.debug("[批 %d][%d] 送模型=%r", bi, k, batch[k][1])

            result = translate_with_retry(client, batch)

            # 整批缺行 → 单条重试
            missing = [(k, t) for k, t in batch
                       if k not in result or not result[k].strip()]
            if missing:
                log.warning("[批 %d] 缺失 %d 条，单条重试", bi, len(missing))
            for k, safe in missing:
                for attempt in range(config.SINGLE_RETRIES):
                    try:
                        r = translate_with_retry(client, [(k, safe)])
                        if k in r and r[k].strip():
                            result[k] = r[k]
                            break
                    except Exception as e:
                        log.debug("[批 %d][%d] 单条重试 %d 失败：%s",
                                  bi, k, attempt + 1, e)
                        time.sleep(1.5)

            ok = 0
            for k, src in enumerate(batch_texts):
                raw = result.get(k)
                if not raw:
                    log.warning("[批 %d][%d] 无返回：%r", bi, k, src)
                    failed.append(src)
                    continue

                log.debug("[批 %d][%d] 模型原文=%r", bi, k, raw)
                maps = maps_dict[k]

                # 占位符校验
                ok_ph, missing_ph = PR.verify(raw, maps)
                if not ok_ph:
                    log.warning("[批 %d][%d] 占位符丢失 %s，原文=%r",
                                bi, k, missing_ph, src)
                    retried = False
                    for _ in range(config.SINGLE_RETRIES):
                        try:
                            r = translate_with_retry(client, [(k, batch[k][1])])
                            if k in r and r[k].strip():
                                ok3, _ = PR.verify(r[k], maps)
                                if ok3:
                                    raw = r[k]
                                    retried = True
                                    break
                        except Exception:
                            time.sleep(1.0)
                    if not retried:
                        raw = _force_restore(raw, maps)
                        log.info("[批 %d][%d] 占位符兜底补回", bi, k)

                    ok_final, _ = PR.verify(raw, maps)
                    if not ok_final:
                        log.error("[批 %d][%d] 占位符仍失败，保留原文", bi, k)
                        failed.append(src)
                        continue

                final = PR.finalize(raw, maps)
                log.debug("[批 %d][%d] 最终译文=%r", bi, k, final)
                cache.put(src, final)
                ok += 1

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
                print(f"    {t[:70]}")
            if len(failed) > 10:
                print(f"    … 其余 {len(failed) - 10} 条省略")

    # ---------- 回写 ----------
    translations = {txt: cache.get(txt) for _, txt in entries if cache.get(txt)}
    replaced = P.write_output(
        lines, entries, translations,
        config.Runtime.output_file, newline, config.OUTPUT_ENCODING,
    )
    log.info("回写：%d/%d → %s",
             replaced, len(entries), config.Runtime.output_file)
    print(f"\n✔ 输出：{config.Runtime.output_file}")
    print(f"  替换 {replaced}/{len(entries)} 条")

    # ---------- 自动检查 ----------
    print("\n[检查] 生成检查报告…")
    try:
        out_lines, _ = P.read_file(config.Runtime.output_file,
                                   config.OUTPUT_ENCODING)
        hits = checker.check(lines, out_lines, entries, special,
                             config.CHECK_REPORT)
        _print_summary(hits, config.CHECK_REPORT)
    except Exception as e:
        log.error("自动检查失败：%s", e)
        print(f"  自动检查失败（不影响翻译结果）：{e}")


# ================================================================
# 功能 2：检查
# ================================================================
def cmd_check():
    log.info("=" * 50)
    log.info("检查  %s", config.Runtime.output_file)

    if not os.path.exists(config.Runtime.input_file):
        print(f"缺少输入文件：{config.Runtime.input_file}")
        return
    if not os.path.exists(config.Runtime.output_file):
        print(f"缺少输出文件：{config.Runtime.output_file}（先跑一次翻译）")
        return

    src_lines, _ = P.read_file(config.Runtime.input_file, config.INPUT_ENCODING)
    out_lines, _ = P.read_file(config.Runtime.output_file, config.OUTPUT_ENCODING)
    entries, special = P.extract_entries(src_lines)
    log.info("待检查 %d 条  特殊 %d 条", len(entries), len(special))

    hits = checker.check(src_lines, out_lines, entries, special,
                         config.CHECK_REPORT)
    _print_summary(hits, config.CHECK_REPORT)


def _print_summary(hits, report_path):
    from collections import Counter
    c = Counter(h['kind'] for h in hits)
    print(f"  共 {len(hits)} 处问题：")
    for k in ('未翻译', '疑似未翻译', '符号不匹配', '特殊行'):
        if c.get(k):
            print(f"    {k}: {c[k]}")
    print(f"  报告：{report_path}")


# ================================================================
# 功能 3：Excel 转术语表
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

    # ---------- 选 Excel 文件 ----------
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

    # ---------- 选语言 ----------
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

    # ---------- 选工作表 ----------
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

    # ---------- 输出路径 ----------
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
# 功能 4：切换输入文件
# ================================================================
def cmd_switch_file():
    """切换输入文件，自动派生输出 / 缓存路径。"""
    import filepicker

    print(f"\n当前输入：{config.Runtime.input_file}")

    picked = filepicker.pick_text_file(
        initial_dir=os.path.dirname(config.Runtime.input_file),
        title="选择文本文件",
    )
    if not picked:
        print("已取消")
        return

    config.Runtime.set_input(picked)
    log.info("切换输入：%s", picked)

    # 可选持久化
    try:
        config.Runtime.save()
    except Exception:
        pass

    print(f"\n✔ 已切换：")
    print(f"   输入：{config.Runtime.input_file}")
    print(f"   输出：{config.Runtime.output_file}")
    print(f"   缓存：{config.Runtime.cache_file}")


# ================================================================
# 兼容：老菜单若还引用这些函数名
# ================================================================
def cmd_preview():
    cmd_check()


def cmd_cache_stats():
    cache = Cache(config.Runtime.cache_file)
    print(f"\n[缓存] {config.Runtime.cache_file}")
    print(f"        条目：{len(cache)}")