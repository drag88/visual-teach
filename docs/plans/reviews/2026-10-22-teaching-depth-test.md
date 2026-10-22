---
reviewer: before/after generation test (plan U3)
model: claude opus, effort high, through the course page's Teach job (serve.py TIERS deep)
date: 2026-10-22
reviewed: docs/plans/2026-10-22-2056-feat-teaching-depth-plan.md, worktree feat/teaching-depth before commit
---

# Before/after test of the teaching rules

**Question.** With the same brief and the same sources, does the revised skill (this branch) teach with more reasoning and a shape that follows the subject than v1.3.1 did, without the lessons becoming formulaic or bloated?

## Setup

- Two copies of the skill: `before` = a worktree at tag v1.3.1; `after` = this branch at the commit under review.
- Three subjects, each an empty course folder holding only `MISSION.md` and `RESOURCES.md`, identical for both versions: `harness` (the systems control: build a coding-agent harness, with OpenAI's Codex docs), `cashflow` (interpretive: judge whether a company's profit is real from its cash-flow statement), `memo` (practical: write a one-page decision memo for an executive).
- Sources: a local `--code` folder per subject holding text copies of the primary documents (8 OpenAI pages; the SEC Beginners' Guide, the IFRS summary of IAS 7 and Apple's FY2024 10-K; the Kennedy School memo guide, Behn's memo essay, a DC government decision-memo template and an Irish government page). No `--web`, so both versions had exactly the same material.
- One job per course: `POST /api/teach {"action": "next"}` on each course's server, started 21:22 Singapore time; all six finished by 21:28. Each version's own course check ran afterwards and passed on all six. Total cost about US$9.80.
- The harness brief is the real codex-harness mission with the learner's name removed and the skill's own format words ("picture first, one workshop analogy") taken out of its Constraints, so neither version was told to use an analogy.

## Results

| | before/harness | before/cashflow | before/memo | after/harness | after/cashflow | after/memo |
|---|---|---|---|---|---|---|
| Title | The map: a model that decides, a harness that acts | The map: profit, cash and the three sections | The map: four parts of a decision memo | The harness map | Profit is not cash | Open with the decision |
| Hero | diagram | diagram | diagram | diagram + parts table | bridge (waterfall) chart of a made-up example | before/after memo pair, no diagram |
| Opens with | "Picture a busy kitchen whose head chef is not in the room" | "Picture a corner shop that keeps two notebooks" | "Picture a traveller in a hurry who reaches a fork in the road" | the parts table, then three reasoned ideas | the made-up Lamp Shop bridge | one memo, two openings |
| Everyday comparison | kitchen, mapped in NOTES.md | corner shop, mapped in NOTES.md | signpost, mapped in NOTES.md | none (NOTES.md says so) | none | none |
| "By the end" | name the seven parts | name the three sections | name the four parts, in order | given any agent, say which part chooses, which does the work, where a safety rule has to live | work out cash from operations from profit and the working-capital changes, and say why they differ | rewrite a memo's opening so the reader knows the decision, deadline and answer before line four |
| Prose words | 1011 | 921 | 1066 | 1225 | 1335 | 1645 |
| Practice items | spot, mcq, mcq, order, match, predict, recall | spot, match, mcq, recall, predict | spot, spot, order, mcq, mcq, predict, recall | spot, mcq, recall, recall, order | spot, mcq, match, predict, recall | mcq, mcq, mcq, recall, order |
| Items on a case the lesson did not show | 1 | 0 to 1 | 1 | 3 | 3 | 4 |
| Source citations | 16 | 11 | 15 | 25 | 8 | 16 |
| Quoted passages (blockquote) | 0 | 0 | 0 | 2 | 3 | 5 |

A "case the lesson did not show" is a practice item whose situation does not appear in the lesson body (for example after/harness asks what has happened to the money when a made-up support agent's model returns an `issue_refund` tool call; after/memo asks the learner to rewrite the opening of a lease memo it has not discussed). The count is the reviewer's reading, not a script.

## Against the disproof criteria

- **Claims match sources.** Every citation in all six lessons was printed beside its source lines and read. All hold, including Apple's figures and the arithmetic built on them (93,736 net income to 118,254 operating cash; 11,445 + 11,688 − 2,266 = 20,867 of non-cash items; 3,788 receivables and 6,020 payables) and the 13.3% to 38.3% benchmark figure. No stop condition triggered.
- **Reasons present.** The before lessons explain each part in one to three sentences (what it is, a citation) and keep the why for a short "where the picture breaks" section. The after lessons give each idea its reason, its consequence and its limit. Excerpts, harness: before, "The chef on the phone. It never touches a file. When it wants something done, it replies with a tool call"; after, "That split is the reason a harness exists. The model has no hands. Every change to a file or a system passes through code you control, so that code is where you can watch, limit and record actions." Cash flow: before, "A customer takes goods and promises to pay later. The diary records the sale, so profit goes up. The tin gets nothing yet"; after, "Receivables, −50. [...] Profit counted all 500, but only 450 came in as cash. [...] If those customers never pay, part of the profit was never real." Memo: before, "This is the fork. In one or two lines, say what the reader must decide, and by when"; after, "What goes wrong without it: the reader works through the background without knowing what it is for. Then they put the memo aside, or reply asking what you need. Either way the decision waits."
- **Same shape across subjects.** Before: all three are "The map", open with an analogy before any real term, walk a diagram, and test by naming parts. After: three different heroes and three different practice mixes; the memo lesson has no diagram at all and its recall item is a performance task (rewrite two lines). No stop condition triggered.
- **Longer without application.** The after lessons are longer: +21% (harness), +45% (cashflow), +54% (memo), outside the ±25% band the plan set for cashflow and memo. The extra length carries the reasoning and the new-case items, and each after lesson still teaches two or three ideas, but this is the one criterion that did not hold and it stays a watch item: at about 1,650 words the memo lesson is at the edge of the mission's ten minutes.
- **Repeat but not transfer.** Not observable without a learner; the after lessons at least ask for it (3 to 4 new-case items each against 0 to 1).

## Other observations

- The after harness NOTES.md records "What the learner already knows is not yet recorded in MISSION.md ... Ask at the next live session", which is the new catch-up rule working.
- Two of the three after lessons label their sub-paragraphs "Why", "What goes wrong without it" and "Where it stops applying". That is the rule's reason, consequence and limit made visible. It reads well here, but if it appears in every lesson it becomes the next formula; watch for it in the next real course.
- The before cash-flow lesson's "two notebooks" comparison was a good one. The after lesson covers the same distinction in real terms ("two clocks"). Making comparisons optional cost nothing here, but the rule does not forbid a good one.
- The quoted-passage exclusion in the checker was needed: the after memo lesson quotes a 50-word sentence from Behn inside a `blockquote`, which the old rule would have failed.

## What this test does and does not show

Source accuracy: checked, all claims hold. Teaching quality: the reviewer's read above, against the plan's rubric; a blind read by the learner (pages shuffled under letters A to F, key sealed) is prepared at `~/learn/_abtest/read/` and has not happened yet. Immediate performance and retention: not measured; no learner has taken these lessons.

The six course folders, sources and the blind-read copies stay under `~/learn/_abtest/`, outside the repository.
