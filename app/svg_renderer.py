"""Отрисовка SVG без сторонних пакетов и графических окон."""
import os
import tempfile
from math import isfinite
from pathlib import Path
import xml.etree.ElementTree as ET

from core.projection import project

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def element(parent, tag, **attributes):
    return ET.SubElement(parent, f"{{{SVG}}}{tag}", {k.replace("_", "-"): str(v) for k, v in attributes.items()})


def screen_points(graph, rotation=(0, 0, 0)):
    scale = max((abs(x) for v in graph.vertices for x in v.coordinates), default=1)
    scale = max(1, scale)
    xyz = {v.id: tuple(x / scale for x in v.coordinates) + (0,) * (3 - graph.dimension) for v in graph.vertices}
    center = tuple((min(p[i] for p in xyz.values()) + max(p[i] for p in xyz.values())) / 2 for i in range(3)) if xyz else (0, 0, 0)
    raw = {}
    for key, point in xyz.items():
        raw[key] = project(point, center, rotation) if graph.dimension == 3 else (point[0] - center[0], -(point[1] - center[1]), 0)
    extent = max((abs(x) for point in raw.values() for x in point[:2]), default=1)
    extent = extent or 1
    return {key: (500 + x / extent * 350, 350 + y / extent * 240, d) for key, (x, y, d) in raw.items()}


def render_svg(graph, selected_id=None, rotation=(0, 0, 0)):
    if len(rotation) != 3 or not all(isfinite(x) for x in rotation):
        raise ValueError("Поворот должен содержать три конечных угла.")
    root = ET.Element(f"{{{SVG}}}svg", {"viewBox": "0 0 1000 700", "width": "1000", "height": "700", "role": "img"})
    element(root, "title").text = "Граф из консольной программы Ч 1"
    element(root, "rect", width=1000, height=700, fill="white")
    element(root, "text", x=30, y=35, fill="black", font_family="sans-serif", font_size=20).text = f"{graph.dimension}D | V={len(graph.vertices)} | arcs={len(graph.edges)} | revision={graph.revision}"
    defs = element(root, "defs")
    marker = element(defs, "marker", id="arrow", viewBox="0 0 10 10", refX=10, refY=5, markerWidth=6, markerHeight=6, orient="auto")
    element(marker, "path", d="M 0 0 L 10 5 L 0 10 z", fill="#777777")
    points = screen_points(graph, rotation)
    weights = {(e.source_id, e.target_id): e.weight for e in graph.edges}
    for edge in graph.edges:
        reverse = weights.get((edge.target_id, edge.source_id)) == edge.weight
        if reverse and edge.source_id > edge.target_id:
            continue
        x, y, _ = points[edge.source_id]
        u, v, _ = points[edge.target_id]
        if not reverse:
            length = ((u - x) ** 2 + (v - y) ** 2) ** .5
            if length:
                u, v = u - (u - x) / length * 10, v - (v - y) / length * 10
        line = element(root, "line", x1=x, y1=y, x2=u, y2=v, stroke="#999999", stroke_width=1.5)
        if not reverse:
            line.set("marker-end", "url(#arrow)")
        element(line, "title").text = f"{edge.source_id} -> {edge.target_id}; weight={edge.weight}"
    colors = {"ordinary": "#eeeeee", "green": "#86efac", "red": "#fca5a5"}
    for vertex in sorted(graph.vertices, key=lambda v: points[v.id][2]):
        x, y, _ = points[vertex.id]
        group = element(root, "g", id=vertex.id)
        element(group, "title").text = f"{vertex.id}: {vertex.coordinates}; role={vertex.role}"
        element(group, "circle", cx=x, cy=y, r=8, fill=colors[vertex.role], stroke="black", stroke_width=3 if vertex.id == selected_id else 1)
        if len(graph.vertices) <= 250 or vertex.id == selected_id:
            suffix = " S" if vertex.id == graph.start_id else ""
            element(group, "text", x=x+12, y=y-10, fill="black", font_family="sans-serif", font_size=12).text = vertex.id + suffix
    if not graph.vertices:
        element(root, "text", x=350, y=350, fill="black", font_family="sans-serif", font_size=18).text = "Граф пуст. Добавьте точки или создайте решётку."
    element(root, "text", x=30, y=675, fill="black", font_family="sans-serif", font_size=13).text = "ordinary — обычная; green — зелёная; red — красная; S — старт"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def save_svg(path, graph, selected_id=None, rotation=(0, 0, 0)):
    data = render_svg(graph, selected_id, rotation)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            temporary = f.name
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
