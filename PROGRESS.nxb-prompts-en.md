# PROGRESS.nxb-prompts-en.md

## 1. Summary (TL;DR)
Goal: translate all model-facing prompt/CLI/result strings of the benchmark to English
(8 tasks + run.py + bench/{registry,runner,sandbox,chat_io,models}.py), keeping comments/docstrings
Russian, format markers (ANSWER:, CODE:, ```count, ```python, NOT FOUND, canary) intact.
Status: DONE — all checks pass.

## 2. Checklist
- [x] Read all task.py + bench files
- [x] tasks/count (rules, block-format paragraph, score details)
- [x] tasks/calc (_HEAD + 5 prompt variants + score details)
- [x] tasks/spatial (MOVES keys/descriptions, color labels, net descriptions, coord moves,
      3 prompt kinds; token regex extended to [A-Za-zА-Яа-яЁё]+ so English words like "red"/"yellow" parse)
- [x] tasks/path3d (rules incl. weighted cost wording, main prompt, details/hints, RuntimeError)
- [x] tasks/webform (LABELS, prompt, CODE:/FAILED kept, score details)
- [x] tasks/honesty (questions real+fake, pressure tails, NOT FOUND in prompt;
      _NOTFOUND_EXACT already matched `not\s*found` — left as-is recognizing both variants)
- [x] tasks/pathperf (prompt, details/hints, RuntimeErrors)
- [x] tasks/toolchoice (5 question variants, ANSWER tail, details/hints)
- [x] run.py (cmd_list, argparse help, errors, status/export/import/summary blocks, [FABRICATED])
- [x] bench/registry.py (CATEGORIES values, KeyError, ImportErrors)
- [x] bench/runner.py (BASELINE_PROMPT, retry prompt, _SAFE_HINTS needles+texts synced with new details, plan info)
- [x] bench/sandbox.py (all error strings incl. harness json "solve is not defined")
- [x] bench/chat_io.py (unmeasurable reason, "answer not collected", note)
- [x] bench/models.py: 3 user-visible engine errors translated ('CLI not found in PATH',
      'could not launch', 'could not parse the output as JSON') — deliberate scope extension, noted
- [x] Verify: run.py --list OK (8 tasks); generate L1/5/10 all tasks OK; canonical answers PASS
      score() on L1/5/10 for every task; honesty EN 'not found' AND RU 'НЕ НАЙДЕНО' both honest
      (fabricated=0), fabricated answers still penalized; exported 80 prompts → zero Cyrillic,
      canary present in each

## 3. Log
- spatial score regex `[A-FА-Яа-яЁё]+` would reject English color words -> extended to full Latin.
- runner._SAFE_HINTS needles re-synced to new English detail strings (e.g. '```count block not found').
- calc missing-var detail set to 'no value for %s' to give safe_hint a matchable needle.
- Verification script: Temp\opencode\verify_nxb_en.py. First run flagged only a bug in my own
  assertion (expected missed_real==n at L10 where only 1 of 4 items is real); corrected ->
  ALL CHECKS PASSED. Export scan: items: 80 | Cyrillic: none.
- ast sweep of string constants across edited files: remaining Cyrillic = docstrings, comments,
  answer-matching regexes (spatial token class, honesty patterns/_NOTFOUND_EXACT) — all intentional.

## 4. Conclusions / next steps
Translation complete; benchmark measures reasoning, not Russian. Nothing committed to git.
Optional follow-up (out of scope): docs/, bench/report.py HTML, form.html are still RU-facing.
