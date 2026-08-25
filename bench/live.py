# -*- coding: utf-8 -*-
"""Живой пульт прогона: страница, которая сама обновляется, пока идут бенчи.

Зачем отдельный сервер, а не файл: страница обязана видеть СВЕЖИЕ отметки, а
они лежат вне репозитория, во временном каталоге сессии, и меняются каждые
несколько секунд. Открытый с диска html туда не дотянется — браузер не пустит
его к произвольному пути.

Сервер намеренно крошечный и на голой стандартной библиотеке: он запускается
рядом с прогоном, на localhost, и не должен ни тянуть зависимости, ни пережить
сам прогон.
"""
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import runner

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(HERE, 'docs', 'live.html')


def snapshot():
    """Отметки о ходе работы плюс то, что считается прямо сейчас."""
    import calendar
    import time as _t
    now = calendar.timegm(_t.gmtime())
    rows = runner.read_progress()
    for r in rows:
        # Сколько секунд назад отметка обновлялась. Считает сервер, а не
        # страница: часы браузера и часы прогона могут расходиться, и тогда
        # «молчит 40 минут» появлялось бы у только что запущенного прогона.
        try:
            then = calendar.timegm(_t.strptime(r.get('updated_utc'), '%Y-%m-%dT%H:%M:%SZ'))
            r['idle_seconds'] = max(0, now - then)
        except (TypeError, ValueError):
            r['idle_seconds'] = None
        # Итог по всему файлу результата: отметка описывает один запуск, а
        # пользователю нужен весь путь модели. Тот же приём, что в --progress.
        if r.get('total_score') is None:
            safe = str(r.get('model', '')).replace('/', '_').replace(':', '_')
            path = os.path.join(HERE, 'results', '%s_%s.json' % (safe, r.get('seed')))
            try:
                with open(path, encoding='utf-8') as fh:
                    saved = json.load(fh)
                r['total_score'] = (saved.get('summary') or {}).get('score')
                r['total_max'] = (saved.get('summary') or {}).get('max_score')
                r['total_levels'] = len(saved.get('levels') or [])
            except (IOError, ValueError, OSError):
                pass
    live = [r for r in rows if not r.get('finished')]
    return {
        'runs': rows,
        'in_flight': len(live),
        'finished': len(rows) - len(live),
        'levels_left': sum(max(0, (r.get('remaining') if r.get('remaining') is not None
                                   else (r.get('planned') or 0) - (r.get('done') or 0)))
                           for r in live),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        # Пульт обязан показывать текущее состояние, а не то, что браузер
        # успел запомнить: без этого страница «замирает» на первом снимке.
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    # Пульт заодно отдаёт сам лидерборд: смотреть результаты хочется прямо
    # отсюда, а публичная страница на GitHub Pages показывает последний
    # запушенный прогон, а не тот, что идёт сейчас.
    TYPES = {'.html': 'text/html; charset=utf-8', '.json': 'application/json; charset=utf-8',
             '.svg': 'image/svg+xml', '.png': 'image/png', '.css': 'text/css',
             '.js': 'text/javascript'}

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path in ('/', '/live.html'):
            try:
                with open(PAGE, encoding='utf-8') as fh:
                    return self._send(200, fh.read(), 'text/html; charset=utf-8')
            except IOError:
                return self._send(500, 'live.html not found', 'text/plain')
        if path == '/progress.json':
            return self._send(200, json.dumps(snapshot(), ensure_ascii=False),
                              'application/json; charset=utf-8')

        docs = os.path.join(HERE, 'docs')
        target = os.path.normpath(os.path.join(docs, path.lstrip('/')))
        # Проверка обязательна: без неё ../ в запросе уводит из docs куда угодно
        # по диску, и локальный сервер раздаёт файлы, о которых его не просили.
        if not target.startswith(docs + os.sep) or not os.path.isfile(target):
            return self._send(404, 'not found', 'text/plain')
        ctype = self.TYPES.get(os.path.splitext(target)[1].lower(),
                               'application/octet-stream')
        mode = 'rb' if ctype.startswith(('image/', 'application/octet')) else 'r'
        kwargs = {} if mode == 'rb' else {'encoding': 'utf-8'}
        with open(target, mode, **kwargs) as fh:
            return self._send(200, fh.read(), ctype)

    def log_message(self, *args):
        # Иначе каждый опрос страницы печатается в консоль поверх лога прогона.
        pass


def serve(port=8791, open_browser=True):
    httpd = HTTPServer(('127.0.0.1', port), Handler)
    url = 'http://127.0.0.1:%d/' % port
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print('live dashboard: %s   (Ctrl+C to stop)' % url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')
    finally:
        httpd.server_close()
