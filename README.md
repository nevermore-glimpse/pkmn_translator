\# Pokémon Fan Game Translation Tool



\[中文](README.md) | \[English](README\_EN.md)



A batch translation tool for Pokémon fan game text files, powered by a local Ollama LLM.

Supports terminology lists, placeholder protection, resume from cache, and automatic checking.



\## Features



\- 🤖 \*\*Local translation\*\*: Uses the Ollama API, data never leaves your machine

\- 📚 \*\*Terminology list\*\*: Generate from an Excel multilingual sheet with one click; official translations are pre-substituted

\- 🔒 \*\*Placeholder protection\*\*: Control codes like `\\PN`, `\\wt\[10]`, `\[Haya]` are not translated

\- 💾 \*\*Resume from cache\*\*: Cache is saved after each batch; you can Ctrl+C and continue anytime

\- ✅ \*\*Auto-check\*\*: Automatically reports untranslated lines / symbol mismatches / special lines after translation

\- 🔀 \*\*Line rewrapping\*\*: Smart line breaks at 15–17 characters and sentence-ending punctuation



\## Requirements



\- Python 3.9+

\- \[Ollama](https://ollama.com/download) installed and running

\- Recommended model: `qwen2.5:14b` (good for Chinese localization)



\## Installation



```bash

\# 1. Install dependencies

pip install -r requirements.txt



\# 2. Pull the model

ollama pull qwen2.5:14b



\# 3. Make sure Ollama is running

curl http://localhost:11434/api/tags

```



\## Usage



\### Quick Start



Double-click `启动.bat`, or run from the command line:



```bash

python main.py

```



You will see the menu:



```

1\. Translate

2\. Check (untranslated / symbol mismatch / special lines)

3\. Excel to terminology

4\. Switch input file

0\. Exit

```



\### Translation Workflow



1\. Select `1` → a file dialog opens to choose the `.txt` file to translate

2\. Wait for translation to finish; output is written to `<filename>\_translated.txt`

3\. Open `reports/check\_report.txt` and fix issues line by line as reported

4\. If problems remain, select `2` to run the check again



\### Terminology List



Prepare an Excel file where each sheet has language column headers (e.g. `English`, `Simplified Chinese`).

You can also use mine:



| Pokédex No. | English | Simplified Chinese |

|-------------|---------|-------------------|

| 1 | Bulbasaur | 妙蛙种子 |

| 2 | Ivysaur | 妙蛙草 |



Select menu `3` → choose the Excel file in the dialog → choose source/target languages → `term\_dict.py` is generated automatically.



\### Input File Format



```

\[map1]

Text A

Text A            ← the repeated second line will be translated

Text B

Text B

```



\- Block markers `\[map1]` occupy a line by themselves

\- Pure numeric lines are skipped

\- Text lines must appear in \*\*duplicate pairs\*\*; only the second line is translated

\- Text lines that are not paired are marked as "special lines" and need manual handling



\## Configuration



Edit `config.py`:



```python

MODEL = "qwen2.5:14b"        # change model

BATCH\_SIZE  = 20             # lines per batch

WRAP\_CHARS\_MIN = 15          # lower wrap limit

WRAP\_CHARS\_MAX = 17          # upper wrap limit

```



\## Logging



\- Console: `INFO` level

\- File: `logs/translate\_YYYYMMDD.log` (includes `DEBUG`)

\- Debug mode: `set DEBUG\_PH=1 \&\& python main.py`



\## License



MIT

