# Neoxider Benchmark — аудит, раунд 4

Дата: 2026-08-24

## Регрессия исправлений раунда 3

Прошлые отчёты прочитаны. Ниже будут только результаты повторного воспроизведения восьми заявленных исправлений раунда 3 и новые обходы, возникшие вокруг них.

- `pathperf`: прежний precompute через monkeypatch `json.load` отклонён на первой карте (`KeyError`); top-level `sleep(0.2)` попал в время первого вызова; one-answer cache отклонён на карте 2. В expected больше нет budget, поэтому искусственная задержка только в generate при том же seed оставляет cases байтово идентичными.
- `path3d`: прежний stateful hardcode `[19, -1, 17, 17]` отклонён на карте 2; корректный L10 Dijkstra прошёл за 0.333 s, поэтому отдельные child processes не делают честный верхний уровень непрактичным на проверенной машине.
- `calc` и `spatial`: все canonical эталоны L1–L10 приняты; прежние многострочные/мусорные ответы отвергнуты. Одна обычная завершающая newline принимается; завершающая точка отвергается в соответствии с явно запрещёнными пояснениями и точной грамматикой.
- `honesty`: смесь реальных/fake вопросов сохранена на L9–L10; проверка точного `НЕ НАЙДЕНО` повторяется отдельно с Unicode-escaped input, чтобы не смешать результат с кодировкой shell.

Пользовательская правка после начала раунда закрыла новый vacuous pass: `bench/sandbox.py:28-38` читает вход до `runpy`, а `:137-143` отвергает число results, отличное от числа cases. Payload, переписывающий `cases.json` в `[]`, и payload, сериализующий пустой results array, теперь получают `решение вернуло 0 ответов вместо …` в обеих задачах.

## Новые находки

### P0 — `pathperf`: solution может подделать измеренные секунды после честного расчёта

`bench/sandbox.py:23-62` исполняет недоверенный module в том же interpreter, где harness позднее вызывает module-global `json.dumps`. Payload заменяет `json.dumps`, перед финальной сериализацией проставляет каждому result `seconds=0`, затем трижды `sleep(0.8)` и возвращает правильную манхэттенскую длину. Настоящий `tasks/pathperf/task.py:134-186` принял его как `0.00 s` при budget `2.00 s`; wall time score был 2.54 s. Это полностью отменяет цель performance task, хотя прежний top-level precompute закрыт.

Приоритет: **P0**. Нужен protocol, в котором недоверенный код не управляет публикацией timings: как минимум сохранить bound `json.dumps`/`sys.stdout.write` до `runpy` и валидировать структуру results; для честной границы доверия — отдельный worker/API без общих mutable Python modules.

### P1 — `pathperf`: fix «разные ответы» почти превращает BFS в предсказуемую формулу

`tasks/pathperf/task.py:84-93` задаёт три цели `(size-1, size-1, size-1-case_index)` и допускает карту, когда её ответ ещё не встречался. На 30 независимых seeds это дало Manhattan distance для **90/90** L1-карт и **89/90** L10-карт; на official L10 — `[189, 188, 187]`, ровно `sum(abs(start[i]-goal[i]))`. Решение `return sum(abs(a-b) for a,b in zip(start, goal))` прошло official L10. Таким образом, одноответный cache закрыт, но почти все hidden maps можно решить без чтения `grid` и обхода препятствий.

Приоритет: **P1**. Требуются не только pairwise different `best`, а хотя бы один обязательный detour/unreachable case на набор и acceptance invariant `best != Manhattan(start, goal)` для достаточной доли карт.

### P1 — `toolchoice`: пустой или нерелевантный compute-named вызов всё ещё засчитывается

Allowlist исправила прошлый `totally_irrelevant_tool`: он отклонён. Но `tasks/toolchoice/task.py:99-135` смотрит только на имя telemetry, а не на command, его успешное выполнение или связь output инструмента с ответом. На настоящем L10 верная цифра с `meta={'tools': ['bash']}` принята; так же приняты `browser_execute_script` и даже `read_commandments` из-за подстрок `execute`/`command` в `:93-101`. Следовательно модель может вызвать пустой `bash` и посчитать в уме — это именно указанный регресс-тест, и он проходит.

Приоритет: **P1**. Нужна нормализованная structured telemetry с kind/status и доказуемой computation action (или задача должна честно измерять лишь выбор класса инструмента, не заявляя, что им получен ответ).

### P1 — `webform`: вкладки и список проходятся изменением DOM, без click/drag

На L8 `docs/form.html:136-143` поля Billing/Access не disabled и не removed: у panel только CSS-класс `.hidden`. `collect()` без проверки visibility читает `invoice`/`seats` напрямую (`:260-285`). На L9 итогом считается порядок `#sortable li` в DOM (`:279-281`), а не transcript действий. Поэтому browser-evaluate может установить hidden inputs и вызвать `list.appendChild(...)`, затем `requestSubmit()`: ни клик вкладки, ни drag не требуются. Это дополнительно не проверяется scorer, который принимает только FNV code (`tasks/webform/task.py:135-147`).

Приоритет: **P1**. Если измеряется UI interaction, нужны event transcript/receipt и запрет evaluation shortcuts; если измеряется только конечный state, документация должна перестать требовать click/drag.

## Документация против кода

### P1 — публичная документация описывает другой benchmark

- `README.md:50-52` обещает English README, docs, site, CLI output **и task prompts**, но все текущие task prompts (`tasks/*/task.py`) и строки CLI (`run.py:59-82`, `:125-185`) написаны по-русски. Это не внутренняя деталь: язык prompt меняет измеряемую способность.
- `docs/TASKS.md:3` всё ещё говорит «Six tasks», а `README.md:19-28` и registry содержат восемь. `TASKS.md` не документирует реализованные `pathperf` и `toolchoice`; table categories (`:152-159`) не включает их веса. В `:136-139` осталась старая калибровка calc, в `:113-115` — старая модель honesty «до 4 fake», хотя `tasks/honesty/task.py:62-65` теперь сохраняет один real на верхних уровнях.
- `docs/TASKS.md:59-80` утверждает, что FNV невозможно получить без правильного заполнения, вкладки «must be clicked», а список нельзя пройти без drag. Код прямо опровергает все три утверждения: FNV опубликован в `tasks/webform/task.py:34-40`, controls не disabled, финальный DOM state читается без telemetry. Кроме того, `:77-80` называет реализацию pointer events, а listeners в `docs/form.html:215-239` — `mousedown/mousemove/mouseup`.
- `docs/TODO.md:9-34` всё ещё планирует `toolchoice`, причём как hidden-instance performance task. Реальная `tasks/toolchoice/task.py:42-86` — одна числовая задача, а эффективность не измеряется; performance task уже существует отдельно как `pathperf`.

Все пункты — **P1**: публичный англоязычный репозиторий сообщает поведение, которое текущий код не реализует. В `docs/index.html` есть лишь leaderboard; ссылки на запуск, task contract или manifest/coverage отсутствуют, поэтому внешний разработчик не может по сайту отличить актуальный полный result от неполного/несовместимого прогона.

## Что я изменил

Я не менял эталонные ответы или task protocol: явных ошибок эталонных значений в этом раунде не найдено. Созданы и ведутся только `docs/AUDIT_ROUND4.md` и обязательный `PROGRESS.nxb-audit-r4.md`. Пользователь самостоятельно изменил `bench/sandbox.py` во время аудита; его правка выше перепроверена.

## Что осталось нерешённым и почему

- P0 serializer/timing bypass требует изменения границы исполнения недоверенного Python, а не локальной правки expected; по прямой инструкции аудита он описан, но не внесён.
- P1 pathperf generator, telemetry toolchoice и webform event receipt меняют protocol и смысл измерения; оставлены как рекомендации, а не односторонние contract changes.
- P1 public documentation drift не исправлялся, поскольку пользователь запросил аудит, а не переписывание публичных обещаний. Для исправления нужен согласованный актуальный contract.

Проверки: `python -m compileall -q bench tasks run.py` и `git diff --check` завершились успешно. В worktree замечены сторонние изменения `docs/results.json`, `results/index.json`, карточки и results JSON; они не менялись в рамках аудита.
