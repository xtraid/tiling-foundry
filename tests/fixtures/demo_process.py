"""Real subprocess tree used only by the demo supervisor tests."""

from pathlib import Path
import ctypes
import os
import signal
import subprocess
import sys
import time


mode, location = sys.argv[1:]
root = Path(location)


def wait_for(name):
    deadline = time.monotonic() + 8
    while not (root / name).exists():
        if time.monotonic() >= deadline:
            raise RuntimeError(f"fixture did not receive {name}")
        time.sleep(0.01)


if mode in ("child", "grandchild"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (root / f"{mode}.pid").write_text(str(os.getpid()))
    if mode == "child":
        subprocess.Popen([sys.executable, __file__, "grandchild", str(root)])
        wait_for("grandchild.pid")
    (root / f"{mode}.ready").touch()
    while True:
        time.sleep(0.02)

(root / "worker.pid").write_text(str(os.getpid()))
if mode == "unusual-name":
    # /proc stat comm is arbitrary bytes and can contain whitespace/parentheses.
    assert ctypes.CDLL(None).prctl(15, b"demo \xff ) name", 0, 0, 0) == 0
if mode == "normal":
    print("normal worker output", flush=True)
    sys.exit(0)

subprocess.Popen([sys.executable, __file__, "child", str(root)])
wait_for("child.ready")
(root / "ready").touch()
sys.stdout.write("partial output without newline")
sys.stdout.flush()
if mode in ("leader0", "leader7"):
    wait_for("release")
    sys.exit(0 if mode == "leader0" else 7)
while True:
    if mode == "verbose":
        os.write(sys.stdout.fileno(), b"x" * 65536)
    time.sleep(0.002)
