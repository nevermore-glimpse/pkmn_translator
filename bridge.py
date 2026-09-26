# -*- coding: utf-8 -*-
"""
CLI / GUI 桥接层。

核心逻辑（commands.py）只通过本模块输出信息、上报进度、询问是否取消，
从而同时支持命令行与图形界面，避免在核心代码里出现 input() / print() 混用。

GUI 侧：
    bridge.set_sinks(print_fn=..., progress_fn=..., cancel_fn=...)
CLI 侧：
    bridge.set_sinks(None, None, None)   # 退回 print()
"""
import threading

_print_sink = None
_progress_sink = None
_cancel_fn = None

_lock = threading.RLock()
_cancelled = False


# ================================================================
# 注册
# ================================================================
def set_sinks(print_fn=None, progress_fn=None, cancel_fn=None):
    """注册 GUI 回调；传 None 表示退回命令行行为。"""
    global _print_sink, _progress_sink, _cancel_fn
    with _lock:
        _print_sink = print_fn
        _progress_sink = progress_fn
        _cancel_fn = cancel_fn


def reset_cancel():
    global _cancelled
    with _lock:
        _cancelled = False


def request_cancel():
    global _cancelled
    with _lock:
        _cancelled = True


def cancelled():
    """核心循环里周期性调用，判断是否应当中止。"""
    with _lock:
        fn = _cancel_fn
    if fn is not None:
        try:
            return bool(fn())
        except Exception:
            return False
    with _lock:
        return _cancelled


# ================================================================
# 输出
# ================================================================
def emit(*args, **kwargs):
    """等价于 print()，但会被 GUI 接管。"""
    sep = kwargs.pop("sep", " ") if "sep" in kwargs else " "
    end = kwargs.pop("end", "\n") if "end" in kwargs else "\n"
    if kwargs:
        # 兼容少量误用，直接忽略
        pass
    text = sep.join(str(a) for a in args) + end

    # ★ 同步写入运行日志：让日志文件与 cmd / 界面上看到的输出保持一致
    try:
        import logger
        logger.log_cmd(text)
    except Exception:
        pass

    with _lock:
        sink = _print_sink
    if sink is not None:
        try:
            sink(text)
            return
        except Exception:
            pass
    try:
        print(text, end="")
    except Exception:
        pass


def progress(done=None, total=None, text=""):
    """上报进度：done/total 为 None 时表示只更新文字。"""
    with _lock:
        sink = _progress_sink
    if sink is None:
        return
    try:
        sink(done, total, text)
    except Exception:
        pass


class CancelRequested(Exception):
    """核心流程主动中止时抛出。"""
    pass
