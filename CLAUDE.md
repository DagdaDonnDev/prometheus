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

## Query flow (ui/main_window.py)
`_generate_response` → trace + `IntentRouter.route()` → fork:
- **Training Path** when `routing_plan.use_training_path` (tab in electronics/chemistry/build/navigation,
  intent EXPLAIN or ASSESS, not strict). `TrainingWorker` (QThread) runs `DerivationEngine.run()`.
  DERIVED / NEEDS_DATA are shown; anything else falls back to the Knowledge Path with a chat note.
- **Knowledge Path** `_run_knowledge_path`: tiered RAG → sufficiency gate → contradiction →
  decision gate (+ sufficiency override) → bounds → memory filter → map context →
  `build_system_prompt` → CLARIFY (no LLM) or `LLMWorker` stream → TTS.
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
- Anchors live in `knowledge_base/scientific_reference/` (the only committed KB folder).
  If you add a concept, add matching text there and check `TestEngine.test_all_anchors_resolve`.

## Conventions (owner's standing preferences)
- Colour never on text — use left bars, borders, small bar widgets. No pills/badges.
- Dark dialog backdrops; plain, short wording in the UI.
- Readable step-by-step comments ("Step 1: …").
- Keep README current with every change.
- Desktop and Android should behave as one app — a change on one side is made on the other.
  NOTE: the Android app is generated inside `build_apk.py` (Kivy) and currently calls
  `llm.stream` directly with none of the decision layers or the Training Path.
- Deliver as a commit plus a zip of changed files; the owner pushes.

## Known gaps
- Android parity (above).
- Pre-populated KB folders described in README (water_purification, emergency_medicine, …) are not in the repo.
- `ingest.py` JSON fallback appends on `--rebuild` instead of replacing (duplicates).
- Vector (ChromaDB) anchor retrieval untested in CI; keyword fallback path is tested.
