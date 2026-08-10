from __future__ import annotations

import subprocess
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STOP_FLAG = ROOT / "stop.flag"
MAIN = ROOT / "main.py"
LOG = ROOT / "watchdog.log"


def _pythonw() -> str:
    """Prefer windowless interpreter so no CMD appears on the taskbar."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        return str(exe)
    candidate = exe.with_name("pythonw.exe")
    if candidate.exists():
        return str(candidate)
    discovered = shutil.which("pythonw") or shutil.which("python")
    return discovered or str(exe)


def _creation_flags() -> int:
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    return flags


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def main() -> int:
    if STOP_FLAG.exists():
        STOP_FLAG.unlink(missing_ok=True)
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from app.config import load_config
        from app.machine import assert_allowed

        assert_allowed(load_config().allowed_machine_id)
    except Exception as exc:
        log(f"machine lock refused: {exc}")
        return 1

    py = _pythonw()
    log(f"watchdog started (python={py}); stop only via stop.flag")
    while True:
        if STOP_FLAG.exists():
            log("stop.flag found — watchdog exit")
            STOP_FLAG.unlink(missing_ok=True)
            return 0
        log("starting main.py")
        try:
            proc = subprocess.run(
                [py, str(MAIN)],
                cwd=str(ROOT),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_creation_flags(),
            )
            code = proc.returncode
        except Exception as exc:
            log(f"launch failed: {exc}")
            code = 1
        if STOP_FLAG.exists():
            log("stop.flag found after main exit — watchdog exit")
            STOP_FLAG.unlink(missing_ok=True)
            return 0
        log(f"main.py exited code={code}; restart in 3s")
        time.sleep(3)


if __name__ == "__main__":
    raise SystemExit(main())
