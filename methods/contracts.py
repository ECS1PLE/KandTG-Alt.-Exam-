from typing import Callable, Protocol
from core.model import Graph


class Solver(Protocol):
    def solve(self, graph_snapshot: Graph, parameters: dict,
              emit: Callable[[dict], None], cancel: Callable[[], bool]) -> dict:
        """Получить снимок; вернуть результат по контракту второй недели."""
        pass


def transition_inputs(graph: Graph, vertex_id: str):
    """Вернуть пары (ID соседа, исходный вес). Нормализация остаётся методу."""
    return tuple((edge.target_id, edge.weight) for edge in graph.neighbors(vertex_id))
