"""
System fingerprinting for portable benchmark results.

Captures hardware context (CPU, RAM, GPU, OS) and writes to data/system_profile.json.
Generates a machine_id hash so results are traceable to their hardware.
"""

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import psutil

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SYSTEM_PROFILE_PATH = DATA_DIR / "system_profile.json"


def _get_cpu_info() -> tuple[str, int]:
    """Return (cpu_model, core_count)."""
    try:
        model = platform.processor() or "unknown"
        if not model or model == "unknown":
            # Fallback on some systems
            if hasattr(psutil, "cpu_freq") and psutil.cpu_freq():
                model = f"CPU ({psutil.cpu_freq().max or 0:.0f} MHz)"
        cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 0
        return (model.strip(), cores)
    except Exception:
        return ("unknown", 0)


def _get_ram_gb() -> float:
    """Total RAM in GB."""
    try:
        return round(psutil.virtual_memory().total / (1024**3), 2)
    except Exception:
        return 0.0


def _get_gpu_info() -> dict:
    """Detect GPU presence and VRAM. Tries nvidia-smi, system_profiler (macOS)."""
    out = {"present": False, "model": "", "vram_gb": None}
    # Try nvidia-smi
    if not out["present"]:
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                parts = r.stdout.strip().split("\n")[0].split(", ")
                if len(parts) >= 1:
                    out["present"] = True
                    out["model"] = parts[0].strip()
                if len(parts) >= 2:
                    try:
                        out["vram_gb"] = round(float(parts[1].strip()) / 1024, 2)
                    except (ValueError, TypeError):
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

    # Try system_profiler on macOS
    if not out["present"] and platform.system() == "Darwin":
        try:
            r = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0 and "Chipset Model" in r.stdout:
                out["present"] = True
                for line in r.stdout.splitlines():
                    if "Chipset Model:" in line:
                        out["model"] = line.split(":", 1)[-1].strip()
                        break
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

    return out


def capture_and_save(
    baseline_tps: dict[str, float] | None = None,
) -> dict:
    """
    Capture hardware context, optionally merge baseline_tps from calibration,
    write to data/system_profile.json, and return the full profile including machine_id.
    """
    cpu_model, core_count = _get_cpu_info()
    ram_gb = _get_ram_gb()
    gpu = _get_gpu_info()
    os_name = platform.system()
    os_release = platform.release()
    python_version = sys.version.split()[0]

    fingerprint = f"{cpu_model}|{ram_gb}|{os_name}|{os_release}"
    machine_id = hashlib.sha256(fingerprint.encode()).hexdigest()[:12]

    profile = {
        "machine_id": machine_id,
        "cpu_model": cpu_model,
        "cpu_cores": core_count,
        "ram_gb": ram_gb,
        "gpu_present": gpu["present"],
        "gpu_model": gpu["model"],
        "gpu_vram_gb": gpu["vram_gb"],
        "os": os_name,
        "os_release": os_release,
        "python_version": python_version,
    }
    if baseline_tps:
        profile["baseline_tps"] = baseline_tps

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SYSTEM_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    return profile


def load_profile() -> dict | None:
    """Load system_profile.json if it exists."""
    if not SYSTEM_PROFILE_PATH.exists():
        return None
    try:
        with open(SYSTEM_PROFILE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def format_banner(profile: dict | None) -> str:
    """Format profile for dashboard banner: 'Apple M2 Pro · 16GB RAM · macOS 14.4'."""
    if not profile:
        return "Benchmarked on: unknown system"
    parts = []
    cpu = profile.get("cpu_model") or "unknown CPU"
    ram = profile.get("ram_gb")
    if ram is not None:
        parts.append(f"{ram}GB RAM")
    os_name = profile.get("os", "")
    os_rel = profile.get("os_release", "")
    if os_name:
        os_str = f"{os_name}" + (f" {os_rel}" if os_rel else "")
        parts.append(os_str)
    return "Benchmarked on: " + (cpu + (" · " if parts else "") + " · ".join(parts)).strip()
