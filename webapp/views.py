import json
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from app.presentation import LABELS
from core.errors import GraphError, require
from methods.solvers import solve
from storage.json_io import decode_document, load_document


def response(value, status=200):
    return JsonResponse(value, status=status, json_dumps_params={'ensure_ascii': False, 'allow_nan': False})


def errors(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except GraphError as error:
            return response({'error': error.to_dict()}, 400)
        except (json.JSONDecodeError, UnicodeError, RequestDataTooBig):
            return response({'error': {'code': 'INVALID_JSON', 'message': 'Нужен UTF-8 JSON размером до 20 МиБ.', 'path': '$'}}, 400)
    return wrapped


def body(request):
    require(request.content_type == 'application/json', 'INVALID_FORMAT', 'Запрос должен содержать данные в формате JSON.', '$')
    value = json.loads(request.body)
    require(isinstance(value, dict), 'INVALID_FORMAT', 'Нужен JSON-объект.', '$')
    return value


@require_GET
def index(request):
    return render(request, 'index.html', {'labels': LABELS})


@require_GET
def examples(request):
    return response({'examples': sorted(p.name for p in (settings.BASE_DIR / 'examples').glob('*.json'))})


@require_GET
@errors
def example(request, name):
    folder = settings.BASE_DIR / 'examples'
    require(name == Path(name).name and name in {p.name for p in folder.glob('*.json')},
            'UNKNOWN_EXAMPLE', 'Пример не найден.', 'name')
    graph, extra = load_document(folder / name)
    return response({'document': {'schema_version': 1, 'graph': graph.to_dict(), **extra}})


@require_POST
@errors
def validate(request):
    graph, extra = decode_document(body(request))
    return response({'document': {'schema_version': 1, 'graph': graph.to_dict(), **extra}})


@require_POST
@errors
def run(request):
    data = body(request)
    graph, extra = decode_document(data.get('document'))
    run = solve(graph, data.get('method', 'exact'), data.get('parameters'), data.get('start_id'))
    document = {'schema_version': 1, 'graph': graph.to_dict(), **extra, 'run': run}
    return response({**run, 'document': document})


def csrf_failure(request, reason=''):
    return response({'error': {'code': 'CSRF_FAILED', 'message': 'Проверка защиты запроса не пройдена. Обновите страницу и повторите действие.', 'path': '$'}}, 403)


def not_found(request, exception=None):
    return response({'error': {'code': 'NOT_FOUND', 'message': 'Страница не найдена.', 'path': '$'}}, 404)


def server_error(request):
    return response({'error': {'code': 'SERVER_ERROR', 'message': 'Внутренняя ошибка сервера.', 'path': '$'}}, 500)
