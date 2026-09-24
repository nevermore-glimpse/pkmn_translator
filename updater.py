# -*- coding: utf-8 -*-
"""
检查更新：从 GitHub Releases 获取最新 tag，与当前版本比对。

只做读取，不自动下载；有新版本时由调用方（GUI）弹窗提示。
"""
import json
import re
import urllib.request

import config
from logger import get_logger

log = get_logger("updater")

# 仓库地址（与 config.AUTHOR_GITHUB 保持一致）
REPO_OWNER    = "nevermore-glimpse"
REPO_NAME     = "pkmn_translator"
API_URL       = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
RELEASES_URL  = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases"
TAG_URL       = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/tag/{{tag}}"

UA = f"{REPO_NAME}-translator/{getattr(config, 'VERSION', '0')}"


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


def fetch_latest(timeout=8):
    """拉取最新 release 信息，返回 dict 或 None（失败返回 None）。"""
    req = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": UA,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))

    tag = (data.get("tag_name") or "").strip()
    if not tag:
        return None

    url = data.get("html_url") or TAG_URL.format(tag=tag)
    return {
        "tag":   tag,
        "name":  data.get("name") or tag,
        "url":   url,
        "notes": (data.get("body") or "").strip()[:600],
    }


def check_update(timeout=8):
    """
    返回 (has_update: bool, info: dict)。
    info 含 tag / url / notes；出错时含 error。
    """
    try:
        info = fetch_latest(timeout)
    except Exception as e:
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
    except Exception:
        newer = new != cur

    info["current"] = getattr(config, "VERSION", "")
    return newer, info
