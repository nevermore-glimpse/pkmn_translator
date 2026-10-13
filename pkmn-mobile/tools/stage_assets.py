# -*- coding: utf-8 -*-
"""
把工程里的源码与资源复制进 APK 的打包目录。

    web/      → android/app/src/main/assets/web/
    core/     → android/app/src/main/python/core/
    shim/     → android/app/src/main/python/shim/
    server/   → android/app/src/main/python/server/
    vendor/   → android/app/src/main/python/vendor/
    bootstrap.py + mobile_main.py → android/app/src/main/python/
    core_data/ → android/app/src/main/assets/core_data/

★ **手动运行**，不参与 Gradle 构建。想更新内容就重跑一次再打包。

    python tools/stage_assets.py

为什么要这一步
------------
Gradle 的 `preBuild` 钩子也能做同样的事，但那是**每次打包都自动执行**：
改了网页却忘了同步，手机上看到的还是旧版 —— 而且会覆盖你在打包目录里
做的临时调整。改成手动之后，你明确知道打进 APK 的是哪一份。

跑完可以放心直接 `gradlew assembleDebug`。
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANDROID = os.path.join(ROOT, "android", "app", "src", "main")
ASSETS = os.path.join(ANDROID, "assets")
PYTHON_DIR = os.path.join(ANDROID, "python")

# (源目录/文件, 目标目录, 是否为目录)
JOBS = [
    ("web", "assets/web", True),
    ("core_data", "assets/core_data", True),
    ("core", "python/core", True),
    ("shim", "python/shim", True),
    ("server", "python/server", True),
    ("vendor", "python/vendor", True),
    ("bootstrap.py", "python/bootstrap.py", False),
    ("mobile_main.py", "python/mobile_main.py", False),
]

SKIP_NAMES = {"__pycache__", ".pyc", ".pyo", ".git"}


def _clean(dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    elif os.path.isfile(dst):
        os.remove(dst)


def _ignore(_dir, names):
    return [n for n in names if n in SKIP_NAMES or n.endswith(".pyc")]


def copy_one(src, dst_rel, is_dir):
    src = os.path.join(ROOT, src)
    dst = os.path.join(ANDROID, dst_rel)
    if not os.path.exists(src):
        print(f"  ⚠ 跳过（不存在）：{src}")
        return False
    _clean(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if is_dir:
        shutil.copytree(src, dst, ignore=_ignore)
        n = sum(len(f) for _, _, f in os.walk(dst))
    else:
        shutil.copyfile(src, dst)
        n = 1
    size = sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(dst) for f in fs)
    print(f"  ✔ {dst_rel:28} {n:4} 个文件  {size / 1024:8.0f} KB")
    return True


def main():
    print("同步打包资源（手动）：")
    ok = 0
    for src, dst, is_dir in JOBS:
        if copy_one(src, dst, is_dir):
            ok += 1

    # 清理 python 目录里上轮残留、但这次没同步的模块
    for stale in ("core", "shim", "server", "vendor"):
        p = os.path.join(PYTHON_DIR, stale)
        if os.path.isdir(p) and not any(s == stale for s, _, _ in JOBS):
            shutil.rmtree(p, ignore_errors=True)

    print(f"完成，{ok}/{len(JOBS)} 项。")
    if ok < len(JOBS):
        print("有项目缺失，请检查上面的提示。")
        return 1
    print("现在可以执行：cd android && gradlew assembleDebug")
    return 0


if __name__ == "__main__":
    sys.exit(main())