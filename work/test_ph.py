# -*- coding: utf-8 -*-
"""占位符保留逻辑的快速验证。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import processor as PR
from processor import _is_placeholder_token
from commands import _force_restore

# ① 占位符 token 识别
assert _is_placeholder_token("@0@")
assert _is_placeholder_token("@12@")
assert _is_placeholder_token("⟦3⟧")
assert not _is_placeholder_token("hello")
assert not _is_placeholder_token("@x@")
print("[1] _is_placeholder_token OK")

# ② protect -> restore 往返（源文不含字面 @数字@，避免触发分隔符切换）
src = r"\PN ha dicho algo \v[50]"
safe, maps = PR.protect(src)
assert "@0@" in safe and "@1@" in safe, safe
back = PR.restore(safe, maps)
assert back == src, (back, src)
print("[2] protect/restore roundtrip OK ->", back)

# ③ 模型丢了 @0@ 的兜底补回（保留 @1@ 作为锚点，贴近真实单处丢失）
safe2, maps2 = PR.protect(src)
# 模型把 @0@ 翻没了，但保留了 @1@（输入里不含原始控制码）
bad = "ha dicho 某事 @1@"
ok, missing = PR.verify(bad, maps2)
assert not ok and "@0@" in missing, (ok, missing)
fixed = _force_restore(bad, maps2, src=src)   # 返回 token 形态
ok2, _ = PR.verify(fixed, maps2)
assert ok2, fixed
assert "@0@" in fixed and "@1@" in fixed, fixed
final = PR.restore(fixed, maps2)              # 走 finalize 同款还原
for it in maps2:
    assert it["original"] in final, (it["original"], final)
print("[3] 占位符兜底补回 OK ->", final)

# ④ find_terms 不应把占位符当术语
PR.load_terms()
hits = PR.find_terms("@0@ @1@ 大木博士")
assert not any(k in ("@0@", "@1@") for k, _ in hits), hits
print("[4] find_terms 排除占位符 OK ->", hits)

print("\nALL PASS")
