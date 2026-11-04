"""
Derivation Engine — the Training Path
=====================================
Derives an answer from first principles instead of looking it up.

The Anchor Principle:
  Every derivation must end in text retrieved from the scientific_reference
  knowledge-base domain, never in what the model remembers. If the anchor
  text is missing from the library, the engine reports a foundational gap
  and declines to derive.

Steps (run() below):
  1. Match the question to a concept in the graph
  2. Retrieve KB anchors for the concept and its tier-1 axioms
  3. Check every parent concept is trained
  4. Check the question has the numbers it needs (situational gap)
  5. Ask the model for three independent derivations
  6. Validate each one — result form, reconstruction, axiom violations
  7. Report the result, or say why it could not be derived

Statuses returned in result["status"]:
  DERIVED            at least one method verified — show it, ask for a verdict
  NEEDS_DATA         a local fact or number is missing — ask the user
  NEEDS_PREREQS      parent concepts are not trained yet — fall back
  FOUNDATIONAL_GAP   the law itself is missing from the KB — fall back
  BLOCKED            quarantined, or no method verified — fall back
  NO_MATCH           no concept fits the question — fall back silently
"""

import re
from typing import Dict, List, Optional

from core.training.graph import TrainingGraph

ANCHOR_DOMAIN = "scientific_reference"
NUM_METHODS   = 3

# Questions that want a number worked out
NUMERIC_ASK = re.compile(
    r"\b(calculate|work out|how much|how many|how long|how far|"
    r"what (is|would be|will be) the (value|power|current|voltage|resistance|"
    r"load|moment|stress|volume|mass|distance|time|latitude|longitude))\b"
)

DERIVE_SYSTEM = (
    "You derive results from first principles.\n"
    "Use ONLY the foundations you are given. Do not rely on remembering the answer.\n"
    "Never state the final result before you have derived it.\n"
    "Write plain text. No markdown, no bold, no headings other than the METHOD labels."
)


def normalise_formula(text: str) -> str:
    """Lower-case, unify multiplication and power signs, squeeze spaces."""
    t = text.lower()
    for sign in ("×", "·", "⋅", "∙"):
        t = t.replace(sign, "*")
    t = t.replace("²", "^2").replace("³", "^3").replace("−", "-")
    return re.sub(r"\s+", " ", t).strip()


def squash(text: str) -> str:
    """Lower-case with all whitespace removed — used for anchor matching."""
    return re.sub(r"\s+", "", text.lower())


class DerivationEngine:

    def __init__(self, graph: TrainingGraph, knowledge, llm):
        self.graph     = graph
        self.knowledge = knowledge
        self.llm       = llm

    # ── Step 1: concept matching ───────────────────────────────────────────

    def get_concept_or_request(self, query: str, tab_id: str) -> Optional[Dict]:
        """
        Best-matching derivable concept for this tab, or None.
        Tier-1 axioms are excluded — they are quoted, not derived,
        so the Knowledge Path answers those.
        """
        q = query.lower()
        best, best_score = None, 0
        for node in self.graph.concepts_for_tab(tab_id):
            if node["tier"] == 1:
                continue
            # Longer keyword matches count for more ("voltage divider" > "voltage")
            score = sum(len(k) for k in node["keywords"] if k in q)
            if score > best_score:
                best, best_score = node, score
        return best

    # ── Step 2: KB anchors ─────────────────────────────────────────────────

    def _kb_anchors(self, concept: Dict) -> Dict[str, Optional[Dict]]:
        """
        For the concept and each tier-1 axiom it rests on, find KB text
        that contains its anchor terms. Returns {concept_id: anchor or None}.
        """
        needed = [concept["id"]] + [
            a for a in self.graph.ancestors(concept["id"])
            if self.graph.get(a)["tier"] == 1
        ]
        return {cid: self._find_anchor(self.graph.get(cid)) for cid in needed}

    def _find_anchor(self, node: Dict) -> Optional[Dict]:
        chunks = []

        # First: the normal retrieval route, limited to the anchor domain
        search = getattr(self.knowledge, "_search_domains", None)
        if search:
            try:
                chunks = search(node["anchor_query"], [ANCHOR_DOMAIN], 6) or []
            except Exception:
                chunks = []

        # Second: scan the loaded KB chunks directly (keyword index)
        fallback = [
            c for c in getattr(self.knowledge, "_fallback_chunks", [])
            if c.get("domain") == ANCHOR_DOMAIN
        ]

        for chunk in list(chunks) + fallback:
            content = chunk.get("content", "")
            flat = squash(content)
            for term in node["anchor_terms"]:
                if term in flat:
                    return {
                        "source":  chunk.get("source", ANCHOR_DOMAIN),
                        "snippet": self._snippet(content, term),
                    }
        return None

    @staticmethod
    def _snippet(content: str, term: str, before: int = 25, after: int = 45) -> str:
        """About 70 words of the chunk around where the anchor term appears."""
        words = content.split()
        for i in range(len(words)):
            if term in squash(" ".join(words[i:i + 14])):
                return " ".join(words[max(0, i - before): i + after])
        return " ".join(words[:after])

    # ── Step 4: situational gaps ───────────────────────────────────────────

    def _classify_gap(self, concept: Dict, anchors: Dict, query: str) -> Optional[Dict]:
        """
        Foundational gap: a universal law is missing from the KB.
            The system declines. It never asks the user to supply a law.
        Situational gap: a local number or fact is missing.
            The system asks the user for it.
        """
        missing = [cid for cid, a in anchors.items() if a is None]
        if missing:
            return {
                "kind": "FOUNDATIONAL_GAP",
                "missing": [self.graph.get(c)["name"] for c in missing],
            }

        q = query.lower()
        if concept["inputs"] and NUMERIC_ASK.search(q) and not re.search(r"\d", q):
            return {"kind": "NEEDS_DATA", "missing": concept["inputs"]}
        return None

    # ── Step 5: derivation ─────────────────────────────────────────────────

    def derive(self, concept: Dict, anchors: Dict, query: str,
               num_methods: int = NUM_METHODS, tab_id: str = "") -> Dict:
        # The concept's own anchor is held back: it is what the result is
        # checked against, so giving it to the model would hand over the answer
        foundations = []
        for cid, anchor in anchors.items():
            if cid == concept["id"]:
                continue
            node = self.graph.get(cid)
            foundations.append(
                f"- {node['name']}: {node['statement']}\n"
                f"  Library text ({anchor['source']}): \"{anchor['snippet']}\""
            )
        for pid in concept["parents"]:
            if pid not in anchors:
                p = self.graph.get(pid)
                foundations.append(f"- {p['name']} (already derived): {p['statement']}")

        # Lower confidence → longer, more explicit steps
        confidence = concept["confidence"]
        if confidence < 0.3:
            detail = "Show every step and name the foundation each step uses."
            max_tokens = 900
        elif confidence < 0.7:
            detail = "Show the key steps and name the foundations you use."
            max_tokens = 700
        else:
            detail = "Be brief: the essential steps only."
            max_tokens = 500

        prompt = (
            f"Question: {query}\n\n"
            f"Derive: {concept['name']}\n\n"
            f"Foundations you may use:\n" + "\n".join(foundations) + "\n\n"
            f"Give {num_methods} independent methods that each reach the result "
            f"from the foundations alone. {detail}\n"
            f"Use exactly this layout:\n"
            + "".join(
                f"METHOD {i}:\n<steps, one per line>\nRESULT: <final relationship>\n"
                for i in range(1, num_methods + 1)
            )
        )

        raw = self.llm.complete(
            DERIVE_SYSTEM, prompt, tab_id=tab_id,
            temperature=0.2, max_tokens=max_tokens,
        )
        methods = self._parse_methods(raw)
        checked = [self._check_method(concept, m) for m in methods]
        violations = self._validate_against_axioms(concept, raw)
        return {"raw": raw, "methods": checked, "violations": violations}

    @staticmethod
    def _parse_methods(raw: str) -> List[Dict]:
        parts = re.split(r"(?im)^\s*\**\s*method\s*(\d)\s*[:.)]?\**", raw)
        methods = []
        # re.split gives [preamble, num, body, num, body, ...]
        for i in range(1, len(parts) - 1, 2):
            body = parts[i + 1]
            m = re.search(r"(?im)^\s*\**\s*result\s*[:\-]\**\s*(.+)$", body)
            result = m.group(1).strip() if m else ""
            steps_text = body[:m.start()] if m else body
            steps = [s.strip(" -*\t") for s in steps_text.strip().splitlines() if s.strip(" -*\t")]
            methods.append({"number": int(parts[i]), "steps": steps, "result": result})
        return methods

    def _check_method(self, concept: Dict, method: Dict) -> Dict:
        markers = concept["result_markers"]

        def matches(text: str) -> bool:
            t = normalise_formula(text)
            return any(re.search(m, t) for m in markers) if markers else bool(t)

        problems = []
        if not method["result"]:
            problems.append("no result line")
        elif not matches(method["result"]):
            problems.append("result does not match the expected form")

        # Reconstruction invariant: the result must be reached, not assumed
        if len(method["steps"]) < 2:
            problems.append("too few steps")
        elif markers and matches(method["steps"][0]):
            problems.append("states the result before deriving it")

        # Must lean on at least one given foundation
        body = squash(" ".join(method["steps"]))
        cites = False
        for pid in concept["parents"]:
            p = self.graph.get(pid)
            names = [squash(p["name"].split("(")[0])] + [squash(k) for k in p["keywords"]]
            if any(n and n in body for n in names) or any(t in body for t in p["anchor_terms"]):
                cites = True
                break
        if not cites and "foundation" not in body:
            problems.append("does not use a given foundation")

        return {**method, "ok": not problems, "problems": problems}

    def _validate_against_axioms(self, concept: Dict, raw: str) -> List[str]:
        """Names of tier-1 axioms the derivation contradicts."""
        text = normalise_formula(raw)
        broken = []
        for aid in self.graph.ancestors(concept["id"]):
            axiom = self.graph.get(aid)
            if axiom["tier"] != 1:
                continue
            if any(re.search(v, text) for v in axiom["violations"]):
                broken.append(axiom["name"])
        return broken

    # ── Full run ───────────────────────────────────────────────────────────

    def run(self, query: str, tab_id: str) -> Dict:
        # Step 1: match
        concept = self.get_concept_or_request(query, tab_id)
        if not concept:
            return {"status": "NO_MATCH"}
        base = {"concept_id": concept["id"], "concept_name": concept["name"]}

        if concept["quarantined"]:
            return {**base, "status": "BLOCKED",
                    "reason": f"{concept['name']} is on hold after a contradiction."}

        # Step 2: anchors
        anchors = self._kb_anchors(concept)

        # Step 3: prerequisites
        missing = self.graph.missing_parents(concept["id"])
        if missing:
            names = [self.graph.get(m)["name"] for m in missing]
            return {**base, "status": "NEEDS_PREREQS", "missing": names,
                    "reason": "First ask me to explain: " + ", ".join(names) + "."}

        # Step 4: gaps
        gap = self._classify_gap(concept, anchors, query)
        if gap and gap["kind"] == "FOUNDATIONAL_GAP":
            return {**base, "status": "FOUNDATIONAL_GAP", "missing": gap["missing"],
                    "reason": ("The library is missing the foundation for "
                               + ", ".join(gap["missing"])
                               + ". Run ingest.py to index scientific_reference.")}
        if gap and gap["kind"] == "NEEDS_DATA":
            ask = ", ".join(gap["missing"])
            return {**base, "status": "NEEDS_DATA", "missing": gap["missing"],
                    "text": (f"I can work this out from first principles "
                             f"({concept['name']}), but I need the numbers first: {ask}.")}

        # Steps 5–6: derive and validate
        outcome = self.derive(concept, anchors, query, tab_id=tab_id)
        ok = [m for m in outcome["methods"] if m["ok"]]

        self.graph.record_attempt(concept["id"], {
            "query":      query[:200],
            "methods":    len(outcome["methods"]),
            "verified":   len(ok),
            "violations": outcome["violations"],
            "problems":   [m["problems"] for m in outcome["methods"]],
        })

        if outcome["violations"]:
            reason = "contradicts " + ", ".join(outcome["violations"])
            self.graph.quarantine(concept["id"], reason)
            return {**base, "status": "BLOCKED",
                    "reason": f"The derivation {reason}, so {concept['name']} is on hold."}

        if not ok:
            return {**base, "status": "BLOCKED",
                    "reason": "None of the derivations checked out."}

        # Step 7: present
        best = max(ok, key=lambda m: len(m["steps"]))
        sources = sorted({a["source"] for a in anchors.values()})
        return {
            **base,
            "status":        "DERIVED",
            "methods_ok":    len(ok),
            "methods_total": len(outcome["methods"]) or NUM_METHODS,
            "result":        best["result"],
            "anchors":       sources,
            "text":          self._format(concept, anchors, best, len(ok),
                                          len(outcome["methods"]) or NUM_METHODS),
        }

    def _format(self, concept, anchors, method, n_ok, n_total) -> str:
        lines = [f"Worked out from first principles: {concept['name']}", "", "Starting from:"]
        for cid in anchors:
            if cid == concept["id"]:
                continue
            node = self.graph.get(cid)
            lines.append(f"• {node['name']} — {node['statement']}")
        for pid in concept["parents"]:
            if pid not in anchors:
                p = self.graph.get(pid)
                lines.append(f"• {p['name']} — {p['statement']}")
        lines.append("")
        lines.extend(f"{i}. {s}" for i, s in enumerate(method["steps"], 1))
        lines += ["", f"Result: {method['result']}"]
        own = anchors.get(concept["id"])
        if own:
            label = own["source"].replace("_", " ").title()
            lines.append(f"Checked against the library ({label}): {concept['statement']}")
        lines.append("")
        lines.append(f"{n_ok} of {n_total} separate methods reached this result.")
        if concept["sample_problems"]:
            sp = concept["sample_problems"][0]
            lines.append(f"Quick check: {sp['q']} → {sp['a']}")
        lines.append("Is this right? Your answer is how this result earns trust.")
        return "\n".join(lines)
