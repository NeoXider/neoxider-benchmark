# -*- coding: utf-8 -*-
"""Задача 3 — агентный режим: заполнить форму в браузере.

Балл ставится по тому, что ПРИНЯЛА форма. Страница шлёт значения на локальный
сервер прогона, оттуда их и читает score. Раньше подтверждением служил хеш,
который страница печатала, а модель должна была разглядеть и переписать в
ответ, — лишний шаг, превращавший «заполнил форму» в «нашёл и не опечатался в
восьми символах». Сейчас утверждение модели о своей работе не значит ничего:
либо сервер получил ровно те значения, либо нет.

Ступень одна и берёт форму целиком: текстовые поля, число, выпадающий список,
радиокнопки, флажок, поле, появляющееся только после включения флажка, дата,
поля во вкладках (их не видно, пока по вкладке не кликнули), множественный
выбор, перетаскивание списка и слайдер. Дробить это на десять ступеней смысла
нет: сложность здесь не в отдельном элементе, а в том, чтобы дойти до конца.
"""
import re

NAME = 'webform'
TITLE = 'Browser form filling'
MAX_LEVEL = 10

# Ступени прогона. Внутренние ручки сложности не менялись: здесь
# выбрано, какие из них стоят отдельного замера — одна ступень: вся форма разом — вкладки, перетаскивание, слайдер, условные поля.
LADDER = (10,)
# Версию поднимает тот, кто меняет generate или score: иначе допрогон
# подмешает к новым уровням старые, посчитанные по другим правилам.
# v2: задание требует закрыть за собой вкладку. Прогоны оставляли в
# браузере пользователя по вкладке на уровень, и через десяток моделей
# это уже десятки открытых страниц. Убирать за собой — часть агентной
# работы, а не придирка.
VERSION = 6
CATEGORIES = {'agentic': 1.0}
NEEDS = ['browser', 'network']

# Страница формы. По умолчанию — опубликованная, чтобы задачу можно было
# посмотреть и повторить откуда угодно. Но во время прогона сюда подставляется
# локальный адрес: зависимость от внешнего хоста означает, что чужая сеть
# решает балл. Живой прогон это и показал — модель честно ушла в изолированный
# браузер, получила там обрыв TLS и записала три уровня минимального набора как
# провал, хотя мерилась дорога до GitHub, а не умение заполнять форму.
import os as _os
PUBLIC_URL = 'https://neoxider.github.io/neoxider-benchmark/form.html'


def base_url():
    """Адрес читается в момент генерации, а не при импорте.

    Локальный сервер поднимается уже после того, как модуль задачи загружен,
    и константа, вычисленная на импорте, навсегда осталась бы публичной.
    """
    return _os.environ.get('NXB_FORM_URL') or PUBLIC_URL


BASE_URL = PUBLIC_URL      # для тех, кто смотрит задачу глазами

COUNTRIES = ['Armenia', 'Cyprus', 'Georgia', 'Kazakhstan', 'Portugal', 'Serbia']
PLANS = ['basic', 'pro', 'team']
TOPICS = ['unity', 'dotnet', 'python', 'ai']

# Данные заведомо ненастоящие, и это принципиально. С правдоподобными именем и
# почтой модели упирались в собственные ограничения на персональные данные:
# «Confirmation is required before transmitting the name and email», «the
# browser's security policy blocks entry of the email value». Это осторожность,
# а не неумение заполнить форму, и мерить ею агентный навык нечестно. Домен
# .invalid зарезервирован и существовать не может — сигнал однозначный.
_NAMES = ['Testuser', 'Sampleuser', 'Demouser', 'Fixtureuser', 'Dummyuser', 'Mockuser']
_SURNAMES = ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot']



def _fields_for(level, rng):
    """Какие поля участвуют на этом уровне и какие значения требуются."""
    f = {}
    f['name'] = '%s %s' % (rng.choice(_NAMES), rng.choice(_SURNAMES))
    f['email'] = '%s@benchmark.invalid' % f['name'].split()[0].lower()
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



def generate(level, rng):
    fields = _fields_for(level, rng)
    lines = []
    for k in ORDER:
        if k in fields:
            lines.append('- %s: %s' % (LABELS[k], fields[k]))

    prompt = (
        'Open the page %s?level=%d in a browser\n\n'
        'The page contains a form. Fill it in with exactly these values:\n\n%s\n\n'
        'After filling it in, click the Submit button. The page confirms that the '
        'form was sent; there is nothing to copy back from it.\n\n'
        'Return the answer exactly in the format:\n'
        'DONE\n\n'
        'If filling in the form failed, write exactly:\n'
        'FAILED\n'
        'and the reason on one line. What counts is what the form actually '
        'received, not what the answer claims.\n\n'
        # Об изоляции модель НЕ просим: её обеспечивает запрет на рабочий
        # профиль снаружи. Пока просьба стояла здесь, модели уходили искать
        # «isolated in-app browser», не находили и отвечали «isolated session
        # is unavailable» — теряя на добросовестности первую попытку.
        'The page is a local test fixture and the values above are synthetic, '
        'so no real personal data is involved.\n\n'
        # Про «отцепиться — не значит закрыть» сказано прямо: это ровно та
        # ошибка, на которой мусор и копился. Сессия закрывалась, вкладка
        # оставалась, и человек, просто запустивший бенчмарк, получал свой
        # браузер, забитый группами вкладок.
        'When you are done, close every tab you opened. Detaching from a tab is '
        'not the same as closing it, so check that the tabs are actually gone. '
        "Leaving pages behind in someone else's browser counts against you.\n\n"
        ''
        % (base_url(), level, '\n'.join(lines))
    )
    return prompt, {'level': level, 'fields': fields}


# Балл ставится по тому, что ПРИНЯЛА форма, поэтому задаче нужны сведения о
# вызове: список отправок, накопленных сервером за эту попытку.
WANTS_META = True

_FAILED = re.compile(r'(?mi)^\s*(?:CODE:\s*)?FAILED\b')


def score(output, expected, meta=None):
    subs = [s for s in ((meta or {}).get('submissions') or [])
            if isinstance(s, dict)]
    want = expected['fields']

    # Сначала смотрим, что дошло до формы, и лишь потом — что написано в
    # ответе. Порядок важен: модель, которая всё заполнила правильно, но
    # забыла написать DONE, сделала работу, а модель с идеальным DONE и пустой
    # формой — нет.
    for sub in reversed(subs):
        got = sub.get('fields')
        if not isinstance(got, dict):
            continue
        wrong = [k for k, v in want.items()
                 if str(got.get(k, '')).strip() != str(v).strip()]
        if not wrong:
            return True, 'form received the exact values'
        missing = [k for k in wrong if k not in got]
        detail = 'form received wrong %s' % ', '.join(sorted(wrong)[:4])
        if missing:
            detail += ' (missing %s)' % ', '.join(sorted(missing)[:4])
        return False, detail

    # Форма ничего не получила. Признание в этом — законный ответ,
    # предусмотренный заданием: балла нет, но и штрафа быть не должно, иначе
    # честное «не справился» стоит столько же, сколько уверенное «DONE» поверх
    # пустой формы. Задача помечает это сама: центральный распознаватель
    # отказов смотрит на короткие ответы, а здесь модель объясняет причину и в
    # его рамки не укладывается.
    if _FAILED.search(output or ''):
        return False, 'agent reported failure (honestly)', {'refused': True}
    if re.search(r'(?mi)^\s*(?:CODE:\s*)?DONE\b', output or ''):
        # Сказала «готово», а форма пуста. Это не промах в значении поля и не
        # сбой канала — это утверждение о сделанной работе, которой не было.
        return False, 'answered DONE, but the form received nothing', \
            {'fabricated': 1}
    return False, 'the form received nothing'
