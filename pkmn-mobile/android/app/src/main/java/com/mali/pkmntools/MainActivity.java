package com.mali.pkmntools;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.util.Log;
import android.view.View;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.List;

/**
 * 壳：起一个 CPython，把里面的 HTTP 服务跑起来，然后用 WebView 打开它。
 *
 * <p>界面完全是 HTML —— 改 UI 不用碰 Java。真正的业务逻辑在 Python 侧，
 * 跑的就是电脑版那份 core/。
 *
 * <p><b>★ 为什么是 {@link Activity} 而不是 AppCompatActivity</b>：
 * AppCompat 会把 androidx 的一批开机组件塞进清单（androidx.startup 的
 * ContentProvider、appComponentFactory 等），而 ContentProvider 是系统在
 * {@code Application.onCreate} **之前**创建的。那批组件里任何一个出问题，
 * 进程就在我们能装崩溃处理器之前死掉 —— 表现为「点开闪一下，毫无提示」。
 * 本工具的界面全在 WebView 里，用不到 AppCompat 的任何东西，直接砍掉。
 *
 * <p><b>★ 为什么 Python 在这里启动而不是 Application 里</b>：
 * Chaquopy 首次启动要解包 ~7MB stdlib，耗时数秒。放在 Application.onCreate
 * 会被国产 ROM 的启动看门狗盯上（超时 SIGKILL，同样没弹窗），而且一旦挂掉
 * Activity 永远起不来，我们的诊断弹窗永远没机会显示。放这里以后，
 * 即使 Python 挂了，界面也已经画出来了，用户至少能看到卡在哪一步。
 *
 * <p>这里只管四件 Android 特有的事：
 * <ol>
 *   <li>把 assets 解包到私有目录（Python 需要真实文件路径）
 *   <li>申请「所有文件访问权限」（读不到 /sdcard 就什么也干不了）
 *   <li>启动 Python 并等它把本地 HTTP 服务拉起来
 *   <li>把每一步都实时画到屏幕上，方便截图反馈
 * </ol>
 */
public class MainActivity extends Activity {

    private static final String TAG = "PkmnTools";

    private WebView webView;
    private TextView statusText;
    private TextView logText;
    private ScrollView logScroll;
    private View bootLayer;
    private View spinner;
    private FrameLayout rootView;
    private boolean pythonReady = false;
    private String lastUrl = null;

    /** 启动遮罩上累积的日志行。 */
    private final StringBuilder bootLog = new StringBuilder();

    // ================================================================
    // 生命周期
    // ================================================================
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        // ★ 兜底必须在 super.onCreate 之前装 —— Activity 构造阶段崩掉也能抓到
        Diagnostics.init(this);
        Diagnostics.installCrashHandler(this);
        Diagnostics.step("onCreate 开始");

        super.onCreate(savedInstanceState);

        try {
            setContentView(R.layout.activity_main);
            rootView = findViewById(R.id.root);
            statusText = findViewById(R.id.status_text);
            logText = findViewById(R.id.log_text);
            logScroll = findViewById(R.id.log_scroll);
            bootLayer = findViewById(R.id.boot_layer);
            spinner = findViewById(R.id.boot_spinner);
            webView = findViewById(R.id.webview);
            Diagnostics.step("布局已加载");
        } catch (Throwable t) {
            // 连布局都起不来，后面的日志界面也用同样的布局，只能干瞪眼。
            // 这次把原因写进 已经写入 crash.log（error() 里做了），下次能看到。
            Diagnostics.error("setContentView", t);
            return;
        }

        // ★ 装实时日志管道，并把在它之前记下的几步回填上来。
        //   这样从 App.onCreate 起的每一步都会出现在屏幕上。
        installLogSink();

        try {
            setupWebView();
            Diagnostics.step("WebView 已配置");
        } catch (Throwable t) {
            Diagnostics.error("setupWebView", t);
            showPlainError("WebView 初始化失败：\n" + Diagnostics.describe(t)
                    + "\n\n这台手机的系统 WebView 可能需要更新"
                    + "（设置 → 应用管理 → 系统组件 → WebView）。");
            return;
        }

        // 曾经崩过吗？先把上次的现场摆出来，用户不用连 adb 也能看到原因
        if (Diagnostics.hasCrash()) {
            showCrashDialog();
            return;
        }

        // 权限先问，但不阻塞启动 —— 用户可能想先看看界面。
        // 弹窗是任务1 的核心：说清为什么需要，而不是直接甩到系统设置页。
        try {
            if (needsStoragePermission()) {
                showPermissionDialog();
            } else {
                startPython();
            }
        } catch (Throwable t) {
            Diagnostics.error("onCreate 后续", t);
            showPlainError(Diagnostics.report(this));
        }
    }

    /**
     * 把 {@link Diagnostics} 的每一步都实时刷到界面左下角的日志区。
     *
     * <p>回调可能来自后台线程（Python 启动线程），所以统一 post 到主线程。
     * 日志文本本身设了 textIsSelectable，用户可以长按复制，也可以直接截图。
     */
    private void installLogSink() {
        Diagnostics.setSink(line -> runOnUiThread(() -> appendLog(line)));
        for (String line : Diagnostics.snapshot()) {
            appendLog(line);
        }
    }

    private void appendLog(String line) {
        if (logText == null) {
            return;
        }
        bootLog.append(line).append('\n');
        // 只留最近 200 行，避免长时间运行把内存堆满
        if (bootLog.length() > 20000) {
            bootLog.delete(0, bootLog.length() - 20000);
        }
        logText.setText(bootLog.toString());
        if (logScroll != null) {
            logScroll.post(() -> logScroll.fullScroll(View.FOCUS_DOWN));
        }
    }

    // ================================================================
    // WebView
    // ================================================================
    private void setupWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setTextZoom(100);          // 不跟随系统字号，避免排版被挤坏

        webView.setBackgroundColor(Color.parseColor("#F5F7FA"));
        webView.setWebViewClient(new WebViewClient() {

            @Override
            public boolean shouldOverrideUrlLoading(WebView view,
                                                    WebResourceRequest req) {
                // 服务只在本机，外链一律交给系统浏览器，绝不放进 WebView
                Uri u = req.getUrl();
                if (u != null && "127.0.0.1".equals(u.getHost())) {
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (Exception ignored) {
                }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req,
                                        WebResourceError err) {
                // 只关心主文档失败；图片/CSS 挂了不该打扰用户
                if (req != null && req.isForMainFrame()) {
                    // WebResourceError 不是 Throwable，包一层再记
                    Diagnostics.error("WebView 加载失败",
                            new IllegalStateException("加载 " + req.getUrl()
                                    + " 失败：" + err.getErrorCode() + " "
                                    + err.getDescription()));
                    statusText.setText("界面加载失败：" + err.getDescription());
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                Diagnostics.step("页面已加载 " + url);
            }

            /**
             * WebView 渲染进程被系统杀掉。
             *
             * <p>国产 ROM 上这个回调不罕见：系统内存紧张时会把 WebView
             * 单独回收，App 还活着但界面变白。不处理的话用户只看到白屏，
             * 连「为什么」都不知道。
             *
             * <p>返回 true = 我自己处理（系统不再杀进程）；返回 false =
             * 系统按默认方式杀掉整个 App。必须重建 WebView 才有界面。
             */
            @Override
            public boolean onRenderProcessGone(WebView view,
                                               RenderProcessGoneDetail detail) {
                Diagnostics.error("WebView 渲染进程被杀", detail.didCrash()
                        ? new IllegalStateException("渲染进程崩溃（didCrash=true）")
                        : new IllegalStateException("渲染进程被系统回收（didCrash=false）"));
                showUi("界面进程被系统回收，正在重启…");
                rebuildWebView();
                return true;
            }
        });
        webView.setWebChromeClient(new WebChromeClient());
    }

    /** 重建 WebView（渲染进程被回收后必须整个换掉）。 */
    private void rebuildWebView() {
        try {
            if (webView != null) {
                webView.destroy();
            }
            FrameLayout parent = rootView;
            webView = new WebView(this);
            webView.setId(R.id.webview);
            webView.setLayoutParams(new FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT));
            parent.addView(webView, 0);
            setupWebView();
            if (lastUrl != null) {
                webView.loadUrl(lastUrl);
                Diagnostics.step("WebView 已重建，重新加载 " + lastUrl);
            } else {
                startPython();
            }
        } catch (Throwable t) {
            Diagnostics.error("rebuildWebView", t);
            showPlainError("界面重建失败：\n" + Diagnostics.describe(t));
        }
    }

    /** 更新冷启动遮罩。msg=null 时整层撤掉，露出下面的 WebView。 */
    private void showUi(final String msg) {
        runOnUiThread(() -> {
            if (bootLayer == null) {
                return;
            }
            if (msg == null) {
                bootLayer.setVisibility(View.GONE);
            } else {
                bootLayer.setVisibility(View.VISIBLE);
                if (statusText != null) {
                    statusText.setText(msg);
                }
            }
        });
    }

    // ================================================================
    // 诊断报告入口（不依赖 WebView / Python）
    // ================================================================

    /** 上次崩过 → 把现场摆出来。 */
    private void showCrashDialog() {
        final String report = Diagnostics.report(this);
        try {
            new AlertDialog.Builder(this)
                    .setTitle("上次启动时崩溃了")
                    .setCancelable(false)
                    .setMessage("下面是崩溃现场，复制给作者就能定位问题：\n\n"
                            + brief(report))
                    .setPositiveButton("复制完整报告", (d, w) -> {
                        copyToClipboard(report);
                        Diagnostics.clearCrash();
                        proceed();
                    })
                    .setNegativeButton("清除并继续", (d, w) -> {
                        Diagnostics.clearCrash();
                        proceed();
                    })
                    .setNeutralButton("重新打开工具", (d, w) -> {
                        Diagnostics.clearCrash();
                        recreate();
                    })
                    .show();
        } catch (Throwable t) {
            // 连弹窗都弹不出来（个别 ROM 会拦）→ 直接把报告铺在屏幕上
            showPlainError(report);
        }
    }

    private void proceed() {
        if (needsStoragePermission()) {
            showPermissionDialog();
        } else {
            startPython();
        }
    }

    /**
     * 任何兜不住的失败都在这里收尾：把报告直接显示出来。
     *
     * <p>用原生 TextView 而不是 WebView —— 后者正是可能出问题的那一环。
     */
    private void showPlainError(String msg) {
        Diagnostics.step("兜底错误界面：" + msg);
        runOnUiThread(() -> {
            if (rootView == null) {
                return;
            }
            try {
                TextView tv = new TextView(this);
                tv.setText(msg);
                tv.setTextSize(11);
                tv.setTextColor(Color.parseColor("#20304A"));
                tv.setBackgroundColor(Color.parseColor("#F5F7FA"));
                tv.setPadding(28, 40, 28, 40);
                tv.setTextIsSelectable(true);      // 方便直接长按复制
                rootView.removeAllViews();
                rootView.addView(tv, new FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT));
            } catch (Throwable t) {
                // 连兜底界面都画不出来，只能对不起了
            }
        });
    }

    private void copyToClipboard(String text) {
        try {
            ClipboardManager cm = (ClipboardManager)
                    getSystemService(Context.CLIPBOARD_SERVICE);
            cm.setPrimaryClip(ClipData.newPlainText("诊断报告", text));
            android.widget.Toast.makeText(this, "已复制，粘贴给作者即可",
                    android.widget.Toast.LENGTH_LONG).show();
        } catch (Throwable t) {
            Diagnostics.error("复制到剪贴板", t);
        }
    }

    /** 报告太长，弹窗里只放前几行 + 提示复制。 */
    private String brief(String report) {
        String[] lines = report.split("\n");
        StringBuilder sb = new StringBuilder();
        int n = Math.min(lines.length, 14);
        for (int i = 0; i < n; i++) {
            sb.append(lines[i]).append('\n');
        }
        if (lines.length > n) {
            sb.append("\n… 还有 ").append(lines.length - n).append(" 行，点「复制完整报告」拿到全部。");
        }
        return sb.toString();
    }

    // ================================================================
    // ① 权限
    // ================================================================

    /** 是否还缺权限。低于 Android 11 一律返回 false（那时用普通读写权限）。 */
    private boolean needsStoragePermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return false;
        }
        try {
            return !Environment.isExternalStorageManager();
        } catch (Throwable t) {
            return false;
        }
    }

    /**
     * 任务1：没有「所有文件访问权限」时弹窗，**说清为什么需要**。
     *
     * <p>为什么不直接跳系统设置：用户看到的是一个陌生的开关，不知道开它干嘛，
     * 于是要么拒绝要么乱开。弹窗把「读不到游戏目录就什么也做不了」
     * 这件事讲明白，再让他自己决定。
     */
    private void showPermissionDialog() {
        if (isFinishing() || isDestroyed()) {
            return;
        }
        Diagnostics.step("弹出权限说明");
        try {
            new AlertDialog.Builder(this)
                    .setTitle("需要「所有文件访问权限」")
                    .setCancelable(false)
                    .setMessage(
                            "这个工具要直接读写你手机里的游戏文件：\n\n"
                            + "· 读取 Data/Scripts、Game.rxdata 等引擎脚本\n"
                            + "· 读取与备份游戏存档\n"
                            + "· 开启 DEBUG 时修改脚本、写入备份\n\n"
                            + "这些文件通常在 /sdcard/Android/data/... 或游戏自己的"
                            + "目录里，普通权限读不到，所以系统才提供了"
                            + "「所有文件访问权限」这一个开关。\n\n"
                            + "★ 本工具**完全离线**，不联网、不上传任何文件。\n"
                            + "你可以随时在系统设置里关掉这个权限。")
                    .setPositiveButton("去授权", (d, w) -> openAllFilesAccessSettings())
                    .setNegativeButton("暂不授权", (d, w) -> {
                        // 不强求：先进去，界面里也会提示哪些功能用不了
                        Diagnostics.step("用户选择暂不授权");
                        showUi("未授权：无法读取游戏目录，可在「关于」页查看说明");
                        startPython();
                    })
                    .show();
        } catch (Throwable t) {
            Diagnostics.error("权限弹窗", t);
            // 弹不出来就直接进主流程，别卡死在这里
            startPython();
        }
    }

    /**
     * 从系统设置页返回时重新检查。
     *
     * <p>★ 挂在 {@code onResume} 上而不是 {@code postDelayed} ——
     * 用户在设置页可能停留任意久，延时回调早就跑完了，回来还是没权限，
     * 于是卡在「Python 没启动、界面永远转圈」。
     */
    private boolean awaitingPermission = false;

    private void openAllFilesAccessSettings() {
        awaitingPermission = true;
        try {
            Intent it = new Intent(
                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:" + getPackageName()));
            startActivity(it);
        } catch (Exception e) {
            // 个别厂商 ROM 没有这个页面，退到全局「特殊权限」列表
            try {
                startActivity(new Intent(
                        Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION));
            } catch (Exception e2) {
                try {
                    startActivity(new Intent(Settings.ACTION_SETTINGS));
                } catch (Exception e3) {
                    Diagnostics.error("打开系统设置", e3);
                    showPlainError("无法打开系统设置页。\n请手动到："
                            + "设置 → 应用管理 → 宝可梦同人工具 → 权限"
                            + " → 打开「所有文件访问权限」。");
                }
            }
        }
    }

    // ================================================================
    // ② 资源解包：assets → 私有目录
    // ================================================================
    private File copyAssets(String assetFolder, String dstName) {
        File out = new File(getFilesDir(), dstName);
        try {
            copyAssetFolder(assetFolder, out);
        } catch (IOException e) {
            Diagnostics.error("解包 " + assetFolder, e);
            throw new RuntimeException("解包资源失败：" + assetFolder, e);
        }
        return out;
    }

    private void copyAssetFolder(String path, File outDir) throws IOException {
        String[] items = getAssets().list(path);
        if (items == null) {
            throw new IOException("assets 里找不到目录：" + path);
        }
        if (!outDir.exists() && !outDir.mkdirs()) {
            throw new IOException("无法创建目录：" + outDir);
        }
        for (String item : items) {
            File sub = new File(outDir, item);
            String[] subItems = getAssets().list(path + "/" + item);
            if (subItems != null && subItems.length > 0) {
                copyAssetFolder(path + "/" + item, sub);
            } else {
                copyAssetFile(path + "/" + item, new File(outDir, item));
            }
        }
    }

    private void copyAssetFile(String assetPath, File dst) throws IOException {
        try (InputStream in = getAssets().open(assetPath);
             OutputStream os = new FileOutputStream(dst)) {
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = in.read(buf)) > 0) {
                os.write(buf, 0, n);
            }
        }
    }

    // ================================================================
    // ③ 起 Python
    // ================================================================
    private void startPython() {
        if (pythonReady || isFinishing() || isDestroyed()) {
            return;
        }
        Diagnostics.step("启动 Python 线程");
        // 解包 CPython 与资源要几秒（首次更久），必须放后台线程
        new Thread(this::bootstrap, "python-boot").start();
    }

    private void bootstrap() {
        try {
            showUi("正在准备…");
            Diagnostics.step("解包资源");

            File homeDir = new File(getFilesDir(), "home/data");
            if (!homeDir.exists() && !homeDir.mkdirs()) {
                throw new IOException("无法创建工作目录：" + homeDir);
            }
            File webDir = copyAssets("web", "web");
            File dataDir = copyAssets("core_data", "core_data");
            Diagnostics.step("资源解包完成");

            showUi("正在启动 Python…");

            // ★ Chaquopy 的首次启动就在这里：解包 ~7MB stdlib + 原生模块。
            //   放在后台线程而不是 Application.onCreate，见类注释。
            if (!Python.isStarted()) {
                Diagnostics.step("Python.start() 开始（首次较慢）");
                Python.start(new AndroidPlatform(this));
            }
            Diagnostics.step("Python 已就绪");

            PyObject mod = Python.getInstance().getModule("mobile_main");
            Diagnostics.step("已取得 mobile_main 模块");

            PyObject portObj = mod.callAttr("start",
                    homeDir.getAbsolutePath(),
                    webDir.getAbsolutePath(),
                    dataDir.getAbsolutePath());

            int port = portObj.toInt();
            final String url = "http://127.0.0.1:" + port + "/";
            lastUrl = url;
            Log.i(TAG, "服务已启动 " + url);
            Diagnostics.step("服务已启动 " + url);

            pythonReady = true;
            Diagnostics.endStartup();      // 走到这一步就算启动成功，清掉标记
            showUi(null);
            runOnUiThread(() -> webView.loadUrl(url));

        } catch (Throwable e) {
            // ★ Throwable 而不是 Exception：Python 层的失败常常是
            //   UnsatisfiedLinkError / NoClassDefFoundError 这些 Error，
            //   用 Exception 接不住，会直接崩到全局处理器里。
            Diagnostics.error("启动失败", e);
            final String report = Diagnostics.report(this);
            final String summary = Diagnostics.describe(e);
            runOnUiThread(() -> {
                // 先把兜底界面画出来，再弹窗 —— 万一弹窗也被 ROM 拦了，
                // 屏幕上至少还留着一份可读的报告，用户能截图发出来。
                showPlainError(report);
                showFatal(summary, report);
            });
        }
    }

    private void showFatal(String summary, String report) {
        showUi(null);
        try {
            new AlertDialog.Builder(this)
                    .setTitle("无法启动")
                    .setCancelable(false)
                    .setMessage(summary + "\n\n"
                            + "把下面的诊断报告发给作者，就能定位问题：\n\n"
                            + brief(report))
                    .setPositiveButton("复制报告", (d, w) -> copyToClipboard(report))
                    .setNegativeButton("重试", (d, w) -> {
                        pythonReady = false;
                        showUi("正在准备…");
                        startPython();
                    })
                    .setNeutralButton("关闭", (d, w) -> showPlainError(report))
                    .show();
        } catch (Throwable t) {
            Diagnostics.error("失败弹窗", t);
        }
    }

    // ================================================================
    // 返回键 / 生命周期
    // ================================================================
    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.onResume();
        }
        // ★ 从系统设置页回来了：如果之前在等授权，现在给上
        if (awaitingPermission) {
            awaitingPermission = false;
            if (!needsStoragePermission()) {
                Diagnostics.step("权限已授予");
                showUi(null);
                startPython();
            } else if (!pythonReady) {
                Diagnostics.step("权限仍未授予，但先进去看看界面");
                showUi("未授权：无法读取游戏目录");
                startPython();
            }
        }
    }

    @Override
    protected void onPause() {
        if (webView != null) {
            webView.onPause();
        }
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
