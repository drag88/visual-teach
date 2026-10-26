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
        self.oc.request_shutdown = lambda port, token=None, if_idle=False: False
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
        open_course.request_shutdown = lambda port, token=None, if_idle=False: False  # and no shutdown route either
        try:
            self.assertTrue(open_course.stop(ws))
            self.assertIsNotNone(server.wait(timeout=5))
        finally:
            open_course.ping, open_course.request_shutdown = old
            if server.poll() is None:
                server.kill()


class StubbedOpen(unittest.TestCase):
    """open_course.main() run in this process, with the server calls replaced."""

    def setUp(self):
        import open_course
        self.oc = open_course
        self.saved = {k: getattr(open_course, k) for k in ("ping", "teaching", "stop", "start", "subprocess", "time",
                                                            "port_free")}
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


class UpdateTest(StubbedOpen):
    """An update must reach a running server, but never by stopping a teaching job or claiming a start that failed."""

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
        self.oc.stop = lambda ws, if_idle=False: None
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


class SyncTest(unittest.TestCase):
    def test_a_tag_written_another_way_is_not_added_twice(self):
        import sync_course
        ws = Path(tempfile.mkdtemp())
        (ws / "lessons").mkdir()
        page = ws / "lessons" / "one.html"
        page.write_text('<html><head><link rel="stylesheet" href="../assets/style.css" />\n'
                        '<script src="../assets/theme.js" defer></script></head><body><main></main></body></html>')
        self.assertTrue(sync_course.link_assets(page, ws))
        html = page.read_text()
        for name in ("style.css", "theme.js", "ask.css", "quiz.js", "ask.js"):
            self.assertEqual(html.count(f"assets/{name}"), 1, name)
        self.assertFalse(sync_course.link_assets(page, ws), "a second sync changes nothing")
        shutil.rmtree(ws)


class SyncTagTest(unittest.TestCase):
    def test_only_a_real_tag_counts_as_loading(self):
        import sync_course
        ws = Path(tempfile.mkdtemp())
        (ws / "lessons").mkdir()
        page = ws / "lessons" / "two.html"
        page.write_text('<html><head><script data-src="../assets/theme.js"></script></head><body><main></main>'
                        '<!-- <script src="../assets/ask.js"></script> -->'
                        '<SCRIPT SRC="../assets/quiz.js?v=2"></SCRIPT></body></html>')
        sync_course.link_assets(page, ws)
        html = page.read_text()
        self.assertIn('<script src="../assets/theme.js"></script>', html, "data-src loads nothing")
        self.assertIn('<script src="../assets/ask.js"></script>\n</body>', html, "a commented-out tag loads nothing")
        self.assertEqual(html.lower().count("assets/quiz.js"), 1, "SRC= with a query string already loads it")
        shutil.rmtree(ws)


class SyncParseTest(unittest.TestCase):
    def test_tags_are_read_as_html_not_as_text(self):
        import sync_course
        ws = Path(tempfile.mkdtemp())
        (ws / "lessons").mkdir()
        page = ws / "lessons" / "three.html"
        page.write_text('<html><head><link rel="preload" as="style" href="../assets/style.css"></head><body><main></main>'
                        '<script data-example=" src=\'../assets/ask.js\'"></script>'
                        '<script title=">" src="../assets/quiz.js"></script></body></html>')
        sync_course.link_assets(page, ws)
        html = page.read_text()
        self.assertIn('<link rel="stylesheet" href="../assets/style.css">', html, "a preload does not apply a stylesheet")
        self.assertIn('<script src="../assets/ask.js"></script>', html, "src inside another attribute loads nothing")
        self.assertEqual(html.count("assets/quiz.js"), 1, "a > inside a quoted attribute is still one tag")
        shutil.rmtree(ws)

    def test_the_tag_type_counts_and_a_broken_url_does_not_stop_sync(self):
        import sync_course
        ws = Path(tempfile.mkdtemp())
        (ws / "lessons").mkdir()
        page = ws / "lessons" / "four.html"
        page.write_text('<html><head><link rel="stylesheet" href="../assets/ask.js"></head><body><main></main>'
                        '<script src="https://[broken/vendor.js"></script><script src="../assets/quiz.js\n"></script></body></html>')
        sync_course.link_assets(page, ws)  # must not raise
        self.assertIn('<script src="../assets/ask.js"></script>', page.read_text(), "a link tag does not run a script")
        self.assertEqual(page.read_text().count("assets/quiz.js"), 1, "a browser drops the newline, so this loads quiz.js")
        shutil.rmtree(ws)


class LanSettingTest(StubbedOpen):
    def test_no_lan_turns_the_phone_link_off(self):
        self.oc.ping = lambda port, token=None: None
        self.oc.start = lambda ws, cfg, stale_pid=None: True
        self.oc.port_free = lambda port: True
        (self.ws / "course.json").write_text(json.dumps({"lan": True, "port": 1}))
        self.main("--no-lan")
        self.assertFalse(json.loads((self.ws / "course.json").read_text())["lan"])


class EngineSettingTest(StubbedOpen):
    def test_engine_is_saved_and_kept(self):
        self.oc.ping = lambda port, token=None: None
        self.oc.start = lambda ws, cfg, stale_pid=None: True
        self.oc.port_free = lambda port: True
        self.main("--engine", "codex")
        self.assertEqual(json.loads((self.ws / "course.json").read_text())["engine"], "codex")
        self.main()
        self.assertEqual(json.loads((self.ws / "course.json").read_text())["engine"], "codex")


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
        # HOME and USERPROFILE (Windows) too, so syncing writes the diagram profile here, not in the real home folder.
        self.env = dict(os.environ, PATH=f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
                        FAKE_CLAUDE_LOG=str(base / "claude.log"), HOME=str(base), USERPROFILE=str(base))
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


class RestartSafetyTest(unittest.TestCase):
    """A restart for an update waits for any teaching job, and an opened page carries the phone token it needs."""

    def setUp(self):
        import open_course
        self.oc = open_course
        self.saved = {k: getattr(open_course, k) for k in ("ping", "teaching", "stop", "start", "port_free")}
        self.saved_sync = open_course.sync_course.sync
        self.synced = []
        open_course.sync_course.sync = lambda ws: self.synced.append(ws) or ([], [])
        self.ws = Path(tempfile.mkdtemp())
        (self.ws / "index.html").write_text("<main></main>")
        self.old = {"course": str(self.ws.resolve()), "code": None, "web": [], "lan": False, "pid": 1,
                    "version": "older", "skill": str(HERE.parent)}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(self.oc, k, v)
        self.oc.sync_course.sync = self.saved_sync
        shutil.rmtree(self.ws, ignore_errors=True)

    def main(self, *args):
        out, argv = StringIO(), sys.argv
        sys.argv = ["open_course.py", str(self.ws), *args, "--no-open", "--port", "1"]  # page first, as in the usage
        try:
            with redirect_stdout(out):
                self.oc.main()
        finally:
            sys.argv = argv
        return out.getvalue()

    def never(self, *_a, **_k):
        raise AssertionError("must not be called")

    def test_unknown_teaching_state_keeps_the_server_and_its_files(self):
        self.oc.ping = lambda port, token=None: self.old
        self.oc.teaching = lambda port, token=None: None  # the status request failed
        self.oc.stop = self.oc.start = self.never
        self.assertIn("may be running a teaching job", self.main())
        self.assertEqual(self.synced, [], "the old server's check would see new files and its fix would copy old ones back")

    def test_a_job_started_after_the_check_refuses_the_shutdown(self):
        self.oc.ping = lambda port, token=None: self.old
        self.oc.teaching = lambda port, token=None: False
        self.oc.stop = lambda ws, if_idle=False: "busy" if if_idle else self.never()
        self.oc.start = self.never
        self.assertIn("may be running a teaching job", self.main())
        self.assertEqual(self.synced, [])

    def test_a_failed_if_idle_request_never_falls_back_to_a_kill(self):
        # Nothing confirmed the server idle, so a job may have started; only --stop forces a stop.
        server = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        threading.Thread(target=server.wait, daemon=True).start()
        (self.ws / ".serve.json").write_text(json.dumps({"pid": server.pid, "port": 1}))
        old = self.oc.ping, self.oc.request_shutdown
        self.oc.ping = lambda port, token=None: {**self.old, "pid": server.pid}
        self.oc.request_shutdown = lambda port, token=None, if_idle=False: False  # timed out
        try:
            self.assertEqual(self.oc.stop(self.ws, if_idle=True), "busy")
            self.assertIsNone(server.poll(), "the server and its job were left running")
        finally:
            self.oc.ping, self.oc.request_shutdown = old
            server.kill()

    def test_the_token_joins_a_query_the_page_already_has(self):
        self.oc.ping = lambda port, token=None: None
        self.oc.port_free = lambda port: True
        def start(ws, cfg, stale_pid=None):
            (ws / ".serve.json").write_text(json.dumps({"phone_url": "http://192.0.2.1:1/?k=tok"}))
            return True
        self.oc.start = start
        self.assertIn("Open: http://localhost:1/lessons/x.html?view=1&k=tok#q-one", self.main("lessons/x.html?view=1#q-one"))

    def test_the_opened_link_carries_the_phone_token(self):
        # With --lan the server wants the token from this computer too, and a restart makes a new one.
        self.oc.ping = lambda port, token=None: None
        self.oc.port_free = lambda port: True
        def start(ws, cfg, stale_pid=None):
            (ws / ".serve.json").write_text(json.dumps({"phone_url": "http://192.0.2.1:1/?k=tok"}))
            return True
        self.oc.start = start
        out = self.main("lessons/x.html#q-one")
        self.assertIn("Open: http://localhost:1/lessons/x.html?k=tok#q-one", out)


class SyncSafetyTest(unittest.TestCase):
    def test_sync_replaces_a_linked_asset_instead_of_writing_through_it(self):
        import sync_course
        base = Path(tempfile.mkdtemp())
        outside = base / "outside.css"
        outside.write_text("someone else's file\n")
        ws = base / "course"
        shutil.copytree(HERE.parent / "starter" / "assets", ws / "assets")
        (ws / "assets" / "style.css").unlink()
        (ws / "assets" / "style.css").symlink_to(outside)
        old_profile, sync_course.PROFILE = sync_course.PROFILE, base / "profile.md"
        try:
            sync_course.sync(ws)
        finally:
            sync_course.PROFILE = old_profile
        self.assertEqual(outside.read_text(), "someone else's file\n")
        self.assertFalse((ws / "assets" / "style.css").is_symlink())
        self.assertEqual((ws / "assets" / "style.css").read_bytes(), (HERE.parent / "starter/assets/style.css").read_bytes())
        shutil.rmtree(base)

    def test_a_linked_asset_is_replaced_even_when_its_bytes_match(self):
        # The server never serves a file from outside the course, so a link would leave the page without its script.
        import sync_course
        base = Path(tempfile.mkdtemp())
        same = base / "same-ask.js"
        shutil.copy(HERE.parent / "starter" / "assets" / "ask.js", same)
        ws = base / "course"
        shutil.copytree(HERE.parent / "starter" / "assets", ws / "assets")
        (ws / "assets" / "ask.js").unlink()
        (ws / "assets" / "ask.js").symlink_to(same)
        old_profile, sync_course.PROFILE = sync_course.PROFILE, base / "profile.md"
        try:
            changed, _ = sync_course.sync(ws)
        finally:
            sync_course.PROFILE = old_profile
        self.assertIn("ask.js", changed)
        self.assertFalse((ws / "assets" / "ask.js").is_symlink())
        shutil.rmtree(base)


if __name__ == "__main__":
    unittest.main(verbosity=1)
