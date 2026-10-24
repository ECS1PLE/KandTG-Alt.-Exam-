from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Mapping

from .errors import require

ROLES = ("ordinary", "green", "red")
MAX_VERTICES = 20_000
MAX_EDGES = 120_000 

def is_number(value):
    try:
        return type(value) in (int, float) and isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class Vertex:
    id: str
    coordinates: tuple[float, ...]
    role: str = "ordinary"


@dataclass(frozen=True)
class Edge:
    source_id: str
    target_id: str
    weight: float = 1.0


@dataclass(frozen=True)
class Graph:
    """Неизменяемый снимок. Индексы строятся за O(V + E)."""
    dimension: int = 2
    revision: int = 0
    vertices: tuple[Vertex, ...] = ()
    edges: tuple[Edge, ...] = ()
    start_id: str | None = None
    by_id: Mapping[str, Vertex] = field(init=False, repr=False, compare=False)
    adjacency: Mapping[str, tuple[Edge, ...]] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        require(type(self.dimension) is int and 1 <= self.dimension <= 3,
                "INVALID_DIMENSION", "Размерность должна быть 1, 2 или 3.", "graph.dimension")
        require(type(self.revision) is int and self.revision >= 0,
                "INVALID_REVISION", "Редакция должна быть целым неотрицательным числом.", "graph.revision")
        vertices = tuple(Vertex(v.id, tuple(v.coordinates), v.role) for v in self.vertices)
        edges = tuple(self.edges)
        require(len(vertices) <= MAX_VERTICES and len(edges) <= MAX_EDGES,
                "GRAPH_TOO_LARGE", "Превышен предел 20 000 вершин или 120 000 переходов.")
        index, positions, adjacency = {}, set(), {}
        for i, v in enumerate(vertices):
            path = f"graph.vertices[{i}]"
            require(type(v.id) is str and bool(v.id.strip()), "INVALID_ID", "ID не должен быть пустым.", path + ".id")
            require(v.id not in index, "DUPLICATE_ID", "ID вершины уже существует.", path + ".id")
            require(len(v.coordinates) == self.dimension and all(is_number(x) for x in v.coordinates),
                    "INVALID_COORDINATES", "Нужны конечные числовые координаты выбранной размерности.", path + ".coordinates")
            require(v.coordinates not in positions, "DUPLICATE_COORDINATES", "Такая точка уже существует.", path + ".coordinates")
            require(v.role in ROLES, "INVALID_ROLE", "Роль должна быть ordinary, green или red.", path + ".role")
            index[v.id] = v
            positions.add(v.coordinates)
            adjacency[v.id] = []
        pairs = set()
        for i, e in enumerate(edges):
            path = f"graph.edges[{i}]"
            require(e.source_id in index and e.target_id in index,
                    "UNKNOWN_VERTEX", "Конец перехода отсутствует в графе.", path)
            require(e.source_id != e.target_id, "SELF_LOOP", "Петли в этой версии модели запрещены.", path)
            require(is_number(e.weight) and e.weight > 0,
                    "INVALID_WEIGHT", "Вес должен быть конечным положительным числом.", path + ".weight")
            pair = e.source_id, e.target_id
            require(pair not in pairs, "DUPLICATE_EDGE", "Такой направленный переход уже существует.", path)
            pairs.add(pair)
            adjacency[e.source_id].append(e)
        require(self.start_id is None or self.start_id in index,
                "INVALID_START", "Стартовая вершина отсутствует в графе.", "graph.start_id")
        object.__setattr__(self, "vertices", vertices)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "by_id", MappingProxyType(index))
        object.__setattr__(self, "adjacency", MappingProxyType({k: tuple(v) for k, v in adjacency.items()}))

    def neighbors(self, vertex_id: str) -> tuple[Edge, ...]:
        require(vertex_id in self.by_id, "UNKNOWN_VERTEX", "Вершина не найдена.", "vertex_id")
        return self.adjacency[vertex_id]

    def to_dict(self):
        return {
            "dimension": self.dimension, "revision": self.revision,
            "vertices": [{"id": v.id, "coordinates": list(v.coordinates), "role": v.role} for v in self.vertices],
            "edges": [{"source_id": e.source_id, "target_id": e.target_id, "weight": e.weight} for e in self.edges],
            "start_id": self.start_id,
        }
