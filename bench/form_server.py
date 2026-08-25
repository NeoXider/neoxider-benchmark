# -*- coding: utf-8 -*-
"""Локальная выдача страницы формы на время прогона.

Задача webform обращалась к опубликованной странице на GitHub Pages, и это
делало балл заложником внешней сети: обрыв TLS в изолированном браузере
записывался как неумение модели заполнить форму. Здесь та же самая страница
отдаётся с петлевого адреса — без интернета, без сертификатов и без чужой
доступности.

Сервер поднимается один на прогон и живёт в фоновом потоке.
"""
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(HERE, 'docs')

_server = None
_lock = threading.Lock()


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DOCS, **kw)

    def log_message(self, *args):
        # Каждое обращение модели иначе печатается поверх лога прогона.
        pass


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
