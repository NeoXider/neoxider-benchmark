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
import threading
import time


class Result(object):
    def __init__(self, text='', tokens=None, cost=None, seconds=0.0,
                 error=None, raw_meta=None, tools=None, calls=None):
        self.text = text or ''
        self.tokens = tokens          # dict или None
        self.cost = cost              # float или None
        self.seconds = seconds
        self.error = error
        self.raw_meta = raw_meta or {}
        # Имена вызванных инструментов, по порядку. None означает «движок не
        # сообщает», и это НЕ то же самое, что «инструментов не было»:
        # задача toolchoice в таком случае не делает вывода, а помечает
        # результат как неизмеримый.
        self.tools = tools
        self.calls = calls or []

    def as_dict(self):
        return {'tokens': self.tokens, 'cost': self.cost,
                'seconds': round(self.seconds, 2), 'error': self.error,
                'tools': self.tools}


def _zero_tokens():
    return {'input': 0, 'output': 0, 'reasoning': 0, 'cache_read': 0, 'cache_write': 0}


_EXE_IN_CMD = re.compile(r'"([^"]+\.exe)"', re.I)
_JS_IN_CMD = re.compile(r'"([^"]+\.js)"', re.I)


def _unwrap_windows_shim(path):
    """Достаёт настоящий .exe из npm-обёртки .CMD.

    Две попытки запустить иначе провалились, и обе тихо:
      - по голому имени CreateProcess .CMD не находит вовсе — вызов падал
        мгновенно, а в отчёте это выглядело как ноль баллов у модели;
      - через `cmd.exe /c` многострочный промпт разрушается интерпретатором,
        и модель получала пустое задание, отвечая «а что нужно сделать?».
    Сама обёртка всего лишь вызывает соседний .exe, поэтому берём его напрямую:
    ни оболочки, ни экранирования, аргументы уходят как есть.
    """
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            body = fh.read()
    except OSError:
        return None
    here = os.path.dirname(path) + os.sep

    def expand(p):
        return os.path.normpath(p.replace('%~dp0', here).replace('%dp0%', here))

    for m in _EXE_IN_CMD.finditer(body):
        target = expand(m.group(1))
        if os.path.isfile(target):
            return target

    # Обёртки вида `node ... foo.js %*` — запускаем скрипт через node.
    for m in _JS_IN_CMD.finditer(body):
        script = expand(m.group(1))
        if os.path.isfile(script):
            node = os.path.join(here, 'node.exe')
            if not os.path.isfile(node):
                node = shutil.which('node')
            if node:
                return [node, script]
    return None


def _resolve(cmd):
    """Разворачивает имя CLI в исполняемый путь."""
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    if os.name == 'nt' and exe.lower().endswith(('.cmd', '.bat')):
        real = _unwrap_windows_shim(exe)
        if isinstance(real, list):
            return real + list(cmd[1:])
        if real:
            return [real] + list(cmd[1:])
        # запасной путь: через оболочку. Промпт передавать так ненадёжно,
        # поэтому это крайний случай, а не основной режим.
        comspec = os.environ.get('COMSPEC', 'cmd.exe')
        return [comspec, '/c', exe] + list(cmd[1:])
    return [exe] + list(cmd[1:])


# Прогон обязан идти в СВОЁМ браузере, а не в том, где человек работает.
# Просить об этом модель бесполезно: profile_mode по умолчанию — «current», то
# есть рабочий Chrome пользователя, и модель, ни разу не упомянувшая режим,
# попадает именно туда. Переменная включает запрет на стороне web-search-neo:
# любой запрос в рабочий профиль понижается до одноразового браузера.
BENCH_ENV = {'WSN_FORBID_CURRENT_PROFILE': '1'}


def _child_env():
    import os as _os
    env = dict(_os.environ)
    env.update(BENCH_ENV)
    return env


def _run(cmd, timeout, cwd=None, on_output=None):
    """Запускает движок и ЧИТАЕТ вывод по мере поступления.

    Ждать завершения процесса было проще, но тогда во время уровня о нём не
    известно ничего: живая модель, которая пишет ответ пятую минуту, и намертво
    зависшая выглядят одинаково. Движки при этом шлют события построчно, так что
    признак жизни есть — надо просто его не выбрасывать.

    on_output(line) вызывается на каждой строке и не имеет права уронить прогон:
    отчёт о ходе работы — не работа.
    """
    t0 = time.time()
    real = _resolve(cmd)
    if not real:
        return '', '', time.time() - t0, 'CLI not found in PATH: %s' % cmd[0]
    try:
        # stdin закрыт намеренно: codex сообщает «Reading additional input from
        # stdin» и ждёт, если поток открыт, а прогон ему ничего не пришлёт.
        proc = subprocess.Popen(real, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, cwd=cwd, env=_child_env())
    except OSError as e:
        return '', '', time.time() - t0, 'could not launch %s: %s' % (cmd[0], e)

    chunks = []
    errs = []

    def _pump(stream, sink, notify):
        for raw in iter(stream.readline, b''):
            line = raw.decode('utf-8', 'replace')
            sink.append(line)
            if notify and on_output is not None:
                try:
                    on_output(line)
                except Exception:      # noqa: BLE001 - отчёт не роняет прогон
                    pass

    threads = [
        threading.Thread(target=_pump, args=(proc.stdout, chunks, True), daemon=True),
        # stderr читается своим потоком: иначе полный буфер трубы намертво
        # блокирует движок, и прогон ждёт таймаута на пустом месте.
        threading.Thread(target=_pump, args=(proc.stderr, errs, False), daemon=True),
    ]
    for t in threads:
        t.start()
    try:
        proc.wait(timeout=max(1, timeout))
    except subprocess.TimeoutExpired:
        proc.kill()
        for t in threads:
            t.join(timeout=5)
        return ''.join(chunks), ''.join(errs), time.time() - t0, 'timeout %ds' % timeout
    for t in threads:
        t.join(timeout=10)
    return ''.join(chunks), ''.join(errs), time.time() - t0, None


# ------------------------------------------------------------------ opencode

def run_opencode(model, prompt, timeout=900, cwd=None, on_output=None):
    """opencode run --format json: события построчно, в step_finish лежат токены."""
    cmd = ['opencode', 'run', '--format', 'json', '--model', model, prompt]
    out, err, secs, error = _run(cmd, timeout, cwd, on_output)
    if error:
        return Result(seconds=secs, error=error)

    tokens = _zero_tokens()
    cost = 0.0
    chunks = []
    tools = []
    calls = []
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
        elif typ == 'tool_use' or (typ or '').startswith('tool'):
            name = part.get('tool') or part.get('name')
            if name:
                tools.append(name)
                # Аргументы вызова нужны, чтобы поймать подглядывание в сам
                # бенчмарк: предотвратить чтение чужих файлов мы не можем,
                # но зафиксировать факт — можем, и такой прогон помечается
                # недостоверным вместо того, чтобы попасть в лидерборд.
                st = part.get('state') or {}
                calls.append({'tool': name,
                              'input': json.dumps(st.get('input'), ensure_ascii=False)[:400]})
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
                  cost=cost if seen_any else None, seconds=secs, error=error,
                  tools=tools if seen_any else None,
                  calls=calls if seen_any else None)


# -------------------------------------------------------------------- claude

def run_claude(model, prompt, timeout=900, cwd=None, on_output=None):
    """claude -p --output-format json: usage лежит в итоговом объекте."""
    cmd = ['claude', '-p', '--output-format', 'json', '--model', model, prompt]
    out, err, secs, error = _run(cmd, timeout, cwd, on_output)
    if error:
        return Result(seconds=secs, error=error)
    try:
        data = json.loads(out)
    except ValueError:
        return Result(text=out, seconds=secs,
                      error='could not parse the output as JSON' if not out.strip() else None)

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
    # CLI не перечисляет вызовы инструментов, но считает ходы: вызов требует
    # второго хода — модель обращается к инструменту и возвращается с ответом.
    # Одного хода без инструментов достаточно, чтобы отличить одно от другого,
    # а без этого запрет инструментов в toolchoice был непроверяем.
    turns = data.get('num_turns')
    tools = None
    if isinstance(turns, int):
        tools = ['tool round-trip'] if turns > 1 else []
    return Result(text=data.get('result') or data.get('text') or '',
                  tokens=tokens if u else None,
                  cost=data.get('total_cost_usd'),
                  seconds=secs,
                  error=data.get('error'),
                  tools=tools)


# --------------------------------------------------------------------- codex

def run_codex(model, prompt, timeout=900, cwd=None, on_output=None):
    """codex exec --json: события построчно, ответ приходит агентским сообщением.

    --skip-git-repo-check обязателен. Задачи специально решаются в свежей
    временной папке, чтобы агент не видел ни бенчмарка, ни чужих результатов, а
    codex вне доверенного каталога отказывается работать вовсе — и отказ занимал
    считанные секунды, так что в отчёт он ложился неотличимо от «модель не
    справилась». Прогон целиком выглядел как ноль у GPT-5.6, чего на самом деле
    не было.
    """
    cmd = ['codex', 'exec', '--model', model, '--skip-git-repo-check', '--json', prompt]
    out, err, secs, error = _run(cmd, timeout, cwd, on_output)
    if error:
        return Result(seconds=secs, error=error)
    tokens = _zero_tokens()
    seen = False
    chunks = []
    tool_names = []
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
            tokens['cache_write'] += u.get('cache_write_input_tokens', 0) or 0
        # Ответ лежит в item.completed с type=agent_message. Плоских ключей
        # хватало прежним сборкам codex, но в нынешней текст вложен, и без
        # разбора item ответ терялся целиком, а уровень падал на разборе формата.
        item = ev.get('item')
        # Вызовы инструментов приходят отдельными item'ами: command_execution
        # для оболочки, mcp_tool_call для MCP. Без их сбора запрет инструментов
        # на верхних уровнях toolchoice был непроверяем — модель могла посчитать
        # оболочкой, а уровень засчитывался как решённый в уме.
        if isinstance(item, dict):
            kind = item.get('type')
            if kind and kind not in ('agent_message', 'assistant_message', 'reasoning'):
                name = item.get('server_label') or item.get('tool_name') or kind
                if name not in tool_names:
                    tool_names.append(name)
        if isinstance(item, dict) and item.get('type') == 'agent_message':
            v = item.get('text')
            if isinstance(v, str) and v:
                chunks.append(v)
                continue
        for key in ('text', 'message', 'last_agent_message'):
            v = ev.get(key) or (ev.get('msg') or {}).get(key)
            if isinstance(v, str) and v:
                chunks.append(v)
    text = '\n'.join(chunks) if chunks else out
    return Result(text=text, tokens=tokens if seen else None,
                  seconds=secs, error=error, tools=tool_names)


# Какие возможности харнесс реально даёт модели. Таблица ведётся руками и
# обязана соответствовать настройке движков на этой машине: определить её по
# телеметрии нельзя, потому что неиспользованный инструмент и отсутствующий
# выглядят одинаково.
#
# Зачем она вообще: у codex не подключён браузерный MCP, и задача webform у
# него падала на всех уровнях. В отчёт это ложилось как «модель не справилась»,
# хотя мерился не GPT-5.6, а отсутствие инструмента, и три уровня занижали его
# балл. Сравнивать модель, которой дали браузер, с моделью, которой не дали,
# нельзя — такие уровни помечаются неизмеримыми и в счёт не идут.
ENGINE_TOOLS = {
    'opencode': {'browser', 'network', 'shell'},
    'claude':   {'browser', 'network', 'shell'},
    # браузер появился после того, как web-search-neo прописали в
    # ~/.codex/config.toml: раньше webform у codex падал на всех уровнях
    # и мерил отсутствие инструмента. Проверено вызовом:
    # инструмент виден как mcp__web_search_neo__web_action.
    'codex':    {'browser', 'network', 'shell'},
    'chat':     set(),
}


def missing_capabilities(engine, needs):
    """Чего из требуемого задачей у движка нет."""
    have = ENGINE_TOOLS.get(engine)
    if have is None:            # незнакомый движок — не выдумываем ограничений
        return []
    return sorted(set(needs or []) - have)


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


def call(model_id, prompt, timeout=900, cwd=None, on_output=None):
    eng = engine_for(model_id)
    return ENGINES[eng](strip_prefix(model_id), prompt, timeout=timeout, cwd=cwd,
                        on_output=on_output)
