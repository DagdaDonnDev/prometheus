# ⚡ PROMETHEUS
### A Complete Offline AI Companion for Survival, Rebuilding, and Human Connection

> *"The sum of everything a human needs to know to go from nothing to thriving civilization."*

**Completely offline. Completely unlimited. Forever free.**
No internet. No API keys. No subscription. No data leaving your device.
No token limits. No rate limits. No telemetry. No servers. Ever.

---

## What Prometheus Is

A self-contained AI assistant that works when everything else fails. Built for one purpose: if modern infrastructure collapses, this device and this software should be enough to keep you alive, sane, and capable of rebuilding.

- **Talks to you** — voice input and output, feels like a companion not a manual
- **Knows everything** — survival, medicine, electronics, navigation, agriculture, chemistry, rebuilding civilisation from scratch
- **Remembers you** — persistent memory across sessions, knows your name, your situation, your progress, your day count
- **Multiple focused tabs** — Survival, Medical, Electronics, Navigation, Farm, Build, Chemistry, Companion
- **Quick Access panel** — 16 critical one-tap actions, no typing required
- **Situation Assessment** — 5 questions, immediate prioritised action list on first run
- **Skill Tree** — full civilisation rebuild tracker, 55 skills across 8 stages
- **Personal documents** — add your own PDFs, notes, maps as searchable context
- **Printable reference** — 6-page emergency PDF ready to print and laminate
- **Confident where warranted, honest where uncertain** — confidence scoring on all knowledge
- **Automatic backup** — silent backup on every close, auto-restores if files corrupt
- **Runs on anything** — laptop, Raspberry Pi, old Android phone
- **Powers from sunlight** — 5W solar panel sufficient for Raspberry Pi

---

## Quick Start

### Fastest — one script does it all
```bash
# Windows: double-click setup.bat
# Linux / macOS / Raspberry Pi:
bash setup.sh
```
Both scripts check Python 3.9+ and pip, check for Ollama (Windows opens the
download page, Linux/macOS installs it), pull the default model (LFM2.5 1.2B Instruct), install
requirements, index the knowledge base, then offer to launch.
Downloading the full source library (`bootstrap.py`, ~2GB) stays a separate step.

Or step by step:

### 1. Install Ollama
```bash
# Linux/Mac
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: download installer from https://ollama.ai
```

### 2. Get the AI model (default: LFM2.5 1.2B Instruct, ~730 MB)
The model is kept in `prometheus/models`, so the whole app is one folder you
can copy or back up. Downloads straight there:
```bash
python -m core.ollama_local --pull hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest
```
Already pulled it with plain `ollama pull`? Move it in instead (no download;
every file is checked, then the old copy is removed):
```bash
python -m core.ollama_local --move
```

### 3. Install Python dependencies
```bash
python -m pip install -r requirements.txt   # "python -m" installs into the Python that runs Prometheus
```

### 4. Download all source materials (one time, needs internet)
```bash
python bootstrap.py
```
Downloads ~1.9GB–1GB of public domain survival manuals, medical references,
and practical guides. Self-deletes after completion.

### 5. Index the knowledge base
```bash
python ingest.py
```
Processes all downloaded sources into the searchable vector database.
Takes 10–30 minutes on first run. Subsequent runs only process new files.

### 6. Run Prometheus
```bash
# Start Ollama (if not already running as a service)
ollama serve &

# Launch Prometheus
python main.py
```

---

## Voice Setup (Optional — Highly Recommended)

Voice changes the experience from tool to companion. One command sets it up
and tests it (`setup.bat`/`setup.sh` run it too):
```bash
python setup_voice.py            # install what's missing, then test
python setup_voice.py --check    # only report, no downloads
```
1. Installs **faster-whisper** (listening) and **sounddevice** (microphone)
   into the Python you ran it with.
2. Downloads the Whisper model into `models/whisper/` (tiny ≈ 75 MB, once;
   offline after).
3. Finds **Piper** (speaking), or downloads the release program into
   `prometheus/piper/`. It also looks on your PATH, in `prometheus_setup/`,
   and at `PROMETHEUS_PIPER`. (`piper-master` is Piper's source code and
   can't speak.)
4. Checks `voices/`: one folder per voice, each with the model and its config.
   If it's empty, it copies voices it finds in `prometheus_setup/`.
   ```
   voices/
   ├── Vasco/   en_GB-…-medium.onnx  +  en_GB-…-medium.onnx.json
   └── Data/    en_US-…-medium.onnx  +  en_US-…-medium.onnx.json
   ```
   The folder name is the voice name shown in ⚙ Settings. More voices:
   https://huggingface.co/rhasspy/piper-voices
5. **Tests it end to end:** Piper says a sentence and Whisper writes down
   what it heard. Then it lists your microphones.

If something's missing it says exactly what to do (e.g. the Visual C++
Redistributable on Windows, `libportaudio2` on Linux, or a Python version
faster-whisper doesn't support yet).

**How speech plays:** one Piper process stays loaded for the whole session,
replies are spoken in whole sentences, and the next sentence is made while
the current one plays, so there are no gaps. The first piece can end at a
comma so the voice starts quickly. Markdown (`**`, `#`, bullets) isn't read
out. Playback uses Windows' built-in sound on Windows, and `aplay`/`paplay`
(Linux) or `afplay` (macOS) elsewhere.

**Talking to it**

| Do | What happens |
|----|-------------|
| **Hold the send button** ➤ | It listens while you hold (the button turns red ●). Let go and what you said is sent |
| **Click the 🎤** | Voice conversation: it listens (🎤 turns red), sends when you pause, speaks the reply, then listens again. Click 🎤 again to end it |
| **While it's talking** | The 🎤 becomes a **black square**: click it to stop the voice (the reply text still finishes) |
| **Talk over it** (in a voice conversation) | It stops talking and listens. While it's talking you need to be clearly louder than its voice for a moment, so its own sound from your speakers doesn't count. Headphones make this most reliable |
| **Escape / ⏹** | Stops the voice and the reply, and ends a voice conversation |

It decides you've finished when you've been quiet for about a second. The
first third of a second sets the room's noise level, so a fan or traffic
doesn't count as talking.

**Whisper model size** (Settings → Voice → Whisper model) — the listening
model, not the voice:

| Size | Download | Speed on a CPU | Accuracy |
|------|----------|----------------|----------|
| tiny | ~75 MB | fastest (well under a second for a short sentence) | fine for clear speech in a quiet room; trips on accents, noise, names |
| base | ~145 MB | about 2× slower than tiny | noticeably fewer mistakes — the best all-round pick |
| small | ~485 MB | about 4× slower than base | good with accents and background noise |
| medium | ~1.5 GB | slow on a CPU (several seconds) | best, but too slow to feel like a conversation without a GPU |

After changing it, run `python setup_voice.py` once to download that size
for offline use.

Voice input works once speech recognition has loaded; hover the 🎤 to see why
if it doesn't.

---

## App icon
Save the icon as **`assets/icon.png`** (square, 512×512 or larger). It's
used for the window and taskbar, next to the name in the header, the Windows
`.exe` (`build_exe.py` makes `icon.ico`/`icon.icns` from it; needs
`pip install pillow`) and the Android app icon and launch screen.

## Building Executables

### Windows / Linux / macOS — Single EXE
```bash
pip install pyinstaller
python build_exe.py              # single .exe (default)
python build_exe.py --onedir     # folder build (faster startup)
python build_exe.py --clean      # clean previous build first
```
Output: `dist/Prometheus.exe` (~150–300MB, self-contained).
Knowledge base, voices, and memory sit alongside the exe — not bundled inside —
so you can update knowledge without rebuilding.

### Android APK — same app, built with Qt for Python (shiboken6)
The phone runs the same `main.py`, `core/` and `ui/` as desktop, so every
feature and fix lands on both. On a phone the layout switches automatically:
the header and tabs scroll sideways, ◀ Info swaps the chat for the situation
panel, dialogs open full screen, and the verdict buttons sit in a 2×2 grid.
Preview it on desktop with `PROMETHEUS_PHONE_LAYOUT=1 python main.py`.

You need the PySide6 and shiboken6 **Android wheels** (e.g.
`PySide6-6.x.y-…-android_aarch64.whl`), the same version as the PySide6
installed on the build computer, plus JDK 17. The Android NDK/SDK are
fetched by the deploy tool if you don't give them.

```bash
# Linux or macOS (on Windows use WSL2)
python build_apk.py --setup                        # first time only
python build_apk.py --debug --wheels ~/qtwheels    # folder with both wheels
python build_apk.py --install                      # push to a phone via ADB

# Emulator instead of a real phone:
python build_apk.py --debug --wheels ~/qtwheels --arch x86_64

# Build on GitHub instead (free):
python build_apk.py --github   # writes .github/workflows/build_apk.yml
```
Without `--wheels`, it looks in `./wheels`, `~/wheels`, `~/qtwheels`,
`~/Downloads` and `~/.pyside6_android_deploy`.

The APK includes the knowledge base text and the stylesheet. It never includes
`memory/`, so your conversations and personal documents stay off the build.

**On the phone:** run Ollama on a laptop or Pi on the same WiFi and set
Settings → Model → Ollama address (e.g. `http://192.168.1.100:11434`). Start Ollama
with `OLLAMA_HOST=0.0.0.0 ollama serve` so the phone can reach it.
Voice (Piper, Faster-Whisper) is desktop-only for now.

---

## Wikipedia (Optional — Simple English, ~360MB download)

Download `simplewiki-latest-pages-articles.xml.bz2` from
https://dumps.wikimedia.org/simplewiki/latest/ (or let Prometheus fetch it),
keep it in `prometheus_setup/`, then **extract** it — a few minutes:

```bash
python ingest.py --wikipedia prometheus_setup/simplewiki-latest-pages-articles.xml.bz2 --extract-only
python ingest.py --download-wikipedia --extract-only     # same, downloading it for you
```

That also builds the **search index** for the Wikipedia tab (SQLite full-text
search, built in — a minute or two, no AI model), so every article's text is
searchable straight away. For articles you extracted before this existed:

```bash
python ingest.py --wiki-index
```

Indexing for the AI library search as well (`python ingest.py --source
wikipedia`) is optional and takes hours on a CPU. Re-running the extract with a newer dump only
rewrites changed articles and removes deleted ones.

**In chat:** when a message names something with its own article — a film,
show, band, book, person, place — its opening paragraph is given to the model
(by title, in milliseconds), and the reply says *From: Wikipedia — Title*.
"have you seen inception?" finds *Inception (film)*. Everyday words don't
count: "I watched a movie yesterday" pulls in nothing. Never used in the
Medical tab or for step-by-step/diagnosis questions.

**The Wikipedia tab** (second tab): finds anything in Wikipedia — a title, a
name, a phrase, a few words that appear anywhere in an article. Exact titles
come first, then the best matches, each with the matching text as its preview.
Read whole articles, and **Ask about this** to talk about one in the chat tab.

- Only real articles are kept — no talk/user/project pages, redirects or stubs
  under 100 words.
- Keep dumps **outside** `knowledge_base/`: the desktop build copies that folder
  next to the exe. `knowledge_base/wikipedia/` isn't committed.

---

## Knowledge Sources

`bootstrap.py` downloads all of these automatically. All are public domain or explicitly free to reproduce.

### Tier 1 — Critical (Downloaded Automatically)
| Source | Domain Folder | License |
|--------|--------------|---------|
| Where There Is No Doctor | `where_no_doctor/` | Free to reproduce (Hesperian) |
| Where There Is No Dentist | `where_no_dentist/` | Free to reproduce (Hesperian) |
| US Army Survival Manual FM 3-05.70 | `army_fm_3_05_70/` | Public Domain |
| US Army First Aid FM 4-25.11 | `medical/` | Public Domain |
| US Army Field Hygiene FM 21-10 | `medical/` | Public Domain |
| Nuclear War Survival Skills (Kearny) | `nuclear_survival/` | Public Domain |
| US Army Water Supply FM 10-52 | `water_purification/` | Public Domain |

### Tier 2 — Important (Downloaded Automatically)
| Source | Domain Folder | License |
|--------|--------------|---------|
| Practical Blacksmithing Vol 1–3 (1889) | `blacksmithing/` | Public Domain |
| Farm Mechanics (1922) | `farming/` | Public Domain |
| Canning and Preserving (1914) | `food_preservation/` | Public Domain |
| Fermentation and Home Production (1900) | `food_preservation/` | Public Domain |
| Henley's Twentieth Century Formulas (1916) | `chemistry/` | Public Domain |
| Soap Making Past and Present (1908) | `soap_making/` | Public Domain |
| Electricity for the Farm (1915) | `electronics/` | Public Domain |
| American Medicinal Plants (1892) | `plants_temperate/` | Public Domain |
| Edible Wild Plants (1939) | `plants_temperate/` | Public Domain |
| Plumbing and Sanitation (1908) | `build/` | Public Domain |
| Navigation and Nautical Astronomy (1918) | `navigation/` | Public Domain |
| Boy Scout Handbook (1911) | `survival/` | Public Domain |
| Art of Travel — Galton (1872) | `survival/` | Public Domain |
| + 15 more sources | various | Public Domain |

### Pre-Populated Knowledge (No Download Needed)
Included in the repository:

| Folder | Contents |
|--------|---------|
| `scientific_reference/` | 8 files of universal laws and constants — physics, electronics, chemistry, mechanics and materials, navigation, mathematics, computer science, constants. The anchor source for the Training Path. |

Hand-written guides (committed — `.gitignore` keeps every `.md` in a domain
folder and leaves downloaded books out):

| Folder | Contents |
|------|---------|
| `water_purification/` | Ceramic pot filter, bio-sand filter, solar still, SODIS, chemical treatment — full build instructions |
| `emergency_medicine/` | Trauma, bleeding, fractures, burns, shock, wound closure, childbirth, improvised medicines |
| `navigation/` | Polaris method, shadow stick, watch method, Southern Cross, terrain reading, distress signals |
| `soap_making/` | Complete lye extraction from wood ash, saponification process, troubleshooting |
| `food_preservation/` | Lacto-fermentation, vinegar, beer from grain, wine, mead, distillation with full methanol safety guidance |
| `companion/` | Psychology of isolation, Frankl, Stoicism, Camus, grief processing, practical mental health tools |

---

## Adding Your Own Documents

Click **📎** in the header to open the personal document manager.

Drag and drop or pick files — they are indexed and searched automatically
alongside the main knowledge base in every query.

**Supported formats:** PDF, TXT, MD, DOCX, HTML, CSV, JSON, PNG/JPG (OCR requires tesseract)

Good candidates:
- Medical records, prescriptions, allergy information
- Local maps (photographed or scanned)
- Personal notes and guides specific to your location
- Contacts, radio frequencies, local knowledge

Personal documents are stored in `memory/personal_docs/` and indexed
in a separate ChromaDB collection — fully independent from the main library.

---

## Features Reference

### Tabs
| Tab | Focus |
|-----|-------|
| 💬 Prometheus | Chat — talk about anything (first tab, opens by default) |
| 📖 Wikipedia | Search and read the offline Wikipedia |
| 🔥 Survival | Water, fire, shelter, food, immediate threats |
| ⚕️ Medical | Procedures, triage, improvised medicine, wound care |
| ⚡ Electronics | Circuits, salvage, power generation, radio, solar |
| 🌍 Navigate | Location finding, star navigation, terrain, weather |
| 🌱 Farm | Agriculture, food preservation, fermentation, animals |
| 🔧 Build | Construction, tools, fabrication, blacksmithing |
| ⚗️ Chemistry | Metallurgy, materials, synthesis, soap, explosives |
| ➕ Custom | Create tabs for your specific situation |

### Training Path — working things out from first principles
In the ⚡ Electronics, ⚗️ Chemistry, 🔧 Build and 🌍 Navigate tabs, "explain"
and "should I / which is better" questions first try to **derive** the answer
instead of looking it up.

- 38 concepts in a 3-tier graph: tier 1 laws (Ohm's law, F = ma, PV = nRT,
  Earth's rotation…) are locked; tier 2 is one step from a law (P = VI,
  Kirchhoff's laws, n = m/M, σ = F/A, latitude from Polaris…); tier 3 builds on
  tier 2 (voltage divider, stoichiometry, beam bending, great-circle distance…).
- **Anchor rule:** every derivation must rest on text found in
  `knowledge_base/scientific_reference/`, never on the model's memory. If the
  law is missing from the library, Prometheus says so and answers from the
  library instead.
- The model is asked for three independent methods. Each is checked: the result
  must have the right form, must be reached rather than stated up front, must use
  a given foundation, and must not contradict a tier-1 law.
- **You're never asked to check its work.** Its own three-way check decides:
  all three agree → learned; two of three → partly; fewer → not trusted, and the
  answer comes from the library instead with "I haven't been trained on … yet".
  Contradicting a law puts the concept on hold and lowers trust in everything
  built on it.
- While it works, the chat shows **🔍 Researching \<topic\>…**. If a tier-3
  question needs building blocks it hasn't learned (up to three), it works those
  out first and names each one as it goes.
- If a calculation needs numbers you didn't give, it asks for them.
- Learning is saved in `memory/training/` and included in backups.

### The chat tab
Talks like a real person, not a counsellor or a performer: calm, plain,
curious, has opinions, no gushing. **Tone is read from each message** — annoyed,
low, excited, asking, or neutral (wording, CAPITALS, "!!", emoji, and what you
said just before) — and the model is told how to sound for that one reply:
short and direct when you're annoyed, quiet when you're low, into it when
you're excited. "mhm" is a valid reply. When corrected it says "my mistake" and
moves on. If you ask about a film, book or person it has no article on, it says
so ("I don't have The Juror in my database") instead of making something up.
That holds through follow-ups that don't repeat the name ("go into the lore",
"tell me more", "their missions") until you change the subject. When it does
have an article, it's told that's all it has, and to say so rather than fill in.

### What it remembers about you
When you mention something about yourself — "my sister Kate", "my dog is
called Max", "I live in Cork", "I work as a nurse", "I love hiking", "I hate
mornings", "my favourite film is Inception", "I know how to tie knots" — it's
noted, and the status bar says what (**Remembered: Kate is your sister**).
It only picks up plain statements like these; it never guesses.
The chat tab uses this to talk to you as someone it knows, and knows the
topics of your last few chats in that tab (titles only, so a new chat still
starts fresh). See and fix all of it in **Settings → You** (work, people and
pets, likes, dislikes, notes) or in Obsidian's `Me` note (below).

### Obsidian — a map of you, and your notes as a source
[Obsidian](https://obsidian.md) is a free notes app that keeps everything as
plain files in a folder (a "vault"). In **Settings → Obsidian**, choose your
vault folder and press **Update now**. Prometheus adds a `Prometheus` folder:

| Note | What it is |
|------|-----------|
| `Me` | What it knows about you, as properties (name, location, work, people, likes, dislikes, skills, notes). **Edit them in Obsidian** and the changes come back into the app, merged with anything it learned meanwhile |
| One per tab (`Survival`, `Medical`…) | That tab's mind map: links to its chats and the topics in them |
| `Chats/…` | Each chat, linked to its tab, its topics and any of your notes it mentioned |
| `Topics/…` | A topic (water purification, first aid, a film…) linked from every chat that touched it |

Open **Graph view** in Obsidian to see it: Me → tabs → chats → topics.
It updates by itself when you close Prometheus, and only rewrites notes that
changed. A chat note you've edited is never deleted.

**Your own notes** (everything outside the `Prometheus` folder) are never
changed. With "Use my other notes as a source" ticked, the knowledge tabs
search them alongside the library (not for medical or strict questions), and
the chat tab reads a note when you mention it by name — "is my Sourdough
Starter ok?" — shown as **Obsidian — Sourdough Starter** under the answer.

### Chats
Every tab keeps its own list of chats in the **Chats** bar on the left
(the header's **Chats** button shows or hides it; on a phone it swaps the
conversation for the list).
- **+ New chat** starts an empty conversation. It sees none of your earlier
  chats, so an old topic can't steer it.
- **Search chats** matches titles and everything said in them.
- Click a chat to go back to it. Right-click to **Rename** or **Delete** it.
- A chat is named after its first message and saved as you go.
- More ▾ → Reset → **Clear this chat** empties only the open chat;
  **Clear all chats in every tab** removes them all (a backup is made first).

### Messages
- **Up** in an empty message box brings back what you sent before (Down goes
  forward again) — edit it or just press Enter to send it again.
- Hover a message (phone: always shown) for **⋯**, or right-click it:
  **Copy**, **Edit** (your messages — sending replaces it and everything after
  it; Esc cancels), **Retry** (the last reply) and **Delete**.

Anything about suicide or self-harm, in any tab, switches to a calm, direct
crisis response that asks whether you're safe and points you to a real person.

### Settings → Assistant
Change the assistant's **name** (header, chat tab, and what the model calls
itself) and its **personality** in plain words, e.g. "a calm old sailor who
doesn't rush you". The knowledge tabs stay factual whatever you choose.

### Sources and pictures
Under each library answer: **From:** the book and page it drew on, and the
page itself as a picture (click for full size). Pages are rendered by
`ingest.py` for PDFs in the medical, plant, survival, build, electronics,
navigation and farming folders — re-run `python ingest.py` after adding PDFs.
PDFs indexed before their folder had pictures are redone once, automatically,
on the next `python ingest.py` (you'll see "↻ adding page pictures").

### Follow-up questions
"why?", "yes but why", "are you sure?" and other short follow-ups keep the
sources of the answer they're about, and the model is told to explain its
reasoning from them — or say plainly if the sources don't back it up.

### Speed
On Windows, "localhost" used to add about **2 seconds to every request**:
Python tries IPv6 first, Ollama only listens on IPv4, and Windows waits before
falling back. Prometheus now always talks to `127.0.0.1` for a local Ollama
(your setting can still say localhost).

A reply also waits for the model to read its instructions before the first word.
These are now small: about 250 tokens for the chat tab (was ~2,600) and about
1,500 for knowledge tabs (was ~3,300; library passages are trimmed to the part
that matches your question). The model is kept loaded for 30 minutes, warmed up
at startup, and always run with the same context size, so Ollama never reloads
it between messages. Hover a reply's timing stamp, or open the Developer panel's
Patterns tab, to see where the time went: preparation, model load, reading the
prompt (with its size), and writing.

### Speak-start timing
Replies stream straight into the voice, so you hear an answer as soon as the
first words arrive. Each reply shows a small stamp, e.g. `↳ 🔊 420ms  ✓ 1830ms`:
🔊 is speak-start (the number that matters), ✓ is full completion.

### Dev Panel (Ctrl+D)
- **Live Traces** — every query: mode (left bar colour), lookup or derive,
  sources, 🔊 speak-start (bar: green under 500ms, amber under 800ms, red above),
  ✓ full time, tab.
- **Patterns** — averages and rates, flags speak-start above 800ms.
- **Eval** — runs the 22 decision-layer checks and the 19 Training Path tests.
- **Training** — every concept, its tier, confidence, and status; release a
  concept that is on hold.

### Keyboard
| Key | Action |
|-----|--------|
| Enter | Send |
| Shift+Enter | New line |
| Escape or ⏹ | Stop the current answer immediately |
| Ctrl+D | Dev Panel |

### Getting around
Prometheus opens in the **Prometheus** (companion) tab with the cursor in the
message box, so you can just start typing. There's no popup on first launch.

Every empty tab shows what it's for and a few questions you can tap. The
Survival tab also offers the optional 5-question **Situation check**.

| Control | Function |
|---------|---------|
| **Quick help** (tab bar, left) | 16 one-tap questions for urgent situations |
| **Situation check** | 5 questions → a numbered priority list |
| **Skills** | Civilisation rebuild tracker (55 skills, 8 stages) |
| **Map** | Offline world map (run `bootstrap_map.py` for map data) |
| **Chats** | Show or hide this tab's chats (new, search, switch) on the left |
| **Info** | Show or hide your situation panel. It starts hidden until there's something in it |
| **Settings** | You (what it knows about you), assistant, model, voice, Obsidian |
| **More ▾** | Personal documents · Print emergency reference · Reset · Developer panel (Ctrl+D) |

On a phone, Situation check, Skills and Map move into **More ▾**.

### Where the model lives
Once `prometheus/models` has a model in it, Prometheus starts its own Ollama
for it in the background (port 11435) and stops it when you close the app.
An Ollama app already running on your PC isn't touched, and the two don't
clash. If `prometheus/models` is empty, Prometheus uses your normal Ollama as
before.

| Command | Does |
|---------|------|
| `python -m core.ollama_local --move` | Move the models Settings uses from Ollama's usual folder into `prometheus/models` |
| `python -m core.ollama_local --pull <name>` | Download a model straight into `prometheus/models` |
| `python -m core.ollama_local --list` | What's in `prometheus/models` |

If `--move` says the old copy is still in use, quit Ollama (tray icon → Quit)
and run it again to free the space.

### Choosing the model
Settings → Model has one box for the knowledge tabs and one for the companion
tab. Each lists the models installed in Ollama, and you can type any other name
(get it first with `python -m core.ollama_local --pull <name>`). **Check Ollama** tests the address
you've typed. Changes apply as soon as you save; no restart needed.

If Ollama isn't reachable, the status bar says so in plain words and checks
again every 10 seconds, so starting Ollama after Prometheus is fine. If a model
isn't installed, it shows the exact `ollama pull` command to run.

### Quick Access Panel
16 pre-wired critical actions across 4 sections. Tap any button — it navigates
to the correct tab and fires the query automatically. No typing needed.

- **Survival:** Water, Fire, Shelter, Food
- **Medical:** Bleeding, Fever, Fracture, Infection
- **Navigation:** Find North, Where Am I, Signal, Weather
- **Build & Resources:** Power, Tools, Soap, Ferment

### Situation Check
5 questions, whenever you want them (header → Situation check, or the card in
an empty Survival tab):
surroundings → temperature → injury → companions → supplies.
Generates a numbered, prioritised action list specific to your exact situation.
Tapping any priority opens the relevant tab.

### Skill Tree
55 skills across 8 rebuild stages with prerequisite dependencies:

```
Stage 0 — Immediate Survival    Stage 1 — Stone Age
Stage 2 — Neolithic             Stage 3 — Bronze Age
Stage 4 — Iron Age              Stage 5 — Medieval
Stage 6 — Industrial            Stage 7 — Electrical Age
```

Completing skills unlocks dependent ones. Progress saved persistently.

### Confidence Scoring
Every knowledge chunk is scored 0–100 based on source reliability.
Sources ranked: field-tested manuals > historical practical > synthesis > Wikipedia.
Critical queries (medical, water, poison, radiation) require two independent
source confirmations. Model explicitly told when confidence is low.

### Automatic Backup
On every close: silent backup to `memory/backups/`. Keeps last 30 backups.
On startup: validates all JSON files — auto-restores from latest clean backup
if any file is corrupted. ~5MB total backup footprint.

### Rolling Conversation Summaries
History never fills the context window. When any tab exceeds 20 messages,
the oldest 10 are summarised by the model and compressed into a single paragraph.
Effectively unlimited conversation memory per tab.

---

## Raspberry Pi Setup

```bash
# Install Ollama (ARM build)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF

# Install Python dependencies
python3 -m pip install -r requirements.txt --break-system-packages

# Auto-start on boot — add to /etc/rc.local before exit 0:
# ollama serve &
# sleep 5 && cd /home/pi/prometheus && python main.py &
```

Power: ~5W idle on Pi 5. A 20W panel + 10,000mAh bank runs it all day.
For a go-bag device, add a small e-ink or sunlight-readable screen.

---

## System Requirements

| | Minimum | Recommended |
|-|---------|-------------|
| RAM | 4GB | 8GB |
| Storage | 4GB free | 16GB free |
| CPU | Any 2015+ | Any 2018+ |
| OS | Linux, Windows, macOS | Linux |
| Python | 3.9+ | 3.11+ |

---

## Storage Breakdown

| Component | Approximate Size |
|-----------|-----------------|
| LFM2.5 1.2B Instruct (via Ollama, default) | ~730MB |
| Faster-Whisper Tiny STT | ~75MB |
| Piper TTS voice | ~100MB |
| Sentence-transformers embedding model | ~90MB |
| ChromaDB vector index | ~1.9GB+ |
| Knowledge base (after bootstrap + ingest) | ~1.9GB–2GB |
| App code + UI | ~2MB |
| **Total typical | ~5GB** |

---

## Ingest Reference

```bash
python ingest.py                                  # index all new files
python ingest.py --rebuild                        # clear and reindex everything
python ingest.py --source medical                 # one domain only
python ingest.py --stats                          # knowledge base statistics
python ingest.py --wikipedia FILE.xml.bz2         # ingest Wikipedia XML dump
python ingest.py --wikipedia FILE.xml.bz2 --max-articles 50000
python ingest.py --init                           # create folder structure only
```

**Upgrading from v19 or earlier:** run `python ingest.py` once. It indexes the new
`scientific_reference/` folder (needed by the Training Path) and, with the v22
cleaner, keeps formulas intact (`=`, `+`, `×`, `²` used to be stripped). For the
formula fix to apply to sources indexed earlier, run `python ingest.py --rebuild`.

Re-running `ingest.py` keeps the index matching the folder:
- an edited file's old entries are replaced, not duplicated;
- a deleted file's entries are removed;
- the same file under two names (same contents) is indexed once — otherwise one
  book would count as two independent sources. Delete the extra copy to stop the
  warning.

---

## Project Structure

```
prometheus/
├── main.py                    # Entry point
├── setup.bat / setup.sh       # One-step install (Windows / Linux, macOS, Pi)
├── bootstrap.py               # One-time downloader (self-deletes after use)
├── bootstrap_map.py           # Offline map data downloader
├── ingest.py                  # Knowledge base indexing pipeline
├── generate_reference.py      # Printable emergency PDF generator
├── build_exe.py               # EXE builder (Windows/Linux/Mac)
├── build_apk.py               # APK builder (Android, pyside6-android-deploy)
├── requirements.txt
├── README.md
├── CLAUDE.md                  # Working notes for AI-assisted development
│
├── core/
│   ├── pipeline.py            # Decision layers in one place (no UI code)
│   ├── wiki_lookup.py         # Wikipedia by title (chat background, Wikipedia tab)
│   ├── wiki_index.py          # Full-text search over every article (SQLite FTS5)
│   ├── tone.py                # Reads the tone of each chat message
│   ├── embedder.py            # One shared text-embedding model, offline once cached
│   ├── platform_info.py       # Android / phone-layout detection
│   ├── intent_router.py       # 10 intents, domain tiers, Training Path flag
│   ├── rag.py                 # Tiered knowledge search, image lookup
│   ├── sufficiency_gate.py    # SUFFICIENT / WEAK / CONFLICTING / NONE
│   ├── contradiction.py       # Opposing-claim and numeric conflict checks
│   ├── decision_gate.py       # EMERGENCY / SAFE_MODE / CLARIFY / CAUTIOUS / DIRECT
│   ├── llm_bounds.py          # Per-tab constraints, companion personality
│   ├── memory_filter.py       # Only the most relevant memory goes in the prompt
│   ├── llm.py                 # Ollama streaming, intent temperatures, prompt order
│   ├── tracer.py              # Query traces, speak-start + full timing
│   ├── eval_harness.py        # 22 deterministic decision-layer checks
│   ├── training/              # Training Path
│   │   ├── axiom_seeds.py     #   38 concepts: laws, direct and composite results
│   │   ├── graph.py           #   Confidence DAG, caps, quarantine, lemmas
│   │   ├── engine.py          #   Anchors, derivation, checks, gap types
│   │   └── session.py         #   Your verdicts, trusted-result promotion
│   ├── backup.py              # Automatic backup and restore
│   ├── confidence.py          # Source confidence scoring + redundancy checking
│   ├── config.py              # Settings, model per tab
│   ├── context_manager.py     # Rolling conversation summaries
│   ├── map_engine.py          # Offline maps, biome and resource context
│   ├── memory.py              # Persistent user state
│   ├── p2p.py                 # Local-network messaging (off — core/features.py)
│   ├── features.py            # Feature switches (P2P_ENABLED = False)
│   ├── stt.py                 # Faster-Whisper speech-to-text
│   ├── tabs.py                # Tab definitions and management
│   ├── tts.py                 # Piper text-to-speech (streaming)
│   └── voice_manager.py       # Voice model management
│
├── ui/
│   ├── main_window.py         # Window, query fork, both paths
│   ├── layout_helpers.py      # Desktop vs phone dialog sizing
│   ├── workers.py             # LLMWorker, TrainingWorker, InitWorker
│   ├── chat_view.py           # Messages, timing stamp, "Researching…" line, sources + page images
│   ├── welcome.py             # Empty-tab welcome panel
│   ├── wiki_search.py         # Wikipedia tab: search, read, ask about it
│   ├── dev_panel.py           # Ctrl+D observability
│   ├── assessment.py          # Situation assessment mode
│   ├── doc_context.py         # Personal document manager
│   ├── input_bar.py           # Text and voice input, stop button
│   ├── map_view.py            # Offline map
│   ├── messages_view.py       # Local-network messages
│   ├── quick_access.py        # 16-button critical action panel
│   ├── settings_dialog.py     # Settings dialog
│   ├── sidebar.py             # Situation panel
│   ├── skill_tree.py          # Civilisation rebuild tracker
│   ├── style.qss              # Dark amber theme
│   └── tab_bar.py             # Tab navigation
│
├── tests/
│   └── test_training.py       # python -m unittest discover tests
│
├── knowledge_base/            # Populated by bootstrap.py + ingest.py
│   ├── scientific_reference/  # In the repo — Training Path anchors
│   ├── [28 more domain folders]
│   └── wikipedia/             # Optional — populated separately
│
├── voices/                    # Piper voice models (.onnx + .json)
│
└── memory/                    # Auto-created on first run
    ├── config.json
    ├── user_memory.json
    ├── tabs.json
    ├── training/              # graph.json (learning), history.json (attempts)
    ├── query_traces.jsonl     # Every query trace, incl. speak-start
    ├── backups/               # Rolling backups — last 30
    ├── personal_docs/         # Uploaded personal documents
    ├── personal_chroma_db/    # Personal document vectors
    ├── chroma_db/             # Main knowledge base vectors
    └── model_cache/           # Embedding model cache
```

## Debug run (temporary)
Double-click `debug_run.bat`. It runs Prometheus normally. When you close it,
`logs\run_<date>_<time>.log` holds your Python/PySide6/Ollama versions, the
installed and loaded models, your settings, everything the app printed
(errors included) and the last 10 replies with where each wait came from. The
folder opens with the file selected, ready to send. `logs/` isn't committed.

## Testing

```bash
python -m unittest discover tests                                  # Training Path
python -c "from core.eval_harness import EvalHarness; EvalHarness().run_all()"   # decision layers
```
Both also run from the Dev Panel → Eval. Neither needs Ollama.

---

## Philosophy

**Knowledge should be resilient.**
If the internet dies, human knowledge shouldn't die with it.

**Honesty matters more than false confidence.**
A system that says "I'm uncertain — verify before acting" is worth more
than one that answers everything with unwarranted authority.

**People need companionship, not just information.**
Isolation kills as surely as injury. Keeping someone psychologically functional
long enough to find other people is as important as telling them how to purify water.
Prometheus is a bridge to real human connection, not a replacement for it.

---

*Bringing fire back to humanity.*
