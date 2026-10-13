package com.mali.pkmntools;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.SystemClock;
import android.util.Log;
import android.webkit.WebView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * 崩溃诊断 —— 存在的唯一理由是「手机打不开、但拿不到 logcat」这个困境。
 *
 * <p>问题出在国产 ROM 上时，用户不会去连 adb 抓日志，只会告诉你「打不开」。
 * 与其猜，不如让 App 把现场自己记下来：
 *
 * <ul>
 *   <li>任何未捕获异常 → 写进 {@code crash.log}，下次启动直接显示给用户；
 *   <li>WebView 渲染进程被杀（{@code onRenderProcessGone}）—— 这在国产
 *       WebView 上很常见，表现就是「白屏/闪一下就没」，同样要记；
 *   <li>系统信息（Android 版本、ABI、**页大小**、WebView 版本）也一起记，
 *       因为 16KB 页这类问题光看报错是猜不出来的。
 * </ul>
 *
 * <p>诊断文本会显示在界面上，也提供「复制」，用户直接粘给作者即可。
 * 全程不联网。
 */
public final class Diagnostics {

    private static final String TAG = "PkmnTools";
    private static final String FILE = "diagnostics.txt";
    private static final String CRASH = "crash.log";

    /**
     * 构建标识。
     *
     * <p>★ 存在的理由很实际：用户装没装上新包，光看界面是分不出来的。
     * 把这一行写进诊断报告，用户一复制就能确认跑的是哪一版 ——
     * 免得在「其实装的还是旧 APK」上白排查一轮。
     */
    public static final String BUILD_TAG =
            "2026-10-13 v1.6：修目录浏览权限起点 / 补 7 种开启 DEBUG 方式 / "
            + "修关于页基准数据缺失 / 更正作者信息";

    private static final List<String> steps = new ArrayList<>();
    private static final long t0 = SystemClock.elapsedRealtime();

    /**
     * 每记一步就回调一次，用来把进度**实时画在屏幕上**。
     *
     * <p>为什么需要：用户拿不到 logcat，只能靠「屏幕上有什么」来判断。
     * 之前只有失败时才显示报告，一旦卡在某一步（而不是直接崩），
     * 用户看到的就只是一个转圈的「正在准备…」，什么信息都没有。
     * 现在每一步都会刷到界面上，截图即可定位。
     */
    public interface Sink {
        void onStep(String line);
    }

    private static volatile Sink sink;

    public static void setSink(Sink s) {
        sink = s;
    }

    private Diagnostics() {
    }

    // ================================================================
    // 启动过程打点
    // ================================================================

    /** 记录一步。带上毫秒时间戳，方便看是哪一步卡住/失败。 */
    public static synchronized void step(String msg) {
        long dt = SystemClock.elapsedRealtime() - t0;
        String line = String.format("[%5dms] %s", dt, msg);
        steps.add(line);
        Log.i(TAG, line);
        Sink s = sink;
        if (s != null) {
            try {
                s.onStep(line);
            } catch (Throwable ignore) {
                // 回调本身出错不能影响主流程
            }
        }
    }

    public static synchronized void error(String where, Throwable t) {
        String line = "[" + where + "] " + describe(t);
        steps.add("✘ " + line);
        Log.e(TAG, line, t);
        append(CRASH, "\n=== " + where + " @ "
                + System.currentTimeMillis() + " ===\n" + stackOf(t) + "\n");
        Sink s = sink;
        if (s != null) {
            try {
                s.onStep("✘ " + line);
            } catch (Throwable ignore) {
                // 同上
            }
        }
    }

    // ================================================================
    // 全局兜底：任何没接住的崩溃都记下来
    // ================================================================

    public static void installCrashHandler(final Context ctx) {
        final Context app = ctx.getApplicationContext();
        final Thread.UncaughtExceptionHandler prev =
                Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler(
                (t, e) -> {
                    try {
                        String body = stackOf(e);
                        append(CRASH, "\n=== 致命崩溃 " + t.getName()
                                + " @ " + System.currentTimeMillis() + " ===\n"
                                + body + "\n\n"
                                + "--- 当时的环境 ---\n" + environment(app) + "\n");
                        append(FILE, "发生致命崩溃：" + t.getName() + "\n");
                    } catch (Throwable ignore) {
                        // 崩溃处理里再抛就真没救了
                    }
                    if (prev != null) {
                        prev.uncaughtException(t, e);   // 交给系统照旧弹「已停止」
                    } else {
                        android.os.Process.killProcess(android.os.Process.myPid());
                    }
                });
    }

    public static boolean hasCrash() {
        return new File(dir(), CRASH).isFile()
                && new File(dir(), CRASH).length() > 0;
    }

    public static String readCrash() {
        return read(CRASH);
    }

    public static void clearCrash() {
        File f = new File(dir(), CRASH);
        //noinspection ResultOfMethodCallIgnored
        f.delete();
    }

    // ================================================================
    // 「上次启动未完成」标记
    // ================================================================

    private static final String DIRTY = "startup.dirty";

    /**
     * 标记一次「启动正在进行中」，返回**上一次**是否也是这样开始的。
     *
     * <p>针对的正是「打开即闪退，连 Activity 都进不去」这种情况：
     * 原生库 dlopen 失败发生在进程初始化阶段，Java 层的崩溃处理器
     * 还没来得及装载，什么都记不下来。这个标记是那段时间唯一的线索。
     *
     * @return true 表示上次启动也没走完
     */
    public static boolean beginStartup() {
        boolean dirty = false;
        try {
            File f = new File(dir(), DIRTY);
            dirty = f.isFile() && f.length() > 0;
        } catch (Throwable ignore) {
            // 读不到就当没有
        }
        try {
            FileOutputStream out = new FileOutputStream(new File(dir(), DIRTY));
            out.write(String.valueOf(System.currentTimeMillis())
                    .getBytes(StandardCharsets.UTF_8));
            out.close();
        } catch (Throwable ignore) {
            // 写不进去就算了
        }
        if (dirty) {
            append(CRASH, "\n=== 上次启动未完成 ===\n"
                    + "进程在走到成功启动之前就退出了（最常见原因："
                    + "原生库加载失败）。当前环境：\n"
                    + "（见下方最近一次环境快照）\n");
        }
        return dirty;
    }

    /** 成功启动到一定程度后调用，清掉标记。 */
    public static void endStartup() {
        try {
            //noinspection ResultOfMethodCallIgnored
            new File(dir(), DIRTY).delete();
        } catch (Throwable ignore) {
        }
    }

    /** 当前已记录的步骤快照（给界面回填历史用）。 */
    public static synchronized List<String> snapshot() {
        return new ArrayList<>(steps);
    }

    // ================================================================
    // 报告文本
    // ================================================================

    /**
     * 汇总一份能直接发给作者的报告。
     *
     * <p>刻意包含「页大小」这一项 —— Android 15/16 的 16KB 页问题，
     * 从崩溃日志里是看不出来的，只有把系统信息一起发过去才能定位。
     */
    public static String report(Context ctx) {
        StringBuilder sb = new StringBuilder();
        sb.append("===== 宝可梦同人工具 · 诊断报告 =====\n");
        sb.append("构建标识：").append(BUILD_TAG).append("\n");
        sb.append("生成时间：").append(now()).append("\n\n");

        sb.append("【运行环境】\n");
        sb.append(environment(ctx)).append("\n");

        sb.append("\n【启动过程】\n");
        synchronized (Diagnostics.class) {
            if (steps.isEmpty()) {
                sb.append("（没有记录 —— 说明根本没走到打点这一步，"
                        + "崩溃发生在 onCreate 之前）\n");
            } else {
                for (String s : steps) {
                    sb.append(s).append('\n');
                }
            }
        }

        String crash = readCrash();
        sb.append("\n【已记录的崩溃】\n");
        sb.append(crash.isEmpty() ? "（无）\n" : crash + "\n");
        return sb.toString();
    }

    private static String environment(Context ctx) {
        StringBuilder sb = new StringBuilder();
        sb.append("  Android      : ").append(Build.VERSION.RELEASE)
                .append(" (API ").append(Build.VERSION.SDK_INT).append(")\n");
        sb.append("  设备         : ").append(Build.MANUFACTURER)
                .append(' ').append(Build.MODEL).append('\n');
        sb.append("  架构         : ")
                .append(java.util.Arrays.toString(Build.SUPPORTED_ABIS)).append('\n');
        sb.append("  内存页大小   : ").append(pageSizeText()).append('\n');
        sb.append("  WebView      : ").append(webViewVersion(ctx)).append('\n');
        sb.append("  存储权限     : ")
                .append(hasAllFiles(ctx) ? "已授予" : "未授予").append('\n');
        sb.append("  应用版本     : ").append(appVersion(ctx)).append('\n');
        return sb.toString();
    }

    /**
     * 当前设备的内存页大小。
     *
     * <p>这是判断「16KB 页设备」最直接的依据。
     *
     * <p>首选 {@code Os.sysconf(_SC_PAGESIZE)} —— 它就是 C 的 getpagesize()，
     * 权威、一次调用就准。
     *
     * <p>★ 之前只靠 /proc/self/maps 推算，在一台 vivo 上报出过
     * <b>134217728 字节（128MB）</b>：那种算法取的是「最大的 2 的幂对齐」，
     * 把某个大映射的起始地址当成了页大小 —— 纯属误导。现改为 sysconf 优先，
     * maps 只作兜底并明确标注「仅供参考」。
     */
    private static String pageSizeText() {
        try {
            long ps = android.system.Os.sysconf(
                    android.system.OsConstants._SC_PAGESIZE);
            if (ps > 0) {
                return ps >= 16384
                        ? ps + " 字节（★ 16KB 页设备，需要 16KB 对齐的原生库）"
                        : ps + " 字节";
            }
        } catch (Throwable ignore) {
            // 走下面的 maps 兜底
        }
        long guess = pageSizeFromMaps();
        if (guess > 0) {
            return guess + " 字节（maps 推算，仅供参考）";
        }
        return "未知";
    }

    /**
     * 兜底：从 /proc/self/maps 推算页大小。
     *
     * <p>所有映射的起始地址都是页对齐的，所以「能整除某个起始地址的最大
     * 2 的幂」≥ 页大小；而只要有**任意一个**映射落在奇数号页边界上，
     * 它正好等于页大小。因此要取**最小**值 —— 取最大值正是上面那个
     * 「128MB」错误答案的来源。
     */
    private static long pageSizeFromMaps() {
        try (java.io.BufferedReader r = new java.io.BufferedReader(
                new java.io.FileReader("/proc/self/maps"))) {
            String line;
            long best = Long.MAX_VALUE;
            boolean any = false;
            while ((line = r.readLine()) != null) {
                int sp = line.indexOf(' ');
                if (sp <= 0) {
                    continue;
                }
                String range = line.substring(0, sp);
                int dash = range.indexOf('-');
                if (dash <= 0) {
                    continue;
                }
                try {
                    long start = Long.parseLong(range.substring(0, dash), 16);
                    if (start == 0) {
                        continue;
                    }
                    best = Math.min(best, start & (-start));   // 最大 2 的幂因子
                    any = true;
                } catch (NumberFormatException ignore) {
                    // 有一行解析不了不算事
                }
            }
            if (!any || best == Long.MAX_VALUE) {
                return 0;
            }
            return Math.max(best, 4096);        // 小于 4KB 的多半是特殊映射
        } catch (Throwable t) {
            return 0;
        }
    }

    private static String webViewVersion(Context ctx) {
        // 优先查 WebView 提供包的版本名 —— 国产 ROM 的「系统浏览器」
        // 与 Google WebView 包名不同，两个都试。
        String[] pkgs = {"com.google.android.webview", "com.android.webview",
                         "com.tencent.tbrowser", "com.vivo.browser",
                         "com.baidu.browser.webapps"};
        for (String p : pkgs) {
            try {
                android.content.pm.PackageInfo pi = ctx.getPackageManager()
                        .getPackageInfo(p, 0);
                return p + " · " + pi.versionName;
            } catch (Throwable ignore) {
                // 换下一个
            }
        }
        // 都查不到：至少把「有没有 WebView」这件事说清楚。
        // 有些系统禁用了 WebView 组件，只装应用是打不开的 —— 这本身就是要报的信息。
        try {
            Class<?> c = Class.forName("android.webkit.WebView");
            c.getMethod("getCurrentWebViewPackageName");
            return "已找到 WebView，但读不到版本号（可能是系统内置组件）";
        } catch (Throwable t) {
            return "★ 找不到系统 WebView —— 需要在「设置 → 应用管理」里"
                    + "安装或启用 WebView 组件";
        }
    }

    private static boolean hasAllFiles(Context ctx) {
        try {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
                return true;
            }
            return android.os.Environment.isExternalStorageManager();
        } catch (Throwable t) {
            return false;
        }
    }

    private static String appVersion(Context ctx) {
        try {
            PackageInfo pi = ctx.getPackageManager()
                    .getPackageInfo(ctx.getPackageName(), 0);
            return pi.versionName + " (code " + pi.versionCode + ")";
        } catch (Throwable t) {
            return "未知";
        }
    }

    // ================================================================
    // 小工具
    // ================================================================

    /** 把异常翻译成人话；认得出来的常见问题直接给建议。 */
    public static String describe(Throwable t) {
        String raw = t.getClass().getSimpleName() + ": " + t.getMessage();
        String m = raw.toLowerCase();
        if (m.contains("dlopen") || m.contains("tag") && m.contains("hash")) {
            return raw + "\n      → 原生库加载失败。这台设备的内存页大小"
                    + "与 APK 里的库不匹配（见下方【运行环境】）。";
        }
        if (m.contains("outofmemory") || t instanceof OutOfMemoryError) {
            return raw + "\n      → 内存不够。可以关掉其他应用再试。";
        }
        if (t instanceof NoClassDefFoundError || m.contains("classnotfound")) {
            return raw + "\n      → APK 不完整或安装被系统优化过，"
                    + "建议先卸载再重装。";
        }
        return raw;
    }

    private static String stackOf(Throwable t) {
        StringWriter sw = new StringWriter();
        t.printStackTrace(new PrintWriter(sw));
        return sw.toString();
    }

    private static String now() {
        java.text.SimpleDateFormat f =
                new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
        return f.format(new java.util.Date());
    }

    /**
     * 诊断文件的落盘目录。
     *
     * <p>正常情况是 App 私有目录（由 {@link #init} 注入）；拿不到时退到
     * 系统给的临时目录。**不能写死 /data/data/包名** —— 那需要先有 Context
     * 才能算出来，正是这里没有的东西。
     */
    private static File DIR;

    public static void init(Context ctx) {
        try {
            File d = ctx.getFilesDir();
            if (d != null && (d.isDirectory() || d.mkdirs())) {
                DIR = d;
                return;
            }
        } catch (Throwable ignore) {
            // 继续走兜底
        }
        DIR = null;
    }

    private static File dir() {
        if (DIR != null) {
            return DIR;
        }
        File d = new File(System.getProperty("java.io.tmpdir", "."));
        if (!d.isDirectory()) {
            //noinspection ResultOfMethodCallIgnored
            d.mkdirs();
        }
        return d;
    }

    private static void append(String name, String text) {
        try {
            File f = new File(dir(), name);
            FileOutputStream out = new FileOutputStream(f, true);
            try {
                out.write(text.getBytes(StandardCharsets.UTF_8));
            } finally {
                out.close();
            }
        } catch (Throwable ignore) {
            // 诊断功能自己失败就算了，不能因此再崩一次
        }
    }

    private static String read(String name) {
        try {
            File f = new File(dir(), name);
            if (!f.isFile()) {
                return "";
            }
            byte[] buf = new byte[(int) f.length()];
            FileInputStreamExt.read(f, buf);
            return new String(buf, StandardCharsets.UTF_8);
        } catch (Throwable t) {
            return "";
        }
    }

    /** 避免在 import 列表里再引一个 InputStream，简单包一下。 */
    private static final class FileInputStreamExt {
        static void read(File f, byte[] buf) throws java.io.IOException {
            try (java.io.FileInputStream in = new java.io.FileInputStream(f)) {
                int off = 0;
                while (off < buf.length) {
                    int n = in.read(buf, off, buf.length - off);
                    if (n < 0) {
                        break;
                    }
                    off += n;
                }
            }
        }
    }
}