"""widgets — los dibujos de Centro.

Tres piezas, todas Gtk.DrawingArea con Cairo:

  Aguja    medidor circular. Sustituye a una fila de texto con un numero.
  Historia linea de los ultimos minutos.
  Curva    editor de curva de ventilador: los puntos SE ARRASTRAN.

Lo de la curva es el motivo de este fichero. Dibujarla y luego pedir los seis
numeros en una caja de texto era lo peor de los dos mundos: el usuario ve la
forma pero tiene que traducirla a numeros a mano para cambiarla.
"""
import math, collections, gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GObject

HISTORIA = 120


def _rgb(w):
    c = w.get_style_context().get_color()
    return c.red, c.green, c.blue


def _tinte(v, aviso, critico):
    """Verde -> ambar -> rojo. Los colores son los de Adwaita para que no
    desentone con el resto del escritorio."""
    if critico and v >= critico:
        return (0.88, 0.27, 0.25)
    if aviso and v >= aviso:
        return (0.96, 0.65, 0.14)
    return (0.30, 0.74, 0.47)


class Aguja(Gtk.DrawingArea):
    """Medidor circular con el valor dentro. Un vistazo basta: el color y lo
    lleno que esta el arco dicen si va bien, sin leer el numero."""

    def __init__(self, titulo, unidad="", maximo=100, aviso=None, critico=None):
        super().__init__()
        self.titulo, self.unidad, self.maximo = titulo, unidad, maximo
        self.aviso, self.critico = aviso, critico
        self.valor = None
        self.texto_alt = None
        self.set_content_width(112)
        self.set_content_height(118)
        self.set_draw_func(self._pintar)

    def poner(self, v, texto_alt=None):
        self.valor, self.texto_alt = v, texto_alt
        self.queue_draw()

    def _pintar(self, area, cr, w, h):
        r, g, b = _rgb(self)
        cx, cy = w / 2, h / 2 + 4
        rad = min(w, h) / 2 - 16
        ini, fin = math.radians(135), math.radians(405)

        cr.set_line_width(9)
        cr.set_line_cap(1)
        cr.set_source_rgba(r, g, b, 0.13)
        cr.arc(cx, cy, rad, ini, fin)
        cr.stroke()

        if self.valor is not None:
            frac = max(0.0, min(1.0, self.valor / self.maximo))
            cr.set_source_rgb(*_tinte(self.valor, self.aviso, self.critico))
            cr.arc(cx, cy, rad, ini, ini + (fin - ini) * frac)
            cr.stroke()

        txt = self.texto_alt if self.texto_alt else (
            f"{self.valor:.0f}" if self.valor is not None else "—")
        cr.select_font_face("sans", 0, 1)
        cr.set_font_size(26 if len(txt) <= 3 else 17)
        e = cr.text_extents(txt)
        cr.set_source_rgba(r, g, b, 0.95)
        cr.move_to(cx - e.width / 2 - e.x_bearing, cy + 4)
        cr.show_text(txt)

        if self.unidad and not self.texto_alt:
            cr.set_font_size(11)
            e2 = cr.text_extents(self.unidad)
            cr.set_source_rgba(r, g, b, 0.5)
            cr.move_to(cx - e2.width / 2, cy + 20)
            cr.show_text(self.unidad)

        cr.select_font_face("sans", 0, 0)
        cr.set_font_size(11)
        e3 = cr.text_extents(self.titulo)
        cr.set_source_rgba(r, g, b, 0.6)
        cr.move_to(cx - e3.width / 2, h - 2)
        cr.show_text(self.titulo)


class Historia(Gtk.DrawingArea):
    """Los ultimos minutos. El eje se ajusta a lo visto, no a un tope
    inventado, para que una subida pequeña tambien se note."""

    def __init__(self, maximo=100, aviso=None):
        super().__init__()
        self.datos = collections.deque(maxlen=HISTORIA)
        self.maximo, self.aviso = maximo, aviso
        self.set_content_height(52)
        self.set_hexpand(True)
        self.set_draw_func(self._pintar)

    def empujar(self, v):
        self.datos.append(v if v is not None else 0)
        self.queue_draw()

    def _pintar(self, area, cr, w, h):
        if len(self.datos) < 2:
            return
        r, g, b = _rgb(self)
        if self.aviso and self.datos[-1] >= self.aviso:
            r, g, b = 0.88, 0.27, 0.25
        tope = max(self.maximo * 0.25, max(self.datos) * 1.15)
        paso = w / (HISTORIA - 1)
        pts = [(i * paso, h - (v / tope) * h) for i, v in enumerate(self.datos)]
        d = w - pts[-1][0]
        pts = [(x + d, y) for x, y in pts]

        cr.move_to(pts[0][0], h)
        for x, y in pts:
            cr.line_to(x, y)
        cr.line_to(pts[-1][0], h)
        cr.close_path()
        cr.set_source_rgba(r, g, b, 0.15)
        cr.fill()
        cr.move_to(*pts[0])
        for x, y in pts[1:]:
            cr.line_to(x, y)
        cr.set_source_rgba(r, g, b, 0.9)
        cr.set_line_width(1.8)
        cr.stroke()


class Curva(Gtk.DrawingArea):
    """Editor de curva de ventilador. Los seis puntos se arrastran.

    Reglas del EC que la interfaz hace cumplir sola, para que no haya forma de
    guardar una curva invalida:
      - las temperaturas tienen que ir de menor a mayor
      - cada punto se mueve entre sus dos vecinos, nunca los adelanta
      - la velocidad no baja al subir la temperatura
    """

    __gsignals__ = {"cambiada": (GObject.SignalFlags.RUN_FIRST, None, ())}

    T_MIN, T_MAX = 35, 100
    MARGEN = 26

    def __init__(self):
        super().__init__()
        self.temps, self.velocs = [], []
        self.arrastrando = None
        self.encima = None
        self.set_content_height(190)
        # No baja de aqui: por debajo los puntos se pisan y no se pueden coger.
        self.set_size_request(240, 150)
        self.set_hexpand(True)
        self.set_draw_func(self._pintar)

        g = Gtk.GestureDrag()
        g.connect("drag-begin", self._inicio)
        g.connect("drag-update", self._mover)
        g.connect("drag-end", self._fin)
        self.add_controller(g)

        m = Gtk.EventControllerMotion()
        m.connect("motion", self._raton)
        m.connect("leave", lambda *_: (setattr(self, "encima", None), self.queue_draw()))
        self.add_controller(m)
        self.set_cursor(Gdk.Cursor.new_from_name("default"))

    # --- datos ---
    def poner(self, t, v):
        try:
            self.temps = [int(x) for x in str(t).split()]
            self.velocs = [int(x) for x in str(v).split()]
        except ValueError:
            self.temps, self.velocs = [], []
        self.queue_draw()

    def como_texto(self):
        return (" ".join(str(x) for x in self.temps),
                " ".join(str(x) for x in self.velocs))

    # --- geometria ---
    def _px(self, t, w):
        u = w - self.MARGEN * 2
        return self.MARGEN + (t - self.T_MIN) / (self.T_MAX - self.T_MIN) * u

    def _py(self, v, h):
        u = h - self.MARGEN * 2
        return self.MARGEN + u - (v / 100) * u

    def _temp(self, x, w):
        u = w - self.MARGEN * 2
        return self.T_MIN + (x - self.MARGEN) / u * (self.T_MAX - self.T_MIN)

    def _vel(self, y, h):
        u = h - self.MARGEN * 2
        return (1 - (y - self.MARGEN) / u) * 100

    def _cerca(self, x, y):
        w, h = self.get_width(), self.get_height()
        for i, (t, v) in enumerate(zip(self.temps, self.velocs)):
            if math.hypot(x - self._px(t, w), y - self._py(v, h)) < 20:
                return i
        return None

    # --- interaccion ---
    def _raton(self, ctrl, x, y):
        i = self._cerca(x, y)
        if i != self.encima:
            self.encima = i
            self.set_cursor(Gdk.Cursor.new_from_name("grab" if i is not None else "default"))
            self.queue_draw()

    def _inicio(self, g, x, y):
        self.arrastrando = self._cerca(x, y)
        if self.arrastrando is not None:
            self.set_cursor(Gdk.Cursor.new_from_name("grabbing"))

    def _mover(self, g, dx, dy):
        i = self.arrastrando
        if i is None:
            return
        ok, x0, y0 = g.get_start_point()
        if not ok:
            return
        w, h = self.get_width(), self.get_height()
        t = round(self._temp(x0 + dx, w))
        v = round(self._vel(y0 + dy, h) / 5) * 5      # la velocidad, de 5 en 5

        # Un punto nunca adelanta a sus vecinos: el EC exige temperaturas
        # crecientes, y una curva que baje al calentarse no tiene sentido.
        tmin = self.temps[i - 1] + 2 if i > 0 else self.T_MIN
        tmax = self.temps[i + 1] - 2 if i < len(self.temps) - 1 else self.T_MAX
        vmin = self.velocs[i - 1] if i > 0 else 0
        vmax = self.velocs[i + 1] if i < len(self.velocs) - 1 else 100

        self.temps[i] = max(tmin, min(tmax, t))
        self.velocs[i] = max(vmin, min(vmax, max(0, min(100, v))))
        self.queue_draw()

    def _fin(self, g, dx, dy):
        if self.arrastrando is not None:
            self.arrastrando = None
            self.set_cursor(Gdk.Cursor.new_from_name("grab"))
            self.emit("cambiada")

    # --- dibujo ---
    def _pintar(self, area, cr, w, h):
        if len(self.temps) != 6 or len(self.velocs) != 6:
            return
        r, g, b = _rgb(self)
        cr.select_font_face("sans", 0, 0)
        cr.set_font_size(10)

        # rejilla con las referencias que importan
        cr.set_line_width(1)
        for v in (0, 25, 50, 75, 100):
            y = self._py(v, h)
            cr.set_source_rgba(r, g, b, 0.08)
            cr.move_to(self.MARGEN, y); cr.line_to(w - self.MARGEN, y); cr.stroke()
            cr.set_source_rgba(r, g, b, 0.35)
            cr.move_to(4, y + 3); cr.show_text(f"{v}%")
        for t in (40, 55, 70, 85, 100):
            x = self._px(t, w)
            cr.set_source_rgba(r, g, b, 0.08)
            cr.move_to(x, self.MARGEN); cr.line_to(x, h - self.MARGEN); cr.stroke()
            cr.set_source_rgba(r, g, b, 0.35)
            e = cr.text_extents(f"{t}°")
            cr.move_to(x - e.width / 2, h - 8); cr.show_text(f"{t}°")

        pts = [(self._px(t, w), self._py(v, h)) for t, v in zip(self.temps, self.velocs)]
        izq = (self.MARGEN, pts[0][1])
        der = (w - self.MARGEN, pts[-1][1])
        todos = [izq] + pts + [der]

        cr.move_to(todos[0][0], h - self.MARGEN)
        for x, y in todos:
            cr.line_to(x, y)
        cr.line_to(todos[-1][0], h - self.MARGEN)
        cr.close_path()
        cr.set_source_rgba(0.30, 0.60, 0.95, 0.16)
        cr.fill()

        cr.move_to(*todos[0])
        for x, y in todos[1:]:
            cr.line_to(x, y)
        cr.set_source_rgba(0.40, 0.68, 1.0, 0.95)
        cr.set_line_width(2.4)
        cr.set_line_join(1)
        cr.stroke()

        for i, (x, y) in enumerate(pts):
            activo = i in (self.encima, self.arrastrando)
            cr.set_source_rgba(0.40, 0.68, 1.0, 1)
            cr.arc(x, y, 8 if activo else 5.5, 0, 6.2832)
            cr.fill()
            cr.set_source_rgba(0.10, 0.11, 0.13, 1)
            cr.arc(x, y, 3.2 if activo else 2.2, 0, 6.2832)
            cr.fill()
            if activo:
                et = f"{self.temps[i]}°  {self.velocs[i]}%"
                cr.set_font_size(11)
                e = cr.text_extents(et)
                bx, by = x - e.width / 2 - 6, y - 30
                cr.set_source_rgba(0.10, 0.11, 0.13, 0.92)
                cr.rectangle(bx, by, e.width + 12, 20)
                cr.fill()
                cr.set_source_rgba(0.95, 0.95, 0.95, 1)
                cr.move_to(bx + 6, by + 14)
                cr.show_text(et)
