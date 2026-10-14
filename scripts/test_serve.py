"""Tests for serve.py, run against a fake `claude` that replays a canned stream.

Usage: python3 test_serve.py
"""

import http.client
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import serve  # noqa: E402

FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
prompt = sys.stdin.read()
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as f:
    f.write(json.dumps({"argv": argv, "stdin": prompt}) + "\n")
def arg(name):
    return argv[argv.index(name) + 1] if name in argv else None
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
        for k in ("FAKE_CLAUDE_FAIL_RESUME", "FAKE_CLAUDE_FAIL", "FAKE_READ", "FAKE_CLAUDE_SLOW",
                  "FAKE_CLAUDE_IS_ERROR", "FAKE_TEXT"):
            os.environ.pop(k, None)
        self.claude = str(fake)
        self.start()

    def start(self, lan=False):
        self.server = serve.make_server(self.ws, port=0, lan=lan, code=self.code, claude=self.claude,
                                        web=["adk.dev", "github.com"])
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
        system = argv[argv.index("--append-system-prompt") + 1]
        self.assertIn("office manager", system)
        self.assertIn("test mission", system)

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
        self.assertIn("WebFetch(domain:adk.dev)", deep)
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

    def test_topics_from_syllabus(self):
        _, data = self.request("GET", "/api/topics")
        topics = json.loads(data)["topics"]
        self.assertEqual(topics[0], {"title": "Building blocks", "href": "lessons/one.html", "tags": "agent · runner"})
        self.assertEqual(topics[1]["title"], "Tools")

    def test_static_files_and_ping(self):
        resp, data = self.request("GET", "/lessons/one.html")
        self.assertEqual(resp.status, 200)
        self.assertIn("hands out jobs", data)
        resp, data = self.request("GET", "/api/ping")
        self.assertEqual(json.loads(data)["ok"], True)

    def test_rejects_cross_site_and_non_json_posts(self):
        resp, _ = self.request("POST", "/api/ask", {"kind": "ask"}, {"Origin": "https://evil.example"})
        self.assertEqual(resp.status, 403)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/api/ask", body="{}", headers={"Host": f"localhost:{self.port}", "Content-Type": "text/plain"})
        self.assertEqual(conn.getresponse().status, 415)
        conn.close()
        resp, _ = self.request("GET", "/api/ping", headers={"Host": "evil.example"})
        self.assertEqual(resp.status, 403, "DNS rebinding: unknown Host refused on localhost mode")

    def test_lan_mode_needs_token(self):
        self.server.shutdown()
        self.server.server_close()
        self.start(lan=True)
        token = self.server.token
        resp, _ = self.request("GET", "/api/ping")
        self.assertEqual(resp.status, 401)
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
