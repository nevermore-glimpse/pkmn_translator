# -*- coding: utf-8 -*-
"""改动后的冒烟测试：术语表 / 解析器 / 保护还原 / 检查报告 / 前缀字典。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import parser as P
import processor as PR
import prefix_dict as PFD
import term_sync as TS
import checker

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "examples", "intl.txt")


def main():
    print("=" * 60)
    print("1) 术语表加载")
    t0 = time.time()
    PR.load_terms()
    t1 = time.time()
    print(f"   加载耗时 {t1 - t0:.3f}s   共 {len(PR._TERMS)} 条")
    print(f"   单词类 {len(PR._TERM_SINGLE)} / 多词类 {len(PR._TERM_MULTI)}")
    print(f"   _MULTI_RE = {bool(PR._MULTI_RE)}")

    t0 = time.time()
    PR.load_terms()          # 第二次应命中缓存
    print(f"   二次加载耗时 {time.time() - t0:.4f}s（应接近 0）")

    sample = "\\w[1]<ar>¡Hola, Owen! Enfermera Joy y el Profesor Oak en Ciudad Lavanda."
    t0 = time.time()
    for _ in range(200):
        hits = PR.find_terms(sample)
    t1 = time.time()
    print(f"   find_terms x200 耗时 {t1 - t0:.3f}s  命中 {hits}")

    out = PR.apply_terms(sample)
    print(f"   apply_terms → {out}")

    print("=" * 60)
    print("2) 解析")
    lines, nl = P.read_file(SRC, config.INPUT_ENCODING)
    entries, special = P.extract_entries(lines)
    print(f"   行数 {len(lines)}  待翻 {len(entries)}  特殊 {len(special)}  换行符 {nl!r}")

    print("=" * 60)
    print("3) 保护 / 还原 往返")
    bad = 0
    for ln, txt in entries[:300]:
        safe, maps, breaks, ht = PR.prepare(txt)
        back = PR.restore(safe, maps)
        if back != txt.replace("\\n", ""):
            bad += 1
            if bad <= 3:
                print(f"   [差异] {txt!r}\n        → {back!r}")
    print(f"   往返不一致 {bad} / {min(300, len(entries))}")

    print("=" * 60)
    print("4) 保留 \\n 的保护（润色用）")
    s = "你好！\\n你怎么样？\\N再见 @0@"
    safe, maps = PR.protect(s, drop_newline=False)
    print(f"   safe={safe!r}  maps={[m['original'] for m in maps]}")
    print(f"   restore={PR.restore(safe, maps)!r}")

    print("=" * 60)
    print("5) 前缀字典")
    PFD.reload_dict()
    st = PFD.stats()
    print(f"   共 {st['total']} 条  已译 {st['done']}  待译 {st['pending']}")
    p, b = PR.split_prefix("\\w[speech hgss 3]\\tg[Alba]Hola")
    print(f"   split_prefix → prefix={p!r} body={b!r}")
    print(f"   apply_prefix → {PFD.apply_prefix(p)!r}")

    print("=" * 60)
    print("6) 术语快照")
    cur = TS.load_current_terms()
    print(f"   当前术语 {len(cur)} 条  快照存在 {TS.snapshot_exists()}")
    auto = TS.load_auto_block()
    print(f"   AUTO 块 {len(auto)} 条：{auto[:3]}")
    added, removed, modified, keyonly = TS.diff_terms()
    print(f"   新增 {len(added or [])}  删除 {len(removed or [])}  "
          f"修改 {len(modified or [])}")

    print("=" * 60)
    print("7) 检查报告（输出到临时文件）")
    out_path = os.path.join(BASE, "work", "_smoke_out.txt")
    cache_like = {}
    translations = {}
    for ln, txt in entries[:50]:
        translations[txt] = txt
    replaced = P.write_output(lines, entries[:50], translations, out_path, nl,
                              config.OUTPUT_ENCODING)
    out_lines, _ = P.read_file(out_path, config.OUTPUT_ENCODING)
    rp = os.path.join(BASE, "work", "_smoke_report.txt")
    hits = checker.check(lines, out_lines, entries, special, rp)
    print(f"   回写 {replaced} 条  hits {len(hits)}  → {rp}")
    os.remove(out_path)

    print("=" * 60)
    print("全部冒烟检查完成")


if __name__ == "__main__":
    main()
