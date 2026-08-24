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
TITLE = 'Следование инструкции'
MAX_LEVEL = 10
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
        rule = 'Выведи числа от 1 до %d, по одному в строке.' % hi
        exp = [str(i) for i in range(1, hi + 1)]

    elif level == 2:
        rule = 'Выведи числа от %d до 1 в убывающем порядке, по одному в строке.' % hi
        exp = [str(i) for i in range(hi, 0, -1)]

    elif level == 3:
        k = rng.choice([3, 4, 7])
        rule = ('Выведи числа от 1 до %d по одному в строке, но каждое число, '
                'кратное %d, замени на слово skip.' % (hi, k))
        exp = ['skip' if i % k == 0 else str(i) for i in range(1, hi + 1)]

    elif level == 4:
        rule = ('Выведи числа от 1 до %d по одному в строке. Каждое чётное число '
                'выведи в скобках, например (2).' % hi)
        exp = ['(%d)' % i if i % 2 == 0 else str(i) for i in range(1, hi + 1)]

    elif level == 5:
        per = rng.choice([5, 8])
        rule = ('Выведи числа от 1 до %d, по %d штук в строке, разделяя их одним '
                'пробелом. Последняя строка может быть короче.' % (hi, per))
        nums = [str(i) for i in range(1, hi + 1)]
        exp = [' '.join(nums[i:i + per]) for i in range(0, len(nums), per)]

    elif level == 6:
        rule = ('Выведи числа от 1 до %d по одному в строке, пропустив все простые '
                'числа целиком (строк для них быть не должно).' % hi)
        exp = [str(i) for i in range(1, hi + 1) if i not in primes]

    elif level == 7:
        rule = ('Выведи числа от 1 до %d по одному в строке в формате NNN:X, где '
                'NNN — число, дополненное нулями слева до трёх знаков, а X — буква '
                'E для чётных и O для нечётных. Пример: 007:O' % hi)
        exp = ['%03d:%s' % (i, 'E' if i % 2 == 0 else 'O') for i in range(1, hi + 1)]

    elif level == 8:
        rule = ('Выведи числа от 1 до %d по одному в строке. Если число делится на 3 — '
                'выведи Fizz, если на 5 — Buzz, если и на 3 и на 5 — FizzBuzz, '
                'иначе само число.' % hi)
        def fb(i):
            if i % 15 == 0: return 'FizzBuzz'
            if i % 3 == 0: return 'Fizz'
            if i % 5 == 0: return 'Buzz'
            return str(i)
        exp = [fb(i) for i in range(1, hi + 1)]

    elif level == 9:
        rule = ('Выведи числа от 1 до %d по одному в строке, но в обратном порядке '
                'цифр внутри каждого числа: 12 станет 21, 100 станет 001. '
                'Ведущие нули сохраняй.' % hi)
        exp = [str(i)[::-1] for i in range(1, hi + 1)]

    else:
        step = rng.choice([3, 7])
        rule = ('Выведи числа от 1 до %d по одному в строке. Каждое число, кратное %d, '
                'замени на сумму его цифр в квадратных скобках, например [7]. '
                'Простые числа выводи с восклицательным знаком в конце, например 13!. '
                'Если число одновременно простое и кратное %d — приоритет у скобок.'
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
        'Весь вывод помести в один блок кода, открывающийся ровно строкой ```count '
        'и закрывающийся ровно строкой ```. Внутри блока не должно быть ничего, '
        'кроме требуемых строк: ни нумерации, ни комментариев, ни пустых строк. '
        'До и после блока ничего не пиши.\n\n'
        'NXB-CANARY-a7f3c1' % rule
    )
    return prompt, exp


_BLOCK = re.compile(r'```count[ \t]*\r?\n(.*?)```', re.S)


def score(output, expected):
    """Возвращает (ok, detail)."""
    m = _BLOCK.search(output or '')
    if not m:
        return False, 'блок ```count не найден'
    got = m.group(1).replace('\r\n', '\n').strip('\n').split('\n')
    if got == expected:
        return True, 'совпало, строк: %d' % len(got)
    if len(got) != len(expected):
        return False, 'строк %d, ожидалось %d' % (len(got), len(expected))
    for i, (a, b) in enumerate(zip(got, expected)):
        if a != b:
            return False, 'строка %d: %r вместо %r' % (i + 1, a, b)
    return False, '不 совпало'
