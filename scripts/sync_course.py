"""Make a course look and work exactly like the current visual-teach skill.

Usage: python3 sync_course.py <workspace>

Copies the skill's shared files (style.css, theme.js, quiz.js, ask.css, ask.js) into the course's assets/,
replacing older copies, and makes every page (index, lessons, reference) load them, plus
assets/course.css when the course has one. Course-only styling belongs in assets/course.css,
never in the shared files, so every course keeps the same look and feel.
"""

import hashlib
import re
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SHARED = ["style.css", "theme.js", "quiz.js", "ask.css", "ask.js"]
PROFILE = Path.home() / ".diagram-design" / "profiles" / "learn.md"


def code_version():
    """A short hash of the code a running server holds in memory. serve.py reports the one it started with, and
    open_course.py restarts a server whose hash differs from the installed files, so an update reaches it."""
    digest = hashlib.sha256()
    for name in ("serve.py", "sync_course.py"):  # everything else the server reads from disk when it needs it
        digest.update((SKILL / "scripts" / name).read_bytes())
    return digest.hexdigest()[:12]


def pages(ws):
    return [p for p in [ws / "index.html"] if p.exists()] + sorted(ws.glob("lessons/*.html")) + sorted(ws.glob("reference/*.html"))


def drifted(ws):
    """Shared files in the course that differ from the skill's. A link counts even when its bytes match: the server
    never serves a file from outside the course, so the page would go without it."""
    src = SKILL / "starter" / "assets"
    return [n for n in SHARED if (ws / "assets" / n).is_symlink() or not (ws / "assets" / n).exists()
            or (ws / "assets" / n).read_bytes() != (src / n).read_bytes()]


def link_assets(page, ws):
    prefix = "" if page.parent == ws else "../"
    html = page.read_text(encoding="utf-8")
    original = html
    sheets = ["style.css", "ask.css"] + (["course.css"] if (ws / "assets" / "course.css").exists() else [])
    tags = [f'<link rel="stylesheet" href="{prefix}assets/{s}">' for s in sheets]
    tags.append(f'<script src="{prefix}assets/theme.js"></script>')  # in <head>, so the theme is set before paint
    missing = [t for t in tags if t not in html]
    if missing:
        html = html.replace("</head>", "\n".join(missing) + "\n</head>", 1)
    scripts = [f'<script src="{prefix}assets/{s}"></script>' for s in ("quiz.js", "ask.js")]
    missing = [t for t in scripts if t not in html]
    if missing:
        html = re.sub(r"</body>", "\n".join(missing) + "\n</body>", html, count=1)
    if html != original:
        page.write_text(html, encoding="utf-8")
        return True
    return False


def sync(ws):
    ws = Path(ws).expanduser().resolve()
    if (ws / "assets").is_symlink():
        raise ValueError("Cannot sync: assets is a symlink.")
    (ws / "assets").mkdir(exist_ok=True)
    changed = drifted(ws)
    for name in changed:
        dest = ws / "assets" / name
        if dest.is_symlink():
            dest.unlink()  # replace the link with a copy; never write through it to a file outside the course
        shutil.copy(SKILL / "starter" / "assets" / name, dest)
    linked = [p.relative_to(ws) for p in pages(ws) if p.resolve().is_relative_to(ws) and link_assets(p, ws)]
    marker = ws / ".diagram-design"
    if not marker.exists() and not marker.is_symlink():
        marker.write_text("profile: learn\n", encoding="utf-8")
    src = SKILL / "starter" / "diagram-profile-learn.md"
    if not PROFILE.exists() or PROFILE.read_bytes() != src.read_bytes():
        PROFILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, PROFILE)
    return changed, linked


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        changed, linked = sync(sys.argv[1])
    except ValueError as exc:
        sys.exit(str(exc))
    print("Updated shared files:", ", ".join(changed) or "none, already current")
    print("Pages now loading them:", ", ".join(map(str, linked)) or "none needed")


if __name__ == "__main__":
    main()
