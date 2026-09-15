# 宝可梦同人游戏翻译工具

[中文](README-ch.md) | [English](README.md)

使用本地 Ollama 大模型批量翻译宝可梦同人游戏文本文件，支持术语表、
占位符保护、断点续传、自动检查。

## 特性

- 🤖 **本地翻译** — 调用 Ollama API，数据不出本机
- 📚 **术语表** — 从 Excel 多语言表一键生成，官方译名预替换
- 🔒 **占位符保护** — `\PN`、`\wt[10]`、`[Haya]` 等控制码不被翻译
- 💾 **断点续传** — 缓存每批落盘，随时 Ctrl+C 都能继续
- ✅ **自动检查** — 翻译后自动报告未翻译 / 符号不匹配 / 特殊行
- 🔄 **自动重翻** — 一键重翻未翻译 / 疑似未翻译的句子
- 🔀 **换行重排** — 按 15–17 字 + 句末标点智能换行
- 🧠 **术语更新重翻** — 自动识别新增术语，只重翻包含它的句子
- ⚙️ **内置设置菜单** — 菜单里直接改配置，不用手动编辑文件
- 🖥️ **独立 exe** — Releases 页提供可直接运行的 Windows 可执行文件

## 环境要求

**下载 Releases 里的 exe：**

- Windows 10/11
- [Ollama](https://ollama.com/download) 已安装并运行
- 推荐模型：`qwen2.5:14b`

**源码运行：**

- Python 3.9+
- [Ollama](https://ollama.com/download) 已安装并运行
- 推荐模型：`qwen2.5:14b`

## 安装

### 方式 A —— 下载 exe（推荐）

1. 打开 [Releases](https://github.com/nevermore-glimpse/pkmn_translator/releases) 页面
2. 下载 `PkmnTranslator_vX.Y.Z.zip` 并解压
3. 双击 `宝可梦翻译工具.exe`
4. （可选）双击 `创建桌面快捷方式.vbs` 生成桌面带图标的快捷方式

### 方式 B —— 源码运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 拉取模型
ollama pull qwen2.5:14b

# 3. 确认 Ollama 在跑
curl http://localhost:11434/api/tags

# 4. 启动程序
python main.py
```

## 使用

### 快速开始

双击 `启动.bat`（或 exe 版本的 `宝可梦翻译工具.exe`），或在命令行：

```bash
python main.py
```

启动时会自动检查 Python 环境、依赖、Ollama 服务和模型。
若 Ollama 未启动，会询问是否自动启动（优先启动桌面应用，
找不到则退回命令行 `ollama serve`）。

出现菜单：

```
1. 翻译
2. 重翻未翻译内容
3. Excel 转术语表
4. 切换输入文件
5. 术语更新后重翻
6. 设置
7. 重新检查环境
0. 退出
```

### 创建桌面快捷方式（可选）

双击 `创建桌面快捷方式.vbs`。
桌面会出现名为"宝可梦同人游戏翻译工具"的快捷方式。

### 翻译流程

1. 选 `1` → 选源/目标语言 → 弹窗选择要翻译的 `.txt` 文件
2. 等待翻译完成，输出到 `<文件名>_translated.txt`
3. 检查报告会生成在**输出文件旁边**：`<文件名>_translated_report.txt`
4. 若还有问题，选 `2` 自动重翻未翻译的行，或手动修正

### 重翻未翻译内容（菜单 2）

对输出文件重新检查，然后：

- 自动重翻标记为 **未翻译** 或 **疑似未翻译** 的句子
- **符号不匹配** 和 **特殊行** 只报告，不自动重翻
  （符号不匹配通常意味着模型漏了控制码，重翻往往还是漏）

只有被影响的缓存条目会被删除，重翻速度很快。

### 术语表

准备一份 Excel，每个 sheet 表头含语言列名（`英文`、`简体中文` 等），当然也可以用我的：

| 图鉴编号 | 英语 | 简体中文 |
|---------|------|---------|
| 1 | Bulbasaur | 妙蛙种子 |
| 2 | Ivysaur | 妙蛙草 |

选菜单 `3` → 弹窗选 Excel → 选源/目标语言 → 自动生成 `term_dict.py`。

### 术语更新后重翻（菜单 5）

修改 `term_dict.py`（或重新从 Excel 生成）后：

1. 选菜单 `5`
2. 系统自动对比当前术语表和上次快照
3. 找出新增的术语，并定位到所有包含这些术语的缓存句子
4. 删除这些缓存并重新翻译

**首次运行菜单 5** 会把当前术语表记录为基准；
**以后每次运行** 都会对比它，只需几十秒就能完成增量重翻。

### 输入文件格式

```
[map1]
Text A
Text A            ← 重复的第二行会被翻译
Text B
Text B
```

- 区块符 `[map1]` 独占一行
- 纯数字行跳过
- 文本行必须**成对重复**，只翻译第二行
- 不成对的文本行会被标记为"特殊行"，需手动处理

## 配置

三种修改方式：

**方式 1 —— 菜单里改（推荐）**

选菜单 `6`，输入要改的设置序号：

```
  1. Ollama 模型名      = qwen2.5:14b
  2. Ollama 服务地址    = http://localhost:11434/api/chat
  3. 每批条数           = 20
  4. 采样温度           = 0.2
  ...
 20. Excel 目标语言列   = 简体中文
```

改完**当前会话立即生效**，无需重启。

- **源码运行** → 写回 `config.py`
- **exe 运行** → 存到 exe 同目录的 `user_config.json`

**方式 2 —— 直接编辑 `config.py`（源码模式）**

```python
MODEL = "qwen2.5:14b"        # 换模型
BATCH_SIZE = 20              # 每批条数
WRAP_CHARS_MIN = 15          # 换行下限
WRAP_CHARS_MAX = 17          # 换行上限
```

**方式 3 —— 编辑 `user_config.json`（exe 模式）**

在 exe 同目录创建 `user_config.json`，写想覆盖的项：

```json
{
  "MODEL": "qwen2.5:7b",
  "BATCH_SIZE": 15
}
```

重启 exe 生效。

## 日志

- 控制台：`INFO` 级
- 文件：`logs/translate_YYYYMMDD.log`（含 `DEBUG`）
- 调试模式：源码 `set DEBUG_PH=1 && python main.py`，exe `set DEBUG_PH=1 && 宝可梦翻译工具.exe`

## 常见问题

**Ollama 没启动**

工具会自动尝试启动。若失败：

1. 检查系统托盘有没有 Ollama 图标（Desktop 版会自动运行）
2. 手动运行 `ollama serve` 看报错
3. 检查 11434 端口是否被占用：`netstat -ano | findstr :11434`
4. 查看日志：`logs/ollama_launch.log`

**模型未安装**

```
ollama pull qwen2.5:14b
```

**译文里混着英文**

选菜单 `2` 自动重翻，或打开 `<输出文件>_report.txt` 手动修正。

**占位符丢了**

工具会自动重试和兜底。仍失败的行会出现在检查报告里，
手工修正或把相关词加入术语表。

**exe 报 `FileNotFoundError: config.py`**

请使用最新版本的 Release。exe 模式使用 `user_config.json`，不再读写 `config.py`。

**双击 exe 闪退**

在 exe 所在目录打开命令行（cmd），手动运行看错误：

```cmd
宝可梦翻译工具.exe
```

## 编译 exe

```bash
pip install pyinstaller
pyinstaller --onefile --name "宝可梦翻译工具" --icon=start.ico ^
    --hidden-import openpyxl --hidden-import tkinter main.py
```

打包完成后把 `start.ico` 复制到 `dist\` 里与 exe 同级。

## 许可

MIT