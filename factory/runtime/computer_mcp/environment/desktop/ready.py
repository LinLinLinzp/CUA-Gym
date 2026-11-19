"""Start the two desktop endpoints after the visible task is ready."""

from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


HERE = Path(__file__).resolve().parent
SOCKET = Path("/run/cua-grading/terminal-state.sock")


def healthy(url):
    try:
        with urlopen(url, timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def snapshot_ready():
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(SOCKET))
            client.sendall(b"snapshot\n")
            with client.makefile("rb") as response:
                header = response.read(8)
                return len(header) == 8 and 0 < int.from_bytes(header, "big") <= 48 * 1024 * 1024
    except OSError:
        return False


if sys.argv[1:] == ["--check"]:
    sys.exit(0 if snapshot_ready() and healthy("http://127.0.0.1:8000/health") else 1)

children = [
    subprocess.Popen(["/usr/bin/python3", str(HERE / "snapshot_server.py")]),
    subprocess.Popen(["runuser", "-u", "desktop-driver", "--", "/usr/bin/python3", str(HERE / "gui_server.py")]),
]


def stop(*_):
    for child in children:
        if child.poll() is None:
            child.terminate()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
while all(child.poll() is None for child in children):
    time.sleep(1)
stop()
for child in children:
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
sys.exit(1)
