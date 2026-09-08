"""Start the local Second Listen demo and open it in the default browser."""

from __future__ import annotations

import subprocess
import sys
import urllib.error
import time
import urllib.request
import webbrowser
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
URL = "http://localhost:3000"
# Use the loopback IP for the readiness check so a system proxy cannot
# accidentally make localhost look healthy before our server is running.
HEALTH_URL = "http://127.0.0.1:3000/health"


def is_ready() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def main() -> int:
    if is_ready():
        print(f"Second Listen is already running. Opening {URL} ...")
        webbrowser.open(URL)
        return 0

    server = APP_DIR / "deployment" / "browser" / "server.py"
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    process = subprocess.Popen(
        [sys.executable, str(server)],
        cwd=APP_DIR,
        creationflags=creationflags,
    )

    for _ in range(30):
        if is_ready():
            print(f"Server is ready. Opening {URL} ...")
            webbrowser.open(URL)
            return 0
        if process.poll() is not None:
            print(
                "[ERROR] The server stopped before becoming ready "
                f"(exit code {process.returncode})."
            )
            return 1
        time.sleep(1)

    print("[ERROR] The server did not become ready within 30 seconds.")
    print("Check the Second Listen server window for the error message.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
