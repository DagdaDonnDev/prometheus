"""
What this computer can do — so Prometheus can pick full or low-power mode by
itself (Settings → Model → Performance: Automatic).

Step 1: memory, processor cores and type, graphics card (no extra packages:
        OS calls, nvidia-smi / PowerShell / lspci when they're there)
Step 2: after the models have loaded, ask Ollama whether they're actually on
        the graphics card (/api/ps → size_vram). That's the surest sign: a
        card Ollama can't use doesn't help.
Step 3: recommend() → ("full" | "low", the reason in plain words)

Low-power mode (see config.low_power_active) keeps answers lean so a
processor-only machine — an Orange Pi, an old laptop — still feels quick.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Hardware:
    ram_gb: float = 0.0
    cores: int = 0
    arch: str = ""
    gpu_name: str = ""          # "" = none found
    gpu_vram_gb: float = 0.0    # 0 = unknown

    def summary(self) -> str:
        bits = [f"{self.cores} cores" if self.cores else "",
                f"{self.ram_gb:.0f} GB memory" if self.ram_gb else "",
                ("ARM processor" if self.is_arm else "")]
        if self.gpu_name:
            bits.append(self.gpu_name + (f" ({self.gpu_vram_gb:.0f} GB)" if self.gpu_vram_gb else ""))
        else:
            bits.append("no graphics card found")
        return " · ".join(b for b in bits if b)

    @property
    def is_arm(self) -> bool:
        return self.arch.lower() in ("arm64", "aarch64", "armv7l", "armv8l")


# ── Step 1 ──────────────────────────────────────────────────────────────────

def _ram_gb() -> float:
    try:
        if os.name == "nt":
            import ctypes

            class _MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = _MEM()
            m.dwLength = ctypes.sizeof(_MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 2**30
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            return int(out.stdout.strip()) / 2**30
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 2**20
    except Exception:
        pass
    return 0.0


def _gpu() -> Tuple[str, float]:
    """(name, video memory GB) of the best graphics card found, or ("", 0)."""
    run = lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
    try:
        if shutil.which("nvidia-smi"):
            out = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
            first = out.strip().splitlines()[0] if out.strip() else ""
            if first:
                name, _, mib = first.rpartition(",")
                return name.strip(), float(mib) / 1024 if mib.strip().isdigit() else 0.0
        if os.name == "nt":
            out = run(["powershell", "-NoProfile", "-Command",
                       "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + '|' + $_.AdapterRAM }"])
            cards = []
            for line in out.splitlines():
                name, _, ram = line.partition("|")
                if name.strip() and not re.search(r"basic display|remote|virtual", name, re.I):
                    cards.append((name.strip(), int(ram) / 2**30 if ram.strip().isdigit() else 0.0))
            # a separate card beats the processor's built-in one
            cards.sort(key=lambda c: (bool(re.search(r"nvidia|radeon rx|arc a", c[0], re.I)), c[1]),
                       reverse=True)
            if cards:
                return cards[0]
        elif shutil.which("lspci"):
            for line in run(["lspci"]).splitlines():
                if re.search(r"vga|3d controller|display", line, re.I):
                    return line.split(":", 2)[-1].strip(), 0.0
    except Exception:
        pass
    return "", 0.0


def detect() -> Hardware:
    name, vram = _gpu()
    return Hardware(ram_gb=_ram_gb(), cores=os.cpu_count() or 0,
                    arch=platform.machine(), gpu_name=name, gpu_vram_gb=vram)


# ── Step 2 ──────────────────────────────────────────────────────────────────

def ollama_on_gpu(base_url: str) -> Optional[bool]:
    """True/False once a model is loaded; None if Ollama can't say."""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"{base_url.rstrip('/')}/api/ps", timeout=5) as r:
            models = json.loads(r.read()).get("models", [])
    except Exception:
        return None
    if not models:
        return None
    return any(int(m.get("size_vram", 0) or 0) > 0 for m in models)


# ── Step 3 ──────────────────────────────────────────────────────────────────

def recommend(hw: Hardware, on_gpu: Optional[bool]) -> Tuple[str, str]:
    """("full" | "low", why — one plain sentence)."""
    if hw.ram_gb and hw.ram_gb < 7:
        return "low", f"this computer has {hw.ram_gb:.0f} GB of memory"
    if on_gpu is False:
        return "low", "the AI is running on the processor (no graphics card Ollama can use)"
    if on_gpu is True:
        return "full", "the AI is running on the graphics card"
    # Ollama couldn't say — judge from the parts
    if not hw.gpu_name and (hw.is_arm or (hw.cores and hw.cores < 6)):
        return "low", "there's no graphics card and the processor is " + \
            ("an ARM chip" if hw.is_arm else f"{hw.cores}-core")
    return "full", "this computer looks fast enough"
