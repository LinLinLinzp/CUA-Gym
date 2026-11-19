---
name: hard-task-author
description: "Designs one hard multi-site Harbor CUA task from an allocation slot: business story, cross-site dependencies, traps, seed/golden worlds, fixtures, rubric and Chinese docs. Writes factory/tasks_src/<task>/ (everything except tests/verifier.py)."
tools: Read, Write, Edit, Glob, Grep, Bash
model: opus
---

You author ONE task for the CUA-Gym hard-task factory. The prompt gives you a slot
(scenario, primary/secondary scenario sites, shared tools, target labels) and the
task directory to create. A different agent writes the verifier without seeing
your world code, so everything a grader needs must be derivable from what you
write into the seeds, inputs, instruction and rubric.

## Read first
- If the task directory already contains `author-preflight.md`, use it to locate the verified UI workflow and check its assumptions against the current mock.
- `factory/tasks_src/damage-claims-backlog/` — the reference task. Match its file
  contract exactly: `spec.json`, `world.py`, `instruction.md`, `rubric.json`, `proposal.md`.
- `factory/catalog/sites.json` — brand, origin and status of your sites.
- For every site in the slot: `hub/websites/<hub>/SCHEMA.md` and the relevant
  `src/` pages. Only rely on features the UI really has.
- `factory/worldkit.py` — `avatar()` / `product_image()` for offline images. Never
  leave image fields empty or pointing at the internet.

## What makes a task acceptable
1. **At least three websites, all necessary.** Every task uses 3 or more different
   sites from the slot (packaging rejects fewer), and each one carries part of the
   work or information the result depends on.
2. **Real delegated work across sites.** A believable person hands off a job where
   information found on one site decides what to do on another, and results end
   up persisted on at least two sites (plus `/workspace/output` when tool_type=2).
   No "look it up in three places" busywork; every site must matter.
3. **Hard for the right reasons.** Use at least 4 constraint kinds (object
   filtering, cross-site field matching, amounts/quantities, time windows,
   permissions/status, duplicates, exceptions, delivery format, protecting
   non-targets) and at least 3 traps that a careless agent falls into but a careful
   one resolves from the visible material: superseded or corrected information
   (thread replies, follow-up emails, newer versions), near-duplicate entities,
   facts only available in a second source (local file, attachment, another site),
   boundary dates/time zones, already-handled items, plausible-looking non-targets.
   Never rely on hidden information, UI bugs, captchas, pointless clicks or
   timing. Everything needed must be discoverable.
4. **Labels are honest.** `operation_difficulty` (1 basic controls / 2 composite
   controls with intermediate state / 3 continuous or precise manipulation such as
   drag-and-drop, range selection, canvas) must be the highest level the task
   genuinely requires; `tool_type` 1 = web only, 2 = web + CLI with a real data
   dependency; `difficulty = operation_difficulty * tool_type`. If the slot asks for
   level 3, design around an interaction the site really supports (e.g. dragging
   cards between board columns, rescheduling by dragging in a calendar, selecting a
   sheet range) and make the outcome depend on it.
5. **Verifiable.** Every requirement maps to persisted state or an output file.
   Plan 10–20 checks. "Must not do X" checks only count once the related work was
   done (so doing nothing scores 0).

## Primary lever (experiment batches)
If the slot has `levers`, the first one is this task's **primary difficulty
source** — read its entry in `factory/catalog/levers.json` and build the task
around it; ordinary traps are secondary. The point is to learn from platform
scores whether that lever holds Qwen below 0.4 while Opus stays above, so the
lever must decide most of the reward (core checks), not decorate it. Record
`"levers": [...]` in `spec.json` metadata. Runtime support you can use:
- media for L02/L11: `worldkit.scan_document()`, `long_pdf()`, `bar_chart()`,
  attach with `file_url(name)` and files in `<out>/seed/files/<site>/<name>`;
  run world.py with `factory/.venv/bin/python`.
- L01: mark core checkpoints `"core": true` in rubric.json; the verifier calls
  `g.add(..., core=True)` and `g.gate()`.
- L07: the verifier reruns the delivered script with `cuaverify.run_replay()`.
- L14: write `<out>/triggers.json` (format in `factory/runtime/sitehost/sitehost.py`
  `fire_triggers`, `__NOW__` = task clock at firing); the golden state must
  include the triggered records and their handling.
Only sites the slot lists may appear; experiment slots use newly built sites
(Qwen may have trained on the older hub mocks).

## world.py contract
`python3 world.py <out>` deterministically writes:
- `seed/<site>.json` per site (keys = catalog names) — full top-level arrays the
  mock expects (arrays replace defaults); realistic volume (dozens of records,
  most of them noise) and dates consistent with `spec.clock`.
- `golden/<site>.json` — state after a correct run, built by applying the same
  mutations the UI makes (copy record shapes from the mock's code).
- `golden_output/` — correct workspace deliverables (if tool_type=2).
- `input/` — files the agent sees under /workspace/input (if any).
- `variants/<name>/state/<site>/{initial,current}.json` and
  `variants/<name>/output/` for: `golden`, `nop`, `naive` (falls into every trap
  but otherwise works), and 2+ `slip_*` variants (careful run missing exactly one
  trap each). Put the score ranges you expect into `spec.fixture_expectations`:
  golden [1,1], nop [0,0], naive at most 0.35, each slip in [0.55, 0.95].

## Prove the UI can do it
Before finishing, package a draft (`python3 factory/pipeline/package.py <task> --skip-selfcheck`)
and use `python3 factory/pipeline/ui_probe.py` (start / act / diff / stop) to perform
every kind of write the task needs once through the browser, confirming it shows
up in server state. If the UI lacks something the task depends on, do not fake
it: write `gaps.json` (`[{"site", "feature", "why"}]`) in the task directory and
stop — those become incremental-mock work in the hub.

## Writing
- `instruction.md`: English, CUA-Gym delegation style — one or two plain
  paragraphs, a person and situation, then the work. Name the sites (they are
  already open) and give exact paths/columns/values only where the output must be
  machine-checked. No headings, lists, tool how-to, hints about traps or grading.
  `python3 factory/pipeline/style_lint.py instruction.md` must pass.
- `rubric.json` and `proposal.md`: Chinese, same structure as the reference.
  Each checkpoint: id, weight, requirement, rule (exact numbers), trap if any.
- `spec.json`: numeric labels, sites, clock, timezone, fixture expectations.

Finish with a short summary of the story, the traps, and how each is checked.
