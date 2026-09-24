# -*- coding: utf-8 -*-
"""GUI 冒烟：构建窗口、切换全部页面、模拟文件选择，5 秒后自动关闭。"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk

import gui

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "work", "_e2e_in.txt")

errors = []


def main():
    root = tk.Tk()
    try:
        app = gui.App(root)
        gui.apply_window_effects(root)

        def step():
            try:
                for key in list(gui.MENU_KEYS.values()):
                    app.show(key)
                    root.update()
                print("[ok] 全部页面切换完成")

                # 文件侧边栏
                if os.path.exists(SRC):
                    for fp in (app.fp_translate, app.fp_report,
                               app.fp_terms, app.fp_prefix, app.fp_polish):
                        fp.add_files([SRC])
                    print("[ok] 文件侧边栏：",
                          len(app.fp_translate.selected()), "个文件")

                # 术语 / 前缀表
                print("[ok] 术语行：", len(app.term_tree.get_children()))
                print("[ok] 前缀行：", len(app.prefix_tree.get_children()))
                print("[ok] 设置行：", len(app.setting_widgets))
                print("[ok] 日志长度：",
                      len(app.log_text.get("1.0", "end-1c")))

                # 模拟编辑一条术语 / 前缀
                kids = app.term_tree.get_children()
                if kids:
                    app.term_tree.set(kids[0], "#3", "测试译文")
                    app._on_term_edit(kids[0], "#3", "测试译文")
                    print("[ok] 术语编辑记录：", list(app.term_edits.items())[:2])
                pk = app.prefix_tree.get_children()
                if pk:
                    app._on_prefix_edit(pk[0], "#2", "测试前缀")
                    print("[ok] 前缀编辑记录：", list(app.prefix_edits.items())[:2])

                # 报告表填充
                app._fill_report({SRC: [
                    {"kind": "疑似未翻译", "line_no": 3,
                     "src": "abc", "dst": "abc", "detail": "测试"}]})
                print("[ok] 报告表行数：", len(app.report_tree.get_children()))

                # 进度/日志
                app._on_progress(3, 10, "测试进度")
                print("[ok] 进度：", app.prog_var.get())
            except Exception:
                errors.append(traceback.format_exc())
            root.after(300, root.destroy)

        root.after(3500, step)
        root.mainloop()
    except Exception:
        errors.append(traceback.format_exc())

    if errors:
        print("\n[ERROR]")
        for e in errors:
            print(e)
        sys.exit(1)
    print("\nGUI 冒烟通过")


if __name__ == "__main__":
    main()
