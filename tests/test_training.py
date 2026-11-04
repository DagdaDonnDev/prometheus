"""
Training Path tests — no Ollama or Qt needed.
Run from the project root:  python -m unittest discover tests
"""

import tempfile
import threading
import unittest
from pathlib import Path

from core.intent_router import IntentRouter
from core.training.graph import TrainingGraph
from core.training.engine import DerivationEngine
from core.training.session import TrainingSession
from core.training.axiom_seeds import CONCEPTS
from core.rag import KnowledgeBase


GOOD_POWER = """METHOD 1:
Start from conservation of energy: power is energy per unit time.
Voltage is energy per unit charge and current is charge per unit time.
Multiply them: (energy/charge) x (charge/time) = energy/time.
RESULT: P = V × I
METHOD 2:
From Ohm's law V = I R, substitute into the energy rate.
Energy per second through the resistor is V times the charge per second.
RESULT: P = V I
METHOD 3:
Using Ohm's law, I = V / R.
Power is V × I so substituting gives V² / R.
RESULT: P = V² / R
"""

BAD_POWER = """METHOD 1:
P = V I because everyone knows it.
RESULT: P = V I
METHOD 2:
It is just remembered.
RESULT: P = V + I
"""

VIOLATING = """METHOD 1:
Using conservation of energy, energy can be created by the resistor.
So more comes out than goes in.
RESULT: P = V I
"""


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0
        self.prompts = []

    def complete(self, system, prompt, **kw):
        self.calls += 1
        self.prompts.append(prompt)
        return self.reply


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.graph = TrainingGraph(d / "graph.json", d / "history.json")
        self.kb = KnowledgeBase()   # keyword index over knowledge_base/

    def tearDown(self):
        self.tmp.cleanup()

    def engine(self, reply):
        return DerivationEngine(self.graph, self.kb, FakeLLM(reply))


class TestSeeds(unittest.TestCase):
    def test_parents_exist_and_tiers_consistent(self):
        ids = {c["id"]: c for c in CONCEPTS}
        for c in CONCEPTS:
            for p in c["parents"]:
                self.assertIn(p, ids, c["id"])
            if c["parents"]:
                expected = 2 if all(ids[p]["tier"] == 1 for p in c["parents"]) else 3
                self.assertEqual(c["tier"], expected, c["id"])
            else:
                self.assertEqual(c["tier"], 1, c["id"])

    def test_every_tab_has_derivable_concepts(self):
        for tab in ("electronics", "chemistry", "build", "navigation"):
            n = [c for c in CONCEPTS if tab in c["tabs"] and c["tier"] > 1]
            self.assertGreaterEqual(len(n), 5, tab)


class TestRouting(unittest.TestCase):
    def test_training_flag(self):
        r = IntentRouter()
        self.assertTrue(r.route("explain why power equals voltage times current", "electronics").use_training_path)
        self.assertFalse(r.route("how do i wire a battery", "electronics").use_training_path)       # procedure
        self.assertFalse(r.route("what is a voltage divider", "medical").use_training_path)         # wrong tab
        self.assertFalse(r.route("help he got shocked right now", "electronics").use_training_path)  # emergency


class TestGraph(Base):
    def test_axioms_locked(self):
        self.assertEqual(self.graph.apply_delta("ohms_law", -0.9), 1.0)

    def test_cap_and_cascade(self):
        g = self.graph
        g.apply_delta("electrical_power", 0.9)            # T2, parents are axioms
        self.assertAlmostEqual(g.get("electrical_power")["confidence"], 0.9)
        # T3 capped at its weakest parent (kirchhoff_voltage is untrained → 0)
        g.apply_delta("series_resistance", 0.8)
        self.assertEqual(g.get("series_resistance")["confidence"], 0.0)
        g.apply_delta("kirchhoff_voltage", 0.6)
        g.apply_delta("series_resistance", 0.8)
        self.assertAlmostEqual(g.get("series_resistance")["confidence"], 0.6)
        # Lowering a parent pushes the cap down to children and grandchildren
        g.apply_delta("voltage_divider", 0.5)
        g.apply_delta("kirchhoff_voltage", -0.3)
        self.assertAlmostEqual(g.get("series_resistance")["confidence"], 0.3)
        self.assertLessEqual(g.get("voltage_divider")["confidence"], 0.3)
        # Quarantine cascades to 0
        g.quarantine("kirchhoff_voltage", "test")
        self.assertEqual(g.get("series_resistance")["confidence"], 0.0)
        self.assertEqual(g.get("voltage_divider")["confidence"], 0.0)

    def test_success_counted_once(self):
        g = self.graph
        g.record_attempt("electrical_power", {"verified": 3})
        self.assertEqual(g.get("electrical_power")["success_count"], 0)
        g.apply_delta("electrical_power", 0.25, success=True)
        self.assertEqual(g.get("electrical_power")["success_count"], 1)

    def test_rlock_no_deadlock(self):
        done = threading.Event()

        def work():
            self.graph.apply_delta("kirchhoff_voltage", 0.6)
            self.graph.quarantine("kirchhoff_voltage", "x")
            done.set()

        t = threading.Thread(target=work, daemon=True)
        t.start()
        self.assertTrue(done.wait(5), "graph update deadlocked")

    def test_persistence(self):
        self.graph.apply_delta("dilution", 0.5, success=True)
        reloaded = TrainingGraph(self.graph._graph_path, self.graph._history_path)
        self.assertAlmostEqual(reloaded.get("dilution")["confidence"], 0.5)
        self.assertEqual(reloaded.get("dilution")["success_count"], 1)


class TestEngine(Base):
    def test_kb_anchor_found(self):
        e = self.engine(GOOD_POWER)
        anchors = e._kb_anchors(self.graph.get("electrical_power"))
        self.assertTrue(all(anchors.values()), anchors)

    def test_all_anchors_resolve(self):
        e = self.engine("")
        for c in CONCEPTS:
            self.assertIsNotNone(e._find_anchor(self.graph.get(c["id"])), c["id"])

    def test_derived(self):
        r = self.engine(GOOD_POWER).run("explain why power equals voltage times current", "electronics")
        self.assertEqual(r["status"], "DERIVED", r)
        self.assertEqual(r["methods_ok"], 3)
        self.assertIn("Result:", r["text"])

    def test_answer_not_given_to_model(self):
        e = self.engine(GOOD_POWER)
        e.run("explain electrical power", "electronics")
        foundations = e.llm.prompts[0].split("Foundations you may use:")[1].split("Give ")[0]
        self.assertNotIn("Electrical power", foundations)
        self.assertIn("Ohm's law", foundations)

    def test_bad_derivation_blocked(self):
        r = self.engine(BAD_POWER).run("explain electrical power", "electronics")
        self.assertEqual(r["status"], "BLOCKED")

    def test_axiom_violation_quarantines(self):
        r = self.engine(VIOLATING).run("explain electrical power", "electronics")
        self.assertEqual(r["status"], "BLOCKED")
        self.assertTrue(self.graph.get("electrical_power")["quarantined"])

    def test_prereqs(self):
        e = self.engine(GOOD_POWER)
        r = e.run("explain a voltage divider", "electronics")
        self.assertEqual(r["status"], "NEEDS_PREREQS")
        self.assertEqual(e.llm.calls, 0)

    def test_needs_data(self):
        r = self.engine(GOOD_POWER).run("calculate the power used by my lamp", "electronics")
        self.assertEqual(r["status"], "NEEDS_DATA")

    def test_foundational_gap(self):
        class EmptyKB:
            _fallback_chunks = []
            def _search_domains(self, *a):
                return []
        e = DerivationEngine(self.graph, EmptyKB(), FakeLLM(GOOD_POWER))
        r = e.run("explain electrical power", "electronics")
        self.assertEqual(r["status"], "FOUNDATIONAL_GAP")
        self.assertEqual(e.llm.calls, 0)

    def test_no_match(self):
        self.assertEqual(self.engine(GOOD_POWER).run("explain the weather", "electronics")["status"], "NO_MATCH")


class TestSession(Base):
    def test_lemma_promotion_and_demotion(self):
        s = TrainingSession(self.graph)
        fake = {"status": "DERIVED", "concept_id": "dilution", "concept_name": "Dilution"}
        for _ in range(4):
            s.remember("chemistry", dict(fake))
            msg = s.apply_verdict("chemistry", "correct")
        self.assertEqual(self.graph.get("dilution")["trust_level"], "derived")
        self.assertIn("trusted result", msg)
        s.remember("chemistry", dict(fake))
        s.apply_verdict("chemistry", "contradiction")
        node = self.graph.get("dilution")
        self.assertTrue(node["quarantined"])
        self.assertNotEqual(node["trust_level"], "derived")


if __name__ == "__main__":
    unittest.main()
