# -*- coding: utf-8 -*-
"""原文 → 译文 缓存，每 N 批落盘一次，支持 Ctrl+C 后继续。"""
import json
import os

from logger import get_logger

log = get_logger("cache")


class Cache:
    def __init__(self, path):
        self.path = path
        self.data = {}
        self._dirty = False
        self._load()

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

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value
        self._dirty = True

    def __contains__(self, key):
        return key in self.data

    def __len__(self):
        return len(self.data)

    def save(self, force=False):
        if not self._dirty and not force:
            return
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        self._dirty = False
        log.debug("缓存已保存：%d 条", len(self.data))
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