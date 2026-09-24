# -*- coding: utf-8 -*-
"""原文 → 译文 缓存，每 N 批落盘一次，支持 Ctrl+C 后继续。"""
import json
import os

import config
from logger import get_logger

log = get_logger("cache")


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
        os.replace(tmp, self.path)
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
