"""Serve a visual-teach course and answer questions about it with Claude, live.

Usage: python3 serve.py <workspace> [--port 8765] [--code DIR] [--web DOMAIN ...] [--lan]

Serves the course folder as a website. A question asked on a lesson page runs
`claude -p` with read-only tools and streams the answer back as server-sent
events. Follow-ups resume the same Claude session. Every question and answer is
appended to <workspace>/questions.jsonl for the next teaching session.

--code DIR      lets answers read that folder (read-only), for courses about a real codebase
--web DOMAIN    lets Deep answers fetch pages from that domain (repeatable)
--lan           listens on the network for a phone; needs the printed link, which carries a token

Start it from your normal shell so `claude` inherits your login and proxy settings.
"""

import argparse
import html
import json
import os
import re
import secrets
import select
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SKILL = Path(__file__).resolve().parent.parent
TIERS = {"quick": ("sonnet", "low"), "deep": ("opus", "high")}
ALWAYS_QUICK = {"explain", "simpler", "more"}
KIND_TASK = {
    "explain": "Explain the highlighted words in about two sentences.",
    "simpler": "Explain the highlighted passage again, more simply, in about three sentences.",
    "more": "Say more about the highlighted passage in about six sentences, with one concrete example.",
    "connect": "Explain how the highlighted idea connects to the topic named below, in under 150 words. "
               "If a lesson in this course covers that topic, name it.",
    "ask": "Answer the question about the highlighted passage.",
    "whole": "Answer the question about the whole lesson.",
    "walk": "Walk through the highlighted lines in order, one step per line or statement, saying what each does "
            "in plain words. At most eight steps.",
    "uses": "Search the source folder for where the highlighted name or phrase is defined and where else it is "
            "used or mentioned. List up to eight places as path:line, most important first, a few plain words each.",
    "check": "The learner answered from memory. Mark it against the right answer and the lesson: start with Right, "
             "Nearly or Not yet, then say what they got right, what they missed, and if wrong where their thinking "
             "went off. Under 120 words.",
}
READ_TOOLS = ["Read", "Grep", "Glob"]
MAX_BODY = 1_000_000
MAX_SOURCE = 512_000
REVIEW_DAYS = (1, 3, 7)  # wait after a miss, by rights in a row since it; the third right retires the question
COOKIE = "vt_k"


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_text(path):
    try:
        return Path(path).read_text()
    except OSError:
        return ""


class Course:
    """The workspace, its question log, and how to ask Claude about it."""

    def __init__(self, ws, code, claude, web):
        self.ws = Path(ws).resolve()
        self.code = Path(code).resolve() if code else None
        self.claude = claude
        self.web = list(web or [])
        self.git = shutil.which("git")
        self.log = self.ws / "questions.jsonl"
        self.quiz_log = self.ws / "quiz.jsonl"
        self.lock = threading.Lock()
        self.busy = set()  # threads with an answer still streaming
        self.live = set()  # running claude processes, stopped if the server stops

    # Question log

    def append(self, record, log=None):
        with self.lock, (log or self.log).open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def records(self, log=None):
        with self.lock:
            text = read_text(log or self.log)
        out = []
        for line in text.split("\n"):  # not splitlines(): answers may hold U+2028 and friends
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
        return out

    def threads(self, lesson=None):
        by_thread, deleted = {}, set()
        for r in self.records():
            if r.get("role") == "meta":
                if r.get("event") == "deleted":
                    deleted.add(r.get("thread"))
                continue
            by_thread.setdefault(r.get("thread"), []).append(r)
        out = []
        for tid, msgs in by_thread.items():
            first = msgs[0]
            if tid in deleted or (lesson and first.get("lesson") != lesson):
                continue
            out.append({"thread": tid, "lesson": first.get("lesson"), "kind": first.get("kind"),
                        "mode": first.get("mode"), "topic": first.get("topic"), "anchor": first.get("anchor"),
                        "selection": first.get("selection"), "messages": msgs})
        return out

    def last_session(self, thread):
        sessions = [r["session"] for r in self.records() if r.get("thread") == thread and r.get("session")]
        return sessions[-1] if sessions else None

    def history(self, thread):
        lines = []
        for r in self.records():
            if r.get("thread") == thread and r.get("role") in ("user", "assistant"):
                who = "Learner" if r["role"] == "user" else "You answered"
                lines.append(f"{who}: {r.get('text', '')}")
        return "\n\n".join(lines)

    # Prompts

    def system_prompt(self):
        parts = [read_text(self.ws / "ask-prompt.md") or read_text(SKILL / "starter" / "ask-prompt.md")]
        for name in ("MISSION.md", "NOTES.md", "GLOSSARY.md"):
            text = read_text(self.ws / name)
            if text:
                parts.append(f"## The course's {name}\n\n{text}")
        if self.code:
            parts.append(f"The learner's code is in {self.code}. Read it only to check a claim, and cite path:line.")
        return "\n\n".join(p for p in parts if p)

    def user_prompt(self, q, follow_up):
        kind = q.get("kind")
        lines = []
        if follow_up:
            lines.append("This is a follow-up in the same thread.")
        else:
            lines.append(f"Lesson: {q.get('lesson_title', '')} ({q.get('lesson', '')})")
        lines.append(f"Task: {KIND_TASK[kind]}")
        if kind == "connect" and q.get("topic"):
            lines.append(f"Topic to connect to: {q['topic']}")
        para = q.get("para") or {}
        src = q.get("source")
        if src:
            lines.append(f'Highlighted lines {src.get("start")}-{src.get("end") or src.get("start")} '
                         f'of {src.get("path")}: "{q.get("selection") or ""}"')
        elif q.get("selection"):
            where = f" (in ¶{para['n']})" if para.get("n") else ""
            lines.append(f'Highlighted text{where}: "{q["selection"]}"')
        elif para.get("n") and not follow_up:
            lines.append(f"The learner was reading ¶{para['n']} when they asked.")
        if q.get("para_text") and not follow_up:
            lines.append(f"That paragraph: {q['para_text']}")
        if q.get("question"):
            lines.append(f"Question: {q['question']}")
        if kind == "check":
            lines.append(f"Learner's answer: {q.get('answer') or ''}")
            lines.append(f"Right answer: {q.get('model') or ''}")
        if q.get("lesson_text") and not follow_up:
            lines.append(f"The lesson, paragraph by paragraph:\n{q['lesson_text']}")
        return "\n\n".join(lines)

    def command(self, tier, session, resume):
        model, effort = TIERS[tier]
        deep_web = tier == "deep" and self.web
        cmd = [self.claude, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--model", model, "--effort", effort, "--permission-mode", "dontAsk", "--strict-mcp-config",
               "--append-system-prompt", self.system_prompt(),
               "--tools", *READ_TOOLS, *(["WebFetch"] if deep_web else [])]
        if deep_web:
            cmd += ["--allowedTools", *[f"WebFetch(domain:{d})" for d in self.web]]
        if self.code:
            cmd += ["--add-dir", str(self.code)]
        cmd += ["--resume", session] if resume else ["--session-id", session]
        return cmd

    def describe(self, tool):
        name, args = tool.get("name"), tool.get("input") or {}
        if name == "Read":
            return f"Reading {self.short(args.get('file_path', ''))}"
        if name == "Grep":
            return f'Searching for "{args.get("pattern", "")}"'
        if name == "Glob":
            return f"Looking for {args.get('pattern', '')}"
        if name == "WebFetch":
            return f"Fetching {args.get('url', '')}"
        return f"Using {name}"

    def short(self, path):
        p = Path(path)
        for root in (self.code, self.ws):
            if root and p.is_absolute():
                try:
                    return str(p.resolve().relative_to(root))
                except ValueError:
                    continue
        return path

    # Running Claude

    def run(self, cmd, prompt, send, gone):
        """Stream one Claude run through send(event, data). Returns a result dict, or None if the reader left."""
        started = time.time()
        proc = subprocess.Popen(cmd, cwd=self.ws, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        err = []
        with self.lock:
            self.live.add(proc)
        drain = threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True)
        drain.start()
        # Claude can be quiet for a while as it reads files, so check for a departed reader on a timer,
        # not only when the next send fails. A deleted card or closed tab then stops spending.
        threading.Thread(target=watch, args=(proc, gone), daemon=True).start()
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except BrokenPipeError:
            pass  # claude exited at once; its return code and stderr say why
        result = {"text": "", "model": None, "cost_usd": None, "ms_first_word": None}
        try:
            for line in proc.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                kind = ev.get("type")
                if kind == "system" and ev.get("subtype") == "init":
                    result["model"] = ev.get("model")
                elif kind == "assistant":
                    for block in (ev.get("message") or {}).get("content") or []:
                        if block.get("type") == "tool_use":
                            send("status", {"text": self.describe(block)})
                elif kind == "stream_event":
                    delta = (ev.get("event") or {}).get("delta") or {}
                    if delta.get("type") == "text_delta":
                        if result["ms_first_word"] is None:
                            result["ms_first_word"] = int((time.time() - started) * 1000)
                        result["text"] += delta["text"]
                        send("delta", {"text": delta["text"]})
                elif kind == "result":
                    result["cost_usd"] = ev.get("total_cost_usd")
                    if ev.get("is_error"):
                        result["error"] = str(ev.get("result") or "Claude reported an error")
        except OSError:
            stop(proc)
            return None
        finally:
            proc.stdout.close()
            with self.lock:
                self.live.discard(proc)
        proc.wait()
        drain.join(timeout=2)
        proc.stderr.close()
        if gone():
            return None
        result["returncode"] = proc.returncode
        result["stderr"] = "".join(err).strip()
        result["ms_total"] = int((time.time() - started) * 1000)
        return result

    def ask(self, q, send, gone=lambda: False):
        kind = q.get("kind")
        if not isinstance(q.get("source"), dict):
            q["source"] = None
        tier = "quick" if kind in ALWAYS_QUICK else (q.get("mode") if q.get("mode") in TIERS else "quick")
        thread = q.get("thread")
        session = self.last_session(thread) if thread else None
        follow_up = bool(thread)
        thread = thread or str(uuid.uuid4())
        send("thread", {"thread": thread})
        with self.lock:
            if thread in self.busy:
                send("error", {"message": "Still answering the last question in this card. Ask again when it finishes."})
                return
            self.busy.add(thread)
        try:
            self.answer(q, send, gone, kind, tier, thread, session, follow_up)
        finally:
            with self.lock:
                self.busy.discard(thread)

    def answer(self, q, send, gone, kind, tier, thread, session, follow_up):
        history = self.history(thread) if follow_up else ""
        prompt = self.user_prompt(q, follow_up)
        record = {"t": now(), "thread": thread, "lesson": q.get("lesson"), "kind": kind, "mode": tier,
                  "topic": q.get("topic"), "anchor": q.get("para"), "selection": q.get("selection"),
                  "source": q.get("source"), "role": "user",
                  "text": q.get("answer") or q.get("question") or KIND_TASK[kind]}
        if kind == "check":
            record["quiz"] = q.get("quiz")
        self.append(record)

        resumed = bool(session)
        session = session or str(uuid.uuid4())
        result = self.run(self.command(tier, session, resumed), prompt, send, gone)
        if result is None:
            return
        if resumed and result["returncode"] != 0 and not result["text"]:
            # The saved Claude session is gone; start a new one and hand it the thread so far.
            session = str(uuid.uuid4())
            prompt = f"The conversation so far:\n\n{history}\n\n{prompt}"
            result = self.run(self.command(tier, session, False), prompt, send, gone)
            if result is None:
                return
        if result["returncode"] != 0 or result.get("error"):
            send("error", {"message": result.get("error") or result["stderr"][-300:]
                           or f"claude exited {result['returncode']}"})
            return
        self.append({"t": now(), "thread": thread, "role": "assistant", "session": session,
                     "model": result["model"], "cost_usd": result["cost_usd"],
                     "ms_first_word": result["ms_first_word"], "text": result["text"]})
        send("done", {"thread": thread, "model": result["model"], "cost_usd": result["cost_usd"],
                      "ms_first_word": result["ms_first_word"], "ms_total": result["ms_total"]})

    def topics(self):
        index = read_text(self.ws / "index.html")
        syllabus = re.search(r'<ol class="syllabus">(.*?)</ol>', index, re.S)
        out = []
        for li in re.findall(r"<li[^>]*>(.*?)</li>", syllabus.group(1) if syllabus else "", re.S):
            href = re.search(r'href="([^"]+)"', li)
            tags = re.search(r'<span class="tag">(.*?)</span>', li, re.S)
            title = re.sub(r"<[^>]+>", "", re.split(r"<br\s*/?>", li)[0])
            out.append({"title": html.unescape(title).strip(), "href": href.group(1) if href else None,
                        "tags": html.unescape(tags.group(1)).strip() if tags else ""})
        return out

    # Source files and quiz results

    def source(self, path):
        """(status, body) for one file in the source folder. Every refusal is the same 404, so a reader
        cannot tell a hidden or ignored file that exists from one that does not."""
        if not self.code or not path:
            return 404, None
        try:
            real = (self.code / path).resolve()  # resolve first, so ".." and symlinks are judged by where they land
            rel = real.relative_to(self.code)
        except (OSError, RuntimeError, ValueError):  # a NUL byte, a symlink loop, or outside the folder
            return 404, None
        if not rel.parts or any(p.startswith(".") for p in rel.parts) or self.ignored(rel) or not real.is_file():
            return 404, None
        try:
            with real.open("rb") as f:
                raw = f.read(MAX_SOURCE + 1)
        except OSError:
            return 404, None
        if len(raw) > MAX_SOURCE:
            return 413, None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return 415, None
        if "\0" in text:
            return 415, None
        return 200, {"path": rel.as_posix(), "text": text}

    def ignored(self, rel):
        """True when git ignores rel. Ignored files are where secrets and build output live, so when the
        folder is in a git checkout (its own, or a parent's) and git cannot answer, every file counts as ignored."""
        if not any((d / ".git").exists() for d in (self.code, *self.code.parents)):
            return False
        if not self.git:
            return True
        try:
            done = subprocess.run([self.git, "-C", str(self.code), "check-ignore", "-q", "--", str(rel)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return True
        return done.returncode != 1  # 1 is "not ignored"; 0 is ignored and 128 is an error

    def review(self):
        """Questions the learner has missed and not yet got right three times running, due ones soonest first."""
        items = {}
        for r in self.records(self.quiz_log):
            key = (r.get("lesson"), r.get("quiz"))
            if not isinstance(r.get("right"), bool) or not all(isinstance(k, str) for k in key):
                continue  # null is a reveal with no self-mark yet, so it says nothing about memory
            item = items.setdefault(key, {"streak": 0, "missed": False})
            item.update(t=r.get("t"), q=r.get("q"))
            if r["right"]:
                item["streak"] += 1
            else:
                item.update(streak=0, missed=True)
        due, waiting, at_now = [], 0, datetime.now(timezone.utc)
        for (lesson, quiz), item in items.items():
            if not item["missed"] or item["streak"] >= len(REVIEW_DAYS):
                continue
            try:
                at = datetime.fromisoformat(item["t"]).astimezone() + timedelta(days=REVIEW_DAYS[item["streak"]])
            except (TypeError, ValueError):
                continue
            if at > at_now:
                waiting += 1
            else:
                due.append((at, {"lesson": lesson, "quiz": quiz, "q": item["q"], "href": f"{lesson}#{quiz}",
                                 "streak": item["streak"]}))
        due.sort(key=lambda d: d[0])
        return {"due": [d for _, d in due], "waiting": waiting}


def stop_all(course):
    with course.lock:
        procs = list(course.live)
    for proc in procs:
        stop(proc)


def watch(proc, gone):
    while proc.poll() is None:
        if gone():
            stop(proc)
            return
        time.sleep(0.3)


def stop(proc):
    # SIGTERM, not SIGINT: a process started in the background often has SIGINT ignored.
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except (subprocess.TimeoutExpired, OSError):
        proc.kill()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.course.ws), **kwargs)

    # Access checks: the server can make Claude read code, so only the reader may use it.

    def allowed(self):
        srv = self.server
        if srv.token:
            query = parse_qs(urlparse(self.path).query)
            if query.get("k", [None])[0] == srv.token:
                self.set_cookie = True
                return True
            cookies = dict(c.strip().split("=", 1) for c in (self.headers.get("Cookie") or "").split(";") if "=" in c)
            if cookies.get(COOKIE) == srv.token:
                return True
            self.send_error(401, "Open the link printed when the server started")
            return False
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("localhost", "127.0.0.1"):
            self.send_error(403, "Unknown host")
            return False
        return True

    def send_head(self):
        real = Path(self.translate_path(self.path)).resolve()
        if real != self.course.ws and self.course.ws not in real.parents:
            self.send_error(404, "Not in this course")
            return None
        return super().send_head()

    def end_headers(self):
        if getattr(self, "set_cookie", False):
            self.send_header("Set-Cookie", f"{COOKIE}={self.server.token}; Path=/; HttpOnly; SameSite=Strict")
        super().end_headers()

    def do_GET(self):
        if not self.allowed():
            return
        url = urlparse(self.path)
        course = self.course
        if url.path == "/api/ping":
            return self.json({"ok": True, "course": str(course.ws), "tiers": {k: v[0] for k, v in TIERS.items()},
                              "web": course.web, "code": str(course.code) if course.code else None,
                              "lan": bool(self.server.token)})
        if url.path == "/api/threads":
            lesson = parse_qs(url.query).get("lesson", [None])[0]
            return self.json({"threads": course.threads(lesson)})
        if url.path == "/api/topics":
            return self.json({"topics": course.topics()})
        if url.path == "/api/source":
            status, data = course.source(parse_qs(url.query).get("path", [""])[0])
            return self.json(data) if status == 200 else self.send_error(status)
        if url.path == "/api/review":
            return self.json(course.review())
        super().do_GET()

    def do_HEAD(self):
        if self.allowed():
            super().do_HEAD()

    def do_POST(self):
        if not self.allowed():
            return
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self.send_error(403, "Cross-site request refused")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self.send_error(415, "Send JSON")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self.send_error(413, "Too large")
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self.send_error(400, "Bad JSON")
        course = self.course
        path = urlparse(self.path).path
        if path == "/api/delete":
            course.append({"t": now(), "thread": body.get("thread"), "role": "meta", "event": "deleted"})
            return self.json({"ok": True})
        if path == "/api/quiz":
            if not all(isinstance(body.get(k), str) and body[k] for k in ("lesson", "quiz")):
                return self.send_error(400, "Needs lesson and quiz")
            right = body.get("right")
            course.append({"t": now(), "lesson": body["lesson"], "quiz": body["quiz"], "type": body.get("type"),
                           "q": body.get("q"), "right": right if isinstance(right, bool) else None}, course.quiz_log)
            return self.json({"ok": True})
        if path != "/api/ask":
            return self.send_error(404)
        if body.get("kind") not in KIND_TASK:
            return self.send_error(400, "Unknown kind")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def send(event, data):
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()

        try:
            course.ask(body, send, self.reader_gone)
        except OSError:
            pass

    def reader_gone(self):
        """True once the browser has closed the connection (it sends nothing after its request)."""
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
        except OSError:
            return True

    def json(self, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")  # source files and review state must never sit in a cache
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        if not self.server.quiet:
            sys.stderr.write(f"{self.log_date_time_string()} {fmt % args}\n")


class CourseServer(ThreadingHTTPServer):
    def server_close(self):
        stop_all(self.course)
        super().server_close()


def make_server(ws, port=8765, lan=False, code=None, claude=None, web=(), quiet=True):
    course = Course(ws, code, claude or shutil.which("claude"), web)
    handler = type("CourseHandler", (Handler,), {"course": course})
    server = CourseServer(("0.0.0.0" if lan else "127.0.0.1", port), handler)
    server.course = course
    server.daemon_threads = True
    server.token = secrets.token_urlsafe(16) if lan else None
    server.quiet = quiet
    return server


def lan_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # no packet is sent; this only picks the outgoing interface
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main():
    ap = argparse.ArgumentParser(description="Serve a visual-teach course with live Claude answers.")
    ap.add_argument("workspace")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--code", help="folder answers may read, read-only")
    ap.add_argument("--web", action="append", default=[], help="domain Deep answers may fetch (repeatable)")
    ap.add_argument("--lan", action="store_true", help="listen on the network for a phone")
    args = ap.parse_args()
    if not shutil.which("claude"):
        sys.exit("claude is not on PATH. Start this from the shell you use Claude Code in.")
    server = make_server(args.workspace, args.port, args.lan, args.code, None, args.web, quiet=False)
    ws = server.course.ws
    run = {"pid": os.getpid(), "port": args.port, "url": f"http://localhost:{args.port}/"}
    if args.lan:
        run["phone_url"] = f"http://{lan_address()}:{args.port}/?k={server.token}"
    run_file = ws / ".serve.json"  # read by open_course.py; holds the phone token, so only this user may read it
    run_file.write_text(json.dumps(run))
    run_file.chmod(0o600)
    print(f"Course: {ws}")
    print(f"On this Mac: {run['url']}")
    if args.lan:
        print(f"On your phone (same network): {run['phone_url']}")
    print("Stop with Ctrl-C.")
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            if json.loads(run_file.read_text()).get("pid") == os.getpid():
                run_file.unlink()
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    main()
