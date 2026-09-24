# -*- coding: utf-8 -*-
"""
文件选择器。

优先用 tkinter 弹窗（有图形界面），
若无 tkinter 则退化为命令行输入。
"""
import os

import config
from logger import get_logger

log = get_logger("filepicker")

try:
    import tkinter as tk
    from tkinter import filedialog
    _HAS_TK = True
except Exception:
    _HAS_TK = False


def _initial_dir(initial_dir):
    """统一处理初始目录：优先用户传入，其次 BASE_DIR，最后 cwd。"""
    if initial_dir and os.path.isdir(initial_dir):
        return initial_dir
    if os.path.isdir(config.BASE_DIR):
        return config.BASE_DIR
    return os.getcwd()


def _disable_root_icon():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def pick_text_file(initial_dir=None, title="选择文本文件"):
    """弹出选择框选一个文本文件，返回路径或 None。"""
    if not _HAS_TK:
        return _input_path_cli(title)

    try:
        root = _disable_root_icon()
        path = filedialog.askopenfilename(
            title=title,
            initialdir=_initial_dir(initial_dir),
            filetypes=[
                ("文本文件", "*.txt"),
                ("所有文件", "*.*"),
            ],
        )
        root.destroy()
        return path or None
    except Exception as e:
        log.warning("tkinter 弹窗失败：%s，退回命令行", e)
        return _input_path_cli(title)


def pick_dir(initial_dir=None, title="选择文件夹"):
    """选文件夹，返回路径或 None。"""
    if not _HAS_TK:
        print(f"\n{title}（直接回车放弃）")
        raw = input("路径：").strip().strip('"').strip("'")
        if not raw:
            return None
        return raw if os.path.isdir(raw) else None

    try:
        root = _disable_root_icon()
        path = filedialog.askdirectory(
            title=title,
            initialdir=_initial_dir(initial_dir),
        )
        root.destroy()
        return path or None
    except Exception as e:
        log.warning("tkinter 弹窗失败：%s", e)
        return None


def pick_excel_file(initial_dir=None):
    """选 Excel 文件。"""
    if not _HAS_TK:
        return _input_path_cli("选择 Excel 文件")

    try:
        root = _disable_root_icon()
        path = filedialog.askopenfilename(
            title="选择 Excel 文件",
            initialdir=_initial_dir(initial_dir),
            filetypes=[
                ("Excel 文件", "*.xlsx *.xlsm"),
                ("所有文件", "*.*"),
            ],
        )
        root.destroy()
        return path or None
    except Exception as e:
        log.warning("tkinter 弹窗失败：%s，退回命令行", e)
        return _input_path_cli("选择 Excel 文件")


def _input_path_cli(title):
    print(f"\n{title}（直接回车放弃）")
    raw = input("路径：").strip().strip('"').strip("'")
    if not raw:
        return None
    if not os.path.exists(raw):
        print(f"文件不存在：{raw}")
        return None
    return raw

