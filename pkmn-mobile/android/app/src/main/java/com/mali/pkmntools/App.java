package com.mali.pkmntools;

import android.app.Application;

/**
 * 自定义 Application —— **整个 App 里最早执行的我们自己的代码**。
 *
 * <p>存在的唯一目的：抢在一切之前把崩溃处理器装上。
 *
 * <p>为什么需要它：用户反馈「点开即闪退，根本没有弹窗」。那种崩溃发生在
 * {@code Activity} 之前（进程刚起来、或加载原生库时就炸），装在
 * {@code Activity.onCreate} 里的兜底**根本来不及生效**。Application.onCreate
 * 是目前能拿到的、最早且保证被调用的 Java 回调点。
 *
 * <hr>
 *
 * <p><b>★ 这里刻意什么都不做，这是有意为之。</b>
 *
 * <p>之前的版本在这里调用了 {@code Python.start()} 想「预热」CPython。
 * 这是错的，两个原因：
 *
 * <ol>
 *   <li><b>会被看门狗杀掉。</b>首次启动时 Chaquopy 要把 ~7MB 的 stdlib
 *       与内置模块从 assets 解包到私有目录，在手机上要好几秒。
 *       部分国产 ROM 对「应用启动耗时」有硬性看门狗，超时就 SIGKILL。
 *       被 SIGKILL 的进程不会弹任何窗 —— 正是「闪一下就没」。</li>
 *   <li><b>会吃掉诊断机会。</b>Application.onCreate 里挂掉，Activity 就永远
 *       起不来；而我们的「上次崩溃了」弹窗是在 Activity 里显示的。
 *       于是每台出问题的手机都只会说「打不开」，永远拿不到现场。</li>
 * </ol>
 *
 * <p>现在 Chaquopy 的启动挪到了 {@code MainActivity} 的后台线程
 * （见 {@code MainActivity#bootstrap}）。这样一来：
 * <ul>
 *   <li>{@code onCreate} 只做两次文件读写，耗时以毫秒计，看门狗追不上；</li>
 *   <li>就算后面 Python 真的起不来，Activity 已经画出来了，用户能直接在
 *       屏幕上看到卡在哪一步；进程即使被杀，下次进来也能弹出崩溃现场。</li>
 * </ul>
 */
public class App extends Application {

    @Override
    public void onCreate() {
        super.onCreate();

        // ★ 顺序很重要：先装崩溃处理器，再做任何可能失败的事。
        //   下面两步都只碰私有目录里的小文件，不会有明显耗时。
        Diagnostics.init(this);
        Diagnostics.installCrashHandler(this);

        // ★「上次没走到成功启动就算崩了」——
        //   写一个「启动进行中」标记，每次成功启动后清掉。
        //   下次进来发现标记还在，说明上次是在进程刚起来时就挂的
        //   （原生库 dlopen 失败最典型），连 Activity 都进不去，
        //   这种情况下只能靠这个标记把现场留下来。
        //
        // ★ 注意：这个标记写在**我们自己的代码最早的位置**。
        //   如果连这里都没走到，说明崩在系统初始化阶段
        //   （清单解析 / ContentProvider / Application 构造），
        //   那就不是我们的代码能救的了 —— 也正是本项目要把清单
        //   和依赖都削到最简的原因。
        boolean dirty = Diagnostics.beginStartup();
        Diagnostics.step(dirty
                ? "Application.onCreate（检测到上次启动未完成）"
                : "Application.onCreate");

        // ★ 就此打住。不要在这里启动 Python、不要拷贝 assets、
        //   不要做任何网络或磁盘的重活。原因见类注释。
    }
}
