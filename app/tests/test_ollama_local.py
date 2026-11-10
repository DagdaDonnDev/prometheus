"""prometheus/models: moving a model in, and running our own Ollama for it."""

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core.ai import ollama_local as ol


def _blob(store: Path, data: bytes) -> str:
    d = "sha256:" + hashlib.sha256(data).hexdigest()
    (store / "blobs").mkdir(parents=True, exist_ok=True)
    (store / "blobs" / d.replace(":", "-")).write_bytes(data)
    return d


def _model(store: Path, name: str, blobs) -> Path:
    digests = [_blob(store, b) for b in blobs]
    m = store / ol._manifest_rel(name)
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps({"config": {"digest": digests[0]},
                             "layers": [{"digest": d} for d in digests[1:]]}))
    return m


class TestNames(unittest.TestCase):
    def test_manifest_paths(self):
        self.assertEqual(ol._manifest_rel("llama3.2:3b").as_posix(),
                         "manifests/registry.ollama.ai/library/llama3.2/3b")
        self.assertEqual(ol._manifest_rel(ol.DEFAULT_MODEL).as_posix(),
                         "manifests/hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF/latest")
        self.assertEqual(ol._manifest_rel("bob/x").as_posix(),
                         "manifests/registry.ollama.ai/bob/x/latest")


class TestMove(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "home_ollama"
        self.dst = Path(self.tmp.name) / "prometheus_models"
        self.quiet = lambda *_: None

    def tearDown(self):
        self.tmp.cleanup()

    def test_move_keeps_blobs_other_models_use(self):
        _model(self.src, ol.DEFAULT_MODEL, [b"config", b"weights" * 1000, b"shared template"])
        _model(self.src, "llama3.2:3b", [b"other config", b"shared template"])
        ok = ol.move_model(ol.DEFAULT_MODEL.lower(), self.src, self.dst, say=self.quiet)
        self.assertTrue(ok)
        # Here: manifest + all three blobs
        self.assertIsNotNone(ol._find_manifest(self.dst, ol.DEFAULT_MODEL))
        self.assertEqual(len(list((self.dst / "blobs").iterdir())), 3)
        # Old folder: our manifest gone, our own blobs gone, the shared one kept
        self.assertIsNone(ol._find_manifest(self.src, ol.DEFAULT_MODEL))
        left = {p.read_bytes() for p in (self.src / "blobs").iterdir()}
        self.assertEqual(left, {b"other config", b"shared template"})
        # Doing it again is harmless
        self.assertTrue(ol.move_model(ol.DEFAULT_MODEL, self.src, self.dst, say=self.quiet))

    def test_bad_copy_is_not_moved(self):
        m = _model(self.src, ol.DEFAULT_MODEL, [b"config", b"weights"])
        bad = next(p for p in (self.src / "blobs").iterdir() if p.read_bytes() == b"weights")
        bad.write_bytes(b"corrupted")                 # doesn't match its name any more
        self.assertFalse(ol.move_model(ol.DEFAULT_MODEL, self.src, self.dst, say=self.quiet))
        self.assertTrue(m.exists())                   # old copy untouched
        self.assertIsNone(ol._find_manifest(self.dst, ol.DEFAULT_MODEL))

    def test_locked_old_copy_is_finished_next_time(self):
        _model(self.src, ol.DEFAULT_MODEL, [b"config", b"weights"])
        real_unlink = Path.unlink
        def locked(self_, *a, **k):
            if self_.parent.name == "blobs" and self_.read_bytes() == b"weights":
                raise PermissionError("in use")
            return real_unlink(self_, *a, **k)
        notes = []
        with mock.patch.object(Path, "unlink", locked):
            self.assertTrue(ol.move_model(ol.DEFAULT_MODEL, self.src, self.dst, say=notes.append))
        self.assertTrue(any("still in use" in n for n in notes))
        self.assertIsNotNone(ol._find_manifest(self.src, ol.DEFAULT_MODEL))   # kept for next time
        # Ollama closed: run again
        self.assertTrue(ol.move_model(ol.DEFAULT_MODEL, self.src, self.dst, say=self.quiet))
        self.assertIsNone(ol._find_manifest(self.src, ol.DEFAULT_MODEL))
        self.assertEqual(list((self.src / "blobs").iterdir()), [])

    def test_missing_model(self):
        self.assertFalse(ol.move_model("nothing:here", self.src, self.dst, say=self.quiet))

    def test_local_models_listing(self):
        with mock.patch.object(ol, "MODELS_DIR", self.dst):
            self.assertFalse(ol.has_local_models())
            _model(self.dst, ol.DEFAULT_MODEL, [b"c"])
            _model(self.dst, "llama3.2:3b", [b"d"])
            self.assertEqual(ol.local_models(),
                             ["hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest", "llama3.2:3b"])


FAKE_SERVE = r'''
import http.server, json, os
host, port = os.environ["OLLAMA_HOST"].split(":")
assert os.environ["OLLAMA_MODELS"]
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        names = [n for n in os.environ.get("FAKE_NAMES", "").split(",") if n]
        body = json.dumps({"models": [{"name": n} for n in names]}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
http.server.HTTPServer((host, int(port)), H).serve_forever()
'''


class TestOwnServer(unittest.TestCase):
    def test_start_connect_stop(self):
        # A stand-in for `ollama serve`: run as `python serve` from a temp folder
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "serve").write_text(FAKE_SERVE)
        models = root / "models"
        _model(models, ol.DEFAULT_MODEL, [b"c"])
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        host = f"127.0.0.1:{port}"
        cwd = os.getcwd()
        os.chdir(root)
        self.addCleanup(os.chdir, cwd)
        with mock.patch.multiple(ol, MODELS_DIR=models, HOST=host, URL=f"http://{host}", PORTS=(port,)), \
                mock.patch.dict(os.environ, {"FAKE_NAMES": ol.DEFAULT_MODEL}), \
                mock.patch.object(ol, "find_ollama", return_value=sys.executable):
            self.assertTrue(ol.start(wait=10))
            self.assertTrue(ol.answering())
            self.assertEqual(ol.active_url(), f"http://{host}")
            # The app's Ollama client tries it first
            from core.ai.llm import LLMEngine
            from core.app.config import Config
            llm = LLMEngine(Config())
            self.assertEqual(llm._candidate_urls()[0], f"http://{host}")
            self.assertTrue(llm.is_available())
            self.assertEqual(llm.base_url, f"http://{host}")
            ol.stop()
            time.sleep(0.3)
            self.assertFalse(ol.answering())

    def test_old_server_with_other_models_is_left_alone(self):
        # Owner, after moving the folder into app/: an Ollama still running on
        # 11435 from the old place said the models weren't there
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "serve").write_text(FAKE_SERVE)
        models = root / "models"
        _model(models, ol.DEFAULT_MODEL, [b"c"])
        ports = []
        for _ in range(2):
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                ports.append(s.getsockname()[1])
        old = subprocess.Popen([sys.executable, str(root / "serve")],
                               env={**os.environ, "OLLAMA_HOST": f"127.0.0.1:{ports[0]}",
                                    "OLLAMA_MODELS": "elsewhere", "FAKE_NAMES": ""})
        self.addCleanup(old.kill)
        for _ in range(40):
            if ol.answering(f"http://127.0.0.1:{ports[0]}"):
                break
            time.sleep(0.1)
        cwd = os.getcwd()
        os.chdir(root)
        self.addCleanup(os.chdir, cwd)
        with mock.patch.multiple(ol, MODELS_DIR=models, PORTS=tuple(ports), _proc=None), \
                mock.patch.dict(os.environ, {"FAKE_NAMES": ol.DEFAULT_MODEL}), \
                mock.patch.object(ol, "find_ollama", return_value=sys.executable):
            self.assertTrue(ol.start(wait=10))
            self.assertEqual(ol.active_url(), f"http://127.0.0.1:{ports[1]}")
            self.assertTrue(ol.serves_ours(ol.URL))
            ol.stop()
        ol._use(11435)

    def test_old_ollama_on_our_port_is_stopped(self):
        # It can sit on graphics-card memory (owner: 1.1 GB free of 8 GB)
        import shutil as sh
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "serve").write_text(FAKE_SERVE)
        fake_ollama = root / "ollama"                       # a process named "ollama"
        os.symlink(os.path.realpath(sys.executable), fake_ollama)
        models = root / "models"
        _model(models, ol.DEFAULT_MODEL, [b"c"])
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        old = subprocess.Popen([str(fake_ollama), str(root / "serve")],
                               env={**os.environ, "OLLAMA_HOST": f"127.0.0.1:{port}",
                                    "OLLAMA_MODELS": "elsewhere", "FAKE_NAMES": ""})
        self.addCleanup(old.kill)
        for _ in range(40):
            if ol.answering(f"http://127.0.0.1:{port}"):
                break
            time.sleep(0.1)
        with mock.patch.multiple(ol, MODELS_DIR=models, PORTS=(port,)):
            done = ol.clear_stale()
        if not done:
            self.skipTest("can't see which process holds the port here (no lsof)")
        self.assertIn(f"port {port}", done[0])
        old.wait(timeout=5)
        self.assertIsNotNone(old.poll())

    def test_a_server_that_isnt_ollama_is_left_alone(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "serve").write_text(FAKE_SERVE)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        other = subprocess.Popen([sys.executable, str(root / "serve")],
                                 env={**os.environ, "OLLAMA_HOST": f"127.0.0.1:{port}",
                                      "OLLAMA_MODELS": "x", "FAKE_NAMES": ""})
        self.addCleanup(other.kill)
        for _ in range(40):
            if ol.answering(f"http://127.0.0.1:{port}"):
                break
            time.sleep(0.1)
        with mock.patch.multiple(ol, PORTS=(port,)):
            self.assertEqual(ol.clear_stale(), [])
        self.assertIsNone(other.poll())

    def test_not_used_without_local_models(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(ol, "MODELS_DIR", Path(t)):
            self.assertFalse(ol.start())
            self.assertEqual(ol.active_url(), "")


class TestSwapWatch(unittest.TestCase):
    def test_two_swaps_mean_one_model(self):
        from core.ai.llm import LLMEngine
        from core.ai.librarian import Librarian
        from core.app.config import Config
        llm = LLMEngine(Config())
        lib = Librarian(llm)
        llm._note_load("qwen3:1.7b", 1400)       # first loads don't count
        llm._note_load("lfm", 1400)
        self.assertTrue(lib.enabled())
        llm._note_load("qwen3:1.7b", 30)          # stayed loaded
        llm._note_load("lfm", 1700)               # swapped back in
        self.assertTrue(lib.enabled())
        llm._note_load("qwen3:1.7b", 1600)
        self.assertFalse(lib.enabled())           # thrashing: librarian off


if __name__ == "__main__":
    unittest.main()
