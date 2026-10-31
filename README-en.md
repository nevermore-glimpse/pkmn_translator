# Pokémon Fan Game Translation Tool

[中文](README.md) | [English](README-en.md)

A batch translation tool for Pokémon fan game text files, powered by a local Ollama LLM.  
Supports terminology lists, control-code detection, resume from cache, and automatic checking.

## Features

- 🤖 **Local translation** — Uses the Ollama API, data never leaves your machine
- 📚 **Terminology list** — Generate from an Excel multilingual sheet with one click; official translations are pre-substituted
- 🔒 **Placeholder protection** — Control codes like `\PN`, `\wt[10]`, `[Haya]` are not translated
- 💾 **Resume from cache** — Cache is saved after each batch; you can Ctrl+C and continue anytime
- ✅ **Auto-check** — Automatically reports untranslated lines / symbol mismatches / special lines after translation
- 🔄 **Auto re-translate** — Re-translates untranslated / suspected-untranslated sentences with one click
- 🔀 **Line rewrapping** — Dedicated step (menu 6): by character count for `[map*]` (`\n`) and other blocks (spaces). **Blocks can be multi-selected, and only the selected blocks are rewrapped.** Not applied automatically after translation.
- 📤 **Extract / compile game text** — Same as *Extract Text* / *Compile Text* in the game's debug menu, but without launching the game. Text is always split into **one txt per section** (older builds go to `Text_<lang>/`, v21+ to `Text_<lang>_core/` and `Text_<lang>_game/`), which makes translating far easier. **Splitting never changes the compiled result** — the compiler rebuilds the table by section/map id, so a single file and 20 files produce a **byte-identical** `.dat` (verified on real games; regression `work/t_lang_split.py`). Can also add the language to `Settings::LANGUAGES` for you (uncomment the first entry → copy the line → `English`→`Chinese`; no model call, no comment translation). Verified byte-for-byte against real games' own output (menu 1).
- ✏️ **Edit translations by hand + apply them** — Double-click any row in the check report to edit it: source text on top (read-only, for reference), translation below. Saved into the cache and filed under a new "已编辑" (edited) kind that is never overwritten by re-translation. Then hit **"应用已编辑"** to push every hand-edited line into the translation cache *and* into the generated `*_translated.txt` — untouched lines stay byte-identical (menu 3).
- 🈶 **Chinese text plugin** — **Six plugin bodies ship with the tool (21.1 / 20.1 / 19.1 / 18.1 / 17.2 / 16) and the right one is picked automatically from the game's `Essentials::VERSION`** (a fingerprint match is used when the version can't be read, and an 18.1 fallback when neither works).
  - Games **with** a `Plugins/` folder: the plugin is dropped in there and every plugin (including the game's own) is **compiled straight into `Data/PluginScripts.rxdata`** — no debug mode, no launching the game. A compatibility shim is added when the version can't be read, falling back to the engine's own implementation if the plugin raises.
  - Games **without** a `Plugins/` folder, or without a plugin system at all (pre-v18, **Ruby 1.8.1**): the plugin is concatenated into a single script and **inserted just *before* the `Main` script in `Scripts.rxdata`** — RGSS evaluates scripts top to bottom and enters the game loop the moment it reaches `Main`, so anything placed *after* `Main` never runs (that was the original "injected but no effect" bug). For unpacked games the file is named after `Main`'s number minus one (e.g. `999_Main.rb` → `998_pkmn_chinese_text.rb`) so it sorts between the last normal script and `Main`.  
  - **Font replacement**: choosing a font when loading the plugin also patches every font-related engine script at once — `SpriteWindow`, `MessageConfig` and `Settings` font constants, plus hardcoded font names in `pbSetSystemFontName` / `pbTryFonts` / `Font.default_name` / `FONT_OPTIONS`. Each modified script is backed up first; "restore" rolls them all back.
    The legacy body patches `String#ord` (via `unpack("U")` — `self[0]` only returns the first *byte* in 1.8 and would never detect Chinese) and `String#each_char`, routes every per-character split through `_pkmn_chars()` (Ruby 1.8's `$KCODE` is not `'U'`, so `scan(/./m)` splits *bytes* and Chinese is never detected), writes both the modern `FONT_NAME` and the legacy `MessageConfig::FontName` font constants, and builds the `\p{Han}` regex at runtime so old Oniguruma won't choke. Re-injecting never stacks duplicates, and "restore" removes exactly that one entry. Verified: `Scripts.rxdata` round-trips byte-for-byte on six real games, so only the one inserted entry changes (menu 1).
- 🧠 **Terminology re-translation** — Detects newly added terms and re-translates only the affected sentences
- ⚙️ **In-app settings** — Edit all configuration values from the menu, no manual file editing
- 📋 **One-click copy** — Right-click any report / term / prefix list to copy it as  
  tab-separated text (paste straight into Excel); logs, file paths, statistics and  
  settings fields are copyable too
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
3. Run `宝可梦同人工具.exe`
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

Double-click `启动.bat` (or `宝可梦同人工具.exe` if using the release build), or run:

```bash
python main.py          # acrylic GUI (default)
python main.py --cli    # command-line menu
```

On startup, the tool automatically checks your Python environment, dependencies,  
Ollama service, and the required model. If Ollama is not running, it will offer to  
launch it for you (Ollama Desktop App is preferred, with `ollama serve` as fallback).

GUI pages:

The left side has **8 main menus**; some open into **sub-pages** (reached  
from the parent page, with a "← back" bar at the top):

```
1. Extract / compile text   5. Enable DEBUG
2. Game localization        6. Save editor
3. PBS edit                 7. Settings
4. Local model server       8. Log
```

Game localization (menu 2) sub-pages: term extraction / term-check report /  
translate / re-translate report / re-translate after term update / prefix  
dictionary / line rewrap / terminology dictionary / Excel conversion (the  
dictionary page is the default; switch to the Excel view from there).

Save editor (menu 6) sub-pages: trainer / party Pokémon / bag / PC boxes /  
switches & variables.

PBS edit (menu 3) sub-page: the PBS editor window (only pokemon /  
pokemon_forms / items / moves are editable).

The Enable DEBUG page (GUI menu 5 / CLI 10) works on a chosen game  
executable: pick the game's `.exe` (its folder becomes the game directory;  
a `Data` folder is not required), then choose one of the methods from the  
dropdown — write `$DEBUG=true` as the first line of Main's `pbCallTitle`,  
strip `$DEBUG` conditions (F9 / party Debug / walk-through-walls), inject a  
SPECIAL-key hook, inject into `pbRepel` (set `$DEBUG` or open the debug  
menu), or generate a **debug launcher (test)** that starts the game in  
debug mode without modifying the game itself. Method ⑥ is the only one  
that needs no `Data` folder; it uses an in-memory patch for RGSS (v16–v18)  
or `Game.exe debug` + a `preloadScript` in `mkxp.json` for mkxp-z  
(v19–v21.1), and fills in empty placeholder `Data/*.dat` / `pbs/*.txt`  
files so debug mode does not trigger a full recompile.

The game-localization sub-pages have a file-checklist sidebar on the right  
("Single file" / "Whole folder"); menu 1 uses a game-folder picker instead  
(it must contain a `Data` folder and an `.exe`); menus 4 / 7 have an  
"Adaptation" sidebar listing what changed after switching provider.

Command-line menu:

```
1. Extract / compile text (extract text / compile text / Chinese plugin)
2. Translate
3. Re-translate check report
4. Re-translate after terminology update
5. Prefix dictionary (view / apply)
6. Line rewrap
7. Terminology dictionary (Excel to terms / view & edit dictionary)
8. Settings
9. Local model server (Ollama / llama.cpp / LM Studio)
10. Enable DEBUG (check engine / write $DEBUG=true)
11. Log / environment check
0. Exit
```

Menus 3 / 4 / 5 ask for "single file / whole folder" first.

### Create Desktop Shortcut (Optional)

Double-click `创建桌面快捷方式.vbs` (Create Desktop Shortcut.vbs).  
A shortcut named *Pokémon Fan Game Translation Tool* will be created on your desktop.

### Translation Workflow

1. Select `1` → choose source/target languages → a file dialog opens to pick the `.txt` file
2. Wait for translation to finish; output is written to `<filename>_translated.txt`
3. A check report is generated next to the output file: `<filename>_translated_report.txt`
4. If problems remain, select `2` to auto re-translate the untranslated lines, or fix manually

### Re-translate Check Report (Menu 3)

Runs a fresh check on the output file, then:

- Auto re-translates lines marked as **Untranslated** or **Suspected untranslated**
- Only reports **Symbol mismatch** and **Special lines** — these are not auto-fixed  
  (symbol mismatches usually mean the model dropped a control code; retrying rarely helps)

Only the affected cache entries are deleted, so re-translation is fast.

#### Editing a translation by hand

Double-click any row in the report list: the top box shows the **source** (read-only,  
for reference) and the bottom box the **translation** (editable). Saving writes the  
line into the translation cache and files it under the "已编辑" (edited) kind, which  
is **never** overwritten by re-translation.

That alone does **not** touch the already-generated `*_translated.txt`. To push your  
edits into the output file, click **"应用已编辑" (Apply edits)** next to "Copy list":

- every entry of `<cache>_edited.json` is written back into the translation cache;
- the translation file is rewritten **in place** — only the edited lines change,  
  every other line stays byte-identical (line endings included);
- lines whose source text no longer matches (e.g. after manual rewrapping) are  
  skipped and reported in the log; a missing translation file only updates the cache.

So the order is: **edit lines → "Apply edits" → (optionally) "Refresh report"**.

#### Resolving term conflicts

A term conflict means the model translated a term differently from the terminology  
list (e.g. the list says `Pikachu = 皮卡丘` but the model wrote 皮卡揪). Conflicts are  
recorded in `<input>_conflicts.json` while translating; the **"解决术语冲突"  
(Resolve term conflicts)** button on the report page is enabled once there are any.


It opens a dedicated view that fills the main area (the file panel on the right stays
put):

- **Top**: the conflict list — `术语原文` (term) / `已有译文` (list translation) /
  `新增译文` (model translation) / `状态` (status).
  There are only two states, `待解决` (pending) and `已编辑` (edited); pending rows come
  first and edited ones are shown in green at the bottom. **Clicking the `状态` cell
  toggles the state by hand** (no sentence edit required) and writes it back at once.
- **Bottom**: the sentences that hit the selected term (`原文` + the sentence's
  current cached translation).
- **"编辑译文" (Edit translation)** — or double-clicking a sentence — opens a dialog
  with the **source read-only** on top and an **editable translation** below. On
  "确定并保存" (Save) it:
  1. writes the new translation into the cache of the file that sentence belongs to
     (and into `<cache>_edited.json`, so the report files it under "已编辑");
  2. marks that term **已编辑** and moves its row to the very bottom of the list.
- Click **"应用已编辑" (Apply edits)** in the top-right corner to push the change into
  the generated `*_translated.txt` as well; at the same time every **已编辑** conflict is
  deleted from `<input>_conflicts.json` (the view returns to the report automatically
  once the record is empty). Pending ones stay in the list.
  **"返回报告" (Back to report)** just leaves the view without applying anything.

> This flow only edits **sentence translations**; the terminology list is untouched.
> To change the term itself, use the term dictionary page (menu 7).
> If the conflict content changes later (the model returns yet another translation),
> the "已编辑" mark is cleared automatically; an identical conflict keeps it.

#### Line rewrapping (Menu 6)

Pick the translation `.txt` files on the right, hit **Refresh list**, then select the
blocks to rewrap in the left list (Ctrl / Shift for multi-select, or `[全选]`). With
**"仅重排选中的区块" (only selected blocks)** checked — the default — blocks you did
not select are left untouched, byte for byte. Use the two parameter sets (lower/upper
char count + minimum gap) for `[map*]` blocks (`\n`) and for all other blocks
(spaces). With nothing selected, the tool asks before falling back to "all blocks".

Rewrapping only rearranges line breaks and spaces: it never changes the translated
text and never calls the model, and running it twice with the same settings is a no-op.

### Term Extraction (Game localization → Term extraction)

Reads the proper nouns out of the game's exported name files (`ITEM_NAMES` /
`MOVE_NAMES` / `TYPE_NAMES` / `POKEMON_NICKNAMES` …, or any file whose leading
`[number]` block is a name block), sends them to the model, and writes the
resulting `source → translation` pairs into the AUTO block of `term_dict.py`.

**It is the regular translation pipeline**, just doing a different job:

- it runs the exact same pipeline as Translate (menu 2) over the name files,
  producing ordinary `*_translated.txt` files, ordinary translation caches
  (`*_cache.json`) and check reports;
- so **resume-from-cache, whole-sentence term substitution and injecting hit
  terms into the prompt all work exactly as usual**;
- the only difference is *when* the terminology list is updated: **after every
  batch** those `source → translation` pairs are merged into the `term_dict.py`
  AUTO block via `auto_terms.merge_into_term_dict()` and the list is reloaded
  immediately, so **later batches of the same file use the new terms right
  away**; a final whole-file merge runs at the end as a safety net (already
  merged entries are not counted twice).

Resuming and resetting the cache work just like ordinary translation (delete the
corresponding `*_cache.json` to re-translate).

#### Term check report (no model calls for edits; re-translation does call the model)

Buttons to the right of "Start extraction & translation" on the term
extraction page:

| Button | What it does |
| --- | --- |
| Check report | Reads only the translation cache and the terminology list and classifies every entry into one of four mutually exclusive kinds, in this order — empty translation, untranslated (echoed source), leftover English in the translation, likely machine-translation leftovers — plus the additive same source/different translation — into `<target>_terms_check.txt`. The page filters by problem kind; **double-clicking the translation column edits a translation**, and "Apply" writes the changes into (1) the translation cache, (2) the name file's translated file, and (3) the AUTO block of the terminology list, with per-edit undo. **Editing a translation / "Apply" do not call the model.** |
| Re-translate terms | For the rows currently shown after filtering: (1) deletes their keys from the translation cache, (2) re-runs the normal translation pipeline (re-parse, whole-sentence term lookup, term injection into the prompt, batched model calls), (3) merges each batch's new translations into the AUTO block of the terminology list and reloads it, exactly like the extraction page. **This one does call the model.** |

> Name files (`*_NAMES`, or any file whose leading `[number]` block is a name
> block) belong to term extraction only: translate / re-translate report /
> terminology re-translation / line rewrap all skip them
> automatically, and the file panels no longer list them.

#### Translation workflow (red text on the right of the Game-localization page)

1. Term extraction — every file to translate goes through term extraction first
2. Term fix — check the terms for omissions or mistranslations
3. Translate — translate the non-term files
4. Re-translate check report — fix the problematic sentences
5. Check terms — see whether any term needs updating, and fix the related sentences
6. Review the prefix dictionary — only `\tg[]` contents are translated
7. Line rewrap — re-wrap the sentences
8. When everything is translated, delete the auto-extracted terms in 8. Terminology dictionary

> **Translate page (menu 2) toggles**: to the right of "term hit statistics" there is an "auto shut down after translation" option (off by default) — when translation finishes successfully it schedules shutdown after 60 seconds, cancelable with `shutdown /a`.


### Terminology List

Prepare an Excel file where each sheet has language column headers (e.g. `English`, `Simplified Chinese`).
You can also use mine:

| Pokédex No. | English | Simplified Chinese |
|-------------|---------|-------------------|
| 1 | Bulbasaur | 妙蛙种子 |
| 2 | Ivysaur | 妙蛙草 |

Select menu `3` → choose the Excel file → choose source/target languages → `term_dict.py` is generated automatically.

#### Whole-sentence terms (on by default)

When a line is exactly a term (for example `Defensa X`, `¡Defensa X!` or `(?)`),
no model call is needed: before translating, the tool checks the terminology list
and, on a hit, writes the term's translation straight into the cache.

- Only **hand-maintained** terms participate — entries the translation run
  auto-extracted into the `term_dict.py` AUTO block are ignored.
- Leading/trailing punctuation and whitespace are ignored **for matching only**
  and are kept verbatim in the translation: `Yes!` → `是!`.
- Backslashes and `[ ] { } < > @ # ~` are *not* stripped (they build control
  codes / tags, so `[Pikachu]` is never mistaken for a term).
- A term that itself contains punctuation is matched as-is first
  (`(?)` → `神石`), then with the surrounding punctuation stripped.

Toggle: Settings → 「整句术语直译」(`WHOLE_TERM_MATCH`, default on).

### Re-translate After Adding New Terms (Menu 4)

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
- Debug mode: `set DEBUG_PH=1 && python main.py` (source) or `set DEBUG_PH=1 && 宝可梦同人工具.exe`

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

Run menu `3` to auto re-translate, or open `<output>_report.txt` and fix manually.

**Placeholder lost**

The tool retries and falls back automatically. If a line still fails, it is reported in the check report. Fix it manually or add the term to your terminology list.

**exe throws `FileNotFoundError: config.py`**

Make sure you are using the latest release. The tool uses `user_config.json` in exe mode.

**Double-clicking the exe flashes and closes**

Open a Command Prompt in the exe folder and run it manually to see the error:

```cmd
宝可梦同人工具.exe
```

## Building the exe

```bash
pip install pyinstaller
pyinstaller --onefile --name "宝可梦同人工具" --icon=start.ico ^
    --add-data "萝莉体.ttf;." ^
    --add-data "LM操作指南;LM操作指南" ^
    --hidden-import openpyxl --hidden-import tkinter --hidden-import PIL main.py
```

The bundled font (`萝莉体.ttf`) is loaded privately via GDI at runtime, so
the exe works on machines where the font is not installed. If you want to
swap the font, just drop a different `萝莉体.ttf` next to the exe.

`LM操作指南/` (the LM Studio screenshots behind the "操作指南" button on
menu 8) is bundled the same way. Lookup order is **next to the exe →
inside the exe → source tree**, so dropping the folder next to the exe
overrides the built-in copy. Because a one-file exe deletes its unpack
directory on exit, the images are copied to `%TEMP%\pkmn_translator_guide\`
before the viewer HTML is written.

`打包程序.bat` already passes both `--add-data` flags and checks that the
files exist first — a missing font or guide folder only produces a warning.

Then copy `start.ico` next to the produced exe in `dist\`.

## License

MIT