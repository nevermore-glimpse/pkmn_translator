# 宝可梦同人游戏翻译工具



使用本地 Ollama 大模型批量翻译宝可梦同人游戏文本文件，支持术语表、

占位符保护、断点续传、自动检查。



## 特性



- 🤖 \*\*本地翻译\*\*：调用 Ollama API，数据不出本机

- 📚 \*\*术语表\*\*：从 Excel 多语言表一键生成，官方译名预替换

- 🔒 \*\*占位符保护\*\*：`\\PN`、`\\wt\[10]`、`\[Haya]` 等控制码不被翻译

- 💾 \*\*断点续传\*\*：缓存每批落盘，随时 Ctrl+C 都能继续

- ✅ \*\*自动检查\*\*：翻译后自动报告未翻译 / 符号不匹配 / 特殊行

- 🔀 \*\*换行重排\*\*：按 15–17 字 + 句末标点智能换行



## 环境要求



- Python 3.9+

- [Ollama](https://ollama.com/download) 已安装并运行

- 推荐模型：`qwen2.5:14b`（中文本地化）



## 安装



```bash

# 1. 安装依赖

pip install -r requirements.txt



# 2. 拉取模型

ollama pull qwen2.5:7b



# 3. 确认 Ollama 在跑

curl http://localhost:11434/api/tags

```



## 使用



### 快速开始



双击 `启动.bat`，或在命令行：



```bash

python main.py

```



出现菜单：



```

1\. 翻译

2\. 检查（未翻译 / 符号不匹配 / 特殊行）

3\. Excel 转术语表

4\. 切换输入文件

0\. 退出

```



### 翻译流程



1\. 选 `1` → 弹窗选择要翻译的 `.txt` 文件

2\. 等待翻译完成，输出到 `<文件名>\_translated.txt`

3\. 打开 `reports/check\_report.txt`，按报告逐行修正

4\. 若还有问题，选 `2` 重新检查



### 术语表



准备一份 Excel，每个 sheet 表头含语言列名（`英文`、`简体中文` 等）：



| 图鉴编号 | 英语 | 简体中文 |

|---------|------|---------|

| 1 | Bulbasaur | 妙蛙种子 |

| 2 | Ivysaur | 妙蛙草 |



选菜单 `3` → 弹窗选 Excel → 选源/目标语言 → 自动生成 `term\_dict.py`。



### 输入文件格式



```

[map1]

Text A

Text A            ← 重复的第二行会被翻译

Text B

Text B

```



- 区块符 `\[map1]` 独占一行

- 纯数字行跳过

- 文本行必须\*\*成对重复\*\*，只翻译第二行

- 不成对的文本行会被标记为"特殊行"，需手动处理



## 目录结构



```

pkmn\_translator/

├── main.py               主入口

├── config.py             配置

├── commands.py           三大功能实现

├── processor.py          文本处理（保护/术语/换行）

├── parser.py             intl.txt 解析

├── checker.py            翻译检查

├── cache.py              缓存

├── logger.py             日志

├── translator.py         Ollama 客户端

├── build\_terms.py        Excel 提取

├── filepicker.py         文件选择器

├── 启动.bat              双击启动

├── start.ico             图标

├── requirements.txt

└── term\_dict.example.py  术语表模板

```



## 配置



编辑 `config.py`：



```python

MODEL       = "qwen2.5:7b"   # 换模型

BATCH\_SIZE  = 20             # 每批条数

WRAP\_CHARS\_MIN = 15          # 换行下限

WRAP\_CHARS\_MAX = 17          # 换行上限

```



## 日志



- 控制台：`INFO` 级

- 文件：`logs/translate\_YYYYMMDD.log`（含 `DEBUG`）

- 调试模式：`set DEBUG\_PH=1 \&\& python main.py`


## 许可



MIT

