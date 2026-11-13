import io
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from app.cli import CLI
from app.viewer_3d import Viewer3D
from core import Graph, Vertex, GraphService
from core.errors import GraphError
from core.generators import grid


class ViewerValidationTests(unittest.TestCase):
    def test_requires_real_3d_coordinates(self):
        for graph in (grid((2,2)), Graph(dimension=3, vertices=(Vertex('a'),))):
            with self.assertRaises(GraphError):
                Viewer3D(graph)


@unittest.skipUnless(os.environ.get('DISPLAY'), 'Для Tk нужен графический дисплей')
class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.cli=CLI(GraphService(grid((2,2,2),spacing=2,origin=(10,20,30))),
                     Path(self.folder.name)/'graph.svg',io.StringIO())
        self.cli.open_3d()
        self.viewer=self.cli.viewer
        self.addCleanup(self.viewer.close)

    def test_real_coordinates_colors_edges_zoom_rotate_reset_and_live_point(self):
        from matplotlib.backend_bases import MouseEvent
        viewer=self.viewer
        viewer.pump()
        before=list(zip(*viewer.axes.collections[-1]._offsets3d))
        self.assertEqual(before,[v.coordinates for v in self.cli.service.graph.vertices])

        viewer.canvas.draw()
        x,y=viewer.axes.transAxes.transform((.5,.5))
        angle=(viewer.axes.elev,viewer.axes.azim)
        for name,dx,dy in [('button_press_event',0,0),('motion_notify_event',40,25),('button_release_event',40,25)]:
            event=MouseEvent(name,viewer.canvas,x+dx,y+dy,button=1)
            viewer.canvas.callbacks.process(name,event)
        self.assertNotEqual((viewer.axes.elev,viewer.axes.azim),angle)
        width=viewer.axes.get_xlim3d()[1]-viewer.axes.get_xlim3d()[0]
        viewer.zoom(SimpleNamespace(button='up'))
        self.assertLess(viewer.axes.get_xlim3d()[1]-viewer.axes.get_xlim3d()[0],width)
        self.cli.execute('(15;24;34)')
        self.cli.execute('edge v7 v8 1 both')
        self.cli.execute('role v8 1')
        self.cli.execute('role v0 2')
        viewer.pump()
        positions=list(zip(*viewer.axes.collections[-1]._offsets3d))
        self.assertEqual(positions[-1],(15,24,34))
        self.assertEqual(len(positions),9)
        self.assertEqual(len(viewer.axes.collections[0]._segments3d),13)

        colors=viewer.axes.collections[-1]._facecolors
        self.assertEqual(tuple(colors[0][:3]),(239/255,68/255,68/255))
        self.assertEqual(tuple(colors[-1][:3]),(34/255,197/255,94/255))
        self.cli.execute('reset3d')
        self.assertEqual((viewer.axes.elev,viewer.axes.azim),(25,-60))
        viewer.pump()
        self.assertIsNotNone(viewer.canvas.get_tk_widget().winfo_id())

    def test_cli_pumps_gui_while_waiting_for_stdin(self):
        class InputStream:
            def __iter__(stream):
                import time
                time.sleep(.15)
                yield '(15;24;34)\n'
                time.sleep(.15)
                yield 'quit\n'
        with patch.object(self.viewer,'pump',wraps=self.viewer.pump) as pump:
            self.cli.run(InputStream(),interactive=False)
            self.assertGreater(pump.call_count,2)
        self.assertFalse(self.viewer.alive)
        self.assertEqual(len(self.cli.service.graph.vertices),9)
