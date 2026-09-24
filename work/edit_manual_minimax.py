# -*- coding: utf-8 -*-
"""
通过 minimax-docx CLI 将「使用手册.docx」从 v1.1.0 升级到 v1.2.0：
  - replace-text 将 v1.1.0 -> v1.2.0（标题区、页脚、主菜单示例）
  - insert-paragraph 在目录后增加两章入口
  - insert-paragraph 在第 1 章前插入「0. 升级到 v1.2.0（变更说明）」
  - insert-paragraph 在文末前插入「14. v1.2.0 新增功能详解」
每次插入都重新读取文档以定位锚点，按逆序插入保证顺序正确。
"""
import os, shutil, subprocess, zipfile, sys
import xml.etree.ElementTree as ET

IN = os.path.abspath("dist/使用手册.docx")
BAK = os.path.abspath("dist/使用手册.v1.1.0.bak.docx")
DLL = r"C:/Users/13122/.workbuddy/skills/minimax-docx/scripts/dotnet/MiniMaxAIDocx.Cli/bin/Release/net8.0/MiniMaxAIDocx.Cli.dll"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

shutil.copy(IN, BAK)
print("backup ->", BAK)

def run(args):
    p = subprocess.run(["dotnet", DLL] + args, capture_output=True, text=True)
    if p.returncode != 0:
        print("CLI FAIL:", args[:4], "STDERR:", p.stderr[:500])
        sys.exit(1)
    return p.stdout

def para_texts(path):
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.iter(W + "p"):
        texts = [t.text or "" for t in p.iter(W + "t")]
        out.append("".join(texts))
    return out

def find_index(path, contains, occurrence=1):
    texts = para_texts(path)
    cnt = 0
    for i, t in enumerate(texts):
        if contains in t:
            cnt += 1
            if cnt == occurrence:
                return i
    return -1

def insert_after(anchor_text, style, text, occurrence=1, before=False):
    idx = find_index(IN, anchor_text, occurrence)
    if idx < 0:
        print("ANCHOR NOT FOUND:", anchor_text); sys.exit(1)
    after = (idx - 1) if before else idx
    tmp = IN + ".tmp.docx"
    run(["edit", "insert-paragraph",
         "--input", IN, "--output", tmp,
         "--text", text, "--style", style,
         "--after-paragraph", str(after)])
    shutil.move(tmp, IN)

def replace_all(find, repl):
    cnt = 0
    while True:
        texts = para_texts(IN)
        if not any(find in t for t in texts):
            break
        tmp = IN + ".tmp.docx"
        run(["edit", "replace-text", "--input", IN, "--output", tmp,
             "--search", find, "--replace", repl])
        shutil.move(tmp, IN)
        cnt += 1
        if cnt > 10:
            break
    print("replace_all done, passes =", cnt)

# ---------- 1) 版本号 ----------
replace_all("v1.1.0", "v1.2.0")
left = sum(1 for t in para_texts(IN) if "v1.1.0" in t)
print("remaining v1.1.0:", left)

# ---------- 2) 目录增加入口（在 TOC「常见问题」条目后） ----------
toc_entries = [
    ("ds-markdown-paragraph", "升级到 v1.2.0（变更说明）"),
    ("ds-markdown-paragraph", "v1.2.0 新增功能详解"),
]
for style, text in reversed(toc_entries):
    insert_after("常见问题", style, text, occurrence=1, before=False)

# ---------- 3) 第 0 章：变更说明（插入到「1. 环境要求」之前） ----------
# before 插入需按正向顺序（锚点会随插入下移，逐次插入到上一插入项之后）
changelog = [
    ("heading 2", "0. 升级到 v1.2.0（变更说明）"),
    ("ds-markdown-paragraph", "本版相较 v1.1.0 在界面、翻译流程与术语管理上做了大量升级，并重点加固了占位符保留。以下为变更摘要，详细用法见第 14 章。"),
    ("ds-markdown-paragraph", "【新增功能】"),
    ("ds-markdown-paragraph", "• 亚克力毛玻璃 GUI：圆形头像、宝可梦主题配色、8 个菜单页、右侧文件侧边栏、状态条小精灵球，支持本地 Ollama 与云端 API 双模式切换。"),
    ("ds-markdown-paragraph", "• 文件范围选择：菜单 1/2/3/5 执行前可选「单文件 / 整个文件夹」，自动跳过生成物，选择结果在菜单间自动同步。"),
    ("ds-markdown-paragraph", "• 中文润色重翻：新增菜单 5，对缓存中的中文译文做一轮润色并覆盖回写。"),
    ("ds-markdown-paragraph", "• 云端 API 模式：新增 OpenAI 兼容 /chat/completions 云端模式，切换时同步调整参数并弹窗提示。"),
    ("ds-markdown-paragraph", "• 检查更新：从 GitHub Release 拉取最新 tag，版本不一致时弹窗提醒（含下载链接）。"),
    ("ds-markdown-paragraph", "• 前缀 / 检查报告列表滚动条：溢出时显示滚动条，长文件不溢出。"),
    ("ds-markdown-paragraph", "【修复与改进】"),
    ("ds-markdown-paragraph", "• 占位符保留加固（重点）：术语表加载排除 @0@ 等占位符 token，杜绝其被当术语注入 prompt 反向教模型翻译占位符；清理了模型误提取的 @0@…@4@ 伪术语；auto_terms 与 @@T: 提取增加占位符型 key 拒绝。"),
    ("ds-markdown-paragraph", "• 译后占位符校验失败时，针对性重试并明确告知模型丢失了哪些 @N@；兜底补回改用源文相对位置精确回插，并修正此前兜底结果被二次判失败、整条被丢弃的潜在缺陷。"),
    ("ds-markdown-paragraph", "• 术语提取 / 匹配性能优化（单词哈希 + 多词小正则）；中文字体统一为微软雅黑，字号适度放大不溢出；译文缺失 / 未保留的控制码按原文原样补回。"),
    ("ds-markdown-paragraph", "【升级说明】直接覆盖运行即可；首次使用请在「设置」中配置模型，云端模式需填写 API 地址与密钥。术语表 term_dict.py 为本地私有数据，不随仓库分发。"),
]
for style, text in changelog:
    insert_after("1. 环境要求", style, text, occurrence=1, before=True)

# ---------- 4) 第 14 章：新增功能详解（插入到「文档结束」之前） ----------
chapter14 = [
    ("heading 2", "14. v1.2.0 新增功能详解"),
    ("heading 3", "14.1 毛玻璃 GUI 界面"),
    ("ds-markdown-paragraph", "启动后进入亚克力磨砂质感 GUI：左上圆形头像（悬停显示作者信息），标题栏显示版本 v1.2.0；左侧 8 个菜单，右侧文件侧边栏，底部状态条带小精灵球。"),
    ("ds-markdown-paragraph", "GUI 菜单顺序：1 翻译 / 2 重翻检查报告 / 3 术语更新后重翻 / 4 前缀字典 / 5 中文润色 / 6 Excel 转术语表 / 7 设置 / 8 日志·环境·检查更新。"),
    ("ds-markdown-paragraph", "菜单 8 为日志页，翻译等任务启动后会自动跳转过去查看进度。"),
    ("heading 3", "14.2 文件范围选择"),
    ("ds-markdown-paragraph", "菜单 1/2/3/5 执行前，右侧侧边栏可选择「单个文件」或「整个文件夹」。"),
    ("ds-markdown-paragraph", "选文件夹时列出全部 .txt 并逐个翻译；自动跳过生成物（*_translated.txt、*_translated_report.txt）。"),
    ("ds-markdown-paragraph", "在菜单 1 选择的结果会自动同步到菜单 2~5，无需重复选择。"),
    ("heading 3", "14.3 中文润色（菜单 5，新增）"),
    ("ds-markdown-paragraph", "对缓存中的中文译文再做一轮润色并覆盖回写，不改变原意与占位符。"),
    ("ds-markdown-paragraph", "短于阈值的句子自动跳过；润色时严格校验占位符，不全则保留原译文。"),
    ("heading 3", "14.4 云端 API 模式（新增）"),
    ("ds-markdown-paragraph", "除本地 Ollama 外，新增 OpenAI 兼容 /chat/completions 云端模式；在「设置」或模式切换处选择「云端 API」并填写 API 地址与密钥即可。"),
    ("ds-markdown-paragraph", "切换时自动调整术语上限 / 超时 / 上下文 / 最大生成 / 每批条数 / 单批字符，并弹窗提示前后值。"),
    ("heading 3", "14.5 检查更新（菜单 8，新增）"),
    ("ds-markdown-paragraph", "从 GitHub Release 拉取最新 tag，与本地版本不一致时弹窗提醒并提供下载链接。"),
    ("heading 3", "14.6 术语删除与撤回（菜单 3，新增）"),
    ("ds-markdown-paragraph", "术语列表支持双击编辑译文；可选中（可多选）或按当前筛选批量删除术语。"),
    ("ds-markdown-paragraph", "删除在「应用术语」之前可一键「撤回」，撤回栈支持逐步恢复，便于安心整理术语表。"),
    ("ds-markdown-paragraph", "应用后：改动 / 删除写入术语字典，并删除含相关术语句子的缓存以重翻。"),
]
for style, text in chapter14:
    insert_after("文档结束", style, text, occurrence=1, before=True)

print("ALL INSERTIONS DONE")
print("total paragraphs now:", len(para_texts(IN)))
