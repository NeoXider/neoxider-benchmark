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
TITLE = 'Browser form filling'
MAX_LEVEL = 10
# Версию поднимает тот, кто меняет generate или score: иначе допрогон
# подмешает к новым уровням старые, посчитанные по другим правилам.
# v2: задание требует закрыть за собой вкладку. Прогоны оставляли в
# браузере пользователя по вкладке на уровень, и через десяток моделей
# это уже десятки открытых страниц. Убирать за собой — часть агентной
# работы, а не придирка.
VERSION = 2
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
        # Поля живут во вкладках и не видны, пока по вкладке не кликнули.
        f['invoice'] = 'INV-%04d' % rng.randrange(1000, 9999)
        f['seats'] = str(rng.randrange(2, 40))
    if level >= 9:
        n = rng.randrange(2, 4)
        f['topics'] = ','.join(sorted(rng.sample(TOPICS, n)))
        # Перетаскивание: порядок заведомо отличается от исходного, иначе
        # уровень проходился бы, даже если агент вообще ничего не тащил.
        items = ['alpha', 'beta', 'gamma', 'delta']
        shuffled = list(items)
        while shuffled == items:
            rng.shuffle(shuffled)
        f['order'] = ','.join(shuffled)
    if level >= 10:
        f['priority'] = str(rng.randrange(1, 11))
    return f


# Порядок полей в подписи фиксирован — от него зависит код.
ORDER = ['name', 'email', 'quantity', 'country', 'plan', 'newsletter',
         'comment', 'frequency', 'startdate', 'invoice', 'seats', 'topics',
         'order', 'priority']

LABELS = {
    'name': 'Full name (text field)',
    'email': 'Email (text field)',
    'quantity': 'Quantity (numeric field)',
    'country': 'Country (dropdown list)',
    'plan': 'Plan (radio buttons)',
    'newsletter': 'Newsletter (checkbox; yes — turn it on, no — leave it off)',
    'comment': 'Comment (multiline field)',
    'frequency': 'Frequency (dropdown list; appears only when the Newsletter checkbox is on)',
    'startdate': 'Start date (date field, YYYY-MM-DD format)',
    'invoice': 'Invoice number (text field on the Billing tab)',
    'seats': 'Seats (numeric field on the Access tab)',
    'topics': 'Topics (checkboxes, tick the listed ones)',
    'order': 'Priority order (drag-and-drop list — arrange the items in the '
             'given order top to bottom)',
    'priority': 'Priority (slider from 1 to 10)',
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
        'Open the page %s?level=%d in a browser\n\n'
        'The page contains a form. Fill it in with exactly these values:\n\n%s\n\n'
        'After filling it in, click the Submit button. The page validates the input '
        'and shows a confirmation code — a string of eight hexadecimal characters '
        'in the block titled "Confirmation code".\n\n'
        'Return the answer exactly in the format:\n'
        'CODE: XXXXXXXX\n\n'
        'If filling in the form failed, write exactly:\n'
        'CODE: FAILED\n'
        'and the reason on one line. Making up a code is forbidden — it is verified.\n\n'
        # Про «отцепиться — не значит закрыть» сказано прямо: это ровно та
        # ошибка, на которой мусор и копился. Сессия закрывалась, вкладка
        # оставалась, и человек, просто запустивший бенчмарк, получал свой
        # браузер, забитый группами вкладок.
        'Work in a browser session of your own, not in the user\'s everyday '
        'browser: do not attach to their existing tabs and do not drive their '
        'current profile.\n\n'
        'When you are done, close every tab you opened. Detaching from a tab is '
        'not the same as closing it, so check that the tabs are actually gone. '
        "Leaving pages behind in someone else's browser counts against you.\n\n"
        'NXB-CANARY-a7f3c1'
        % (BASE_URL, level, '\n'.join(lines))
    )
    return prompt, {'level': level, 'fields': fields, 'code': expected_code(level, fields)}


_CODE = re.compile(r'CODE:\s*([0-9A-Fa-f]{8}|FAILED)')


def score(output, expected):
    m = _CODE.search(output or '')
    if not m:
        return False, 'CODE: line not found'
    got = m.group(1).upper()
    if got == 'FAILED':
        return False, 'agent reported failure (honestly)'
    if got == expected['code']:
        return True, 'code matches'
    return False, 'code %s, expected %s' % (got, expected['code'])
