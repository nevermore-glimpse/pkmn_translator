# -*- coding: utf-8 -*-
"""
把 E:\\Pokemon Essentials 下各版本的**完整官方脚本**收进
scripts/essentials_src/<ver>/，供报告页取基准函数源码。

  · v19–v21.1：直接拷 Data/Scripts/**.rb（保持相对路径）
  · v16–v18  ：从 Data/Scripts.rxdata 解包成 <title>.rb 平铺存放
"""
import os
import shutil
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = r"E:\Pokemon Essentials"
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "scripts", "essentials_src")
VERS = ["16", "17", "18", "19", "19.1", "20", "20.1", "21", "21.1"]


def pack_folder(ver, src_scripts, dst):
    n = 0
    for dp, _dn, fs in os.walk(src_scripts):
        for f in fs:
            if not f.endswith(".rb"):
                continue
            rel = os.path.relpath(os.path.join(dp, f), src_scripts)
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copyfile(os.path.join(dp, f), out)
            n += 1
    return n


def pack_rxdata(ver, rxdata, dst):
    """解包 Scripts.rxdata → 每个脚本一个 <编号>_<safe_title>.rb（平铺）。"""
    from rubymarshal.reader import load
    import re
    with open(rxdata, "rb") as f:
        scripts = load(f)
    n = 0
    for e in scripts:
        if not (isinstance(e, (list, tuple)) and len(e) >= 3):
            continue
        _id, title, data = e[0], e[1], e[2]
        if isinstance(title, bytes):
            title = title.decode("utf-8", "replace")
        try:
            code = zlib.decompress(bytes(data)).decode("utf-8", "replace")
        except Exception:
            continue
        title = str(title or "").strip()
        if not code.strip():
            continue
        safe = re.sub(r"[\\/:*?\"<>|]+", "_", title) or f"unnamed_{_id}"
        # 编号前缀保留原始下标，避免重名；func_source 会去掉编号前缀
        with open(os.path.join(dst, f"{_id:04d}_{safe}.rb"), "w",
                  encoding="utf-8", newline="") as f:
            f.write(code)
        n += 1
    return n


def main():
    for ver in VERS:
        base = os.path.join(ROOT, f"pokemon-essentials-{ver}")
        dst = os.path.join(DST, ver)
        os.makedirs(dst, exist_ok=True)
        src_scripts = os.path.join(base, "Data", "Scripts")
        rxdata = os.path.join(base, "Data", "Scripts.rxdata")
        if os.path.isdir(src_scripts):
            n = pack_folder(ver, src_scripts, dst)
            print(f"v{ver}: 拷贝 {n} 个 .rb（目录）")
        elif os.path.isfile(rxdata):
            n = pack_rxdata(ver, rxdata, dst)
            print(f"v{ver}: 解包 {n} 个脚本（rxdata）")
        else:
            print(f"v{ver}: 未找到脚本源")


if __name__ == "__main__":
    main()
