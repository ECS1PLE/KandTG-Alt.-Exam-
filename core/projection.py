from math import cos, sin, radians, sqrt


def project(coordinates, center=(0, 0, 0), rotation=(0, 0, 0)):
    """Вращения X, затем Y, затем Z; экранная ось v смотрит вниз."""
    xyz = tuple(coordinates) + (0,) * (3 - len(coordinates))
    x, y, z = (xyz[i] - center[i] for i in range(3))
    a, b, c = map(radians, rotation)
    y, z = y * cos(a) - z * sin(a), y * sin(a) + z * cos(a)
    x, z = x * cos(b) + z * sin(b), -x * sin(b) + z * cos(b)
    x, y = x * cos(c) - y * sin(c), x * sin(c) + y * cos(c)
    return sqrt(3) / 2 * (x - y), (x + y) / 2 - z, (x + y + z) / sqrt(3)


def projected_graph(graph, rotation=(0, 0, 0)):
    if not graph.vertices:
        return {}
    padded = [v.coordinates + (0,) * (3 - graph.dimension) for v in graph.vertices]
    center = tuple((min(p[i] for p in padded) + max(p[i] for p in padded)) / 2 for i in range(3))
    if graph.dimension == 3:
        return {v.id: project(v.coordinates, center, rotation) for v in graph.vertices}
    return {v.id: (p[0] - center[0], -(p[1] - center[1]), 0) for v, p in zip(graph.vertices, padded)}
