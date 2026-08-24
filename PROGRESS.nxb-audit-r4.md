# Summary (TL;DR)

Финальный аудит восьми задач Neoxider Benchmark завершён. Исходные fixes раунда 3 в основном устояли; пользовательская защита от vacuous pass также прошла повторную проверку. Главный остаточный риск — P0 подделка pathperf timings через shared serializer; дополнительно найдены P1 predictability, telemetry-only toolchoice, DOM shortcut webform и публичный documentation drift.

## Checklist

- [x] Прочитать прошлые аудиты, структуру проекта и обязательные инструкции проекта/пакета.
- [x] Воспроизвести каждый контрпример из раздела «Что исправлено в раунде 3».
- [x] Проверить все восемь задач на новые обходы, отдельно webform tabs и pointer drag.
- [x] Сверить README.md, docs/TASKS.md, docs/TODO.md и docs/index.html с кодом.
- [x] Немедленно исправить явные ошибки эталонов и проверить изменения.
- [x] Завершить docs/AUDIT_ROUND4.md с приоритетами, строками и нерешёнными вопросами.

## Log

- 2026-08-24: checkpoint отсутствовал; создан. Прочитаны обязательные `unity-game-agent` и `neoxider-tools` инструкции; аудит классифицирован как прямой read-mostly review с точечными fixes только явных ошибок эталонов.
- 2026-08-24: полностью прочитаны `docs/ARCHITECTURE_REVIEW.md` и `docs/AUDIT_ROUND3.md`. Решение: не дублировать их открытые P0/P1/P2; проверять только регрессии заявленных fixes и ранее не описанные дефекты.
- 2026-08-24: настоящие `score()` подтвердили: pathperf ловит прежний `json.load` precompute (`KeyError`) и single-cache на карте 2; top-level sleep включён в время; delayed generate не меняет expected (`cases,size`, без budget). calc/spatial: 10/10 эталонов приняты, старый мусор отвергнут, одна завершающая newline принята. path3d: старый sequence hardcode отвергнут на карте 2; честный L10 Dijkstra прошёл за 0.333 s. toolchoice: irrelevant tool отвергнут, но корректный ответ с telemetry `bash`, `browser_execute_script` или `read_commandments` зачтён без связи с результатом инструмента.
- 2026-08-24: пользователь исправил обнаруженный vacuous pass в `bench/sandbox.py`: cases читаются до `runpy`, а число results проверяется. Payload, переписывающий `cases.json` в `[]`, теперь проваливает и pathperf, и path3d. Новый P0: solution monkeypatches shared `json.dumps` and writes each result's `seconds=0`; pathperf solution sleeping 0.8 s per three cases passed as `0.00 s` (wall 2.54 s, budget 2.00 s).
- 2026-08-24: exact Unicode regression: four `НЕ НАЙДЕНО` на L9/L10 дают `3/4, сдалась на разрешимых 1`, `fabricated=0`; fix honesty устоял. Pathperf distribution: 30 seeds × 3 карты — L1 90/90 и L10 89/90 ответов равны Manhattan(start, goal); requirement unique answers почти всегда достигается тремя соседними goals, а не картами, требующими BFS.
- 2026-08-24: static audit `docs/form.html`: Billing/Access controls remain enabled DOM nodes under `.hidden`; `collect()` reads them directly and takes `#sortable li` DOM order. Browser-evaluate can fill hidden inputs and reorder nodes without tab click or mouse/pointer drag. Listeners are `mousedown/mousemove/mouseup`, despite docs calling them pointer events.
- 2026-08-24: public-doc read completed for README/TASKS/TODO/index and CLI help. Confirmed P1 documentation drift: README promises English task prompts/CLI while current prompts and CLI strings are Russian; TASKS says six tasks and omits implemented pathperf/toolchoice, retains superseded calc/honesty/webform behaviour; TODO still plans already-shipped toolchoice with a different contract.
- 2026-08-24: final regression of cardinality used a `json.dumps` payload that reported `results: []`; pathperf/path3d rejected it with `решение вернуло 0 ответов вместо 3/1`. `python -m compileall -q bench tasks run.py` and `git diff --check` passed. Report completed; no reference-answer defect found, so no source/task contract was edited.

## Conclusions / next steps

Deliverables complete: `docs/AUDIT_ROUND4.md` contains regression evidence, new P0/P1 findings, documentation-vs-code defects, change scope and explicit non-fix rationale. No commit created.
