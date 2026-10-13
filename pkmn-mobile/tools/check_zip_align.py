# -*- coding: utf-8 -*-
"""
检查 APK 里的 .so 在 **zip 内部的位置** 是否 16KB 对齐。

为什么 `check_16kb.py` 不够
-------------------------
它只读了 .so 文件**内部**的 ELF `p_align`（段对齐）。但 16KB 页设备要能
直接 mmap 压缩包里的库，还要求这个 .so 在 zip 里的**数据起始偏移**也是
16KB 的整数倍 —— 否则内核没法把它按 16KB 边界映射进去。

两个条件缺一不可：
    ① ELF 的 p_align ≥ 0x4000     （check_16kb.py 查这个）
    ② zip 内数据偏移 % 16384 == 0（这个脚本查这个）

只满足 ① 的 APK 依然会在 16KB 页设备上打不开，而报错和普通崩溃一模一样。

用法：
    python tools/check_zip_align.py
    python tools/check_zip_align.py 路径/到/某个.apk
"""
import glob
import os
import struct
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_APK = os.path.join(
    ROOT, "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk")

PAGE = 16384


def zip_data_offset(zf, info, raw_file):
    """
    算出这个条目在 zip 里的**数据起始偏移**。

    ★ 不能用 `zf.open(info)`：它返回的流已经定位到数据区开头了，
      读出来的是 .so 的内容、不是文件头。这里直接按 header_offset
      去原始字节里读。

    zip 本地文件头结构：
        signature 4B │ version 2B │ flags 2B │ method 2B │ time 2B │ date 2B
        │ crc32 4B │ compressed 4B │ uncompressed 4B
        │ name_len 2B │ extra_len 2B │ name │ extra │ data...
    所以 data 偏移 = header_offset + 30 + name_len + extra_len
    """
    raw_file.seek(info.header_offset)
    head = raw_file.read(30)
    if len(head) < 30 or head[:4] != b"PK\x03\x04":
        return None
    name_len, extra_len = struct.unpack_from("<HH", head, 26)
    return info.header_offset + 30 + name_len + extra_len


def elf_max_align(data):
    """读 .so 内部最大的 PT_LOAD 对齐值。"""
    if data[:4] != b"\x7fELF":
        return None
    is64 = data[4] == 2
    e_phoff = struct.unpack_from("<Q", data, 0x20)[0] if is64 else \
        struct.unpack_from("<I", data, 0x1C)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x36 if is64 else 0x2A)[0]
    e_phnum = struct.unpack_from("<H", data, 0x38 if is64 else 0x2C)[0]
    mx = 0
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if off + 4 > len(data):
            break
        if struct.unpack_from("<I", data, off)[0] != 1:      # PT_LOAD
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
            print("✘ 找不到 APK，先构建一次。")
            return 2
        apk = cands[0]

    print(f"APK：{apk}")
    print(f"大小：{os.path.getsize(apk) / 1048576:.1f} MB\n")

    zf = zipfile.ZipFile(apk)
    with open(apk, "rb") as raw:
        infos = [i for i in zf.infolist() if i.filename.endswith(".so")]
        if not infos:
            print("⚠ 没有 .so")
            return 2

        # 只有 lib/ 下的会被系统直接从 APK 加载；assets 里的是运行时解包出来的
        native = [i for i in infos if i.filename.startswith("lib/")]
        assets_so = [i for i in infos if i.filename.startswith("assets/")]

        problems = []
        print("── lib/ 下的原生库（系统直接从 APK 加载，要求 zip 偏移也 16KB 对齐）──")
        for i in sorted(native, key=lambda x: x.filename):
            raw.seek(i.header_offset)
            head = raw.read(30)
            name_len, extra_len = struct.unpack_from("<HH", head, 26)
            doff = i.header_offset + 30 + name_len + extra_len

            ealign = elf_max_align(zf.read(i))
            stored = (i.compress_type == zipfile.ZIP_STORED)
            ok_off = doff % PAGE == 0
            ok_elf = ealign is not None and ealign >= PAGE

            if not stored:
                note = "压缩(偏移不适用)"
                mark = "·"
            elif ok_off:
                note = f"偏移 {doff} ✔"
                mark = "✔"
            else:
                note = f"偏移 {doff} ✘"
                mark = "✘"
                problems.append((i.filename, doff))

            e = f"{ealign:#x}" if ealign else "?"
            print(f"  {mark} elf={e:>9}  {note:18} {i.filename}")

        if assets_so:
            print(f"\n── assets/ 下的 .so（共 {len(assets_so)} 个，运行时解包）──")
            bad_elf = 0
            for i in assets_so:
                ealign = elf_max_align(zf.read(i))
                if not (ealign and ealign >= PAGE):
                    bad_elf += 1
                    print(f"  ✘ elf={ealign:#x}  {i.filename}")
            if not bad_elf:
                print(f"  ✔ 全部 {len(assets_so)} 个 ELF 段都是 16KB 对齐")
                print("     （这些会解到应用私有目录，zip 内偏移不影响加载）")

    print()
    if problems:
        print(f"✘ {len(problems)} 个原生库在 APK 里的位置没按 16KB 对齐 ——")
        print("  这正是「ELF 内部对齐了、装到 16KB 页设备上仍然打不开」的原因。")
        print()
        print("修复：确认 app/build.gradle 里有")
        print("    packaging { jniLibs { useLegacyPackaging false } }")
        print("并使用 AGP ≥ 8.5.1（更早的版本直接忽略这个开关）。")
        return 1

    print("✔ zip 内偏移与 ELF 段对齐都合格。")
    if problems:
        return 1
    print("  若仍打不开，说明问题不在 16KB，请提供 logcat：")
    print("    adb logcat -s PkmnTools:V AndroidRuntime:E Chaquopy:V")
    return 0


if __name__ == "__main__":
    sys.exit(main())