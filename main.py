# -*- coding: utf-8 -*-
"""宝可梦同人游戏翻译工具 —— 主入口。"""
import os
import sys
import traceback

import config
from logger import get_logger

log = get_logger("main")

import commands
import processor as PR
import env_check
import settings


BANNER = """\
====================================================================
                      宝可梦同人游戏翻译工具
作者github：
https://github.com/nevermore-glimpse
作者bilibili（玛俐大小姐想让我告白）：
https://space.bilibili.com/3546602748775226?spm_id_from=333.1007.0.0
====================================================================
  模型：{model}
  工作目录：{base}
  术语表：{terms} 条
--------------------------------------------------------------------
  输入文件：{input}
  输出文件：{output}
--------------------------------------------------------------------
  1. 翻译（术语匹配大小写不敏感）
  2. 重翻未翻译内容
  3. Excel 转术语表
  4. 切换输入文件
  5. 术语更新后重翻相关句子
  6. 设置
  7. 重新检查环境
  0. 退出
====================================================================
"""


def _short(path, max_len=58):
    if not path:
        return ""
    if len(path) <= max_len:
        return path
    keep = (max_len - 3) // 2
    return path[:keep] + "..." + path[-keep:]


def _startup_checks():
    """启动环境检查；如遇致命问题给出修复建议。"""
    result = env_check.check_all(verbose=True)

    # Python 版本
    if not result["python"][0]:
        print("\n✘ Python 版本过低，请升级到 3.9+")
        input("按回车退出...")
        sys.exit(1)

    # 依赖
    if not result["packages"][0]:
        print("\n✘ 依赖缺失，请运行：pip install -r requirements.txt")
        input("按回车继续（Ollama 相关功能可能失败）...")

    # Ollama 服务
    if not result["ollama_service"][0]:
        ok = env_check.ensure_ollama_interactive()
        if not ok:
            print("\n⚠ Ollama 未就绪，翻译功能将不可用（其余功能正常）")
            input("按回车继续...")
    # 模型未安装
    elif not result["ollama_model"][0]:
        print(f"\n⚠ {result['ollama_model'][1]}")
        print(f"  修复：ollama pull {config.MODEL}")
        input("按回车继续...")

def _ensure_snapshot_once():
    """
    首次启动时建立术语表快照，并把 SNAPSHOT_INITIALIZED 置为 True。
    之后启动就不再自动重建。
    """
    if getattr(config, "SNAPSHOT_INITIALIZED", False):
        return

    try:
        import term_sync as TS
        import settings

        terms = TS.load_current_terms()
        if terms:
            TS.save_snapshot(terms)
            log.info("首次启动：已建立术语表快照（%d 条）", len(terms))
        else:
            log.info("首次启动：术语表为空，跳过快照")

        # 无论有没有术语，都置为 True，避免每次启动都重试
        ok = settings.set_internal("SNAPSHOT_INITIALIZED", True)
        if not ok:
            log.warning("无法持久化 SNAPSHOT_INITIALIZED 标志")
    except Exception as e:
        log.warning("建立初始快照失败：%s", e)


def main():
    os.makedirs(config.BASE_DIR, exist_ok=True)
    os.makedirs(config.REPORT_DIR, exist_ok=True)

    log.info("程序启动  模型=%s  工作目录=%s", config.MODEL, config.BASE_DIR)

    # ---------- 启动检查 ----------
    _startup_checks()

    # ---------- 术语表 ----------
    try:
        PR.load_terms()
    except Exception as e:
        log.error("术语表加载失败：%s", e)

    # ★ 首次启动建立快照
    _ensure_snapshot_once()
    # ---------- 主循环 ----------
    while True:
        print(BANNER.format(
            model=config.MODEL,
            base=_short(config.BASE_DIR, 55),
            terms=len(PR._TERMS),
            input=_short(config.Runtime.input_file, 55),
            output=_short(config.Runtime.output_file, 55),
        ))
        try:
            choice = input("请选择：").strip()
        except EOFError:
            break

        log.info("菜单选择：%s", choice)

        try:
            if choice == "1":
                commands.cmd_translate()
            elif choice == "2":
                commands.cmd_retranslate_failed()
            elif choice == "3":
                commands.cmd_build_terms()
            elif choice == "4":
                commands.cmd_switch_file()
            elif choice == "5":
                commands.cmd_retranslate_terms()
            elif choice == "6":
                settings.show_menu()
            elif choice == "7":
                env_check.check_all(verbose=True)
            elif choice == "0":
                log.info("用户退出")
                print("再见")
                break
            else:
                print("无效选项")
        except KeyboardInterrupt:
            log.warning("用户中断")
            print("\n[中断] 已返回主菜单")
        except Exception:
            log.error("未捕获异常：\n%s", traceback.format_exc())
            print("\n[错误] 详见日志：logs\\translate_*.log")

        try:
            input("\n按回车继续...")
        except EOFError:
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("主程序被中断")
        print("\n[退出]")
        sys.exit(0)