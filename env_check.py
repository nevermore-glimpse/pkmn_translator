# -*- coding: utf-8 -*-
"""
启动时环境检查：
  · Python 版本
  · 第三方依赖 (requests, openpyxl)
  · Ollama 服务
  · Ollama 模型
并支持自动启动 Ollama（优先桌面应用，退回命令行）。
"""
import importlib
import os
import shutil
import socket
import subprocess
import sys
import urllib.parse

import config
from logger import get_logger

log = get_logger("env_check")


# ================================================================
# 基础检查
# ================================================================
def check_python():
    v = sys.version_info
    if (v.major, v.minor) < (3, 9):
        return False, f"Python {v.major}.{v.minor}（需要 3.9+）"
    return True, f"Python {v.major}.{v.minor}.{v.micro}"


def check_packages():
    required = ["requests", "openpyxl"]
    missing = [p for p in required if not importlib.util.find_spec(p)]
    if missing:
        return False, f"缺少依赖：{', '.join(missing)}", missing
    return True, "依赖完整", []


def _parse_host_port(url):
    p = urllib.parse.urlparse(url)
    return p.hostname or "localhost", p.port or 11434


def check_ollama_service(url=None):
    host, port = _parse_host_port(url or config.OLLAMA_URL)
    try:
        with socket.create_connection((host, port), timeout=2):
            return True, f"服务在线（{host}:{port}）"
    except Exception as e:
        return False, f"无法连接 {host}:{port}（{e.__class__.__name__}）"


def list_ollama_models(timeout=4):
    """
    列出本机 Ollama 已安装的模型名（升序）。
    服务不可用时返回空列表，不抛异常。
    """
    try:
        import requests
        p = urllib.parse.urlparse(config.OLLAMA_URL)
        r = requests.get(f"{p.scheme}://{p.netloc}/api/tags", timeout=timeout)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        return sorted(n for n in names if n)
    except Exception as e:
        log.debug("查询模型列表失败：%s", e)
        return []


def check_ollama_model(model=None):
    import requests
    model = model or config.MODEL
    p = urllib.parse.urlparse(config.OLLAMA_URL)
    tags_url = f"{p.scheme}://{p.netloc}/api/tags"
    try:
        r = requests.get(tags_url, timeout=3)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        base = model.split(":")[0]
        for n in names:
            if n == model or n.startswith(base + ":"):
                return True, f"模型已安装（{n}）", names
        return False, f"模型未安装：{model}", names
    except Exception as e:
        return False, f"无法查询模型列表：{e}", []


# ================================================================
# Ollama 启动辅助
# ================================================================
def _find_ollama_app():
    """查找 ollama app.exe（桌面应用）。"""
    candidates = [
        os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama app.exe"),
        r"C:\Program Files\Ollama\ollama app.exe",
        r"C:\Program Files (x86)\Ollama\ollama app.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    # 从 PATH 里的 ollama.exe 反推
    exe = shutil.which("ollama")
    if exe:
        app = os.path.join(os.path.dirname(exe), "ollama app.exe")
        if os.path.exists(app):
            return app
    return None


def _find_ollama_exe():
    """查找 ollama.exe（命令行）。"""
    exe = shutil.which("ollama")
    if exe:
        return exe

    candidates = [
        os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
        r"C:\Program Files\Ollama\ollama.exe",
        r"C:\Program Files (x86)\Ollama\ollama.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _is_ollama_process_running():
    """检查系统里有没有 ollama 相关进程。"""
    if os.name != "nt":
        try:
            r = subprocess.run(["pgrep", "-f", "ollama"],
                               capture_output=True, text=True, timeout=3)
            return r.returncode == 0
        except Exception:
            return False

    # Windows：同时检查 ollama app.exe 和 ollama.exe
    try:
        for image in ("ollama app.exe", "ollama.exe"):
            r = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
                capture_output=True, text=True, timeout=5,
                encoding="gbk", errors="ignore",
            )
            if image.lower() in r.stdout.lower():
                return True
        return False
    except Exception:
        return False


def _show_log_tail(path, n=15):
    """打印日志文件最后 n 行。"""
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        tail = lines[-n:] if len(lines) > n else lines
        if not tail:
            print("    （日志为空）")
            return
        print(f"  日志末尾（{path}）：")
        for line in tail:
            print(f"    {line.rstrip()}")
    except Exception as e:
        print(f"    读取日志失败：{e}")


def try_start_ollama():
    """
    尝试启动 Ollama。
    优先启动桌面应用 ollama app.exe，找不到则退回 ollama serve。
    返回 (ok, msg, log_path)
    """
    if os.name != "nt":
        return False, "非 Windows 系统，请手动运行 ollama serve", None

    log_dir = os.path.join(config.BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    out_path = os.path.join(log_dir, "ollama_launch.log")

    # ---------- 方案 A：桌面应用 ----------
    app_exe = _find_ollama_app()
    if app_exe:
        log.info("找到 ollama app：%s", app_exe)
        try:
            subprocess.Popen(
                [app_exe],
                cwd=os.path.dirname(app_exe),
                close_fds=True,
            )
            return True, "已启动 Ollama 桌面应用", None
        except Exception as e:
            log.warning("启动 ollama app 失败：%s", e)
            # 继续尝试命令行方式

    # ---------- 方案 B：命令行 serve ----------
    exe = _find_ollama_exe()
    if not exe:
        return False, (
            "未找到 Ollama。\n"
            "  请安装：https://ollama.com/download\n"
            "  或确认 ollama.exe 已加入 PATH"
        ), None

    log.info("改用命令行方式：%s", exe)

    try:
        out = open(out_path, "w", encoding="utf-8")
    except Exception as e:
        return False, f"无法写入日志文件：{e}", None

    try:
        proc = subprocess.Popen(
            [exe, "serve"],
            stdout=out,
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(exe) or config.BASE_DIR,
        )
        log.info("已启动 ollama serve  PID=%s", proc.pid)
        return True, f"已启动 ollama serve（PID {proc.pid}）", out_path
    except Exception as e:
        try:
            out.close()
        except Exception:
            pass
        return False, f"启动失败：{e}", out_path


def ensure_ollama_interactive():
    """
    交互式：若 Ollama 未启动，询问用户是否尝试启动。
    返回 True 表示服务可用。
    """
    import time

    # ---------- 1. 快速检查 ----------
    ok, _ = check_ollama_service()
    if ok:
        return True

    print("\n⚠ Ollama 服务未启动（连接 11434 端口失败）")

    # ---------- 2. 进程已在跑 ----------
    if _is_ollama_process_running():
        print("  检测到 ollama 进程正在运行，但服务未响应。")
        print("  可能原因：")
        print("    · 服务仍在加载模型（首次启动较慢）")
        print("    · 端口被占用 / 被防火墙拦截")
        print("    · 服务监听在非默认端口")
        print("  建议：")
        print("    · 检查系统托盘是否有 Ollama 图标")
        print("    · 手动运行 ollama serve 查看输出")
        return False

    # ---------- 3. 询问用户 ----------
    ans = input("是否尝试自动启动？(Y/n): ").strip().lower()
    if ans == "n":
        return False

    ok2, msg2, log_path = try_start_ollama()
    print(f"  {msg2}")
    if not ok2:
        return False

    # ---------- 4. 渐进式等待 ----------
    print("  等待服务就绪…")
    waits = [1, 2, 3, 5, 8, 12]     # 累计 31 秒
    elapsed = 0
    for w in waits:
        time.sleep(w)
        elapsed += w
        ok3, _ = check_ollama_service()
        if ok3:
            print(f"  ✔ Ollama 已就绪（耗时约 {elapsed} 秒）")
            return True
        print(f"    … 已等待 {elapsed} 秒")

    # ---------- 5. 超时诊断 ----------
    if _is_ollama_process_running():
        print("  ✘ 服务启动超时（进程还在，但端口未响应）")
        print("  请检查是否有其他程序占用 11434 端口：")
        print("    netstat -ano | findstr :11434")
    else:
        print("  ✘ ollama 进程已退出，启动失败")
        _show_log_tail(log_path)

    return False


# ================================================================
# 综合检查
# ================================================================
def check_all(verbose=True):
    """返回 dict，同时打印到控制台。"""
    result = {}

    if verbose:
        print("\n[环境检查]")

    ok, msg = check_python()
    result["python"] = (ok, msg)
    if verbose:
        print(f"  [{'✔' if ok else '✘'}] {msg}")

    ok, msg, missing = check_packages()
    result["packages"] = (ok, msg)
    if verbose:
        print(f"  [{'✔' if ok else '✘'}] {msg}")
        if missing:
            print(f"      修复：pip install {' '.join(missing)}")

    ok, msg = check_ollama_service()
    result["ollama_service"] = (ok, msg)
    if verbose:
        print(f"  [{'✔' if ok else '✘'}] Ollama 服务：{msg}")

    if ok:
        ok2, msg2, _ = check_ollama_model()
        result["ollama_model"] = (ok2, msg2)
        if verbose:
            print(f"  [{'✔' if ok2 else '✘'}] Ollama 模型：{msg2}")
    else:
        result["ollama_model"] = (False, "服务未启动，跳过")
        if verbose:
            print("  [ ] Ollama 模型：跳过")

    return result