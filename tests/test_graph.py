import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

from core.errors import GraphError
from core.generators import grid, grid_1d, grid_2d, grid_3d
from core.input_parser import parse_point
from core.model import Edge, Graph, Vertex
from core.projection import project
from core.service import GraphService
from methods.contracts import transition_inputs
from storage.json_io import decode_document, load_document, save_document


class GraphTests(unittest.TestCase):
    def test_all_small_rectangular_grids(self):
        for d in (1, 2, 3):
            for shape in itertools.product(range(1, 5), repeat=d):
                with self.subTest(shape=shape):
                    graph = grid(shape)
                    count = math.prod(shape)
                    links = sum((n - 1) * (count // n) for n in shape)
                    self.assertEqual(len(graph.vertices), count)
                    self.assertEqual(len(graph.edges), 2 * links)
                    pairs = {(e.source_id, e.target_id) for e in graph.edges}
                    self.assertEqual(len(pairs), len(graph.edges))
                    for edge in graph.edges:
                        self.assertIn((edge.target_id, edge.source_id), pairs)
                        a, b = graph.by_id[edge.source_id], graph.by_id[edge.target_id]
                        self.assertEqual(sum(abs(x - y) for x, y in zip(a.coordinates, b.coordinates)), 1)

    def test_reference_sizes(self):
        self.assertEqual((len(grid_1d(5).vertices), len(grid_1d(5).edges)), (5, 8))
        self.assertEqual((len(grid_2d(4, 3).vertices), len(grid_2d(4, 3).edges)), (12, 34))
        self.assertEqual((len(grid_3d(3, 3, 3).vertices), len(grid_3d(3, 3, 3).edges)), (27, 108))
        self.assertEqual(len(grid_3d(3, 3, 3).neighbors('v13')), 6)
        self.assertEqual(len(grid_2d(3, 3).neighbors('v4')), 4)

    def test_spacing_origin_weight_and_order(self):
        graph = grid((2, 2), spacing=0.5, origin=(-1, 2), weight=2.5)
        self.assertEqual(graph.by_id['v1'].coordinates, (-0.5, 2))
        self.assertEqual(graph.by_id['v2'].coordinates, (-1, 2.5))
        self.assertTrue(all(e.weight == 2.5 for e in graph.edges))
        self.assertEqual(graph.to_dict(), grid((2, 2), spacing=0.5, origin=(-1, 2), weight=2.5).to_dict())

    def test_invalid_generators(self):
        invalid = [([], {}), ([0], {}), ([-1], {}), ([2.5], {}), ([True], {}),
                   ([1, 1, 1, 1], {}), ([500, 500], {}), ([2], {'spacing': 0}),
                   ([2], {'spacing': float('inf')}), ([2], {'weight': -1}), ([2], {'origin': [0, 0]})]
        for shape, kwargs in invalid:
            with self.subTest(shape=shape, kwargs=kwargs), self.assertRaises(GraphError):
                grid(shape, **kwargs)

    def test_point_contract(self):
        self.assertEqual(parse_point(' (1.5; -2; 0) ', 2), (1.5, -2))
        self.assertEqual(parse_point('(-1;0;0)', 1), (-1,))
        for text in ['1;2;0', '(1;;0)', '(1;2)', '(1;2;0;0)', '(nan;0;0)', '(inf;0;0)', '(1,5;0;0)', '(1;2;3)']:
            with self.subTest(text=text), self.assertRaises(GraphError):
                parse_point(text, 2)

    def test_immutable_snapshot(self):
        graph = grid((3,))
        with self.assertRaises(FrozenInstanceError):
            graph.revision = 5
        with self.assertRaises(TypeError):
            graph.adjacency['v0'] = ()
        service = GraphService(graph)
        service.command('set_role', {'vertex_id': 'v0', 'role': 'green'})
        self.assertEqual(graph.by_id['v0'].role, 'ordinary')
        self.assertEqual(service.graph.by_id['v0'].role, 'green')

    def test_rejected_mutation_is_atomic(self):
        service = GraphService(grid((3,)))
        before = service.graph
        for kind, payload in [('add_vertex', {'point': '(0;0;0)'}),
                              ('add_edge', {'source_id': 'v0', 'target_id': 'missing'}),
                              ('generate', {'shape': [0]}), ('set_start', {'vertex_id': 'missing'}),
                              ('set_role', {'vertex_id': 'v0', 'role': 'blue'})]:
            with self.subTest(kind=kind), self.assertRaises(GraphError):
                service.command(kind, payload)
            self.assertIs(service.graph, before)

    def test_revision_conflict(self):
        service = GraphService(grid((3,)))
        service.command('set_start', {'vertex_id': 'v1'}, expected_revision=0)
        with self.assertRaisesRegex(GraphError, 'Граф изменился'):
            service.command('remove_vertex', {'vertex_id': 'v1'}, expected_revision=0)
        self.assertEqual(service.graph.revision, 1)
        self.assertEqual(len(service.graph.vertices), 3)

    def test_add_remove_and_stable_id(self):
        service = GraphService(grid((3,)))
        service.command('set_start', {'vertex_id': 'v1'})
        service.command('remove_vertex', {'vertex_id': 'v1'})
        self.assertIsNone(service.graph.start_id)
        self.assertEqual(len(service.graph.edges), 0)
        self.assertEqual(service.graph.by_id['v2'].coordinates, (2,))
        result = service.command('add_vertex', {'point': '(4;0;0)'})
        self.assertEqual(result['selected_id'], 'v1')
        self.assertEqual(len(service.graph.edges), 0)

    def test_weighted_transition_contract(self):
        graph = Graph(dimension=1, vertices=(Vertex('a', (0,)), Vertex('b', (1,)), Vertex('c', (2,))),
                      edges=(Edge('a', 'b', 2), Edge('a', 'c', 5)))
        self.assertEqual(transition_inputs(graph, 'a'), (('b', 2), ('c', 5)))
        self.assertEqual(transition_inputs(graph, 'c'), ())

    def test_bad_edges(self):
        graph = grid((2,))
        for edge in [Edge('v0', 'v0'), Edge('v0', 'missing'), Edge('v0', 'v1', 0), Edge('v0', 'v1', float('nan')), Edge('v0', 'v1', True)]:
            with self.subTest(edge=edge), self.assertRaises(GraphError):
                replace(graph, edges=(edge,))
        with self.assertRaises(GraphError):
            replace(graph, edges=graph.edges + (graph.edges[0],))

    def test_json_roundtrip_with_metadata(self):
        document = {'schema_version': 1, 'graph': grid((2, 2)).to_dict(), 'view': {'rotation': [0, 0, 30]}, 'run': {'method': 'monte_carlo'}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'graph.json'
            save_document(path, document)
            graph, extra = load_document(path)
            self.assertEqual(graph.to_dict(), document['graph'])
            self.assertEqual(extra['view'], document['view'])

    def test_bad_file_keeps_service(self):
        service = GraphService(grid((3,)))
        before = service.graph
        document = service.document()
        document['graph']['edges'][0]['target_id'] = 'missing'
        with self.assertRaises(GraphError):
            graph, extra = decode_document(document)
            service.replace_graph(graph, extra)
        self.assertIs(service.graph, before)
        for bad in [{'schema_version': 2}, {'schema_version': True}, {'schema_version': 1, 'graph': {}}]:
            with self.subTest(bad=bad), self.assertRaises(GraphError):
                decode_document(bad)

    def test_failed_save_preserves_file(self):
        document = GraphService(grid((3,))).document()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'graph.json'
            save_document(path, document)
            old = path.read_bytes()
            with patch('storage.json_io.os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    save_document(path, GraphService(grid((4,))).document())
            self.assertEqual(path.read_bytes(), old)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_projection(self):
        u, v, d = project((1, 0, 0))
        self.assertAlmostEqual(u, math.sqrt(3) / 2)
        self.assertAlmostEqual(v, .5)
        self.assertAlmostEqual(d, 1 / math.sqrt(3))
        self.assertEqual(project((0, 0, 0))[:2], project((1, 1, 1))[:2])
        self.assertNotEqual(project((0, 0, 0), rotation=(0, 0, 15))[:2], project((1, 1, 1), rotation=(0, 0, 15))[:2])


if __name__ == '__main__':
    unittest.main()
