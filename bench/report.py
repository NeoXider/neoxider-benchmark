# -*- coding: utf-8 -*-
"""Сводит результаты прогонов в docs/results.json для лидерборда.

Графики рисует сама страница (инлайновый SVG), поэтому здесь только агрегация:
никаких зависимостей, работает где угодно.
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, 'results')
DOCS = os.path.join(HERE, 'docs')
PRICING = os.path.join(HERE, 'bench', 'pricing.json')


def load_pricing():
    try:
        with open(PRICING, encoding='utf-8') as fh:
            return json.load(fh)
    except (IOError, ValueError):
        return {}


def estimate_cost(model, tokens_breakdown, pricing):
    """Стоимость из прайса. Нет цены — возвращаем None, а не выдуманное число."""
    p = pricing.get(model)
    if not p or not tokens_breakdown:
        return None
    inp = p.get('input_per_mtok')
    out = p.get('output_per_mtok')
    if inp is None or out is None:
        return None
    t_in = tokens_breakdown.get('input', 0) + tokens_breakdown.get('cache_read', 0)
    t_out = tokens_breakdown.get('output', 0) + tokens_breakdown.get('reasoning', 0)
    return round(t_in / 1e6 * inp + t_out / 1e6 * out, 6)


def collect():
    pricing = load_pricing()
    rows = []
    for path in sorted(glob.glob(os.path.join(RESULTS, '*.json'))):
        if os.path.basename(path) == 'index.json':
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                run = json.load(fh)
        except ValueError:
            continue
        s = run.get('summary') or {}
        model = run.get('model', '?')
        meta = pricing.get(model, {})
        cost = s.get('cost_reported')
        cost_src = 'reported'
        if not cost:
            cost = estimate_cost(model, s.get('tokens_breakdown'), pricing)
            cost_src = 'priced' if cost is not None else None
        rows.append({
            'model': model,
            'engine': run.get('engine'),
            'access': meta.get('access', 'unknown'),   # free / paid / unknown
            'seed': run.get('seed'),
            'date': (run.get('started_utc') or '')[:10],
            'score': s.get('score'),
            'max_score': s.get('max_score'),
            'passed': s.get('passed'),
            'first_try': s.get('first_try'),
            'fixed': s.get('fixed'),
            'failed': s.get('failed'),
            'fabricated': s.get('fabricated'),
            'seconds': s.get('seconds'),
            'tokens_total': s.get('tokens_total'),
            'tokens_net': s.get('tokens_net'),
            'baseline_tokens': s.get('baseline_tokens'),
            'cost': cost,
            'cost_source': cost_src,
            'per_task': s.get('per_task') or {},
            'per_category': s.get('per_category') or {},
            'levels_done': s.get('levels_done'),
            'card': 'cards/%s.svg' % model.replace('/', '_').replace(':', '_'),
        })
    rows.sort(key=lambda r: (-(r['score'] or -999), r['model']))
    return rows


def write_cards():
    """Карточка на каждый прогон — SVG в docs/cards/."""
    from . import card
    pricing = load_pricing()
    made = []
    for path in sorted(glob.glob(os.path.join(RESULTS, '*.json'))):
        if os.path.basename(path) == 'index.json':
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                run = json.load(fh)
        except ValueError:
            continue
        if not run.get('summary'):
            continue
        made.append(card.write(run, os.path.join(DOCS, 'cards'), pricing))
    return made


def write():
    rows = collect()
    os.makedirs(DOCS, exist_ok=True)
    write_cards()
    # Тот же приём, что в runner: параллельные прогоны пересобирают лидерборд
    # одновременно, поэтому пишем через уникальный временный файл и подменяем
    # атомарно. Иначе читатель мог поймать наполовину записанный JSON.
    def _atomic(path, data):
        tmp = '%s.%d.tmp' % (path, os.getpid())
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    out = os.path.join(DOCS, 'results.json')
    _atomic(out, {'runs': rows})
    os.makedirs(RESULTS, exist_ok=True)
    _atomic(os.path.join(RESULTS, 'index.json'), {'runs': rows})
    return out, len(rows)


if __name__ == '__main__':
    path, n = write()
    print('записано %s, прогонов: %d' % (path, n))
