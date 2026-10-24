import json
import os
import tempfile
from pathlib import Path

from core.errors import GraphError, require
from core.model import Edge, Graph, Vertex, MAX_EDGES, MAX_VERTICES

MAX_FILE_BYTES = 20 * 1024 * 1024


def decode_document(document):
    require(isinstance(document, dict), "INVALID_FORMAT", "Корень JSON должен быть объектом.", "$")
    require(type(document.get("schema_version")) is int and document["schema_version"] == 1,
            "UNSUPPORTED_VERSION", "Поддерживается schema_version = 1.", "schema_version")
    try:
        g = document["graph"]
        vertices, edges = g["vertices"], g["edges"]
        require(isinstance(vertices, list) and isinstance(edges, list), "INVALID_FORMAT", "vertices и edges должны быть массивами.")
        require(len(vertices) <= MAX_VERTICES and len(edges) <= MAX_EDGES,
                "GRAPH_TOO_LARGE", "Превышен допустимый размер графа.")
        require(all(isinstance(v.get("coordinates"), list) for v in vertices),
                "INVALID_FORMAT", "coordinates должен быть массивом.", "graph.vertices")
        graph = Graph(g["dimension"], g["revision"],
                      tuple(Vertex(v["id"], tuple(v["coordinates"]), v["role"]) for v in vertices),
                      tuple(Edge(e["source_id"], e["target_id"], e["weight"]) for e in edges), g["start_id"])
    except (KeyError, TypeError, AttributeError) as error:
        raise GraphError("INVALID_FORMAT", "Проверьте обязательные поля и типы JSON.") from error
    extra = {k: document[k] for k in ("run", "view") if k in document}
    for key, value in extra.items():
        require(isinstance(value, dict), "INVALID_FORMAT", f"{key} должен быть объектом.", key)
    try:
        json.dumps(document, allow_nan=False)
    except (ValueError, TypeError) as error:
        raise GraphError("INVALID_FORMAT", "Документ должен содержать только допустимые JSON-значения.") from error
    return graph, extra


def load_document(path):
    p = Path(path)
    require(p.stat().st_size <= MAX_FILE_BYTES, "FILE_TOO_LARGE", "JSON не должен превышать 20 МиБ.", "file")
    try:
        document = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise GraphError("INVALID_JSON", "Файл должен содержать корректный UTF-8 JSON.", "file") from error
    return decode_document(document)


def save_document(path, document):
    decode_document(document)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=p.parent, delete=False) as f:
            temp = f.name
            json.dump(document, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, p)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
