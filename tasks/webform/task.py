# -*- coding: utf-8 -*-
"""Задача 3 — агентный режим: заполнить форму в браузере.

Форма лежит на GitHub Pages. Проверки на сервере быть не может — Pages отдаёт
только статику, — поэтому страница проверяет введённое сама и показывает
код подтверждения: FNV-1a от нормализованных значений полей. Подделать код,
не заполнив форму правильно, нельзя: он зависит от каждого значения.

Агент обязан вернуть этот код. Мы считаем эталонный код тем же алгоритмом
на Python и сравниваем.

Уровни добавляют поля и усложняют элементы управления: текст -> число ->
выпадающий список -> радиокнопки -> флажок -> поле, появляющееся только после
включения флажка -> дата -> множественный выбор.
"""
import re

NAME = 'webform'
TITLE = 'Заполнение формы в браузере'
MAX_LEVEL = 10
CATEGORIES = {'agentic': 1.0}
NEEDS = ['browser', 'network']

BASE_URL = 'https://neoxider.github.io/neoxider-benchmark/form.html'

COUNTRIES = ['Armenia', 'Cyprus', 'Georgia', 'Kazakhstan', 'Portugal', 'Serbia']
PLANS = ['basic', 'pro', 'team']
TOPICS = ['unity', 'dotnet', 'python', 'ai']

_NAMES = ['Viktor', 'Anna', 'Pavel', 'Marina', 'Oleg', 'Daria']
_SURNAMES = ['Nirov', 'Belova', 'Orlov', 'Sizova', 'Karpov', 'Ivleva']


def fnv1a(s):
    """32-битный FNV-1a. Тот же алгоритм реализован в form.html."""
    h = 0x811C9DC5
    for ch in s.encode('utf-8'):
        h ^= ch
        h = (h * 0x01000193) & 0xFFFFFFFF
    return '%08X' % h


def _fields_for(level, rng):
    """Какие поля участвуют на этом уровне и какие значения требуются."""
    f = {}
    f['name'] = '%s %s' % (rng.choice(_NAMES), rng.choice(_SURNAMES))
    f['email'] = '%s@example.org' % f['name'].split()[0].lower()
    if level >= 2:
        f['quantity'] = str(rng.randrange(2, 99))
    if level >= 3:
        f['country'] = rng.choice(COUNTRIES)
    if level >= 4:
        f['plan'] = rng.choice(PLANS)
    if level >= 5:
        f['newsletter'] = rng.choice(['yes', 'no'])
    if level >= 6:
        f['comment'] = rng.choice(['no blockers', 'needs review', 'ship it'])
    if level >= 7:
        # поле появляется только когда newsletter = yes
        f['newsletter'] = 'yes'
        f['frequency'] = rng.choice(['daily', 'weekly', 'monthly'])
    if level >= 8:
        f['startdate'] = '2026-%02d-%02d' % (rng.randrange(1, 13), rng.randrange(1, 29))
    if level >= 9:
        n = rng.randrange(2, 4)
        f['topics'] = ','.join(sorted(rng.sample(TOPICS, n)))
    if level >= 10:
        f['priority'] = str(rng.randrange(1, 11))
    return f


# Порядок полей в подписи фиксирован — от него зависит код.
ORDER = ['name', 'email', 'quantity', 'country', 'plan', 'newsletter',
         'comment', 'frequency', 'startdate', 'topics', 'priority']

LABELS = {
    'name': 'Full name (текстовое поле)',
    'email': 'Email (текстовое поле)',
    'quantity': 'Quantity (числовое поле)',
    'country': 'Country (выпадающий список)',
    'plan': 'Plan (радиокнопки)',
    'newsletter': 'Newsletter (флажок; yes — включить, no — оставить выключенным)',
    'comment': 'Comment (многострочное поле)',
    'frequency': 'Frequency (выпадающий список; появляется только когда включён флажок Newsletter)',
    'startdate': 'Start date (поле даты, формат ГГГГ-ММ-ДД)',
    'topics': 'Topics (флажки, отметить перечисленные)',
    'priority': 'Priority (ползунок от 1 до 10)',
}


def expected_code(level, fields):
    parts = ['%s=%s' % (k, fields[k]) for k in ORDER if k in fields]
    return fnv1a('L%d|%s' % (level, '|'.join(parts)))


def generate(level, rng):
    fields = _fields_for(level, rng)
    lines = []
    for k in ORDER:
        if k in fields:
            lines.append('- %s: %s' % (LABELS[k], fields[k]))

    prompt = (
        'Открой в браузере страницу %s?level=%d\n\n'
        'На странице форма. Заполни её ровно этими значениями:\n\n%s\n\n'
        'После заполнения нажми кнопку Submit. Страница проверит введённое и покажет '
        'код подтверждения — строку из восьми шестнадцатеричных символов в блоке '
        'с заголовком «Confirmation code».\n\n'
        'Верни ответ ровно в формате:\n'
        'CODE: XXXXXXXX\n\n'
        'Если форму заполнить не удалось, напиши ровно:\n'
        'CODE: FAILED\n'
        'и одной строкой причину. Выдумывать код нельзя — он проверяется.\n\n'
        'NXB-CANARY-a7f3c1'
        % (BASE_URL, level, '\n'.join(lines))
    )
    return prompt, {'level': level, 'fields': fields, 'code': expected_code(level, fields)}


_CODE = re.compile(r'CODE:\s*([0-9A-Fa-f]{8}|FAILED)')


def score(output, expected):
    m = _CODE.search(output or '')
    if not m:
        return False, 'строка CODE: не найдена'
    got = m.group(1).upper()
    if got == 'FAILED':
        return False, 'агент сообщил о неудаче (честно)'
    if got == expected['code']:
        return True, 'код совпал'
    return False, 'код %s, ожидался %s' % (got, expected['code'])
