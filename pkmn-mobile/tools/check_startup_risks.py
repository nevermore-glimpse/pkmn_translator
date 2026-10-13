# -*- coding: utf-8 -*-
"""
启动期风险自检 —— 专查「点开就闪退、连弹窗都没有」这一类问题。

为什么单独写一个
---------------
这类崩溃和普通崩溃的排查方式完全不同：普通崩溃至少有堆栈，而它们的
共同点是**崩在我们可以写日志之前**，用户那边只会说「打不开」。
所以只能靠**构建期静态检查**把它们挡在发版之前。

本脚本检查四项（每一项都对应一个真实踩过的坑，见每条的注释）：

    ① 主题/背景图里有没有 <bitmap android:src="@mipmap/...">，
       而那个 mipmap 名字在 *-anydpi-v26 下是个 <adaptive-icon> XML
       —— <bitmap> 只吃真图片，喂 XML 必然抛
          XmlPullParserException: <bitmap> requires a valid 'src' attribute
       而 windowBackground 是框架在 onCreate 之前就加载的。

    ② 清单里有没有 android:networkSecurityConfig
       —— 由系统在 Application.onCreate 之前解析。

    ③ 源码/依赖里有没有 androidx 的开机组件
       （androidx.startup.InitializationProvider 那批 ContentProvider、
         appComponentFactory），同样早于 Application.onCreate。

    ④ Application 子类里有没有 Python.start() / 大批量文件拷贝
       —— 会被启动看门狗 SIGKILL，且挂掉后 Activity 永远起不来，
          我们的诊断弹窗也就永远没机会显示。

用法：
    python tools/check_startup_risks.py
    python tools/check_startup_risks.py 路径/到/某个.apk     # 顺带查已打包的 APK
"""
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "android", "app", "src", "main")
RES = os.path.join(MAIN, "res")
MANIFEST = os.path.join(MAIN, "AndroidManifest.xml")
APP_JAVA = os.path.join(MAIN, "java", "com", "mali", "pkmntools", "App.java")
DEFAULT_APK = os.path.join(
    ROOT, "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk")

problems = []


def _rel(path):
    """相对 ROOT 的短路径；跨盘符时退回绝对路径，不让它把检查脚本自己搞崩。"""
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _strip_comments(text):
    """去掉 XML/Java 注释 —— 注释里提到某个坏写法是允许的（本仓库到处是说明）。"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    return text


def check_bitmap_src():
    """
    ① <bitmap android:src="@mipmap/X"> 且 X 在 anydpi 目录下是 XML。

    这是本项目最贵的一个坑：splash_window.xml 里这么写之后，
    Android 8.0+ 上窗口背景加载失败，App 直接打不开。
    """
    # 找出哪些 mipmap 名字在 *-anydpi* 目录里被定义成了 XML
    anydpi_names = set()
    for dirpath, _dirs, files in os.walk(RES):
        base = os.path.basename(dirpath)
        if "anydpi" not in base:
            continue
        for fn in files:
            if fn.endswith(".xml"):
                anydpi_names.add(os.path.splitext(fn)[0])
    if not anydpi_names:
        return
    pat = re.compile(r"<bitmap[^>]*android:src\s*=\s*\"@(mipmap|drawable)/([\w.]+)\"",
                     re.S)
    for dirpath, _dirs, files in os.walk(RES):
        for fn in files:
            if not fn.endswith(".xml"):
                continue
            p = os.path.join(dirpath, fn)
            body = _strip_comments(_read(p))
            for m in pat.finditer(body):
                if m.group(2) in anydpi_names:
                    problems.append(
                        f"① {_rel(p)}：<bitmap> 指向 @{m.group(1)}/"
                        f"{m.group(2)}，但它在 *-anydpi-v26 里是 <adaptive-icon> XML。\n"
                        f"     <bitmap> 只接受真图片，会抛 "
                        f"XmlPullParserException: <bitmap> requires a valid 'src' attribute。\n"
                        f"     请改用一张独立的普通 PNG（如 @drawable/splash_logo）。")


def check_manifest_source():
    """② 清单源码里不应该出现 networkSecurityConfig。"""
    body = _strip_comments(_read(MANIFEST))
    if "networkSecurityConfig" in body:
        problems.append(
            "② AndroidManifest.xml 里写了 android:networkSecurityConfig。\n"
            "     该配置由系统在 Application.onCreate **之前**解析，"
            "解析失败进程直接死、无弹窗。\n"
            "     本工具只连 127.0.0.1，用 android:usesCleartextTraffic=\"true\" 即可，"
            "把这条去掉。")


def check_application_class():
    """④ Application 子类里不能有耗时/危险动作。"""
    body = _strip_comments(_read(APP_JAVA))
    if "Python.start" in body:
        problems.append(
            "④ App.java 里调用了 Python.start()。\n"
            "     Chaquopy 首次启动要解包 ~7MB stdlib，耗时数秒：\n"
            "       · 会被国产 ROM 的启动看门狗 SIGKILL（无弹窗）；\n"
            "       · 一旦失败，Activity 永远起不来，诊断弹窗也没机会显示。\n"
            "     请把 Python 启动放到 MainActivity 的后台线程里。")


def check_built_apk(apk):
    """③ 已打包的 APK：查合并清单里有没有 androidx 开机组件。"""
    if not os.path.isfile(apk):
        print(f"  （跳过 APK 检查：找不到 {os.path.relpath(apk, ROOT)}，先构建一次）")
        return
    aapt2 = _find_aapt2()
    if not aapt2:
        print("  （跳过 APK 检查：没找到 aapt2，可设 ANDROID_HOME 或装 build-tools）")
        return

    try:
        out = subprocess.run(
            [aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", apk],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120).stdout
    except Exception as e:                                    # noqa: BLE001
        print(f"  （aapt2 执行失败，跳过：{e}）")
        return

    size_mb = os.path.getsize(apk) / 1024 / 1024
    print(f"  APK：{_rel(apk)}  {size_mb:.1f} MB")

    for needle, why in (
        ("androidx.startup", "androidx 的 InitializationProvider 会在 "
                             "Application.onCreate 之前创建"),
        ("androidx.core.app.CoreComponentFactory", "自定义组件工厂同样是 androidx 注入的"),
        ("networkSecurityConfig", "该配置由系统在应用代码之前解析"),
    ):
        if needle in out:
            problems.append(
                f"③ 合并清单里仍有 {needle} —— {why}。\n"
                f"     本工具不需要任何 androidx 依赖，"
                f"请确认 app/build.gradle 的 dependencies 为空。")
    if "extractNativeLibs" in out and "extractNativeLibs(0x010104ea)=true" not in out:
        problems.append(
            "③ 合并清单里 extractNativeLibs 不是 true。\n"
            "     参照 APK（DeepSeek / MT管理器 / 口袋改版工具盒）全部为 true，"
            "改成 false 会在部分 ROM 上加载 .so 失败、秒退。")
    if "provider" not in out:
        print("  ✔ 合并清单里没有任何 ContentProvider（没有开机期初始化组件）")
    for key in ("versionName", "targetSdkVersion"):
        for line in out.splitlines():
            if key in line:
                print("  " + line.strip()[:100])
                break


def _find_aapt2():
    import glob
    env = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    roots = [env] if env else []
    local = os.path.join(ROOT, "android", "local.properties")
    for line in _read(local).splitlines():
        if line.startswith("sdk.dir="):
            roots.append(line.split("=", 1)[1].strip().replace("\\\\", "\\"))
    roots += [r"C:\Android"]
    for r in roots:
        if not r:
            continue
        hits = sorted(glob.glob(os.path.join(r, "build-tools", "*", "aapt2.exe"))) \
            or sorted(glob.glob(os.path.join(r, "build-tools", "*", "aapt2")))
        if hits:
            return hits[-1]
    return None


def main():
    apk = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_APK
    print("启动期风险自检：")
    check_bitmap_src()
    check_manifest_source()
    check_application_class()
    check_built_apk(apk)

    print()
    if problems:
        print(f"✘ 发现 {len(problems)} 个启动期风险：\n")
        for p in problems:
            print("  " + p + "\n")
        return 1
    print("✔ 没有发现「点开就闪退、无弹窗」类型的启动期风险。")
    print("  （这只覆盖静态可查的那几类；真机仍打不开时请配合 logcat：")
    print("    adb logcat -s PkmnTools:V AndroidRuntime:E Chaquopy:V）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
