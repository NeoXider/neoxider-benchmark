# -*- coding: utf-8 -*-
"""Адаптеры к CLI-движкам.

Каждый адаптер обязан вернуть Result: текст ответа, измеренные токены и время.
Токены НЕ оцениваются: если движок их не отдаёт, поле остаётся None и в отчёте
стоит прочерк. Выдуманная цифра хуже отсутствующей.
"""
import json
import os
import re
import shutil
import subprocess
import time


class Result(object):
    def __init__(self, text='', tokens=None, cost=None, seconds=0.0,
                 error=None, raw_meta=None):
        self.text = text or ''
        self.tokens = tokens          # dict или None
        self.cost = cost              # float или None
        self.seconds = seconds
        self.error = error
        self.raw_meta = raw_meta or {}

    def as_dict(self):
        return {'tokens': self.tokens, 'cost': self.cost,
                'seconds': round(self.seconds, 2), 'error': self.error}


def _zero_tokens():
    return {'input': 0, 'output': 0, 'reasoning': 0, 'cache_read': 0, 'cache_write': 0}


def _run(cmd, timeout, cwd=None):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd)
        return p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace'), \
            time.time() - t0, None
    except subprocess.TimeoutExpired:
        return '', '', time.time() - t0, 'timeout %ds' % timeout
    except FileNotFoundError:
        return '', '', time.time() - t0, 'CLI не найден: %s' % cmd[0]


# ------------------------------------------------------------------ opencode

def run_opencode(model, prompt, timeout=900, cwd=None):
    """opencode run --format json: события построчно, в step_finish лежат токены."""
    cmd = ['opencode', 'run', '--format', 'json', '--model', model, prompt]
    out, err, secs, error = _run(cmd, timeout, cwd)
    if error:
        return Result(seconds=secs, error=error)

    tokens = _zero_tokens()
    cost = 0.0
    chunks = []
    seen_any = False
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        typ = ev.get('type')
        part = ev.get('part') or {}
        if typ == 'text':
            chunks.append(part.get('text') or '')
        elif typ == 'step_finish':
            seen_any = True
            t = part.get('tokens') or {}
            tokens['input'] += t.get('input', 0) or 0
            tokens['output'] += t.get('output', 0) or 0
            tokens['reasoning'] += t.get('reasoning', 0) or 0
            c = t.get('cache') or {}
            tokens['cache_read'] += c.get('read', 0) or 0
            tokens['cache_write'] += c.get('write', 0) or 0
            cost += part.get('cost', 0) or 0
        elif typ == 'error':
            error = json.dumps(ev.get('error'), ensure_ascii=False)[:300]

    text = '\n'.join(c for c in chunks if c)
    if not text and err.strip():
        error = error or err.strip()[-300:]
    return Result(text=text, tokens=tokens if seen_any else None,
                  cost=cost if seen_any else None, seconds=secs, error=error)


# -------------------------------------------------------------------- claude

def run_claude(model, prompt, timeout=900, cwd=None):
    """claude -p --output-format json: usage лежит в итоговом объекте."""
    cmd = ['claude', '-p', '--output-format', 'json', '--model', model, prompt]
    out, err, secs, error = _run(cmd, timeout, cwd)
    if error:
        return Result(seconds=secs, error=error)
    try:
        data = json.loads(out)
    except ValueError:
        return Result(text=out, seconds=secs,
                      error='ответ не разобран как JSON' if not out.strip() else None)

    if isinstance(data, list):
        data = data[-1] if data else {}
    u = data.get('usage') or {}
    tokens = {
        'input': u.get('input_tokens', 0) or 0,
        'output': u.get('output_tokens', 0) or 0,
        'reasoning': 0,
        'cache_read': u.get('cache_read_input_tokens', 0) or 0,
        'cache_write': u.get('cache_creation_input_tokens', 0) or 0,
    }
    return Result(text=data.get('result') or data.get('text') or '',
                  tokens=tokens if u else None,
                  cost=data.get('total_cost_usd'),
                  seconds=secs,
                  error=data.get('error'))


# --------------------------------------------------------------------- codex

def run_codex(model, prompt, timeout=900, cwd=None):
    cmd = ['codex', 'exec', '--model', model, '--json', prompt]
    out, err, secs, error = _run(cmd, timeout, cwd)
    if error:
        return Result(seconds=secs, error=error)
    tokens = _zero_tokens()
    seen = False
    chunks = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        u = ev.get('usage') or (ev.get('msg') or {}).get('usage') or {}
        if u:
            seen = True
            tokens['input'] += u.get('input_tokens', 0) or 0
            tokens['output'] += u.get('output_tokens', 0) or 0
            tokens['reasoning'] += (u.get('reasoning_output_tokens', 0) or 0)
            tokens['cache_read'] += u.get('cached_input_tokens', 0) or 0
        for key in ('text', 'message', 'last_agent_message'):
            v = ev.get(key) or (ev.get('msg') or {}).get(key)
            if isinstance(v, str) and v:
                chunks.append(v)
    text = '\n'.join(chunks) if chunks else out
    return Result(text=text, tokens=tokens if seen else None,
                  seconds=secs, error=error)


ENGINES = {
    'opencode': run_opencode,
    'claude': run_claude,
    'codex': run_codex,
}


def engine_for(model_id):
    """Движок определяется префиксом до первого слэша, если он известен."""
    head = model_id.split('/', 1)[0]
    if head in ENGINES:
        return head
    if model_id.startswith('claude-') or model_id in ('opus', 'sonnet', 'haiku'):
        return 'claude'
    if model_id.startswith('gpt-') or model_id.startswith('o3') or model_id.startswith('o4'):
        return 'codex'
    return 'opencode'


def strip_prefix(model_id):
    """opencode/foo -> foo для движков, которым префикс не нужен."""
    head, _, tail = model_id.partition('/')
    if head in ('claude', 'codex') and tail:
        return tail
    return model_id


def available():
    return {name: bool(shutil.which(name)) for name in ENGINES}


def call(model_id, prompt, timeout=900, cwd=None):
    eng = engine_for(model_id)
    return ENGINES[eng](strip_prefix(model_id), prompt, timeout=timeout, cwd=cwd)
