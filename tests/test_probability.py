import io
import json
import math
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from app.cli import CLI
from core import Edge, Graph, GraphService, Vertex
from core.errors import GraphError
from core.generators import grid
from methods.probability import normalize_weights, build_system
from methods.solvers import solve
from storage.json_io import decode_document, load_document, save_document

ROOT = Path(__file__).resolve().parents[1]


def example(name):
    return load_document(ROOT / 'examples' / name)[0]


class FormatTests(unittest.TestCase):
    def test_coordinate_free_examples_roundtrip_calculate(self):
        names = ['example3_grid.json', 'example3_small.json', 'example4_weighted.json', 'example5_unreachable.json']
        with tempfile.TemporaryDirectory() as folder:
            for name in names:
                with self.subTest(name=name):
                    graph = example(name)
                    self.assertTrue(all(v.coordinates is None and type(v.id) is str for v in graph.vertices))
                    service = GraphService(graph)
                    service.extra['run'] = solve(graph)
                    path = Path(folder) / name
                    save_document(path, service.document())
                    data = json.loads(path.read_text())
                    self.assertTrue(all('coordinates' not in v for v in data['graph']['vertices']))
                    self.assertEqual(load_document(path)[0], graph)
                    self.assertEqual(load_document(path)[1]['run'], service.extra['run'])

    def test_legacy_roles_canonical_save(self):
        document = {'schema_version': 1, 'graph': {'vertices': [
            {'id': '0', 'role': 'ordinary'}, {'id': 'green', 'role': 'green'}, {'id': 'red', 'role': 'red'}],
            'edges': [], 'start_id': '0'}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'graph.json'
            save_document(path, document)
            vertices = json.loads(path.read_text())['graph']['vertices']
            self.assertEqual([v['role'] for v in vertices], [0, 1, 2])
            self.assertEqual(vertices[0]['id'], '0')
        for role in (-1, 3, True, 1.0, '1', 'blue', None, [], {}):
            with self.subTest(role=role), self.assertRaises(GraphError):
                Graph(vertices=(Vertex('x', role=role),))
        with self.assertRaises(GraphError):
            Graph(vertices=(Vertex(1),))

    def test_lattice_coordinates_required_and_dimension_checked(self):
        for shape in ((3,), (2, 3), (2, 2, 3)):
            graph = grid(shape)
            self.assertEqual(graph.kind, 'lattice')
            for coords in (None, (), (0,) * (len(shape) + 1), ('bad',) * len(shape)):
                with self.subTest(shape=shape, coords=coords), self.assertRaises(GraphError):
                    replace(graph, vertices=(Vertex('v0', coords),))
        self.assertEqual(Graph(vertices=(Vertex('a'), Vertex('b'))).by_id['a'].coordinates, None)
        with self.assertRaises(GraphError):
            Graph(dimension=3, vertices=(Vertex('x', (0, 1)),))

    def test_every_repository_example_loads(self):
        for path in (ROOT / 'examples').glob('*.json'):
            with self.subTest(path=path):
                graph, _ = load_document(path)
                self.assertTrue(all(type(v.id) is str for v in graph.vertices))
                data = json.loads(path.read_text())
                self.assertTrue(all(type(v['role']) is int for v in data['graph']['vertices']))


class ProbabilityTests(unittest.TestCase):
    def test_exact_hand_answers(self):
        expected = {'example3_small.json': {'s': 1/3, 'a': 2/3, 'green': 1, 'red': 0},
                    'example4_weighted.json': {'start': .2, 'green': 1, 'red': 0, 'dead': 0},
                    'example5_unreachable.json': {'s': 0, 'loop-a': 0, 'loop-b': 0, 'red': 0, 'green': 1, 'dead': 0}}
        for name, answers in expected.items():
            result = solve(example(name))['result']
            for key, answer in answers.items():
                with self.subTest(name=name, key=key):
                    self.assertAlmostEqual(result['probabilities'][key], answer)
        self.assertAlmostEqual(solve(example('weighted.json'))['result']['P'], 2/7)
        line = solve(example('example1_line5.json'))['result']['probabilities']
        for i in range(5):
            self.assertAlmostEqual(line[str(i)], i/4)

    def test_absorbing_red_barrier_and_closed_components(self):
        graph = example('example5_unreachable.json')
        system = build_system(graph)
        self.assertEqual(system.unknowns, ())
        self.assertEqual(system.transitions['red'], ())
        graph = Graph(vertices=(Vertex('s'), Vertex('g', role=1), Vertex('a'), Vertex('b')),
                      edges=(Edge('s','g'), Edge('s','a'), Edge('a','b'), Edge('b','a')), start_id='s')
        result = solve(graph)['result']
        self.assertAlmostEqual(result['P'], .5)
        self.assertEqual(result['probabilities']['a'], 0)

    def test_weight_normalization_handles_overflow(self):
        graph = Graph(vertices=(Vertex('s'), Vertex('g', role=1), Vertex('r', role=2)),
                      edges=(Edge('s','g',1e308), Edge('s','r',1e308)), start_id='s')
        self.assertEqual(normalize_weights(graph)['s'], (('g', .5), ('r', .5)))
        self.assertEqual(solve(graph)['result']['P'], .5)

    def test_validation(self):
        with self.assertRaises(GraphError):
            solve(Graph())
        graph = example('example3_small.json')
        for method, params in [('unknown', {}), ('exact', {'T':1}), ('finite_horizon', {'T':-1}),
                               ('finite_horizon', {'T':True}), ('monte_carlo', {'samples':0}),
                               ('monte_carlo', {'seed':1.0}), ('relaxation', {'tolerance':float('nan')})]:
            with self.subTest(method=method, params=params), self.assertRaises(GraphError):
                solve(graph, method, params)
        with self.assertRaises(GraphError):
            solve(graph, start_id='missing')
        for weight in (0, -1, True, math.inf, math.nan):
            with self.assertRaises(GraphError):
                replace(graph, edges=(Edge('s','a',weight),))

    def test_sequential_relaxation_and_history(self):
        run = solve(example('example3_small.json'), 'relaxation', {'tolerance':1e-10})
        self.assertTrue(run['result']['converged'])
        self.assertAlmostEqual(run['result']['P'], 1/3, places=9)
        self.assertEqual(run['history'][1]['probabilities']['a'], .5)
        self.assertEqual(run['history'][2]['probabilities']['a'], .625)
        reference = run['result']['reference']
        for i, item in enumerate(run['history']):
            self.assertEqual(item['iteration'], i)
            self.assertEqual(item['max_abs_error'], max(abs(item['probabilities'][key] - value) for key,value in reference.items()))
        run = solve(example('example3_small.json'), 'relaxation', {'max_iterations':1})
        self.assertFalse(run['result']['converged'])

    def test_finite_horizon_hand_paths_and_zero(self):
        graph = example('example3_small.json')
        for horizon, expected in [(0,(0,0,1)), (1,(0,.5,.5)), (2,(.25,.5,.25)), (3,(.25,.625,.125))]:
            run = solve(graph, 'finite_horizon', {'T':horizon})
            self.assertEqual(len(run['history']), horizon+1)
            self.assertEqual(tuple(run['result'][k] for k in ('P','Q','U')), expected)
            for item in run['history']:
                for values in item['by_vertex'].values():
                    self.assertAlmostEqual(sum(values.values()), 1)
                    self.assertTrue(all(0 <= v <= 1 for v in values.values()))
        for start, expected in [('green',(1,0,0)),('red',(0,1,0))]:
            for horizon in (0,2):
                result = solve(graph, 'finite_horizon', {'T':horizon}, start)['result']
                self.assertEqual(tuple(result[k] for k in ('P','Q','U')), expected)
        dead = solve(example('example4_weighted.json'), 'finite_horizon', {'T':20}, 'dead')['result']
        self.assertEqual((dead['P'],dead['Q'],dead['U']), (0,0,1))

    def test_monte_carlo_all_trials_seed_and_horizon(self):
        graph = example('example3_small.json')
        params = {'samples':40000,'seed':123,'max_steps':2,'batch_size':5000}
        run = solve(graph, 'monte_carlo', params)
        self.assertEqual(run, solve(graph, 'monte_carlo', params))
        result = run['result']
        self.assertLess(abs(result['P'] - .25), .01)
        self.assertEqual(result['finite_horizon_P'], .25)
        self.assertEqual(sum(result['counts'].values()), params['samples'])
        for key in ('P','Q','U'):
            self.assertEqual(result[key], result['counts'][key]/params['samples'])
        self.assertEqual([h['trials'] for h in run['history']], list(range(5000,40001,5000)))
        for item in run['history']:
            self.assertAlmostEqual(item['P']+item['Q']+item['U'],1)
        zero = solve(graph,'monte_carlo',{'samples':3,'max_steps':0})['result']
        self.assertEqual((zero['P'],zero['Q'],zero['U']), (0,0,1))
        for start, key in [('green','P'),('red','Q')]:
            self.assertEqual(solve(graph,'monte_carlo',{'samples':3,'max_steps':0},start)['result'][key],1)
        dead = solve(example('example4_weighted.json'), 'monte_carlo', {'samples':10000,'max_steps':1})['result']
        self.assertLess(abs(dead['P']-.2),.02)
        self.assertGreater(dead['U'],.25)

    def test_cli_history_result_saved_and_invalidated_after_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            cli = CLI(GraphService(example('example3_small.json')), Path(folder)/'graph.svg', io.StringIO())
            for command in ('method relaxation tolerance=0.0001', 'run', 'history 1', f'save "{folder}/run.json"'):
                cli.execute(command)
            graph, extra = load_document(Path(folder)/'run.json')
            self.assertTrue(extra['run']['result']['converged'])
            self.assertIn('Итерация 1', cli.output.getvalue())
            self.assertIn('максимальное абсолютное отклонение от эталона=',cli.output.getvalue())
            cli.execute('role a 1')
            self.assertNotIn('result', cli.service.extra['run'])
            self.assertEqual(cli.service.extra['run']['method'], 'relaxation')
            self.assertTrue(all(v.coordinates is None for v in graph.vertices))

    def test_batch_cli_all_four_methods(self):
        with tempfile.TemporaryDirectory() as folder:
            for method in ('exact','relaxation','finite_horizon','monte_carlo'):
                path = Path(folder)/f'{method}.json'
                args = [sys.executable, 'main.py','--load','examples/example3_small.json','--method',method,'--output',str(path)]
                if method == 'finite_horizon': args += ['--T','2']
                if method == 'monte_carlo': args += ['--samples','100','--max-steps','2']
                process = subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=20)
                self.assertEqual(process.returncode,0,process.stderr)
                run = json.loads(path.read_text())['run']
                self.assertEqual(run['method'],method)
                self.assertEqual(run['start_id'],'s')
                self.assertIn('P',run['result'])
