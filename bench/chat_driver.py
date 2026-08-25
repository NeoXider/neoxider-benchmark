# -*- coding: utf-8 -*-
"""Прогон чат-канала: отправляет промпты в веб-чат и собирает ответы.

Почему не через MCP-инструменты по одному вызову: промптов 57 на модель, и
каждый пришлось бы отправлять отдельным обращением. Здесь тот же браузер
управляется напрямую из Python, и весь список проходится одним запуском.

Про профиль браузера. Всё остальное в бенчмарке намеренно уведено из рабочего
Chrome пользователя, но чат — исключение, и вынужденное: страница отвечает
только залогиненному, а логина у прогона нет и быть не должно. Поэтому берётся
рабочий профиль, ровно одна вкладка, и она закрывается по окончании.
"""
import json
import os
import sys
import time

WSN = os.environ.get('NXB_WSN_PATH') or r'C:\Git\PythonUrlFeatch'
if WSN not in sys.path:
    sys.path.insert(0, WSN)

# Чат — единственное место, где рабочий профиль нужен по существу, поэтому
# общий запрет здесь снимается адресно, а не забывается.
os.environ.pop('WSN_FORBID_CURRENT_PROFILE', None)

import browser_tools  # noqa: E402

SITES = {
    'qwen': {
        'url': 'https://chat.qwen.ai/',
        'input': 'textarea.message-input-textarea',
        'answer': '[class*="markdown"], [class*="message-content"]',
    },
    'deepseek': {
        'url': 'https://chat.deepseek.com/',
        'input': 'textarea[placeholder*="Message DeepSeek"]',
        'answer': '[class*="ds-markdown"], [class*="markdown"]',
    },
}

# Сколько ждать ответа. Рассуждающие режимы думают долго, и обрыв ожидания
# записался бы как пустой ответ модели, то есть как её неудача.
MAX_WAIT = 900
SETTLE = 6           # чаты стримят текст: снимок сразу после остановки обрывочен


def _js(script, args=None, session='nxb-chat', await_promise=False):
    return browser_tools.execute_js(script, args=args or [], session_id=session,
                                    await_promise=await_promise)


def _value(res):
    return (res or {}).get('value')


def open_chat(site, session='nxb-chat'):
    cfg = SITES[site]
    browser_tools.open_page(cfg['url'], session_id=session, profile_mode='current',
                            agent_label='bench-chat')
    time.sleep(4)
    return cfg


def current_model(session='nxb-chat'):
    """Какая модель реально выбрана в интерфейсе.

    Записывать прогон под именем, которое не проверено на странице, нельзя:
    результат уедет не той модели.
    """
    return _value(_js(
        "var out=null;[].forEach.call(document.querySelectorAll('*'),function(e){"
        "if(e.children.length) return; var t=(e.innerText||'').trim();"
        "var r=e.getBoundingClientRect(); if(r.width>0 && r.y<60 && /^(qwen|deepseek)/i.test(t)) out=t;});"
        "return out;", session=session))


def ask(cfg, prompt, session='nxb-chat'):
    """Отправляет один промпт и возвращает ответ или None."""
    # Вставка через буфер обмена: поле ввода живёт на своём фреймворке, и
    # прямая запись в DOM до состояния приложения не доходит.
    _js("return navigator.clipboard.writeText(String(arguments[0]||''))"
        ".then(function(){return true;});",
        args=[prompt], session=session, await_promise=True)
    browser_tools.click(cfg['input'], session_id=session, trusted=True)
    time.sleep(0.4)
    # Комбинация собирается по шагам: press_keys принимает одиночные клавиши,
    # а 'CONTROL+V' одной строкой он не понимает.
    browser_tools.input_batch(key_actions=[
        {'key': 'CONTROL', 'action': 'hold'},
        {'key': 'A', 'action': 'tap'},
        {'key': 'V', 'action': 'tap'},
        {'key': 'CONTROL', 'action': 'release'},
    ], session_id=session)
    time.sleep(0.6)

    filled = _value(_js(
        "var el=document.querySelector(arguments[0]);"
        "var v=el?(el.value!==undefined?el.value:el.innerText):'';return (v||'').length;",
        args=[cfg['input']], session=session))
    if not filled or filled < 20:
        return None

    before = _value(_js(
        "return document.querySelectorAll(arguments[0]).length;",
        args=[cfg['answer']], session=session)) or 0

    browser_tools.press_keys(['ENTER'], session_id=session)

    # Ждём, пока текст перестанет расти: признак, что стрим закончился.
    # Считать по «появился блок» нельзя — блок появляется сразу и пустым.
    deadline = time.time() + MAX_WAIT
    last, stable = '', 0
    while time.time() < deadline:
        time.sleep(3)
        text = _value(_js(
            "var n=document.querySelectorAll(arguments[0]);"
            "if(n.length<=arguments[1]) return '';"
            "var last=n[n.length-1];return (last.innerText||'').trim();",
            args=[cfg['answer'], before], session=session)) or ''
        if text and text == last:
            stable += 1
            if stable >= 3:
                time.sleep(SETTLE)
                return text
        else:
            stable = 0
        last = text
    return last or None


def run(path, site, limit=None, session='nxb-chat'):
    """Проходит файл промптов, дописывая ответы. Прерывание не теряет работу."""
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)

    cfg = open_chat(site, session)
    seen = current_model(session)
    print('model shown in the UI: %r' % seen, flush=True)

    todo = [i for i in data['items']
            if not i.get('unmeasurable') and not (i.get('answer') or '').strip()]
    if limit:
        todo = todo[:limit]
    print('to ask: %d' % len(todo), flush=True)

    for n, item in enumerate(todo, 1):
        t0 = time.time()
        try:
            answer = ask(cfg, item['prompt'], session)
        except Exception as exc:                    # noqa: BLE001
            print('  %-10s L%-2d ERROR %s' % (item['task'], item['level'], exc), flush=True)
            answer = None
        item['answer'] = answer or ''
        # Пишем после КАЖДОГО ответа: прогон длинный, и обрыв на сороковом
        # промпте не должен стоить тридцати девяти собранных.
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        print('  %2d/%d %-10s L%-2d %5.0fs %s' %
              (n, len(todo), item['task'], item['level'], time.time() - t0,
               ('%d chars' % len(answer)) if answer else 'NO ANSWER'), flush=True)

    return path


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='drive a web chat through the prompt file')
    ap.add_argument('--file', required=True)
    ap.add_argument('--site', required=True, choices=sorted(SITES))
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--session', default='nxb-chat')
    a = ap.parse_args()
    run(a.file, a.site, a.limit, a.session)
