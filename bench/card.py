# -*- coding: utf-8 -*-
"""Карточка модели: результат прогона одной картинкой.

SVG собирается вручную, без зависимостей — открывается в браузере, вставляется
в README, конвертируется во что угодно. Данные берутся из готового прогона,
ничего не пересчитывается.
"""
import os

W, H = 720, 460
BG = '#0f1115'
FG = '#e6e6e6'
MUTED = '#8b93a1'
ACCENT = '#3b82f6'
GOOD = '#22c55e'
BAD = '#ef4444'
LINE = '#2a2f3a'

CAT_TITLES = {
    'instruction': 'Instruction',
    'logic': 'Logic',
    'spatial': 'Spatial',
    'math': 'Arithmetic',
    'agentic': 'Agentic',
    'honesty': 'Honesty',
}


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _fmt_int(n):
    if n is None:
        return '—'
    return '{:,}'.format(int(n)).replace(',', ' ')


def _fmt_cost(c, src):
    if c is None:
        return '—'
    return '$%.4f%s' % (c, '' if src == 'reported' else '~')


def render(run, pricing=None):
    """run — словарь прогона (results/<model>_<seed>.json)."""
    s = run.get('summary') or {}
    model = run.get('model', '?')
    cats = s.get('per_category') or {}
    per_task = s.get('per_task') or {}

    score = s.get('score') or 0.0
    mx = s.get('max_score') or 1.0
    pct = max(0.0, min(1.0, score / mx if mx else 0.0))

    meta = (pricing or {}).get(model, {})
    weights = meta.get('weights', 'unknown')
    # Тот же расчёт, что и в лидерборде: замер CLI, иначе ставка из прайса.
    # Ноль от бесплатного тарифа ценой не считается — см. report.estimate_cost.
    from .report import estimate_cost
    cost = s.get('cost_reported')
    cost_src = 'reported'
    if not cost:
        cost = estimate_cost(model, s.get('tokens_breakdown'), pricing or {})
        cost_src = 'estimated' if cost is not None else 'reported'
    fabricated = s.get('fabricated') or 0

    p = []
    add = p.append
    add('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="system-ui,-apple-system,Segoe UI,sans-serif">'
        % (W, H, W, H))
    add('<rect width="%d" height="%d" rx="14" fill="%s"/>' % (W, H, BG))
    add('<rect x="0.5" y="0.5" width="%d" height="%d" rx="14" fill="none" stroke="%s"/>'
        % (W - 1, H - 1, LINE))

    # шапка
    add('<text x="28" y="42" fill="%s" font-size="13" letter-spacing="2">'
        'NEOXIDER BENCHMARK</text>' % MUTED)
    add('<text x="28" y="74" fill="%s" font-size="23" font-weight="700">%s</text>'
        % (FG, _esc(model)))
    badge = {'open': ('open weights', GOOD),
             'closed': ('closed weights', ACCENT)}.get(
        weights, ('weights unknown', MUTED))
    if meta.get('local'):
        badge = (badge[0] + ', local', badge[1])
    add('<text x="28" y="96" fill="%s" font-size="12">%s · engine %s · seed %s</text>'
        % (badge[1], _esc(badge[0]), _esc(run.get('engine', '?')), _esc(run.get('seed', '?'))))

    # крупный балл
    add('<text x="%d" y="72" text-anchor="end" fill="%s" font-size="44" '
        'font-weight="700">%.1f</text>' % (W - 28, ACCENT, score))
    add('<text x="%d" y="94" text-anchor="end" fill="%s" font-size="12">of %.0f'
        '</text>' % (W - 28, MUTED, mx))

    # полоса общего результата
    y = 118
    add('<rect x="28" y="%d" width="%d" height="8" rx="4" fill="%s"/>'
        % (y, W - 56, LINE))
    add('<rect x="28" y="%d" width="%.1f" height="8" rx="4" fill="%s"/>'
        % (y, (W - 56) * pct, ACCENT))

    # Отдельная строка про минимальный набор. Общий балл и порог стабильности
    # отвечают на разные вопросы: «насколько далеко модель заходит» и «можно ли
    # на неё положиться в простом». Модель может взять сложный уровень и при
    # этом развалиться на нижнем — одно число это скрывает.
    st, st_max = s.get('stability_score'), s.get('stability_max')
    if st is not None and st_max:
        st_pct = max(0.0, min(1.0, st / st_max))
        ok = st_pct >= 0.999
        add('<text x="28" y="%d" fill="%s" font-size="12">'
            'Stability floor (minimal set) %.1f of %.0f</text>'
            % (y + 26, MUTED, st, st_max))
        add('<text x="%d" y="%d" text-anchor="end" fill="%s" font-size="12" '
            'font-weight="600">%s</text>'
            % (W - 28, y + 26, GOOD if ok else BAD,
               'all clear' if ok else '%d missed' % (s.get('stability_failed') or 0)))
        add('<rect x="28" y="%d" width="%d" height="4" rx="2" fill="%s"/>'
            % (y + 34, W - 56, LINE))
        add('<rect x="28" y="%d" width="%.1f" height="4" rx="2" fill="%s"/>'
            % (y + 34, (W - 56) * st_pct, GOOD if ok else BAD))

    # категории (сдвинуты ниже: над ними теперь строка порога стабильности)
    y = 176
    add('<text x="28" y="%d" fill="%s" font-size="12" letter-spacing="1">'
        'BY CATEGORY</text>' % (y, MUTED))
    y += 18
    bar_x, bar_w = 150, 330
    for key in ('instruction', 'logic', 'spatial', 'math', 'agentic', 'honesty'):
        if key not in cats:
            continue
        v = cats[key]
        add('<text x="28" y="%d" fill="%s" font-size="13">%s</text>'
            % (y + 11, FG, _esc(CAT_TITLES.get(key, key))))
        add('<rect x="%d" y="%d" width="%d" height="10" rx="5" fill="%s"/>'
            % (bar_x, y + 2, bar_w, LINE))
        col = GOOD if v >= 0.75 else (ACCENT if v >= 0.4 else BAD)
        add('<rect x="%d" y="%d" width="%.1f" height="10" rx="5" fill="%s"/>'
            % (bar_x, y + 2, bar_w * max(0.0, min(1.0, v)), col))
        add('<text x="%d" y="%d" fill="%s" font-size="12" '
            'font-family="ui-monospace,Consolas,monospace">%.2f</text>'
            % (bar_x + bar_w + 12, y + 11, MUTED, v))
        y += 24

    # нижние показатели
    y = H - 96
    add('<line x1="28" y1="%d" x2="%d" y2="%d" stroke="%s"/>' % (y, W - 28, y, LINE))
    y += 26
    stats = [
        ('first try', s.get('first_try')),
        ('after fix', s.get('fixed')),
        ('failed', s.get('failed')),
        ('fabricated', fabricated),
    ]
    x = 28
    for label, val in stats:
        col = BAD if (label == 'fabricated' and val) else FG
        add('<text x="%d" y="%d" fill="%s" font-size="20" font-weight="700" '
            'font-family="ui-monospace,Consolas,monospace">%s</text>'
            % (x, y, col, _esc(val if val is not None else '—')))
        add('<text x="%d" y="%d" fill="%s" font-size="11">%s</text>'
            % (x, y + 18, MUTED, _esc(label)))
        x += 118
    # токены и стоимость справа
    add('<text x="%d" y="%d" text-anchor="end" fill="%s" font-size="13" '
        'font-family="ui-monospace,Consolas,monospace">%s tokens</text>'
        % (W - 28, y - 4, FG, _fmt_int(s.get('tokens_net'))))
    add('<text x="%d" y="%d" text-anchor="end" fill="%s" font-size="11">'
        'net, overhead %s</text>'
        % (W - 28, y + 14, MUTED, _fmt_int(s.get('baseline_tokens'))))
    add('<text x="%d" y="%d" text-anchor="end" fill="%s" font-size="11">'
        '%s · %.0f s</text>'
        % (W - 28, y + 30, MUTED, _esc(_fmt_cost(cost, cost_src)),
           s.get('seconds') or 0))

    add('</svg>')
    return '\n'.join(p)


def write(run, out_dir, pricing=None):
    os.makedirs(out_dir, exist_ok=True)
    safe = run['model'].replace('/', '_').replace(':', '_')
    path = os.path.join(out_dir, '%s.svg' % safe)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(render(run, pricing))
    return path
