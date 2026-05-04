import uvicorn
import os
import sys
import multiprocessing
import io
from pathlib import Path

# ── Auto-load .env ──────────────────────────────────────────────────
try:
    from dotenv import load_dotenv

    _env_paths = [
        Path(__file__).resolve().parent / ".env",  # backend/.env
        Path(__file__).resolve().parent.parent / ".env",  # project root .env
    ]
    for _p in _env_paths:
        if _p.exists():
            load_dotenv(_p, override=False)
            print(f"[dotenv] Loaded {_p}")
            break
    else:
        print("[dotenv] No .env file found (using system env)")
except ImportError:
    print("[dotenv] python-dotenv not installed, skipping .env")

# Force UTF-8 encoding for stdout/stderr to prevent Windows UnicodeEncodeError
if sys.stdout:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr:
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Necessary for PyInstaller to handle multiprocessing
multiprocessing.freeze_support()

if getattr(sys, "frozen", False):
    print("Running frozen mode")
    # In PyInstaller --onefile, sys.executable is the binary.
    # But files are unpacked in sys._MEIPASS
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = sys._MEIPASS
    print("BASE_DIR", BASE_DIR)
    print("BUNDLE_DIR", BUNDLE_DIR)
    print("sys.path INITIAL", sys.path)

    # Determine base path for OneDir execution (safer than _MEIPASS for verifying location)
    # In OneDir mode, sys.executable is inside the folder.
    # binaries are in 'bin' relative to the executable dir.
    base_path = os.path.dirname(sys.executable)

    # FFmpeg
    # Check for .exe on Windows explicitly
    ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    # Use BUNDLE_DIR (sys._MEIPASS) which points to _internal
    ffmpeg_path = os.path.join(BUNDLE_DIR, "bin", ffmpeg_name)

    if os.path.exists(ffmpeg_path):
        os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path
        os.environ["FFMPEG_BINARY"] = ffmpeg_path
        print(f"[INFO] Bundled FFmpeg found: {ffmpeg_path}")
    else:
        # The user provided a malformed string in the instruction.
        # I will interpret it as replacing the emoji and the specific message,
        # while trying to keep the original f-string structure for ffmpeg_path.
        # Assuming {binary_name} should be ffmpeg_name and {path} should be ffmpeg_path.
        print(
            f"[ERROR] {ffmpeg_name} not found at: {ffmpeg_path} - App may likely fail if assuming strict bundling."
        )
        # For strict compliance, we do NOT fallback to system path if prohibited
        # But during debug we might want to know.

    # ImageMagick
    magick_name = "magick.exe" if os.name == "nt" else "magick"
    magick_path = os.path.join(BUNDLE_DIR, "bin", magick_name)

    if os.path.exists(magick_path):
        os.environ["IMAGEMAGICK_BINARY"] = magick_path
        print(f"[INFO] Bundled ImageMagick found: {magick_path}")
    else:
        print(f"[ERROR] Bundled ImageMagick NOT found at {magick_path}")
else:
    print("Running script mode")
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

# Add the directory containing 'src' package to sys.path
# BUNDLE_DIR should contain 'src' because of datas=[('Backend/src', 'src')]
sys.path.insert(0, BUNDLE_DIR)
# ALSO Add the 'src' directory itself to sys.path so 'import services' works
sys.path.insert(0, os.path.join(BUNDLE_DIR, "src"))

try:
    from src.app import app
except ImportError as e:
    import sys

    print(f"[ERROR] Failed to import src.app: {e}")
    print("sys.path=", sys.path)
    # List contents of BUNDLE_DIR to help debug
    try:
        print(f"Contents of {BUNDLE_DIR}:", os.listdir(BUNDLE_DIR))
        src_path = os.path.join(BUNDLE_DIR, "src")
        if os.path.exists(src_path):
            print(f"Contents of {src_path}:", os.listdir(src_path))
    except Exception as list_err:
        print(f"Could not list dir: {list_err}")
    raise


# Function to kill process on port 5001 if it exists
def kill_port(port):
    import psutil

    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                # Skip system processes to avoid permission errors or hanging
                if proc.pid < 100:
                    continue

                for conn in proc.connections(kind="inet"):
                    if conn.laddr.port == port:
                        print(
                            f"[BUSY] Port {port} is busy. Killing process {proc.pid} ({proc.name()})..."
                        )
                        proc.kill()
                        proc.wait(timeout=3)
                        print(f"[SUCCESS] Process {proc.pid} killed.")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        print(f"[ERROR] Error killing port {port}: {e}")


if __name__ == "__main__":
    # Ensure port is free
    kill_port(9478)

    import logging

    # Route uvicorn startup messages to stdout (not stderr)
    log_config = uvicorn.config.LOGGING_CONFIG.copy()
    for handler in log_config.get("handlers", {}).values():
        handler["stream"] = "ext://sys.stdout"

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=9478,
        workers=1,
        log_level="warning",  # Suppress per-request access logs
        log_config=log_config,
    )
