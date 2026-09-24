# -*- coding: utf-8 -*-
"""宝可梦同人游戏翻译工具 —— 主入口（CLI / GUI）。"""
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
                    {title}
作者github：
{github}
作者bilibili（{author}）：
{bilibili}
====================================================================
  模型：{model}
  工作目录：{base}
  术语表：{terms} 条
--------------------------------------------------------------------
  输入文件：{input}
  输出文件：{output}
--------------------------------------------------------------------
  1. 翻译
  2. 重翻检查报告内容
  3. 术语更新后重翻
  4. 前缀字典（查看 / 应用）
  5. 中文润色重翻
  6. Excel 转术语表
  7. 设置
  8. 日志 / 环境检查
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

    if not result["python"][0]:
        print("\n✘ Python 版本过低，请升级到 3.9+")
        input("按回车退出...")
        sys.exit(1)

    if not result["packages"][0]:
        print("\n✘ 依赖缺失，请运行：pip install -r requirements.txt")
        input("按回车继续（Ollama 相关功能可能失败）...")

    if not result["ollama_service"][0]:
        ok = env_check.ensure_ollama_interactive()
        if not ok:
            print("\n⚠ Ollama 未就绪，翻译功能将不可用（其余功能正常）")
            input("按回车继续...")
    elif not result["ollama_model"][0]:
        print(f"\n⚠ {result['ollama_model'][1]}")
        print(f"  修复：ollama pull {config.MODEL}")
        input("按回车继续...")


def _ensure_snapshot_once():
    """首次启动时建立术语表快照，之后不再自动重建。"""
    if getattr(config, "SNAPSHOT_INITIALIZED", False):
        return

    try:
        import term_sync as TS
        terms = TS.load_current_terms()
        if terms:
            TS.save_snapshot(terms)
            log.info("首次启动：已建立术语表快照（%d 条）", len(terms))
        else:
            log.info("首次启动：术语表为空，跳过快照")

        if not settings.set_internal("SNAPSHOT_INITIALIZED", True):
            log.warning("无法持久化 SNAPSHOT_INITIALIZED 标志")
    except Exception as e:
        log.warning("建立初始快照失败：%s", e)


def _boot():
    """公共初始化。"""
    os.makedirs(config.BASE_DIR, exist_ok=True)
    os.makedirs(config.REPORT_DIR, exist_ok=True)

    config.Runtime.load()          # ★ 恢复上次使用的文件/目录

    log.info("程序启动  v%s  模型=%s  工作目录=%s",
             config.VERSION, config.MODEL, config.BASE_DIR)

    try:
        PR.load_terms()
    except Exception as e:
        log.error("术语表加载失败：%s", e)

    _ensure_snapshot_once()


def run_cli():
    """命令行主循环。"""
    import bridge

    bridge.set_sinks(None, None, None)
    _startup_checks()

    while True:
        print(BANNER.format(
            title=config.APP_TITLE,
            github=config.AUTHOR_GITHUB,
            author=config.AUTHOR_NAME,
            bilibili=config.AUTHOR_BILIBILI,
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
                commands.cmd_retranslate_report()
            elif choice == "3":
                commands.cmd_retranslate_terms()
            elif choice == "4":
                commands.cmd_review_prefix_dict()
            elif choice == "5":
                commands.cmd_polish()
            elif choice == "6":
                commands.cmd_build_terms()
            elif choice == "7":
                settings.show_menu()
            elif choice == "8":
                commands.cmd_show_logs()
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


def run_gui():
    """图形界面。"""
    try:
        import gui
    except Exception as e:
        log.error("GUI 加载失败，退回命令行：%s\n%s", e, traceback.format_exc())
        print(f"GUI 加载失败，退回命令行：{e}")
        run_cli()
        return
    gui.main()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    want_cli = any(a in ("--cli", "-c", "--console") for a in argv)
    want_gui = any(a in ("--gui", "-g", "--window") for a in argv)

    _boot()

    if not want_cli:
        try:
            import tkinter  # noqa: F401
            has_tk = True
        except Exception:
            has_tk = False

        if has_tk or want_gui:
            if not has_tk:
                print("未检测到 tkinter，使用命令行模式")
            else:
                run_gui()
                return

    run_cli()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("主程序被中断")
        print("\n[退出]")
        sys.exit(0)
