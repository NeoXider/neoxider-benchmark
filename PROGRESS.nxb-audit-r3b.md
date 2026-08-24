# Summary (TL;DR)

Аудит калибровки и обходов восьми задач завершён; полный отчёт — `docs/AUDIT_ROUND3.md`.
Главное: calc L3 слишком тяжёл; верх spatial/honesty/toolchoice инвертирован; pathperf имеет три P0 обхода. Исправлены два ошибочных success-hint.

# Checklist

- [x] Прочитать генераторы/проверки и зафиксировать поверхность обходов
- [x] Сгенерировать и вручную оценить уровни 1, 2, 3, 9, 10 (seed 20260824)
- [x] Проверить исполняемые контрпримеры для восьми задач
- [x] Исправить только явные ошибки эталона и перепроверить
- [x] Завершить `docs/AUDIT_ROUND3.md`

# Log

- 2026-08-24: чекпоинт отсутствовал; найдены все 8 `tasks/*/task.py`. Начат статический разбор.
- 2026-08-24: первый `rg tasks/*/task.py` не сработал из-за glob в PowerShell (`os error 123`); файлы целы, повторяю поиском по каталогу.
- 2026-08-24: прочитаны все 8 генераторов/scorer и `bench/sandbox.py`. Первично: `path3d` имеет нулевой логический рост внутри 1–4/5–7/8–10; `pathperf` бюджет измеряется при генерации, а решение — позже; `toolchoice` считает любой непустой список tools доказательством вычисления.
- 2026-08-24: с точным RNG сгенерированы L1/2/3/9/10 и дополнительные L7/8 всех задач. Таблица записана в `docs/AUDIT_ROUND3.md`; ключевые инверсии: calc L3>L7, spatial L10<L7, honesty L10<L7, toolchoice L10<L9.
- 2026-08-24: первый counterexample harness: прошли count/calc/path3d/pathperf/webform/toolchoice. `pathperf`: cache-first-map прошёл L10 (0.37 s); те же карты с budget 5.742/17.659 дали fail/pass для решения 7.50 s. Spatial/honesty строки исказились при передаче кириллицы через PowerShell pipe и не распознаны; повторяю Unicode-safe.
- 2026-08-24: Unicode-safe повтор подтвердил spatial (лишние `A B C !!!` приняты) и honesty (4×`НЕ НАЙДЕНО` на L10 приняты). Найдены ошибочные success-hints в pathperf/toolchoice; каталог `tests/` отсутствует (`rg: tests: Не удается найти указанный файл`).
- 2026-08-24: дополнительный P0 pathperf подтверждён: подмена `json.load` вычислила BFS до таймера, L10 принят за 0.00 s (ratio 0.0). Все обходы и приоритеты записаны в `docs/AUDIT_ROUND3.md`.
- 2026-08-24: verification: imports всех 8 задач OK; toolchoice success/failure hints OK. Первый pathperf assertion с кириллическим literal в PowerShell pipe дал `AssertionError`; повторяю через Unicode escapes. Обнаружены несвязанные user-файлы/изменения — не трогаю.
- 2026-08-24: Unicode-safe pathperf assertion OK; targeted `git diff --check` OK (только предупреждение LF→CRLF). Аудит завершён, все чекбоксы закрыты.

# Conclusions / next steps

Заказчику: сначала закрыть P0 pathperf/toolchoice/webform, затем пересобрать шкалу calc и инвертированные верхние уровни. Антиобходные/калибровочные изменения не внесены без отдельного решения по дизайну.
