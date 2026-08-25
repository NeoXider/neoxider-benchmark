# -*- coding: utf-8 -*-
"""Уборка вкладок, оставленных браузерной задачей.

Просить об этом модель бесполезно как единственную меру: промпт её просит, но
слабая модель уборку не сделает, а сильная не обязана делать её правильно —
и мусор в любом случае оказывается в браузере человека, который просто запустил
бенчмарк. Поэтому здесь подметает сам прогон, после каждого уровня.

Закрываются только вкладки САМОГО бенчмарка — те, чей адрес указывает на его
форму. Всё остальное не трогается: браузер принадлежит пользователю, а не
прогону, и уборщик, закрывающий лишнее, хуже мусора.

Зависимость на web-search-neo мягкая: нет его рядом — уборка молча
пропускается, и прогон продолжается. Бенчмарк не должен падать из-за того, что
не смог прибраться.
"""
import os

# Адрес формы задаётся так же, как в самой задаче: страницу можно поднять
# локально, и тогда вкладки будут вести на localhost, а не на github.io.
_MARKERS = ('neoxider-benchmark', 'form.html')


def _bridge():
    """Модуль web-search-neo, если он доступен. Иначе None."""
    path = os.environ.get('NXB_WSN_PATH') or r'C:\Git\PythonUrlFeatch'
    if not os.path.isdir(path):
        return None
    import sys
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        import chrome_bridge
        return chrome_bridge
    except Exception:      # noqa: BLE001 - уборка не имеет права ронять прогон
        return None


def sweep(markers=_MARKERS):
    """Закрывает оставшиеся вкладки бенчмарка. Возвращает, сколько закрыл."""
    cb = _bridge()
    if cb is None or not hasattr(cb, 'close_current_chrome_tabs'):
        return 0
    try:
        listing = cb.list_current_chrome_tabs(0.0)
    except Exception:      # noqa: BLE001
        return 0
    ids = []
    for tab in (listing.get('tabs') or []):
        if not isinstance(tab, dict):
            continue
        url = str(tab.get('url') or '')
        # Закреплённые не трогаем даже при совпадении адреса: человек мог
        # закрепить страницу формы нарочно, чтобы смотреть на неё.
        if tab.get('pinned'):
            continue
        if any(m in url for m in markers):
            ids.append(tab['id'])
    if not ids:
        return 0
    try:
        # include_claimed: вкладку мог держать сам прогон, и его собственная
        # заявка не повод оставлять мусор.
        out = cb.close_current_chrome_tabs(ids, include_claimed=True)
        return len(out.get('closed') or [])
    except Exception:      # noqa: BLE001
        return 0
