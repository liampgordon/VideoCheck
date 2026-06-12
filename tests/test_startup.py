import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_DIR / "videocheck_qt.py"


def test_app_launches_without_crashing():
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT)],
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(2)
        returncode = proc.poll()
        if returncode is not None:
            _, stderr = proc.communicate()
            raise AssertionError(
                f"App exited immediately (code {returncode}):\n{stderr}"
            )
    finally:
        proc.terminate()
        proc.wait(timeout=5)
