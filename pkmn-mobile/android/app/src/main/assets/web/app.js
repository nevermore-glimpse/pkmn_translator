/* 宝可梦同人工具 —— 前端逻辑
   只和本机 Python 服务通信，端口由 MainActivity 注入。 */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const API = async (path, body) => {
    const opt = body
      ? { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body) }
      : { method: "GET" };
    const r = await fetch(path, opt);
    return await r.json();
  };

  // ------------------------------------------------------------
  // 小工具
  // ------------------------------------------------------------
  function toast(msg, ms) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("on");
    clearTimeout(t._h);
    t._h = setTimeout(() => t.classList.remove("on"), ms || 2200);
  }

  function esc(s) {
    return String(s === undefined || s === null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function kv(pairs) {
    return pairs.map(([k, v, cls]) =>
      `<div class="k">${esc(k)}</div><div class="v ${cls || ""}">${esc(v)}</div>`
    ).join("");
  }

  /**
   * 通用确认框。WebView 里 confirm() 会被部分 ROM 拦掉，
   * 而且样式跟 App 不统一 —— 统一用自己的对话框。
   */
  function confirmBox(title, bodyHtml, okText, danger) {
    return new Promise((resolve) => {
      $("dlgH").textContent = title;
      $("dlgB").innerHTML = bodyHtml;
      const f = $("dlgF");
      f.innerHTML = "";
      const cancel = document.createElement("button");
      cancel.className = "btn ghost";
      cancel.textContent = "取消";
      const ok = document.createElement("button");
      ok.className = "btn " + (danger ? "danger" : "primary");
      ok.textContent = okText || "确定";
      f.appendChild(cancel);
      f.appendChild(ok);
      $("dlg").classList.add("on");
      const done = (v) => {
        $("dlg").classList.remove("on");
        ok.onclick = null; cancel.onclick = null;
        resolve(v);
      };
      ok.onclick = () => done(true);
      cancel.onclick = () => done(false);
    });
  }

  /**
   * 多选按钮对话框（confirmBox 只有两个按钮，这个能放任意个）。
   * buttons: [{text, value, cls}]；返回被点按钮的 value，未选就返回 null。
   */
  function choiceBox(title, bodyHtml, buttons) {
    return new Promise((resolve) => {
      $("dlgH").textContent = title;
      $("dlgB").innerHTML = bodyHtml;
      const f = $("dlgF");
      f.innerHTML = "";
      let settled = false;
      const done = (v) => {
        if (settled) return;
        settled = true;
        $("dlg").classList.remove("on");
        resolve(v);
      };
      buttons.forEach((b) => {
        const el = document.createElement("button");
        el.className = "btn " + (b.cls || "");
        el.textContent = b.text;
        el.addEventListener("click", () => done(b.value));
        f.appendChild(el);
      });
      $("dlg").classList.add("on");
    });
  }

  function askBox(title, label, value) {
    return new Promise((resolve) => {
      $("dlgH").textContent = title;
      $("dlgB").innerHTML =
        `<div class="hint" style="margin-bottom:8px">${esc(label)}</div>` +
        `<input class="inp" id="dlgInput" value="${esc(value || "")}">`;
      const f = $("dlgF");
      f.innerHTML = "";
      const cancel = document.createElement("button");
      cancel.className = "btn ghost";
      cancel.textContent = "取消";
      const ok = document.createElement("button");
      ok.className = "btn primary";
      ok.textContent = "确定";
      f.appendChild(cancel);
      f.appendChild(ok);
      $("dlg").classList.add("on");
      setTimeout(() => $("dlgInput").focus(), 60);
      const done = (v) => {
        $("dlg").classList.remove("on");
        resolve(v);
      };
      ok.onclick = () => done($("dlgInput").value);
      cancel.onclick = () => done(null);
      $("dlgInput").onkeydown = (e) => { if (e.key === "Enter") done(e.target.value); };
    });
  }

  // ------------------------------------------------------------
  // 任务2：封面页，停留 3 秒
  // ------------------------------------------------------------
  (function cover() {
    const el = $("cover");
    if (!el) return;
    let done = false;
    const leave = () => {
      if (done) return;
      done = true;
      el.classList.add("leave");
      setTimeout(() => el.remove(), 480);
      loadHealth();
    };
    $("coverSkip").addEventListener("click", leave);
    setTimeout(leave, 3000);          // ★ 任务2：3 秒
  })();

  // ------------------------------------------------------------
  // 页面切换
  // ------------------------------------------------------------
  const TITLES = {
    debug: "开启 DEBUG",
    ow: "基准覆盖",
    font: "字体替换",
    save: "存档编辑",
    pbs: "PBS 编辑",
    about: "关于",
  };

  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.addEventListener("click", () => {
      const p = b.dataset.page;
      document.querySelectorAll(".tab-btn").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".page").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      $("page-" + p).classList.add("active");
      $("pageTitle").textContent = TITLES[p] || "";
      if (p === "about") loadAbout();
      if (p === "ow") loadOwState();
      if (p === "font") loadFonts();
      if (p === "pbs") loadPbs();
    });
  });

  // ------------------------------------------------------------
  // 健康检查
  // ------------------------------------------------------------
  async function loadHealth() {
    try {
      const r = await API("/api/health");
      if (!r.ok) throw new Error(r.message);
      const miss = r.data.missing || [];
      $("healthLine").textContent = miss.length
        ? "核心模块缺失：" + miss.join("/")
        : "就绪 · Python " + r.data.python;
    } catch (e) {
      $("healthLine").textContent = "服务未连接：" + e.message;
    }
  }

  async function loadAbout() {
    let r;
    try { r = await API("/api/health"); }
    catch (e) { $("aboutBody").textContent = "服务未连接"; return; }
    const d = (r && r.data) || {};
    const mods = Object.entries(d.modules || {})
      .map(([k, v]) => [k, v === "ok" ? "已加载" : v, v === "ok" ? "on" : "off"]);
    $("aboutBody").innerHTML = kv([
      ["Python", d.python],
      ["工作根目录", d.root],
      ["core/ 目录", d.core_exists ? "就位" : "缺失", d.core_exists ? "on" : "off"],
      ["基准数据", d.data_exists ? "就位" : "缺失", d.data_exists ? "on" : "off"],
      ["基准目录", d.data_dir],
    ].concat(mods));
    renderBaseline(d);
  }

  /**
   * 关于页的「内置基准数据」。
   *
   * ★ 以前这里只看 data_exists 一个布尔值，而那个值在安卓上是错的
   *   （bootstrap 把 core_data 路径写死成源码树下，永远是 False）——
   *   于是关于页一直显示「基准数据：缺失」，用户以为数据没打包进去。
   *   实际数据一直都在。现在把版本号列出来，一眼就能确认。
   */
  function renderBaseline(d) {
    const base = d.baseline_versions || [];
    const src = d.src_versions || [];
    const okData = !!d.data_exists;
    $("baselineBody").innerHTML = kv([
      ["引擎基准", okData ? base.length + " 个版本" : "缺失", base.length ? "on" : "off"],
      ["官方 debug 脚本", src.length + " 个版本", src.length ? "on" : "off"],
    ]) + (base.length
      ? `<div style="margin-top:8px">` + base.map((v) =>
          `<span class="tag on">v${esc(v)}</span>`).join("") + `</div>`
      : `<div class="hint err" style="margin-top:8px">没找到基准数据 —— `
        + `请把「诊断报告」发给我（APK 里的 core_data 可能没解出来）。</div>`);
  }

  // ------------------------------------------------------------
  // 夜间模式
  // ------------------------------------------------------------
  // 偏好存在后端（App 私有目录），不放在浏览器 localStorage —— 原因是
  // WebView 每次启动都用随机端口起服务，源（http://127.0.0.1:<随机端口>）
  // 每次都变，localStorage 按源隔离，重启就读不到，表现就是「退出再进又变白天」。
  // 首屏的 .night 类由 index.html 内联脚本注入（值来自后端），这里只负责
  // ① 同步开关按钮文字 ② 点击切换并写回后端落盘。
  function isNight() {
    return document.body.classList.contains("night");
  }

  function applyNight(on) {
    on = !!on;
    document.body.classList.toggle("night", on);
    $("btnNight").textContent = on ? "关闭" : "开启";
    // 安卓状态栏 / 最近任务里的主题色也跟着换
    const meta = $("metaTheme");
    if (meta) meta.setAttribute("content", on ? "#12181F" : "#0F4C86");
    window.__NIGHT__ = on;
    // 持久化：写回后端落盘，重启后依然生效
    try {
      fetch("api/settings/set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ night: on })
      }).catch(function () {});
    } catch (e) {}
  }

  applyNight(isNight());   // 类通常已由首屏脚本挂好，这里只是把按钮文字对上

  $("btnNight").addEventListener("click", () => {
    applyNight(!isNight());
    toast(isNight() ? "夜间模式已开启" : "夜间模式已关闭");
  });

  // ------------------------------------------------------------
  // 游戏定位：手机版**选游戏主程序（exe）**，由它推出游戏根目录
  //   —— 手机上要一层层点进 Android/data/<包名>/ 找那一层文件夹太费劲，
  //      直接点 Game.exe 更直观，根目录由后端 exe_root() 算出来。
  //   所有后端接口仍收「游戏根目录」（gameDir() 返回的就是它）。
  //   ★ 四个页面各有一个「游戏主程序」输入框，值保持同步；这一段要放在
  //     浏览按钮绑定之前（const 有暂时性死区，晚了会直接报错）。
  // ------------------------------------------------------------
  let gameRoot = "";                    // 由 exe 解析出来的游戏根目录
  const EXE_IDS = ["gameExe", "gameExeOw", "gameExeFont", "gameExeSave",
    "gameExePbs"];
  const gameExe = () => ($("gameExe").value || "").trim();
  const gameDir = () => gameRoot;       // 兼容原来所有 gameDir() 调用点

  function syncExe(v) {
    EXE_IDS.forEach((id) => {
      const el = $(id);
      if (el && el.value !== v) el.value = v;
    });
  }

  function isFontFile(name) {
    return /\.(ttf|otf|ttc)$/i.test(String(name || ""));
  }

  // ------------------------------------------------------------
  // 目录 / 文件浏览
  // ------------------------------------------------------------
  let browseMode = "dir";          // dir / file / exe / font
  let browseTarget = null;
  let browseCwd = "";

  function openBrowse(mode, targetId, title) {
    browseMode = mode;
    browseTarget = $(targetId);
    $("browseTitle").textContent = title;
    $("browseSheet").classList.add("on");
    browseCwd = browseTarget.value || "";
    listDir(browseCwd);
  }

  async function listDir(dir) {
    const r = await API("/api/fs/list?dir=" + encodeURIComponent(dir || ""));
    if (!r.ok) {
      // 直接把原因铺在列表里，别用 toast —— 安卓上的报错都好几句，
      // toast 一闪就没了，用户根本读不完。
      $("browseList").innerHTML =
        `<div class="hint err" style="padding:11px 15px;white-space:pre-line">`
        + esc(r.message || "读取失败") + `</div>`;
      return;
    }
    browseCwd = r.data.cwd || "";
    $("browsePath").textContent = browseCwd || "选择位置";
    const rows = [];
    const isExe = browseMode === "exe";

    // 空路径在安卓上返回的是「可用起点列表」，带一句说明
    if (r.data.hint && !browseCwd) {
      rows.push(`<div class="hint" style="padding:11px 15px;white-space:pre-line">`
                + esc(r.data.hint) + `</div>`);
    }
    if (r.data.parent !== null && r.data.parent !== undefined) {
      rows.push(`<div data-up="1">📁 .. 返回上级</div>`);
    }
    if (browseMode === "dir" && browseCwd) {
      const star = r.data.looks_like_game ? "　★ 看着就是游戏根目录" : "";
      rows.push(`<div data-pick="${esc(browseCwd)}">✓ 就选当前这个目录${star}</div>`);
    }
    (r.data.dirs || []).forEach((d) => {
      rows.push(`<div data-dir="${esc(d.path)}">📁 ${esc(d.name)}</div>`);
    });
    let files = r.data.files || [];
    const isFont = browseMode === "font";
    // 选游戏主程序时，只把 exe / 启动脚本列出来 —— 手机上目录文件很多，
    // 混在一起很难找（点错的概率也高）。选字体只列字体文件，同理。
    if (isExe) files = files.filter((f) => f.looks_like_exe);
    if (isFont) files = files.filter((f) => isFontFile(f.name));
    if (isExe && browseCwd && !files.length) {
      rows.push(`<div class="hint" style="padding:11px 15px">` +
                `这个目录里没有 .exe —— 游戏主程序一般在 Data 的<b>上一层</b>，` +
                `试试返回上级。</div>`);
    }
    if (isFont && browseCwd && !files.length) {
      rows.push(`<div class="hint" style="padding:11px 15px">` +
                `这个目录里没有 .ttf / .otf / .ttc 字体文件。</div>`);
    }
    files.forEach((f) => {
      const kb = f.size != null ? (f.size / 1024).toFixed(0) + "K" : "";
      const pickable = (browseMode === "file") ||
                       (isExe && f.looks_like_exe) ||
                       (isFont && isFontFile(f.name));
      const attr = pickable ? `data-pick="${esc(f.path)}"` : `data-dir="${esc(f.path)}"`;
      const icon = f.looks_like_exe ? "🎮"
                 : (isFontFile(f.name) ? "字"
                 : (f.looks_like_save ? "💾" : "📄"));
      rows.push(`<div ${attr}>${icon} ${esc(f.name)}` +
                `　<span class="sub">${kb}</span></div>`);
    });
    if (!rows.length) rows.push(`<div class="hint" style="padding:11px 15px">（空目录）</div>`);
    $("browseList").innerHTML = rows.join("");

    $("browseList").querySelectorAll("div[data-up],div[data-dir],div[data-pick]")
      .forEach((el) => {
        el.addEventListener("click", () => {
          if (el.dataset.up) { listDir(parentOf(browseCwd)); return; }
          if (el.dataset.pick !== undefined) {
            browseTarget.value = el.dataset.pick;
            $("browseSheet").classList.remove("on");
            browseTarget.dispatchEvent(new Event("change"));
            return;
          }
          listDir(el.dataset.dir);
        });
      });
  }

  function parentOf(p) {
    if (!p) return "";
    const i = p.lastIndexOf("/");
    return i > 0 ? p.slice(0, i) : "";
  }

  // 「游戏主程序」浏览按钮：四个页面各一个，逻辑完全一样
  ["btnBrowseGame", "btnBrowseGameOw", "btnBrowseGameFont",
   "btnBrowseGameSave"].forEach((btn, i) => {
    const el = $(btn);
    if (el) el.addEventListener("click", () =>
      openBrowse("exe", EXE_IDS[i], "选择游戏主程序（Game.exe）"));
  });
  $("btnBrowsePbsGame").addEventListener("click", () =>
    openBrowse("exe", "gameExePbs", "选择游戏主程序（Game.exe）"));
  $("btnBrowseFont").addEventListener("click", () =>
    openBrowse("font", "fontPath", "选择字体文件"));
  $("btnBrowseSave").addEventListener("click", () =>
    openBrowse("file", "savePath", "选择存档文件"));
  $("browseClose").addEventListener("click", () =>
    $("browseSheet").classList.remove("on"));

  // ------------------------------------------------------------
  // 通用：跑一个 SSE 任务
  // ------------------------------------------------------------
  let currentSource = null;

  function runTask(path, body, logId, barId, cancelId, afterDone) {
    const log = $(logId), bar = $(barId);
    log.textContent = "";
    $(cancelId).disabled = false;
    bar.style.width = "8%";

    return new Promise(async (resolve) => {
      const r = await API(path, body);
      if (!r.ok) {
        log.textContent = "✘ " + (r.message || "请求失败");
        $(cancelId).disabled = true;
        bar.style.width = "0";
        return resolve(null);
      }
      currentSource = new EventSource("/api/task/" + r.data.task_id + "/stream");
      currentSource.onmessage = (ev) => {
        const d = JSON.parse(ev.data);
        if (d.type === "log") {
          log.textContent += d.payload + "\n";
          log.scrollTop = log.scrollHeight;
        } else if (d.type === "prog") {
          const p = d.payload || {};
          if (p.total) bar.style.width =
            Math.round((p.done || 0) / p.total * 100) + "%";
          if (p.text) log.textContent += p.text + "\n";
        } else if (d.type === "done") {
          bar.style.width = "100%";
          currentSource.close();
          $(cancelId).disabled = true;
          const ok = d.payload && d.payload.ok;
          toast(ok ? "完成" : "结束（详见日志）");
          if (afterDone) afterDone(d.payload);
          resolve(d.payload);
        } else if (d.type === "error") {
          log.textContent += "✘ " + (d.payload.message || "") + "\n";
        }
      };
      currentSource.onerror = () => {
        currentSource.close();
        $(cancelId).disabled = true;
        resolve(null);
      };
    });
  }

  function bindCancel(btnId, logId) {
    $(btnId).addEventListener("click", async () => {
      if (!currentSource) return;
      try { await API("/api/task/x/cancel", {}); } catch (e) {}
      currentSource.close();
      $(logId).textContent += "（已请求取消）\n";
      $(btnId).disabled = true;
    });
  }

  // ------------------------------------------------------------
  // 开启方式（①–⑦，清单由后端给，避免前后端各写一份）
  // ------------------------------------------------------------
  let DEBUG_MODES = [];

  async function loadModes() {
    const sel = $("debugMode");
    const r = await API("/api/debug/modes");
    if (!r.ok || !r.data || !(r.data.modes || []).length) {
      sel.innerHTML = `<option value="main">① 通用（写 Main，启动即调试）</option>`;
      return;
    }
    DEBUG_MODES = r.data.modes;
    sel.innerHTML = DEBUG_MODES.map((m) =>
      `<option value="${esc(m.key)}">${esc(m.label)}</option>`).join("");
    sel.value = "main";
    renderModeDesc();
  }

  function renderModeDesc() {
    const m = DEBUG_MODES.find((x) => x.key === $("debugMode").value);
    $("debugModeDesc").textContent = m ? m.desc : "";
  }

  $("debugMode").addEventListener("change", renderModeDesc);
  loadModes();

  // ------------------------------------------------------------
  // 记住上次选的游戏主程序 —— 手机上每次重开都要重新点进
  // Android/data/xxx 里翻一遍，实在难受
  // ------------------------------------------------------------
  const EXE_KEY = "pkmn.gameExe";

  function rememberExe(exe) {
    try { if (exe) localStorage.setItem(EXE_KEY, exe); } catch (e) {}
  }

  // ------------------------------------------------------------
  // 开启 DEBUG
  // ------------------------------------------------------------
  function appendLog(text) {
    const el = $("debugLog");
    if (el.textContent.startsWith("（")) el.textContent = "";
    el.textContent += text + "\n";
    el.scrollTop = el.scrollHeight;
  }

  /**
   * 解析「游戏主程序」→ 游戏根目录，并刷新各页状态。
   * 后端 `check_game?exe=` 会顺带做根目录校验（含 Data/）。
   */
  function renderExeMini(text, bad) {
    ["gameInfoOw", "gameInfoFont", "gameInfoSave"].forEach((id) => {
      const el = $(id);
      if (el) el.innerHTML = bad ? `<span class="err">${esc(text)}</span>` : esc(text);
    });
  }

  async function refreshGameInfo() {
    const exe = gameExe();
    rememberExe(exe);
    if (!exe) {
      gameRoot = "";
      $("gameInfo").innerHTML = `<div class="hint">还没选择游戏主程序</div>`;
      renderExeMini("还没选择游戏主程序");
      loadOwState();
      return;
    }
    const r = await API("/api/fs/check_game?exe=" + encodeURIComponent(exe));
    if (!r.ok) {
      gameRoot = "";
      $("gameInfo").innerHTML = `<div class="hint err">${esc(r.message)}</div>`;
      renderExeMini(r.message || "识别失败", true);
      loadOwState();
      return;
    }
    gameRoot = r.data.dir || "";
    $("gameInfo").innerHTML = kv([
      ["游戏主程序", r.data.exe_name || ""],
      ["识别结果", r.data.valid ? "通过" : "不通过", r.data.valid ? "on" : "off"],
      ["游戏根目录", gameRoot || "（未解析出）"],
      ["说明", r.data.reason],
    ]);
    renderExeMini(gameRoot ? ("游戏根目录：" + gameRoot) : "（未解析出游戏根目录）");
    // 存档页的「游戏根目录（数据源）」自动跟着填，用户不用再选一次
    if (gameRoot && (!$("saveRoot").value.trim() || $("saveRoot").dataset.auto === "1")) {
      $("saveRoot").value = gameRoot;
      $("saveRoot").dataset.auto = "1";
    }
    const sr = $("saveRootHint");
    if (sr) {
      sr.innerHTML = gameRoot
        ? ("数据源目录：<b>" + esc(gameRoot) + "</b>（自动来自游戏主程序）<br>" +
           "宝可梦 / 道具的名字按这个目录里的数据显示。")
        : ("<b>游戏数据可以不选</b>：" +
           "名字显示不全，这时改「种族 / 道具 / 特性 / 招式 / 训练家类型」" +
           "请填 <b>英文内部名</b>（如 PIKACHU / POKEBALL）或<b>编号</b>。");
    }
    if (r.data.valid) loadDebugStatus();
    loadOwState();
    // 字体页：顺手刷一下当前装了什么插件
    if (document.querySelector("#page-font.active")) loadFontScan();
  }

  async function loadDebugStatus() {
    const dir = gameDir();
    if (!dir) return;
    const r = await API("/api/debug/status?dir=" + encodeURIComponent(dir));
    const box = $("debugStatus");
    if (!r.ok) { box.innerHTML = `<div class="hint err">${esc(r.message)}</div>`; return; }
    const d = r.data;
    box.innerHTML = kv([
      ["Essentials 版本", d.version],
      ["DEBUG 开关", d.debug_on ? "已开启" : "未开启", d.debug_on ? "on" : "off"],
    ]);
  }

  $("btnCheckGame").addEventListener("click", refreshGameInfo);
  // 四个页面的「游戏主程序」框都绑到同一套逻辑：改了哪个都同步到其它三个
  EXE_IDS.forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("change", () => {
      syncExe(el.value.trim());
      refreshGameInfo();
    });
  });
  $("saveRoot").addEventListener("input", () => {
    $("saveRoot").dataset.auto = "0";     // 用户手动改过就别再自动覆盖
  });

  $("btnEnable").addEventListener("click", async () => {
    const dir = gameDir();
    if (!dir) return toast("先选游戏主程序");

    // ★ 反调试**不自动注释**：先扫一遍，把可疑代码摆给用户看，让他自己选。
    //   电脑版有个复核窗口做这件事，手机用对话框代替。
    let adDecisions = undefined;      // undefined → 后端默认「不注释」
    const ad = await API("/api/debug/antidebug?dir=" + encodeURIComponent(dir));
    if (!ad.ok) {
      toast(ad.message, 3400);
      return;
    }
    const srcs = (ad.data && ad.data.sources) || [];
    if (srcs.length) {
      const list = srcs.map((s, i) => {
        const code = String(s.code || "").split("\n").slice(0, 14)
          .map((l) => "    " + l).join("\n");
        return `${i + 1}. 「${s.name}」 ${s.where}\n` +
               `   共 ${s.blocks} 处，下面是被判为反调试的代码：\n${code}`;
      }).join("\n\n");
      const body =
        `<div class="hint" style="margin-bottom:6px">` +
        `检测到 <b>${srcs.length}</b> 处疑似「反调试」代码 —— 它每帧把 ` +
        `$DEBUG 摁回 false，还会把场景踢掉，正是「开了没效果」的原因。` +
        `要不要自动注释掉？</div>` +
        `<div style="max-height:44vh;overflow:auto;font-size:12px;` +
        `line-height:1.55;white-space:pre-wrap;background:#FAFCFF;` +
        `border:1px solid #D5E4F5;border-radius:8px;padding:8px">` +
        `${esc(list)}</div>`;
      const pick = await choiceBox("发现疑似「反调试」代码", body, [
        { text: "自动注释", value: "comment", cls: "primary" },
        { text: "跳过（不注释）", value: "skip", cls: "ghost" },
        { text: "取消", value: null, cls: "ghost" },
      ]);
      if (pick === null || pick === undefined) {
        return toast("已取消（反调试代码未做任何改动）");
      }
      adDecisions = {};
      srcs.forEach((s) => { adDecisions[s.key] = pick; });
    }

    // 方式①–⑦ + 勾选项，全部交给后端（逻辑在 api_debug.api_enable）
    runTask("/api/debug/enable", {
      dir,
      mode: $("debugMode").value || "main",
      force: $("optForce").checked,
      antidebug: adDecisions,
    }, "debugLog", "debugBar", "btnCancel", loadDebugStatus);
  });
  $("btnDisable").addEventListener("click", () => {
    const dir = gameDir();
    if (!dir) return toast("先选游戏主程序");
    runTask("/api/debug/disable", { dir }, "debugLog", "debugBar", "btnCancel",
            loadDebugStatus);
  });
  $("btnRestore").addEventListener("click", async () => {
    const dir = gameDir();
    if (!dir) return toast("先选游戏主程序");
    if (!await confirmBox("还原备份",
      "会用自动备份覆盖当前脚本。<span class=\"warn\">原作者的改动如果不在备份里就找不回来了。</span>",
      "确认还原", true)) return;
    runTask("/api/debug/restore", { dir }, "debugLog", "debugBar", "btnCancel",
            loadDebugStatus);
  });
  bindCancel("btnCancel", "debugLog");

  // ------------------------------------------------------------
  // 基准覆盖
  // ------------------------------------------------------------
  async function loadOwState() {
    const dir = gameDir();
    const info = $("owInfo");
    if (!dir) {
      info.textContent = "先在「DEBUG」页选好游戏主程序";
      $("btnOwDebug").disabled = true;
      $("btnOwMap").disabled = true;
      return;
    }
    const r = await API("/api/ow/versions");
    if (!r.ok) {
      info.innerHTML = `<span class="err">${esc(r.message)}</span>`;
      return;
    }
    const vs = r.data.versions || [];
    // ★ 版本下拉：第一项「自动」= 游戏自报版本 → 读不到就用**脚本指纹**识别
    //   （后端 api_overwrite.resolve_version）。其余是手动指定。
    const cur = $("owVersion").value || "";
    $("owVersion").innerHTML =
      `<option value="">自动（自报版本 → 指纹识别）</option>` +
      vs.map((v) => `<option value="${esc(v.version)}">v${esc(v.version)}` +
        `（debug ${v.debug_count} 个脚本${v.has_scene_map ? "，含地图更新" : ""}）</option>`
      ).join("");
    $("owVersion").value = cur;

    // 让后端告诉我们「自动会选到哪一版」，直接显示出来
    let auto = "（未识别）", src = "";
    const dt = await API("/api/ow/detect?dir=" + encodeURIComponent(dir) +
                         "&version=" + encodeURIComponent(cur));
    if (dt.ok) {
      auto = dt.data.version ? ("v" + dt.data.version) : "（未识别）";
      src = dt.data.source || "";
    }
    info.innerHTML =
      `<div class="hint">当前会使用的基准：<b>${esc(cur ? ("v" + cur) : auto)}</b>` +
      (cur ? `　（手动指定）` : (src ? `　· ${esc(src)}` : "")) + `</div>` +
      `<div class="hint">自动 = 先读游戏自报版本，读不到就按<b>脚本指纹</b>挑最接近的基准：</div>` +
      `<div style="margin-top:6px">` + vs.map((v) =>
        `<span class="tag ${v.has_scene_map ? "on" : "off"}">v${esc(v.version)}` +
        ` · debug ${v.debug_count}</span>`).join("") + `</div>`;
    $("btnOwDebug").disabled = false;
    $("btnOwMap").disabled = false;
  }

  async function doOverwrite(kind) {
    const dir = gameDir();
    if (!dir) return toast("先在「DEBUG」页选好游戏主程序");
    // 覆盖是不可逆的（虽有备份），所以强制用户勾选知情确认
    if (!$("owWarn").checked) {
      const ok = await confirmBox(
        "确认覆盖" + (kind === "scene_map" ? "地图更新" : "debug 函数"),
        "这一步会用<b>官方同版本脚本</b>盖掉游戏里的对应文件。\n\n" +
        "<span class=\"warn\">原作者对这些脚本的改动会被替换掉。</span>\n\n" +
        "原文件会自动备份，之后可以用「还原覆盖」恢复。\n\n" +
        "要继续吗？",
        "我已了解，继续覆盖", true);
      if (!ok) return;
    }

    // 先给用户看一遍覆盖计划
    const plan = await API(
      `/api/ow/plan?dir=${encodeURIComponent(dir)}&kind=${kind}` +
      `&version=${encodeURIComponent($("owVersion").value.trim())}`);
    if (!plan.ok) { toast(plan.message); return; }
    const items = plan.data.items || [];
    if (!items.length) return toast("没有需要覆盖的脚本");

    // ★ 弹窗只负责问一句「是否开始执行」，清单放进可滚动正文。
    //   原先几十行清单直接当弹窗正文、又没有高度上限，弹窗被撑满全屏，
    //   小屏上「开始执行」按钮被顶出可视区，既看不到也点不到。
    //   现在 .dlg-b 有 max-height + 自身滚动（见 style.css），按钮固定在最下面。
    const listText = items.map((i) =>
      `${i.has_target ? "覆盖" : "新建"}　${esc(i.name)}` +
      (i.where ? `\n　　${esc(i.where)}` : "")).join("\n");

    const body =
      `<span class="warn">原作者对这些脚本的改动会被整份替换掉。</span>\n` +
      `原文件会自动备份，之后可用「还原覆盖」恢复。\n\n` +
      `<span class="hint">即将覆盖的 ${items.length} 个脚本：</span>\n` +
      listText;

    const ok = await confirmBox(
      `将覆盖 ${plan.data.count} 个脚本（v${plan.data.version}）—— 开始执行吗？`,
      body, "开始执行", true);
    if (!ok) return;

    const endpoint = kind === "scene_map"
      ? "/api/ow/overwrite_scene_map" : "/api/ow/overwrite_debug";
    await runTask(endpoint,
      { dir, version: plan.data.version },
      "owLog", "owBar", "btnOwCancel");
  }

  $("btnOwDebug").addEventListener("click", () => doOverwrite("debug"));
  $("btnOwMap").addEventListener("click", () => doOverwrite("scene_map"));
  $("btnOwRestore").addEventListener("click", async () => {
    const dir = gameDir();
    if (!dir) return toast("先选游戏主程序");
    if (!await confirmBox("还原覆盖",
      "把所有被本工具覆盖过的脚本恢复回覆盖前的状态。", "确认还原", true)) return;
    runTask("/api/ow/restore", { dir }, "owLog", "owBar", "btnOwCancel");
  });
  bindCancel("btnOwCancel", "owLog");
  $("owVersion").addEventListener("change", loadOwState);

  // ------------------------------------------------------------
  // 任务5：字体替换（#fontPath 留空 = 用工具自带的萝莉体）
  // ------------------------------------------------------------
  let fontsCache = [];

  const fontPath = () => ($("fontPath").value || "").trim();
  const builtinFont = () => fontsCache.find((f) => f.builtin) || null;

  async function loadFonts() {
    const r = await API("/api/font/fonts");
    if (!r.ok) {
      $("fontList").innerHTML = `<span class="err">${esc(r.message)}</span>`;
      return;
    }
    fontsCache = r.data.fonts || [];
    if (!fontsCache.length) {
      $("fontList").innerHTML =
        `<div class="hint">没找到可用字体（内置字体缺失：core_data/fonts/）</div>`;
      return;
    }
    const cur = fontPath();
    $("fontList").innerHTML =
      `<div class="hint" style="margin-bottom:7px">点一个选中：</div>` +
      fontsCache.map((f, i) =>
        `<div class="item" data-font="${i}">` +
        `<span class="tag ${f.builtin ? "on" : "off"}">${f.builtin ? "内置" : "自备"}</span>` +
        `<span class="grow">${esc(f.name)}` +
        `<div class="sub">${esc(f.family || "读不出族名")} · ${(f.size / 1048576).toFixed(1)}MB</div></span>` +
        ((cur ? f.path === cur : f.builtin) ? `<span class="tag on">已选</span>` : "")
        + `</div>`).join("");
    $("fontList").querySelectorAll("[data-font]").forEach((el) => {
      el.addEventListener("click", () => {
        $("fontPath").value = fontsCache[+el.dataset.font].path;
        loadFonts();
      });
    });
  }

  $("fontPath").addEventListener("change", loadFonts);
  $("btnFontBuiltin").addEventListener("click", () => {
    $("fontPath").value = "";
    loadFonts();
  });

  async function loadFontScan() {
    const dir = gameDir();
    if (!dir) { $("fontInfo").innerHTML = ""; return; }
    const r = await API("/api/font/scan?dir=" + encodeURIComponent(dir));
    $("fontInfo").innerHTML = r.ok
      ? kv([["当前插件", (r.data.plugins || []).join("、") || "未安装"]])
      : "";
  }

  $("btnFontInstall").addEventListener("click", async () => {
    const dir = gameDir();
    if (!dir) return toast("先选游戏主程序");
    const picked = fontPath() || builtinFont();
    const name = picked ? picked.name : "工具自带萝莉体";
    const ok = await confirmBox("替换游戏字体",
      `将把游戏字体换成 <b>${esc(name)}</b>。<br><br>` +
      `会植入「中文文本处理」插件，并修改引擎里的字体定义。<br>` +
      `原文件会自动备份，可用「还原」撤销。`,
      "确认替换", true);
    if (!ok) return;
    // font 留空 = 后端用内置萝莉体
    runTask("/api/font/install", { dir, font: fontPath() },
            "fontLog", "fontBar", "btnFontCancel");
  });

  $("btnFontRestore").addEventListener("click", async () => {
    const dir = gameDir();
    if (!dir) return toast("先选游戏主程序");
    if (!await confirmBox("还原字体",
      "移除插件、恢复原字体、撤销引擎改动。", "确认还原", true)) return;
    runTask("/api/font/restore", { dir },
            "fontLog", "fontBar", "btnFontCancel");
  });
  bindCancel("btnFontCancel", "fontLog");

  // ------------------------------------------------------------
  // 存档编辑（对齐电脑版菜单 6：主角 / 同行 / 背包 / 箱子 / 开关变量）
  // ------------------------------------------------------------
  let saveView = "trainer";

  const saveArgs = () =>
    "path=" + encodeURIComponent($("savePath").value.trim()) +
    "&game_root=" + encodeURIComponent($("saveRoot").value.trim());

  const saveBody = () => $("saveBody");

  function val(id) { const e = $(id); return e ? e.value : ""; }
  function numOr(id, dflt) {
    const v = parseInt(val(id), 10);
    return isNaN(v) ? dflt : v;
  }

  // ---- 选项缓存（species / item / move / nature / status / trainer_type / ability） ----
  const OPT = {};
  async function getOptions(kind, where) {
    const key = kind + ":" + (where || "");
    if (OPT[key]) return OPT[key];
    const r = await API("/api/save/options?" + saveArgs() + "&kind=" + kind +
                        (where ? "&where=" + encodeURIComponent(where) : ""));
    if (!r.ok) return [];
    OPT[key] = r.data.options || [];
    return OPT[key];
  }
  function optName(opts, id) {
    const hit = (opts || []).find((o) => String(o[1]) === String(id));
    return hit ? hit[0] : "（#" + id + "）";
  }

  // ---- 选择器：搜索 + 手输（物种 / 道具 / 招式） ----
  let pickState = null;

  async function openPicker(kind, currentId, onPick, where) {
    const opts = await getOptions(kind, where);
    pickState = { kind, opts, onPick, currentId, where };
    $("pickTitle").textContent =
      ({ species: "选择宝可梦", item: "选择道具", move: "选择招式",
         nature: "选择性格", status: "选择状态", ability: "选择特性",
         trainer_type: "选择训练家类型" }[kind]) || "选择";
    $("pickManualHint").textContent =
      "找不到就点最上面那条「用手输…」——必须用英文内部名（如 PIKACHU）或编号。";
    $("pickSearch").value = "";
    renderPick("");
    $("pickSheet").classList.add("on");
    setTimeout(() => { try { $("pickSearch").focus(); } catch (e) {} }, 60);
  }

  function renderPick(q) {
    if (!pickState) return;
    const { opts, currentId } = pickState;
    const list = $("pickList");
    const rows = [];
    q = (q || "").trim();
    const low = q.toLowerCase();
    if (q) {
      rows.push(`<div data-manual="1">✎ 用手输的「${esc(q)}」（英文内部名 / 编号）</div>`);
    }
    let hits = q
      ? opts.filter((o) => String(o[0]).toLowerCase().includes(low) ||
                            String(o[1]) === low)
      : opts;
    hits = hits.slice(0, 400);
    hits.forEach(([n, id]) => {
      rows.push(`<div data-id="${id}">${esc(n)}　<span class="sub">#${id}</span>` +
                (String(id) === String(currentId) ? ` <span class="tag on">当前</span>` : "") +
                `</div>`);
    });
    if (!hits.length && !q) {
      rows.push(`<div class="hint" style="padding:11px 15px">` +
                `（没有选项数据 —— 请用搜索框手输英文内部名或编号）</div>`);
    }
    list.innerHTML = rows.join("");
    list.querySelectorAll("div[data-id],div[data-manual]").forEach((el) => {
      el.addEventListener("click", async () => {
        let id = null;
        if (el.dataset.manual) {
          const r = await API("/api/save/resolve?" + saveArgs() +
            "&kind=" + pickState.kind + "&text=" + encodeURIComponent(q) +
            (pickState.where ? "&where=" + encodeURIComponent(pickState.where) : ""));
          if (!r.ok) return toast(r.message, 3400);
          id = r.data.id;
        } else {
          id = Number(el.dataset.id);
        }
        const label = optName(pickState.opts, id);
        $("pickSheet").classList.remove("on");
        const cb = pickState.onPick;
        pickState = null;
        if (cb) cb(id, label);
      });
    });
  }

  $("pickSearch").addEventListener("input", (e) => renderPick(e.target.value));
  $("pickClose").addEventListener("click", () => {
    $("pickSheet").classList.remove("on");
    pickState = null;
  });

  // ---- 表单小工具 ----
  function fieldRow(label, inner) {
    return `<div class="field"><div class="lb">${esc(label)}</div>${inner}</div>`;
  }
  function numInp(id, value, extra) {
    return `<input id="${id}" class="inp" type="number" inputmode="numeric"` +
           ` value="${value === undefined || value === null ? "" : esc(value)}"` +
           `${extra || ""}>`;
  }
  function txtInp(id, value) {
    return `<input id="${id}" class="inp" type="text" value="${value == null ? "" : esc(value)}">`;
  }
  function pickBtn(id, label) {
    return `<button class="pick" id="${id}"><span class="val">${esc(label)}</span>` +
           `<span class="arw">选择▾</span></button>`;
  }
  function selInp(id, value, options) {
    return `<select id="${id}" class="inp">` + options.map(([n, v]) =>
      `<option value="${esc(v)}"${String(v) === String(value) ? " selected" : ""}>` +
      `${esc(n)}</option>`).join("") + `</select>`;
  }
  const STAT6 = ["HP", "攻击", "防御", "速度", "特攻", "特防"];

  // ------------------------------------------------------------
  // 打开存档 / 分页面
  // ------------------------------------------------------------
  async function openSave() {
    const path = $("savePath").value.trim();
    if (!path) return toast("先选存档文件");
    const r = await API("/api/save/open", {
      path, game_root: $("saveRoot").value.trim() || undefined,
    });
    if (!r.ok) {
      $("saveInfo").innerHTML = `<div class="hint err">打不开：${esc(r.message)}</div>`;
      return;
    }
    const d = r.data;
    for (const k in OPT) delete OPT[k];        // 换存档 → 选项缓存作废
    $("saveInfo").innerHTML = kv([
      ["格式", d.fmt], ["封装", d.encoding_label], ["读取", "成功", "on"],
    ]);
    toast("存档已打开");
    renderSaveView();
  }

  document.querySelectorAll("#saveTabs .tab").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#saveTabs .tab").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      saveView = b.dataset.view;
      renderSaveView();
    });
  });

  async function renderSaveView() {
    const body = saveBody();
    if (!$("savePath").value.trim()) {
      body.innerHTML = `<div class="hint">先打开一个存档</div>`;
      return;
    }
    body.innerHTML = `<div class="hint">读取中…</div>`;
    try {
      if (saveView === "trainer") return await viewTrainer(body);
      if (saveView === "party")  return await viewParty(body);
      if (saveView === "bag")    return await viewBag(body);
      if (saveView === "boxes")  return await viewBoxes(body);
      if (saveView === "vars")   return await viewVars(body);
    } catch (e) {
      body.innerHTML = `<div class="hint err">加载失败：${esc(e.message)}</div>`;
    }
  }

  // ------------------------------------------------------------
  // 主角
  // ------------------------------------------------------------
  async function viewTrainer(body) {
    const r = await API("/api/save/trainer?" + saveArgs());
    if (!r.ok) { body.innerHTML = `<div class="hint err">${esc(r.message)}</div>`; return; }
    const t = r.data.trainer || {};
    const bd = await API("/api/save/badges?" + saveArgs());
    const badges = (bd.ok && bd.data.badges) || [];
    const ttypes = await getOptions("trainer_type");

    // ★ 训练家类型也允许手输内部名（POKEMONTRAINER_Red）；没选游戏数据时
    //   下拉是空的，这时**不发送**这个字段（避免把当前编号误写成别的类型）。
    const ttCtrl = pickBtn("tr_tt", t["训练家类型"] || "（未设）");

    body.innerHTML =
      `<div class="card-h">主角</div>` +
      fieldRow("名字", txtInp("tr_name", t["名字"])) +
      fieldRow("金钱", numInp("tr_money", t["持有金钱"])) +
      fieldRow("训练家ID", numInp("tr_id", t["训练家ID"])) +
      fieldRow("语种", txtInp("tr_lang", t["语种"])) +
      fieldRow("训练家类型", ttCtrl) +
      fieldRow("服装编号", numInp("tr_outfit", t["服装编号"])) +
      fieldRow("已有图鉴", selInp("tr_dex", t["已获得图鉴"] ? 1 : 0,
                                  [["否", 0], ["是", 1]])) +
      `<div class="sub-h">徽章（按存档实际个数，共 ${badges.length}）</div>` +
      `<div class="mini-row">` + badges.map((on, i) =>
        `<button class="btn${on ? " primary" : ""}" data-badge="${i}">徽章 ${i + 1}</button>`
      ).join("") + `</div>` +
      `<div class="sub-h">图鉴</div>` +
      `<div class="mini-row">` +
        `<button class="btn" id="btnDexSeen">已见全开</button>` +
        `<button class="btn" id="btnDexCaught">已捕获全开</button>` +
        `<button class="btn ghost" id="btnDexClear">清空已见</button>` +
        `<button class="btn ghost" id="btnForms">形态图鉴全开</button>` +
      `</div>` +
      `<div class="hint" style="margin-top:8px">已见 ${t["图鉴已见数"]} · ` +
      `已捕获 ${t["图鉴已捕获数"]}</div>` +
      `<div class="btns" style="margin-top:12px">` +
      `<button class="btn primary" id="btnTrainerApply">应用主角修改</button></div>`;

    // 当前训练家类型：有数据才预置编号，没数据留空（见上面的说明）
    $("tr_tt").dataset.id = ttypes.length ? (t["训练家类型ID"] ?? "") : "";
    $("tr_tt").addEventListener("click", () => {
      openPicker("trainer_type", t["训练家类型ID"], (id, label) => {
        $("tr_tt").querySelector(".val").textContent = label;
        $("tr_tt").dataset.id = id;
      });
    });

    $("btnTrainerApply").addEventListener("click", async () => {
      const fields = {
        name: val("tr_name"),
        money: numOr("tr_money", 0),
        id: numOr("tr_id", 0),
        outfit: numOr("tr_outfit", 0),
        pokedex: numOr("tr_dex", 0) ? true : false,
      };
      const lang = val("tr_lang").trim();
      if (lang !== "") {
        const n = parseInt(lang, 10);
        fields.language = isNaN(n) ? 2 : n;   // 语种存的是数字；非数字给 2
      }
      const ttId = $("tr_tt").dataset.id;
      if (ttId !== "" && ttId !== undefined && ttId !== null) {
        fields.trainertype = ttId;            // 数字或内部名，后端 core 都认
      }
      const rr = await API("/api/save/set_trainer", {
        path: $("savePath").value.trim(),
        game_root: $("saveRoot").value.trim() || undefined,
        fields,
      });
      toast(rr.ok ? "已改（记得点「写回存档」）" : rr.message, 3200);
      if (rr.ok) viewTrainer(body);
    });

    body.querySelectorAll("button[data-badge]").forEach((b) => {
      b.addEventListener("click", async () => {
        const i = +b.dataset.badge;
        const rr = await API("/api/save/set_badge", {
          path: $("savePath").value.trim(),
          game_root: $("saveRoot").value.trim() || undefined,
          index: i, on: !b.classList.contains("primary"),
        });
        if (rr.ok) viewTrainer(body); else toast(rr.message);
      });
    });

    const dexBtn = (which, value, id) => {
      $(id).addEventListener("click", async () => {
        const rr = await API("/api/save/set_dex", {
          path: $("savePath").value.trim(),
          game_root: $("saveRoot").value.trim() || undefined,
          which, all: true, value,
        });
        toast(rr.ok ? "已设置（记得写回）" : rr.message, 2400);
        if (rr.ok) viewTrainer(body);
      });
    };
    dexBtn("seen", true, "btnDexSeen");
    dexBtn("caught", true, "btnDexCaught");
    dexBtn("seen", false, "btnDexClear");
    $("btnForms").addEventListener("click", async () => {
      const rr = await API("/api/save/unlock_forms", {
        path: $("savePath").value.trim(),
        game_root: $("saveRoot").value.trim() || undefined,
      });
      toast(rr.ok ? ("已开 " + rr.data.unlocked + " 条形态图鉴") : rr.message, 2600);
      if (rr.ok) viewTrainer(body);
    });
  }

  // ------------------------------------------------------------
  // 宝可梦编辑（同行 / 箱子共用）
  // ------------------------------------------------------------
  function pokeCardHtml(p) {
    const sp = p["宝可梦"] || "?";
    const nick = p["昵称"] || sp;
    const lv = p["等级"] != null ? p["等级"] : "?";
    const shiny = p["异色"] ? `<span class="tag warn">异色</span>` : "";
    const same = p["相同与否"] === "已改名" ? `<span class="tag off">已改名</span>` : "";
    return `<div class="poke-card" data-slot="${esc(p.slot)}">
      <div class="t"><span class="nm">${esc(nick)}</span>
      <span class="sub">${esc(p.slot)}</span></div>
      <div class="ln">${esc(sp)} · Lv.${esc(lv)} · ${esc(p["性格"] || "?")} · ${esc(p["特性"] || "?")}</div>
      <div class="ln">${shiny}${same}招式：${esc(p["招式文本"] || "（无）")}</div>
    </div>`;
  }

  async function renderPokeEditor(body, where, onBack, rerender) {
    body.innerHTML = `<div class="hint">读取中…</div>`;
    const args = saveArgs() + "&where=" + encodeURIComponent(where);
    const pr = await API("/api/save/pokemon?" + args);
    if (!pr.ok) { body.innerHTML = `<div class="hint err">${esc(pr.message)}</div>`; return; }
    const p = pr.data.pokemon || {};
    const sid = p["全国图鉴编号"];
    let speciesName = p["宝可梦"] || "?";
    let speciesId = sid;
    const curNick = p["昵称"] || "";

    const ivs = p["个体值IV"] || {};
    const evs = p["努力值EV"] || {};
    const moves = p["招式"] || [];
    const moveCells = [];
    for (let i = 0; i < 4; i++) {
      const m = moves[i] || {};
      moveCells.push(
        fieldRow("招式" + (i + 1),
          pickBtn("pe_mv" + i, m["招式"] != null ? m["招式"] : "（空）") +
          `<input id="pe_pp${i}" class="inp" style="flex:0 0 62px" type="number"` +
          ` inputmode="numeric" placeholder="PP" value="${m["PP"] != null ? esc(m["PP"]) : ""}">`));
    }
    const ivCells = STAT6.map((k, i) =>
      `<div class="cell"><div class="lb">${esc(k)}</div>` +
      numInp("pe_iv" + i, ivs[k]) + `</div>`).join("");
    const evCells = STAT6.map((k, i) =>
      `<div class="cell"><div class="lb">${esc(k)}</div>` +
      numInp("pe_ev" + i, evs[k]) + `</div>`).join("");

    body.innerHTML =
      `<div class="card-h">编辑宝可梦<span class="sub">${esc(where)}</span></div>` +
      fieldRow("昵称", txtInp("pe_nick", curNick)) +
      fieldRow("种族", pickBtn("pe_sp", speciesName)) +
      fieldRow("形态", numInp("pe_form", p["形态"] || 0)) +
      fieldRow("等级", numInp("pe_level", p["等级"])) +
      fieldRow("经验", numInp("pe_exp", p["经验值"])) +
      fieldRow("性格", pickBtn("pe_nat", p["性格"] || "（未设）")) +
      fieldRow("特性", pickBtn("pe_ab", p["特性"] || "（未设）")) +
      fieldRow("当前HP", numInp("pe_hp", p["HP"] ? String(p["HP"]).split("/")[0] : 0) +
                        `<button class="btn mini" id="pe_hpfull" style="flex:0 0 auto;min-width:0">回满</button>`) +
      fieldRow("状态", pickBtn("pe_st", p["状态"] || "正常")) +
      `<div class="sub-h">个体值 IV（0–31）
        <button class="mini" id="pe_iv31" style="float:right">全 31</button></div>` +
      `<div class="grid6">${ivCells}</div>` +
      `<div class="sub-h">努力值 EV（0–252，总和 ≤510）
        <button class="mini" id="pe_ev0" style="float:right">清空</button></div>` +
      `<div class="grid6">${evCells}</div>` +
      `<div class="sub-h">招式（最多 4；PP 留空＝用默认）</div>` + moveCells.join("") +
      `<div class="sub-h">其它</div>` +
      fieldRow("携带道具", pickBtn("pe_item", p["携带道具"] || "（无）")) +
      fieldRow("捕获用球", pickBtn("pe_ball", p["捕获用球"] || "（未知）")) +
      fieldRow("亲密度", numInp("pe_happy", p["亲密度"] || 0)) +
      fieldRow("孵蛋步数", numInp("pe_egg", p["孵蛋步数"] || 0)) +
      fieldRow("异色", selInp("pe_shiny",
                             p["异色"] === true ? "yes" : (p["异色"] === false ? "no" : "auto"),
                             [["自动（按个体ID算）", "auto"], ["是", "yes"], ["否", "no"]])) +
      fieldRow("勋章", txtInp("pe_ribbons", Array.isArray(p["勋章"]) ? p["勋章"].join(",") : (p["勋章"] || ""))) +
      fieldRow("初训家", txtInp("pe_ot", p["初训家"])) +
      fieldRow("训练家ID", numInp("pe_tid", p["训练家ID"])) +
      fieldRow("个体ID", numInp("pe_pid", p["个体ID"])) +
      `<div class="btns" style="margin-top:12px">
        <button class="btn primary" id="pe_apply">应用修改</button>
        <button class="btn ghost" id="pe_back">← 返回</button>
      </div>`;

    $("pe_back").addEventListener("click", () => onBack(body));
    $("pe_hpfull").addEventListener("click", () => {
      const hp = p["HP"] ? String(p["HP"]).split("/")[1] : "0";
      $("pe_hp").value = hp;
    });
    $("pe_iv31").addEventListener("click", () => STAT6.forEach((_, i) => $("pe_iv" + i).value = 31));
    $("pe_ev0").addEventListener("click", () => STAT6.forEach((_, i) => $("pe_ev" + i).value = 0));
    // ★ 记住当前取值：用户没动过时，apply 要写回原值而不是 0
    $("pe_item").dataset.id = p["携带道具ID"] || 0;
    $("pe_ball").dataset.id = p["捕获用球ID"] || 0;
    $("pe_nat").dataset.id = p["性格"] == null ? 0 : natIndex(p);
    $("pe_ab").dataset.id = p["特性序号"] == null ? 0 : p["特性序号"];
    $("pe_st").dataset.id = statusCode(p["状态"]);

    // 性格 / 特性 / 状态：都可手输（内部名 HARDY / ANALYTIC / SLEEP…，或编号）
    $("pe_nat").addEventListener("click", () => {
      openPicker("nature", Number($("pe_nat").dataset.id), (id, label) => {
        $("pe_nat").querySelector(".val").textContent = label;
        $("pe_nat").dataset.id = id;
      });
    });
    $("pe_ab").addEventListener("click", () => {
      openPicker("ability", Number($("pe_ab").dataset.id), (id, label) => {
        $("pe_ab").querySelector(".val").textContent = label;
        $("pe_ab").dataset.id = id;
      }, where);
    });
    $("pe_st").addEventListener("click", () => {
      openPicker("status", Number($("pe_st").dataset.id), (id, label) => {
        $("pe_st").querySelector(".val").textContent = label;
        $("pe_st").dataset.id = id;
      });
    });

    // 种族选择：改了就同步昵称（与电脑版一致）
    $("pe_sp").addEventListener("click", () => {
      openPicker("species", speciesId, (id, label) => {
        const oldName = speciesName;
        speciesId = id;
        speciesName = label;
        $("pe_sp").querySelector(".val").textContent = label;
        const nickEl = $("pe_nick");
        if (nickEl.value.trim() === "" || nickEl.value.trim() === oldName) {
          nickEl.value = label;
        }
      });
    });
    $("pe_item").addEventListener("click", () => {
      openPicker("item", p["携带道具ID"] || 0, (id, label) => {
        $("pe_item").querySelector(".val").textContent = label;
        $("pe_item").dataset.id = id;
      });
    });
    $("pe_ball").addEventListener("click", () => {
      openPicker("item", 0, (id, label) => {
        $("pe_ball").querySelector(".val").textContent = label;
        $("pe_ball").dataset.id = id;
      });
    });
    for (let i = 0; i < 4; i++) {
      const m = moves[i] || {};
      $("pe_mv" + i).dataset.id = (m["招式ID"] != null ? m["招式ID"] : 0);
      $("pe_mv" + i).addEventListener("click", ((idx, cur) => () => {
        openPicker("move", cur, (id, label) => {
          $("pe_mv" + idx).querySelector(".val").textContent = label;
          $("pe_mv" + idx).dataset.id = id;
        });
      })(i, m["招式ID"] || 0));
    }

    $("pe_apply").addEventListener("click", async () => {
      const base = { path: $("savePath").value.trim(),
                     game_root: $("saveRoot").value.trim() || undefined,
                     where };
      const set = (key, value, recalc) =>
        API("/api/save/set_pokemon", Object.assign({}, base,
          { key, value, recalc: recalc !== false }));
      try {
        let r = await set("种族", speciesId, false);
        if (!r.ok) return toast(r.message, 3400);
        r = await set("昵称", val("pe_nick"), false);
        if (!r.ok) return toast(r.message, 3400);
        await set("形态", numOr("pe_form", 0), false);
        await set("等级", numOr("pe_level", 1), false);
        await set("个体值", STAT6.map((_, i) => numOr("pe_iv" + i, 0)), false);
        await set("努力值", STAT6.map((_, i) => numOr("pe_ev" + i, 0)), false);
        await set("性格", $("pe_nat").dataset.id, false);
        await set("特性", $("pe_ab").dataset.id, true);
        const boxes = [];
        for (let i = 0; i < 4; i++) {
          const mid = $("pe_mv" + i).dataset.id;
          boxes.push([(mid === "" || mid == null) ? 0 : mid,
                      val("pe_pp" + i).trim() === "" ? null : numOr("pe_pp" + i, null)]);
        }
        await API("/api/save/set_moves", Object.assign({}, base, { moves: boxes }));
        await set("携带道具", $("pe_item").dataset.id || 0, false);
        await set("捕获用球", $("pe_ball").dataset.id || 0, false);
        await set("亲密度", numOr("pe_happy", 0), false);
        await set("孵蛋步数", numOr("pe_egg", 0), false);
        const stv = $("pe_st").dataset.id;
        await set("状态", (stv === "" || stv == null) ? 0 : stv, false);
        await set("异色", val("pe_shiny") === "auto" ? null : (val("pe_shiny") === "yes"), false);
        await set("勋章", val("pe_ribbons"), false);
        await set("初训家", val("pe_ot"), false);
        await set("训练家ID", numOr("pe_tid", 0), false);
        await set("个体ID", numOr("pe_pid", 0), false);
        await API("/api/save/recalc", base);
        const hp = numOr("pe_hp", null);
        if (hp !== null) await set("当前HP", hp, false);
        toast("已改（记得点「写回存档」）", 2600);
        if (rerender) rerender();
        else renderPokeEditor(body, where, onBack);
      } catch (e) {
        toast("写入出错：" + e.message, 3200);
      }
    });
  }

  function natIndex(p) {
    // 后端「性格」返回的是显示名，这里按 NATURES 顺序反查编号
    const NAT = ["勤奋", "怕寂寞", "勇敢", "固执", "调皮", "大胆", "坦率",
      "悠闲", "淘气", "乐天", "胆小", "急躁", "认真", "爽朗", "天真",
      "内敛", "慢吞吞", "冷静", "害羞", "马虎", "温顺", "温和", "狂妄",
      "慎重", "浮躁"];
    const i = NAT.indexOf(p["性格"]);
    return i >= 0 ? i : 0;
  }
  function statusCode(name) {
    const M = { "正常": 0, "睡眠": 1, "中毒": 2, "灼伤": 3, "冰冻": 4, "麻痹": 5, "濒死": 6 };
    return M[name] != null ? M[name] : 0;
  }

  // ------------------------------------------------------------
  // 同行
  // ------------------------------------------------------------
  async function viewParty(body) {
    const r = await API("/api/save/party?" + saveArgs());
    if (!r.ok) { body.innerHTML = `<div class="hint err">${esc(r.message)}</div>`; return; }
    const list = (r.data.party || []).filter((p) => !p.empty);
    if (!list.length) { body.innerHTML = `<div class="hint">同行队伍是空的</div>`; return; }
    body.innerHTML = `<div class="card-h">同行队伍（${list.length}）</div>` +
      `<div class="hint" style="margin-bottom:8px">点一只进入编辑</div>` +
      list.map(pokeCardHtml).join("");
    body.querySelectorAll(".poke-card").forEach((el) => {
      el.addEventListener("click", () => renderPartyPokeEditor(body, el.dataset.slot));
    });
  }

  // 同行宝可梦编辑：在通用编辑器上补「复制一只 / 移入 PC / 移出队伍」
  async function renderPartyPokeEditor(body, where) {
    await renderPokeEditor(body, where, viewParty,
                           () => renderPartyPokeEditor(body, where));
    const btns = body.querySelector(".btns");
    if (!btns) return;
    const idx = Number(where.split(":")[1]);
    const mk = (cls, id, text) => {
      const b = document.createElement("button");
      b.className = "btn " + cls; b.id = id; b.textContent = text;
      btns.appendChild(b); return b;
    };
    const base = () => ({
      path: $("savePath").value.trim(),
      game_root: $("saveRoot").value.trim() || undefined,
    });
    mk("", "pp_clone", "复制一只").addEventListener("click", async () => {
      const rr = await API("/api/save/clone", Object.assign(base(), {
        where, to: "party",
      }));
      toast(rr.ok ? "已复制到队伍" : rr.message);
      if (rr.ok) viewParty(body);
    });
    mk("ghost", "pp_tobox", "移入 PC").addEventListener("click", async () => {
      const rr = await API("/api/save/move", Object.assign(base(), {
        op: "party_to_box", index: idx, box_index: 0,
      }));
      toast(rr.ok ? "已移入 PC 箱子 1" : rr.message);
      if (rr.ok) viewParty(body);
    });
    mk("danger", "pp_remove", "移出队伍").addEventListener("click", async () => {
      if (!await confirmBox("移出队伍",
        "把这只从队伍移除（不写回存档前可反悔）。", "确认移出", true)) return;
      const rr = await API("/api/save/move", Object.assign(base(), {
        op: "remove_party", index: idx,
      }));
      toast(rr.ok ? "已移出队伍" : rr.message);
      if (rr.ok) viewParty(body);
    });
  }

  // ------------------------------------------------------------
  // PC 箱子
  // ------------------------------------------------------------
  async function viewBoxes(body) {
    const r = await API("/api/save/boxes?" + saveArgs());
    if (!r.ok) { body.innerHTML = `<div class="hint err">${esc(r.message)}</div>`; return; }
    const boxes = r.data.boxes || [];
    body.innerHTML = `<div class="card-h">PC 箱子</div>` +
      kv([["盒子总数", boxes.length]]) +
      `<div class="hint" style="margin-top:6px">点一个箱子看里面的宝可梦：</div>` +
      boxes.map((b, i) =>
        `<div class="item" data-box="${i}"><span class="grow">箱子 ${i + 1}</span>` +
        `<span class="sub">${b.count} 格</span></div>`).join("");
    body.querySelectorAll("[data-box]").forEach((el) => {
      el.addEventListener("click", () => viewBoxSlots(body, +el.dataset.box));
    });
  }

  async function viewBoxSlots(body, bi) {
    const r = await API("/api/save/boxes?" + saveArgs() + "&box=" + bi);
    if (!r.ok) return toast(r.message);
    const slots = (r.data.box.slots || []).filter((p) => !p.empty);
    body.innerHTML = `<div class="card-h">箱子 ${bi + 1}</div>` +
      `<div class="mini-row" style="margin-bottom:8px">` +
      `<button class="btn ghost" id="bx_rename">改箱名</button></div>` +
      (slots.length
        ? `<div class="hint" style="margin-bottom:8px">点一只进入编辑</div>` +
          slots.map(pokeCardHtml).join("")
        : `<div class="hint">这个箱子是空的</div>`) +
      `<div class="btns" style="margin-top:10px">` +
      `<button class="btn ghost" id="bx_back">← 返回箱子列表</button></div>`;
    $("bx_back").addEventListener("click", () => viewBoxes(body));
    $("bx_rename").addEventListener("click", async () => {
      const nm = await askBox("改箱名", `箱子 ${bi + 1} 的新名字：`, "");
      if (nm === null) return;
      const rr = await API("/api/save/move", {
        path: $("savePath").value.trim(),
        game_root: $("saveRoot").value.trim() || undefined,
        op: "rename_box", box_index: bi, name: nm,
      });
      toast(rr.ok ? "已改箱名" : rr.message);
    });
    body.querySelectorAll(".poke-card").forEach((el) => {
      el.addEventListener("click", () => renderBoxPokeEditor(body, el.dataset.slot, bi));
    });
  }

  // 箱子里的宝可梦编辑：在通用编辑器上补「移入队伍 / 复制 / 清空」按钮
  async function renderBoxPokeEditor(body, where, bi) {
    await renderPokeEditor(body, where, () => viewBoxSlots(body, bi),
                           () => renderBoxPokeEditor(body, where, bi));
    const btns = body.querySelector(".btns");
    if (!btns) return;
    const part = where.split(":");   // box:bi:slot
    const slot = part[2];
    const mk = (cls, id, text) => {
      const b = document.createElement("button");
      b.className = "btn " + cls; b.id = id; b.textContent = text;
      btns.appendChild(b); return b;
    };
    mk("", "bp2party", "移入队伍").addEventListener("click", async () => {
      const rr = await API("/api/save/move", Object.assign({}, {
        path: $("savePath").value.trim(),
        game_root: $("saveRoot").value.trim() || undefined,
        op: "box_to_party", box_index: bi, slot: Number(slot),
      }));
      toast(rr.ok ? "已移入队伍" : rr.message);
      if (rr.ok) viewBoxSlots(body, bi);
    });
    mk("ghost", "bp2clone", "复制一只").addEventListener("click", async () => {
      const rr = await API("/api/save/clone", Object.assign({}, {
        path: $("savePath").value.trim(),
        game_root: $("saveRoot").value.trim() || undefined,
        where, to: "box", box_index: bi,
      }));
      toast(rr.ok ? "已复制到空位" : rr.message);
      if (rr.ok) viewBoxSlots(body, bi);
    });
    mk("danger", "bp2clear", "清空该格").addEventListener("click", async () => {
      if (!await confirmBox("清空该格", "这一格的宝可梦会被删掉（不可撤销，需自己写回存档）。",
                            "确认清空", true)) return;
      const rr = await API("/api/save/move", Object.assign({}, {
        path: $("savePath").value.trim(),
        game_root: $("saveRoot").value.trim() || undefined,
        op: "remove_box", box_index: bi, slot: Number(slot),
      }));
      toast(rr.ok ? "已清空" : rr.message);
      if (rr.ok) viewBoxSlots(body, bi);
    });
  }

  // ------------------------------------------------------------
  // 背包
  // ------------------------------------------------------------
  async function viewBag(body) {
    const r = await API("/api/save/bag?" + saveArgs());
    if (!r.ok) { body.innerHTML = `<div class="hint err">${esc(r.message)}</div>`; return; }
    const bag = r.data.bag || {};
    const pockets = bag["口袋"] || [];
    body.innerHTML = `<div class="card-h">背包</div>` +
      kv([["登记道具", bag["登记道具"] || "（无）"]]) +
      (pockets.length
        ? `<div class="hint" style="margin-top:6px">点一个口袋编辑：</div>` +
          pockets.map((p) =>
            `<div class="item" data-pocket="${p["口袋编号"]}">` +
            `<span class="grow">${esc(p["口袋名称"])}</span>` +
            `<span class="sub">${p["物品数"]} 种</span></div>`).join("")
        : `<div class="hint">背包是空的</div>`) +
      `<div class="btns" style="margin-top:10px">` +
      `<button class="btn ghost" id="bagReg">设置登记道具</button></div>`;
    body.querySelectorAll("[data-pocket]").forEach((el) => {
      el.addEventListener("click", () => viewPocket(body, +el.dataset.pocket));
    });
    $("bagReg").addEventListener("click", () => {
      openPicker("item", bag["登记道具ID"] || 0, async (id) => {
        const rr = await API("/api/save/set_registered_item", {
          path: $("savePath").value.trim(),
          game_root: $("saveRoot").value.trim() || undefined, item_id: id,
        });
        toast(rr.ok ? "已设置登记道具" : rr.message);
        if (rr.ok) viewBag(body);
      });
    });
  }

  async function viewPocket(body, pi) {
    const r = await API("/api/save/pocket?" + saveArgs() + "&index=" + pi);
    if (!r.ok) return toast(r.message);
    const rows = r.data.pocket || [];        // [{item_id, count, name}, ...]
    const pname = r.data.pocket_name || ("口袋 #" + pi);
    body.innerHTML = `<div class="card-h">${esc(pname)}</div>` +
      (rows.length ? rows.map((row, i) =>
        `<div class="item"><span class="grow">${esc(row.name || ("#" + row.item_id))}` +
        `<div class="sub">#${row.item_id}</div></span>` +
        `<span class="sub">×${row.count}</span>` +
        `<button class="mini" data-ei="${i}">改</button>` +
        `<button class="mini" data-di="${i}">删</button></div>`).join("")
        : `<div class="hint">这个口袋是空的</div>`) +
      `<div class="mini-row" style="margin-top:10px">` +
      `<button class="btn" id="pk_add">添加道具</button>` +
      `<button class="btn ghost" id="pk_fill">全部补满 999</button></div>` +
      `<div class="btns" style="margin-top:10px">` +
      `<button class="btn ghost" id="pk_back">← 返回背包</button></div>`;

    $("pk_back").addEventListener("click", () => viewBag(body));
    $("pk_fill").addEventListener("click", async () => {
      const rr = await API("/api/save/fill_pocket", {
        path: $("savePath").value.trim(),
        game_root: $("saveRoot").value.trim() || undefined,
        pocket_index: pi, count: 999,
      });
      toast(rr.ok ? ("已补满 " + rr.data.filled + " 种") : rr.message);
      if (rr.ok) viewPocket(body, pi);
    });
    $("pk_add").addEventListener("click", () => {
      openPicker("item", 0, async (id) => {
        const cnt = await askBox("数量", "给多少？（默认 1）", "1");
        if (cnt === null) return;
        const rr = await API("/api/save/set_bag_item", {
          path: $("savePath").value.trim(),
          game_root: $("saveRoot").value.trim() || undefined,
          pocket_index: pi, item_id: id, count: parseInt(cnt, 10) || 1,
        });
        toast(rr.ok ? "已添加" : rr.message);
        if (rr.ok) viewPocket(body, pi);
      });
    });
    body.querySelectorAll("[data-ei]").forEach((b) => {
      b.addEventListener("click", async () => {
        const i = +b.dataset.ei;
        const cnt = await askBox("改数量", (rows[i].name || "") + " 的数量：", String(rows[i].count));
        if (cnt === null) return;
        const rr = await API("/api/save/set_bag_item", {
          path: $("savePath").value.trim(),
          game_root: $("saveRoot").value.trim() || undefined,
          pocket_index: pi, item_id: rows[i].item_id, count: parseInt(cnt, 10) || 0,
        });
        toast(rr.ok ? "已改数量" : rr.message);
        if (rr.ok) viewPocket(body, pi);
      });
    });
    body.querySelectorAll("[data-di]").forEach((b) => {
      b.addEventListener("click", async () => {
        if (!await confirmBox("删除道具", "把这个道具从口袋删掉？", "删除", true)) return;
        const rr = await API("/api/save/remove_bag_index", {
          path: $("savePath").value.trim(),
          game_root: $("saveRoot").value.trim() || undefined,
          pocket_index: pi, i: Number(b.dataset.di),
        });
        toast(rr.ok ? "已删除" : rr.message);
        if (rr.ok) viewPocket(body, pi);
      });
    });
  }

  // ------------------------------------------------------------
  // 开关 / 变量
  // ------------------------------------------------------------
  async function viewVars(body) {
    const s = await API("/api/save/switches?" + saveArgs());
    const v = await API("/api/save/variables?" + saveArgs());
    if (!s.ok) { body.innerHTML = `<div class="hint err">${esc(s.message)}</div>`; return; }
    const sw = s.data.switches || [];
    const vr = (v.ok && v.data.variables) || [];
    body.innerHTML = `<div class="card-h">开关 / 变量</div>` +
      kv([["开关数量", sw.length], ["变量数量", vr.length]]) +
      `<div class="btns" style="margin-top:10px">` +
      `<button class="btn ghost" id="btnSetSw">改开关</button>` +
      `<button class="btn ghost" id="btnSetVar">改变量</button></div>`;

    const setter = (endpoint) => async () => {
      const i = await askBox("索引", "第几号？（从 0 开始）", "0");
      if (i === null) return;
      const value = await askBox("值", "值是多少？（开关填 true/false，变量填数字）", "");
      if (value === null) return;
      const rr = await API(endpoint, {
        path: $("savePath").value.trim(),
        game_root: $("saveRoot").value.trim() || undefined,
        index: Number(i), value,
      });
      toast(rr.ok ? "已改（记得点写回存档）" : rr.message);
    };
    $("btnSetSw").addEventListener("click", setter("/api/save/set_switch"));
    $("btnSetVar").addEventListener("click", setter("/api/save/set_variable"));
  }

  $("btnOpenSave").addEventListener("click", openSave);

  $("btnSaveWrite").addEventListener("click", async () => {
    const path = $("savePath").value.trim();
    if (!path) return toast("还没打开存档");
    if (!await confirmBox("写回存档",
      "会覆盖原文件（首次自动备份 .bak）。\n<span class=\"warn\">建议先用副本试。</span>",
      "确认写入", true)) return;
    const r = await API("/api/save/write", {
      path, game_root: $("saveRoot").value.trim() || undefined,
    });
    toast(r.ok ? "已写入：" + r.data.written_to : r.message, 3200);
  });

  // ------------------------------------------------------------
  // 问题反馈：诊断报告
  // ------------------------------------------------------------
  // Android 侧（MainActivity）在任何失败时都会写诊断文件，
  // 通过 /api/fs/read 把文本读出来，用户复制给作者即可。
  $("btnDiag").addEventListener("click", async () => {
    const box = $("diagOut");
    box.style.display = "block";
    box.textContent = "读取中…";
    const r = await API("/api/fs/read?path=" + encodeURIComponent("diagnostics.txt"));
    if (!r.ok) {
      // 没崩过就没有文件，给一份能手动填的基础信息
      const h = await API("/api/health");
      const d = (h && h.data) || {};
      box.textContent =
        "（App 侧没有崩溃记录，说明没有崩溃到留下现场的程度）\n\n" +
        "请手动附上以下信息：\n" +
        "· 手机型号与系统版本\n" +
        "· 打开后是「闪退」还是「白屏」还是「一直转圈」\n" +
        "· Python 版本：" + (d.python || "?") + "\n";
      return;
    }
    box.textContent = r.data.text || "（报告是空的）";
    // 复制到剪贴板，WebView 里用 execCommand 最省事
    try {
      const ta = document.createElement("textarea");
      ta.value = box.textContent;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      toast("诊断报告已复制，粘贴给作者即可", 3000);
    } catch (e) {
      toast("自动复制失败，请长按上方文字手动复制");
    }
  });

  $("btnClearCrash").addEventListener("click", async () => {
    if (!await confirmBox("清除崩溃记录",
      "下次再崩溃会重新记录。这不影响工具功能，只是清理旧现场。",
      "清除")) return;
    const r = await API("/api/fs/write",
      { path: "diagnostics.txt", text: "" });
    toast(r.ok ? "已清除" : r.message);
  });

  // ------------------------------------------------------------
  // 启动时恢复上次选的游戏主程序（旧版本存的是游戏根目录，也兼容读一次）
  // ------------------------------------------------------------
  try {
    const savedExe = localStorage.getItem(EXE_KEY);
    // 旧 key（pkmn.gameDir）存的是「游戏根目录」—— 不是 exe，不能直接塞进
    // 主程序输入框，单独走一次「按目录校验」。
    const oldDir = localStorage.getItem("pkmn.gameDir") || "";
    if (savedExe) {
      $("gameExe").value = savedExe;
      refreshGameInfo();
    } else if (oldDir) {
      (async () => {
        const r = await API("/api/fs/check_game?dir=" + encodeURIComponent(oldDir));
        if (r.ok && r.data.valid) {
          gameRoot = r.data.dir || oldDir;
          $("gameInfo").innerHTML = kv([
            ["识别结果", "通过", "on"],
            ["游戏根目录", gameRoot],
            ["说明", r.data.reason],
          ]);
          if (!$("saveRoot").value.trim()) {
            $("saveRoot").value = gameRoot;
            $("saveRoot").dataset.auto = "1";
          }
          loadDebugStatus();
        }
        loadOwState();
      })();
    }
  } catch (e) {}

  // ------------------------------------------------------------
  // PBS 编辑
  //   · 右侧「三个动作」= 提取 / 编译
  //   · 文件列表 → 点一个文件 → 选条目 → 改字段（每个字段下面带中文说明）
  //   ★ v16/v17/v18 老游戏的「编译」= 标记待重编译（游戏启动时自己重建 .dat）
  // ------------------------------------------------------------
  const pbs = { dir: "", family: "", legacy: false, path: "", rows: [],
                idx: 0, name: "", query: "", vis: [] };

  function pbsInfo(html) { $("pbsInfo").innerHTML = html; }
  function pbsLog(html) { $("pbsLog").innerHTML = html; }

  async function loadPbs() {
    const dir = gameDir();
    if (!dir) {
      pbsInfo("还没选择游戏主程序（先在上面点「浏览」选 Game.exe）");
      return;
    }
    const r = await API("/api/pbs/list?dir=" + encodeURIComponent(dir));
    if (!r.ok) { pbsInfo("读取失败：" + r.message); return; }
    pbs.dir = r.data.dir;
    pbs.family = r.data.family || "";
    pbs.legacy = !!r.data.legacy;
    if (!pbs.family) {
      pbsInfo("认不出版本：" + (r.data.why || ""));
      renderPbsFiles([]);
      return;
    }
    pbsInfo(kv([
      ["游戏根目录", pbs.dir],
      ["版本族", pbs.family, "on"],
      ["PBS 目录", r.data.pbs_exists ? "已就绪" : "还没有",
       r.data.pbs_exists ? "on" : "off"],
      ["编译方式", pbs.legacy
        ? "标记待重编译（游戏启动时自己重建 .dat）"
        : "直接写回 Data/*.dat", pbs.legacy ? "warn" : "on"],
    ]));
    renderPbsFiles(r.data.files || []);
  }

  function renderPbsFiles(files) {
    const box = $("pbsFiles");
    if (!files.length) {
      box.innerHTML = '<div class="hint">PBS 文件夹还是空的，先点「提取 PBS」。</div>';
      return;
    }
    box.innerHTML = "";
    files.forEach((f) => {
      const b = document.createElement("button");
      b.className = "btn ghost pbs-file";
      b.textContent = f.name;
      b.addEventListener("click", () => openPbsFile(f));
      box.appendChild(b);
    });
  }

  async function openPbsFile(f) {
    const path = (pbs.dir.replace(/[\\/]+$/, "")) + "/PBS/" + f.file;
    const r = await API("/api/pbs/read?dir=" + encodeURIComponent(pbs.dir)
      + "&path=" + encodeURIComponent(path));
    if (!r.ok) { toast("打开失败：" + r.message); return; }
    pbs.path = path;
    pbs.rows = (r.data.rows || []).map((row) => ({
      sid: row.sid, label: row.label,
      fields: row.fields.map((x) => ({ ...x })),
    }));
    pbs.idx = 0;
    pbs.query = "";
    const sbox = $("pbsSearch");
    if (sbox) sbox.value = "";
    pbs.name = r.data.name || f.name;
    $("pbsEditCard").style.display = "";
    $("pbsSaveBar").style.display = "";
    $("pbsEditTitle").textContent = r.data.name + "（" + r.data.file + "）";
    $("pbsHint").innerHTML = (r.data.hint || "")
      + (r.data.truncated ? "<br><b>条目太多，手机版只载入前 3000 条。</b>" : "");
    renderPbsEntries();
    renderPbsFields();
    $("pbsEditCard").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* 列表上方搜索：按 名字 / 内部名 / 任意字段内容 过滤条目 */
  function pbsRowMatches(row, q) {
    if (!q) return true;
    if ((row.label || "").toLowerCase().includes(q)) return true;
    if ((row.sid || "").toLowerCase().includes(q)) return true;
    return (row.fields || []).some((f) =>
      (f.key || "").toLowerCase().includes(q)
      || String(f.value == null ? "" : f.value).toLowerCase().includes(q));
  }

  function renderPbsEntries() {
    const q = (pbs.query || "").trim().toLowerCase();
    const sel = $("pbsEntry");
    const old = pbs.idx;
    sel.innerHTML = "";
    pbs.vis = [];
    pbs.rows.forEach((row, i) => {
      if (!pbsRowMatches(row, q)) return;
      const o = document.createElement("option");
      o.value = String(i);
      o.textContent = row.label || row.sid || ("#" + (i + 1));
      sel.appendChild(o);
      pbs.vis.push(i);
    });
    if (!pbs.vis.length) {
      const o = document.createElement("option");
      o.value = "0";
      o.textContent = "（没有匹配的条目）";
      sel.appendChild(o);
      $("pbsSearchInfo").textContent = q
        ? ("搜索「" + pbs.query + "」：命中 0 / " + pbs.rows.length + " 条")
        : "";
      return;
    }
    if (pbs.vis.indexOf(old) < 0) pbs.idx = pbs.vis[0];
    sel.value = String(pbs.idx);
    $("pbsSearchInfo").textContent = q
      ? ("搜索「" + pbs.query + "」：命中 " + pbs.vis.length
         + " / " + pbs.rows.length + " 条")
      : ("共 " + pbs.rows.length + " 条");
  }

  function renderPbsFields() {
    const row = pbs.rows[pbs.idx];
    const box = $("pbsFields");
    box.innerHTML = "";
    if (!row) return;
    row.fields.forEach((f, i) => {
      const wrap = document.createElement("div");
      wrap.className = "pbs-field";
      const lab = document.createElement("div");
      lab.className = "pbs-label";
      lab.textContent = f.key;
      const inp = document.createElement("input");
      inp.className = "inp";
      inp.value = f.value;
      inp.addEventListener("input", () => { f.value = inp.value; });
      wrap.appendChild(lab);
      wrap.appendChild(inp);
      if (f.desc) {
        const d = document.createElement("div");
        d.className = "pbs-desc";
        d.textContent = f.desc;
        wrap.appendChild(d);
      }
      box.appendChild(wrap);
    });
  }

  function pbsGo(delta) {
    const order = (pbs.vis && pbs.vis.length) ? pbs.vis : null;
    if (order) {
      let at = order.indexOf(pbs.idx);
      if (at < 0) at = 0;
      at = Math.max(0, Math.min(order.length - 1, at + delta));
      pbs.idx = order[at];
    } else {
      if (!pbs.rows.length) return;
      pbs.idx = Math.max(0, Math.min(pbs.rows.length - 1, pbs.idx + delta));
    }
    const sel = $("pbsEntry");
    sel.value = String(pbs.idx);
    renderPbsFields();
  }

  async function savePbs() {
    if (!pbs.path) return;
    const r = await API("/api/pbs/write", {
      dir: pbs.dir, path: pbs.path, rows: pbs.rows,
    });
    toast(r.ok ? "已保存到 " + r.data.file : "保存失败：" + r.message);
    if (r.ok) pbsLog("已保存 " + r.data.file + "（" + r.data.count + " 条）");
  }

  async function pbsExtract() {
    if (!pbs.dir) { toast("先选游戏主程序"); return; }
    pbsLog("提取中…");
    const r = await API("/api/pbs/extract", { dir: pbs.dir });
    if (!r.ok) { pbsLog("提取失败：" + r.message); return; }
    const lines = (r.data.results || []).map((x) =>
      (x.ok ? "✔ " : "· ") + x.name + "  " + x.stat);
    pbsLog("提取完成：" + r.data.ok_count + " 个文件<br>"
      + lines.join("<br>").replace(/</g, "&lt;").replace(/&lt;br&gt;/g, "<br>"));
    loadPbs();
  }

  async function pbsCompile() {
    if (!pbs.dir) { toast("先选游戏主程序"); return; }
    pbsLog("编译中…");
    const r = await API("/api/pbs/compile", { dir: pbs.dir });
    if (!r.ok) { pbsLog("编译失败：" + r.message); return; }
    if (r.data.legacy) {
      pbsLog("<b>已标记待重编译</b><br>" + r.data.message
        + "<br>（v16~v18 的 .dat 由官方编译器在游戏启动时一次性重建）");
    } else {
      const lines = (r.data.results || []).map((x) =>
        (x.ok ? "✔ " : "✘ ") + x.name + "  " + x.stat);
      pbsLog("编译完成：" + r.data.ok_count + " 个<br>"
        + lines.join("<br>"));
    }
  }

  async function pbsCompileOne() {
    if (!pbs.path) return;
    const r = await API("/api/pbs/compile_one",
      { dir: pbs.dir, path: pbs.path });
    if (!r.ok) { toast("编译失败：" + r.message); return; }
    toast(r.data.legacy ? "已标记待重编译" : ("已编译 " + r.data.name));
  }

  $("btnPbsLoad").addEventListener("click", loadPbs);
  $("btnPbsExtract").addEventListener("click", pbsExtract);
  $("btnPbsCompile").addEventListener("click", pbsCompile);
  $("btnPbsSave").addEventListener("click", savePbs);
  $("btnPbsCompileOne").addEventListener("click", pbsCompileOne);
  $("btnPbsPrev").addEventListener("click", () => pbsGo(-1));
  $("btnPbsNext").addEventListener("click", () => pbsGo(1));
  $("pbsSearch").addEventListener("input", (e) => {
    pbs.query = e.target.value || "";
    renderPbsEntries();
    renderPbsFields();
  });
  $("pbsEntry").addEventListener("change", (e) => {
    pbs.idx = parseInt(e.target.value, 10) || 0;
    renderPbsFields();
  });

  loadHealth();
  loadOwState();
})();