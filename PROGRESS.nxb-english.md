# PROGRESS — nxb-english

## Summary (TL;DR)
Translate public docs (README.md, docs/TASKS.md, docs/TODO.md, docs/index.html) to professional English. Python comments, ARCHITECTURE_REVIEW/AUDIT files untouched. Status: reading sources done; writing translations in progress.

## Checklist
- [x] Read all 4 source files
- [x] Verified cited facts (52753 / 960 maps / cases.json 0.01s) live only in Python comments — out of scope
- [ ] Translate README.md
- [ ] Translate docs/TASKS.md
- [ ] Translate docs/TODO.md
- [ ] Translate visible strings in docs/index.html
- [ ] Final verification pass (structure, tables, canary intact)

## Log
- Read README.md (142 lines), docs/TASKS.md (183), docs/TODO.md (61), docs/index.html (431). No PROGRESS.nxb-english.md existed before.
- grep confirmed: 52753 nowhere in translatable files; 960/960 + cases.json 0.01s only in tasks/path3d/task.py and bench/sandbox.py comments (stay Russian per task).

## Conclusions / next steps
Write English versions of all 4 files, keep tables/section structure/canary NXB-CANARY-a7f3c1, no JS/data-key changes.
