import ast
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from app.cli import CLI
from app.svg_renderer import render_svg
from core import Edge, Graph, GraphService, Vertex
from core.generators import grid


class CLITests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)
        self.output = io.StringIO()
        self.cli = CLI(svg_path=self.path/'graph.svg', output=self.output)

    def test_generate_and_add_immediately(self):
        self.cli.execute('grid 4 3')
        self.assertEqual(len(self.cli.service.graph.vertices), 12)
        before = (self.path/'graph.svg').read_bytes()
        self.cli.execute('(4;1;0)')
        self.assertEqual(self.cli.selected_id, 'v12')
        self.assertEqual(len(self.cli.service.graph.vertices), 13)
        self.assertNotEqual(before, (self.path/'graph.svg').read_bytes())
        svg = ET.parse(self.path/'graph.svg')
        self.assertEqual(len(svg.findall('.//{http://www.w3.org/2000/svg}circle')), 13)

    def test_invalid_point_does_not_change_model_or_image(self):
        self.cli.execute('grid 2 2')
        graph = self.cli.service.graph
        image = (self.path/'graph.svg').read_bytes()
        self.cli.execute('(1;;0)')
        self.assertIs(self.cli.service.graph, graph)
        self.assertEqual(image, (self.path/'graph.svg').read_bytes())
        self.assertIn('INVALID_POINT', self.output.getvalue())

    def test_invalid_grid_command_keeps_cli_alive(self):
        for command in ['grid', 'grid 1 2 --unknown', 'grid text', 'grid 0', '"unterminated']:
            self.assertTrue(self.cli.execute(command))
        self.cli.execute('grid 3 --spacing 0.5 --weight 2 --origin -1')
        self.assertEqual(self.cli.service.graph.by_id['v1'].coordinates, (-.5,))

    def test_roles_start_edges_and_neighbors(self):
        self.cli.execute('(0;0;0)')
        self.cli.execute('(1;0;0)')
        self.cli.execute('edge v0 v1 2 both')
        self.cli.execute('role v1 green')
        self.cli.execute('start v0')
        self.cli.execute('neighbors v0')
        graph = self.cli.service.graph
        self.assertEqual(graph.by_id['v1'].role, 'green')
        self.assertEqual(graph.start_id, 'v0')
        self.assertEqual(len(graph.edges), 2)
        self.assertIn("('v1', 2.0)", self.output.getvalue())

    def test_json_save_open_and_view(self):
        path = (self.path/'file with spaces.json').as_posix()
        self.cli.execute('grid 2 2 2')
        self.cli.execute('rotate 20 15 0')
        self.cli.execute('method monte_carlo samples=120 seed=1')
        self.cli.execute(f'save "{path}"')
        self.cli.execute('grid 4')
        self.cli.execute(f'open "{path}"')
        self.assertEqual(self.cli.service.graph.dimension, 3)
        self.assertEqual(self.cli.rotation, [20, 15, 0])
        self.assertEqual(self.cli.service.extra['run']['parameters']['samples'], 120)
        self.assertEqual(json.loads(Path(path).read_text())['graph']['revision'], 1)

    def test_invalid_load_keeps_current_graph(self):
        self.cli.execute('grid 5')
        before = self.cli.service.graph
        path = self.path/'bad.json'
        path.write_text('{"schema_version":99}', encoding='utf-8')
        self.cli.execute(f'open "{path.as_posix()}"')
        self.assertIs(self.cli.service.graph, before)
        self.assertIn('UNSUPPORTED_VERSION', self.output.getvalue())

    def test_method_parameters_are_atomic_and_no_fake_result(self):
        self.cli.execute('method monte_carlo samples=100')
        old = self.cli.service.extra['run']
        self.cli.execute('method relaxation tolerance=nan')
        self.assertIs(self.cli.service.extra['run'], old)
        self.cli.execute('run')
        self.cli.execute('result')
        self.assertIn('METHOD_NOT_AVAILABLE', self.output.getvalue())
        self.assertIn('Результат отсутствует', self.output.getvalue())

    def test_rotation_keeps_mathematical_model(self):
        self.cli.execute('grid 2 2 2')
        before = self.cli.service.graph
        old_image = (self.path/'graph.svg').read_bytes()
        self.cli.execute('rotate 0 0 15')
        self.assertIs(self.cli.service.graph, before)
        self.assertNotEqual(old_image, (self.path/'graph.svg').read_bytes())

    def test_failed_svg_write_is_reported(self):
        self.cli.execute('grid 2')
        previous = (self.path/'graph.svg').read_bytes()
        with patch('app.svg_renderer.os.replace', side_effect=OSError('write failed')):
            self.cli.execute('(2;0;0)')
        self.assertEqual(len(self.cli.service.graph.vertices), 3)
        self.assertEqual(previous, (self.path/'graph.svg').read_bytes())
        self.assertIn('SVG_WRITE_FAILED', self.output.getvalue())

    def test_svg_escaping_and_large_coordinates(self):
        graph = Graph(dimension=3, vertices=(Vertex('<a&b>', (1e308,1e308,1e308)), Vertex('other', (-1e308,-1e308,-1e308))), edges=(Edge('<a&b>','other'),))
        data = render_svg(graph)
        ET.fromstring(data)
        self.assertIn(b'&lt;a&amp;b&gt;', data)
        self.assertNotIn(b'="nan"', data)
        self.assertNotIn(b'="inf"', data)

    def test_script_without_site_packages(self):
        script = self.path/'commands.txt'
        script.write_text('grid 2 2\n(2;2;0)\n(1;;0)\ninfo\nquit\n', encoding='utf-8')
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-S', str(root/'main.py'), '--script', str(script), '--svg', str(self.path/'batch.svg')], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('V=5, arcs=8, revision=2', result.stdout)
        self.assertIn('INVALID_POINT', result.stdout)
        self.assertTrue((self.path/'batch.svg').is_file())

    def test_only_standard_library_imports(self):
        root = Path(__file__).resolve().parents[1]
        local = {'app','core','storage','methods'}
        for path in root.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                names = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and not node.level else []
                for name in names:
                    if name:
                        self.assertIn(name.split('.')[0], sys.stdlib_module_names | local, f'{path}: {name}')


if __name__ == '__main__':
    unittest.main()
