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
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePath
from urllib.parse import parse_qs, urlparse

import sync_course  # the scripts folder is on the path when serve.py runs

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
DATA_RULE = ("Quote code and prose, never data. If a file holds records, query results, logs or anything about real "
             "people or customers (names, contact details, IDs, account numbers), describe its shape in words instead "
             "of repeating any of it.")
# Teaching sessions started from the course page. Each runs Claude with edit rights inside the course folder only.
TEACH_TASKS = {
    "next": "Write the next lesson in the syllabus (index.html shows which one is next), then update index.html, "
            "the reference sheets and reference/carry-over.html to match.",
    "update": "Work through the questions and quiz results not yet handled (section 6, Use the questions): rewrite "
              "the passages they point to, write learning records, update NOTES.md, and mark each thread handled. "
              "Do not write a new lesson.",
    "fix": "The course check failed with the problems below. Fix them in the course files.",
}
TEACH_ACTIONS = (*TEACH_TASKS, "refresh")
MAX_BODY = 1_000_000
MAX_SOURCE = 512_000
REVIEW_DAYS = (1, 3, 7)  # wait after a miss, by rights in a row since it; the third right retires the question
COOKIE = "vt_k"
WINDOWS = os.name == "nt"
VERSION = sync_course.code_version()  # taken at start, so a server running older code can tell


def rule_path(path):
    """A path the way Claude Code permission rules want it: "//" then the absolute path in POSIX form, a Windows
    drive included (C:\\Users\\me becomes //c/Users/me), with glob characters escaped so it matches only itself."""
    p = path if isinstance(path, PurePath) else PurePath(path)
    posix = f"/{p.drive[0].lower()}/" + "/".join(p.parts[1:]) if p.drive else p.as_posix()
    return "/" + re.sub(r"([\\*?\[\]])", r"\\\1", posix)


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def failure(result):
    """What went wrong with a finished Claude run, in words for the page, or None when it went fine."""
    if result.get("error"):
        return result["error"]
    if result["returncode"] == 0:
        return None
    if result["returncode"] < 0:  # ended by a signal: a stop from the page, or the server stopping
        return "It was stopped before it finished."
    return result["stderr"][-300:] or f"claude exited {result['returncode']}"


def read_dict(path):
    """A file's JSON object, or {} when the file is missing, broken or holds something else."""
    try:
        data = json.loads(read_text(path) or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


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
        self.job = None  # the latest teaching job started from the course page
        self.closing = False  # set once a shutdown is accepted, so no teaching job starts after it
        self.user_settings = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"
        # Long or structured arguments go in files here, never on the command line, which Windows can mangle.
        self.tmp = Path(tempfile.mkdtemp(prefix="visual-teach-"))

    # Question log

    def append(self, record, log=None):
        with self.lock, (log or self.log).open("a", encoding="utf-8") as f:
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
            if tid in deleted or (lesson is not None and first.get("lesson") != lesson):
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
        parts.append(DATA_RULE)  # after any course prompt file, so none can drop it
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

    def arg_file(self, name, text):
        path = self.tmp / f"{name}-{uuid.uuid4().hex}"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def forget_files(self, cmd):
        for arg in cmd:
            if arg.startswith(str(self.tmp)):
                Path(arg).unlink(missing_ok=True)

    def claude_env(self):
        """The environment for a Claude run. --restricted skips the learner's settings files, hooks and plugins
        included, so the one part they rely on to run at all (the env block: proxy certificates, say) is passed on.
        A variable already set in the shell wins."""
        env = dict(os.environ)
        extra = read_dict(self.user_settings).get("env")
        for key, value in (extra if isinstance(extra, dict) else {}).items():
            if isinstance(key, str) and isinstance(value, str):
                env.setdefault(key, value)
        return env

    def claude_args(self, tier):
        """The start of every Claude run, answers and teaching alike, so both stay isolated the same way."""
        model, effort = TIERS[tier]
        return [self.claude, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
                "--model", model, "--effort", effort, "--permission-mode", "dontAsk", "--strict-mcp-config",
                "--restricted"]

    def command(self, tier, session, resume):
        deep_web = tier == "deep" and self.web
        cmd = [*self.claude_args(tier), "--append-system-prompt-file", self.arg_file("system", self.system_prompt()),
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
        if name in ("Edit", "Write"):
            return f"{'Editing' if name == 'Edit' else 'Writing'} {self.short(args.get('file_path', ''))}"
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
        try:
            proc = subprocess.Popen(cmd, cwd=self.ws, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                    env=self.claude_env(), start_new_session=True)
        except OSError as exc:
            self.forget_files(cmd)
            return {"text": "", "model": None, "cost_usd": None, "ms_first_word": None, "returncode": 127,
                    "stderr": "", "error": f"Could not start claude: {exc}", "ms_total": 0}
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
            self.forget_files(cmd)
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
        message = failure(result)
        if message:
            send("error", {"message": message})
            return
        self.append({"t": now(), "thread": thread, "role": "assistant", "session": session,
                     "model": result["model"], "cost_usd": result["cost_usd"],
                     "ms_first_word": result["ms_first_word"], "text": result["text"]})
        send("done", {"thread": thread, "model": result["model"], "cost_usd": result["cost_usd"],
                      "ms_first_word": result["ms_first_word"], "ms_total": result["ms_total"]})

    # Teaching from the course page

    def settings(self):
        return read_dict(self.ws / "course.json")

    def teach_command(self):
        ws = rule_path(self.ws)
        # Exec form (command plus args): no shell, so a path with spaces or backslashes reaches Python intact.
        guard = {"type": "command", "command": sys.executable, "onFailure": "block",  # fail closed, not open
                 "args": ["-I", str(SKILL / "scripts" / "teach_guard.py"), str(self.ws)]}
        settings = {"hooks": {"PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit", "hooks": [guard]}]}}
        # --restricted loads only what is passed here, so the learner's own allow rules cannot widen these.
        # Claude Code checks writes against Edit rules and ignores Write(path) rules, so only Edit rules are given.
        # course.json is out of reach because the server runs its refresh command in a shell.
        cmd = [*self.claude_args("deep"), "--settings", self.arg_file("settings", json.dumps(settings)),
               "--tools", *READ_TOOLS, "Edit", "Write", *(["WebFetch"] if self.web else []),
               "--allowedTools", f"Edit({ws}/**)", *[f"WebFetch(domain:{d})" for d in self.web],
               "--disallowedTools", *[f"Edit({ws}/{f})" for f in
                                      ("course.json", ".serve.json", "assets/*.js", ".claude/**", "CLAUDE.md", "AGENTS.md")],
               "--add-dir", str(SKILL)]
        if self.code:
            cmd += ["--add-dir", str(self.code)]
        return cmd

    def teach_prompt(self, action, problems):
        lines = [
            f"Run one visual-teach teaching session for the course in {self.ws}, started from the course page.",
            f"Read {SKILL / 'SKILL.md'} and follow it, with these differences:",
            "- The server has already synced the course's shared files, and it runs the course check after you finish.",
            "- You have no shell: run no script and take no screenshots. Read and edit files only.",
            "- Edit only files inside the course folder. To mark a question thread handled, add its meta line "
            "after the last line of questions.jsonl.",
            "- You cannot search the web" + (f"; you can fetch pages only from {', '.join(self.web)}" if self.web else "")
            + ". Where a lesson needs a fact you cannot check in the course, the skill or the source folder, leave it "
            "out or mark it unchecked, and say so in your closing lines rather than writing it from memory.",
            f"Task: {TEACH_TASKS[action]}",
        ]
        if problems:
            lines.append(f"The course check said:\n{problems}")
        lines.append("End with at most five short lines saying what you changed.")
        return "\n".join(lines)

    def call(self, cmd, job, cwd, shell=False, timeout=900):
        proc = subprocess.Popen(cmd, cwd=cwd, shell=shell, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                start_new_session=True)
        with self.lock:
            self.live.add(proc)
        threading.Thread(target=watch, args=(proc, lambda: job["stopped"]), daemon=True).start()
        try:
            output, _ = proc.communicate(timeout=timeout)
            return proc.returncode, output
        finally:
            stop(proc)
            proc.stdout.close()
            with self.lock:
                self.live.discard(proc)

    def checkers(self):
        return [[sys.executable, "-I", "-X", "utf8"],
                ["uv", "run", "--no-project", "--no-config", "--quiet", "--with", "playwright", "python", "-I", "-X", "utf8"]]

    def check(self, job):
        """(ok, report) from check_lessons.py; ok is None when no Python with Playwright can be found."""
        script = str(SKILL / "scripts" / "check_lessons.py")
        for py in self.checkers():
            if job["stopped"]:
                break
            if not shutil.which(py[0]):
                continue
            code, _ = self.call([*py, "-c", "import playwright"], job, cwd=SKILL)
            if job["stopped"]:
                break
            if code:
                continue
            code, output = self.call([*py, script, str(self.ws)], job, cwd=SKILL)
            return code == 0, output.strip()[-3000:]
        return None, "Checks skipped: no Python with Playwright was found."

    def start_job(self, action):
        """Start a teaching job in the background. Returns an HTTP status and the job."""
        if not (SKILL / "SKILL.md").is_file():
            # A plugin update moved the skill and its old folder was deleted: no guard script, method or check.
            return 409, "The skill was updated since this server started. Open the course again, then try again."
        refresh = self.settings().get("refresh")
        with self.lock:
            if self.closing:
                return 409, "The server is restarting. Try again in a moment."
            last = self.job
            if last and last["state"] == "running":
                return 409, "A teaching job is already running."
            problems = (last or {}).get("check") or {}
            if action == "fix" and problems.get("ok") is not False:
                return 409, "The last check found nothing to fix."
            if action == "refresh" and not isinstance(refresh, str):
                return 404, "This course has no refresh command in course.json."
            job = {"action": action, "state": "running", "started": now(), "lines": [], "summary": "",
                   "check": None, "cost_usd": None, "error": None, "stopped": False}
            self.job = job
        target = self.refresh_job if action == "refresh" else self.teach_job
        threading.Thread(target=target, args=(job, refresh if action == "refresh" else problems.get("text")),
                         daemon=True).start()
        return 200, job

    def teach_job(self, job, problems):
        def send(event, data):
            if event == "status":
                job["lines"] = (job["lines"] + [data["text"]])[-50:]
                job["summary"] = ""  # keep only the words after the last step: the closing summary
            elif event == "delta":
                job["summary"] += data["text"]

        try:
            if job["stopped"]:
                return
            sync_course.sync(self.ws)
            if job["stopped"]:
                return
            result = self.run(self.teach_command(), self.teach_prompt(job["action"], problems), send,
                              lambda: job["stopped"])
            if job["stopped"] or result is None:
                job["state"] = "stopped"
                return
            job["cost_usd"] = result["cost_usd"]
            job["error"] = failure(result)
            if job["error"]:
                job["state"] = "failed"
                return
            job["lines"].append("Checking the course")
            ok, report = self.check(job)
            job["check"] = {"ok": ok, "text": report}
            job["state"] = "stopped" if job["stopped"] else "done"
        except Exception as exc:  # a job that dies must still say so on the page
            job["error"], job["state"] = str(exc), "failed"
        finally:
            if job["stopped"]:
                job["state"] = "stopped"

    def refresh_job(self, job, command):
        try:
            if job["stopped"]:
                return
            code, output = self.call(command, job, shell=True, cwd=Path.home())
            job["lines"] = output.strip().splitlines()[-20:]
            job["state"] = "stopped" if job["stopped"] else ("done" if code == 0 else "failed")
            if code:
                job["error"] = f"The refresh command exited {code}"
        except (OSError, subprocess.TimeoutExpired) as exc:
            job["error"], job["state"] = str(exc), "failed"
        finally:
            if job["stopped"]:
                job["state"] = "stopped"

    def job_view(self):
        job = self.job
        return {k: v for k, v in job.items() if k != "stopped"} if job else None

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
    """End a process and everything it started. On Mac and Linux each run has its own process group; Windows has
    none, so taskkill /T ends the tree from the process down."""
    if WINDOWS:
        if proc.poll() is None:  # an exited process's PID may already belong to something else
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            finally:
                # A child can outlive its parent or ignore SIGTERM.
                os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


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
        self.course_html = real.is_file() and real.suffix.lower() == ".html" or (
            real.is_dir() and urlparse(self.path).path.endswith("/"))
        return super().send_head()

    def end_headers(self):
        if getattr(self, "course_html", False):
            host = self.headers.get("Host")
            scripts = " ".join(f"http://{host}/assets/{name}.js" for name in ("theme", "quiz", "ask"))
            self.send_header("Content-Security-Policy", f"script-src {scripts}; object-src 'none'; base-uri 'none'")
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
                              "lan": bool(self.server.token), "pid": os.getpid(), "version": VERSION,
                              "skill": str(SKILL)})
        if url.path == "/api/threads":
            # keep_blank_values: the course home page is the lesson "", not a request for every lesson
            lesson = parse_qs(url.query, keep_blank_values=True).get("lesson", [None])[0]
            return self.json({"threads": course.threads(lesson)})
        if url.path == "/api/topics":
            return self.json({"topics": course.topics()})
        if url.path == "/api/source":
            status, data = course.source(parse_qs(url.query).get("path", [""])[0])
            return self.json(data) if status == 200 else self.send_error(status)
        if url.path == "/api/review":
            return self.json(course.review())
        if url.path == "/api/teach":
            return self.json({"allowed": self.local(), "refresh": isinstance(course.settings().get("refresh"), str),
                              "job": course.job_view()})
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
        if path == "/api/shutdown":
            if not self.local():
                return self.send_error(403, "Only from this computer")
            # if_idle is how open_course.py restarts for an update: checked and settled under the lock that starting
            # a job takes, so a job begun a moment after the opener looked is never ended by it.
            with course.lock:
                busy = bool(body.get("if_idle")) and bool(course.job) and course.job["state"] == "running"
                course.closing = course.closing or not busy
            if busy:
                return self.json({"error": "A teaching job is running."}, 409)
            try:
                self.json({"ok": True})
            finally:
                # Stop even if the reply never arrives: closing is already set, so a server left running would refuse
                # teaching for good. A clean stop ends the Claude runs and removes the temporary files.
                threading.Thread(target=lambda: (self.server.shutdown(), self.server.server_close()), daemon=True).start()
            return
        if path in ("/api/teach", "/api/teach/stop"):
            if not self.local():
                return self.send_error(403, "Teaching runs only from this computer")
            if path == "/api/teach/stop":
                if course.job:
                    course.job["stopped"] = True
                return self.json({"ok": True})
            if body.get("action") not in TEACH_ACTIONS:
                return self.send_error(400, "Unknown action")
            status, job = course.start_job(body["action"])
            # A refusal carries its reason as JSON, so the page can say why instead of showing a status number.
            return self.json({"job": course.job_view()} if status == 200 else {"error": job}, status)
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

    def local(self):
        """True for a request from this computer. Teaching edits files and costs money, so the phone link can't."""
        try:
            host = urlparse("//" + (self.headers.get("Host") or "")).hostname
        except ValueError:
            return False
        return self.client_address[0] in ("127.0.0.1", "::1") and host in ("localhost", "127.0.0.1", "::1")

    def reader_gone(self):
        """True once the browser has closed the connection (it sends nothing after its request)."""
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
        except OSError:
            return True

    def json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")  # source files and review state must never sit in a cache
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        if not self.server.quiet:
            sys.stderr.write(f"{self.log_date_time_string()} {fmt % args}\n")


class CourseServer(ThreadingHTTPServer):
    allow_reuse_address = not WINDOWS  # on Windows reuse would let another program share the port

    def server_bind(self):
        if WINDOWS and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def server_close(self):
        stop_all(self.course)
        shutil.rmtree(self.course.tmp, ignore_errors=True)
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
    run_file.write_text(json.dumps(run), encoding="utf-8")
    run_file.chmod(0o600)
    print(f"Course: {ws}")
    print(f"On this computer: {run['url']}")
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
            if json.loads(run_file.read_text(encoding="utf-8")).get("pid") == os.getpid():
                run_file.unlink()
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    main()
