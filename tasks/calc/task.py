# -*- coding: utf-8 -*-
"""Задача 6 — точный счёт: длинные выражения и уравнения.

Ловит класс ошибок, которого нет в остальных задачах: не «не понял условие»,
а «сбился в середине длинной цепочки». Эталон считается точной рациональной
арифметикой (Fraction), поэтому ответ либо совпадает, либо нет — округление
не спасает.

Уровни — по три на сферу:
  1-3   длинное выражение со скобками: целые -> дроби -> дроби со степенями
  4-6   одно неизвестное: простое -> x по обе стороны -> с дробными коэффициентами
  7-9   два неизвестных: целые корни -> дробные корни -> дробные коэффициенты
  10    финал: система трёх неизвестных и квадратное уравнение в одном задании
"""
import random
import re
from fractions import Fraction

NAME = 'calc'
TITLE = 'Точный счёт'
MAX_LEVEL = 10
CATEGORIES = {'math': 0.8, 'logic': 0.2}
NEEDS = []


# ------------------------------------------------------- длинные выражения

def _expr(rng, depth, allow_frac=False):
    """Строит выражение и его точное значение."""
    if depth == 0:
        if allow_frac and rng.random() < 0.35:
            num = rng.randrange(1, 40)
            den = rng.choice([2, 3, 4, 5, 6, 8])
            return '%d/%d' % (num, den), Fraction(num, den)
        v = rng.randrange(2, 60)
        if allow_frac and rng.random() < 0.25:
            return '(-%d)' % v, Fraction(-v)
        return str(v), Fraction(v)

    ops = ['+', '-', '*'] + (['*', '+'] if not allow_frac else ['/', '**'])
    op = rng.choice(ops)

    if op == '**':
        base, bv = _expr(rng, 0, allow_frac=False)
        p = rng.randrange(2, 4)
        return '%s ** %d' % (base, p), bv ** p

    ls, lv = _expr(rng, depth - 1, allow_frac)
    rs, rv = _expr(rng, depth - 1, allow_frac)

    if op == '/':
        if rv == 0:
            rs, rv = '3', Fraction(3)
        return '(%s) / (%s)' % (ls, rs), lv / rv
    if op == '+':
        return '(%s + %s)' % (ls, rs), lv + rv
    if op == '-':
        return '(%s - %s)' % (ls, rs), lv - rv
    return '(%s * %s)' % (ls, rs), lv * rv


def _fmt(fr):
    fr = Fraction(fr)
    return str(fr.numerator) if fr.denominator == 1 else '%d/%d' % (fr.numerator, fr.denominator)


def _linear(rng, hard=False):
    """Уравнение вида a*x + b = c*x + d с рациональным корнем."""
    x = Fraction(rng.randrange(-20, 21), rng.choice([1, 1, 2, 4]))
    if hard:
        a = Fraction(rng.randrange(3, 20), rng.choice([2, 3, 4]))
        c = Fraction(rng.randrange(3, 20), rng.choice([2, 3, 5]))
        while c == a:
            c = Fraction(rng.randrange(3, 20), rng.choice([2, 3, 5]))
        b = Fraction(rng.randrange(-30, 31), rng.choice([1, 2, 3]))
    else:
        a = Fraction(rng.randrange(2, 15))
        c = Fraction(rng.randrange(2, 15))
        while c == a:
            c = Fraction(rng.randrange(2, 15))
        b = Fraction(rng.randrange(-40, 41))
    d = (a - c) * x + b
    left = '(%s)*x + (%s)' % (_fmt(a), _fmt(b))
    right = '(%s)*x + (%s)' % (_fmt(c), _fmt(d))
    return '%s = %s' % (left, right), {'x': x}


def _system2(rng, kind=1):
    """kind: 1 — целые корни, 2 — дробные корни, 3 — дробные коэффициенты."""
    if kind >= 2:
        x = Fraction(rng.randrange(-24, 25), rng.choice([2, 3, 4]))
        y = Fraction(rng.randrange(-24, 25), rng.choice([2, 3, 5]))
    else:
        x = Fraction(rng.randrange(-12, 13))
        y = Fraction(rng.randrange(-12, 13))

    def coef():
        if kind >= 3:
            return Fraction(rng.randrange(-12, 13), rng.choice([1, 2, 3]))
        return Fraction(rng.randrange(-9, 10))

    while True:
        a, b, c, d = coef(), coef(), coef(), coef()
        if a * d - b * c != 0:
            break
    e = a * x + b * y
    f = c * x + d * y
    eqs = ['(%s)*x + (%s)*y = %s' % (_fmt(a), _fmt(b), _fmt(e)),
           '(%s)*x + (%s)*y = %s' % (_fmt(c), _fmt(d), _fmt(f))]
    return '\n'.join(eqs), {'x': x, 'y': y}


def _system3(rng):
    x = Fraction(rng.randrange(-9, 10))
    y = Fraction(rng.randrange(-9, 10))
    z = Fraction(rng.randrange(-9, 10))
    rows = []
    for _ in range(3):
        a, b, c = (rng.randrange(-7, 8) for _ in range(3))
        if (a, b, c) == (0, 0, 0):
            a = 1
        rows.append((a, b, c))
    # проверка невырожденности
    (a1, b1, c1), (a2, b2, c2), (a3, b3, c3) = rows
    det = (a1 * (b2 * c3 - b3 * c2) - b1 * (a2 * c3 - a3 * c2)
           + c1 * (a2 * b3 - a3 * b2))
    if det == 0:
        return _system3(rng)
    eqs = []
    for a, b, c in rows:
        r = a * x + b * y + c * z
        eqs.append('%d*x + %d*y + %d*z = %s' % (a, b, c, _fmt(r)))
    return '\n'.join(eqs), {'x': x, 'y': y, 'z': z}


def _quadratic(rng):
    """x**2 + p*x + q = 0 с двумя рациональными корнями."""
    r1 = Fraction(rng.randrange(-12, 13))
    r2 = Fraction(rng.randrange(-12, 13))
    while r2 == r1:
        r2 = Fraction(rng.randrange(-12, 13))
    p = -(r1 + r2)
    q = r1 * r2
    lo, hi = sorted([r1, r2])
    eq = 'x**2 + (%s)*x + (%s) = 0' % (_fmt(p), _fmt(q))
    return eq, {'x1': lo, 'x2': hi}


_HEAD = ('Посчитай точно. Дроби не округляй.\n\n')
_TAIL = ('\n\nNXB-CANARY-a7f3c1')


def generate(level, rng):
    if level <= 3:
        depth = {1: 3, 2: 4, 3: 5}[level]
        frac = level >= 2
        s, val = _expr(rng, depth, allow_frac=frac)
        prompt = (
            _HEAD +
            'Вычисли значение выражения:\n\n%s\n\n'
            'Операторы читаются как в Python: ** это возведение в степень, '
            '/ это обычное деление (не целочисленное).\n\n'
            'Ответ дай ровно одной строкой в формате:\n'
            'ANSWER: <значение>\n'
            'Значение — целое число либо несократимая дробь вида p/q '
            '(например -17/4). Десятичную запись не используй. '
            'Никаких пояснений.' % s + _TAIL
        )
        return prompt, {'kind': 'single', 'vars': {'value': val}}

    if level <= 6:
        eq, sol = _linear(rng, hard=(level == 6))
        prompt = (
            _HEAD +
            'Реши уравнение относительно x:\n\n%s\n\n'
            'Ответ дай ровно одной строкой:\n'
            'ANSWER: x=<значение>\n'
            'Значение — целое число либо несократимая дробь p/q. '
            'Никаких пояснений.' % eq + _TAIL
        )
        return prompt, {'kind': 'vars', 'vars': sol}

    if level <= 9:
        eqs, sol = _system2(rng, kind=level - 6)
        prompt = (
            _HEAD +
            'Реши систему уравнений:\n\n%s\n\n'
            'Ответ дай ровно одной строкой:\n'
            'ANSWER: x=<значение>, y=<значение>\n'
            'Значения — целые числа либо несократимые дроби p/q. '
            'Никаких пояснений.' % eqs + _TAIL
        )
        return prompt, {'kind': 'vars', 'vars': sol}

    # Уровень 10 — финал: две разные задачи в одном задании. Проверяет, что
    # модель не бросит вторую половину, дорешав первую.
    eqs3, sol3 = _system3(rng)
    eq2, sol2 = _quadratic(rng)
    merged = {'x': sol3['x'], 'y': sol3['y'], 'z': sol3['z'],
              'x1': sol2['x1'], 'x2': sol2['x2']}
    prompt = (
        _HEAD +
        'Задание из двух частей, ответить нужно на обе.\n\n'
        'Часть A. Реши систему уравнений:\n\n%s\n\n'
        'Часть B. Найди оба корня уравнения:\n\n%s\n\n'
        'Ответ дай ровно одной строкой, корни в части B в порядке возрастания:\n'
        'ANSWER: x=<значение>, y=<значение>, z=<значение>, '
        'x1=<меньший>, x2=<больший>\n'
        'Значения — целые числа либо несократимые дроби p/q. '
        'Никаких пояснений.' % (eqs3, eq2) + _TAIL
    )
    return prompt, {'kind': 'vars', 'vars': merged}


_ANSWER = re.compile(r'ANSWER\s*:\s*(.+)', re.I)
_NUM = re.compile(r'-?\d+\s*/\s*-?\d+|-?\d+\.\d+|-?\d+')


def _to_fraction(tok, strict=True):
    """Разбирает число ответа.

    В задании прямо сказано: целое либо НЕСОКРАТИМАЯ дробь p/q, десятичную
    запись не использовать. Раньше проверялось только значение, поэтому
    «52949.0» и «-26/2» засчитывались вопреки условию. Теперь при strict=True
    представление проверяется тоже — иначе требование в промпте было бы
    декоративным.
    """
    tok = tok.strip().replace(' ', '')
    try:
        if '/' in tok:
            n, d = tok.split('/', 1)
            fr = Fraction(int(n), int(d))
            if strict and (int(d) <= 0 or fr.denominator != abs(int(d))):
                return None      # сократимая дробь либо отрицательный знаменатель
            return fr
        if '.' in tok:
            return None if strict else Fraction(tok)
        return Fraction(int(tok))
    except (ValueError, ZeroDivisionError):
        return None


def score(output, expected):
    m = _ANSWER.search(output or '')
    if not m:
        return False, 'строка ANSWER: не найдена'
    line = m.group(1).strip()

    if expected['kind'] == 'single':
        nums = _NUM.findall(line)
        if not nums:
            return False, 'число в ответе не найдено'
        got = _to_fraction(nums[0])
        want = expected['vars']['value']
        if got is None:
            return False, 'ответ %r не разобран' % nums[0]
        return (got == want), 'ответ %s, эталон %s' % (_fmt(got), _fmt(want))

    want = expected['vars']
    got = {}
    for name in want:
        mm = re.search(r'\b%s\s*=\s*(-?\d+\s*/\s*-?\d+|-?\d+\.\d+|-?\d+)' % name,
                       line, re.I)
        if not mm:
            return False, 'не найдено значение %s' % name
        v = _to_fraction(mm.group(1))
        if v is None:
            return False, 'значение %s не разобрано' % name
        got[name] = v

    bad = [n for n in want if got[n] != want[n]]
    detail = ', '.join('%s=%s (эталон %s)' % (n, _fmt(got[n]), _fmt(want[n]))
                       for n in sorted(want))
    return (not bad), detail
