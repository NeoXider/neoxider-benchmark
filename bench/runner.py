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
import shutil
import tempfile
import time

from . import models, registry

SCORE_FIRST = 1.0
SCORE_FIXED = 0.5
SCORE_FAIL = 0.0
PENALTY_FABRICATION = -1.0

BASELINE_PROMPT = 'Ответь ровно одним словом: ок'
SCHEMA_VERSION = 2


# Белый список: только те диагностики, из которых эталон вытащить нельзя.
# Всё остальное схлопывается в общую фразу. Правило простое — если сомневаешься,
# попадает ли строка сюда, значит не попадает.
_SAFE_HINTS = (
    ('блок ```count не найден', 'Ответ должен быть внутри блока ```count.'),
    ('блок кода не найден', 'Ответ должен быть внутри блока кода.'),
    ('функция solve не определена', 'В блоке должна быть функция solve.'),
    ('solve не является функцией', 'solve должна быть функцией.'),
    ('код не исполняется', 'Код не запускается — проверь синтаксис и импорты.'),
    ('исключение', 'Функция падает с ошибкой на проверочных данных.'),
    ('строка CODE: не найдена', 'В ответе нет строки в формате CODE: XXXXXXXX.'),
    ('строка ANSWER: не найдена', 'В ответе нет строки в формате ANSWER: ...'),
    ('ответы не распознаны', 'Формат ответа не распознан, нужен «<номер>: <ответ>».'),
    ('координаты не найдены', 'Нужен ответ в формате (x, y, z).'),
    ('ответ не распознан', 'Формат ответа не распознан.'),
    ('пустой ответ', 'Ответ пустой.'),
    ('число в ответе не найдено', 'В строке ANSWER нет числа.'),
    ('не найдено значение', 'В ответе не хватает одной из переменных.'),
    ('агент сообщил о неудаче', 'Форму заполнить не удалось.'),
)


def safe_hint(detail):
    """Превращает диагностику проверяльщика в подсказку без эталона."""
    d = (detail or '').lower()
    for needle, text in _SAFE_HINTS:
        if needle in d:
            return text
    return 'Ответ неверный либо не соответствует требуемому формату.'


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
           'score': SCORE_FAIL, 'fixed': False, 'passed': False,
           'fabricated': 0, 'seconds': 0.0, 'peeked': False, 'peek_calls': [],
           'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

    tokens_acc = models._zero_tokens()
    cost_acc = 0.0
    have_tokens = False

    for attempt in (1, 2):
        res = models.call(model_id, prompt, timeout=timeout, cwd=workspace)
        rec['seconds'] += res.seconds
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
            prompt = ('%s\n\n--- ПРЕДЫДУЩАЯ ПОПЫТКА НЕ ЗАСЧИТАНА ---\n'
                      'Что не так: %s\n'
                      'Исправь ответ. Это последняя попытка. Формат ответа тот же.'
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
        save(out, results_dir, final=True)
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
            save(out, results_dir)          # черновик вне репозитория

    out['levels'].sort(key=lambda r: (r['task'], r['level']))
    out['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    out['summary'] = summarize(out)
    # Перенос готового результата в репозиторий — уже после того, как агент
    # отработал: во время замера рядом с ним не должно быть ничего опознаваемого.
    save(out, results_dir, final=True)
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

    return {
        'score': round(sum(r['score'] for r in lv), 2),
        'max_score': float(len(lv)),
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
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)     # атомарно: прерванный прогон не портит файл
    return path


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
