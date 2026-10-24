class GraphError(ValueError):
    """Ошибка данных с кодом, сообщением и путём к полю."""

    def __init__(self, code: str, message: str, path: str = "graph"):
        super().__init__(message)
        self.code, self.message, self.path = code, message, path

    def to_dict(self):
        return {"code": self.code, "message": self.message, "path": self.path}


def require(condition, code, message, path="graph"):
    if not condition:
        raise GraphError(code, message, path)
