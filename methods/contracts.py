from typing import Callable, Protocol
from core.model import Graph


class Solver(Protocol):
    def solve(self, graph_snapshot: Graph, parameters: dict,
              emit: Callable[[dict], None], cancel: Callable[[], bool]) -> dict:

        pass


def transition_inputs(graph: Graph, vertex_id: str):

    return tuple((edge.target_id, edge.weight) for edge in graph.neighbors(vertex_id))
