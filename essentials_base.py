# -*- coding: utf-8 -*-
"""
Essentials「基本函数」基准库 —— 版本识别 + 改动检测。

背景
----
给游戏开 $DEBUG 之前，得先确认它用的还是不是原版引擎：
一旦作者改过引擎的基本函数（Compiler / Main / MessageTypes / PluginManager…），
我们往里写 $DEBUG=true、或者把 Compiler.main 换成空操作，都可能踩空。

基准的形态（与 RMXP 脚本编辑器一致）
------------------------------------
脚本编辑器左边那一栏是**一个个脚本**（Settings / RGSS2Compatibility /
Game_Temp / … / Compiler / Main），点开一个，右边是它的代码。

所以基准表按「**脚本名 → {函数名 → 函数体指纹}**」组织：

    "Main":     {"mainFunction": "ab12…", "mainFunctionDebug": "cd34…", …}
    "Compiler": {"main": "ef56…", "compile_all": "…", …}

比对时同样按脚本名找游戏里那份脚本，再对它里面的函数：

    · 脚本对上了，函数指纹一致   → 没动过
    · 脚本对上了，函数指纹不同   → 作者改过引擎
    · 基准里有、游戏里没有       → 缺了（整个脚本找不到也算）
    · 游戏里有、基准里没有       → **作者自己加的，不算问题**
    · Settings 脚本              → **忽略**（那是作者自己的游戏设置，
                                   动它是天经地义）

官方 Essentials（16 / 17 / 18 / 19 / 19.1 / 20 / 20.1 / 21 / 21.1）各生成一份，
存成 JSON 随程序分发（scripts/essentials_base/*.json）。

★ 指纹不是拿全文做哈希：先去掉注释与缩进差异，避免「只加了注释 / 只改了缩进」
  被误判成改过引擎。
"""
import hashlib
import io
import json
import os
import re
import time

import config
import game_scripts as GS
from logger import get_logger

log = get_logger("essentials_base")

# 基准表存放位置（scripts/ 会被 --add-data 打进 exe）
BASE_DIR_NAME = os.path.join("scripts", "essentials_base")

# 比对时忽略的脚本：Settings 是作者自己的游戏配置，改它天经地义
_IGNORED_SCRIPTS = ("settings",)

# ================================================================
# Ruby 源码 → 函数定义
# ================================================================
# def 名字：普通名 / self.xxx / 运算符（[] + - == …）
_DEF_RE = re.compile(
    r"^([ \t]*)def\s+((?:self\s*\.\s*)?"
    r"[A-Za-z_][A-Za-z0-9_]*[?!]?|"
    r"(?:self\s*\.\s*)?(?:\[\]=?|<<|>>|[+\-*/%]=?|<=>|<=|>=|==|===|!=|!|~|&|\||\^))")

# 会开一个块的开头（用于配对 end）
_OPEN_RE = re.compile(
    r"^(module|class|def|if|unless|while|until|for|case|begin)\b")
# 行尾的 do（each / loop / times …）
_DO_RE = re.compile(r"\bdo\b\s*(\|[^|]*\|)?\s*$")

# 单行 def（def foo; end）不再往下配对
_ONE_LINE_DEF = re.compile(r"^([ \t]*)def\b.*\bend\b\s*$")


def is_ignored_script(name):
    """比对时要不要跳过这个脚本（目前只跳 Settings）。"""
    return str(name or "").strip().lower() in _IGNORED_SCRIPTS


def _strip_comment(line):
    """
    去掉行尾注释（` # xxx`）。

    ★ `#` 在引号里（"#{}" 插值也算）时不能删 —— 用「# 之前引号个数是否为偶数」
      判断，够用且便宜。
    """
    pos = -1
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if c in "\"'`":
            pos = i
            break
        if c == "#":
            break
        i += 1
    # 找到第一个 # 或第一个引号
    idx = line.find("#")
    if idx < 0:
        return line
    if pos >= 0 and pos < idx:
        return line            # 引号在 # 之前：可能是字符串里的 #，保守不删
    if idx > 0 and line[idx - 1] not in " \t":
        return line            # 紧贴着代码，多半是字符串插值，不删
    return line[:idx].rstrip()


def _normalize_body(lines):
    """函数体 → 归一化文本（去注释、去空行、去缩进，用于算指纹）。"""
    out = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        line = _strip_comment(line)
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def _fingerprint(text):
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12]


def scan_defs(text):
    """
    扫一份 Ruby 源码 → {限定名: 指纹}。

    限定名形如 `Compiler.main` / `MessageTypes#get` / `Scene_Map#update`；
    模块里的 `def self.foo` 记成 `MessageTypes.foo`。

    ★ 用「缩进配对 end」定位每个函数的结尾：Essentials 官方脚本缩进严格，
      作者魔改过的脚本一般也沿用，够准；基线与实际扫描用的是同一套算法，
      偶有偏差也是两边一起偏，不会凭空报一堆「改了」。
    """
    lines = text.split("\n")
    stack = []          # [(缩进, 名字, 是不是 def)]
    out = {}
    for i, raw in enumerate(lines):
        line = raw.rstrip("\r")
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())

        # ---- 闭合 ----
        if re.match(r"^end\b", stripped):
            while stack and stack[-1][0] >= indent:
                stack.pop()
            continue

        # ---- 开块 ----
        if _ONE_LINE_DEF.match(line):
            continue
        m = _DEF_RE.match(line)
        if m:
            fname = re.sub(r"\s+", "", m.group(2))
            qual = ".".join([s[1] for s in stack] + [fname])
            stack.append((indent, fname, True))
            # 找这一层的 end
            depth = 0
            end_i = len(lines)
            for j in range(i + 1, len(lines)):
                s2 = lines[j].strip()
                ind2 = len(lines[j]) - len(lines[j].lstrip())
                if _OPEN_RE.match(s2) or _DO_RE.search(s2.rstrip()):
                    if ind2 >= indent or _DO_RE.search(s2.rstrip()):
                        depth += 1
                elif re.match(r"^end\b", s2):
                    if depth == 0 and ind2 <= indent:
                        end_i = j
                        break
                    depth -= 1
            body = _normalize_body(lines[i + 1:end_i])
            out[qual] = _fingerprint(body)
            continue

        m = re.match(r"^(module|class)\s+([A-Za-z_][\w:]*)", stripped)
        if m:
            stack.append((indent, m.group(2), False))
            continue

        if _OPEN_RE.match(stripped) or _DO_RE.search(line.rstrip()):
            stack.append((indent, "_", False))
            continue
    return out


# ================================================================
# 本工具自己写进脚本的那几行（$DEBUG=true / 编译闸门）——比对时要先抹掉，
# 否则第二次检测会把「我们自己打的补丁」报成「作者改过引擎」。
# ★ 标记必须足够独特：游戏代码里就有叫 pkmn 的变量（`[pkmn]`、
#   `newPokemon[pkmn]`），用 `[pkmn]` 当标记会把人家正常代码整行删掉。
# ================================================================
PATCH_MARK = "[pkmn-debug]"
PATCH_LINE_RE = re.compile(
    r"^[ \t]*(?:\$DEBUG=true|[^\n]*" + re.escape(PATCH_MARK) + r"[^\n]*)"
    r"[ \t]*\r?$", re.M)


def strip_own_patch(text):
    """去掉本工具注入的行（比对基准前先清一遍，保证幂等）。"""
    return PATCH_LINE_RE.sub("", text)


def scan_game_scripts(game_dir):
    """
    扫游戏脚本 → {脚本名: {限定名: 指纹}}。

    ★ 脚本名就是 RMXP 脚本编辑器左边那一栏（见 game_scripts.script_name）。
    ★ 同名脚本（同人游戏会把一个名字用两次，POG 里就有两个 `Trainer`）
      **合并**：函数取并集，先出现的指纹优先。
      只留第一份的话，第二份的函数会被整个认成「缺失」。
    """
    out = {}
    for _m, _k, _p, name, text in GS.iter_named_scripts(game_dir):
        funcs = scan_defs(strip_own_patch(text))
        if name in out:
            for fname, fp in funcs.items():
                out[name].setdefault(fname, fp)
        else:
            out[name] = funcs
    return out


# ================================================================
# 基准表
# ================================================================
def base_dir():
    """基准表目录（打包后从 _MEIPASS / exe 同目录找）。"""
    return config.resource_path(BASE_DIR_NAME)


def list_baselines():
    """已内置的基准版本 → ["16", "17", …, "21.1"]（按版本号排序）。"""
    d = base_dir()
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".json"):
            continue
        stem = f[:-5]
        if stem.startswith("v"):
            stem = stem[1:]
        out.append(stem)
    return sorted(out, key=_vkey)


def _vkey(text):
    try:
        return tuple(int(x) for x in str(text).split("."))
    except ValueError:
        return (999,)


def baseline_path(version):
    d = base_dir()
    return os.path.join(d, f"v{version}.json")


def load_baseline(version):
    """读基准表 → {脚本名: {限定名: 指纹}}；没有这个版本返回 None。"""
    p = baseline_path(version)
    if not os.path.isfile(p):
        return None
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.warning("读基准表 %s 失败：%s", p, e)
        return None
    scripts = data.get("scripts")
    return scripts if isinstance(scripts, dict) else None


def flat_funcs(scripts):
    """{脚本名: {函数: 指纹}} → {「脚本.函数」: 指纹}（挑基准时算重合度用）。"""
    out = {}
    for name, funcs in (scripts or {}).items():
        for fname, fp in funcs.items():
            out[f"{name}.{fname}"] = fp
    return out


def _game_index(scripts):
    """
    {脚本名: {函数: 指纹}} → ({限定名: 指纹}, {限定名: 脚本名})

    ★ 只按下标：同一个限定名出现在多个脚本里时取第一份。
    ★ 用途：作者常把函数从 A 脚本**搬家**到 B 脚本（同人游戏改结构很常见），
      这时「按脚本名配对」会把它误报成「缺失」——
      配不上时拿这张全局表再查一次就知道它只是换了地方。
    """
    flat, owner = {}, {}
    for name, funcs in (scripts or {}).items():
        for fname, fp in funcs.items():
            if fname in flat:
                continue
            flat[fname] = fp
            owner[fname] = name
    return flat, owner


# ================================================================
# 版本
# ================================================================
def detect_version(game_dir):
    """读游戏里的 Essentials::VERSION（读不到返回 ""）。"""
    return GS.essentials_version(game_dir)


def pick_baseline_version(version):
    """
    按游戏版本挑一份最接近的基准表。

      · 完全一致优先（21.1 → v21.1）
      · 否则取同主版本里不高于它的最近一个（21 → v21）
      · 都没有就取最新的那份，并把 exact 标成 False
    返回 (版本字符串 or None, 是否完全一致)
    """
    ver = (version or "").strip()
    known = list_baselines()
    if not known:
        return None, False
    if ver in known:
        return ver, True
    try:
        cur = tuple(int(x) for x in ver.split(".")[:2])
    except (ValueError, AttributeError):
        return known[-1], False
    same_major = [v for v in known
                  if _vkey(v)[:1] == cur[:1] and _vkey(v) <= cur]
    if same_major:
        return same_major[-1], False
    lower = [v for v in known if _vkey(v) <= cur]
    return (lower[-1] if lower else known[-1]), False


def best_baseline(scripts, min_ratio=0.5):
    """
    版本号靠不住时（老游戏 / 魔改版），按「函数指纹重合度」挑基准表。

    返回 (版本字符串 or None, 重合比例)。挑 `一致数 / 基准总数` 最高的那份；
    最高那份也不到 min_ratio 就返回 None（说明这游戏引擎改得太狠，比不出来）。
    """
    known = list_baselines()
    cur = flat_funcs(scripts)
    best, best_r = None, 0.0
    for v in known:
        base = load_baseline(v)
        if not base:
            continue
        want = flat_funcs(base)
        if not want:
            continue
        same = sum(1 for k, h in want.items() if cur.get(k) == h)
        r = same / float(len(want))
        if r > best_r:
            best, best_r = v, r
    if best_r < min_ratio:
        return None, best_r
    return best, best_r


# ================================================================
# 比对
# ================================================================
MAX_REPORT = 40          # 「改了 / 缺了」最多列多少条


def compare(game_dir, version=None, emit=None, limit=MAX_REPORT):
    """
    把游戏脚本和官方基准对一遍（按「脚本名 → 函数」）。

    Settings 脚本**不参与比对**；作者新增的脚本 / 函数只统计、不算问题。

    返回 dict：
      version / baseline / exact
      scripts_total   基准里参与比对的脚本数
      scripts_missing 基准里有、游戏里找不到的脚本名（信息性）
      scripts_added   游戏里有、基准里没有的脚本名（作者加的，不算问题）
      total / same / changed / missing
      moved           基准里在 A 脚本、游戏里搬到了 B 脚本，且内容一致
      changed_n / missing_n / added_n / moved_n
      ok              True = 没有「被改 / 缺失」
      tight           True = 全部一致
      reason          没比成的说明
    """
    def say(msg):
        if emit:
            emit(msg)

    ver = version or detect_version(game_dir)
    cur_scripts = scan_game_scripts(game_dir)
    if not cur_scripts:
        return _empty(ver, "这个游戏的脚本读不出来，跳过比对")

    bver, exact = pick_baseline_version(ver)

    # ★ v16 脚本里**根本没有版本号常量**（v17 起才有 ESSENTIALSVERSION），
    #   所以「读不到版本号」在这里是常态，不是异常 —— 直接按指纹重合度挑基准，
    #   不当成「版本号对不上」来吓唬用户。
    if not ver:
        auto, ratio = best_baseline(cur_scripts)
        if auto:
            say(f"[检测] 脚本里没有版本号（v16 起才有这个常量），"
                f"按函数指纹认出是 v{auto}（重合 {ratio:.0%}）")
            bver, exact = auto, True
    # ★ 版本号读出来了、却和这份基准对不上时，按指纹重合度重挑一份
    #   （老游戏、魔改版、把版本号改掉的同人作都靠这一步兜住）
    elif bver:
        probe = load_baseline(bver) or {}
        want = flat_funcs(probe)
        cur = flat_funcs(cur_scripts)
        hit = sum(1 for k, h in want.items() if cur.get(k) == h)
        if not want or hit / float(len(want)) < 0.5:
            auto, ratio = best_baseline(cur_scripts)
            if auto and auto != bver:
                say(f"[检测] 版本号写的是 {ver}，与基准 v{bver} 对不上"
                    f"（只认出 {hit} 个），改按指纹重合度取 v{auto}"
                    f"（{ratio:.0%}）")
                bver, exact = auto, False

    if not bver:
        return _empty(ver, "没有内置任何 Essentials 基准表，"
                           "或这份引擎改得太狠认不出来，跳过比对")

    base_scripts = load_baseline(bver)
    if base_scripts is None:
        return _empty(ver, f"基准表 v{bver} 读不出来，跳过比对")

    # 基准里参与比对的脚本（Settings 忽略）
    cmp_names = [n for n in base_scripts if not is_ignored_script(n)]
    base_norm = {_norm(n): n for n in cmp_names}
    game_norm = {_norm(n): n for n in cur_scripts}

    total = sum(len(base_scripts[n]) for n in cmp_names)
    same = 0
    changed, missing = [], []
    moved = []
    scripts_missing, scripts_added = [], []
    added_funcs = 0
    # 「限定名 → 指纹 / 它在哪个脚本」的全局索引（查函数搬家用）
    g_flat, g_owner = _game_index(cur_scripts)

    for bn in cmp_names:
        want_funcs = base_scripts[bn]
        gname = game_norm.get(_norm(bn))
        if gname is None:
            scripts_missing.append(bn)
        got_funcs = cur_scripts[gname] if gname is not None else {}
        for fname, want in want_funcs.items():
            got = got_funcs.get(fname)
            if got is None:
                # 不在这个脚本里 → 全局再找一次（可能只是被搬了家）
                other = g_flat.get(fname)
                if other is None:
                    missing.append((bn, fname))
                elif other == want:
                    same += 1
                    moved.append((bn, fname, g_owner.get(fname, "")))
                else:
                    changed.append((g_owner.get(fname) or bn, fname,
                                    other, want))
            elif got != want:
                changed.append((bn, fname, got, want))
            else:
                same += 1
        for fname in got_funcs:
            if fname not in want_funcs:
                added_funcs += 1

    # 游戏里多出来的脚本（作者自己加的，不算问题）
    for gname in cur_scripts:
        if _norm(gname) not in base_norm:
            scripts_added.append(gname)

    changed.sort()
    missing.sort()
    moved.sort()
    scripts_missing.sort()
    scripts_added.sort()
    # ★ 判「有没有问题」只看**函数**：被改 / 找不到。
    #   整个脚本没了但它的函数都活在别的脚本里（搬家），不算问题；
    #   真丢了函数的（谁那儿都找不到）已经记在 missing 里了。
    tight = not changed and not missing

    rep = {
        "version": ver, "baseline": bver, "exact": exact,
        "scripts_total": len(cmp_names),
        "scripts_missing": scripts_missing[:limit],
        "scripts_missing_n": len(scripts_missing),
        "scripts_added": scripts_added[:limit],
        "scripts_added_n": len(scripts_added),
        "total": total, "same": same,
        "changed": changed[:limit], "missing": missing[:limit],
        "moved": moved[:limit],
        "changed_n": len(changed), "missing_n": len(missing),
        "moved_n": len(moved),
        "added_n": added_funcs + len(scripts_added),
        "ok": tight, "tight": tight, "reason": "",
    }

    tag = "" if exact else ("（指纹完全吻合）" if tight
                            else f"（近似：内置的是 v{bver}）")
    say(f"[检测] Essentials {ver or '?'} · 基准 v{bver}{tag}："
        f"{len(cmp_names)} 个脚本 / {total} 个基本函数")
    # ★ 日志只出总结，不再逐条罗列明细 —— 明细都写进检测报告，用户点
    #   「检测报告」就能逐行对比。这里只给一行结论。
    say(f"[检测] 结论：一致 {same} · 被改 {len(changed)} · 缺失 {len(missing)}"
        f" · 搬家 {len(moved)}"
        f" · 脚本缺失 {len(scripts_missing)}"
        f" · 新增 {added_funcs + len(scripts_added)}"
        f"（新增是作者自己加的，不算问题）")
    return rep


def _norm(name):
    """脚本名归一化（比对用）：只留字母数字，忽略大小写。"""
    return re.sub(r"[^0-9A-Za-z]+", "", str(name or "")).lower()


def _empty(ver, reason):
    rep = {"version": ver, "baseline": None, "exact": False,
           "scripts_total": 0, "scripts_missing": [], "scripts_missing_n": 0,
           "scripts_added": [], "scripts_added_n": 0,
           "total": 0, "same": 0, "changed": [], "missing": [],
           "moved": [], "moved_n": 0,
           "changed_n": 0, "missing_n": 0, "added_n": 0,
           "ok": True, "tight": False, "reason": reason}
    log.info("比对跳过：%s", reason)
    return rep


# ================================================================
# 生成基准表（开发用；需要有官方 Essentials 源码）
# ================================================================
def build_baseline(engine_dir, out_path, version=None):
    """
    从一份官方 Essentials 目录生成基准表。返回 (版本, 脚本数, 函数数)。

    用法（命令行）：
        python essentials_base.py "E:/Pokemon Essentials/pokemon-essentials-21.1"
    """
    ver = version or detect_version(engine_dir)
    if not ver:
        stem = os.path.basename(os.path.normpath(engine_dir))
        m = re.search(r"(\d+(?:\.\d+)*)", stem)
        ver = m.group(1) if m else stem
    scripts = {}
    for _m, _k, _p, name, text in GS.iter_named_scripts(engine_dir,
                                                        allow_backup=True):
        if name in scripts:
            continue
        # ★ 与比对同一步骤：先抹掉本工具可能留下的注入行
        scripts[name] = scan_defs(strip_own_patch(text))
    data = {
        "version": ver,
        "engine": "Pokemon Essentials",
        "generated": time.strftime("%Y-%m-%d"),
        "note": "脚本名 → {函数限定名: 函数体指纹}；比对时忽略 Settings",
        "scripts": scripts,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    n_funcs = sum(len(v) for v in scripts.values())
    return ver, len(scripts), n_funcs


def build_all(engine_root, out_dir=None):
    """把 engine_root 下所有 pokemon-essentials-* 目录都生成一遍。"""
    out_dir = out_dir or base_dir()
    os.makedirs(out_dir, exist_ok=True)
    done = []
    for name in sorted(os.listdir(engine_root)):
        d = os.path.join(engine_root, name)
        if not os.path.isdir(d) or not name.lower().startswith("pokemon-essentials"):
            continue
        ver = name[len("pokemon-essentials-"):]
        try:
            _v, ns, nf = build_baseline(d, os.path.join(out_dir, f"v{ver}.json"),
                                        version=ver)
            done.append((ver, ns, nf))
            print(f"  v{ver:<6s} {ns:4d} 个脚本 / {nf:5d} 个函数")
        except Exception as e:
            print(f"  v{ver:<6s} 失败：{e}")
    return done


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if os.path.isdir(arg) and os.path.isdir(os.path.join(arg, "Data")):
            if "essentials" in os.path.basename(arg).lower():
                print("生成全部版本 →", base_dir())
                build_all(os.path.dirname(arg))
            else:
                v, ns, nf = build_baseline(arg,
                                           baseline_path(detect_version(arg)))
                print(f"v{v}  {ns} 个脚本 / {nf} 个函数 → {baseline_path(v)}")
        else:
            print("用法：python essentials_base.py <Essentials 游戏目录>")
    else:
        print("已内置基准版本：", ", ".join(list_baselines()) or "（无）")
