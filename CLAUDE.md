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
- `session.py` — verdicts: correct +0.25, not_quite −0.10, incorrect −0.25, contradiction → quarantine.
  Lemma at ≥3 successes, ≥80% confidence, ≥75% success rate; demoted below 50%.
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
