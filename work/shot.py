# -*- coding: utf-8 -*-
"""启动 GUI 并截图，用于人工检查界面。用法：python work/shot.py [页面名] [等待秒]"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")

name = sys.argv[1] if len(sys.argv) > 1 else "translate"
wait = float(sys.argv[2]) if len(sys.argv) > 2 else 9.0

# 让 GUI 启动后直接跳到指定页面
driver = f"""
import sys, ctypes, tkinter as tk
sys.path.insert(0, r"{BASE}")
import gui
root = tk.Tk()
app = gui.App(root)
gui.apply_window_effects(root)
root.geometry("1200x780+150+60")
root.update()
root.attributes("-topmost", True)
root.lift()
root.focus_force()
root.after(1200, lambda: app.show({name!r}))
root.after(int({wait} * 1000), root.destroy)

def dump_pos():
    nl = chr(10)
    lines = ["POS %d %d %d %d" % (root.winfo_rootx(), root.winfo_rooty(),
                                  root.winfo_width(), root.winfo_height())]
    for nm in ("fp_translate", "fp_report", "fp_terms", "fp_prefix",
               "fp_polish"):
        fp = getattr(app, nm, None)
        if fp is not None and fp.winfo_exists():
            lines.append("%s %d %d %d %d" % (
                nm, fp.winfo_rootx(), fp.winfo_rooty(),
                fp.winfo_width(), fp.winfo_height()))
    with open(r"{BASE}\work\_pos.txt", "w", encoding="utf-8") as f:
        f.write(nl.join(lines))
    root.update_idletasks()

root.after(int({wait} * 1000) - 300, dump_pos)
root.mainloop()
"""

proc = subprocess.Popen([PY, "-c", driver], cwd=BASE)
time.sleep(wait + 1.2)

try:
    from PIL import ImageGrab
    img = ImageGrab.grab()
    out = os.path.join(BASE, "work", f"shot_{name}.png")
    img.save(out)
    print("saved:", out, img.size)
except Exception as e:
    print("截图失败：", e)

# 抓图后再读一次控件位置（写到文件，避免与主进程时序竞争）
try:
    with open(os.path.join(BASE, "work", "_pos.txt"), "r", encoding="utf-8") as f:
        print(f.read())
except Exception as e:
    print("无位置信息", e)

try:
    proc.terminate()
except Exception:
    pass
