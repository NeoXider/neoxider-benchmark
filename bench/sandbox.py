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
# Решение выполняется в том же интерпретаторе и может менять общие модули.
# Захватываем функции ДО runpy: иначе top-level monkeypatch json.load выносил
# всё вычисление из таймера, а затем solve() возвращала готовый ответ.
clock = time.perf_counter
load_cases = json.load
setup_t0 = clock()
ns = runpy.run_path(sol_path)
solve = ns.get("solve")
if not callable(solve):
    print(json.dumps({"error": "solve не определена"}))
    raise SystemExit(0)

with open(cases_path, encoding="utf-8") as fh:
    cases = load_cases(fh)
setup_seconds = clock() - setup_t0

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
        # В измеряемую зону входят импорт решения и любой его top-level код.
        # Загрузку входа тоже оставляем внутри: это небольшой одинаковый для
        # всех решений overhead, зато работу нельзя спрятать до solve().
        dt += setup_seconds
    if not isinstance(val, (int, float)) and val is not None:
        val, err = None, "вернула %s вместо числа" % type(val).__name__
    out.append({"value": val, "error": err, "seconds": dt})

print(json.dumps({"results": out}))
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
                return {'ok': False, 'error': 'превышен лимит времени %g с' % timeout,
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
            return {'ok': False, 'error': 'превышен лимит времени %g с' % timeout,
                    'results': [], 'seconds': timeout, 'timeout': True}
        secs = _t.time() - t0

        out = p.stdout.decode('utf-8', 'replace').strip()
        if not out:
            err = p.stderr.decode('utf-8', 'replace').strip()[-300:]
            return {'ok': False, 'error': err or 'решение ничего не вернуло',
                    'results': [], 'seconds': secs}
        try:
            data = json.loads(out.splitlines()[-1])
        except ValueError:
            return {'ok': False, 'error': 'вывод харнесса не разобран',
                    'results': [], 'seconds': secs}
        if data.get('error'):
            return {'ok': False, 'error': data['error'], 'results': [], 'seconds': secs}
        return {'ok': True, 'error': None, 'results': data['results'], 'seconds': secs}
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
