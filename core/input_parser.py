from .errors import require
from .model import is_number


def parse_point(text: str, dimension: int):
    text = text.strip()
    require(text.startswith("(") and text.endswith(")"), "INVALID_POINT",
            "Введите точку в формате (x;y;z).", "point")
    parts = text[1:-1].split(";")
    require(len(parts) == 3 and all(p.strip() for p in parts), "INVALID_POINT",
            "В скобках нужны три числа через точку с запятой.", "point")
    try:
        numbers = tuple(float(x.strip()) for x in parts)
    except ValueError:
        require(False, "INVALID_POINT", "Координаты должны быть числами с десятичной точкой.", "point")
    require(all(is_number(x) for x in numbers), "INVALID_POINT", "NaN и бесконечность запрещены.", "point")
    require(all(x == 0 for x in numbers[dimension:]), "EXTRA_COORDINATE",
            "Для 1D нужны y=z=0; для 2D нужен z=0.", "point")
    return numbers[:dimension]
