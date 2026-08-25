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

from .runner import MIN_COVERAGE


def load_pricing():
    try:
        with open(PRICING, encoding='utf-8') as fh:
            return json.load(fh)
    except (IOError, ValueError):
        return {}


def estimate_cost(model, tokens_breakdown, pricing):
    """Стоимость из прайса. Нет цены — возвращаем None, а не выдуманное число.

    Бесплатный тариф — не бесплатная модель: за кодовым именем стоят открытые
    веса с публичной рыночной ценой, и стоимость прогона считается по измеренным
    токенам. Ставка берётся из прайса (price_ref в pricing.json указывает, из
    какого именно листинга), поэтому число можно перепроверить по источнику.

    Нулевой прайс при этом ценой не считается: прогон встал бы ровно на нулевую
    ось графика «цена/score» и выглядел бы бесконечно выгодным при любом
    качестве. Это артефакт тарифа, а не сравнение.
    """
    p = pricing.get(model)
    if not p or not tokens_breakdown:
        return None
    inp = p.get('input_per_mtok')
    out = p.get('output_per_mtok')
    if inp is None or out is None:
        return None
    if not inp and not out:
        return None
    t_in = tokens_breakdown.get('input', 0) + tokens_breakdown.get('cache_read', 0)
    t_out = tokens_breakdown.get('output', 0) + tokens_breakdown.get('reasoning', 0)
    return round(t_in / 1e6 * inp + t_out / 1e6 * out, 6)


def collect(results_dir=None):
    pricing = load_pricing()
    rows = []
    for path in sorted(glob.glob(os.path.join(results_dir or RESULTS, '*.json'))):
        if os.path.basename(path) == 'index.json':
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                run = json.load(fh)
        except ValueError:
            continue
        s = run.get('summary') or {}
        model = run.get('model', '?')
        # Полнота считается здесь по самим уровням, а не берётся из сводки: файлы
        # накапливаются между версиями, и у прогонов, записанных до появления
        # порога, поля просто нет — а показать «100%» с трети дистанции хуже,
        # чем показать «неполный».
        levels = run.get('levels') or []
        coverage = s.get('coverage')
        if coverage is None and levels:
            measured = sum(1 for r in levels if 'unmeasurable' not in r)
            coverage = round(measured / float(len(levels)), 3)
        incomplete = (s.get('incomplete') if s.get('incomplete') is not None
                      else (coverage is not None and coverage < MIN_COVERAGE))
        meta = pricing.get(model, {})
        cost = s.get('cost_reported')
        cost_src = 'reported'
        if not cost:
            # cost_reported == 0 у бесплатных тарифов — это не «дёшево», а «нет цены»
            cost = estimate_cost(model, s.get('tokens_breakdown'), pricing)
            cost_src = 'estimated' if cost is not None else None
        rows.append({
            'model': model,
            'engine': run.get('engine'),
            # open / closed / unknown — опубликованы ли веса. Это свойство
            # модели, в отличие от free/paid, который описывал лишь то, как
            # оплачен конкретный прогон: одна и та же модель бывает и такой,
            # и такой, и сравнивать по этому нечего.
            'weights': meta.get('weights', 'unknown'),
            'local': bool(meta.get('local')),
            'weights_ref': meta.get('weights_ref'),
            'seed': run.get('seed'),
            'date': (run.get('started_utc') or '')[:10],
            'score': s.get('score'),
            'max_score': s.get('max_score'),
            # Доля, а не абсолют. Знаменатели у прогонов разные — профиль может
            # быть минимальным или полным, а часть уровней бывает неизмерима, —
            # и сортировка по сырому баллу ставила модель у потолка из 21 ниже
            # модели у потолка из 24. Это сравнение разного, а выглядело как
            # разница в качестве.
            # У неполного прогона процента нет: он посчитался бы от огрызка
            # дистанции и встал бы в таблицу рядом с полными как равный.
            'score_pct': (None if incomplete else
                          (round(100.0 * (s.get('score') or 0) / s['max_score'], 1)
                           if s.get('max_score') else None)),
            'coverage': coverage,
            'incomplete': bool(incomplete),
            # порог стабильности: минимальный набор, считается отдельно
            'stability_score': s.get('stability_score'),
            'stability_max': s.get('stability_max'),
            'stability_failed': s.get('stability_failed'),
            'unmeasurable': s.get('unmeasurable') or 0,
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
            'cost_source': cost_src,          # reported (замерено CLI) | estimated (по прайсу)
            'price_ref': meta.get('price_ref'),
            'per_task': s.get('per_task') or {},
            'per_category': s.get('per_category') or {},
            'levels_done': s.get('levels_done'),
            'card': 'cards/%s.svg' % model.replace('/', '_').replace(':', '_'),
        })
    rows.sort(key=lambda r: (-(r['score_pct'] if r['score_pct'] is not None else -999),
                             -(r['max_score'] or 0), r['model']))
    return rows


def write_cards(results_dir=None):
    """Карточка на каждый прогон — SVG в docs/cards/."""
    from . import card
    pricing = load_pricing()
    made = []
    for path in sorted(glob.glob(os.path.join(results_dir or RESULTS, '*.json'))):
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


def write(results_dir=None):
    """results_dir=None — каталог по умолчанию рядом с бенчмарком.

    Каталог обязан пробрасываться: с --results прогон пишется в свою папку, а
    отчёт молча собирался из каталога по умолчанию и показывал чужие числа.
    """
    results_dir = results_dir or RESULTS
    rows = collect(results_dir)
    os.makedirs(DOCS, exist_ok=True)
    write_cards(results_dir)
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
    os.makedirs(results_dir, exist_ok=True)
    _atomic(os.path.join(results_dir, 'index.json'), {'runs': rows})
    return out, len(rows)


if __name__ == '__main__':
    path, n = write()
    print('записано %s, прогонов: %d' % (path, n))
