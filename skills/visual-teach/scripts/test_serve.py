"""Tests for serve.py, run against a fake `claude` that replays a canned stream.

Usage: python3 test_serve.py
"""

import http.client
import json
import os
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import serve  # noqa: E402
import sync_course  # noqa: E402

FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
prompt = sys.stdin.read()
def arg(name):
    return argv[argv.index(name) + 1] if name in argv else None
def contents(flag):
    value = arg(flag)
    return open(value, encoding="utf-8").read() if value and os.path.isfile(value) else value
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as f:
    f.write(json.dumps({"argv": argv, "stdin": prompt, "system": contents("--append-system-prompt-file"),
                        "settings": contents("--settings"), "env": os.environ.get("VT_TEST_ENV")}) + "\n")
if "--resume" in argv and os.environ.get("FAKE_CLAUDE_FAIL_RESUME"):
    print("No conversation found", file=sys.stderr)
    sys.exit(1)
if os.environ.get("FAKE_CLAUDE_FAIL"):
    print("boom", file=sys.stderr)
    sys.exit(2)
session = arg("--session-id") or arg("--resume")
model = {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}.get(arg("--model"), arg("--model"))
def out(obj):
    print(json.dumps(obj), flush=True)
out({"type": "system", "subtype": "init", "session_id": session, "model": model})
out({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": os.environ.get("FAKE_READ", "lessons/one.html")}}]}})
if os.environ.get("FAKE_CLAUDE_IS_ERROR"):
    out({"type": "result", "subtype": "success", "is_error": True, "result": "Claude usage limit reached"})
    sys.exit(0)
if os.environ.get("FAKE_CLAUDE_SLOW"):
    import time
    time.sleep(3)  # a quiet stretch, like Claude reading files before it writes
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as f:  # recorded before writing, so a closed pipe cannot hide it
    f.write(json.dumps({"finished": True}) + "\n")
pieces = [os.environ["FAKE_TEXT"]] if os.environ.get("FAKE_TEXT") else ["The runner ", "is the office ", "manager. (¶2)"]
for piece in pieces:
    out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": piece}}})
out({"type": "result", "subtype": "success", "total_cost_usd": 0.0123, "session_id": session})
'''


def make_workspace(root):
    (root / "lessons").mkdir()
    (root / "index.html").write_text(
        '<ol class="syllabus"><li><a href="lessons/one.html">Building blocks</a><br>'
        '<span class="tag">agent · runner</span></li><li class="soon">Tools<br><span class="tag">docstrings</span></li></ol>'
    )
    (root / "lessons/one.html").write_text("<main><p>The runner hands out jobs.</p></main>")
    (root / "MISSION.md").write_text("# Mission: test mission\n")
    (root / "NOTES.md").write_text("Analogy: the runner is the office manager.\n")


class GuardTest(unittest.TestCase):
    """teach_guard.py: the hook that keeps a teaching session's edits inside the course."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.ws = base / "course"
        (self.ws / "lessons").mkdir(parents=True)
        (self.ws / "assets").mkdir()
        (base / "outside").mkdir()
        (self.ws / "lessons" / "escape").symlink_to(base / "outside")

    def tearDown(self):
        self.tmp.cleanup()

    def guard(self, event):
        return subprocess.run([sys.executable, "-I", str(HERE / "teach_guard.py"), str(self.ws)],
                              input=event if isinstance(event, str) else json.dumps(event),
                              capture_output=True, text=True).returncode

    def edit(self, path, tool="Edit"):
        return self.guard({"tool_name": tool, "tool_input": {"file_path": str(path)}, "cwd": str(self.ws)})

    def test_lessons_may_be_edited(self):
        self.assertEqual(self.edit(self.ws / "lessons" / "0002-new.html", "Write"), 0)
        self.assertEqual(self.edit("lessons/0001-x.html"), 0, "relative to the session's folder")
        self.assertEqual(self.edit(self.ws / "assets" / "course.css"), 0)

    def test_everything_else_is_blocked(self):
        for path in (self.ws.parent / "outside" / "x.txt", self.ws / "lessons" / "escape" / "x.html",
                     self.ws / "lessons" / ".." / ".." / "x", self.ws / "course.json", self.ws / ".serve.json",
                     self.ws / ".claude" / "settings.json", self.ws / "CLAUDE.md", self.ws / "assets" / "ask.js",
                     # A Mac's disk ignores case, so these name the same protected files.
                     self.ws / "Course.json", self.ws / "claude.md", self.ws / ".Claude" / "settings.json",
                     self.ws / "ASSETS" / "ask.js", self.ws / "Assets" / "Course.CSS" / ".." / "ask.js"):
            self.assertEqual(self.edit(path), 2, path)

    def test_anything_unexpected_blocks(self):
        self.assertEqual(self.guard("not json"), 2)
        self.assertEqual(self.guard({"tool_name": "Edit", "tool_input": {}}), 2)


class ServeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.ws = base / "course"
        self.ws.mkdir()
        make_workspace(self.ws)
        self.code = base / "code"
        self.code.mkdir()
        bindir = base / "bin"
        bindir.mkdir()
        fake = bindir / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.log = base / "claude.log"
        os.environ["FAKE_CLAUDE_LOG"] = str(self.log)
        # Teaching jobs sync the course, which installs the diagram profile; keep it out of the real home folder.
        self.addCleanup(setattr, sync_course, "PROFILE", sync_course.PROFILE)
        sync_course.PROFILE = base / "profile.md"
        for k in ("FAKE_CLAUDE_FAIL_RESUME", "FAKE_CLAUDE_FAIL", "FAKE_READ", "FAKE_CLAUDE_SLOW",
                  "FAKE_CLAUDE_IS_ERROR", "FAKE_TEXT"):
            os.environ.pop(k, None)
        self.claude = str(fake)
        self.start()

    def start(self, lan=False):
        self.server = serve.make_server(self.ws, port=0, lan=lan, code=self.code, claude=self.claude,
                                        web=["docs.example.org", "github.com"], codex="")
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"localhost:{self.port}"}
        if body is not None:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        resp = conn.getresponse()
        data = resp.read().decode()
        conn.close()
        return resp, data

    def ask(self, **fields):
        body = {"lesson": "lessons/one.html", "lesson_title": "Building blocks", "kind": "ask", "mode": "quick",
                "selection": "runner", "para": {"n": 2, "key": "the-runner-hands-out-jobs", "quote": {"exact": "runner"}},
                "para_text": "The runner hands out jobs.", "question": "What is the runner?",
                "lesson_text": "¶1 Title\n¶2 The runner hands out jobs."}
        body.update(fields)
        resp, data = self.request("POST", "/api/ask", body)
        events = []
        for block in data.strip().split("\n\n"):
            lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
            if "event" in lines:
                events.append((lines["event"], json.loads(lines["data"])))
        return resp, events

    def calls(self):
        return [c for c in map(json.loads, self.log.read_text().splitlines()) if "argv" in c]

    def finished_runs(self):
        return [c for c in map(json.loads, self.log.read_text().splitlines()) if c.get("finished")]

    def records(self):
        return [json.loads(line) for line in (self.ws / "questions.jsonl").read_text().splitlines()]

    def test_streams_status_then_deltas_then_done(self):
        resp, events = self.ask()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "text/event-stream")
        kinds = [k for k, _ in events]
        self.assertEqual(kinds[0], "thread")
        self.assertIn("status", kinds)
        self.assertLess(kinds.index("status"), kinds.index("delta"))
        self.assertEqual(kinds[-1], "done")
        text = "".join(d["text"] for k, d in events if k == "delta")
        self.assertEqual(text, "The runner is the office manager. (¶2)")
        status = next(d for k, d in events if k == "status")
        self.assertEqual(status["text"], "Reading lessons/one.html")
        done = events[-1][1]
        self.assertEqual(done["model"], "claude-sonnet-5-5")
        self.assertAlmostEqual(done["cost_usd"], 0.0123)
        self.assertIsInstance(done["ms_first_word"], int)

    def test_read_only_flags_and_prompt_on_stdin(self):
        self.ask()
        argv = self.calls()[0]["argv"]
        self.assertIn("-p", argv)
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertIn("--strict-mcp-config", argv)
        tools = argv[argv.index("--tools") + 1: argv.index("--tools") + 4]
        self.assertEqual(tools, ["Read", "Grep", "Glob"])
        for banned in ("Edit", "Write", "Bash", "NotebookEdit"):
            self.assertNotIn(banned, argv)
        self.assertEqual(argv[argv.index("--add-dir") + 1], str(self.code.resolve()))
        stdin = self.calls()[0]["stdin"]
        self.assertIn("What is the runner?", stdin)
        self.assertIn("¶2 The runner hands out jobs.", stdin)
        # Long, multi-line text travels in a file: a Windows command line (claude.cmd) would mangle it.
        self.assertNotIn("--append-system-prompt", argv)
        system = self.calls()[0]["system"]
        self.assertIn("office manager", system)
        self.assertIn("test mission", system)
        # The learner's own Claude settings (hooks, plugins, allow rules) stay out of answers.
        self.assertIn("--restricted", argv)
        self.assertNotIn("--setting-sources", argv)

    def test_page_question_names_the_paragraph_being_read(self):
        self.ask(kind="whole", selection=None, para_text=None, para={"n": 2, "key": "the-runner", "quote": None})
        self.assertIn("The learner was reading ¶2 when they asked.", self.calls()[0]["stdin"])
        self.assertEqual(self.records()[0]["anchor"]["n"], 2, "the card comes back beside that paragraph")

    def test_quick_and_deep_models(self):
        self.ask(mode="quick")
        self.ask(mode="deep")
        self.ask(mode="deep", kind="simpler")
        quick, deep, simpler = (c["argv"] for c in self.calls())
        self.assertEqual(quick[quick.index("--model") + 1], "sonnet")
        self.assertEqual(quick[quick.index("--effort") + 1], "low")
        self.assertEqual(deep[deep.index("--model") + 1], "opus")
        self.assertEqual(deep[deep.index("--effort") + 1], "high")
        self.assertIn("WebFetch", deep)
        self.assertIn("WebFetch(domain:docs.example.org)", deep)
        self.assertNotIn("WebFetch", quick)
        self.assertEqual(simpler[simpler.index("--model") + 1], "sonnet", "simpler always runs quick")

    def test_follow_up_resumes_same_session(self):
        _, first = self.ask()
        thread = first[0][1]["thread"]
        _, second = self.ask(thread=thread, question="And the agent?", lesson_text=None)
        a, b = (c["argv"] for c in self.calls())
        session = a[a.index("--session-id") + 1]
        self.assertEqual(b[b.index("--resume") + 1], session)
        self.assertNotIn("--session-id", b)
        self.assertEqual(second[0][1]["thread"], thread)

    def test_resume_failure_starts_new_session_with_thread_inlined(self):
        _, first = self.ask()
        thread = first[0][1]["thread"]
        os.environ["FAKE_CLAUDE_FAIL_RESUME"] = "1"
        _, events = self.ask(thread=thread, question="And the agent?", lesson_text=None)
        calls = self.calls()
        self.assertEqual(len(calls), 3)
        retry = calls[2]
        self.assertIn("--session-id", retry["argv"])
        self.assertIn("What is the runner?", retry["stdin"], "earlier question inlined")
        self.assertIn("The runner is the office manager.", retry["stdin"], "earlier answer inlined")
        self.assertEqual(events[-1][0], "done")

    def start_slow_ask(self, port=None, **fields):
        """Open a question that goes quiet after its first status line, and return the open socket."""
        os.environ["FAKE_CLAUDE_SLOW"] = "1"
        q = {"kind": "ask", "mode": "deep", "lesson": "lessons/one.html", "question": "Slow one"}
        q.update(fields)
        body = json.dumps(q).encode()
        port = port or self.port
        sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        sock.sendall(f"POST /api/ask HTTP/1.1\r\nHost: localhost:{port}\r\nContent-Type: application/json\r\n"
                     f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        seen = b""
        while b"event: status" not in seen:
            seen += sock.recv(4096)
        return sock

    def test_error_result_is_an_error(self):
        os.environ["FAKE_CLAUDE_IS_ERROR"] = "1"
        _, events = self.ask()
        self.assertEqual(events[-1][0], "error")
        self.assertIn("usage limit", events[-1][1]["message"])
        self.assertFalse(any(r["role"] == "assistant" for r in self.records()))

    def test_unicode_line_separators_survive_the_log(self):
        os.environ["FAKE_TEXT"] = "One\u2028two\u2029three"
        self.ask()
        _, data = self.request("GET", "/api/threads?lesson=lessons/one.html")
        messages = json.loads(data)["threads"][0]["messages"]
        self.assertEqual(messages[-1]["text"], "One\u2028two\u2029three")

    def test_one_question_at_a_time_per_thread(self):
        _, first = self.ask()
        thread = first[0][1]["thread"]
        sock = self.start_slow_ask(thread=thread)
        _, events = self.ask(thread=thread, question="Second, while the first is running")
        sock.close()
        self.assertEqual(events[-1][0], "error")
        self.assertIn("still answering", events[-1][1]["message"].lower())

    def test_symlink_out_of_the_course_is_not_served(self):
        outside = self.ws.parent / "secret.txt"
        outside.write_text("private")
        (self.ws / "leak.txt").symlink_to(outside)
        resp, data = self.request("GET", "/leak.txt")
        self.assertEqual(resp.status, 404)
        self.assertNotIn("private", data)

    def test_killing_the_server_stops_running_claude(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        os.environ["FAKE_CLAUDE_SLOW"] = "1"  # set before the server starts, so its fake claude inherits it
        env = dict(os.environ, PATH=f"{Path(self.claude).parent}{os.pathsep}{os.environ['PATH']}")
        server = subprocess.Popen([sys.executable, str(HERE / "serve.py"), str(self.ws), "--port", str(port)],
                                  env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=1).close()
                    break
                except OSError:
                    time.sleep(0.1)
            sock = self.start_slow_ask(port=port)
            server.terminate()  # what `kill <pid>` sends, as opposed to Ctrl-C in its own terminal
            server.wait(timeout=5)
            time.sleep(4)
            sock.close()
            self.assertEqual(self.finished_runs(), [], "claude kept running after the server was killed")
        finally:
            if server.poll() is None:
                server.kill()

    def test_reader_leaving_stops_claude(self):
        os.environ["FAKE_CLAUDE_SLOW"] = "1"
        body = json.dumps({"kind": "ask", "mode": "deep", "lesson": "lessons/one.html", "question": "Slow one"}).encode()
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        sock.sendall(f"POST /api/ask HTTP/1.1\r\nHost: localhost:{self.port}\r\nContent-Type: application/json\r\n"
                     f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        seen = b""
        while b"event: status" not in seen:
            seen += sock.recv(4096)
        sock.close()  # the reader deletes the card or closes the tab while Claude is quiet
        time.sleep(4)
        self.assertEqual(self.finished_runs(), [], "claude kept running after the reader left")
        self.assertFalse(any(r["role"] == "assistant" for r in self.records()))

    def test_follow_up_to_an_unanswered_question_carries_what_was_asked(self):
        # The first answer never finished, so no Claude session was saved; the follow-up starts a new one and
        # must hand over the original question and the passage it was about.
        self.server.course.append({"t": serve.now(), "thread": "t-lost", "lesson": "lessons/one.html", "kind": "explain",
                                   "mode": "quick", "selection": "the runner hands out jobs", "role": "user",
                                   "text": serve.KIND_TASK["explain"]})
        self.ask(thread="t-lost", question="Explain it again", selection=None, para=None)
        stdin = self.calls()[-1]["stdin"]
        self.assertIn("The conversation so far", stdin)
        self.assertIn('about "the runner hands out jobs"', stdin)
        self.assertIn("--session-id", self.calls()[-1]["argv"], "a new session, since none was saved")

    def test_follow_up_to_an_unanswered_connect_keeps_its_topic(self):
        self.server.course.append({"t": serve.now(), "thread": "t-connect", "lesson": "lessons/one.html", "kind": "connect",
                                   "mode": "quick", "topic": "Tools", "selection": "the runner", "role": "user",
                                   "text": serve.KIND_TASK["connect"]})
        self.ask(thread="t-connect", question="Explain it again", selection=None, para=None)
        self.assertIn('connecting it to "Tools"', self.calls()[-1]["stdin"])

    def test_step_lines_stay_short(self):
        # Steps show in a narrow panel: the skill's files by name, long search patterns cut.
        course = self.server.course
        skill_file = {"name": "Read", "input": {"file_path": str(serve.SKILL / "vendor" / "teach" / "GLOSSARY-FORMAT.md")}}
        self.assertEqual(course.describe(skill_file), "Reading the skill's GLOSSARY-FORMAT.md")
        long = course.describe({"name": "Grep", "input": {"pattern": "^(async )?def (match|compute|score|rank|pick)_[a-z]+"}})
        self.assertEqual(long, 'Searching for "^(async )?def (match|compute|score|rank…"')

    def test_failure_words(self):
        ok = {"returncode": 0, "stderr": "", "error": None}
        self.assertIsNone(serve.failure(ok))
        self.assertEqual(serve.failure({**ok, "returncode": -15}), "It was stopped before it finished.")
        self.assertEqual(serve.failure({**ok, "returncode": 1, "stderr": "boom"}), "boom")
        self.assertEqual(serve.failure({**ok, "returncode": 2}), "claude exited 2")
        self.assertEqual(serve.failure({**ok, "error": "Claude usage limit reached"}), "Claude usage limit reached")

    def test_teaching_prompt_says_what_it_cannot_reach(self):
        # Without the web, a lesson on a topic outside the course folder would be written from memory.
        prompt = self.server.course.teach_prompt("next", None)
        self.assertIn("cannot search the web", prompt)
        self.server.course.web = ["docs.example.org"]
        self.assertIn("docs.example.org", self.server.course.teach_prompt("next", None))

    def test_failure_sends_error_event(self):
        os.environ["FAKE_CLAUDE_FAIL"] = "1"
        _, events = self.ask()
        self.assertEqual(events[-1][0], "error")
        self.assertIn("boom", events[-1][1]["message"])

    def test_records_and_threads_and_delete(self):
        _, events = self.ask()
        thread = events[0][1]["thread"]
        user, assistant = self.records()
        self.assertEqual(user["role"], "user")
        self.assertEqual(user["thread"], thread)
        self.assertEqual(user["kind"], "ask")
        self.assertEqual(user["anchor"]["key"], "the-runner-hands-out-jobs")
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["text"], "The runner is the office manager. (¶2)")
        self.assertIn("session", assistant)
        _, data = self.request("GET", "/api/threads?lesson=lessons/one.html")
        threads = json.loads(data)["threads"]
        self.assertEqual(len(threads), 1)
        self.assertEqual([m["role"] for m in threads[0]["messages"]], ["user", "assistant"])
        self.request("POST", "/api/delete", {"thread": thread})
        _, data = self.request("GET", "/api/threads?lesson=lessons/one.html")
        self.assertEqual(json.loads(data)["threads"], [])
        self.assertEqual(self.records()[-1]["event"], "deleted")

    def test_learning_records_list_and_delete(self):
        records = self.ws / "learning-records"
        records.mkdir()
        (records / "0001-runner.md").write_text("# Runner landed\n\nStatus: superseded by 0002\n")
        (records / "0002-tools.md").write_text("# Tools landed\n")
        _, data = self.request("GET", "/api/records")
        self.assertEqual(json.loads(data)["records"], [
            {"name": "0001-runner.md", "title": "Runner landed", "superseded": True},
            {"name": "0002-tools.md", "title": "Tools landed", "superseded": False}])
        for bad in ("../MISSION.md", "missing.md", None, ["0002-tools.md"]):
            resp, _ = self.request("POST", "/api/records/delete", {"name": bad})
            self.assertEqual(resp.status, 404, bad)
        self.assertTrue((self.ws / "MISSION.md").exists())
        resp, _ = self.request("POST", "/api/records/delete", {"name": "0001-runner.md"})
        self.assertEqual(resp.status, 200)
        self.assertTrue((self.ws / ".deleted/learning-records/0001-runner.md").exists(), "moved aside, not erased")
        _, data = self.request("GET", "/api/records")
        self.assertEqual([r["name"] for r in json.loads(data)["records"]], ["0002-tools.md"])

    def test_deleting_a_record_twice_keeps_both_copies(self):
        records, deleted = self.ws / "learning-records", self.ws / ".deleted/learning-records"
        records.mkdir()
        deleted.mkdir(parents=True)
        (deleted / "0002-tools.md").write_text("first")
        (deleted / "0002-tools-1.md").write_text("second")
        (records / "0002-tools.md").write_text("# Tools landed\nthird")
        resp, _ = self.request("POST", "/api/records/delete", {"name": "0002-tools.md"})
        self.assertEqual(resp.status, 200)
        self.assertEqual((deleted / "0002-tools.md").read_text(), "first")
        self.assertEqual((deleted / "0002-tools-1.md").read_text(), "second")
        self.assertEqual((deleted / "0002-tools-2.md").read_text(), "# Tools landed\nthird")

    def test_symlinked_records_are_neither_listed_nor_moved(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "0001-a.md").write_text("# Not the course's\n")
        (self.ws / "learning-records").symlink_to(outside)  # the whole folder points elsewhere
        _, data = self.request("GET", "/api/records")
        self.assertEqual(json.loads(data)["records"], [])
        resp, _ = self.request("POST", "/api/records/delete", {"name": "0001-a.md"})
        self.assertEqual(resp.status, 404)
        self.assertTrue((outside / "0001-a.md").exists())
        (self.ws / "learning-records").unlink()
        (self.ws / "learning-records").mkdir()
        (self.ws / "learning-records/0002-link.md").symlink_to(outside / "0001-a.md")  # one entry points elsewhere
        (self.ws / "learning-records/0003-real.md").write_text("# Real\n")
        _, data = self.request("GET", "/api/records")
        self.assertEqual([r["name"] for r in json.loads(data)["records"]], ["0003-real.md"])
        resp, _ = self.request("POST", "/api/records/delete", {"name": "0002-link.md"})
        self.assertEqual(resp.status, 404)
        (self.ws / ".deleted").symlink_to(outside)  # the archive points elsewhere
        resp, _ = self.request("POST", "/api/records/delete", {"name": "0003-real.md"})
        self.assertEqual(resp.status, 404)
        self.assertTrue((self.ws / "learning-records/0003-real.md").exists())

    def test_threads_for_a_blank_page_name_are_its_own(self):
        self.ask()
        _, data = self.request("GET", "/api/threads?lesson=")
        self.assertEqual(json.loads(data)["threads"], [], "a blank page name is a page, not every page")

    def test_topics_from_syllabus(self):
        _, data = self.request("GET", "/api/topics")
        topics = json.loads(data)["topics"]
        self.assertEqual(topics[0], {"title": "Building blocks", "href": "lessons/one.html", "tags": "agent · runner"})
        self.assertEqual(topics[1]["title"], "Tools")

    def test_static_files_and_ping(self):
        resp, data = self.request("GET", "/lessons/one.html")
        self.assertEqual(resp.status, 200)
        # A browser must check before reusing a course file, or after an update it can mix old scripts with new styles.
        self.assertEqual(resp.getheader("Cache-Control"), "no-cache")
        self.assertIn("hands out jobs", data)
        resp, data = self.request("GET", "/api/ping")
        info = json.loads(data)
        self.assertEqual(info["ok"], True)
        # open_course.py restarts a server whose code or skill folder differs from the installed one.
        self.assertEqual(info["version"], sync_course.code_version())
        self.assertEqual(info["skill"], str(serve.SKILL))

    def test_ping_lists_the_engines_on_path(self):
        info = json.loads(self.request("GET", "/api/ping")[1])
        self.assertEqual(info["engines"], ["claude"])
        self.assertEqual(info["engine_default"], "claude")

    def test_codex_only_server_starts_and_reads_the_course_default_live(self):
        self.server.shutdown()
        self.server.server_close()
        fake = Path(self.tmp.name) / "bin" / "codex"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        self.server = serve.make_server(self.ws, port=0, claude="", codex=str(fake))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        info = json.loads(self.request("GET", "/api/ping")[1])
        self.assertEqual((info["engines"], info["engine_default"]), (["codex"], "codex"))
        # A course default naming an engine that is not here is ignored.
        (self.ws / "course.json").write_text(json.dumps({"engine": "claude"}))
        self.assertEqual(json.loads(self.request("GET", "/api/ping")[1])["engine_default"], "codex")

    def test_course_default_engine_is_read_on_each_ping(self):
        self.server.shutdown()
        self.server.server_close()
        fake = Path(self.tmp.name) / "bin" / "codex"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        self.server = serve.make_server(self.ws, port=0, claude=self.claude, codex=str(fake))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.assertEqual(json.loads(self.request("GET", "/api/ping")[1])["engine_default"], "claude")
        (self.ws / "course.json").write_text(json.dumps({"engine": "codex"}))
        self.assertEqual(json.loads(self.request("GET", "/api/ping")[1])["engine_default"], "codex")

    def test_server_needs_claude_or_codex(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        done = subprocess.run([sys.executable, str(HERE / "serve.py"), str(self.ws), "--port", "0"],
                              env=dict(os.environ, PATH=str(empty)), capture_output=True, text=True, timeout=20)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("claude", done.stderr)
        self.assertIn("codex", done.stderr)

    def test_rejects_cross_site_and_non_json_posts(self):
        resp, _ = self.request("POST", "/api/ask", {"kind": "ask"}, {"Origin": "https://evil.example"})
        self.assertEqual(resp.status, 403)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/api/ask", body="{}", headers={"Host": f"localhost:{self.port}", "Content-Type": "text/plain"})
        self.assertEqual(conn.getresponse().status, 415)
        conn.close()
        resp, _ = self.request("GET", "/api/ping", headers={"Host": "evil.example"})
        self.assertEqual(resp.status, 403, "DNS rebinding: unknown Host refused on localhost mode")

    # Teaching from the course page

    def teach(self, action):
        return self.request("POST", "/api/teach", {"action": action})

    def teach_status(self):
        return json.loads(self.request("GET", "/api/teach")[1])

    def wait_job(self, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            job = self.teach_status()["job"]
            if job and job["state"] != "running":
                return job
            time.sleep(0.1)
        self.fail("the teaching job did not finish")

    @staticmethod
    def flag_values(argv, flag):
        i = argv.index(flag) + 1
        out = []
        while i < len(argv) and not argv[i].startswith("--"):
            out.append(argv[i])
            i += 1
        return out

    def test_teach_edits_only_inside_the_course(self):
        self.server.course.check = lambda *_: (True, "ok: 1 pages, 1 lessons")
        self.assertTrue(self.teach_status()["allowed"])
        resp, _ = self.teach("next")
        self.assertEqual(resp.status, 200)
        job = self.wait_job()
        self.assertEqual(job["state"], "done")
        self.assertIn("office manager", job["summary"])
        self.assertEqual(job["check"], {"ok": True, "text": "ok: 1 pages, 1 lessons"})
        call = self.calls()[-1]
        argv, ws = call["argv"], str(self.ws.resolve())
        tools = self.flag_values(argv, "--tools")
        self.assertIn("Edit", tools)
        self.assertIn("Write", tools)
        self.assertNotIn("Bash", argv, "no shell: the server runs every script itself")
        self.assertEqual(argv[argv.index("--model") + 1], "opus")
        # Claude Code checks writes against Edit rules and ignores Write(path) rules, so only Edit rules are given.
        allowed = self.flag_values(argv, "--allowedTools")
        self.assertIn(f"Edit(/{ws}/**)", allowed)
        denied = self.flag_values(argv, "--disallowedTools")
        self.assertIn(f"Edit(/{ws}/course.json)", denied)  # holds the refresh command, run in a shell
        self.assertFalse([r for r in allowed + denied if r.startswith("Write(")])
        dirs = [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir"]
        self.assertIn(str(serve.SKILL), dirs)
        self.assertIn(str(self.code.resolve()), dirs)
        self.assertIn("SKILL.md", call["stdin"])
        self.assertIn("next lesson", call["stdin"])
        # Rules alone are not enough: a user's own settings may allow Edit everywhere, so a hook checks every path.
        self.assertIn("--restricted", argv, "no user or course settings: only what the server passes")
        hooks = json.loads(call["settings"])["hooks"]["PreToolUse"]
        hook = hooks[0]["hooks"][0]
        # Exec form: no shell, so a path with spaces or backslashes reaches Python intact on any system.
        self.assertEqual(hook["command"], sys.executable)
        self.assertEqual(hook.get("onFailure"), "block", "a guard that cannot run must stop the edit, not wave it on")
        for protected in ("assets/*.js", ".claude/**", "CLAUDE.md"):
            self.assertIn(f"Edit(/{ws}/{protected})", denied)
        self.assertIn(str(serve.SKILL / "scripts" / "teach_guard.py"), hook["args"])
        self.assertIn(ws, hook["args"])
        self.assertIn("Edit", hooks[0]["matcher"])
        self.assertIn("Write", hooks[0]["matcher"])

    def test_answers_ignore_settings_planted_in_the_course(self):
        self.ask()
        self.assertIn("--restricted", self.calls()[0]["argv"])

    def test_data_rule_survives_a_course_prompt(self):
        (self.ws / "ask-prompt.md").write_text("A course's own answer rules.\n")
        self.ask()
        system = self.calls()[0]["system"]
        self.assertIn("A course's own answer rules.", system)
        self.assertIn("never data", system, "the data rule is the server's, not a prompt file's")

    def test_claude_config_dir_is_respected(self):
        home = self.ws.parent / "work-profile"
        home.mkdir()
        (home / "settings.json").write_text(json.dumps({"env": {"VT_TEST_ENV": "work"}}))
        os.environ["CLAUDE_CONFIG_DIR"] = str(home)
        os.environ.pop("VT_TEST_ENV", None)
        try:
            self.assertEqual(serve.Course(self.ws, None, self.claude, []).claude_env().get("VT_TEST_ENV"), "work")
        finally:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)

    def test_a_failed_launch_leaves_no_prompt_files(self):
        self.server.course.claude = str(self.ws.parent / "no-such-claude")
        _, events = self.ask()
        self.assertEqual(events[-1][0], "error")
        self.assertEqual(list(self.server.course.tmp.iterdir()), [])

    def test_ping_names_the_process_and_shutdown_is_local_and_clean(self):
        _, data = self.request("GET", "/api/ping")
        self.assertEqual(json.loads(data)["pid"], os.getpid())
        resp, _ = self.request("POST", "/api/shutdown", {}, headers={"Origin": "http://evil.example"})
        self.assertEqual(resp.status, 403)
        tmp = self.server.course.tmp
        resp, _ = self.request("POST", "/api/shutdown", {})
        self.assertEqual(resp.status, 200)
        end = time.time() + 5
        while tmp.exists() and time.time() < end:
            time.sleep(0.05)
        self.assertFalse(tmp.exists(), "a clean shutdown removes the server's temporary files")

    def test_user_settings_env_reaches_claude(self):
        # --restricted skips settings files, so the env block a learner relies on (proxy certificates, say) is passed on.
        settings = self.ws.parent / "user-settings.json"
        settings.write_text(json.dumps({"env": {"VT_TEST_ENV": "from-settings"}, "hooks": {"Stop": []}}))
        self.server.course.user_settings = settings
        os.environ.pop("VT_TEST_ENV", None)
        self.ask()
        self.assertEqual(self.calls()[0]["env"], "from-settings")
        os.environ["VT_TEST_ENV"] = "from-shell"
        try:
            self.ask(question="Again")
            self.assertEqual(self.calls()[-1]["env"], "from-shell", "the shell's own value wins")
        finally:
            os.environ.pop("VT_TEST_ENV", None)

    def test_windows_stop_kills_the_whole_tree(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        calls = []

        def taskkill(cmd, **_):
            calls.append(cmd)
            proc.kill()
            return subprocess.CompletedProcess(cmd, 0)

        old = serve.WINDOWS, serve.subprocess.run
        serve.WINDOWS, serve.subprocess.run = True, taskkill
        try:
            serve.stop(proc)
        finally:
            serve.WINDOWS, serve.subprocess.run = old
        self.assertEqual(calls, [["taskkill", "/T", "/F", "/PID", str(proc.pid)]])
        self.assertIsNotNone(proc.returncode)

    def test_rule_paths_on_windows(self):
        # Claude Code matches Windows paths in their POSIX form: C:\\Users\\me becomes /c/Users/me.
        from pathlib import PureWindowsPath
        self.assertEqual(serve.rule_path(PureWindowsPath(r"C:\Users\me\learn\course[1]")), "//c/Users/me/learn/course\\[1\\]")
        self.assertEqual(serve.rule_path(Path("/tmp/course")), "//tmp/course")

    def test_permission_rules_escape_the_course_path(self):
        self.server.course.ws = Path("/tmp/course[1]")
        argv = self.server.course.teach_command()
        self.assertIn("Edit(//tmp/course\\[1\\]/**)", self.flag_values(argv, "--allowedTools"))

    def test_course_pages_run_only_the_shared_scripts(self):
        resp, _ = self.request("GET", "/lessons/one.html")
        csp = resp.getheader("Content-Security-Policy") or ""
        for name in ("theme.js", "quiz.js", "ask.js"):
            self.assertIn(f"http://localhost:{self.port}/assets/{name}", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertIn("base-uri 'none'", csp)

    def test_check_never_imports_from_the_course(self):
        for prefix in self.server.course.checkers():
            self.assertIn("-I", prefix, "isolated: no course file can shadow an import")
            if prefix[0] == "uv":
                self.assertIn("--no-project", prefix)
                self.assertIn("--no-config", prefix)

    def test_stop_ends_a_running_check(self):
        course = self.server.course
        course.check = lambda job: course.call(["sleep", "30"], job, cwd=self.ws)
        self.teach("next")
        end = time.time() + 15
        while "Checking the course" not in ((self.teach_status()["job"] or {}).get("lines") or []):
            self.assertLess(time.time(), end, "the job never reached its check")
            time.sleep(0.1)
        started = time.time()
        self.request("POST", "/api/teach/stop", {})
        self.assertEqual(self.wait_job()["state"], "stopped")
        self.assertLess(time.time() - started, 6)

    def test_teach_one_job_at_a_time_and_stop(self):
        os.environ["FAKE_CLAUDE_SLOW"] = "1"
        self.server.course.check = lambda *_: (True, "ok")
        self.assertEqual(self.teach("next")[0].status, 200)
        self.assertEqual(self.teach("update")[0].status, 409)
        self.assertEqual(self.request("POST", "/api/teach/stop", {})[0].status, 200)
        self.assertEqual(self.wait_job()["state"], "stopped")
        self.assertEqual(self.teach("nonsense")[0].status, 400)

    def test_teach_refuses_once_the_skill_folder_is_gone(self):
        # A plugin update moves the skill to a new folder and later deletes the old one; this server would then
        # run a session with no guard script, no SKILL.md and no check.
        old = serve.SKILL
        serve.SKILL = self.ws / "deleted-skill"
        try:
            resp, body = self.teach("next")
        finally:
            serve.SKILL = old
        self.assertEqual(resp.status, 409)
        self.assertIn("Open the course again", json.loads(body)["error"])
        self.assertFalse(self.log.exists(), "no Claude run started")

    def test_shutdown_if_idle_waits_for_a_teaching_job(self):
        # The opener asks this way before a restart, so a job started a moment after its check is not ended.
        os.environ["FAKE_CLAUDE_SLOW"] = "1"
        self.server.course.check = lambda *_: (True, "ok")
        self.assertEqual(self.teach("next")[0].status, 200)
        resp, body = self.request("POST", "/api/shutdown", {"if_idle": True})
        self.assertEqual(resp.status, 409)
        self.assertEqual(self.teach_status()["job"]["state"], "running")
        self.request("POST", "/api/teach/stop", {})
        self.wait_job()

    def test_no_teaching_job_starts_once_a_shutdown_is_under_way(self):
        self.server.course.closing = True
        resp, body = self.teach("next")
        self.assertEqual(resp.status, 409)
        self.assertFalse(self.log.exists(), "no Claude run started")
        self.server.course.closing = False

    def test_teach_fix_sends_the_check_problems(self):
        self.server.course.check = lambda *_: (False, "0001-x.html: sentence over 25 words")
        self.teach("next")
        job = self.wait_job()
        self.assertFalse(job["check"]["ok"])
        self.teach("fix")
        self.wait_job()
        self.assertIn("sentence over 25 words", self.calls()[-1]["stdin"])

    def test_refresh_runs_the_course_command(self):
        self.assertFalse(self.teach_status()["refresh"])
        self.assertEqual(self.teach("refresh")[0].status, 404)
        out = self.ws / "refreshed.txt"
        (self.ws / "course.json").write_text(json.dumps({"refresh": f"pwd > {shlex.quote(str(out))}"}))
        self.assertTrue(self.teach_status()["refresh"])
        self.teach("refresh")
        self.assertEqual(self.wait_job()["state"], "done")
        # It runs from the home folder, so a relative path can never reach a file a teaching session wrote.
        self.assertEqual(Path(out.read_text().strip()).resolve(), Path.home().resolve())

    @unittest.skipIf(serve.lan_address() == "127.0.0.1", "no network address to test from")
    def test_teach_only_from_this_mac(self):
        self.server.shutdown()
        self.server.server_close()
        self.start(lan=True)
        ip = serve.lan_address()
        conn = http.client.HTTPConnection(ip, self.port, timeout=10)
        conn.request("GET", f"/api/teach?k={self.server.token}", headers={"Host": f"{ip}:{self.port}"})
        resp = conn.getresponse()
        status = json.loads(resp.read())
        conn.close()
        self.assertFalse(status["allowed"])
        conn = http.client.HTTPConnection(ip, self.port, timeout=10)
        conn.request("POST", f"/api/teach?k={self.server.token}", body=json.dumps({"action": "next"}),
                     headers={"Host": f"{ip}:{self.port}", "Content-Type": "application/json"})
        self.assertEqual(conn.getresponse().status, 403)
        conn.close()
        # A page from another site that points its name at this computer has the token's cookie but not our name.
        resp, _ = self.request("POST", f"/api/teach?k={self.server.token}", {"action": "next"},
                               headers={"Host": f"evil.example:{self.port}", "Origin": f"http://evil.example:{self.port}"})
        self.assertEqual(resp.status, 403)

    def test_lan_mode_needs_token(self):
        self.server.shutdown()
        self.server.server_close()
        self.start(lan=True)
        token = self.server.token
        resp, _ = self.request("GET", "/api/ping")
        self.assertEqual(resp.status, 401)
        resp, _ = self.request("HEAD", "/index.html")
        self.assertEqual(resp.status, 401, "HEAD is gated like GET")
        resp, _ = self.request("GET", f"/index.html?k={token}")
        self.assertEqual(resp.status, 200)
        cookie = resp.getheader("Set-Cookie").split(";")[0]
        resp, _ = self.request("GET", "/api/ping", headers={"Cookie": cookie})
        self.assertEqual(resp.status, 200)

    def test_status_shows_paths_relative_to_code_dir(self):
        os.environ["FAKE_READ"] = str(self.code / "ai/agent.py")
        _, events = self.ask()
        status = next(d for k, d in events if k == "status")
        self.assertEqual(status["text"], "Reading ai/agent.py")

    def source(self, path):
        resp, data = self.request("GET", "/api/source?path=" + quote(str(path)))
        return resp.status, (json.loads(data) if resp.status == 200 else data)

    def test_source_is_confined(self):
        (self.code / "app.py").write_text("one\ntwo\nthree\n")
        status, data = self.source("app.py")
        self.assertEqual((status, data), (200, {"path": "app.py", "text": "one\ntwo\nthree\n"}))
        resp, _ = self.request("GET", "/api/source?path=app.py")
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")
        self.assertEqual(self.source(self.code / "app.py"), (200, data), "absolute inside the folder")
        outside = self.ws.parent / "secret.txt"
        outside.write_text("private")
        (self.code / "leak.txt").symlink_to(outside)
        (self.code / "env-link").symlink_to(self.code / ".env")
        (self.code / ".env").write_text("TOKEN=private")
        (self.code / "sub").mkdir()
        refused = ["../secret.txt", "sub/../../secret.txt", str(outside), "leak.txt", ".env", "env-link",
                   "sub", "missing.py", "", "a\0b"]
        for path in refused:
            status, data = self.source(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn("private", data, path)
        (self.code / "bin.dat").write_bytes(b"ok\0ok")
        (self.code / "latin.txt").write_bytes(b"caf\xe9")
        self.assertEqual(self.source("bin.dat")[0], 415)
        self.assertEqual(self.source("latin.txt")[0], 415)
        (self.code / "big.txt").write_text("x" * 512_001)
        self.assertEqual(self.source("big.txt")[0], 413)
        (self.code / ".git").mkdir()
        self.server.course.git = None
        self.assertEqual(self.source("app.py")[0], 404, "a git folder without git on PATH refuses everything")
        (self.code / ".git").rmdir()
        self.server.course.code = None
        self.assertEqual(self.source("app.py")[0], 404, "no source folder")

    @unittest.skipUnless(shutil.which("git"), "git is not on PATH")
    def test_source_refuses_git_ignored(self):
        subprocess.run(["git", "init", "-q", str(self.code)], check=True)
        (self.code / ".gitignore").write_text("ignored.txt\nbuild/\n--stdin\n")
        (self.code / "ignored.txt").write_text("private")
        (self.code / "build").mkdir()
        (self.code / "build" / "out.js").write_text("private")
        (self.code / "--stdin").write_text("private")  # read as an option without "--", git would find nothing ignored
        (self.code / "app.py").write_text("x = 1\n")
        self.assertEqual(self.source("app.py")[0], 200)
        for path in ("ignored.txt", "build/out.js", "--stdin"):
            status, data = self.source(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn("private", data, path)

    @unittest.skipUnless(shutil.which("git"), "git is not on PATH")
    def test_source_refuses_what_a_parent_repo_ignores(self):
        # The source folder is often one part of a bigger project, so git's rules come from above it.
        repo = self.code.parent
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / ".gitignore").write_text("secrets.json\n")
        (self.code / "secrets.json").write_text("private")
        (self.code / "app.py").write_text("x = 1\n")
        self.assertEqual(self.source("app.py")[0], 200)
        self.assertEqual(self.source("secrets.json")[0], 404)

    def test_check_and_walk_prompts(self):
        self.ask(kind="check", quiz="q-runner", question="What does the runner do?", answer="It hands out jobs",
                 model="It schedules work for each agent.", selection=None, para_text=None)
        stdin = self.calls()[0]["stdin"]
        self.assertIn(serve.KIND_TASK["check"], stdin)
        self.assertIn("Question: What does the runner do?", stdin)
        self.assertIn("Learner's answer: It hands out jobs", stdin)
        self.assertIn("Right answer: It schedules work for each agent.", stdin)
        self.ask(kind="walk", mode="deep", question=None, selection="def run():\n    pass",
                 source={"path": "ai/agent.py", "start": 12, "end": 13})
        walk = self.calls()[1]
        self.assertIn('Highlighted lines 12-13 of ai/agent.py: "def run():\n    pass"', walk["stdin"])
        self.assertNotIn("Highlighted text", walk["stdin"])
        self.assertEqual(walk["argv"][walk["argv"].index("--model") + 1], "opus", "walk follows the learner's mode")
        tools = walk["argv"][walk["argv"].index("--tools") + 1:]
        self.assertEqual(tools[:4], ["Read", "Grep", "Glob", "WebFetch"])
        records = self.records()
        self.assertEqual([r["role"] for r in records], ["user", "assistant"] * 2)
        check, walk_user = records[0], records[2]
        self.assertEqual((check["kind"], check["quiz"], check["text"], check["source"]),
                         ("check", "q-runner", "It hands out jobs", None))
        self.assertEqual(walk_user["source"], {"path": "ai/agent.py", "start": 12, "end": 13})
        self.assertEqual(walk_user["text"], serve.KIND_TASK["walk"])
        self.assertNotIn("quiz", walk_user)
        self.ask(kind="uses", selection="run", source={"path": "ai/agent.py", "start": 12, "end": 12})
        self.assertIn(serve.KIND_TASK["uses"], self.calls()[2]["stdin"])

    def test_quiz_and_review(self):
        def post(**fields):
            body = {"lesson": "lessons/one.html", "quiz": "q-a", "type": "mcq", "q": "A?", "right": False}
            body.update(fields)
            return self.request("POST", "/api/quiz", body)

        resp, data = post()
        self.assertEqual((resp.status, json.loads(data)), (200, {"ok": True}))
        post(right=None, type="recall")
        rec = json.loads((self.ws / "quiz.jsonl").read_text().splitlines()[0])
        self.assertEqual(set(rec), {"t", "lesson", "quiz", "type", "q", "right"})
        self.assertFalse((self.ws / "questions.jsonl").exists(), "quiz results stay out of questions.jsonl")
        self.assertEqual(post(quiz=None)[0].status, 400)
        self.assertEqual(post(lesson="")[0].status, 400)
        self.assertEqual(self.request("POST", "/api/quiz", {"lesson": "x", "quiz": "q"},
                                      {"Origin": "https://evil.example"})[0].status, 403)
        _, data = self.request("GET", "/api/review")
        self.assertEqual(json.loads(data), {"due": [], "waiting": 1}, "a miss just now waits a day")

        def ago(**kw):
            return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()

        def rec(quiz, t, right):
            return json.dumps({"t": t, "lesson": "lessons/two.html", "quiz": quiz, "type": "mcq",
                               "q": quiz.upper() + "?", "right": right})

        seeded = [
            rec("q-b", ago(days=5), False), rec("q-b", ago(days=4), True),  # streak 1, due a day ago
            rec("q-b", ago(minutes=1), None),  # self-mark pending: ignored, so it does not push q-b back
            rec("q-a", ago(days=10), False),  # streak 0, due nine days ago
            rec("q-c", ago(days=30), False), rec("q-c", ago(days=20), True), rec("q-c", ago(days=10), True),
            rec("q-c", ago(days=2), True),  # three rights since the miss: retired
            rec("q-d", ago(days=9), True),  # never missed
            rec("q-e", ago(days=20), False), rec("q-e", ago(days=2), True),  # due tomorrow: waiting
        ]
        with (self.ws / "quiz.jsonl").open("a") as f:
            f.write("not json\n" + "\n".join(seeded) + "\n")
        _, data = self.request("GET", "/api/review")
        review = json.loads(data)
        self.assertEqual(review["due"], [
            {"lesson": "lessons/two.html", "quiz": "q-a", "q": "Q-A?", "href": "lessons/two.html#q-a", "streak": 0},
            {"lesson": "lessons/two.html", "quiz": "q-b", "q": "Q-B?", "href": "lessons/two.html#q-b", "streak": 1},
        ])
        self.assertEqual(review["waiting"], 2, "lessons/one.html#q-a and q-e")


if __name__ == "__main__":
    unittest.main(verbosity=1)
