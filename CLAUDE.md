# Prometheus — working notes

Offline AI survival and rebuilding companion. PySide6 desktop app, Llama 3.2 3B
through Ollama, ChromaDB + sentence-transformers retrieval (JSON keyword fallback),
Piper TTS, Faster-Whisper STT. No network after setup.

## Run and test
- `python main.py` (needs `ollama serve` and `ollama pull llama3.2:3b`)
- `python -m unittest discover tests` — Training Path (no Ollama, no Qt)
- `python -c "from core.eval_harness import EvalHarness; EvalHarness().run_all()"` — 22 decision-layer checks, must stay 22/22
- Both run from the Dev Panel (Ctrl+D → Eval)
- Offscreen UI check: `QT_QPA_PLATFORM=offscreen`, patch `LLMEngine.stream/complete`

## Query flow (ui/main_window.py + core/pipeline.py)
Decision layers live in `core/pipeline.py` (`QueryPipeline`, no Qt). The window handles threads/UI.
`_generate_response` → trace + `pipeline.route()` → fork:
- **Training Path** when `routing_plan.use_training_path` (tab in electronics/chemistry/build/navigation,
  intent EXPLAIN or ASSESS, not strict). `TrainingWorker` (QThread) runs `DerivationEngine.run()`.
  DERIVED / NEEDS_DATA are shown; anything else falls back to the Knowledge Path with a chat note.
- **Knowledge Path** `_run_knowledge_path` → `pipeline.prepare_knowledge()`: tiered RAG → sufficiency gate →
  contradiction → decision gate (+ sufficiency override) → bounds → memory filter → map context →
  `build_system_prompt` → returns `PreparedAnswer`. Window then shows CLARIFY text or streams via `LLMWorker` → TTS.
- `_generation_id` guards late signals after Escape/⏹ (`_force_stop`).
- Timing: `tracer.record_first_token()` in `_on_token` = speak-start (headline);
  `tracer.finish()` = full completion. `_finish_trace()` returns both for the chat stamp.

## Training Path (core/training/)
- `axiom_seeds.py` — all concepts. Tier = 1 if no parents, 2 if all parents are tier 1, else 3 (a test enforces it).
  `anchor_terms` are compared with whitespace removed and lower-cased against KB text;
  `result_markers` are regexes against `normalise_formula()` output (× · → `*`, ² → `^2`).
- `graph.py` — RLock (re-entrant on purpose). Axioms locked at 1.0. Confidence capped by weakest parent,
  pushed to descendants. Quarantine = 0 for children. `success_count` only changes in `apply_delta`.
- `engine.py` — the concept's own anchor is never given to the model (it would hand over the answer);
  it's used to show "Checked against the library".
- No user verdicts (owner: "the person won't know"). `engine.run(query, tab, progress)` self-checks:
  `SELF_CHECK_GAIN` 3/3 → +0.5 (learned), 2/3 → +0.3, 1 → +0.05, 0 → −0.1; DERIVED needs ≥2 agree.
  Untrained ancestors (≤3) are derived first, each reported via `progress("Researching X")` →
  `TrainingWorker.progress` → `ChatView.show_researching`. Failures → NEEDS_TRAINING / BLOCKED /
  FOUNDATIONAL_GAP with "I haven't been trained on X yet" → library fallback note.
  `session.py` (verdicts) is kept but no UI calls it. Lemma rules unchanged.
- Anchors live in `knowledge_base/scientific_reference/`.
  If you add a concept, add matching text there and check `TestEngine.test_all_anchors_resolve`.

## Conventions (owner's standing preferences)
- Colour never on text — use left bars, borders, small bar widgets. No pills/badges.
- Dark dialog backdrops; plain, short wording in the UI.
- Readable step-by-step comments ("Step 1: …").
- Keep README current with every change.
- Desktop and Android are one app: the APK is the same PySide6 code built with
  `pyside6-android-deploy` (shiboken6) via `build_apk.py`. Phone differences go through
  `core/platform_info.PHONE_LAYOUT` (preview: `PROMETHEUS_PHONE_LAYOUT=1`) and
  `ui/layout_helpers.size_dialog`. Never hard-code a minimum width above ~400px without a phone branch.
- Android build: owner has the PySide6/shiboken6 Android wheels locally. `build_apk.py` wraps the
  deploy tool's `BuildozerConfig` to add .md/.qss/.json files, requests/sqlite3, network permissions,
  and to exclude memory/. Can't be built in the cloud sandbox (download.qt.io and NDK blocked).
- Deliver as a commit plus a zip of changed files; the owner pushes.

## Owner's local layout (Windows, listed 2026-11-05)
```
<parent>/
├── prometheus/            the repo (main.py, core/, ui/, knowledge_base/, voices/Data, voices/Vasco, memory/, map/ empty)
└── prometheus_setup/      NEXT TO the repo, not inside: wiki dumps, a duplicate knowledge_base/ copy,
                           piper-master (Piper SOURCE, not a program), piper-voice-models-main
```
- Use `core/paths.setup_dir()` for prometheus_setup (inside first, then beside). Never assume one.
- TTS: `VoiceManager.find_piper()` searches PROMETHEUS_PIPER → PATH → project/piper → setup_dir().
  Playback: `winsound` on Windows (polled so stop works), aplay/paplay/afplay elsewhere;
  `stop()` bumps a generation counter and terminates only our own player process.

## UI (overhauled 2026-11-05)
- `ui/style.qss` is the single source of look: neutral text, colour only in bars/borders/fills,
  `QLabel { background: transparent }` (a global QWidget background used to paint black boxes behind
  labels). Small square buttons need `padding: 0` or the global padding hides their text.
- Header: PROMETHEUS + day; Situation check, Skills, Map, Info (checkable), Settings, More ▾ menu
  (documents, print, reset, developer panel). Phone: first three move into More.
- Companion tab is first and the default. No first-launch popup: empty tabs show `ui/welcome.py`
  (intro + suggestions); only Survival offers the situation check, until `user.assessment_done`.
- Sidebar starts hidden until memory has something (`_has_situation_data`).
- Ollama: `OllamaCheckWorker` (QThread) — never check on the UI thread; retries every 10 s;
  `is_available()` falls back from localhost to 127.0.0.1. Settings → Model edits `fast_model` and
  `companion_model` (chats use these; `llm_model` mirrors fast_model; old configs migrate in `Config.load`).

## Chat tab, speed, crisis (2026-11-05, owner uses LFM2.5-1.2B-Instruct)
- Companion = `pipeline._prepare_companion`: COMPANION_PERSONALITY (friend, length follows mood,
  "mhm" ok, no therapy talk) + name + optional 2×90-word background only for COMPANION_TOPICS.
  Never route the companion through the full knowledge prompt (it was ~2,600 tokens → ~3 s).
- Knowledge prompts: ≤ `rag_results` passages, each `trim_passage`d to 130 words.
- Every Ollama request sends `keep_alive` and a fixed `num_ctx` (changing num_ctx reloads the model).
  `warm_up()` runs once Ollama is ready. `llm.last_stats` → trace (load / prompt tokens / eval ms).
- Crisis: `intent_router.is_crisis` (suicide/self-harm wording) → `RoutingPlan.is_crisis` →
  `CRISIS_PROMPT`, any tab. Bare "help" is NOT an emergency (only "please help", "help!" …).
- Assistant name/persona: `config.assistant_name/assistant_persona`; `pipeline._tab_system` swaps
  "You are Prometheus"; header + companion tab label follow it.
- P2P/Messages hidden: `core/features.P2P_ENABLED = False` (no tab, no sockets).
- Answers carry their own `images`/`sources` (PreparedAnswer) — never read `knowledge.get_last_*`
  after the fact (the companion path doesn't search, so those can be stale).

## From the owner's debug logs (2026-11-05)
- Windows: requests to `localhost` cost ~2 s each (IPv6 tried first, Ollama is IPv4-only).
  `llm.fast_local_url()` / `LLMEngine.base_url` setter always use 127.0.0.1. Ollama's own time to
  first token was ~0.3 s on the owner's GPU — everything else was this.
- Settings probes Ollama on a QThread (never block the dialog).
- One shared embedder (`core/embedder.get_embedder`); offline (HF_HUB_OFFLINE) once cached.
- ingest re-does image-eligible PDFs whose processed entry lacks `"paged": True` (pictures + page_num).
- Follow-ups (`pipeline.is_follow_up`) search with the previous question + FOLLOW_UP_NOTE.
- `python -m core.tracer` also prints the last Training Path attempts (problems + raw output start).

## Wikipedia
- Owner hadn't extracted it (old parser found 0 articles anyway). `--extract-only` extracts without
  the hours-long indexing; `core/wiki_lookup` reads the extracted files directly.
- `find_articles(text)`: n-grams (1–6 words) → file stems, media-hint suffixes (_film, _tv_series…),
  disambiguation → variant, single words only if Capitalised / quoted / after LEAD_IN ("seen", "about",
  "what is"…), never generic MEDIA_HINTS words. ~0.1 ms with 100k titles (listing: ~0.5 s once, cached).
- Used by `pipeline._wikipedia_background`: chat tab always; knowledge tabs only non-strict and not medical.
- Full-text: `core/wiki_index` (SQLite FTS5, porter, title weight 10, last word prefix,
  AND then OR fallback) → `knowledge_base/wikipedia_search.sqlite`. Built after every extraction and by
  `ingest.py --wiki-index`. 50k articles: 3 s build, ~25–65 ms per search.
- Wikipedia tab = tab 2 (`id="wikipedia"`, not a chat): `ui/wiki_search.py`, search on a QThread,
  title ranking + vector matches when indexed; "Ask about this" → chat tab "Tell me about <title>".

## Repo hygiene
- `.gitattributes` keeps `setup.bat` CRLF and `setup.sh` LF; `setup.sh` is committed executable.

## Knowledge base
- In git: only hand-written `knowledge_base/<domain>/*.md` (not README.md, not wikipedia/).
  Downloaded books stay local. Owner's local library (listed 2026-11-05): ~60 PDFs/TXTs across
  22 domains, plus the six hand-written guides (companion, emergency_medicine, food_preservation,
  navigation, soap_making, water_purification).
- `ingest.py` skips identical-content files (SHA-256) so one book can't count as two sources,
  removes deleted files' chunks, replaces edited files' chunks in both stores, and always writes
  `memory/chunks_fallback.json` (even with ChromaDB). Tested with chromadb 1.5 + a fake embedder.
  Exception: with ChromaDB, `wikipedia` chunks are kept out of the JSON (it's loaded into RAM).
- Wikipedia: `python ingest.py --download-wikipedia` (Simple English pages-articles.xml.bz2,
  resume + SHA-1 check). Parser strips any export-schema namespace (the old fixed
  "Export-0.10" string matched nothing → 0 articles) and keeps `<ns>0</ns>` pages only.

## Known gaps
- Voice (Piper, Faster-Whisper) is desktop-only; Android shows no voice.
- APK build not yet run end to end (needs the owner's wheels + NDK).
