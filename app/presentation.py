import json

ROLE_NAMES = {'ordinary': 'обычная', 'green': 'зелёная', 'red': 'красная'}
METHOD_NAMES = {'exact': 'решение системы', 'relaxation': 'последовательная релаксация',
                'finite_horizon': 'конечный горизонт', 'monte_carlo': 'Монте-Карло'}
LABELS = {
    'P': 'Вероятность зелёной цели', 'Q': 'Вероятность красной цели', 'U': 'Вероятность без попадания',
    'probabilities': 'Вероятности по вершинам', 'reference': 'Эталон по вершинам',
    'by_vertex': 'Оценки по вершинам', 'converged': 'Достигнута точность',
    'iterations': 'Число итераций', 'iteration': 'Итерация', 'step': 'Шаг',
    'max_abs_error': 'Максимальное абсолютное отклонение от эталона',
    'max_delta': 'Максимальное изменение', 'trials': 'Число испытаний',
    'counts': 'Число исходов', 'finite_horizon_P': 'Эталон при том же числе шагов',
    'abs_error': 'Абсолютная ошибка', 'method': 'Метод', 'parameters': 'Параметры',
    'start_id': 'Стартовая вершина', 'graph_revision': 'Редакция графа',
    'result': 'Результат', 'history': 'История', 'samples': 'Число испытаний',
    'seed': 'Начальное значение генератора', 'max_steps': 'Лимит шагов',
    'batch_size': 'Период промежуточных оценок', 'tolerance': 'Точность',
    'max_iterations': 'Лимит итераций', 'T': 'Число шагов',
}


def localize_data(value, vertex_ids=False):
    if isinstance(value, dict):
        return {(key if vertex_ids else LABELS.get(key, key)):
                (METHOD_NAMES.get(item, item) if not vertex_ids and key == 'method' and isinstance(item, str)
                 else localize_data(item, not vertex_ids and key in ('probabilities', 'reference', 'by_vertex')))
                for key, item in value.items()}
    if isinstance(value, list):
        return [localize_data(item) for item in value]
    if value is None:
        return 'не задано'
    if type(value) is bool:
        return 'да' if value else 'нет'
    return value


def display_data(value):
    return json.dumps(localize_data(value), ensure_ascii=False, indent=2)


def describe_vertex(vertex, start_id):
    coordinates = vertex.coordinates if vertex.coordinates is not None else 'не заданы'
    return f'{vertex.id}: координаты={coordinates}; роль={ROLE_NAMES[vertex.role]}; старт={"да" if vertex.id == start_id else "нет"}'
