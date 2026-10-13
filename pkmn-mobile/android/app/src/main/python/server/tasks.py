# -*- coding: utf-8 -*-
"""
任务管理：长耗时操作放后台线程跑，日志/进度实时推给前端。

和电脑版的连接点在这里 —— 电脑版 GUI 是这么接的（gui.py:2754）：

    bridge.set_sinks(print_fn=..., progress_fn=..., cancel_fn=...)

而 debug_tool / essentials_base 这些函数签名本身就预留了 emit 参数
（`enable_debug(game_dir, emit=None, ...)`），所以本模块只要把 emit 重定向到
队列，核心代码一个字都不用改。

前端消费方式：
    POST /api/debug/enable      → {"task_id": "..."}
    GET  /api/task/{id}/stream  → SSE，持续推送 {"type":"log"|"prog"|"done"|"error"}
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
import uuid

_tasks = {}
_lock = threading.RLock()
_MAX_KEEP = 32          # 只留最近的任务，避免内存无限涨


class Task:
    def __init__(self, name, fn):
        self.id = uuid.uuid4().hex[:12]
        self.name = name
        self.fn = fn
        self.q = queue.Queue()
        self.cancel_flag = False
        self.result = None
        self.error = None
        self.started_at = time.time()
        self.finished_at = None
        self.done = False
        self._thread = threading.Thread(target=self._run,
                                        name=f"task-{self.id}", daemon=True)

    # ---- 给核心代码用的三个 hook，与 bridge.set_sinks 一一对应 ----
    def emit(self, msg):
        self.q.put(("log", str(msg)))

    def progress(self, done=None, total=None, text=""):
        self.q.put(("prog", {"done": done, "total": total, "text": text}))

    def cancelled(self):
        return self.cancel_flag

    # ---- 生命周期 ----
    def start(self):
        self._thread.start()
        return self

    def _run(self):
        try:
            self.result = self.fn(
                emit=self.emit,
                progress=self.progress,
                cancelled=self.cancelled,
            )
            self.q.put(("done", {"ok": True, "result": self.result}))
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            traceback.print_exc()
            self.q.put(("error", {"message": self.error}))
            self.q.put(("done", {"ok": False}))
        finally:
            self.done = True
            self.finished_at = time.time()

    def request_cancel(self):
        self.cancel_flag = True

    def snapshot(self):
        return {
            "id": self.id,
            "name": self.name,
            "done": self.done,
            "error": self.error,
            "elapsed": round((self.finished_at or time.time()) - self.started_at, 2),
        }


def create(name, fn):
    """建一个任务并启动。fn 会被调用为 fn(emit=..., progress=..., cancelled=...)。"""
    with _lock:
        # 清理老任务
        if len(_tasks) > _MAX_KEEP:
            for tid, t in sorted(_tasks.items(),
                                 key=lambda kv: kv[1].started_at)[:-_MAX_KEEP]:
                if t.done:
                    _tasks.pop(tid, None)
        t = Task(name, fn)
        _tasks[t.id] = t
        t.start()
        return t


def get(task_id):
    with _lock:
        return _tasks.get(task_id)


def cancel(task_id):
    t = get(task_id)
    if not t:
        return False
    t.request_cancel()
    return True
