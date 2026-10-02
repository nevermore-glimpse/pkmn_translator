# -*- coding: utf-8 -*-
"""
术语字典（菜单 8）编辑器：给 GUI 提供「查看 / 修改 / 新增 / 删除 / 撤回」。

设计要点：
  · 所有改动先落在内存（staged），点「保存」才一次性写进 term_dict.py；
    保存前可以「撤回」，每一步操作都进撤销栈。
  · 视图顺序 = term_dict.py 里的原始顺序（正文条目在前，AUTO 块条目在后），
    叠加「删除 / 改名 / 改译文 / 新增」后的结果。
  · 校验规则对齐 processor.load_terms 的采纳条件 + auto_terms._validate
    的新增条件，避免"改了却不生效"。
  · 保存顺序：删除 → 改名 → 改译文 → 新增。
    先删除是为了给「改名 / 新增」腾出被删掉的原文名，否则会被跳过。
"""
import re

import config
import term_sync as TS
from logger import get_logger

log = get_logger("dict_editor")

UNDO_LIMIT = 60              # 撤销栈上限
VIEW_LIMIT_DEFAULT = 600     # 列表一次最多渲染多少条（10335 条全渲染太慢）
ORIGIN_ALL = "全部"
ORIGIN_AUTO = "自动"
ORIGIN_MANUAL = "手动"

_PLACEHOLDER_RE = re.compile(r'[@\u27e6]\d+[@\u27e7]\Z')


def _norm(k):
    return (k or "").strip().lower()


def _is_placeholder(k):
    return bool(_PLACEHOLDER_RE.match(k or ""))


def _is_skipped_short(k):
    """processor.load_terms 会跳过「长度 ≤3 的纯英文词」。"""
    return len(k) <= 3 and k.isascii() and k.isalpha()


def why_invalid_key(src, dst=""):
    """原文作为术语 key 不合格的原因；合格返回 ""。对齐 load_terms 的采纳条件。"""
    src = (src or "").strip()
    if not src:
        return "原文不能为空"
    if "\\" in src or "[" in src or "]" in src:
        return "原文里不能包含控制码（\\）或方括号（[ ]）"
    if _is_placeholder(src):
        return "占位符型条目（@0@ 等）不是术语，加载时会被跳过"
    if _is_skipped_short(src):
        return "原文太短：纯英文 3 个字符以内加载时会被跳过"
    if dst and src == dst:
        return "原文与译文相同"
    return ""


def why_invalid_new(src, dst):
    """「新增术语」不合格的原因；合格返回 ""。对齐 auto_terms._validate。"""
    src = (src or "").strip()
    dst = (dst or "").strip()
    if not src or not dst:
        return "原文与译文都不能为空"
    try:
        import auto_terms
        min_len = getattr(config, "AUTO_EXTRACT_MIN_LEN", 3)
        if not auto_terms._validate({src: dst}, min_len):
            return TS._why_invalid(src, dst, min_len)
    except Exception:
        pass
    return why_invalid_key(src, dst)


class TermDictEditor:
    """内存态的术语字典编辑器（线程内使用，不做加锁）。"""

    def __init__(self):
        self.reload()

    # ================================================================
    # 载入 / 视图
    # ================================================================
    def reload(self):
        """从 term_dict.py 重新载入，丢弃所有未保存改动。"""
        try:
            self.base = dict(TS.load_current_terms() or {})
        except Exception as e:
            log.warning("读取术语字典失败：%s", e)
            self.base = {}
        try:
            auto = TS.load_auto_block() or []
        except Exception as e:
            log.warning("读取 AUTO 块失败：%s", e)
            auto = []
        self.auto_keys = [k for k, _v in auto]
        self.auto_norm = {_norm(k) for k in self.auto_keys}

        self.added = {}       # 原文 → 译文（新增，保持添加顺序）
        self.changed = {}     # 原始原文 → 新译文
        self.renamed = {}     # 原始原文 → 新原文
        self.removed = {}     # 原始原文 → 原译文
        self._undo = []
        self._last_op = ""
        log.info("术语字典载入：%d 条（其中自动提取 %d 条）",
                 len(self.base), len(self.auto_keys))

    def _view_items(self):
        """当前视图：[(原始原文, 现状原文, 现状译文, 来源)]。"""
        items = []
        for src, dst in self.base.items():
            if src in self.removed:
                continue
            new_src = self.renamed.get(src, src)
            new_dst = self.changed.get(src, dst)
            origin = ORIGIN_AUTO if _norm(new_src) in self.auto_norm else ORIGIN_MANUAL
            items.append((src, new_src, new_dst, origin))
        for src, dst in self.added.items():
            items.append((src, src, dst, ORIGIN_MANUAL))
        return items

    def rows(self, query="", origin=ORIGIN_ALL, limit=VIEW_LIMIT_DEFAULT):
        """
        过滤后的列表行。
        返回 (rows, matched)：rows = [(原始原文, 现状原文, 现状译文, 来源), ...]
        matched = 命中总数（可能大于 len(rows)，因为 limit 截断）
        """
        q = (query or "").strip().lower()
        want = origin or ORIGIN_ALL
        rows = []
        matched = 0
        for item in self._view_items():
            _orig, src, dst, org = item
            if want == ORIGIN_AUTO and org != ORIGIN_AUTO:
                continue
            if want == ORIGIN_MANUAL and org != ORIGIN_MANUAL:
                continue
            if q and q not in src.lower() and q not in (dst or "").lower():
                continue
            matched += 1
            if limit is None or len(rows) < limit:
                rows.append(item)
        return rows, matched

    def stats(self):
        """(总条数, 未保存改动数, 自动提取条数)。"""
        return (len(self.base) + len(self.added) - len(self.removed),
                self.pending_count(), len(self.auto_keys))

    def pending_count(self):
        return (len(self.added) + len(self.changed)
                + len(self.renamed) + len(self.removed))

    def is_dirty(self):
        return self.pending_count() > 0

    def pending_text(self):
        """给状态栏用的一句话摘要。"""
        if not self.is_dirty():
            return "没有未保存的改动"
        parts = []
        if self.added:
            parts.append(f"新增 {len(self.added)}")
        if self.changed:
            parts.append(f"改译文 {len(self.changed)}")
        if self.renamed:
            parts.append(f"改名 {len(self.renamed)}")
        if self.removed:
            parts.append(f"删除 {len(self.removed)}")
        return "未保存：" + "、".join(parts) + "（点「保存」写入 term_dict.py）"

    def changed_rows(self):
        """有未保存改动的条目，供「保存前预览」用。"""
        out = []
        for src in self.removed:
            out.append(("删除", self.base.get(src, ""), src, ""))
        for src, new_src in self.renamed.items():
            out.append(("改名", src, new_src, ""))
        for src, new_dst in self.changed.items():
            out.append(("改译文", self.renamed.get(src, src),
                        self.base.get(src, ""), new_dst))
        for src, dst in self.added.items():
            out.append(("新增", src, dst, ""))
        return out

    # ================================================================
    # 撤回栈
    # ================================================================
    def _push_undo(self, desc):
        state = (dict(self.added), dict(self.changed),
                 dict(self.renamed), dict(self.removed))
        self._undo.append((desc, state))
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
        self._last_op = desc

    def can_undo(self):
        return bool(self._undo)

    def undo(self):
        """撤回上一步（未保存的）操作。返回 (ok, msg)。"""
        if not self._undo:
            return False, "没有可撤回的操作"
        desc, state = self._undo.pop()
        self.added, self.changed, self.renamed, self.removed = (
            dict(state[0]), dict(state[1]), dict(state[2]), dict(state[3]))
        self._last_op = ""
        return True, f"已撤回：{desc}"

    def _take_norm(self, exclude_orig=None):
        """当前视图里已被占用的归一化原文集合（可排除某一行）。"""
        taken = {}
        for orig, src, _dst, _org in self._view_items():
            if exclude_orig is not None and orig == exclude_orig:
                continue
            taken[_norm(src)] = src
        return taken

    # ================================================================
    # 编辑操作
    # ================================================================
    def add(self, src, dst):
        """新增一条（staged）。返回 (ok, msg)。"""
        src = (src or "").strip()
        dst = (dst or "").strip()
        why = why_invalid_new(src, dst)
        if why:
            return False, why
        hit = self._take_norm().get(_norm(src))
        if hit is not None:
            return False, f"已存在术语「{hit}」，请直接修改它（或在列表里搜索）"
        self._push_undo(f"新增「{src}」")
        self.added[src] = dst
        return True, f"已加入待保存队列：{src} → {dst}"

    def update(self, orig_src, new_src, new_dst):
        """修改一行的原文 / 译文（staged）。返回 (ok, msg)。"""
        new_src = (new_src or "").strip()
        new_dst = (new_dst or "").strip()
        if not new_src or not new_dst:
            return False, "原文与译文都不能为空"

        if orig_src in self.added:
            # 待新增条目：直接改，校验按「新增」算
            why = why_invalid_new(new_src, new_dst)
            if why:
                return False, why
            hit = self._take_norm(exclude_orig=orig_src).get(_norm(new_src))
            if hit is not None:
                return False, f"已存在术语「{hit}」"
            if self.added.get(orig_src) == new_dst and orig_src == new_src:
                return True, "没有变化"
            self._push_undo(f"修改「{orig_src}」")
            # 保持添加顺序：原地重建
            new_added = {}
            for k, v in self.added.items():
                if k == orig_src:
                    new_added[new_src] = new_dst
                else:
                    new_added[k] = v
            self.added = new_added
            return True, f"已修改：{new_src} → {new_dst}"

        if orig_src not in self.base:
            return False, f"术语「{orig_src}」不存在（可能已删除，请重新载入）"

        cur_src = self.renamed.get(orig_src, orig_src)
        cur_dst = self.changed.get(orig_src, self.base.get(orig_src, ""))
        if new_src == cur_src and new_dst == cur_dst:
            return True, "没有变化"

        if new_src != cur_src:
            why = why_invalid_key(new_src)
            if why:
                return False, why
            hit = self._take_norm(exclude_orig=orig_src).get(_norm(new_src))
            if hit is not None:
                return False, f"已存在术语「{hit}」，不能改成重复的原文"

        self._push_undo(f"修改「{cur_src}」")
        if new_src != orig_src:
            self.renamed[orig_src] = new_src
        else:
            self.renamed.pop(orig_src, None)
        if new_dst != self.base.get(orig_src, ""):
            self.changed[orig_src] = new_dst
        else:
            self.changed.pop(orig_src, None)
        return True, f"已修改：{new_src} → {new_dst}"

    def delete(self, orig_srcs):
        """把若干行标记为待删除（staged）。返回 (ok, msg)。"""
        keys = [k for k in (orig_srcs or []) if k]
        if not keys:
            return False, "没有选中任何术语"
        dropped = 0
        staged = []
        for orig in keys:
            if orig in self.added or (orig in self.base
                                      and orig not in self.removed):
                if orig not in staged:
                    staged.append(orig)
        if not staged:
            return False, "选中的条目已经不在字典里了"
        self._push_undo(f"删除 {len(staged)} 条术语")
        for orig in staged:
            if orig in self.added:
                self.added.pop(orig, None)
                dropped += 1
                continue
            self.removed[orig] = self.base.get(orig, "")
            # 删掉的行不再参与改名 / 改译文，否则保存时按新名字删不掉
            self.renamed.pop(orig, None)
            self.changed.pop(orig, None)
        left = len(staged) - dropped
        return True, (f"已标记删除 {left} 条（点「保存」生效，可「撤回」）"
                      + ("，另有 %d 条待新增条目已移出队列" % dropped
                         if dropped else ""))

    def delete_all_auto(self):
        """把「自动提取（AUTO 块）」里的术语一次性标记删除。返回 (ok, msg)。"""
        targets = [orig for orig, src, _d, org in self._view_items()
                   if org == ORIGIN_AUTO and orig not in self.removed]
        if not targets:
            return False, "当前字典里没有自动提取的术语"
        self._push_undo(f"一键删除自动提取术语 {len(targets)} 条")
        for orig in targets:
            if orig in self.added:
                self.added.pop(orig, None)
                continue
            self.removed[orig] = self.base.get(orig, "")
            self.renamed.pop(orig, None)
            self.changed.pop(orig, None)
        return True, (f"已标记删除 {len(targets)} 条自动提取术语"
                      "（点「保存」生效，取消请点「撤回」）")

    def reset(self):
        """丢弃所有未保存改动。返回丢弃条数。"""
        n = self.pending_count()
        if n:
            self._push_undo(f"放弃 {n} 处未保存改动")
        self.added, self.changed, self.renamed, self.removed = {}, {}, {}, {}
        return n

    # ================================================================
    # 写盘
    # ================================================================
    def save(self):
        """
        把未保存改动一次性写进 term_dict.py。
        返回 report 字典：{deleted, renamed, changed, added, errors:[...]}
        """
        report = {"deleted": 0, "renamed": 0, "changed": 0, "added": 0,
                  "errors": []}
        if not self.is_dirty():
            return report

        # ① 删除（先删，给下面的改名 / 新增腾出原文名）
        if self.removed:
            try:
                report["deleted"] = TS.delete_term_keys(list(self.removed))
            except Exception as e:
                report["errors"].append(f"删除失败：{e}")

        # ② 改名
        if self.renamed:
            try:
                report["renamed"] = TS.rename_term_keys(dict(self.renamed))
            except Exception as e:
                report["errors"].append(f"改名失败：{e}")

        # ③ 改译文（用改名后的新原文）
        if self.changed:
            updates = {self.renamed.get(k, k): v
                       for k, v in self.changed.items()}
            try:
                report["changed"] = TS.save_term_values(updates)
            except Exception as e:
                report["errors"].append(f"改译文失败：{e}")

        # ④ 新增（manual=True → 写进手工区，不被「一键删除自动术语」波及）
        for src, dst in list(self.added.items()):
            try:
                ok, msg, _key = TS.add_term(src, dst, manual=True)
            except Exception as e:
                ok, msg = False, str(e)
            if ok:
                report["added"] += 1
            else:
                report["errors"].append(f"新增「{src}」失败：{msg}")

        self.reload()
        log.info("术语字典保存完成：删除 %d / 改名 %d / 改译文 %d / 新增 %d，"
                 "失败 %d", report["deleted"], report["renamed"],
                 report["changed"], report["added"], len(report["errors"]))
        return report
