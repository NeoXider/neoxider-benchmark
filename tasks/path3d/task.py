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


def _make_grid(rng, size, density, mode):
    """Строит карту, гарантированно имеющую решение."""
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
        if best is not None:
            return grid, start, goal, best
    raise RuntimeError('не удалось сгенерировать проходимую карту')


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
    cases = []
    for _ in range(4):
        grid, start, goal, best = _make_grid(rng, size, density, mode)
        cases.append({'grid': grid, 'start': list(start), 'goal': list(goal), 'best': best})

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

    ns = {}
    try:
        exec(compile(code, '<solution>', 'exec'), ns)
    except Exception as e:
        return False, 'код не исполняется: %s: %s' % (type(e).__name__, e)

    fn = ns.get('solve')
    if not callable(fn):
        return False, 'solve не является функцией'

    for i, c in enumerate(expected['cases'], 1):
        try:
            got = fn([[list(col) for col in plane] for plane in c['grid']],
                     list(c['start']), list(c['goal']))
        except Exception as e:
            return False, 'карта %d: исключение %s: %s' % (i, type(e).__name__, e)
        if got != c['best']:
            return False, 'карта %d: вернула %r, эталон %r' % (i, got, c['best'])
    return True, 'все %d карт пройдены' % len(expected['cases'])
