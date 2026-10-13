# -*- coding: utf-8 -*-
r"""
调试启动器 —— **独立可执行版入口**（PyInstaller 打成单文件 exe 用）。

设计目标：**exe 本身是固定的**，所有游戏共用同一个文件；每个游戏各自的
设置（游戏 exe 名、运行库类型、钩子脚本…）放在游戏目录里的
`_pkmn_debug_launcher.json`，由本程序读取。

    游戏目录/
      宝可梦调试启动器.exe        ← 固定，一个文件，所有游戏都一样
      _pkmn_debug_launcher.json   ← 随游戏而变（由翻译工具生成）
      Game.exe、Data/、…

★ 这样打包出来的 exe 自带 Python 解释器，**玩家机器上不需要装 Python**。
★ 本文件**只依赖标准库**，PyInstaller 打包时不会牵扯项目的其它模块。

用法：
    宝可梦调试启动器.exe                 # 就近读配置
    宝可梦调试启动器.exe "D:\某个游戏"   # 指定游戏目录
    宝可梦调试启动器.exe --rebuild       # 重新生成本地配置（兜底）
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import ctypes
from ctypes import wintypes

APP_VERSION = "1.0"
CONFIG_NAME = "_pkmn_debug_launcher.json"
EXE_NAME = "宝可梦调试启动器.exe"
MARKER_FALLBACK = "_pkmn_debug_ok.txt"

# ================================================================
# 输出
# ================================================================
def _init_console():
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:                                        # noqa: BLE001
        pass
    if not hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                          encoding="utf-8",
                                          errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer,
                                          encoding="utf-8",
                                          errors="replace")
        except Exception:                                    # noqa: BLE001
            pass
        return
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                    # noqa: BLE001
            pass


def log(msg):
    try:
        print(msg)
        sys.stdout.flush()
    except Exception:                                        # noqa: BLE001
        pass


# ================================================================
# 配置文件
# ================================================================
def default_config(game_dir, game_exe, runtime="auto"):
    return {
        "version": 1,
        "tool_version": APP_VERSION,
        "game_dir": game_dir,
        "game_exe": game_exe,
        # "mkxp" / "rgss" / "auto"（auto = 启动后看进程加载了哪个 dll 再定）
        "runtime": runtime,
        "marker": MARKER_FALLBACK,
        # RGSS 用的注入钩子源码（随游戏/引擎版本变化，故放配置里）
        "hook_rb": DEFAULT_HOOK_RB,
    }


def read_config(game_dir):
    """读配置；没有 / 读不出来 → None。"""
    p = os.path.join(game_dir, CONFIG_NAME)
    if not os.path.isfile(p):
        return None
    try:
        with io.open(p, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except Exception as e:                                   # noqa: BLE001
        log("[!] 配置读不出来：%s（%s）" % (CONFIG_NAME, e))
        return None
    if not isinstance(cfg, dict):
        return None
    cfg.setdefault("marker", MARKER_FALLBACK)
    cfg.setdefault("runtime", "auto")
    cfg.setdefault("hook_rb", DEFAULT_HOOK_RB)
    return cfg


def write_config(game_dir, cfg):
    p = os.path.join(game_dir, CONFIG_NAME)
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return p


# ================================================================
# mkxp-z 分支：原生命令行参数 `debug`
# ================================================================
def run_mkxp(game_dir, game_exe, marker):
    exe_path = os.path.join(game_dir, game_exe)
    if not os.path.isfile(exe_path):
        log("找不到游戏：%s" % exe_path)
        return 2
    _rm(os.path.join(game_dir, marker))
    log("=" * 52)
    log("  调试模式启动器（mkxp-z）")
    log("=" * 52)
    log("启动命令：%s debug" % game_exe)
    subprocess.Popen([exe_path, "debug"], cwd=game_dir)
    for _ in range(40):
        time.sleep(0.5)
        if os.path.exists(os.path.join(game_dir, marker)):
            break
    if os.path.exists(os.path.join(game_dir, marker)):
        log("[OK] 已进入调试模式")
    else:
        log("[i] 未收到自检标记；进游戏后按 F9 验证。")
    log("地图上按 F9 打开调试菜单。")
    return 0


# ================================================================
# RGSS / 未知分支：运行时探测引擎 + 内存补丁
# ================================================================
BOOTSTRAP_NEEDLE = b"$RGSS_SCRIPTS = load_data"
RGSS_DLL_RE = re.compile(r"^rgss\d*\w*\.dll$", re.I)
RUBY_DLL_RE = re.compile(r"^(?:x64-|x86-)?(?:msvcrt|vcruntime)-ruby.*\.dll$",
                         re.I)

# 注入到游戏进程内存的钩子：设 $DEBUG、复刻 RGSS 引导逻辑、屏蔽编译入口。
# 不检查引擎指纹；找不到引导串时按正常模式放行。
DEFAULT_HOOK_RB = r"""
$DEBUG = true
begin
  fname = scripts_fname
rescue Exception
  fname = nil
end
if fname.nil? || fname.to_s.empty?
  begin
    ini = File.open("Game.ini", "rb") { |f| f.read }
    fname = ini.scan(/Scripts\s*=\s*(\S+)/).flatten.first.to_s.gsub("\\", "/")
  rescue Exception
    fname = nil
  end
end
fname = "Data/Scripts.rxdata" if fname.nil? || fname.empty?
$RGSS_SCRIPTS = load_data(fname)
$RGSS_SCRIPTS.each { |s| s[3, 0] = Zlib::Inflate.inflate(s[2]) }

patched = 0
$RGSS_SCRIPTS.each do |s|
  code = s[3].to_s
  orig = code.dup
  # (1) Settings 里 `$DEBUG = false` 会盖掉上面的值 -> 改 true
  code = code.sub(/\$DEBUG\s*=\s*false/, "$DEBUG = true")
  # (2) Main 里裸调 pbCompiler（打包版磁盘没有 PBS，会崩）-> 注释
  code = code.sub(/^pbCompiler\s*$/, "# pbCompiler (debug launcher: disabled)")
  # (3) 兜底：pbCompiler 方法体开局 return
  code = code.sub(/def pbCompiler[ \t]*\n/) { "def pbCompiler\n  return\n" }
  if code != orig
    s[3] = code
    patched += 1
  end
end

begin
  _mk = File.join(Dir.pwd, "__MARKER__")
  File.open(_mk, "wb") do |f|
    f.write("DEBUG=#{$DEBUG.inspect}\npatched=#{patched}\ncount=#{$RGSS_SCRIPTS.size}\n")
  end
rescue Exception
end
$RGSS_SCRIPTS.size
"""


class ME32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("dw32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260),
    ]


def _scan_range(h, base, size, needle):
    off = 0
    buf = ctypes.create_string_buffer(1 << 20)
    while off < size:
        chunk = min(1 << 20, size - off)
        rd = ctypes.c_size_t(0)
        if ctypes.windll.kernel32.ReadProcessMemory(
                h, ctypes.c_void_p(base + off), buf, chunk,
                ctypes.byref(rd)):
            i = buf.raw[:rd.value].find(needle)
            if i != -1:
                return base + off + i
        off += chunk
    return None


def _mods(pid):
    """列出进程已加载模块 [(name, base, size), ...]。"""
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(0x08 | 0x10, pid)
    me = ME32()
    me.dwSize = ctypes.sizeof(ME32)
    out = []
    if k32.Module32First(snap, ctypes.byref(me)):
        while True:
            out.append((me.szModule.decode("mbcs", "replace"),
                        me.modBaseAddr or 0, me.modBaseSize))
            if not k32.Module32Next(snap, ctypes.byref(me)):
                break
    k32.CloseHandle(snap)
    return out


def _find_running(exe_name):
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq " + exe_name, "/FO", "CSV",
             "/NH"], stderr=subprocess.DEVNULL).decode("mbcs", "replace")
        return exe_name.lower() in out.lower()
    except Exception:                                        # noqa: BLE001
        return False


def _rm(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def run_rgss(game_dir, game_exe, marker, hook_rb):
    k32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll
    exe_path = os.path.join(game_dir, game_exe)
    if not os.path.isfile(exe_path):
        log("找不到游戏：%s" % exe_path)
        return 2
    if _find_running(game_exe):
        log("游戏已在运行。请先关闭，再用本程序启动"
            "（补丁必须在启动前打）。")
        return 7

    marker_path = os.path.join(game_dir, marker)
    _rm(marker_path)

    hook_path = os.path.join(tempfile.gettempdir(), "_pkmn_debug_hook.rb")
    try:
        with io.open(hook_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(hook_rb.replace("__MARKER__", marker).strip() + "\n")
    except OSError as e:
        log("写钩子脚本失败：%s" % e)
        return 5
    payload = ('eval(File.read("%s"))'
               % hook_path.replace("\\", "/")).encode("ascii")

    log("=" * 52)
    log("  调试模式启动器（运行时探测引擎）")
    log("=" * 52)
    log("正在启动游戏 ...")
    proc = subprocess.Popen([exe_path], cwd=game_dir, creationflags=0x00000008)
    h = k32.OpenProcess(0x001F0FFF, False, proc.pid)
    if not h:
        log("无法打开进程（权限不足）。请以普通用户方式运行。")
        return 3

    addr = None
    detected = None
    mkxp_seen = False
    scanned = set()
    t0 = time.time()
    log("等待运行库载入 ...")
    while time.time() - t0 < 90:
        if proc.poll() is not None:
            log("游戏进程已退出。")
            return 4
        hit = None
        for name, base, size in _mods(proc.pid):
            ln = name.lower()
            if RGSS_DLL_RE.match(ln):
                hit = ("rgss", base, size, name)
                break
            if RUBY_DLL_RE.match(ln):
                hit = hit or ("mkxp", base, size, name)
        if hit:
            kind, base, size, mname = hit
            if kind != detected:
                detected = kind
                log("识别到引擎：%s（%s，%.1fs）"
                    % ("RGSS" if kind == "rgss" else "mkxp-z",
                       mname, time.time() - t0))
            if base not in scanned:
                scanned.add(base)
                addr = _scan_range(h, base, size, BOOTSTRAP_NEEDLE)
                if addr:
                    log("已定位引导代码: 0x%X (%.1fs)"
                        % (addr, time.time() - t0))
                    break
                if kind == "rgss":
                    log("· 该模块里没搜到引导串")
            if kind == "mkxp":
                mkxp_seen = True
                break
        if mkxp_seen:
            break
        time.sleep(0.15)

    if detected == "mkxp":
        log("-" * 52)
        log("[i] mkxp-z：改用原生调试参数重启 ...")
        try:
            proc.terminate()
        except Exception:                                    # noqa: BLE001
            pass
        time.sleep(0.6)
        subprocess.Popen([exe_path, "debug"], cwd=game_dir)
        log("[OK] 已用 mkxp-z 原生调试模式启动。")
        log("进游戏后按 F9 打开调试菜单；按 F12 复位。")
        return 0

    if not addr:
        if detected is None:
            log("[i] 未认出引擎模块，按默认（RGSS）方式再试一次 ...")
        for name, base, size in _mods(proc.pid):
            if proc.poll() is not None:
                break
            if base in scanned:
                continue
            addr = _scan_range(h, base, size, BOOTSTRAP_NEEDLE)
            if addr:
                detected = detected or "rgss"
                log("在模块 %s 内定位到引导代码: 0x%X" % (name, addr))
                break

    if not addr:
        log("[i] 没找到可替换的引导串 → 用 `%s debug` 再试一次 ..." % game_exe)
        try:
            proc.terminate()
        except Exception:                                    # noqa: BLE001
            pass
        time.sleep(0.6)
        subprocess.Popen([exe_path, "debug"], cwd=game_dir)
        log("已用 `%s debug` 重启。" % game_exe)
        log("mkxp-z 会置 $DEBUG/$TEST；RGSS 会忽略该参数、按正常模式运行。")
        return 0

    old = wintypes.DWORD()
    ntdll.NtSuspendProcess(h)
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), ctypes.c_size_t(256),
                         0x04, ctypes.byref(old))
    written = ctypes.c_size_t(0)
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr),
                                payload + b"\x00", len(payload) + 1,
                                ctypes.byref(written))
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), ctypes.c_size_t(256),
                         old.value or 0x02, ctypes.byref(old))
    ntdll.NtResumeProcess(h)
    if not ok:
        log("写入内存失败，补丁未生效。游戏按正常模式运行。")
        return 6
    log("补丁已写入 (%d 字节)。" % written.value)

    for _ in range(60):
        time.sleep(0.5)
        if os.path.exists(marker_path):
            break
    if os.path.exists(marker_path):
        try:
            info = io.open(marker_path, "r", encoding="utf-8",
                           errors="replace").read().strip()
        except Exception:                                    # noqa: BLE001
            info = ""
        log("-" * 52)
        log("[OK] 调试模式已开启")
        for line in info.splitlines():
            log("   " + line)
        log("地图上按 F9 开调试菜单；按住 Ctrl 移动 = 穿墙。")
    else:
        log("[!] 钩子未被执行（补丁可能晚了一步）。游戏仍在正常模式运行。")
    log("游戏已交由系统接管，本窗口可以关闭。")
    return 0


# ================================================================
# 入口
# ================================================================
def looks_like_game(game_dir):
    """
    这个目录像不像一个游戏根目录。

    ★ 用于「配置丢了、要不要就地重建」的判断：**宁可报错也不能瞎启动**。
      没有判断就重建的话，把exe 放在翻译工具目录旁边时，它会把翻译工具
      本身当游戏拉起来（实测踩过）。
    """
    if not os.path.isdir(game_dir):
        return False
    if os.path.isfile(os.path.join(game_dir, "Game.ini")):
        return True
    if os.path.isdir(os.path.join(game_dir, "Data")):
        return True
    try:
        names = [n.lower() for n in os.listdir(game_dir)]
    except OSError:
        return False
    return any(n.startswith("rgss") and n.endswith(".dll") for n in names) or         any("mkxp" in n for n in names) or         (any(n.endswith(".exe") for n in names)
         and any(n in ("data", "pbs", "graphics", "audio") for n in names))


def _pick_game_exe(game_dir):
    """找主 exe：优先 Game.exe，否则取最大的非工具 exe。"""
    bad = ("editor", "animmaker", "extendtext", "townmapgen",
           "旧", "old", "备份", "bak", "debug", "更新", "update")
    cands = []
    try:
        names = [n for n in os.listdir(game_dir)
                 if n.lower().endswith(".exe")
                 and os.path.normcase(n) != os.path.normcase(EXE_NAME)]
    except OSError:
        return "Game.exe"
    if "Game.exe" in names:
        return "Game.exe"
    for n in names:
        if any(k in n.lower() for k in bad):
            continue
        try:
            cands.append((os.path.getsize(os.path.join(game_dir, n)), n))
        except OSError:
            pass
    if cands:
        cands.sort(reverse=True)
        return cands[0][1]
    return names[0] if names else "Game.exe"


def main(argv=None):
    _init_console()
    argv = list(argv if argv is not None else sys.argv[1:])
    here = os.path.dirname(os.path.abspath(sys.argv[0]))

    game_dir = None
    for a in argv:
        if not a.startswith("-"):
            game_dir = os.path.abspath(a)
            break
    if game_dir is None:
        game_dir = here

    if not os.path.isdir(game_dir):
        log("[ERROR] 游戏目录不存在：%s" % game_dir)
        return 2

    cfg = read_config(game_dir)
    if cfg is None:
        # ★ 没有配置时**只有确定这是游戏目录**才就地重建 ——
        #   否则把 exe 放在工具目录旁边，它会拿工具 exe 当游戏启动。
        if "--rebuild" in argv or not argv:
            if not looks_like_game(game_dir):
                log("=" * 52)
                log("  调试模式启动器")
                log("=" * 52)
                log("[ERROR] 这个目录里没有 %s，" % CONFIG_NAME)
                log("        而且看起来**不是游戏目录**（没有 Game.ini / Data）。")
                log("        为安全起见不自动猜测游戏程序，已停止。")
                log("        目录：%s" % game_dir)
                log("")
                log("        请把它放到游戏根目录（和 Game.exe 放在一起），")
                log("        或用翻译工具的「⑥ 调试启动器」重新生成一次。")
                return 4
            game_exe = _pick_game_exe(game_dir)
            cfg = default_config(game_dir, game_exe)
            write_config(game_dir, cfg)
            log("已生成配置：%s（主程序 %s，运行库 auto）"
                % (CONFIG_NAME, game_exe))
        else:
            log("=" * 52)
            log("  调试模式启动器")
            log("=" * 52)
            log("[ERROR] 这个目录里没有 %s —— 请让本程序和它待在")
            log("        同一个游戏目录里，或把它拖到游戏 exe 上运行。" %
                CONFIG_NAME)
            log("        目录：%s" % game_dir)
            return 3

    gd = cfg.get("game_dir") or game_dir
    if not os.path.isdir(gd):
        gd = game_dir
    game_exe = cfg.get("game_exe") or _pick_game_exe(gd)
    marker = cfg.get("marker") or MARKER_FALLBACK
    kind = (cfg.get("runtime") or "auto").lower()
    hook = cfg.get("hook_rb") or DEFAULT_HOOK_RB

    log("游戏目录：%s" % gd)
    log("主程序：%s" % game_exe)
    if kind == "mkxp":
        return run_mkxp(gd, game_exe, marker)
    return run_rgss(gd, game_exe, marker, hook)


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:                                   # noqa: BLE001
        import traceback
        log("发生异常：%r" % (e,))
        log(traceback.format_exc())
        rc = 1
    if rc != 0:
        try:
            input("按回车键关闭 ...")
        except Exception:                                    # noqa: BLE001
            pass
    else:
        try:
            time.sleep(6)
        except Exception:                                    # noqa: BLE001
            pass
    sys.exit(rc)