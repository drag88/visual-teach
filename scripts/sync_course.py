"""Make a course look and work exactly like the current visual-teach skill.

Usage: python3 sync_course.py <workspace>

Copies the skill's shared files (style.css, theme.js, quiz.js, ask.css, ask.js) into the course's assets/,
replacing older copies, and makes every page (index, lessons, reference) load them, plus
assets/course.css when the course has one. Course-only styling belongs in assets/course.css,
never in the shared files, so every course keeps the same look and feel.
"""

import re
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SHARED = ["style.css", "theme.js", "quiz.js", "ask.css", "ask.js"]
PROFILE = Path.home() / ".diagram-design" / "profiles" / "learn.md"


def pages(ws):
    return [p for p in [ws / "index.html"] if p.exists()] + sorted(ws.glob("lessons/*.html")) + sorted(ws.glob("reference/*.html"))


def drifted(ws):
    """Shared files in the course that differ from the skill's."""
    src = SKILL / "starter" / "assets"
    return [n for n in SHARED if not (ws / "assets" / n).exists() or (ws / "assets" / n).read_bytes() != (src / n).read_bytes()]


def link_assets(page, ws):
    prefix = "" if page.parent == ws else "../"
    html = page.read_text()
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
        page.write_text(html)
        return True
    return False


def sync(ws):
    ws = Path(ws).expanduser().resolve()
    (ws / "assets").mkdir(exist_ok=True)
    changed = drifted(ws)
    for name in changed:
        shutil.copy(SKILL / "starter" / "assets" / name, ws / "assets" / name)
    linked = [p.relative_to(ws) for p in pages(ws) if link_assets(p, ws)]
    marker = ws / ".diagram-design"
    if not marker.exists():
        marker.write_text("profile: learn\n")
    src = SKILL / "starter" / "diagram-profile-learn.md"
    if not PROFILE.exists() or PROFILE.read_bytes() != src.read_bytes():
        PROFILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, PROFILE)
    return changed, linked


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    changed, linked = sync(sys.argv[1])
    print("Updated shared files:", ", ".join(changed) or "none, already current")
    print("Pages now loading them:", ", ".join(map(str, linked)) or "none needed")


if __name__ == "__main__":
    main()
