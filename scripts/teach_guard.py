"""Allow teaching edits only to unprotected files inside the course."""

import json
import sys
from pathlib import Path


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError
        course = Path(sys.argv[1]).resolve()
        event = json.load(sys.stdin)
        if event["tool_name"] not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            raise ValueError
        args = event["tool_input"]
        name = args.get("file_path") or args.get("notebook_path")
        if not isinstance(name, str) or not name:
            raise ValueError
        path = Path(name)
        if not path.is_absolute():
            cwd = Path(event["cwd"])
            if not cwd.is_absolute():
                raise ValueError
            path = cwd / path
        parts = tuple(part.casefold() for part in path.resolve().relative_to(course).parts)
        if (not parts or parts[0] == ".claude"
                or parts in (("course.json",), (".serve.json",), ("claude.md",), ("agents.md",))
                or (parts[0] == "assets" and parts != ("assets", "course.css"))):
            raise ValueError
    except Exception:
        print("Edits must stay in unprotected course files.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
