# Pokémon Fan Game Translation Tool

[中文](README-ch.md) | [English](README.md)

A batch translation tool for Pokémon fan game text files, powered by a local Ollama LLM.
Supports terminology lists, placeholder protection, resume from cache, and automatic checking.

## Features

- 🤖 **Local translation** — Uses the Ollama API, data never leaves your machine
- 📚 **Terminology list** — Generate from an Excel multilingual sheet with one click; official translations are pre-substituted
- 🔒 **Placeholder protection** — Control codes like `\PN`, `\wt[10]`, `[Haya]` are not translated
- 💾 **Resume from cache** — Cache is saved after each batch; you can Ctrl+C and continue anytime
- ✅ **Auto-check** — Automatically reports untranslated lines / symbol mismatches / special lines after translation
- 🔀 **Line rewrapping** — Smart line breaks at 15–17 characters and sentence-ending punctuation
- 🧠 **Terminology re-translation** — Detects newly added terms and re-translates only the affected sentences
- ⚙️ **In-app settings** — Edit all configuration values from the menu, no manual file editing

## Requirements

- Python 3.9+
- [Ollama](https://ollama.com/download) installed and running
- Recommended model: `qwen2.5:14b` (good for Chinese localization)

## Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Pull the model
ollama pull qwen2.5:14b

# 3. Make sure Ollama is running
curl http://localhost:11434/api/tags
```

## Usage

### Quick Start

Double-click `Start.bat`, or run from the command line:

```bash
python main.py
```

On startup, the tool automatically checks your Python environment, dependencies,
Ollama service, and the required model. If Ollama is not running, it will offer to
launch it for you (Ollama Desktop App is preferred, with `ollama serve` as fallback).

You will see the menu:

```
1. Translate
2. Check (untranslated / symbol mismatch / special lines)
3. Excel to terminology
4. Switch input file
5. Re-translate after terminology update
6. Settings
7. Re-check environment
0. Exit
```

### Create Desktop Shortcut (Optional)

Double-click `Create Desktop Shortcut.vbs`.
A shortcut named *Pokémon Fan Game Translation Tool* will be created on your desktop.

### Translation Workflow

1. Select `1` → a file dialog opens to choose the `.txt` file to translate
2. Wait for translation to finish; output is written to `<filename>_translated.txt`
3. Open `reports/check_report.txt` and fix issues line by line as reported
4. If problems remain, select `2` to run the check again

### Terminology List

Prepare an Excel file where each sheet has language column headers (e.g. `English`, `Simplified Chinese`).
You can also use mine:

| Pokédex No. | English | Simplified Chinese |
|-------------|---------|-------------------|
| 1 | Bulbasaur | 妙蛙种子 |
| 2 | Ivysaur | 妙蛙草 |

Select menu `3` → choose the Excel file in the dialog → choose source/target languages → `term_dict.py` is generated automatically.

### Re-translate After Adding New Terms

After editing `term_dict.py` (or regenerating from Excel):

1. Select `5`
2. The tool compares the current terminology list against the last snapshot
3. Newly added terms are identified; sentences containing them are located in the cache
4. Those cache entries are deleted and re-translated with the new terminology

The first time you run menu `5`, it records the current terminology list as the baseline.
Every subsequent run compares against it.

### Input File Format

```
[map1]
Text A
Text A            ← the repeated second line will be translated
Text B
Text B
```

- Block markers `[map1]` occupy a line by themselves
- Pure numeric lines are skipped
- Text lines must appear in **duplicate pairs**; only the second line is translated
- Text lines that are not paired are marked as "special lines" and need manual handling

## Configuration

You can edit settings in two ways:

**Method 1 — In-app menu (recommended)**

Select `6` from the main menu. Enter the number of the setting you want to change:

```
  1. Ollama model         = qwen2.5:14b
  2. Ollama URL           = http://localhost:11434/api/chat
  3. Batch size           = 20
  4. Temperature          = 0.2
  ...
 20. Excel target column  = 简体中文
```

Changes are written back to `config.py` and take effect immediately — no restart needed.

**Method 2 — Edit `config.py` directly**

```python
MODEL = "qwen2.5:14b"        # model name
BATCH_SIZE = 20              # lines per batch
WRAP_CHARS_MIN = 15          # lower wrap limit
WRAP_CHARS_MAX = 17          # upper wrap limit
```

## Logging

- Console: `INFO` level
- File: `logs/translate_YYYYMMDD.log` (includes `DEBUG`)
- Debug mode: `set DEBUG_PH=1 && python main.py`

## Troubleshooting

**Ollama is not running**

The tool will try to launch it automatically. If that fails:
1. Check the system tray for the Ollama icon (Desktop version runs in background)
2. Run `ollama serve` manually and check its output
3. Check whether port 11434 is occupied: `netstat -ano | findstr :11434`
4. See the log: `logs/ollama_launch.log`

**Model not installed**

```
ollama pull qwen2.5:14b
```

**Translation output contains raw English**

Run menu `2` (Check) and look at the report. Lines marked as *suspected untranslated* need manual fixing.

**Placeholder lost**

The tool retries and falls back automatically. If a line still fails, it is reported in the check report. Fix it manually or add the term to your terminology list.

## License

MIT