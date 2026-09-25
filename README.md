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
- 🔄 **Auto re-translate** — Re-translates untranslated / suspected-untranslated sentences with one click
- 🔀 **Line rewrapping** — Dedicated step (menu 6): by character count for `[map*]` (`\n`) and other blocks (spaces). Not applied automatically after translation.
- 🧠 **Terminology re-translation** — Detects newly added terms and re-translates only the affected sentences
- ⚙️ **In-app settings** — Edit all configuration values from the menu, no manual file editing
- 🖥️ **Standalone exe** — Releases include a ready-to-run Windows executable

## Requirements

**If you download the exe from [Releases](https://github.com/nevermore-glimpse/pkmn_translator/releases):**

- Windows 10/11
- [Ollama](https://ollama.com/download) installed and running
- Recommended model: `qwen2.5:14b`

**If you run from source:**

- Python 3.9+
- [Ollama](https://ollama.com/download) installed and running
- Recommended model: `qwen2.5:14b`

## Installation

### Option A — Download the exe (recommended)

1. Go to the [Releases](https://github.com/nevermore-glimpse/pkmn_translator/releases) page
2. Download `PkmnTranslator_vX.Y.Z.zip` and unzip it
3. Run `宝可梦翻译工具.exe`
4. (Optional) Double-click `创建桌面快捷方式.vbs` to create a desktop shortcut with icon

### Option B — Run from source

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Pull the model
ollama pull qwen2.5:14b

# 3. Make sure Ollama is running
curl http://localhost:11434/api/tags

# 4. Start the tool
python main.py
```

## Usage

### Quick Start

Double-click `启动.bat` (or `宝可梦翻译工具.exe` if using the release build), or run:

```bash
python main.py          # acrylic GUI (default)
python main.py --cli    # command-line menu
```

On startup, the tool automatically checks your Python environment, dependencies,
Ollama service, and the required model. If Ollama is not running, it will offer to
launch it for you (Ollama Desktop App is preferred, with `ollama serve` as fallback).

GUI pages:

```
1. Translate            5. Chinese polish
2. Re-translate report  6. Excel to terminology
3. Re-translate terms   7. Settings
4. Prefix dictionary    8. Log
```

Pages 1–5 have a file checklist sidebar on the right; add files via
"Single file" or "Whole folder".

Command-line menu:

```
1. Translate
2. Re-translate check report
3. Re-translate after terminology update
4. Prefix dictionary (view / apply)
5. Chinese polish
6. Excel to terminology
7. Settings
8. Log / environment check
0. Exit
```

Menus 2 / 3 / 4 ask for "single file / whole folder" first.

### Create Desktop Shortcut (Optional)

Double-click `创建桌面快捷方式.vbs` (Create Desktop Shortcut.vbs).
A shortcut named *Pokémon Fan Game Translation Tool* will be created on your desktop.

### Translation Workflow

1. Select `1` → choose source/target languages → a file dialog opens to pick the `.txt` file
2. Wait for translation to finish; output is written to `<filename>_translated.txt`
3. A check report is generated next to the output file: `<filename>_translated_report.txt`
4. If problems remain, select `2` to auto re-translate the untranslated lines, or fix manually

### Re-translate Check Report (Menu 2)

Runs a fresh check on the output file, then:

- Auto re-translates lines marked as **Untranslated** or **Suspected untranslated**
- Only reports **Symbol mismatch** and **Special lines** — these are not auto-fixed
  (symbol mismatches usually mean the model dropped a control code; retrying rarely helps)

Only the affected cache entries are deleted, so re-translation is fast.

### Terminology List

Prepare an Excel file where each sheet has language column headers (e.g. `English`, `Simplified Chinese`).
You can also use mine:

| Pokédex No. | English | Simplified Chinese |
|-------------|---------|-------------------|
| 1 | Bulbasaur | 妙蛙种子 |
| 2 | Ivysaur | 妙蛙草 |

Select menu `3` → choose the Excel file → choose source/target languages → `term_dict.py` is generated automatically.

### Re-translate After Adding New Terms (Menu 3)

After editing `term_dict.py` (or regenerating from Excel):

1. Select `3`
2. The tool compares the current terminology list against the last snapshot
3. Newly added terms are identified; sentences containing them are located in the cache
4. Those cache entries are deleted and re-translated with the new terminology

The first time you run menu `3`, it records the current terminology list as the baseline.
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

You can edit settings in three ways:

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

Changes take effect immediately — no restart needed.

- **Running from source** → changes are written back to `config.py`
- **Running from exe** → changes are saved in `user_config.json` next to the exe

**Method 2 — Edit `config.py` directly (source mode)**

```python
MODEL = "qwen2.5:14b"        # model name
BATCH_SIZE = 20              # lines per batch
WRAP_CHARS_MIN = 15          # lower wrap limit
WRAP_CHARS_MAX = 17          # upper wrap limit
```

**Method 3 — Edit `user_config.json` (exe mode)**

Create a `user_config.json` file next to the exe with any keys you want to override:

```json
{
  "MODEL": "qwen2.5:7b",
  "BATCH_SIZE": 15
}
```

Restart the exe to apply.

## Logging

- Console: `INFO` level
- File: `logs/translate_YYYYMMDD.log` (includes `DEBUG`)
- Debug mode: `set DEBUG_PH=1 && python main.py` (source) or `set DEBUG_PH=1 && 宝可梦翻译工具.exe`

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

Run menu `2` to auto re-translate, or open `<output>_report.txt` and fix manually.

**Placeholder lost**

The tool retries and falls back automatically. If a line still fails, it is reported in the check report. Fix it manually or add the term to your terminology list.

**exe throws `FileNotFoundError: config.py`**

Make sure you are using the latest release. The tool uses `user_config.json` in exe mode.

**Double-clicking the exe flashes and closes**

Open a Command Prompt in the exe folder and run it manually to see the error:

```cmd
宝可梦翻译工具.exe
```

## Building the exe

```bash
pip install pyinstaller
pyinstaller --onefile --name "宝可梦翻译工具" --icon=start.ico ^
    --hidden-import openpyxl --hidden-import tkinter --hidden-import PIL main.py
```

Then copy `start.ico` next to the produced exe in `dist\`.

## License

MIT