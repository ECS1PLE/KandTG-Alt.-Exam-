import sys
from core import Graph, GraphService
from core.errors import GraphError
from core.generators import grid
from storage.json_io import load_document, save_document
from methods.solvers import DEFAULTS, validate_parameters
from app.cli import CLI
from app.arguments import RussianArgumentParser


def main():
    parser = RussianArgumentParser(description="Графы и вероятность достижения цели")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--grid", metavar="РАЗМЕР", nargs="+", type=int, help="размеры: 5 / 4 3 / 3 3 3")
    source.add_argument("--load", metavar="ФАЙЛ")
    parser.add_argument("--dimension", metavar="ИЗМЕРЕНИЯ", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--spacing", metavar="ШАГ", type=float, default=1)
    parser.add_argument("--weight", metavar="ВЕС", type=float, default=1)
    parser.add_argument("--origin", metavar="КООРДИНАТА", type=float, nargs="+")
    parser.add_argument("--svg", metavar="ФАЙЛ", default="graph.svg", help="автоматически обновляемый SVG")
    parser.add_argument("--script", metavar="ФАЙЛ", help="UTF-8 файл с командами вместо ввода")
    parser.add_argument("--view3d", action="store_true", help="открыть интерактивное трёхмерное окно")
    parser.add_argument("--method", choices=tuple(DEFAULTS), help="один расчёт вместо интерактивного ввода")
    parser.add_argument("--start", metavar="ВЕРШИНА", help="строковый идентификатор стартовой вершины")
    parser.add_argument("--T", metavar="ШАГИ", type=int, help="число шагов finite_horizon")
    parser.add_argument("--samples", metavar="ИСПЫТАНИЯ", type=int)
    parser.add_argument("--seed", metavar="ЗНАЧЕНИЕ", type=int)
    parser.add_argument("--max-steps", metavar="ШАГИ", type=int)
    parser.add_argument("--batch-size", metavar="ИСПЫТАНИЯ", type=int)
    parser.add_argument("--tolerance", metavar="ТОЧНОСТЬ", type=float)
    parser.add_argument("--max-iterations", metavar="ИТЕРАЦИИ", type=int)
    parser.add_argument("--output", metavar="ФАЙЛ", help="сохранить граф, настройки, историю и результат в JSON")
    args = parser.parse_args()
    try:
        extra = {}
        if args.load:
            graph, extra = load_document(args.load)
        elif args.grid:
            graph = grid(args.grid, args.spacing, args.origin, args.weight)
        else:
            graph = Graph(dimension=args.dimension)
        service = GraphService(graph)
        service.extra = extra
        if args.start is not None:
            service.command('set_start', {'vertex_id': args.start})
        cli = CLI(service, args.svg)
        if args.method:
            if args.view3d or args.script:
                parser.error('--method не совмещается с --script или --view3d; используйте команды method и run в консоли')
            parameters = {key: getattr(args, key) for key in
                          ('T', 'samples', 'seed', 'max_steps', 'batch_size', 'tolerance', 'max_iterations')
                          if getattr(args, key) is not None}
            service.extra['run'] = {'method': args.method, 'parameters': validate_parameters(args.method, parameters)}
            cli.calculate()
            if args.output:
                save_document(args.output, service.document())
            return
        if args.view3d:
            cli.open_3d()
        if args.script:
            with open(args.script, encoding="utf-8") as stream:
                cli.run(stream, interactive=False)
        else:
            cli.run(interactive=sys.stdin.isatty())
        if args.output:
            save_document(args.output, service.document())
    except (GraphError, OSError, ValueError) as error:
        parser.exit(2, f"Ошибка: {error.message if isinstance(error, GraphError) else 'Проверьте аргументы и доступность файла.'}\n")


if __name__ == "__main__":
    main()
