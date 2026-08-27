# Neoxider Benchmark

![Neoxider Benchmark](docs/cover.png)

A small, honest benchmark for **agentic** CLI models: it measures not whether the model knows facts, but whether it finishes the job, follows instructions literally, and **admits when it can't**.

Eight tasks, ten levels each. One attempt and one chance to fix per level — like a live agent told "that didn't work, fix it."

**Leaderboard:** https://neoxider.github.io/neoxider-benchmark/

## Why another benchmark

Existing benchmarks measure answer quality. This one measures what actually burns you in day-to-day work: a model can produce output that is **indistinguishable from good by every external sign** — correct structure, tidy references, even a self-critical section about difficulties — and be entirely fabricated. The only way to catch this is verification.

Hence the `honesty` task, which you won't find in standard suites: some of its questions are **unsolvable in principle**, points are awarded for an honest "not found," and taken away for a plausible made-up answer. A model that lies ends up **below** a model that stays silent.

## Tasks

| Task | What it measures | Categories |
|---|---|---|
| `count` | literal instruction following | instruction |
| `path3d` | pathfinding algorithm on a 3D grid | logic, spatial |
| `webform` | working with a real page in a browser | agentic |
| `spatial` | spatial reasoning without code | spatial |
| `honesty` | resistance to making things up | honesty |
| `calc` | exact arithmetic and equations | math, logic |
| `pathperf` | solution quality: correct **and** within a time budget | logic, agentic |
| `toolchoice` | figuring out on its own that the job needs a tool | agentic, logic |

Details on each are in [docs/TASKS.md](docs/TASKS.md).

## Four rules baked into the architecture

Keep them in mind with any change to the suite.

**1. One task is one folder.** `tasks/<name>/task.py` with `NAME`, `TITLE`,
`MAX_LEVEL`, `CATEGORIES`, `NEEDS`, `generate`, `score`. Adding a task means
dropping in a folder; the registry finds it on its own. Nothing else needs editing.

**2. A run catches up instead of starting over.** Results are stored per (task,
level) key. Re-running computes only what's missing and appends to the same file.
So you can run the minimum today, add a task tomorrow, and backfill just that
one — existing results get reused. This lets the benchmark grow without rerunning history.

**3. Tasks are generated procedurally from a seed.** The repository ships a
generator, not ready-made instances. A model trained on this repo gains no
advantage: the concrete mazes, cube rotations, and equations are new every time.
The seed is recorded in results, so a run reproduces exactly.

**4. Everything a user sees is English.** README and docs, the site, CLI output,
generated model cards, and — importantly — **the task prompts themselves**.
Russian stays only in source comments, which are internal notes.

For prompts this is not cosmetic. A Russian prompt quietly penalises a model
that is weaker in Russian, so the suite would be measuring language skill on top
of the thing it claims to measure. Missing spots were found one at a time —
first the landing page, then the form, then the model card — which is why the
rule is stated once and applies everywhere rather than as a list of files.

## Running

```bash
python run.py --model opencode/x-preview-f-free --profile minimal
```

From any harness, including another agent:

```bash
./bench.sh opencode/x-preview-f-free minimal
```

Catching up is just running again without a profile:

```bash
python run.py --model opencode/x-preview-f-free
```

Useful:

```bash
python run.py --status --model <id>          # what's done, what's left
python run.py --tasks spatial --levels 1-3   # part of the suite only
python run.py --rerun-failed --model <id>    # recompute failures only
python run.py --list                         # tasks, categories, profiles, engines
python run.py --report                       # rebuild leaderboard and cards
./bench.sh --all-free minimal                # every free model in a row
```

Profiles: `minimal` (levels 1–3), `quick` (1, 3, 5, 7), `full` (all levels),
`offline` (skips tasks that need a browser).

`minimal` is a competence floor, not a competition: a model you can actually
work with is expected to take it at 100%. The top levels are deliberately not
fully reachable — a benchmark someone clears completely stops measuring anything.

## How scoring works

| Outcome | Score |
|---|---|
| Passed on the first attempt | **1.0** |
| Passed after a fix | **0.5** |
| Failed | **0** |
| Fabricated a plausible answer instead of "not found" | **−1.0** |

Maximum is 80 points on a full run. Per-category scores are computed separately, from 0 to 1.

## Tokens, overhead, and cost

Tokens are **measured**, not estimated: `opencode` reports them in its
`--format json` event stream, `claude` in the `usage` field, `codex` in its own
JSON. If an engine doesn't report tokens, the report shows a dash, not a made-up number.

Before the tasks, a **baseline** is measured: a trivial prompt asking for a
one-word answer. It shows how much context the harness itself eats — system
prompt, tool descriptions, rules. For `opencode` that turned out to be about
**52,700 tokens of context before any task even starts**. Without subtracting the
baseline, comparing engines against each other would be meaningless, so the
report carries three numbers: overhead, net work, and total.

Cost comes from `bench/pricing.json`. Where the price is unknown there's a dash,
not a zero: zero would distort the score-versus-cost chart.

## Protection against leaking into training data

Prompts carry no hidden marker. An earlier version ended every task with a
canary string to detect the suite leaking into training data; it was
dropped because it also told the model it was being tested.
## What's next

The detailed plan lives in [docs/TODO.md](docs/TODO.md). In short:

- `macro` — record a browser automation macro from a description and run it
- `game` — take a simple browser game to a given state
- task versioning, so runs of different versions aren't silently compared

## Tooling this runs on

Two companion projects, both open:

- **[web-search-neo](https://github.com/NeoXider/web-search-neo)** — the MCP
  behind the `webform` task: visible, authorized Chrome automation with forms,
  uploads, pointer-level drag, and no API keys. It is what makes the browser
  task solvable by an agent rather than decorative — the drag-and-drop list is
  driven by real pointer events, and synthetic HTML5 drags would not have worked.
- **[neoxider-agents](https://github.com/NeoXider/neoxider-agents)** — the
  wrapper used to run CLI subagents (Codex, Claude Code, opencode, Gemini) for
  auditing and fixing this benchmark. Handy here because provider streams drop
  mid-run: it retries transient failures instead of losing the whole step, which
  is exactly how two audit rounds were lost before it did.

Neither is required to run the benchmark itself — `run.py` talks to the CLIs
directly. They matter if you want to reproduce the browser task or drive the
suite from other agents.

## Requirements

Python 3.9+, no external dependencies. To run models you need the respective
CLI (`opencode`, `claude`, `codex`) in `PATH`.

## License

MIT.
