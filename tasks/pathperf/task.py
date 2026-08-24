# -*- coding: utf-8 -*-
"""Задача 7 — качество решения, а не только правильность.

Та же задача о кратчайшем пути, но карты БОЛЬШИЕ, а зачёт даётся только если
решение уложилось в бюджет времени. Наивный или неаккуратный алгоритм даст
верный ответ на маленькой сетке и упрётся в лимит на большой.

Главное: в промпте НЕ СКАЗАНО про оптимизацию, скорость или сложность.
Модель должна сама понять, что на сетке 60x60x60 перебор не пройдёт, и сама
выбрать нормальный алгоритм и аккуратную реализацию. Именно это здесь и
меряется — качество инженерного решения без напоминания.

Бюджет времени считается от эталонной реализации на той же машине, а не
абсолютной константой: иначе результат зависел бы от того, где запускали.
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


def generate(level, rng):
    size, density = _spec(level)
    cases = []
    ref_total = 0.0
    for _ in range(3):
        grid = _make_grid(rng, size, density)
        start, goal = (0, 0, 0), (size - 1, size - 1, size - 1)
        t0 = time.perf_counter()
        best = _reference(grid, start, goal)
        ref_total += time.perf_counter() - t0
        cases.append({'grid': grid, 'start': list(start), 'goal': list(goal),
                      'best': best})

    budget = max(MIN_BUDGET, ref_total * SLACK)

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
    return prompt, {'cases': cases, 'budget': round(budget, 3),
                    'ref_seconds': round(ref_total, 3), 'size': size}


_BLOCK = re.compile(r'```(?:python|py)?[ \t]*\r?\n(.*?)```', re.S)


def score(output, expected):
    m = _BLOCK.search(output or '')
    if not m:
        return False, 'блок кода не найден', {'hint': 'Ответ должен быть внутри блока ```python.'}
    code = m.group(1)
    if 'def solve' not in code:
        return False, 'функция solve не определена', {
            'hint': 'В блоке должна быть функция solve.'}

    from bench import sandbox
    budget = expected['budget']
    run = sandbox.run_solution(code, expected['cases'],
                               timeout=min(HARD_TIMEOUT, budget * 3 + 15))

    if not run['ok']:
        if run.get('timeout'):
            return False, 'не уложилась в лимит времени', {
                'hint': 'Решение работает слишком долго на картах такого размера.',
                'slow': True}
        return False, run['error'], {'hint': 'Код не запускается либо падает с ошибкой.'}

    total = 0.0
    for i, (got, c) in enumerate(zip(run['results'], expected['cases']), 1):
        if got['error']:
            return False, 'карта %d: %s' % (i, got['error']), {
                'hint': 'Функция падает с ошибкой на проверочных данных.'}
        if got['value'] != c['best']:
            return False, 'карта %d: ответ неверный' % i, {
                'hint': 'Ответ неверный хотя бы на одной карте.'}
        total += got['seconds']

    ratio = total / max(expected['ref_seconds'], 1e-6)
    extra = {'seconds': round(total, 3), 'budget': budget,
             'ref_seconds': expected['ref_seconds'], 'ratio': round(ratio, 2)}

    if total > budget:
        extra['slow'] = True
        extra['hint'] = ('Ответы верные, но решение слишком медленное для карт '
                         'такого размера. Нужен более эффективный подход.')
        return False, ('верно, но медленно: %.2f с при бюджете %.2f с (x%.1f от эталона)'
                       % (total, budget, ratio)), extra

    extra['hint'] = 'Проверка не пройдена.'
    return True, ('верно за %.2f с при бюджете %.2f с (x%.1f от эталона)'
                  % (total, budget, ratio)), extra
