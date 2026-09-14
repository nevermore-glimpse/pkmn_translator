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


BANNER = """\
========================================================
        宝可梦同人游戏翻译工具
========================================================
  模型：{model}
  工作目录：{base}
  术语表：{terms} 条
--------------------------------------------------------
  输入文件：{input}
  输出文件：{output}
--------------------------------------------------------
  1. 翻译
  2. 检查（未翻译 / 符号不匹配 / 特殊行）
  3. Excel 转术语表
  4. 切换输入文件
  0. 退出
========================================================
"""


def _short(path, max_len=60):
    """路径太长就缩略显示（保留头尾）。"""
    if not path:
        return ""
    if len(path) <= max_len:
        return path
    keep = (max_len - 3) // 2
    return path[:keep] + "..." + path[-keep:]


def main():
    os.makedirs(config.BASE_DIR, exist_ok=True)
    os.makedirs(config.REPORT_DIR, exist_ok=True)

    log.info("程序启动  模型=%s  工作目录=%s", config.MODEL, config.BASE_DIR)

    # 启动时加载一次术语表
    try:
        PR.load_terms()
    except Exception as e:
        log.error("术语表加载失败：%s", e)

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
            print()
            break

        log.info("菜单选择：%s", choice)

        try:
            if choice == "1":
                commands.cmd_translate()
            elif choice == "2":
                commands.cmd_check()
            elif choice == "3":
                commands.cmd_build_terms()
            elif choice == "4":
                commands.cmd_switch_file()
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