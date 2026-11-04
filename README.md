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
download page, Linux/macOS installs it), pull `llama3.2:3b`, install
requirements, index the knowledge base, then offer to launch.
Downloading the full source library (`bootstrap.py`, ~2GB) stays a separate step.

Or step by step:

### 1. Install Ollama
```bash
# Linux/Mac
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: download installer from https://ollama.ai
```

### 2. Pull Llama 3.2 3B (the AI brain)
```bash
ollama pull llama3.2:3b
```

### 3. Install Python dependencies
```bash
pip install -r requirements.txt
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

Voice changes the experience from tool to companion.

### Text-to-Speech (Piper)
```bash
# Download Piper binary for your platform:
# https://github.com/rhasspy/piper/releases

# Download voice model (recommended: en_US-amy-medium):
# https://huggingface.co/rhasspy/piper-voices

# Place .onnx and .json voice files in the voices/ directory
```

### Speech-to-Text (Faster-Whisper)
```bash
pip install faster-whisper sounddevice
```
Model (~75MB) downloads automatically on first use.

---

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

### Android APK
```bash
# Linux or macOS required (or use WSL2 on Windows)
python build_apk.py --setup      # install dependencies (first time only)
python build_apk.py --debug      # build debug APK (~20–40 min first run)
python build_apk.py --install    # push to connected device via ADB

# Windows users — build in the cloud for free:
python build_apk.py --github     # generates GitHub Actions workflow
# Push to GitHub → Actions tab → APK builds automatically
```

**Android LLM options:**
- **Recommended:** Run Ollama on your laptop/Pi on the same WiFi.
  Set the IP in app Settings → Ollama URL (e.g. `http://192.168.1.100:11434`)
- **Standalone:** Add `llama-cpp-python` to buildozer.spec requirements for fully on-device inference

---

## Wikipedia (Optional — Adds 230,000 Articles)

```bash
# Download Simple English Wikipedia from:
# https://dumps.wikimedia.org/simplewiki/latest/
# File: simplewiki-latest-articles.xml.bz2 (~150MB compressed)

python ingest.py --wikipedia simplewiki-latest-articles.xml.bz2

# Limit articles for faster processing:
python ingest.py --wikipedia simplewiki-latest-articles.xml.bz2 --max-articles 50000
```

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

Written for earlier builds but **not currently in the repository** (the
`knowledge_base/` folder used to be git-ignored, so these were never committed —
they need rewriting or restoring from a local copy):

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
| 🔥 Survival | Water, fire, shelter, food, immediate threats |
| ⚕️ Medical | Procedures, triage, improvised medicine, wound care |
| ⚡ Electronics | Circuits, salvage, power generation, radio, solar |
| 🌍 Navigate | Location finding, star navigation, terrain, weather |
| 🌱 Farm | Agriculture, food preservation, fermentation, animals |
| 🔧 Build | Construction, tools, fabrication, blacksmithing |
| ⚗️ Chemistry | Metallurgy, materials, synthesis, soap, explosives |
| 💬 Prometheus | Companion, philosophy, psychology, meaning, memory |
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
- Under each derivation: **Right / Not quite / Wrong / Contradicts a source**.
  Only your answers move a concept's trust. After 3 confirmations at 80%+
  it becomes a trusted result. "Contradicts a source" puts it on hold and
  lowers trust in everything built on it.
- A tier-3 concept needs its building blocks trained first. If they aren't,
  Prometheus answers from the library and tells you which ones to ask about.
- If a calculation needs numbers you didn't give, it asks for them.
- Learning is saved in `memory/training/` and included in backups.

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

### Header Controls
| Control | Function |
|---------|---------|
| **⚡** (tab bar, leftmost) | Quick Access — 16 one-tap critical actions |
| **📋 Assess** | Situation assessment → immediate priority list |
| **🌱 Skills** | Civilisation rebuild skill tree (55 skills, 8 stages) |
| **◀ Info** | Toggle situation sidebar |
| **📎** | Add personal documents as searchable context |
| **🖨️** | Generate printable 6-page emergency reference PDF |
| **⚙** | Settings (model, voice, identity) |
| **↺** | Reset — clear one tab, all tabs, user memory, or everything (backup saved first) |

### Quick Access Panel
16 pre-wired critical actions across 4 sections. Tap any button — it navigates
to the correct tab and fires the query automatically. No typing needed.

- **Survival:** Water, Fire, Shelter, Food
- **Medical:** Bleeding, Fever, Fracture, Infection
- **Navigation:** Find North, Where Am I, Signal, Weather
- **Build & Resources:** Power, Tools, Soap, Ferment

### Situation Assessment
5 questions on first launch (or via 📋 Assess any time):
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
ollama pull llama3.2:3b

# Install Python dependencies
pip install -r requirements.txt --break-system-packages

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
| Llama 3.2 3B Q4 (via Ollama) | ~1.9GB |
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
├── build_apk.py               # APK builder (Android)
├── requirements.txt
├── README.md
├── CLAUDE.md                  # Working notes for AI-assisted development
│
├── core/
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
│   ├── p2p.py                 # Local-network messaging
│   ├── stt.py                 # Faster-Whisper speech-to-text
│   ├── tabs.py                # Tab definitions and management
│   ├── tts.py                 # Piper text-to-speech (streaming)
│   └── voice_manager.py       # Voice model management
│
├── ui/
│   ├── main_window.py         # Window, query fork, both paths
│   ├── workers.py             # LLMWorker, TrainingWorker, InitWorker
│   ├── chat_view.py           # Messages, timing stamp, verdict row, images
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
