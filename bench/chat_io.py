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


def unmeasurable_in_chat(task, level):
    """Почему уровень нельзя честно померить в чате. None — можно.

    В чате нет инструментов, и это не недостаток модели, а отсутствие канала.
    Две разные причины:

    * задача требует браузера или сети — выполнить её в окне чата нечем;
    * нижние уровни toolchoice проверяют, догадается ли модель ВЗЯТЬ
      инструмент. Без инструментов вопрос теряет смысл. Верхние уровни, где
      инструменты, наоборот, запрещены, в чате измеримы прекрасно — там нечего
      нарушать, и они остаются.
    """
    if getattr(task, 'NEEDS', None):
        return 'no tools in the chat channel'
    floor = getattr(task, 'NO_TOOLS_FROM', None)
    if floor is not None and level < floor:
        return 'this level scores whether the model reaches for a tool'
    return None


def export_prompts(model, seed=20260824, tasks=None, levels=None, profile=None,
                   out_dir='results'):
    """Складывает промпты в файл для ручного или макросного прогона."""
    plan = registry.resolve(tasks=tasks, levels=levels, profile=profile)
    items = []
    for name, lvl in plan:
        task = registry.get(name)
        why = unmeasurable_in_chat(task, lvl)
        if why:
            # Не выгружаем вовсе, а не собираем пустой ответ задним числом:
            # человеку незачем нести в чат задание, которое там физически
            # невыполнимо, и видеть его в списке как «не собрано».
            items.append({'task': name, 'level': lvl,
                          'needs': list(getattr(task, 'NEEDS', [])),
                          'prompt': '', 'answer': '', 'unmeasurable': why})
            continue
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


def audit_answers(path):
    """Что в собранных ответах нельзя оценивать. Пустой список — всё чисто.

    У чат-канала своя порода поломок, и все три встретились живьём:
      - селектор поля ввода перестал совпадать после переименования сайта, и
        каждый промпт записался как молчание модели;
      - оформленный блок кода отдавался без тройных кавычек, и верный ответ
        читался как нарушение формата;
      - селектор ответа совпадал с пузырём пользователя, и «ответом»
        оказывался сам промпт.

    Ни одну из них не видно по баллу — он просто выходит низким. Поэтому
    проверка отдельная, до оценки.
    """
    import json as _json
    with open(path, encoding='utf-8') as fh:
        data = _json.load(fh)

    bad = []
    for it in data.get('items') or []:
        if it.get('unmeasurable'):
            continue
        ans = (it.get('answer') or '').strip()
        where = '%s L%s' % (it['task'], it['level'])
        if not ans:
            continue
        head = ' '.join((it.get('prompt') or '').split())[:120]
        if head and head in ' '.join(ans.split()):
            bad.append((where, 'это эхо промпта, а не ответ'))
            continue
        # Задача просит блок кода, а ограждения нет — почти всегда его срезал
        # интерфейс, а не модель забыла.
        if it['task'] in _CODE_TASKS and '```' not in ans:
            bad.append((where, 'блок кода без ограждения — вероятно срезан интерфейсом'))
    return bad


_CODE_TASKS = ('count', 'path3d', 'pathperf')


def import_answers(path, results_dir='results'):
    """Оценивает собранные ответы и пишет обычный файл результата."""
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)

    # Перед оценкой — проверка собранного. Оценивать эхо промпта или ответ с
    # вырезанным ограждением значит записать нашу поломку в счёт модели.
    spoiled = audit_answers(path)
    if spoiled:
        lines = '\n'.join('  %-14s %s' % w for w in spoiled[:10])
        raise SystemExit(
            'в собранных ответах %d записей, которым нельзя верить:\n%s\n'
            'Это поломка сбора, а не модели. Очистите эти ответы и соберите '
            'их заново, прежде чем считать балл.' % (len(spoiled), lines))

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

        if it.get('unmeasurable'):
            rec['unmeasurable'] = it['unmeasurable']
            skipped += 1
            levels.append(rec)
            continue

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
        'ui_model': data.get('ui_model'),
        # Имя модели в чате задаёт человек в интерфейсе, и проверить его можно
        # только тем, что видно на странице. Не увидели — так и пишем.
        'model_unverified': bool(data.get('model_unverified')),
    }
    run['summary'] = runner.summarize(run)
    run['summary']['unmeasurable'] = skipped
    runner.save(run, results_dir, final=True)
    return run
