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

## What it needs (estimates)

| | Minimum | Recommended |
|---|---|---|
| **Memory (RAM)** | 8 GB | 16 GB |
| **Processor** | 4 cores, 64-bit, AVX2 (most CPUs from ~2015) | 6–8 cores, recent |
| **Graphics** | none — the models run on the processor, slower | NVIDIA with 6 GB+ video memory (RTX 2060 / 3050 or newer) |
| **Storage** | 16 GB free (the portable folder is ~13 GB) | an SSD, or a USB 3 stick / card |
| **System** | Windows 10/11 64-bit or Linux | same |

In use it takes about 4.5–5.5 GB of memory: the speaker (~2 GB) and the
librarian (~1 GB), library search (0.5–1 GB), the window and voice (~0.6 GB).
Both models fit in about 3 GB of video memory, so even a 4 GB card makes
replies start almost at once; on a processor alone expect the reply to start
after a second or two and then write at roughly 10–20 words a second.

## Quick Start

The folder looks like this — **double-click `Prometheus.exe` to start**:
```
prometheus/
├── Prometheus.exe     start it (Windows)
├── prometheus.sh      start it (Linux / macOS / Raspberry Pi)
├── README.md
└── app/               everything else: code, models, books, settings, Python
```
The commands in this README are run **inside `app`** (`cd app` first).

### Fastest — one script does it all
```bash
# Windows: double-click app\setup.bat
# Linux / macOS / Raspberry Pi:
bash app/setup.sh
```
Both scripts check Python 3.9+ and pip, check for Ollama (Windows opens the
download page, Linux/macOS installs it), pull the default model (LFM2.5 1.2B Instruct), install
requirements, index the knowledge base, then offer to launch.
Downloading the full source library (`tools/bootstrap.py`, ~2GB) stays a separate step.

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
python -m core.ai.ollama_local --pull hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest
```
Already pulled it with plain `ollama pull`? Move it in instead (no download;
every file is checked, then the old copy is removed):
```bash
python -m core.ai.ollama_local --move
```

### 3. Install Python dependencies
```bash
python -m pip install -r requirements.txt   # "python -m" installs into the Python that runs Prometheus
```

### 4. Download all source materials (one time, needs internet)
```bash
python tools/bootstrap.py
```
Downloads ~1.9GB–1GB of public domain survival manuals, medical references,
and practical guides. Self-deletes after completion.

### 5. Index the knowledge base
```bash
python tools/ingest.py
```
Processes all downloaded sources into the searchable vector database.
Takes 10–30 minutes on first run. Subsequent runs only process new files.

### 6. Run Prometheus
```bash
# Start Ollama (if not already running as a service)
ollama serve &

# Launch Prometheus — or double-click Prometheus.exe
python main.py
```

---

## Where things live

```
prometheus/
├── Prometheus.exe, prometheus.sh            start it
└── app/
├── main.py                                  what both of those run
├── setup.bat, setup.sh, debug_run.bat       first-time setup / a run with a saved log
├── tools/        commands you run: ingest (library), setup_voice, make_portable,
│                 bootstrap (downloads), bootstrap_map, generate_reference,
│                 build_exe (Prometheus.exe), build_apk, move_into_app,
│                 remove_old_layout
├── core/
│   ├── ai/       the two models and how they're prompted (llm, librarian, tone…)
│   ├── answers/  how each reply is decided (pipeline, gates, tracer, eval)
│   ├── library/  search: books, Wikipedia, Obsidian notes
│   ├── you/      memory, what it knows about you, chats, backups
│   ├── voice/    speaking (Piper) and listening (Whisper)
│   ├── app/      settings, paths, phone/desktop, map, messages
│   └── training/ working things out from first principles
├── ui/
│   ├── chat/     the conversation, message box, menu, chats list
│   ├── panels/   Info, Review, Search, Quick help
│   ├── dialogs/  Settings, Situation check, Skills, Map, documents, developer panel
│   └── main_window.py, style.qss (the whole look)
├── tests/
└── assets/ knowledge_base/ memory/ models/ voices/   (+ ollama/ piper/ runtime/ once made portable)
```

**Coming from the old layout** (main.py at the top)? Unzip the update, then
run once from the prometheus folder:
```bash
python app\tools\move_into_app.py --check   # list what it will do
python app\tools\move_into_app.py
```
It moves everything at the top into `app\` — models, Ollama, the portable
Python, voices, memory, your books (instant on one drive, even for GB) — and
deletes old copies of files the update replaced. `.git`, a `.venv` and
`prometheus_setup` stay where they are. In git, `git add -A` records it as moves.

## Moving Prometheus to another computer

One command gathers everything into the `app` folder, so you can copy
the folder to another computer (same system, e.g. Windows → Windows) and run it:

```bash
python tools/make_portable.py            # gather everything in
python tools/make_portable.py --check    # just list what's still outside
```

| What | Where it goes |
|------|---------------|
| Both AI models (speaker + librarian) | `models\` (moved, not re-downloaded) |
| The Ollama program (with its GPU libraries) | `ollama\` — Prometheus uses this copy first |
| Piper (with its speech data) and the Whisper model | `piper\`, `models\whisper\` (your voices are already in `voices\`) |
| Python and every package (Windows) | `runtime\python\` — Python's official portable build, downloaded once |
| Python packages (Linux/macOS) | `wheels\` — installed offline on first start |

Your chats, memory, settings, library and its search index are already inside
and don't depend on where the folder is. On the new computer just double-click
**`Prometheus.exe`** (or run `./prometheus.sh`) — no installing. `setup.bat` and
`debug_run.bat` use the folder's Python too. Expect the folder to be several GB.

**Size.** It's meant to fit a 16 GB SD card or USB stick (about 14.5 GB as
Windows counts it), so `make_portable` ends by checking the folder is under
14 GB and, if not, lists the biggest parts. The largest is usually `ollama\`:
Ollama brings graphics-card libraries for both NVIDIA and AMD so the folder
works on any PC; the sizes are listed. If you know which card it'll run on,
`python tools/make_portable.py --gpu nvidia` (or `amd`, `intel`) keeps only that
one's — other cards then fall back to the slower Vulkan or CPU versions, which
are always kept. Running it again finishes anything left half-done (for
example the Python packages after a dropped connection). Format the stick
exFAT (FAT32 can't hold files over 4 GB).

Not copied: an Obsidian vault elsewhere (copy it and set it again in
Settings → Obsidian), and `prometheus_setup` (downloads and sources — the app
doesn't need it).

## Voice Setup (Optional — Highly Recommended)

Voice changes the experience from tool to companion. One command sets it up
and tests it (`setup.bat`/`setup.sh` run it too):
```bash
python tools/setup_voice.py            # install what's missing, then test
python tools/setup_voice.py --check    # only report, no downloads
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

After changing it, run `python tools/setup_voice.py` once to download that size
for offline use.

Voice input works once speech recognition has loaded; hover the 🎤 to see why
if it doesn't.

---

## App icon
Save the icon as **`assets/icon.png`** (square, 512×512 or larger). It's
used for the window and taskbar, next to the name in the header, the Windows
`Prometheus.exe` (`tools/build_exe.py` makes `icon.ico` from it) and the
Android app icon and launch screen.

## Building Executables

### Prometheus.exe (Windows)
`Prometheus.exe` is a small launcher (about 60 KB) with your icon. It starts
the app from `app\` with the folder's own Python if it has one
(`app\runtime\python`), otherwise the Python on the computer — no console
window. If the app stops while starting (packages not installed yet, say), it
offers to run it again in debug mode. Hold **Shift** while opening it for a
debug run any time.

It's committed, so you don't build it. After changing the icon or the
launcher (`tools/launcher/`), rebuild it with MinGW-w64 installed:
```bash
python tools/build_exe.py
```
Why not the whole app in one .exe: a one-file exe unpacks itself on every
start — with the models and library that's ~10 GB each time (and over ~4 GB
it doesn't work at all). The launcher starts the app in place instead.

Windows may show "Windows protected your PC" the first time (the exe isn't
signed): **More info → Run anyway**.

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
python tools/build_apk.py --setup                        # first time only
python tools/build_apk.py --debug --wheels ~/qtwheels    # folder with both wheels
python tools/build_apk.py --install                      # push to a phone via ADB

# Emulator instead of a real phone:
python tools/build_apk.py --debug --wheels ~/qtwheels --arch x86_64

# Build on GitHub instead (free):
python tools/build_apk.py --github   # writes .github/workflows/build_apk.yml
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

## Wikipedia (Optional)

### The big one: 1 million English articles (recommended)
```bash
python tools/ingest.py --download-wikipedia-full
```
- Downloads the full English Wikipedia once (about 24 GB, into
  `prometheus_setup/`; resumes if cut off, checked against Wikimedia's checksum).
- Keeps the **1,000,000 most linked-to articles** — the things people actually
  know about, from Titanfall 2 and BT-7274 to every country, film and band you'd
  ask about. Disambiguation pages, talk pages and "References/See also"
  sections are left out; very long articles are kept to 5,000 words.
- Redirects become other names for the article: "BT-7274" finds *Titanfall 2*.
- Everything goes into one file, `knowledge_base/wikipedia_full.sqlite`
  (roughly 10 GB), with full-text search built in.
- Takes a few hours, once, using every CPU core but one. **You can stop it
  and run the same command again — it carries on where it stopped.**
- Afterwards the 24 GB download can be deleted.

```bash
python tools/ingest.py --download-wikipedia-full --top 500000      # a smaller one (~5 GB)
python tools/ingest.py --wikipedia-full path/to/enwiki-…-multistream.xml.bz2   # a dump you already have
```
When it's there, chat, the librarian and the Wikipedia section use it instead
of the Simple English files.

### The small one: Simple English (~360 MB download)

Download `simplewiki-latest-pages-articles.xml.bz2` from
https://dumps.wikimedia.org/simplewiki/latest/ (or let Prometheus fetch it),
keep it in `prometheus_setup/`, then **extract** it — a few minutes:

```bash
python tools/ingest.py --wikipedia prometheus_setup/simplewiki-latest-pages-articles.xml.bz2 --extract-only
python tools/ingest.py --download-wikipedia --extract-only     # same, downloading it for you
```

That also builds the **search index** for the Wikipedia tab (SQLite full-text
search, built in — a minute or two, no AI model), so every article's text is
searchable straight away. For articles you extracted before this existed:

```bash
python tools/ingest.py --wiki-index
```

Indexing for the AI library search as well (`python tools/ingest.py --source
wikipedia`) is optional and takes hours on a CPU. Re-running the extract with a newer dump only
rewrites changed articles and removes deleted ones.

**In chat:** when a message names something with its own article — a film,
show, band, book, person, place — its opening paragraph is given to the model
(by title, in milliseconds), and the reply says *From: Wikipedia — Title*.
"have you seen inception?" finds *Inception (film)*. Everyday words don't
count: "I watched a movie yesterday" pulls in nothing. Never used in the
Medical tab or for step-by-step/diagnosis questions.

**The Search tab** (second tab): one search over **your books, your notes
and Wikipedia**. Results come in groups — *In your books*, *Your notes*,
*Wikipedia* — and each says where it's from ("Edible Wild Plants · p. 12 ·
plants"). Click one to read it:
- a **book** result shows the passage, the page itself as a picture, and
  **Open the book** (opens the PDF in your usual viewer; desktop only)
- a **Wikipedia** result shows the whole article
- **Ask about this** asks the section that reads that book (a plants book →
  Survival), or the chat tab for Wikipedia

Wikipedia finds a title, a name, or words anywhere in an article; exact titles
come first ("plants" finds *Plant*). Book passages that aren't on the subject
are left out. Without Wikipedia set up, books and notes are still searched.

- Only real articles are kept — no talk/user/project pages, redirects or stubs
  under 100 words.
- Keep dumps **outside** `knowledge_base/`: the desktop build copies that folder
  next to the exe. `knowledge_base/wikipedia/` isn't committed.

---

## Knowledge Sources

`tools/bootstrap.py` downloads all of these automatically. All are public domain or explicitly free to reproduce.

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

### What it remembers about you — only what you confirm
When you mention something about yourself ("my sister Kate", "my dog is
called Max", "I live in Cork", "I work as a nurse", "I love hiking", "my
favourite film is Inception"), it **doesn't use it yet**. It goes to the
**Review** tab, which shows a count ("Review (2)"):

| On each card | |
|---|---|
| What it understood | "Kate is your sister" — and how sure it is |
| Your words | "You said: my sister Kate is visiting…" |
| **Accept** | It's added to what it knows about you, marked as confirmed by you, with your words kept as the source |
| **Edit** | Fix it ("Katie", not "Kate"), then save — saved as confirmed |
| **Reject** | Never used, and never raised again |

Nothing waiting for review is ever shown to a model.

Besides those fixed patterns, after each reply the librarian model also looks
at what you said for things they miss ("we moved to Galway last year", "my
brother Tom fixes cars"). Each one must be made of words you actually wrote,
and it goes to Review marked **not sure · noticed by the model** — nothing is
used until you accept it. It never slows a reply, only looks at messages about
yourself, and is off in low-power mode; turn it off in **Settings → You**. Confirmed facts let the chat tab
talk to you as someone it knows, and it knows the topics of your last few
chats in that tab (titles only, so a new chat still starts fresh). You can
also see and change everything in **Settings → You**, or in Obsidian's `Me`
note (below) — your own edits there count as confirmed.

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
Pick a **voice**, then give that voice its own **name** (header, chat tab,
and what the model calls itself) and **personality** in plain words, e.g. "a
calm old sailor who doesn't rush you". Each voice keeps its own: switch voices
and its name and personality come back with it. Everything in Settings is
kept when you close and reopen Prometheus. Library answers stay factual
whatever you choose.

### Sources and pictures
Under each library answer: **From:** the book and page it drew on, and the
page itself as a picture (click for full size). Pages are rendered by
`tools/ingest.py` for PDFs in the medical, plant, survival, build, electronics,
navigation and farming folders — re-run `python tools/ingest.py` after adding PDFs.
PDFs indexed before their folder had pictures are redone once, automatically,
on the next `python tools/ingest.py` (you'll see "↻ adding page pictures").

Only pages that **really have a picture** are shown — a drawing, a photo, a
"Fig. 3" caption, or a page that's mostly not text. A page of plain text isn't
shown any more. When the passage says "see Fig. 3" and the figure is on the
next page, that page is shown instead. Ask for one ("do you have a picture of
hemlock", "what does … look like", "how would I identify …") and passages that
come with a figure are put first. Asking for a picture of something ("a
picture of water hemlock", "a diagram of a bow drill") looks for the figure
page whose **caption or labels name it** ("Fig. 9-5. Water hemlock"), in any
book — not the page some text about it came from. The reply is told which
picture is shown (or that there's none), so it doesn't say it can't show
pictures above one. Which pages have figures, and what's printed on them, is
kept in `knowledge_base\<folder>\_images\figures.json` and
`figure_text.json`, done by every library update; for books already in your
library, run once (seconds per book, no re-indexing — run it again if you ran
it before 10 Nov, to pick up the captions):

    python tools\ingest.py --figures

Books are credited by their **real title** ("From: Practical carpentry, p. 12"),
not the file name an archive gave them. Titles come from inside each PDF, the
first heading of a guide, or the file name; they're kept in
`knowledge_base\titles.json`, which you can open and correct — your changes are
never overwritten. Filled in after every library update, or on its own with
`python tools/ingest.py --titles`.

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
Prometheus opens in the **Prometheus** (companion) section with the cursor in
the message box, so you can just start typing. There's no popup on first launch.

**The menu on the left** (☰ in the top corner shows or hides it):
- **Quick help** at the top: 16 one-tap questions for urgent situations
- **Sections**: Prometheus (chat), Wikipedia, Survival, Medical, Electronics,
  Navigate, Farm, Build, Chemistry, and **Review** (things to confirm about
  you — shows a count when something's waiting). **+** adds your own section.
- Under them, the open section's **chats**: New chat, search, and the list.

The conversation sits in a centred column: your messages as soft bubbles on
the right, replies as plain text. The message box underneath holds the mic
and send buttons.

Every empty section shows what it's for and a few questions you can tap. The
Survival section also offers the optional 5-question **Situation check**.

| Header button | Function |
|---------|---------|
| **☰** | Show or hide the menu (phone: opens it full-screen; pick a section or chat to go back) |
| **Situation check** | 5 questions → a numbered priority list |
| **Skills** | Civilisation rebuild tracker (55 skills, 8 stages) |
| **Map** | Offline world map (run `tools/bootstrap_map.py` for map data) |
| **Info** | Show or hide your situation panel. It starts hidden until there's something in it |
| **Settings** | You (what it knows about you), assistant and voice, models, voice input, Obsidian |
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
| `python -m core.ai.ollama_local --move` | Move the models Settings uses from Ollama's usual folder into `prometheus/models` |
| `python -m core.ai.ollama_local --pull <name>` | Download a model straight into `prometheus/models` |
| `python -m core.ai.ollama_local --list` | What's in `prometheus/models` |

If `--move` says the old copy is still in use, quit Ollama (tray icon → Quit)
and run it again to free the space.

### Two models: a speaker and a librarian
Prometheus runs two models side by side:

| | Model | Job |
|---|---|---|
| **Speaker** | Qwen3 1.7B (thinking off) | The only one that talks to you. Turns your message into a clear request for the librarian, then answers you in its persona |
| **Librarian** | LFM2.5 1.2B | Never talks to you. Reads the library passages and lists only the facts in them that answer the request — or says it found nothing |

A question that needs the library goes:
1. the speaker picks search words (a follow-up like "their missions" gets the
   subject from the last question)
2. the library is searched with those words. Only passages that are actually
   on the subject go further — your one or two key words, or half of three or
   more, must be in them. Nothing on the subject → the librarian isn't asked
   at all, and the speaker says it doesn't have it
3. no book on the subject, or a section you made yourself (like
   Entertainment)? Wikipedia is searched inside its articles too, not just by
   title ("tell me about magic the gathering" → *Magic: The Gathering*)
4. the librarian reads your question **in your own words** — not the
   speaker's rewrite of it, which added things ("soap from fat" became "soap
   from coconut oil") — and lists the facts the passages support, with
   numbers, doses and steps copied exactly
5. the speaker answers in its own voice using only those facts. If the
   librarian says NOT FOUND anyway, the speaker reads the on-subject passages
   itself. It's told not to write links, file names or "Source:" lines — the
   sources are shown under the answer

Pictures and **From:** lines under an answer come only from the passages it
actually used (the ones the librarian cited, or the on-subject ones) — not
from whatever else the search turned up. Ask for a picture ("show me a picture
of hemlock") and every on-subject passage with one counts, and the speaker is
told whether a picture is shown — so it doesn't say "I don't have pictures"
above one.

**Its own name.** Ask "who are you", "who are you named after" or about its
name (even misspelt) and it answers as that name. If the name comes from
someone in history or a story, it looks them up in your Wikipedia by the
nearest spelling ("confuscious" → Confucius) and can tell you about them.

Small talk skips all of this, so it's as quick as before. Emergencies skip
step 1 and the speaker reads the field-manual passages word for word. A
looked-up answer takes roughly half a second to a second longer; the chat
stamp shows where the time went ("request 300 ms, librarian 450 ms").

If the librarian can't be reached (Ollama down, model not downloaded), the
speaker reads the passages itself, as before.

### Low-power mode (automatic)
Once the models have loaded, Prometheus checks the computer — memory,
processor, graphics card — and asks Ollama whether the models are actually on
the graphics card. If they're running on the processor (an Orange Pi, an old
laptop, a PC without a usable graphics card), **low-power mode** turns on and
a note in the chat says why. It keeps answers quick by:
- skipping the speaker's separate request to the librarian (the librarian
  still checks the facts),
- reading 2 shorter library passages instead of 3, and the librarian less,
- keeping 10 messages of chat history instead of 20,
- slightly shorter replies.

**Settings → Model → Performance**: *Automatic* (recommended), *Full* or
*Low power*. The same page shows what was found ("8 cores · 16 GB memory · no
graphics card found"). The note only appears when the automatic choice changes.

### Choosing the models
Settings → Model has a box for the **speaker** and one for the **librarian**,
listing the models installed in Ollama (get one with
`python -m core.ai.ollama_local --pull <name>`). Untick **Use the librarian** to go
back to one model reading the library itself. **Check Ollama** tests the
address you've typed. Changes apply as soon as you save; no restart needed.
`setup.bat` / `setup.sh` download both (about 2.1 GB together).

If Ollama isn't reachable, the status bar says so in plain words and checks
again every 10 seconds, so starting Ollama after Prometheus is fine. If a model
isn't installed, it shows the exact command to get it.

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
# sleep 5 && /home/pi/prometheus/prometheus.sh &
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
python tools/ingest.py                                  # index all new files
python tools/ingest.py --rebuild                        # clear and reindex everything
python tools/ingest.py --source medical                 # one domain only
python tools/ingest.py --stats                          # knowledge base statistics
python tools/ingest.py --wikipedia FILE.xml.bz2         # ingest Wikipedia XML dump
python tools/ingest.py --wikipedia FILE.xml.bz2 --max-articles 50000
python tools/ingest.py --init                           # create folder structure only
```

**Upgrading from v19 or earlier:** run `python tools/ingest.py` once. It indexes the new
`scientific_reference/` folder (needed by the Training Path) and, with the v22
cleaner, keeps formulas intact (`=`, `+`, `×`, `²` used to be stripped). For the
formula fix to apply to sources indexed earlier, run `python tools/ingest.py --rebuild`.

Re-running `tools/ingest.py` keeps the index matching the folder:
- an edited file's old entries are replaced, not duplicated;
- a deleted file's entries are removed;
- the same file under two names (same contents) is indexed once — otherwise one
  book would count as two independent sources. Delete the extra copy to stop the
  warning.

---

## Project Structure

```
prometheus/
├── Prometheus.exe             # Windows: double-click to start (tools/build_exe.py)
├── prometheus.sh              # Linux / macOS / Pi: start it
└── app/                       # everything below
├── main.py                    # Entry point
├── setup.bat / setup.sh       # One-step install (Windows / Linux, macOS, Pi)
├── tools/bootstrap.py               # One-time downloader (self-deletes after use)
├── tools/bootstrap_map.py           # Offline map data downloader
├── tools/ingest.py                  # Knowledge base indexing pipeline
├── tools/generate_reference.py      # Printable emergency PDF generator
├── tools/build_exe.py               # Prometheus.exe: the launcher + icon (MinGW)
├── tools/launcher/                  # the launcher's C source and icon/file details
├── tools/move_into_app.py           # one-time move from the old layout
├── tools/build_apk.py               # APK builder (Android, pyside6-android-deploy)
├── requirements.txt
├── README.md
├── CLAUDE.md                  # Working notes for AI-assisted development
│
├── core/
│   ├── pipeline.py            # Decision layers in one place (no UI code)
│   ├── wiki_lookup.py         # Wikipedia by title (chat background, Search tab)
│   ├── search_all.py          # Search tab: books + notes + Wikipedia, each with its source
│   ├── wiki_index.py          # Full-text search over every article (SQLite FTS5)
│   ├── tone.py                # Reads the tone of each chat message
│   ├── embedder.py            # One shared text-embedding model, offline once cached
│   ├── platform_info.py       # Android / phone-layout detection
│   ├── intent_router.py       # 10 intents, domain tiers, Training Path flag
│   ├── rag.py                 # Tiered knowledge search, image lookup
│   ├── figures.py             # Which book pages have a picture on them
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
│   ├── p2p.py                 # Local-network messaging (off — core/app/features.py)
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
│   ├── wiki_search.py         # Search tab: books, notes, Wikipedia — read, ask about it
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
├── knowledge_base/            # Populated by tools/bootstrap.py + tools/ingest.py
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
**Hold Shift while opening `Prometheus.exe`** (or double-click
`app\debug_run.bat`). It runs Prometheus normally in a window. When you close it,
`app\logs\run_<date>_<time>.log` holds your Python/PySide6/Ollama versions, the
installed and loaded models, your settings, everything the app printed
(errors included) and the last 10 replies with where each wait came from —
and what each model said: the speaker's request to the librarian, the facts the
librarian found (or NOT FOUND, with what it actually wrote), how long the
librarian took to load, read and write, the reply you got, and any pictures shown.
It also says which Ollama program is used, whether every model file is in
`app\models`, which Ollama is running on Prometheus's ports (and whether it's
the one reading your models), and the last lines Prometheus's own Ollama
printed (`app\logs\ollama_serve.log`). If Prometheus stops while starting,
`Prometheus.exe` offers the debug run itself. The
folder opens with the file selected, ready to send. `logs/` isn't committed.

## Testing

```bash
python -m unittest discover tests                                  # Training Path
python -c "from core.answers.eval_harness import EvalHarness; EvalHarness().run_all()"   # decision layers
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
