# -*- coding: utf-8 -*-
"""Прогон модели по задачам — с докатыванием.

Ключевое свойство: результат хранится по ключу (задача, уровень). Повторный
запуск считает ТОЛЬКО недостающие ключи и дописывает их в тот же файл.
Поэтому можно прогнать minimal сегодня, добавить задачу завтра и догнать
только её — старое не пересчитывается и не теряется.

Пересчитать намеренно: --rerun (всё) или --rerun-failed (только проваленные).

Правило попыток: одна попытка и одна возможность исправиться.
Баллы: 1.0 с первой, 0.5 после правки, 0 провал, -1.0 за выдумку без исправления.
"""
import json
import os
import random
import time

from . import models, registry

SCORE_FIRST = 1.0
SCORE_FIXED = 0.5
SCORE_FAIL = 0.0
PENALTY_FABRICATION = -1.0

BASELINE_PROMPT = 'Ответь ровно одним словом: ок'
SCHEMA_VERSION = 2


def _tok_total(t):
    if not t:
        return None
    return t.get('input', 0) + t.get('output', 0) + t.get('reasoning', 0)


def _sub(a, b):
    if a is None:
        return None
    if b is None:
        return dict(a)
    return {k: max(0, a.get(k, 0) - b.get(k, 0)) for k in a}


def result_path(results_dir, model, seed):
    safe = model.replace('/', '_').replace(':', '_')
    return os.path.join(results_dir, '%s_%s.json' % (safe, seed))


def load_existing(results_dir, model, seed):
    path = result_path(results_dir, model, seed)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except ValueError:
        return None


def measure_baseline(model_id, timeout, cwd):
    """Накладные расходы движка: системный промпт, описания инструментов, правила.

    Без этого замера сравнение нечестное: у разных харнессов стартовый контекст
    отличается в разы, и он попадает в счёт каждой задачи. Измеряется один раз
    на модель и переиспользуется при докатывании.
    """
    r = models.call(model_id, BASELINE_PROMPT, timeout=min(timeout, 180), cwd=cwd)
    return {'tokens': r.tokens, 'cost': r.cost, 'seconds': round(r.seconds, 2),
            'error': r.error, 'sample': (r.text or '')[:80]}


def run_level(model_id, task, level, rng, timeout, cwd, baseline):
    prompt, expected = task.generate(level, rng)

    rec = {'task': task.NAME, 'level': level, 'attempts': [],
           'score': SCORE_FAIL, 'fixed': False, 'passed': False,
           'fabricated': 0, 'seconds': 0.0,
           'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

    tokens_acc = models._zero_tokens()
    cost_acc = 0.0
    have_tokens = False

    for attempt in (1, 2):
        res = models.call(model_id, prompt, timeout=timeout, cwd=cwd)
        rec['seconds'] += res.seconds
        if res.tokens:
            have_tokens = True
            for k in tokens_acc:
                tokens_acc[k] += res.tokens.get(k, 0)
        if res.cost:
            cost_acc += res.cost

        scored = task.score(res.text, expected)
        ok, detail = scored[0], scored[1]
        extra = scored[2] if len(scored) > 2 else {}
        # выдумки считаем по ПОСЛЕДНЕЙ попытке: одумалась — не штрафуем
        rec['fabricated'] = extra.get('fabricated', 0)

        rec['attempts'].append({
            'n': attempt, 'ok': bool(ok), 'detail': detail,
            'seconds': round(res.seconds, 2), 'error': res.error,
            'output_head': (res.text or '')[:400],
        })

        if ok:
            rec['passed'] = True
            rec['score'] = SCORE_FIRST if attempt == 1 else SCORE_FIXED
            rec['fixed'] = (attempt == 2)
            break

        if attempt == 1:
            prompt = ('%s\n\n--- ПРЕДЫДУЩАЯ ПОПЫТКА НЕ ЗАСЧИТАНА ---\n'
                      'Проверка сказала: %s\n'
                      'Исправь ответ. Это последняя попытка. Формат ответа тот же.'
                      % (prompt, detail))

    # Врать хуже, чем молчать: выдумала и не исправилась — уходит в минус.
    if rec['fabricated'] and not rec['passed']:
        rec['score'] = PENALTY_FABRICATION

    rec['tokens_raw'] = tokens_acc if have_tokens else None
    rec['tokens_net'] = _sub(tokens_acc, (baseline or {}).get('tokens')) if have_tokens else None
    rec['cost'] = round(cost_acc, 6) if have_tokens else None
    rec['seconds'] = round(rec['seconds'], 2)
    return rec


def run_model(model_id, tasks=None, levels=None, profile=None, seed=20260824,
              timeout=900, cwd=None, results_dir='results',
              rerun=False, rerun_failed=False, progress=None, save_every=True):
    plan = registry.resolve(tasks=tasks, levels=levels, profile=profile)

    prev = load_existing(results_dir, model_id, seed) or {}
    done = {(r['task'], r['level']): r for r in prev.get('levels', [])}

    # Пересчёт затрагивает ТОЛЬКО текущий план. Иначе `--rerun --tasks count`
    # снёс бы результаты всех остальных задач — а весь смысл файла в том, что
    # он накапливается и его не приходится набирать заново.
    plan_keys = set(plan)
    if rerun:
        done = {k: v for k, v in done.items() if k not in plan_keys}
    elif rerun_failed:
        done = {k: v for k, v in done.items()
                if k not in plan_keys or v.get('passed')}

    todo = [(t, l) for (t, l) in plan if (t, l) not in done]

    out = {
        'schema': SCHEMA_VERSION,
        'model': model_id,
        'engine': models.engine_for(model_id),
        'seed': seed,
        'started_utc': prev.get('started_utc') or
                       time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'baseline': prev.get('baseline'),
        'levels': list(done.values()),
    }

    if progress:
        progress({'_info': 'план %d уровней, из них уже есть %d, считаем %d'
                  % (len(plan), len(plan) - len(todo), len(todo))})

    if not todo:
        out['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        out['summary'] = summarize(out)
        save(out, results_dir)
        return out

    # базовую линию меряем один раз на модель и переиспользуем при докатывании
    if not out['baseline'] or not out['baseline'].get('tokens'):
        out['baseline'] = measure_baseline(model_id, timeout, cwd)

    for tname, lvl in todo:
        task = registry.get(tname)
        # сид детерминирован по (сид, задача, уровень): разные модели получают
        # ОДИНАКОВЫЕ задачи, а добавление новой задачи не сдвигает старые
        rng = random.Random('%d|%s|%d' % (seed, tname, lvl))
        rec = run_level(model_id, task, lvl, rng, timeout, cwd, out['baseline'])
        out['levels'].append(rec)
        if progress:
            progress(rec)
        if save_every:
            out['summary'] = summarize(out)
            save(out, results_dir)

    out['levels'].sort(key=lambda r: (r['task'], r['level']))
    out['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    out['summary'] = summarize(out)
    save(out, results_dir)
    return out


def summarize(run):
    lv = run['levels']
    per_task = {}
    for r in lv:
        d = per_task.setdefault(r['task'], {'score': 0.0, 'passed': 0, 'fixed': 0,
                                            'total': 0, 'seconds': 0.0})
        d['score'] += r['score']
        d['passed'] += 1 if r['passed'] else 0
        d['fixed'] += 1 if r['fixed'] else 0
        d['total'] += 1
        d['seconds'] = round(d['seconds'] + r['seconds'], 1)
    for d in per_task.values():
        d['score'] = round(d['score'], 2)

    tok = models._zero_tokens()
    tok_net = models._zero_tokens()
    have = False
    cost = 0.0
    for r in lv:
        if r.get('tokens_raw'):
            have = True
            for k in tok:
                tok[k] += r['tokens_raw'].get(k, 0)
                tok_net[k] += (r.get('tokens_net') or {}).get(k, 0)
        if r.get('cost'):
            cost += r['cost']

    return {
        'score': round(sum(r['score'] for r in lv), 2),
        'max_score': float(len(lv)),
        'levels_done': len(lv),
        'passed': sum(1 for r in lv if r['passed']),
        'first_try': sum(1 for r in lv if r['passed'] and not r['fixed']),
        'fixed': sum(1 for r in lv if r['fixed']),
        'failed': sum(1 for r in lv if not r['passed']),
        'fabricated': sum(r['fabricated'] for r in lv),
        'seconds': round(sum(r['seconds'] for r in lv), 1),
        'tokens_total': _tok_total(tok) if have else None,
        'tokens_net': _tok_total(tok_net) if have else None,
        'tokens_breakdown': tok if have else None,
        'baseline_tokens': _tok_total((run.get('baseline') or {}).get('tokens')),
        'cost_reported': round(cost, 6) if have else None,
        'per_task': per_task,
        'per_category': registry.category_scores(lv),
    }


def save(run, results_dir='results'):
    os.makedirs(results_dir, exist_ok=True)
    path = result_path(results_dir, run['model'], run['seed'])
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(run, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)     # атомарно: прерванный прогон не портит файл
    return path


def status(model_id, seed, results_dir='results', profile=None,
           tasks=None, levels=None):
    """Что уже посчитано, а что осталось. Для планирования докатывания."""
    plan = registry.resolve(tasks=tasks, levels=levels, profile=profile)
    prev = load_existing(results_dir, model_id, seed) or {}
    done = {(r['task'], r['level']) for r in prev.get('levels', [])}
    missing = [p for p in plan if p not in done]
    return {'planned': len(plan), 'done': len(plan) - len(missing),
            'missing': missing, 'has_file': bool(prev)}
