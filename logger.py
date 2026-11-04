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
import threading
from datetime import datetime, timedelta

import config

_LOG_DIR = os.path.join(config.BASE_DIR, "logs")
_INITIALIZED = False
_emit_logger = None     # cmd / 界面输出专用：只写文件，不回灌控制台
_gui_sink = None        # GUI「运行日志」页回调

# ★ 「只提示一次」的日志去重表：key → 出现次数
_ONCE_LOCK = threading.Lock()
_ONCE_SEEN = {}

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


def log_once(key, msg, *args, level=logging.INFO, logger=None):
    """
    同一条提示**只写一次**，后面的重复只计数（不写盘、不刷屏）。

    用在「每句 / 每批都会触发、但内容一样」的提示上，例如
    「剥掉译文开头残留的旧前缀」「安全恢复：省略号形态跟随原文」——
    一个文件几千句就会刷出几千行，把真正有用的信息埋掉。

    key    —— 去重键（同一 key 只出一条）；建议用 ("类别", 细分) 的元组
    msg    —— 标准 logging 格式串，args 照旧
    level  —— 默认 INFO，可传 logging.WARNING
    logger —— 不传就用按调用模块名推断的 logger

    返回 True 表示这次真的写下去了（没写过），False 表示被去重。
    想看总共出现过多少次，用 once_count(key)；想重新开始计数用 reset_once()。
    """
    logger = logger or _caller_logger()
    with _ONCE_LOCK:
        n = _ONCE_SEEN.get(key, 0)
        _ONCE_SEEN[key] = n + 1
    if n:
        return False
    try:
        logger.log(level, msg, *args)
    except Exception:
        pass
    return True


def _caller_logger():
    """按调用方的模块名取 logger（log_once 不想强制传 logger 参数）。"""
    try:
        name = sys._getframe(2).f_globals.get("__name__", "main")
    except Exception:
        name = "main"
    return get_logger(name)


def once_count(key):
    """某个 key 被触发过多少次（含被去重掉的那些）。"""
    with _ONCE_LOCK:
        return _ONCE_SEEN.get(key, 0)


def reset_once(prefix=None):
    """
    清空去重计数。给长期运行的界面用：一轮翻译开始前重置，
    下一轮又能看到一次提示。prefix 给定时只清「key 的第一段等于它」的那些。
    """
    with _ONCE_LOCK:
        if prefix is None:
            _ONCE_SEEN.clear()
            return
        for k in list(_ONCE_SEEN):
            head = k[0] if isinstance(k, tuple) and k else k
            if head == prefix:
                _ONCE_SEEN.pop(k, None)


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