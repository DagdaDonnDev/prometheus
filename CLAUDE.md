# Prometheus — working notes

Offline AI survival and rebuilding companion. PySide6 desktop app, LFM2.5 1.2B Instruct (default)
through Ollama, ChromaDB + sentence-transformers retrieval (JSON keyword fallback),
Piper TTS, Faster-Whisper STT. No network after setup.

## Run and test
- `python main.py` (needs Ollama installed and the default model in prometheus/models: `python -m core.ai.ollama_local --move` or `--pull hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest`)
- `python -m unittest discover tests` — Training Path (no Ollama, no Qt)
- `python -c "from core.answers.eval_harness import EvalHarness; EvalHarness().run_all()"` — 22 decision-layer checks, must stay 22/22
- Both run from the Dev Panel (Ctrl+D → Eval)
- Offscreen UI check: `QT_QPA_PLATFORM=offscreen`, patch `LLMEngine.stream/complete`

## Layout (reorganised 2026-11-09)
- Root: main.py, launchers, setup/debug .bat/.sh, docs. `tools/` = runnable scripts (each chdirs to
  the project root and puts it on sys.path; `ROOT_DIR`/`ROOT` = parent.parent). `tools` is a package
  (tests import `tools.make_portable`).
- core/{ai, answers, library, you, voice, app, training}; ui/{chat, panels, dialogs} + main_window,
  workers, layout_helpers, style.qss. `core.app.paths.PROJECT_DIR` / `core.ai.ollama_local.PROJECT_DIR`
  = parent.parent.parent. Commands: `python tools/ingest.py …`, `python -m core.ai.ollama_local …`.
- Owner unzips over the old copy → `python tools/remove_old_layout.py` deletes moved files (only when
  the new one exists). bootstrap.py no longer deletes itself.

## Query flow (ui/main_window.py + core/answers/pipeline.py)
Decision layers live in `core/answers/pipeline.py` (`QueryPipeline`, no Qt). The window handles threads/UI.
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
  `pyside6-android-deploy` (shiboken6) via `tools/build_apk.py`. Phone differences go through
  `core/platform_info.PHONE_LAYOUT` (preview: `PROMETHEUS_PHONE_LAYOUT=1`) and
  `ui/layout_helpers.size_dialog`. Never hard-code a minimum width above ~400px without a phone branch.
- Android build: owner has the PySide6/shiboken6 Android wheels locally. `tools/build_apk.py` wraps the
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

## UI (redesigned 2026-11-09)
- `ui/style.qss` is the single source of look: navy palette from the icon (#11131a window, #1d212c card,
  #2b3040 border), neutral text, amber #f0a500 only in bars/borders/fills.
  `QLabel { background: transparent }`. Small square buttons need `padding: 0`.
- Layout: header (☰ `_chats_btn` → `_toggle_chats`, logo, name, day; Situation check, Skills, Map,
  Info, Settings, More ▾) / splitter: `NavPanel` (ui/chat/nav_panel.py: Quick help, Sections list, then the
  embedded ChatsPanel) | `_chat_pane` (ChatView + InputBar) | Sidebar. Wiki/Review widgets are
  inserted at splitter index 1 and hide `_chat_pane`. `self.tab_bar` IS the NavPanel (same API as the
  old TabBar: set_active/set_label/refresh/_buttons; ui/tab_bar.py deleted).
- Phone: ☰ swaps the whole screen to the menu; picking a section/chat closes it. Day label hidden.
- Chat: centred column (max 820), user = `#bubble_user` rounded fill right-aligned, `fit_width()` so
  short messages aren't clipped; assistant = plain text. Composer `#composer` (rounded box, mic + send).
- Companion tab is first and the default. No first-launch popup: empty tabs show `ui/chat/welcome.py`
  (intro + suggestions); only Survival offers the situation check, until `user.assessment_done`.
- Sidebar starts hidden until memory has something (`_has_situation_data`).
- Ollama: `OllamaCheckWorker` (QThread) — never check on the UI thread; retries every 10 s;
  `is_available()` falls back from localhost to 127.0.0.1.

## Two models (2026-11-09) — core/ai/librarian.py
- `config.speaker_model` (qwen3:1.7b; `model_for_tab` → it, every tab) talks; `config.librarian_model`
  (LFM2.5) only extracts; `two_models` toggle. `_thinking_off(model)` sends `think: false` only to
  qwen3/deepseek-r1/qwq/magistral (Ollama rejects it for others); `strip_thinking` + stream filter.
- Knowledge tabs: `Librarian.brief` (speaker, ≤60 tokens: SEARCH/QUESTION lines, gets the last
  exchange) → search with brief.search + old search_q → `extract(question, passages)` (librarian,
  passages cut to 380 words total, ≤8 "- fact [n]" lines or NOT FOUND) → `facts_block` replaces
  knowledge_context. Emergency: no brief, no extraction (raw passages). Crisis: CRISIS_PROMPT only.
- Companion: no brief; wiki (250 words)/own notes/companion shelf → passages → extract → facts_block.
  `Facts.failed` (no answer at all) → fall back to raw passages, never "nothing found".
- `prepare_knowledge(..., progress)` runs in `ui/workers.PrepareWorker` (QThread); results guarded
  by `_generation_id`; `_answer_prepared` continues on the UI thread. Trace: brief_ms, librarian_ms.

## Answer quality fixes (2026-11-09, owner: "consistent low confidence", Build "redundant things")
- ingest names chunks' `source` after the FILE stem (owner's PDFs: "practicalcarpen01radfgoog"), so
  `SOURCE_TIERS.get(source, 55)` scored every book 55 = LOW → CAUTIOUS/SAFE_MODE. `score_chunk(…, domain)`
  now falls back to the FOLDER grade (survival 85, medical 90, build 82 … in SOURCE_TIERS).
- `build_bounds`: FAILURE_INSTRUCTIONS + "ask one clarifying question" only for medical/chemistry or
  when sources are missing/conflicting or mode is SAFE_MODE/CLARIFY.
- `KnowledgeBase._diverse`: passages sharing >50% word pairs with a better one are left out of the
  prompt (`_last_used_chunks`, also what the librarian reads). Obsidian `title_hit` floor 80 → 92.
- Owner (2026-11-09): "response time exceptionally fast", "better to talk with".

## Prompt layout for Ollama's cache (2026-11-09)
- `PreparedAnswer.system_prompt` = what rarely changes (companion persona + name + about_line +
  earlier_topics; knowledge tabs: `_tab_system` only). `turn_context` = per-question (facts/rules/
  guidance/tone) → `pipeline.with_turn_context(messages, ctx)` prefixes it onto the NEWEST user message
  only ("[For this reply — not part of their message] … [Their message]"); saved history stays raw.
  `full_prompt` property = both (tests use it). Measured: chat tab ~24% less to read per message;
  knowledge tabs ~1% (the per-question passages dominate — low-power trims those).
- `ContextManager.messages_for(tab)` never blocks (newest MAX_MESSAGES if no summary yet);
  summaries run on a thread (`_background_summarize` → `_SummaryBridge` → `apply_summary`, applied only
  if the chat still starts with the summarised messages). It used to summarise on the UI thread.

## Low power (2026-11-09) — core/app/hardware.py
- `detect()` (RAM via OS calls, cores, arch, GPU via nvidia-smi / Win32_VideoController / lspci) +
  `ollama_on_gpu(base_url)` (/api/ps size_vram, after warm-up) → `recommend()` → full|low + reason.
  Low if RAM < 7 GB, models on CPU, or (unknown and no GPU and ARM or <6 cores).
- `config.power_mode` auto|full|low (saved), `power_last` (last auto choice → note only on change);
  runtime attrs (NOT fields, never saved): `low_power_active`, `power_reason`, `hardware_summary`
  (`__post_init__`; until checked, auto assumes power_last). Anything copying Config must filter to
  `__dataclass_fields__` (Settings' Ollama probe did `Config(**__dict__)` and broke).
- Effects when low: no `Librarian.brief`; librarian passages 220 words, ≤5 facts; 2 passages × 90 words;
  history 10 messages (`messages_for`); num_predict ≤ 220; (model-noticed facts off).
- Window: warm-up thread → `_PowerBridge.decided` → `_apply_power` (+ chat note, status) →
  `_apply_power_limits`. Settings → Model → Performance combo + "This computer: …" line.

## Book titles (2026-11-09) — core/library/titles.py
- knowledge_base/titles.json {source key (file stem, spaces→_, lower): title}; built by
  `tools/ingest.py --titles` and after every ingest; never overwrites (owner may edit). PDF metadata
  title (subtitle after ;/: dropped), md first heading, else cleaned file name unless it looks like a
  code. `confidence._source_label` checks `titles.title_for(source)` first (cached by mtime).

## Figure pages + log text (2026-11-09) — core/library/figures.py
- Owner: "a hard time to provide usable images" — ingest renders EVERY PDF page. `scan_pdf` marks
  figure pages (caption regex / words < 45% of the book's median but ≥25 / placed image 5–85% of the
  page / >40 drawings) → `<domain>/_images/figures.json`; ingest records it, `--figures` back-fills.
  `rag._resolve_image`: unscanned book → old behaviour; else only figure pages (±1 if text mentions
  a figure). `wants_picture(query)` → `_score_and_format` sorts image-carrying passages first.
- `wiki_lookup.find_articles`: n≥2 grams starting with `_EVERYDAY_START` (your/my/the…) need a
  capitalised later word, quotes, a lead-in or a media hint ("your name" → anime "Your Name" in the log).
- Trace: `brief_text`, `librarian_text` (`pipeline._facts_note`), `response_text` (600 chars),
  `images` → printed by `tracer.print_recent` (debug_run log).

## Log 2026-11-09 15:24 fixes + Search tab
- Speaker copied BRIEF_SYSTEM back ("SEARCH: 3-8 keywords…") → `_copied` → use the message; search ≤8 words.
- Librarian said NOT FOUND to nearly everything (even the soap guide's lye steps, the MTG article).
  `librarian.relevant(message, passage)` (≥half the subject words, `_GENERIC` ignored, 5-letter
  stems + difflib for typos); NOT FOUND + relevant passages → `loose_block` (speaker reads them),
  none → `facts_block` "nothing" note (reworded: the old one was quoted back verbatim).
  EXTRACT_SYSTEM now asks for partial answers. Companion path does the same.
- `PreparedAnswer.images/sources` = cited passages (`Facts.cited()`) or the relevant ones — never
  every searched passage (a first-aid manual cover came up for "halo"). `figures.scan_pdf` skips pages
  1–2 unless captioned. Trace: `librarian_stats` (from `llm.last_complete_stats`), NOT FOUND shows raw.
- `_subject_text`: "who are you / your name / yourself" start fresh (it carried an old subject).
  Companion prompt says who it is when asked.
- Search tab (id still "wikipedia", name "Search", 🔍): `core/library/search_all.search_everything` →
  {book: `KnowledgeBase.search_library` (Chroma `$nin` wikipedia, else keyword) filtered by `relevant`,
  one per page, `source`/`image` (any page image)/`path` (`book_file`); note: obsidian; wikipedia:
  `wiki_lookup.search` (plural → singular titles)}. Panel groups with headers; book reader shows passage
  + page + "Open the book" (desktop); "Ask about this" → `ask_in(domain, subject)` →
  `MainWindow._ask_about_passage` picks the tab reading that folder (or prefix family).
- `_keyword_search` matches words without punctuation + 5-letter stems.

## Model-noticed facts (2026-11-09) — core/you/notice.py
- After `_on_response_done` → `_notice_facts(text)` on a thread (not low power, two_models,
  `config.notice_facts`): `worth_asking` (first-person, ≥4 words, not just a question) → librarian with
  NOTICE_SYSTEM (fixed "field: value" lines or NONE, 80 tokens) → `parse` keeps only values whose words
  all appear in the message (person: Name + relation both in it) → `claims.stage` with confidence 0.55,
  `origin="model"` (claims tables gained an `origin` column via ALTER) → `_NoticedBridge` → Review count.
  Review card kind line adds "· noticed by the model". Settings → You checkbox.

## Chat tab, speed, crisis (2026-11-05, owner uses LFM2.5-1.2B-Instruct)
- Companion = `pipeline._prepare_companion`: COMPANION_PERSONALITY (friend, length follows mood,
  "mhm" ok, no therapy talk) + name + optional 2×90-word background only for COMPANION_TOPICS.
  Never route the companion through the full knowledge prompt (it was ~2,600 tokens → ~3 s).
- Knowledge prompts: ≤ `rag_results` passages, each `trim_passage`d to 130 words.
- Every Ollama request sends `keep_alive` and a fixed `num_ctx` (changing num_ctx reloads the model).
  `warm_up()` runs once Ollama is ready. `llm.last_stats` → trace (load / prompt tokens / eval ms).
- Crisis: `intent_router.is_crisis` (suicide/self-harm wording) → `RoutingPlan.is_crisis` →
  `CRISIS_PROMPT`, any tab. Bare "help" is NOT an emergency (only "please help", "help!" …).
- main.py MUST use `Config.load()` (it used `Config()` — nothing in Settings survived a restart).
- Per-voice profiles: `config.voice_profiles {voice: {name, persona}}`; `use_voice()` makes one active
  (copies into assistant_name/persona, which everything reads); `store_profile()`. Settings →
  Assistant: Voice combo on top, name + personality swap with it. Old single persona migrates in load().
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
- `python -m core.answers.tracer` also prints the last Training Path attempts (problems + raw output start).

## Wikipedia
- Owner hadn't extracted it (old parser found 0 articles anyway). `--extract-only` extracts without
  the hours-long indexing; `core/library/wiki_lookup` reads the extracted files directly.
- `find_articles(text)`: n-grams (1–6 words) → file stems, media-hint suffixes (_film, _tv_series…),
  disambiguation → variant, single words only if Capitalised / quoted / after LEAD_IN ("seen", "about",
  "what is"…), never generic MEDIA_HINTS words. ~0.1 ms with 100k titles (listing: ~0.5 s once, cached).
- Used by `pipeline._wikipedia_background`: chat tab always; knowledge tabs only non-strict and not medical.
- Full-text: `core/library/wiki_index` (SQLite FTS5, porter, title weight 10, last word prefix,
  AND then OR fallback) → `knowledge_base/wikipedia_search.sqlite`. Built after every extraction and by
  `tools/ingest.py --wiki-index`. 50k articles: 3 s build, ~25–65 ms per search.
- NEVER load Wikipedia into memory at startup: `rag.SKIP_IN_MEMORY` skips the folder in the raw-file
  scan and filters it from chunks_fallback.json; ingest never writes it there. (Owner had no JSON →
  raw scan read every extracted article on the UI thread → window never appeared.) InitWorker pre-lists titles.
- Search tab (was Wikipedia) = tab 2 (`id="wikipedia"`, not a chat): `ui/panels/wiki_search.py`, search on a QThread,
  title ranking + vector matches when indexed; "Ask about this" → chat tab "Tell me about <title>".

## Full English Wikipedia (2026-11-09) — core/library/wiki_full.py
- `tools/ingest.py --download-wikipedia-full [--top N] [--workers N]` / `--wikipedia-full DUMP`:
  enwiki multistream dump + index (download_wikipedia generalised: dump_name/sums_name; checksum
  matched on the part after the date). Jobs = 50 bz2 streams each; multiprocessing (spawn on Windows).
- Pass 1 `_scan`: link targets → blake2b 64-bit → two 2^26 uint32 count-min tables (512 MB), workers
  pre-aggregate with np.unique; redirect counts added to targets; top N by score (disambig excluded).
  Saved as `<db>.chosen.npy`. Pass 2 `_extract`: chosen pages → `core/wikitext.clean_wikitext(cut_tail,
  max_words=5000)`; each finished piece in `done_jobs` (resume). Then aliases (titles + redirects to
  kept pages), FTS5 `articles` external-content over `pages` (same columns wiki_index.search reads),
  `.building` → final. Measured ~17 MB/s/core of wikitext here → est. 2–3 h for ~100 GB on 6–8 cores.
- `wiki_lookup`: `FULL_DB` exists → `_titles()` returns `_DbTitles` (SQLite-backed mapping, thread-safe
  lock, aliases→target); `_DbArticle` mimics Path (.stem/.open/.read_text, str = "wikidb:<key>",
  `read_article` resolves it). `search()` uses `keys_starting` + FTS on the DB.
- `core/wikitext.title_key` = file-stem rules lower-cased; shared by builder + lookup.
- APK excludes knowledge_base/*.sqlite etc. Sandbox can't reach dumps.wikimedia.org; tested on
  generated multistream dumps (tests/test_wiki_full.py).

## Chat behaviour (2026-11-06)
- Librarian default `config.DEFAULT_MODEL` = hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest; speaker
  `DEFAULT_SPEAKER` = qwen3:1.7b (setup.bat/.sh pull both). The owner's real log after the localhost fix: speak-start 100–500 ms.
- Tone: `core/tone.detect_tone(text, previous)` → annoyed/low/excited/curious/neutral → one
  "Right now: …" line LAST in the companion prompt + intent `chat_<tone>` → INTENT_TEMPERATURE.
  The model can't read tone itself (owner: "too friendly, like an actor").
- Missing things: `wiki_lookup.asked_about` (specific named thing) + no article →
  "NOT IN YOUR LIBRARY: … say 'I don't have X in my database'". Errs toward not firing.
  "do/what you know about|of X" counts if X is Capitalised, quoted or has a digit ("bt 7274").
  `pipeline._subject_text`: a follow-up that names nothing (≤8 words, "more/their/lore"…) uses the
  newest of the last 4 user messages that did — article or missing note, marked "if they're still
  on the same subject"; "anyway/how was your/hi…" starts fresh. Wiki note ends "that is ALL…".
- Messages: Up/Down recall in `ExpandingTextEdit`; bubbles carry `.msg` (tab-history dict, by
  identity) → ⋯/right-click actions copy/edit/retry/delete handled in `MainWindow._on_message_action`.
  Edit + send deletes from that message on, then sends. Esc cancels an edit when idle.

## Chats (2026-11-06)
- `Tab.history/summary` = the CURRENT chat (rest of the app unchanged); `chat_id/chat_title/chat_created`
  describe it; `Tab.chats` = saved chat records {id,title,created,updated,history,summary}.
  `new_chat()` archives (only if non-empty) and empties; `open_chat/delete_chat/rename_chat/all_chats(query)`.
- `ui/chat/chats_panel.py` = left column of the splitter (chats | chat_view | sidebar). Hidden on the
  Wikipedia tab; phone swaps it with chat_view. Refresh after send/response/switch/reset.
  Button checked state uses `not isHidden()` (isVisibleTo is wrong before the window is shown).
- `clear_tab(id)` empties the open chat; `every_chat=True` also drops saved chats.

## Profile + claims (2026-11-09)
- `core/profile.extract(text)` → `claims.Claim(field, value, note, utterance, confidence)` (regex only,
  errs toward nothing). `profile.learn()` = `claims.stage(extract(text), memory)` — NEVER writes memory.
- `core/you/claims.py` (memory/claims.sqlite): pending → `accept(id, memory, edited_value)` (writes
  memory.user + `verified` row with verified_by_user=1 and the utterance) / `reject(id)` (`rejected`,
  never re-staged). Already-in-profile, pending, verified or rejected values aren't staged again.
- Review tab: `Tab(id="review")` (last in DEFAULT_TABS, not a chat) → `ui/review_panel.ReviewPanel`
  cards; `MainWindow._on_review_changed` sets "Review (n)" via `TabBar.set_label`.
- Companion prompt: `about_line` (memory only = verified) + `earlier_topics(tab)` (last 3 chat TITLES).
  Settings → You and Obsidian Me edits write memory directly (they are the verification).

## Obsidian (2026-11-06) — core/library/obsidian.py, no Qt
- `config.obsidian_vault/obsidian_use_notes`; `obsidian.set_vault()` at startup + after Settings.
- `sync(memory, tab_manager)` (close + Settings → Obsidian → Update now): read back Me.md → write
  <vault>/Prometheus/{Me, <Tab>, Chats/*, Topics/*}.md, only changed files; links are full paths
  `[[Prometheus/…|label]]`. Removes notes it wrote earlier only if still byte-identical.
  State (last Me text/props, written files) in memory/obsidian_state.json.
- Me.md read-back: scalars → file wins; lists → 3-way merge vs last written props (removed in
  Obsidian = removed, learned in app meanwhile = kept). Own tiny YAML subset (no PyYAML).
- Own notes (outside Prometheus/ and dot-folders), cached, re-listed ≤ every 30 s:
  `search_notes` → rag `_tiered_search` as tier 1 (not strict, not medical); `title_hit` → score ≥80.
  `notes_named_in` → companion "From their own notes" (and suppresses the not-in-library rule).

## Model folder (2026-11-06) — core/ai/ollama_local.py, stdlib only
- Models live in `prometheus/models` (gitignored, excluded from the APK). When it has a manifest,
  `OllamaCheckWorker` calls `ollama_local.start()` → own `ollama serve` with OLLAMA_MODELS=models,
  OLLAMA_HOST=127.0.0.1:11435; `LLMEngine._candidate_urls` tries it first; closeEvent stops only ours.
- `--move`: copies manifest + blobs (SHA-256 checked, `.partial` then rename, manifest last), then
  removes the old copy like `ollama rm` (blobs other manifests use are kept; if a blob is locked the
  manifest stays so a re-run finishes). `--pull`, `--has`, `--list`. setup.bat/sh: move, else pull.
- Local HTTP checks use a no-proxy opener (a system proxy swallowed 127.0.0.1 requests).

## Voice (2026-11-06)
- `tools/setup_voice.py`: pip faster-whisper + sounddevice (checked separately) → Whisper model into
  models/whisper/<size> (`faster_whisper.utils.download_model`) → Piper release zip/tar into
  prometheus/piper/ (gitignored, APK-excluded) → voices/ (copies from setup_dir if empty) →
  round trip (Piper speaks TEST_SENTENCE, Whisper transcribes) → microphones. `--check` = no downloads.
- `STTEngine.initialize`: local model dir first, any failure → `available=False` + `error`.
  Mic button: `InputBar.set_voice_available()` after InitWorker (it used to stay disabled forever).
- `TTSEngine`: one persistent Piper (`_PiperProcess`, `--json-input`, absolute model path, prints
  the wav path per line), synth thread + player thread (next sentence made while one plays),
  warm-up at start. Cuts at sentence ends; first piece may end at a comma (>25 chars); >220 chars
  cut anywhere. `clean_for_speech` strips markdown. Measured: gaps 1.6 s → 0, first sound 0.45 → 0.24 s.
- Mic button (`InputBar.set_mic_mode`): idle 🎤 → click starts voice conversation; listening (red)
  → click ends it; speaking (light button, painted black square) → click = `tts.hush(reply_still_coming)`
  (mutes rest of that reply; `begin_reply()`/`stop()` unmute). Send button: click sends, hold 350 ms
  = push-to-talk (`talk_started`/`talk_finished` → `stt.listen(auto_stop=False)`/`finish_listening`).
- `MainWindow._voice_tick` (120 ms): sets the mic look; in voice mode keeps `stt.listen(auto_stop=True)`
  open even while speaking/generating, `stt.set_strict(busy)`; `heard_speech()` while busy →
  `_force_stop(keep_voice_mode=True)` + `tts.stop()` (barge-in). Results come back via `_HeardBridge`
  (Qt signal from Whisper's thread) → `_on_send`. Esc ends voice mode.
- `core/stt.SpeechDetector`: 0.3 s noise calibration, loud = >3× noise (strict: 5×, 2× floor, 0.4 s),
  done after 0.9 s quiet; `start_block` (0.3 s lead-in) trims echo/room before speech; only ~1 s kept
  while waiting. `transcribe_samples` feeds numpy straight to Whisper (vad_filter) on a thread.
- Sandbox: GitHub reachable (Piper + rhasspy/piper etc/test_voice.onnx), Hugging Face blocked.

## Portable folder (2026-11-09) — tools/make_portable.py
- Steps: models (`ollama_local.move_model(dst=MODELS_DIR)` for speaker + librarian) → Ollama install
  copied to prometheus/ollama (Windows: whole Programs\Ollama dir; Linux: bin + ../lib/ollama) →
  Piper dir (with espeak-ng-data) + Whisper snapshot from HF caches → Windows: python.org embeddable
  build (same version, else 3.12.10) in runtime/python, `enable_site_packages` edits ._pth, get-pip,
  `pip install -r requirements.txt`; other OS: `pip download` into wheels/ → launchers. `--check`.
- `ollama_local.find_ollama` prefers prometheus/ollama. Prometheus.bat/prometheus.sh committed;
  setup.bat + debug_run.bat prefer runtime\python. runtime/ and ollama/ gitignored + APK-excluded.
- python.org and bootstrap.pypa.io are blocked in the sandbox: the Python step is untested here.
- Owner's limit: must fit a 16 GB SD/USB → `LIMIT_GIB = 14` checked in step_report (GiB, as Windows
  shows). Owner's sizes (2026-11-09): ollama 6.3, models 2.16, knowledge_base 1.93, voices 0.69 GB.
- GPU libs: kept ALL by default (owner: the next PC may have a different card); `--gpu nvidia|amd|
  intel|none|auto` → `trim_ollama` removes cuda*/rocm*/hip* dirs of other makers, keeps vulkan + CPU.
  `show_gpu_libs()` lists sizes. Python step resumes when runtime exists without PySide6
  (`_has_packages`); launchers use runtime only if `Lib\site-packages\PySide6` (setup.bat: `pip`) exists.

## Icon
- `assets/icon.png` (owner's design: open hand, flame above, navy square). main.py setWindowIcon +
  Windows AppUserModelID; header logo 26px; build_exe makes .ico/.icns (Pillow, gitignored);
  build_apk sets icon.filename + presplash.filename.

## Repo hygiene
- `.gitattributes` keeps `setup.bat` CRLF and `setup.sh` LF; `setup.sh` is committed executable.

## Knowledge base
- In git: only hand-written `knowledge_base/<domain>/*.md` (not README.md, not wikipedia/).
  Downloaded books stay local. Owner's local library (listed 2026-11-05): ~60 PDFs/TXTs across
  22 domains, plus the six hand-written guides (companion, emergency_medicine, food_preservation,
  navigation, soap_making, water_purification).
- `tools/ingest.py` skips identical-content files (SHA-256) so one book can't count as two sources,
  removes deleted files' chunks, replaces edited files' chunks in both stores, and always writes
  `memory/chunks_fallback.json` (even with ChromaDB). Tested with chromadb 1.5 + a fake embedder.
  Exception: with ChromaDB, `wikipedia` chunks are kept out of the JSON (it's loaded into RAM).
- Wikipedia: `python tools/ingest.py --download-wikipedia` (Simple English pages-articles.xml.bz2,
  resume + SHA-1 check). Parser strips any export-schema namespace (the old fixed
  "Export-0.10" string matched nothing → 0 articles) and keeps `<ns>0</ns>` pages only.

## Known gaps
- Voice (Piper, Faster-Whisper) is desktop-only; Android shows no voice.
- Whisper transcription untested here (model download blocked); tools/setup_voice.py's round trip checks it on the owner's PC.
- APK build not yet run end to end (needs the owner's wheels + NDK).
