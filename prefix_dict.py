# -*- coding: utf-8 -*-
r"""
句首控制码字典：
  · 缓存句子开头的连续控制码串（如 \w[speech hgss 3]\tg[???]）
  · 用户手工翻译后复用
  · 翻译时剥离，回写时拼回
"""
import json
import os
import re

import config
from logger import get_logger, log_once

log = get_logger("prefix_dict")

# 存储位置：与 term_dict.py 同目录
DICT_FILE = os.path.join(config.BASE_DIR, "prefix_dict.json")

# ★「应用术语」处理的是「名字标签」里的内容：\tg[...] 与 \xn[...]
#   （三段：\tg[ / 内容 / ]），内容段才是可替换的角色名。
#   ★ \xn[] 是 setTextMode("\\ml[名字]\\xn[名字]") 那种写法里的名字框，
#     内容同样是给玩家看的角色名 —— 只替换 \tg[] 的话，用 \xn[] 的游戏
#     （如 宝可梦重聚 / Edge Rising）永远命不中。
NAME_TAG_RE = re.compile(r'(\\(?:tg|xn)\[)([^\]]*)(\])')

# 兼容旧名字（以前只有 \tg[]，外部若按 TG_RE 引用也能用）
TG_RE = NAME_TAG_RE

# 全局内存缓存
_entries = {}     # {前缀原文: 前缀译文}  空串表示待翻译
_loaded = False


def normalize_value(value):
    r"""
    前缀译文的规范形态：**去掉首尾空白**。

    ★ 前缀 = 句首连续控制码串，本身不可能以空格 / 制表符结尾；
      字典里出现 `\xn[Kao]\b\t` 这种（手工编辑时手滑打了个 Tab）会拼出
      `\xn[卡奥]\b<Tab>正文`，既在游戏里多一格空白，也让 `strip_prefix_echo`
      按字符串前缀比对全部失败 —— 于是这些句子每次「应用前缀字典」都被当成
      「前缀变了」，正文被反复重拼。
    ★ 只剩空白的译文一律归零（= 待翻译），交给「应用术语」或人工补。
    """
    if value is None:
        return ""
    return str(value).strip()


# ================================================================
# 读写
# ================================================================
def _load():
    global _entries, _loaded
    if _loaded:
        return

    if not os.path.exists(DICT_FILE):
        _entries = {}
        _loaded = True          # 文件不存在是正常状态，不用反复去查
        return

    try:
        with open(DICT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "entries" in data:
            raw = dict(data.get("entries") or {})
        elif isinstance(data, dict):
            # 兼容裸 dict 格式
            raw = dict(data)
        else:
            raw = {}
        # ★ 读入即规范化：键与译文都去首尾空白（见 normalize_value）。
        #   前缀是控制码串，本来就不会以空白开头/结尾，带空白只可能是手误，
        #   留着永远匹配不上。
        _entries = {str(k).strip(): normalize_value(v) for k, v in raw.items()
                    if str(k).strip()}
        _loaded = True
        log.info("前缀字典加载：%d 条（%s）", len(_entries), DICT_FILE)
    except Exception as e:
        # ★ 读失败时**不要**把 _loaded 置 True：否则这一次异常会把字典
        #   永久钉成空的，后面再怎么调都读不回来（只能重启程序）。
        log.warning("前缀字典加载失败（下次会重试）：%s", e)
        _entries = {}


def _save():
    """原子写回。"""
    tmp = DICT_FILE + ".tmp"
    data = {
        "version": 1,
        "entries": _entries,
    }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DICT_FILE)


def reload_dict():
    """强制从磁盘重读。"""
    global _loaded
    _loaded = False
    _load()


# ================================================================
# 查询 / 注册
# ================================================================
def get_translation(prefix):
    """
    返回译后前缀；未注册或未翻译返回 None。
    """
    _load()
    if not prefix:
        return None
    v = _entries.get(prefix)
    if v is None:
        return None
    v = normalize_value(v)
    return v or None      # 空串视为未翻译


def register_prefix(prefix, fill_by_terms=True):
    """
    注册新前缀。已存在返回 False；新增返回 True。

    ★ fill_by_terms=True：若该前缀里命中术语字典，直接把「术语替换后的前缀」
      作为它的译文填进去（不用再手工翻一遍）。
      例：\\tg[Owen] 命中术语 Owen=欧文 → 译文直接写成 \\tg[欧文]。
      没命中任何术语时仍保持空值（= 待翻译）。
    """
    _load()
    if not prefix:
        return False
    if prefix in _entries:
        return False

    value = ""
    if fill_by_terms:
        sub = substitute_terms(prefix)
        if sub and sub != prefix:
            value = normalize_value(sub)
            log.info("新前缀 %r 命中术语，已自动填入译文 %r", prefix, value)

    _entries[prefix] = value
    return True


def substitute_terms(prefix):
    """
    前缀里命中术语字典的部分，替换为术语译文。
    典型场景：\\tg[Owen] 中的 Owen 命中术语 → \\tg[欧文]。

    术语表不可用、或替换过程中出错时原样返回，绝不让前缀处理拖垮主流程。
    """
    if not prefix:
        return prefix
    try:
        import processor as _PR          # 惰性导入，避免与 processor 形成循环依赖
        _PR.load_terms()
        out = _PR.apply_terms(prefix)
        return out if out else prefix
    except Exception as e:               # 术语表损坏/未配置都不影响翻译
        log.debug("前缀术语替换失败（已回退原前缀）：%s", e)
        return prefix


def _apply_terms_to_text(text):
    """对一段纯文本做术语替换；术语表不可用时原样返回。"""
    if not text:
        return text
    try:
        import processor as _PR
        _PR.load_terms()
        out = _PR.apply_terms(text)
        return out if out else text
    except Exception as e:
        log.debug("术语替换失败（已回退原文）：%s", e)
        return text


def _terms_hit_in(text):
    """返回 text 中命中的术语 [(原文, 译文), ...]；术语表不可用时返回 []。

    ★ 只认整词（allow_derived=False）：前缀预填是「把 \tg[] 里的名字换成译文」，
      派生匹配（Altarianites → Altaria）在这里会把后缀吃掉，故不启用。
    """
    if not text:
        return []
    try:
        import processor as _PR
        _PR.load_terms()
        return _PR.find_terms(text, allow_derived=False) or []
    except Exception as e:
        log.debug("术语命中检测失败：%s", e)
        return []


def substitute_tg_terms(prefix):
    r"""
    只把前缀里名字标签（\tg[...] / \xn[...]）的内部文字按术语表替换
    （其余部分原样保留）。

    例：\w[speech hgss 3]\tg[Owen] → \w[speech hgss 3]\tg[欧文]
        \ml[Lilith]\xn[Lilith]     → \ml[Lilith]\xn[莉莉丝]
    没命中任何术语时原样返回。

    ★ 「应用术语」的作用范围就限定在这两种名字标签，避免误伤
      \w[speech hgss 3] / \ml[none] 之类必须保持原样的控制码参数。
    """
    if not prefix or not NAME_TAG_RE.search(prefix):
        return prefix
    try:
        def _repl(m):
            inner = m.group(2)
            if not inner.strip():
                return m.group(0)
            new_inner = _apply_terms_to_text(inner)
            return m.group(1) + new_inner + m.group(3)

        return NAME_TAG_RE.sub(_repl, prefix)
    except Exception as e:
        log.warning("前缀名字标签（\\tg[] / \\xn[]）术语替换失败（已回退）：%s",
                    e)
        return prefix


def tg_terms_of(prefix):
    r"""
    列出前缀中名字标签（\tg[...] / \xn[...]）内部命中的术语
    [(原文, 译文), ...]（已去重）。
    """
    if not prefix or not NAME_TAG_RE.search(prefix):
        return []
    out, seen = [], set()
    for m in NAME_TAG_RE.finditer(prefix):
        for src, dst in _terms_hit_in(m.group(2)):
            key = (src or "").lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((src, dst))
    return out


def scan_terms_for_tg():
    r"""
    扫描整本前缀字典，预演「应用术语」的结果（不写盘）。

    只对「当前生效文本」里名字标签（\tg[] / \xn[]）的内容做术语替换：
      · 已有译文 → 在译文基础上替换（保留用户其它手工改动）
      · 译文为空 → 在原文基础上替换

    返回 (changes, stats)
      changes: [{"src", "old", "new", "terms":[(原文, 译文), ...]}, ...]
      stats  : {"total", "changed", "untouched"}
    """
    _load()
    changes = []
    stats = {"total": len(_entries), "changed": 0, "untouched": 0}

    for src, dst in _entries.items():
        base = dst or src
        terms = tg_terms_of(base)
        if not terms:
            stats["untouched"] += 1
            continue
        new = substitute_tg_terms(base)
        if new == dst:
            stats["untouched"] += 1
            continue
        changes.append({"src": src, "old": dst, "new": new, "terms": terms})
        stats["changed"] += 1

    return changes, stats


def apply_terms_for_tg():
    r"""
    把术语表套用到前缀字典并落盘（只替换名字标签 \tg[...] / \xn[...]
    的内容）。
    返回 (changes, stats)，与 scan_terms_for_tg() 结构一致。
    """
    changes, stats = scan_terms_for_tg()
    if not changes:
        return changes, stats

    n = update_many({c["src"]: c["new"] for c in changes})
    _save()
    log.info("前缀字典「应用术语」：命中 %d 条，写入 %d 条",
             len(changes), n)
    return changes, stats


def _ctrl_boundaries(text):
    r"""
    返回 text 里「每个控制码结束」的位置列表（升序）。

    例：`\xn[Kao]\b\.` → [9, 11, 13]（对应 `\xn[Kao]` / `\b` / `\.` 的末尾）。
    认不出来（processor 不可用）时返回 []。
    """
    if not text:
        return []
    try:
        import processor as _PR
    except Exception:                    # noqa: BLE001
        return []
    out, i, n = [], 0, len(text)
    while i < n:
        m = _PR.ALL_CTRL_RE.match(text, i)
        if not m or m.end() <= i:
            break
        i = m.end()
        out.append(i)
    return out


def _known_split(prefix):
    r"""
    在字典里按「最长已知前缀」把 prefix 拆成 (已知前缀, 余下控制码)。

    ★ 为什么需要：`split_prefix` 会把句首**一整串**控制码都算进前缀，
      而字典里往往只登记了其中一部分 —— 例如字典有 `\xn[Yahn Deer]\r`，
      实际句子却是 `\xn[Yahn Deer]\r\..\..\...`（多出三个 `\.` 等待码）。
      不拆的话整个前缀「不认识」，用户改了字典也永远应用不上。
    ★ 找不到任何已知前缀时返回 ("", prefix)。
    """
    if not prefix:
        return "", prefix
    if prefix in _entries:
        return prefix, ""
    for i in reversed(_ctrl_boundaries(prefix)):
        if i < len(prefix) and prefix[:i] in _entries:
            return prefix[:i], prefix[i:]
    return "", prefix


def is_known(prefix):
    """前缀（或它的某个更短的控制码前缀）在字典里登记过没有。"""
    _load()
    if not prefix:
        return False
    if prefix in _entries:
        return True
    return bool(_known_split(prefix)[0])


def apply_prefix(prefix):
    """
    返回应使用的译后前缀：
      · 已翻译 → 译后前缀
      · 未翻译 → 原前缀，但其中命中术语的部分先替换成术语译文
      · 整体没登记、但它的某个更短的前缀登记过 → 只替换那一段，余下原样保留
    """
    t = get_translation(prefix)
    if t:
        return t
    head, tail = _known_split(prefix)
    if head and tail:
        th = get_translation(head)
        return (th if th else substitute_terms(head)) + tail
    return substitute_terms(prefix)


def strip_prefix_echo(text, src_prefix="", src_body=""):
    r"""
    剥掉译文开头重复出现的「前缀回显」。

    背景：译后前缀是拼回去的，但缓存里存的是**已经拼过前缀的整行**，
    而历史上写进去的那版前缀可能和现在字典里的不一样
    （比如上次是术语替换版 \tg[丹帝, el 伽勒尔冠军]，这次用户改成了
    \tg[丹帝, 伽勒尔的冠军]）。按字符串比对认不出来，就会出现
    `\tg[新]\tg[旧]正文` 这种新旧并存。

    做法：
      ① 先用「当前应生效的译后前缀 / 原文前缀 / 术语替换版」逐个比对剥掉
      ② 都不匹配时兜底：**仅当原文正文本身不以控制码开头**，
         才把译文开头的那段控制码当作旧前缀剥掉（避免误伤正文自带的控制码）

    text      —— 待处理的译文（可能已经带了旧前缀）
    src_prefix—— 该行原文的前缀（可为空）
    src_body  —— 原文去掉前缀后的正文（用于兜底判断，可为空）
    """
    if not text:
        return text

    # ① 已知的几种前缀写法
    cands = []
    if src_prefix:
        cands.append(apply_prefix(src_prefix))
        cands.append(src_prefix)
        cands.append(substitute_terms(src_prefix))
    for c in cands:
        if c and text.startswith(c):
            return text[len(c):]

    # ② 兜底：原文正文不以控制码开头 → 译文开头的控制码串只可能是前缀回显
    if src_prefix:
        try:
            import processor as _PR
            if src_body:
                h_src, _ = _PR.split_prefix(src_body)
                if h_src:
                    return text          # 正文自己就带控制码，不动它
            head, rest = _PR.split_prefix(text)
            if head:
                # ★ 一句话一条的话，几千条对白就是几千行日志 —— 只提示一次
                log_once(("prefix_echo",), "剥掉译文开头残留的旧前缀：%r"
                         "（同类提示本次只显示这一条）", head,
                         logger=log)
                return rest
        except Exception as e:
            log.debug("前缀回显剥离失败（已回退原文本）：%s", e)

    return text


def _ctrl_signature(text):
    r"""
    前缀的「控制码骨架」：把名字标签 `\tg[X]` / `\xn[X]` 括号里的名字抹掉，
    只留控制码本身。用来判断「译文前缀是否偷偷换掉了控制码」。
    """
    if not text:
        return []
    try:
        import processor as _PR
        codes = [m.group(0) for m in _PR.ALL_CTRL_RE.finditer(text)]
    except Exception:                    # noqa: BLE001
        return []
    return [NAME_TAG_RE.sub(r"\1\3", c) if NAME_TAG_RE.search(c) else c
            for c in codes]


def ctrl_mismatches(limit=0):
    r"""
    列出「译文前缀的控制码与原文前缀不一致」的条目（字典里手滑打错的情况）。

    例：`\xn[Hate]\b` 的译文写成 `\xn[海特]\r` —— `\b`（加粗）变成了
    `\r`（复位），拼进译文后游戏里的显示效果就变了。
    翻译本身只该改括号里的名字，控制码应当逐个保持一致。

    返回 [(前缀原文, 译文, "原文码 → 译文码"), ...]；limit>0 时最多返回这么多条。
    """
    _load()
    out = []
    for src, dst in _entries.items():
        if not dst:
            continue
        a = _ctrl_signature(src)
        b = _ctrl_signature(dst)
        if a == b:
            continue
        diff = []
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else "（无）"
            y = b[i] if i < len(b) else "（无）"
            if x != y:
                diff.append(f"{x} → {y}")
        out.append((src, dst, "、".join(diff[:3]) or "控制码数量不同"))
        if limit and len(out) >= limit:
            break
    return out


def update_many(mapping):
    """批量写入 {前缀原文: 译文}，返回改动条数（译文会去首尾空白）。"""
    _load()
    n = 0
    for k, v in (mapping or {}).items():
        if not k:
            continue
        if _entries.get(k) != normalize_value(v):
            _entries[k] = normalize_value(v)
            n += 1
    return n


def remove(prefix):
    """删除一条前缀。"""
    _load()
    return _entries.pop(prefix, None) is not None


def all_entries():
    """返回 {前缀原文: 译文} 的副本。"""
    _load()
    return dict(_entries)


def save():
    """外部修改后调用，落盘。"""
    _save()


# ================================================================
# 批量统计
# ================================================================
def stats():
    _load()
    total = len(_entries)
    done = sum(1 for v in _entries.values() if v)
    pending = total - done
    return {"total": total, "done": done, "pending": pending}


def list_pending():
    """返回 [(前缀原文, 前缀译文), ...]，只列未翻译的。"""
    _load()
    return [(k, v) for k, v in sorted(_entries.items()) if not v]