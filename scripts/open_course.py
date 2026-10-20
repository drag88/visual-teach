"""Start or reuse a course's reading server, then open a page of the course in the browser.

Usage: python3 open_course.py <workspace> [page] [--code DIR] [--web DOMAIN ...] [--lan] [--port N]
                                                 [--no-open] [--stop]

Settings given once (--code, --web, --lan, --port) are saved in <workspace>/course.json, so later
sessions only need `open_course.py <workspace>`. The server runs on its own, so it keeps going after
the session that started it ends; --stop ends it. Run this from the shell you use Claude Code in, so
answers use your Claude login and network settings.

Each open also brings the course's shared files up to date, and restarts a server that runs older code
or another copy of the skill, unless it is in the middle of a teaching job.
"""

import argparse
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import sync_course  # the scripts folder is on the path when this runs

HERE = Path(__file__).resolve().parent
DEFAULT_PORT = 8765

WINDOWS = os.name == "nt"


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def token_of(run):
    """The phone link's token from a .serve.json record. A server on the network wants it on every request."""
    return run.get("phone_url", "").partition("?k=")[2] or None


def api(port, path, token=None):
    url = f"http://localhost:{port}{path}" + (f"?k={token}" if token else "")
    try:
        with urllib.request.urlopen(url, timeout=1) as r:
            return json.loads(r.read())
    except (OSError, ValueError):  # URLError is an OSError
        return None


def ping(port, token=None):
    return api(port, "/api/ping", token)


def teaching(port, token=None):
    """True while the server runs a teaching job, which stopping it would end; False when it runs none; None when
    the server does not say."""
    url = f"http://localhost:{port}/api/teach" + (f"?k={token}" if token else "")
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            info = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return False if exc.code == 404 else None  # 404: a server from before teaching from the page existed
    except (OSError, ValueError):
        return None
    job = info.get("job") if isinstance(info, dict) else None
    return isinstance(job, dict) and job.get("state") == "running"


def port_free(port):
    with socket.socket() as s:
        # Same reuse rule as the server, so connections still closing from the last run do not move the course
        # to a new port (and lose what the browser saved for the old address, such as the theme).
        if not WINDOWS:  # there, reuse would let it bind a port another program holds
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def alive(pid):
    """True while the process runs. Not os.kill(pid, 0): on Windows that ends the process instead of checking it."""
    if WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True).stdout or ""
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def request_shutdown(port, token=None, if_idle=False):
    """True once the server agrees to stop, "busy" when if_idle and a teaching job is running, else False."""
    url = f"http://localhost:{port}/api/shutdown" + (f"?k={token}" if token else "")
    body = json.dumps({"if_idle": if_idle}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except urllib.error.HTTPError as exc:
        return "busy" if exc.code == 409 else False
    except OSError:
        return False


def stop(ws, if_idle=False):
    """True once stopped, False when nothing answers as this course's server, None while it is still stopping,
    and "busy" when if_idle and the server is running a teaching job (then nothing is ended)."""
    run = read_json(ws / ".serve.json")
    pid, port = run.get("pid"), run.get("port")
    token = token_of(run)
    info = ping(port, token) if pid and port else None
    # A server from before ping named its process gives no pid; one answering as this course is still real.
    if not info or info.get("course") != str(Path(ws).resolve()) or info.get("pid", pid) != pid:
        # Nothing answers as this course's server: the record is stale (a crash or a reboot), and its process
        # number may now belong to something else, so nothing is ended.
        (ws / ".serve.json").unlink(missing_ok=True)
        return False
    answer = request_shutdown(port, token, if_idle)  # a clean stop ends its Claude runs and tidies up
    if answer == "busy":
        return "busy"
    if not answer:
        if WINDOWS:  # no SIGTERM handling there: taskkill /T ends the server and what it started
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, text=True)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    for _ in range(50):
        if not alive(pid):
            (ws / ".serve.json").unlink(missing_ok=True)
            return True
        time.sleep(0.1)
    return None  # still running: keep the record so a later --stop can find it


def start(ws, cfg, stale_pid=None):
    # -X utf8: the server prints the course path, which a Windows console encoding may not hold.
    cmd = [sys.executable, "-X", "utf8", str(HERE / "serve.py"), str(ws), "--port", str(cfg["port"])]
    if cfg.get("code"):
        cmd += ["--code", cfg["code"]]
    for domain in cfg.get("web", []):
        cmd += ["--web", domain]
    if cfg.get("lan"):
        cmd.append("--lan")
    # Detached from this terminal, so the server keeps running after it closes.
    detach = ({"creationflags": getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)}
              if WINDOWS else {"start_new_session": True})
    with (ws / ".serve.log").open("a", encoding="utf-8") as log:
        subprocess.Popen(cmd, cwd=ws, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **detach)
    for _ in range(150):
        token = token_of(read_json(ws / ".serve.json"))
        info = ping(cfg["port"], token)
        # Not the old server answering while it shuts down. (Not the new process's pid either: on Windows a
        # venv's python.exe starts the real interpreter as a child, so the server's pid is not Popen's.)
        if info and info.get("course") == str(ws) and info.get("pid") not in (None, stale_pid):
            return True
        time.sleep(0.1)
    return False


def wanted(info, cfg):
    """True when the running server has the settings this course asks for and runs this copy of the skill's code.
    A plugin update installs into a new folder and later deletes the old one, so the folder must match too."""
    return (info.get("code") == cfg.get("code") and info.get("web") == cfg.get("web", [])
            and info.get("lan") == bool(cfg.get("lan"))
            and info.get("version") == sync_course.code_version() and info.get("skill") == str(HERE.parent))


def refresh(ws):
    """Bring the course's shared files up to date with this copy of the skill."""
    try:
        changed, _ = sync_course.sync(ws)
    except (OSError, ValueError) as exc:
        print(f"Could not update the course's shared files: {exc}")
        return
    if changed:
        print("Updated the course's shared files:", ", ".join(changed))


def main():
    ap = argparse.ArgumentParser(description="Start or reuse a course's reading server and open a page.")
    ap.add_argument("workspace")
    ap.add_argument("page", nargs="?", default="", help="page to open, e.g. lessons/0002-x.html")
    ap.add_argument("--code", help="folder answers may read, read-only")
    ap.add_argument("--web", action="append", help="domain Deep answers may fetch (repeatable)")
    ap.add_argument("--lan", action="store_true", default=None, help="also listen on the network for a phone")
    ap.add_argument("--port", type=int)
    ap.add_argument("--no-open", action="store_true", help="print the link without opening a browser")
    ap.add_argument("--stop", action="store_true", help="stop this course's server")
    args = ap.parse_args()

    ws = Path(args.workspace).expanduser().resolve()
    if not (ws / "index.html").exists() and not (ws / "lessons").is_dir():
        sys.exit(f"{ws} does not look like a visual-teach course (no index.html or lessons/).")
    if args.stop:
        print({True: "Stopped.", False: "No server was running for this course.",
               None: "The server has not stopped yet. Run --stop again in a moment."}[stop(ws)])
        return

    cfg = read_json(ws / "course.json")
    if args.code:
        cfg["code"] = str(Path(args.code).expanduser().resolve())
    if args.web:
        cfg["web"] = args.web
    if args.lan is not None:
        cfg["lan"] = True
    cfg["port"] = args.port or cfg.get("port") or DEFAULT_PORT

    run = read_json(ws / ".serve.json")
    token = token_of(run)
    info = ping(cfg["port"], token)
    ours = bool(info) and info.get("course") == str(ws)
    restart = waiting = False
    if ours and not wanted(info, cfg):
        # Same course, new settings or code: restart it, but never during a teaching job, which a restart would end.
        # A server that cannot say keeps running, and so do the course's files, which its own check compares against.
        # The server itself refuses if a job started after this check.
        stopped = stop(ws, if_idle=True) if teaching(cfg["port"], token) is False else "busy"
        if stopped is None:
            sys.exit("The course server has not stopped yet. Run this again in a moment.")
        waiting, restart = stopped == "busy", stopped != "busy"
    if waiting:
        print("Reusing the course server for now: it may be running a teaching job, which a restart would stop.\n"
              "Open the course again after it finishes to use the new settings or the updated skill.")
    elif ours and not restart:
        refresh(ws)
        print("Reusing the course server that is already running.")
    else:
        refresh(ws)
        if not restart and not port_free(cfg["port"]):
            cfg["port"] = next(p for p in range(cfg["port"] + 1, cfg["port"] + 100) if port_free(p))
        if not start(ws, cfg, info.get("pid") if restart else None):
            tail = (ws / ".serve.log").read_text(encoding="utf-8", errors="replace")[-1500:] if (ws / ".serve.log").exists() else ""
            sys.exit(f"The course server did not start. Last lines of {ws / '.serve.log'}:\n{tail}")
        print("Started the course server.")
    (ws / "course.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    # With --lan the server wants its token from this computer too, and each start makes a new one.
    page, _, fragment = args.page.lstrip("/").partition("#")
    token = token_of(read_json(ws / ".serve.json"))
    url = (f"http://localhost:{cfg['port']}/{page}" + (f"?k={token}" if token else "")
           + (f"#{fragment}" if fragment else ""))
    print(f"Open: {url}")
    phone = read_json(ws / ".serve.json").get("phone_url")
    if phone:
        print(f"On your phone (same Wi-Fi): {phone}")
    print(f"Stop it with: {sys.executable} {Path(__file__).resolve()} {ws} --stop")
    if not args.no_open:
        if platform.system() == "Darwin":
            subprocess.run(["open", url], check=False)
        else:
            webbrowser.open(url)


if __name__ == "__main__":
    main()
