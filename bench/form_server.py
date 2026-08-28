# -*- coding: utf-8 -*-
"""Локальная выдача страницы формы на время прогона.

Задача webform обращалась к опубликованной странице на GitHub Pages, и это
делало балл заложником внешней сети: обрыв TLS в изолированном браузере
записывался как неумение модели заполнить форму. Здесь та же самая страница
отдаётся с петлевого адреса — без интернета, без сертификатов и без чужой
доступности.

Сервер поднимается один на прогон и живёт в фоновом потоке.
"""
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(HERE, 'docs')

_server = None
_lock = threading.Lock()

# Что форма приняла с момента последнего take(). Подтверждением отправки служит
# именно эта запись, а не строка в ответе модели: страница больше не печатает
# код, переписывать нечего, и выдумать «я отправил» невозможно — либо сервер
# принял значения, либо нет.
_submissions = []
_sub_lock = threading.Lock()


def take():
    """Забирает накопленные отправки и очищает список.

    Забирает, а не читает: у каждой попытки должны быть СВОИ отправки. Иначе
    вторая попытка засчитает форму, которую отправила первая, и уровень,
    проваленный дважды, выглядел бы пройденным.
    """
    with _sub_lock:
        got, _submissions[:] = list(_submissions), []
    return got


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DOCS, **kw)

    def log_message(self, *args):
        # Каждое обращение модели иначе печатается поверх лога прогона.
        pass

    def do_POST(self):
        if self.path.rstrip('/').rsplit('/', 1)[-1] != 'submit':
            self.send_error(404)
            return
        try:
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(n).decode('utf-8')) if n else {}
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return
        with _sub_lock:
            _submissions.append(body)
        payload = b'{"ok":true}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start(port=0):
    """Поднимает сервер (один раз) и возвращает адрес form.html."""
    global _server
    with _lock:
        if _server is None:
            _server = ThreadingHTTPServer(('127.0.0.1', port), _Handler)
            t = threading.Thread(target=_server.serve_forever, daemon=True)
            t.start()
    return 'http://127.0.0.1:%d/form.html' % _server.server_address[1]


def stop():
    global _server
    with _lock:
        if _server is not None:
            _server.shutdown()
            _server.server_close()
            _server = None
