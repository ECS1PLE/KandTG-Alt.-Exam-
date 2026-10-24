"""Прямоугольные решётки с соседями вдоль осей без диагоналей и замыкания."""
from math import prod

from .errors import require
from .model import Edge, Graph, Vertex, MAX_EDGES, MAX_VERTICES, is_number


def grid(shape, spacing=1.0, origin=None, weight=1.0) -> Graph:
    require(isinstance(shape, (list, tuple)) and 1 <= len(shape) <= 3,
            "INVALID_SHAPE", "Нужны 1, 2 или 3 размера решётки.", "shape")
    shape = tuple(shape)
    require(all(type(n) is int and n >= 1 for n in shape), "INVALID_SHAPE",
            "Размеры решётки должны быть целыми положительными числами.", "shape")
    require(is_number(spacing) and spacing > 0, "INVALID_SPACING",
            "Шаг должен быть конечным положительным числом.", "spacing")
    require(is_number(weight) and weight > 0, "INVALID_WEIGHT",
            "Вес должен быть конечным положительным числом.", "weight")
    d = len(shape)
    origin = (0.0,) * d if origin is None else tuple(origin)
    require(len(origin) == d and all(is_number(x) for x in origin),
            "INVALID_ORIGIN", "Начало должно содержать конечные координаты выбранной размерности.", "origin")
    count = prod(shape)
    links = sum((n - 1) * (count // n) for n in shape)
    require(count <= MAX_VERTICES and 2 * links <= MAX_EDGES, "GRAPH_TOO_LARGE",
            "Превышен предел 20 000 вершин или 120 000 переходов.", "shape")
    strides = [prod(shape[:axis]) for axis in range(d)]
    vertices, edges = [], []
    for index in range(count):
        cell = tuple((index // strides[a]) % shape[a] for a in range(d))
        xyz = tuple(origin[a] + spacing * cell[a] for a in range(d))
        vertices.append(Vertex(f"v{index}", xyz))
        for axis in range(d):
            if cell[axis] + 1 < shape[axis]:
                other = index + strides[axis]
                edges.extend((Edge(f"v{index}", f"v{other}", weight),
                              Edge(f"v{other}", f"v{index}", weight)))
    return Graph(dimension=d, vertices=tuple(vertices), edges=tuple(edges))


def grid_1d(nx, **kwargs):
    return grid((nx,), **kwargs)


def grid_2d(nx, ny, **kwargs):
    return grid((nx, ny), **kwargs)


def grid_3d(nx, ny, nz, **kwargs):
    return grid((nx, ny, nz), **kwargs)
