"""
Ensure deno is available for yt-dlp YouTube JS challenge solving.
Deno is not available via apt on Streamlit Cloud, so we download
the binary directly from GitHub releases at startup.
"""

import os
import platform
import subprocess
import stat
import zipfile
import io
import requests

DENO_DIR = os.path.expanduser("~/.deno/bin")
DENO_PATH = os.path.join(DENO_DIR, "deno")


def is_deno_installed() -> bool:
    """Check if deno is available on PATH or in our custom location."""
    # Check custom location first
    if os.path.isfile(DENO_PATH) and os.access(DENO_PATH, os.X_OK):
        return True
    # Check system PATH
    try:
        subprocess.run(["deno", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_deno() -> bool:
    """Download and install deno binary from GitHub releases."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux" and machine in ("x86_64", "amd64"):
        target = "x86_64-unknown-linux-gnu"
    elif system == "linux" and machine in ("aarch64", "arm64"):
        target = "aarch64-unknown-linux-gnu"
    elif system == "darwin" and machine in ("x86_64", "amd64"):
        target = "x86_64-apple-darwin"
    elif system == "darwin" and machine in ("aarch64", "arm64"):
        target = "aarch64-apple-darwin"
    else:
        print(f"[deno] Unsupported platform: {system} {machine}")
        return False

    url = f"https://github.com/denoland/deno/releases/latest/download/deno-{target}.zip"
    print(f"[deno] Downloading from {url} ...")

    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"[deno] Download failed: {e}")
        return False

    os.makedirs(DENO_DIR, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extract("deno", DENO_DIR)
        os.chmod(DENO_PATH, os.stat(DENO_PATH).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    except Exception as e:
        print(f"[deno] Extraction failed: {e}")
        return False

    # Verify
    try:
        result = subprocess.run([DENO_PATH, "--version"], capture_output=True, text=True, timeout=5)
        print(f"[deno] Installed: {result.stdout.splitlines()[0] if result.stdout else 'ok'}")
        return True
    except Exception as e:
        print(f"[deno] Verification failed: {e}")
        return False


def ensure_deno():
    """Make sure deno is installed and on PATH."""
    if is_deno_installed():
        # Make sure our custom location is on PATH anyway
        if DENO_DIR not in os.environ.get("PATH", ""):
            os.environ["PATH"] = DENO_DIR + os.pathsep + os.environ.get("PATH", "")
        return True

    print("[deno] Not found, installing...")
    success = install_deno()
    if success:
        os.environ["PATH"] = DENO_DIR + os.pathsep + os.environ.get("PATH", "")
    return success
