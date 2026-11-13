from math import fsum
from random import Random
import warnings

from core.errors import GraphError, require
from core.model import Graph, is_number
from .probability import build_system, normalize_weights

DEFAULTS = {
    'exact': {},
    'relaxation': {'tolerance': 1e-6, 'max_iterations': 10000},
    'monte_carlo': {'samples': 10000, 'seed': 42, 'max_steps': 1000, 'batch_size': 1000},
    'finite_horizon': {'T': 10},
}


def validate_parameters(method, parameters=None):
    require(type(method) is str and method in DEFAULTS, 'INVALID_METHOD',
            'Метод: exact, relaxation, monte_carlo, finite_horizon.', 'method')
    require(parameters is None or isinstance(parameters, dict), 'INVALID_PARAMETER',
            'Параметры должны быть объектом.', 'parameters')
    result = DEFAULTS[method].copy()
    for key, value in (parameters or {}).items():
        require(key in result, 'INVALID_PARAMETER', 'Неизвестный параметр метода.', str(key))
        if key == 'tolerance':
            valid = is_number(value) and value > 0
        else:
            valid = type(value) is int and (key == 'seed' or value >= (0 if key in ('T', 'max_steps') else 1))
        require(valid, 'INVALID_PARAMETER', 'Проверьте тип и допустимый диапазон параметра.', key)
        result[key] = value
    return result


def exact_probabilities(graph, system=None):
    system = system or build_system(graph)
    probabilities = system.boundary.copy()
    if system.unknowns:

        try:
            import numpy as np
            from scipy.sparse import csc_matrix
            from scipy.sparse.linalg import MatrixRankWarning, spsolve
        except ImportError as error:
            raise GraphError('DEPENDENCY_MISSING', 'Для решения системы установите зависимости: pip install -r requirements.txt') from error
        row_ids, columns, data = [], [], []
        for i, row in enumerate(system.rows):
            for j, value in row.items():
                row_ids.append(i)
                columns.append(j)
                data.append(value)
        matrix = csc_matrix((data, (row_ids, columns)), shape=(len(system.rows), len(system.rows)))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', MatrixRankWarning)
                solution = spsolve(matrix, np.asarray(system.rhs))
            require(bool(np.all(np.isfinite(solution))), 'NUMERICAL_ERROR', 'Система численно неустойчива.')
            residual = max(abs(matrix @ solution - system.rhs), default=0)
            require(residual < 1e-8 and bool(np.all((solution >= -1e-8) & (solution <= 1 + 1e-8))),
                    'NUMERICAL_ERROR', 'Не удалось получить устойчивое решение системы.')
        except (MatrixRankWarning, RuntimeError) as error:
            raise GraphError('NUMERICAL_ERROR', 'Не удалось решить систему для указанных весов.') from error
        probabilities.update((key, min(1.0, max(0.0, float(value)))) for key, value in zip(system.unknowns, solution))
    return {v.id: probabilities[v.id] for v in graph.vertices}


def horizon_steps(graph, transitions, horizon):
    p = {v.id: float(v.role == 'green') for v in graph.vertices}
    q = {v.id: float(v.role == 'red') for v in graph.vertices}
    for step in range(horizon + 1):
        yield step, {key: {'P': p[key], 'Q': q[key], 'U': max(0.0, 1.0 - p[key] - q[key])} for key in p}
        if step < horizon:
            p = {v.id: (p[v.id] if v.role != 'ordinary' else fsum(w * p[t] for t, w in transitions[v.id])) for v in graph.vertices}
            q = {v.id: (q[v.id] if v.role != 'ordinary' else fsum(w * q[t] for t, w in transitions[v.id])) for v in graph.vertices}


def solve(graph: Graph, method='exact', parameters=None, start_id=None, emit=None, cancel=None):

    parameters = validate_parameters(method, parameters)
    start_id = graph.start_id if start_id is None else start_id
    require(type(start_id) is str and start_id in graph.by_id, 'INVALID_START',
            'Для расчёта выберите существующую стартовую вершину.', 'start_id')
    history = []

    def record(item):
        if cancel and cancel():
            raise GraphError('CANCELLED', 'Расчёт отменён.')
        history.append(item)
        if emit:
            emit(item)

    if method in ('exact', 'relaxation'):
        system = build_system(graph)
        reference = exact_probabilities(graph, system)
        if method == 'exact':
            result = {'P': reference[start_id], 'probabilities': reference}
        else:
            values = {v.id: system.boundary.get(v.id, 0.0) for v in graph.vertices}
            error = max(abs(values[key] - reference[key]) for key in values)
            record({'iteration': 0, 'probabilities': values.copy(), 'max_abs_error': error, 'max_delta': 0.0})
            iteration = 0
            while error > parameters['tolerance'] and iteration < parameters['max_iterations']:
                delta = 0.0
                for key in system.unknowns:
                    value = fsum(p * values[target] for target, p in system.transitions[key])
                    delta = max(delta, abs(value - values[key]))
                    values[key] = value
                iteration += 1
                error = max(abs(values[key] - reference[key]) for key in values)
                record({'iteration': iteration, 'probabilities': values.copy(), 'max_abs_error': error, 'max_delta': delta})
            result = {'P': values[start_id], 'probabilities': values, 'reference': reference,
                      'converged': error <= parameters['tolerance'], 'iterations': iteration, 'max_abs_error': error}
    elif method == 'finite_horizon':
        for step, values in horizon_steps(graph, normalize_weights(graph), parameters['T']):
            record({'step': step, 'by_vertex': values})
        result = {**values[start_id], 'by_vertex': values}
    else:
        transitions = normalize_weights(graph)
        random = Random(parameters['seed'])
        counts = {'P': 0, 'Q': 0, 'U': 0}
        for trial in range(1, parameters['samples'] + 1):
            current = start_id
            for step in range(parameters['max_steps'] + 1):
                role = graph.by_id[current].role
                if role != 'ordinary':
                    counts['P' if role == 'green' else 'Q'] += 1
                    break
                outgoing = transitions[current]
                if step == parameters['max_steps'] or not outgoing:
                    counts['U'] += 1
                    break
                threshold, cumulative = random.random(), 0.0
                current = outgoing[-1][0]
                for target, probability in outgoing:
                    cumulative += probability
                    if threshold < cumulative:
                        current = target
                        break
            if trial % parameters['batch_size'] == 0 or trial == parameters['samples']:
                record({'trials': trial, **{key: count / trial for key, count in counts.items()}})

        for _, finite in horizon_steps(graph, transitions, parameters['max_steps']):
            pass
        result = {key: count / parameters['samples'] for key, count in counts.items()}
        result.update({'trials': parameters['samples'], 'counts': counts,
                       'finite_horizon_P': finite[start_id]['P'],
                       'abs_error': abs(result['P'] - finite[start_id]['P'])})
    return {'method': method, 'start_id': start_id, 'parameters': parameters,
            'graph_revision': graph.revision, 'result': result, 'history': history}


class NumericalSolver:

    def __init__(self, method):
        self.method = method

    def solve(self, graph_snapshot, parameters, emit, cancel):
        return solve(graph_snapshot, self.method, parameters, emit=emit, cancel=cancel)
