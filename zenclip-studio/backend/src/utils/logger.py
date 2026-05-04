"""
SnipieAI Backend Logger
=======================
Centralized, structured logging with color-coded levels.
All backend modules should use this instead of bare print().

Usage:
    from utils.logger import log
    log.info("Processing started", module="JobRunner")
    log.warn("Low memory", module="ResourceMonitor")
    log.error("FFmpeg failed", module="VideoEncoder", error=str(e))
    log.debug("Frame count: 120", module="Cutter")  # Only shown in DEBUG mode
    log.success("Job complete", module="JobRunner", job_id="abc123")
    log.step("Transcribing audio...", module="Transcriber")  # Progress step
"""

import os
import sys
import logging
from datetime import datetime

# ── Color codes (ANSI) ──────────────────────────────────────────────────────
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_BLUE   = "\033[34m"
_MAGENTA= "\033[35m"
_WHITE  = "\033[37m"

# Disable colors if not a TTY (e.g. log file redirect)
_USE_COLOR = sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"

def _c(color: str, text: str) -> str:
    return f"{color}{text}{_RESET}" if _USE_COLOR else text

# ── Log level from env ───────────────────────────────────────────────────────
_DEBUG_MODE = os.environ.get("SNIPIE_DEBUG", "0") == "1"

# ── Formatter ────────────────────────────────────────────────────────────────
_LEVEL_STYLES = {
    "INFO":    (_CYAN,    "INFO "),
    "STEP":    (_BLUE,    "STEP "),
    "SUCCESS": (_GREEN,   "OK   "),
    "WARN":    (_YELLOW,  "WARN "),
    "ERROR":   (_RED,     "ERROR"),
    "DEBUG":   (_DIM,     "DEBUG"),
}

def _format(level: str, message: str, module: str = "", **kwargs) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    color, label = _LEVEL_STYLES.get(level, (_WHITE, level[:5].ljust(5)))

    time_part   = _c(_DIM, f"[{now}]")
    level_part  = _c(color, f"[{label}]")
    module_part = _c(_MAGENTA, f"[{module}]") if module else ""
    msg_part    = message

    # Append extra kwargs as key=value pairs
    extras = ""
    if kwargs:
        kv = "  ".join(f"{k}={v}" for k, v in kwargs.items())
        extras = _c(_DIM, f"  {kv}")

    parts = [time_part, level_part]
    if module_part:
        parts.append(module_part)
    parts.append(msg_part)

    return " ".join(parts) + extras


class _Logger:
    """Simple structured logger. Thread-safe (print is GIL-protected)."""

    def info(self, message: str, module: str = "", **kwargs):
        print(_format("INFO", message, module, **kwargs), flush=True)

    def step(self, message: str, module: str = "", **kwargs):
        """Use for progress steps within a pipeline."""
        print(_format("STEP", f"→ {message}", module, **kwargs), flush=True)

    def success(self, message: str, module: str = "", **kwargs):
        print(_format("SUCCESS", message, module, **kwargs), flush=True)

    def warn(self, message: str, module: str = "", **kwargs):
        print(_format("WARN", message, module, **kwargs), flush=True)

    def error(self, message: str, module: str = "", **kwargs):
        print(_format("ERROR", message, module, **kwargs), file=sys.stderr, flush=True)

    def debug(self, message: str, module: str = "", **kwargs):
        if _DEBUG_MODE:
            print(_format("DEBUG", message, module, **kwargs), flush=True)

    def section(self, title: str):
        """Print a visual separator for major pipeline sections."""
        bar = "─" * 50
        print(_c(_BOLD, f"\n{bar}"), flush=True)
        print(_c(_BOLD, f"  {title}"), flush=True)
        print(_c(_BOLD, f"{bar}"), flush=True)


# ── Singleton ─────────────────────────────────────────────────────────────────
log = _Logger()
