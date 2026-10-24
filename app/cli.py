import argparse
import shlex
import sys
from pathlib import Path

from core.errors import GraphError, require
from core.model import is_number
from core.service import GraphService
from methods.contracts import transition_inputs
from storage.json_io import load_document, save_document
from .svg_renderer import save_svg

HELP = """Команды CLI:
  grid 5 | grid 4 3 | grid 3 3 3
    Параметры: --spacing 0.5 --weight 2 --origin 0 0
  (x;y;z)                 добавить отдельную точку через Enter
  point (x;y;z)           то же действие с именем команды
  edge v0 v1 2 [both]     переход с весом 2; both — в обе стороны
  role v0 green           роль ordinary / green / red
  start v1 | start none   назначить / снять старт
  remove v1               удалить вершину и её переходы
  vertex v0 | neighbors v0  свойства / соседи с весами
  show [all] | edges [all]  список вершин / переходов (до 50 без all)
  info                    размерность, размеры и редакция
  rotate 20 15 0          поворот вида 3D вокруг X, Y, Z
  open "graph.json"       открыть JSON вместо текущего графа
  save "graph.json"       сохранить граф и параметры
  export "graph.svg"      дополнительно сохранить изображение
  method                  показать настройки метода
  method monte_carlo samples=10000 seed=42 max_steps=1000
  method relaxation tolerance=0.000001 max_iterations=10000
  run | result            состояние подключения метода / результат
  help | quit             справка / выход
grid и open заменяют модель. Сначала сохраните нужный граф командой save.
SVG автоматически обновляется после успешного изменения. Окна не открываются.
"""


class CommandParser(argparse.ArgumentParser):
    def error(self, message):
        raise GraphError("INVALID_COMMAND", message, "command")


def parse_grid(args):
    parser = CommandParser(prog="grid", add_help=False)
    parser.add_argument("shape", type=int, nargs="+")
    parser.add_argument("--spacing", type=float, default=1)
    parser.add_argument("--weight", type=float, default=1)
    parser.add_argument("--origin", type=float, nargs="+")
    return vars(parser.parse_args(args))


class CLI:
    def __init__(self, service=None, svg_path="graph.svg", output=None):
        self.service = service or GraphService()
        self.svg_path = Path(svg_path)
        self.output = output or sys.stdout
        self.rotation = [0.0, 0.0, 0.0]
        self.selected_id = None
        self.restore_view()

    def print(self, text):
        print(text, file=self.output)

    def restore_view(self):
        rotation = self.service.extra.get("view", {}).get("rotation")
        if isinstance(rotation, list) and len(rotation) == 3 and all(is_number(x) for x in rotation):
            self.rotation = rotation.copy()
        else:
            self.rotation = [0.0, 0.0, 0.0]

    def refresh(self):
        try:
            save_svg(self.svg_path, self.service.graph, self.selected_id, self.rotation)
            self.print(f"Изображение обновлено: {self.svg_path}")
        except (OSError, ValueError) as error:
            self.print(f"SVG_WRITE_FAILED: модель сохранена в памяти, изображение не обновлено: {error}")

    def change(self, kind, payload):
        response = self.service.command(kind, payload)
        if response["selected_id"]:
            self.selected_id = response["selected_id"]
            self.print(f"Добавлена вершина {self.selected_id}")
        if self.selected_id not in self.service.graph.by_id:
            self.selected_id = None
        if kind == "generate":
            self.selected_id = None
            self.rotation = [0.0, 0.0, 0.0]
        self.refresh()

    def configure_method(self, args):
        require(bool(args), "INVALID_METHOD", "Укажите метод.", "method")
        name, *pairs = args
        defaults = {
            "monte_carlo": {"samples": 10000, "seed": 42, "max_steps": 1000},
            "relaxation": {"tolerance": 1e-6, "max_iterations": 10000},
        }
        require(name in defaults, "INVALID_METHOD", "Метод: monte_carlo или relaxation.", "method")
        parameters = defaults[name].copy()
        for pair in pairs:
            key, sep, text = pair.partition("=")
            require(bool(sep) and key in parameters, "INVALID_PARAMETER", "Проверьте имена параметров метода.", "parameters")
            try:
                value = float(text) if key == "tolerance" else int(text)
            except ValueError as error:
                raise GraphError("INVALID_PARAMETER", "Неверный числовой параметр метода.", key) from error
            require(is_number(value) and (key == "seed" or value > 0),
                    "INVALID_PARAMETER", "Параметр должен быть конечным и положительным; seed — целым.", key)
            parameters[key] = value
        self.service.extra["run"] = {"method": name, "parameters": parameters}
        self.print(f"Метод настроен: {name}; {parameters}. Вычислительный модуль ещё не подключён.")

    def execute(self, line):
        """Обработать одну строку; False означает запрос выхода."""
        try:
            line = line.strip()
            if not line:
                return True
            if line.startswith("("):
                self.change("add_vertex", {"point": line})
                return True
            command, *args = shlex.split(line)
            if command == "quit" and not args:
                return False
            if command == "help" and not args:
                self.print(HELP)
            elif command == "grid":
                self.change("generate", parse_grid(args))
            elif command == "point" and args:
                self.change("add_vertex", {"point": " ".join(args)})
            elif command == "edge" and len(args) in (3, 4):
                require(len(args) == 3 or args[3] == "both", "INVALID_COMMAND", "Четвёртый аргумент edge должен быть both.")
                self.change("add_edge", {"source_id": args[0], "target_id": args[1], "weight": float(args[2]), "bidirectional": len(args) == 4})
            elif command == "role" and len(args) == 2:
                self.change("set_role", {"vertex_id": args[0], "role": args[1]})
            elif command == "start" and len(args) == 1:
                self.change("set_start", {"vertex_id": None if args[0] == "none" else args[0]})
            elif command == "remove" and len(args) == 1:
                self.change("remove_vertex", {"vertex_id": args[0]})
            elif command == "neighbors" and len(args) == 1:
                self.print(str(transition_inputs(self.service.graph, args[0])))
            elif command == "vertex" and len(args) == 1:
                require(args[0] in self.service.graph.by_id, "UNKNOWN_VERTEX", "Вершина не найдена.", "vertex_id")
                v = self.service.graph.by_id[args[0]]
                self.print(f"{v.id}: coordinates={v.coordinates}; role={v.role}; start={v.id == self.service.graph.start_id}")
            elif command in ("show", "edges") and (not args or args == ["all"]):
                items = self.service.graph.vertices if command == "show" else self.service.graph.edges
                for item in items if args else items[:50]:
                    self.print(str(item))
                if not args and len(items) > 50:
                    self.print(f"Показано 50 из {len(items)}. Полный список: {command} all")
            elif command == "info" and not args:
                g = self.service.graph
                self.print(f"{g.dimension}D: V={len(g.vertices)}, arcs={len(g.edges)}, revision={g.revision}, start={g.start_id}")
            elif command == "rotate" and len(args) == 3:
                rotation = [float(x) for x in args]
                require(all(is_number(x) for x in rotation), "INVALID_ROTATION", "Нужны три конечных угла.", "rotation")
                self.rotation = rotation
                self.service.extra.setdefault("view", {})["rotation"] = rotation.copy()
                self.refresh()
            elif command == "open" and len(args) == 1:
                graph, extra = load_document(args[0])
                self.service.replace_graph(graph, extra)
                self.restore_view()
                self.selected_id = None
                self.print(f"Граф загружен: {args[0]}")
                self.refresh()
            elif command == "save" and len(args) == 1:
                save_document(args[0], self.service.document())
                self.print(f"Граф сохранён: {args[0]}")
            elif command == "export" and len(args) == 1:
                save_svg(args[0], self.service.graph, self.selected_id, self.rotation)
                self.print(f"SVG сохранён: {args[0]}")
            elif command == "method":
                if args:
                    self.configure_method(args)
                else:
                    self.print(str(self.service.extra.get("run", "Метод не настроен.")))
            elif command == "run" and not args:
                raise GraphError("METHOD_NOT_AVAILABLE", "Вычислительный модуль ещё не подключён. Подготовлены модель и контракт solve().", "method")
            elif command == "result" and not args:
                self.print("Результат отсутствует: вычислительный модуль ещё не подключён.")
            else:
                raise GraphError("INVALID_COMMAND", "Неизвестная команда или неверное число аргументов. Введите help.", "command")
        except GraphError as error:
            self.print(f"{error.code}: {error.message} [{error.path}]")
        except (OSError, ValueError) as error:
            self.print(f"COMMAND_FAILED: {error}")
        return True

    def run(self, input_stream=None, interactive=True):
        stream = input_stream or sys.stdin
        self.print("Ч 1 — консольный редактор графа. Справка: help. Выход: quit.")
        self.refresh()
        while True:
            if interactive:
                self.output.write("graph> ")
                self.output.flush()
            try:
                line = stream.readline()
            except KeyboardInterrupt:
                self.print("\nЗавершено. Для сохранения изменений используйте save перед выходом.")
                break
            if not line or not self.execute(line):
                break
