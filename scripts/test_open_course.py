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
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_serve import FAKE_CLAUDE  # noqa: E402


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
        self.env = dict(os.environ, PATH=f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
                        FAKE_CLAUDE_LOG=str(base / "claude.log"))
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
        out = self.run_cmd("lessons/x.html", "--port", str(self.port), "--web", "adk.dev")
        self.assertIn("Started the course server", out)
        self.assertIn(f"http://localhost:{self.port}/lessons/x.html", out)
        first = self.pid()
        saved = json.loads((self.ws / "course.json").read_text())
        self.assertEqual(saved, {"web": ["adk.dev"], "port": self.port})

        out = self.run_cmd()
        self.assertIn("Reusing", out, "a second call with no flags reuses the saved settings")
        self.assertEqual(self.pid(), first)

        out = self.run_cmd("--code", str(self.ws))
        self.assertIn("Started", out, "new settings restart the server")
        self.assertNotEqual(self.pid(), first)

        self.assertIn("Stopped", self.run_cmd("--stop"))
        self.assertFalse((self.ws / ".serve.json").exists())

    def test_busy_port_moves_to_the_next_free_one(self):
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", self.port))
            blocker.listen()
            out = self.run_cmd("--port", str(self.port))
        self.assertIn("Started", out)
        self.assertNotEqual(json.loads((self.ws / "course.json").read_text())["port"], self.port)


if __name__ == "__main__":
    unittest.main(verbosity=1)
