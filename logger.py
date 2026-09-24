# -*- coding: utf-8 -*-
"""
统一日志模块。

用法：
    from logger import get_logger
    log = get_logger(__name__)
    log.info("...")

日志文件：<BASE_DIR>/logs/translate_YYYYMMDD.log
环境变量 DEBUG_PH=1 时，控制台也输出 DEBUG 级别。
启动时自动删除 keep_days 天前的日志。
"""
import logging
import os
import re
import sys
from datetime import datetime, timedelta

import config

_LOG_DIR = os.path.join(config.BASE_DIR, "logs")
_INITIALIZED = False
_emit_logger = None     # cmd / 界面输出专用：只写文件，不回灌控制台
_gui_sink = None        # GUI「运行日志」页回调

# 保留最近 N 天的日志
LOG_KEEP_DAYS = 3


class _ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[41m",
    }
    RESET = "\033[0m"

    def format(self, record):
        msg = super().format(record)
        color = self.COLORS.get(record.levelname, "")
        if color and sys.stdout.isatty():
            return f"{color}{msg}{self.RESET}"
        return msg


def _cleanup_old_logs(log_dir, keep_days=LOG_KEEP_DAYS):
    """
    删除 keep_days 天前的 translate_*.log。
    只处理 translate_YYYYMMDD.log 格式的文件，
    其它日志（如 ollama_launch.log）不动。
    """
    pattern = re.compile(r'^translate_(\d{8})\.log$')
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0

    try:
        for name in os.listdir(log_dir):
            m = pattern.match(name)
            if not m:
                continue
            try:
                file_date = datetime.strptime(m.group(1), "%Y%m%d")
            except ValueError:
                continue
            if file_date < cutoff:
                p = os.path.join(log_dir, name)
                try:
                    os.remove(p)
                    removed += 1
                except Exception:
                    pass
    except Exception:
        pass

    return removed


def _init():
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    os.makedirs(_LOG_DIR, exist_ok=True)

    # ★ 清理旧日志
    try:
        n = _cleanup_old_logs(_LOG_DIR, LOG_KEEP_DAYS)
        if n:
            print(f"[logger] 已清理 {n} 个超过 {LOG_KEEP_DAYS} 天的日志文件")
    except Exception:
        pass

    root = logging.getLogger("pkmn")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.propagate = False

    date_str = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(_LOG_DIR, f"translate_{date_str}.log")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-7s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    console_level = logging.DEBUG if os.environ.get("DEBUG_PH") == "1" else logging.INFO
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(console_level)
    ch.setFormatter(_ColorFormatter(
        "%(asctime)s [%(levelname)-7s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(ch)

    # ★ cmd / 界面输出专用日志器：
    #   复用同一个文件句柄（避免两个 handler 同时打开同一个文件），
    #   并关闭冒泡 —— 否则 emit() 的内容会被控制台 handler 再打一遍，
    #   命令行里同一行就会出现两次。
    global _emit_logger
    el = logging.getLogger("pkmn.cmd")
    el.setLevel(logging.DEBUG)
    el.handlers.clear()
    el.propagate = False
    el.addHandler(fh)
    _emit_logger = el

    root.info("=" * 60)
    root.info("会话开始  日志文件：%s", log_file)
    root.info("=" * 60)


def get_logger(name):
    _init()
    short = name.split(".")[-1] or "main"
    return logging.getLogger(f"pkmn.{short}")


def log_cmd(text):
    """
    把 cmd / 界面上的输出同步写入运行日志文件，
    使「运行日志」与命令行里看到的内容保持一致。

    只写文件、不回灌控制台：emit() 本身已经打印过一次，
    再走控制台 handler 会造成同一行重复出现。
    """
    _init()
    el = _emit_logger
    if el is None:
        return
    try:
        for line in str(text).splitlines():
            if line.strip():
                el.info(line)
    except Exception:
        pass


class _GuiHandler(logging.Handler):
    """把 logging 记录转发给 GUI「运行日志」页。"""

    def emit(self, record):
        fn = _gui_sink
        if fn is None:
            return
        try:
            fn(self.format(record) + "\n")
        except Exception:
            pass


def set_gui_sink(fn):
    """
    注册 GUI 回调后，log.info / warning / error 会同步显示在 GUI「运行日志」页，
    与命令行里看到的内容一致。传 None 取消注册。
    """
    global _gui_sink
    _init()
    _gui_sink = fn

    root = logging.getLogger("pkmn")
    for h in list(root.handlers):
        if isinstance(h, _GuiHandler):
            root.removeHandler(h)
    if fn is not None:
        gh = _GuiHandler()
        gh.setLevel(logging.INFO)
        gh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-7s] %(message)s",
            datefmt="%H:%M:%S",
        ))
        root.addHandler(gh)