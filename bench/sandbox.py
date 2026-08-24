# -*- coding: utf-8 -*-
"""Запуск кода модели в отдельном процессе, с таймаутом и замером времени.

Две причины не делать exec прямо в процессе бенчмарка:

1. Безопасность. Чужой код получал доступ к кадру проверяльщика и мог достать
   оттуда эталонные ответы, а бесконечный цикл вешал весь прогон навсегда.
2. Замер. Честно измерить время решения можно, только изолировав его от всего
   остального: импортов бенчмарка, сборки мусора чужих объектов и прочего шума.

Возвращает результаты по каждому случаю и время выполнения каждого.
"""
import json
import os
import subprocess
import sys
import tempfile

# Мини-харнесс, который запускается в отдельном процессе. Он получает путь к
# файлу с кодом решения и путь к файлу с задачами, а печатает JSON с ответами
# и таймингами. Ничего из бенчмарка он не импортирует.
_HARNESS = r'''
import json, sys, time, runpy

sol_path, cases_path = sys.argv[1], sys.argv[2]

# Ссылки на сериализатор и вывод захватываются ДО загрузки решения. Иначе
# недоверенный код подменял json.dumps в общем модуле и проставлял всем
# результатам seconds=0 уже на выходе: решение спало 2.4 секунды и
# засчитывалось как «0.00 с», то есть как идеально оптимизированное.
clock = time.perf_counter
_dumps = json.dumps
_write = sys.stdout.write

# Вход читаем ДО загрузки решения и держим только в памяти. Иначе решение
# успевало переписать cases.json пустым списком: харнесс возвращал ноль
# результатов, zip в проверяльщике проходил по пустому списку, и уровень
# засчитывался, ничего не проверив. У pathperf это выглядело как «0.00 с»,
# то есть как идеально оптимизированное решение.
with open(cases_path, encoding="utf-8") as fh:
    cases = json.load(fh)

setup_t0 = clock()
ns = runpy.run_path(sol_path)
setup_seconds = clock() - setup_t0

solve = ns.get("solve")
if not callable(solve):
    print(json.dumps({"error": "solve is not defined"}))
    raise SystemExit(0)

out = []
for index, c in enumerate(cases):
    t0 = clock()
    try:
        val = solve(c["grid"], list(c["start"]), list(c["goal"]))
        err = None
    except Exception as e:
        val, err = None, "%s: %s" % (type(e).__name__, e)
    dt = clock() - t0
    if index == 0:
        # Импорт решения и его top-level код входят в измеряемое время:
        # иначе вычисление выносилось из-под таймера на верхний уровень.
        dt += setup_seconds
    if not isinstance(val, (int, float)) and val is not None:
        val, err = None, "returned %s instead of a number" % type(val).__name__
    out.append({"value": val, "error": err, "seconds": dt})

payload = {"results": out, "n_cases": len(cases), "wall": clock() - setup_t0}
_write(_dumps(payload))
_write(chr(10))
'''


def run_solution(code, cases, timeout=60, isolate_cases=False):
    """Прогоняет solve(grid, start, goal) на списке случаев.

    Возвращает dict:
        ok       — удалось ли вообще выполнить
        error    — текст ошибки, если нет
        results  — [{'value', 'error', 'seconds'}, ...]
        seconds  — общее время процесса
    """
    if isolate_cases:
        # Для задач, где скорость не оценивается, каждый case получает новый
        # процесс и новое состояние module globals. Решение видит только свою
        # карту: порядок вызовов и состав соседних карт использовать нельзя.
        import time as _t
        deadline = _t.monotonic() + timeout
        results = []
        seconds = 0.0
        for case in cases:
            remaining = deadline - _t.monotonic()
            if remaining <= 0:
                return {'ok': False, 'error': 'time limit of %g s exceeded' % timeout,
                        'results': results, 'seconds': seconds,
                        'timeout': True}
            run = run_solution(code, [case], timeout=remaining)
            seconds += run.get('seconds', 0.0)
            if not run['ok']:
                run['seconds'] = seconds
                return run
            results.extend(run['results'])
        return {'ok': True, 'error': None, 'results': results, 'seconds': seconds}

    tmp = tempfile.mkdtemp(prefix='nxb_')
    sol = os.path.join(tmp, 'solution.py')
    dat = os.path.join(tmp, 'cases.json')
    har = os.path.join(tmp, 'harness.py')
    try:
        with open(sol, 'w', encoding='utf-8') as fh:
            fh.write(code)
        # В файл уходят ТОЛЬКО входные данные. Эталонные ответы остаются в
        # процессе бенчмарка: раньше сюда клался весь case вместе с полем
        # 'best', и решение из четырёх строк, читающее cases.json, проходило
        # проверку за 0.01 секунды — то есть выглядело как идеально
        # оптимизированный алгоритм.
        with open(dat, 'w', encoding='utf-8') as fh:
            json.dump([{'grid': c['grid'], 'start': c['start'], 'goal': c['goal']}
                       for c in cases], fh)
        with open(har, 'w', encoding='utf-8') as fh:
            fh.write(_HARNESS)

        import time as _t
        t0 = _t.time()
        try:
            p = subprocess.run([sys.executable, har, sol, dat],
                               capture_output=True, timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired:
            return {'ok': False, 'error': 'time limit of %g s exceeded' % timeout,
                    'results': [], 'seconds': timeout, 'timeout': True}
        secs = _t.time() - t0

        out = p.stdout.decode('utf-8', 'replace').strip()
        if not out:
            err = p.stderr.decode('utf-8', 'replace').strip()[-300:]
            return {'ok': False, 'error': err or 'the solution returned nothing',
                    'results': [], 'seconds': secs}
        try:
            data = json.loads(out.splitlines()[-1])
        except ValueError:
            return {'ok': False, 'error': 'could not parse the harness output',
                    'results': [], 'seconds': secs}
        if data.get('error'):
            return {'ok': False, 'error': data['error'], 'results': [], 'seconds': secs}
        results = data.get('results') or []
        if len(results) != len(cases):
            # Страховка на случай, если решение всё же повлияет на состав входа.
            return {'ok': False,
                    'error': 'the solution returned %d answers instead of %d'
                             % (len(results), len(cases)),
                    'results': [], 'seconds': secs}
        # Сверка: сумма заявленных времён не может быть заметно меньше времени,
        # реально проведённого в решении. Это ловит любую подделку тайминга,
        # включая ту, что мы ещё не придумали.
        claimed = sum((r.get('seconds') or 0) for r in results)
        inside = data.get('wall')
        if inside is not None and claimed + 0.25 < inside * 0.5:
            return {'ok': False,
                    'error': 'claimed time %.2f s does not agree with the actual %.2f s'
                             % (claimed, inside),
                    'results': [], 'seconds': secs}
        return {'ok': True, 'error': None, 'results': results, 'seconds': secs}
    finally:
        for f in (sol, dat, har):
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass
