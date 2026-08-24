# -*- coding: utf-8 -*-
"""Канал для моделей, у которых нет CLI: обмен через файлы.

Qwen Max, DeepSeek и старшие режимы вроде Sol Pro доступны только в чате. Гонять
их тем же адаптером нельзя, поэтому прогон разбит на три шага:

    1. export  — бенчмарк выгружает все промпты уровня в JSON;
    2. чат     — макрос web-search-neo (или человек) отправляет их по одному
                 и складывает ответы в тот же формат;
    3. import  — бенчмарк оценивает собранные ответы и пишет обычный результат.

Важное ограничение, и оно записано прямо в результат: у чат-канала НЕТ второй
попытки и НЕТ телеметрии инструментов. Поэтому:
  - балл за уровень либо 1.0, либо 0 — половинок не бывает;
  - задачи, которым нужны инструменты или браузер, помечаются неизмеримыми,
    а не проваленными;
  - токены неизвестны и остаются прочерком, а не выдуманным числом.
Сравнивать такой прогон с CLI-прогоном напрямую нельзя, и в файле стоит
пометка channel=chat, чтобы лидерборд их не смешивал.
"""
import json
import os
import random
import time

from . import registry, runner


def export_prompts(model, seed=20260824, tasks=None, levels=None, profile=None,
                   out_dir='results'):
    """Складывает промпты в файл для ручного или макросного прогона."""
    plan = registry.resolve(tasks=tasks, levels=levels, profile=profile)
    items = []
    for name, lvl in plan:
        task = registry.get(name)
        rng = random.Random('%d|%s|%d' % (seed, name, lvl))
        prompt, _ = task.generate(lvl, rng)
        items.append({
            'task': name,
            'level': lvl,
            'needs': list(getattr(task, 'NEEDS', [])),
            'prompt': prompt,
            'answer': '',          # сюда макрос кладёт ответ модели
        })

    os.makedirs(out_dir, exist_ok=True)
    safe = model.replace('/', '_').replace(':', '_')
    path = os.path.join(out_dir, 'chat_%s_%s.json' % (safe, seed))
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'model': model, 'seed': seed, 'channel': 'chat',
                   'items': items}, fh, ensure_ascii=False, indent=1)
    return path, len(items)


def import_answers(path, results_dir='results'):
    """Оценивает собранные ответы и пишет обычный файл результата."""
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)

    model = data['model']
    seed = data.get('seed', 20260824)
    levels = []
    skipped = 0

    for it in data['items']:
        task = registry.get(it['task'])
        rng = random.Random('%d|%s|%d' % (seed, it['task'], it['level']))
        _, expected = task.generate(it['level'], rng)

        rec = {'task': it['task'], 'level': it['level'], 'attempts': [],
               'score': 0.0, 'fixed': False, 'passed': False,
               'fabricated': 0, 'seconds': 0.0, 'peeked': False,
               'channel': 'chat',
               'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

        answer = (it.get('answer') or '').strip()
        if not answer:
            # Пустой ответ на задачу, требующую инструментов, — это не провал
            # модели, а отсутствие канала. Помечаем неизмеримым.
            if it.get('needs'):
                rec['unmeasurable'] = 'no tools in the chat channel'
                skipped += 1
                levels.append(rec)
                continue
            rec['attempts'].append({'n': 1, 'ok': False, 'detail': 'answer not collected',
                                    'seconds': 0.0, 'error': None, 'output_head': ''})
            levels.append(rec)
            continue

        scored = (task.score(answer, expected, None)
                  if getattr(task, 'WANTS_META', False)
                  else task.score(answer, expected))
        ok, detail = scored[0], scored[1]
        extra = scored[2] if len(scored) > 2 else {}
        rec['fabricated'] = extra.get('fabricated', 0)
        rec['attempts'].append({'n': 1, 'ok': bool(ok), 'detail': detail,
                                'seconds': 0.0, 'error': None,
                                'output_head': answer[:400]})
        if ok:
            rec['passed'] = True
            rec['score'] = runner.SCORE_FIRST
        elif rec['fabricated']:
            rec['score'] = runner.PENALTY_FABRICATION
        levels.append(rec)

    # неизмеримые уровни не должны занижать балл — исключаем их из счёта
    counted = [r for r in levels if 'unmeasurable' not in r]
    run = {
        'schema': runner.SCHEMA_VERSION,
        'model': model,
        'engine': 'chat',
        'channel': 'chat',
        'seed': seed,
        'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'finished_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'baseline': None,
        'levels': counted,
        'unmeasurable': skipped,
        'note': ('chat channel: a single attempt, no tool or token telemetry; '
                 'do not compare directly with CLI runs'),
    }
    run['summary'] = runner.summarize(run)
    run['summary']['unmeasurable'] = skipped
    runner.save(run, results_dir, final=True)
    return run
