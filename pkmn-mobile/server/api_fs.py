# -*- coding: utf-8 -*-
"""
文件系统接口 —— 手机上没有 tkinter 的「选择文件夹」对话框（filepicker.py 依赖
tkinter），所以目录浏览和文件选取改由前端完成，这里提供后端能力。

★ 这是电脑上 `filepicker.py` 在移动端的等价替换，但**没有改动任何原文件**：
  电脑上照旧弹对话框，手机上由 WebView 提供这份接口。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bootstrap  # noqa: E402,F401

# 兄弟模块：按「自己是怎么被导入的」二选一（详见 server/app.py 的说明）
if __package__:
    from . import jsonutil as JU     # noqa: E402
else:
    import jsonutil as JU            # noqa: E402

# 可选沙箱：如果设了 PKMN_FS_ROOT，则禁止访问它以外的路径
_FS_ROOT = os.environ.get("PKMN_FS_ROOT") or None

_SAVE_EXT = {".rxdata", ".dat", ".sav", ".bin"}
# 游戏主程序 / 启动脚本：手机版「选游戏主程序」用它高亮
_EXE_EXT = {".exe", ".sh", ".app", ".bat", ".command"}


# ================================================================
# 「从哪里开始浏览」—— 安卓上这是必须的
# ================================================================
# 手机没有「我的电脑」这一层。而进程的当前目录是 "/"，
# `os.listdir("/")` 会被 SELinux 拒绝 → PermissionError →
# 前端只能弹一句「没有读取权限」，用户完全不知道该往哪走
# （v1.5 的真实反馈就是这个）。
#
# 所以空路径时不再去列 "/"，而是给一组**确定可用**的起点。
_ANDROID_ROOTS = [
    ("/storage/emulated/0", "内部存储"),
    ("/storage/emulated/0/Android/data", "游戏数据（Android/data）"),
    ("/storage/emulated/0/Android/media", "游戏媒体（Android/media）"),
    ("/storage/emulated/0/Download", "下载"),
    ("/storage/emulated/0/Documents", "文档"),
    ("/storage/emulated/0/Games", "Games"),
    ("/storage", "存储设备（含外置 SD 卡）"),
]


def _is_android():
    """
    是不是跑在安卓上。

    <p>`PKMN_FORCE_ANDROID` 是给本地测试用的 —— 否则
    `tools/test_mobile_boot.py` 在电脑上永远测不到这条分支
    （同一个函数在两种平台走不同的路，正是前面几轮翻车的原因）。
    """
    if os.environ.get("PKMN_FORCE_ANDROID"):
        return True
    return ("ANDROID_ARGUMENT" in os.environ
            or hasattr(sys, "getandroidapilevel"))


def _roots_payload():
    """
    安卓上的「起点列表」。

    <p>顺带把外置 SD 卡（/storage/XXXX-XXXX）也列出来 —— 不少人的游戏
    装在存储卡上。用 realpath 去重，避免 /sdcard 与 /storage/emulated/0
    这种同一个地方出现两次。
    """
    dirs, seen = [], set()

    def add(path, label):
        try:
            if not os.path.isdir(path):
                return
            real = os.path.realpath(path)
        except OSError:
            return
        if real in seen:
            return
        seen.add(real)
        dirs.append({"name": label, "path": path, "dir": True})

    for path, label in _ANDROID_ROOTS:
        add(path, label)

    # 外置存储卡：/storage/<UUID 之类>
    try:
        for n in sorted(os.listdir("/storage")):
            if n in ("emulated", "self"):
                continue
            add("/storage/" + n, n + "（外置存储）")
    except OSError:
        pass

    return {"cwd": "", "parent": None, "dirs": dirs, "files": [],
            "roots": True,
            "hint": "手机没有「我的电脑」这一层。游戏一般在 "
                    "内部存储 / Android/data/<游戏包名>/ 下；"
                    "也可以直接在输入框里手打路径。"}


def _looks_like_game(d, names):
    """
    当前目录像不像游戏根目录（有 Data/ 和某个 .exe / .app）。

    <p>只看**已经列出来的** names，不额外 listdir 子目录 ——
    否则在大目录（比如内部存储根）上会明显卡顿。
    """
    if not d:
        return False
    lower = {n.lower() for n in names}
    has_data = "data" in lower
    has_exe = any(n.endswith((".exe", ".app", ".sh")) for n in names)
    return has_data and has_exe


def _guard(path):
    """返回 None 表示放行，否则返回错误信息。"""
    if not path:
        return "缺少参数 path"
    if _FS_ROOT:
        root = JU.normalize_path(_FS_ROOT).replace("\\", "/").rstrip("/")
        p = JU.normalize_path(path).replace("\\", "/")
        if not (p == root or p.startswith(root + "/")):
            return f"超出允许范围：{root}"
    return None


def api_list(ctx):
    raw = ctx["query"].get("dir") or ""
    d = JU.normalize_path(raw) or ""

    # ★★ 这一行是「没有读取权限」的真正根因，别删：
    #    os.path.normpath("") 返回的是 **"."**，所以「没传目录」到了这里
    #    会变成一个合法的相对路径 "."，下面 `if not d` 判断不出来 ——
    #    于是安卓上去列进程的当前目录，而那是 "/"，
    #    SELinux 不许 listdir → PermissionError → 前端只弹一句
    #    「没有读取权限」，用户完全不知道该往哪走。
    if d == ".":
        d = ""

    bad = _guard(d or (_FS_ROOT or "/"))
    if bad:
        return JU.err(bad)

    # 空路径在安卓上不是「列当前目录」，而是「给一组可用起点」。
    # 见 _ANDROID_ROOTS 上面的说明。
    if not d and _is_android():
        return JU.ok(_roots_payload())

    if d and not os.path.isdir(d):
        return JU.err(f"目录不存在：{d}")

    try:
        names = sorted(os.listdir(d or "."))
    except PermissionError:
        # 兜底：从根一路点上来也会到 "/"，那时把起点列表再给一次，
        # 而不是甩一句看不懂的报错。
        if d in ("", ".", "/"):
            return JU.ok(_roots_payload())
        return JU.err(
            f"没有读取权限：{d}\n"
            "· 这是系统限制，不是 App 没授权 —— 根目录 / 和其它应用的私有目录"
            "本来就列不了。\n"
            "· 游戏一般装在「内部存储 / Android/data/<游戏包名>/」下面。")
    except OSError as e:
        return JU.err(e)

    dirs, files = [], []
    for n in names:
        full = os.path.join(d, n) if d else n
        try:
            isdir = os.path.isdir(full)
        except OSError:
            continue
        item = {"name": n, "path": full.replace("\\", "/"), "dir": isdir}
        if isdir:
            dirs.append(item)
        else:
            try:
                item["size"] = os.path.getsize(full)
            except OSError:
                item["size"] = None
            ext = os.path.splitext(n)[1].lower()
            item["looks_like_save"] = ext in _SAVE_EXT
            item["looks_like_exe"] = ext in _EXE_EXT
            files.append(item)

    parent = os.path.dirname(d.rstrip("/")) if d else None
    return JU.ok({
        "cwd": d,
        "parent": parent.replace("\\", "/") if parent else None,
        "dirs": dirs,
        "files": files,
        # 让前端能提示「这个目录看起来就是游戏根目录」
        "looks_like_game": _looks_like_game(d, names),
    })


def api_stat(ctx):
    path = JU.normalize_path(ctx["query"].get("path"))
    bad = _guard(path)
    if bad:
        return JU.err(bad)
    if not path or not os.path.exists(path):
        return JU.err(f"路径不存在：{path}")
    st = os.stat(path)
    return JU.ok({
        "path": path.replace("\\", "/"),
        "is_dir": os.path.isdir(path),
        "size": st.st_size,
        "mtime": st.st_mtime,
        "exists": True,
    })


def api_check_game(ctx):
    """复用 core 的校验逻辑，判断选中的是不是游戏根目录。

    ★ 两种入口都支持（手机版主用 exe）：
      · `dir=`  —— 直接给游戏根目录（老用法，保留）；
      · `exe=`  —— 给**游戏主程序（Game.exe）**，由它推出根目录
        （`game_scripts.exe_root`），再用 `verify_game` 校验。
    返回里带上 `dir` / `exe`，前端拿它当「解析出来的游戏根目录」。
    """
    q = ctx["query"]
    exe = JU.normalize_path(q.get("exe"))
    path = JU.normalize_path(q.get("dir")) or ""
    try:
        import game_scripts as GS
    except Exception as e:                                  # noqa: BLE001
        return JU.err(f"核心模块不可用：{e}")

    if exe:
        if not os.path.isfile(exe):
            return JU.err(f"这个文件不存在：{exe}")
        root, exe_name = GS.exe_root(exe)
        if not root:
            return JU.err(f"没法从「{os.path.basename(exe)}」推出游戏目录")
        # 校验交给 core 的统一入口（与电脑版一致：exe 所在目录即游戏根目录，
        # 旁边必须有 Data/）。选到 ...\Data\Game.exe 这类内层时它会给提示。
        ok_, why, norm, exe_path, has_data = GS.verify_game(root, exe=exe)
        return JU.ok({
            "valid": bool(ok_ and has_data), "reason": why,
            "dir": (norm or root).replace("\\", "/"),
            "exe": (exe_path or exe).replace("\\", "/"),
            "exe_name": os.path.basename(exe_path or exe),
            "has_data": bool(has_data), "from_exe": True,
        })

    if not path:
        return JU.err("缺少参数 dir 或 exe")
    ok_, why = GS.check_game_root(path)
    return JU.ok({"valid": ok_, "reason": why, "dir": path.replace("\\", "/"),
                  "exe": None, "from_exe": False})


# ================================================================
# 诊断文件（配合 android/.../Diagnostics.java）
# ================================================================
# 安卓侧把崩溃现场写到 <App私有目录>/diagnostics.txt，
# 这两个接口给「关于」页的「复制诊断报告」按钮用。
#
# 只允许访问这两个固定文件名，不接受任意路径 —— 免得变成任意文件读写。
_DIAG_FILES = {"diagnostics.txt", "crash.log"}


def _diag_path(name):
    """把文件名解析到 App 私有目录，越界一律拒绝。"""
    import config
    name = os.path.basename(name or "")
    if name not in _DIAG_FILES:
        return None
    return os.path.join(getattr(config, "HOME_DIR", "."), name)


def api_read(ctx):
    """读诊断报告。文件不存在不算错 —— 返回空文本，前端会给出替代提示。"""
    path = _diag_path(ctx["query"].get("path"))
    if not path:
        return JU.err("只允许读取 diagnostics.txt / crash.log")
    text = ""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            return JU.err(str(e))
    return JU.ok({"path": path.replace("\\", "/"), "text": text})


def api_write(ctx):
    """写诊断文件（清空崩溃记录用）。"""
    body = ctx["body"]
    path = _diag_path(body.get("path"))
    if not path:
        return JU.err("只允许写入 diagnostics.txt / crash.log")
    text = body.get("text") or ""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        return JU.err(str(e))
    return JU.ok({"path": path.replace("\\", "/"), "written": len(text)})


def dispatch(ctx, action):
    table = {
        "list": api_list,
        "stat": api_stat,
        "check_game": api_check_game,
        "read": api_read,
        "write": api_write,
    }
    fn = table.get(action)
    if not fn:
        return JU.err(f"未知的 fs 操作：{action}")
    try:
        return fn(ctx)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JU.err(f"{type(e).__name__}: {e}")
