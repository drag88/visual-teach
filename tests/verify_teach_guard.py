"""Bounded exhaustive check of the teaching edit guard (skills/visual-teach/scripts/teach_guard.py).

Property: an edit the guard allows never changes a protected course file or any file outside the course.
Protected: course.json, .serve.json, CLAUDE.md, AGENTS.md, everything under .claude/, and every file under assets/
except assets/course.css.

How: build a real course folder (with symlinks planted inside it), then call the real guard on every edit path made
of up to DEPTH segments from SEGMENTS, in each FORM. Each allowed edit is then actually performed (parents created,
bytes appended, as Claude's Write and Edit do), and the check compares every protected and outside file before and
after. It judges by the effect on disk, not by re-deriving the guard's rules, so a wrong rule shows up as harm.

Usage: python3 tests/verify_teach_guard.py [--depth N]   (exit 0: holds within the bound; 1: counterexample printed)
"""

import argparse
import contextlib
import io
import itertools
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "skills" / "visual-teach" / "scripts" / "teach_guard.py"


def load_guard():
    """The guard's main(), compiled from the file as it is now. Not imported: a cached .pyc can outlive an edit
    made in the same second at the same size, and then the check would test old code."""
    namespace = {"__name__": "teach_guard"}
    exec(compile(GUARD.read_text(encoding="utf-8"), str(GUARD), "exec"), namespace)
    return namespace["main"]

# Path pieces an edit could use: protected names in two casings, the protected folders, ordinary course files,
# traversal, and the planted links. Each piece is a reason a guard could go wrong.
SEGMENTS = ["..", ".", "course.json", "Course.JSON", ".serve.json", "CLAUDE.md", "claude.md", "AGENTS.md",
            ".claude", ".Claude", "settings.json", "assets", "ASSETS", "course.css", "style.css", "ask.js",
            "lessons", "x.html", "outside", "link_out", "link_cfg", "link_assets", "link_dotclaude", "notes.md"]
DEPTH = 3
# How the path reaches the guard: absolute from the course, relative to the course (Claude's cwd), relative to a
# lesson folder, and absolute from the course's parent folder.
FORMS = ("abs-course", "rel-course", "rel-lessons", "abs-parent")


def build(base):
    """A course in base/course with protected files, allowed files and planted links, plus files outside it."""
    course, outside = base / "course", base / "outside"
    for d in (course / "lessons", course / "assets", course / ".claude", outside):
        d.mkdir(parents=True)
    for rel in ("course.json", ".serve.json", "CLAUDE.md", "AGENTS.md", ".claude/settings.json", "assets/style.css",
                "assets/ask.js", "assets/course.css", "lessons/x.html", "index.html", "NOTES.md"):
        (course / rel).write_text(f"original {rel}\n", encoding="utf-8")
    (outside / "secret.txt").write_text("outside\n", encoding="utf-8")
    (base / "sibling.txt").write_text("sibling\n", encoding="utf-8")
    # Relative links, so a copy of this folder links within the copy.
    os.symlink("../outside", course / "link_out", target_is_directory=True)  # a folder that leads out of the course
    os.symlink("course.json", course / "link_cfg")  # a file link onto a protected file
    os.symlink("assets", course / "link_assets", target_is_directory=True)
    os.symlink(".claude", course / "link_dotclaude", target_is_directory=True)
    os.symlink("../..", course / "lessons" / "link_up", target_is_directory=True)
    return course


def harmed(course, path):
    """True when a changed entry is a protected course file or lies outside the course, judged by where it really
    is on disk (links resolved), not by the name the edit used."""
    real = Path(os.path.realpath(path))
    root = course.resolve()
    if root not in real.parents:
        return True
    rel = real.relative_to(root).parts
    return (rel[0] == ".claude" or rel in (("course.json",), (".serve.json",), ("CLAUDE.md",), ("AGENTS.md",))
            or (rel[0] == "assets" and rel != ("assets", "course.css")))


def ask_guard(course, event, guard):
    """The guard's verdict (True = allowed) on one hook event, run in-process as the hook would run it."""
    stdin = io.TextIOWrapper(io.BytesIO(json.dumps(event).encode("utf-8")), encoding="utf-8")
    old = sys.argv, sys.stdin
    sys.argv, sys.stdin = ["teach_guard.py", str(course)], stdin
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return guard() == 0
    finally:
        sys.argv, sys.stdin = old


def tree(base):
    """Every entry under base, links not followed, with the size of each regular file."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(base):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            out[p] = None if os.path.islink(p) or os.path.isdir(p) else os.path.getsize(p)
    return out


def edit(path, base, before):
    """Do what an allowed Write or Edit does: create the parents and append to the file. Returns the entries the
    write created or grew (an append always grows a file), and an undo that puts base back to `before`."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("teaching edit\n")
    except OSError:
        pass
    after = tree(base)
    changed = [p for p, size in after.items() if p not in before or (size is not None and size != before[p])]

    def undo():
        for p in changed:
            if p in before:
                os.truncate(p, before[p])
        for p in sorted((p for p in changed if p not in before), key=len, reverse=True):
            if os.path.isdir(p) and not os.path.islink(p):
                os.rmdir(p)
            else:
                os.unlink(p)
    return changed, undo


def cases(depth):
    for n in range(1, depth + 1):
        for segs in itertools.product(SEGMENTS, repeat=n):
            for form in FORMS:
                yield form, segs


def event_for(course, form, segs):
    rel = "/".join(segs)
    if form == "abs-course":
        return {"tool_name": "Write", "cwd": str(course), "tool_input": {"file_path": str(course / rel)}}
    if form == "rel-course":
        return {"tool_name": "Write", "cwd": str(course), "tool_input": {"file_path": rel}}
    if form == "rel-lessons":
        return {"tool_name": "Edit", "cwd": str(course / "lessons"), "tool_input": {"file_path": rel}}
    return {"tool_name": "Write", "cwd": str(course), "tool_input": {"file_path": str(course.parent / rel)}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--depth", type=int, default=DEPTH)
    args = ap.parse_args()
    template = Path(tempfile.mkdtemp(prefix="vt-guard-template-"))
    work = Path(tempfile.mkdtemp(prefix="vt-guard-"))
    try:
        build(template)
        base = work / "w"
        shutil.copytree(template, base, symlinks=True)
        # The real path, as the server passes it: on macOS /var is a link to /private/var.
        course = (base / "course").resolve()
        base = course.parent
        before = tree(base)
        guard = load_guard()
        checked = allowed = 0
        for form, segs in cases(args.depth):
            checked += 1
            event = event_for(course, form, segs)
            if not ask_guard(course, event, guard):
                continue
            allowed += 1
            target = Path(event["tool_input"]["file_path"])
            if not target.is_absolute():
                target = Path(event["cwd"]) / target
            changed, undo = edit(target, base, before)
            bad = [p for p in changed if not os.path.isdir(p) and harmed(course, p)]
            # A write that escaped above the test folder would not show in its tree, so the target itself is
            # located too.
            if os.path.isfile(target) and harmed(course, target) and str(target) not in bad:
                bad.append(str(target))
            if bad:
                short = lambda p: str(p).replace(str(course), "<course>").replace(str(base), "<parent>")  # noqa: E731
                print("COUNTEREXAMPLE: the guard allowed an edit that changed a protected or outside file.")
                print(f"  1. A teaching session asks to {event['tool_name']} {short(event['tool_input']['file_path'])!r}"
                      f" (cwd {short(event['cwd'])}).")
                print("  2. teach_guard.py exits 0, so Claude Code lets the edit through.")
                print(f"  3. The write lands on: {', '.join(sorted({short(os.path.realpath(p)) for p in bad}))}")
                return 1
            undo()
        print(f"OK: {checked} edit requests (depth {args.depth}, {len(SEGMENTS)} segments, {len(FORMS)} forms); "
              f"{allowed} allowed, none touched a protected or outside file.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(template, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
