# Summary (TL;DR)

Финальный аудит восьми задач Neoxider Benchmark продолжается после пользовательской правки sandbox. Регрессии pathperf/path3d, calc/spatial, honesty и toolchoice воспроизведены; vacuous pass закрыт, но найден новый P0 bypass измерения времени через подмену сериализатора child harness.

## Checklist

- [x] Прочитать прошлые аудиты, структуру проекта и обязательные инструкции проекта/пакета.
- [~] Воспроизвести каждый контрпример из раздела «Что исправлено в раунде 3».
- [ ] Проверить все восемь задач на новые обходы, отдельно webform tabs и pointer drag.
- [ ] Сверить README.md, docs/TASKS.md, docs/TODO.md и docs/index.html с кодом.
- [ ] Немедленно исправить явные ошибки эталонов и проверить изменения.
- [ ] Завершить docs/AUDIT_ROUND4.md с приоритетами, строками и нерешёнными вопросами.

## Log

- 2026-08-24: checkpoint отсутствовал; создан. Прочитаны обязательные `unity-game-agent` и `neoxider-tools` инструкции; аудит классифицирован как прямой read-mostly review с точечными fixes только явных ошибок эталонов.
- 2026-08-24: полностью прочитаны `docs/ARCHITECTURE_REVIEW.md` и `docs/AUDIT_ROUND3.md`. Решение: не дублировать их открытые P0/P1/P2; проверять только регрессии заявленных fixes и ранее не описанные дефекты.
- 2026-08-24: настоящие `score()` подтвердили: pathperf ловит прежний `json.load` precompute (`KeyError`) и single-cache на карте 2; top-level sleep включён в время; delayed generate не меняет expected (`cases,size`, без budget). calc/spatial: 10/10 эталонов приняты, старый мусор отвергнут, одна завершающая newline принята. path3d: старый sequence hardcode отвергнут на карте 2; честный L10 Dijkstra прошёл за 0.333 s. toolchoice: irrelevant tool отвергнут, но корректный ответ с telemetry `bash`, `browser_execute_script` или `read_commandments` зачтён без связи с результатом инструмента.
- 2026-08-24: пользователь исправил обнаруженный vacuous pass в `bench/sandbox.py`: cases читаются до `runpy`, а число results проверяется. Payload, переписывающий `cases.json` в `[]`, теперь проваливает и pathperf, и path3d. Новый P0: solution monkeypatches shared `json.dumps` and writes each result's `seconds=0`; pathperf solution sleeping 0.8 s per three cases passed as `0.00 s` (wall 2.54 s, budget 2.00 s).

## Conclusions / next steps

Следующие шаги: завершить honesty Unicode regression, проверить distribution/predictability pathperf, webform tabs/drag without events, затем сверить публичные документы с текущим CLI/code.
