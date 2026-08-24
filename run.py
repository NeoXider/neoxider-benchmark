#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Neoxider Benchmark — точка входа.

Запускается из любого харнесса, в том числе другим агентом.

    python run.py --model opencode/x-preview-f-free --profile minimal
    python run.py --model opencode/x-preview-f-free            # догонит остальное
    python run.py --model claude/claude-opus-5 --tasks spatial --levels 1-3
    python run.py --status --model opencode/x-preview-f-free   # что осталось
    python run.py --list

Прогон ДОКАТЫВАЕТСЯ: уже посчитанные уровни не пересчитываются. Чтобы
пересчитать намеренно — --rerun или --rerun-failed.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bench import models, registry, runner

FREE_OPENCODE = [
    'opencode/x-preview-f-free',
    'opencode/muse-spark-1.2-contributor-free',
    'opencode/pickle-rick-free',
    'opencode/hy3-free',
    'opencode/mimo-free',
    'opencode/nemotron-ultra-free',
    'opencode/lightning-free',
]

PAID = [
    'claude/claude-opus-5',
    'claude/claude-sonnet-5',
    'claude/claude-haiku-4-5-20251001',
    'codex/gpt-5.6-terra',
    'codex/gpt-5.6-sol',
    'codex/gpt-5.6-luna',
]


def parse_levels(spec):
    if not spec:
        return None
    out = []
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(out))


def cmd_list():
    print('Tasks:')
    for name in registry.all_names():
        m = registry.get(name)
        cats = ', '.join('%s x%.1f' % (c, w) for c, w in sorted(m.CATEGORIES.items()))
        needs = (' needs: ' + ','.join(m.NEEDS)) if m.NEEDS else ''
        print('  %-9s L1-%-2d  %-28s [%s]%s'
              % (name, m.MAX_LEVEL, m.TITLE, cats, needs))
    print('\nCategories:')
    for k, v in registry.CATEGORIES.items():
        print('  %-12s %s' % (k, v))
    print('\nProfiles:')
    for k, v in registry.PROFILES.items():
        print('  %-8s levels %s%s' % (k, v['levels'],
                                      '  (no browser)' if v.get('exclude_needs') else ''))
    print('\nEngines in PATH:')
    for k, v in models.available().items():
        print('  %-10s %s' % (k, 'yes' if v else 'NO'))
    print('\nFree opencode:')
    for m in FREE_OPENCODE:
        print('  ' + m)
    print('\nPaid:')
    for m in PAID:
        print('  ' + m)


def main():
    ap = argparse.ArgumentParser(description='Neoxider Benchmark')
    ap.add_argument('--model')
    ap.add_argument('--tasks', help='comma-separated; default: all')
    ap.add_argument('--levels', help='e.g. 1-5 or 1,3,7')
    ap.add_argument('--profile', choices=sorted(registry.PROFILES),
                    help='minimal | quick | full | offline')
    ap.add_argument('--seed', type=int, default=20260824)
    ap.add_argument('--timeout', type=int, default=900)
    ap.add_argument('--cwd', default=None)
    ap.add_argument('--results', default='results')
    ap.add_argument('--rerun', action='store_true', help='recompute everything from scratch')
    ap.add_argument('--rerun-failed', action='store_true',
                    help='recompute failed levels only')
    ap.add_argument('--status', action='store_true', help='show what remains')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--report', action='store_true', help='rebuild the leaderboard')
    ap.add_argument('--export-prompts', action='store_true',
                    help='export prompts for a model without a CLI (chat channel)')
    ap.add_argument('--import-answers', metavar='FILE',
                    help='score answers collected in chat')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    if args.list:
        cmd_list()
        return 0

    if args.report and not args.model:
        from bench import report
        path, n = report.write()
        print('leaderboard: %s, runs: %d' % (path, n))
        return 0

    if args.import_answers:
        from bench import chat_io
        run = chat_io.import_answers(args.import_answers, args.results)
        s = run['summary']
        print('model %s (chat channel)' % run['model'])
        print('score %.1f out of %.0f, unmeasurable levels: %d'
              % (s['score'], s['max_score'], run['unmeasurable']))
        from bench import report
        report.write()
        return 0

    if not args.model:
        ap.error('need --model (or --list / --report)')

    if args.export_prompts:
        from bench import chat_io
        tsk = [t.strip() for t in args.tasks.split(',')] if args.tasks else None
        path, n = chat_io.export_prompts(args.model, args.seed, tsk,
                                         parse_levels(args.levels), args.profile,
                                         args.results)
        print('prompts exported: %d' % n)
        print('file: %s' % path)
        print('Fill in the answer field of each item and then run:')
        print('  python run.py --import-answers %s' % path)
        return 0

    tasks = [t.strip() for t in args.tasks.split(',')] if args.tasks else None
    if tasks:
        unknown = [t for t in tasks if t not in registry.all_names()]
        if unknown:
            ap.error('unknown tasks: %s' % ', '.join(unknown))
    levels = parse_levels(args.levels)

    if args.status:
        st = runner.status(args.model, args.seed, args.results,
                           profile=args.profile, tasks=tasks, levels=levels)
        print('model %s, seed %d' % (args.model, args.seed))
        print('planned: %d, done: %d, remaining: %d'
              % (st['planned'], st['done'], len(st['missing'])))
        if st['missing']:
            by = {}
            for t, l in st['missing']:
                by.setdefault(t, []).append(l)
            for t in sorted(by):
                print('  %-9s levels %s' % (t, ','.join(str(x) for x in sorted(by[t]))))
        return 0

    def progress(rec):
        if args.quiet:
            return
        if '_info' in rec:
            print(rec['_info'], flush=True)
            return
        mark = 'FIX' if rec['fixed'] else ('OK ' if rec['passed'] else 'FAIL')
        note = rec['attempts'][-1]['detail'] if rec['attempts'] else ''
        if rec['fabricated']:
            note += '  [FABRICATED x%d]' % rec['fabricated']
        print('  %-9s L%-2d %-4s %6.1fs  %s'
              % (rec['task'], rec['level'], mark, rec['seconds'], note[:88]), flush=True)

    if not args.quiet:
        print('model: %s   engine: %s   seed: %d   profile: %s'
              % (args.model, models.engine_for(args.model), args.seed,
                 args.profile or 'full'), flush=True)

    run = runner.run_model(args.model, tasks=tasks, levels=levels,
                           profile=args.profile, seed=args.seed,
                           timeout=args.timeout, cwd=args.cwd,
                           results_dir=args.results,
                           rerun=args.rerun, rerun_failed=args.rerun_failed,
                           progress=progress)

    s = run['summary']
    if args.quiet:
        print(json.dumps(s, ensure_ascii=False))
    else:
        print('\n--- summary ---')
        print('score:           %.1f out of %.0f  (levels done: %d)'
              % (s['score'], s['max_score'], s['levels_done']))
        print('first try:       %d,  after fix: %d,  failed: %d'
              % (s['first_try'], s['fixed'], s['failed']))
        if s['fabricated']:
            print('FABRICATED:      %d' % s['fabricated'])
        print('time:            %.1f s' % s['seconds'])
        if s['tokens_total'] is not None:
            print('tokens total:    %d' % s['tokens_total'])
            print('  overhead:      %s' % (s['baseline_tokens'] or '-'))
            print('  net work:      %d' % (s['tokens_net'] or 0))
        else:
            print('tokens:          not reported by the engine')
        if s['per_category']:
            print('by category:')
            for c, v in sorted(s['per_category'].items()):
                print('  %-12s %.2f  %s' % (c, v, registry.CATEGORIES.get(c, '')))

    from bench import report
    report.write()
    return 0


if __name__ == '__main__':
    sys.exit(main())
