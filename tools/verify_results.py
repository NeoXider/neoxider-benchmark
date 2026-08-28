# -*- coding: utf-8 -*-
"""Проверка собранных результатов ПЕРЕД публикацией.

Здесь собраны те способы соврать числами, на которые бенчмарк за свою короткую
жизнь уже попадался. Каждая проверка стоит не потому, что «так аккуратнее», а
потому, что соответствующая ошибка однажды доехала до таблицы и перевернула
порядок моделей:

  * прогон по СТАРОЙ версии задачи лежит рядом с новым, и сумма складывает два
    разных бенчмарка;
  * уровень, который движок не осилил, уходит из знаменателя, и модель получает
    процент за дистанцию, которую не прошла;
  * пропала верхняя ступень — процент считается по огрызку и оказывается ВЫШЕ,
    чем у тех, кто потолок брал;
  * сборник ответов чат-канала попадает в лидерборд отдельной моделью;
  * честность посчитана там, где несданных уровней не было вовсе;
  * цена посчитана по нулевой ставке и рисует бесконечную эффективность.

Скрипт ничего не чинит: он печатает найденное и возвращает ненулевой код, чтобы
им можно было закрыть публикацию.

    python tools/verify_results.py            # обычный отчёт
    python tools/verify_results.py --strict   # предупреждения тоже валят проверку
"""
import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from bench import registry  # noqa: E402

RESULTS = os.path.join(HERE, 'results')
DOCS = os.path.join(HERE, 'docs')


class Report(object):
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.notes = []

    def error(self, where, what):
        self.errors.append((where, what))

    def warn(self, where, what):
        self.warnings.append((where, what))

    def note(self, what):
        self.notes.append(what)


def load_runs(results_dir):
    runs = []
    for path in sorted(glob.glob(os.path.join(results_dir, '*.json'))):
        if os.path.basename(path) == 'index.json':
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
        except ValueError as exc:
            runs.append((path, None, str(exc)))
            continue
        runs.append((path, data, None))
    return runs


def check_task_versions(runs, rep):
    """Каждый уровень обязан быть посчитан по ТЕКУЩЕЙ версии своей задачи."""
    current = {name: registry.version_of(name) for name in registry.all_names()}
    for path, run, err in runs:
        if not run or not run.get('levels'):
            continue
        stale = collections.Counter()
        for lvl in run['levels']:
            task = lvl.get('task')
            if task not in current:
                rep.error(run.get('model', path), 'уровень неизвестной задачи %r' % task)
                continue
            if lvl.get('task_version') != current[task]:
                stale[task] += 1
        for task, n in sorted(stale.items()):
            rep.error(run.get('model', path),
                      '%s: %d уровней по старой версии задачи (в файле v%s, сейчас v%s)'
                      % (task, n,
                         next((l.get('task_version') for l in run['levels']
                               if l.get('task') == task), '?'),
                         current[task]))


def check_ladder_shape(runs, rep):
    """Набор ступеней обязан совпадать с текущей лестницей задачи."""
    want = {name: registry.get(name).MAX_LEVEL for name in registry.all_names()}
    for path, run, err in runs:
        if not run or not run.get('levels'):
            continue
        have = collections.Counter(l['task'] for l in run['levels'])
        for task, need in sorted(want.items()):
            got = have.get(task, 0)
            if got == 0:
                rep.warn(run.get('model', path), 'задача %s не прогонялась вовсе' % task)
            elif got != need:
                rep.error(run.get('model', path),
                          '%s: ступеней %d, а лестница объявляет %d' % (task, got, need))
        for task in sorted(set(have) - set(want)):
            rep.error(run.get('model', path), 'лишняя задача %s' % task)


def check_unmeasurable(runs, rep):
    """Неизмеримые уровни — законны, но их надо видеть, а потолок терять нельзя."""
    for path, run, err in runs:
        if not run or not run.get('levels'):
            continue
        levels = run['levels']
        model = run.get('model', path)
        top = {}
        for lvl in levels:
            t = lvl['task']
            top[t] = max(top.get(t, 0), lvl['level'])
        un = [l for l in levels if 'unmeasurable' in l]
        if un:
            rep.note('%s: неизмеримых уровней %d из %d' % (model, len(un), len(levels)))
        for lvl in un:
            why = str(lvl.get('unmeasurable'))[:70]
            if lvl['level'] == top.get(lvl['task']):
                rep.error(model,
                          'потерян ПОТОЛОК задачи %s (ступень %d): %s — процент по '
                          'такому прогону считать нельзя'
                          % (lvl['task'], lvl['level'], why))
            else:
                rep.warn(model, '%s L%d неизмерим: %s'
                         % (lvl['task'], lvl['level'], why))


def check_score_arithmetic(runs, rep):
    """Сумма в сводке обязана сходиться с суммой по уровням."""
    for path, run, err in runs:
        if not run or not run.get('levels'):
            continue
        s = run.get('summary') or {}
        counted = [l for l in run['levels'] if 'unmeasurable' not in l]
        total = round(sum(l.get('score') or 0 for l in counted), 4)
        claimed = s.get('score')
        if claimed is not None and abs(total - float(claimed)) > 0.01:
            rep.error(run.get('model', path),
                      'сводка обещает %s, по уровням выходит %s' % (claimed, total))
        mx = s.get('max_score')
        if mx is not None and abs(float(mx) - len(counted)) > 0.01:
            rep.error(run.get('model', path),
                      'знаменатель %s, а измеримых уровней %d' % (mx, len(counted)))


def check_scale_bounds(runs, rep):
    """Ни один уровень не имеет права выйти за пределы объявленной шкалы."""
    from bench.runner import PENALTY_FABRICATION, SCORE_FIRST
    for path, run, err in runs:
        if not run or not run.get('levels'):
            continue
        for lvl in run['levels']:
            sc = lvl.get('score')
            if sc is None:
                rep.error(run.get('model', path),
                          '%s L%s без балла вовсе' % (lvl.get('task'), lvl.get('level')))
                continue
            if sc > SCORE_FIRST + 1e-9 or sc < PENALTY_FABRICATION - 1e-9:
                rep.error(run.get('model', path),
                          '%s L%s балл %s вне шкалы [%s..%s]'
                          % (lvl.get('task'), lvl.get('level'), sc,
                             PENALTY_FABRICATION, SCORE_FIRST))


def check_leaderboard(rep):
    """То, что увидит читатель сайта, а не то, что лежит в results/."""
    path = os.path.join(DOCS, 'results.json')
    if not os.path.isfile(path):
        rep.error('docs/results.json', 'файла нет — лидерборд не собран')
        return
    with open(path, encoding='utf-8') as fh:
        rows = (json.load(fh) or {}).get('runs') or []
    if not rows:
        rep.error('docs/results.json', 'лидерборд пуст')
        return

    seen = collections.Counter(r.get('model') for r in rows)
    for model, n in sorted(seen.items()):
        if n > 1:
            rep.error('лидерборд', 'модель %s встречается %d раза' % (model, n))

    for r in rows:
        model = r.get('model', '?')
        if r.get('items') is not None:
            rep.error('лидерборд', '%s: это сборник ответов, а не прогон' % model)
        pct = r.get('score_pct')
        if pct is not None and r.get('incomplete'):
            rep.error('лидерборд', '%s: процент показан у неполного прогона' % model)
        if pct is not None and not (-100.0 <= pct <= 100.0):
            rep.error('лидерборд', '%s: процент %s вне разумных границ' % (model, pct))
        if r.get('ceiling_missing') and pct is not None:
            rep.error('лидерборд',
                      '%s: потерян потолок %s, но процент всё равно показан'
                      % (model, ', '.join(r['ceiling_missing'])))
        # Честность считается по НЕсданным уровням; у прогона без промахов её
        # быть не должно — иначе это выдуманный замер.
        if r.get('honesty') is not None and not (r.get('failed') or r.get('wrong')
                                                 or r.get('refused')
                                                 or r.get('fabricated')):
            rep.warn('лидерборд', '%s: честность посчитана, хотя промахов нет' % model)
        if r.get('cost') is not None and r['cost'] <= 0:
            rep.error('лидерборд',
                      '%s: цена %s — ноль не цена, а отсутствие ставки'
                      % (model, r['cost']))
        if r.get('channel') not in ('cli', 'chat'):
            rep.warn('лидерборд', '%s: неизвестный канал %r' % (model, r.get('channel')))
    rep.note('в лидерборде строк: %d (cli %d, chat %d)'
             % (len(rows),
                sum(1 for r in rows if r.get('channel') != 'chat'),
                sum(1 for r in rows if r.get('channel') == 'chat')))


def check_comparability(rep):
    """Прогоны, стоящие рядом в таблице, обязаны быть одной длины."""
    path = os.path.join(DOCS, 'results.json')
    if not os.path.isfile(path):
        return
    with open(path, encoding='utf-8') as fh:
        rows = (json.load(fh) or {}).get('runs') or []
    ranked = [r for r in rows if r.get('score_pct') is not None
              and r.get('channel') != 'chat']
    denominators = collections.Counter(r.get('max_score') for r in ranked)
    if len(denominators) > 1:
        rep.error('лидерборд',
                  'в общем зачёте разные знаменатели: %s — это сравнение разных '
                  'дистанций, а читается как разница в силе'
                  % ', '.join('%s у %d моделей' % (k, v)
                              for k, v in sorted(denominators.items(),
                                                 key=lambda kv: -kv[1])))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--results', default=RESULTS)
    ap.add_argument('--strict', action='store_true',
                    help='считать предупреждения ошибками')
    args = ap.parse_args()

    rep = Report()
    runs = load_runs(args.results)
    for path, run, err in runs:
        if err:
            rep.error(os.path.basename(path), 'файл не читается: %s' % err)

    check_task_versions(runs, rep)
    check_ladder_shape(runs, rep)
    check_unmeasurable(runs, rep)
    check_score_arithmetic(runs, rep)
    check_scale_bounds(runs, rep)
    check_leaderboard(rep)
    check_comparability(rep)

    for note in rep.notes:
        print('   .. %s' % note)
    for where, what in rep.warnings:
        print('   ?  %-34s %s' % (where, what))
    for where, what in rep.errors:
        print('  !!  %-34s %s' % (where, what))

    print('\nитог: ошибок %d, предупреждений %d, прогонов проверено %d'
          % (len(rep.errors), len(rep.warnings),
             sum(1 for _, r, e in runs if r and not e)))
    bad = len(rep.errors) + (len(rep.warnings) if args.strict else 0)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
