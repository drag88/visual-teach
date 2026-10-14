# Upstream source

- Repository: https://github.com/cathrynlavery/diagram-design
- Source directory: `skills/diagram-design`
- Pinned commit: `9874ad73813715fc36875e45afd9cd94c68f3c3f`
- Declared skill version: 2.6
- Installed: 2026-09-16
- Scope: bundled inside the visual-teach skill (copied from the agent-config repo's `skills/diagram-design/` on 2026-10-14)
- Installation: Codex system skill installer, pinned to the commit above
- Licence: MIT; the upstream repository's notice is preserved in `LICENSE`

Upstream wording and behaviour are preserved. Windows-style line endings in nine files are normalised to LF, and two trailing-whitespace lines are cleaned, for the catalogue's whitespace gate. This provenance note and the root licence notice are the only packaging additions. No global brand profile, alternate skill root or plugin-cache copy was created.

The skill was already used from a temporary source checkout to redraw an anonymised telco CX appendix. Its installed accessible/static-SVG self-check was then run against that appendix's extracted SVG component. Browser verification of the full slide deck remains a separate check.

`SKILL.md` is renamed `GUIDE.md` inside visual-teach so no tool lists it as a second diagram-design skill. Paths in it that start `references/`, `assets/` or `scripts/` resolve from this folder.
