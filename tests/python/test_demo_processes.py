from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/demo_process.py"
HARNESS = """
import os, pathlib, sys, time
from tools import demo
root = pathlib.Path(sys.argv[1])
if sys.argv[4] == 'backpressure':
    # Fill both pipes before supervision, then leave their readers idle.
    for stream in (sys.stdout, sys.stderr):
        fd = stream.fileno()
        os.set_blocking(fd, False)
        try:
            while True:
                os.write(fd, b'P' * 4096)
        except BlockingIOError:
            pass
        finally:
            os.set_blocking(fd, True)
if sys.argv[4] == 'broken-output':
    class BrokenOutput:
        def write(self, data):
            raise OSError('terminal disappeared')
        def flush(self):
            pass
    sys.stdout = BrokenOutput()
try:
    result = demo._supervise(
        [sys.executable, sys.argv[2], sys.argv[3], str(root)],
        cwd=pathlib.Path.cwd(), env=os.environ.copy(),
        log_path=root / 'worker.log', timeout=float(sys.argv[5]),
    )
except OSError as error:
    print(str(error), file=sys.stderr)
    result = 1
sys.exit(result)
"""


def live(pid):
    try:
        # Linux stat comm may contain spaces and parentheses.
        state = Path(f"/proc/{pid}/stat").read_bytes().rsplit(b")", 1)[1].split()[0]
        return state not in (b"Z", b"X")
    except FileNotFoundError:
        return False


class DemoProcessTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("tools.demo"), "demo supervisor is missing")

    def run_tree(self, mode, *, timeout=1.5, signals=(), broken=False, undrained=False):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            started = time.monotonic()
            process = subprocess.Popen(
                [sys.executable, "-c", HARNESS, str(root), str(FIXTURE), mode,
                 "backpressure" if undrained else "broken-output" if broken else "output", str(timeout)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True,
            )
            try:
                if mode != "normal":
                    deadline = time.monotonic() + 8
                    while not (root / "ready").exists():
                        if process.poll() is not None or time.monotonic() >= deadline:
                            stdout, stderr = process.communicate(timeout=3)
                            self.fail(f"fixture did not become ready: {stdout} {stderr}")
                        time.sleep(0.01)
                    if mode.startswith("leader"):
                        (root / "release").touch()
                    for item in signals:
                        process.send_signal(item)
                        time.sleep(0.05)
                if undrained:
                    try:
                        process.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        self.fail("supervisor blocked on undrained output instead of stopping its group")
                stdout, stderr = process.communicate(timeout=10)
                self.assertLess(time.monotonic() - started, 10)
                for pid_file in root.glob("*.pid"):
                    self.assertFalse(live(int(pid_file.read_text())), pid_file.name)
                log = (root / "worker.log").read_bytes()
                self.assertNotIn("dossier=", stdout)
                return process.returncode, stdout, stderr, log
            finally:
                worker_pid = root / "worker.pid"
                if worker_pid.exists():
                    try:
                        os.killpg(int(worker_pid.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=3)

    def test_normal_worker_is_reaped_and_output_is_logged_and_forwarded(self):
        code, stdout, _, log = self.run_tree("normal")
        self.assertEqual(code, 0)
        self.assertIn("normal worker output", stdout)
        self.assertIn(b"normal worker output", log)

    def test_timeout_stops_child_and_grandchild_which_ignore_term(self):
        code, stdout, stderr, log = self.run_tree("tree")
        self.assertEqual(code, 124, stderr)
        self.assertIn("timeout", (stdout + stderr).lower())
        self.assertIn(b"partial output without newline", log)

    def test_process_names_with_non_utf8_bytes_do_not_break_group_cleanup(self):
        code, _, stderr, _ = self.run_tree("unusual-name")
        self.assertEqual(code, 124, stderr)

    def test_dead_leader_does_not_orphan_children_or_block_on_inherited_output(self):
        for mode in ("leader0", "leader7"):
            with self.subTest(mode=mode):
                code, _, _, log = self.run_tree(mode, timeout=8)
                self.assertNotEqual(code, 0)
                self.assertNotEqual(code, 124)
                self.assertIn(b"partial output", log)

    def test_repeated_cancellation_signals_do_not_interrupt_group_cleanup(self):
        for first in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=first):
                code, stdout, stderr, _ = self.run_tree("tree", timeout=8, signals=(first, signal.SIGTERM, signal.SIGINT))
                self.assertEqual(code, 128 + first, stderr)
                self.assertIn("cancel", (stdout + stderr).lower())

    def test_verbose_partial_output_cannot_postpone_global_timeout(self):
        code, stdout, _, log = self.run_tree("verbose")
        self.assertEqual(code, 124)
        self.assertGreater(len(log), 100000)
        self.assertLess(len(stdout), 2_000_000)

    def test_full_stdout_and_stderr_pipes_cannot_block_timeout_or_cancellation(self):
        for signals in ((), (signal.SIGTERM, signal.SIGINT)):
            with self.subTest(signals=signals):
                code, _, _, log = self.run_tree(
                    "verbose", timeout=8 if signals else 0.4,
                    signals=signals, undrained=True,
                )
                self.assertEqual(code, 143 if signals else 124)
                self.assertIn(b"partial output without newline", log)

    def test_parent_output_exception_still_cleans_the_entire_group(self):
        code, _, stderr, log = self.run_tree("tree", timeout=8, broken=True)
        self.assertEqual(code, 1)
        self.assertIn("terminal disappeared", stderr)
        self.assertIn(b"partial output", log)


if __name__ == "__main__":
    unittest.main()
