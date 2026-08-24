# -*- coding: utf-8 -*-
"""Задача 7 — качество решения, а не только правильность.

Та же задача о кратчайшем пути, но карты БОЛЬШИЕ, а зачёт даётся только если
решение уложилось в бюджет времени. Наивный или неаккуратный алгоритм даст
верный ответ на маленькой сетке и упрётся в лимит на большой.

Главное: в промпте НЕ СКАЗАНО про оптимизацию, скорость или сложность.
Модель должна сама понять, что на сетке 60x60x60 перебор не пройдёт, и сама
выбрать нормальный алгоритм и аккуратную реализацию. Именно это здесь и
меряется — качество инженерного решения без напоминания.

Эффективность меряется ОТНОШЕНИЕМ к эталонной реализации, а не абсолютными
секундами: отношение почти не зависит от машины, на которой запускали, а
секунды зависят целиком. Эталон замеряется рядом с решением и берётся лучшим
из нескольких проходов — случайная нагрузка может замедлить проход, но не
может его ускорить. Итог переводится в оценку: optimal, good, acceptable,
inefficient.
"""
import collections
import random
import re
import time

NAME = 'pathperf'
TITLE = 'Эффективность решения'
MAX_LEVEL = 10
CATEGORIES = {'logic': 0.6, 'agentic': 0.4}
NEEDS = []

DIRS6 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]

# Во сколько раз решению разрешено быть медленнее эталона. Запас щедрый:
# наказываем не за неидеальность, а за алгоритмический промах.
SLACK = 8.0
MIN_BUDGET = 2.0     # секунд, чтобы не наказывать за накладные расходы запуска
HARD_TIMEOUT = 120   # общий предел на процесс


def _spec(level):
    """Размер сетки растёт так, чтобы плохой алгоритм гарантированно упёрся."""
    size = [20, 24, 28, 32, 36, 40, 46, 52, 58, 64][level - 1]
    density = 0.22
    return size, density


def _make_grid(rng, size, density):
    grid = [[[0] * size for _ in range(size)] for _ in range(size)]
    for x in range(size):
        for y in range(size):
            for z in range(size):
                if rng.random() < density:
                    grid[x][y][z] = -1
    grid[0][0][0] = 0
    grid[size - 1][size - 1][size - 1] = 0
    return grid


def _reference(grid, start, goal):
    size = len(grid)
    sx, sy, sz = start
    gx, gy, gz = goal
    dq = collections.deque([(sx, sy, sz, 0)])
    seen = [[[False] * size for _ in range(size)] for _ in range(size)]
    seen[sx][sy][sz] = True
    while dq:
        x, y, z, d = dq.popleft()
        if x == gx and y == gy and z == gz:
            return d
        for dx, dy, dz in DIRS6:
            nx, ny, nz = x + dx, y + dy, z + dz
            if 0 <= nx < size and 0 <= ny < size and 0 <= nz < size \
                    and not seen[nx][ny][nz] and grid[nx][ny][nz] != -1:
                seen[nx][ny][nz] = True
                dq.append((nx, ny, nz, d + 1))
    return -1



def _barrier_grid(rng, size, offset):
    """Стена с отверстием вне прямого коридора: обход обязателен.

    offset сдвигает финиш по оси y, чтобы у разных карт получались разные
    ответы, не ослабляя требование обхода.
    """
    grid = [[[0] * size for _ in range(size)] for _ in range(size)]
    wall = size // 2
    for y in range(size):
        for z in range(size):
            grid[wall][y][z] = -1
    hy = rng.randrange(size)
    grid[wall][hy][size - 1] = 0          # единственный проход, на дальней грани

    start = (0, 0, 0)
    goal = (size - 1, max(0, size - 1 - offset), 0)
    grid[start[0]][start[1]][start[2]] = 0
    grid[goal[0]][goal[1]][goal[2]] = 0
    best = _reference(grid, start, goal)
    if best < 0:
        raise RuntimeError('барьерная карта оказалась непроходимой')
    return grid, start, goal, best

def generate(level, rng):
    size, density = _spec(level)
    cases = []
    answers = set()
    for case_index in range(3):
        # У соседних дальних целей обычно разные манхэттенские расстояния.
        # Из-за препятствий длины всё же могут совпасть, поэтому принимаем
        # карту только после проверки эталоном. Это не позволяет один раз
        # посчитать ответ и вернуть тот же глобальный cache всем трём картам.
        for _attempt in range(100):
            grid = _make_grid(rng, size, density)
            start = (0, 0, 0)
            goal = (size - 1, size - 1, size - 1 - case_index)
            grid[goal[0]][goal[1]][goal[2]] = 0
            best = _reference(grid, start, goal)
            # Карта обязана ТРЕБОВАТЬ ОБХОДА. Одного условия «ответы различны»
            # оказалось мало: цели по одной оси сделали все пути прямыми, и на
            # 90 картах из 90 ответ совпал с манхэттенским расстоянием — то
            # есть однострочник sum(abs(a-b)) проходил десятый уровень, ни разу
            # не заглянув в grid.
            manhattan = sum(abs(a - b) for a, b in zip(start, goal))
            if best > manhattan and best not in answers:
                answers.add(best)
                cases.append({'grid': grid, 'start': list(start), 'goal': list(goal),
                              'best': best})
                break
        else:
            # Случайная карта почти всегда пропускает прямой путь, поэтому
            # обход приходится строить: стена поперёк маршрута с единственным
            # отверстием ВНЕ прямого коридора. Финиш лежит в плоскости z=0, а
            # отверстие — на дальней грани по z, иначе через дырку всё равно
            # проходил бы путь манхэттенской длины.
            grid, start, goal, best = _barrier_grid(rng, size, case_index)
            if best in answers:
                best_alt = None
                for shift in range(1, size):
                    grid, start, goal, best_alt = _barrier_grid(rng, size, shift)
                    if best_alt not in answers:
                        break
                best = best_alt
            answers.add(best)
            cases.append({'grid': grid, 'start': list(start), 'goal': list(goal),
                          'best': best})

    if len(answers) != len(cases):
        raise RuntimeError('ответы pathperf должны быть попарно различны')

    prompt = (
        'Напиши на Python функцию:\n\n'
        '    def solve(grid, start, goal):\n\n'
        'grid — трёхмерный список grid[x][y][z] размером %d x %d x %d. '
        'Значение -1 означает непроходимую клетку, 0 — свободную. '
        'start и goal — списки [x, y, z].\n\n'
        'Перемещаться можно на соседнюю клетку по шести направлениям вдоль осей, '
        'по одному шагу, стоимость каждого шага равна 1. Верни длину кратчайшего '
        'пути в шагах, а если пути нет — верни -1. Стартовая и финишная клетки '
        'всегда проходимы.\n\n'
        'Карты ты не видишь: функцию запустят на скрытых картах указанного размера.\n\n'
        'Ответ дай одним блоком кода, открывающимся ровно ```python и закрывающимся '
        'ровно ```. В блоке только импорты и определение функции solve. '
        'Ничего не печатай, input() не вызывай.\n\n'
        'NXB-CANARY-a7f3c1'
        % (size, size, size)
    )
    return prompt, {'cases': cases, 'size': size}


_BLOCK = re.compile(r'```(?:python|py)?[ \t]*\r?\n(.*?)```', re.S)


REPEATS = 3          # повторов замера, чтобы шум машины не решал исход


def _measure_reference(cases, repeats=REPEATS):
    """Замеряет эталон рядом с решением, а не в момент генерации задания.

    Берётся ЛУЧШИЙ из нескольких проходов, а не средний: минимум ближе к
    настоящей стоимости алгоритма, потому что случайная нагрузка на машину
    может замедлить проход, но не может его ускорить.
    """
    best_run = None
    for _ in range(max(1, repeats)):
        t0 = time.perf_counter()
        for c in cases:
            got = _reference(c['grid'], c['start'], c['goal'])
            if got != c['best']:
                raise RuntimeError('эталон pathperf изменился после генерации')
        dt = time.perf_counter() - t0
        best_run = dt if best_run is None else min(best_run, dt)
    return best_run


def _efficiency_grade(ratio):
    """Во сколько раз решение дороже эталона — в понятную оценку.

    Меряется отношение к эталону, а не абсолютные секунды: отношение почти не
    зависит от машины, на которой запускали, а секунды зависят целиком.
    """
    if ratio <= 1.5:
        return 'optimal'       # на уровне эталонного BFS
    if ratio <= 3.0:
        return 'good'
    if ratio <= SLACK:
        return 'acceptable'    # проходит, но заметно дороже
    return 'inefficient'


def score(output, expected):
    m = _BLOCK.search(output or '')
    if not m:
        return False, 'блок кода не найден', {'hint': 'Ответ должен быть внутри блока ```python.'}
    code = m.group(1)
    if 'def solve' not in code:
        return False, 'функция solve не определена', {
            'hint': 'В блоке должна быть функция solve.'}

    from bench import sandbox
    # Первый замер даёт безопасный process timeout. Второй делается сразу
    # после решения; итоговый бюджет использует оба соседних замера, поэтому
    # случайная нагрузка в далёкой фазе generate больше не меняет результат.
    ref_before = _measure_reference(expected['cases'])
    preliminary_budget = max(MIN_BUDGET, ref_before * SLACK)
    run = sandbox.run_solution(code, expected['cases'],
                               timeout=min(HARD_TIMEOUT, preliminary_budget * 3 + 15))

    if not run['ok']:
        if run.get('timeout'):
            return False, 'не уложилась в лимит времени', {
                'hint': 'Решение работает слишком долго на картах такого размера.',
                'slow': True}
        return False, run['error'], {'hint': 'Код не запускается либо падает с ошибкой.'}

    ref_after = _measure_reference(expected['cases'])
    ref_seconds = (ref_before + ref_after) / 2.0
    budget = max(MIN_BUDGET, ref_seconds * SLACK)

    total = 0.0
    for i, (got, c) in enumerate(zip(run['results'], expected['cases']), 1):
        if got['error']:
            return False, 'карта %d: %s' % (i, got['error']), {
                'hint': 'Функция падает с ошибкой на проверочных данных.'}
        if got['value'] != c['best']:
            return False, 'карта %d: ответ неверный' % i, {
                'hint': 'Ответ неверный хотя бы на одной карте.'}
        total += got['seconds']

    ratio = total / max(ref_seconds, 1e-6)
    extra = {'seconds': round(total, 3), 'budget': budget,
             'ref_seconds': round(ref_seconds, 3), 'ratio': round(ratio, 2),
             'efficiency': _efficiency_grade(ratio)}

    if total > budget:
        extra['slow'] = True
        extra['hint'] = ('Ответы верные, но решение слишком медленное для карт '
                         'такого размера. Нужен более эффективный подход.')
        return False, ('верно, но медленно: %.2f с при бюджете %.2f с (x%.1f от эталона)'
                       % (total, budget, ratio)), extra

    extra['hint'] = 'Проверка пройдена.'
    return True, ('верно за %.2f с, x%.1f от эталона — %s'
                  % (total, ratio, extra['efficiency'])), extra
