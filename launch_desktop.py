"""Desktop EXE entry: starts screen-telegram watchdog (keeps app alive)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Keep the source tree relocatable. A frozen build should be placed next to it.
ROOT = Path(__file__).resolve().parent
STOP_FLAG = ROOT / "stop.flag"
WATCHDOG = ROOT / "watchdog.py"
# Prefer a windowless interpreter without relying on a user-specific path.
_python = shutil.which("pythonw") or shutil.which("python") or sys.executable
PYTHONW = Path(_python)


def _already_running() -> bool:
    try:
        cmd = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" |"
            " Where-Object { $_.CommandLine -match 'screen-telegram.*(watchdog|main\\.py)' } |"
            " Select-Object -First 1 -ExpandProperty ProcessId"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        ).strip()
        return bool(out)
    except Exception:
        return False


def _machine_allowed() -> bool:
    """Fail closed on foreign PCs before spawning watchdog."""
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from app.config import load_config
        from app.machine import assert_allowed

        cfg = load_config()
        assert_allowed(cfg.allowed_machine_id)
        return True
    except Exception:
        return False


def main() -> int:
    os.chdir(ROOT)
    if STOP_FLAG.exists():
        STOP_FLAG.unlink(missing_ok=True)

    if not _machine_allowed():
        # Silent refuse on foreign machines — no UI hint for misuse.
        return 1

    if _already_running():
        return 0

    creation = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creation |= subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creation |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creation |= subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [str(PYTHONW), str(WATCHDOG)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation,
        close_fds=True,
    )
    time.sleep(0.8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
