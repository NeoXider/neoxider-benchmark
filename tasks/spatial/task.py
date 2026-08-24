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
TITLE = 'Пространственное мышление'
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
    'наклонить вперёд':  ('верхняя грань становится передней',
                          lambda u, d, f, b, l, r: (b, f, u, d, l, r)),
    'наклонить назад':   ('верхняя грань становится задней',
                          lambda u, d, f, b, l, r: (f, b, d, u, l, r)),
    'повернуть вправо':  ('передняя грань становится правой',
                          lambda u, d, f, b, l, r: (u, d, l, r, b, f)),
    'повернуть влево':   ('передняя грань становится левой',
                          lambda u, d, f, b, l, r: (u, d, r, l, f, b)),
    'наклонить вправо':  ('верхняя грань становится правой',
                          lambda u, d, f, b, l, r: (l, r, f, b, d, u)),
    'наклонить влево':   ('верхняя грань становится левой',
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
    ('A B C D в ряд, E сверху над B, F снизу под B',
     {'A': (0, 1), 'B': (1, 1), 'C': (2, 1), 'D': (3, 1), 'E': (1, 0), 'F': (1, 2)}),
    ('A B C D в ряд, E сверху над C, F снизу под C',
     {'A': (0, 1), 'B': (1, 1), 'C': (2, 1), 'D': (3, 1), 'E': (2, 0), 'F': (2, 2)}),
    ('A B C в ряд, D сверху над A, E снизу под C, F справа от C',
     {'A': (0, 1), 'B': (1, 1), 'C': (2, 1), 'F': (3, 1), 'D': (0, 0), 'E': (2, 2)}),
    ('A B в ряд, C сверху над B, D снизу под B, E снизу под D, F справа от E',
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
        labels = {'U': 'красная', 'D': 'синяя', 'F': 'зелёная', 'B': 'жёлтая',
                  'L': 'белая', 'R': 'чёрная'}
        state = dict(labels)
        names = sorted(MOVES.keys())
        seq = [rng.choice(names) for _ in range(n_moves)]
        for s in seq:
            state = _apply_move(state, s)
        asked = rng.choice(['U', 'F', 'R', 'L', 'D'])
        pos = {'U': 'сверху', 'D': 'снизу', 'F': 'спереди',
               'L': 'слева', 'R': 'справа'}[asked]
        legend = '\n'.join('- %s: %s' % (n, MOVES[n][0]) for n in names)
        prompt = (
            'Куб лежит перед тобой. Его грани окрашены так: сверху красная, снизу синяя, '
            'спереди зелёная, сзади жёлтая, слева белая, справа чёрная.\n\n'
            'Куб поворачивают целиком на 90 градусов. Движения определены так:\n%s\n\n'
            'Выполни последовательность:\n%s\n\n'
            'Какая грань окажется %s?\n\n'
            'Ответь ровно одним словом — названием цвета в именительном падеже женского рода '
            '(например: зелёная). Ничего больше не пиши.\n\n'
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
            'Дана развёртка куба из шести квадратов, обозначенных буквами A, B, C, D, E, F.\n'
            'Расположение квадратов: %s.\n\n'
            'Развёртку сворачивают в куб. Какой квадрат окажется на грани, '
            'противоположной квадрату %s?\n\n'
            'Ответь ровно одной заглавной буквой. Ничего больше не пиши.\n\n'
            'NXB-CANARY-a7f3c1' % (desc, a)
        )
        return prompt, {'kind': 'word', 'answer': b}

    # Уровни 8-10: траектория точки в объёме
    size = [4, 5, 6][level - 8]
    steps = [5, 7, 9][level - 8]
    pos = [rng.randrange(size), rng.randrange(size), rng.randrange(size)]
    start = list(pos)
    moves = []
    axis_names = {0: ('вправо', 'влево'), 1: ('вверх', 'вниз'), 2: ('вперёд', 'назад')}
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
        'Представь куб %d x %d x %d из клеток. Координаты клетки — (x, y, z), '
        'где x растёт вправо, y растёт вверх, z растёт вперёд. Отсчёт с нуля.\n\n'
        'Точка стоит в клетке (%d, %d, %d) и делает шаги по одной клетке:\n%s\n\n'
        'В какой клетке окажется точка?\n\n'
        'Ответь ровно в формате (x, y, z) — три числа в скобках через запятую и пробел. '
        'Ничего больше не пиши.\n\n'
        'NXB-CANARY-a7f3c1'
        % (size, size, size, start[0], start[1], start[2],
           '\n'.join('%d. %s' % (i, m) for i, m in enumerate(moves, 1)))
    )
    return prompt, {'kind': 'coord', 'answer': '(%d, %d, %d)' % tuple(pos)}


def score(output, expected):
    text = (output or '').strip()
    if not text:
        return False, 'пустой ответ'
    if expected['kind'] == 'coord':
        m = re.findall(r'\(\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*\)', text)
        if not m:
            return False, 'координаты не найдены в ответе'
        got = re.sub(r'\s+', '', m[-1])
        want = re.sub(r'\s+', '', expected['answer'])
        return (got == want), 'ответ %s, эталон %s' % (got, want)

    want = expected['answer']
    # берём последнее непустое слово/букву — модели любят дописывать пояснение
    tokens = re.findall(r'[A-FА-Яа-яЁё]+', text)
    if not tokens:
        return False, 'ответ не распознан'
    got = tokens[-1]
    ok = got.lower().strip('.') == want.lower()
    return ok, 'ответ %r, эталон %r' % (got, want)
