from dataclasses import dataclass
from math import fsum

from core.model import Graph
from .contracts import transition_inputs


def normalize_weights(graph: Graph):

    transitions = {}
    for vertex in graph.vertices:
        outgoing = transition_inputs(graph, vertex.id) if vertex.role == 'ordinary' else ()
        scale = max((weight for _, weight in outgoing), default=1)
        total = fsum(weight / scale for _, weight in outgoing)
        transitions[vertex.id] = tuple((target, (weight / scale) / total) for target, weight in outgoing)
    return transitions


@dataclass
class ProbabilitySystem:
    unknowns: tuple[str, ...]
    rows: list[dict[int, float]]
    rhs: list[float]
    boundary: dict[str, float]
    transitions: dict[str, tuple]


def build_system(graph: Graph) -> ProbabilitySystem:
    transitions = normalize_weights(graph)
    reverse = {v.id: [] for v in graph.vertices}
    for source, outgoing in transitions.items():
        for target, probability in outgoing:
            if probability > 0:
                reverse[target].append(source)
    reachable = {v.id for v in graph.vertices if v.role == 'green'}
    stack = list(reachable)
    while stack:
        for source in reverse[stack.pop()]:
            if source not in reachable:
                reachable.add(source)
                stack.append(source)


    boundary = {v.id: float(v.role == 'green') for v in graph.vertices
                if v.role != 'ordinary' or v.id not in reachable}
    unknowns = tuple(v.id for v in graph.vertices if v.id not in boundary)
    index = {key: i for i, key in enumerate(unknowns)}
    rows, rhs = [], []
    for key in unknowns:
        row = {index[key]: 1.0}
        rhs.append(fsum(p * boundary.get(target, 0) for target, p in transitions[key]))
        for target, probability in transitions[key]:
            if target in index:
                j = index[target]
                row[j] = row.get(j, 0) - probability
        rows.append(row)
    return ProbabilitySystem(unknowns, rows, rhs, boundary, transitions)
