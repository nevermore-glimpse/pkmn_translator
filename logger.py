# -*- coding: utf-8 -*-
"""
统一日志模块。

用法：
    from logger import get_logger
    log = get_logger(__name__)
    log.info("...")

日志文件：E:\pkmn_translator\logs\translate_YYYYMMDD.log
环境变量 DEBUG_PH=1 时，控制台也输出 DEBUG 级别。
"""
import logging
import os
import sys
from datetime import datetime

import config

_LOG_DIR = os.path.join(config.BASE_DIR, "logs")
_INITIALIZED = False


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


def _init():
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    os.makedirs(_LOG_DIR, exist_ok=True)
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

    root.info("=" * 60)
    root.info("会话开始  日志文件：%s", log_file)
    root.info("=" * 60)


def get_logger(name):
    _init()
    short = name.split(".")[-1] or "main"
    return logging.getLogger(f"pkmn.{short}")