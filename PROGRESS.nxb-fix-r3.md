# Summary (TL;DR)

Цель: исправить восемь находок раунда 3, проверяя исходный контрпример после каждой правки.
Статус: аудит прочитан; начат P0-1. Webform намеренно вне изменений.

# Checklist

- [x] Прочитать `docs/AUDIT_ROUND3.md` целиком
- [x] P0-1: учитывать импорт/top-level в `pathperf`
- [x] P0-2: гарантировать разные ответы карт `pathperf`
- [x] P0-3: стабилизировать бюджет `pathperf`
- [x] P0-4: allowlist вычислительных инструментов `toolchoice`
- [~] P0-5: перестроить шкалу `calc` и просмотреть L1–L10
- [ ] P1-6: сохранить real/fake смесь `honesty` L9–L10
- [ ] P1-7: сделать состав/порядок карт `path3d` непредсказуемым
- [ ] P2-8: строгий однострочный формат `calc` и `spatial`
- [ ] Smoke: все 8 задач, уровни 1/5/10
- [ ] Дописать `docs/AUDIT_ROUND3.md`

# Log

- 2026-08-24: `PROGRESS.nxb-fix-r3.md` отсутствовал; создан. Полностью прочитан `docs/AUDIT_ROUND3.md`; первый вывод PowerShell был mojibake, дальнейшее чтение — с явным UTF-8.
- 2026-08-24: P0-1 до правки воспроизведён на seeded L10: monkeypatch `json.load` прошёл, `ok=true`, `seconds=0.0`, `best=[189,189,189]`.
- 2026-08-24: P0-1 исправлен в `bench/sandbox.py`: `json.load`/clock захватываются до solution module, setup/import/top-level добавлены к первому таймингу. Тот же exploit: `ok=false`, `карта 1: KeyError`; контрольный BFS с top-level `sleep(0.2)`: `ok=true`, `seconds=1.601`.
- 2026-08-24: P0-2 до правки: cache-first прошёл seeded L10 за `0.465 с`, ответы `[189,189,189]`. Генератор теперь принимает только достижимые карты с попарно различными эталонами и проверяет инвариант; после правки ответы `[189,188,187]`, exploit отклонён на карте 2.
- 2026-08-24: P0-3 до правки: controlled `sleep(0.5)` только в generate/reference при одинаковых cases раздул budget `5.976→19.101`. Калибровка перенесена в score: reference измеряется до/после solution. После правки одинаковый synthetic run 7.50 с отклонён при budget `6.006` и `5.881` независимо от задержки generate.
- 2026-08-24: P0-4 до правки: правильный L10 + `totally_irrelevant_tool` прошёл. Добавлен substring allowlist вычислительных tools и обязательный compute-call при доступной telemetry. После: irrelevant/search/read fail, `functions.shell_command` pass, отсутствующая telemetry остаётся unmeasured/pass.

# Conclusions / next steps

Сейчас: перестроить `calc` и вручную просмотреть seeded L1–L10.
