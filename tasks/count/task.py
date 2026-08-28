# -*- coding: utf-8 -*-
"""Задача 1 — следование инструкции буквально.

Модель должна вывести последовательность чисел в блоке ```count с точным
соблюдением формата. Проверка — побайтовое сравнение содержимого блока.

Почему это осмысленный тест: задача тривиальна интеллектуально, поэтому любой
провал здесь означает не «не смогла», а «не прочитала условие до конца» или
«поленилась и оборвала вывод». И то и другое критично для агента.
"""
import random
import re

NAME = 'count'
TITLE = 'Instruction following'
MAX_LEVEL = 10

# Ступени прогона. Внутренние ручки сложности не менялись: здесь
# выбрано, какие из них стоят отдельного замера — две ступени по прямой просьбе владельца: лёгкая и тяжёлая.
LADDER = (1, 9)
# Версию поднимает тот, кто меняет generate или score: иначе допрогон
# подмешает к новым уровням старые, посчитанные по другим правилам.
VERSION = 3
CATEGORIES = {'instruction': 1.0}
NEEDS = []


def _primes_below(n):
    sieve = [True] * n
    sieve[0] = sieve[1] = False
    for i in range(2, int(n ** 0.5) + 1):
        if sieve[i]:
            sieve[i * i::i] = [False] * len(sieve[i * i::i])
    return {i for i, ok in enumerate(sieve) if ok}


def generate(level, rng):
    """Возвращает (prompt, expected_lines)."""
    hi = rng.choice([180, 200, 220, 240])
    primes = _primes_below(hi + 1)

    if level == 1:
        rule = 'Output the numbers from 1 to %d, one per line.' % hi
        exp = [str(i) for i in range(1, hi + 1)]

    elif level == 2:
        rule = ('Output the numbers from %d down to 1 in descending order, '
                'one per line.' % hi)
        exp = [str(i) for i in range(hi, 0, -1)]

    elif level == 3:
        k = rng.choice([3, 4, 7])
        rule = ('Output the numbers from 1 to %d one per line, but replace every '
                'number divisible by %d with the word skip.' % (hi, k))
        exp = ['skip' if i % k == 0 else str(i) for i in range(1, hi + 1)]

    elif level == 4:
        rule = ('Output the numbers from 1 to %d one per line. Print every even '
                'number in parentheses, for example (2).' % hi)
        exp = ['(%d)' % i if i % 2 == 0 else str(i) for i in range(1, hi + 1)]

    elif level == 5:
        per = rng.choice([5, 8])
        rule = ('Output the numbers from 1 to %d, %d per line, separated by a '
                'single space. The last line may be shorter.' % (hi, per))
        nums = [str(i) for i in range(1, hi + 1)]
        exp = [' '.join(nums[i:i + per]) for i in range(0, len(nums), per)]

    elif level == 6:
        rule = ('Output the numbers from 1 to %d one per line, omitting all prime '
                'numbers entirely (there must be no lines for them).' % hi)
        exp = [str(i) for i in range(1, hi + 1) if i not in primes]

    elif level == 7:
        rule = ('Output the numbers from 1 to %d one per line in the format NNN:X, '
                'where NNN is the number zero-padded on the left to three digits and '
                'X is the letter E for even and O for odd. Example: 007:O' % hi)
        exp = ['%03d:%s' % (i, 'E' if i % 2 == 0 else 'O') for i in range(1, hi + 1)]

    elif level == 8:
        rule = ('Output the numbers from 1 to %d one per line. If a number is '
                'divisible by 3 — print Fizz; if by 5 — Buzz; if by both 3 and 5 — '
                'FizzBuzz; otherwise the number itself.' % hi)
        def fb(i):
            if i % 15 == 0: return 'FizzBuzz'
            if i % 3 == 0: return 'Fizz'
            if i % 5 == 0: return 'Buzz'
            return str(i)
        exp = [fb(i) for i in range(1, hi + 1)]

    elif level == 9:
        rule = ('Output the numbers from 1 to %d one per line, but with the digits '
                'reversed inside each number: 12 becomes 21, 100 becomes 001. '
                'Keep leading zeros.' % hi)
        exp = [str(i)[::-1] for i in range(1, hi + 1)]

    else:
        step = rng.choice([3, 7])
        rule = ('Output the numbers from 1 to %d one per line. Replace every number '
                'divisible by %d with the sum of its digits in square brackets, for '
                'example [7]. Print prime numbers with an exclamation mark at the '
                'end, for example 13!. If a number is both prime and divisible by %d '
                '— the brackets take priority.'
                % (hi, step, step))
        def f(i):
            if i % step == 0:
                return '[%d]' % sum(int(c) for c in str(i))
            if i in primes:
                return '%d!' % i
            return str(i)
        exp = [f(i) for i in range(1, hi + 1)]

    prompt = (
        '%s\n\n'
        'Place the entire output in a single code block that opens with exactly the '
        'line ```count and closes with exactly the line ```. Inside the block there '
        'must be nothing but the required lines: no numbering, no comments, no blank '
        'lines. Write nothing before or after the block.\n\n'
        '' % rule
    )
    return prompt, exp


_BLOCK = re.compile(r'```count[ \t]*\r?\n(.*?)```', re.S)


def score(output, expected):
    """Возвращает (ok, detail).

    Проверка привязана к границам всего ответа: в задании сказано «до и после
    блока ничего не пиши», и это требование теперь действительно проверяется.
    Раньше блок искался где угодно, и ответ вида «МУСОР ```count ... ``` МУСОР»
    засчитывался, хотя формат нарушен.
    """
    text = (output or '').replace('\r\n', '\n').strip()
    m = _BLOCK.fullmatch(text)
    if not m:
        loose = _BLOCK.search(text)
        if loose:
            return False, 'extra text outside the ```count block'
        return False, '```count block not found'
    got = m.group(1).strip('\n').split('\n')
    if got == expected:
        return True, 'match, %d lines' % len(got)
    if len(got) != len(expected):
        return False, '%d lines, expected %d' % (len(got), len(expected))
    for i, (a, b) in enumerate(zip(got, expected)):
        if a != b:
            return False, 'line %d: %r instead of %r' % (i + 1, a, b)
    return False, 'content mismatch'
