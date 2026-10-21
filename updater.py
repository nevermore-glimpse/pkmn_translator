# -*- coding: utf-8 -*-
"""
检查更新 / 自动下载更新。

发布约定（一个 release 两个 asset）：
  · 程序包 —— zip，里面能找到主程序 exe（如 宝可梦同人工具.exe）
  · 资源包 —— zip，只有程序资源（prompts / replacements / scripts /
              text_preserve / LM操作指南）

★ 两个包都按「内容」识别，不认文件名。
  v1.8.2 的包叫 pokemon.tools.v1.8.2.zip，v1.8.3 改叫 pkmn.tools.v1.8.3.zip，
  v1.8.4 又改成 pokemon.tools.zip + resource.zip，资源包名字以后也可能变，
  写死名字早晚会断。
  识别分两段：
    · 检查阶段 —— 只看文件名/扩展名（零延迟，classify_assets_fast）
    · 下载之后 —— 本地打开 zip 看内容（inspect_zip_local）
  早期版本是在检查阶段远程读 zip 中央目录（HTTP Range），
  读 48MB 的包要发多次 Range 请求，直连 GitHub 常常一卡十几秒，
  「检查更新」被拖到 30 秒起步，用户只看到「打开工具没触发更新检测」。

★ 更新是两件互不牵连的事：
  1) 资源更新 —— 解压资源包，但**只覆盖白名单里的程序资源**。
     缓存、术语表、配置、报告、日志属于用户数据，另有独立保护名单，双保险。
  2) 程序更新 —— 只换 exe 这一个文件，别的一概不动。

★ 加速：大陆直连 github.com 基本超时，按 MIRRORS 顺序并发探测，
  把能用的线路排前面再下载。api.github.com 同样留代理兜底——
  它一挂，「检查更新」就永远失败，用户只会觉得「怎么没提示更新」。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

import config
from logger import get_logger

log = get_logger("updater")

# ================================================================
# 仓库 / 地址
# ================================================================
REPO_OWNER   = "nevermore-glimpse"
REPO_NAME    = "pkmn_translator"
API_URL      = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
API_LIST_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
RELEASES_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases"
TAG_URL      = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/tag/{{tag}}"

UA = f"{REPO_NAME}-translator/{getattr(config, 'VERSION', '0')}"

# ★ 下载加速线路。空串 = 直连 GitHub（能通就用它，最快也最稳）。
#   顺序即尝试顺序：先直连，失败再走代理；代理之间按实测延迟排。
MIRRORS = (
    "https://v6.gh-proxy.org/",
    "https://v4.gh-proxy.org/",
    "https://gh-proxy.org/",
    "",
)

# 单个地址的超时（秒）。直连要短一点，免得卡在那儿等太久。
TIMEOUT_DIRECT = 10
TIMEOUT_PROXY  = 25

# ================================================================
# 覆盖白名单 / 用户数据保护名单
# ================================================================
# ★ 资源包**只允许**写这些顶层条目（目录以 / 结尾）。
#   新增随程序分发的资源目录时，记得同步加到这里，否则更新不会带上它。
RESOURCE_WHITELIST = (
    "prompts/",
    "replacements/",
    "scripts/",
    "text_preserve/",
    "LM操作指南/",
)

# ★ 用户数据：不管它出现在哪个包里、在哪个层级，一律不覆盖。
#   这些文件被覆盖一次，用户几十小时的翻译缓存和手工维护的术语表就没了。
USER_DATA_PROTECT = (
    "logs/",
    "reports/",
    "intl.txt",
    "intl_translated.txt",
    "intl_cache.json",
    "user_config.json",
    ".runtime.json",
    "term_dict.py",
    "term_sections.json",
    "term_conflicts.json",
    "terms_stats.json",
    "check_whitelist.json",
    "术语表（Glossary）.xlsx",
    "术语表.xlsx",
)

# 按后缀保护：缓存 / 冲突 / 译文产物，任何目录下都算用户数据
USER_DATA_SUFFIXES = (
    "_cache.json",
    "_conflicts.json",
    "_translated.txt",
)

# 更新暂存目录（放 BASE_DIR 下，和 exe 同盘，rename 才够快）
UPDATE_DIR_NAME = ".update"

# 跳过版本的记录文件
SKIP_FILE_NAME = "skip.json"


# ================================================================
# 版本工具
# ================================================================
def _normalize(tag):
    """去掉 v 前缀与空白。"""
    return (tag or "").strip().lstrip("vV")


def _version_tuple(text):
    """'1.2.0' → (1, 2, 0)；非数字段按 0 处理。"""
    parts = re.split(r"[.\-_+]", _normalize(text))
    out = []
    for p in parts[:4]:
        m = re.match(r"^(\d+)", p or "")
        out.append(int(m.group(1)) if m else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


# ================================================================
# 网络
# ================================================================
def _is_direct(url):
    return not re.match(r"^https?://(v[46]\.)?gh-proxy\.org/", url)


def _timeout_for(url):
    return TIMEOUT_DIRECT if _is_direct(url) else TIMEOUT_PROXY


def _mirror_urls(url):
    """给一个 GitHub 地址生成「直连 + 各代理」的候选列表。

    ★ 顺序即尝试顺序，直连最快最稳，失败才逐个换代理。
    ★ api.github.com 也**必须**留代理兜底：
      部分网络下 api.github.com 同样连不上，而它一挂，
      「检查更新」就永远失败，用户只会觉得「怎么没提示更新」。
    """
    out = []
    for m in MIRRORS:
        out.append(url if not m else m + url)
    return out


def _open(url, headers=None, method=None, timeout=None):
    hdrs = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method=method)
    t = timeout if timeout else _timeout_for(url)
    return urllib.request.urlopen(req, timeout=t)


def _api_get(url, timeout=8):
    """GitHub API：所有线路**并发**请求，谁先成功用谁。

    ★ 为什么必须并发，不能串行：
      国内直连 api.github.com 的典型故障是「挂住」——TCP 连上了，
      但 TLS 握手/响应迟迟不来，socket 超时要等满 10 秒才报错。
      串行的话，8 秒的总预算会被直连一条吃光，
      后面三条代理线路根本没机会跑——用户看到的还是「没检测到更新」。
      并发之后总耗时 = 最快那条线路的耗时（实测 1.5s 内），
      无论哪条能通都一样。

    ★ 每条线路都带 timeout 兜底，不会无限挂住。
    """
    deadline = time.time() + max(1.0, float(timeout))
    urls = _mirror_urls(url)
    results = {}
    errors = []

    def worker(u):
        left = deadline - time.time()
        if left <= 0.5:
            return
        try:
            with _open(u, timeout=max(1.0, left)) as resp:
                body = resp.read().decode("utf-8", "replace")
            data = json.loads(body)
            # ★ 代理有可能返回错误页/HTML，必须验证是像样的 release JSON
            if not isinstance(data, dict) or not (data.get("tag_name") or data.get("message")):
                raise ValueError("返回内容不像 release JSON")
            results[u] = data
        except Exception as e:                      # noqa: BLE001
            errors.append((u, e))
            log.debug("API 线路失败 %s：%s", u, e)

    threads = []
    for u in urls:
        t = threading.Thread(target=worker, args=(u,), daemon=True)
        t.start()
        threads.append(t)

    # 等第一个成功的
    while threads and not results:
        alive = [t for t in threads if t.is_alive()]
        if not alive:
            break
        alive[0].join(timeout=0.1)

    if results:
        return next(iter(results.values()))

    if errors:
        raise errors[-1][1]
    raise IOError("所有线路都失败")


def fetch_latest(timeout=8):
    """拉取最新 release 信息，返回 dict 或 None（失败抛异常）。"""
    data = _api_get(API_URL, timeout)

    tag = (data.get("tag_name") or "").strip()
    if not tag:
        return None

    url = data.get("html_url") or TAG_URL.format(tag=tag)
    assets = []
    for a in data.get("assets") or []:
        assets.append({
            "name":   a.get("name") or "",
            "size":   a.get("size") or 0,
            "url":    a.get("browser_download_url") or "",
            "digest": a.get("digest") or "",        # "sha256:xxxx"
        })

    return {
        "tag":    tag,
        "name":   data.get("name") or tag,
        "url":    url,
        "notes":  (data.get("body") or "").strip()[:600],
        "assets": assets,
        "published": data.get("published_at") or "",
    }


def _has_exe(names):
    return any(n.lower().endswith(".exe") for n in names)


# ★ 辅助 exe：它们也是 .exe，但**绝不能**当成主程序去替换。
#   实测 resource.zip 里就躺着「宝可梦调试启动器.exe」，
#   只按「有没有 exe」判断包类型，会把它当成程序包，
#   结果更新时用调试启动器把主程序覆盖掉。
HELPER_EXE_HINTS = ("调试", "debug", "launcher", "启动器", "updater", "update")


def _is_helper_exe(name):
    """判断这个 exe 是不是辅助工具（而不是主程序）。"""
    low = (name or "").lower()
    for h in HELPER_EXE_HINTS:
        if h.lower() in low:
            return True
    return False


def _has_main_exe(names):
    """包里有**主程序** exe（排除调试器/启动器这类辅助工具）。"""
    return any(n.lower().endswith(".exe") and not _is_helper_exe(n) for n in names)


def _has_resource_dir(names):
    return any(n.startswith(RESOURCE_WHITELIST) for n in names)


def _find_exe_asset(assets, exclude_urls=()):
    """
    在 asset 列表里找一个**可能**是程序包的（名字像 exe 包，或干脆是裸 exe）。

    只按名字筛，不联网：真正的确认在下载后本地看 zip 内容时做。
    exclude_urls：已经试过不行的地址，不再重复下载。
    """
    exclude = set(exclude_urls or ())
    cands = []
    for a in assets or []:
        name = (a.get("name") or "").lower()
        url = a.get("url") or ""
        if not url or url in exclude:
            continue
        if name.endswith(".exe"):
            return a
        if name.endswith(".zip") and ("resource" not in name and "资源" not in name):
            cands.append(a)
    return cands[0] if cands else None


def inspect_zip_local(path):
    """
    看一个**已经下载到本地**的 zip 里有什么。

    返回 (has_exe: bool, has_resource: bool)；不是有效 zip 时返回 (False, False)。

    ★ has_exe 判的是「有**主程序** exe」：
      resource.zip 里含「宝可梦调试启动器.exe」，它也是 .exe，
      但它是辅助工具，不能当成程序包——否则更新会用它覆盖主程序。

    ★ 为什么改成「下完再本地看」而不是「下载前远程看」：
      远程看要读 zip 中央目录，得对 48MB 的包发多次 Range 请求，
      在大陆直连 github.com 常常一卡十几秒——检查更新因此被拖到 30 秒，
      用户看到的现象就是「打开工具没触发更新检测」。
      本地看是零延迟的，而且下载过程中顺带就做了，不用额外请求。
    """
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except Exception as e:                          # noqa: BLE001
        log.debug("本地检查 zip 失败 %s：%s", path, e)
        return False, False
    return _has_main_exe(names), _has_resource_dir(names)


def classify_assets_fast(assets):
    """
    **不联网**的快速分类：只看文件名/扩展名。

    返回 (exe_asset, res_asset, need_probe)。

    ★ 为什么要分两段：
      精确识别要读远程 zip 的中央目录（多次 Range 请求），
      直连 GitHub 在大陆常常一卡十几秒。把它塞进「检查更新」里，
      启动时的静默检查就会迟迟不弹窗，甚至直接被用户当成「没检测到」。
      所以检查阶段只做零延迟的快速分类；
      need_probe=True 表示还有 zip 需要联网精确定位，
      那个活儿留到用户点「立即更新」之后再做。

    ★ 快速分类的判断依据：
      · .exe 结尾 → 一定是程序本体
      · 文件名含 resource/资源 → 资源包
      · 其它 .zip → 程序包（用户约定 exe 压缩包就叫这个）
    """
    exe_asset = None
    res_asset = None
    need_probe = False

    for a in assets:
        name = (a.get("name") or "").lower()
        if not name or not (a.get("url") or ""):
            continue

        if name.endswith(".exe"):
            # 裸 exe 就是程序本体
            exe_asset = exe_asset or a
            continue

        if not name.endswith(".zip"):
            continue

        if "resource" in name or "资源" in name or "assets" in name:
            res_asset = res_asset or a
        else:
            # 拿不准是不是「exe + 资源」合一的包，留到精确定位
            exe_asset = exe_asset or a
            need_probe = True

    return exe_asset, res_asset, need_probe


# ================================================================
# 检查更新
# ================================================================
def check_update(timeout=8):
    """
    返回 (has_update: bool, info: dict)。
    info 含 tag / url / notes / assets / exe_asset / res_asset；出错时含 error。
    """
    try:
        info = fetch_latest(timeout)
    except Exception as e:                          # noqa: BLE001
        log.debug("检查更新失败：%s", e)
        return False, {"error": str(e)}

    if not info:
        return False, {"error": "未获取到 release 信息"}

    cur = _normalize(getattr(config, "VERSION", ""))
    new = _normalize(info["tag"])
    if not new:
        return False, {"error": "release 无 tag"}

    try:
        newer = _version_tuple(new) > _version_tuple(cur)
    except Exception:                               # noqa: BLE001
        newer = new != cur

    info["current"] = getattr(config, "VERSION", "")

    # ★ 这里**只做零延迟的快速分类**（不联网）。
    #   精确识别要读远程 zip 的中央目录，直连 GitHub 在大陆常常一卡十几秒，
    #   塞在检查阶段会让启动时的静默检查迟迟不弹窗——用户只会觉得「没检测到更新」。
    #   联网精确定位推迟到用户点「立即更新」之后再做。
    if newer:
        try:
            exe_a, res_a, need_probe = classify_assets_fast(info.get("assets") or [])
            info["exe_asset"] = exe_a
            info["res_asset"] = res_a
            info["need_probe"] = need_probe
        except Exception as e:                      # noqa: BLE001
            log.debug("asset 识别失败：%s", e)
            info["exe_asset"] = None
            info["res_asset"] = None
            info["need_probe"] = False

    return newer, info


# ================================================================
# 下载
# ================================================================
def _sha256_file(path, progress=None):
    h = hashlib.sha256()
    total = os.path.getsize(path) or 1
    done = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total, "校验中…")
    return h.hexdigest()


def _probe_mirrors(url, timeout=6):
    """并发探测各条线路能不能用，按「可用优先、快的在前」返回线路顺序。

    ★ 为什么下载前要先探：
      直连 github.com 在国内是「挂住」而不是「快速失败」——
      串行下载的话，第一条直连线路要先浪费掉 10 秒 socket 超时，
      用户看到的就是「点了立即更新，半天没反应」。
      先并发探一下（每条只取几个字节），把能用的线路排前面，
      下载就能直接走通的那条。
    """
    urls = _mirror_urls(url)
    ok = {}
    err = {}

    def worker(u):
        t0 = time.time()
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Range": "bytes=0-1023"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                r.read(1024)
            ok[u] = time.time() - t0
        except Exception as e:                      # noqa: BLE001
            err[u] = e

    threads = []
    for u in urls:
        t = threading.Thread(target=worker, args=(u,), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=timeout + 1.0)

    if not ok:
        # 一条都没通：保持原顺序，让调用方自己按超时重试
        return urls
    good = sorted(ok.keys(), key=lambda u: ok[u])
    bad = [u for u in urls if u not in ok]
    log.debug("可用线路：%s", good)
    return good + bad


def download(url, dest, progress=None, expected_sha256="", resume=True):
    """
    下载到 dest，支持断点续传与 sha256 校验。

    progress(done, total, text) 用于界面进度条。
    返回 (ok, msg)。失败时保留 .part 文件，下次可续传。
    """
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

    if not resume and os.path.exists(part):
        try:
            os.remove(part)
        except OSError:
            pass

    start = os.path.getsize(part) if os.path.exists(part) else 0
    last_err = None

    # ★ 先并发探测线路，把能用的排前面，避免第一条直连挂住 10 秒
    ordered = _probe_mirrors(url)

    for u in ordered:
        try:
            headers = {"User-Agent": UA}
            if start:
                headers["Range"] = f"bytes={start}-"
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=_timeout_for(u)) as r:
                # 服务器不认 Range（返回 200）时，从头写，不能续
                if start and r.status != 206:
                    start = 0
                total = 0
                cr = r.headers.get("Content-Range") or ""
                m = re.search(r"/(\d+)\s*$", cr)
                if m:
                    total = int(m.group(1))
                else:
                    cl = r.headers.get("Content-Length")
                    total = int(cl) + start if cl else 0

                mode = "ab" if start else "wb"
                done = start
                t0 = time.time()
                with open(part, mode) as f:
                    while True:
                        chunk = r.read(1 << 18)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if progress:
                            speed = done / max(0.001, time.time() - t0)
                            progress(done, total,
                                     f"下载中 {done * 100 // max(1, total)}%"
                                     f"（{speed / 1048576:.1f} MB/s）")

            # 大小对不上就当作没下完，保留 .part 供续传
            if total and os.path.getsize(part) < total:
                last_err = f"下载不完整（{os.path.getsize(part)}/{total}）"
                continue

            # sha256 校验（GitHub asset 的 digest 字段）
            if expected_sha256:
                if progress:
                    progress(0, 1, "校验文件完整性…")
                got = _sha256_file(part, progress)
                if got.lower() != expected_sha256.lower():
                    # ★ 文件坏了就删掉重下，并换下一条线路
                    try:
                        os.remove(part)
                    except OSError:
                        pass
                    start = 0
                    last_err = (f"校验失败：期望 {expected_sha256[:16]}…，"
                                f"实际 {got[:16]}…")
                    continue

            os.replace(part, dest)
            return True, "下载完成"

        except Exception as e:                      # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            log.debug("下载线路失败 %s：%s", u, e)
            # 续传点可能已失效（换了线路），下一次重新取大小
            if os.path.exists(part):
                start = os.path.getsize(part)
            continue

    return False, f"所有线路都失败：{last_err or '未知错误'}"


def _digest_of(asset):
    """从 asset 的 digest 字段取出裸 sha256（没有则返回空串）。"""
    d = (asset or {}).get("digest") or ""
    m = re.match(r"^sha256:([0-9a-fA-F]{64})$", d.strip())
    return m.group(1) if m else ""


def _is_raw_exe(asset):
    """asset 本身就是 exe 文件（不是 zip 包）。"""
    return (asset or {}).get("name", "").lower().endswith(".exe")


def _stage_raw_exe(path, progress=None):
    """
    把下载下来的裸 exe 放进暂存目录，准备替换当前 exe。

    优先用**当前 exe 的文件名**，这样替换后窗口标题、任务栏图标的名字不变；
    源码运行（没有 exe）时退回下载文件名。
    返回 (ok, msg, path)。
    """
    try:
        name = os.path.basename(current_exe() or "") or os.path.basename(path)
        dst = os.path.join(update_dir(), name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if progress:
            progress(0, 1, "准备新 exe…")
        shutil.copyfile(path, dst)
        size = os.path.getsize(dst)
        return True, f"已准备新 exe（{size / 1048576:.1f} MB）", dst
    except Exception as e:                          # noqa: BLE001
        log.warning("准备裸 exe 失败：%s", e)
        return False, f"准备 exe 失败：{e}", None


# ================================================================
# 解压：资源白名单
# ================================================================
def _norm_entry(name):
    """zip 内路径归一化：统一斜杠、去掉开头的 ./ 和 /。"""
    n = (name or "").replace("\\", "/").lstrip("./")
    return n


def _is_user_data(rel):
    """判断 zip 内路径是否属于用户数据（命中即拒绝写入）。"""
    n = _norm_entry(rel)
    low = n.lower()
    for p in USER_DATA_PROTECT:
        if low == p.lower() or low.startswith(p.lower()):
            return True
    for suf in USER_DATA_SUFFIXES:
        if low.endswith(suf):
            return True
    return False


def _is_whitelisted(rel):
    """判断 zip 内路径是否落在资源白名单内。"""
    n = _norm_entry(rel)
    return any(n.startswith(p) for p in RESOURCE_WHITELIST)


def extract_resource_zip(zip_path, target_dir=None, progress=None):
    """
    解压资源包，**只写白名单内的程序资源**。

    双重闸门：白名单之外的跳过，用户数据一律拒绝。
    返回 (ok, msg, stats)。stats = {"written": n, "skipped": n}
    """
    target_dir = target_dir or config.BASE_DIR
    written = skipped = 0

    try:
        with zipfile.ZipFile(zip_path) as z:
            members = [i for i in z.infolist() if not i.is_dir()]
            total = len(members) or 1

            for idx, info in enumerate(members, 1):
                rel = _norm_entry(info.filename)
                if progress and idx % 20 == 0:
                    progress(idx, total, f"解压资源 {idx}/{total}")

                if not rel:
                    continue
                if _is_user_data(rel):
                    log.debug("跳过用户数据：%s", rel)
                    skipped += 1
                    continue
                if not _is_whitelisted(rel):
                    log.debug("不在白名单：%s", rel)
                    skipped += 1
                    continue

                # ★ 防 zip 路径穿越：解压后的真实路径必须仍在 target_dir 内
                dst = os.path.abspath(os.path.join(target_dir, rel))
                base = os.path.abspath(target_dir)
                if not (dst == base or dst.startswith(base + os.sep)):
                    log.warning("拒绝越界路径：%s", rel)
                    skipped += 1
                    continue

                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(info) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)
                written += 1

    except Exception as e:                          # noqa: BLE001
        log.warning("解压资源包失败：%s", e)
        return False, f"解压失败：{e}", {"written": written, "skipped": skipped}

    return True, f"资源已更新：写入 {written} 个文件，跳过 {skipped} 个", {
        "written": written, "skipped": skipped}


# ================================================================
# exe 替换
# ================================================================
def update_dir():
    d = os.path.join(config.BASE_DIR, UPDATE_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def current_exe():
    """当前正在运行的 exe 路径；源码运行时返回 None。"""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return None


def extract_exe(zip_path, progress=None):
    """
    从程序包里**只抽 exe** 到暂存目录。

    认哪个 exe：优先取与当前 exe 同名的那个；否则取体积最大的 exe。
    ★ 辅助 exe（调试器/启动器）一律排除：resource.zip 里就有一个，
      它比主程序小，命中「取最大的」就会拿它去覆盖主程序。
    返回 (ok, msg, path)。
    """
    try:
        with zipfile.ZipFile(zip_path) as z:
            cands = [i for i in z.infolist()
                     if not i.is_dir() and i.filename.lower().endswith(".exe")
                     and not _is_helper_exe(i.filename)]
            if not cands:
                return False, "程序包里没有 exe", None

            want = os.path.basename(current_exe() or "")
            pick = None
            if want:
                for i in cands:
                    if os.path.basename(_norm_entry(i.filename)) == want:
                        pick = i
                        break
            if pick is None:
                pick = max(cands, key=lambda i: i.file_size)

            if progress:
                progress(0, 1, "抽取 exe…")
            dst = os.path.join(update_dir(), os.path.basename(
                _norm_entry(pick.filename)))
            with z.open(pick) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
            return True, f"已准备新 exe（{pick.file_size / 1048576:.1f} MB）", dst

    except Exception as e:                          # noqa: BLE001
        log.warning("抽取 exe 失败：%s", e)
        return False, f"抽取 exe 失败：{e}", None


def apply_exe_update(new_exe):
    """
    用暂存的新 exe 替换当前 exe。

    ★ Windows 上「正在运行的 exe」不允许写、不允许删，但**允许改名**
      （同盘 MoveFile）。所以流程是：
        旧 exe → .old（改名，立刻成功）
        新 exe → 原位置（移动）
        失败就把 .old 改回来，保证任何一步出错都不会留下没有 exe 的目录。

    返回 (ok, msg)。成功后调用方负责重启。
    """
    cur = current_exe()
    if not cur:
        return False, "当前是源码运行，不替换 exe"
    if not os.path.exists(new_exe):
        return False, "新 exe 不存在"

    old = cur + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        pass

    try:
        os.rename(cur, old)
    except OSError as e:
        return False, f"无法重命名当前 exe（可能被占用）：{e}"

    try:
        shutil.move(new_exe, cur)
    except Exception as e:                          # noqa: BLE001
        # ★ 回滚：新 exe 没落位就绝不能把旧的丢了
        try:
            os.rename(old, cur)
        except OSError as e2:
            log.error("回滚失败，请手动把 %s 改名为 %s：%s", old, cur, e2)
        return False, f"替换失败，已回滚：{e}"

    return True, "exe 已更新"


def restart(new_args=None):
    """启动新 exe 并退出当前进程。"""
    cur = current_exe()
    if not cur:
        return False
    try:
        creation = 0
        if os.name == "nt":
            DETACHED_PROCESS = 0x00000008
            creation = DETACHED_PROCESS
        subprocess.Popen([cur] + list(new_args or []),
                         close_fds=True, creationflags=creation,
                         cwd=config.BASE_DIR)
    except Exception as e:                          # noqa: BLE001
        log.error("重启失败：%s", e)
        return False
    return True


def cleanup_old():
    """
    清理上次更新留下的 .old 与暂存文件。

    ★ 启动时调用：上一次替换完 exe 后，旧文件当时还被占用删不掉，
      等新进程起来（旧进程已退出）才删得掉。
    """
    removed = 0
    cur = current_exe()
    if cur:
        old = cur + ".old"
        if os.path.exists(old):
            try:
                os.remove(old)
                removed += 1
            except OSError as e:
                log.debug("旧 exe 暂时删不掉（下次再试）：%s", e)

    # ★ 也扫一遍 BASE_DIR 里的 *.old：exe 目录不一定等于 BASE_DIR，
    #   上次更新留下的残留在下次启动时一并清掉。
    try:
        for name in os.listdir(config.BASE_DIR):
            if name.lower().endswith(".old"):
                p = os.path.join(config.BASE_DIR, name)
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                        removed += 1
                except OSError:
                    pass
    except OSError:
        pass

    d = os.path.join(config.BASE_DIR, UPDATE_DIR_NAME)
    if os.path.isdir(d):
        for name in os.listdir(d):
            # ★ skip.json 是「跳过此版本」的记录，不能删！
            #   删了的话用户点了「跳过此版本」，下次启动又会被同一个新版骚扰，
            #   「跳过」按钮就等于白按。
            if name == SKIP_FILE_NAME:
                continue
            p = os.path.join(d, name)
            try:
                if os.path.isfile(p):
                    os.remove(p)
                    removed += 1
            except OSError:
                pass
        try:
            os.rmdir(d)
        except OSError:
            pass

    if removed:
        log.info("更新清理：移除 %d 个旧文件", removed)
    return removed


# ================================================================
# 跳过版本
# ================================================================
def _skip_path():
    return os.path.join(config.BASE_DIR, UPDATE_DIR_NAME, SKIP_FILE_NAME)


def skipped_version():
    """用户选择「跳过此版本」时记下的 tag；没有则返回空串。"""
    try:
        with open(_skip_path(), "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("tag", "")
    except Exception:                               # noqa: BLE001
        return ""


def skip_version(tag):
    try:
        os.makedirs(os.path.dirname(_skip_path()), exist_ok=True)
        with open(_skip_path(), "w", encoding="utf-8") as f:
            json.dump({"tag": tag, "at": time.strftime("%Y-%m-%d %H:%M:%S")},
                      f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:                          # noqa: BLE001
        log.debug("写入跳过版本失败：%s", e)
        return False


def clear_skip():
    try:
        os.remove(_skip_path())
    except OSError:
        pass


# ================================================================
# 一站式更新
# ================================================================
def run_update(info, progress=None, do_exe=True, do_resource=False):
    """
    按 info 里识别好的两个包执行更新。

    步骤：下载 → 校验 → （资源解压 / exe 抽取并替换）
    返回 (ok, msg, needs_restart)。
    ★ 不在这里重启：让 GUI 先把提示弹出来，再决定什么时候重启。

    ★ do_resource 默认 **False**：更新只换 exe，别的一概不动。
      资源包要更新时由用户显式勾选（GUI 里的复选框），
      而且解压时只写白名单里的程序资源，缓存/术语表/配置一律不碰。

    ★ 识别靠**下载后本地看**，不靠下载前的远程探测：
      远程探测要读 48MB 包的中央目录（多次 Range 请求），
      在大陆常常一卡十几秒，整个更新流程被拖成 30 秒起步。
      本地看是零延迟的，而且正好是「文件已经在硬盘上」的那一刻。
    """
    tmp = update_dir()
    parts = []

    res_a = info.get("res_asset") if do_resource else None
    exe_a = info.get("exe_asset") if do_exe else None

    # ---------- 下载并本地识别 ----------
    fetched = {}                    # url -> 本地路径

    def fetch(asset, role):
        """下载一个 asset，返回本地路径。失败返回 None。"""
        url = (asset or {}).get("url") or ""
        if not url:
            return None
        if url in fetched:
            return fetched[url]
        suffix = ".exe" if (role == "exe" and _is_raw_exe(asset)) else ".zip"
        dst = os.path.join(tmp, "pkg_%d%s" % (len(fetched), suffix))
        ok, msg = download(url, dst, progress, _digest_of(asset))
        if not ok:
            log.warning("下载 %s 失败：%s", asset.get("name"), msg)
            fetched[url] = None
            return None
        fetched[url] = dst
        return dst

    # ---------- 程序包 ----------
    needs_restart = False
    if exe_a:
        path = fetch(exe_a, "exe")
        if not path:
            return False, f"程序包下载失败：{(exe_a.get('name') or '')}", False

        if _is_raw_exe(exe_a):
            ok, msg, new_exe = _stage_raw_exe(path, progress)
        else:
            # ★ 下载后本地看：这个包到底是程序包还是资源包？
            has_exe, has_res = inspect_zip_local(path)
            if has_exe:
                ok, msg, new_exe = extract_exe(path, progress)
            elif has_res:
                # ★ 包名骗人了：这个其实是资源包。
                #   那它就当资源包用，程序包另找。
                log.info("包 %s 里没有 exe，按资源包处理", exe_a.get("name"))
                if do_resource and not res_a:
                    res_a = exe_a
                ok, msg, new_exe = False, "包里没有 exe", None
            else:
                ok, msg, new_exe = False, "包里既没有 exe 也没有资源", None

        if ok and new_exe:
            ok2, msg2 = apply_exe_update(new_exe)
            if not ok2:
                return False, msg2, False
            parts.append(msg2)
            needs_restart = True
        elif not ok:
            # ★ 退一步：从其它 asset 里再找一个真正带 exe 的包。
            alt = _find_exe_asset(info.get("assets") or [], fetched.keys())
            if not alt:
                return False, msg, False
            path = fetch(alt, "exe")
            if not path:
                return False, "程序包下载失败", False
            if _is_raw_exe(alt):
                ok, msg, new_exe = _stage_raw_exe(path, progress)
            else:
                ok, msg, new_exe = extract_exe(path, progress)
            if not ok:
                return False, msg, False
            ok2, msg2 = apply_exe_update(new_exe)
            if not ok2:
                return False, msg2, False
            parts.append(msg2)
            needs_restart = True

    # ---------- 资源（用户显式勾选时才做） ----------
    if do_resource and res_a:
        zpath = fetch(res_a, "res")
        if zpath:
            ok, msg, _stats = extract_resource_zip(zpath, progress=progress)
            if ok:
                parts.append(msg)
        else:
            return False, f"资源包下载失败：{(res_a.get('name') or '')}", False

    # ---------- 收掉下载的临时包 ----------
    for p in fetched.values():
        if not p:
            continue
        try:
            os.remove(p)
        except OSError:
            pass

    if not parts:
        return False, "这个版本没有可用的更新包", False
    return True, "；".join(parts), needs_restart
# probe
