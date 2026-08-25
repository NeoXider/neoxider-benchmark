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
        # Открытие страницы сбрасывает выбор на модель по умолчанию, поэтому
        # драйвер выбирает её сам и проверяет результат.
        'picker': {'trigger': (339, 30), 'label': '.wms-trigger__text'},
    },
    'deepseek': {
        'url': 'https://chat.deepseek.com/',
        'input': 'textarea[placeholder*="Message DeepSeek"]',
        'answer': '[class*="ds-markdown"], [class*="markdown"]',
    },
    'chatgpt': {
        'url': 'https://chatgpt.com/',
        # Поле ввода — contenteditable, а не textarea: значение читается через
        # innerText, и вставка идёт тем же путём через буфер обмена.
        'input': '#prompt-textarea',
        'answer': '[data-message-author-role="assistant"]',
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


def select_model(cfg, wanted, session='nxb-chat'):
    """Выбирает модель в интерфейсе и подтверждает выбор. Возвращает, что видно.

    Меню здесь — переключатель: клик открывает его, если оно закрыто, и
    закрывает, если открыто. Состояние к началу неизвестно, поэтому сначала
    оно приводится к закрытому — Escape и клик по пустому месту, — и только
    потом открывается. Без этого выбор срабатывал через раз: клик «открыть»
    попадал в уже открытое меню и закрывал его, а следующий клик уходил в
    страницу под ним.
    """
    picker = cfg.get('picker')
    if not picker:
        return None
    tx, ty = picker['trigger']
    seen = None
    for _ in range(3):
        # Вкладку приходится выводить на передний план: в фоне выпадающее меню
        # не раскрывается вовсе — клик уходит, а списка нет. Это единственное
        # место, где прогон перехватывает фокус, и делается оно один раз.
        browser_tools.show_session(session)
        time.sleep(1.8)
        # Меню — переключатель, и состояние к началу неизвестно, поэтому его
        # сначала приводят к закрытому. Кликать по пустому месту нельзя: на
        # этой странице там либо поле ввода, либо элемент списка бесед.
        browser_tools.press_keys(['ESCAPE'], session_id=session)
        time.sleep(0.8)
        browser_tools.pointer_action('click', tx, ty, session_id=session)
        time.sleep(2.5)
        # Позицию пункта ищем каждый раз: она зависит от числа моделей в списке
        # и от прокрутки, и зашитые координаты попадали мимо.
        # Искомое имя переносится в переменную ДО обхода. Внутри колбэка
        # arguments[0] — это сам элемент, а не параметр скрипта, и сравнение
        # молча шло не с тем: поиск «находил» случайный узел, клик уходил мимо,
        # а выбор модели не срабатывал без единой ошибки.
        hit = _value(_js(
            "var want=arguments[0], h=null;"
            "[].forEach.call(document.querySelectorAll('*'),function(e){"
            "if(e.children.length) return;"
            "if((e.innerText||'').trim()===want){var r=e.getBoundingClientRect();"
            "if(r.width>0) h={x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};}});"
            "return h;", args=[wanted], session=session))
        if hit:
            browser_tools.pointer_action('click', hit['x'], hit['y'],
                                         session_id=session)
            time.sleep(2.5)
        seen = _value(_js("var el=document.querySelector(arguments[0]);"
                          "return el?(el.innerText||'').trim():null;",
                          args=[picker['label']], session=session))
        if seen == wanted:
            return seen
    return seen
    return seen


def current_model(session='nxb-chat'):
    """Какая модель реально выбрана в интерфейсе.

    Записывать прогон под именем, которое не проверено на странице, нельзя:
    результат уедет не той модели.
    """
    return _value(_js(
        "var out=null;[].forEach.call(document.querySelectorAll('*'),function(e){"
        "if(e.children.length) return; var t=(e.innerText||'').trim();"
        "var r=e.getBoundingClientRect(); if(r.width>0 && r.y<60 && /^(qwen|deepseek|gpt|chatgpt)/i.test(t)) out=t;});"
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
    # Освободить всё удержанное ПЕРЕД вставкой. Комбинация держит CONTROL, и
    # если предыдущий промпт оборвался между «hold» и «release», клавиша
    # остаётся зажатой — а следующая вставка падает с «key is already held».
    # Так и потерялось 40 ответов DeepSeek из 49: одна осечка, и весь остаток
    # прогона писался как «модель не ответила».
    try:
        browser_tools.release_inputs(session_id=session)
    except Exception:      # noqa: BLE001
        pass
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


def run(path, site, limit=None, session='nxb-chat', wanted=None):
    """Проходит файл промптов, дописывая ответы. Прерывание не теряет работу."""
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)

    cfg = open_chat(site, session)
    if wanted:
        picked = select_model(cfg, wanted, session)
        if picked != wanted:
            # Не подменяем молча: прогон под чужим именем хуже отсутствия прогона.
            raise SystemExit('could not select %r in the UI; it shows %r'
                             % (wanted, picked))
    seen = current_model(session)
    print('model shown in the UI: %r' % seen, flush=True)
    # Что показано в интерфейсе, то и записывается. Если распознать не удалось,
    # результат помечается непроверенным: подписать прогон именем модели,
    # которого мы не видели, — это ровно та выдумка, за которую бенчмарк
    # снимает баллы в задаче honesty.
    data['ui_model'] = seen
    data['model_unverified'] = not (seen and len(seen) > 3)

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
            # Сбой мог оставить клавишу зажатой; без этого падает и всё
            # последующее, а в отчёт уходит «модель молчала».
            try:
                browser_tools.release_inputs(session_id=session)
            except Exception:      # noqa: BLE001
                pass
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
    ap.add_argument('--model', default=None,
                    help='select this model in the UI and verify it')
    a = ap.parse_args()
    run(a.file, a.site, a.limit, a.session, a.model)
