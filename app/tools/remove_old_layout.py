"""
Tidy up after the November 2026 reorganisation.

The project moved into folders (tools/, core/ai, core/answers, core/library,
core/you, core/voice, core/app, ui/chat, ui/panels, ui/dialogs). Unzipping
the new files over an older copy leaves the old ones behind. This deletes
each old file — but only when its new copy is already in place, so nothing
that's still needed can go.

    python tools/remove_old_layout.py           # delete the leftovers
    python tools/remove_old_layout.py --dry     # just list them
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CORE = {
 "ai":      ["llm","librarian","llm_bounds","tone","context_manager","embedder","ollama_local"],
 "answers": ["pipeline","intent_router","decision_gate","sufficiency_gate","contradiction",
             "confidence","memory_filter","tracer","eval_harness"],
 "library": ["rag","wiki_lookup","wiki_index","wiki_full","wikitext","obsidian"],
 "you":     ["memory","profile","claims","tabs","backup"],
 "voice":   ["tts","stt","voice_manager"],
 "app":     ["config","paths","platform_info","features","map_engine","p2p"],
}
UI = {
 "chat":    ["chat_view","input_bar","chats_panel","nav_panel","welcome"],
 "panels":  ["sidebar","review_panel","wiki_search","messages_view","quick_access"],
 "dialogs": ["settings_dialog","assessment","dev_panel","doc_context","skill_tree","map_view"],
}
TOOLS = ["ingest","setup_voice","make_portable","bootstrap","bootstrap_map","generate_reference",
         "build_apk","build_exe"]


def moves():
    """(old file, new file) for everything that moved."""
    for sub, mods in CORE.items():
        for m in mods:
            yield ROOT / "core" / f"{m}.py", ROOT / "core" / sub / f"{m}.py"
    for sub, mods in UI.items():
        for m in mods:
            yield ROOT / "ui" / f"{m}.py", ROOT / "ui" / sub / f"{m}.py"
    for t in TOOLS:
        yield ROOT / f"{t}.py", ROOT / "tools" / f"{t}.py"
    yield ROOT / "kb_inventory.txt", ROOT / "tools" / "kb_inventory.txt"
    # replaced by ui/chat/nav_panel.py
    yield ROOT / "ui" / "tab_bar.py", ROOT / "ui" / "chat" / "nav_panel.py"


def main() -> int:
    dry = "--dry" in sys.argv
    gone = kept = 0
    for old, new in moves():
        if not old.exists():
            continue
        if not new.exists():
            print(f"[!]  keeping {old.relative_to(ROOT)} — {new.relative_to(ROOT)} isn't there yet")
            kept += 1
            continue
        print(f"{'would delete' if dry else 'deleted'}  {old.relative_to(ROOT)}")
        if not dry:
            old.unlink()
        gone += 1
        # its compiled copy, if any
        for pyc in (old.parent / "__pycache__").glob(f"{old.stem}.*.pyc"):
            if not dry:
                pyc.unlink()
    print()
    print(f"{gone} old file(s) {'to delete' if dry else 'deleted'}" + (f", {kept} kept" if kept else "") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
