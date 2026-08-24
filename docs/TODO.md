# Roadmap

Tasks are added as a folder under `tasks/`, and old runs don't break: new
levels simply show up as missing and get computed on the next run. So the list
below can be worked through one item at a time without rerunning everything.

---

## `toolchoice` — the model has to figure out on its own that it needs a script

**Categories:** logic, agentic

Pose a task that is **unprofitable to solve in your head** but profitable to
solve with a script: the data volume makes manual enumeration unrealistic,
while a short program computes it in seconds. Nothing hints to the model that a
script is needed — it has to decide that itself.

Three things are measured, not one:

1. **Did it pick the right strategy** — wrote a script or started counting by hand.
2. **Does the script work** — it runs on a dozen hidden instances of the task
   and its answers are checked against references.
3. **How efficient is it** — runtime is measured per instance. A naive
   solution fits within the limit on small inputs and times out on large ones;
   a good algorithm passes everything.

The score combines correctness and fitting the time budget. This is what sets
the task apart from `path3d`, where efficiency isn't checked: there, a correct
answer is enough.

Ideas for the problem statement: counting something over large ranges where a
sieve or dynamic programming is needed instead of enumeration; graph search
over hundreds of thousands of edges; processing a long sequence with a
one-pass requirement.

## `multilingual` — working in a language other than English

**Categories:** instruction, agentic

Not a translation of the whole suite — running every task in another language
would just fold language skill into every score. This is one task that measures
language handling on purpose and in isolation.

The shape is agentic rather than translational: the assignment arrives in one
language, the source material is in a second, and the required output format is
in a third. Passing means the model kept the format, didn't silently switch
languages, and didn't lose content in transfer. Failure modes worth catching:
answering in the wrong language, translating identifiers that must stay verbatim,
and dropping diacritics or non-Latin text on the way through.

Because the rest of the suite is English-only by rule, this is the only place
where language becomes a measured variable instead of noise.

## `orchestration` — spawning and steering subagents

**Categories:** agentic

Everything else measures a model doing the work itself. This one measures
whether it can get work done through others: split a job, launch subagents,
keep track of them, and merge what comes back.

The setup gives the model a wrapper that can start CLI subagents
([neoxider-agents](https://github.com/NeoXider/neoxider-agents)) and a job that
is awkward to do alone — several independent pieces with a deadline. Scoring
looks at whether the pieces were actually split rather than done sequentially,
whether results were checked before being merged, and whether a subagent that
died was noticed and restarted.

The interesting failure is not "couldn't spawn an agent" but accepting a
subagent's report without verification. That has a real precedent: a free model
returned 25 fully fabricated job applications with a flawless-looking report,
and the only way to catch it was opening the links. A model that merges
unverified subagent output should not score the same as one that checks.

## `macro` — record a browser automation macro

**Categories:** agentic

From a text description of a scenario, assemble a macro for `web-search-neo`
and run it. Pass/fail is whether the macro reaches the target page state.

## `game` — play through a simple browser game

**Categories:** agentic, spatial

Take a simple game to a target state. The game is static, hosted alongside on
GitHub Pages, with state read from the DOM.

A dino runner is a good candidate: one input (jump), a clearly readable state
(score, obstacle distance), and it measures something no other task does —
acting under a real-time constraint rather than thinking it over. The agent has
to react while the game is running, not compose a perfect answer offline.
Scoring by distance survived, with obstacle patterns generated from the seed.

---

## Infrastructure

- **Task versioning.** When a task's spec changes, old results become
  incomparable with new ones, and right now nothing marks that. Each task needs
  a version recorded in results, so the leaderboard doesn't silently compare
  different things.
- **Parallel runs of several models** into one `results/` directory: writing is
  already atomic (via a temp file), and each model gets its own file, so there
  should be no conflicts — needs a real-world test.
- **Repeat runs of one model** to estimate variance: currently it's one run per
  model, and free models are noticeably unstable.
