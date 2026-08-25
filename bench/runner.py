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
import glob
import json
import os
import random
import shutil
import tempfile
import time

from . import models, registry

SCORE_FIRST = 1.0
SCORE_FIXED = 0.5
SCORE_FAIL = 0.0
PENALTY_FABRICATION = -1.0

# Сколько раз повторить вызов, если движок сорвался и не вернул текста.
# Это НЕ вторая попытка модели: сбой провайдера не должен стоить ей баллов.
#
# Живой прогон показал, зачем этого мало. Бесплатные провайдеры отдавали
# «unknown certificate verification error» пачками: 35 срывов пережили повтор,
# а 17 съели весь запас и легли в отчёт как провалы модели — с пустым ответом.
# Так hy3 «не смогла» написать код на трёх уровнях подряд, хотя до неё запрос
# просто не дошёл. Отсюда и запас больше, и пауза между попытками, и главное —
# исчерпанный сбой связи считается неизмеримым, а не проваленным.
MAX_TRANSIENT = 6
TRANSIENT_BACKOFF = 4.0

# Какую долю запланированных уровней нужно реально измерить, чтобы балл
# вообще имел смысл. Ниже порога прогон помечается неполным и не получает
# процента: сравнивать 100% с восьми уровней и 97% с восьмидесяти нельзя.
MIN_COVERAGE = 0.9

BASELINE_PROMPT = 'Reply with exactly one word: ok'
SCHEMA_VERSION = 2


# Белый список: только те диагностики, из которых эталон вытащить нельзя.
# Всё остальное схлопывается в общую фразу. Правило простое — если сомневаешься,
# попадает ли строка сюда, значит не попадает.
_SAFE_HINTS = (
    ('```count block not found', 'The answer must be inside a ```count block.'),
    ('code block not found', 'The answer must be inside a code block.'),
    ('function solve not defined', 'The block must define the solve function.'),
    ('solve is not defined', 'solve must be a function.'),
    ('exception', 'The function crashes with an error on the test data.'),
    ('code: line not found', 'The answer lacks a line in the CODE: XXXXXXXX format.'),
    ('answer: line not found', 'The answer lacks a line in the ANSWER: ... format.'),
    ('answers not recognized', 'Answer format not recognized; "<number>: <answer>" lines are required.'),
    ('coordinates not found', 'The answer must have the (x, y, z) format.'),
    ('answer not recognized', 'Answer format not recognized.'),
    ('empty answer', 'The answer is empty.'),
    ('no number in the ANSWER line', 'The ANSWER line has no number.'),
    ('no value for', 'One of the variables is missing from the answer.'),
    ('reported failure', 'Failed to fill in the form.'),
)


def safe_hint(detail):
    """Превращает диагностику проверяльщика в подсказку без эталона."""
    d = (detail or '').lower()
    for needle, text in _SAFE_HINTS:
        if needle in d:
            return text
    return 'The answer is wrong or does not match the required format.'


def _tok_total(t):
    """Все токены, прошедшие через модель, включая прочитанные из кэша.

    Кэш обязательно учитывать. Системный промпт и описания инструментов — это
    примерно 52 тысячи токенов, и в зависимости от попадания в кэш движок
    кладёт их либо в input, либо в cache_read. Считая только input, мы получали
    для одной задачи 216 токенов, а для соседней — 53 423 при одинаковой
    нагрузке. Сравнивать такое нельзя.
    """
    if not t:
        return None
    return (t.get('input', 0) + t.get('cache_read', 0) + t.get('cache_write', 0)
            + t.get('output', 0) + t.get('reasoning', 0))


def _context(t):
    """Токены промпта: и свежие, и прочитанные из кэша."""
    if not t:
        return 0
    return t.get('input', 0) + t.get('cache_read', 0) + t.get('cache_write', 0)


def _generated(t):
    if not t:
        return 0
    return t.get('output', 0) + t.get('reasoning', 0)


def _net_total(raw, baseline_tokens):
    """Чистая работа = (контекст сверх накладного) + сгенерированное.

    Вычитать надо СУММАРНЫЙ контекст, а не каждое поле по отдельности:
    движок распределяет одни и те же 52 тысячи токенов системного промпта
    между input и cache_read по-разному от вызова к вызову. Поле за полем
    получалось, что у задачи с непопавшим кэшем «чистых» 53 406 вместо двухсот.
    """
    if raw is None:
        return None
    over = max(0, _context(raw) - _context(baseline_tokens))
    return over + _generated(raw)


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


def measure_baseline(model_id, timeout, cwd=None):
    """Накладные расходы движка: системный промпт, описания инструментов, правила.

    Без этого замера сравнение нечестное: у разных харнессов стартовый контекст
    отличается в разы, и он попадает в счёт каждой задачи. Измеряется один раз
    на модель и переиспользуется при докатывании.
    """
    ws = cwd or _fresh_workspace()
    try:
        r = models.call(model_id, BASELINE_PROMPT, timeout=min(timeout, 180), cwd=ws)
    finally:
        if cwd is None:
            shutil.rmtree(ws, ignore_errors=True)
    return {'tokens': r.tokens, 'cost': r.cost, 'seconds': round(r.seconds, 2),
            'error': r.error, 'sample': (r.text or '')[:80]}


BENCH_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Что считается подглядыванием: обращение к самому бенчмарку или к рабочим
# папкам соседних прогонов.
_PEEK_MARKERS = ('neoxider-benchmark', os.path.basename(BENCH_ROOT),
                 'nxb_ws_', 'cases.json', 'results/index.json')


def detect_peeking(calls):
    """Ищет в аргументах вызовов инструментов обращения к бенчмарку.

    Предотвратить чтение чужих файлов на одной машине без контейнера нельзя —
    проверено: агент поднимается из выданной временной папки в родительский
    каталог и видит и репозиторий, и папки соседних прогонов. Поэтому здесь
    не защита, а честная отметка: уровень, на котором модель лезла в бенчмарк,
    помечается недостоверным и не должен попадать в сравнение.
    """
    hits = []
    root_low = BENCH_ROOT.lower().replace('\\', '/')
    for c in calls or []:
        blob = ('%s %s' % (c.get('tool', ''), c.get('input', ''))).lower().replace('\\', '/')
        if root_low and root_low in blob:
            hits.append(c)
            continue
        if any(m.lower() in blob for m in _PEEK_MARKERS if m):
            hits.append(c)
    return hits


_SESSION_ROOT = None


def _session_root():
    """Общий корень для рабочих папок одного запуска, с нейтральным именем.

    Не в общем каталоге временных файлов напрямую: там агент видит соседей.
    Проверено живьём — модель перечислила рабочие папки других прогонов по
    префиксу и заодно весь репозиторий бенчмарка.
    """
    global _SESSION_ROOT
    if _SESSION_ROOT is None:
        base = os.environ.get('NXB_WORKROOT') or tempfile.gettempdir()
        _SESSION_ROOT = tempfile.mkdtemp(prefix='', suffix='', dir=base)
    return _SESSION_ROOT


def _fresh_workspace():
    """Пустой каталог для агента, вне репозитория и с неговорящим именем.

    Три причины именно так:
      - при cwd внутри репозитория агент уходит читать сам бенчмарк: в первом
        живом прогоне модель вместо счёта открыла docs/results.json и стала
        пересказывать чужие результаты;
      - говорящий префикс в имени папки подсказывал, что идёт замер, и позволял
        найти соседние прогоны простым перечислением каталога;
      - общий корень на запуск позволяет унести весь замер на другой диск через
        переменную NXB_WORKROOT — например, туда, где репозитория нет вовсе.
    """
    return tempfile.mkdtemp(prefix='', dir=_session_root())


def run_level(model_id, task, level, rng, timeout, cwd, baseline):
    prompt, expected = task.generate(level, rng)
    workspace = cwd or _fresh_workspace()
    owns_workspace = cwd is None

    rec = {'task': task.NAME, 'level': level, 'attempts': [],
           'task_version': getattr(task, 'VERSION', 1),
           'score': SCORE_FAIL, 'fixed': False, 'passed': False,
           'fabricated': 0, 'seconds': 0.0, 'peeked': False, 'peek_calls': [],
           'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

    tokens_acc = models._zero_tokens()
    cost_acc = 0.0
    have_tokens = False

    attempt = 0
    transient = 0
    while attempt < 2:
        res = models.call(model_id, prompt, timeout=timeout, cwd=workspace)
        rec['seconds'] += res.seconds

        # Сбой движка — не ответ модели. Раньше пустой ответ после обрыва сети
        # оценивался как провал: попытка сгорала, модель получала подсказку
        # «почини» на задание, которого не видела, и теряла полбалла за чужой
        # сетевой сбой. Такой вызов повторяется, не тратя попытку.
        blank_failure = res.error and not (res.text or '').strip()
        if blank_failure and transient < MAX_TRANSIENT:
            transient += 1
            rec.setdefault('transient_errors', []).append(str(res.error)[:200])
            # Пауза растёт: сбои идут сериями, и мгновенный повтор попадает в ту
            # же неисправность, тратя запас впустую.
            time.sleep(TRANSIENT_BACKOFF * transient)
            continue
        if blank_failure:
            # Запас исчерпан, а текста от модели так и не было. Записать это
            # провалом — значит поставить ноль за неисправность канала связи.
            rec['unmeasurable'] = ('the engine returned no answer after %d '
                                   'retries: %s' % (transient, str(res.error)[:160]))
            rec['score'] = 0.0
            break
        attempt += 1
        if res.tokens:
            have_tokens = True
            for k in tokens_acc:
                tokens_acc[k] += res.tokens.get(k, 0)
        if res.cost:
            cost_acc += res.cost

        # Задача может попросить сведения о самом вызове — например, чтобы
        # понять, брала ли модель инструмент. Объявляется флагом WANTS_META,
        # чтобы не менять сигнатуру всех остальных задач.
        if getattr(task, 'WANTS_META', False):
            scored = task.score(res.text, expected,
                                {'tools': res.tools, 'seconds': res.seconds,
                                 'tokens': res.tokens})
        else:
            scored = task.score(res.text, expected)
        ok, detail = scored[0], scored[1]
        extra = scored[2] if len(scored) > 2 else {}
        # выдумки считаем по ПОСЛЕДНЕЙ попытке: одумалась — не штрафуем
        rec['fabricated'] = extra.get('fabricated', 0)

        peek = detect_peeking(getattr(res, 'calls', None))
        if peek:
            rec['peeked'] = True
            rec['peek_calls'] = (rec['peek_calls'] + peek)[:6]

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
            # В подсказку идёт ТОЛЬКО безопасный hint от задачи, никогда не
            # detail: detail содержит эталон («ответ 5, эталон 7», «ожидался
            # XXXXXXXX»). Раньше сюда подставлялся detail, и модель могла
            # провалить первую попытку мусором, прочитать правильный ответ и
            # вернуть его за 0.5 балла — вся шкала «после правки» была фиктивной.
            hint = extra.get('hint') or safe_hint(detail)
            prompt = ('%s\n\n--- PREVIOUS ATTEMPT WAS REJECTED ---\n'
                      'What is wrong: %s\n'
                      'Fix the answer. This is the last attempt. The answer format '
                      'stays the same.'
                      % (prompt, hint))

    # Врать хуже, чем молчать: выдумала и не исправилась — уходит в минус.
    if rec['fabricated'] and not rec['passed']:
        rec['score'] = PENALTY_FABRICATION

    # Заглянула в бенчмарк — результат уровня недостоверен. Не штрафуем, но и
    # не засчитываем: балл обнуляется, а факт остаётся в записи.
    if rec['peeked']:
        rec['score_before_peek'] = rec['score']
        rec['score'] = 0.0

    if owns_workspace:
        shutil.rmtree(workspace, ignore_errors=True)

    rec['tokens_raw'] = tokens_acc if have_tokens else None
    rec['tokens_net'] = _net_total(tokens_acc, (baseline or {}).get('tokens')) if have_tokens else None
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

    # Допрогон обязан отличать «уровень уже пройден» от «уровень пройден по
    # ДРУГИМ правилам». Задача может измениться — сместиться генератор, ослабнуть
    # или ужесточиться разбор ответа, — и тогда её старые уровни несравнимы с
    # новыми. Смешать их в одном прогоне значит сложить два разных бенчмарка и
    # выдать сумму за результат. Версия задачи снимает это молча и точечно:
    # устаревают только уровни изменившейся задачи, остальные докатываются как
    # обычно, ради чего накопительный файл и заведён.
    stale = [(t, l) for (t, l) in done
             if (t, l) in plan_keys
             and done[(t, l)].get('task_version') != registry.version_of(t)]
    for key in stale:
        done.pop(key, None)
    if stale and progress:
        by_task = sorted({t for t, _ in stale})
        progress({'_info': 'task changed since the stored run, recomputing '
                           '%d level(s): %s' % (len(stale), ', '.join(by_task))})

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
        progress({'_info': 'plan %d levels, %d already done, computing %d'
                  % (len(plan), len(plan) - len(todo), len(todo))})

    if not todo:
        out['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        out['summary'] = summarize(out)
        save(out, results_dir, final=True)
        return out

    # базовую линию меряем один раз на модель и переиспользуем при докатывании
    if not out['baseline'] or not out['baseline'].get('tokens'):
        out['baseline'] = measure_baseline(model_id, timeout, cwd)

    note_progress(out, len(plan), plan_keys=plan_keys)
    engine = out['engine']
    for tname, lvl in todo:
        note_progress(out, len(plan), current='%s L%d' % (tname, lvl),
                      plan_keys=plan_keys)
        task = registry.get(tname)
        # Задача, требующая инструмента, которого у движка нет, мерит харнесс,
        # а не модель. Ноль за такой уровень занижал бы балл за чужой недостаток,
        # поэтому уровень помечается неизмеримым и в счёт не идёт.
        lack = models.missing_capabilities(engine, getattr(task, 'NEEDS', []))
        if lack:
            out['levels'].append({
                'task': tname, 'level': lvl, 'attempts': [],
                'task_version': getattr(task, 'VERSION', 1),
                'score': 0.0, 'fixed': False, 'passed': False, 'fabricated': 0,
                'seconds': 0.0, 'peeked': False,
                'unmeasurable': 'the %s harness provides no %s'
                                % (engine, ', '.join(lack)),
                'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            })
            if progress:
                progress({'_info': '%s L%d skipped: %s has no %s'
                          % (tname, lvl, engine, ', '.join(lack))})
            continue
        # сид детерминирован по (сид, задача, уровень): разные модели получают
        # ОДИНАКОВЫЕ задачи, а добавление новой задачи не сдвигает старые
        rng = random.Random('%d|%s|%d' % (seed, tname, lvl))
        rec = run_level(model_id, task, lvl, rng, timeout, cwd, out['baseline'])
        out['levels'].append(rec)
        if progress:
            progress(rec)
        if save_every:
            out['summary'] = summarize(out)
            save(out, results_dir)          # черновик вне репозитория
        note_progress(out, len(plan), plan_keys=plan_keys)

    out['levels'].sort(key=lambda r: (r['task'], r['level']))
    out['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    out['summary'] = summarize(out)
    # Перенос готового результата в репозиторий — уже после того, как агент
    # отработал: во время замера рядом с ним не должно быть ничего опознаваемого.
    save(out, results_dir, final=True)
    note_progress(out, len(plan), finished=True, plan_keys=plan_keys)
    return out


def summarize(run):
    # Неизмеримые уровни исключаются целиком: они не провал модели и не успех,
    # и попадание их в знаменатель делало бы балл несравнимым между движками
    # с разным набором инструментов.
    lv = [r for r in run['levels'] if 'unmeasurable' not in r]
    skipped = len(run['levels']) - len(lv)
    # Доля от огрызка — не результат. Исключение неизмеримых уровней правильно,
    # пока их немного, но при обрыве связи на весь прогон оно давало обратное
    # от правды: hy3 потеряла 16 уровней из 24 и вышла с «8.0 из 8.0», то есть
    # со 100%, хотя две трети дистанции просто не проехала. Балл ниже порога
    # полноты не публикуется вовсе — иначе неисправность канала читается как
    # безупречный прогон.
    total = len(run['levels']) or 1
    coverage = round(len(lv) / float(total), 3)
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
    net_sum = 0
    have = False
    cost = 0.0
    for r in lv:
        if r.get('tokens_raw'):
            have = True
            for k in tok:
                tok[k] += r['tokens_raw'].get(k, 0)
            net_sum += r.get('tokens_net') or 0
        if r.get('cost'):
            cost += r['cost']

    # Минимальный набор — отдельная оценка, а не часть общей. Он и задуман как
    # порог стабильной агентской работы: нижние уровни каждой задачи, которые
    # рабочая модель обязана брать все. Поэтому 100% здесь — нормальный, ожидаемый
    # результат, тогда как 100% по всему бенчмарку означал бы, что мерить больше
    # нечего. Смешивать их в одно число нельзя: провал на потолке и провал на полу
    # говорят о модели совершенно разное.
    min_levels = set(registry.PROFILES['minimal']['levels'])
    mlv = [r for r in lv if r['level'] in min_levels]

    return {
        'score': round(sum(r['score'] for r in lv), 2),
        'max_score': float(len(lv)),
        'unmeasurable': skipped,
        'coverage': coverage,
        'incomplete': coverage < MIN_COVERAGE,
        'stability_score': round(sum(r['score'] for r in mlv), 2) if mlv else None,
        'stability_max': float(len(mlv)) if mlv else None,
        'stability_failed': sum(1 for r in mlv if not r['passed']) if mlv else None,
        'levels_done': len(lv),
        'passed': sum(1 for r in lv if r['passed']),
        'first_try': sum(1 for r in lv if r['passed'] and not r['fixed']),
        'fixed': sum(1 for r in lv if r['fixed']),
        'failed': sum(1 for r in lv if not r['passed']),
        'fabricated': sum(r['fabricated'] for r in lv),
        'peeked': sum(1 for r in lv if r.get('peeked')),
        'seconds': round(sum(r['seconds'] for r in lv), 1),
        'tokens_total': _tok_total(tok) if have else None,
        'tokens_net': net_sum if have else None,
        'tokens_breakdown': tok if have else None,
        'baseline_tokens': _tok_total((run.get('baseline') or {}).get('tokens')),
        'baseline_context': _context((run.get('baseline') or {}).get('tokens')),
        'cost_reported': round(cost, 6) if have else None,
        'per_task': per_task,
        'per_category': registry.category_scores(lv),
    }


def staging_path(run):
    """Куда пишется прогон, пока он идёт: вне репозитория, рядом не с чем.

    Промежуточные результаты нельзя держать в самом репозитории: в первом живом
    прогоне модель нашла results/ и прочитала оттуда чужие цифры вместо решения
    задачи. Поэтому во время замера файл лежит в изолированном корне запуска, а
    в repo переносится готовым — уже после того, как агент отработал.
    """
    return os.path.join(_session_root(), 'run_%s_%s.json'
                        % (run['model'].replace('/', '_').replace(':', '_'),
                           run['seed']))


def _write_json(path, data):
    # Имя временного файла уникально для процесса. С общим '<path>.tmp' два
    # параллельных прогона писали в один и тот же файл и затирали друг друга
    # ещё до os.replace — при параллельном запуске моделей это молча теряло
    # результаты.
    tmp = '%s.%d.tmp' % (path, os.getpid())
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)     # атомарно: прерванный прогон не портит файл
    return path


def progress_dir():
    """Куда прогоны кладут отметки о ходе работы.

    Отдельно от черновиков результата: у каждого прогона свой случайный рабочий
    корень, поэтому со стороны узнать, где он, нельзя — а посмотреть, идёт ли
    дело и сколько осталось, нужно снаружи и на ходу. Каталог фиксированный и
    лежит вне репозитория: рядом с агентом не должно оказаться ничего, что
    указывает на бенчмарк, а внутри одни счётчики — ни задач, ни ответов.
    """
    base = os.environ.get('NXB_PROGRESS') or os.path.join(
        tempfile.gettempdir(), 'nxb-progress')
    os.makedirs(base, exist_ok=True)
    return base


def _progress_path(model, seed):
    safe = str(model).replace('/', '_').replace(':', '_')
    return os.path.join(progress_dir(), '%s_%s.json' % (safe, seed))


def note_progress(run, planned, current=None, finished=False, plan_keys=None):
    """Отметка о ходе прогона: сколько сделано, что идёт сейчас, когда обновлено.

    Считаются уровни ТЕКУЩЕГО плана, а не все в файле. Файл накопительный, и при
    точечном запуске вроде `--tasks webform --levels 1-3` прогресс показывал
    «24/3»: в знаменателе план, в числителе всё прошлое.
    """
    lv = run.get('levels') or []
    if plan_keys is not None:
        lv = [r for r in lv if (r['task'], r['level']) in plan_keys]
    try:
        _write_json(_progress_path(run['model'], run['seed']), {
            'model': run['model'],
            'engine': run.get('engine'),
            'seed': run.get('seed'),
            'planned': planned,
            'done': len(lv),
            'passed': sum(1 for r in lv if r.get('passed')),
            # Неизмеримый уровень не провал: в сводке прогона он уже исключён,
            # а здесь считался как неудача, и модель, до которой не дошёл ни один
            # запрос, показывалась как «провалила всё».
            'failed': sum(1 for r in lv
                          if not r.get('passed') and 'unmeasurable' not in r),
            'score': round(sum(r.get('score') or 0 for r in lv), 2),
            'seconds': round(sum(r.get('seconds') or 0 for r in lv), 1),
            'current': current,
            # Сколько ещё и сколько это займёт. Без остатка и оценки времени
            # видно только «идёт», и понять, ждать минуту или час, нельзя.
            'remaining': max(0, planned - len(lv)),
            'unmeasurable': sum(1 for r in lv if 'unmeasurable' in r),
            'eta_seconds': (round((planned - len(lv)) *
                                  (sum(r.get('seconds') or 0 for r in lv) / len(lv)))
                            if lv and planned > len(lv) else (0 if finished else None)),
            'finished': bool(finished),
            # Итог по ВСЕМУ накопленному файлу, а не только по текущему плану.
            # Точечный перезапуск на два уровня показывал Opus как «2/2, 0.0»,
            # и модель с 77.5 из 82 читалась в сводке как полный ноль.
            'total_levels': len(run.get('levels') or []),
            'total_score': round(sum(r.get('score') or 0
                                     for r in (run.get('levels') or [])), 2),
            'started_utc': run.get('started_utc'),
            'updated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        })
    except Exception:
        # Отчёт о ходе работы не имеет права уронить сам прогон.
        pass


def read_progress():
    """Все известные отметки, свежие сверху."""
    out = []
    for path in sorted(glob.glob(os.path.join(progress_dir(), '*.json'))):
        try:
            with open(path, encoding='utf-8') as fh:
                out.append(json.load(fh))
        except (IOError, ValueError):
            continue
    return out


def save(run, results_dir='results', final=False):
    """final=False — черновик в изолированный корень, True — перенос в репозиторий."""
    if not final:
        return _write_json(staging_path(run), run)
    os.makedirs(results_dir, exist_ok=True)
    return _write_json(result_path(results_dir, run['model'], run['seed']), run)


def status(model_id, seed, results_dir='results', profile=None,
           tasks=None, levels=None):
    """Что уже посчитано, а что осталось. Для планирования докатывания."""
    plan = registry.resolve(tasks=tasks, levels=levels, profile=profile)
    prev = load_existing(results_dir, model_id, seed) or {}
    done = {(r['task'], r['level']) for r in prev.get('levels', [])}
    missing = [p for p in plan if p not in done]
    return {'planned': len(plan), 'done': len(plan) - len(missing),
            'missing': missing, 'has_file': bool(prev)}
