# -*- coding: utf-8 -*-
"""端到端：翻译 → 中文润色 → 检查 → 应用前缀字典（走真实 Ollama）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import bridge
import commands
import parser as P

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "work", "_e2e_in.txt")


def make_sample(n=90):
    src = os.path.join(BASE, "examples", "intl.txt")
    lines, nl = P.read_file(src, config.INPUT_ENCODING)
    sub = lines[:n]
    with open(SRC, "w", encoding="utf-8-sig") as f:
        f.write(nl.join(sub))
    return sub, nl


def main():
    sub, nl = make_sample()
    config.Runtime.set_input(SRC)
    print("输入：", SRC)
    print("输出：", config.Runtime.output_file)
    print("缓存：", config.Runtime.cache_file)

    print("\n===== 1. 翻译 =====")
    t0 = time.time()
    r = commands.translate_paths([SRC])
    print("结果：", r, f"  耗时 {time.time() - t0:.1f}s")

    print("\n===== 2. 中文润色 =====")
    t0 = time.time()
    r2 = commands.polish_paths([SRC])
    print("结果：", r2, f"  耗时 {time.time() - t0:.1f}s")

    print("\n===== 3. 检查 =====")
    hits = commands.check_file(SRC)
    print("命中问题：", len(hits or []))
    for h in (hits or [])[:5]:
        print("   ", h["kind"], "|", h["src"][:40], "→", h["dst"][:40])

    print("\n===== 4. 应用前缀字典 =====")
    r4 = commands.apply_prefix_dict_paths([SRC])
    print("结果：", r4)

    print("\n===== 5. 重翻检查报告 =====")
    r5 = commands.retranslate_report_paths([SRC])
    print("结果：", r5)

    print("\n===== 6. 术语更新后重翻 =====")
    r6 = commands.retranslate_terms_paths([SRC])
    print("结果：", r6)

    print("\n===== 输出前 8 行 =====")
    out_lines, _ = P.read_file(config.Runtime.output_file,
                               config.OUTPUT_ENCODING)
    for line in out_lines[:8]:
        print("   ", line[:90])


if __name__ == "__main__":
    main()
