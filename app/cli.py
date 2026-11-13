import json
import queue
import shlex
import sys
from threading import Thread
from pathlib import Path

from core.errors import GraphError, require
from core.model import is_number
from core.service import GraphService
from methods.contracts import transition_inputs
from methods.solvers import solve, validate_parameters
from storage.json_io import load_document, save_document
from .arguments import RussianArgumentParser, translate_error
from .svg_renderer import save_svg
from .presentation import METHOD_NAMES, describe_vertex, display_data

HELP = """Команды консоли:
  grid 5 | grid 4 3 | grid 3 3 3
    Параметры: --spacing 0.5 --weight 2 --origin 0 0
  (x;y;z)                 добавить отдельную точку клавишей ввода
  point (x;y;z)           то же действие с именем команды
  edge v0 v1 2 [both]     переход с весом 2; both — в обе стороны
  role v0 1               роль: 0 — обычная, 1 — зелёная, 2 — красная
  start v1 | start none   назначить / снять старт
  remove v1               удалить вершину и её переходы
  vertex v0 | neighbors v0  свойства / соседи с весами
  show [all] | edges [all]  список вершин / переходов (до 50 без all)
  info                    размерность, размеры и редакция
  rotate 20 15 0          поворот трёхмерного вида вокруг осей
  view3d | reset3d        трёхмерное окно / сброс ракурса
  open "graph.json"       открыть JSON вместо текущего графа
  save "graph.json"       сохранить граф и параметры
  export "graph.svg"      дополнительно сохранить изображение
  method                  показать настройки метода
  method monte_carlo samples=10000 seed=42 max_steps=1000
  method relaxation tolerance=0.000001 max_iterations=10000
  method exact
  method finite_horizon T=10
  run | result            запустить расчёт / показать результат
  history [номер]         история метода или одна итерация/шаг
  help | quit             справка / выход
grid и open заменяют модель. Сначала сохраните нужный граф командой save.
Изображение автоматически обновляется после успешного изменения. Трёхмерное окно: view3d.
"""


class CommandParser(RussianArgumentParser):
    def error(self, message):
        raise GraphError("INVALID_COMMAND", translate_error(message), "command")


def parse_grid(args):
    parser = CommandParser(prog="grid", add_help=False)
    parser.add_argument("shape", metavar="РАЗМЕР", type=int, nargs="+")
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
        self.viewer = None
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
        if self.viewer and self.viewer.alive:
            graph = self.service.graph
            if graph.dimension == 3 and all(v.coordinates is not None for v in graph.vertices):
                self.viewer.update_graph(graph)
            else:
                self.viewer.close()
                self.print("Трёхмерное окно закрыто: у текущего графа нет трёхмерных координат.")
        try:
            save_svg(self.svg_path, self.service.graph, self.selected_id, self.rotation)
            self.print(f"Изображение обновлено: {self.svg_path}")
        except (OSError, ValueError) as error:
            self.print("Ошибка записи изображения: модель сохранена в памяти, изображение не обновлено.")

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
        parameters = validate_parameters(name)
        for pair in pairs:
            key, sep, text = pair.partition("=")
            require(bool(sep) and key in parameters, "INVALID_PARAMETER", "Проверьте имена параметров метода.", "parameters")
            try:
                value = float(text) if key == "tolerance" else int(text)
            except ValueError as error:
                raise GraphError("INVALID_PARAMETER", "Неверный числовой параметр метода.", key) from error
            parameters[key] = value
        parameters = validate_parameters(name, parameters)
        self.service.extra["run"] = {"method": name, "parameters": parameters}
        self.print(f"Метод настроен: {METHOD_NAMES[name]}.")
        self.print(display_data(parameters))

    def open_3d(self):
        from .viewer_3d import Viewer3D
        if not self.viewer or not self.viewer.alive:
            self.viewer = Viewer3D(self.service.graph)
        self.viewer.pump()
        self.print("Трёхмерное окно открыто. Продолжайте вводить команды и точки в консоли.")

    def print_history_item(self, item):
        if 'iteration' in item:
            self.print(f"Итерация {item['iteration']}: {json.dumps(item['probabilities'], ensure_ascii=False)}; максимальное абсолютное отклонение от эталона={item['max_abs_error']:.10g}")
        else:
            self.print(display_data(item))

    def calculate(self):
        settings = self.service.extra.get('run', {'method': 'exact', 'parameters': {}})
        method = settings.get('method', 'exact')
        run = solve(self.service.graph, method, settings.get('parameters'),
                    emit=self.print_history_item if method == 'relaxation' else None)
        self.service.extra['run'] = run
        self.print(display_data(run['result']))
        self.print(f"Старт {run['start_id']}: вероятность зелёной цели={run['result']['P']:.10g}")
        return run

    def execute(self, line):

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
                role = int(args[1]) if args[1].lstrip('-').isdigit() else args[1]
                self.change("set_role", {"vertex_id": args[0], "role": role})
            elif command == "start" and len(args) == 1:
                self.change("set_start", {"vertex_id": None if args[0] == "none" else args[0]})
            elif command == "remove" and len(args) == 1:
                self.change("remove_vertex", {"vertex_id": args[0]})
            elif command == "neighbors" and len(args) == 1:
                neighbors = transition_inputs(self.service.graph, args[0])
                self.print(str(neighbors) if neighbors else 'Исходящих переходов нет.')
            elif command == "vertex" and len(args) == 1:
                require(args[0] in self.service.graph.by_id, "UNKNOWN_VERTEX", "Вершина не найдена.", "vertex_id")
                v = self.service.graph.by_id[args[0]]
                self.print(describe_vertex(v, self.service.graph.start_id))
            elif command in ("show", "edges") and (not args or args == ["all"]):
                items = self.service.graph.vertices if command == "show" else self.service.graph.edges
                for item in items if args else items[:50]:
                    self.print(describe_vertex(item, self.service.graph.start_id) if command == 'show'
                               else f'{item.source_id} → {item.target_id}; вес={item.weight}')
                if not args and len(items) > 50:
                    self.print(f"Показано 50 из {len(items)}. Полный список: {command} all")
            elif command == "info" and not args:
                g = self.service.graph
                self.print(f"Размерность: {g.dimension}; вершин={len(g.vertices)}, переходов={len(g.edges)}, редакция={g.revision}, старт={g.start_id if g.start_id is not None else 'не задан'}")
            elif command == "rotate" and len(args) == 3:
                rotation = [float(x) for x in args]
                require(all(is_number(x) for x in rotation), "INVALID_ROTATION", "Нужны три конечных угла.", "rotation")
                self.rotation = rotation
                self.service.extra.setdefault("view", {})["rotation"] = rotation.copy()
                self.refresh()
            elif command == "view3d" and not args:
                self.open_3d()
            elif command == "reset3d" and not args:
                require(self.viewer is not None and self.viewer.alive, 'VIEWER_CLOSED', 'Сначала выполните view3d.')
                self.viewer.reset()
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
                self.print(f"Изображение сохранено: {args[0]}")
            elif command == "method":
                if args:
                    self.configure_method(args)
                else:
                    self.print(display_data(self.service.extra['run']) if 'run' in self.service.extra else 'Метод не настроен.')
            elif command == "run" and not args:
                self.calculate()
            elif command == "result" and not args:
                result = self.service.extra.get('run', {}).get('result')
                self.print(display_data(result) if result is not None else 'Результат отсутствует. Выполните run.')
            elif command == "history" and len(args) <= 1:
                history = self.service.extra.get('run', {}).get('history', [])
                if args:
                    index = int(args[0])
                    require(0 <= index < len(history), 'INVALID_STEP', 'Такого шага нет в истории.')
                    history = [history[index]]
                for item in history:
                    self.print_history_item(item)
            else:
                raise GraphError("INVALID_COMMAND", "Неизвестная команда или неверное число аргументов. Введите help.", "command")
        except GraphError as error:
            self.print(f"Ошибка: {error.message}")
        except (OSError, ValueError) as error:
            self.print('Ошибка выполнения команды. Проверьте аргументы и доступность файла.')
        return True

    def run(self, input_stream=None, interactive=True):
        stream = input_stream or sys.stdin
        self.print("Графы и вероятности. Справка: help. Выход: quit.")
        self.refresh()
        lines = queue.Queue()

        def read_lines():
            for line in stream:
                lines.put(line)
            lines.put(None)


        Thread(target=read_lines, daemon=True).start()
        prompt = True
        try:
            while True:
                if interactive and prompt:
                    self.output.write("граф> ")
                    self.output.flush()
                    prompt = False
                if self.viewer:
                    self.viewer.pump()
                try:
                    line = lines.get(timeout=.03)
                except queue.Empty:
                    continue
                if line is None or not self.execute(line):
                    break
                prompt = True
        except KeyboardInterrupt:
            self.print("\nЗавершено. Для сохранения изменений используйте save перед выходом.")
        finally:
            if self.viewer:
                self.viewer.close()
