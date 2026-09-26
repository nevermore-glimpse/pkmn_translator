# -*- coding: utf-8 -*-
"""原文 → 译文 缓存，每 N 批落盘一次，支持 Ctrl+C 后继续。"""
import json
import os
import time

import config
from logger import get_logger

log = get_logger("cache")


def atomic_replace(tmp, path, retries=6, delay=0.12):
    """
    原子替换文件。

    Windows 上 os.replace 偶尔会因杀毒软件 / 索引服务短暂占用目标文件
    而抛「拒绝访问（WinError 5）」或「共享冲突（WinError 32）」——
    缓存每批都要落盘，一旦抛异常整批翻译就断了，所以这里做有限次重试。
    """
    last = None
    for i in range(max(1, retries)):
        try:
            os.replace(tmp, path)
            return True
        except OSError as e:
            code = getattr(e, "winerror", None)
            if isinstance(e, PermissionError) or code in (5, 32):
                last = e
                time.sleep(delay * (i + 1))
                continue
            raise
    log.warning("原子替换失败（重试 %d 次）：%s → %s：%s",
                retries, tmp, path, last)
    raise last


class Cache:
    def __init__(self, path, save_every=None):
        self.path = path
        self.data = {}
        self._dirty = False
        if save_every is None:
            save_every = getattr(config, "CACHE_SAVE_EVERY", 1) or 1
        self.save_every = max(1, int(save_every))
        self._since_save = 0
        self._load()

    # ---------- 读写 ----------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                log.info("缓存加载成功：%s  (%d 条)", self.path, len(self.data))
            except Exception as e:
                log.warning("缓存加载失败（忽略）：%s", e)
                self.data = {}
        else:
            log.info("缓存文件不存在，新建：%s", self.path)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def put(self, key, value):
        self.data[key] = value
        self._dirty = True

    def put_many(self, mapping):
        self.data.update(mapping)
        if mapping:
            self._dirty = True

    def remove_many(self, keys):
        """批量删除缓存条目，返回实际删除的数量。"""
        n = 0
        for k in keys:
            if k in self.data:
                del self.data[k]
                n += 1
        if n:
            self._dirty = True
        return n

    def keys(self):
        return list(self.data.keys())

    def items(self):
        return self.data.items()

    # ---------- 落盘 ----------
    def save(self, force=False):
        if not self._dirty and not force:
            return
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        atomic_replace(tmp, self.path)
        self._dirty = False
        self._since_save = 0
        log.debug("缓存已保存：%d 条", len(self.data))
    def tick(self):
        """每处理完一批调用一次；到达间隔才真正写盘。"""
        self._since_save += 1
        if self._since_save >= self.save_every:
            self.save()

    def __contains__(self, key):
        return key in self.data

    def __getitem__(self, key):
        return self.data[key]

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)
