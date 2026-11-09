"""The prometheus folder: Prometheus.exe + app/ — and the one-time move into it."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent


class TestMoveIntoApp(unittest.TestCase):
    def test_old_layout_is_folded_into_app(self):
        with tempfile.TemporaryDirectory() as t:
            top = Path(t) / "prometheus"
            app = top / "app"
            (app / "tools").mkdir(parents=True)
            shutil.copy2(APP / "tools" / "move_into_app.py", app / "tools")
            (app / "main.py").write_text("new")                       # from the zip
            (app / "knowledge_base" / "build").mkdir(parents=True)
            (app / "knowledge_base" / "build" / "guide.md").write_text("new guide")
            # The old copy at the top
            (top / "main.py").write_text("old")
            (top / "Prometheus.bat").write_text("old launcher")
            (top / "models" / "blobs").mkdir(parents=True)
            (top / "models" / "blobs" / "sha256-x").write_text("2 GB of model")
            (top / "knowledge_base" / "build").mkdir(parents=True)
            (top / "knowledge_base" / "build" / "guide.md").write_text("old guide")
            (top / "knowledge_base" / "build" / "book.pdf").write_text("your book")
            (top / ".venv").mkdir()
            (top / "prometheus_setup").mkdir()
            (top / "Prometheus.exe").write_bytes(b"MZ")

            check = subprocess.run([sys.executable, str(app / "tools" / "move_into_app.py"), "--check"],
                                   capture_output=True, text=True)
            self.assertIn("Would move", check.stdout)
            self.assertTrue((top / "main.py").exists())                # --check changes nothing

            subprocess.run([sys.executable, str(app / "tools" / "move_into_app.py")], check=True,
                           capture_output=True)
            self.assertEqual(sorted(p.name for p in top.iterdir()),
                             [".venv", "Prometheus.exe", "app", "prometheus_setup"])
            self.assertEqual((app / "main.py").read_text(), "new")
            self.assertEqual((app / "knowledge_base" / "build" / "guide.md").read_text(), "new guide")
            self.assertEqual((app / "knowledge_base" / "build" / "book.pdf").read_text(), "your book")
            self.assertEqual((app / "models" / "blobs" / "sha256-x").read_text(), "2 GB of model")
            again = subprocess.run([sys.executable, str(app / "tools" / "move_into_app.py")],
                                   capture_output=True, text=True)
            self.assertIn("Already tidy", again.stdout)

    def test_folder_in_use_is_moved_file_by_file(self):
        # Owner's PC: WinError 5 moving voices/ (something had a file in it open)
        import importlib.util
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            top = Path(t) / "prometheus"
            app = top / "app"
            (app / "tools").mkdir(parents=True)
            shutil.copy2(APP / "tools" / "move_into_app.py", app / "tools")
            (app / "main.py").write_text("new")
            (top / "voices" / "Data").mkdir(parents=True)
            (top / "voices" / "Data" / "data.onnx").write_text("voice")
            (top / "voices" / "Data" / "open.json").write_text("in use")
            spec = importlib.util.spec_from_file_location("mia", app / "tools" / "move_into_app.py")
            mia = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mia)
            real = os.replace

            def replace(src, dst):
                # like Windows: a folder holding an open file can't move either
                if Path(src).name == "open.json" or (Path(src).is_dir() and
                                                     any(Path(src).rglob("open.json"))):
                    raise PermissionError(5, "Access is denied")
                return real(src, dst)
            with mock.patch.object(mia.os, "replace", replace), mock.patch.object(sys, "argv", ["x"]):
                self.assertEqual(mia.main(), 1)                         # something stayed
            self.assertEqual((app / "voices" / "Data" / "data.onnx").read_text(), "voice")
            self.assertTrue((top / "voices" / "Data" / "open.json").exists())
            with mock.patch.object(sys, "argv", ["x"]):                 # closed it, ran again
                self.assertEqual(mia.main(), 0)
            self.assertEqual((app / "voices" / "Data" / "open.json").read_text(), "in use")
            self.assertFalse((top / "voices").exists())

    def test_exe_is_committed_with_the_icon(self):
        exe = APP.parent / "Prometheus.exe"
        self.assertTrue(exe.exists())
        data = exe.read_bytes()
        self.assertEqual(data[:2], b"MZ")
        self.assertIn("Prometheus".encode("utf-16-le"), data)        # file details


if __name__ == "__main__":
    unittest.main()
