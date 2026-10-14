"""Start or reuse a course's reading server, then open a page of the course in the browser.

Usage: python3 open_course.py <workspace> [page] [--code DIR] [--web DOMAIN ...] [--lan] [--port N]
                                                 [--no-open] [--stop]

Settings given once (--code, --web, --lan, --port) are saved in <workspace>/course.json, so later
sessions only need `open_course.py <workspace>`. The server runs on its own, so it keeps going after
the session that started it ends; --stop ends it. Run this from the shell you use Claude Code in, so
answers use your Claude login and network settings.
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

HERE = Path(__file__).resolve().parent
DEFAULT_PORT = 8765


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def ping(port, token=None):
    url = f"http://localhost:{port}/api/ping" + (f"?k={token}" if token else "")
    try:
        with urllib.request.urlopen(url, timeout=1) as r:
            return json.loads(r.read())
    except (OSError, ValueError, urllib.error.URLError):
        return None


def port_free(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def stop(ws):
    run = read_json(ws / ".serve.json")
    pid = run.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        (ws / ".serve.json").unlink(missing_ok=True)
        return False
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return True


def start(ws, cfg):
    cmd = [sys.executable, str(HERE / "serve.py"), str(ws), "--port", str(cfg["port"])]
    if cfg.get("code"):
        cmd += ["--code", cfg["code"]]
    for domain in cfg.get("web", []):
        cmd += ["--web", domain]
    if cfg.get("lan"):
        cmd.append("--lan")
    with (ws / ".serve.log").open("a") as log:
        subprocess.Popen(cmd, cwd=ws, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)  # its own session, so it outlives this one
    for _ in range(150):
        token = read_json(ws / ".serve.json").get("phone_url", "").partition("?k=")[2] or None
        info = ping(cfg["port"], token)
        if info and info.get("course") == str(ws):
            return True
        time.sleep(0.1)
    return False


def wanted(info, cfg):
    """True when the running server already has the settings this course asks for."""
    return (info.get("code") == cfg.get("code") and info.get("web") == cfg.get("web", [])
            and info.get("lan") == bool(cfg.get("lan")))


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
        print("Stopped." if stop(ws) else "No server was running for this course.")
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
    token = run.get("phone_url", "").partition("?k=")[2] or None
    info = ping(cfg["port"], token)
    if info and info.get("course") == str(ws) and wanted(info, cfg):
        print("Reusing the course server that is already running.")
    else:
        if info and info.get("course") == str(ws):
            stop(ws)  # same course, new settings: restart it
        elif not port_free(cfg["port"]):
            cfg["port"] = next(p for p in range(cfg["port"] + 1, cfg["port"] + 100) if port_free(p))
        if not start(ws, cfg):
            tail = (ws / ".serve.log").read_text()[-1500:] if (ws / ".serve.log").exists() else ""
            sys.exit(f"The course server did not start. Last lines of {ws / '.serve.log'}:\n{tail}")
        print("Started the course server.")
    (ws / "course.json").write_text(json.dumps(cfg, indent=2) + "\n")

    url = f"http://localhost:{cfg['port']}/{args.page.lstrip('/')}"
    print(f"Open: {url}")
    phone = read_json(ws / ".serve.json").get("phone_url")
    if phone:
        print(f"On your phone (same Wi-Fi): {phone}")
    print(f"Stop it with: python3 {Path(__file__).resolve()} {ws} --stop")
    if not args.no_open:
        if platform.system() == "Darwin":
            subprocess.run(["open", url], check=False)
        else:
            webbrowser.open(url)


if __name__ == "__main__":
    main()
