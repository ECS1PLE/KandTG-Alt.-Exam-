"""Точка входа CLI. Достаточно Python 3.10+, установка пакетов не нужна."""
import argparse
import sys
from core import Graph, GraphService
from core.errors import GraphError
from core.generators import grid
from storage.json_io import load_document
from app.cli import CLI


def main():
    parser = argparse.ArgumentParser(description="Ч 1 — консольный редактор графа")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--grid", nargs="+", type=int, help="размеры: 5 / 4 3 / 3 3 3")
    source.add_argument("--load", metavar="JSON")
    parser.add_argument("--dimension", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--spacing", type=float, default=1)
    parser.add_argument("--weight", type=float, default=1)
    parser.add_argument("--origin", type=float, nargs="+")
    parser.add_argument("--svg", default="graph.svg", help="автоматически обновляемый SVG")
    parser.add_argument("--script", help="UTF-8 файл с командами вместо ввода")
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
        cli = CLI(service, args.svg)
        if args.script:
            with open(args.script, encoding="utf-8") as stream:
                cli.run(stream, interactive=False)
        else:
            cli.run(interactive=sys.stdin.isatty())
    except (GraphError, OSError, ValueError) as error:
        parser.exit(2, f"Ошибка: {error}\n")


if __name__ == "__main__":
    main()
