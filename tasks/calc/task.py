# -*- coding: utf-8 -*-
"""Задача 6 — точный счёт: длинные выражения и уравнения.

Ловит класс ошибок, которого нет в остальных задачах: не «не понял условие»,
а «сбился в середине длинной цепочки». Эталон считается точной рациональной
арифметикой (Fraction), поэтому ответ либо совпадает, либо нет — округление
не спасает.

Шкала начинается с короткой целой и простой дробной арифметики, затем плавно
переходит к смешанным выражениям, линейным уравнениям, системам и составным
точным вычислениям. L1-L3 — обязательный нижний порог; L9-L10 — потолок.
"""
import random
import re
from fractions import Fraction

NAME = 'calc'
TITLE = 'Exact arithmetic'
MAX_LEVEL = 12

# Ступени прогона. Внутренние ручки сложности не менялись: здесь
# выбрано, какие из них стоят отдельного замера — разогрев, дроби и степени, система уравнений, предел.
LADDER = (1, 5, 9, 12)
# Версию поднимает тот, кто меняет generate или score: иначе допрогон
# подмешает к новым уровням старые, посчитанные по другим правилам.
VERSION = 5
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
    if hard:
        den = rng.choice([2, 3, 4])
        num = rng.randrange(-20, 21)
        while num % den == 0:
            num = rng.randrange(-20, 21)
        x = Fraction(num, den)
        a = Fraction(rng.randrange(3, 20), rng.choice([2, 3, 4]))
        c = Fraction(rng.randrange(3, 20), rng.choice([2, 3, 5]))
        while c == a:
            c = Fraction(rng.randrange(3, 20), rng.choice([2, 3, 5]))
        b = Fraction(rng.randrange(-30, 31), rng.choice([1, 2, 3]))
    else:
        x = Fraction(rng.randrange(-20, 21))
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
        def non_integer(denominators):
            den = rng.choice(denominators)
            num = rng.randrange(-24, 25)
            while num % den == 0:
                num = rng.randrange(-24, 25)
            return Fraction(num, den)

        x = non_integer([2, 3, 4])
        y = non_integer([2, 3, 5])
    else:
        x = Fraction(rng.randrange(-12, 13))
        y = Fraction(rng.randrange(-12, 13))

    def coef():
        if kind >= 3:
            return Fraction(rng.randrange(-12, 13), rng.choice([1, 2, 3]))
        return Fraction(rng.randrange(-9, 10))

    while True:
        a, b, c, d = coef(), coef(), coef(), coef()
        if all(v != 0 for v in (a, b, c, d)) and a * d - b * c != 0:
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



def _chained(rng, links):
    """Цепочка, где каждое звено считается по ответу предыдущего.

    Это другой род трудности, чем «то же самое, но длиннее». Длинное задание
    можно разбить и считать куски независимо; здесь нельзя: следующее звено
    берёт значение предыдущего, поэтому ошибка в начале делает весь остаток
    заведомо неверным, а проверить себя можно только пройдя цепь целиком.
    Модель, аккуратная на любой отдельной операции, ломается именно тут.
    """
    parts = []
    cur = Fraction(rng.randrange(2, 9))
    parts.append('Step 1. Let t1 = %s.' % _fmt(cur))
    for i in range(2, links + 1):
        a = rng.randrange(2, 7)
        b = rng.randrange(-9, 10)
        c = rng.choice([2, 3, 4, 5])
        style = rng.randrange(3)
        if style == 0:
            cur = (a * cur + b) / Fraction(c)
            parts.append('Step %d. t%d = (%d*t%d + (%d)) / %d.'
                         % (i, i, a, i - 1, b, c))
        elif style == 1:
            parts.append('Step %d. t%d = t%d**2 - (%d).' % (i, i, i - 1, b))
            cur = cur * cur - Fraction(b)
        else:
            # ноль в знаменателе недопустим — сдвигаем b, пока он не безопасен
            while cur + b == 0:
                b += 1
            parts.append('Step %d. t%d = %d / (t%d + (%d)).' % (i, i, a, i - 1, b))
            cur = Fraction(a) / (cur + b)
    return chr(10).join(parts), cur


_HEAD = ('Compute exactly. Do not round fractions.\n\n')
_TAIL = ''


def _easy_expression(level, rng):
    """Короткие L1-L3 без случайного взрыва длины или знаменателя."""
    if level == 1:
        a, b, c = (rng.randrange(2, 16) for _ in range(3))
        return '%d + %d * %d' % (a, b, c), Fraction(a + b * c)
    if level == 2:
        a, b, c, d = (rng.randrange(2, 21) for _ in range(4))
        return '(%d + %d) * %d - %d' % (a, b, c, d), Fraction((a + b) * c - d)

    a, c = rng.randrange(1, 13), rng.randrange(1, 13)
    b, d = rng.choice([2, 3, 4, 5, 6, 8]), rng.choice([2, 3, 4, 5, 6, 8])
    op = rng.choice(['+', '-'])
    left, right = Fraction(a, b), Fraction(c, d)
    value = left + right if op == '+' else left - right
    return '%d/%d %s %d/%d' % (a, b, op, c, d), value


def _moderate_expression(rng):
    """L4: несколько действий с дробями, но без огромных чисел."""
    a, c = rng.randrange(2, 20), rng.randrange(2, 20)
    b, d = rng.choice([2, 3, 4, 5, 6, 8]), rng.choice([2, 3, 4, 5, 6, 8])
    mul, sub = rng.randrange(2, 10), rng.randrange(2, 21)
    value = (Fraction(a, b) + Fraction(c, d)) * mul - sub
    return '(%d/%d + %d/%d) * %d - %d' % (a, b, c, d, mul, sub), value


def generate(level, rng):
    if level <= 4:
        # L1-L3 намеренно имеют жёсткую верхнюю границу сложности. На L4
        # впервые появляется рекурсивное смешанное выражение со скобками.
        if level <= 3:
            s, val = _easy_expression(level, rng)
        else:
            s, val = _moderate_expression(rng)
        prompt = (
            _HEAD +
            'Evaluate the expression:\n\n%s\n\n'
            'Operators follow Python semantics: ** is exponentiation, '
            '/ is ordinary division (not integer division).\n\n'
            'Give the answer as exactly one line in the format:\n'
            'ANSWER: <value>\n'
            'The value is an integer or an irreducible fraction p/q '
            '(for example -17/4). Do not use decimal notation. No explanations.'
            % s + _TAIL
        )
        return prompt, {'kind': 'single', 'vars': {'value': val}}

    if level <= 6:
        eq, sol = _linear(rng, hard=(level == 6))
        prompt = (
            _HEAD +
            'Solve the equation for x:\n\n%s\n\n'
            'Give the answer as exactly one line:\n'
            'ANSWER: x=<value>\n'
            'The value is an integer or an irreducible fraction p/q. '
            'No explanations.' % eq + _TAIL
        )
        return prompt, {'kind': 'vars', 'vars': sol}

    if level <= 8:
        eqs, sol = _system2(rng, kind=level - 6)
        prompt = (
            _HEAD +
            'Solve the system of equations:\n\n%s\n\n'
            'Give the answer as exactly one line:\n'
            'ANSWER: x=<value>, y=<value>\n'
            'The values are integers or irreducible fractions p/q. '
            'No explanations.' % eqs + _TAIL
        )
        return prompt, {'kind': 'vars', 'vars': sol}

    if level == 9:
        eqs, sol = _system2(rng, kind=3)
        expr, value = _expr(rng, 4, allow_frac=True)
        merged = {'x': sol['x'], 'y': sol['y'], 'e': value}
        prompt = (
            _HEAD +
            'The task has two parts; answer both.\n\n'
            'Part A. Solve the system of equations:\n\n%s\n\n'
            'Part B. Compute the exact value of the expression:\n\n%s\n\n'
            'Give the answer as exactly one line:\n'
            'ANSWER: x=<value>, y=<value>, e=<Part B value>\n'
            'The values are integers or irreducible fractions p/q. '
            'No explanations.' % (eqs, expr) + _TAIL
        )
        return prompt, {'kind': 'vars', 'vars': merged}

    if level == 10:
        # Уровень 10 — финал: три разные задачи в одном задании, каждая с точной
        # рациональной арифметикой. Верхний уровень намеренно тяжёлый: бенчмарк,
        # который берут на 100%, перестаёт мерить. Здесь ломаются и на длине
        # вычисления, и на том, что бросают недорешанной последнюю часть.
        eqs3, sol3 = _system3(rng)
        eq2, sol2 = _quadratic(rng)
        long_expr, long_val = _expr(rng, 6, allow_frac=True)
        merged = {'x': sol3['x'], 'y': sol3['y'], 'z': sol3['z'],
                  'x1': sol2['x1'], 'x2': sol2['x2'], 'e': long_val}
        prompt = (
            _HEAD +
            'The task has three parts; answer all three.\n\n'
            'Part A. Solve the system of equations:\n\n%s\n\n'
            'Part B. Find both roots of the equation:\n\n%s\n\n'
            'Part C. Compute the exact value of the expression:\n\n%s\n\n'
            'Give the answer as exactly one line, with the roots of Part B in '
            'ascending order:\n'
            'ANSWER: x=<value>, y=<value>, z=<value>, '
            'x1=<smaller>, x2=<larger>, e=<Part C value>\n'
            'The values are integers or irreducible fractions p/q. '
            'No explanations.' % (eqs3, eq2, long_expr) + _TAIL
        )
        return prompt, {'kind': 'vars', 'vars': merged}

    if level == 11:
        # Цепочка плюс система: последняя часть считается по собственным
        # ответам модели, поэтому части нельзя решать независимо.
        chain, tval = _chained(rng, 5)
        eqs3, sol3 = _system3(rng)
        final = tval + sol3['x'] * sol3['y'] - sol3['z']
        merged = {'t5': tval, 'x': sol3['x'], 'y': sol3['y'], 'z': sol3['z'],
                  'r': final}
        prompt = (
            _HEAD +
            'The parts depend on one another; work through them in order.\n\n'
            'Part A. Follow the chain and report the final value t5:\n\n%s\n\n'
            'Part B. Solve the system:\n\n%s\n\n'
            'Part C. Compute r = t5 + x*y - z from your own answers above.\n\n'
            'Give the answer as exactly one line:\n'
            'ANSWER: t5=<value>, x=<value>, y=<value>, z=<value>, r=<value>\n'
            'The values are integers or irreducible fractions p/q. '
            'No explanations.' % (chain, eqs3) + _TAIL
        )
        return prompt, {'kind': 'vars', 'vars': merged}

    # Уровень 12 — потолок: восемь звеньев цепи, система, и квадратное
    # уравнение, коэффициенты которого берутся из первых двух частей.
    chain, tval = _chained(rng, 8)
    eqs3, sol3 = _system3(rng)
    lo, hi2 = sorted([tval, sol3['x']])
    merged = {'t8': tval, 'x': sol3['x'], 'y': sol3['y'], 'z': sol3['z'],
              'x1': lo, 'x2': hi2}
    prompt = (
        _HEAD +
        'Every part depends on the one before it: a later part cannot be '
        'checked without finishing the earlier ones.\n\n'
        'Part A. Follow the chain and report the final value t8:\n\n%s\n\n'
        'Part B. Solve the system:\n\n%s\n\n'
        'Part C. Build the equation u**2 + p*u + q = 0 where p = -(t8 + x) and '
        'q = t8 * x, using your own answers, and give both roots in ascending '
        'order.\n\n'
        'Give the answer as exactly one line:\n'
        'ANSWER: t8=<value>, x=<value>, y=<value>, z=<value>, '
        'x1=<smaller>, x2=<larger>\n'
        'The values are integers or irreducible fractions p/q. '
        'No explanations.' % (chain, eqs3) + _TAIL
    )
    return prompt, {'kind': 'vars', 'vars': merged}



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


_ANSWER_LINE = re.compile(r'^\s*ANSWER\s*:\s*(.*?)\s*$', re.I | re.M)


def score(output, expected):
    """Считает арифметику, а не аккуратность оформления.

    Раньше ответ отвергался, если в выводе была хоть одна лишняя строка. Но
    задача весит math 0.8 / logic 0.2 и не содержит доли instruction: модель,
    посчитавшая верно и добавившая фразу, получала ноль по математике. Буквальное
    следование формату меряет отдельная задача count, и дублировать её здесь
    значит мерить одно дважды, а математику — не мерить вовсе.

    Послабление ровно одно: строку ANSWER разрешено окружать текстом. Несколько
    строк ANSWER по-прежнему провал — это не оформление, а перебор вариантов в
    надежде, что засчитают подходящий.
    """
    found = _ANSWER_LINE.findall(output or '')
    if not found:
        return False, 'ANSWER: line not found'
    if len(found) > 1:
        return False, ('%d ANSWER: lines - the answer must be a single value, '
                       'not a list of candidates' % len(found))
    line = found[0].strip()

    if expected['kind'] == 'single':
        number = _NUM.fullmatch(line)
        if not number:
            return False, 'exactly one number must follow ANSWER'
        got = _to_fraction(number.group(0))
        want = expected['vars']['value']
        if got is None:
            return False, 'could not parse answer %r' % number.group(0)
        return (got == want), 'answer %s, expected %s' % (_fmt(got), _fmt(want))

    want = expected['vars']
    got = {}
    parts = [part.strip() for part in line.split(',')]
    if len(parts) != len(want):
        return False, 'wrong number of values in the ANSWER line'
    for name, part in zip(want, parts):
        mm = re.fullmatch(
            r'%s\s*=\s*(-?\d+\s*/\s*-?\d+|-?\d+\.\d+|-?\d+)' % re.escape(name),
            part, re.I)
        if not mm:
            return False, 'no value for %s' % name
        v = _to_fraction(mm.group(1))
        if v is None:
            return False, 'could not parse value %s' % name
        got[name] = v

    bad = [n for n in want if got[n] != want[n]]
    detail = ', '.join('%s=%s (expected %s)' % (n, _fmt(got[n]), _fmt(want[n]))
                       for n in sorted(want))
    return (not bad), detail
