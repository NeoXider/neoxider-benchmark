# -*- coding: utf-8 -*-
"""Реестр задач и категорий.

АРХИТЕКТУРНОЕ ПРАВИЛО НАБОРА (менять только осознанно):

1. Одна задача — одна папка в tasks/. Внутри task.py с обязательными полями
   NAME, TITLE, MAX_LEVEL, CATEGORIES, generate(level, rng), score(output, expected).
   Добавить задачу = положить папку. Ничего больше править не нужно: реестр
   находит её сам.

2. Прогон ДОКАТЫВАЕТСЯ, а не начинается с нуля. Результат хранится по ключу
   (модель, сид, задача, уровень). Новый запуск считает только недостающие
   ключи. Поэтому можно прогнать минимум сегодня, добавить задачу завтра
   и догнать только её — старое переиспользуется.

3. Каждая задача объявляет КАТЕГОРИИ способностей с весами. Оценка по
   категории — среднее по всем уровням всех задач, которые в неё входят.
   Так набор растёт вширь, не ломая сравнимость старых прогонов.
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(HERE, 'tasks')

# Человеческие названия категорий для отчёта.
CATEGORIES = {
    'instruction': 'Следование инструкции',
    'logic': 'Логика и алгоритмы',
    'spatial': 'Пространственное мышление',
    'math': 'Точный счёт',
    'agentic': 'Агентные возможности',
    'honesty': 'Честность',
}

_REQUIRED = ('NAME', 'TITLE', 'MAX_LEVEL', 'CATEGORIES', 'generate', 'score')

# Наборы для быстрых прогонов. minimal — дешёвая проверка, что всё живо.
PROFILES = {
    'minimal': {'levels': [1, 5, 10], 'tasks': None},
    'quick':   {'levels': [1, 3, 5, 7, 10], 'tasks': None},
    'full':    {'levels': list(range(1, 11)), 'tasks': None},
    'offline': {'levels': list(range(1, 11)), 'tasks': None, 'exclude_needs': ['browser']},
}

_cache = None


def _load_module(folder):
    path = os.path.join(TASKS_DIR, folder, 'task.py')
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location('nxb_task_%s' % folder, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    missing = [f for f in _REQUIRED if not hasattr(mod, f)]
    if missing:
        raise ImportError('tasks/%s/task.py: не хватает %s' % (folder, ', '.join(missing)))
    unknown = set(mod.CATEGORIES) - set(CATEGORIES)
    if unknown:
        raise ImportError('tasks/%s/task.py: неизвестные категории %s'
                          % (folder, ', '.join(sorted(unknown))))
    mod.FOLDER = folder
    if not hasattr(mod, 'NEEDS'):
        mod.NEEDS = []          # например ['browser'] или ['network']
    return mod


def discover(force=False):
    """Находит все задачи в tasks/. Порядок — по имени папки."""
    global _cache
    if _cache is not None and not force:
        return _cache
    found = {}
    if os.path.isdir(TASKS_DIR):
        for folder in sorted(os.listdir(TASKS_DIR)):
            if folder.startswith('_') or folder.startswith('.'):
                continue
            if not os.path.isdir(os.path.join(TASKS_DIR, folder)):
                continue
            mod = _load_module(folder)
            if mod:
                found[mod.NAME] = mod
    _cache = found
    return found


def all_names():
    return list(discover().keys())


def get(name):
    tasks = discover()
    if name not in tasks:
        raise KeyError('неизвестная задача %r; есть: %s'
                       % (name, ', '.join(sorted(tasks))))
    return tasks[name]


def resolve(tasks=None, levels=None, profile=None, exclude_needs=None):
    """Возвращает список пар (имя задачи, уровень) для прогона."""
    prof = PROFILES.get(profile or 'full', PROFILES['full'])
    levels = levels or prof['levels']
    names = tasks or prof.get('tasks') or all_names()
    excl = set(exclude_needs or prof.get('exclude_needs') or [])

    plan = []
    for name in names:
        mod = get(name)
        if excl & set(getattr(mod, 'NEEDS', [])):
            continue
        for lvl in levels:
            if lvl <= mod.MAX_LEVEL:
                plan.append((name, lvl))
    return plan


def category_scores(level_records):
    """Оценка по категориям: 0..1, взвешенно по объявленным весам задач.

    Записи с отрицательным баллом (выдумка) считаем как 0 — иначе штраф
    дважды учитывается: и в общем балле, и в категории.
    """
    acc = {}
    for rec in level_records:
        try:
            mod = get(rec['task'])
        except KeyError:
            continue
        norm = max(0.0, min(1.0, rec.get('score', 0.0)))
        for cat, weight in mod.CATEGORIES.items():
            d = acc.setdefault(cat, {'sum': 0.0, 'weight': 0.0})
            d['sum'] += norm * weight
            d['weight'] += weight
    return {c: round(d['sum'] / d['weight'], 3)
            for c, d in acc.items() if d['weight'] > 0}
