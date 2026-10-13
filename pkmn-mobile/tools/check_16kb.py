# -*- coding: utf-8 -*-
"""
检查 APK 里的原生库是不是 16KB 页对齐。

为什么需要它
------------
Android 15 起支持 16KB 内存页（比 4KB 快 5~10%），但这类设备**跑不了**
按 4KB 对齐编译的 .so —— 表现是「点开 App 就闪退」，报错还莫名其妙：

    dlopen failed: unset DT_HASH/DT_GNU_HASH in libpython3.11.so

三个条件缺一不可（细节见 README）：
    · Python 3.13+       3.12 及更早的官方 wheels 是 4KB 对齐
    · Chaquopy 17        16.x 只把两个 stub 改成 16KB
    · useLegacyPackaging false   不压缩 .so，AGP 才做页面对齐

用法：
    python tools/check_16kb.py
    python tools/check_16kb.py 路径/到/某个.apk
"""
import glob
import os
import struct
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_APK = os.path.join(
    ROOT, "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk")

PAGE_16K = 0x4000          # = 16384。ELF 里写的是「对齐值」不是字节数，
                            #   所以 16KB 页对齐的库这里是 0x4000（不是 0x10000）。


def load_align(data):
    """返回该 .so 的最大 PT_LOAD 对齐值（读不出返回 None）。"""
    if data[:4] != b"\x7fELF":
        return None
    is64 = data[4] == 2
    if is64:
        e_phoff = struct.unpack_from("<Q", data, 0x20)[0]
    else:
        e_phoff = struct.unpack_from("<I", data, 0x1C)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x2A if not is64 else 0x36)[0]
    e_phnum = struct.unpack_from("<H", data, 0x2C if not is64 else 0x38)[0]
    mx = 0
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if off + 4 > len(data):
            break
        p_type = struct.unpack_from("<I", data, off)[0]
        if p_type != 1:            # PT_LOAD
            continue
        a = (struct.unpack_from("<Q", data, off + 0x30)[0] if is64
             else struct.unpack_from("<I", data, off + 0x1C)[0])
        mx = max(mx, a)
    return mx or None


def main():
    apk = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_APK
    if not os.path.isfile(apk):
        cands = glob.glob(os.path.join(
            ROOT, "android", "app", "build", "outputs", "apk", "*", "*.apk"))
        if not cands:
            print("✘ 找不到 APK。先构建一次：cd android && gradlew assembleDebug")
            return 2
        apk = cands[0]

    size = os.path.getsize(apk) / 1024 / 1024
    print(f"APK：{apk}")
    print(f"大小：{size:.1f} MB\n")

    z = zipfile.ZipFile(apk)
    names = [n for n in z.namelist() if n.endswith(".so")]

    if not names:
        print("⚠ APK 里没有 .so —— 这不正常，检查一下打包配置")
        return 2

    bad, ok, skipped = [], 0, 0
    for n in sorted(names):
        a = load_align(z.read(n))
        if a is None:
            skipped += 1
            continue
        if a >= PAGE_16K:
            ok += 1
            flag = "OK"
        else:
            bad.append((n, a))
            flag = "!!"
        print(f"  {flag}  align={a:#08x}  {n}")

    print()
    print(f"16KB 兼容：{ok}　不兼容：{len(bad)}　读不出：{skipped}")

    if bad:
        print("\n✘ 这些库在 16KB 页设备上会加载失败（Android 15/16 打不开）：")
        for n, a in bad:
            print(f"    {n}  (align={a:#x})")
        print("\n排查顺序：")
        print("  1. python { version '3.13' }        —— 别用 3.12 及更早")
        print("  2. Chaquopy 17.0.0                  —— 16.x 不够")
        print("  3. jniLibs { useLegacyPackaging false }")
        print("  4. AGP ≥ 8.5.1（更早的会忽略上面第 3 条）")
        return 1

    print("\n✔ 全部 16KB 页对齐，Android 15/16 上能正常加载原生库。")
    return 0


if __name__ == "__main__":
    sys.exit(main())