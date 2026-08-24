# -*- coding: utf-8 -*-
"""Задача 8 — сама ли догадалась взять инструмент.

Задание сформулировано как обычный вопрос. В нём НЕТ слов «напиши скрипт»,
«посчитай кодом», «используй инструменты». Но объём вычислений такой, что в
уме или «прикидкой» ответ не получить: правильный ответ достижим практически
только счётом.

Меряем две вещи сразу:
  1. Верен ли ответ.
  2. Взяла ли модель инструмент, чтобы его получить.

Обе фиксируются отдельно, потому что интересны разные исходы:
  - посчитала инструментом и ответила верно — то, что нужно;
  - ответила верно без инструмента — либо повезло, либо задача слишком лёгкая;
  - взяла инструмент, но ответила неверно — умеет решать, но неаккуратна;
  - не взяла и ошиблась — самый частый провал: уверенно назвала число «на глаз».

Если движок не сообщает о вызовах инструментов, вывод об этом не делается:
результат помечается как неизмеримый, а не как «инструментов не было».
"""
import random
import re

NAME = 'toolchoice'
TITLE = 'Выбор инструмента'
MAX_LEVEL = 10
CATEGORIES = {'agentic': 0.6, 'logic': 0.4}
NEEDS = []
WANTS_META = True          # задаче нужны сведения о вызовах инструментов


def _primes_upto(n):
    sieve = bytearray([1]) * (n + 1)
    sieve[0:2] = b'\x00\x00'
    for i in range(2, int(n ** 0.5) + 1):
        if sieve[i]:
            sieve[i * i::i] = bytearray(len(sieve[i * i::i]))
    return sieve


def _kind(level, rng):
    """Возвращает (текст вопроса, точный ответ)."""
    scale = [3, 5, 8, 12, 18, 25, 35, 50, 70, 95][level - 1] * 100000

    variant = level % 5
    if variant == 0:
        n = scale
        sieve = _primes_upto(n)
        ans = sum(sieve)
        q = 'Сколько простых чисел строго меньше или равно %d?' % n
    elif variant == 1:
        n = scale
        total = sum(i for i in range(1, n + 1) if i % 3 == 0 or i % 7 == 0)
        ans = total
        q = ('Чему равна сумма всех целых чисел от 1 до %d включительно, '
             'которые делятся на 3 или на 7?' % n)
    elif variant == 2:
        n = scale
        ans = sum(1 for i in range(1, n + 1) if str(i) == str(i)[::-1])
        q = ('Сколько целых чисел от 1 до %d включительно являются '
             'палиндромами в десятичной записи?' % n)
    elif variant == 3:
        n = scale
        ans = sum(int(c) for i in range(1, n + 1) for c in str(i))
        q = ('Чему равна сумма всех цифр всех целых чисел от 1 до %d '
             'включительно?' % n)
    else:
        n = scale
        sieve = _primes_upto(n)
        ans = sum(i for i in range(n + 1) if sieve[i] and str(i) == str(i)[::-1])
        q = ('Чему равна сумма всех простых чисел не больше %d, которые '
             'при этом являются палиндромами?' % n)
    return q, ans


def generate(level, rng):
    q, ans = _kind(level, rng)
    prompt = (
        '%s\n\n'
        'Ответ дай ровно одной строкой:\n'
        'ANSWER: <число>\n'
        'Без пояснений, без разделителей разрядов, без пробелов внутри числа.\n\n'
        'NXB-CANARY-a7f3c1' % q
    )
    return prompt, {'answer': ans}


_ANSWER = re.compile(r'ANSWER\s*:\s*(-?\d[\d\s_]*)', re.I)


def score(output, expected, meta=None):
    m = _ANSWER.search(output or '')
    if not m:
        return False, 'строка ANSWER: не найдена', {
            'hint': 'В ответе нет строки в формате ANSWER: <число>.'}

    raw = re.sub(r'[\s_]', '', m.group(1))
    try:
        got = int(raw)
    except ValueError:
        return False, 'число не разобрано', {'hint': 'ANSWER должен содержать целое число.'}

    tools = (meta or {}).get('tools')
    used_tool = None if tools is None else bool(tools)
    correct = (got == expected['answer'])

    extra = {'used_tool': used_tool,
             'tools': (tools or [])[:6],
             'hint': 'Ответ неверный. Проверь вычисление.'}

    if correct and used_tool:
        return True, 'верно, посчитала инструментом (%s)' % ', '.join(sorted(set(tools))), extra
    if correct and used_tool is False:
        # Ответ верный без единого вызова инструмента. Это подозрительно на
        # больших уровнях, но доказать угадывание мы не можем, поэтому зачёт
        # ставим и просто помечаем факт.
        extra['answered_without_tool'] = True
        return True, 'верно, но без единого вызова инструмента', extra
    if correct:
        return True, 'верно (движок не сообщает о вызовах инструментов)', extra

    detail = 'ответ неверный'
    if used_tool is False:
        detail += ', инструменты не вызывались'
        extra['guessed'] = True
    elif used_tool:
        detail += ', хотя инструмент вызывался'
    return False, detail, extra
