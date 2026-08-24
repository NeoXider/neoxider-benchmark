# -*- coding: utf-8 -*-
"""Задача 4 — пространственное мышление без кода.

Модель мысленно вращает куб и сворачивает развёртки. Решить программой нельзя:
задача даётся текстом и ответ — короткая строка, а не алгоритм. Это отделяет
пространственное представление от умения писать код (задача 2).

Уровни: повороты одного куба -> развёртка -> развёртка плюс повороты ->
траектория точки в объёме.
"""
import random
import re

NAME = 'spatial'
TITLE = 'Spatial reasoning'
MAX_LEVEL = 10
CATEGORIES = {'spatial': 1.0}
NEEDS = []

# Грани куба: (верх, низ, перед, зад, лево, право) в текущей ориентации.
FACES = ('U', 'D', 'F', 'B', 'L', 'R')


# Каждое движение задаётся ЯВНО — какая грань куда переходит. Обтекаемые
# формулировки вроде «повернуть вправо» неоднозначны (объект вправо или
# наблюдатель?), и модель могла бы рассуждать верно, но получить незачёт.
# Значение — новое содержимое (U, D, F, B, L, R) из старого (u, d, f, b, l, r).
MOVES = {
    'tip forward':    ('the top face becomes the front face',
                       lambda u, d, f, b, l, r: (b, f, u, d, l, r)),
    'tip backward':   ('the top face becomes the back face',
                       lambda u, d, f, b, l, r: (f, b, d, u, l, r)),
    'turn right':     ('the front face becomes the right face',
                       lambda u, d, f, b, l, r: (u, d, l, r, b, f)),
    'turn left':      ('the front face becomes the left face',
                       lambda u, d, f, b, l, r: (u, d, r, l, f, b)),
    'roll right':     ('the top face becomes the right face',
                       lambda u, d, f, b, l, r: (l, r, f, b, d, u)),
    'roll left':      ('the top face becomes the left face',
                       lambda u, d, f, b, l, r: (r, l, f, b, u, d)),
}


def _apply_move(state, name):
    u, d, f, b, l, r = (state[k] for k in FACES)
    return dict(zip(FACES, MOVES[name][1](u, d, f, b, l, r)))

# --------------------------------------------------------------- развёртки
# Развёртка задаётся координатами клеток на плоскости: (столбец, строка),
# строка растёт вниз. Ответ (какие грани противоположны) НЕ вписывается руками,
# а вычисляется свёрткой — иначе легко ошибиться, что и произошло при первой
# попытке задать таблицу вручную.
_NETS = [
    ('A B C D in a row, E above B, F below B',
     {'A': (0, 1), 'B': (1, 1), 'C': (2, 1), 'D': (3, 1), 'E': (1, 0), 'F': (1, 2)}),
    ('A B C D in a row, E above C, F below C',
     {'A': (0, 1), 'B': (1, 1), 'C': (2, 1), 'D': (3, 1), 'E': (2, 0), 'F': (2, 2)}),
    ('A B C in a row, D above A, E below C, F to the right of C',
     {'A': (0, 1), 'B': (1, 1), 'C': (2, 1), 'F': (3, 1), 'D': (0, 0), 'E': (2, 2)}),
    ('A B in a row, C above B, D below B, E below D, F to the right of E',
     {'A': (0, 1), 'B': (1, 1), 'C': (1, 0), 'D': (1, 2), 'E': (1, 3), 'F': (2, 3)}),
]


def _neg(v):
    return (-v[0], -v[1], -v[2])


def _fold(cells):
    """Сворачивает развёртку и возвращает {метка: противоположная метка}.

    Каждой клетке сопоставляется тройка векторов (right, down, normal).
    Переход к соседу поворачивает базис на 90 градусов вокруг общего ребра.
    Грань куба однозначно задаётся нормалью, противоположные грани — нормали
    с обратным знаком.
    """
    pos2label = {p: l for l, p in cells.items()}
    root = next(iter(sorted(cells.items(), key=lambda kv: (kv[1][1], kv[1][0]))))
    start_pos = root[1]

    basis = {start_pos: ((1, 0, 0), (0, 1, 0), (0, 0, 1))}
    stack = [start_pos]
    while stack:
        p = stack.pop()
        right, down, normal = basis[p]
        for (dx, dy), nb in (((1, 0), 'r'), ((-1, 0), 'l'), ((0, 1), 'd'), ((0, -1), 'u')):
            q = (p[0] + dx, p[1] + dy)
            if q not in pos2label or q in basis:
                continue
            if nb == 'r':
                basis[q] = (normal, down, _neg(right))
            elif nb == 'l':
                basis[q] = (_neg(normal), down, right)
            elif nb == 'd':
                basis[q] = (right, normal, _neg(down))
            else:
                basis[q] = (right, _neg(normal), down)
            stack.append(q)

    if len(basis) != len(cells):
        raise ValueError('развёртка не связна')

    by_normal = {}
    for p, (_, _, n) in basis.items():
        by_normal[n] = pos2label[p]
    if len(by_normal) != 6:
        raise ValueError('развёртка не сворачивается в куб: граней %d' % len(by_normal))

    return {lab: by_normal[_neg(n)] for n, lab in by_normal.items()}


def generate(level, rng):
    if level <= 4:
        n_moves = [2, 3, 4, 6][level - 1]
        labels = {'U': 'red', 'D': 'blue', 'F': 'green', 'B': 'yellow',
                  'L': 'white', 'R': 'black'}
        state = dict(labels)
        names = sorted(MOVES.keys())
        seq = [rng.choice(names) for _ in range(n_moves)]
        for s in seq:
            state = _apply_move(state, s)
        asked = rng.choice(['U', 'F', 'R', 'L', 'D'])
        pos = {'U': 'on top', 'D': 'at the bottom', 'F': 'in front',
               'L': 'on the left', 'R': 'on the right'}[asked]
        legend = '\n'.join('- %s: %s' % (n, MOVES[n][0]) for n in names)
        prompt = (
            'A cube lies in front of you. Its faces are colored as follows: red on '
            'top, blue on the bottom, green in front, yellow at the back, white on '
            'the left, black on the right.\n\n'
            'The cube is rotated as a whole by 90 degrees. The moves are defined as '
            'follows:\n%s\n\n'
            'Perform the sequence:\n%s\n\n'
            'Which face ends up %s?\n\n'
            'Answer with exactly one word — the name of the color '
            '(for example: green). Write nothing else.\n\n'
            'NXB-CANARY-a7f3c1'
            % (legend,
               '\n'.join('%d. %s' % (i, s) for i, s in enumerate(seq, 1)),
               pos)
        )
        return prompt, {'kind': 'word', 'answer': state[asked]}

    if level <= 7:
        desc, cells = _NETS[(level - 5) % len(_NETS)]
        pairs = _fold(cells)
        a = rng.choice(sorted(pairs.keys()))
        b = pairs[a]
        prompt = (
            'Given is a net of a cube made of six squares labeled A, B, C, D, E, F.\n'
            'Arrangement of the squares: %s.\n\n'
            'The net is folded into a cube. Which square ends up on the face '
            'opposite square %s?\n\n'
            'Answer with exactly one capital letter. Write nothing else.\n\n'
            'NXB-CANARY-a7f3c1' % (desc, a)
        )
        return prompt, {'kind': 'word', 'answer': b}

    # Уровни 8-10: траектория точки в объёме
    size = [4, 5, 6][level - 8]
    steps = [5, 7, 9][level - 8]
    pos = [rng.randrange(size), rng.randrange(size), rng.randrange(size)]
    start = list(pos)
    moves = []
    axis_names = {0: ('right', 'left'), 1: ('up', 'down'), 2: ('forward', 'backward')}
    for _ in range(steps):
        ax = rng.randrange(3)
        d = rng.choice([1, -1])
        nv = pos[ax] + d
        if not (0 <= nv < size):
            d = -d
            nv = pos[ax] + d
        pos[ax] = nv
        moves.append(axis_names[ax][0 if d > 0 else 1])
    prompt = (
        'Picture a %d x %d x %d cube made of cells. Cell coordinates are (x, y, z), '
        'where x grows to the right, y grows upward, z grows forward. Counting '
        'starts at zero.\n\n'
        'A point stands in cell (%d, %d, %d) and makes single-cell steps:\n%s\n\n'
        'In which cell does the point end up?\n\n'
        'Answer exactly in the format (x, y, z) — three numbers in parentheses, '
        'comma- and space-separated. Write nothing else.\n\n'
        'NXB-CANARY-a7f3c1'
        % (size, size, size, start[0], start[1], start[2],
           '\n'.join('%d. %s' % (i, m) for i, m in enumerate(moves, 1)))
    )
    return prompt, {'kind': 'coord', 'answer': '(%d, %d, %d)' % tuple(pos)}


def score(output, expected):
    lines = (output or '').splitlines()
    if len(lines) != 1:
        return False, 'the answer must be exactly one line'
    text = lines[0].strip()
    if not text:
        return False, 'empty answer'
    if expected['kind'] == 'coord':
        m = re.fullmatch(r'\(\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*\)', text)
        if not m:
            return False, 'coordinates not found in the answer'
        got = re.sub(r'\s+', '', m.group(0))
        want = re.sub(r'\s+', '', expected['answer'])
        return (got == want), 'answer %s, expected %s' % (got, want)

    want = expected['answer']
    token = re.fullmatch(r'[A-Za-zА-Яа-яЁё]+', text)
    if not token:
        return False, 'answer not recognized'
    got = token.group(0)
    ok = got.lower() == want.lower()
    return ok, 'answer %r, expected %r' % (got, want)
