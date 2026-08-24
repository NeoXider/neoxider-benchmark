# -*- coding: utf-8 -*-
"""Задача 2 — программирование: кратчайший путь в 3D-сетке с препятствиями.

Модель НЕ видит уровни. Она пишет функцию solve(grid, start, goal), которую мы
затем прогоняем на скрытых сгенерированных картах и сверяем длину найденного
пути с эталоном (BFS). Это меряет именно умение написать корректный алгоритм,
а не подогнать ответ под конкретный лабиринт.

Уровни усложняются по трём осям: размер сетки, плотность препятствий и правила
перемещения (6 направлений -> 26 направлений -> веса клеток -> телепорты).
"""
import collections
import json
import random
import re

NAME = 'path3d'
TITLE = 'Поиск пути в 3D'
MAX_LEVEL = 10
CATEGORIES = {'logic': 0.7, 'spatial': 0.3}
NEEDS = []

DIRS6 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
DIRS26 = [(dx, dy, dz)
          for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
          if (dx, dy, dz) != (0, 0, 0)]


def _spec(level):
    """Параметры уровня: размер, плотность, режим."""
    size = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14][level - 1]
    density = [0.10, 0.15, 0.20, 0.25, 0.28, 0.30, 0.32, 0.34, 0.36, 0.38][level - 1]
    if level <= 4:
        mode = 'moves6'
    elif level <= 7:
        mode = 'moves26'
    else:
        mode = 'weighted'
    return size, density, mode


def _lower_bound(start, goal, mode):
    """Длина пути, если бы препятствий не было.

    Нужна, чтобы отбирать карты, где обход ОБЯЗАТЕЛЕН. Без этого отбора
    генератор выдавал карты, на которых ответ всегда равнялся расстоянию по
    прямой, и решение, полностью игнорирующее grid, проходило уровни 1-4
    (проверено: 960 карт из 960).
    """
    d = [abs(a - b) for a, b in zip(start, goal)]
    return sum(d) if mode == 'moves6' else max(d)


def _sealed_grid(rng, size, mode):
    """Карта, где финиш заведомо замурован: правильный ответ -1."""
    grid = [[[0] * size for _ in range(size)] for _ in range(size)]
    if mode == 'weighted':
        grid = [[[1] * size for _ in range(size)] for _ in range(size)]
    gx = gy = gz = size - 1
    for dx, dy, dz in DIRS26:
        x, y, z = gx + dx, gy + dy, gz + dz
        if 0 <= x < size and 0 <= y < size and 0 <= z < size:
            grid[x][y][z] = -1
    grid[gx][gy][gz] = 1 if mode == 'weighted' else 0
    grid[0][0][0] = 1 if mode == 'weighted' else 0
    return grid, (0, 0, 0), (gx, gy, gz), -1


def _make_grid(rng, size, density, mode, require_detour=False):
    """Строит карту с решением. require_detour — путь по прямой не должен подходить."""
    dirs = DIRS6 if mode == 'moves6' else DIRS26
    for _ in range(400):
        grid = [[[0] * size for _ in range(size)] for _ in range(size)]
        for x in range(size):
            for y in range(size):
                for z in range(size):
                    if rng.random() < density:
                        grid[x][y][z] = -1
        start = (0, 0, 0)
        goal = (size - 1, size - 1, size - 1)
        grid[0][0][0] = 0
        grid[size - 1][size - 1][size - 1] = 0
        if mode == 'weighted':
            for x in range(size):
                for y in range(size):
                    for z in range(size):
                        if grid[x][y][z] == 0:
                            grid[x][y][z] = rng.choice([1, 1, 1, 2, 3])
            grid[0][0][0] = 1
            grid[size - 1][size - 1][size - 1] = 1
        best = _reference(grid, start, goal, dirs, mode)
        if best is None:
            continue
        if require_detour and mode != 'weighted' and best <= _lower_bound(start, goal, mode):
            continue          # прямой путь прошёл — карта ничего не проверяет
        return grid, start, goal, best
    # не удалось набрать обход случайно — строим барьер с одним проходом
    return _barrier_grid(rng, size, mode, dirs)


def _barrier_grid(rng, size, mode, dirs):
    """Стена поперёк маршрута с отверстием ВНЕ прямого коридора.

    Тонкость: если финиш в противоположном углу, то через любое отверстие в
    перпендикулярной стене всё равно проходит путь манхэттенской длины —
    барьер ничего не проверяет. Поэтому финиш ставится в плоскость z=0, а
    единственное отверстие — на z=size-1, то есть заведомо в стороне:
    пройти можно только сделав крюк по оси z и вернувшись.
    """
    fill = 1 if mode == 'weighted' else 0
    grid = [[[fill] * size for _ in range(size)] for _ in range(size)]
    wall = size // 2
    for y in range(size):
        for z in range(size):
            grid[wall][y][z] = -1
    hy = rng.randrange(size)
    hz = size - 1
    grid[wall][hy][hz] = fill

    start = (0, 0, 0)
    goal = (size - 1, size - 1, 0)
    grid[start[0]][start[1]][start[2]] = fill
    grid[goal[0]][goal[1]][goal[2]] = fill
    best = _reference(grid, start, goal, dirs, mode)
    if best is None:
        raise RuntimeError('барьерная карта оказалась непроходимой')
    return grid, start, goal, best


def _reference(grid, start, goal, dirs, mode):
    """Эталон: BFS для невзвешенных, Дейкстра для взвешенных."""
    size = len(grid)

    def passable(x, y, z):
        return 0 <= x < size and 0 <= y < size and 0 <= z < size and grid[x][y][z] != -1

    if mode != 'weighted':
        dq = collections.deque([(start, 0)])
        seen = {start}
        while dq:
            (x, y, z), d = dq.popleft()
            if (x, y, z) == goal:
                return d
            for dx, dy, dz in dirs:
                n = (x + dx, y + dy, z + dz)
                if n not in seen and passable(*n):
                    seen.add(n)
                    dq.append((n, d + 1))
        return None

    import heapq
    pq = [(grid[start[0]][start[1]][start[2]], start)]
    dist = {start: grid[start[0]][start[1]][start[2]]}
    while pq:
        d, (x, y, z) = heapq.heappop(pq)
        if (x, y, z) == goal:
            return d
        if d > dist.get((x, y, z), 1 << 60):
            continue
        for dx, dy, dz in dirs:
            n = (x + dx, y + dy, z + dz)
            if passable(*n):
                nd = d + grid[n[0]][n[1]][n[2]]
                if nd < dist.get(n, 1 << 60):
                    dist[n] = nd
                    heapq.heappush(pq, (nd, n))
    return None


def generate(level, rng):
    size, density, mode = _spec(level)
    # Набор карт подобран так, чтобы решение, игнорирующее препятствия, не
    # прошло: две карты требуют обхода, одна непроходима вовсе (ответ -1),
    # одна обычная случайная.
    cases = []
    for _ in range(2):
        grid, start, goal, best = _make_grid(rng, size, density, mode,
                                             require_detour=True)
        cases.append({'grid': grid, 'start': list(start), 'goal': list(goal), 'best': best})
    grid, start, goal, best = _sealed_grid(rng, size, mode)
    cases.append({'grid': grid, 'start': list(start), 'goal': list(goal), 'best': best})
    grid, start, goal, best = _make_grid(rng, size, density, mode)
    cases.append({'grid': grid, 'start': list(start), 'goal': list(goal), 'best': best})
    rng.shuffle(cases)

    if mode == 'moves6':
        rules = ('Перемещаться можно на соседнюю клетку по шести направлениям '
                 '(вдоль осей X, Y, Z, по одному шагу). Стоимость каждого шага равна 1. '
                 'Верни длину кратчайшего пути в шагах.')
    elif mode == 'moves26':
        rules = ('Перемещаться можно на любую из 26 соседних клеток, включая диагональные '
                 '(любая комбинация смещений -1, 0, +1, кроме нулевой). Стоимость шага '
                 'равна 1 независимо от диагональности. Верни длину кратчайшего пути в шагах.')
    else:
        rules = ('Перемещаться можно на любую из 26 соседних клеток. Клетки имеют вес: '
                 'число в клетке — это стоимость входа в неё. Стоимость пути включает '
                 'вес стартовой клетки и вес финишной. Верни минимальную суммарную стоимость.')

    prompt = (
        'Напиши на Python функцию решения задачи о кратчайшем пути в трёхмерной сетке.\n\n'
        'Сигнатура ровно такая:\n\n'
        '    def solve(grid, start, goal):\n\n'
        'Аргументы:\n'
        '- grid — трёхмерный список grid[x][y][z] размером %d x %d x %d;\n'
        '  значение -1 означает непроходимое препятствие%s;\n'
        '- start — список [x, y, z] стартовой клетки;\n'
        '- goal — список [x, y, z] финишной клетки.\n\n'
        'Правила перемещения: %s\n\n'
        'Если пути не существует, верни -1. Стартовая и финишная клетки всегда проходимы.\n\n'
        'ВАЖНО: сами карты ты не видишь — твою функцию запустят на скрытых картах, '
        'сгенерированных отдельно. Поэтому решай задачу в общем виде, не подгоняй под пример.\n\n'
        'Ответ дай одним блоком кода, открывающимся ровно ```python и закрывающимся ровно ```. '
        'В блоке только определение функции solve и, если нужно, импорты. '
        'Никакого кода вне функции, ничего не печатай, input() не вызывай.\n\n'
        'NXB-CANARY-a7f3c1'
        % (size, size, size,
           ', 0 — свободная клетка' if mode != 'weighted'
           else ', положительное число — вес входа в клетку',
           rules)
    )
    return prompt, {'cases': cases, 'mode': mode}


_BLOCK = re.compile(r'```(?:python|py)?[ \t]*\r?\n(.*?)```', re.S)


def score(output, expected):
    m = _BLOCK.search(output or '')
    if not m:
        return False, 'блок кода не найден'
    code = m.group(1)
    if 'def solve' not in code:
        return False, 'функция solve не определена'

    # Исполняем в отдельном процессе, а не exec в процессе бенчмарка:
    # чужой код мог добраться до кадра проверяльщика и вытащить эталоны, а
    # бесконечный цикл вешал весь прогон навсегда.
    from bench import sandbox
    # Каждый case запускается с чистым module state. Иначе решение могло
    # игнорировать grid и вернуть заученный список по номеру вызова.
    run = sandbox.run_solution(code, expected['cases'], timeout=60,
                               isolate_cases=True)
    if not run['ok']:
        if run.get('timeout'):
            return False, 'превышен лимит времени', {
                'hint': 'Решение работает слишком долго.'}
        return False, run['error'], {'hint': 'Код не запускается либо падает с ошибкой.'}

    for i, (got, c) in enumerate(zip(run['results'], expected['cases']), 1):
        if got['error']:
            return False, 'карта %d: %s' % (i, got['error']), {
                'hint': 'Функция падает с ошибкой на проверочных данных.'}
        if got['value'] != c['best']:
            return False, 'карта %d: ответ неверный' % i, {
                'hint': 'Ответ неверный хотя бы на одной карте.'}
    return True, 'все %d карт пройдены' % len(expected['cases'])
