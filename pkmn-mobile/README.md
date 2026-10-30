# 宝可梦同人工具 · 手机版

电脑版 [`E:\pkmn_translator`](file:///E:/pkmn_translator) 的安卓移植。
**安卓 App 壳 + WebView + 内置 CPython**，跑的核心代码与电脑版逐字节相同。

---

## 最要紧的一件事

> `core/` 目录里的文件是**从电脑版原样拷过来的，不要手改**。
>
> 需要任何调整，请改 `shim/` 或 `server/`。

这条一旦破坏，两端就又变成两份代码，得人工同步了。

---

## 更新流程：全部手动

**本工程没有任何自动同步。** 想更新就手动拷、重跑一次打包脚本：

```bash
# 1. 从电脑版把改过的文件拷进 core/（例如改了 save_tools.py）
cp E:/pkmn_translator/save_tools.py core/
# 引擎基准变了就顺手更新：
cp E:/pkmn_translator/scripts/essentials_base/*.json core_data/essentials_base/

# 2. 把源码与资源复制进 APK 的打包目录
python tools/stage_assets.py

# 3. 自检（确认改动没把手机版带崩）
python tools/verify_core.py

# 3.5 ★ 在本地按 Chaquopy 的方式把服务真起一遍（改过 core/shim/server/mobile_main 必跑）
python tools/test_mobile_boot.py
python tools/test_debug_modes.py      # 七种开启方式逐个端到端

# 4. 端到端验证（造假游戏目录，真的写进去再读回来）
python tools/test_debug_e2e.py
python tools/test_overwrite_font.py

# 5. 打包
cd android && gradlew assembleDebug
```

第 2 步是**手动**的，不是 Gradle 自动钩子。这样你明确知道打进 APK 的是哪一份，
也不会被构建过程覆盖掉临时改动。

### 为什么第 3.5 步不能省

`tools/test_mobile_boot.py` 复刻的是**安卓上的导入环境** ——
Chaquopy 只把 `app/src/main/python/` 平铺到 `sys.path`，
什么都不额外加。而电脑版入口 `run_server.py` 偷偷多做了
`sys.path.insert(0, ROOT/"server")`，正是这个差异让
「`server/app.py` 里的平铺导入在手机上找不到兄弟模块」这个问题
**在本地完全测不出来**（v1.3 就是这么翻车的）。

---

## 手机打不开怎么定位

这是最难的一类问题：国产 ROM（OriginOS / HyperOS / ColorOS…）上「打不开」
可能是十几种原因，而且**光看崩溃日志是看不出来的**。所以这个 App 带了
一个诊断层。

### App 会自己告诉你哪里坏了

打开后如果起不来，会弹出诊断窗口，点「复制完整报告」把内容发给我即可。
报告里有：

- Android 版本、机型、ABI
- **内存页大小** ← 判断是不是 16KB 页设备的关键
- 系统 WebView 的版本（找不到 WebView 组件会单独标出来）
- 启动过程的逐步打点（卡在解包 / Python 启动 / 加载页面 一眼可见）
- 上次崩溃的完整堆栈

同样的按钮在「关于 → 问题反馈 → 复制诊断报告」里，任何时候都能点。

### 三个高频原因

| 现象 | 大概率原因 | 已做的处理 |
|---|---|---|
| 点开就闪退 | 原生库页大小与设备不匹配 | Python 3.13 + Chaquopy 17 + 16KB 对齐，`check_16kb.py` 可验证 |
| 白屏 / 闪一下就没 | WebView 渲染进程被 ROM 回收 | 加了 `onRenderProcessGone`，自动重建 WebView |
| 一直转圈 | ROM 拦了 localhost 明文流量 | `android:usesCleartextTraffic="true"`（只连 127.0.0.1，不出网） |

### ★ 「点开即闪退、连弹窗都没有」——已定位的三个真凶（v1.3）

三个都是**崩在系统初始化阶段**的坑，共同特点是崩在我们能记日志之前，
所以用户在手机上什么提示都看不到。已逐一修掉，并由
`tools/check_startup_risks.py` 静态把关（防止改回去）：

| # | 根因 | 为什么致命 | 处理 |
|---|---|---|---|
| 1 | `drawable/splash_window.xml` 里写了 `<bitmap android:src="@mipmap/ic_launcher">` | `@mipmap/ic_launcher` 在 **Android 8.0+** 解析到的是 `mipmap-anydpi-v26` 里的 `<adaptive-icon>` **XML**；`<bitmap>` 只吃真图片，`BitmapFactory` 返回 null → 抛 `XmlPullParserException: <bitmap> requires a valid 'src' attribute`。它挂在 Activity 主题的 `windowBackground` 上，而窗口背景是框架在 `onCreate` **之前**就加载的 | 换成独立 PNG `@drawable/splash_logo`（`drawable-xxhdpi/`，名字在 anydpi 里没有同名覆盖，所有版本都稳定解析到图片） |
| 2 | 依赖里的 androidx 把 `androidx.startup.InitializationProvider` 塞进清单 | 它是 **ContentProvider**，由系统在 `Application.onCreate` **之前**创建，里面挂着 EmojiCompat / ProcessLifecycle / ProfileInstaller 三个 Initializer。任何一个抛异常，进程就在我们装崩溃处理器之前死掉 | `dependencies` 清空，改用平台 `android.app.Activity` + 平台主题；合并清单里现在 **0 个 ContentProvider** |
| 3 | `App.onCreate()` 里调 `Python.start()` | Chaquopy 首启要解包 ~7MB stdlib，耗时数秒，会被国产 ROM 的启动看门狗 SIGKILL；且一旦挂掉 Activity 永远起不来，「上次崩溃了」弹窗永远没机会显示 | `App` 里只做毫秒级的事；Python 启动挪到 `MainActivity` 的后台线程，界面先画出来 |

另外顺手做的：清单里不再写 `networkSecurityConfig`（该配置同样由系统在应用代码之前解析）。

**现在启动遮罩会实时打印每一步打点**（原生 TextView，不依赖 WebView / Python）。
真机再出问题时，直接截那一屏发给作者即可。

### ★ v1.4：界面起来了，但 Python 报 `No module named 'app'`

v1.3 修完上面三条之后，App 终于能打开、能走到 Python 启动那一步了，
但卡在这里：

```
[17937ms] 已取得 mobile_main 模块
✘ [启动失败] PyException: ModuleNotFoundError: No module named 'app'
```

**真实原因跟 `app` 毫无关系**，而是被错误信息带偏的典型：

- `server/app.py` 用的是**平铺导入**：`import jsonutil` / `import tasks` /
  `import api_debug` …，所以 `server/` 目录**自己必须在 `sys.path` 上**。
- 电脑版 `run_server.py` 一直是这么做的：`sys.path.insert(0, ROOT/"server")`。
- 安卓入口 `mobile_main.py` 却漏了这一步，而它写的又是

  ```python
  try:
      from server import app as APP
  except ImportError:
      import app as APP          # ← 报出来的就是这个
  ```

  `from server import app` 能找到 `app.py`，但一执行就炸在 `import jsonutil`；
  这个 ImportError 被兜住，外面只看到 `No module named 'app'`。

**修法**：`mobile_main._prepare()` 里补上 `_ensure_server_dir(root)`，
把 `<root>/server` 插到 `sys.path` 中 `root` 之后（查找顺序变成
`core → shim → vendor → root → server`，不改变原有优先级）；
并把那个 `try/except ImportError` 换成直接 `import app`，**让真实堆栈原样抛出**。

**配套防回归**：新增 `tools/test_mobile_boot.py`，在本地复刻 Chaquopy 的
`sys.path` 环境并真的把服务起起来。这个脚本能在几秒内拦住上面这类
「只在安卓上才犯」的导入错误。

### ★ v1.5：`No module named 'app'` 还在 —— 因为 v1.4 的修复被一道门槛吃掉了

v1.4 补了 `_ensure_server_dir()`，但里面写了

```python
if not os.path.isdir(server_dir):   # ← 这一行把路径悄悄吃掉了
    return
```

**安卓上 `root` 不是真实目录**：Chaquopy 把 `app.imy` 当目录用，
`os.path.isdir("<...>/app.imy/server")` 永远是 `False`。
于是路径根本没加上，报错和没改之前一模一样。

查 Chaquopy 源码（`java/android/importer.py` 的 `AssetFinder`）确认了两件事：

| 事实 | 依据 |
|---|---|
| **zip 内的子目录可以用作 `sys.path` 条目** | `AssetFinder.__init__` 里有专门分支处理 `dirname(path) != ASSET_PREFIX`：取父 finder 的 `extract_root`，把相对部分当 `prefix` 去 zip 里找。`bootstrap` 给 core/shim/vendor 加路径用的就是它 |
| **带 `__init__` 的目录走「常规包」分支** | 与 Chaquopy 自己在用的 `java/`、`java/_vendor/elftools/` 完全一致，证据最扎实 |

于是 v1.5 改成**两条独立通路**，任意一条坏掉都能起来：

| 通路 | 做法 | 依赖 |
|---|---|---|
| ① 包形式（首选） | 新增 `server/__init__.py`；`app.py` 与 5 个 `api_*.py` 改成 `if __package__: from . import …` | 只要 Chaquopy 的常规包支持，**完全不碰 `sys.path`** |
| ② 平铺形式（退路） | `_ensure_server_dir()` 去掉 `isdir` 门槛，无条件把 `<root>/server` 挂上 | Chaquopy 的 zip 子目录条目 |

同时把 `run_server.py`、`tools/smoke_api.py` 也统一成**包形式** ——
以前电脑走平铺、手机走另一套，正是这种分歧让问题在本地测不出来。

**`_import_app()` 的降级也修对了**：只在 `e.name` 是 `server` / `server.app`
时才降级，其它错误原样抛出。原来的 `except ImportError` 会把
「app.py 内部缺 `jsonutil`」偷换成「找不到 app」。

### ★ Python 日志现在会打到手机屏幕上

`mobile_main._log()` 通过 Chaquopy 调 `Diagnostics.step()`，
所以启动遮罩的日志区会多出 `[Python] …` 行。启动时还会**自检三条路径**：

```
[Python] 源码根 = asset.app.zip
[Python] sys.path 前 5 项 = [...]
[Python] 导入 config ✔          ← shim/
[Python] 导入 save_tools ✔      ← core/
[Python] 导入 rubymarshal ✔     ← vendor/
[Python] app 模块（包形式）已导入：…
[Python] 服务已监听 127.0.0.1:xxxxx
```

以后 Python 侧再出问题，截图就能定位，不用连 adb、也不用再猜一轮。

---

## v1.6：四个实际使用中反馈的问题

### ① 浏览游戏根目录 → 「没有读取权限」

**根因不在权限上，在路径上。** `os.path.normpath("")` 返回的是 **`"."`**，
所以「没传目录」到了后端会变成一个合法的相对路径，`if not d` 判断不出来 →
安卓上去列**进程的当前目录**，而那是 `/`，SELinux 不许 `listdir` →
`PermissionError` → 前端只弹一句「没有读取权限」。

手机也没有「我的电脑」这一层，用户看到这句话完全不知道该往哪走。

修法（`server/api_fs.py`）：
- 把 `"."` 也当成「没指定目录」（这一行是真正的修复，别删）；
- 安卓上空路径**不再列 `/`**，改为返回一组确定可用的起点：
  内部存储 / `Android/data` / `Android/media` / 下载 / 文档 / 外置 SD 卡；
- 报错时给可读的说明，并且**铺在列表里而不是 toast** ——
  toast 一闪就没了，安卓上的报错都是好几行；
- 额外标记「当前目录看着就是游戏根目录」（有 `Data/` 且有 `.exe`），
  以及记住上次选的游戏目录（手机上进 `Android/data/xxx` 翻一遍很痛苦）。

### ② 作者信息

封面页与关于页都改成：作者「玛俐大小姐想让我告白」、
GitHub `nevermore-glimpse/pkmn_translator`、Bilibili `space.bilibili.com/3546602748775226`，
链接可点，点了交给系统浏览器打开。

### ③ 补齐电脑版的前 7 种开启 DEBUG 方式

电脑版 `gui.py` 的下拉框有 8 项，其中「⑧ 调试启动器」要生成 Windows exe，
手机做不到；其余 ①–⑦ 现在**全部可用**：

| 方式 | 落点 | 调的 core 函数 |
|---|---|---|
| ① 通用 | 写 Main 的 `pbCallTitle` 第一行 | `debug_tool.enable_debug(write_debug=True)` |
| ② 删条件 | `Game_Player` / `Scene_Map` / 队伍 / 背包 | `engine_tools.patch_remove_debug_conditions` |
| ③ F6 键（提示） | `Scene_Map` | `engine_tools.patch_special_key` |
| ④ F6 键（菜单） | `Scene_Map` | 同上，`mode="special_menu"` |
| ⑤ 除虫喷雾（设 $DEBUG） | `Item_Effects` / `PItem_ItemEffects` | `engine_tools.patch_repel` |
| ⑥ 除虫喷雾（开菜单） | 同上 | `patch_repel(mode="repel_menu")` |
| ⑦ 改名调试函数（按 T） | 全库调用点 | `engine_tools.patch_rewrite_debug_func` |

★ **只有方式① 会写 `$DEBUG=true`**，②–⑦ 一律不写 ——
方式⑦ 的整套设计前提就是「全程不设 $DEBUG」，反调试里有 `exit if $DEBUG`，
一设就被踢出游戏。这条规则原来只在电脑版里，现在两端一致，并由
`tools/test_debug_modes.py` 逐方式断言。UI 上还保留了电脑版的勾选项
（引擎被改过也继续写入；「自动关闭全量编译」已随电脑版一同删除，
现在不再给 Compiler 装编译闸门）。

### ④ 关于页「基准数据：缺失」

**数据一直都在打包里，是判断写错了。** `bootstrap.py` 把 `DATA_DIR` 写死成
`<源码根>/core_data`，而安卓上源码在 `app.imy` 里、`core_data` 是 assets 解出来的
（路径由 `PKMN_DATA_DIR` 注入）→ `os.path.isdir` 永远 False。

改成优先读 `PKMN_DATA_DIR`；`status()` 还多返回了基准版本清单，
关于页现在会列出实际内置的版本（v16 … v21.1），一眼就能确认工具能认出哪些版本。



## v1.7：存档编辑对齐电脑版

电脑版「存档编辑（菜单 6）」的功能现在手机端也齐了，另加手输与自动识别：

| 页面 | 能力 |
|---|---|
| **主角** | 名字 / 金钱 / 训练家ID / 语种 / 训练家类型 / 服装编号 / 已有图鉴；徽章逐个点；图鉴「已见 / 已捕获」全开、清空、**形态图鉴全开** |
| **同行** | 点一只进编辑 —— 昵称 / 种族 / 形态 / 等级 / 经验 / 性格 / 特性 / 当前HP / 状态 / IV / EV / 4 招式+PP / 携带道具 / 捕获用球 / 亲密度 / 孵蛋步数 / 异色 / 勋章 / 初训家 / 训练家ID / 个体ID，改完自动重算能力值 |
| **背包** | 按口袋列出道具，改数量、删除、添加，「全部补满 999」，设置登记道具 |
| **PC 箱子** | 看每个箱子；箱内宝可梦可编辑、**移入队伍 / 复制一只 / 清空该格**；可改箱名 |
| **开关变量** | 改 `$game_switches` / `$game_variables` |

- **种族 / 道具 / 招式可手输**：下拉里找不到时，点搜索框敲 **英文内部名**
  （`PIKACHU` / `POKEBALL`）或**编号**即可，认不出会提示该用什么格式。
- **改种族同步昵称**：和电脑版一致，改完种族昵称自动跟成新种族名，
  不再出现「名字写电灯灯、图标是果然翁」这种对不上的情况。
- **字体**：沿用「植入中文文本处理插件 + 换内置萝莉体」那一套，可还原。

### 选游戏主程序（不用再找文件夹）

- 手机版不再让你去选「游戏根目录」，而是**直接选 `Game.exe`** ——
  根目录由 `game_scripts.exe_root()` + `verify_game()` 自动推出来
  （`/api/fs/check_game?exe=`），存档页的数据源目录也跟着自动带出来。
- 浏览时只列 `.exe`（🎮 图标），其它文件不显示，省得在手机的目录海洋里翻。
- 上次选的主程序会记住（`localStorage` 的 `pkmn.gameExe`）。

### 基准覆盖：版本可手动选，认不出才用指纹

- 版本改成**下拉框**：`自动（自报版本 → 指纹识别）` + 具体版本（v16…v21.1）。
- 「自动」的判定顺序（后端 `api_overwrite.resolve_version`）：
  ① 读游戏自报的 `Essentials::VERSION` → 映射到最接近的基准；
  ② **读不到版本号**（老游戏 / 魔改版常把版本号删了）→ 按**脚本指纹**
     与每份基准比对，挑重合度最高的（`best_baseline`，≥50%）；
  ③ 都不行 → 提示手动选一个。
- 页面会直接显示「当前会使用的基准」和判定来源（自报 / 指纹 + 重合度）。

### 反调试不再自动注释

- 点「开启 DEBUG」时先扫描反调试代码（`/api/debug/antidebug`），
  **发现就把代码摆出来弹窗**，由你选：
  - **自动注释** —— 把那些行加 `# [pkmn-debug] ` 前缀（原样保留，可还原）；
  - **跳过（不注释）** —— 一处都不动；
  - **取消** —— 整个「开启 DEBUG」中止。
- 注意：**不选就不注释**（后端默认 `skip`）—— 以前是发现即自动注释，
  现在改成必须先问你。

> 手机端 `core/` 仍是**从电脑版原样拷来**的（本轮同步了 `save_tools.py` /
> `engine_tools.py` / `plugin_tools.py` / `launcher.py`），
> `server/api_save.py` 与 `web/` 才是手机专属。改完记得
> `python tools/stage_assets.py`。

---

### 自己查 logcat（如果连了 adb）

```bash
adb logcat -s PkmnTools:V AndroidRuntime:E Chaquopy:V
```

### 遇到「打开即闪退，连弹窗都没有」

这是最难反馈的一种，因为崩在进程初始化阶段，Java 层还没来得及记录。
判断依据与对策：

| 判断 | 说明 |
|---|---|
| App 根本进不去（图标点开就消失） | 崩在原生库加载或系统初始化阶段 —— 查 `extractNativeLibs`，并跑一次 `check_startup_risks.py` |
| 有过 1~2 秒界面再消失 | 崩在 Java 代码里 —— 诊断日志应该已写盘，下次启动会弹出来 |

**下次启动时 App 会自动把上次的现场弹出来**，点「复制完整报告」发我即可。
若连这个都没出现，说明崩在 `Application.onCreate` 之前，
那时只剩 `startup.dirty` 标记能证明「上次没启动完」。

**怎么确认装的是新版**：诊断报告第一行是「构建标识」，
例如 `2026-10-13 修复版：去 androidx 开机组件 / …`。看不到这一行就是装的旧包。

### 排查同类问题的标准流程

以后遇到国产 ROM 兼容问题，别猜 —— **要一个同机型能跑的同类 APK 做对照**：

```bash
aapt2 dump badging 参考.apk          # minSdk / targetSdk / compileSdk / 权限
aapt2 dump xmltree --file AndroidManifest.xml 参考.apk   # application 属性全集
unzip -l 参考.apk | grep '\.so$'      # 原生库在哪、数量、架构
strings classes*.dex | grep WebView   # 技术栈是否相同
```

优先对齐 `extractNativeLibs`、`targetSdk`、`lib/` 里的 `.so` 数量这���项。

### 不装 App 也能自查

```bash
python tools/test_mobile_boot.py      # 本地按 Chaquopy 的方式把服务真起一遍
python tools/test_debug_modes.py      # 七种开启方式逐个端到端
python tools/check_16kb.py            # .so 的 ELF 段对齐
python tools/check_zip_align.py       # .so 在 APK 里的偏移对齐
python tools/check_startup_risks.py   # 「点开就闪退、无弹窗」那几类启动期坑
```

全部通过 = 代码与 APK 本身没问题，问题在设备侧（ROM 策略 / WebView 版本 /
内存不足），这时诊断报告才是关键。

---

## 功能

| 页面 | 做什么 |
|---|---|
| **封面页** | 进入后先停 3 秒：顶部免责两行、中间封面图、底部作者信息（可点） |
| **DEBUG** | 前 7 种开启方式（①通用 ②删条件 ③④F6 键 ⑤⑥除虫喷雾 ⑦改名调试函数）+ 关/还原 + 实时日志（SSE） |
| **基准覆盖** | 用官方同版本脚本盖掉被改坏的 **debug 函数** 与 **地图更新（Scene_Map）**，可还原 |
| **字体** | 植入「中文文本处理」插件 + 换成内置**萝莉体**，可还原 |
| **存档** | 主角 / 同行 / 背包 / 箱子 / 开关变量，写回存档 |
| **关于** | 环境体检、内置基准版本清单、复制诊断报告、作者与链接 |

---

## 手机版本兼容

| 项 | 值 | 为什么 |
|---|---|---|
| minSdk | 24 | Chaquopy 17 的下限；覆盖 97%+ 在用设备 |
| compileSdk | 36 | 只是编译期用，能用最新 API |
| **targetSdk** | **29** | ★ 见下方「为什么是 29」，这是能不能在国产 ROM 上打开的关键 |
| AGP | 8.13 | 8.5.1 是 16KB 页面对齐的第一个支持版本 |
| Chaquopy | 17.0 | **唯一**真正支持 16KB 页的版本 |
| Python | 3.13 | 3.12 及更早的 Android wheels 是 4KB 对齐的 |
| 架构 | arm64-v8a（+ 可选 x86_64） | **不带 32 位**，见下 |

### ★ 为什么 targetSdk 是 29（iQOO Neo7 SE 打不开的真凶）

用户提供了一个在**同一台手机**上能正常打开的 APK
（口袋改版工具盒_2.1.0.0.clone.apk），用 `aapt2` 解出来：

| | 参考 APK（能跑） | 本工程 v1.1（打不开） | 本工程 v1.2 |
|---|---|---|---|
| minSdk | 21 | 24 | 24 |
| **targetSdk** | **29** | **36** | **29** |
| compileSdk | 32 | 36 | 36 |
| `lib/` 里的 .so | **0 个**（全在 assets/） | 8 个 | 8 个 |
| `lib/` 体积 | 0 | ~12 MB | ~12 MB |

`targetSdk 36` 会触发 Android 15/16 上的一批新行为，其中至少有一项
让 App 在这台机器上直接起不来。国产 ROM 对这些行为的实现各不相同，
逐条排查不现实 —— 与其赌 ROM 的实现，不如退到**已知可用的 29**。

代价（都已处理）：
- edge-to-edge 不再强制，但我们自己是开着的，Insets 代码保留即可
- 分页存储不再强制，反而更简单
- 通知权限、照片选择器等一律不触发

本工具完全离线、不联外网、不做后台调度，这些新行为对我们没有价值。

> **参考 APK 还揭示了一件事**：它的 `.so` 全在 `assets/` 而不在 `lib/`，
> 所以完全绕开了「原生库页对齐」这个坑。我们的架构（C++ 运行时必须由
> 系统加载）绕不开，所以 16KB 对齐那条修复依然要保留 —— 两处差异要分开看。

### ★ Android 15/16 打不开的原因

用户提供了三个在**同一台手机**（iQOO Neo7 SE / OriginOS 6）上能正常打开的
APK 做对照，aapt2 解出来的结果如下：

| APK | targetSdk | `extractNativeLibs` | `lib/` 里的 .so |
|---|---|---|---|
| 口袋改版工具盒 2.1.0 | 29 | true | 0 个（全在 assets/） |
| MT管理器 2.26.9 | 30 | true | 40 个 |
| DeepSeek 2.4.5 | **36** | **true** | 11 个 |
| **本工程 v1.0（打不开）** | 36 | **false** | 8 个 |
| 本工程 v1.2 | 29 | true | 8 个 |

**真凶是 `extractNativeLibs=false`。**

`false` 时系统把 APK 里的 `.so` 直接 mmap 进进程，要求文件在包内偏移与
ELF 段都严格 16KB 对齐。国产 ROM 的安装器 / 应用优化流程会重写 APK，
**把对齐破坏掉** → `dlopen` 失败 → 秒退。因为崩在进程初始化阶段，
Java 层的崩溃处理器还没装载，所以**连弹窗都没有**。

`true` 时安装时把 `.so` 解到 `/data/data/<包名>/lib/`，由文件系统保证
对齐，绕开整条风险链。三个参照 APK 全都是 `true`。

改动后 APK 从 32MB 降到 **24.7MB**（`.so` 现在可以压缩了）。

配套还做了两件事：

1. **加 `App`（Application 子类）** —— 全 App 最早的 Java 回调点，
   在这里装崩溃处理器。Activity 里的兜底对「进程刚起来就挂」的情况来不及生效。
2. **加「启动未完成」标记** —— 每次启动写一个 dirty 标记，成功后才清。
   下次进来发现标记还在，就知道上次是崩在 Activity 之前，
   现场会留在 `crash.log` 里等你来看。

> 顺带修正：上一版把 targetSdk 降到 29 是**误判**。DeepSeek 用 36 一样能跑，
> 说明 targetSdk 不是原因。不过 29 本身也没坏处（我们完全离线、不联外网，
> 不依赖那些新行为），留着不算错，只是不该把它当成「修复」。

**自查**：`python tools/check_16kb.py` 与 `python tools/check_zip_align.py`

### 为什么放弃 32 位设备

Chaquopy 17 的 Python 3.13 **没有 armeabi-v7a（32 位）版本**，
写进 `abiFilters` 会直接构建失败：

```
Python 3.13 is not available for the ABI 'armeabi-v7a'.
Supported ABIs are [arm64-v8a, x86_64].
```

而 16KB 页设备本来就只支持 64 位 —— 两个理由指向同一个结论。
真要支持 32 位老机器，只能退回 Python 3.12 + Chaquopy 16，
那样 Android 15/16 又打不开了。不划算。

### APK 体积构成

| 部分 | 大小 | 说明 |
|---|---|---|
| arm64 原生库 + bootstrap | ~12 MB | CPython 3.13 + Chaquopy 运行时 |
| 内置字体 | 11.4 MB | 萝莉体，替换游戏字体要用 |
| 引擎基准 | 2.6 MB | v16~v21.1 的函数指纹 |
| 官方脚本 | 1.4 MB | debug 脚本 + Scene_Map，覆盖功能要用 |
| web + python 源码 | ~0.6 MB | 界面与逻辑 |

调试版含 x86_64（模拟器）约 45MB；发布版只有 arm64，约 **33MB**。

想在电脑的模拟器上跑：

```bash
cd android && gradlew assembleDebug -PwithEmulator=true
```

---

## 权限

需要「所有文件访问权限」——游戏脚本和存档都在 `/sdcard` 下，普通权限读不到。
首次启动会弹窗**说明为什么需要**再跳授权，可以选「暂不授权」先进去看界面。

**工具完全离线**，不联网、不上传任何数据（只连本机 127.0.0.1）。

---

## 目录结构

```
core/           ← 从电脑版原样拷来的核心模块（只读！勿手改）
    save_tools.py      存档读写，统一 v16~v21 差异
    debug_tool.py      开启 DEBUG / 关闭 / 还原
    engine_tools.py    ★ 基准覆盖（覆盖 debug 脚本与 Scene_Map）
    plugin_tools.py    ★ 中文文本处理插件 + 字体替换
    intl_text.py       中日韩文本处理
    engine_src.py      官方脚本基准的索引
    game_scripts.py    游戏根目录识别、rxdata 读写
    essentials_base.py 引擎版本探测与基准比对
    rmarshal.py / logger.py / mini_data.py / launcher.py / launcher_exe.py

core_data/      ← 人工从电脑版拷来的数据
    essentials_base/     引擎版本基准 JSON（v16 ~ v21.1）
    essentials_src/      ★ 官方脚本：各版本 debug 脚本 + Scene_Map（1.4MB）
    plugins/ctm-*/      中文文本处理插件本体（6 个版本变体）
    fonts/萝莉体.ttf      ★ 内置字体（11MB）

vendor/         ← 内置的第三方纯 Python 包（rubymarshal，避开 pip 的坑）
shim/           ← 移动端替身层
    config.py          替代 config.BASE_DIR / resource_path / FONT_FILE
bootstrap.py    ← 拼 sys.path：core/ + shim/ + vendor/

server/         ← HTTP 服务（全部标准库）
    app.py             路由 + SSE + /fonts/ 字体直出
    api_debug.py       开启/关闭/还原 DEBUG
    api_overwrite.py   ★ 基准覆盖
    api_font.py        ★ 字体替换
    api_save.py        存档编辑
    api_fs.py          目录浏览

web/            ← 手机界面（HTML/CSS/JS）
    index.html         含 3 秒封面页
    style.css          配色抄电脑版 gui.py
tools/          ← 手动脚本与测试
android/        ← App 壳
```

---

## 字体为什么要走插件

RPG Maker Essentials 默认用 RMVX 的位图字体渲染中文，直接改引擎字体常量的话
很多对话框还是方块。插件的做法是把字体名写进 `Font.default_name`，让引擎走
TTF 渲染路径 —— 这是 Essentials 生态公认的解法，电脑版实测有效。

字体实体只有一份（`core_data/fonts/萝莉体.ttf`，11MB），服务端挂在 `/fonts/lolita.ttf`
给 CSS 用。**不在 `web/` 里再放一份**，否则 APK 会凭空胖 11MB。

> 路由用 ASCII 别名 `lolita.ttf` 而不是中文文件名：中文 URL 在部分
> WebView / ROM 上编码不一致，会 404。

---

## 构建前提

| 依赖 | 位置 |
|---|---|
| JDK 17 | `C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot` |
| Android SDK 36 | `C:\Android`（platform-36 + build-tools 36.0.0） |
| Gradle 8.13 | `C:\Gradle\gradle-8.13`，或用仓库自带的 wrapper |

`android/local.properties` 里写 SDK 路径，默认 `C:\Android`。

### 踩过的坑

1. **Chaquopy 的 `pip install` 会报 `No module named 'cgi'`**
   它的构建环境 pip 版本偏旧，Python 3.13 已移除 `cgi`。
   → `rubymarshal` 直接内置进 `vendor/`（6 个纯 Python 文件、26KB、零依赖）。

2. **`settings.gradle` 的 `FAIL_ON_PROJECT_REPOS` 与根 `build.gradle` 的
   `allprojects.repositories` 冲突** → 报 "prefer settings repositories"。
   仓库统一由 settings 管，根 build.gradle 只留 buildscript。

2. **`Settings.rxdata` 里少于 10 条脚本时工具不认**
   写测试造假游戏时最容易踩 —— 数据能读出来，但 `collect_scripts` 直接跳过。
   造样本要凑够 10 条。

   顺带一提：**`Scripts.rxdata` 在 `Data/` 下面**，不是游戏根目录。
   建错位置的话所有脚本都「找不到」，看起来像功能坏了，其实是自己造错了。

3. **Python 3.13 没有 32 位（armeabi-v7a）版本**
   Chaquopy 17 直接报 `Python 3.13 is not available for the ABI 'armeabi-v7a'`。
   → `abiFilters` 只留 `arm64-v8a` + `x86_64`。

4. **Kotlin stdlib 重复类**
   appcompat 1.7 拉 `kotlin-stdlib-jdk7/jdk8:1.6.21`，webkit 1.12 拉
   `kotlin-stdlib:1.8.22` —— 从 1.8 起前两个已并入主包，同包共存就报
   一堆 `Duplicate class kotlin.io.path.PathsKt`。
   → 在 `dependencies { constraints { … } }` 里把两者顶到同一版本。

---

## 已实测通过

```bash
python tools/verify_core.py           # 26 项：模块加载 + 数值函数 + 坏档识别
python tools/test_debug_e2e.py        # 13 项：$DEBUG 真写进 pbCallTitle、幂等、还原
python tools/test_overwrite_font.py   # 30 项：覆盖真改文件 + 还原、字体真装进 Fonts/
python tools/smoke_api.py             # 接口冒烟 + SSE 实时日志
python tools/check_16kb.py            # APK 原生库 16KB 对齐检查
```

**还没在真机上验证过**：第一次用请先拿**副本**试存档。