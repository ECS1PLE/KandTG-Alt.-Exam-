from core.errors import GraphError, require

COLORS = {'ordinary': '#64748b', 'green': '#22c55e', 'red': '#ef4444'}


def validate_3d(graph):
    require(graph.dimension == 3 and all(v.coordinates is not None for v in graph.vertices),
            'INVALID_3D_GRAPH', 'Для трёхмерного просмотра нужны координаты всех вершин.')


class Viewer3D:
    def __init__(self, graph):
        validate_3d(graph)
        try:
            import tkinter as tk
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except ImportError as error:
            raise GraphError('DEPENDENCY_MISSING', 'Для трёхмерного окна установите графические зависимости проекта.') from error
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            raise GraphError('DISPLAY_UNAVAILABLE', 'Не удалось открыть графическое окно. Проверьте доступность дисплея.') from error
        self.alive = True
        self.root.title('Трёхмерная решётка — граф вероятностей')
        self.root.geometry('960x760')
        self.figure = Figure(figsize=(9, 7), dpi=100)
        self.axes = self.figure.add_subplot(111, projection='3d')
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        controls = tk.Frame(self.root)
        controls.pack()
        tk.Button(controls, text='Приблизить', command=lambda: self.scale(.85)).pack(side=tk.LEFT)
        tk.Button(controls, text='Отдалить', command=lambda: self.scale(1 / .85)).pack(side=tk.LEFT)
        tk.Button(controls, text='Сбросить ракурс', command=self.reset).pack(side=tk.LEFT)
        tk.Label(self.root, text='ЛКМ — вращение · колесо — масштаб · ПКМ — масштаб · команды и точки вводятся в консоли').pack()
        self.canvas.mpl_connect('scroll_event', self.zoom)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.update_graph(graph)
        self.reset()

    def update_graph(self, graph):
        validate_3d(graph)
        self.graph = graph
        angles = (self.axes.elev, self.axes.azim)
        self.axes.clear()
        from mpl_toolkits.mplot3d.art3d import Line3DCollection
        segments, seen = [], set()
        for edge in graph.edges:
            key = frozenset((edge.source_id, edge.target_id))
            if key not in seen:
                segments.append((graph.by_id[edge.source_id].coordinates, graph.by_id[edge.target_id].coordinates))
                seen.add(key)
        if segments:
            self.axes.add_collection3d(Line3DCollection(segments, colors='#94a3b8', linewidths=1))
        vertices = graph.vertices
        if vertices:
            self.axes.scatter(*zip(*(v.coordinates for v in vertices)),
                              c=[COLORS[v.role] for v in vertices],
                              s=[85 if v.id == graph.start_id else 35 for v in vertices], depthshade=False)
            if len(vertices) <= 150:
                for vertex in vertices:
                    self.axes.text(*vertex.coordinates, vertex.id, fontsize=8)
        self.axes.set(xlabel='x', ylabel='y', zlabel='z',
                      title=f'Вершин: {len(vertices)}, переходов: {len(graph.edges)}, редакция: {graph.revision}')
        self.axes.set_box_aspect((1, 1, 1))
        self.axes.view_init(*angles)
        self.axes.mouse_init(rotate_btn=1, zoom_btn=3)
        self.fit()
        self.canvas.draw_idle()

    def fit(self):
        positions = [v.coordinates for v in self.graph.vertices] or [(0, 0, 0)]
        spans = [max(p[a] for p in positions) - min(p[a] for p in positions) for a in range(3)]
        radius = max(max(spans) * .6, .5)
        for axis, setter in enumerate((self.axes.set_xlim3d, self.axes.set_ylim3d, self.axes.set_zlim3d)):
            center = (min(p[axis] for p in positions) + max(p[axis] for p in positions)) / 2
            setter(center - radius, center + radius)

    def reset(self):
        self.axes.view_init(elev=25, azim=-60)
        self.fit()
        self.canvas.draw_idle()

    def zoom(self, event):
        factor = .85 if event.button == 'up' else 1 / .85
        self.scale(factor)

    def scale(self, factor):
        for getter, setter in ((self.axes.get_xlim3d, self.axes.set_xlim3d),
                               (self.axes.get_ylim3d, self.axes.set_ylim3d),
                               (self.axes.get_zlim3d, self.axes.set_zlim3d)):
            low, high = getter()
            center, radius = (low + high) / 2, (high - low) * factor / 2
            setter(center - radius, center + radius)
        self.canvas.draw_idle()

    def pump(self):
        if self.alive:
            self.root.update_idletasks()
            self.root.update()

    def close(self):
        if self.alive:
            self.alive = False
            self.root.destroy()
