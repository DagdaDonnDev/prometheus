"""tools/make_portable.py: everything gathered into the folder, nothing outside left behind."""

import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import make_portable as mp
from core.ai import ollama_local as ol


def _fake_model(store: Path, name: str):
    data = b"weights"
    d = "sha256:" + hashlib.sha256(data).hexdigest()
    (store / "blobs").mkdir(parents=True, exist_ok=True)
    (store / "blobs" / d.replace(":", "-")).write_bytes(data)
    m = store / ol._manifest_rel(name)
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps({"config": {"digest": d}, "layers": []}))


class TestPortable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.root = t / "prometheus"
        self.root.mkdir()
        self.home_store = t / "home" / ".ollama" / "models"
        for name in (ol.SPEAKER_MODEL, ol.DEFAULT_MODEL):
            _fake_model(self.home_store, name)
        # An installed Ollama (Linux layout: bin/ollama + lib/ollama/…)
        inst = t / "usr"
        (inst / "bin").mkdir(parents=True)
        exe = inst / "bin" / "ollama"
        exe.write_text("#!/bin/sh\necho 'ollama version is 9.9'\n")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        (inst / "lib" / "ollama").mkdir(parents=True)
        (inst / "lib" / "ollama" / "libggml.so").write_bytes(b"x" * 10)
        self.inst = inst
        self.patches = [
            mock.patch.object(mp, "ROOT", self.root),
            mock.patch.object(mp, "OLLAMA_DIR", self.root / "ollama"),
            mock.patch.object(mp, "PIPER_DIR", self.root / "piper"),
            mock.patch.object(ol, "PROJECT_DIR", self.root),
            mock.patch.object(ol, "MODELS_DIR", self.root / "models"),
            mock.patch.object(ol, "default_store", lambda: self.home_store),
            mock.patch.dict(os.environ, {"PATH": str(inst / "bin") + os.pathsep + os.environ["PATH"]}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_models_move_in(self):
        self.assertFalse(mp.step_models(check=True))
        self.assertTrue(mp.step_models(check=False))
        for name in (ol.SPEAKER_MODEL, ol.DEFAULT_MODEL):
            self.assertIsNotNone(ol._find_manifest(self.root / "models", name))
            self.assertIsNone(ol._find_manifest(self.home_store, name))     # moved, not copied
        self.assertTrue(mp.step_models(check=True))

    @unittest.skipIf(os.name == "nt", "Linux install layout")
    def test_ollama_copied_with_its_libraries_and_used_first(self):
        self.assertFalse(mp.step_ollama(check=True))
        self.assertTrue(mp.step_ollama(check=False))
        self.assertTrue((self.root / "ollama" / "bin" / "ollama").is_file())
        self.assertTrue((self.root / "ollama" / "lib" / "ollama" / "libggml.so").is_file())
        self.assertEqual(ol.find_ollama(), str(self.root / "ollama" / "bin" / "ollama"))
        self.assertTrue(mp.step_ollama(check=True))

    def _gpu_libs(self):
        lib = self.root / "ollama" / "lib" / "ollama"
        for name in ("cuda_v12", "cuda_v13", "rocm", "vulkan"):
            (lib / name).mkdir(parents=True)
            (lib / name / "x.dll").write_bytes(b"x" * 100)
        (lib / "ggml-cpu.dll").write_bytes(b"c")
        return lib

    def test_every_graphics_card_kept_by_default(self):
        lib = self._gpu_libs()
        self.assertEqual(mp.trim_ollama("all"), 0)
        self.assertEqual(sorted(p.name for p in lib.iterdir()),
                         ["cuda_v12", "cuda_v13", "ggml-cpu.dll", "rocm", "vulkan"])

    def test_trim_to_one_maker_keeps_vulkan_and_cpu(self):
        lib = self._gpu_libs()
        self.assertEqual(mp.trim_ollama("nvidia"), 100)
        self.assertEqual(sorted(p.name for p in lib.iterdir()),
                         ["cuda_v12", "cuda_v13", "ggml-cpu.dll", "vulkan"])
        mp.trim_ollama("intel")                                       # neither NVIDIA nor AMD
        self.assertEqual(sorted(p.name for p in lib.iterdir()), ["ggml-cpu.dll", "vulkan"])

    def test_half_set_up_python_is_finished_not_skipped(self):
        rt = self.root / "runtime" / "python"
        rt.mkdir(parents=True)
        (rt / "python.exe").write_bytes(b"")
        with mock.patch.object(mp, "RUNTIME", rt), mock.patch.object(mp.os, "name", "nt"), \
                mock.patch.object(mp, "_install_packages", return_value=True) as install:
            self.assertFalse(mp.step_python(check=True))                 # reported, not "ok"
            self.assertTrue(mp.step_python(check=False))
            install.assert_called_once()
            (rt / "Lib" / "site-packages" / "PySide6").mkdir(parents=True)
            install.reset_mock()
            self.assertTrue(mp.step_python(check=False))
            install.assert_not_called()

    def test_piper_and_whisper_come_in(self):
        from core.voice import voice_manager
        from core.app import paths
        setup = self.root.parent / "prometheus_setup" / "piper_windows" / "piper"
        (setup / "espeak-ng-data").mkdir(parents=True)
        exe = setup / ("piper.exe" if os.name == "nt" else "piper")
        exe.write_text("x")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        snap = self.root / "memory" / "model_cache" / "models--Systran--faster-whisper-tiny" / "snapshots" / "abc"
        snap.mkdir(parents=True)
        (snap / "model.bin").write_bytes(b"w")
        with mock.patch.object(paths, "PROJECT_DIR", self.root), \
                mock.patch.dict(os.environ, {"PATH": "/nonexistent"}), \
                mock.patch("core.app.config.CONFIG_PATH", str(self.root / "memory" / "config.json")):
            self.assertFalse(mp.step_voice(check=True))
            self.assertTrue(mp.step_voice(check=False))
            self.assertTrue((self.root / "piper" / exe.name).is_file())
            self.assertTrue((self.root / "piper" / "espeak-ng-data").is_dir())    # kept beside it
            self.assertTrue((self.root / "models" / "whisper" / "tiny" / "model.bin").is_file())

    def test_portable_python_reads_installed_packages(self):
        d = self.root / "py"
        d.mkdir()
        (d / "python313._pth").write_text("python313.zip\n.\n\n# Uncomment to run site.main() automatically\n#import site\n")
        mp.enable_site_packages(d)
        lines = (d / "python313._pth").read_text().splitlines()
        self.assertIn("import site", lines)
        self.assertNotIn("#import site", lines)
        self.assertEqual(lines[0], r"Lib\site-packages")
        mp.enable_site_packages(d)                                   # running twice changes nothing
        self.assertEqual((d / "python313._pth").read_text().splitlines(), lines)

    def test_launchers(self):
        mp.step_launchers(check=False)
        bat = (self.root / "Prometheus.bat").read_bytes()
        self.assertIn(b"\r\n", bat)
        self.assertIn(b"runtime\\python\\pythonw.exe", bat)
        self.assertTrue(os.access(self.root / "prometheus.sh", os.X_OK))


if __name__ == "__main__":
    unittest.main()
