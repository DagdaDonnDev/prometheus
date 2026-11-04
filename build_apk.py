"""
build_apk.py
============
Builds Prometheus into an Android APK using Buildozer + Kivy.

The core logic (core/*.py) is shared between desktop and Android.
Only the UI layer differs — Android uses Kivy instead of PySide6.

Usage:
    python build_apk.py --setup      # install dependencies, init buildozer
    python build_apk.py --debug      # build debug APK (faster, for testing)
    python build_apk.py --release    # build release APK (for distribution)
    python build_apk.py --install    # build and install to connected device

Requirements:
    - Linux or macOS (Buildozer does not support Windows directly)
    - Windows users: use WSL2 (Ubuntu) or a Linux VM
    - Java JDK 17
    - Android SDK/NDK (installed automatically by Buildozer)

Output:
    bin/Prometheus-1.0.0-debug.apk
    bin/Prometheus-1.0.0-release.apk

Android-specific notes:
    - Ollama cannot run on Android (ARM, different architecture)
    - Android version uses a remote Ollama server OR a bundled llama.cpp
    - llama.cpp Android build is included via python-for-android recipe
    - Recommended: run Ollama on a laptop/Pi on same WiFi, Android connects to it
    - Or: use llama-cpp-python which supports Android ARM via python-for-android

LLM strategy on Android:
    1. Local network Ollama (preferred) - user sets IP in settings
    2. llama-cpp-python (bundled) - runs Llama 3.2 3B directly on device
    3. No LLM (offline knowledge search only) - always works
"""

import os
import sys
import subprocess
import shutil
import platform
from pathlib import Path


APP_NAME      = "Prometheus"
APP_VERSION   = "1.0.0"
PACKAGE_NAME  = "org.prometheus.survival"
ANDROID_DIR   = Path("android")


# ── Buildozer spec ─────────────────────────────────────────────────────────

BUILDOZER_SPEC = """[app]
title = Prometheus
package.name = prometheus
package.domain = org.survival
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,md,txt,json,qss,onnx
source.include_patterns = assets/*,core/*,knowledge_base/*,voices/*,memory/*

version = 1.0.0

requirements = python3,\
    kivy==2.3.0,\
    kivymd,\
    requests,\
    numpy,\
    pillow,\
    certifi,\
    charset-normalizer,\
    idna,\
    urllib3

# For on-device LLM (optional - large download):
# requirements = ...,llama-cpp-python

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,\
    RECORD_AUDIO,\
    WRITE_EXTERNAL_STORAGE,\
    READ_EXTERNAL_STORAGE,\
    WAKE_LOCK,\
    FOREGROUND_SERVICE

android.api = 33
android.minapi = 26
android.ndk = 25b
android.sdk = 33
android.accept_sdk_license = True

android.archs = arm64-v8a, armeabi-v7a

android.allow_backup = True
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1
"""


# ── Android main.py (Kivy entry point) ────────────────────────────────────

ANDROID_MAIN = '''"""
Android entry point for Prometheus.
Uses Kivy UI instead of PySide6.
All core logic (core/*.py) is shared with desktop version.
"""

import os
import sys
from pathlib import Path

# Android storage paths
from kivy.utils import platform as kivy_platform

if kivy_platform == "android":
    from android.storage import app_storage_path, primary_external_storage_path
    from android.permissions import request_permissions, Permission
    request_permissions([
        Permission.RECORD_AUDIO,
        Permission.WRITE_EXTERNAL_STORAGE,
        Permission.READ_EXTERNAL_STORAGE,
    ])
    APP_DIR = Path(app_storage_path())
else:
    APP_DIR = Path(".")

# Redirect memory and knowledge paths for Android
os.environ["PROMETHEUS_DATA_DIR"] = str(APP_DIR)
sys.path.insert(0, str(Path(__file__).parent))

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDIconButton, MDFlatButton, MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.navigationdrawer import MDNavigationDrawer, MDNavigationLayout
from kivymd.uix.list import MDList, OneLineListItem, TwoLineListItem
from kivymd.uix.dialog import MDDialog
from kivymd.uix.snackbar import Snackbar
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty, ListProperty

# Core systems (shared with desktop)
from core.config import Config
from core.memory import Memory
from core.tabs import TabManager
from core.rag import KnowledgeBase
from core.llm import LLMEngine
from core.confidence import ConfidenceScorer
from core.context_manager import ContextManager

import threading


# ── Tab definitions for Android UI ────────────────────────────────────────

TAB_ICONS = {
    "survival":   "fire",
    "medical":    "medical-bag",
    "electronics": "flash",
    "navigation": "map-marker",
    "farming":    "sprout",
    "build":      "wrench",
    "chemistry":  "flask",
    "prometheus": "chat",
}


# ── Message bubble widgets ─────────────────────────────────────────────────

class UserMessage(MDCard):
    text = StringProperty("")

    def __init__(self, text, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.orientation = "vertical"
        self.padding = dp(12)
        self.spacing = dp(4)
        self.size_hint_y = None
        self.radius = [dp(16), dp(16), dp(4), dp(16)]
        self.md_bg_color = (0.16, 0.24, 0.16, 1)
        self.size_hint_x = 0.8
        self.pos_hint = {"right": 0.98}

        label = MDLabel(
            text=text,
            theme_text_color="Custom",
            text_color=(0.83, 0.93, 0.83, 1),
            adaptive_height=True,
            font_size=dp(14),
        )
        self.add_widget(label)
        self.bind(minimum_height=self.setter("height"))


class AssistantMessage(MDCard):
    text = StringProperty("")

    def __init__(self, text="", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.orientation = "vertical"
        self.padding = dp(12)
        self.spacing = dp(4)
        self.size_hint_y = None
        self.radius = [dp(16), dp(16), dp(16), dp(4)]
        self.md_bg_color = (0.12, 0.12, 0.12, 1)
        self.size_hint_x = 0.85
        self.pos_hint = {"x": 0.02}

        self._label = MDLabel(
            text=text or "...",
            theme_text_color="Custom",
            text_color=(0.91, 0.91, 0.91, 1),
            adaptive_height=True,
            font_size=dp(14),
        )
        self.add_widget(self._label)
        self.bind(minimum_height=self.setter("height"))

    def append_text(self, token):
        current = self._label.text
        if current == "...":
            self._label.text = token
        else:
            self._label.text = current + token


# ── Chat screen ────────────────────────────────────────────────────────────

class ChatScreen(MDScreen):
    def __init__(self, tab_id, tab_manager, llm, knowledge,
                 memory, context_mgr, config, **kwargs):
        super().__init__(**kwargs)
        self.tab_id = tab_id
        self.tab_manager = tab_manager
        self.llm = llm
        self.knowledge = knowledge
        self.memory = memory
        self.context_mgr = context_mgr
        self.config = config
        self._generating = False
        self._current_bubble = None
        self._build_ui()
        self._load_history()

    def _build_ui(self):
        layout = MDBoxLayout(orientation="vertical")

        # Messages scroll area
        scroll = MDScrollView()
        self._messages = MDBoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=[dp(8), dp(8), dp(8), dp(8)],
            size_hint_y=None,
            adaptive_height=True,
        )
        self._messages.bind(minimum_height=self._messages.setter("height"))
        scroll.add_widget(self._messages)
        layout.add_widget(scroll)
        self._scroll = scroll

        # Input area
        input_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(60),
            padding=[dp(8), dp(8), dp(8), dp(8)],
            spacing=dp(8),
            md_bg_color=(0.08, 0.08, 0.08, 1),
        )

        self._input = MDTextField(
            hint_text="Ask anything...",
            mode="rectangle",
            size_hint_x=0.85,
            multiline=False,
        )
        self._input.bind(on_text_validate=self._on_submit)

        send_btn = MDIconButton(
            icon="send",
            theme_icon_color="Custom",
            icon_color=(0.94, 0.65, 0, 1),
            on_release=self._on_send_press,
        )

        input_row.add_widget(self._input)
        input_row.add_widget(send_btn)
        layout.add_widget(input_row)

        self.add_widget(layout)

    def _load_history(self):
        tab = self.tab_manager.get_tab(self.tab_id)
        if not tab:
            return
        for msg in tab.history[-20:]:  # Last 20 messages
            if msg["role"] == "user":
                self._messages.add_widget(UserMessage(text=msg["content"]))
            else:
                self._messages.add_widget(AssistantMessage(text=msg["content"]))
        Clock.schedule_once(lambda dt: self._scroll_bottom(), 0.1)

    def _on_submit(self, instance):
        self._send(instance.text)

    def _on_send_press(self, instance):
        self._send(self._input.text)

    def _send(self, text):
        text = text.strip()
        if not text or self._generating:
            return

        self._input.text = ""
        tab = self.tab_manager.get_tab(self.tab_id)
        if not tab:
            return

        # Add user message
        tab.add_message("user", text)
        self._messages.add_widget(UserMessage(text=text))
        self.tab_manager.save()

        # Generate response in background thread
        self._generating = True
        self._current_bubble = AssistantMessage()
        self._messages.add_widget(self._current_bubble)
        Clock.schedule_once(lambda dt: self._scroll_bottom(), 0.1)

        thread = threading.Thread(
            target=self._generate,
            args=(tab, text),
            daemon=True
        )
        thread.start()

    def _generate(self, tab, user_input):
        try:
            knowledge_context, confidence_note = self.knowledge.search(
                user_input,
                domains=tab.domains,
                n_results=self.config.rag_results
            )
            user_context = self.memory.get_context_string()
            system_prompt = self.llm.build_system_prompt(
                tab.system_prompt,
                user_context,
                knowledge_context,
                confidence_note
            )
            messages = self.context_mgr.prepare_messages(tab)

            full_response = []

            def on_token(token):
                full_response.append(token)
                Clock.schedule_once(
                    lambda dt: self._current_bubble.append_text(token), 0
                )
                Clock.schedule_once(lambda dt: self._scroll_bottom(), 0)

            def on_done(full):
                tab.add_message("assistant", full)
                self.tab_manager.save()
                self._generating = False
                self._current_bubble = None

            def on_error(err):
                Clock.schedule_once(
                    lambda dt: self._show_error(err), 0
                )
                self._generating = False

            self.llm.stream(messages, system_prompt, on_token, on_done, on_error)

        except Exception as e:
            Clock.schedule_once(lambda dt: self._show_error(str(e)), 0)
            self._generating = False

    def _show_error(self, msg):
        Snackbar(text=f"Error: {msg}", duration=4).open()

    def _scroll_bottom(self):
        self._scroll.scroll_y = 0


# ── Main Prometheus Android App ────────────────────────────────────────────

class PrometheusApp(MDApp):

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Amber"
        self.theme_cls.primary_hue = "700"
        self.title = "Prometheus"

        # Initialize core systems
        self.config = Config()
        self.memory = Memory()
        self.tab_manager = TabManager()
        self.knowledge = KnowledgeBase()
        self.llm = LLMEngine(self.config)
        self.context_mgr = ContextManager(self.llm)

        # Check if Ollama is on local network
        self._check_llm_available()

        # Initialize knowledge base in background
        threading.Thread(
            target=self.knowledge.initialize_vector_db,
            daemon=True
        ).start()

        return self._build_main_layout()

    def _build_main_layout(self):
        layout = MDBoxLayout(orientation="vertical")

        # Top bar
        toolbar = MDTopAppBar(
            title="⚡ Prometheus",
            right_action_items=[
                ["cog", lambda x: self._show_settings()],
                ["information", lambda x: self._show_situation()],
            ],
            md_bg_color=(0.07, 0.07, 0.07, 1),
        )
        layout.add_widget(toolbar)

        # Tab bar
        self._tabs = MDTabs(
            tab_indicator_anim=True,
            tab_hint_x=False,
        )
        self._chat_screens = {}

        for tab in self.tab_manager.tabs:
            icon = TAB_ICONS.get(tab.id, "star")
            tab_item = self._make_tab(tab.id, tab.name, icon)
            self._tabs.add_widget(tab_item)

        self._tabs.bind(on_tab_switch=self._on_tab_switch)
        layout.add_widget(self._tabs)

        return layout

    def _make_tab(self, tab_id, name, icon):
        from kivymd.uix.tab import MDTabsBase
        from kivymd.uix.floatlayout import MDFloatLayout

        class Tab(MDFloatLayout, MDTabsBase):
            pass

        tab = Tab(title=name, icon=icon)

        # Create chat screen for this tab
        screen = ChatScreen(
            tab_id=tab_id,
            tab_manager=self.tab_manager,
            llm=self.llm,
            knowledge=self.knowledge,
            memory=self.memory,
            context_mgr=self.context_mgr,
            config=self.config,
        )
        self._chat_screens[tab_id] = screen
        tab.add_widget(screen)

        return tab

    def _on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        self.tab_manager.active_tab_id = instance_tab.tab_id
        self.tab_manager.save()

    def _check_llm_available(self):
        if not self.llm.is_available():
            Clock.schedule_once(self._show_llm_setup_dialog, 1)

    def _show_llm_setup_dialog(self, dt):
        dialog = MDDialog(
            title="LLM Setup Required",
            text=(
                "Prometheus needs Ollama to generate responses.\\n\\n"
                "Options:\\n"
                "1. Run Ollama on your laptop/PC on the same WiFi\\n"
                "   Set the IP in Settings → Model → Ollama URL\\n"
                "   Example: http://192.168.1.100:11434\\n\\n"
                "2. Knowledge search still works without LLM."
            ),
            buttons=[
                MDFlatButton(
                    text="OK",
                    on_release=lambda x: dialog.dismiss()
                ),
                MDRaisedButton(
                    text="Settings",
                    on_release=lambda x: (dialog.dismiss(), self._show_settings())
                ),
            ]
        )
        dialog.open()

    def _show_settings(self):
        from kivymd.uix.textfield import MDTextField

        url_field = MDTextField(
            text=self.config.ollama_url,
            hint_text="Ollama URL (e.g. http://192.168.1.100:11434)",
            mode="rectangle",
        )

        def save(instance):
            self.config.ollama_url = url_field.text.strip()
            self.llm.base_url = self.config.ollama_url
            self.config.save()
            dialog.dismiss()
            Snackbar(text="Settings saved").open()

        dialog = MDDialog(
            title="Settings",
            type="custom",
            content_cls=url_field,
            buttons=[
                MDFlatButton(text="Cancel", on_release=lambda x: dialog.dismiss()),
                MDRaisedButton(text="Save", on_release=save),
            ]
        )
        dialog.open()

    def _show_situation(self):
        u = self.memory.data["user"]
        inv = self.memory.data["inventory"]

        info = (
            f"Name: {u.get('name') or 'Unknown'}\\n"
            f"Day: {u.get('day_count', 1)}\\n"
            f"Location: {u.get('location_estimate') or 'Unknown'}\\n"
            f"Food: {inv.get('food_days') or '?'} days\\n"
            f"Water: {inv.get('water_days') or '?'} days\\n"
            f"Shelter: {inv.get('shelter_status') or 'Unknown'}"
        )

        dialog = MDDialog(
            title="Your Situation",
            text=info,
            buttons=[
                MDFlatButton(text="Close", on_release=lambda x: dialog.dismiss()),
            ]
        )
        dialog.open()


if __name__ == "__main__":
    PrometheusApp().run()
'''

# ── Build functions ────────────────────────────────────────────────────────

def check_platform():
    """Buildozer requires Linux or macOS."""
    if platform.system() == "Windows":
        print("""
⚠️  Buildozer does not run natively on Windows.

Options:
  1. Use WSL2 (Windows Subsystem for Linux):
     wsl --install
     Then run this script inside WSL2

  2. Use a Linux virtual machine (VirtualBox, VMware)

  3. Use GitHub Actions (build in the cloud — free):
     See: https://github.com/marketplace/actions/build-apk-via-buildozer

The build_apk.py script will generate all necessary files.
Copy them to a Linux environment and run: buildozer android debug
""")
        return False
    return True


def install_dependencies():
    """Install Buildozer and Android build dependencies."""
    print("Installing Buildozer...")

    # Install buildozer
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "buildozer", "kivy", "kivymd", "--upgrade"
    ], check=True)

    # Linux-specific dependencies
    if platform.system() == "Linux":
        print("\nInstalling Linux build dependencies...")
        packages = [
            "git", "zip", "unzip", "openjdk-17-jdk",
            "autoconf", "libtool", "pkg-config",
            "zlib1g-dev", "libncurses5-dev", "libncursesw5-dev",
            "cmake", "libffi-dev", "libssl-dev",
            "python3-pip", "python3-setuptools",
        ]
        subprocess.run(
            ["sudo", "apt-get", "install", "-y"] + packages,
            capture_output=False
        )

    print("✓ Dependencies installed")


def setup_android_project():
    """Create Android project structure."""
    ANDROID_DIR.mkdir(exist_ok=True)

    # Write buildozer.spec
    spec_path = Path("buildozer.spec")
    spec_path.write_text(BUILDOZER_SPEC)
    print(f"✓ Created buildozer.spec")

    # Write Android main.py
    android_main = Path("main_android.py")
    android_main.write_text(ANDROID_MAIN)
    print(f"✓ Created main_android.py")

    # Create Android-specific config adapter
    adapter = Path("android_config.py")
    adapter.write_text('''"""
Android path adapter.
Redirects file paths to Android storage locations.
Imported automatically on Android by main_android.py.
"""
import os
from pathlib import Path

# On Android, use app-private storage
if os.environ.get("PROMETHEUS_DATA_DIR"):
    DATA_DIR = Path(os.environ["PROMETHEUS_DATA_DIR"])
else:
    DATA_DIR = Path(".")

# Override default paths
MEMORY_PATH_OVERRIDE    = str(DATA_DIR / "memory")
KNOWLEDGE_PATH_OVERRIDE = str(DATA_DIR / "knowledge_base")
VOICES_PATH_OVERRIDE    = str(DATA_DIR / "voices")
''')
    print(f"✓ Created android_config.py")

    # Create presplash and icon placeholders
    assets = Path("assets")
    assets.mkdir(exist_ok=True)
    (assets / "presplash.png").touch()   # Replace with actual splash screen
    (assets / "icon.png").touch()        # Replace with actual icon

    print(f"\n✓ Android project structure ready")
    print(f"\nNext: run 'python build_apk.py --debug' to build")


def build_apk(release: bool = False):
    """Run Buildozer to build the APK."""
    if not Path("buildozer.spec").exists():
        print("buildozer.spec not found. Run: python build_apk.py --setup")
        sys.exit(1)

    # Swap main.py temporarily for Android version
    main_backup = Path("main_desktop.py")
    main_py = Path("main.py")

    if Path("main_android.py").exists():
        print("Swapping to Android main...")
        if main_py.exists():
            shutil.copy2(main_py, main_backup)
        shutil.copy2("main_android.py", main_py)

    try:
        mode = "release" if release else "debug"
        print(f"\nBuilding {mode} APK with Buildozer...")
        print("First build downloads Android SDK/NDK — takes 20-40 minutes.")
        print("Subsequent builds: 3-5 minutes.\n")

        result = subprocess.run(
            ["buildozer", "-v", "android", mode],
            capture_output=False
        )

        if result.returncode == 0:
            # Find the APK
            apks = list(Path("bin").glob("*.apk")) if Path("bin").exists() else []
            if apks:
                apk = apks[-1]
                size = apk.stat().st_size / 1024 / 1024
                print(f"""
{'='*50}
✅ APK BUILD SUCCESSFUL
{'='*50}

APK: {apk}
Size: {size:.0f} MB

Install on device:
  adb install {apk}

Or copy to device and install manually.

Note: Enable 'Install from unknown sources' on device.
""")
        else:
            print("\n✗ Build failed. Check output above.")

    finally:
        # Restore desktop main.py
        if main_backup.exists():
            shutil.copy2(main_backup, main_py)
            main_backup.unlink()
            print("Restored desktop main.py")


def install_to_device():
    """Install APK to connected Android device via ADB."""
    apks = list(Path("bin").glob("*.apk")) if Path("bin").exists() else []
    if not apks:
        print("No APK found. Build first with: python build_apk.py --debug")
        return

    apk = sorted(apks)[-1]
    print(f"Installing {apk} to connected device...")

    result = subprocess.run(["adb", "install", "-r", str(apk)])
    if result.returncode == 0:
        print("✓ Installed successfully")
        print("Launch Prometheus on your device")
    else:
        print("✗ Install failed. Is the device connected with USB debugging enabled?")


def generate_github_actions():
    """Generate GitHub Actions workflow for cloud APK building."""
    workflow_dir = Path(".github/workflows")
    workflow_dir.mkdir(parents=True, exist_ok=True)

    workflow = """name: Build Prometheus APK

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  build-apk:
    runs-on: ubuntu-22.04

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        sudo apt-get update
        sudo apt-get install -y git zip unzip openjdk-17-jdk \\
          autoconf libtool pkg-config zlib1g-dev \\
          libncurses5-dev libncursesw5-dev cmake \\
          libffi-dev libssl-dev python3-pip
        pip install buildozer kivy kivymd cython

    - name: Setup Android project
      run: python build_apk.py --setup

    - name: Build APK
      run: |
        cp main_android.py main.py
        buildozer android debug

    - name: Upload APK
      uses: actions/upload-artifact@v3
      with:
        name: Prometheus-APK
        path: bin/*.apk
        retention-days: 30
"""
    (workflow_dir / "build_apk.yml").write_text(workflow)
    print(f"✓ Created .github/workflows/build_apk.yml")
    print("  Push to GitHub → Actions tab → APK builds automatically")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build Prometheus Android APK"
    )
    parser.add_argument("--setup",   action="store_true", help="Install dependencies and init project")
    parser.add_argument("--debug",   action="store_true", help="Build debug APK")
    parser.add_argument("--release", action="store_true", help="Build release APK")
    parser.add_argument("--install", action="store_true", help="Install to connected device")
    parser.add_argument("--github",  action="store_true", help="Generate GitHub Actions workflow")
    args = parser.parse_args()

    print(f"""
{'='*50}
⚡ PROMETHEUS APK BUILDER
{'='*50}
""")

    if args.github:
        generate_github_actions()
        return

    if args.setup:
        if not check_platform():
            generate_github_actions()
            print("\nGenerated GitHub Actions workflow as alternative.")
            return
        install_dependencies()
        setup_android_project()
        return

    if args.debug or args.release:
        if not check_platform():
            sys.exit(1)
        build_apk(release=args.release)
        return

    if args.install:
        install_to_device()
        return

    # No args — show help
    parser.print_help()
    print(f"""
Quick start:
  1. python build_apk.py --setup      (first time only)
  2. python build_apk.py --debug      (build APK)
  3. python build_apk.py --install    (push to device)

On Windows, generate a cloud build workflow instead:
  python build_apk.py --github
  Then push to GitHub and build runs automatically.

Android LLM options:
  - Recommended: Run Ollama on laptop on same WiFi
    Set URL in app Settings → Ollama URL
    e.g. http://192.168.1.100:11434

  - Alternative: on-device llama.cpp (add to buildozer.spec requirements)
    Slower but fully self-contained
""")


if __name__ == "__main__":
    main()
