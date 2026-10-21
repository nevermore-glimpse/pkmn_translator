# -*- coding: utf-8 -*-
"""
检查更新 / 自动下载更新。

发布约定（一个 release 两个 asset）：
  · 程序包 —— zip，里面能找到主程序 exe（如 宝可梦同人工具.exe）
  · 资源包 —— zip，只有程序资源（prompts / replacements / scripts /
              text_preserve / LM操作指南）

★ 两个包都按「内容」识别，不认文件名。
  v1.8.2 的包叫 pokemon.tools.v1.8.2.zip，v1.8.3 改叫 pkmn.tools.v1.8.3.zip，
  资源包名字以后也可能变，写死名字早晚会断。识别方式是只读 zip 的中央目录
  （HTTP Range），不必把 48MB 整个下下来就能知道里面有没有 exe。

★ 更新是两件互不牵连的事：
  1) 资源更新 —— 解压资源包，但**只覆盖白名单里的程序资源**。
     缓存、术语表、配置、报告、日志属于用户数据，另有独立保护名单，双保险。
  2) 程序更新 —— 只换 exe 这一个文件，别的一概不动。

★ 加速：大陆直连 github.com 基本超时，按 MIRRORS 顺序逐个试。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
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
    "",
    "https://v6.gh-proxy.org/",
    "https://v4.gh-proxy.org/",
    "https://gh-proxy.org/",
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

    ★ 只有 github.com 上的下载/页面地址才需要代理；
      api.github.com 直连通常可用，套了代理反而更慢。
    """
    if "api.github.com" in url:
        return [url]
    out = []
    for m in MIRRORS:
        out.append(url if not m else m + url)
    return out


def _open(url, headers=None, method=None):
    hdrs = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method=method)
    return urllib.request.urlopen(req, timeout=_timeout_for(url))


def _api_get(url, timeout=8):
    """GitHub API：直连优先，失败再走代理。"""
    last = None
    for u in _mirror_urls(url):
        try:
            with _open(u) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as e:                      # noqa: BLE001
            last = e
            log.debug("API 失败 %s：%s", u, e)
    raise last or IOError("所有线路都失败")


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


# ================================================================
# 远程 zip 探测（只读中央目录，不下载整个包）
# ================================================================
class _RangeFile:
    """只读、可 seek 的 HTTP Range 文件对象，专供 zipfile 读中央目录。

    ★ 用它就不必为了「这个包是不是程序包」先下 48MB：
      zip 的中央目录在文件末尾，range 读个几百 KB 就够了。

    ★ 每条线路一个实例：直连 github.com/.../releases/download/ 在大陆
      基本超时，但 api.github.com 反而通 → 探测和下载都必须能换线路。
    """

    def __init__(self, url, timeout=20):
        self.url = url
        self.timeout = timeout
        self.pos = 0
        self.size = self._probe_size()

    def _probe_size(self):
        req = urllib.request.Request(
            self.url, headers={"Range": "bytes=0-0", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            cr = r.headers.get("Content-Range") or ""
            m = re.search(r"/(\d+)\s*$", cr)
            if m:
                return int(m.group(1))
            cl = r.headers.get("Content-Length")
            if cl:
                return int(cl)
        raise IOError("无法获取远程文件大小")

    def seek(self, off, whence=0):
        if whence == 0:
            self.pos = off
        elif whence == 1:
            self.pos += off
        elif whence == 2:
            self.pos = self.size + off
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = max(0, self.size - self.pos)
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.size, self.pos + n) - 1
        req = urllib.request.Request(
            self.url,
            headers={"Range": f"bytes={self.pos}-{end}", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = r.read()
        self.pos += len(data)
        return data

    def seekable(self):
        return True

    def readable(self):
        return True

    def close(self):
        pass


def _remote_zip_names(url):
    """远程读取 zip 的成员名单。失败抛异常。

    ★ 逐条线路试：直连 → v6 → v4 → gh-proxy。
      每条线路都试一遍 zipfile，中央目录读不出来就换下一条。
    """
    last = None
    for u in _mirror_urls(url):
        fp = None
        try:
            fp = _RangeFile(u, timeout=_timeout_for(u))
            with zipfile.ZipFile(fp) as z:
                return z.namelist()
        except Exception as e:                      # noqa: BLE001
            last = e
            log.debug("探测 %s 失败：%s", u, e)
        finally:
            if fp is not None:
                try:
                    fp.close()
                except Exception:
                    pass
    raise last or IOError("所有线路都失败")


def _has_exe(names):
    return any(n.lower().endswith(".exe") for n in names)


def _has_resource_dir(names):
    return any(n.startswith(RESOURCE_WHITELIST) for n in names)


def classify_assets(assets):
    """把 asset 分成 (程序包, 资源包)，识别不了的给 None。

    识别顺序：
      ① 读 zip 成员名单按内容判定（最可靠）
      ② 探测失败就退回文件名猜测

    ★ 同一个包可以**同时**是程序包和资源包。
      v1.8.3 的 pkmn.tools.v1.8.3.zip 里既有 exe 也有 scripts/，
      用户后来决定拆成两个包，但旧的/新造的都可能同时满足两边，
      所以这里不互斥，只记录“哪个包能干什么”。
    """
    exe_asset = None
    res_asset = None

    for a in assets:
        name = (a.get("name") or "").lower()
        if not name.endswith(".zip"):
            continue
        url = a.get("url") or ""
        if not url:
            continue

        try:
            names = _remote_zip_names(url)
        except Exception as e:                      # noqa: BLE001
            log.debug("探测 %s 失败，改用文件名判断：%s", a.get("name"), e)
            if "resource" in name or "assets" in name:
                res_asset = res_asset or a
            else:
                exe_asset = exe_asset or a
            continue

        if _has_exe(names):
            exe_asset = exe_asset or a
        if _has_resource_dir(names):
            res_asset = res_asset or a
        if not _has_exe(names) and not _has_resource_dir(names):
            log.debug("asset %s 既没 exe 也没资源目录，忽略", a.get("name"))

    return exe_asset, res_asset


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

    # 只在确实有新版本时才去探测 zip（探测要走网络，没必要每次都做）
    if newer:
        try:
            exe_a, res_a = classify_assets(info.get("assets") or [])
            info["exe_asset"] = exe_a
            info["res_asset"] = res_a
        except Exception as e:                      # noqa: BLE001
            log.debug("asset 识别失败：%s", e)
            info["exe_asset"] = None
            info["res_asset"] = None

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

    for u in _mirror_urls(url):
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
    返回 (ok, msg, path)。
    """
    try:
        with zipfile.ZipFile(zip_path) as z:
            cands = [i for i in z.infolist()
                     if not i.is_dir() and i.filename.lower().endswith(".exe")]
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

    d = os.path.join(config.BASE_DIR, UPDATE_DIR_NAME)
    if os.path.isdir(d):
        for name in os.listdir(d):
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

    ★ 同一个 asset 同时充当程序包和资源包时**只下一次**：
      v1.8.3 的包里面既有 exe 又有 scripts/，下两次就是白费 48MB。
      所以按 URL 去重，下载一次、两头用。
    """
    tmp = update_dir()
    parts = []

    res_a = info.get("res_asset") if do_resource else None
    exe_a = info.get("exe_asset") if do_exe else None

    # ---------- 按 URL 去重，只下一遍 ----------
    zips = {}                      # url -> 本地 zip 路径
    needed = []                    # [(用途, asset)]
    if res_a:
        needed.append(("res", res_a))
    if exe_a:
        needed.append(("exe", exe_a))

    for role, asset in needed:
        url = asset.get("url") or ""
        if not url:
            return False, "更新包缺少下载地址", False
        if url in zips:
            continue
        dst = os.path.join(tmp, "pkg_%d.zip" % len(zips))
        ok, msg = download(url, dst, progress, _digest_of(asset))
        if not ok:
            return False, f"{'资源包' if role == 'res' else '程序包'}下载失败：{msg}", False
        zips[url] = dst

    # ---------- 资源（用户显式勾选时才做） ----------
    if res_a:
        zpath = zips[res_a.get("url") or ""]
        ok, msg, _stats = extract_resource_zip(zpath, progress=progress)
        if not ok:
            return False, msg, False
        parts.append(msg)

    # ---------- exe ----------
    needs_restart = False
    if exe_a:
        zpath = zips[exe_a.get("url") or ""]
        ok, msg, new_exe = extract_exe(zpath, progress)
        if not ok:
            return False, msg, False
        ok, msg = apply_exe_update(new_exe)
        if not ok:
            return False, msg, False
        parts.append(msg)
        needs_restart = True

    # ---------- 收掉下载的临时包 ----------
    for p in zips.values():
        try:
            os.remove(p)
        except OSError:
            pass

    if not parts:
        return False, "这个版本没有可用的更新包", False
    return True, "；".join(parts), needs_restart
# probe
