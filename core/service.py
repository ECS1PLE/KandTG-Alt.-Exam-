from copy import deepcopy
from dataclasses import replace
from threading import RLock

from .errors import require
from .generators import grid
from .input_parser import parse_point
from .model import Edge, Graph, Vertex


class GraphService:
    """Единая точка изменения. Новый снимок публикуется только после проверки."""

    def __init__(self, graph=None):
        self.graph = graph or Graph()
        self.extra = {}
        self.lock = RLock()

    def document(self):
        with self.lock:
            return {"schema_version": 1, "graph": self.graph.to_dict(), **deepcopy(self.extra)}

    def replace_graph(self, graph, extra=None):
        with self.lock:
            candidate = replace(graph, revision=self.graph.revision + 1)
            self.graph = candidate
            self.extra = deepcopy(extra or {})
            return candidate

    def command(self, kind, payload, expected_revision=None):
        with self.lock:
            g = self.graph
            require(expected_revision is None or (type(expected_revision) is int and expected_revision == g.revision),
                    "REVISION_CONFLICT", "Граф изменился. Обновите снимок и повторите команду.", "expected_revision")
            require(isinstance(payload, dict), "INVALID_COMMAND", "payload должен быть объектом.", "payload")
            extra = self.extra
            selected_id = None
            try:
                if kind == "generate":
                    candidate = grid(payload["shape"], payload.get("spacing", 1), payload.get("origin"), payload.get("weight", 1))
                    extra = {} 
                elif kind == "add_vertex":
                    coords = parse_point(payload["point"], g.dimension) if "point" in payload else tuple(payload["coordinates"])
                    existing = g.by_id
                    n = 0
                    while f"v{n}" in existing:
                        n += 1
                    selected_id = f"v{n}"
                    candidate = replace(g, vertices=g.vertices + (Vertex(selected_id, coords, payload.get("role", "ordinary")),))
                elif kind == "set_role":
                    vertex_id = payload["vertex_id"]
                    require(vertex_id in g.by_id, "UNKNOWN_VERTEX", "Вершина не найдена.", "payload.vertex_id")
                    candidate = replace(g, vertices=tuple(replace(v, role=payload["role"]) if v.id == vertex_id else v for v in g.vertices))
                elif kind == "set_start":
                    candidate = replace(g, start_id=payload["vertex_id"])
                elif kind == "add_edge":
                    source, target, weight = payload["source_id"], payload["target_id"], payload.get("weight", 1)
                    require(type(payload.get("bidirectional", False)) is bool, "INVALID_COMMAND", "bidirectional должен быть bool.")
                    new = (Edge(source, target, weight),)
                    if payload.get("bidirectional", False):
                        new += (Edge(target, source, weight),)
                    candidate = replace(g, edges=g.edges + new)
                elif kind == "remove_vertex":
                    vertex_id = payload["vertex_id"]
                    require(vertex_id in g.by_id, "UNKNOWN_VERTEX", "Вершина не найдена.", "payload.vertex_id")
                    candidate = replace(g, vertices=tuple(v for v in g.vertices if v.id != vertex_id),
                                        edges=tuple(e for e in g.edges if vertex_id not in (e.source_id, e.target_id)),
                                        start_id=None if g.start_id == vertex_id else g.start_id)
                else:
                    require(False, "UNKNOWN_COMMAND", "Неизвестная команда.", "kind")
            except (KeyError, TypeError, AttributeError, OverflowError) as error:
                from .errors import GraphError
                raise GraphError("INVALID_COMMAND", "Проверьте обязательные поля и их типы.", "payload") from error
            self.graph = replace(candidate, revision=g.revision + 1)
            self.extra = extra
            return {"document": self.document(), "selected_id": selected_id}
