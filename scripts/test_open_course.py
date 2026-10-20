"""Tests for open_course.py: start, reuse, restart on new settings, stop. Uses a fake `claude`.

Usage: python3 test_open_course.py
"""

import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_serve import FAKE_CLAUDE  # noqa: E402


class WindowsTest(unittest.TestCase):
    """On Windows, os.kill(pid, 0) ends a process instead of checking it, and start_new_session does nothing."""

    def setUp(self):
        import open_course
        self.oc = open_course
        self.old = open_course.WINDOWS, open_course.subprocess.run, open_course.subprocess.Popen
        open_course.WINDOWS = True

    def tearDown(self):
        self.oc.WINDOWS, self.oc.subprocess.run, self.oc.subprocess.Popen = self.old

    def test_alive_asks_tasklist_and_never_signals(self):
        seen = []

        def run(cmd, **_):
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout='"python.exe","4242","Console","1","9,000 K"\n')

        self.oc.subprocess.run = run
        self.assertTrue(self.oc.alive(4242))
        self.assertEqual(seen[0][0], "tasklist")
        self.oc.subprocess.run = lambda cmd, **_: subprocess.CompletedProcess(cmd, 0, stdout="INFO: No tasks are running\n")
        self.assertFalse(self.oc.alive(4242))

    def test_stop_ends_the_server_and_its_children(self):
        ws = Path(tempfile.mkdtemp())
        (ws / ".serve.json").write_text(json.dumps({"pid": 4242, "port": 1}))
        # The server answers as this course's, ignores the polite request, and so gets ended.
        self.oc.ping = lambda port, token=None: {"course": str(ws.resolve()), "pid": 4242}
        self.oc.request_shutdown = lambda port, token=None: False
        seen = []

        def run(cmd, **_):
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="INFO: No tasks are running\n")

        self.oc.subprocess.run = run
        self.assertTrue(self.oc.stop(ws))
        self.assertIn(["taskkill", "/T", "/F", "/PID", "4242"], seen)

    def test_start_detaches_the_server(self):
        seen = {}

        def popen(cmd, **kw):
            seen.update(kw, cmd=cmd)
            raise OSError("not starting anything in a test")

        self.oc.subprocess.Popen = popen
        ws = Path(tempfile.mkdtemp())
        with self.assertRaises(OSError):
            self.oc.start(ws, {"port": 1})
        self.assertTrue(seen.get("creationflags"), "detached from the console, so closing it does not stop the server")
        self.assertEqual(seen["cmd"][1:3], ["-X", "utf8"], "UTF-8 output, so a non-ASCII course path cannot crash it")


class StaleRecordTest(unittest.TestCase):
    def test_stop_never_kills_a_process_it_cannot_confirm(self):
        # After a crash or a reboot, the saved process number may belong to something else entirely.
        import open_course
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            ws = Path(tempfile.mkdtemp())
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            (ws / ".serve.json").write_text(json.dumps({"pid": other.pid, "port": port}))
            self.assertFalse(open_course.stop(ws))
            self.assertIsNone(other.poll(), "an unrelated process with a reused number was left alone")
            self.assertFalse((ws / ".serve.json").exists(), "the stale record is cleared")
        finally:
            other.kill()
            other.wait()


class OlderServerTest(unittest.TestCase):
    def test_stop_ends_a_server_from_before_ping_named_its_process(self):
        import open_course
        server = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        # Collect it the moment it ends, as init would for a real server; otherwise it lingers as a zombie.
        threading.Thread(target=server.wait, daemon=True).start()
        ws = Path(tempfile.mkdtemp())
        (ws / ".serve.json").write_text(json.dumps({"pid": server.pid, "port": 1}))
        old = open_course.ping, open_course.request_shutdown
        open_course.ping = lambda port, token=None: {"course": str(ws.resolve())}  # no "pid": an older server
        open_course.request_shutdown = lambda port, token=None: False  # and no shutdown route either
        try:
            self.assertTrue(open_course.stop(ws))
            self.assertIsNotNone(server.wait(timeout=5))
        finally:
            open_course.ping, open_course.request_shutdown = old
            if server.poll() is None:
                server.kill()


class UpdateTest(unittest.TestCase):
    """An update must reach a running server, but never by stopping a teaching job or claiming a start that failed."""

    def setUp(self):
        import open_course
        self.oc = open_course
        self.saved = {k: getattr(open_course, k) for k in ("ping", "teaching", "stop", "start", "subprocess", "time")}
        self.saved_sync = open_course.sync_course.sync
        open_course.sync_course.sync = lambda ws: ([], [])
        self.ws = Path(tempfile.mkdtemp())
        (self.ws / "index.html").write_text("<main></main>")
        current = {"course": str(self.ws.resolve()), "code": None, "web": [], "lan": False, "pid": 1,
                   "version": open_course.sync_course.code_version(), "skill": str(HERE.parent)}
        self.info = current

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(self.oc, k, v)
        self.oc.sync_course.sync = self.saved_sync
        shutil.rmtree(self.ws, ignore_errors=True)

    def main(self, *args):
        out, argv = StringIO(), sys.argv
        sys.argv = ["open_course.py", str(self.ws), "--no-open", "--port", "1", *args]
        try:
            with redirect_stdout(out):
                self.oc.main()
        finally:
            sys.argv = argv
        return out.getvalue()

    def refuse(self, *_args, **_kw):
        raise AssertionError("must not be called")

    def test_wanted_needs_the_same_code_and_skill_folder(self):
        cfg = {"port": 1}
        self.assertTrue(self.oc.wanted(self.info, cfg))
        self.assertFalse(self.oc.wanted({**self.info, "version": "older"}, cfg))
        self.assertFalse(self.oc.wanted({**self.info, "skill": "/an/old/plugin/folder"}, cfg))
        self.assertFalse(self.oc.wanted({k: v for k, v in self.info.items() if k != "version"}, cfg))

    def test_a_running_teaching_job_keeps_the_old_server(self):
        self.oc.ping = lambda port, token=None: {**self.info, "version": "older"}
        self.oc.teaching = lambda port, token=None: True
        self.oc.stop = self.oc.start = self.refuse
        self.assertIn("teaching job", self.main())

    def test_a_server_still_stopping_is_not_reported_as_started(self):
        self.oc.ping = lambda port, token=None: {**self.info, "version": "older"}
        self.oc.teaching = lambda port, token=None: False
        self.oc.stop = lambda ws: None
        self.oc.start = self.refuse
        with self.assertRaises(SystemExit) as caught:
            self.main()
        self.assertIn("has not stopped yet", str(caught.exception))

    def test_start_waits_for_the_new_server_not_the_old_one(self):
        class Proc:
            pid = 7
        self.oc.subprocess = type("S", (), {"Popen": lambda *a, **k: Proc(), "DEVNULL": None, "STDOUT": None})
        self.oc.time = type("T", (), {"sleep": staticmethod(lambda s: None)})
        self.oc.ping = lambda port, token=None: {**self.info, "pid": 99}  # the old server, still answering
        self.assertFalse(self.oc.start(self.ws.resolve(), {"port": 1}, stale_pid=99))
        self.oc.ping = lambda port, token=None: {**self.info, "pid": 100}
        self.assertTrue(self.oc.start(self.ws.resolve(), {"port": 1}, stale_pid=99))


class OpenCourseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.ws = base / "course"
        shutil.copytree(HERE.parent / "starter" / "assets", self.ws / "assets")
        (self.ws / "lessons").mkdir()
        shutil.copy(HERE.parent / "starter" / "index.html", self.ws / "index.html")
        (base / "bin").mkdir()
        fake = base / "bin" / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        # HOME too, so syncing the course writes its diagram profile here, not into the real home folder.
        self.env = dict(os.environ, PATH=f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
                        FAKE_CLAUDE_LOG=str(base / "claude.log"), HOME=str(base))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]

    def tearDown(self):
        self.run_cmd("--stop")
        self.tmp.cleanup()

    def run_cmd(self, *args):
        out = subprocess.run([sys.executable, str(HERE / "open_course.py"), str(self.ws), *args, "--no-open"]
                             if "--stop" not in args else
                             [sys.executable, str(HERE / "open_course.py"), str(self.ws), *args],
                             env=self.env, capture_output=True, text=True, timeout=30)
        return out.stdout + out.stderr

    def pid(self):
        return json.loads((self.ws / ".serve.json").read_text())["pid"]

    def test_start_reuse_restart_stop(self):
        out = self.run_cmd("lessons/x.html", "--port", str(self.port), "--web", "docs.example.org")
        # The exact Python that ran this, not "python3", which on Windows may be a Microsoft Store placeholder.
        self.assertIn(f"Stop it with: {sys.executable} ", out)
        self.assertIn("Started the course server", out)
        self.assertIn(f"http://localhost:{self.port}/lessons/x.html", out)
        first = self.pid()
        saved = json.loads((self.ws / "course.json").read_text())
        self.assertEqual(saved, {"web": ["docs.example.org"], "port": self.port})

        out = self.run_cmd()
        self.assertIn("Reusing", out, "a second call with no flags reuses the saved settings")
        self.assertEqual(self.pid(), first)

        out = self.run_cmd("--code", str(self.ws))
        self.assertIn("Started", out, "new settings restart the server")
        self.assertNotEqual(self.pid(), first)

        self.assertIn("Stopped", self.run_cmd("--stop"))
        self.assertFalse((self.ws / ".serve.json").exists())

    def test_open_refreshes_the_course_shared_files(self):
        (self.ws / "assets" / "ask.js").write_text("// from an older version of the skill\n")
        out = self.run_cmd("--port", str(self.port))
        self.assertIn("Updated the course's shared files: ask.js", out)
        self.assertEqual((self.ws / "assets" / "ask.js").read_bytes(),
                         (HERE.parent / "starter" / "assets" / "ask.js").read_bytes())

    def test_a_server_started_from_another_copy_of_the_skill_is_restarted(self):
        # As after a plugin update: the old server runs from a folder that will be deleted.
        copy = Path(self.tmp.name) / "old-skill"
        shutil.copytree(HERE, copy / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(HERE.parent / "starter", copy / "starter")
        old = subprocess.Popen([sys.executable, str(copy / "scripts" / "serve.py"), str(self.ws), "--port", str(self.port)],
                               env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Collect it the moment it ends, as init would for a real server; otherwise it lingers as a zombie.
        threading.Thread(target=old.wait, daemon=True).start()
        try:
            import open_course
            for _ in range(100):
                info = open_course.ping(self.port)
                if info:
                    break
                subprocess.run([sys.executable, "-c", "import time; time.sleep(0.1)"])
            self.assertEqual(info["skill"], str(copy.resolve()))
            out = self.run_cmd("--port", str(self.port))
            self.assertIn("Started", out)
            self.assertEqual(open_course.ping(self.port)["skill"], str(HERE.parent))
            self.assertIsNotNone(old.wait(timeout=15), "the old server was stopped")
        finally:
            if old.poll() is None:
                old.kill()

    def test_busy_port_moves_to_the_next_free_one(self):
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", self.port))
            blocker.listen()
            out = self.run_cmd("--port", str(self.port))
        self.assertIn("Started", out)
        self.assertNotEqual(json.loads((self.ws / "course.json").read_text())["port"], self.port)


if __name__ == "__main__":
    unittest.main(verbosity=1)
