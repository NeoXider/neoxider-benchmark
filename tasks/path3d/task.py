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
TITLE = 'Pathfinding in 3D'
MAX_LEVEL = 10
# Версию поднимает тот, кто меняет generate или score: иначе допрогон
# подмешает к новым уровням старые, посчитанные по другим правилам.
VERSION = 1
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
        raise RuntimeError('barrier map turned out to be impassable')
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
        rules = ('Movement is allowed to a neighboring cell along six directions '
                 '(along the X, Y, Z axes, one step at a time). Each step costs 1. '
                 'Return the length of the shortest path in steps.')
    elif mode == 'moves26':
        rules = ('Movement is allowed to any of the 26 neighboring cells, including '
                 'diagonals (any combination of offsets -1, 0, +1 except all-zero). '
                 'A step costs 1 regardless of whether it is diagonal. Return the '
                 'length of the shortest path in steps.')
    else:
        rules = ('Movement is allowed to any of the 26 neighboring cells. Cells have '
                 'weights: the number in a cell is the cost of entering it. The path '
                 'cost includes the weight of the start cell and the weight of the '
                 'goal cell. Return the minimal total cost.')

    prompt = (
        'Write a Python function that solves the shortest-path problem in a '
        'three-dimensional grid.\n\n'
        'The signature is exactly:\n\n'
        '    def solve(grid, start, goal):\n\n'
        'Arguments:\n'
        '- grid is a three-dimensional list grid[x][y][z] of size %d x %d x %d;\n'
        '  the value -1 means an impassable obstacle%s;\n'
        '- start is the [x, y, z] list of the start cell;\n'
        '- goal is the [x, y, z] list of the goal cell.\n\n'
        'Movement rules: %s\n\n'
        'If no path exists, return -1. The start and goal cells are always '
        'passable.\n\n'
        'IMPORTANT: you do not see the maps themselves — your function will be run '
        'on hidden maps generated separately. Therefore solve the problem in its '
        'general form; do not fit it to an example.\n\n'
        'Give the answer as one code block opening with exactly ```python and '
        'closing with exactly ```. The block must contain only the definition of '
        'the solve function and, if needed, imports. No code outside the function, '
        'print nothing, do not call input().\n\n'
        'NXB-CANARY-a7f3c1'
        % (size, size, size,
           ', 0 means a free cell' if mode != 'weighted'
           else ', a positive number is the weight of entering the cell',
           rules)
    )
    return prompt, {'cases': cases, 'mode': mode}


_BLOCK = re.compile(r'```(?:python|py)?[ \t]*\r?\n(.*?)```', re.S)


def score(output, expected):
    m = _BLOCK.search(output or '')
    if not m:
        return False, 'code block not found'
    code = m.group(1)
    if 'def solve' not in code:
        return False, 'function solve not defined'

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
            return False, 'time limit exceeded', {
                'hint': 'The solution runs for too long.'}
        return False, run['error'], {'hint': 'The code does not run or crashes with an error.'}

    for i, (got, c) in enumerate(zip(run['results'], expected['cases']), 1):
        if got['error']:
            return False, 'map %d: %s' % (i, got['error']), {
                'hint': 'The function crashes with an error on the test data.'}
        if got['value'] != c['best']:
            return False, 'map %d: wrong answer' % i, {
                'hint': 'The answer is wrong on at least one map.'}
    return True, 'all %d maps passed' % len(expected['cases'])
